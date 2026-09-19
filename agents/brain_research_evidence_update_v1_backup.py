# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Evidence Update Engine V1
-------------------------------------------------
Evidence Review
    ↓
Brain update / provenance / research priority

AMAÇ
----
brain_research_evidence_reviews tablosundaki AI evidence review sonuçlarını
Brain'in mevcut katmanlarına kontrollü şekilde yansıtmak.

Bu motor:
    - observation değiştirmez
    - learned_rules değiştirmez
    - brain_claims değiştirmez
    - validations değiştirmez
    - raw experiment/result değiştirmez
    - research knowledge'ı verified yapmaz

Yalnızca ayrı bir update/audit tablosu ve gerekiyorsa
brain_research_queue kaydı oluşturur.

VERDICTS
--------
SUPPORTIVE
    -> research evidence alignment olumlu
    -> review sonucu brain audit'e yazılır
    -> sonraki recheck önceliği düşük/normal

PARTIALLY_SUPPORTIVE
    -> research ile observation kısmen uyumlu
    -> yeni "verified" statüsü verilmez
    -> ek bağımsız araştırma sorusu queue'ya alınır

CONTRADICTORY
    -> contradiction/review önceliği yükseltilir
    -> yeni research task oluşturulur

INSUFFICIENT
    -> evidence gap research task oluşturulur

Ayrı tablo:
    brain_research_brain_updates

Ayrıca research queue dedup kontrolü yapılır.

Çalıştırma:
    python agents/brain_research_evidence_update_v1.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_EVIDENCE_UPDATE"
