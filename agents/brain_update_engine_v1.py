# -*- coding: utf-8 -*-
"""
MarketHQ Brain Update Engine V1
-------------------------------
Rule Validation -> Brain State Update

Amaç:
    brain_rule_validations sonuçlarını Brain'in kalıcı node/edge
    katmanına yansıtmak.

Bu motor:
    - learned_rules kayıtlarını silmez/değiştirmez.
    - brain_claims kayıtlarını doğrulanmış claim'e dönüştürmez.
    - ham experiment / result verilerine dokunmaz.
    - validation sonucuna göre learned-rule Brain node'unu:
          validated_candidate
          review_required
      durumlarından biriyle günceller.
    - validation status concept node'ları oluşturur.
    - Rule -> status ilişkisini brain_edges içine yazar.
    - HOLDOUT_WEAK kurallar için research queue girdisi oluşturur.
    - brain_learning_events.created_node_id / created_edge_id alanlarını
      mümkün olduğunca doldurur.
    - Aynı update tekrar çalıştırıldığında duplicate edge/queue üretmez.

EPISTEMIC SINIR:
    validated_candidate != verified rule
    HOLDOUT_PASS yalnızca mevcut tarihsel temporal holdout kontrolünün
    geçtiğini ifade eder.

Akış:
    learned_rule
         ↓
    brain_rule_validation
         ↓
    BRAIN UPDATE
      ├── validated_candidate
      └── review_required
         ↓
    brain_nodes / brain_edges
         ↓
    research_queue (gerektiğinde)

Çalıştırma:
    python agents/brain_update_engine_v1.py
"""

from __future__ import annotations

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

ENGINE_NAME = "MARKETHQ_BRAIN_UPDATE_ENGINE"
ENGINE_VERSION = "V1"

VALIDATED_CANDIDATE_STATUS = "validated_candidate"
REVIEW_REQUIRED_STATUS = "review_required"

PASS_VERDICT = "HOLDOUT_PASS"
WEAK_VERDICT = "HOLDOUT_WEAK"
INSUFFICIENT_VERDICT = "INSUFFICIENT_DATA"


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
# SCHEMA / INDEXES
# ---------------------------------------------------------------------------

def ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_nodes_type_status
        ON brain_nodes(node_type, status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_edges_relation
        ON brain_edges(relation)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_research_queue_claim
        ON brain_research_queue(target_claim_id)
        """
    )


# ---------------------------------------------------------------------------
# LOAD VALIDATIONS
# ---------------------------------------------------------------------------

def load_validations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = conn.execute(
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
            v.holdout_best_return_20d,
            v.holdout_worst_return_20d,
            v.positive_rate_delta,
            v.average_return_20d_ratio,
            v.split_date,
            v.rationale,

            r.method_name,
            r.method_type,
            r.symbol,
            r.market,
            r.timeframe,
            r.condition_name,
            r.sample_size,
            r.success_rate,
            r.average_return_20d,
            r.confidence,
            r.observation

        FROM brain_rule_validations v
        JOIN learned_rules r
          ON r.id = v.learned_rule_id

        ORDER BY v.id
        """
    ).fetchall()

    return list(rows)


# ---------------------------------------------------------------------------
# BRAIN NODES
# ---------------------------------------------------------------------------

def get_or_create_node(
    conn: sqlite3.Connection,
    node_key: str,
    node_type: str,
    canonical_name: str,
    summary: str,
    confidence: float,
    status: str,
    metadata: dict[str, Any],
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM brain_nodes
        WHERE node_key = ?
        """,
        (node_key,),
    ).fetchone()

    now = utc_now()

    if existing:
        conn.execute(
            """
            UPDATE brain_nodes
            SET
                node_type = ?,
                canonical_name = ?,
                summary = ?,
                confidence = ?,
                status = ?,
                last_seen_at = ?,
                updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                node_type,
                canonical_name,
                summary,
                confidence,
                status,
                now,
                now,
                compact_json(metadata),
                int(existing["id"]),
            ),
        )
        return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO brain_nodes (
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            status,
            first_seen_at,
            last_seen_at,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            status,
            now,
            now,
            compact_json(metadata),
            now,
            now,
        ),
    )

    return int(cur.lastrowid)


