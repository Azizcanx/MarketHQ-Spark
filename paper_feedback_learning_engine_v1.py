# -*- coding: utf-8 -*-
"""
MarketHQ Paper Feedback & Learning Engine V1.2
================================================

Amaç:
    Paper Trading Engine çıktısını MarketHQ öğrenme katmanına taşımak.

Akış:
    paper_trading_results/*.json
              ↓
        Feedback Engine
              ↓
    learning_experiments
              ↓
      experiment_results
              ↓
    brain_learning_events
              ↓
    Araştırma / tekrar test kararı

ÖNEMLİ GÜVENLİK SINIRLARI:
    - Gerçek emir göndermez.
    - Broker bağlantısı yapmaz.
    - Gerçek para ile işlem yapmaz.
    - Paper sonucu "doğrulanmış kural" olarak kabul etmez.
    - learned_rules tablosuna otomatik olarak kural yazmaz.
    - Sonuçları idempotent şekilde kaydeder.
    - Zayıf sonuçlarda yeni araştırma kuyruğu oluşturabilir.

Bu motor, mevcut MarketHQ Brain şemasındaki:
    learning_experiments
    experiment_results
    brain_learning_events
    brain_research_queue

tablolarını kullanır.

Çalıştırma:
    .\\.venv\\Scripts\\python.exe paper_feedback_learning_engine_v1.py

Belirli bir paper sonucu:
    .\\.venv\\Scripts\\python.exe paper_feedback_learning_engine_v1.py --file <JSON_DOSYASI>

Belirli strateji:
    .\\.venv\\Scripts\\python.exe paper_feedback_learning_engine_v1.py --strategy-id STR-XXXX
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# PATHS / CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DB_PATH = PROJECT_ROOT / "market_hq.db"
PAPER_RESULTS_DIR = PROJECT_ROOT / "paper_trading_results"
FEEDBACK_RESULTS_DIR = PROJECT_ROOT / "paper_feedback_results"

ENGINE_NAME = "MARKETHQ_PAPER_FEEDBACK_LEARNING_ENGINE"
ENGINE_VERSION = "V1.2"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

# Paper sonucu sınıflandırma eşikleri.
# Bunlar "strateji doğrulandı" anlamına gelmez.
MIN_TRADES_FOR_SUPPORT = 20
MIN_WIN_RATE_FOR_SUPPORT = 50.0
MIN_PROFIT_FACTOR_FOR_SUPPORT = 1.05
MIN_RETURN_FOR_SUPPORT = 0.0

MIN_TRADES_FOR_REVIEW = 8

# Araştırma kuyruğu önceliği.
QUEUE_PRIORITY_WEAK = 7.0
QUEUE_PRIORITY_MIXED = 6.0


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


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
        default=str,
    )


def pretty_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def stable_hash(*parts: Any) -> str:
    raw = "|".join(normalize(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================================
# DATABASE
# ============================================================================

def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        normalize(row["name"])
        for row in rows
    }


def ensure_schema_compatibility(
    conn: sqlite3.Connection,
) -> None:
    required = {
        "learning_experiments",
        "experiment_results",
        "brain_learning_events",
    }

    missing = [
        name
        for name in sorted(required)
        if not table_exists(conn, name)
    ]

    if missing:
        raise RuntimeError(
            "MarketHQ öğrenme şeması eksik. "
            "Eksik tablolar: "
            + ", ".join(missing)
        )

    experiment_columns = table_columns(
        conn,
        "learning_experiments",
    )

    result_columns = table_columns(
        conn,
        "experiment_results",
    )

    learning_event_columns = table_columns(
        conn,
        "brain_learning_events",
    )

    required_experiment_columns = {
        "id",
        "knowledge_id",
        "method_name",
        "method_type",
        "symbol",
        "market",
        "timeframe",
        "signal_direction",
        "start_date",
        "end_date",
        "status",
        "parameters_json",
        "created_at",
    }

    required_result_columns = {
        "id",
        "experiment_id",
        "observation_date",
        "entry_price",
        "return_20d",
        "result_20d",
        "market_regime",
        "volume_state",
        "volatility_state",
        "metadata_json",
        "created_at",
    }

    required_event_columns = {
        "id",
        "event_type",
        "experiment_id",
        "experiment_result_id",
        "learned_rule_id",
        "source_claim_id",
        "score",
        "decision",
        "created_at",
        "metadata_json",
    }

    missing_experiment = (
        required_experiment_columns
        - experiment_columns
    )

    missing_result = (
        required_result_columns
        - result_columns
    )

    missing_event = (
        required_event_columns
        - learning_event_columns
    )

    if missing_experiment:
        raise RuntimeError(
            "learning_experiments şeması uyumsuz. "
            "Eksik: "
            + ", ".join(sorted(missing_experiment))
        )

    if missing_result:
        raise RuntimeError(
            "experiment_results şeması uyumsuz. "
            "Eksik: "
            + ", ".join(sorted(missing_result))
        )

    if missing_event:
        raise RuntimeError(
            "brain_learning_events şeması uyumsuz. "
            "Eksik: "
            + ", ".join(sorted(missing_event))
        )


# ============================================================================
# PAPER RESULT LOAD
# ============================================================================

def load_json(path: Path) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(
            f"JSON object bekleniyordu: {path}"
        )

    return data


def paper_result_files() -> list[Path]:
    if not PAPER_RESULTS_DIR.exists():
        return []

    return sorted(
        [
            path
            for path in PAPER_RESULTS_DIR.glob(
                "*.json"
            )
            if path.is_file()
        ],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def select_paper_result(
    explicit_file: str | None = None,
    strategy_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    if explicit_file:
        path = Path(explicit_file)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if not path.exists():
            raise FileNotFoundError(
                f"Paper sonucu bulunamadı: {path}"
            )

        data = load_json(path)

        return path, data

    candidates = paper_result_files()

    if strategy_id:
        filtered: list[tuple[Path, dict[str, Any]]] = []

        for path in candidates:
            try:
                data = load_json(path)
            except Exception:
                continue

            current_id = extract_strategy_id(
                path,
                data,
            )

            if current_id.upper() == strategy_id.upper():
                filtered.append(
                    (path, data)
                )

        candidates = [
            item[0]
            for item in filtered
        ]

        if filtered:
            return filtered[0]

    if not candidates:
        raise FileNotFoundError(
            "paper_trading_results klasöründe "
            "JSON sonucu bulunamadı."
        )

    path = candidates[0]
    data = load_json(path)

    return path, data


# ============================================================================
# ROBUST PAPER RESULT FIELD EXTRACTION
# ============================================================================

STRATEGY_ID_PATTERN = re.compile(
    r"\bSTR-[A-Z0-9]{6,20}\b",
    re.IGNORECASE,
)


def find_value_recursive(
    data: Any,
    keys: set[str],
) -> Any:
    """
    JSON içinde alanı recursive arar.

    Paper Trading Engine sürümleri arasında:
        strategy_id
        strategy
        strategy_metadata
        metadata
    gibi farklı nesting olabileceği için kullanılır.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if normalize(key).lower() in {
                item.lower()
                for item in keys
            }:
                return value

        for value in data.values():
            found = find_value_recursive(
                value,
                keys,
            )

            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = find_value_recursive(
                item,
                keys,
            )

            if found is not None:
                return found

    return None


