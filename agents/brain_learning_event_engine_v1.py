# -*- coding: utf-8 -*-
"""
MarketHQ Brain Learning Event Engine V1
---------------------------------------
Evaluation -> Learning Event -> Rule Promotion Candidate

Amaç:
    brain_claim_evaluations sonuçlarını Brain'in öğrenme olaylarına
    dönüştürmek ve yalnızca yeterli koşulları sağlayan claim'leri
    "learned rule promotion candidate" olarak işaretlemek.

ÖNEMLİ:
    - Ham experiment / experiment_result kayıtlarına dokunmaz.
    - Mevcut claim/evaluation kayıtlarını silmez veya bozmaz.
    - Otomatik olarak canlı işlem / emir üretmez.
    - "learned rule candidate" ile "verified rule" ayrımını korur.
    - Mevcut learned_rules tablosuna doğrudan körlemesine yazmaz.
    - Her karar brain_learning_events içinde izlenebilir tutulur.
    - İleride AI reviewer'lar ikinci bir değerlendirme katmanı olabilir.

Akış:
    CLAIM
      ↓
    EVALUATION
      ↓
    LEARNING EVENT
      ↓
    PROMOTE_TO_RULE_CANDIDATE / HOLD / REJECT
      ↓
    sonraki aşamada rule promotion + brain update

Promotion politikası V1:
    PROMOTE_TO_RULE_CANDIDATE:
        verdict == SUPPORTIVE
        sample >= 250
        evidence >= 1
        score >= 0.75
        positive_rate >= 0.65
        average_return_20d >= 5.0

    HOLD_FOR_REVIEW:
        verdict == PROMISING
        veya
        SUPPORTIVE olup yukarıdaki promotion şartlarından biri eksik

    REJECT_FOR_LEARNING:
        verdict == NEEDS_REVIEW / WEAK

NOT:
    "PROMOTE_TO_RULE_CANDIDATE", doğrulanmış learned rule değildir.
    Bir sonraki rule promotion katmanı bağımsız doğrulama / uygunluk
    kontrolleri yapmalıdır.

Çalıştırma:
    python agents/brain_learning_event_engine_v1.py
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

ENGINE_NAME = "MARKETHQ_BRAIN_LEARNING_EVENT_ENGINE"
ENGINE_VERSION = "V1"

# Rule promotion candidate thresholds.
PROMOTE_MIN_SCORE = 0.75
PROMOTE_MIN_SAMPLE = 250
PROMOTE_MIN_EVIDENCE = 1
PROMOTE_MIN_POSITIVE_RATE = 0.65
PROMOTE_MIN_AVG20 = 5.0

# A strong/supportive claim that misses one promotion condition
# is held for review instead of rejected.
PROMOTE_VERDICT = "SUPPORTIVE"


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
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_learning_event_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_learning_events_exp
        ON brain_learning_events(experiment_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_learning_events_result
        ON brain_learning_events(experiment_result_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_learning_events_rule
        ON brain_learning_events(learned_rule_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_learning_events_claim
        ON brain_learning_events(source_claim_id)
        """
    )


# ---------------------------------------------------------------------------
# DATA LOAD
# ---------------------------------------------------------------------------

