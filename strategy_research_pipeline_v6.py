# -*- coding: utf-8 -*-

"""
MarketHQ - Strategy Research Pipeline V6
=========================================

RESEARCH FLOW

Sources
    ↓
Discovery
    ↓
Knowledge Base
    ↓
Candidate Generation
    ↓
Fast Backtest Screen
    ↓
Walk-Forward Optimization
    ↓
Out-of-Sample Validation
    ↓
Robustness Tests
    ├── Cost Stress
    ├── Parameter Stability
    ├── Regime Stability
    └── Performance Consistency
    ↓
Ranking
    ↓
Research Report

SAFETY
------
Research only.
No broker.
No order execution.
No real-money trading.

V6 GOAL
-------
Amaç tek bir stratejiyi elle optimize etmek değildir.

Amaç:
- kaynaklardan strateji keşfetmek
- çoklu parametre adayları üretmek
- farklı sembollerde test etmek
- walk-forward yapmak
- maliyet stres testi yapmak
- parametre stabilitesini ölçmek
- farklı piyasa dönemlerinde dayanıklılığı ölçmek
- overfit riskini azaltmak
- stratejileri objektif olarak sıralamaktır.
"""

from __future__ import annotations

import json
import math
import statistics
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

RESULT_DIR = (
    PROJECT_ROOT
    / "strategy_pipeline_results"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================================
# IMPORTS
# ============================================================================

try:
    from research_ingestion_engine import (
        discover_source_files,
        process_source,
    )
except Exception as exc:
    discover_source_files = None
    process_source = None
    INGESTION_IMPORT_ERROR = exc
else:
    INGESTION_IMPORT_ERROR = None


try:
    from strategy_knowledge_base import (
        get_strategy,
        search_strategies,
    )
except Exception as exc:
    get_strategy = None
    search_strategies = None
    KB_IMPORT_ERROR = exc
else:
    KB_IMPORT_ERROR = None


try:
    from backtest_engine import run_backtest
except Exception as exc:
    run_backtest = None
    BACKTEST_IMPORT_ERROR = exc
else:
    BACKTEST_IMPORT_ERROR = None


try:
    from strategy_validation_engine import (
        validate_strategy,
    )
except Exception as exc:
    validate_strategy = None
    VALIDATION_IMPORT_ERROR = exc
else:
    VALIDATION_IMPORT_ERROR = None


try:
    from agents.market_data_agent import (
        get_history,
    )
except Exception:
    get_history = None


# ============================================================================
# GLOBAL CONFIG
# ============================================================================

PIPELINE_VERSION = "V6.0"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

BACKTEST_PERIOD = "1y"
WFO_PERIOD = "3y"

TRAIN_BARS = 252
VALIDATION_BARS = 63
STEP_BARS = 63

MIN_TRAIN_TRADES = 8
MIN_VALIDATION_TRADES = 3

TOP_WFO_CANDIDATES = 10

# Robustness
COST_STRESS_LEVELS = [
    {
        "name": "BASE",
        "commission_percent": 0.10,
        "slippage_percent": 0.05,
    },
    {
        "name": "MEDIUM_COST",
        "commission_percent": 0.20,
        "slippage_percent": 0.10,
    },
    {
        "name": "HIGH_COST",
        "commission_percent": 0.30,
        "slippage_percent": 0.20,
    },
]

# Parameter stability neighborhoods.
# V5 intentionally does not explode the search space.
PARAMETER_STABILITY_LIMIT = 12

# Ranking thresholds
PROMISING_MIN_SCORE = 2.50

# V6 speed pipeline
GLOBAL_SCREEN_SYMBOL_LIMIT = 4
GLOBAL_SCREEN_TOP = 30
FULL_BACKTEST_TOP = 10
WFO_TOP = 5
USE_DATA_CACHE = True
MIXED_MIN_SCORE = 0.75

# Maximum number of strategies to process.
# Keeps accidental KB growth from creating an enormous run.
MAX_STRATEGIES = 10


# ============================================================================
# RESEARCH UNIVERSE
# ============================================================================

BIST_RESEARCH_UNIVERSE = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "SISE.IS",
    "BIMAS.IS",
]

US_RESEARCH_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
]

COMBINED_RESEARCH_UNIVERSE = (
    BIST_RESEARCH_UNIVERSE
    + US_RESEARCH_UNIVERSE
)


# ============================================================================
# PARAMETER GRID
# ============================================================================

SMA_FAST_VALUES = [
    10,
    20,
    30,
]

SMA_SLOW_VALUES = [
    50,
    100,
]

EMA_FAST_VALUES = [
    10,
    20,
]

EMA_SLOW_VALUES = [
    30,
    50,
]

RSI_PERIOD_VALUES = [
    14,
]

RSI_OVERSOLD_VALUES = [
    25,
    30,
]

RSI_OVERBOUGHT_VALUES = [
    65,
    70,
]

STOP_ATR_VALUES = [
    1.5,
    2.0,
]

TARGET_ATR_VALUES = [
    2.0,
    3.0,
]


# ============================================================================
# BASIC HELPERS
# ============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().strftime(
        "%Y%m%d_%H%M%S"
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        if value is None:
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


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


def normalize_symbol(
    symbol: Any,
) -> str:

    if symbol is None:
        return ""

    return str(
        symbol
    ).strip().upper()


def print_header(
    title: str,
) -> None:

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_section(
    title: str,
) -> None:

    print()
    print("-" * 80)
    print(title)
    print("-" * 80)


# ============================================================================
# STRATEGY ID EXTRACTION
# ============================================================================

def extract_strategy_ids(
    value: Any,
) -> list[str]:

    found = []

    def walk(
        obj: Any,
    ) -> None:

        if isinstance(
            obj,
            dict,
        ):

            for key in [
                "strategy_id",
                "id",
                "strategyId",
            ]:

                candidate = obj.get(
                    key
                )

                if isinstance(
                    candidate,
                    str,
                ):

                    candidate = candidate.strip()

                    if candidate.startswith(
                        "STR-"
                    ):

                        found.append(
                            candidate
                        )

            for child in obj.values():
                walk(child)

        elif isinstance(
            obj,
            list,
        ):

            for child in obj:
                walk(child)

        elif isinstance(
            obj,
            str,
        ):

            text = obj.strip()

            if text.startswith(
                "STR-"
            ):

                found.append(
                    text
                )

    walk(value)

    result = []

    for item in found:

        if item not in result:
            result.append(item)

    return result


# ============================================================================
# KNOWLEDGE BASE
# ============================================================================

def get_kb_strategy_ids() -> list[str]:

    if search_strategies is None:
        return []

    attempts = [
        {},
        {"query": ""},
        {"keyword": ""},
    ]

    for kwargs in attempts:

        try:

            result = search_strategies(
                **kwargs
            )

            ids = extract_strategy_ids(
                result
            )

            if ids:
                return ids

        except TypeError:
            continue

        except Exception:
            continue

    return []


