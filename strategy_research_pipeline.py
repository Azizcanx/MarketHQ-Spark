# -*- coding: utf-8 -*-

"""
MarketHQ - Strategy Research Pipeline V4.3
------------------------------------------

Araştırma hattı:

Sources
    ↓
Discovery
    ↓
Knowledge Base
    ↓
Backtest
    ↓
Walk-Forward
    ↓
Validation
    ↓
Ranking

SAFETY:
- Research only
- No broker
- No order execution
- No real-money trading

V4.3 FIXES:
1. discover_source_files() parametresiz çağrılıyor.
2. UTC datetime artık timezone-aware.
3. Discovery sonrası KB tekrar taranıyor.
"""

from __future__ import annotations

import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

RESULT_DIR = PROJECT_ROOT / "strategy_pipeline_results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

RESEARCH_SOURCE_DIR = PROJECT_ROOT / "research_sources"


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
        build_summary,
    )
except Exception as exc:
    get_strategy = None
    search_strategies = None
    build_summary = None
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
    from strategy_validation_engine import validate_strategy
except Exception as exc:
    validate_strategy = None
    VALIDATION_IMPORT_ERROR = exc
else:
    VALIDATION_IMPORT_ERROR = None


try:
    from agents.market_data_agent import get_history
except Exception:
    get_history = None


# ============================================================================
# CONFIG
# ============================================================================

PIPELINE_VERSION = "V4.3"

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


# ============================================================================
# PARAMETER GRID
# ============================================================================

SMA_FAST_VALUES = [10, 20, 30]
SMA_SLOW_VALUES = [50, 100]

EMA_FAST_VALUES = [10, 20]
EMA_SLOW_VALUES = [30, 50]

RSI_PERIOD_VALUES = [14]
RSI_OVERSOLD_VALUES = [25, 30]
RSI_OVERBOUGHT_VALUES = [65, 70]

STOP_ATR_VALUES = [1.5, 2.0]
TARGET_ATR_VALUES = [2.0, 3.0]


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
# HELPERS
# ============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().strftime("%Y%m%d_%H%M%S")


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

    except (TypeError, ValueError):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def normalize_symbol(
    symbol: Any,
) -> str:

    if symbol is None:
        return ""

    return str(symbol).strip().upper()


def print_header(
    title: str,
) -> None:

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(
    title: str,
) -> None:

    print()
    print("-" * 78)
    print(title)
    print("-" * 78)


# ============================================================================
# STRATEGY ID EXTRACTION
# ============================================================================

def extract_strategy_ids(
    value: Any,
) -> list[str]:

    found: list[str] = []

    def walk(obj: Any) -> None:

        if isinstance(obj, dict):

            possible_keys = [
                "strategy_id",
                "id",
                "strategyId",
            ]

            for key in possible_keys:

                candidate = obj.get(key)

                if isinstance(candidate, str):

                    candidate = candidate.strip()

                    if candidate.startswith("STR-"):
                        found.append(candidate)

            for child in obj.values():
                walk(child)

        elif isinstance(obj, list):

            for child in obj:
                walk(child)

        elif isinstance(obj, str):

            text = obj.strip()

            if text.startswith("STR-"):
                found.append(text)

    walk(value)

    unique = []

    for item in found:

        if item not in unique:
            unique.append(item)

    return unique


# ============================================================================
# KB
# ============================================================================

def get_kb_strategy_ids() -> list[str]:

    ids: list[str] = []

    if search_strategies is None:
        return ids

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

            candidates = extract_strategy_ids(
                result
            )

            for strategy_id in candidates:

                if strategy_id not in ids:
                    ids.append(strategy_id)

            if ids:
                return ids

        except TypeError:
            continue

        except Exception:
            continue

    return ids


def load_strategy(
    strategy_id: str,
) -> dict[str, Any] | None:

    if get_strategy is None:
        return None

    try:

        strategy = get_strategy(
            strategy_id
        )

        if isinstance(strategy, dict):
            return strategy

        return None

    except Exception:
        return None


# ============================================================================
# DISCOVERY
# ============================================================================

