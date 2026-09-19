# -*- coding: utf-8 -*-
"""
MarketHQ Fresh Independent Research Engine V1.1
=============================================

AMAÇ
-----
STR-43839FA9C6 için daha önceki bağımsız kanıttan ayrı,
V6 tarafından kullanılan aynı sembol-bazlı parametreleri
kullanarak daha eski ve ayrı bir tarihsel dilimde yeniden test yapmak.

Bu modül:
    - V6 pipeline JSON'undan seçilmiş parametreleri okur.
    - Parametreleri değiştirmez.
    - Aynı signal/backtest sözleşmesini kullanır.
    - V6'nın son 3 yıllık WFO penceresinin dışındaki,
      yaklaşık 3-4 yıl önceki 252 işlem gününü hedefler.
    - 16 sembolü mümkün olduğunca test eder.
    - Yetersiz veri varsa açıkça INSUFFICIENT olarak raporlar.
    - Aynı strateji kuralını optimize etmez.
    - Araştırma JSON'u ve ayrı audit tablosu üretir.

GÜVENLİK
--------
Research only.
EXECUTION_ENABLED = False.
Broker bağlantısı yoktur.
Gerçek emir yoktur.
learned_rules / claims / validations / observations değiştirilmez.

Çalıştırma
----------
.venv\\Scripts\\python.exe .\\fresh_independent_research_engine_v1.py
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"
PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
OUTPUT_DIR = PROJECT_ROOT / "fresh_independent_research_results"

ENGINE_NAME = "MARKETHQ_FRESH_INDEPENDENT_RESEARCH"
ENGINE_VERSION = "V1.1"

TARGET_STRATEGY_ID = "STR-43839FA9C6"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

# V6 universe from the verified run context.
UNIVERSE = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "SISE.IS",
    "BIMAS.IS",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
]

# Fresh slice:
# V6 main/WFO window used approximately the latest 3 years.
# The earlier independent runner also used recent 1y + rolling 3y.
# To avoid simply replaying those windows, target ~3-4 years ago.
HISTORY_PERIOD = "5y"
SLICE_START_BARS_AGO = 1008
SLICE_END_BARS_AGO = 756
SLICE_LENGTH = SLICE_START_BARS_AGO - SLICE_END_BARS_AGO

MIN_BARS = max(200, SLICE_LENGTH)

# Same backtest cost assumptions as the existing research engines.
INITIAL_CAPITAL = 100000
POSITION_SIZE_PERCENT = 10.0
COMMISSION_PERCENT = 0.10
SLIPPAGE_PERCENT = 0.05
ALLOW_SHORT = True
ONE_POSITION_AT_A_TIME = True
MAX_HOLDING_BARS = 60
EXIT_ON_OPPOSITE_SIGNAL = True

# Existing research candidate contract.
PARAMETER_KEYS = (
    "sma_fast",
    "sma_slow",
    "ema_fast",
    "ema_slow",
    "rsi_period",
    "rsi_oversold",
    "rsi_overbought",
    "stop_atr_multiplier",
    "target_atr_multiplier",
)

SYMBOL_RE = re.compile(
    r"^[A-Z0-9][A-Z0-9._-]{0,19}$",
    re.IGNORECASE,
)


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def timestamp() -> str:
    return datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def clamp01(value: float) -> float:
    return max(
        0.0,
        min(1.0, value),
    )


# ============================================================================
# SAFETY
# ============================================================================

def assert_research_only() -> None:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False."
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True."
        )


# ============================================================================
# JSON / PIPELINE
# ============================================================================

def latest_v6_file() -> Path:
    if not PIPELINE_DIR.exists():
        raise FileNotFoundError(
            f"Pipeline klasörü bulunamadı: {PIPELINE_DIR}"
        )

    candidates = sorted(
        PIPELINE_DIR.glob(
            "strategy_pipeline_v6_*.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            "strategy_pipeline_v6_*.json bulunamadı."
        )

    return candidates[0]


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            f"JSON okunamadı: {path}\n{exc}"
        ) from exc


def is_strategy_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(
            value.get("strategy_id")
            or value.get("id")
        )
    )


def find_strategy_record(
    payload: Any,
    strategy_id: str,
) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            identity = id(value)
            if identity in seen:
                return

            seen.add(identity)

            if is_strategy_record(value):
                row_id = norm(
                    value.get("strategy_id")
                    or value.get("id")
                )

                if row_id.upper() == strategy_id.upper():
                    found.append(value)

            for child in value.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

        elif isinstance(value, list):
            for child in value:
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

    walk(payload)

    if not found:
        raise RuntimeError(
            f"V6 JSON içinde strategy bulunamadı: "
            f"{strategy_id}"
        )

    return found[0]


# ============================================================================
# V6 PARAMETER EXTRACTION
# ============================================================================

def has_complete_params(
    value: Any,
) -> bool:
    if not isinstance(value, dict):
        return False

    return all(
        key in value
        for key in PARAMETER_KEYS
    )


def coerce_params(
    value: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    int_keys = {
        "sma_fast",
        "sma_slow",
        "ema_fast",
        "ema_slow",
        "rsi_period",
        "rsi_oversold",
        "rsi_overbought",
    }

    for key in PARAMETER_KEYS:
        raw = value[key]

        if key in int_keys:
            params[key] = safe_int(raw)
        else:
            params[key] = safe_float(raw)

    return params


def first_params_in_dict(
    value: Any,
) -> dict[str, Any] | None:
    if has_complete_params(value):
        return coerce_params(value)

    if not isinstance(value, dict):
        return None

    preferred_keys = (
        "params",
        "parameters",
        "best_params",
        "best_parameters",
    )

    for key in preferred_keys:
        child = value.get(key)

        if has_complete_params(child):
            return coerce_params(child)

    return None


def collect_param_dicts(
    value: Any,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            identity = id(obj)
            if identity in seen:
                return

            seen.add(identity)

            candidate = first_params_in_dict(obj)
            if candidate is not None:
                results.append(candidate)

            for child in obj.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

        elif isinstance(obj, list):
            for child in obj:
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

    walk(value)
    return results


def normalize_symbol(
    symbol: Any,
) -> str:
    value = norm(symbol).upper()

    if not value:
        return ""

    if not SYMBOL_RE.match(value):
        return ""

    return value


def find_symbol_blocks(
    strategy_record: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    V6 JSON şeması sürümler arasında değişmiş olabilir.
    Bu nedenle symbol içeren dict blokları recursive topluyoruz.
    """

    blocks: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            identity = id(obj)
            if identity in seen:
                return

            seen.add(identity)

            possible_symbol = (
                obj.get("symbol")
                or obj.get("ticker")
                or obj.get("asset")
            )

            symbol = normalize_symbol(
                possible_symbol
            )

            if symbol:
                blocks.append(obj)

            for child in obj.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

        elif isinstance(obj, list):
            for child in obj:
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

    walk(strategy_record)

    unique: dict[str, dict[str, Any]] = {}

    for block in blocks:
        symbol = normalize_symbol(
            block.get("symbol")
            or block.get("ticker")
            or block.get("asset")
        )

        if symbol and symbol not in unique:
            unique[symbol] = block

    return [
        unique[symbol]
        for symbol in sorted(unique)
    ]