def load_strategy(
    strategy_id: str,
) -> dict[str, Any] | None:

    if get_strategy is None:
        return None

    try:

        result = get_strategy(
            strategy_id
        )

        if isinstance(
            result,
            dict,
        ):

            return result

    except Exception:
        pass

    return None


# ============================================================================
# DISCOVERY
# ============================================================================

def run_discovery() -> list[str]:

    print_header(
        "📚 V5 STRATEGY DISCOVERY"
    )

    if discover_source_files is None:

        print(
            "❌ research_ingestion_engine import edilemedi."
        )

        print(
            f"   {INGESTION_IMPORT_ERROR}"
        )

        return []

    if process_source is None:

        print(
            "❌ process_source bulunamadı."
        )

        return []

    try:

        sources = discover_source_files()

    except Exception as exc:

        print(
            f"❌ Kaynak keşfi başarısız: "
            f"{type(exc).__name__}: {exc}"
        )

        return []

    if sources is None:
        sources = []

    try:
        sources = list(sources)
    except TypeError:
        sources = []

    print(
        f"📂 Kaynak sayısı: {len(sources)}"
    )

    before_ids = set(
        get_kb_strategy_ids()
    )

    discovered = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print()
        print(
            f"SOURCE {index}/{len(sources)}"
        )

        try:

            result = process_source(
                source
            )

        except TypeError:

            try:

                source_path = getattr(
                    source,
                    "path",
                    source,
                )

                result = process_source(
                    str(source_path)
                )

            except Exception as exc:

                print(
                    f"⚠️ Discovery fallback hatası: "
                    f"{exc}"
                )

                continue

        except Exception as exc:

            print(
                f"⚠️ Discovery hatası: "
                f"{exc}"
            )

            continue

        result_ids = extract_strategy_ids(
            result
        )

        for strategy_id in result_ids:

            if strategy_id not in discovered:

                discovered.append(
                    strategy_id
                )

        after_ids = set(
            get_kb_strategy_ids()
        )

        for strategy_id in (
            after_ids - before_ids
        ):

            if strategy_id not in discovered:

                discovered.append(
                    strategy_id
                )

        before_ids = after_ids

    # Final KB scan
    final_ids = get_kb_strategy_ids()

    for strategy_id in final_ids:

        if strategy_id not in discovered:

            discovered.append(
                strategy_id
            )

    discovered = discovered[
        :MAX_STRATEGIES
    ]

    print_section(
        "DISCOVERY RESULT"
    )

    print(
        f"Strategies: {len(discovered)}"
    )

    for strategy_id in discovered:

        strategy = load_strategy(
            strategy_id
        )

        if strategy:

            name = (
                strategy.get("name")
                or strategy.get(
                    "strategy_name"
                )
                or strategy_id
            )

            print(
                f"  • {strategy_id} | {name}"
            )

    return discovered


# ============================================================================
# UNIVERSE
# ============================================================================

def choose_universe(
    strategy: dict[str, Any],
) -> list[str]:

    symbols = []

    fields = [
        "symbols",
        "symbol",
        "tickers",
        "instruments",
    ]

    for field in fields:

        value = strategy.get(
            field
        )

        if isinstance(
            value,
            str,
        ):

            symbol = normalize_symbol(
                value
            )

            if symbol:
                symbols.append(
                    symbol
                )

        elif isinstance(
            value,
            list,
        ):

            for item in value:

                symbol = normalize_symbol(
                    item
                )

                if symbol:
                    symbols.append(
                        symbol
                    )

    unique = []

    for symbol in symbols:

        if symbol not in unique:

            unique.append(
                symbol
            )

    if unique:
        return unique

    market = str(
        strategy.get(
            "market",
            "",
        )
    ).upper()

    if "BIST" in market:
        return BIST_RESEARCH_UNIVERSE.copy()

    if (
        "NASDAQ" in market
        or "NYSE" in market
        or "US" in market
    ):

        return US_RESEARCH_UNIVERSE.copy()

    return COMBINED_RESEARCH_UNIVERSE.copy()


# ============================================================================
# HISTORY
# ============================================================================

def normalize_history(
    data: pd.DataFrame,
) -> pd.DataFrame:

    if not isinstance(
        data,
        pd.DataFrame,
    ):

        return pd.DataFrame()

    result = data.copy()

    if isinstance(
        result.columns,
        pd.MultiIndex,
    ):

        result.columns = [
            str(column[0])
            if isinstance(
                column,
                tuple,
            )
            else str(column)
            for column in result.columns
        ]

    rename_map = {}

    for column in result.columns:

        name = str(
            column
        ).strip().lower()

        if name == "open":
            rename_map[column] = "Open"

        elif name == "high":
            rename_map[column] = "High"

        elif name == "low":
            rename_map[column] = "Low"

        elif name == "close":
            rename_map[column] = "Close"

        elif name == "volume":
            rename_map[column] = "Volume"

        elif name == "adj close":
            rename_map[column] = "Adj Close"

    result = result.rename(
        columns=rename_map
    )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    if not all(
        column in result.columns
        for column in required
    ):

        return pd.DataFrame()

    result = result[
        required
    ].copy()

    for column in required:

        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close",
        ]
    )

    result = result.sort_index()

    return result


