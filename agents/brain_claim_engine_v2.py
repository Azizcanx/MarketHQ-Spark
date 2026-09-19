# -*- coding: utf-8 -*-
"""
MarketHQ Brain Claim Engine V1
--------------------------------
Observation -> Candidate Claim

Amaç:
    brain_observations katmanındaki gözlemleri,
    brain_claims tablosunda deterministik ve izlenebilir
    "candidate claim" kayıtlarına dönüştürmek.

Önemli:
    - Ham experiment / result kayıtlarına dokunmaz.
    - Mevcut brain_claims kayıtlarını ezmez.
    - Aynı observation için duplicate claim üretmez.
    - Her claim observation'a bağlanır.
    - AI kullanmaz. İleride GPT/Luna, Claude, Gemini vb.
      review katmanı bunun üstüne eklenebilir.

Çalıştırma:
    python agents/brain_claim_engine_v1.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_CLAIM_ENGINE"
ENGINE_VERSION = "V1"

# Claim üretim eşikleri.
MIN_SAMPLE_SIZE = 20
MIN_CONFIDENCE = 0.55
POSITIVE_RATE_STRONG = 0.65
NEGATIVE_RATE_STRONG = 0.35
AVG20_STRONG = 5.0

# Candidate claim oluşturmak için daha yumuşak eşikler.
POSITIVE_RATE_MIN = 0.52
NEGATIVE_RATE_MAX = 0.48


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
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
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def claim_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_claim_observation_link_table(conn: sqlite3.Connection) -> None:
    """
    Claim <-> Observation izini açıkça tutar.

    Mevcut brain_claim_evidence tablosuna ek olarak bu tablo,
    claim'in hangi observation'dan doğduğunu doğrudan gösterir.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_claim_observations (
            claim_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,
            link_type TEXT NOT NULL DEFAULT 'DERIVED_FROM',
            created_at TEXT NOT NULL,
            PRIMARY KEY (claim_id, observation_id),
            FOREIGN KEY (claim_id) REFERENCES brain_claims(id) ON DELETE CASCADE,
            FOREIGN KEY (observation_id) REFERENCES brain_observations(id) ON DELETE CASCADE
        )
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
    metadata: dict[str, Any],
) -> int:
    row = conn.execute(
        "SELECT id FROM brain_nodes WHERE node_key = ?",
        (node_key,),
    ).fetchone()

    now = utc_now()

    if row:
        conn.execute(
            """
            UPDATE brain_nodes
            SET
                canonical_name = ?,
                summary = ?,
                confidence = MAX(COALESCE(confidence, 0), ?),
                last_seen_at = ?,
                updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                canonical_name,
                summary,
                confidence,
                now,
                now,
                compact_json(metadata),
                row["id"],
            ),
        )
        return int(row["id"])

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
            "active",
            now,
            now,
            compact_json(metadata),
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def resolve_subject_node(
    conn: sqlite3.Connection,
    observation: sqlite3.Row,
    confidence: float,
) -> int:
    symbol = normalize_text(observation["symbol"])
    market = normalize_text(observation["market"])

    if symbol:
        node_key = f"symbol:{symbol.upper()}"
        return get_or_create_node(
            conn=conn,
            node_key=node_key,
            node_type="symbol",
            canonical_name=symbol.upper(),
            summary=f"{symbol.upper()} ({market})",
            confidence=confidence,
            metadata={
                "market": market,
                "source": "brain_claim_engine_v1",
            },
        )

    method_name = normalize_text(observation["method_name"])
    node_key = f"method:{method_name}"
    return get_or_create_node(
        conn=conn,
        node_key=node_key,
        node_type="method",
        canonical_name=method_name,
        summary=f"Method: {method_name}",
        confidence=confidence,
        metadata={"market": market},
    )


def resolve_result_node(
    conn: sqlite3.Connection,
    result_type: str,
    confidence: float,
) -> int:
    names = {
        "positive": (
            "result:positive_20d",
            "POSITIVE_20D_RETURN",
            "20 günlük gözlem penceresinde pozitif sonuç",
        ),
        "negative": (
            "result:negative_20d",
            "NEGATIVE_20D_RETURN",
            "20 günlük gözlem penceresinde negatif sonuç",
        ),
        "mixed": (
            "result:mixed_20d",
            "MIXED_20D_RETURN",
            "20 günlük gözlem penceresinde karışık sonuç",
        ),
    }

    key, name, summary = names[result_type]
    return get_or_create_node(
        conn=conn,
        node_key=key,
        node_type="concept",
        canonical_name=name,
        summary=summary,
        confidence=confidence,
        metadata={
            "source": "brain_claim_engine_v1",
            "result_type": result_type,
        },
    )


# ---------------------------------------------------------------------------
# CLAIM DECISION
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimDecision:
    result_type: str
    claim_type: str
    status: str
    confidence: float
    eligible: bool
    reason: str


def evaluate_observation(obs: sqlite3.Row) -> ClaimDecision:
    sample = safe_int(obs["sample_size"])
    confidence = safe_float(obs["confidence"])
    pos_rate = safe_float(obs["positive_rate"])
    avg20 = safe_float(obs["average_return_20d"])

    if sample < MIN_SAMPLE_SIZE:
        return ClaimDecision(
            result_type="mixed",
            claim_type="observation",
            status="inactive",
            confidence=confidence,
            eligible=False,
            reason="sample_too_small",
        )

    if confidence < MIN_CONFIDENCE:
        return ClaimDecision(
            result_type="mixed",
            claim_type="observation",
            status="inactive",
            confidence=confidence,
            eligible=False,
            reason="confidence_too_low",
        )

    # Güçlü pozitif gözlem adayı
    if pos_rate >= POSITIVE_RATE_STRONG and avg20 >= AVG20_STRONG:
        return ClaimDecision(
            result_type="positive",
            claim_type="candidate",
            status="active",
            confidence=confidence,
            eligible=True,
            reason="strong_positive_observation",
        )

    # Pozitif ama daha temkinli aday
    if pos_rate >= POSITIVE_RATE_MIN and avg20 > 0:
        return ClaimDecision(
            result_type="positive",
            claim_type="candidate",
            status="active",
            confidence=confidence,
            eligible=True,
            reason="positive_observation",
        )

    # Negatif aday
    if pos_rate <= NEGATIVE_RATE_MAX and avg20 < 0:
        return ClaimDecision(
            result_type="negative",
            claim_type="candidate",
            status="active",
            confidence=confidence,
            eligible=True,
            reason="negative_observation",
        )

    # Karışık yapı da epistemik olarak değerli olabilir fakat
    # otomatik candidate claim'e çevirmiyoruz.
    return ClaimDecision(
        result_type="mixed",
        claim_type="observation",
        status="inactive",
        confidence=confidence,
        eligible=False,
        reason="mixed_or_weak_observation",
    )


# ---------------------------------------------------------------------------
# CLAIM TEXT
# ---------------------------------------------------------------------------

def build_claim_text(obs: sqlite3.Row, decision: ClaimDecision) -> str:
    method = normalize_text(obs["method_name"]) or "unknown_method"
    symbol = normalize_text(obs["symbol"]) or "unknown_symbol"
    market = normalize_text(obs["market"]) or "unknown_market"
    timeframe = normalize_text(obs["timeframe"]) or "unknown_timeframe"

    regime = normalize_text(obs["market_regime"]) or "unspecified_regime"
    volume = normalize_text(obs["volume_state"]) or "unspecified_volume"
    volatility = normalize_text(obs["volatility_state"]) or "unspecified_volatility"

    sample = safe_int(obs["sample_size"])
    pos_rate = safe_float(obs["positive_rate"])
    avg20 = safe_float(obs["average_return_20d"])

    direction = {
        "positive": "pozitif",
        "negative": "negatif",
        "mixed": "karışık",
    }[decision.result_type]

    return (
        f"{symbol} için {method} yöntemi kapsamında, "
        f"{regime} rejimi + {volume} hacim + {volatility} volatilite "
        f"koşullarında {timeframe} gözlem ufkunda "
        f"{sample} örnek üzerinde {direction} 20 günlük sonuç "
        f"gözlenmiştir. Pozitif sonuç oranı %{pos_rate * 100:.1f}, "
        f"ortalama 20 günlük getiri %{avg20:.2f}'dir. "
        f"Bu kayıt doğrulanmış kural değil, aday claim'dir."
    )


# ---------------------------------------------------------------------------
# CLAIM KEY
# ---------------------------------------------------------------------------

def build_claim_key(obs: sqlite3.Row, decision: ClaimDecision) -> str:
    payload = {
        "method_name": normalize_text(obs["method_name"]),
        "symbol": normalize_text(obs["symbol"]).upper(),
        "market": normalize_text(obs["market"]),
        "timeframe": normalize_text(obs["timeframe"]),
        "market_regime": normalize_text(obs["market_regime"]),
        "volume_state": normalize_text(obs["volume_state"]),
        "volatility_state": normalize_text(obs["volatility_state"]),
        "result_type": decision.result_type,
    }

    digest = claim_hash(compact_json(payload))

    return f"candidate:{digest}"


# ---------------------------------------------------------------------------
# CLAIM INSERT
# ---------------------------------------------------------------------------

def insert_or_get_claim(
    conn: sqlite3.Connection,
    obs: sqlite3.Row,
    decision: ClaimDecision,
) -> tuple[int, bool]:
    claim_key = build_claim_key(obs, decision)
    existing = conn.execute(
        """
        SELECT id
        FROM brain_claims
        WHERE claim_key = ?
        """,
        (claim_key,),
    ).fetchone()

    now = utc_now()
    claim_text = build_claim_text(obs, decision)

    subject_node_id = resolve_subject_node(
        conn,
        obs,
        decision.confidence,
    )

    object_node_id = resolve_result_node(
        conn,
        decision.result_type,
        decision.confidence,
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "observation_id": int(obs["id"]),
        "observation_key": normalize_text(obs["observation_key"]),
        "method_name": normalize_text(obs["method_name"]),
        "symbol": normalize_text(obs["symbol"]),
        "market": normalize_text(obs["market"]),
        "timeframe": normalize_text(obs["timeframe"]),
        "market_regime": normalize_text(obs["market_regime"]),
        "volume_state": normalize_text(obs["volume_state"]),
        "volatility_state": normalize_text(obs["volatility_state"]),
        "sample_size": safe_int(obs["sample_size"]),
        "positive_rate": safe_float(obs["positive_rate"]),
        "average_return_20d": safe_float(obs["average_return_20d"]),
        "decision_reason": decision.reason,
        "epistemic_note": "candidate_claim_not_verified_rule",
    }

    if existing:
        claim_id = int(existing["id"])

        # Existing claim'i ezmiyoruz; sadece metadata/updated timestamp
        # gibi güvenli alanları tazeliyoruz.
        conn.execute(
            """
            UPDATE brain_claims
            SET
                confidence = MAX(COALESCE(confidence, 0), ?),
                updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                decision.confidence,
                now,
                compact_json(metadata),
                claim_id,
            ),
        )

        return claim_id, False

    cur = conn.execute(
        """
        INSERT INTO brain_claims (
            claim_key,
            subject_node_id,
            predicate,
            object_node_id,
            claim_text,
            claim_type,
            status,
            confidence,
            valid_from,
            valid_to,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim_key,
            subject_node_id,
            "OBSERVED_20D_OUTCOME_UNDER_CONTEXT",
            object_node_id,
            claim_text,
            decision.claim_type,
            decision.status,
            decision.confidence,
            normalize_text(obs["first_observation_date"]) or None,
            normalize_text(obs["last_observation_date"]) or None,
            now,
            now,
            compact_json(metadata),
        ),
    )

    return int(cur.lastrowid), True


def link_claim_to_observation(
    conn: sqlite3.Connection,
    claim_id: int,
    observation_id: int,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO brain_claim_observations (
            claim_id,
            observation_id,
            link_type,
            created_at
        )
        VALUES (?, ?, 'DERIVED_FROM', ?)
        """,
        (
            claim_id,
            observation_id,
            utc_now(),
        ),
    )


# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 76)
    print("MARKETHQ BRAIN CLAIM ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("CLAIM RUN")
    print("-" * 76)

    conn = open_db()

    try:
        ensure_claim_observation_link_table(conn)

        observations = conn.execute(
            """
            SELECT *
            FROM brain_observations
            ORDER BY id
            """
        ).fetchall()

        total = len(observations)
        eligible = 0
        inserted = 0
        existing = 0
        linked = 0
        positive = 0
        negative = 0
        strong = 0
        skipped = 0

        for obs in observations:
            decision = evaluate_observation(obs)

            if not decision.eligible:
                skipped += 1
                continue

            eligible += 1

            if decision.result_type == "positive":
                positive += 1
            elif decision.result_type == "negative":
                negative += 1

            if (
                safe_float(obs["positive_rate"]) >= POSITIVE_RATE_STRONG
                and safe_float(obs["average_return_20d"]) >= AVG20_STRONG
                and decision.confidence >= 0.65
            ):
                strong += 1

            claim_id, created = insert_or_get_claim(
                conn,
                obs,
                decision,
            )

            if created:
                inserted += 1
            else:
                existing += 1

            link_claim_to_observation(
                conn,
                claim_id,
                int(obs["id"]),
            )
            linked += 1

        conn.commit()

        print(f"observations_seen                  {total}")
        print(f"eligible_observations              {eligible}")
        print(f"claims_inserted                    {inserted}")
        print(f"claims_already_present             {existing}")
        print(f"claim_observation_links            {linked}")
        print(f"positive_candidates                {positive}")
        print(f"negative_candidates                {negative}")
        print(f"strong_candidates                  {strong}")
        print(f"skipped_observations               {skipped}")
        print()

        claim_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_claims
            WHERE claim_type = 'candidate'
            """
        ).fetchone()[0]

        link_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_claim_observations
            """
        ).fetchone()[0]

        print("BRAIN CLAIM TABLE")
        print("-" * 76)
        print(f"candidate claims                    {claim_count}")
        print(f"claim-observation links             {link_count}")
        print()

        print("TOP CANDIDATE CLAIMS")
        print("-" * 76)

        rows = conn.execute(
            """
            SELECT
                c.claim_key,
                c.claim_text,
                c.confidence,
                c.status,
                o.sample_size,
                o.positive_rate,
                o.average_return_20d
            FROM brain_claims c
            JOIN brain_claim_observations co
              ON co.claim_id = c.id
            JOIN brain_observations o
              ON o.id = co.observation_id
            WHERE c.claim_type = 'candidate'
            ORDER BY
                c.confidence DESC,
                o.sample_size DESC
            LIMIT 15
            """
        ).fetchall()

        for row in rows:
            print(
                f"{row['confidence']:.4f} | "
                f"n={safe_int(row['sample_size']):5d} | "
                f"pos={safe_float(row['positive_rate']):.3f} | "
                f"avg20={safe_float(row['average_return_20d']):.4f}"
            )
            print(f"  {row['claim_text']}")
            print()

        print("IMPORTANT")
        print("-" * 76)
        print("- Claim'ler otomatik olarak doğrulanmış kural değildir.")
        print("- Her claim hangi observation'dan türediğini korur.")
        print("- Ham experiment/result kayıtları değiştirilmedi.")
        print("- AI review henüz yapılmadı.")
        print("- Sonraki aşama: contradiction -> evaluation -> learning.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