def rule_node(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    brain_status: str,
) -> int:
    rule_id = int(row["learned_rule_id"])

    # Learned rule node-key'i deterministic.
    node_key = f"learned_rule:{rule_id}"

    # Validation gücü, holdout sonuçlarına göre Brain node confidence
    # için yalnızca bir durum sinyali olarak kullanılır.
    holdout_pos = safe_float(row["holdout_positive_rate"])
    holdout_avg20 = safe_float(row["holdout_average_return_20d"])

    confidence = min(
        1.0,
        max(
            0.0,
            0.5
            + 0.3 * max(0.0, min(1.0, holdout_pos))
            + 0.2 * max(0.0, min(1.0, holdout_avg20 / 10.0))
        ),
    )

    summary = (
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['condition_name'])}"
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "learned_rule_id": rule_id,
        "validation_id": int(row["validation_id"]),
        "validation_verdict": normalize(row["verdict"]),
        "validation_type": normalize(row["validation_type"]),
        "holdout_sample_size": safe_int(row["holdout_sample_size"]),
        "holdout_positive_rate": holdout_pos,
        "holdout_average_return_20d": holdout_avg20,
        "positive_rate_delta": safe_float(row["positive_rate_delta"]),
        "average_return_20d_ratio": row["average_return_20d_ratio"],
        "brain_status": brain_status,
        "epistemic_note": (
            "validated_candidate is a research-memory state, "
            "not a verified rule"
        ),
    }

    return get_or_create_node(
        conn=conn,
        node_key=node_key,
        node_type="learned_rule",
        canonical_name=f"Learned Rule #{rule_id}",
        summary=summary,
        confidence=confidence,
        status=brain_status,
        metadata=metadata,
    )


def status_node(
    conn: sqlite3.Connection,
    status_key: str,
) -> int:
    configs = {
        VALIDATED_CANDIDATE_STATUS: (
            "status:validated_candidate",
            "VALIDATED_CANDIDATE",
            "Temporal holdout kontrolünü geçen araştırma kuralı adayı.",
            0.70,
        ),
        REVIEW_REQUIRED_STATUS: (
            "status:review_required",
            "REVIEW_REQUIRED",
            "Validation sonucu zayıf veya belirsiz; yeniden araştırma gerekiyor.",
            0.40,
        ),
    }

    node_key, name, summary, confidence = configs[status_key]

    return get_or_create_node(
        conn=conn,
        node_key=node_key,
        node_type="concept",
        canonical_name=name,
        summary=summary,
        confidence=confidence,
        status="active",
        metadata={
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "semantic": status_key,
        },
    )


# ---------------------------------------------------------------------------
# EDGE
# ---------------------------------------------------------------------------

def edge_exists(
    conn: sqlite3.Connection,
    source_node_id: int,
    relation: str,
    target_node_id: int,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM brain_edges
        WHERE
            source_node_id = ?
            AND relation = ?
            AND target_node_id = ?
        LIMIT 1
        """,
        (
            source_node_id,
            relation,
            target_node_id,
        ),
    ).fetchone()

    return row is not None


def create_edge(
    conn: sqlite3.Connection,
    source_node_id: int,
    relation: str,
    target_node_id: int,
    confidence: float,
    metadata: dict[str, Any],
) -> tuple[int | None, bool]:
    if edge_exists(
        conn,
        source_node_id,
        relation,
        target_node_id,
    ):
        row = conn.execute(
            """
            SELECT id
            FROM brain_edges
            WHERE
                source_node_id = ?
                AND relation = ?
                AND target_node_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                source_node_id,
                relation,
                target_node_id,
            ),
        ).fetchone()

        return (
            int(row["id"]) if row else None,
            False,
        )

    now = utc_now()

    cur = conn.execute(
        """
        INSERT INTO brain_edges (
            source_node_id,
            relation,
            target_node_id,
            confidence,
            valid_from,
            valid_to,
            observed_at,
            status,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, NULL, NULL, ?, 'active', ?, ?, ?)
        """,
        (
            source_node_id,
            relation,
            target_node_id,
            confidence,
            now,
            compact_json(metadata),
            now,
            now,
        ),
    )

    return int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# RESEARCH QUEUE
# ---------------------------------------------------------------------------

