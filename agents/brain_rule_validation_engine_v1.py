# -*- coding: utf-8 -*-
"""
MarketHQ Brain Rule Validation Engine V1
----------------------------------------
Learned Rule -> Temporal Holdout Validation

AMAÇ
----
brain_rule_promotion_engine_v1.py tarafından oluşturulan
"brain_promoted_candidate" learned_rules kayıtlarını, ham
experiment_result verisi üzerinde zaman bazlı bir holdout kontrolünden
geçirmek.

BU MOTOR NE YAPAR?
------------------
1) Brain tarafından promote edilmiş learned rule'ları bulur.
2) Rule'ın method/symbol/market/timeframe + regime/volume/volatility
   context koşullarını ham experiment_result kayıtlarına uygular.
3) Tarihe göre ilk %70'i "reference/training period",
   son %30'u "temporal holdout period" olarak ayırır.
4) Holdout sample üzerinde:
      - sample size
      - positive rate
      - average 20d return
      - best/worst 20d
      - hit consistency
   hesaplar.
5) Sonucu brain_rule_validations tablosunda saklar.
6) learned_rules kaydını VERIFIED yapmaz.
7) Ham veriye dokunmaz.

ÖNEMLİ EPISTEMIC SINIR
----------------------
Bu "temporal holdout check" gerçek anlamda bağımsız out-of-sample
doğrulama değildir; kuralın context'i mevcut historical dataset'ten
keşfedildiği için seçim yanlılığı tamamen ortadan kalkmaz.

Bu yüzden verdict:
    HOLDOUT_PASS
    HOLDOUT_WEAK
    INSUFFICIENT_DATA

"VERIFIED_RULE" üretmez.

V1 PASS şartları:
    - holdout sample >= 50
    - holdout positive rate >= 0.55
    - holdout average_return_20d > 0
    - learned rule positive rate >= 0.65
    - learned rule average_return_20d >= 5.0

Ayrıca holdout sonuçları, learned rule'ın in-sample değerleriyle
karşılaştırılır. Büyük bozulma varsa HOLDOUT_WEAK olur.

Çalıştırma:
    python agents/brain_rule_validation_engine_v1.py
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RULE_VALIDATION_ENGINE"
ENGINE_VERSION = "V1"

HOLDOUT_FRACTION = 0.30
MIN_HOLDOUT_SAMPLE = 50

# Rule-level reference thresholds.
MIN_HOLDOUT_POSITIVE_RATE = 0.55
MIN_HOLDOUT_AVG20 = 0.0

# A rule should not lose more than this much vs. its learned-rule metrics.
MAX_POSITIVE_RATE_DROP = 0.15
MAX_AVG20_DROP = 0.60

# Learned rule must still be a reasonably strong candidate.
MIN_RULE_POSITIVE_RATE = 0.65
MIN_RULE_AVG20 = 5.0


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
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_validation_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_rule_validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            validation_key TEXT NOT NULL UNIQUE,
            learned_rule_id INTEGER NOT NULL,
            validation_type TEXT NOT NULL,
            verdict TEXT NOT NULL,

            reference_sample_size INTEGER NOT NULL,
            holdout_sample_size INTEGER NOT NULL,

            reference_positive_rate REAL NOT NULL,
            holdout_positive_rate REAL NOT NULL,

            reference_average_return_20d REAL NOT NULL,
            holdout_average_return_20d REAL NOT NULL,

            holdout_best_return_20d REAL NOT NULL,
            holdout_worst_return_20d REAL NOT NULL,

            positive_rate_delta REAL NOT NULL,
            average_return_20d_ratio REAL,

            split_date TEXT,

            rationale TEXT,
            metadata_json TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY (learned_rule_id)
                REFERENCES learned_rules(id)
                ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_rule_validations_rule
        ON brain_rule_validations(learned_rule_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_rule_validations_verdict
        ON brain_rule_validations(verdict)
        """
    )


# ---------------------------------------------------------------------------
# RULE LOAD
# ---------------------------------------------------------------------------