def load_evaluations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Evaluation + claim + observation.

    brain_claim_evaluations tablosunun V1 şeması esas alınır.
    """

    rows = conn.execute(
        """
        SELECT
            e.id AS evaluation_id,
            e.evaluation_key,
            e.claim_id,
            e.observation_id,
            e.evaluation_type,
            e.verdict,
            e.score,
            e.sample_score,
            e.confidence_score,
            e.positive_rate_score,
            e.return_score,
            e.evidence_score,
            e.consistency_score,
            e.sample_size,
            e.positive_rate,
            e.average_return_20d,
            e.evidence_count,
            e.source_count,
            e.consistency_count,
            e.rationale,
            e.metadata_json AS evaluation_metadata,
            e.created_at AS evaluation_created_at,
            e.updated_at AS evaluation_updated_at,

            c.claim_key,
            c.claim_text,
            c.claim_type,
            c.status AS claim_status,
            c.confidence AS claim_confidence,

            o.observation_key,
            o.method_name,
            o.symbol,
            o.market,
            o.timeframe,
            o.market_regime,
            o.volume_state,
            o.volatility_state,
            o.first_observation_date,
            o.last_observation_date

        FROM brain_claim_evaluations e
        JOIN brain_claims c
          ON c.id = e.claim_id
        LEFT JOIN brain_observations o
          ON o.id = e.observation_id

        ORDER BY e.id
        """
    ).fetchall()

    return list(rows)


# ---------------------------------------------------------------------------
# PROMOTION DECISION
# ---------------------------------------------------------------------------

def promotion_decision(row: sqlite3.Row) -> tuple[str, str]:
    verdict = normalize(row["verdict"]).upper()
    score = safe_float(row["score"])
    sample = safe_int(row["sample_size"])
    evidence = safe_int(row["evidence_count"])
    positive_rate = safe_float(row["positive_rate"])
    avg20 = safe_float(row["average_return_20d"])

    if verdict == "SUPPORTIVE":
        passed = (
            score >= PROMOTE_MIN_SCORE
            and sample >= PROMOTE_MIN_SAMPLE
            and evidence >= PROMOTE_MIN_EVIDENCE
            and positive_rate >= PROMOTE_MIN_POSITIVE_RATE
            and avg20 >= PROMOTE_MIN_AVG20
        )

        if passed:
            return (
                "PROMOTE_TO_RULE_CANDIDATE",
                (
                    "supportive claim satisfies all V1 rule-promotion "
                    "candidate thresholds"
                ),
            )

        return (
            "HOLD_FOR_REVIEW",
            (
                "supportive claim is strong but does not satisfy all "
                "promotion thresholds"
            ),
        )

    if verdict == "PROMISING":
        return (
            "HOLD_FOR_REVIEW",
            "promising claim requires stronger evidence before promotion",
        )

    if verdict in {"NEEDS_REVIEW", "WEAK"}:
        return (
            "REJECT_FOR_LEARNING",
            f"evaluation verdict is {verdict}",
        )

    return (
        "HOLD_FOR_REVIEW",
        f"unknown evaluation verdict: {verdict}",
    )


# ---------------------------------------------------------------------------
# EVENT WRITE
# ---------------------------------------------------------------------------

def write_learning_event(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> tuple[int, bool]:
    decision, decision_reason = promotion_decision(row)

    evaluation_id = int(row["evaluation_id"])
    claim_id = int(row["claim_id"])
    observation_id = safe_int(row["observation_id"], 0)

    event_key = (
        "learn:"
        + stable_hash(
            ENGINE_NAME,
            ENGINE_VERSION,
            row["evaluation_key"],
            decision,
        )
    )

    # V1 brain_learning_events schema does not have event_key.
    # We therefore use metadata_json + source claim + event type as
    # the deterministic duplicate key and check it before inserting.
    existing = conn.execute(
        """
        SELECT id
        FROM brain_learning_events
        WHERE
            event_type = ?
            AND source_claim_id = ?
            AND metadata_json LIKE ?
        LIMIT 1
        """,
        (
            "CLAIM_EVALUATION",
            claim_id,
            f'%"event_key":"{event_key}"%',
        ),
    ).fetchone()

    now = utc_now()

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "event_key": event_key,
        "evaluation_id": evaluation_id,
        "evaluation_key": normalize(row["evaluation_key"]),
        "claim_key": normalize(row["claim_key"]),
        "observation_key": normalize(row["observation_key"]),
        "decision": decision,
        "decision_reason": decision_reason,
        "score": safe_float(row["score"]),
        "verdict": normalize(row["verdict"]),
        "sample_size": safe_int(row["sample_size"]),
        "positive_rate": safe_float(row["positive_rate"]),
        "average_return_20d": safe_float(row["average_return_20d"]),
        "evidence_count": safe_int(row["evidence_count"]),
        "source_count": safe_int(row["source_count"]),
        "limitations": [
            "promotion_candidate_is_not_verified_rule",
            "no_live_trading",
            "no_out_of_sample_validation_in_this_engine",
            "no_ai_review_in_this_engine",
        ],
    }

    if existing:
        return int(existing["id"]), False

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
        VALUES (?, NULL, NULL, NULL, ?, NULL, NULL, ?, ?, ?, ?)
        """,
        (
            "CLAIM_EVALUATION",
            claim_id,
            safe_float(row["score"]),
            decision,
            now,
            compact_json(metadata),
        ),
    )

    return int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# BRAIN UPDATE / RESEARCH QUEUE
# ---------------------------------------------------------------------------