def load_history(
    symbol: str,
    period: str,
) -> pd.DataFrame:

    symbol = normalize_symbol(symbol)

    if not hasattr(load_history, "_cache"):
        load_history._cache = {}

    cache = load_history._cache
    cache_key = (symbol, period)

    if USE_DATA_CACHE and cache_key in cache:
        return cache[cache_key].copy()

    data = pd.DataFrame()

    if get_history is not None:
        attempts = [
            {
                "symbol": symbol,
                "period": period,
            },
            {
                "ticker": symbol,
                "period": period,
            },
        ]

        for kwargs in attempts:
            try:
                fetched = get_history(**kwargs)
                if isinstance(fetched, pd.DataFrame):
                    normalized = normalize_history(fetched)
                    if not normalized.empty:
                        data = normalized
                        break
            except Exception:
                continue

    if data.empty:
        try:
            import yfinance as yf
            fetched = yf.download(
                symbol,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
            data = normalize_history(fetched)
        except Exception as exc:
            print(
                f"❌ {symbol} history hatası: {exc}"
            )
            data = pd.DataFrame()

    if USE_DATA_CACHE:
        cache[cache_key] = data.copy()

    return data


# ============================================================================
# CANDIDATE GRID
# ============================================================================

def build_parameter_candidates() -> list[
    dict[str, Any]
]:

    candidates = []

    for sma_fast in SMA_FAST_VALUES:

        for sma_slow in SMA_SLOW_VALUES:

            if sma_fast >= sma_slow:
                continue

            for ema_fast in EMA_FAST_VALUES:

                for ema_slow in EMA_SLOW_VALUES:

                    if ema_fast >= ema_slow:
                        continue

                    for rsi_period in RSI_PERIOD_VALUES:

                        for rsi_oversold in (
                            RSI_OVERSOLD_VALUES
                        ):

                            for rsi_overbought in (
                                RSI_OVERBOUGHT_VALUES
                            ):

                                if (
                                    rsi_oversold
                                    >=
                                    rsi_overbought
                                ):
                                    continue

                                for stop_atr in (
                                    STOP_ATR_VALUES
                                ):

                                    for target_atr in (
                                        TARGET_ATR_VALUES
                                    ):

                                        if target_atr <= 0:
                                            continue

                                        candidates.append(
                                            {
                                                "sma_fast": sma_fast,
                                                "sma_slow": sma_slow,
                                                "ema_fast": ema_fast,
                                                "ema_slow": ema_slow,
                                                "rsi_period": rsi_period,
                                                "rsi_oversold": rsi_oversold,
                                                "rsi_overbought": rsi_overbought,
                                                "stop_atr_multiplier": stop_atr,
                                                "target_atr_multiplier": target_atr,
                                            }
                                        )

    return candidates


# ============================================================================
# CONFIG BUILDERS
# ============================================================================

def build_signal_config(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    return {
        "sma_fast": candidate[
            "sma_fast"
        ],
        "sma_slow": candidate[
            "sma_slow"
        ],
        "ema_fast": candidate[
            "ema_fast"
        ],
        "ema_slow": candidate[
            "ema_slow"
        ],
        "rsi_period": candidate[
            "rsi_period"
        ],
        "rsi_oversold": candidate[
            "rsi_oversold"
        ],
        "rsi_overbought": candidate[
            "rsi_overbought"
        ],
        "buy_threshold": 3,
        "sell_threshold": -3,
    }


def build_backtest_config(
    candidate: dict[str, Any],
    commission_percent: float = 0.10,
    slippage_percent: float = 0.05,
) -> dict[str, Any]:

    return {
        "initial_capital": 100000,
        "position_size_percent": 10.0,
        "commission_percent": commission_percent,
        "slippage_percent": slippage_percent,
        "use_stop_loss": True,
        "use_take_profit": True,
        "allow_short": True,
        "one_position_at_a_time": True,
        "stop_atr_multiplier": candidate[
            "stop_atr_multiplier"
        ],
        "target_atr_multiplier": candidate[
            "target_atr_multiplier"
        ],
        "max_holding_bars": 60,
        "exit_on_opposite_signal": True,
    }


# ============================================================================
# BACKTEST
# ============================================================================

def execute_backtest(
    data: pd.DataFrame,
    symbol: str,
    candidate: dict[str, Any],
    commission_percent: float = 0.10,
    slippage_percent: float = 0.05,
) -> dict[str, Any]:

    if run_backtest is None:

        return {
            "status": "ERROR",
            "error": (
                "Backtest Engine import error: "
                f"{BACKTEST_IMPORT_ERROR}"
            ),
        }

    if data.empty:

        return {
            "status": "INCONCLUSIVE",
            "trades": [],
            "metrics": {},
        }

    signal_config = build_signal_config(
        candidate
    )

    backtest_config = build_backtest_config(
        candidate,
        commission_percent=commission_percent,
        slippage_percent=slippage_percent,
    )

    try:

        result = run_backtest(
            data=data,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )

        if not isinstance(
            result,
            dict,
        ):

            return {
                "status": "ERROR",
                "error": (
                    "Backtest dict döndürmedi."
                ),
            }

        return result

    except Exception as exc:

        return {
            "status": "ERROR",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


# ============================================================================
# METRICS
# ============================================================================

def extract_metrics(
    result: dict[str, Any],
) -> dict[str, Any]:

    metrics = result.get(
        "metrics"
    )

    if not isinstance(
        metrics,
        dict,
    ):

        metrics = {}

    trades_value = metrics.get(
        "total_trades"
    )

    if trades_value is None:

        trade_list = result.get(
            "trades"
        )

        if isinstance(
            trade_list,
            list,
        ):

            trades_value = len(
                trade_list
            )

        else:

            trades_value = 0

    trades = safe_int(
        trades_value
    )

    wins = safe_int(
        metrics.get(
            "winning_trades",
            0,
        )
    )

    losses = safe_int(
        metrics.get(
            "losing_trades",
            0,
        )
    )

    win_rate = safe_float(
        metrics.get(
            "win_rate_percent",
            0.0,
        )
    )

    profit_factor = safe_float(
        metrics.get(
            "profit_factor",
            0.0,
        )
    )

    total_pnl = safe_float(
        metrics.get(
            "net_pnl",
            0.0,
        )
    )

    return_pct = safe_float(
        metrics.get(
            "total_return_percent",
            0.0,
        )
    )

    max_drawdown = safe_float(
        metrics.get(
            "max_drawdown_percent",
            0.0,
        )
    )

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
    }


# ============================================================================
# CANDIDATE QUALITY
# ============================================================================

def candidate_quality_score(
    metrics: dict[str, Any],
) -> float:

    trades = safe_float(
        metrics.get("trades")
    )

    pf = safe_float(
        metrics.get(
            "profit_factor"
        )
    )

    return_pct = safe_float(
        metrics.get(
            "return_pct"
        )
    )

    dd = safe_float(
        metrics.get(
            "max_drawdown"
        )
    )

    if trades < MIN_TRAIN_TRADES:
        return -999.0

    score = 0.0

    score += return_pct * 2.0

    score += (
        max(
            0.0,
            pf - 1.0
        )
        * 3.0
    )

    score -= dd * 0.75

    # Reward enough observations,
    # but cap the influence.
    score += min(
        trades / 20.0,
        2.0,
    )

    return score


# ============================================================================
# FAST SCREEN
# ============================================================================

def fast_screen(
    data: pd.DataFrame,
    symbol: str,
    candidates: list[
        dict[str, Any]
    ],
    commission_percent: float = 0.10,
    slippage_percent: float = 0.05,
) -> list[
    dict[str, Any]
]:

    print_section(
        f"⚡ FAST SCREEN: {symbol}"
    )

    print(
        f"Aday sayısı: {len(candidates)}"
    )

    accepted = []

    errors = 0
    below_min = 0
    max_trades = 0

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        result = execute_backtest(
            data=data,
            symbol=symbol,
            candidate=candidate,
            commission_percent=commission_percent,
            slippage_percent=slippage_percent,
        )

        if result.get(
            "status"
        ) == "ERROR":

            errors += 1
            continue

        metrics = extract_metrics(
            result
        )

        max_trades = max(
            max_trades,
            metrics["trades"],
        )

        if (
            metrics["trades"]
            < MIN_TRAIN_TRADES
        ):

            below_min += 1
            continue

        accepted.append(
            {
                "candidate": candidate,
                "metrics": metrics,
                "quality_score": (
                    candidate_quality_score(
                        metrics
                    )
                ),
            }
        )

        if (
            index == 1
            or index % 50 == 0
            or index == len(candidates)
        ):

            print(
                f"Progress: "
                f"{index}/{len(candidates)}"
            )

    accepted.sort(
        key=lambda item: (
            item["quality_score"],
            item["metrics"][
                "return_pct"
            ],
            item["metrics"][
                "profit_factor"
            ],
        ),
        reverse=True,
    )

    print(
        f"Screen sonucu : "
        f"{len(accepted)} aday"
    )

    print(
        f"< {MIN_TRAIN_TRADES} trade : "
        f"{below_min}"
    )

    print(
        f"Backtest error : "
        f"{errors}"
    )

    print(
        f"En yüksek trade : "
        f"{max_trades}"
    )

    return accepted


# ============================================================================
# WALK FORWARD
# ============================================================================

def run_walk_forward(
    data: pd.DataFrame,
    symbol: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:

    print_section(f"🔬 WALK-FORWARD V6: {symbol}")

    minimum_length = TRAIN_BARS + VALIDATION_BARS

    if len(data) < minimum_length:
        return {
            "status": "INCONCLUSIVE",
            "folds": [],
            "positive_folds": 0,
            "negative_folds": 0,
            "inconclusive_folds": 0,
        }

    folds = []
    start = 0
    fold_number = 0

    # V6: candidates are already reduced before WFO.
    wfo_candidates = candidates[:WFO_TOP]

    while start + TRAIN_BARS + VALIDATION_BARS <= len(data):
        fold_number += 1
        train_end = start + TRAIN_BARS
        validation_end = train_end + VALIDATION_BARS

        train = data.iloc[start:train_end].copy()
        validation = data.iloc[train_end:validation_end].copy()

        print()
        print(f"Fold {fold_number} | candidates={len(wfo_candidates)}")

        train_results = []
        for candidate in wfo_candidates:
            result = execute_backtest(
                data=train,
                symbol=symbol,
                candidate=candidate,
            )
            metrics = extract_metrics(result)
            if metrics["trades"] >= MIN_TRAIN_TRADES:
                train_results.append({
                    "candidate": candidate,
                    "metrics": metrics,
                    "quality_score": candidate_quality_score(metrics),
                })

        train_results.sort(
            key=lambda item: item["quality_score"],
            reverse=True,
        )

        if not train_results:
            folds.append({
                "fold": fold_number,
                "status": "NO_TRAIN_CANDIDATE",
                "train_trades": 0,
                "validation_trades": 0,
            })
            start += STEP_BARS
            continue

        validation_results = []
        for item in train_results[:WFO_TOP]:
            candidate = item["candidate"]
            validation_result = execute_backtest(
                data=validation,
                symbol=symbol,
                candidate=candidate,
            )
            validation_metrics = extract_metrics(validation_result)
            validation_results.append({
                "candidate": candidate,
                "train_metrics": item["metrics"],
                "validation_metrics": validation_metrics,
            })

        validation_results.sort(
            key=lambda item: (
                candidate_quality_score(item["validation_metrics"]),
                item["validation_metrics"]["return_pct"],
            ),
            reverse=True,
        )

        best = validation_results[0]
        vm = best["validation_metrics"]

        if vm["trades"] < MIN_VALIDATION_TRADES:
            status = "INCONCLUSIVE"
        elif vm["return_pct"] > 0 and vm["profit_factor"] > 1:
            status = "POSITIVE"
        else:
            status = "NEGATIVE"

        folds.append({
            "fold": fold_number,
            "status": status,
            "train_metrics": best["train_metrics"],
            "validation_metrics": vm,
            "candidate": best["candidate"],
        })

        print(
            f"Result={status} | trades={vm['trades']} | "
            f"return={vm['return_pct']:.2f}% | PF={vm['profit_factor']:.3f}"
        )

        start += STEP_BARS

    positive = sum(1 for fold in folds if fold.get("status") == "POSITIVE")
    negative = sum(1 for fold in folds if fold.get("status") == "NEGATIVE")
    inconclusive = sum(1 for fold in folds if fold.get("status") == "INCONCLUSIVE")

    returns = []
    pnls = []
    trades = []
    wins = []
    losses = []

    for fold in folds:
        metrics = fold.get("validation_metrics")
        if not metrics:
            continue
        returns.append(safe_float(metrics.get("return_pct")))
        pnls.append(safe_float(metrics.get("total_pnl")))
        trades.append(safe_int(metrics.get("trades")))
        wins.append(safe_int(metrics.get("wins")))
        losses.append(safe_int(metrics.get("losses")))

    total_trades = sum(trades)
    total_wins = sum(wins)
    total_losses = sum(losses)

    return {
        "status": "DONE",
        "fold_count": len(folds),
        "positive_folds": positive,
        "negative_folds": negative,
        "inconclusive_folds": inconclusive,
        "validation_trades": total_trades,
        "validation_wins": total_wins,
        "validation_losses": total_losses,
        "aggregate_win_rate": (total_wins / total_trades * 100.0 if total_trades else 0.0),
        "average_fold_return": statistics.mean(returns) if returns else 0.0,
        "validation_return_std": statistics.pstdev(returns) if len(returns) >= 2 else 0.0,
        "total_validation_pnl": sum(pnls),
        "folds": folds,
    }


# ============================================================================
# COST STRESS
# ============================================================================

def run_cost_stress(
    data: pd.DataFrame,
    symbol: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:

    print_section(
        f"💸 COST STRESS: {symbol}"
    )

    results = []

    for level in COST_STRESS_LEVELS:

        name = level[
            "name"
        ]

        commission = level[
            "commission_percent"
        ]

        slippage = level[
            "slippage_percent"
        ]

        result = execute_backtest(
            data=data,
            symbol=symbol,
            candidate=candidate,
            commission_percent=commission,
            slippage_percent=slippage,
        )

        metrics = extract_metrics(
            result
        )

        results.append(
            {
                "level": name,
                "commission_percent": commission,
                "slippage_percent": slippage,
                "metrics": metrics,
            }
        )

        print(
            f"{name:14} "
            f"Return={metrics['return_pct']:7.2f}% "
            f"PF={metrics['profit_factor']:6.3f} "
            f"Trades={metrics['trades']:3d}"
        )

    base = results[0]["metrics"]

    high = results[-1]["metrics"]

    return_drop = (
        base["return_pct"]
        - high["return_pct"]
    )

    survives_high_cost = (
        high["trades"]
        >= MIN_TRAIN_TRADES
        and high["profit_factor"]
        > 1.0
        and high["return_pct"]
        > 0
    )

    return {
        "levels": results,
        "base_return": base[
            "return_pct"
        ],
        "high_cost_return": high[
            "return_pct"
        ],
        "return_drop": return_drop,
        "survives_high_cost": (
            survives_high_cost
        ),
    }


# ============================================================================
# PARAMETER STABILITY
# ============================================================================

def parameter_key(
    candidate: dict[str, Any],
) -> tuple:

    return (
        candidate.get(
            "sma_fast"
        ),
        candidate.get(
            "sma_slow"
        ),
        candidate.get(
            "ema_fast"
        ),
        candidate.get(
            "ema_slow"
        ),
        candidate.get(
            "rsi_period"
        ),
        candidate.get(
            "rsi_oversold"
        ),
        candidate.get(
            "rsi_overbought"
        ),
        candidate.get(
            "stop_atr_multiplier"
        ),
        candidate.get(
            "target_atr_multiplier"
        ),
    )


def parameter_distance(
    a: dict[str, Any],
    b: dict[str, Any],
) -> int:

    keys = [
        "sma_fast",
        "sma_slow",
        "ema_fast",
        "ema_slow",
        "rsi_period",
        "rsi_oversold",
        "rsi_overbought",
        "stop_atr_multiplier",
        "target_atr_multiplier",
    ]

    return sum(
        1
        for key in keys
        if a.get(key)
        != b.get(key)
    )


def run_parameter_stability(
    data: pd.DataFrame,
    symbol: str,
    best_candidate: dict[str, Any],
    candidates: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:

    print_section(
        f"🧩 PARAMETER STABILITY: {symbol}"
    )

    neighbors = sorted(
        candidates,
        key=lambda candidate: (
            parameter_distance(
                best_candidate,
                candidate,
            )
        ),
    )

    selected = []

    seen = set()

    for candidate in neighbors:

        key = parameter_key(
            candidate
        )

        if key in seen:
            continue

        seen.add(key)

        selected.append(
            candidate
        )

        if len(selected) >= (
            PARAMETER_STABILITY_LIMIT
        ):

            break

    results = []

    for candidate in selected:

        result = execute_backtest(
            data=data,
            symbol=symbol,
            candidate=candidate,
        )

        metrics = extract_metrics(
            result
        )

        results.append(
            {
                "candidate": candidate,
                "metrics": metrics,
                "distance": parameter_distance(
                    best_candidate,
                    candidate,
                ),
            }
        )

    valid = [
        item
        for item in results
        if item["metrics"][
            "trades"
        ] >= MIN_TRAIN_TRADES
    ]

    positive = [
        item
        for item in valid
        if (
            item["metrics"][
                "return_pct"
            ] > 0
            and item["metrics"][
                "profit_factor"
            ] > 1
        )
    ]

    stability_ratio = (
        len(positive)
        / len(valid)
        if valid
        else 0.0
    )

    print(
        f"Neighbors tested : "
        f"{len(results)}"
    )

    print(
        f"Valid neighbors   : "
        f"{len(valid)}"
    )

    print(
        f"Positive neighbors: "
        f"{len(positive)}"
    )

    print(
        f"Stability ratio   : "
        f"{stability_ratio:.2%}"
    )

    return {
        "tested": len(results),
        "valid": len(valid),
        "positive": len(positive),
        "stability_ratio": (
            stability_ratio
        ),
        "results": results,
    }


# ============================================================================
# REGIME STABILITY
# ============================================================================

def run_regime_stability(
    data: pd.DataFrame,
    symbol: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:

    print_section(
        f"🌦️ REGIME STABILITY: {symbol}"
    )

    if len(data) < 90:

        return {
            "status": "INCONCLUSIVE",
            "segments": [],
        }

    segments = []

    segment_size = max(
        63,
        len(data) // 4,
    )

    start = 0
    segment_number = 0

    while start < len(data):

        end = min(
            start + segment_size,
            len(data),
        )

        segment = data.iloc[
            start:end
        ].copy()

        if len(segment) < 30:
            break

        segment_number += 1

        result = execute_backtest(
            data=segment,
            symbol=symbol,
            candidate=candidate,
        )

        metrics = extract_metrics(
            result
        )

        segments.append(
            {
                "segment": segment_number,
                "bars": len(segment),
                "metrics": metrics,
            }
        )

        print(
            f"Segment {segment_number}: "
            f"return="
            f"{metrics['return_pct']:.2f}% "
            f"PF="
            f"{metrics['profit_factor']:.3f} "
            f"trades="
            f"{metrics['trades']}"
        )

        start = end

    valid = [
        item
        for item in segments
        if item["metrics"][
            "trades"
        ] >= MIN_VALIDATION_TRADES
    ]

    positive = [
        item
        for item in valid
        if (
            item["metrics"][
                "return_pct"
            ] > 0
            and item["metrics"][
                "profit_factor"
            ] > 1
        )
    ]

    ratio = (
        len(positive)
        / len(valid)
        if valid
        else 0.0
    )

    return {
        "status": "DONE",
        "segments": segments,
        "valid_segments": len(valid),
        "positive_segments": len(
            positive
        ),
        "positive_ratio": ratio,
    }


# ============================================================================
# CONSISTENCY
# ============================================================================

def calculate_consistency(
    backtests: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:

    valid = [
        item
        for item in backtests
        if item.get(
            "status"
        ) == "DONE"
    ]

    if not valid:

        return {
            "symbols": 0,
            "positive": 0,
            "negative": 0,
            "positive_ratio": 0.0,
            "return_mean": 0.0,
            "return_std": 0.0,
        }

    returns = [
        safe_float(
            item.get(
                "metrics",
                {},
            ).get(
                "return_pct"
            )
        )
        for item in valid
    ]

    positive = sum(
        1
        for value in returns
        if value > 0
    )

    negative = len(
        returns
    ) - positive

    return {
        "symbols": len(valid),
        "positive": positive,
        "negative": negative,
        "positive_ratio": (
            positive
            / len(valid)
        ),
        "return_mean": (
            statistics.mean(
                returns
            )
            if returns
            else 0.0
        ),
        "return_std": (
            statistics.pstdev(
                returns
            )
            if len(returns) >= 2
            else 0.0
        ),
    }


# ============================================================================
# RANKING
# ============================================================================

def calculate_v5_score(
    consistency: dict[str, Any],
    wfo: dict[str, Any],
    cost_stress: list[
        dict[str, Any]
    ],
    parameter_stability: list[
        dict[str, Any]
    ],
    regime_stability: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:

    positive_ratio = safe_float(
        consistency.get(
            "positive_ratio"
        )
    )

    mean_return = safe_float(
        consistency.get(
            "return_mean"
        )
    )

    wfo_positive = sum(
        safe_int(
            item.get(
                "positive_folds"
            )
        )
        for item in wfo
    )

    wfo_negative = sum(
        safe_int(
            item.get(
                "negative_folds"
            )
        )
        for item in wfo
    )

    wfo_inconclusive = sum(
        safe_int(
            item.get(
                "inconclusive_folds"
            )
        )
        for item in wfo
    )

    wfo_total = (
        wfo_positive
        + wfo_negative
        + wfo_inconclusive
    )

    wfo_ratio = (
        wfo_positive
        / wfo_total
        if wfo_total
        else 0.0
    )

    average_wfo_return = (
        statistics.mean(
            [
                safe_float(
                    item.get(
                        "average_fold_return"
                    )
                )
                for item in wfo
            ]
        )
        if wfo
        else 0.0
    )

    cost_survival = (
        sum(
            1
            for item in cost_stress
            if item.get(
                "survives_high_cost"
            )
        )
        / len(cost_stress)
        if cost_stress
        else 0.0
    )

    parameter_ratio = (
        statistics.mean(
            [
                safe_float(
                    item.get(
                        "stability_ratio"
                    )
                )
                for item in parameter_stability
            ]
        )
        if parameter_stability
        else 0.0
    )

    regime_ratio = (
        statistics.mean(
            [
                safe_float(
                    item.get(
                        "positive_ratio"
                    )
                )
                for item in regime_stability
            ]
        )
        if regime_stability
        else 0.0
    )

    score = 0.0

    # Cross-symbol consistency
    score += positive_ratio * 3.0

    # Average return
    score += mean_return * 0.35

    # WFO
    score += wfo_ratio * 3.0

    score += average_wfo_return * 0.50

    # Robustness
    score += cost_survival * 1.50

    score += parameter_ratio * 2.00

    score += regime_ratio * 1.50

    if (
        score
        >= PROMISING_MIN_SCORE
        and positive_ratio >= 0.50
        and wfo_ratio >= 0.50
    ):

        classification = "PROMISING"

    elif score >= MIXED_MIN_SCORE:

        classification = "MIXED"

    else:

        classification = "WEAK"

    return {
        "score": score,
        "classification": classification,
        "cross_symbol_positive_ratio": (
            positive_ratio
        ),
        "average_return": mean_return,
        "wfo_positive_ratio": wfo_ratio,
        "average_wfo_return": (
            average_wfo_return
        ),
        "cost_survival": cost_survival,
        "parameter_stability": (
            parameter_ratio
        ),
        "regime_stability": (
            regime_ratio
        ),
    }


# ============================================================================
# VALIDATION ENGINE
# ============================================================================

def run_external_validation(
    strategy_id: str,
) -> dict[str, Any]:

    print_section(
        "🧪 EXTERNAL STRATEGY VALIDATION"
    )

    if validate_strategy is None:

        return {
            "status": "UNAVAILABLE",
            "error": str(
                VALIDATION_IMPORT_ERROR
            ),
        }

    try:

        result = validate_strategy(
            strategy_id
        )

        if isinstance(
            result,
            dict,
        ):

            return result

        return {
            "status": "DONE",
            "result": str(result),
        }

    except TypeError:

        try:

            strategy = load_strategy(
                strategy_id
            )

            if strategy is None:

                return {
                    "status": "ERROR",
                    "error": (
                        "Strategy KB'den okunamadı."
                    ),
                }

            result = validate_strategy(
                strategy
            )

            if isinstance(
                result,
                dict,
            ):

                return result

            return {
                "status": "DONE",
                "result": str(result),
            }

        except Exception as exc:

            return {
                "status": "ERROR",
                "error": (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            }

    except Exception as exc:

        return {
            "status": "ERROR",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


# ============================================================================
# V6 GLOBAL SCREEN
# ============================================================================

def run_global_screen(
    candidates: list[dict[str, Any]],
    universe: list[str],
) -> list[dict[str, Any]]:
    """
    V6: 384 adayın tamamını bütün sembollerde tekrar tekrar taramak yerine
    küçük bir temsilci sembol grubunda hızlıca değerlendirir.
    """
    print_header("⚡ V6 GLOBAL FAST SCREEN")

    sample_symbols = universe[:GLOBAL_SCREEN_SYMBOL_LIMIT]
    print(f"Sample symbols : {len(sample_symbols)}")
    print(f"Candidates     : {len(candidates)}")
    print(f"Global top     : {GLOBAL_SCREEN_TOP}")

    aggregate = {}

    for symbol in sample_symbols:
        data = load_history(symbol, BACKTEST_PERIOD)
        if data.empty:
            print(f"⚠️ {symbol}: veri yok, global screen atlandı.")
            continue

        print(f"\n🔎 Global screen: {symbol} | bars={len(data)}")
        screen = fast_screen(data, symbol, candidates)

        for rank, item in enumerate(screen):
            key = parameter_key(item["candidate"])
            bucket = aggregate.setdefault(
                key,
                {
                    "candidate": item["candidate"],
                    "scores": [],
                    "returns": [],
                    "profit_factors": [],
                    "drawdowns": [],
                    "trades": [],
                },
            )
            bucket["scores"].append(item["quality_score"])
            bucket["returns"].append(item["metrics"]["return_pct"])
            bucket["profit_factors"].append(item["metrics"]["profit_factor"])
            bucket["drawdowns"].append(item["metrics"]["max_drawdown"])
            bucket["trades"].append(item["metrics"]["trades"])

    ranked = []
    for bucket in aggregate.values():
        if not bucket["scores"]:
            continue
        ranked.append({
            "candidate": bucket["candidate"],
            "global_score": statistics.mean(bucket["scores"]),
            "average_return": statistics.mean(bucket["returns"]),
            "average_profit_factor": statistics.mean(bucket["profit_factors"]),
            "average_drawdown": statistics.mean(bucket["drawdowns"]),
            "average_trades": statistics.mean(bucket["trades"]),
            "symbols_tested": len(bucket["scores"]),
        })

    ranked.sort(
        key=lambda item: (
            item["global_score"],
            item["average_return"],
            item["average_profit_factor"],
        ),
        reverse=True,
    )

    selected = ranked[:GLOBAL_SCREEN_TOP]

    print_section("V6 GLOBAL SCREEN RESULT")
    print(f"Evaluated candidates : {len(aggregate)}")
    print(f"Selected candidates  : {len(selected)}")

    for index, item in enumerate(selected[:10], start=1):
        print(
            f"{index:>2}. score={item['global_score']:.3f} | "
            f"ret={item['average_return']:.2f}% | "
            f"PF={item['average_profit_factor']:.3f} | "
            f"symbols={item['symbols_tested']} | "
            f"{item['candidate']}"
        )

    return [item["candidate"] for item in selected]


# ============================================================================
# STRATEGY RESEARCH
# ============================================================================

def research_strategy(
    strategy_id: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:

    strategy = load_strategy(strategy_id)
    if strategy is None:
        print(f"❌ Strategy bulunamadı: {strategy_id}")
        return None

    strategy_name = (
        strategy.get("name")
        or strategy.get("strategy_name")
        or strategy_id
    )
    universe = choose_universe(strategy)

    print_header(f"🧠 V6 RESEARCH: {strategy_name}")
    print(f"Strategy ID : {strategy_id}")
    print(f"Universe    : {len(universe)} symbols")
    print(", ".join(universe))

    # Stage 1: global reduction 384 -> 30.
    reduced_candidates = run_global_screen(candidates, universe)
    if not reduced_candidates:
        print("⚠️ Global screen sonrası aday kalmadı.")
        return None

    # Stage 2: full 1Y backtest on all symbols, but only reduced candidates.
    backtests = []
    wfo_results = []
    parameter_results = []
    regime_results = []
    cost_results = []

    for index, symbol in enumerate(universe, start=1):
        print_header(f"📈 V6 FULL RESEARCH {index}/{len(universe)}: {symbol}")

        data = load_history(symbol, BACKTEST_PERIOD)
        if data.empty:
            backtests.append({"symbol": symbol, "status": "INCONCLUSIVE", "metrics": {}})
            continue

        screen = fast_screen(data, symbol, reduced_candidates)
        top_full = screen[:FULL_BACKTEST_TOP]

        if not top_full:
            print("⚠️ Full backtest aşamasında aday yok.")
            backtests.append({"symbol": symbol, "status": "INCONCLUSIVE", "metrics": {}})
            continue

        best = top_full[0]
        best_candidate = best["candidate"]
        best_metrics = best["metrics"]

        print_section("🏆 V6 BEST BACKTEST")
        print(f"Trades : {best_metrics['trades']}")
        print(f"WinRate: {best_metrics['win_rate']:.2f}%")
        print(f"PF     : {best_metrics['profit_factor']:.3f}")
        print(f"Return : {best_metrics['return_pct']:.2f}%")
        print(f"DD     : {best_metrics['max_drawdown']:.2f}%")
        print(f"Params : {best_candidate}")

        backtests.append({
            "symbol": symbol,
            "status": "DONE",
            "metrics": best_metrics,
            "candidate": best_candidate,
            "top_candidates": top_full,
        })

        # Stage 3: WFO only sees top candidates from this symbol.
        wfo_data = load_history(symbol, WFO_PERIOD)
        if not wfo_data.empty:
            wfo = run_walk_forward(
                wfo_data,
                symbol,
                [item["candidate"] for item in top_full],
            )
            wfo["symbol"] = symbol
            wfo_results.append(wfo)

            parameter_stability = run_parameter_stability(
                data=wfo_data,
                symbol=symbol,
                best_candidate=best_candidate,
                candidates=reduced_candidates,
            )
            parameter_stability["symbol"] = symbol
            parameter_results.append(parameter_stability)

            regime = run_regime_stability(
                data=wfo_data,
                symbol=symbol,
                candidate=best_candidate,
            )
            regime["symbol"] = symbol
            regime_results.append(regime)

        cost = run_cost_stress(
            data=data,
            symbol=symbol,
            candidate=best_candidate,
        )
        cost["symbol"] = symbol
        cost_results.append(cost)

    consistency = calculate_consistency(backtests)
    ranking = calculate_v5_score(
        consistency=consistency,
        wfo=wfo_results,
        cost_stress=cost_results,
        parameter_stability=parameter_results,
        regime_stability=regime_results,
    )
    validation = run_external_validation(strategy_id)

    print_header(f"📊 V6 STRATEGY SUMMARY: {strategy_name}")
    print(f"Backtest symbols       : {consistency['symbols']}")
    print(f"Positive symbols       : {consistency['positive']}")
    print(f"Negative symbols       : {consistency['negative']}")
    print(f"Cross-symbol ratio     : {consistency['positive_ratio']:.2%}")
    print(f"Average return         : {consistency['return_mean']:.2f}%")
    print(f"Return std             : {consistency['return_std']:.2f}%")

    total_positive_wfo = sum(safe_int(item.get("positive_folds")) for item in wfo_results)
    total_negative_wfo = sum(safe_int(item.get("negative_folds")) for item in wfo_results)
    total_inconclusive_wfo = sum(safe_int(item.get("inconclusive_folds")) for item in wfo_results)

    print(f"WFO positive folds    : {total_positive_wfo}")
    print(f"WFO negative folds    : {total_negative_wfo}")
    print(f"WFO inconclusive      : {total_inconclusive_wfo}")
    print(f"Cost robustness       : {ranking['cost_survival']:.2%}")
    print(f"Parameter stability   : {ranking['parameter_stability']:.2%}")
    print(f"Regime stability      : {ranking['regime_stability']:.2%}")
    print(f"V6 Ranking Score      : {ranking['score']:.4f}")
    print(f"Classification         : {ranking['classification']}")

    result = {
        "pipeline_version": PIPELINE_VERSION,
        "timestamp": utc_now().isoformat(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "strategy": strategy,
        "research_only": RESEARCH_ONLY,
        "execution_enabled": EXECUTION_ENABLED,
        "candidate_count": len(candidates),
        "global_screen_top": len(reduced_candidates),
        "full_backtest_top": FULL_BACKTEST_TOP,
        "wfo_top": WFO_TOP,
        "universe": universe,
        "config": {
            "backtest_period": BACKTEST_PERIOD,
            "wfo_period": WFO_PERIOD,
            "train_bars": TRAIN_BARS,
            "validation_bars": VALIDATION_BARS,
            "step_bars": STEP_BARS,
            "minimum_train_trades": MIN_TRAIN_TRADES,
            "minimum_validation_trades": MIN_VALIDATION_TRADES,
            "global_screen_symbol_limit": GLOBAL_SCREEN_SYMBOL_LIMIT,
            "global_screen_top": GLOBAL_SCREEN_TOP,
            "full_backtest_top": FULL_BACKTEST_TOP,
            "wfo_top": WFO_TOP,
            "use_data_cache": USE_DATA_CACHE,
        },
        "backtests": backtests,
        "walk_forward": wfo_results,
        "cost_stress": cost_results,
        "parameter_stability": parameter_results,
        "regime_stability": regime_results,
        "consistency": consistency,
        "validation": validation,
        "ranking": ranking,
    }

    output_path = RESULT_DIR / f"strategy_pipeline_v6_{strategy_id}_{utc_timestamp()}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=str)

    print()
    print("💾 V6 Strategy result saved:")
    print(str(output_path))
    return result


# ============================================================================
# COMPATIBILITY CHECK
# ============================================================================

def run_compatibility_check() -> bool:

    print_header(
        "🔧 V6 COMPATIBILITY CHECK"
    )

    if run_backtest is None:

        print(
            "❌ Backtest Engine import edilemedi."
        )

        print(
            BACKTEST_IMPORT_ERROR
        )

        return False

    data = load_history(
        "THYAO.IS",
        "1y",
    )

    if data.empty:

        print(
            "❌ THYAO.IS verisi alınamadı."
        )

        return False

    candidates = (
        build_parameter_candidates()
    )

    if not candidates:

        print(
            "❌ Candidate grid boş."
        )

        return False

    candidate = candidates[0]

    result = execute_backtest(
        data=data,
        symbol="THYAO.IS",
        candidate=candidate,
    )

    if result.get(
        "status"
    ) == "ERROR":

        print(
            "❌ Compatibility backtest hatası:"
        )

        print(
            result.get(
                "error"
            )
        )

        return False

    metrics = extract_metrics(
        result
    )

    print(
        f"Candidate count : "
        f"{len(candidates)}"
    )

    print(
        f"THYAO bars      : "
        f"{len(data)}"
    )

    print(
        f"Parsed trades   : "
        f"{metrics['trades']}"
    )

    print(
        f"Parsed win rate : "
        f"{metrics['win_rate']:.2f}%"
    )

    print(
        f"Parsed PF       : "
        f"{metrics['profit_factor']:.3f}"
    )

    print(
        f"Parsed return   : "
        f"{metrics['return_pct']:.2f}%"
    )

    if not isinstance(
        result.get("trades"),
        list,
    ):

        print(
            "❌ result['trades'] list değil."
        )

        return False

    if not isinstance(
        result.get("metrics"),
        dict,
    ):

        print(
            "❌ result['metrics'] dict değil."
        )

        return False

    print(
        "✅ V6 ↔ Backtest Engine "
        "veri sözleşmesi OK."
    )

    return True


# ============================================================================
# MASTER PIPELINE
# ============================================================================

def run_pipeline() -> int:

    started_at = utc_now()

    print_header(
        f"🧠 MARKET HQ "
        f"STRATEGY RESEARCH PIPELINE "
        f"{PIPELINE_VERSION}"
    )

    print(
        "Sources → Discovery → KB → "
        "Global Screen → Full Backtest → WFO → "
        "Validation → Robustness → Ranking"
    )

    print()

    print(
        f"Research Only     : "
        f"{RESEARCH_ONLY}"
    )

    print(
        f"Execution Enabled : "
        f"{EXECUTION_ENABLED}"
    )

    # ------------------------------------------------------------------------
    # DISCOVERY
    # ------------------------------------------------------------------------

    strategy_ids = run_discovery()

    if not strategy_ids:

        print()
        print(
            "❌ Discovery sonrası "
            "strateji bulunamadı."
        )

        return 1

    # ------------------------------------------------------------------------
    # CANDIDATES
    # ------------------------------------------------------------------------

    candidates = (
        build_parameter_candidates()
    )

    print_section(
        "⚙️ CANDIDATE ENGINE"
    )

    print(
        f"Candidate count: "
        f"{len(candidates)}"
    )

    # ------------------------------------------------------------------------
    # STRATEGIES
    # ------------------------------------------------------------------------

    results = []

    for index, strategy_id in enumerate(
        strategy_ids,
        start=1,
    ):

        print_header(
            f"STRATEGY "
            f"{index}/{len(strategy_ids)}"
        )

        try:

            result = research_strategy(
                strategy_id,
                candidates,
            )

            if result is not None:

                results.append(
                    result
                )

        except Exception as exc:

            print()
            print(
                "❌ Strategy research error"
            )

            print(
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            traceback.print_exc()

    # ------------------------------------------------------------------------
    # FINAL RANKING
    # ------------------------------------------------------------------------

    results.sort(
        key=lambda item: safe_float(
            item.get(
                "ranking",
                {},
            ).get(
                "score"
            )
        ),
        reverse=True,
    )

    print_header(
        "🏆 V6 FINAL STRATEGY RANKING"
    )

    for index, result in enumerate(
        results,
        start=1,
    ):

        ranking = result.get(
            "ranking",
            {},
        )

        print(
            f"{index:>2}. "
            f"{result.get('strategy_id')} | "
            f"{result.get('strategy_name')} | "
            f"Score="
            f"{safe_float(ranking.get('score')):.4f} | "
            f"{ranking.get('classification')}"
        )

    # ------------------------------------------------------------------------
    # MASTER RESULT
    # ------------------------------------------------------------------------

    finished_at = utc_now()

    master_result = {
        "pipeline_version": (
            PIPELINE_VERSION
        ),
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "research_only": (
            RESEARCH_ONLY
        ),
        "execution_enabled": (
            EXECUTION_ENABLED
        ),
        "candidate_count": len(
            candidates
        ),
        "strategy_count": len(
            results
        ),
        "strategies": results,
    }

    master_path = (
        RESULT_DIR
        / (
            "strategy_pipeline_v6_"
            f"{utc_timestamp()}.json"
        )
    )

    with master_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            master_result,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------------

    print()
    print(
        "=" * 80
    )

    print(
        "✅ MARKET HQ V5 "
        "RESEARCH PIPELINE TAMAMLANDI"
    )

    print(
        "=" * 80
    )

    print(
        f"Strategy count : "
        f"{len(results)}"
    )

    print(
        f"Candidate count: "
        f"{len(candidates)}"
    )

    print(
        f"Research Only  : "
        f"{RESEARCH_ONLY}"
    )

    print(
        f"Execution      : "
        f"{EXECUTION_ENABLED}"
    )

    print()

    print(
        "💾 Master result:"
    )

    print(
        str(master_path)
    )

    return 0


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":

    try:

        # First verify the data contract.
        if not run_compatibility_check():

            print()
            print(
                "⛔ Compatibility check başarısız."
            )

            print(
                "Pipeline başlatılmadı."
            )

            raise SystemExit(
                1
            )

        raise SystemExit(
            run_pipeline()
        )

    except KeyboardInterrupt:

        print()
        print(
            "⛔ Pipeline kullanıcı "
            "tarafından durduruldu."
        )

        raise SystemExit(
            130
        )

    except Exception as exc:

        print()
        print(
            "❌ V6 PIPELINE ERROR"
        )

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        traceback.print_exc()

        raise SystemExit(
            1
        )