def extract_strategy_id(
    path: Path,
    data: dict[str, Any],
) -> str:
    """
    Strategy ID için güvenli fallback sırası:

    1. JSON içindeki strategy_id
    2. strategy metadata içindeki strategy_id
    3. herhangi bir nested strategy_id
    4. strategy name / id alanlarında STR-XXXX
    5. paper result filename içindeki STR-XXXX

    Böylece Paper Trading Engine'in JSON şeması küçük
    değişiklikler yaptığında Feedback Engine kırılmaz.
    """
    direct = find_value_recursive(
        data,
        {
            "strategy_id",
            "strategyId",
        },
    )

    if direct:
        match = STRATEGY_ID_PATTERN.search(
            normalize(direct)
        )

        if match:
            return match.group(0).upper()

    for key in (
        "strategy",
        "strategy_name",
        "strategyName",
        "method_name",
        "methodName",
        "name",
        "id",
    ):
        value = find_value_recursive(
            data,
            {key},
        )

        if value is None:
            continue

        if isinstance(value, str):
            match = STRATEGY_ID_PATTERN.search(
                value
            )

            if match:
                return match.group(0).upper()

    filename_match = STRATEGY_ID_PATTERN.search(
        path.name
    )

    if filename_match:
        return filename_match.group(0).upper()

    return ""