def extract_symbol_parameters(
    strategy_record: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    blocks = find_symbol_blocks(
        strategy_record
    )

    preferred_result_keys = (
        "best_backtest",
        "best_result",
        "best",
        "full_backtest",
        "backtest",
        "result",
        "metrics",
    )

    for block in blocks:
        symbol = normalize_symbol(
            block.get("symbol")
            or block.get("ticker")
            or block.get("asset")
        )

        if not symbol:
            continue

        params: dict[str, Any] | None = None

        for key in preferred_result_keys:
            child = block.get(key)

            if isinstance(child, dict):
                params = first_params_in_dict(
                    child
                )

                if params is not None:
                    break

        if params is None:
            params = first_params_in_dict(
                block
            )

        if params is None:
            all_params = collect_param_dicts(
                block
            )

            if all_params:
                params = all_params[0]

        if params is not None:
            result[symbol] = params

    return result


def fallback_global_params(
    strategy_record: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Yalnızca symbol-specific params yoksa kullanılır.
    İlk canonical parameter dict'i alır.
    """

    params = first_params_in_dict(
        strategy_record
    )

    if params is not None:
        return params

    all_params = collect_param_dicts(
        strategy_record
    )

    return (
        all_params[0]
        if all_params
        else None
    )


# ============================================================================
# MARKET DATA
# ============================================================================

def normalize_downloaded_data(
    data: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()

    frame = data.copy()

    if isinstance(
        frame.columns,
        pd.MultiIndex,
    ):
        # yfinance commonly returns:
        # Price x Ticker
        if symbol in frame.columns.get_level_values(
            -1
        ):
            frame = frame.xs(
                symbol,
                axis=1,
                level=-1,
                drop_level=True,
            )
        else:
            frame.columns = [
                str(col[0])
                for col in frame.columns
            ]

    rename_map: dict[Any, str] = {}

    for column in frame.columns:
        clean = str(column).strip()

        if clean.lower() == "open":
            rename_map[column] = "Open"
        elif clean.lower() == "high":
            rename_map[column] = "High"
        elif clean.lower() == "low":
            rename_map[column] = "Low"
        elif clean.lower() == "close":
            rename_map[column] = "Close"
        elif clean.lower() == "adj close":
            rename_map[column] = "Adj Close"
        elif clean.lower() == "volume":
            rename_map[column] = "Volume"

    frame = frame.rename(
        columns=rename_map
    )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    missing = [
        column
        for column in required
        if column not in frame.columns
    ]

    if missing:
        return pd.DataFrame()

    for column in required:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    if "Volume" in frame.columns:
        frame["Volume"] = pd.to_numeric(
            frame["Volume"],
            errors="coerce",
        )

    frame = frame.dropna(
        subset=required
    )

    frame = frame.sort_index()

    if getattr(
        frame.index,
        "tz",
        None,
    ) is not None:
        frame.index = frame.index.tz_localize(
            None
        )

    return frame


def load_history(
    symbol: str,
) -> pd.DataFrame:
    try:
        data = yf.download(
            symbol,
            period=HISTORY_PERIOD,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        print(
            f"   ⚠️ {symbol}: yfinance hata: "
            f"{type(exc).__name__}: {exc}"
        )
        return pd.DataFrame()

    return normalize_downloaded_data(
        data,
        symbol,
    )


def select_fresh_slice(
    data: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    str,
    str,
    str,
]:
    """
    Data index'i geçmişten bugüne sıralıdır.

    Örnek:
        0 ... N-1008 ... N-756 ... N

    Seçilen bölüm:
        [N-1008, N-756)

    Bu yaklaşık 252 barlık, daha eski bir tarihsel dilimdir.
    """

    if len(data) < MIN_BARS:
        return (
            pd.DataFrame(),
            "",
            "",
            "INSUFFICIENT_BARS",
        )

    start_index = len(data) - SLICE_START_BARS_AGO
    end_index = len(data) - SLICE_END_BARS_AGO

    if start_index < 0:
        return (
            pd.DataFrame(),
            "",
            "",
            "INSUFFICIENT_BARS",
        )

    if end_index <= start_index:
        return (
            pd.DataFrame(),
            "",
            "",
            "INVALID_SLICE",
        )

    selected = data.iloc[
        start_index:end_index
    ].copy()

    if len(selected) < SLICE_LENGTH * 0.90:
        return (
            selected,
            (
                str(selected.index.min())
                if not selected.empty
                else ""
            ),
            (
                str(selected.index.max())
                if not selected.empty
                else ""
            ),
            "INSUFFICIENT_SLICE",
        )

    return (
        selected,
        str(selected.index.min()),
        str(selected.index.max()),
        "OK",
    )


# ============================================================================
# BACKTEST
# ============================================================================

def build_signal_config(
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sma_fast": params["sma_fast"],
        "sma_slow": params["sma_slow"],
        "ema_fast": params["ema_fast"],
        "ema_slow": params["ema_slow"],
        "rsi_period": params["rsi_period"],
        "rsi_oversold": params["rsi_oversold"],
        "rsi_overbought": params["rsi_overbought"],
        "buy_threshold": 3,
        "sell_threshold": -3,
    }


def build_backtest_config(
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "initial_capital": INITIAL_CAPITAL,
        "position_size_percent": POSITION_SIZE_PERCENT,
        "commission_percent": COMMISSION_PERCENT,
        "slippage_percent": SLIPPAGE_PERCENT,
        "use_stop_loss": True,
        "use_take_profit": True,
        "allow_short": ALLOW_SHORT,
        "one_position_at_a_time": (
            ONE_POSITION_AT_A_TIME
        ),
        "stop_atr_multiplier": params[
            "stop_atr_multiplier"
        ],
        "target_atr_multiplier": params[
            "target_atr_multiplier"
        ],
        "max_holding_bars": (
            MAX_HOLDING_BARS
        ),
        "exit_on_opposite_signal": (
            EXIT_ON_OPPOSITE_SIGNAL
        ),
    }


def run_single_backtest(
    data: pd.DataFrame,
    symbol: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        from backtest_engine import run_backtest
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": (
                "backtest_engine import failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        }

    signal_config = build_signal_config(
        params
    )
    backtest_config = build_backtest_config(
        params
    )

    try:
        result = run_backtest(
            data=data,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }

    if not isinstance(result, dict):
        return {
            "status": "ERROR",
            "error": "Backtest sonucu dict değil.",
        }

    return {
        "status": "DONE",
        "raw": result,
    }


# ============================================================================
# METRICS
# ============================================================================

def extract_metrics(
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    metrics = raw_result.get(
        "metrics"
    )

    if not isinstance(
        metrics,
        dict,
    ):
        metrics = {}

    trade_list = raw_result.get(
        "trades"
    )

    if isinstance(
        trade_list,
        list,
    ):
        trade_count = len(
            trade_list
        )
    else:
        trade_count = safe_int(
            metrics.get(
                "trades",
                raw_result.get(
                    "trade_count",
                    0,
                ),
            )
        )

    wins = safe_int(
        metrics.get(
            "wins",
            raw_result.get(
                "wins",
                0,
            ),
        )
    )

    losses = safe_int(
        metrics.get(
            "losses",
            raw_result.get(
                "losses",
                0,
            ),
        )
    )

    win_rate = safe_float(
        metrics.get(
            "win_rate_percent",
            raw_result.get(
                "win_rate_percent",
                0.0,
            ),
        )
    )

    profit_factor = safe_float(
        metrics.get(
            "profit_factor",
            0.0,
        )
    )

    # Backtest Engine canonical field is total_return_percent.
    # We deliberately prefer this exact field rather than the generic
    # aliases "return" / "return_percent", which may not exist.
    total_return = safe_float(
        metrics.get(
            "total_return_percent",
            raw_result.get(
                "total_return_percent",
                0.0,
            ),
        )
    )

    max_drawdown = safe_float(
        metrics.get(
            "max_drawdown_percent",
            raw_result.get(
                "max_drawdown_percent",
                0.0,
            ),
        )
    )

    final_equity = safe_float(
        metrics.get(
            "final_equity",
            INITIAL_CAPITAL,
        ),
        INITIAL_CAPITAL,
    )

    net_pnl = safe_float(
        metrics.get(
            "net_pnl",
            raw_result.get(
                "net_pnl",
                0.0,
            ),
        )
    )

    return {
        "trades": trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate_percent": win_rate,
        "profit_factor": profit_factor,
        "return_percent": total_return,
        "total_return_percent": total_return,
        "net_pnl": net_pnl,
        "max_drawdown_percent": max_drawdown,
        "final_equity": final_equity,
    }


def classify_result(
    metrics: dict[str, Any],
) -> str:
    trades = safe_int(
        metrics.get("trades")
    )
    total_return = safe_float(
        metrics.get("return_percent")
    )
    pf = safe_float(
        metrics.get("profit_factor")
    )

    if trades < 3:
        return "INCONCLUSIVE"

    if (
        total_return > 0.0
        and pf >= 1.0
    ):
        return "POSITIVE"

    if (
        total_return == 0.0
        and safe_float(metrics.get("net_pnl")) > 0.0
        and pf >= 1.0
    ):
        return "POSITIVE"

    return "NEGATIVE"


# ============================================================================
# DATABASE AUDIT
# ============================================================================

def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.execute(
        "PRAGMA busy_timeout = 60000"
    )
    return conn


def ensure_audit_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS
        brain_fresh_independent_research_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            source_pipeline_file TEXT,
            slice_start_bars_ago INTEGER NOT NULL,
            slice_end_bars_ago INTEGER NOT NULL,
            symbols_tested INTEGER NOT NULL,
            positive_runs INTEGER NOT NULL,
            negative_runs INTEGER NOT NULL,
            inconclusive_runs INTEGER NOT NULL,
            insufficient_runs INTEGER NOT NULL,
            aggregate_return_percent REAL NOT NULL,
            average_profit_factor REAL NOT NULL,
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_fresh_research_strategy
        ON brain_fresh_independent_research_runs(
            strategy_id
        )
        """
    )


def save_audit(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO brain_fresh_independent_research_runs (
            strategy_id,
            engine_version,
            source_pipeline_file,
            slice_start_bars_ago,
            slice_end_bars_ago,
            symbols_tested,
            positive_runs,
            negative_runs,
            inconclusive_runs,
            insufficient_runs,
            aggregate_return_percent,
            average_profit_factor,
            created_at,
            result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            TARGET_STRATEGY_ID,
            ENGINE_VERSION,
            payload.get(
                "source_pipeline_file"
            ),
            SLICE_START_BARS_AGO,
            SLICE_END_BARS_AGO,
            safe_int(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "symbols_tested",
                    0,
                )
            ),
            safe_int(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "positive_runs",
                    0,
                )
            ),
            safe_int(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "negative_runs",
                    0,
                )
            ),
            safe_int(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "inconclusive_runs",
                    0,
                )
            ),
            safe_int(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "insufficient_runs",
                    0,
                )
            ),
            safe_float(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "aggregate_return_percent",
                    0.0,
                )
            ),
            safe_float(
                payload.get(
                    "summary",
                    {},
                ).get(
                    "average_profit_factor",
                    0.0,
                )
            ),
            utc_now(),
            compact_json(payload),
        ),
    )

    return safe_int(
        cursor.lastrowid
    )