def run_discovery() -> list[str]:

    print_header(
        "📚 RESEARCH DISCOVERY"
    )

    if discover_source_files is None:

        print(
            "❌ research_ingestion_engine "
            "import edilemedi:"
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

    # ------------------------------------------------------------------------
    # FIX:
    # discover_source_files() parametresiz.
    # ------------------------------------------------------------------------

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

    if not isinstance(sources, list):

        try:
            sources = list(sources)

        except TypeError:
            sources = []

    print(
        f"📂 Kaynak sayısı: "
        f"{len(sources)}"
    )

    discovered_ids: list[str] = []

    # KB'deki başlangıç durumu
    before_ids = set(
        get_kb_strategy_ids()
    )

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print()
        print(
            f"========== SOURCE "
            f"{index}/{len(sources)} =========="
        )

        print()

        try:

            # --------------------------------------------------------------
            # Source metadata
            # --------------------------------------------------------------

            source_name = None

            if isinstance(source, dict):

                source_name = (
                    source.get("name")
                    or source.get("source_name")
                    or source.get("filename")
                    or source.get("path")
                )

            else:

                source_name = getattr(
                    source,
                    "name",
                    None,
                )

            if source_name is None:
                source_name = str(source)

            print(
                f"📄 Kaynak: "
                f"{source_name}"
            )

            print(
                "   🧠 Strategy Discovery başlıyor..."
            )

            # --------------------------------------------------------------
            # Process source
            # --------------------------------------------------------------

            result = None

            try:

                result = process_source(
                    source
                )

            except TypeError:

                # Bazı eski sürümlerde path beklenebilir.
                try:

                    source_path = getattr(
                        source,
                        "path",
                        source,
                    )

                    result = process_source(
                        str(source_path)
                    )

                except Exception as inner_exc:

                    print(
                        "   ⚠️ Discovery "
                        "TypeError fallback başarısız:"
                    )

                    print(
                        f"      {type(inner_exc).__name__}: "
                        f"{inner_exc}"
                    )

            except Exception as exc:

                print(
                    "   ⚠️ Discovery kaynak hatası:"
                )

                print(
                    f"      {type(exc).__name__}: "
                    f"{exc}"
                )

            # --------------------------------------------------------------
            # Result'tan ID çıkar
            # --------------------------------------------------------------

            result_ids = extract_strategy_ids(
                result
            )

            for strategy_id in result_ids:

                if strategy_id not in discovered_ids:

                    discovered_ids.append(
                        strategy_id
                    )

            # --------------------------------------------------------------
            # KB'yi tekrar tara.
            # --------------------------------------------------------------

            after_ids = set(
                get_kb_strategy_ids()
            )

            new_ids = [
                strategy_id
                for strategy_id in after_ids
                if strategy_id not in before_ids
            ]

            for strategy_id in new_ids:

                if strategy_id not in discovered_ids:

                    discovered_ids.append(
                        strategy_id
                    )

            before_ids = after_ids

        except Exception as exc:

            print(
                f"❌ Source işlenemedi: "
                f"{type(exc).__name__}: {exc}"
            )

            traceback.print_exc()

    # ------------------------------------------------------------------------
    # FINAL KB SCAN
    # ------------------------------------------------------------------------

    final_ids = get_kb_strategy_ids()

    for strategy_id in final_ids:

        if strategy_id not in discovered_ids:

            discovered_ids.append(
                strategy_id
            )

    print_section(
        "📊 DISCOVERY SUMMARY"
    )

    print(
        f"Strategies Found : "
        f"{len(discovered_ids)}"
    )

    for strategy_id in discovered_ids:

        strategy = load_strategy(
            strategy_id
        )

        if strategy:

            name = (
                strategy.get("name")
                or strategy.get("strategy_name")
                or "UNKNOWN"
            )

            print(
                f"  • {strategy_id} | {name}"
            )

    print()
    print("SAFETY")

    print(
        f"Research Only     : "
        f"{RESEARCH_ONLY}"
    )

    print(
        f"Execution Enabled : "
        f"{EXECUTION_ENABLED}"
    )

    return discovered_ids


# ============================================================================
# UNIVERSE
# ============================================================================

def choose_universe(
    strategy: dict[str, Any],
) -> list[str]:

    symbols: list[str] = []

    possible_fields = [
        "symbols",
        "symbol",
        "tickers",
        "instruments",
    ]

    for field in possible_fields:

        value = strategy.get(field)

        if isinstance(value, str):

            candidate = normalize_symbol(
                value
            )

            if candidate:
                symbols.append(
                    candidate
                )

        elif isinstance(value, list):

            for item in value:

                candidate = normalize_symbol(
                    item
                )

                if candidate:
                    symbols.append(
                        candidate
                    )

    clean_symbols = []

    for symbol in symbols:

        if symbol not in clean_symbols:
            clean_symbols.append(symbol)

    if clean_symbols:
        return clean_symbols

    market = str(
        strategy.get(
            "market",
            "",
        )
    ).upper()

    if "BIST" in market:
        return BIST_RESEARCH_UNIVERSE.copy()

    if (
        "US" in market
        or "NASDAQ" in market
        or "NYSE" in market
    ):
        return US_RESEARCH_UNIVERSE.copy()

    return COMBINED_RESEARCH_UNIVERSE.copy()


# ============================================================================
# HISTORY
# ============================================================================

def load_history(
    symbol: str,
    period: str,
) -> pd.DataFrame:

    symbol = normalize_symbol(
        symbol
    )

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

                data = get_history(
                    **kwargs
                )

                if isinstance(
                    data,
                    pd.DataFrame,
                ):

                    return normalize_history(
                        data
                    )

            except TypeError:
                continue

            except Exception:
                continue

    # ------------------------------------------------------------------------
    # yfinance fallback
    # ------------------------------------------------------------------------

    try:

        import yfinance as yf

        data = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

        return normalize_history(
            data
        )

    except Exception as exc:

        print(
            f"   ❌ History alınamadı "
            f"{symbol}: {exc}"
        )

        return pd.DataFrame()


def normalize_history(
    data: pd.DataFrame,
) -> pd.DataFrame:

    if data is None:
        return pd.DataFrame()

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

        flattened = []

        for column in result.columns:

            if isinstance(
                column,
                tuple,
            ):

                flattened.append(
                    str(column[0])
                )

            else:

                flattened.append(
                    str(column)
                )

        result.columns = flattened

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

        elif name == "adj close":
            rename_map[column] = "Adj Close"

        elif name == "volume":
            rename_map[column] = "Volume"

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


# ============================================================================
# PARAMETER GRID
# ============================================================================

def build_parameter_candidates() -> list[
    dict[str, Any]
]:

    candidates = []

    for sma_fast in SMA_FAST_VALUES:

        for sma_slow in SMA_SLOW_VALUES:

            for ema_fast in EMA_FAST_VALUES:

                for ema_slow in EMA_SLOW_VALUES:

                    for rsi_period in RSI_PERIOD_VALUES:

                        for rsi_oversold in (
                            RSI_OVERSOLD_VALUES
                        ):

                            for rsi_overbought in (
                                RSI_OVERBOUGHT_VALUES
                            ):

                                for stop_atr in (
                                    STOP_ATR_VALUES
                                ):

                                    for target_atr in (
                                        TARGET_ATR_VALUES
                                    ):

                                        if (
                                            sma_fast
                                            >=
                                            sma_slow
                                        ):
                                            continue

                                        if (
                                            ema_fast
                                            >=
                                            ema_slow
                                        ):
                                            continue

                                        if (
                                            rsi_oversold
                                            >=
                                            rsi_overbought
                                        ):
                                            continue

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
        "sma_fast": candidate["sma_fast"],
        "sma_slow": candidate["sma_slow"],
        "ema_fast": candidate["ema_fast"],
        "ema_slow": candidate["ema_slow"],
        "rsi_period": candidate["rsi_period"],
        "rsi_oversold": candidate["rsi_oversold"],
        "rsi_overbought": candidate["rsi_overbought"],
        "buy_threshold": 3,
        "sell_threshold": -3,
    }