def extract_strategy_name(
    data: dict[str, Any],
) -> str:
    value = find_value_recursive(
        data,
        {
            "strategy_name",
            "strategyName",
            "method_name",
            "methodName",
        },
    )

    if value:
        return normalize(value)

    strategy = find_value_recursive(
        data,
        {"strategy"},
    )

    if isinstance(strategy, str):
        return normalize(strategy)

    if isinstance(strategy, dict):
        value = find_value_recursive(
            strategy,
            {
                "name",
                "strategy_name",
                "strategyName",
            },
        )

        if value:
            return normalize(value)

    return "Unknown Strategy"


def extract_symbol(
    data: dict[str, Any],
) -> str:
    value = find_value_recursive(
        data,
        {
            "symbol",
            "ticker",
        },
    )

    if value:
        return normalize(value)

    return ""


def extract_metrics(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Paper Trading V1.3 sonuçlarında metrikler top-level değil,
    result["metrics"] altında tutuluyor.

    Ayrıca farklı eski sürümler için alias desteği bulunuyor.
    """
    metrics = find_value_recursive(
        data,
        {"metrics"},
    )

    if not isinstance(metrics, dict):
        metrics = {}

    return metrics


def metric_value(
    metrics: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]

    return default


# ============================================================================
# PAPER RESULT NORMALIZATION
# ============================================================================

def normalize_paper_result(
    path: Path,
    data: dict[str, Any],
) -> dict[str, Any]:
    strategy_id = extract_strategy_id(
        path,
        data,
    )

    strategy_name = extract_strategy_name(
        data,
    )

    symbol = extract_symbol(
        data,
    )

    metrics = extract_metrics(
        data,
    )

    market = data.get(
        "market",
        {},
    )

    if not isinstance(market, dict):
        market = {}

    period = normalize(
        market.get("period")
        or data.get("period"),
        "1y",
    )

    interval = normalize(
        market.get("interval")
        or data.get("interval"),
        "1d",
    )

    start_date = normalize(
        market.get("start")
        or data.get("start")
        or data.get("start_date")
        or data.get("history_start")
    )

    end_date = normalize(
        market.get("end")
        or data.get("end")
        or data.get("end_date")
        or data.get("history_end")
    )

    total_trades = safe_int(
        metric_value(
            metrics,
            "trades",
            "total_trades",
            default=data.get("total_trades", 0),
        )
    )

    wins = safe_int(
        metric_value(
            metrics,
            "wins",
            "winning_trades",
            default=data.get("wins", 0),
        )
    )

    losses = safe_int(
        metric_value(
            metrics,
            "losses",
            "losing_trades",
            default=data.get("losses", 0),
        )
    )

    win_rate = safe_float(
        metric_value(
            metrics,
            "win_rate_percent",
            "win_rate",
            default=data.get("win_rate_percent", 0),
        )
    )

    profit_factor = safe_float(
        metric_value(
            metrics,
            "profit_factor",
            "pf",
            default=data.get("profit_factor", 0),
        )
    )

    net_pnl = safe_float(
        metric_value(
            metrics,
            "net_pnl",
            "aggregate_net_pnl",
            default=data.get("net_pnl", 0),
        )
    )

    return_percent = safe_float(
        metric_value(
            metrics,
            "return_percent",
            "total_return_percent",
            "aggregate_return_percent",
            default=data.get("return_percent", 0),
        )
    )

    max_drawdown = safe_float(
        metric_value(
            metrics,
            "max_drawdown_percent",
            "max_drawdown",
            default=data.get("max_drawdown_percent", 0),
        )
    )

    average_trade = safe_float(
        metric_value(
            metrics,
            "average_trade_pnl",
            "average_trade",
            default=data.get("average_trade", 0),
        )
    )

    initial_capital = safe_float(
        metric_value(
            metrics,
            "initial_capital",
            default=data.get("initial_capital", 0),
        )
    )

    final_equity = safe_float(
        metric_value(
            metrics,
            "final_equity",
            default=data.get("final_equity", 0),
        )
    )

    signal_counts = (
        data.get("signal_counts")
        or data.get("signals")
        or {}
    )

    if not isinstance(signal_counts, dict):
        signal_counts = {}

    parameters = (
        data.get("parameters")
        or data.get("strategy_parameters")
        or {}
    )

    if not isinstance(parameters, dict):
        parameters = {}

    return {
        "source_file": str(path),
        "source_filename": path.name,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_percent": win_rate,
        "profit_factor": profit_factor,
        "net_pnl": net_pnl,
        "return_percent": return_percent,
        "max_drawdown_percent": max_drawdown,
        "average_trade": average_trade,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "signals": signal_counts,
        "parameters": parameters,
        "research_only": bool(
            data.get(
                "research_only",
                True,
            )
        ),
        "execution_enabled": bool(
            data.get(
                "execution_enabled",
                False,
            )
        ),
        "raw": data,
    }


# ============================================================================
# CLASSIFICATION
# ============================================================================

def classify_feedback(
    result: dict[str, Any],
) -> dict[str, Any]:
    trades = result["total_trades"]
    win_rate = result["win_rate_percent"]
    pf = result["profit_factor"]
    return_percent = result["return_percent"]

    reasons: list[str] = []

    if trades < MIN_TRADES_FOR_REVIEW:
        classification = "INSUFFICIENT_SAMPLE"
        reasons.append(
            f"trade sayısı {trades} < {MIN_TRADES_FOR_REVIEW}"
        )

    elif (
        trades >= MIN_TRADES_FOR_SUPPORT
        and win_rate >= MIN_WIN_RATE_FOR_SUPPORT
        and pf >= MIN_PROFIT_FACTOR_FOR_SUPPORT
        and return_percent > MIN_RETURN_FOR_SUPPORT
    ):
        classification = "POSITIVE_PAPER_EVIDENCE"

        reasons.extend(
            [
                "yeterli trade örneklemi",
                "win rate destek eşiğinin üzerinde",
                "profit factor destek eşiğinin üzerinde",
                "paper return pozitif",
            ]
        )

    elif (
        trades >= MIN_TRADES_FOR_REVIEW
        and (
            pf < 1.0
            or return_percent < 0.0
        )
    ):
        classification = "WEAK_PAPER_EVIDENCE"

        if pf < 1.0:
            reasons.append(
                "profit factor 1.0 altında"
            )

        if return_percent < 0.0:
            reasons.append(
                "paper return negatif"
            )

    else:
        classification = "MIXED_PAPER_EVIDENCE"
        reasons.append(
            "sonuçlar doğrulama için yeterince güçlü değil"
        )

    # Örneklem küçükse olumlu görünen sonucu bile
    # doğrulanmış kabul etmiyoruz.
    if trades < MIN_TRADES_FOR_SUPPORT:
        if classification == "POSITIVE_PAPER_EVIDENCE":
            classification = "MIXED_PAPER_EVIDENCE"

        reasons.append(
            "örneklem uzun dönem doğrulama için yetersiz"
        )

    if result["execution_enabled"]:
        raise RuntimeError(
            "Safety gate: execution_enabled=True "
            "olan bir sonuç öğrenme motoruna alınamaz."
        )

    return {
        "classification": classification,
        "reasons": reasons,
    }


def feedback_score(
    result: dict[str, Any],
    classification: str,
) -> float:
    """
    0..1 arası araştırma skoru.

    Bu skor yatırım tavsiyesi değildir ve
    stratejinin doğrulandığı anlamına gelmez.
    """
    trades = result["total_trades"]
    win_rate = result["win_rate_percent"]
    pf = result["profit_factor"]
    return_percent = result["return_percent"]
    dd = result["max_drawdown_percent"]

    sample_score = min(
        trades / 50.0,
        1.0,
    )

    win_score = min(
        max(win_rate / 60.0, 0.0),
        1.0,
    )

    pf_score = min(
        max((pf - 0.5) / 1.0, 0.0),
        1.0,
    )

    return_score = min(
        max((return_percent + 5.0) / 15.0, 0.0),
        1.0,
    )

    dd_penalty = min(
        max(dd / 20.0, 0.0),
        0.5,
    )

    raw = (
        sample_score * 0.20
        + win_score * 0.20
        + pf_score * 0.30
        + return_score * 0.30
        - dd_penalty
    )

    score = max(
        0.0,
        min(
            raw,
            1.0,
        ),
    )

    if classification == "INSUFFICIENT_SAMPLE":
        score *= 0.65

    return round(
        score,
        4,
    )


def learning_decision(
    classification: str,
) -> str:
    """
    Paper sonucu için Brain learning event kararı.

    Burada hiçbir durumda doğrudan learned rule oluşturulmaz.
    """
    if classification == "POSITIVE_PAPER_EVIDENCE":
        return "HOLD_FOR_VALIDATION"

    if classification == "MIXED_PAPER_EVIDENCE":
        return "HOLD_FOR_RESEARCH"

    if classification == "WEAK_PAPER_EVIDENCE":
        return "REQUEST_RESEARCH"

    return "REQUEST_MORE_DATA"


# ============================================================================
# EXPERIMENT INSERT
# ============================================================================

def find_existing_experiment(
    conn: sqlite3.Connection,
    source_key: str,
) -> sqlite3.Row | None:
    rows = conn.execute(
        """
        SELECT
            id,
            method_name,
            symbol,
            timeframe,
            status,
            parameters_json
        FROM learning_experiments
        WHERE parameters_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            f'%\"source_key\":\"{source_key}\"%',
        ),
    ).fetchall()

    if rows:
        return rows[0]

    return None