ENGINE_VERSION = "V1"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_json(raw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(
            norm(raw) or "{}"
        )
        return (
            obj
            if isinstance(obj, dict)
            else {}
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return {}


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA busy_timeout = 60000"
    )
    conn.execute(
        "PRAGMA foreign_keys = ON"
    )
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_update_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_research_brain_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            review_id INTEGER NOT NULL,
            knowledge_item_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,

            verdict TEXT NOT NULL,
            action TEXT NOT NULL,

            research_priority INTEGER NOT NULL DEFAULT 0,
            queue_task_id INTEGER,

            brain_effect TEXT NOT NULL,

            metadata_json TEXT,

            created_at TEXT NOT NULL,

            UNIQUE (review_id)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_review
        ON brain_research_brain_updates(review_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_observation
        ON brain_research_brain_updates(observation_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_action
        ON brain_research_brain_updates(action)
        """
    )


# ---------------------------------------------------------------------------
# LOAD REVIEWS
# ---------------------------------------------------------------------------

def load_unprocessed_reviews(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                r.id,
                r.knowledge_item_id,
                r.observation_id,
                r.verdict,
                r.score,
                r.evidence_alignment,
                r.contradiction_flag,
                r.review_method,
                r.review_text,
                r.next_question,
                r.metadata_json,
                r.created_at,

                ki.title AS knowledge_title,
                ki.method AS knowledge_method,
                ki.metadata_json AS knowledge_metadata,

                o.symbol,
                o.method_name,
                o.market,
                o.timeframe,
                o.market_regime,
                o.volume_state,
                o.volatility_state,
                o.sample_size,
                o.confidence AS observation_confidence,
                o.status AS observation_status

            FROM brain_research_evidence_reviews r

            JOIN knowledge_items ki
              ON ki.id=r.knowledge_item_id

            JOIN brain_observations o
              ON o.id=r.observation_id

            LEFT JOIN brain_research_brain_updates u
              ON u.review_id=r.id

            WHERE u.id IS NULL

            ORDER BY
                CASE
                    WHEN r.verdict='CONTRADICTORY' THEN 1
                    WHEN r.verdict='INSUFFICIENT' THEN 2
                    WHEN r.verdict='PARTIALLY_SUPPORTIVE' THEN 3
                    WHEN r.verdict='SUPPORTIVE' THEN 4
                    ELSE 5
                END,
                r.score ASC,
                r.id ASC

            LIMIT 50
            """
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# ACTION POLICY
# ---------------------------------------------------------------------------

def action_for_verdict(
    verdict: str,
) -> tuple[str, int, str]:
    verdict = norm(
        verdict
    ).upper()

    if verdict == "SUPPORTIVE":
        return (
            "RECORD_SUPPORT",
            3,
            (
                "Research knowledge is aligned with the linked "
                "historical observation, but verification state "
                "remains unchanged."
            ),
        )

    if verdict == "PARTIALLY_SUPPORTIVE":
        return (
            "QUEUE_INDEPENDENT_RECHECK",
            6,
            (
                "Research and observation are partially aligned; "
                "additional independent evidence is needed."
            ),
        )

    if verdict == "CONTRADICTORY":
        return (
            "QUEUE_CONTRADICTION_RESEARCH",
            9,
            (
                "Research evidence indicates a contradiction or "
                "conflict requiring focused research."
            ),
        )

    if verdict == "INSUFFICIENT":
        return (
            "QUEUE_EVIDENCE_GAP_RESEARCH",
            8,
            (
                "Available evidence is insufficient for a strong "
                "judgment; additional evidence is required."
            ),
        )

    return (
        "QUEUE_REVIEW",
        5,
        "Unknown verdict requires manual research review.",
    )


# ---------------------------------------------------------------------------
# QUEUE DEDUP
# ---------------------------------------------------------------------------

def queue_exists_for_review(
    conn: sqlite3.Connection,
    review_id: int,
) -> int | None:
    marker = (
        f'"review_id":{review_id}'
    )

    row = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE metadata_json LIKE ?
          AND status IN ('queued', 'working')
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            f"%{marker}%",
        ),
    ).fetchone()

    if row:
        return safe_int(
            row["id"]
        )

    return None


# ---------------------------------------------------------------------------
# CREATE RESEARCH TASK
# ---------------------------------------------------------------------------

def create_research_task(
    conn: sqlite3.Connection,
    review: sqlite3.Row,
    action: str,
    priority: int,
) -> int | None:
    """
    PARTIAL / CONTRADICTORY / INSUFFICIENT durumlarında
    kontrollü bir research task üretir.
    SUPPORTIVE için yeni queue açılmaz.
    """

    if action == "RECORD_SUPPORT":
        return None

    existing = queue_exists_for_review(
        conn,
        safe_int(review["id"]),
    )

    if existing:
        return existing

    verdict = norm(
        review["verdict"]
    )

    symbol = norm(
        review["symbol"]
    )

    method = norm(
        review["method_name"]
    )

    market = norm(
        review["market"]
    )

    timeframe = norm(
        review["timeframe"]
    )

    next_question = norm(
        review["next_question"]
    )

    if action == "QUEUE_CONTRADICTION_RESEARCH":
        question = (
            "Investigate contradiction: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    elif action == "QUEUE_EVIDENCE_GAP_RESEARCH":
        question = (
            "Collect additional evidence: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    else:
        question = (
            "Recheck research finding independently: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    if next_question:
        question = (
            question
            + " | "
            + next_question[:700]
        )

    reason = (
        "Generated from brain evidence review. "
        f"review_id={safe_int(review['id'])}; "
        f"verdict={verdict}; "
        f"score={safe_float(review['score']):.4f}; "
        f"observation_id={safe_int(review['observation_id'])}; "
        f"knowledge_item_id={safe_int(review['knowledge_item_id'])}. "
        "This is a research task, not a live trading instruction."
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "task_role": "research_followup",
        "review_id": safe_int(
            review["id"]
        ),
        "knowledge_item_id": safe_int(
            review["knowledge_item_id"]
        ),
        "observation_id": safe_int(
            review["observation_id"]
        ),
        "verdict": verdict,
        "score": safe_float(
            review["score"]
        ),
        "task_type": (
            "CONTRADICTION_RESEARCH"
            if action
            == "QUEUE_CONTRADICTION_RESEARCH"
            else (
                "INSUFFICIENT_DATA_RESEARCH"
                if action
                == "QUEUE_EVIDENCE_GAP_RESEARCH"
                else "VALIDATED_RULE_RECHECK"
            )
        ),
        "symbol": symbol,
        "method_name": method,
        "market": market,
        "timeframe": timeframe,
        "generated_from_evidence_review": True,
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
        VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            priority,
            utc_now(),
            utc_now(),
            compact_json(
                metadata
            ),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# WRITE UPDATE
# ---------------------------------------------------------------------------

def update_exists(
    conn: sqlite3.Connection,
    review_id: int,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM brain_research_brain_updates
            WHERE review_id=?
            LIMIT 1
            """,
            (review_id,),
        ).fetchone()
        is not None
    )


def write_update(
    conn: sqlite3.Connection,
    review: sqlite3.Row,
    action: str,
    priority: int,
    brain_effect: str,
    queue_task_id: int | None,
) -> int:
    review_id = safe_int(
        review["id"]
    )

    if update_exists(
        conn,
        review_id,
    ):
        existing = conn.execute(
            """
            SELECT id
            FROM brain_research_brain_updates
            WHERE review_id=?
            LIMIT 1
            """,
            (review_id,),
        ).fetchone()

        return safe_int(
            existing["id"]
        )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "review_method": norm(
            review["review_method"]
        ),
        "review_score": safe_float(
            review["score"]
        ),
        "contradiction_flag": safe_int(
            review["contradiction_flag"]
        ),
        "knowledge_item_id": safe_int(
            review["knowledge_item_id"]
        ),
        "observation_id": safe_int(
            review["observation_id"]
        ),
        "queue_task_id": queue_task_id,
        "verification_changed": False,
        "brain_effect": brain_effect,
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_brain_updates (
            review_id,
            knowledge_item_id,
            observation_id,
            verdict,
            action,
            research_priority,
            queue_task_id,
            brain_effect,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            safe_int(
                review["knowledge_item_id"]
            ),
            safe_int(
                review["observation_id"]
            ),
            norm(
                review["verdict"]
            ),
            action,
            priority,
            queue_task_id,
            brain_effect,
            compact_json(
                metadata
            ),
            utc_now(),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        required = (
            "brain_research_evidence_reviews",
            "brain_research_observation_links",
            "brain_research_queue",
            "knowledge_items",
            "brain_observations",
        )

        for table in required:
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: "
                    + table
                )

        ensure_update_table(
            conn
        )

        reviews = load_unprocessed_reviews(
            conn
        )

        processed = 0
        supportive = 0
        partial = 0
        contradictory = 0
        insufficient = 0
        queue_created = 0
        queue_existing = 0
        errors = 0

        for review in reviews:
            review_id = safe_int(
                review["id"]
            )

            try:
                verdict = norm(
                    review["verdict"]
                ).upper()

                (
                    action,
                    priority,
                    brain_effect,
                ) = action_for_verdict(
                    verdict
                )

                queue_task_id = (
                    create_research_task(
                        conn,
                        review,
                        action,
                        priority,
                    )
                )

                if (
                    action
                    != "RECORD_SUPPORT"
                    and queue_task_id is not None
                ):
                    existing_marker = queue_exists_for_review(
                        conn,
                        review_id,
                    )

                    if (
                        existing_marker is not None
                        and existing_marker
                        != queue_task_id
                    ):
                        queue_existing += 1
                    else:
                        queue_created += 1

                update_id = write_update(
                    conn,
                    review,
                    action,
                    priority,
                    brain_effect,
                    queue_task_id,
                )

                conn.commit()

                processed += 1

                if verdict == "SUPPORTIVE":
                    supportive += 1
                elif verdict == "PARTIALLY_SUPPORTIVE":
                    partial += 1
                elif verdict == "CONTRADICTORY":
                    contradictory += 1
                elif verdict == "INSUFFICIENT":
                    insufficient += 1

                print(
                    f"UPDATED | "
                    f"review={review_id} | "
                    f"{norm(review['symbol'])} | "
                    f"{verdict} | "
                    f"action={action} | "
                    f"priority={priority} | "
                    f"queue={queue_task_id} | "
                    f"update={update_id}"
                )

            except Exception as exc:
                errors += 1
                conn.rollback()

                print(
                    f"ERROR | "
                    f"review={review_id} | "
                    f"{type(exc).__name__}: {exc}"
                )

        total_updates = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_brain_updates
            """
        ).fetchone()[0]

        active_research_queue = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            """
        ).fetchone()[0]

        print()
        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH EVIDENCE UPDATE ENGINE V1"
        )
        print("=" * 76)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            f"Engine   : {ENGINE_NAME}"
        )
        print(
            f"Version  : {ENGINE_VERSION}"
        )
        print()
        print("BRAIN UPDATE RUN")
        print("-" * 76)
        print(
            "reviews_seen                           "
            f"{len(reviews)}"
        )
        print(
            "reviews_processed                      "
            f"{processed}"
        )
        print(
            "supportive                             "
            f"{supportive}"
        )
        print(
            "partially_supportive                   "
            f"{partial}"
        )
        print(
            "contradictory                          "
            f"{contradictory}"
        )
        print(
            "insufficient                           "
            f"{insufficient}"
        )
        print(
            "queue_tasks_created                    "
            f"{queue_created}"
        )
        print(
            "queue_tasks_existing                   "
            f"{queue_existing}"
        )
        print(
            "errors                                 "
            f"{errors}"
        )
        print()
        print(
            "total_brain_research_updates           "
            f"{safe_int(total_updates)}"
        )
        print(
            "active_research_queue                  "
            f"{safe_int(active_research_queue)}"
        )

        print()
        print("RECENT BRAIN UPDATES")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                u.id,
                u.review_id,
                u.knowledge_item_id,
                u.observation_id,
                u.verdict,
                u.action,
                u.research_priority,
                u.queue_task_id,
                o.symbol,
                o.method_name
            FROM brain_research_brain_updates u
            JOIN brain_observations o
              ON o.id=u.observation_id
            ORDER BY u.id DESC
            LIMIT 10
            """
        ).fetchall()

        if not recent:
            print(
                "No brain updates."
            )
        else:
            for row in recent:
                print(
                    f"update_id={row['id']} | "
                    f"review={row['review_id']} | "
                    f"{norm(row['symbol'])} | "
                    f"{norm(row['verdict'])} | "
                    f"{norm(row['action'])} | "
                    f"priority={safe_int(row['research_priority'])} | "
                    f"queue={row['queue_task_id']}"
                )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Evidence review sonucu verified rule durumuna çevrilmedi.")
        print("- Observation / learned_rules / claims / validations değişmedi.")
        print("- Partial/contradictory/insufficient review'lar follow-up")
        print("  research task'larına dönüşebilir.")
        print("- Supportive review yalnızca audit/provenance olarak tutulur.")
        print("- Research queue görevleri tarihsel araştırma içindir.")
        print("- Sonraki aşama: follow-up research -> new knowledge/observation")
        print("  ve zamanla learning loop.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()
