# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Loop Engine V2
--------------------------------------
Semantic deduplication + research queue hygiene.

V1'de aynı konu için farklı cümlelerle birden fazla aktif görev
oluşabiliyordu. V2 bunu task fingerprint üzerinden engeller.

Amaç:
    Brain validation durumlarından gerçek araştırma ihtiyacını
    üretmek ve aynı araştırma işini tek queue item olarak tutmak.

DEĞİŞEN ANA NOKTA
-----------------
V2 bir "semantic fingerprint" üretir:

    task_type
    + learned_rule_id
    + validation_id
    + context

aynıysa aktif duplicate görev oluşturmaz.

Bazı görev tiplerinde daha geniş fingerprint kullanılır:

    WEAK_HOLDOUT_REVIEW
        -> learned_rule_id + context

    VALIDATED_RULE_RECHECK
        -> learned_rule_id + context

    METHOD_VARIANT_COMPARISON
        -> symbol + market + timeframe + condition

Böylece sadece question cümlesinin farklı olması yeni task üretmez.

ÖNEMLİ
------
- Ham experiment/result verileri değiştirilmez.
- learned_rules değiştirilmez.
- validation kayıtları değiştirilmez.
- Mevcut queue kayıtları silinmez.
- Sadece yeni duplicate üretimi engellenir.
- V1'in eski duplicate kayıtları otomatik silinmez; bu nedenle mevcut
  queue sayısı aynı kalabilir.
- Research Agent daha sonra bu queue'yu tüketebilir.

Çalıştırma:
    python agents/brain_research_loop_engine_v2.py
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_LOOP_ENGINE"
ENGINE_VERSION = "V2"

PRIORITY_HIGH = 10
PRIORITY_MEDIUM = 7
PRIORITY_LOW = 4