def insert_experiment(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    source_key: str,
) -> tuple[int, bool]:
    existing = find_existing_experiment(
        conn,
        source_key,
    )

    if existing:
        return (
            safe_int(existing["id"]),
            False,
        )

    now = utc_now()

    method_name = (
        result["strategy_name"]
        or result["strategy_id"]
        or "Unknown Paper Strategy"
    )

    parameters = {
        "source_key": source_key,
        "strategy_id": result["strategy_id"],
        "strategy_name": result["strategy_name"],
        "period": result["period"],
        "interval": result["interval"],
        "paper_source_file": result["source_file"],
        "parameters": result["parameters"],
        "research_only": True,
        "execution_enabled": False,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
    }

    cursor = conn.execute(
        """
        INSERT INTO learning_experiments (
            knowledge_id,
            method_name,
            method_type,
            symbol,
            market,
            timeframe,
            signal_direction,
            start_date,
            end_date,
            status,
            parameters_json,
            created_at
        )
        VALUES (
            NULL,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            method_name,
            "PAPER_TRADING_FEEDBACK",
            result["symbol"],
            "BIST" if result["symbol"].endswith(".IS") else "US",
            result["interval"],
            "MULTI",
            result["start_date"],
            result["end_date"],
            "PAPER_REPLAY_REVIEW",
            compact_json(parameters),
            now,
        ),
    )

    return (
        safe_int(cursor.lastrowid),
        True,
    )


# ============================================================================
# EXPERIMENT RESULT INSERT
# ============================================================================

def find_existing_result(
    conn: sqlite3.Connection,
    experiment_id: int,
    source_key: str,
) -> sqlite3.Row | None:
    rows = conn.execute(
        """
        SELECT
            id
        FROM experiment_results
        WHERE experiment_id=?
          AND metadata_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            experiment_id,
            f'%\"source_key\":\"{source_key}\"%',
        ),
    ).fetchall()

    if rows:
        return rows[0]

    return None