def ensure_research_task(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> bool:
    verdict = normalize(row["verdict"])

    if verdict == PASS_VERDICT:
        return False

    question = (
        "Re-evaluate weak learned rule: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['condition_name'])}"
    )

    reason = (
        f"validation_id={int(row['validation_id'])}; "
        f"rule_id={int(row['learned_rule_id'])}; "
        f"verdict={verdict}; "
        f"holdout_sample={safe_int(row['holdout_sample_size'])}; "
        f"holdout_positive_rate={safe_float(row['holdout_positive_rate']):.4f}; "
        f"holdout_avg20={safe_float(row['holdout_average_return_20d']):.4f}"
    )

    existing = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE
            target_node_id = ?
            AND status IN ('queued', 'working')
        LIMIT 1
        """,
        (
            int(row["learned_rule_id"]),
        ),
    ).fetchone()

    # learned_rule_id target_node_id olarak kullanmak şematik olarak
    # ideal değildir; doğru Brain node id'si ayrıca metadata'da tutulur.
    # Bu fonksiyonun ana duplicate kontrolünü question ile de yapıyoruz.
    if existing:
        return False

    existing_question = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE
            question = ?
            AND status IN ('queued', 'working')
        LIMIT 1
        """,
        (question,),
    ).fetchone()

    if existing_question:
        return False

    now = utc_now()

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
        VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            8,
            now,
            now,
            compact_json(
                {
                    "engine": ENGINE_NAME,
                    "engine_version": ENGINE_VERSION,
                    "validation_id": int(row["validation_id"]),
                    "learned_rule_id": int(row["learned_rule_id"]),
                    "verdict": verdict,
                }
            ),
        ),
    )

    return True


# ---------------------------------------------------------------------------
# LEARNING EVENT LINK
# ---------------------------------------------------------------------------

