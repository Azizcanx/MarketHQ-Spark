# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Recovery Engine V1
-----------------------------------------
Geçmiş Research Agent V1 çıktılarındaki UNKNOWN / yanlış tüketilmiş
research task'larını güvenli biçimde yeniden kuyruğa alır.

AMAÇ
----
Önceki Research Agent V1 yanlışlıkla priority=9 olan legacy
RULE_PROMOTION_REVIEW görevlerini ve bazı gerçek weak task'larını
işledi. Sonuçlar UNKNOWN research episode olarak kalmış olabilir.

Bu motor:
    1) brain_episodes içindeki research_agent_result kayıtlarını tarar.
    2) İçeriğinde UNKNOWN / eski promotion review izi bulunanları bulur.
    3) İlgili queue task'ını veya validation/rule bağını çözer.
    4) Yalnızca gerçek araştırılması gereken:
         WEAK_HOLDOUT_REVIEW
         INSUFFICIENT_DATA_RESEARCH
         VALIDATED_RULE_RECHECK
         METHOD_VARIANT_COMPARISON
       görevlerini yeniden "queued" yapar.
    5) Legacy RULE_PROMOTION_REVIEW görevlerini yeniden kuyruğa koymaz.
    6) Eski episode'ları silmez.
    7) Yeni duplicate queue görevi üretmez.

Çalıştırma:
    python agents/brain_research_recovery_engine_v1.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_RECOVERY_ENGINE"
ENGINE_VERSION = "V1"

REAL_TASK_TYPES = {
    "WEAK_HOLDOUT_REVIEW",
    "INSUFFICIENT_DATA_RESEARCH",
    "VALIDATED_RULE_RECHECK",
    "METHOD_VARIANT_COMPARISON",
}