def insert_experiment_result(
    conn: sqlite3.Connection,
    experiment_id: int,
    result: dict[str, Any],
    classification: str,
    score: float,
    source_key: str,
) -> tuple[int, bool]:
    existing = find_existing_result(
        conn,
        experiment_id,
        source_key,
    )

    if existing:
        return (
            safe_int(existing["id"]),
            False,
        )

    now = utc_now()

    metadata = {
        "source_key": source_key,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "paper_source_file": result["source_file"],
        "strategy_id": result["strategy_id"],
        "strategy_name": result["strategy_name"],
        "period": result["period"],
        "interval": result["interval"],
        "total_trades": result["total_trades"],
        "wins": result["wins"],
        "losses": result["losses"],
        "win_rate_percent": result["win_rate_percent"],
        "profit_factor": result["profit_factor"],
        "net_pnl": result["net_pnl"],
        "return_percent": result["return_percent"],
        "max_drawdown_percent": result["max_drawdown_percent"],
        "average_trade": result["average_trade"],
        "initial_capital": result["initial_capital"],
        "final_equity": result["final_equity"],
        "classification": classification,
        "feedback_score": score,
        "parameters": result["parameters"],
        "signals": result["signals"],
        "research_only": True,
        "execution_enabled": False,
    }

    # Bu tablo 1d/5d/20d forward-result yapısına sahip.
    # Paper replay burada "aggregate feedback evidence" olarak saklanıyor.
    # Forward return alanları yanlış anlam üretmemesi için NULL bırakılıyor.
    cursor = conn.execute(
        """
        INSERT INTO experiment_results (
            experiment_id,
            observation_date,
            entry_price,
            price_1d,
            price_5d,
            price_20d,
            return_1d,
            return_5d,
            return_20d,
            max_favorable_move,
            max_adverse_move,
            result_1d,
            result_5d,
            result_20d,
            market_regime,
            volume_state,
            volatility_state,
            metadata_json,
            created_at
        )
        VALUES (
            ?,
            ?,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            'PAPER_REPLAY',
            'PAPER_REPLAY',
            ?,
            'UNKNOWN',
            'UNKNOWN',
            'UNKNOWN',
            ?,
            ?
        )
        """,
        (
            experiment_id,
            result["end_date"] or now,
            classification,
            compact_json(metadata),
            now,
        ),
    )

    return (
        safe_int(cursor.lastrowid),
        True,
    )


