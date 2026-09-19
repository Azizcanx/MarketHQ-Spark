# -*- coding: utf-8 -*-
"""
MarketHQ Brain Rule Promotion Engine V1
---------------------------------------
Learning Event -> Learned Rule

Amaç:
    brain_learning_events içindeki
    PROMOTE_TO_RULE_CANDIDATE kayıtlarını kontrollü biçimde
    learned_rules tablosuna taşımak.

Bu sürüm:
    - Ham experiment/result kayıtlarına dokunmaz.
    - Claim ve evaluation kayıtlarını değiştirmez.
    - Sadece promotion kararı zaten alınmış adayları inceler.
    - Aynı context içinde birden fazla method/version adayını
      karşılaştırır ve en güçlü adayı seçer.
    - learned_rules UNIQUE(method_name, symbol, timeframe, condition_name)
      yapısına saygı gösterir.
    - Promotion audit tablosu ile sonucu izlenebilir tutar.
    - brain_learning_events.learned_rule_id alanını yalnızca
      gerçekten oluşturulan / mevcut kurala bağlanan event için günceller.
    - "learned rule" adını veritabanı anlamında kullanır; bu kayıt
      bağımsız out-of-sample doğrulama veya canlı işlem garantisi değildir.

Promotion pipeline:

    EVALUATION
        ↓
    LEARNING EVENT
        ↓
    PROMOTE_TO_RULE_CANDIDATE
        ↓
    CONTEXT DEDUPLICATION
        ↓
    RULE PROMOTION
        ↓
    learned_rules
        ↓
    brain_learning_events.learned_rule_id

V1 politika:
    1) Sadece decision='PROMOTE_TO_RULE_CANDIDATE'
    2) Verdict SUPPORTIVE olmalı
    3) Score >= 0.75
    4) Sample >= 250
    5) Evidence >= 1
    6) Positive rate >= 0.65
    7) Average return 20d >= 5.0
    8) Aynı context içinde en yüksek evaluation score seçilir.
       Eşitlikte daha büyük sample seçilir.
    9) Existing learned_rule varsa yeni duplicate yazılmaz.

Çalıştırma:
    python agents/brain_rule_promotion_engine_v1.py
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

ENGINE_NAME = "MARKETHQ_BRAIN_RULE_PROMOTION_ENGINE"
ENGINE_VERSION = "V1"

MIN_SCORE = 0.75
MIN_SAMPLE = 250
MIN_EVIDENCE = 1
MIN_POSITIVE_RATE = 0.65
MIN_AVG20 = 5.0


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

def ensure_promotion_audit_table(conn: sqlite3.Connection) -> None:
    """
    Rule promotion denemelerinin kalıcı audit izi.

    Aynı candidate event tekrar çalıştırıldığında duplicate audit oluşmaz.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_rule_promotion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promotion_key TEXT NOT NULL UNIQUE,
            learning_event_id INTEGER NOT NULL,
            source_claim_id INTEGER,
            evaluation_id INTEGER,
            learned_rule_id INTEGER,
            decision TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            method_name TEXT,
            symbol TEXT,
            market TEXT,
            timeframe TEXT,
            market_regime TEXT,
            volume_state TEXT,
            volatility_state TEXT,
            score REAL,
            sample_size INTEGER,
            positive_rate REAL,
            average_return_20d REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_promo_learning_event
        ON brain_rule_promotion_events(learning_event_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_promo_decision
        ON brain_rule_promotion_events(decision, status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_promo_symbol
        ON brain_rule_promotion_events(symbol, market, timeframe)
        """
    )


# ---------------------------------------------------------------------------
# LOAD CANDIDATES
# ---------------------------------------------------------------------------

def load_promotion_candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Learning event + evaluation + claim + observation.

    Evaluation id metadata içinden alınır çünkü brain_learning_events
    V1 şemasında doğrudan evaluation_id kolonu yok.
    """

    rows = conn.execute(
        """
        SELECT
            le.id AS learning_event_id,
            le.source_claim_id,
            le.learned_rule_id,
            le.score AS event_score,
            le.decision,
            le.metadata_json AS event_metadata,

            c.claim_key,
            c.claim_text,
            c.claim_type,
            c.status AS claim_status,

            e.id AS evaluation_id,
            e.evaluation_key,
            e.verdict,
            e.score AS evaluation_score,
            e.sample_size,
            e.positive_rate,
            e.average_return_20d,
            e.evidence_count,
            e.source_count,
            e.consistency_count,

            o.id AS observation_id,
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

        FROM brain_learning_events le

        JOIN brain_claims c
          ON c.id = le.source_claim_id

        JOIN brain_claim_evaluations e
          ON e.claim_id = c.id

        LEFT JOIN brain_observations o
          ON o.id = e.observation_id

        WHERE
            le.event_type = 'CLAIM_EVALUATION'
            AND le.decision = 'PROMOTE_TO_RULE_CANDIDATE'
            AND c.claim_type = 'candidate'
            AND c.status = 'active'
            AND e.verdict = 'SUPPORTIVE'

        ORDER BY
            e.score DESC,
            e.sample_size DESC,
            le.id ASC
        """
    ).fetchall()

    return list(rows)


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def passes_thresholds(row: sqlite3.Row) -> tuple[bool, list[str]]:
    failures: list[str] = []

    score = safe_float(row["evaluation_score"])
    sample = safe_int(row["sample_size"])
    evidence = safe_int(row["evidence_count"])
    positive_rate = safe_float(row["positive_rate"])
    avg20 = safe_float(row["average_return_20d"])

    if normalize(row["verdict"]).upper() != "SUPPORTIVE":
        failures.append("verdict_not_supportive")

    if score < MIN_SCORE:
        failures.append("score_below_threshold")

    if sample < MIN_SAMPLE:
        failures.append("sample_below_threshold")

    if evidence < MIN_EVIDENCE:
        failures.append("evidence_below_threshold")

    if positive_rate < MIN_POSITIVE_RATE:
        failures.append("positive_rate_below_threshold")

    if avg20 < MIN_AVG20:
        failures.append("average_return_20d_below_threshold")

    return not failures, failures


# ---------------------------------------------------------------------------
# CONTEXT DEDUP
# ---------------------------------------------------------------------------

def context_key(row: sqlite3.Row) -> str:
    """
    Method/version deliberately NOT included.

    Böylece aynı:
        symbol + market + timeframe +
        regime + volume + volatility

    context'inde farklı method/version adayları tek ailede
    karşılaştırılabilir.
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


def choose_context_winner(rows: list[sqlite3.Row]) -> sqlite3.Row:
    """
    En yüksek evaluation score kazanır.
    Eşitlikte sample size, sonra evidence count kullanılır.
    """

    return max(
        rows,
        key=lambda r: (
            safe_float(r["evaluation_score"]),
            safe_int(r["sample_size"]),
            safe_int(r["evidence_count"]),
        ),
    )


def condition_name(row: sqlite3.Row) -> str:
    """
    learned_rules.condition_name için deterministik context.

    Method name ayrı alanda, context bu alanda tutulur.
    """

    parts = [
        f"regime={normalize(row['market_regime']) or 'unspecified'}",
        f"volume={normalize(row['volume_state']) or 'unspecified'}",
        f"volatility={normalize(row['volatility_state']) or 'unspecified'}",
        "outcome=positive_20d",
    ]

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# EXISTING RULE
# ---------------------------------------------------------------------------

def find_existing_rule(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    rule_condition: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM learned_rules
        WHERE
            method_name = ?
            AND symbol = ?
            AND timeframe = ?
            AND condition_name = ?
        LIMIT 1
        """,
        (
            normalize(row["method_name"]),
            normalize(row["symbol"]),
            normalize(row["timeframe"]),
            rule_condition,
        ),
    ).fetchone()


# ---------------------------------------------------------------------------
# INSERT RULE
# ---------------------------------------------------------------------------

def insert_learned_rule(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    rule_condition: str,
) -> tuple[int, bool]:
    existing = find_existing_rule(
        conn,
        row,
        rule_condition,
    )

    if existing:
        return int(existing["id"]), False

    now = utc_now()

    success_rate = safe_float(row["positive_rate"])
    avg_return = safe_float(row["average_return_20d"])
    confidence = safe_float(row["evaluation_score"])

    observation_text = (
        f"Promoted from candidate claim. "
        f"symbol={normalize(row['symbol'])}; "
        f"market={normalize(row['market'])}; "
        f"context={rule_condition}; "
        f"sample={safe_int(row['sample_size'])}; "
        f"positive_rate={success_rate:.4f}; "
        f"average_return_20d={avg_return:.4f}; "
        f"evaluation_score={confidence:.4f}. "
        "Bu kayıt historical research-derived learned rule'dur; "
        "bağımsız out-of-sample doğrulanmış canlı işlem kuralı değildir."
    )

    try:
        cur = conn.execute(
            """
            INSERT INTO learned_rules (
                method_name,
                method_type,
                symbol,
                market,
                timeframe,
                condition_name,
                sample_size,
                success_rate,
                average_return,
                average_return_5d,
                average_return_20d,
                best_return,
                worst_return,
                confidence,
                observation,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalize(row["method_name"]),
                "brain_promoted_candidate",
                normalize(row["symbol"]),
                normalize(row["market"]),
                normalize(row["timeframe"]),
                rule_condition,
                safe_int(row["sample_size"]),
                success_rate,
                # learned_rules.average_return is general/primary return field.
                avg_return,
                0.0,
                avg_return,
                avg_return,
                avg_return,
                confidence,
                observation_text,
                now,
            ),
        )
    except sqlite3.IntegrityError:
        # UNIQUE constraint varsa mevcut rule'ı yeniden bul.
        existing_after_race = find_existing_rule(
            conn,
            row,
            rule_condition,
        )

        if existing_after_race:
            return int(existing_after_race["id"]), False

        raise

    return int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# BRAIN EVENT UPDATE
# ---------------------------------------------------------------------------

def attach_rule_to_learning_event(
    conn: sqlite3.Connection,
    event_id: int,
    rule_id: int,
) -> None:
    conn.execute(
        """
        UPDATE brain_learning_events
        SET learned_rule_id = ?
        WHERE id = ?
        """,
        (
            rule_id,
            event_id,
        ),
    )


# ---------------------------------------------------------------------------
# AUDIT
# ---------------------------------------------------------------------------

def promotion_key(row: sqlite3.Row) -> str:
    return (
        "promotion:"
        + stable_hash(
            ENGINE_NAME,
            ENGINE_VERSION,
            row["learning_event_id"],
        )
    )


def audit(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    decision: str,
    status: str,
    reason: str,
    learned_rule_id: int | None,
) -> None:
    key = promotion_key(row)
    now = utc_now()

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "learning_event_id": int(row["learning_event_id"]),
        "claim_id": safe_int(row["source_claim_id"]),
        "evaluation_id": safe_int(row["evaluation_id"]),
        "rule_id": learned_rule_id,
        "decision": decision,
        "status": status,
        "reason": reason,
        "context_key": context_key(row),
        "condition_name": condition_name(row),
        "method_name": normalize(row["method_name"]),
        "symbol": normalize(row["symbol"]),
        "market": normalize(row["market"]),
        "timeframe": normalize(row["timeframe"]),
        "market_regime": normalize(row["market_regime"]),
        "volume_state": normalize(row["volume_state"]),
        "volatility_state": normalize(row["volatility_state"]),
        "score": safe_float(row["evaluation_score"]),
        "sample_size": safe_int(row["sample_size"]),
        "positive_rate": safe_float(row["positive_rate"]),
        "average_return_20d": safe_float(row["average_return_20d"]),
        "evidence_count": safe_int(row["evidence_count"]),
        "source_count": safe_int(row["source_count"]),
    }

    existing = conn.execute(
        """
        SELECT id
        FROM brain_rule_promotion_events
        WHERE promotion_key = ?
        """,
        (key,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE brain_rule_promotion_events
            SET
                learned_rule_id = ?,
                decision = ?,
                status = ?,
                reason = ?,
                score = ?,
                sample_size = ?,
                positive_rate = ?,
                average_return_20d = ?,
                updated_at = ?,
                metadata_json = ?
            WHERE promotion_key = ?
            """,
            (
                learned_rule_id,
                decision,
                status,
                reason,
                safe_float(row["evaluation_score"]),
                safe_int(row["sample_size"]),
                safe_float(row["positive_rate"]),
                safe_float(row["average_return_20d"]),
                now,
                compact_json(metadata),
                key,
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO brain_rule_promotion_events (
            promotion_key,
            learning_event_id,
            source_claim_id,
            evaluation_id,
            learned_rule_id,
            decision,
            status,
            reason,
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volume_state,
            volatility_state,
            score,
            sample_size,
            positive_rate,
            average_return_20d,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            int(row["learning_event_id"]),
            safe_int(row["source_claim_id"]),
            safe_int(row["evaluation_id"]),
            learned_rule_id,
            decision,
            status,
            reason,
            normalize(row["method_name"]),
            normalize(row["symbol"]),
            normalize(row["market"]),
            normalize(row["timeframe"]),
            normalize(row["market_regime"]),
            normalize(row["volume_state"]),
            normalize(row["volatility_state"]),
            safe_float(row["evaluation_score"]),
            safe_int(row["sample_size"]),
            safe_float(row["positive_rate"]),
            safe_float(row["average_return_20d"]),
            now,
            now,
            compact_json(metadata),
        ),
    )


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    total_candidates: int,
    valid_candidates: int,
    context_groups: int,
    duplicate_context_skipped: int,
    rules_inserted: int,
    rules_existing: int,
    events_linked: int,
    held: int,
) -> None:
    total_rules = conn.execute(
        "SELECT COUNT(*) FROM learned_rules"
    ).fetchone()[0]

    brain_promoted = conn.execute(
        """
        SELECT COUNT(*)
        FROM learned_rules
        WHERE method_type = 'brain_promoted_candidate'
        """
    ).fetchone()[0]

    promo_events = conn.execute(
        "SELECT COUNT(*) FROM brain_rule_promotion_events"
    ).fetchone()[0]

    print("=" * 76)
    print("MARKETHQ BRAIN RULE PROMOTION ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("RULE PROMOTION RUN")
    print("-" * 76)
    print(f"promotion_candidates_seen             {total_candidates}")
    print(f"threshold_valid_candidates            {valid_candidates}")
    print(f"context_groups_seen                   {context_groups}")
    print(f"duplicate_context_skipped             {duplicate_context_skipped}")
    print(f"learned_rules_inserted                {rules_inserted}")
    print(f"learned_rules_already_present         {rules_existing}")
    print(f"learning_events_linked                {events_linked}")
    print(f"held_for_review                       {held}")
    print()
    print("RULE TABLE")
    print("-" * 76)
    print(f"total_learned_rules                   {total_rules}")
    print(f"brain_promoted_candidate_rules        {brain_promoted}")
    print(f"promotion_audit_events                {promo_events}")
    print()

    print("BRAIN-PROMOTED RULES")
    print("-" * 76)

    rows = conn.execute(
        """
        SELECT
            id,
            method_name,
            symbol,
            market,
            timeframe,
            condition_name,
            sample_size,
            success_rate,
            average_return_20d,
            confidence
        FROM learned_rules
        WHERE method_type = 'brain_promoted_candidate'
        ORDER BY confidence DESC, sample_size DESC
        LIMIT 15
        """
    ).fetchall()

    if not rows:
        print("No brain-promoted rules.")
    else:
        for row in rows:
            print(
                f"id={row['id']} | "
                f"score={safe_float(row['confidence']):.4f} | "
                f"n={safe_int(row['sample_size']):5d} | "
                f"pos={safe_float(row['success_rate']):.3f} | "
                f"avg20={safe_float(row['average_return_20d']):.4f}"
            )
            print(
                f"  {normalize(row['symbol'])} | "
                f"{normalize(row['method_name'])} | "
                f"{normalize(row['condition_name'])}"
            )
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- Bu katman yalnızca promotion candidate'ları learned_rules'a taşır.")
    print("- Context duplicate'lerinde tek güçlü aday seçilir.")
    print("- Existing learned rule varsa duplicate yazılmaz.")
    print("- Learned rule = historical research memory kaydıdır.")
    print("- Bu kayıt bağımsız out-of-sample doğrulama veya canlı işlem garantisi değildir.")
    print("- Ham experiment/result kayıtları değiştirilmedi.")
    print("- Bir sonraki aşama: rule validation / brain update / AI review.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_promotion_audit_table(conn)

        candidates = load_promotion_candidates(conn)

        valid: list[sqlite3.Row] = []
        held = 0

        for row in candidates:
            passed, _ = passes_thresholds(row)

            if passed:
                valid.append(row)
            else:
                held += 1
                audit(
                    conn=conn,
                    row=row,
                    decision="HOLD_FOR_REVIEW",
                    status="held",
                    reason="promotion thresholds not satisfied",
                    learned_rule_id=None,
                )

        # Group valid candidates by context.
        groups: dict[str, list[sqlite3.Row]] = {}
        for row in valid:
            groups.setdefault(context_key(row), []).append(row)

        context_winners: dict[int, sqlite3.Row] = {}
        duplicate_context_skipped = 0

        for _, members in groups.items():
            winner = choose_context_winner(members)

            for row in members:
                context_winners[int(row["learning_event_id"])] = winner

                if int(row["learning_event_id"]) != int(
                    winner["learning_event_id"]
                ):
                    duplicate_context_skipped += 1
                    audit(
                        conn=conn,
                        row=row,
                        decision="HOLD_FOR_REVIEW",
                        status="context_duplicate",
                        reason=(
                            "same context has a stronger promotion candidate; "
                            f"winner_learning_event={int(winner['learning_event_id'])}"
                        ),
                        learned_rule_id=None,
                    )

        rules_inserted = 0
        rules_existing = 0
        events_linked = 0

        promoted_event_ids: set[int] = set()

        for row in valid:
            winner = context_winners[int(row["learning_event_id"])]

            if int(row["learning_event_id"]) != int(
                winner["learning_event_id"]
            ):
                continue

            promoted_event_ids.add(int(row["learning_event_id"]))

            rule_condition = condition_name(row)

            rule_id, created = insert_learned_rule(
                conn=conn,
                row=row,
                rule_condition=rule_condition,
            )

            if created:
                rules_inserted += 1
            else:
                rules_existing += 1

            attach_rule_to_learning_event(
                conn,
                int(row["learning_event_id"]),
                rule_id,
            )
            events_linked += 1

            audit(
                conn=conn,
                row=row,
                decision="PROMOTED",
                status="promoted",
                reason=(
                    "promotion candidate passed thresholds and won "
                    "context-level deduplication"
                ),
                learned_rule_id=rule_id,
            )

        conn.commit()

        print_summary(
            conn=conn,
            total_candidates=len(candidates),
            valid_candidates=len(valid),
            context_groups=len(groups),
            duplicate_context_skipped=duplicate_context_skipped,
            rules_inserted=rules_inserted,
            rules_existing=rules_existing,
            events_linked=events_linked,
            held=held,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