def attach_update_to_learning_event(
    conn: sqlite3.Connection,
    validation_id: int,
    node_id: int,
    edge_id: int | None,
) -> int:
    """
    Rule validation sırasında oluşturulmuş en son RULE_VALIDATION event'ini
    bulur ve Brain update node/edge bağlantılarını doldurur.

    brain_learning_events.created_node_id / created_edge_id alanları
    mevcut schema'nın history/audit amacıyla kullanılır.
    """

    rows = conn.execute(
        """
        SELECT id
        FROM brain_learning_events
        WHERE
            event_type = 'RULE_VALIDATION'
            AND metadata_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            f'%"validation_id":{validation_id}%',
        ),
    ).fetchall()

    if not rows:
        # Validation event bulunamazsa yeni update event oluştur.
        cur = conn.execute(
            """
            INSERT INTO brain_learning_events (
                event_type,
                experiment_id,
                experiment_result_id,
                learned_rule_id,
                source_claim_id,
                created_node_id,
                created_edge_id,
                score,
                decision,
                created_at,
                metadata_json
            )
            VALUES (
                'BRAIN_UPDATE',
                NULL,
                NULL,
                NULL,
                NULL,
                ?,
                ?,
                NULL,
                'BRAIN_UPDATED',
                ?,
                ?
            )
            """,
            (
                node_id,
                edge_id,
                utc_now(),
                compact_json(
                    {
                        "engine": ENGINE_NAME,
                        "engine_version": ENGINE_VERSION,
                        "validation_id": validation_id,
                        "created_node_id": node_id,
                        "created_edge_id": edge_id,
                    }
                ),
            ),
        )

        return int(cur.lastrowid)

    event_id = int(rows[0]["id"])

    conn.execute(
        """
        UPDATE brain_learning_events
        SET
            created_node_id = COALESCE(?, created_node_id),
            created_edge_id = COALESCE(?, created_edge_id)
        WHERE id = ?
        """,
        (
            node_id,
            edge_id,
            event_id,
        ),
    )

    return event_id


# ---------------------------------------------------------------------------
# STATUS DECISION
# ---------------------------------------------------------------------------

def brain_status_for(verdict: str) -> str:
    verdict = normalize(verdict).upper()

    if verdict == PASS_VERDICT:
        return VALIDATED_CANDIDATE_STATUS

    return REVIEW_REQUIRED_STATUS


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    validations_seen: int,
    nodes_updated: int,
    edges_created: int,
    research_tasks_queued: int,
    pass_count: int,
    weak_count: int,
    insufficient_count: int,
) -> None:
    print("=" * 76)
    print("MARKETHQ BRAIN UPDATE ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("BRAIN UPDATE RUN")
    print("-" * 76)
    print(f"validations_seen                     {validations_seen}")
    print(f"brain_rule_nodes_updated             {nodes_updated}")
    print(f"status_edges_created                 {edges_created}")
    print(f"research_tasks_queued                {research_tasks_queued}")
    print(f"holdout_pass_applied                 {pass_count}")
    print(f"holdout_weak_applied                 {weak_count}")
    print(f"insufficient_data_applied            {insufficient_count}")
    print()

    status_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM brain_nodes
        WHERE node_type = 'learned_rule'
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()

    print("LEARNED RULE BRAIN STATUS")
    print("-" * 76)

    if status_rows:
        for row in status_rows:
            print(f"{row['status']:35s} {row['n']}")
    else:
        print("No learned_rule Brain nodes.")

    print()

    queue_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        """
    ).fetchone()[0]

    print("ACTIVE RESEARCH QUEUE")
    print("-" * 76)
    print(f"queued_or_working                     {queue_count}")
    print()

    print("UPDATED RULES")
    print("-" * 76)

    rows = conn.execute(
        """
        SELECT
            v.learned_rule_id,
            v.verdict,
            v.holdout_sample_size,
            v.holdout_positive_rate,
            v.holdout_average_return_20d,
            r.symbol,
            r.method_name,
            r.condition_name,
            n.status
        FROM brain_rule_validations v
        JOIN learned_rules r
          ON r.id = v.learned_rule_id
        JOIN brain_nodes n
          ON n.node_key = ('learned_rule:' || v.learned_rule_id)
        ORDER BY
            CASE v.verdict
                WHEN 'HOLDOUT_PASS' THEN 1
                WHEN 'HOLDOUT_WEAK' THEN 2
                ELSE 3
            END,
            v.learned_rule_id
        """
    ).fetchall()

    if not rows:
        print("No rule updates.")
    else:
        for row in rows:
            print(
                f"rule_id={row['learned_rule_id']} | "
                f"brain_status={row['status']} | "
                f"{row['verdict']} | "
                f"holdout_n={safe_int(row['holdout_sample_size'])} | "
                f"pos={safe_float(row['holdout_positive_rate']):.3f} | "
                f"avg20={safe_float(row['holdout_average_return_20d']):.4f}"
            )
            print(
                f"  {normalize(row['symbol'])} | "
                f"{normalize(row['method_name'])} | "
                f"{normalize(row['condition_name'])}"
            )
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- HOLDOUT_PASS -> validated_candidate Brain durumu.")
    print("- validated_candidate != VERIFIED RULE.")
    print("- HOLDOUT_WEAK / INSUFFICIENT_DATA -> review_required.")
    print("- Weak/insufficient rule'lar research queue'ya yönlendirilir.")
    print("- learned_rules tablosunun içeriği bu motor tarafından değiştirilmedi.")
    print("- brain_claims doğrulanmış hale getirilmedi.")
    print("- Ham experiment/result kayıtları değiştirilmedi.")
    print("- Sonraki aşama: AI review / research loop / stronger validation.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_indexes(conn)

        validations = load_validations(conn)

        nodes_updated = 0
        edges_created = 0
        research_tasks_queued = 0

        pass_count = 0
        weak_count = 0
        insufficient_count = 0

        for row in validations:
            verdict = normalize(row["verdict"]).upper()
            brain_status = brain_status_for(verdict)

            if verdict == PASS_VERDICT:
                pass_count += 1
            elif verdict == WEAK_VERDICT:
                weak_count += 1
            else:
                insufficient_count += 1

            rule_node_id = rule_node(
                conn,
                row,
                brain_status,
            )
            nodes_updated += 1

            target_status = status_node(
                conn,
                brain_status,
            )

            relation = (
                "VALIDATED_AS_CANDIDATE"
                if brain_status == VALIDATED_CANDIDATE_STATUS
                else "REQUIRES_REVIEW"
            )

            edge_id, created = create_edge(
                conn=conn,
                source_node_id=rule_node_id,
                relation=relation,
                target_node_id=target_status,
                confidence=(
                    safe_float(row["holdout_positive_rate"])
                    if verdict == PASS_VERDICT
                    else 0.40
                ),
                metadata={
                    "engine": ENGINE_NAME,
                    "engine_version": ENGINE_VERSION,
                    "validation_id": int(row["validation_id"]),
                    "learned_rule_id": int(row["learned_rule_id"]),
                    "verdict": verdict,
                    "holdout_sample_size": safe_int(
                        row["holdout_sample_size"]
                    ),
                    "holdout_positive_rate": safe_float(
                        row["holdout_positive_rate"]
                    ),
                    "holdout_average_return_20d": safe_float(
                        row["holdout_average_return_20d"]
                    ),
                },
            )

            if created:
                edges_created += 1

            if verdict != PASS_VERDICT:
                if ensure_research_task(
                    conn,
                    row,
                ):
                    research_tasks_queued += 1

            attach_update_to_learning_event(
                conn,
                validation_id=int(row["validation_id"]),
                node_id=rule_node_id,
                edge_id=edge_id,
            )

        conn.commit()

        print_summary(
            conn=conn,
            validations_seen=len(validations),
            nodes_updated=nodes_updated,
            edges_created=edges_created,
            research_tasks_queued=research_tasks_queued,
            pass_count=pass_count,
            weak_count=weak_count,
            insufficient_count=insufficient_count,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