def build_backtest_config(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    return {
        "initial_capital": 100000,
        "position_size_percent": 10.0,
        "commission_percent": 0.10,
        "slippage_percent": 0.05,
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
) -> dict[str, Any]:

    if run_backtest is None:

        return {
            "status": "ERROR",
            "error": (
                "backtest_engine import error: "
                f"{BACKTEST_IMPORT_ERROR}"
            ),
        }

    if data.empty:

        return {
            "status": "INCONCLUSIVE",
            "trades": 0,
        }

    signal_config = build_signal_config(
        candidate
    )

    backtest_config = build_backtest_config(
        candidate
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

    # Backtest Engine V3 şeması:
    # result["trades"] = trade listesi
    # result["metrics"] = hesaplanmış metrikler
    #
    # V4.2 burada result["trades"] değerini integer gibi okuyordu.
    # O alan liste olduğu için safe_int(list) -> 0 oluyordu ve
    # 384 adayın tamamı yanlışlıkla MIN_TRAIN_TRADES filtresinden eleniyordu.

    metrics = result.get("metrics")

    if not isinstance(metrics, dict):
        metrics = {}

    trade_list = result.get("trades")

    if isinstance(trade_list, list):
        trade_count_fallback = len(trade_list)
    else:
        trade_count_fallback = 0

    trades = safe_int(
        metrics.get(
            "total_trades",
            trade_count_fallback,
        ),
        trade_count_fallback,
    )

    wins = safe_int(
        metrics.get(
            "winning_trades",
            0,
        ),
        0,
    )

    losses = safe_int(
        metrics.get(
            "losing_trades",
            0,
        ),
        0,
    )

    win_rate = safe_float(
        metrics.get(
            "win_rate_percent",
            0.0,
        ),
        0.0,
    )

    profit_factor = safe_float(
        metrics.get(
            "profit_factor",
            0.0,
        ),
        0.0,
    )

    total_pnl = safe_float(
        metrics.get(
            "net_pnl",
            0.0,
        ),
        0.0,
    )

    return_pct = safe_float(
        metrics.get(
            "total_return_percent",
            0.0,
        ),
        0.0,
    )

    max_drawdown = safe_float(
        metrics.get(
            "max_drawdown_percent",
            0.0,
        ),
        0.0,
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
# FAST SCREEN
# ============================================================================

def fast_screen(
    data: pd.DataFrame,
    symbol: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    print_section(
        f"⚡ FAST SCREEN: {symbol}"
    )

    print(
        f"   Aday sayısı: "
        f"{len(candidates)}"
    )

    results = []

    total = len(candidates)
    screen_errors = 0
    below_min_trade = 0
    best_seen_trades = 0

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        result = execute_backtest(
            data=data,
            symbol=symbol,
            candidate=candidate,
        )

        if result.get("status") == "ERROR":
            screen_errors += 1
            continue

        metrics = extract_metrics(
            result
        )

        best_seen_trades = max(
            best_seen_trades,
            metrics["trades"],
        )

        if (
            metrics["trades"]
            < MIN_TRAIN_TRADES
        ):
            below_min_trade += 1
            continue

        results.append(
            {
                "candidate": candidate,
                "metrics": metrics,
            }
        )

        if (
            index == 1
            or index % 50 == 0
            or index == total
        ):

            print(
                f"   Progress: "
                f"{index}/{total}"
            )

    results.sort(
        key=lambda item: (
            item["metrics"][
                "return_pct"
            ],
            item["metrics"][
                "profit_factor"
            ],
            -item["metrics"][
                "max_drawdown"
            ],
        ),
        reverse=True,
    )

    print(
        f"   Screen sonucu       : {len(results)} aday"
    )
    print(
        f"   < {MIN_TRAIN_TRADES} trade       : "
        f"{below_min_trade}"
    )
    print(
        f"   Backtest error      : "
        f"{screen_errors}"
    )
    print(
        f"   En yüksek trade     : "
        f"{best_seen_trades}"
    )

    return results


# ============================================================================
# WALK FORWARD
# ============================================================================

def run_walk_forward(
    data: pd.DataFrame,
    symbol: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:

    print_section(
        f"🔬 WALK-FORWARD: {symbol}"
    )

    if len(data) < (
        TRAIN_BARS
        + VALIDATION_BARS
    ):

        return {
            "status": "INCONCLUSIVE",
            "folds": [],
        }

    folds = []

    start = 0
    fold_number = 0

    while (
        start
        + TRAIN_BARS
        + VALIDATION_BARS
        <= len(data)
    ):

        fold_number += 1

        train_end = (
            start
            + TRAIN_BARS
        )

        validation_end = (
            train_end
            + VALIDATION_BARS
        )

        train = data.iloc[
            start:train_end
        ].copy()

        validation = data.iloc[
            train_end:validation_end
        ].copy()

        print()
        print(
            f"   Fold {fold_number}"
        )

        print(
            f"   Train      : "
            f"{len(train)} bars"
        )

        print(
            f"   Validation : "
            f"{len(validation)} bars"
        )

        # ------------------------------------------------------------------
        # TRAIN SCREEN
        # ------------------------------------------------------------------

        screen_results = fast_screen(
            train,
            symbol,
            candidates,
        )

        top_candidates = screen_results[
            :TOP_WFO_CANDIDATES
        ]

        if not top_candidates:

            folds.append(
                {
                    "fold": fold_number,
                    "status": (
                        "NO_TRAIN_CANDIDATE"
                    ),
                    "train_trades": 0,
                    "validation_trades": 0,
                }
            )

            start += STEP_BARS
            continue

        # ------------------------------------------------------------------
        # VALIDATION
        # ------------------------------------------------------------------

        validation_results = []

        for item in top_candidates:

            candidate = item[
                "candidate"
            ]

            result = execute_backtest(
                data=validation,
                symbol=symbol,
                candidate=candidate,
            )

            metrics = extract_metrics(
                result
            )

            validation_results.append(
                {
                    "candidate": candidate,
                    "train_metrics": item[
                        "metrics"
                    ],
                    "validation_metrics": metrics,
                }
            )

        validation_results.sort(
            key=lambda item: (
                item[
                    "validation_metrics"
                ]["return_pct"],
                item[
                    "validation_metrics"
                ]["profit_factor"],
            ),
            reverse=True,
        )

        best = (
            validation_results[0]
            if validation_results
            else None
        )

        if best is None:

            folds.append(
                {
                    "fold": fold_number,
                    "status": (
                        "NO_VALIDATION_RESULT"
                    ),
                    "train_trades": 0,
                    "validation_trades": 0,
                }
            )

        else:

            validation_metrics = best[
                "validation_metrics"
            ]

            if (
                validation_metrics["trades"]
                < MIN_VALIDATION_TRADES
            ):

                fold_status = (
                    "INCONCLUSIVE"
                )

            elif (
                validation_metrics[
                    "return_pct"
                ]
                > 0
                and validation_metrics[
                    "profit_factor"
                ]
                > 1
            ):

                fold_status = "POSITIVE"

            else:

                fold_status = "NEGATIVE"

            folds.append(
                {
                    "fold": fold_number,
                    "status": fold_status,
                    "train_metrics": best[
                        "train_metrics"
                    ],
                    "validation_metrics": (
                        validation_metrics
                    ),
                    "candidate": best[
                        "candidate"
                    ],
                }
            )

            print(
                f"   Result     : "
                f"{fold_status}"
            )

            print(
                f"   Trades     : "
                f"{validation_metrics['trades']}"
            )

            print(
                f"   Return     : "
                f"{validation_metrics['return_pct']:.2f}%"
            )

            print(
                f"   PF         : "
                f"{validation_metrics['profit_factor']:.3f}"
            )

        start += STEP_BARS

    # ------------------------------------------------------------------------
    # WFO SUMMARY
    # ------------------------------------------------------------------------

    positive = sum(
        1
        for fold in folds
        if fold.get("status")
        == "POSITIVE"
    )

    negative = sum(
        1
        for fold in folds
        if fold.get("status")
        == "NEGATIVE"
    )

    inconclusive = sum(
        1
        for fold in folds
        if fold.get("status")
        == "INCONCLUSIVE"
    )

    validation_returns = []
    validation_pnls = []
    validation_trades = []
    validation_wins = []
    validation_losses = []

    for fold in folds:

        metrics = fold.get(
            "validation_metrics"
        )

        if not metrics:
            continue

        validation_returns.append(
            metrics["return_pct"]
        )

        validation_pnls.append(
            metrics["total_pnl"]
        )

        validation_trades.append(
            metrics["trades"]
        )

        validation_wins.append(
            metrics["wins"]
        )

        validation_losses.append(
            metrics["losses"]
        )

    total_trades = sum(
        validation_trades
    )

    total_wins = sum(
        validation_wins
    )

    total_losses = sum(
        validation_losses
    )

    aggregate_win_rate = (
        total_wins
        / total_trades
        * 100
        if total_trades
        else 0.0
    )

    average_return = (
        sum(validation_returns)
        / len(validation_returns)
        if validation_returns
        else 0.0
    )

    total_pnl = sum(
        validation_pnls
    )

    return {
        "status": "DONE",
        "fold_count": len(folds),
        "positive_folds": positive,
        "negative_folds": negative,
        "inconclusive_folds": inconclusive,
        "validation_trades": total_trades,
        "validation_wins": total_wins,
        "validation_losses": total_losses,
        "aggregate_win_rate": (
            aggregate_win_rate
        ),
        "average_fold_return": (
            average_return
        ),
        "total_validation_pnl": (
            total_pnl
        ),
        "folds": folds,
    }


# ============================================================================
# VALIDATION ENGINE
# ============================================================================

def run_validation(
    strategy_id: str,
) -> dict[str, Any]:

    print_section(
        "🧪 STRATEGY VALIDATION"
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
# RANKING
# ============================================================================

def calculate_rank_score(
    backtest_metrics: list[
        dict[str, Any]
    ],
    wfo_results: list[
        dict[str, Any]
    ],
) -> float:

    if not backtest_metrics:
        return 0.0

    returns = [
        safe_float(
            item.get(
                "return_pct"
            )
        )
        for item in backtest_metrics
    ]

    pfs = [
        safe_float(
            item.get(
                "profit_factor"
            )
        )
        for item in backtest_metrics
    ]

    dds = [
        safe_float(
            item.get(
                "max_drawdown"
            )
        )
        for item in backtest_metrics
    ]

    avg_return = (
        sum(returns)
        / len(returns)
        if returns
        else 0.0
    )

    avg_pf = (
        sum(pfs)
        / len(pfs)
        if pfs
        else 0.0
    )

    avg_dd = (
        sum(dds)
        / len(dds)
        if dds
        else 0.0
    )

    wfo_returns = []

    for item in wfo_results:

        value = item.get(
            "average_fold_return"
        )

        if value is not None:

            wfo_returns.append(
                safe_float(value)
            )

    avg_wfo_return = (
        sum(wfo_returns)
        / len(wfo_returns)
        if wfo_returns
        else 0.0
    )

    score = (
        avg_return * 2.0
        + avg_wfo_return * 3.0
        + (avg_pf - 1.0) * 2.0
        - avg_dd * 0.5
    )

    return safe_float(
        score
    )


# ============================================================================
# PIPELINE
# ============================================================================

def run_pipeline() -> int:

    started_at = utc_now()

    print_header(
        f"🧠 MARKET HQ STRATEGY RESEARCH "
        f"PIPELINE {PIPELINE_VERSION}"
    )

    print(
        "Flow:"
    )

    print(
        "Sources → Discovery → KB → Backtest → "
        "WFO → Validation → Ranking"
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

    # ========================================================================
    # 1. DISCOVERY
    # ========================================================================

    strategy_ids = run_discovery()

    if not strategy_ids:

        print()

        print(
            "❌ Discovery sonrası KB'de "
            "strateji bulunamadı."
        )

        print(
            "Pipeline durduruldu."
        )

        return 1

    print()

    print(
        f"🧠 Discovery sonrası strateji sayısı: "
        f"{len(strategy_ids)}"
    )

    # ========================================================================
    # 2. GRID
    # ========================================================================

    candidates = (
        build_parameter_candidates()
    )

    print_section(
        "⚙️ STRATEGY CANDIDATE GRID"
    )

    print(
        f"⚡ Aday havuzu: "
        f"{len(candidates)}"
    )

    # ========================================================================
    # 3. STRATEGIES
    # ========================================================================

    pipeline_results = []

    for strategy_index, strategy_id in enumerate(
        strategy_ids,
        start=1,
    ):

        print_header(
            f"STRATEGY "
            f"{strategy_index}/"
            f"{len(strategy_ids)}"
        )

        strategy = load_strategy(
            strategy_id
        )

        if strategy is None:

            print(
                f"❌ Strategy KB'den okunamadı: "
                f"{strategy_id}"
            )

            continue

        strategy_name = (
            strategy.get("name")
            or strategy.get("strategy_name")
            or strategy_id
        )

        print(
            f"Strategy ID : "
            f"{strategy_id}"
        )

        print(
            f"Strategy    : "
            f"{strategy_name}"
        )

        print(
            f"Market      : "
            f"{strategy.get('market', 'UNKNOWN')}"
        )

        universe = choose_universe(
            strategy
        )

        print()

        print(
            f"🌍 Test universe: "
            f"{len(universe)} symbols"
        )

        print(
            ", ".join(universe)
        )

        strategy_backtests = []
        strategy_wfo = []

        # ====================================================================
        # SYMBOLS
        # ====================================================================

        for symbol_index, symbol in enumerate(
            universe,
            start=1,
        ):

            print()

            print(
                "=" * 70
            )

            print(
                f"📈 BACKTEST "
                f"{symbol_index}/"
                f"{len(universe)}"
            )

            print(
                f"Symbol: {symbol}"
            )

            print(
                f"Period: "
                f"{BACKTEST_PERIOD}"
            )

            data = load_history(
                symbol,
                BACKTEST_PERIOD,
            )

            if data.empty:

                print(
                    "   ⚠️ Veri yok."
                )

                strategy_backtests.append(
                    {
                        "symbol": symbol,
                        "status": (
                            "INCONCLUSIVE"
                        ),
                        "metrics": {},
                    }
                )

                continue

            print(
                f"   Bars: "
                f"{len(data)}"
            )

            # ----------------------------------------------------------------
            # FAST SCREEN
            # ----------------------------------------------------------------

            screen = fast_screen(
                data,
                symbol,
                candidates,
            )

            if not screen:

                print(
                    "   ⚠️ Yeterli trade "
                    "üreten aday yok."
                )

                strategy_backtests.append(
                    {
                        "symbol": symbol,
                        "status": (
                            "INCONCLUSIVE"
                        ),
                        "metrics": {},
                    }
                )

            else:

                best = screen[0]

                best_metrics = best[
                    "metrics"
                ]

                print()

                print(
                    "   🏆 BEST FAST CANDIDATE"
                )

                print(
                    f"   Trades : "
                    f"{best_metrics['trades']}"
                )

                print(
                    f"   WinRate: "
                    f"{best_metrics['win_rate']:.2f}%"
                )

                print(
                    f"   PF     : "
                    f"{best_metrics['profit_factor']:.3f}"
                )

                print(
                    f"   Return : "
                    f"{best_metrics['return_pct']:.2f}%"
                )

                print(
                    f"   DD     : "
                    f"{best_metrics['max_drawdown']:.2f}%"
                )

                strategy_backtests.append(
                    {
                        "symbol": symbol,
                        "status": "DONE",
                        "metrics": best_metrics,
                        "candidate": best[
                            "candidate"
                        ],
                    }
                )

            # ----------------------------------------------------------------
            # WFO
            # ----------------------------------------------------------------

            print()

            print(
                f"🔬 WFO verisi alınıyor: "
                f"{symbol}"
            )

            wfo_data = load_history(
                symbol,
                WFO_PERIOD,
            )

            if wfo_data.empty:

                print(
                    "   ⚠️ WFO verisi yok."
                )

            else:

                print(
                    f"   WFO bars: "
                    f"{len(wfo_data)}"
                )

                wfo = run_walk_forward(
                    wfo_data,
                    symbol,
                    candidates,
                )

                wfo["symbol"] = symbol

                strategy_wfo.append(
                    wfo
                )

        # ====================================================================
        # STRATEGY SUMMARY
        # ====================================================================

        print_header(
            f"📊 STRATEGY SUMMARY: "
            f"{strategy_name}"
        )

        completed = [
            item
            for item in strategy_backtests
            if item.get("status")
            == "DONE"
        ]

        positive_backtests = 0
        negative_backtests = 0

        for item in completed:

            metrics = item.get(
                "metrics",
                {},
            )

            if (
                safe_float(
                    metrics.get(
                        "return_pct"
                    )
                )
                > 0
            ):

                positive_backtests += 1

            else:

                negative_backtests += 1

        backtest_metrics = [
            item.get(
                "metrics",
                {},
            )
            for item in completed
        ]

        positive_wfo = sum(
            safe_int(
                item.get(
                    "positive_folds"
                )
            )
            for item in strategy_wfo
        )

        negative_wfo = sum(
            safe_int(
                item.get(
                    "negative_folds"
                )
            )
            for item in strategy_wfo
        )

        inconclusive_wfo = sum(
            safe_int(
                item.get(
                    "inconclusive_folds"
                )
            )
            for item in strategy_wfo
        )

        rank_score = calculate_rank_score(
            backtest_metrics,
            strategy_wfo,
        )

        # --------------------------------------------------------------------
        # CLASSIFICATION
        # --------------------------------------------------------------------

        if not completed:

            classification = "NO_DATA"

        elif (
            positive_backtests
            >= max(
                1,
                len(completed) // 2,
            )
            and positive_wfo
            > negative_wfo
        ):

            classification = "PROMISING"

        elif (
            positive_backtests > 0
            or positive_wfo > 0
        ):

            classification = "MIXED"

        else:

            classification = "WEAK"

        print(
            f"Backtest symbols : "
            f"{len(completed)}"
        )

        print(
            f"Positive         : "
            f"{positive_backtests}"
        )

        print(
            f"Negative         : "
            f"{negative_backtests}"
        )

        print(
            f"WFO positive     : "
            f"{positive_wfo}"
        )

        print(
            f"WFO negative     : "
            f"{negative_wfo}"
        )

        print(
            f"WFO inconclusive : "
            f"{inconclusive_wfo}"
        )

        print(
            f"Ranking Score     : "
            f"{rank_score:.4f}"
        )

        print(
            f"Classification    : "
            f"{classification}"
        )

        # ====================================================================
        # VALIDATION
        # ====================================================================

        validation = run_validation(
            strategy_id
        )

        # ====================================================================
        # STRATEGY RESULT
        # ====================================================================

        strategy_result = {
            "pipeline_version": PIPELINE_VERSION,
            "timestamp": utc_now().isoformat(),
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy": strategy,
            "research_only": RESEARCH_ONLY,
            "execution_enabled": EXECUTION_ENABLED,
            "candidate_count": len(candidates),
            "universe": universe,
            "backtest_period": BACKTEST_PERIOD,
            "wfo_period": WFO_PERIOD,
            "wfo_config": {
                "train_bars": TRAIN_BARS,
                "validation_bars": VALIDATION_BARS,
                "step_bars": STEP_BARS,
                "top_candidates": TOP_WFO_CANDIDATES,
            },
            "backtests": strategy_backtests,
            "walk_forward": strategy_wfo,
            "validation": validation,
            "ranking": {
                "score": rank_score,
                "classification": classification,
                "positive_backtests": (
                    positive_backtests
                ),
                "negative_backtests": (
                    negative_backtests
                ),
                "positive_wfo_folds": (
                    positive_wfo
                ),
                "negative_wfo_folds": (
                    negative_wfo
                ),
                "inconclusive_wfo_folds": (
                    inconclusive_wfo
                ),
            },
        }

        pipeline_results.append(
            strategy_result
        )

        output_path = (
            RESULT_DIR
            / (
                "strategy_pipeline_v4_2_"
                f"{strategy_id}_"
                f"{utc_timestamp()}.json"
            )
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                strategy_result,
                file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print()

        print(
            "💾 Strategy result saved:"
        )

        print(
            str(output_path)
        )

    # ========================================================================
    # FINAL RANKING
    # ========================================================================

    print_header(
        "🏆 FINAL STRATEGY RANKING"
    )

    pipeline_results.sort(
        key=lambda item: safe_float(
            (
                item.get("ranking")
                or {}
            ).get("score")
        ),
        reverse=True,
    )

    for index, item in enumerate(
        pipeline_results,
        start=1,
    ):

        ranking = item.get(
            "ranking",
            {},
        )

        print(
            f"{index:>2}. "
            f"{item.get('strategy_id')} | "
            f"{item.get('strategy_name')} | "
            f"Score="
            f"{safe_float(ranking.get('score')):.4f} | "
            f"{ranking.get('classification')}"
        )

    # ========================================================================
    # MASTER RESULT
    # ========================================================================

    finished_at = utc_now()

    master_result = {
        "pipeline_version": PIPELINE_VERSION,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "research_only": RESEARCH_ONLY,
        "execution_enabled": EXECUTION_ENABLED,
        "candidate_count": len(candidates),
        "strategy_count": len(
            pipeline_results
        ),
        "strategies": pipeline_results,
    }

    master_path = (
        RESULT_DIR
        / (
            "strategy_pipeline_v4_2_"
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

    # ========================================================================
    # FINAL
    # ========================================================================

    print()

    print(
        "=" * 78
    )

    print(
        "✅ MARKET HQ RESEARCH PIPELINE TAMAMLANDI"
    )

    print(
        "=" * 78
    )

    print(
        f"Strategy count : "
        f"{len(pipeline_results)}"
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
# V4.3 COMPATIBILITY CHECK
# ============================================================================

def run_compatibility_check() -> bool:
    """
    Pipeline ile Backtest Engine V3 arasındaki veri sözleşmesini
    küçük bir THYAO testiyle doğrular.

    Yalnızca araştırma/backtest çalıştırır.
    Gerçek emir göndermez.
    """
    print_header("🔧 PIPELINE / BACKTEST COMPATIBILITY CHECK")

    if run_backtest is None:
        print("❌ Backtest Engine import edilemedi.")
        print(f"   {BACKTEST_IMPORT_ERROR}")
        return False

    data = load_history(
        "THYAO.IS",
        "1y",
    )

    if data.empty:
        print("⚠️ THYAO.IS verisi alınamadı.")
        return False

    candidates = build_parameter_candidates()

    if not candidates:
        print("❌ Candidate grid boş.")
        return False

    candidate = candidates[0]

    result = execute_backtest(
        data=data,
        symbol="THYAO.IS",
        candidate=candidate,
    )

    if result.get("status") == "ERROR":
        print("❌ Compatibility backtest hatası:")
        print(f"   {result.get('error')}")
        return False

    metrics = extract_metrics(result)

    print(f"   Candidate count : {len(candidates)}")
    print(f"   THYAO bars      : {len(data)}")
    print(f"   Parsed trades   : {metrics['trades']}")
    print(f"   Parsed win rate : {metrics['win_rate']:.2f}%")
    print(f"   Parsed PF       : {metrics['profit_factor']:.3f}")
    print(f"   Parsed return   : {metrics['return_pct']:.2f}%")

    if not isinstance(result.get("trades"), list):
        print("❌ result['trades'] list değil.")
        return False

    if not isinstance(result.get("metrics"), dict):
        print("❌ result['metrics'] dict değil.")
        return False

    print("✅ Pipeline ↔ Backtest veri sözleşmesi OK.")
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":

    try:

        if not run_compatibility_check():
            print()
            print(
                "⛔ Compatibility check başarısız; "
                "pipeline başlatılmadı."
            )
            raise SystemExit(1)

        raise SystemExit(
            run_pipeline()
        )

    except KeyboardInterrupt:

        print()
        print(
            "⛔ Pipeline kullanıcı tarafından "
            "durduruldu."
        )

        raise SystemExit(130)

    except Exception as exc:

        print()
        print(
            "❌ PIPELINE ERROR"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        traceback.print_exc()

        raise SystemExit(1)