# ============================================================================
# BRAIN LEARNING EVENT
# ============================================================================

def learning_event_exists(
    conn: sqlite3.Connection,
    source_key: str,
) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT
            id,
            decision,
            score
        FROM brain_learning_events
        WHERE metadata_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            f'%\"source_key\":\"{source_key}\"%',
        ),
    ).fetchone()

    return row


def insert_learning_event(
    conn: sqlite3.Connection,
    experiment_id: int,
    experiment_result_id: int,
    result: dict[str, Any],
    classification: str,
    score: float,
    decision: str,
    source_key: str,
) -> tuple[int | None, bool]:
    existing = learning_event_exists(
        conn,
        source_key,
    )

    if existing:
        return (
            safe_int(existing["id"]),
            False,
        )

    now = utc_now()

    metadata = {
        "source_key": source_key,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "strategy_id": result["strategy_id"],
        "strategy_name": result["strategy_name"],
        "symbol": result["symbol"],
        "paper_source_file": result["source_file"],
        "classification": classification,
        "decision": decision,
        "feedback_score": score,
        "total_trades": result["total_trades"],
        "win_rate_percent": result["win_rate_percent"],
        "profit_factor": result["profit_factor"],
        "return_percent": result["return_percent"],
        "max_drawdown_percent": result["max_drawdown_percent"],
        "research_only": True,
        "execution_enabled": False,
    }

    cursor = conn.execute(
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
            ?,
            ?,
            ?,
            NULL,
            NULL,
            NULL,
            NULL,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            "PAPER_TRADING_FEEDBACK",
            experiment_id,
            experiment_result_id,
            score,
            decision,
            now,
            compact_json(metadata),
        ),
    )

    return (
        safe_int(cursor.lastrowid),
        True,
    )


# ============================================================================
# RESEARCH QUEUE
# ============================================================================

