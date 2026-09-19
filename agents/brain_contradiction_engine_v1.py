# -*- coding: utf-8 -*-
"""
MarketHQ Brain Contradiction Engine V1
--------------------------------------
Candidate Claim -> Contradiction Detection

Amaç:
    brain_claims içindeki yönü belirli claim'ler arasında
    aynı sembol/market/timeframe/context altında karşıt sonuçları
    bulmak ve brain_contradictions tablosuna kaydetmek.

Tasarım:
    - AI kullanmaz.
    - Ham experiment / result kayıtlarına dokunmaz.
    - Mevcut claim'leri değiştirmez.
    - Duplicate contradiction üretmez.
    - Claim -> Observation izini korur.
    - Aynı context içindeki farklı method versiyonları arasında
      pozitif/negatif karşıtlığı "competing claim" olarak işaretler.
    - Gerçek contradiction bulunamazsa bunu normal sonuç olarak kabul eder.
    - Kritik disagreement'lar için brain_research_queue kaydı oluşturabilir.

Sonraki katman:
    contradiction -> evaluation -> learning

Çalıştırma:
    python agents/brain_contradiction_engine_v1.py
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

ENGINE_NAME = "MARKETHQ_BRAIN_CONTRADICTION_ENGINE"
ENGINE_VERSION = "V1"

# Candidate claim'ler için minimum güven.
MIN_CLAIM_CONFIDENCE = 0.55

# Güçlü karşıtlık için eşikler.
STRONG_POSITIVE_RATE = 0.65
STRONG_NEGATIVE_RATE = 0.35
STRONG_AVG20 = 5.0

# Normal claim çiftinin contradiction sayılabilmesi için
# aynı context'e sahip olması gerekir.
CONTEXT_FIELDS = (
    "symbol",
    "market",
    "timeframe",
    "market_regime",
    "volume_state",
    "volatility_state",
)


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


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


# ---------------------------------------------------------------------------
# SCHEMA / INDEXES
# ---------------------------------------------------------------------------

def ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claims_type_status
        ON brain_claims(claim_type, status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claims_subject
        ON brain_claims(subject_node_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claim_obs_claim
        ON brain_claim_observations(claim_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claim_obs_observation
        ON brain_claim_observations(observation_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_contradictions_topic
        ON brain_contradictions(topic_key)
        """
    )


# ---------------------------------------------------------------------------
# CLAIM EXTRACTION
# ---------------------------------------------------------------------------

