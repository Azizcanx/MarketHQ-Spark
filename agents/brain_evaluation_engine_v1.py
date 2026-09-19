# -*- coding: utf-8 -*-
"""
MarketHQ Brain Evaluation Engine V1
-----------------------------------
Candidate Claim -> Evidence-based evaluation

Amaç:
    brain_claims içindeki candidate claim'leri değerlendirmek ve
    ayrı bir evaluation katmanında puanlamak.

ÖNEMLİ:
    - Bu motor yeni bir "doğrulanmış strateji" üretmez.
    - Ham experiment / experiment_result kayıtlarına dokunmaz.
    - Claim metnini değiştirmez.
    - Mevcut brain_claims.status alanını otomatik olarak "learned"
      yapmaz.
    - Evaluation sonuçlarını ayrı tabloda tutar.
    - Mevcut evidence / observation bağlantılarını kullanır.
    - İleride GPT/Luna, Claude, Gemini gibi AI reviewer'lar
      bu evaluation katmanına ek kanıt/yorum verebilir.

Değerlendirme mantığı:
    1) sample strength
    2) observation confidence
    3) positive-rate strength
    4) return strength
    5) evidence/source coverage
    6) observation-varyant consistency

Çıktı sınıfları:
    SUPPORTIVE
    PROMISING
    NEEDS_REVIEW
    WEAK

Bunlar epistemik olarak "kanıt gücü" sınıflarıdır.
SUPPORTIVE != VERIFIED RULE

Çalıştırma:
    python agents/brain_evaluation_engine_v1.py
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

ENGINE_NAME = "MARKETHQ_BRAIN_EVALUATION_ENGINE"
ENGINE_VERSION = "V1"

MIN_CLAIM_CONFIDENCE = 0.55
MIN_SAMPLE = 20

# Sample score:
# 20 -> 0, 100 -> ~0.5, 500 -> ~1.0
SAMPLE_REFERENCE = 500.0

# Evidence / source coverage normalization.
EVIDENCE_REFERENCE = 5.0
SOURCE_REFERENCE = 5.0

# Strong candidate thresholds.
STRONG_POSITIVE_RATE = 0.65
STRONG_AVG20 = 5.0

# Evaluation score weights.
WEIGHT_SAMPLE = 0.20
WEIGHT_OBS_CONF = 0.20
WEIGHT_POS_RATE = 0.20
WEIGHT_RETURN = 0.20
WEIGHT_EVIDENCE = 0.10
WEIGHT_CONSISTENCY = 0.10


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


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def stable_key(*parts: Any) -> str:
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

def ensure_evaluation_table(conn: sqlite3.Connection) -> None:
    """
    Evaluation katmanını brain_claims'ten ayrı tutar.

    Aynı claim için yeniden çalıştırıldığında duplicate oluşmaz.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_claim_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_key TEXT NOT NULL UNIQUE,
            claim_id INTEGER NOT NULL,
            observation_id INTEGER,
            evaluation_type TEXT NOT NULL,
            verdict TEXT NOT NULL,
            score REAL NOT NULL,
            sample_score REAL NOT NULL,
            confidence_score REAL NOT NULL,
            positive_rate_score REAL NOT NULL,
            return_score REAL NOT NULL,
            evidence_score REAL NOT NULL,
            consistency_score REAL NOT NULL,
            sample_size INTEGER NOT NULL,
            positive_rate REAL NOT NULL,
            average_return_20d REAL NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            source_count INTEGER NOT NULL DEFAULT 0,
            consistency_count INTEGER NOT NULL DEFAULT 0,
            rationale TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (claim_id)
                REFERENCES brain_claims(id)
                ON DELETE CASCADE,
            FOREIGN KEY (observation_id)
                REFERENCES brain_observations(id)
                ON DELETE SET NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claim_eval_claim
        ON brain_claim_evaluations(claim_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_claim_eval_verdict
        ON brain_claim_evaluations(verdict)
        """
    )


# ---------------------------------------------------------------------------
# CLAIM RETRIEVAL
# ---------------------------------------------------------------------------

def load_candidate_claims(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Candidate claim + bağlı observation.
    Claim Engine V1'in oluşturduğu DERIVED_FROM bağlantısını kullanır.
    """

    rows = conn.execute(
        """
        SELECT
            c.id AS claim_id,
            c.claim_key,
            c.claim_text,
            c.claim_type,
            c.status,
            c.confidence AS claim_confidence,
            c.created_at AS claim_created_at,

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
            o.average_return_1d,
            o.average_return_5d,
            o.median_return_20d,
            o.best_return_20d,
            o.worst_return_20d,
            o.confidence AS observation_confidence,
            o.status AS observation_status,
            o.first_observation_date,
            o.last_observation_date

        FROM brain_claims c
        JOIN brain_claim_observations co
          ON co.claim_id = c.id
        JOIN brain_observations o
          ON o.id = co.observation_id

        WHERE
            c.claim_type = 'candidate'
            AND c.status = 'active'

        ORDER BY c.id
        """
    ).fetchall()

    return list(rows)


# ---------------------------------------------------------------------------
# SUPPORT COUNTS
# ---------------------------------------------------------------------------

def observation_evidence_count(
    conn: sqlite3.Connection,
    observation_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_observation_evidence
        WHERE observation_id = ?
        """,
        (observation_id,),
    ).fetchone()

    return safe_int(row[0] if row else 0)


def observation_source_count(
    conn: sqlite3.Connection,
    observation_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_observation_sources
        WHERE observation_id = ?
        """,
        (observation_id,),
    ).fetchone()

    return safe_int(row[0] if row else 0)


# ---------------------------------------------------------------------------
# CONSISTENCY
# ---------------------------------------------------------------------------

def consistency_count(
    conn: sqlite3.Connection,
    claim: sqlite3.Row,
) -> int:
    """
    Aynı method + symbol + market + timeframe + regime + volume + volatility
    context'i için kaç farklı observation bulunduğunu ölçer.

    Bu ölçüm:
      - "aynı bağlamda tekrar eden gözlem var mı?"
    sorusuna cevap verir.

    NOT:
      Buradaki consistency tekrar sayısıdır; bağımsız out-of-sample
      doğrulama değildir.
    """

    fields = (
        normalize(claim["method_name"]),
        normalize(claim["symbol"]),
        normalize(claim["market"]),
        normalize(claim["timeframe"]),
        normalize(claim["market_regime"]),
        normalize(claim["volume_state"]),
        normalize(claim["volatility_state"]),
    )

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_observations
        WHERE
            method_name = ?
            AND symbol = ?
            AND market = ?
            AND timeframe = ?
            AND market_regime = ?
            AND volume_state = ?
            AND volatility_state = ?
        """,
        fields,
    ).fetchone()

    return safe_int(row[0] if row else 0)


# ---------------------------------------------------------------------------
# SCORE COMPONENTS
# ---------------------------------------------------------------------------

def sample_score(sample_size: int) -> float:
    if sample_size <= MIN_SAMPLE:
        return 0.0

    # Logaritmik artış: 20'den sonra getirisi azalır,
    # böylece çok büyük sample tek başına tüm değerlendirmeyi domine etmez.
    import math

    numerator = math.log1p(sample_size - MIN_SAMPLE)
    denominator = math.log1p(SAMPLE_REFERENCE - MIN_SAMPLE)

    if denominator <= 0:
        return 0.0

    return clamp(numerator / denominator)


def confidence_score(claim_confidence: float, observation_confidence: float) -> float:
    return clamp(
        (clamp(claim_confidence) + clamp(observation_confidence)) / 2.0
    )


def positive_rate_score(
    positive_rate: float,
    average_return_20d: float,
) -> float:
    """
    Pozitif oranı 50% civarında nötr,
    65%+ oldukça güçlü kabul eder.
    Ortalama return küçükse skor biraz azaltılır.
    """

    centered = clamp((positive_rate - 0.50) / 0.25)
    return_component = clamp(max(0.0, average_return_20d) / 10.0)

    return clamp(
        0.70 * centered
        + 0.30 * return_component
    )


def return_score(average_return_20d: float) -> float:
    """
    20d ortalama getiri:
      <= 0 -> 0
      0..10 -> 0..1
      >=10 -> 1

    Bu sadece veri gücü metriğidir, gelecekteki getiri tahmini değildir.
    """

    return clamp(max(0.0, average_return_20d) / 10.0)


def evidence_score(
    evidence_count: int,
    source_count: int,
) -> float:
    evidence_component = clamp(
        evidence_count / EVIDENCE_REFERENCE
    )

    source_component = clamp(
        source_count / SOURCE_REFERENCE
    )

    return clamp(
        0.65 * evidence_component
        + 0.35 * source_component
    )


def consistency_score(
    consistency_count_value: int,
    sample_size: int,
) -> float:
    """
    Tek observation yerine aynı context altında birden fazla
    observation bulunmasını hafif destek olarak kullanır.

    Bu, bağımsız doğrulama olarak yorumlanmaz.
    """

    if sample_size <= 0:
        return 0.0

    # 5+ context observation -> tam puan.
    return clamp((consistency_count_value - 1) / 4.0)


# ---------------------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------------------

def verdict_for(
    score: float,
    sample_size: int,
    confidence: float,
    positive_rate: float,
    average_return_20d: float,
    evidence_count: int,
) -> str:
    if sample_size < MIN_SAMPLE:
        return "WEAK"

    if confidence < MIN_CLAIM_CONFIDENCE:
        return "NEEDS_REVIEW"

    # Çok az evidence varsa yüksek istatistik skorunu tek başına
    # "supportive" seviyesine çıkarmıyoruz.
    if evidence_count == 0 and score >= 0.70:
        return "NEEDS_REVIEW"

    if (
        score >= 0.75
        and positive_rate >= STRONG_POSITIVE_RATE
        and average_return_20d >= STRONG_AVG20
        and evidence_count >= 1
    ):
        return "SUPPORTIVE"

    if score >= 0.55:
        return "PROMISING"

    if score >= 0.35:
        return "NEEDS_REVIEW"

    return "WEAK"


def build_rationale(
    claim: sqlite3.Row,
    verdict: str,
    score: float,
    evidence_count: int,
    source_count: int,
    consistency_count_value: int,
) -> str:
    sample = safe_int(claim["sample_size"])
    pos = safe_float(claim["positive_rate"])
    avg20 = safe_float(claim["average_return_20d"])
    conf = safe_float(claim["observation_confidence"])

    return (
        f"verdict={verdict}; "
        f"score={score:.4f}; "
        f"sample={sample}; "
        f"positive_rate={pos:.4f}; "
        f"average_return_20d={avg20:.4f}; "
        f"observation_confidence={conf:.4f}; "
        f"evidence_count={evidence_count}; "
        f"source_count={source_count}; "
        f"context_observation_count={consistency_count_value}. "
        "Bu değerlendirme doğrulanmış kural değildir; "
        "istatistiksel/evidence tabanlı aday güç değerlendirmesidir."
    )


# ---------------------------------------------------------------------------
# UPSERT
# ---------------------------------------------------------------------------

def write_evaluation(
    conn: sqlite3.Connection,
    claim: sqlite3.Row,
) -> tuple[int, bool]:
    claim_id = int(claim["claim_id"])
    observation_id = int(claim["observation_id"])

    sample_size_value = safe_int(claim["sample_size"])
    positive_rate_value = safe_float(claim["positive_rate"])
    average_return_20d_value = safe_float(
        claim["average_return_20d"]
    )

    claim_conf = safe_float(claim["claim_confidence"])
    obs_conf = safe_float(claim["observation_confidence"])

    evidence_count = observation_evidence_count(
        conn,
        observation_id,
    )

    source_count = observation_source_count(
        conn,
        observation_id,
    )

    consistency_count_value = consistency_count(
        conn,
        claim,
    )

    scores = {
        "sample": sample_score(sample_size_value),
        "confidence": confidence_score(claim_conf, obs_conf),
        "positive_rate": positive_rate_score(
            positive_rate_value,
            average_return_20d_value,
        ),
        "return": return_score(
            average_return_20d_value,
        ),
        "evidence": evidence_score(
            evidence_count,
            source_count,
        ),
        "consistency": consistency_score(
            consistency_count_value,
            sample_size_value,
        ),
    }

    total_score = clamp(
        WEIGHT_SAMPLE * scores["sample"]
        + WEIGHT_OBS_CONF * scores["confidence"]
        + WEIGHT_POS_RATE * scores["positive_rate"]
        + WEIGHT_RETURN * scores["return"]
        + WEIGHT_EVIDENCE * scores["evidence"]
        + WEIGHT_CONSISTENCY * scores["consistency"]
    )

    verdict = verdict_for(
        score=total_score,
        sample_size=sample_size_value,
        confidence=scores["confidence"],
        positive_rate=positive_rate_value,
        average_return_20d=average_return_20d_value,
        evidence_count=evidence_count,
    )

    evaluation_key = (
        f"eval:{stable_key(claim['claim_key'], ENGINE_VERSION)}"
    )

    rationale = build_rationale(
        claim=claim,
        verdict=verdict,
        score=total_score,
        evidence_count=evidence_count,
        source_count=source_count,
        consistency_count_value=consistency_count_value,
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "claim_key": normalize(claim["claim_key"]),
        "observation_key": normalize(claim["observation_key"]),
        "method_name": normalize(claim["method_name"]),
        "symbol": normalize(claim["symbol"]),
        "market": normalize(claim["market"]),
        "timeframe": normalize(claim["timeframe"]),
        "market_regime": normalize(claim["market_regime"]),
        "volume_state": normalize(claim["volume_state"]),
        "volatility_state": normalize(claim["volatility_state"]),
        "weights": {
            "sample": WEIGHT_SAMPLE,
            "confidence": WEIGHT_OBS_CONF,
            "positive_rate": WEIGHT_POS_RATE,
            "return": WEIGHT_RETURN,
            "evidence": WEIGHT_EVIDENCE,
            "consistency": WEIGHT_CONSISTENCY,
        },
        "score_components": scores,
        "limitations": [
            "historical_observation_only",
            "no_out_of_sample_validation",
            "not_a_verified_rule",
            "context_consistency_is_not_independent_validation",
        ],
    }

    now = utc_now()

    existing = conn.execute(
        """
        SELECT id
        FROM brain_claim_evaluations
        WHERE evaluation_key = ?
        """,
        (evaluation_key,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE brain_claim_evaluations
            SET
                observation_id = ?,
                verdict = ?,
                score = ?,
                sample_score = ?,
                confidence_score = ?,
                positive_rate_score = ?,
                return_score = ?,
                evidence_score = ?,
                consistency_score = ?,
                sample_size = ?,
                positive_rate = ?,
                average_return_20d = ?,
                evidence_count = ?,
                source_count = ?,
                consistency_count = ?,
                rationale = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                observation_id,
                verdict,
                total_score,
                scores["sample"],
                scores["confidence"],
                scores["positive_rate"],
                scores["return"],
                scores["evidence"],
                scores["consistency"],
                sample_size_value,
                positive_rate_value,
                average_return_20d_value,
                evidence_count,
                source_count,
                consistency_count_value,
                rationale,
                compact_json(metadata),
                now,
                int(existing["id"]),
            ),
        )
        return int(existing["id"]), False

    cur = conn.execute(
        """
        INSERT INTO brain_claim_evaluations (
            evaluation_key,
            claim_id,
            observation_id,
            evaluation_type,
            verdict,
            score,
            sample_score,
            confidence_score,
            positive_rate_score,
            return_score,
            evidence_score,
            consistency_score,
            sample_size,
            positive_rate,
            average_return_20d,
            evidence_count,
            source_count,
            consistency_count,
            rationale,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            evaluation_key,
            claim_id,
            observation_id,
            "candidate_claim_strength",
            verdict,
            total_score,
            scores["sample"],
            scores["confidence"],
            scores["positive_rate"],
            scores["return"],
            scores["evidence"],
            scores["consistency"],
            sample_size_value,
            positive_rate_value,
            average_return_20d_value,
            evidence_count,
            source_count,
            consistency_count_value,
            rationale,
            compact_json(metadata),
            now,
            now,
        ),
    )

    return int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    claims_seen: int,
    inserted: int,
    updated: int,
) -> None:
    total = conn.execute(
        "SELECT COUNT(*) FROM brain_claim_evaluations"
    ).fetchone()[0]

    rows = conn.execute(
        """
        SELECT verdict, COUNT(*) AS n
        FROM brain_claim_evaluations
        GROUP BY verdict
        ORDER BY
            CASE verdict
                WHEN 'SUPPORTIVE' THEN 1
                WHEN 'PROMISING' THEN 2
                WHEN 'NEEDS_REVIEW' THEN 3
                ELSE 4
            END
        """
    ).fetchall()

    print("=" * 76)
    print("MARKETHQ BRAIN EVALUATION ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("EVALUATION RUN")
    print("-" * 76)
    print(f"candidate_claims_seen                {claims_seen}")
    print(f"evaluations_inserted                 {inserted}")
    print(f"evaluations_updated                  {updated}")
    print()
    print("BRAIN CLAIM EVALUATION TABLE")
    print("-" * 76)
    print(f"total_evaluations                    {total}")
    for row in rows:
        print(f"{row['verdict'].lower():35s} {row['n']}")
    print()

    print("TOP EVALUATED CLAIMS")
    print("-" * 76)

    top = conn.execute(
        """
        SELECT
            e.score,
            e.verdict,
            e.sample_size,
            e.positive_rate,
            e.average_return_20d,
            e.evidence_count,
            c.claim_text
        FROM brain_claim_evaluations e
        JOIN brain_claims c
          ON c.id = e.claim_id
        ORDER BY e.score DESC, e.sample_size DESC
        LIMIT 15
        """
    ).fetchall()

    if not top:
        print("No evaluations.")
    else:
        for row in top:
            print(
                f"{safe_float(row['score']):.4f} | "
                f"{row['verdict']:12s} | "
                f"n={safe_int(row['sample_size']):5d} | "
                f"pos={safe_float(row['positive_rate']):.3f} | "
                f"avg20={safe_float(row['average_return_20d']):.4f} | "
                f"evidence={safe_int(row['evidence_count'])}"
            )
            print(f"  {row['claim_text']}")
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- Evaluation, claim'in kanıt/güç değerlendirmesidir.")
    print("- SUPPORTIVE = VERIFIED RULE değildir.")
    print("- Out-of-sample bağımsız doğrulama bu motor tarafından yapılmıyor.")
    print("- Ham experiment/result kayıtları değiştirilmedi.")
    print("- brain_claims kayıtları doğrulanmış kurala çevrilmedi.")
    print("- İleride AI reviewer'lar bu katmana bağımsız değerlendirme ekleyebilir.")
    print("- Sonraki aşama: evaluation -> learning event -> learned rule.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_evaluation_table(conn)

        claims = load_candidate_claims(conn)

        inserted = 0
        updated = 0

        for claim in claims:
            _, created = write_evaluation(
                conn,
                claim,
            )

            if created:
                inserted += 1
            else:
                updated += 1

        conn.commit()

        print_summary(
            conn=conn,
            claims_seen=len(claims),
            inserted=inserted,
            updated=updated,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