# ============================================================================
# RUN
# ============================================================================

def run() -> int:
    assert_research_only()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pipeline_path = latest_v6_file()
    pipeline_payload = load_json(
        pipeline_path
    )

    strategy_record = find_strategy_record(
        pipeline_payload,
        TARGET_STRATEGY_ID,
    )

    symbol_params = extract_symbol_parameters(
        strategy_record
    )

    global_fallback = fallback_global_params(
        strategy_record
    )

    print()
    print("=" * 78)
    print(
        "MARKETHQ FRESH INDEPENDENT "
        "RESEARCH ENGINE V1"
    )
    print("=" * 78)
    print()
    print(
        f"Strategy          : {TARGET_STRATEGY_ID}"
    )
    print(
        f"Pipeline file     : {pipeline_path}"
    )
    print(
        f"History period    : {HISTORY_PERIOD}"
    )
    print(
        f"Fresh slice       : "
        f"{SLICE_START_BARS_AGO}-{SLICE_END_BARS_AGO} "
        f"bars ago"
    )
    print(
        f"Slice length      : ~{SLICE_LENGTH} bars"
    )
    print(
        f"Cost model        : "
        f"commission={COMMISSION_PERCENT:.2f}% | "
        f"slippage={SLIPPAGE_PERCENT:.2f}%"
    )
    print(
        f"Research only     : {RESEARCH_ONLY}"
    )
    print(
        f"Execution enabled : {EXECUTION_ENABLED}"
    )

    results: list[dict[str, Any]] = []

    positive = 0
    negative = 0
    inconclusive = 0
    insufficient = 0

    returns: list[float] = []
    pfs: list[float] = []

    for position, symbol in enumerate(
        UNIVERSE,
        start=1,
    ):
        print()
        print(
            f"[{position:02d}/{len(UNIVERSE):02d}] "
            f"{symbol}"
        )

        params = symbol_params.get(
            symbol
        )

        param_source = "symbol_v6_params"

        if params is None:
            params = global_fallback
            param_source = (
                "global_v6_fallback"
            )

        if params is None:
            print(
                "   ❌ Parameters not found"
            )

            insufficient += 1

            results.append(
                {
                    "symbol": symbol,
                    "status": "INSUFFICIENT",
                    "reason": (
                        "V6 selected parameters "
                        "could not be extracted."
                    ),
                }
            )
            continue

        print(
            f"   Params: {params}"
        )

        data = load_history(
            symbol
        )

        if data.empty:
            print(
                "   ❌ Historical data unavailable"
            )

            insufficient += 1

            results.append(
                {
                    "symbol": symbol,
                    "status": "INSUFFICIENT",
                    "reason": (
                        "Historical data unavailable."
                    ),
                    "parameter_source": (
                        param_source
                    ),
                    "params": params,
                }
            )
            continue

        fresh_data, slice_start, slice_end, slice_status = (
            select_fresh_slice(
                data
            )
        )

        if slice_status != "OK":
            print(
                f"   ⚠️ Slice status: "
                f"{slice_status} | "
                f"bars={len(fresh_data)}"
            )

            insufficient += 1

            results.append(
                {
                    "symbol": symbol,
                    "status": "INSUFFICIENT",
                    "reason": slice_status,
                    "available_bars": len(
                        data
                    ),
                    "fresh_bars": len(
                        fresh_data
                    ),
                    "slice_start": slice_start,
                    "slice_end": slice_end,
                    "parameter_source": (
                        param_source
                    ),
                    "params": params,
                }
            )
            continue

        print(
            f"   Slice: {slice_start} -> "
            f"{slice_end} | bars={len(fresh_data)}"
        )

        backtest = run_single_backtest(
            fresh_data,
            symbol,
            params,
        )

        if backtest.get("status") != "DONE":
            print(
                "   ❌ Backtest error: "
                f"{backtest.get('error')}"
            )

            insufficient += 1

            results.append(
                {
                    "symbol": symbol,
                    "status": "ERROR",
                    "reason": backtest.get(
                        "error"
                    ),
                    "slice_start": slice_start,
                    "slice_end": slice_end,
                    "bars": len(
                        fresh_data
                    ),
                    "parameter_source": (
                        param_source
                    ),
                    "params": params,
                }
            )
            continue

        metrics = extract_metrics(
            backtest["raw"]
        )

        classification = classify_result(
            metrics
        )

        if classification == "POSITIVE":
            positive += 1
            returns.append(
                safe_float(
                    metrics["return_percent"]
                )
            )
            pfs.append(
                safe_float(
                    metrics["profit_factor"]
                )
            )
        elif classification == "NEGATIVE":
            negative += 1
            returns.append(
                safe_float(
                    metrics["return_percent"]
                )
            )
            pfs.append(
                safe_float(
                    metrics["profit_factor"]
                )
            )
        else:
            inconclusive += 1

        print(
            f"   Result={classification} | "
            f"trades={metrics['trades']} | "
            f"return={metrics['total_return_percent']:.2f}% | "
            f"net_pnl={metrics['net_pnl']:.2f} | "
            f"PF={metrics['profit_factor']:.3f}"
        )

        results.append(
            {
                "symbol": symbol,
                "status": classification,
                "slice_start": slice_start,
                "slice_end": slice_end,
                "bars": len(
                    fresh_data
                ),
                "parameter_source": (
                    param_source
                ),
                "params": params,
                "metrics": metrics,
            }
        )

    tested = positive + negative + inconclusive

    aggregate_return = (
        sum(returns) / len(returns)
        if returns
        else 0.0
    )

    average_pf = (
        sum(pfs) / len(pfs)
        if pfs
        else 0.0
    )

    positive_ratio = (
        positive / tested
        if tested > 0
        else 0.0
    )

    summary = {
        "symbols_requested": len(
            UNIVERSE
        ),
        "symbols_tested": tested,
        "positive_runs": positive,
        "negative_runs": negative,
        "inconclusive_runs": inconclusive,
        "insufficient_runs": insufficient,
        "positive_ratio": round(
            positive_ratio,
            4,
        ),
        "aggregate_return_percent": round(
            aggregate_return,
            4,
        ),
        "average_profit_factor": round(
            average_pf,
            4,
        ),
    }

    payload = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "research_only": True,
        "execution_enabled": False,
        "strategy_id": TARGET_STRATEGY_ID,
        "source_pipeline_file": str(
            pipeline_path
        ),
        "research_design": {
            "type": (
                "fresh_historical_slice"
            ),
            "history_period": (
                HISTORY_PERIOD
            ),
            "slice_start_bars_ago": (
                SLICE_START_BARS_AGO
            ),
            "slice_end_bars_ago": (
                SLICE_END_BARS_AGO
            ),
            "slice_length_target": (
                SLICE_LENGTH
            ),
            "min_bars": MIN_BARS,
            "no_parameter_optimization": True,
            "same_rule_definition": True,
        },
        "cost_model": {
            "initial_capital": (
                INITIAL_CAPITAL
            ),
            "position_size_percent": (
                POSITION_SIZE_PERCENT
            ),
            "commission_percent": (
                COMMISSION_PERCENT
            ),
            "slippage_percent": (
                SLIPPAGE_PERCENT
            ),
            "allow_short": ALLOW_SHORT,
            "one_position_at_a_time": (
                ONE_POSITION_AT_A_TIME
            ),
            "max_holding_bars": (
                MAX_HOLDING_BARS
            ),
            "exit_on_opposite_signal": (
                EXIT_ON_OPPOSITE_SIGNAL
            ),
        },
        "summary": summary,
        "results": results,
    }

    output_path = OUTPUT_DIR / (
        f"fresh_independent_"
        f"{TARGET_STRATEGY_ID}_"
        f"{timestamp()}.json"
    )

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    conn = open_db()

    try:
        ensure_audit_table(
            conn
        )

        audit_id = save_audit(
            conn,
            payload,
        )

        conn.commit()

    finally:
        conn.close()

    print()
    print("=" * 78)
    print("FRESH INDEPENDENT RESEARCH SUMMARY")
    print("=" * 78)
    print(
        f"Requested symbols   : "
        f"{summary['symbols_requested']}"
    )
    print(
        f"Tested symbols      : "
        f"{summary['symbols_tested']}"
    )
    print(
        f"Positive            : "
        f"{summary['positive_runs']}"
    )
    print(
        f"Negative            : "
        f"{summary['negative_runs']}"
    )
    print(
        f"Inconclusive        : "
        f"{summary['inconclusive_runs']}"
    )
    print(
        f"Insufficient/Error   : "
        f"{summary['insufficient_runs']}"
    )
    print(
        f"Positive ratio      : "
        f"{summary['positive_ratio']:.2%}"
    )
    print(
        f"Average return      : "
        f"{summary['aggregate_return_percent']:.2f}%"
    )
    print(
        f"Average PF          : "
        f"{summary['average_profit_factor']:.3f}"
    )
    print(
        f"Audit record        : {audit_id}"
    )
    print()
    print(
        "LEARNING SAFETY"
    )
    print("-" * 78)
    print(
        "learned_rules       : unchanged"
    )
    print(
        "claims              : unchanged"
    )
    print(
        "validations         : unchanged"
    )
    print(
        "observations        : unchanged"
    )
    print(
        "Knowledge Verified  : unchanged"
    )
    print()
    print(
        f"Saved result        : {output_path}"
    )
    print(
        "RUN STATUS          : SUCCESS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        run()
    )