def queue_rule_candidate_review(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    decision: str,
) -> bool:
    """
    Promotion candidate için manuel/AI review kuyruğu.

    Research queue'ya sadece PROMOTE_TO_RULE_CANDIDATE kararlarında
    kayıt açılır. Böylece sistem bir sonraki aşamayı açıkça üretir.
    """

    if decision != "PROMOTE_TO_RULE_CANDIDATE":
        return False

    question = (
        "Rule promotion review: "
        f"{normalize(row['symbol'])} | "
        f"{normalize(row['method_name'])} | "
        f"{normalize(row['market_regime'])} | "
        f"{normalize(row['volume_state'])} | "
        f"{normalize(row['volatility_state'])}"
    )

    reason = (
        "Supportive claim passed V1 promotion-candidate thresholds. "
        f"claim_id={int(row['claim_id'])}; "
        f"evaluation_id={int(row['evaluation_id'])}"
    )

    target_claim_id = int(row["claim_id"])

    existing = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE
            target_claim_id = ?
            AND status IN ('queued', 'working')
        LIMIT 1
        """,
        (target_claim_id,),
    ).fetchone()

    if existing:
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
        VALUES (?, ?, ?, NULL, ?, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            9,
            target_claim_id,
            now,
            now,
            compact_json(
                {
                    "engine": ENGINE_NAME,
                    "engine_version": ENGINE_VERSION,
                    "evaluation_id": int(row["evaluation_id"]),
                    "claim_id": int(row["claim_id"]),
                    "decision": decision,
                    "reason": reason,
                }
            ),
        ),
    )

    return True


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    evaluations_seen: int,
    events_inserted: int,
    events_existing: int,
    promotion_candidates: int,
    hold_for_review: int,
    rejected: int,
    research_tasks_queued: int,
) -> None:
    total_events = conn.execute(
        "SELECT COUNT(*) FROM brain_learning_events"
    ).fetchone()[0]

    total_promotion_candidates = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_learning_events
        WHERE
            event_type = 'CLAIM_EVALUATION'
            AND decision = 'PROMOTE_TO_RULE_CANDIDATE'
        """
    ).fetchone()[0]

    total_queue = conn.execute(
        "SELECT COUNT(*) FROM brain_research_queue"
    ).fetchone()[0]

    print("=" * 76)
    print("MARKETHQ BRAIN LEARNING EVENT ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("LEARNING EVENT RUN")
    print("-" * 76)
    print(f"evaluations_seen                     {evaluations_seen}")
    print(f"events_inserted                      {events_inserted}")
    print(f"events_already_present               {events_existing}")
    print(f"promote_to_rule_candidate             {promotion_candidates}")
    print(f"hold_for_review                       {hold_for_review}")
    print(f"reject_for_learning                   {rejected}")
    print(f"research_tasks_queued                 {research_tasks_queued}")
    print()
    print("BRAIN LEARNING EVENT TABLE")
    print("-" * 76)
    print(f"total_learning_events                {total_events}")
    print(f"total_rule_promotion_candidates      {total_promotion_candidates}")
    print(f"total_research_queue_items           {total_queue}")
    print()

    print("RULE PROMOTION CANDIDATES")
    print("-" * 76)

    rows = conn.execute(
        """
        SELECT
            e.id,
            e.source_claim_id,
            e.score,
            e.decision,
            e.created_at,
            c.claim_text
        FROM brain_learning_events e
        JOIN brain_claims c
          ON c.id = e.source_claim_id
        WHERE
            e.event_type = 'CLAIM_EVALUATION'
            AND e.decision = 'PROMOTE_TO_RULE_CANDIDATE'
        ORDER BY e.score DESC, e.id DESC
        LIMIT 15
        """
    ).fetchall()

    if not rows:
        print("No rule promotion candidates.")
    else:
        for row in rows:
            print(
                f"score={safe_float(row['score']):.4f} | "
                f"claim_id={row['source_claim_id']}"
            )
            print(f"  {row['claim_text']}")
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- Learning Event, Brain'in 'öğrenme kararı' kaydıdır.")
    print("- PROMOTE_TO_RULE_CANDIDATE doğrulanmış learned rule değildir.")
    print("- Bu motor learned_rules tablosuna otomatik kural yazmıyor.")
    print("- Ham experiment/result kayıtları değiştirilmedi.")
    print("- Claim/evaluation kayıtları değiştirilmedi.")
    print("- Promotion adayları bir sonraki rule-promotion/evaluation katmanına")
    print("  research queue üzerinden taşınabilir.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_learning_event_indexes(conn)

        evaluations = load_evaluations(conn)

        events_inserted = 0
        events_existing = 0
        promotion_candidates = 0
        hold_for_review = 0
        rejected = 0
        research_tasks_queued = 0

        for row in evaluations:
            decision, _ = promotion_decision(row)

            _, created = write_learning_event(
                conn,
                row,
            )

            if created:
                events_inserted += 1
            else:
                events_existing += 1

            if decision == "PROMOTE_TO_RULE_CANDIDATE":
                promotion_candidates += 1
                if queue_rule_candidate_review(
                    conn,
                    row,
                    decision,
                ):
                    research_tasks_queued += 1

            elif decision == "HOLD_FOR_REVIEW":
                hold_for_review += 1

            elif decision == "REJECT_FOR_LEARNING":
                rejected += 1

        conn.commit()

        print_summary(
            conn=conn,
            evaluations_seen=len(evaluations),
            events_inserted=events_inserted,
            events_existing=events_existing,
            promotion_candidates=promotion_candidates,
            hold_for_review=hold_for_review,
            rejected=rejected,
            research_tasks_queued=research_tasks_queued,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