def load_brain_rules(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            id,
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
        FROM learned_rules
        WHERE method_type = 'brain_promoted_candidate'
        ORDER BY id
        """
    ).fetchall()


# ---------------------------------------------------------------------------
# CONDITION PARSING
# ---------------------------------------------------------------------------

def parse_condition(condition_name: str) -> dict[str, str]:
    """
    Expected format:
        regime=Yukselen_Trend | volume=Yuksek |
        volatility=Orta | outcome=positive_20d
    """

    result: dict[str, str] = {}

    for part in normalize(condition_name).split("|"):
        text = part.strip()
        if "=" not in text:
            continue

        key, value = text.split("=", 1)
        result[key.strip()] = value.strip()

    return result


# ---------------------------------------------------------------------------
# RAW DATA MATCHING
# ---------------------------------------------------------------------------

def load_matching_results(
    conn: sqlite3.Connection,
    rule: sqlite3.Row,
    condition: dict[str, str],
) -> list[sqlite3.Row]:
    """
    Rule'ın method/symbol/market/timeframe context'ine uyan tüm ham
    result kayıtlarını getirir.

    outcome positive_20d burada filtrelenmez; önce tüm context sample'ı
    alınır, positive_rate result alanlarından hesaplanır.
    """

    regime = condition.get("regime", "")
    volume = condition.get("volume", "")
    volatility = condition.get("volatility", "")

    query = """
        SELECT
            er.id,
            er.experiment_id,
            er.observation_date,
            er.entry_price,
            er.price_20d,
            er.return_20d,
            er.result_20d,
            er.market_regime,
            er.volume_state,
            er.volatility_state,
            er.max_favorable_move,
            er.max_adverse_move
        FROM experiment_results er
        JOIN learning_experiments le
          ON le.id = er.experiment_id
        WHERE
            le.method_name = ?
            AND le.symbol = ?
            AND le.market = ?
            AND le.timeframe = ?
    """

    params: list[Any] = [
        normalize(rule["method_name"]),
        normalize(rule["symbol"]),
        normalize(rule["market"]),
        normalize(rule["timeframe"]),
    ]

    if regime:
        query += " AND er.market_regime = ?"
        params.append(regime)

    if volume:
        query += " AND er.volume_state = ?"
        params.append(volume)

    if volatility:
        query += " AND er.volatility_state = ?"
        params.append(volatility)

    query += """
        ORDER BY er.observation_date ASC, er.id ASC
    """

    return list(
        conn.execute(
            query,
            tuple(params),
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# METRIC CALCULATION
# ---------------------------------------------------------------------------

def is_positive_result(row: sqlite3.Row) -> bool:
    result = normalize(row["result_20d"]).lower()

    if result in {
        "positive",
        "win",
        "profit",
        "pozitif",
        "success",
    }:
        return True

    if result in {
        "negative",
        "loss",
        "fail",
        "negatif",
    }:
        return False

    return safe_float(row["return_20d"]) > 0


def return_values(rows: list[sqlite3.Row]) -> list[float]:
    values: list[float] = []

    for row in rows:
        value = row["return_20d"]
        if value is None:
            continue

        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    return values


def positive_rate(rows: list[sqlite3.Row]) -> float:
    if not rows:
        return 0.0

    positive = sum(
        1
        for row in rows
        if is_positive_result(row)
    )

    return positive / len(rows)


def average_return_20d(rows: list[sqlite3.Row]) -> float:
    values = return_values(rows)

    if not values:
        return 0.0

    return sum(values) / len(values)


def best_return_20d(rows: list[sqlite3.Row]) -> float:
    values = return_values(rows)
    return max(values) if values else 0.0


def worst_return_20d(rows: list[sqlite3.Row]) -> float:
    values = return_values(rows)
    return min(values) if values else 0.0


def split_reference_holdout(
    rows: list[sqlite3.Row],
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], str | None]:
    """
    Son %30 tarih bazlı holdout.

    En az 2 kayıt varsa bir split üretir.
    """

    if len(rows) < 2:
        return rows, [], None

    holdout_size = max(
        1,
        math.ceil(len(rows) * HOLDOUT_FRACTION),
    )

    if holdout_size >= len(rows):
        holdout_size = len(rows) - 1

    split_index = len(rows) - holdout_size

    reference = rows[:split_index]
    holdout = rows[split_index:]

    split_date = (
        normalize(holdout[0]["observation_date"])
        if holdout
        else None
    )

    return reference, holdout, split_date


# ---------------------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------------------

def evaluate_rule(
    rule: sqlite3.Row,
    reference: list[sqlite3.Row],
    holdout: list[sqlite3.Row],
) -> tuple[str, dict[str, Any]]:
    rule_pos = safe_float(rule["success_rate"])
    rule_avg20 = safe_float(rule["average_return_20d"])

    holdout_n = len(holdout)
    holdout_pos = positive_rate(holdout)
    holdout_avg20 = average_return_20d(holdout)

    pos_delta = holdout_pos - rule_pos

    if rule_avg20 == 0:
        avg_ratio = None
    else:
        avg_ratio = holdout_avg20 / rule_avg20

    checks = {
        "holdout_sample_ok": holdout_n >= MIN_HOLDOUT_SAMPLE,
        "holdout_positive_rate_ok": holdout_pos >= MIN_HOLDOUT_POSITIVE_RATE,
        "holdout_average_return_ok": holdout_avg20 > MIN_HOLDOUT_AVG20,
        "rule_positive_rate_ok": rule_pos >= MIN_RULE_POSITIVE_RATE,
        "rule_average_return_ok": rule_avg20 >= MIN_RULE_AVG20,
    }

    if holdout_n < MIN_HOLDOUT_SAMPLE:
        verdict = "INSUFFICIENT_DATA"
    elif not checks["rule_positive_rate_ok"]:
        verdict = "HOLDOUT_WEAK"
    elif not checks["rule_average_return_ok"]:
        verdict = "HOLDOUT_WEAK"
    elif holdout_pos < MIN_HOLDOUT_POSITIVE_RATE:
        verdict = "HOLDOUT_WEAK"
    elif holdout_avg20 <= MIN_HOLDOUT_AVG20:
        verdict = "HOLDOUT_WEAK"
    elif pos_delta < -MAX_POSITIVE_RATE_DROP:
        verdict = "HOLDOUT_WEAK"
    elif (
        rule_avg20 > 0
        and holdout_avg20 < rule_avg20 * MAX_AVG20_DROP
    ):
        # Example: if holdout average is less than 60% of rule average,
        # treat the historical effect as substantially degraded.
        verdict = "HOLDOUT_WEAK"
    else:
        verdict = "HOLDOUT_PASS"

    rationale = (
        f"verdict={verdict}; "
        f"holdout_n={holdout_n}; "
        f"holdout_positive_rate={holdout_pos:.4f}; "
        f"holdout_average_return_20d={holdout_avg20:.4f}; "
        f"rule_positive_rate={rule_pos:.4f}; "
        f"rule_average_return_20d={rule_avg20:.4f}; "
        f"positive_rate_delta={pos_delta:.4f}; "
        f"average_return_20d_ratio="
        f"{avg_ratio if avg_ratio is not None else 'NA'}."
    )

    metrics = {
        "rule_positive_rate": rule_pos,
        "rule_average_return_20d": rule_avg20,
        "reference_sample_size": len(reference),
        "holdout_sample_size": holdout_n,
        "reference_positive_rate": positive_rate(reference),
        "holdout_positive_rate": holdout_pos,
        "reference_average_return_20d": average_return_20d(reference),
        "holdout_average_return_20d": holdout_avg20,
        "holdout_best_return_20d": best_return_20d(holdout),
        "holdout_worst_return_20d": worst_return_20d(holdout),
        "positive_rate_delta": pos_delta,
        "average_return_20d_ratio": avg_ratio,
        "checks": checks,
        "rationale": rationale,
    }

    return verdict, metrics


# ---------------------------------------------------------------------------
# UPSERT VALIDATION
# ---------------------------------------------------------------------------

def validation_key(rule_id: int) -> str:
    return f"rule_validation:{rule_id}:{ENGINE_VERSION}"


def write_validation(
    conn: sqlite3.Connection,
    rule: sqlite3.Row,
    verdict: str,
    metrics: dict[str, Any],
    split_date: str | None,
) -> tuple[int, bool]:
    key = validation_key(int(rule["id"]))
    now = utc_now()

    existing = conn.execute(
        """
        SELECT id
        FROM brain_rule_validations
        WHERE validation_key = ?
        """,
        (key,),
    ).fetchone()

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "learned_rule_id": int(rule["id"]),
        "method_name": normalize(rule["method_name"]),
        "symbol": normalize(rule["symbol"]),
        "market": normalize(rule["market"]),
        "timeframe": normalize(rule["timeframe"]),
        "condition_name": normalize(rule["condition_name"]),
        "validation_limitations": [
            "temporal_holdout_not_fully_independent",
            "rule_context_was_discovered_from_same_historical_dataset",
            "no_forward_live_data",
            "no_live_trading",
            "not_a_verified_rule",
        ],
        "metrics": metrics,
    }

    if existing:
        conn.execute(
            """
            UPDATE brain_rule_validations
            SET
                verdict = ?,
                reference_sample_size = ?,
                holdout_sample_size = ?,
                reference_positive_rate = ?,
                holdout_positive_rate = ?,
                reference_average_return_20d = ?,
                holdout_average_return_20d = ?,
                holdout_best_return_20d = ?,
                holdout_worst_return_20d = ?,
                positive_rate_delta = ?,
                average_return_20d_ratio = ?,
                split_date = ?,
                rationale = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE validation_key = ?
            """,
            (
                verdict,
                safe_int(metrics["reference_sample_size"]),
                safe_int(metrics["holdout_sample_size"]),
                safe_float(metrics["reference_positive_rate"]),
                safe_float(metrics["holdout_positive_rate"]),
                safe_float(metrics["reference_average_return_20d"]),
                safe_float(metrics["holdout_average_return_20d"]),
                safe_float(metrics["holdout_best_return_20d"]),
                safe_float(metrics["holdout_worst_return_20d"]),
                safe_float(metrics["positive_rate_delta"]),
                metrics["average_return_20d_ratio"],
                split_date,
                normalize(metrics["rationale"]),
                compact_json(metadata),
                now,
                key,
            ),
        )
        return int(existing["id"]), False

    cur = conn.execute(
        """
        INSERT INTO brain_rule_validations (
            validation_key,
            learned_rule_id,
            validation_type,
            verdict,
            reference_sample_size,
            holdout_sample_size,
            reference_positive_rate,
            holdout_positive_rate,
            reference_average_return_20d,
            holdout_average_return_20d,
            holdout_best_return_20d,
            holdout_worst_return_20d,
            positive_rate_delta,
            average_return_20d_ratio,
            split_date,
            rationale,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            int(rule["id"]),
            "temporal_holdout_v1",
            verdict,
            safe_int(metrics["reference_sample_size"]),
            safe_int(metrics["holdout_sample_size"]),
            safe_float(metrics["reference_positive_rate"]),
            safe_float(metrics["holdout_positive_rate"]),
            safe_float(metrics["reference_average_return_20d"]),
            safe_float(metrics["holdout_average_return_20d"]),
            safe_float(metrics["holdout_best_return_20d"]),
            safe_float(metrics["holdout_worst_return_20d"]),
            safe_float(metrics["positive_rate_delta"]),
            metrics["average_return_20d_ratio"],
            split_date,
            normalize(metrics["rationale"]),
            compact_json(metadata),
            now,
            now,
        ),
    )

    return int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# OPTIONAL BRAIN EVENT