STABILITY_POSITIVE_RATE_DROP = 0.10
STABILITY_AVG20_RATIO = 0.70


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_hash(*parts: Any) -> str:
    raw = "|".join(normalize(x) for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# INDEXES
# ---------------------------------------------------------------------------

def ensure_queue_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_research_queue_status_priority
        ON brain_research_queue(status, priority)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_research_queue_target_claim
        ON brain_research_queue(target_claim_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_research_queue_question
        ON brain_research_queue(question)
        """
    )


# ---------------------------------------------------------------------------
# LOAD VALIDATIONS
# ---------------------------------------------------------------------------

def load_validations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                v.id AS validation_id,
                v.learned_rule_id,
                v.validation_type,
                v.verdict,

                v.reference_sample_size,
                v.holdout_sample_size,

                v.reference_positive_rate,
                v.holdout_positive_rate,

                v.reference_average_return_20d,
                v.holdout_average_return_20d,

                v.positive_rate_delta,
                v.average_return_20d_ratio,
                v.split_date,

                r.method_name,
                r.method_type,
                r.symbol,
                r.market,
                r.timeframe,
                r.condition_name,
                r.sample_size,
                r.success_rate,
                r.average_return_20d,
                r.confidence

            FROM brain_rule_validations v
            JOIN learned_rules r
              ON r.id = v.learned_rule_id

            ORDER BY v.id
            """
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# CLAIM LINK
# ---------------------------------------------------------------------------

def claim_id_for_rule(
    conn: sqlite3.Connection,
    learned_rule_id: int,
) -> int | None:
    row = conn.execute(
        """
        SELECT source_claim_id
        FROM brain_learning_events
        WHERE
            learned_rule_id = ?
            AND source_claim_id IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (learned_rule_id,),
    ).fetchone()

    if row and row["source_claim_id"] is not None:
        return int(row["source_claim_id"])

    return None


# ---------------------------------------------------------------------------
# TASK FINGERPRINT
# ---------------------------------------------------------------------------

def context_fingerprint(row: sqlite3.Row) -> str:
    return stable_hash(
        normalize(row["symbol"]).upper(),
        normalize(row["market"]).upper(),
        normalize(row["timeframe"]).lower(),
        normalize(row["condition_name"]).lower(),
    )


def task_fingerprint(
    task_type: str,
    row: sqlite3.Row,
) -> str:
    task_type = normalize(task_type).upper()

    if task_type in {
        "WEAK_HOLDOUT_REVIEW",
        "INSUFFICIENT_DATA_RESEARCH",
        "VALIDATED_RULE_RECHECK",
    }:
        return (
            "task:"
            + stable_hash(
                task_type,
                int(row["learned_rule_id"]),
                context_fingerprint(row),
            )
        )

    if task_type == "METHOD_VARIANT_COMPARISON":
        return (
            "task:"
            + stable_hash(
                task_type,
                normalize(row["symbol"]).upper(),
                normalize(row["market"]).upper(),
                normalize(row["timeframe"]).lower(),
                normalize(row["condition_name"]).lower(),
            )
        )

    return (
        "task:"
        + stable_hash(
            task_type,
            int(row["learned_rule_id"]),
            int(row["validation_id"]),
        )
    )


# ---------------------------------------------------------------------------
# ACTIVE DUPLICATE CHECK
# ---------------------------------------------------------------------------

def active_fingerprint_exists(
    conn: sqlite3.Connection,
    fingerprint: str,
) -> bool:
    """
    Öncelik metadata_json içindeki fingerprint'te.

    Eski V1 task'larında fingerprint olmayabileceği için question,
    target_claim_id ve diğer alanlarla fallback kontrolleri de yapılır.
    """

    row = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE
            status IN ('queued', 'working')
            AND metadata_json LIKE ?
        LIMIT 1
        """,
        (f'%"task_fingerprint":"{fingerprint}"%',),
    ).fetchone()

    return row is not None


def active_claim_task_exists(
    conn: sqlite3.Connection,
    target_claim_id: int | None,
    task_type: str,
) -> bool:
    if target_claim_id is None:
        return False

    row = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE
            status IN ('queued', 'working')
            AND target_claim_id = ?
            AND metadata_json LIKE ?
        LIMIT 1
        """,
        (
            target_claim_id,
            f'%"task_type":"{task_type}"%',
        ),
    ).fetchone()

    return row is not None


# ---------------------------------------------------------------------------
# TASK BUILDERS
# ---------------------------------------------------------------------------

def build_weak_task(
    row: sqlite3.Row,
) -> tuple[str, str, int, str]:
    question = (
        "Re-evaluate weak learned rule: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['condition_name'])}"
    )

    reason = (
        "HOLDOUT_WEAK detected. "
        f"holdout_n={safe_int(row['holdout_sample_size'])}; "
        f"holdout_positive_rate="
        f"{safe_float(row['holdout_positive_rate']):.4f}; "
        f"holdout_average_return_20d="
        f"{safe_float(row['holdout_average_return_20d']):.4f}; "
        f"positive_rate_delta="
        f"{safe_float(row['positive_rate_delta']):+.4f}; "
        f"average_return_20d_ratio="
        f"{row['average_return_20d_ratio']}."
    )

    priority = (
        PRIORITY_HIGH
        if (
            safe_float(row["holdout_positive_rate"]) < 0.50
            or safe_float(row["holdout_average_return_20d"]) < -1.0
        )
        else PRIORITY_MEDIUM
    )

    return (
        question,
        reason,
        priority,
        "WEAK_HOLDOUT_REVIEW",
    )


def build_insufficient_task(
    row: sqlite3.Row,
) -> tuple[str, str, int, str]:
    question = (
        "Collect more evidence before evaluating learned rule: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['condition_name'])}"
    )

    reason = (
        "Validation returned INSUFFICIENT_DATA. "
        f"holdout_n={safe_int(row['holdout_sample_size'])}; "
        f"reference_n={safe_int(row['reference_sample_size'])}."
    )

    return (
        question,
        reason,
        PRIORITY_MEDIUM,
        "INSUFFICIENT_DATA_RESEARCH",
    )


def build_stability_task(
    row: sqlite3.Row,
) -> tuple[str, str, int, str] | None:
    delta = safe_float(row["positive_rate_delta"])

    ratio_raw = row["average_return_20d_ratio"]

    try:
        ratio = float(ratio_raw) if ratio_raw is not None else None
    except (TypeError, ValueError):
        ratio = None

    unstable = delta <= -STABILITY_POSITIVE_RATE_DROP

    if ratio is not None:
        unstable = unstable or ratio < STABILITY_AVG20_RATIO

    if not unstable:
        return None

    question = (
        "Recheck stability of validated candidate under changing conditions: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['condition_name'])}"
    )

    reason = (
        "HOLDOUT_PASS but meaningful degradation detected. "
        f"positive_rate_delta={delta:+.4f}; "
        f"average_return_20d_ratio="
        f"{ratio if ratio is not None else 'NA'}."
    )

    return (
        question,
        reason,
        PRIORITY_LOW,
        "VALIDATED_RULE_RECHECK",
    )


def build_variant_task(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> tuple[str, str, int, str] | None:
    count_row = conn.execute(
        """
        SELECT COUNT(*)
        FROM learned_rules
        WHERE
            symbol = ?
            AND market = ?
            AND timeframe = ?
            AND condition_name = ?
        """,
        (
            normalize(row["symbol"]),
            normalize(row["market"]),
            normalize(row["timeframe"]),
            normalize(row["condition_name"]),
        ),
    ).fetchone()

    count = safe_int(count_row[0] if count_row else 0)

    if count <= 1:
        return None

    question = (
        "Compare method variants for same learned-rule context: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['market'])} | "
        f"{normalize(row['timeframe'])} | "
        f"{normalize(row['condition_name'])}"
    )

    reason = (
        f"{count} learned rule variants share the same context. "
        "Check whether they represent the same underlying pattern "
        "or materially different evidence."
    )

    return (
        question,
        reason,
        PRIORITY_LOW,
        "METHOD_VARIANT_COMPARISON",
    )


# ---------------------------------------------------------------------------
# ENQUEUE
# ---------------------------------------------------------------------------

def enqueue_task(
    conn: sqlite3.Connection,
    *,
    row: sqlite3.Row,
    task_type: str,
    question: str,
    reason: str,
    priority: int,
    target_claim_id: int | None,
) -> tuple[bool, str]:
    fingerprint = task_fingerprint(
        task_type,
        row,
    )

    if active_fingerprint_exists(
        conn,
        fingerprint,
    ):
        return False, "fingerprint_duplicate"

    if active_claim_task_exists(
        conn,
        target_claim_id,
        task_type,
    ):
        return False, "claim_task_duplicate"

    now = utc_now()

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "task_type": task_type,
        "task_fingerprint": fingerprint,
        "validation_id": int(row["validation_id"]),
        "learned_rule_id": int(row["learned_rule_id"]),
        "target_claim_id": target_claim_id,
        "symbol": normalize(row["symbol"]),
        "market": normalize(row["market"]),
        "timeframe": normalize(row["timeframe"]),
        "method_name": normalize(row["method_name"]),
        "condition_name": normalize(row["condition_name"]),
        "validation_verdict": normalize(row["verdict"]),
        "holdout_sample_size": safe_int(row["holdout_sample_size"]),
        "holdout_positive_rate": safe_float(
            row["holdout_positive_rate"]
        ),
        "holdout_average_return_20d": safe_float(
            row["holdout_average_return_20d"]
        ),
    }

    conn.execute(
        """
        INSERT INTO brain_research_queue (
            question,
            reason,
            priority,
            target_node_id,
            target_claim_id,
            status,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, NULL, ?, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            int(priority),
            target_claim_id,
            now,
            now,
            compact_json(metadata),
        ),
    )

    return True, "created"


# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_queue_indexes(conn)

        validations = load_validations(conn)

        weak_created = 0
        insufficient_created = 0
        stability_created = 0
        variant_created = 0

        fingerprint_duplicates = 0
        claim_duplicates = 0

        candidate_tasks_seen = 0

        for row in validations:
            target_claim_id = claim_id_for_rule(
                conn,
                int(row["learned_rule_id"]),
            )

            # ---------------------------------------------------------------
            # WEAK HOLDOUT
            # ---------------------------------------------------------------
            if normalize(row["verdict"]).upper() == "HOLDOUT_WEAK":
                (
                    question,
                    reason,
                    priority,
                    task_type,
                ) = build_weak_task(row)

                candidate_tasks_seen += 1

                created, why = enqueue_task(
                    conn=conn,
                    row=row,
                    task_type=task_type,
                    question=question,
                    reason=reason,
                    priority=priority,
                    target_claim_id=target_claim_id,
                )

                if created:
                    weak_created += 1
                elif why == "fingerprint_duplicate":
                    fingerprint_duplicates += 1
                elif why == "claim_task_duplicate":
                    claim_duplicates += 1

            # ---------------------------------------------------------------
            # INSUFFICIENT DATA
            # ---------------------------------------------------------------
            elif normalize(row["verdict"]).upper() == "INSUFFICIENT_DATA":
                (
                    question,
                    reason,
                    priority,
                    task_type,
                ) = build_insufficient_task(row)

                candidate_tasks_seen += 1

                created, why = enqueue_task(
                    conn=conn,
                    row=row,
                    task_type=task_type,
                    question=question,
                    reason=reason,
                    priority=priority,
                    target_claim_id=target_claim_id,
                )

                if created:
                    insufficient_created += 1
                elif why == "fingerprint_duplicate":
                    fingerprint_duplicates += 1
                elif why == "claim_task_duplicate":
                    claim_duplicates += 1

            # ---------------------------------------------------------------
            # PASS STABILITY
            # ---------------------------------------------------------------
            elif normalize(row["verdict"]).upper() == "HOLDOUT_PASS":
                stability = build_stability_task(row)

                if stability:
                    (
                        question,
                        reason,
                        priority,
                        task_type,
                    ) = stability

                    candidate_tasks_seen += 1

                    created, why = enqueue_task(
                        conn=conn,
                        row=row,
                        task_type=task_type,
                        question=question,
                        reason=reason,
                        priority=priority,
                        target_claim_id=target_claim_id,
                    )

                    if created:
                        stability_created += 1
                    elif why == "fingerprint_duplicate":
                        fingerprint_duplicates += 1
                    elif why == "claim_task_duplicate":
                        claim_duplicates += 1

            # ---------------------------------------------------------------
            # METHOD VARIANT COMPARISON
            # ---------------------------------------------------------------
            variant = build_variant_task(
                conn,
                row,
            )

            if variant:
                (
                    question,
                    reason,
                    priority,
                    task_type,
                ) = variant

                candidate_tasks_seen += 1

                created, why = enqueue_task(
                    conn=conn,
                    row=row,
                    task_type=task_type,
                    question=question,
                    reason=reason,
                    priority=priority,
                    target_claim_id=target_claim_id,
                )

                if created:
                    variant_created += 1
                elif why == "fingerprint_duplicate":
                    fingerprint_duplicates += 1
                elif why == "claim_task_duplicate":
                    claim_duplicates += 1

        conn.commit()

        total_new = (
            weak_created
            + insufficient_created
            + stability_created
            + variant_created
        )

        active_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            """
        ).fetchone()[0]

        print("=" * 76)
        print("MARKETHQ BRAIN RESEARCH LOOP ENGINE V2")
        print("=" * 76)
        print()
        print(f"Database : {DB_PATH}")
        print(f"Engine   : {ENGINE_NAME}")
        print(f"Version  : {ENGINE_VERSION}")
        print()
        print("RESEARCH LOOP V2 RUN")
        print("-" * 76)
        print(f"validations_seen                     {len(validations)}")
        print(f"candidate_tasks_seen                 {candidate_tasks_seen}")
        print(f"weak_holdout_tasks_created           {weak_created}")
        print(f"insufficient_data_tasks_created      {insufficient_created}")
        print(f"stability_recheck_tasks_created      {stability_created}")
        print(f"variant_comparison_tasks_created     {variant_created}")
        print(f"fingerprint_duplicates_skipped       {fingerprint_duplicates}")
        print(f"claim_duplicates_skipped             {claim_duplicates}")
        print(f"total_new_tasks                      {total_new}")
        print()
        print("ACTIVE RESEARCH QUEUE")
        print("-" * 76)
        print(f"queued_or_working                    {safe_int(active_count)}")
        print()

        print("ACTIVE QUEUE")
        print("-" * 76)

        active_rows = conn.execute(
            """
            SELECT
                id,
                priority,
                status,
                question,
                reason
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            ORDER BY priority DESC, id ASC
            LIMIT 20
            """
        ).fetchall()

        if not active_rows:
            print("No active research tasks.")
        else:
            for item in active_rows:
                print(
                    f"[priority={safe_int(item['priority']):2d}] "
                    f"{normalize(item['status'])} | "
                    f"id={item['id']}"
                )
                print(f"  Q: {item['question']}")
                print(f"  R: {item['reason']}")
                print()

        print("IMPORTANT")
        print("-" * 76)
        print("- V2 aynı araştırma konusunun farklı soru cümleleriyle")
        print("  tekrar kuyruğa girmesini engeller.")
        print("- Eski V1 duplicate queue kayıtları otomatik silinmez.")
        print("- Queue kaydı araştırmanın yapıldığı anlamına gelmez.")
        print("- Ham experiment/result, learned_rules ve validation kayıtları")
        print("  değiştirilmedi.")
        print("- Sonraki aşama: Research Agent / source discovery / knowledge ingest.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()