UNKNOWN_MARKERS = (
    "UNKNOWN",
    "OPENAI_EMPTY_RESPONSE",
    "OPENAI_CALL_FAILED",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_metadata(raw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(normalize(raw) or "{}")
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# TASK TYPE
# ---------------------------------------------------------------------------

def task_type_from_values(
    question: str,
    metadata_raw: str,
) -> str:
    metadata = parse_metadata(metadata_raw)

    value = normalize(metadata.get("task_type")).upper()
    if value:
        return value

    q = normalize(question).lower()

    if q.startswith("rule promotion review:"):
        return "RULE_PROMOTION_REVIEW"

    if q.startswith("re-evaluate weak learned rule:"):
        return "WEAK_HOLDOUT_REVIEW"

    if q.startswith("why did the learned rule weaken"):
        return "WEAK_HOLDOUT_REVIEW"

    if q.startswith("collect more evidence"):
        return "INSUFFICIENT_DATA_RESEARCH"

    if q.startswith("recheck stability"):
        return "VALIDATED_RULE_RECHECK"

    if q.startswith("compare method variants"):
        return "METHOD_VARIANT_COMPARISON"

    return "GENERIC"


# ---------------------------------------------------------------------------
# EPISODE INSPECTION
# ---------------------------------------------------------------------------

def load_research_episodes(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                id,
                source_table,
                source_id,
                source_key,
                title,
                content,
                content_hash,
                observed_at,
                ingested_at,
                metadata_json
            FROM brain_episodes
            WHERE episode_type = 'research_agent_result'
            ORDER BY id
            """
        ).fetchall()
    )


def episode_is_unknown(row: sqlite3.Row) -> bool:
    content = normalize(row["content"]).upper()
    title = normalize(row["title"]).upper()
    metadata = normalize(row["metadata_json"]).upper()

    combined = "\n".join(
        (content, title, metadata)
    )

    return any(
        marker in combined
        for marker in UNKNOWN_MARKERS
    )


# ---------------------------------------------------------------------------
# QUEUE LOOKUP
# ---------------------------------------------------------------------------

def load_queue_task(
    conn: sqlite3.Connection,
    queue_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            id,
            question,
            reason,
            priority,
            target_node_id,
            target_claim_id,
            status,
            metadata_json
        FROM brain_research_queue
        WHERE id = ?
        LIMIT 1
        """,
        (queue_id,),
    ).fetchone()


def metadata_queue_id(
    episode: sqlite3.Row,
) -> int | None:
    metadata = parse_metadata(
        episode["metadata_json"]
    )

    value = metadata.get("queue_id")
    parsed = safe_int(value, 0)

    if parsed > 0:
        return parsed

    if episode["source_table"] == "brain_research_queue":
        parsed = safe_int(
            episode["source_id"],
            0,
        )
        if parsed > 0:
            return parsed

    return None


# ---------------------------------------------------------------------------
# CONTEXT RESOLUTION
# ---------------------------------------------------------------------------

def claim_id_for_rule(
    conn: sqlite3.Connection,
    learned_rule_id: int,
) -> int | None:
    if not table_exists(
        conn,
        "brain_rule_promotion_events",
    ):
        return None

    row = conn.execute(
        """
        SELECT source_claim_id
        FROM brain_rule_promotion_events
        WHERE
            learned_rule_id = ?
            AND source_claim_id IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (learned_rule_id,),
    ).fetchone()

    if row and row["source_claim_id"] is not None:
        value = safe_int(
            row["source_claim_id"],
            0,
        )
        return value if value > 0 else None

    return None


def validation_for_rule(
    conn: sqlite3.Connection,
    learned_rule_id: int,
) -> sqlite3.Row | None:
    if not table_exists(
        conn,
        "brain_rule_validations",
    ):
        return None

    return conn.execute(
        """
        SELECT
            v.*,
            r.method_name,
            r.symbol,
            r.market,
            r.timeframe,
            r.condition_name
        FROM brain_rule_validations v
        JOIN learned_rules r
          ON r.id = v.learned_rule_id
        WHERE v.learned_rule_id = ?
        ORDER BY v.id DESC
        LIMIT 1
        """,
        (learned_rule_id,),
    ).fetchone()


def parse_rule_id_from_text(
    text: str,
) -> int | None:
    match = re.search(
        r"rule_id\s*=\s*(\d+)",
        normalize(text),
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def resolve_learned_rule_id(
    conn: sqlite3.Connection,
    queue: sqlite3.Row | None,
    episode: sqlite3.Row,
) -> int | None:
    if queue is not None:
        metadata = parse_metadata(
            queue["metadata_json"]
        )

        for key in (
            "learned_rule_id",
            "rule_id",
        ):
            parsed = safe_int(
                metadata.get(key),
                0,
            )
            if parsed > 0:
                return parsed

    metadata = parse_metadata(
        episode["metadata_json"]
    )

    for key in (
        "learned_rule_id",
        "rule_id",
    ):
        parsed = safe_int(
            metadata.get(key),
            0,
        )
        if parsed > 0:
            return parsed

    parsed = parse_rule_id_from_text(
        queue["reason"]
        if queue is not None
        else ""
    )
    if parsed:
        return parsed

    parsed = parse_rule_id_from_text(
        episode["content"]
    )
    if parsed:
        return parsed

    # Eski weak task'larında queue metadata'da rule_id bulunuyorsa
    # yukarıdaki yollar zaten çözer.
    return None


# ---------------------------------------------------------------------------
# TASK RECONSTRUCTION
# ---------------------------------------------------------------------------

def reconstruct_task_from_validation(
    conn: sqlite3.Connection,
    rule_id: int,
) -> tuple[
    str,
    str,
    int,
    str,
    int | None,
] | None:
    validation = validation_for_rule(
        conn,
        rule_id,
    )

    if validation is None:
        return None

    verdict = normalize(
        validation["verdict"]
    ).upper()

    symbol = normalize(
        validation["symbol"]
    )
    method = normalize(
        validation["method_name"]
    )
    condition = normalize(
        validation["condition_name"]
    )

    target_claim_id = claim_id_for_rule(
        conn,
        rule_id,
    )

    if verdict == "HOLDOUT_WEAK":
        question = (
            "Re-evaluate weak learned rule: "
            f"{symbol} | {method} | {condition}"
        )

        reason = (
            "Recovered from invalid/UNKNOWN research result. "
            "Original validation was HOLDOUT_WEAK. "
            f"rule_id={rule_id}; "
            f"validation_id={safe_int(validation['id'])}; "
            f"holdout_n={safe_int(validation['holdout_sample_size'])}; "
            f"holdout_positive_rate="
            f"{float(validation['holdout_positive_rate'] or 0):.4f}; "
            f"holdout_avg20="
            f"{float(validation['holdout_average_return_20d'] or 0):.4f}"
        )

        return (
            question,
            reason,
            8,
            "WEAK_HOLDOUT_REVIEW",
            target_claim_id,
        )

    if verdict == "INSUFFICIENT_DATA":
        question = (
            "Collect more evidence before evaluating learned rule: "
            f"{symbol} | {method} | {condition}"
        )

        reason = (
            "Recovered from invalid/UNKNOWN research result. "
            "Original validation was INSUFFICIENT_DATA. "
            f"rule_id={rule_id}"
        )

        return (
            question,
            reason,
            7,
            "INSUFFICIENT_DATA_RESEARCH",
            target_claim_id,
        )

    if verdict == "HOLDOUT_PASS":
        question = (
            "Recheck stability of validated candidate under changing conditions: "
            f"{symbol} | {method} | {condition}"
        )

        reason = (
            "Recovered from invalid/UNKNOWN research result. "
            "Original validation was HOLDOUT_PASS. "
            f"rule_id={rule_id}"
        )

        return (
            question,
            reason,
            4,
            "VALIDATED_RULE_RECHECK",
            target_claim_id,
        )

    return None


# ---------------------------------------------------------------------------
# DUPLICATE CHECK
# ---------------------------------------------------------------------------

def active_task_same_rule(
    conn: sqlite3.Connection,
    rule_id: int,
) -> bool:
    rows = conn.execute(
        """
        SELECT metadata_json
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        """
    ).fetchall()

    needle = str(rule_id)

    for row in rows:
        metadata = normalize(
            row["metadata_json"]
        )
        if (
            f'"learned_rule_id":{needle}'
            in metadata
        ):
            return True

    return False


def active_task_same_claim(
    conn: sqlite3.Connection,
    claim_id: int | None,
) -> bool:
    if claim_id is None:
        return False

    row = conn.execute(
        """
        SELECT 1
        FROM brain_research_queue
        WHERE
            status IN ('queued', 'working')
            AND target_claim_id = ?
        LIMIT 1
        """,
        (claim_id,),
    ).fetchone()

    return row is not None


# ---------------------------------------------------------------------------
# REQUEUE
# ---------------------------------------------------------------------------

def requeue_existing_task(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    task_type_value: str,
    rule_id: int | None,
) -> None:
    metadata = parse_metadata(
        row["metadata_json"]
    )

    metadata["research_recovery"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "requeued_invalid_research_result",
        "recovered_at": utc_now(),
        "task_type": task_type_value,
        "learned_rule_id": rule_id,
    }

    metadata.setdefault(
        "task_type",
        task_type_value,
    )

    if rule_id:
        metadata["learned_rule_id"] = rule_id

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            status = 'queued',
            updated_at = ?,
            metadata_json = ?
        WHERE id = ?
        """,
        (
            utc_now(),
            compact_json(metadata),
            int(row["id"]),
        ),
    )


def create_recovered_task(
    conn: sqlite3.Connection,
    *,
    question: str,
    reason: str,
    priority: int,
    task_type_value: str,
    target_claim_id: int | None,
    rule_id: int,
) -> int:
    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "task_type": task_type_value,
        "learned_rule_id": rule_id,
        "target_claim_id": target_claim_id,
        "recovered_from_invalid_episode": True,
        "created_at": utc_now(),
    }

    cur = conn.execute(
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
            priority,
            target_claim_id,
            utc_now(),
            utc_now(),
            compact_json(metadata),
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        required = (
            "brain_episodes",
            "brain_research_queue",
            "brain_rule_validations",
            "learned_rules",
        )

        for table in required:
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    f"Gerekli tablo bulunamadı: {table}"
                )

        episodes = load_research_episodes(
            conn
        )

        unknown_found = 0
        tasks_recovered = 0
        tasks_created = 0
        promotion_skipped = 0
        already_active = 0
        unresolved = 0

        processed_queue_ids: set[int] = set()

        for episode in episodes:
            if not episode_is_unknown(episode):
                continue

            unknown_found += 1

            queue_id = metadata_queue_id(
                episode
            )

            queue = (
                load_queue_task(
                    conn,
                    queue_id,
                )
                if queue_id is not None
                else None
            )

            ttype = (
                task_type_from_values(
                    queue["question"],
                    queue["metadata_json"],
                )
                if queue is not None
                else ""
            )

            # Legacy promotion review -> ASLA tekrar kuyruğa alma.
            if ttype == "RULE_PROMOTION_REVIEW":
                promotion_skipped += 1
                continue

            rule_id = resolve_learned_rule_id(
                conn,
                queue,
                episode,
            )

            if rule_id is None:
                unresolved += 1
                continue

            reconstructed = reconstruct_task_from_validation(
                conn,
                rule_id,
            )

            if reconstructed is None:
                unresolved += 1
                continue

            (
                question,
                reason,
                priority,
                recovered_type,
                claim_id,
            ) = reconstructed

            if recovered_type not in REAL_TASK_TYPES:
                unresolved += 1
                continue

            if queue is not None:
                if int(queue["id"]) in processed_queue_ids:
                    continue

                if active_task_same_rule(
                    conn,
                    rule_id,
                ):
                    already_active += 1
                    continue

                if (
                    claim_id is not None
                    and active_task_same_claim(
                        conn,
                        claim_id,
                    )
                ):
                    already_active += 1
                    continue

                requeue_existing_task(
                    conn,
                    queue,
                    task_type_value=recovered_type,
                    rule_id=rule_id,
                )

                # Question / reason da eski legacy ise düzelt.
                conn.execute(
                    """
                    UPDATE brain_research_queue
                    SET
                        question = ?,
                        reason = ?,
                        priority = ?,
                        target_claim_id = COALESCE(?, target_claim_id)
                    WHERE id = ?
                    """,
                    (
                        question,
                        reason,
                        priority,
                        claim_id,
                        int(queue["id"]),
                    ),
                )

                processed_queue_ids.add(
                    int(queue["id"])
                )
                tasks_recovered += 1
                continue

            if (
                active_task_same_rule(
                    conn,
                    rule_id,
                )
            ):
                already_active += 1
                continue

            if (
                claim_id is not None
                and active_task_same_claim(
                    conn,
                    claim_id,
                )
            ):
                already_active += 1
                continue

            create_recovered_task(
                conn,
                question=question,
                reason=reason,
                priority=priority,
                task_type_value=recovered_type,
                target_claim_id=claim_id,
                rule_id=rule_id,
            )
            tasks_created += 1

        conn.commit()

        active_now = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            """
        ).fetchone()[0]

        print("=" * 76)
        print("MARKETHQ BRAIN RESEARCH RECOVERY ENGINE V1")
        print("=" * 76)
        print()
        print(f"Database : {DB_PATH}")
        print(f"Engine   : {ENGINE_NAME}")
        print(f"Version  : {ENGINE_VERSION}")
        print()
        print("RECOVERY RUN")
        print("-" * 76)
        print(f"unknown_episodes_found                {unknown_found}")
        print(f"existing_tasks_recovered              {tasks_recovered}")
        print(f"new_tasks_created                     {tasks_created}")
        print(f"already_active_skipped                {already_active}")
        print(f"legacy_promotion_skipped              {promotion_skipped}")
        print(f"unresolved_unknowns                   {unresolved}")
        print(f"active_queue_now                      {safe_int(active_now)}")
        print()

        print("RECOVERED ACTIVE QUEUE")
        print("-" * 76)

        rows = conn.execute(
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

        if not rows:
            print("No active research tasks.")
        else:
            for row in rows:
                print(
                    f"[priority={safe_int(row['priority']):2d}] "
                    f"{normalize(row['status'])} | "
                    f"id={row['id']}"
                )
                print(f"  Q: {normalize(row['question'])}")
                print(f"  R: {normalize(row['reason'])}")
                print()

        print("IMPORTANT")
        print("-" * 76)
        print("- UNKNOWN research episode'ları silinmedi.")
        print("- Legacy promotion review görevleri yeniden kuyruğa alınmadı.")
        print("- Weak/insufficient gerçek araştırma görevleri yeniden açıldı.")
        print("- Ham experiment/result ve learned_rules kayıtları değişmedi.")
        print("- Sonraki adım: Research Agent V2 ile gerçek task'ları işlemek.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