# ---------------------------------------------------------------------------

def write_validation_learning_event(
    conn: sqlite3.Connection,
    rule: sqlite3.Row,
    validation_id: int,
    verdict: str,
    metrics: dict[str, Any],
) -> int | None:
    """
    Mevcut brain_learning_events tablosuna validation event'i ekler.

    learned_rule_id dolu bırakılır; decision yalnızca validation sonucunu
    ifade eder. Bu event rule'ı değiştirmez.
    """

    event_type = "RULE_VALIDATION"
    source_claim_id = None

    row = conn.execute(
        """
        SELECT id
        FROM brain_learning_events
        WHERE
            event_type = ?
            AND learned_rule_id = ?
            AND metadata_json LIKE ?
        LIMIT 1
        """,
        (
            event_type,
            int(rule["id"]),
            f'%"validation_id":{validation_id}%',
        ),
    ).fetchone()

    if row:
        return int(row["id"])

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "validation_id": validation_id,
        "learned_rule_id": int(rule["id"]),
        "verdict": verdict,
        "holdout_sample_size": safe_int(
            metrics["holdout_sample_size"]
        ),
        "holdout_positive_rate": safe_float(
            metrics["holdout_positive_rate"]
        ),
        "holdout_average_return_20d": safe_float(
            metrics["holdout_average_return_20d"]
        ),
        "note": (
            "Temporal holdout validation event. "
            "Not a verified live rule."
        ),
    }

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
        VALUES (?, NULL, NULL, ?, ?, NULL, NULL, ?, ?, ?, ?)
        """,
        (
            event_type,
            int(rule["id"]),
            source_claim_id,
            safe_float(metrics["holdout_positive_rate"]),
            verdict,
            utc_now(),
            compact_json(metadata),
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    rules_seen: int,
    validations_inserted: int,
    validations_updated: int,
    pass_count: int,
    weak_count: int,
    insufficient_count: int,
) -> None:
    total_validations = conn.execute(
        "SELECT COUNT(*) FROM brain_rule_validations"
    ).fetchone()[0]

    print("=" * 76)
    print("MARKETHQ BRAIN RULE VALIDATION ENGINE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()
    print("VALIDATION RUN")
    print("-" * 76)
    print(f"brain_promoted_rules_seen             {rules_seen}")
    print(f"validations_inserted                  {validations_inserted}")
    print(f"validations_updated                   {validations_updated}")
    print(f"holdout_pass                          {pass_count}")
    print(f"holdout_weak                          {weak_count}")
    print(f"insufficient_data                     {insufficient_count}")
    print()
    print("BRAIN RULE VALIDATION TABLE")
    print("-" * 76)
    print(f"total_validations                     {total_validations}")
    print()

    print("VALIDATION RESULTS")
    print("-" * 76)

    rows = conn.execute(
        """
        SELECT
            v.learned_rule_id,
            v.verdict,
            v.holdout_sample_size,
            v.holdout_positive_rate,
            v.holdout_average_return_20d,
            v.positive_rate_delta,
            v.split_date,
            r.method_name,
            r.symbol,
            r.market,
            r.timeframe,
            r.condition_name
        FROM brain_rule_validations v
        JOIN learned_rules r
          ON r.id = v.learned_rule_id
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
        print("No validation results.")
    else:
        for row in rows:
            print(
                f"rule_id={row['learned_rule_id']} | "
                f"{row['verdict']:17s} | "
                f"holdout_n={safe_int(row['holdout_sample_size']):4d} | "
                f"pos={safe_float(row['holdout_positive_rate']):.3f} | "
                f"avg20={safe_float(row['holdout_average_return_20d']):.4f} | "
                f"delta={safe_float(row['positive_rate_delta']):+.3f}"
            )
            print(
                f"  {normalize(row['symbol'])} | "
                f"{normalize(row['method_name'])} | "
                f"{normalize(row['condition_name'])}"
            )
            print(
                f"  split_date={normalize(row['split_date']) or 'N/A'}"
            )
            print()

    print("IMPORTANT")
    print("-" * 76)
    print("- Bu motor learned rule'ları yeniden yazmıyor.")
    print("- Ham experiment/result verileri değiştirilmedi.")
    print("- HOLDOUT_PASS = tarihsel holdout kontrolü geçti.")
    print("- HOLDOUT_PASS != VERIFIED RULE.")
    print("- Temporal holdout tamamen bağımsız OOS test değildir.")
    print("- Rule'ın context'i aynı historical dataset'ten keşfedildi.")
    print("- Sonraki aşama: brain update + AI review + daha güçlü validation.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        ensure_validation_table(conn)

        rules = load_brain_rules(conn)

        inserted = 0
        updated = 0
        pass_count = 0
        weak_count = 0
        insufficient_count = 0

        for rule in rules:
            condition = parse_condition(
                normalize(rule["condition_name"])
            )

            raw_rows = load_matching_results(
                conn,
                rule,
                condition,
            )

            reference, holdout, split_date = split_reference_holdout(
                raw_rows
            )

            verdict, metrics = evaluate_rule(
                rule,
                reference,
                holdout,
            )

            validation_id, created = write_validation(
                conn,
                rule,
                verdict,
                metrics,
                split_date,
            )

            if created:
                inserted += 1
            else:
                updated += 1

            if verdict == "HOLDOUT_PASS":
                pass_count += 1
            elif verdict == "HOLDOUT_WEAK":
                weak_count += 1
            else:
                insufficient_count += 1

            # Validation olayını Brain event history'ye yaz.
            write_validation_learning_event(
                conn=conn,
                rule=rule,
                validation_id=validation_id,
                verdict=verdict,
                metrics=metrics,
            )

        conn.commit()

        print_summary(
            conn=conn,
            rules_seen=len(rules),
            validations_inserted=inserted,
            validations_updated=updated,
            pass_count=pass_count,
            weak_count=weak_count,
            insufficient_count=insufficient_count,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