def ensure_research_queue(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    classification: str,
    decision: str,
    score: float,
    source_key: str,
) -> tuple[int | None, bool]:
    if not table_exists(
        conn,
        "brain_research_queue",
    ):
        return (
            None,
            False,
        )

    if classification == "POSITIVE_PAPER_EVIDENCE":
        question = (
            f"{result['strategy_name']} için "
            f"{result['symbol']} üzerinde paper sonucu pozitif. "
            "Bağımsız validation ve walk-forward sonuçları "
            "aynı davranışı destekliyor mu?"
        )

        priority = 5.0

    elif classification == "WEAK_PAPER_EVIDENCE":
        question = (
            f"{result['strategy_name']} için "
            f"{result['symbol']} paper replay zayıf. "
            "Hangi parametreler, rejimler veya maliyet varsayımları "
            "performans düşüşünü açıklıyor?"
        )

        priority = QUEUE_PRIORITY_WEAK

    elif classification == "MIXED_PAPER_EVIDENCE":
        question = (
            f"{result['strategy_name']} için "
            f"{result['symbol']} paper replay karışık. "
            "Sonucun farklı dönemlerde ve maliyet seviyelerinde "
            "robust olup olmadığı araştırılmalı mı?"
        )

        priority = QUEUE_PRIORITY_MIXED

    else:
        question = (
            f"{result['strategy_name']} için "
            f"{result['symbol']} paper replay örneklemi yetersiz. "
            "Daha uzun paper/research örneklemi gerekli."
        )

        priority = 6.0

    existing = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE metadata_json LIKE ?
          AND status IN (
              'queued',
              'working',
              'pending',
              'open'
          )
        LIMIT 1
        """,
        (
            f'%\"source_key\":\"{source_key}\"%',
        ),
    ).fetchone()

    if existing:
        return (
            safe_int(existing["id"]),
            False,
        )

    now = utc_now()

    metadata = {
        "source_key": source_key,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "strategy_id": result["strategy_id"],
        "symbol": result["symbol"],
        "classification": classification,
        "decision": decision,
        "feedback_score": score,
        "paper_source_file": result["source_file"],
        "research_only": True,
    }

    cursor = conn.execute(
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
        VALUES (
            ?,
            ?,
            ?,
            NULL,
            NULL,
            'queued',
            ?,
            ?,
            ?
        )
        """,
        (
            question,
            (
                f"Paper feedback classification={classification}; "
                f"score={score:.4f}"
            ),
            priority,
            now,
            now,
            compact_json(metadata),
        ),
    )

    return (
        safe_int(cursor.lastrowid),
        True,
    )


# ============================================================================
# OUTPUT
# ============================================================================