def claim_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Claim'i bağlı observation ile birlikte getirir.

    Her claim'in ilk/ana observation bağlantısı kullanılır.
    Claim Engine V1 bir observation -> bir candidate claim
    ürettiği için bu deterministik kalır.
    """

    rows = conn.execute(
        """
        SELECT
            c.id AS claim_id,
            c.claim_key,
            c.subject_node_id,
            c.predicate,
            c.object_node_id,
            c.claim_text,
            c.claim_type,
            c.status,
            c.confidence,
            c.created_at,
            c.updated_at,

            o.id AS observation_id,
            o.observation_key,
            o.method_name,
            o.symbol,
            o.market,
            o.timeframe,
            o.market_regime,
            o.volume_state,
            o.volatility_state,
            o.sample_size,
            o.positive_rate,
            o.average_return_20d,
            o.first_observation_date,
            o.last_observation_date

        FROM brain_claims c
        JOIN brain_claim_observations co
          ON co.claim_id = c.id
        JOIN brain_observations o
          ON o.id = co.observation_id

        WHERE
            c.claim_type IN ('candidate', 'supported', 'learned')
            AND c.status = 'active'
            AND COALESCE(c.confidence, 0) >= ?

        ORDER BY c.id
        """,
        (MIN_CLAIM_CONFIDENCE,),
    ).fetchall()

    return list(rows)


# ---------------------------------------------------------------------------
# DIRECTION
# ---------------------------------------------------------------------------

def claim_direction(row: sqlite3.Row) -> str:
    """
    Candidate claim'in yönünü mümkün olduğunca deterministik çıkarır.

    Öncelik:
      1) metadata'daki result_type
      2) object node key
      3) observation istatistikleri
    """

    metadata_raw = ""

    # sqlite.Row -> dict dönüşümü
    if "metadata_json" in row.keys():
        metadata_raw = normalize(row["metadata_json"])

    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
            result_type = normalize(metadata.get("result_type")).lower()

            if result_type in {"positive", "negative", "mixed"}:
                return result_type
        except (json.JSONDecodeError, TypeError):
            pass

    object_key = normalize(row["claim_key"]).lower()
    if object_key.startswith("candidate:"):
        # Claim key hash içerdiği için burada yön çıkarılamaz.
        pass

    avg20 = safe_float(row["average_return_20d"])
    pos_rate = safe_float(row["positive_rate"])

    if pos_rate >= 0.5 and avg20 > 0:
        return "positive"

    if pos_rate <= 0.5 and avg20 < 0:
        return "negative"

    return "mixed"


# ---------------------------------------------------------------------------
# CONTEXT
# ---------------------------------------------------------------------------

def context_key(row: sqlite3.Row) -> str:
    values = [
        normalize(row[field]).lower()
        for field in CONTEXT_FIELDS
    ]
    return "|".join(values)


def topic_key(row: sqlite3.Row) -> str:
    """
    Method'u bilerek topic'e dahil etmiyoruz.

    Böylece:
        Method A -> positive
        Method B -> negative

    aynı sembol/context altında competing claims olarak
    yakalanabilir.
    """
    return "|".join(
        [
            normalize(row["symbol"]).upper(),
            normalize(row["market"]).upper(),
            normalize(row["timeframe"]).lower(),
            normalize(row["market_regime"]).lower(),
            normalize(row["volume_state"]).lower(),
            normalize(row["volatility_state"]).lower(),
        ]
    )


# ---------------------------------------------------------------------------
# CONTRADICTION SEVERITY
# ---------------------------------------------------------------------------

def contradiction_severity(
    positive: sqlite3.Row,
    negative: sqlite3.Row,
) -> tuple[str, float]:
    pos_rate_a = safe_float(positive["positive_rate"])
    pos_rate_b = safe_float(negative["positive_rate"])

    avg20_a = safe_float(positive["average_return_20d"])
    avg20_b = safe_float(negative["average_return_20d"])

    conf_a = safe_float(positive["confidence"])
    conf_b = safe_float(negative["confidence"])

    rate_gap = abs(pos_rate_a - pos_rate_b)
    return_gap = abs(avg20_a - avg20_b)
    confidence = (conf_a + conf_b) / 2.0

    strong_directional = (
        pos_rate_a >= STRONG_POSITIVE_RATE
        and pos_rate_b <= STRONG_NEGATIVE_RATE
        and avg20_a >= STRONG_AVG20
        and avg20_b <= -STRONG_AVG20
    )

    if strong_directional and confidence >= 0.70:
        return "high", 0.90

    if (
        rate_gap >= 0.25
        or return_gap >= 5.0
        or confidence >= 0.75
    ):
        return "medium", 0.65

    return "low", 0.40


# ---------------------------------------------------------------------------
# DUPLICATE CHECK
# ---------------------------------------------------------------------------

def contradiction_exists(
    conn: sqlite3.Connection,
    claim_a_id: int,
    claim_b_id: int,
) -> bool:
    a, b = sorted((claim_a_id, claim_b_id))

    row = conn.execute(
        """
        SELECT 1
        FROM brain_contradictions
        WHERE
            claim_a_id = ?
            AND claim_b_id = ?
        LIMIT 1
        """,
        (a, b),
    ).fetchone()

    return row is not None


# ---------------------------------------------------------------------------
# RESEARCH QUEUE
# ---------------------------------------------------------------------------

def queue_research_for_contradiction(
    conn: sqlite3.Connection,
    topic: str,
    claim_a_id: int,
    claim_b_id: int,
    severity: str,
) -> bool:
    priority = {
        "high": 10,
        "medium": 7,
        "low": 4,
    }.get(severity, 4)

    question = (
        "Contradictory claims detected. Re-evaluate competing outcomes "
        f"for topic={topic}"
    )

    reason = (
        f"claim_a={claim_a_id}; "
        f"claim_b={claim_b_id}; "
        f"severity={severity}"
    )

    target_claim_id = min(claim_a_id, claim_b_id)

    existing = conn.execute(
        """
        SELECT 1
        FROM brain_research_queue
        WHERE
            question = ?
            AND status IN ('queued', 'working')
        LIMIT 1
        """,
        (question,),
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
            priority,
            target_claim_id,
            now,
            now,
            compact_json(
                {
                    "engine": ENGINE_NAME,
                    "engine_version": ENGINE_VERSION,
                    "topic_key": topic,
                    "claim_a": claim_a_id,
                    "claim_b": claim_b_id,
                    "severity": severity,
                }
            ),
        ),
    )

    return True


# ---------------------------------------------------------------------------
# CONTRADICTION INSERT
# ---------------------------------------------------------------------------

def insert_contradiction(
    conn: sqlite3.Connection,
    positive: sqlite3.Row,
    negative: sqlite3.Row,
    severity: str,
    score: float,
) -> tuple[bool, bool]:
    claim_a_id, claim_b_id = sorted(
        (int(positive["claim_id"]), int(negative["claim_id"]))
    )

    topic = topic_key(positive)

    if contradiction_exists(conn, claim_a_id, claim_b_id):
        return False, False

    now = utc_now()

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "relation_type": "COMPETING_CLAIMS",
        "topic_key": topic,
        "positive_claim_id": int(positive["claim_id"]),
        "negative_claim_id": int(negative["claim_id"]),
        "positive_method": normalize(positive["method_name"]),
        "negative_method": normalize(negative["method_name"]),
        "positive_observation_id": int(positive["observation_id"]),
        "negative_observation_id": int(negative["observation_id"]),
        "positive_sample_size": int(positive["sample_size"] or 0),
        "negative_sample_size": int(negative["sample_size"] or 0),
        "positive_rate_gap": abs(
            safe_float(positive["positive_rate"])
            - safe_float(negative["positive_rate"])
        ),
        "average_return_20d_gap": abs(
            safe_float(positive["average_return_20d"])
            - safe_float(negative["average_return_20d"])
        ),
    }

    conn.execute(
        """
        INSERT INTO brain_contradictions (
            topic_key,
            claim_a_id,
            claim_b_id,
            severity,
            status,
            detected_at,
            resolved_at,
            resolution_note,
            metadata_json
        )
        VALUES (?, ?, ?, ?, 'open', ?, NULL, NULL, ?)
        """,
        (
            topic,
            claim_a_id,
            claim_b_id,
            severity,
            now,
            compact_json(metadata),
        ),
    )

    queued = queue_research_for_contradiction(
        conn=conn,
        topic=topic,
        claim_a_id=claim_a_id,
        claim_b_id=claim_b_id,
        severity=severity,
    )

    return True, queued


# ---------------------------------------------------------------------------
# PAIRING
# ---------------------------------------------------------------------------

def build_groups(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    groups: dict[str, list[sqlite3.Row]] = {}

    for row in rows:
        key = context_key(row)
        groups.setdefault(key, []).append(row)

    return groups


def detect_contradictions(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> tuple[int, int, int, int]:
    """
    Returns:
        groups_seen,
        candidate_pairs,
        contradictions_inserted,
        research_tasks_queued
    """

    groups = build_groups(rows)

    groups_seen = len(groups)
    candidate_pairs = 0
    contradictions_inserted = 0
    research_tasks_queued = 0

    for _, members in groups.items():
        positives = [
            row for row in members
            if claim_direction(row) == "positive"
        ]

        negatives = [
            row for row in members
            if claim_direction(row) == "negative"
        ]

        if not positives or not negatives:
            continue

        for positive in positives:
            for negative in negatives:
                # Aynı claim kendisiyle eşleşmesin.
                if int(positive["claim_id"]) == int(negative["claim_id"]):
                    continue

                candidate_pairs += 1

                severity, score = contradiction_severity(
                    positive,
                    negative,
                )

                inserted, queued = insert_contradiction(
                    conn=conn,
                    positive=positive,
                    negative=negative,
                    severity=severity,
                    score=score,
                )

                if inserted:
                    contradictions_inserted += 1

                if queued:
                    research_tasks_queued += 1

    return (
        groups_seen,
        candidate_pairs,
        contradictions_inserted,
        research_tasks_queued,
    )


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    groups_seen: int,
    candidate_pairs: int,
    contradictions_inserted: int,
    research_tasks_queued: int,
) -> None:
    total_contradictions = conn.execute(
        "SELECT COUNT(*) FROM brain_contradictions"
    ).fetchone()[0]

    open_contradictions = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_contradictions
        WHERE status = 'open'
        """
    ).fetchone()[0]

    high_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_contradictions
        WHERE severity = 'high' AND status = 'open'
        """
    ).fetchone()[0]

    medium_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_contradictions
        WHERE severity = 'medium' AND status = 'open'
        """
    ).fetchone()[0]

    low_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_contradictions
        WHERE severity = 'low' AND status = 'open'
        """
    ).fetchone()[0]

    print("=" * 76)
    print("MARKETHQ BRAIN CONTRADICTION ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("CONTRADICTION RUN")
    print("-" * 76)
    print(f"claim_context_groups_seen             {groups_seen}")
    print(f"candidate_pairs                       {candidate_pairs}")
    print(f"contradictions_inserted               {contradictions_inserted}")
    print(f"research_tasks_queued                 {research_tasks_queued}")
    print()
    print("BRAIN CONTRADICTION TABLE")
    print("-" * 76)
    print(f"total_contradictions                  {total_contradictions}")
    print(f"open_contradictions                   {open_contradictions}")
    print(f"open_high                              {high_count}")
    print(f"open_medium                            {medium_count}")
    print(f"open_low                               {low_count}")
    print()

    print("OPEN CONTRADICTIONS")
    print("-" * 76)

    rows = conn.execute(
        """
        SELECT
            bc.id,
            bc.topic_key,
            bc.claim_a_id,
            bc.claim_b_id,
            bc.severity,
            bc.status,
            ca.claim_text AS claim_a_text,
            cb.claim_text AS claim_b_text
        FROM brain_contradictions bc
        JOIN brain_claims ca
          ON ca.id = bc.claim_a_id
        JOIN brain_claims cb
          ON cb.id = bc.claim_b_id
        WHERE bc.status = 'open'
        ORDER BY
            CASE bc.severity
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
            END,
            bc.id DESC
        LIMIT 15
        """
    ).fetchall()

    if not rows:
        print("No open contradictions detected.")
    else:
        for row in rows:
            print(
                f"[{row['severity'].upper()}] "
                f"claim_a={row['claim_a_id']} "
                f"claim_b={row['claim_b_id']}"
            )
            print(f"  topic={row['topic_key']}")
            print(f"  A: {row['claim_a_text']}")
            print(f"  B: {row['claim_b_text']}")
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- Contradiction, 'iki claim karşıt veri söylüyor' anlamındadır.")
    print("- Farklı yöntemlerin ikisinin de pozitif olması contradiction değildir.")
    print("- Bu motor claim'leri silmez veya otomatik olarak doğrulamaz.")
    print("- Contradiction bulunan konular evaluation için research queue'ya girebilir.")
    print("- Henüz contradiction olmaması bir hata değildir; mevcut claim kümesi")
    print("  yalnızca pozitif candidate claim'lerden oluşuyorsa sonuç doğal olarak 0 olabilir.")
    print("- Sonraki aşama: contradiction/evaluation -> learning.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

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


def run() -> None:
    conn = open_db()

    try:
        ensure_indexes(conn)

        rows = claim_rows(conn)

        groups_seen, candidate_pairs, inserted, queued = detect_contradictions(
            conn,
            rows,
        )

        conn.commit()

        print_summary(
            conn=conn,
            groups_seen=groups_seen,
            candidate_pairs=candidate_pairs,
            contradictions_inserted=inserted,
            research_tasks_queued=queued,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