def save_feedback_report(
    payload: dict[str, Any],
) -> Path:
    FEEDBACK_RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    strategy_id = normalize(
        payload.get("strategy_id"),
        "UNKNOWN",
    )

    path = (
        FEEDBACK_RESULTS_DIR
        / (
            f"paper_feedback_"
            f"{strategy_id}_"
            f"{timestamp()}.json"
        )
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    temporary.replace(path)

    return path


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    source_path: Path,
    result: dict[str, Any],
    classification: str,
    reasons: list[str],
    score: float,
    decision: str,
    experiment_id: int,
    experiment_result_id: int,
    learning_event_id: int | None,
    queue_id: int | None,
) -> None:
    print()
    print("=" * 82)
    print("🧠 MARKET HQ PAPER FEEDBACK & LEARNING ENGINE V1.2")
    print("=" * 82)
    print()
    print(f"Research Only       : {RESEARCH_ONLY}")
    print(f"Execution Enabled   : {EXECUTION_ENABLED}")
    print()
    print(f"Source              : {source_path}")
    print(f"Strategy ID         : {result['strategy_id']}")
    print(f"Strategy            : {result['strategy_name']}")
    print(f"Symbol              : {result['symbol']}")
    print(f"Period              : {result['period']}")
    print(f"Interval            : {result['interval']}")
    print()
    print("-" * 82)
    print("PAPER EVIDENCE")
    print("-" * 82)
    print(f"Trades              : {result['total_trades']}")
    print(f"Wins / Losses       : {result['wins']} / {result['losses']}")
    print(f"Win Rate            : {result['win_rate_percent']:.2f}%")
    print(f"Profit Factor       : {result['profit_factor']:.4f}")
    print(f"Net PnL             : {result['net_pnl']:.2f}")
    print(f"Return              : {result['return_percent']:.4f}%")
    print(f"Max Drawdown        : {result['max_drawdown_percent']:.4f}%")
    print()
    print("-" * 82)
    print("FEEDBACK DECISION")
    print("-" * 82)
    print(f"Classification      : {classification}")
    print(f"Feedback Score      : {score:.4f}")
    print(f"Brain Decision      : {decision}")
    print()
    print("Reasons:")
    for reason in reasons:
        print(f"  • {reason}")
    print()
    print("-" * 82)
    print("DATABASE LINKS")
    print("-" * 82)
    print(f"Learning Experiment : {experiment_id}")
    print(f"Experiment Result   : {experiment_result_id}")
    print(
        f"Brain Learning Event: "
        f"{learning_event_id if learning_event_id else 'EXISTING / NONE'}"
    )
    print(
        f"Research Queue      : "
        f"{queue_id if queue_id else 'NONE'}"
    )
    print()
    print("=" * 82)
    print("ÖNEMLİ")
    print("=" * 82)
    print("• Paper sonucu doğrulanmış strateji değildir.")
    print("• learned_rules tablosuna otomatik kural yazılmadı.")
    print("• Gerçek emir / broker / execution yoktur.")
    print("• Sonraki doğrulama bağımsız validation + WFO ile yapılmalıdır.")
    print("=" * 82)
    print()


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run(
    explicit_file: str | None = None,
    strategy_id: str | None = None,
) -> Path:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False."
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True."
        )

    source_path, paper_data = select_paper_result(
        explicit_file=explicit_file,
        strategy_id=strategy_id,
    )

    result = normalize_paper_result(
        source_path,
        paper_data,
    )

    if not result["strategy_id"]:
        raise ValueError(
            "Paper sonucunda strategy_id bulunamadı. "
            f"Kaynak dosya: {source_path.name}. "
            "JSON ve dosya adı içinde STR-XXXX formatında "
            "bir strategy ID bulunamadı."
        )

    if not result["symbol"]:
        raise ValueError(
            "Paper sonucunda symbol bulunamadı."
        )

    classification_data = classify_feedback(
        result
    )

    classification = classification_data[
        "classification"
    ]

    reasons = classification_data[
        "reasons"
    ]

    score = feedback_score(
        result,
        classification,
    )

    decision = learning_decision(
        classification
    )

    source_key = stable_hash(
        "paper_feedback",
        result["strategy_id"],
        result["symbol"],
        result["period"],
        result["interval"],
        source_path.name,
    )

    conn = open_db()

    try:
        ensure_schema_compatibility(
            conn
        )

        experiment_id, experiment_created = (
            insert_experiment(
                conn,
                result,
                source_key,
            )
        )

        experiment_result_id, result_created = (
            insert_experiment_result(
                conn,
                experiment_id,
                result,
                classification,
                score,
                source_key,
            )
        )

        learning_event_id, event_created = (
            insert_learning_event(
                conn,
                experiment_id,
                experiment_result_id,
                result,
                classification,
                score,
                decision,
                source_key,
            )
        )

        queue_id, queue_created = (
            ensure_research_queue(
                conn,
                result,
                classification,
                decision,
                score,
                source_key,
            )
        )

        conn.commit()

        report = {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "created_at": utc_now(),
            "research_only": True,
            "execution_enabled": False,
            "source_file": str(source_path),
            "source_key": source_key,
            "strategy_id": result["strategy_id"],
            "strategy_name": result["strategy_name"],
            "symbol": result["symbol"],
            "classification": classification,
            "reasons": reasons,
            "feedback_score": score,
            "decision": decision,
            "experiment_id": experiment_id,
            "experiment_created": experiment_created,
            "experiment_result_id": experiment_result_id,
            "experiment_result_created": result_created,
            "learning_event_id": learning_event_id,
            "learning_event_created": event_created,
            "research_queue_id": queue_id,
            "research_queue_created": queue_created,
            "paper_metrics": {
                "total_trades": result["total_trades"],
                "wins": result["wins"],
                "losses": result["losses"],
                "win_rate_percent": result["win_rate_percent"],
                "profit_factor": result["profit_factor"],
                "net_pnl": result["net_pnl"],
                "return_percent": result["return_percent"],
                "max_drawdown_percent": result["max_drawdown_percent"],
            },
            "parameter_snapshot": result["parameters"],
        }

        output_path = save_feedback_report(
            report
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    print_report(
        source_path,
        result,
        classification,
        reasons,
        score,
        decision,
        experiment_id,
        experiment_result_id,
        learning_event_id,
        queue_id,
    )

    print(
        f"💾 Feedback report: {output_path}"
    )

    return output_path


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ Paper Feedback & Learning Engine V1.2"
        )
    )

    parser.add_argument(
        "--file",
        dest="file",
        default=None,
        help="Belirli paper trading JSON dosyası.",
    )

    parser.add_argument(
        "--strategy-id",
        dest="strategy_id",
        default=None,
        help="Belirli strategy_id için en son paper sonucu.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        run(
            explicit_file=args.file,
            strategy_id=args.strategy_id,
        )

    except KeyboardInterrupt:
        print()
        print("İşlem kullanıcı tarafından durduruldu.")

    except Exception as exc:
        print()
        print("=" * 82)
        print("❌ PAPER FEEDBACK ENGINE HATASI")
        print("=" * 82)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print("=" * 82)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

