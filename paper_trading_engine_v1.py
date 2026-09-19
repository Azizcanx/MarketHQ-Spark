"""
MarketHQ Paper Trading Engine V1.3
=================================

Research-only historical paper trading.

Pipeline
--------
Strategy Selection V2
        ↓
Paper Trading Engine V1.3
        ↓
Virtual positions / equity / trade journal
        ↓
Future TradingView research adapter

SAFETY
------
This module NEVER places real orders and NEVER connects to a broker.
It is strictly for historical paper simulation / research.

Verified APIs used by this file
--------------------------------
agents.market_data_agent:
    get_bist_history(period='1y', interval='1d')
    get_us_history(period='1y', interval='1d')

signal_engine:
    DEFAULT_CONFIG
    generate_signal(data, config=None)
    generate_signal_history(data, config=None)

Important V1.3 correction
-------------------------
Signal parameters and risk parameters are now strictly separated.

Signal Engine config:
    SMA / EMA / RSI / MACD / Bollinger / ATR / Volume / thresholds

Paper Trading risk config:
    stop_atr_multiple
    target_atr_multiple
    max_holding_bars

Therefore stop/target values can NEVER accidentally be inserted into
the Signal Engine config.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agents.market_data_agent import (
    get_bist_history,
    get_us_history,
)
from signal_engine import (
    DEFAULT_CONFIG,
    generate_signal,
    generate_signal_history,
)


PROJECT_ROOT = Path(__file__).resolve().parent

SELECTION_DIR = PROJECT_ROOT / "strategy_selection_results"
RESULTS_DIR = PROJECT_ROOT / "paper_trading_results"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

INITIAL_CAPITAL = 100_000.0
POSITION_SIZE_PERCENT = 10.0
COMMISSION_PERCENT = 0.10
SLIPPAGE_PERCENT = 0.05

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"

# ---------------------------------------------------------------------------
# STRICT PARAMETER SEPARATION
# ---------------------------------------------------------------------------

SIGNAL_CONFIG_KEYS = {
    "sma_fast",
    "sma_slow",
    "ema_fast",
    "ema_slow",
    "rsi_period",
    "macd_fast",
    "macd_slow",
    "macd_signal",
    "bollinger_period",
    "bollinger_std",
    "atr_period",
    "volume_period",
    "buy_threshold",
    "sell_threshold",
    "rsi_oversold",
    "rsi_overbought",
    "minimum_volume_ratio",
}

RISK_CONFIG_KEYS = {
    "stop_atr_multiple",
    "target_atr_multiple",
    "stop_loss_atr_multiple",
    "take_profit_atr_multiple",
    "max_holding_bars",
}

# Common compact parameter names used by MarketHQ strategy records, e.g.
# sma_fast10, sma_slow100, ema_fast20, rsi_period14.
COMPACT_PARAMETER_PREFIXES = {
    "sma_fast": "sma_fast",
    "sma_slow": "sma_slow",
    "ema_fast": "ema_fast",
    "ema_slow": "ema_slow",
    "rsi_period": "rsi_period",
    "macd_fast": "macd_fast",
    "macd_slow": "macd_slow",
    "macd_signal": "macd_signal",
    "bollinger_period": "bollinger_period",
    "bollinger_std": "bollinger_std",
    "atr_period": "atr_period",
    "volume_period": "volume_period",
    "buy_threshold": "buy_threshold",
    "sell_threshold": "sell_threshold",
    "rsi_oversold": "rsi_oversold",
    "rsi_overbought": "rsi_overbought",
    "minimum_volume_ratio": "minimum_volume_ratio",
}


@dataclass
class Position:
    side: str
    quantity: float
    entry_price: float
    entry_bar: int
    entry_time: str
    entry_commission: float
    stop_price: float | None
    target_price: float | None


@dataclass
class Trade:
    trade_id: int
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    entry_commission: float
    exit_commission: float
    slippage_cost: float
    net_pnl: float
    bars_held: int
    exit_reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def normalize_columns(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    rename_map: dict[Any, str] = {}

    for column in result.columns:
        text = str(column).strip()
        upper = text.upper()

        if upper in {"DATE", "DATETIME", "TIMESTAMP"}:
            rename_map[column] = "Datetime"
        elif upper == "OPEN":
            rename_map[column] = "Open"
        elif upper == "HIGH":
            rename_map[column] = "High"
        elif upper == "LOW":
            rename_map[column] = "Low"
        elif upper == "CLOSE":
            rename_map[column] = "Close"
        elif upper in {"ADJ CLOSE", "ADJ_CLOSE"}:
            rename_map[column] = "Adj Close"
        elif upper == "VOLUME":
            rename_map[column] = "Volume"

    result = result.rename(columns=rename_map)

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [
        column
        for column in required
        if column not in result.columns
    ]

    if missing:
        raise ValueError(
            "Market history is missing required columns: "
            f"{missing}. Received: {list(result.columns)}"
        )

    if "Datetime" in result.columns:
        result["Datetime"] = pd.to_datetime(
            result["Datetime"],
            errors="coerce",
        )
        result = result.dropna(
            subset=["Datetime"]
        )
        result = result.set_index("Datetime")

    result.index = pd.to_datetime(
        result.index,
        errors="coerce",
    )

    result = result[
        ~result.index.isna()
    ]

    for column in required:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=required
    )

    result = result.sort_index()

    return result


def extract_symbol_history(
    raw: Any,
    symbol: str,
) -> pd.DataFrame | None:
    if isinstance(raw, pd.DataFrame):
        return raw.copy()

    if isinstance(raw, dict):
        if (
            symbol in raw
            and isinstance(
                raw[symbol],
                pd.DataFrame,
            )
        ):
            return raw[symbol].copy()

        target = (
            symbol.upper()
            .replace("-", "")
        )

        for key, value in raw.items():
            if not isinstance(
                value,
                pd.DataFrame,
            ):
                continue

            normalized_key = (
                str(key)
                .upper()
                .replace("-", "")
            )

            if normalized_key == target:
                return value.copy()

        for key in (
            "data",
            "history",
            "prices",
            "results",
        ):
            value = raw.get(key)

            if isinstance(
                value,
                pd.DataFrame,
            ):
                return value.copy()

            if isinstance(value, dict):
                nested = extract_symbol_history(
                    value,
                    symbol,
                )

                if nested is not None:
                    return nested

    if isinstance(
        raw,
        (list, tuple),
    ):
        for item in raw:
            if not isinstance(
                item,
                pd.DataFrame,
            ):
                continue

            columns_text = " ".join(
                str(column).upper()
                for column in item.columns
            )

            if "CLOSE" in columns_text:
                return item.copy()

    return None


def load_history(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    if symbol.upper().endswith(".IS"):
        raw = get_bist_history(
            period=period,
            interval=interval,
        )
    else:
        raw = get_us_history(
            period=period,
            interval=interval,
        )

    history = extract_symbol_history(
        raw,
        symbol,
    )

    if history is None:
        raise ValueError(
            f"Could not find historical data for {symbol}. "
            f"Loader returned: {type(raw).__name__}"
        )

    history = normalize_columns(history)

    if len(history) < 60:
        raise ValueError(
            f"Only {len(history)} bars found for {symbol}. "
            "At least 60 bars are required."
        )

    return history


def recursively_find_dicts(
    value: Any,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        found.append(value)

        for child in value.values():
            found.extend(
                recursively_find_dicts(child)
            )

    elif isinstance(value, list):
        for child in value:
            found.extend(
                recursively_find_dicts(child)
            )

    return found


def try_numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        number = float(value)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError):
        return None

    return None


def extract_parameters(
    strategy: dict[str, Any],
) -> dict[str, float]:
    """
    Extract numeric parameters from the entire selected strategy record.

    Supports both:
        sma_fast: 10

    and compact strategy names/keys such as:
        sma_fast10
        sma_slow100
        ema_fast20
        rsi_period14

    Risk keys are intentionally also collected here, then separated by
    normalize_strategy_parameters().
    """

    parameters: dict[str, float] = {}

    dictionaries = recursively_find_dicts(
        strategy
    )

    for dictionary in dictionaries:
        for raw_key, raw_value in dictionary.items():
            key = (
                str(raw_key)
                .strip()
                .lower()
            )

            numeric_value = try_numeric(
                raw_value
            )

            if numeric_value is not None:
                parameters[key] = numeric_value

            # Parse compact parameter names.
            for prefix, canonical in (
                COMPACT_PARAMETER_PREFIXES.items()
            ):
                if key == prefix:
                    continue

                match = re.fullmatch(
                    rf"{re.escape(prefix)}"
                    r"[_-]?(\d+(?:\.\d+)?)",
                    key,
                )

                if match:
                    parameters[canonical] = (
                        float(match.group(1))
                    )

    return parameters


def normalize_strategy_parameters(
    strategy: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, float],
]:
    """
    Build two completely independent dictionaries.

    signal_config:
        ONLY keys present in SIGNAL_CONFIG_KEYS and DEFAULT_CONFIG.

    risk_config:
        ONLY keys present in RISK_CONFIG_KEYS.

    This is the central V1.3 fix.
    """

    # Start only from DEFAULT_CONFIG keys that are known to be signal
    # configuration keys. Even if DEFAULT_CONFIG grows later, a risk
    # parameter cannot leak into this dictionary.
    signal_config: dict[str, Any] = {
        key: value
        for key, value in DEFAULT_CONFIG.items()
        if key in SIGNAL_CONFIG_KEYS
    }

    risk_config: dict[str, float] = {
        "stop_atr_multiple": 2.0,
        "target_atr_multiple": 3.0,
    }

    parameters = extract_parameters(
        strategy
    )

    # Exact signal parameters.
    for key in SIGNAL_CONFIG_KEYS:
        if key not in parameters:
            continue

        value = parameters[key]

        if key in signal_config:
            default_value = signal_config[key]

            if isinstance(
                default_value,
                int,
            ):
                signal_config[key] = int(
                    value
                )
            else:
                signal_config[key] = value

    # Risk parameters are handled separately.
    if "stop_atr_multiple" in parameters:
        risk_config[
            "stop_atr_multiple"
        ] = parameters[
            "stop_atr_multiple"
        ]
    elif (
        "stop_loss_atr_multiple"
        in parameters
    ):
        risk_config[
            "stop_atr_multiple"
        ] = parameters[
            "stop_loss_atr_multiple"
        ]

    if "target_atr_multiple" in parameters:
        risk_config[
            "target_atr_multiple"
        ] = parameters[
            "target_atr_multiple"
        ]
    elif (
        "take_profit_atr_multiple"
        in parameters
    ):
        risk_config[
            "target_atr_multiple"
        ] = parameters[
            "take_profit_atr_multiple"
        ]

    if "max_holding_bars" in parameters:
        risk_config[
            "max_holding_bars"
        ] = parameters[
            "max_holding_bars"
        ]

    # Hard safety assertion: these keys may NEVER appear in signal config.
    leaked_risk_keys = (
        set(signal_config)
        & RISK_CONFIG_KEYS
    )

    if leaked_risk_keys:
        raise RuntimeError(
            "Parameter separation failure. "
            f"Risk keys leaked into Signal config: "
            f"{sorted(leaked_risk_keys)}"
        )

    return (
        signal_config,
        risk_config,
    )


def get_strategy_id(
    strategy: dict[str, Any],
) -> str:
    for key in (
        "strategy_id",
        "id",
    ):
        value = strategy.get(key)

        if value:
            return str(value)

    for dictionary in recursively_find_dicts(
        strategy
    ):
        for key in (
            "strategy_id",
            "id",
        ):
            value = dictionary.get(key)

            if value:
                return str(value)

    return "UNKNOWN"


def get_strategy_name(
    strategy: dict[str, Any],
) -> str:
    for key in (
        "strategy_name",
        "name",
        "title",
    ):
        value = strategy.get(key)

        if value:
            return str(value)

    for dictionary in recursively_find_dicts(
        strategy
    ):
        for key in (
            "strategy_name",
            "name",
            "title",
        ):
            value = dictionary.get(key)

            if value:
                return str(value)

    return get_strategy_id(
        strategy
    )


def load_selection_file(
    selection_file: Path,
) -> dict[str, Any]:
    with selection_file.open(
        "r",
        encoding="utf-8",
    ) as handle:
        data = json.load(handle)

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Selection result must be a JSON object."
        )

    return data


def load_selection_candidates(
    selection_data: dict[str, Any],
) -> list[dict[str, Any]]:
    for key in (
        "paper_candidates",
        "shortlist",
        "strategies",
    ):
        value = selection_data.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            candidates = [
                item
                for item in value
                if isinstance(
                    item,
                    dict,
                )
            ]

            if candidates:
                return candidates

    candidates: list[
        dict[str, Any]
    ] = []

    for dictionary in recursively_find_dicts(
        selection_data
    ):
        if (
            dictionary.get(
                "strategy_id"
            )
            or dictionary.get("id")
        ):
            if dictionary not in candidates:
                candidates.append(
                    dictionary
                )

    return candidates


def find_latest_selection_file() -> Path:
    files = sorted(
        SELECTION_DIR.glob(
            "strategy_selection_*.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"No Selection Engine result found in "
            f"{SELECTION_DIR}"
        )

    return files[0]


def choose_strategy(
    candidates: list[dict[str, Any]],
    strategy_id: str | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError(
            "Selection result contains no strategy candidates."
        )

    if strategy_id:
        for candidate in candidates:
            if (
                get_strategy_id(
                    candidate
                )
                == strategy_id
            ):
                return candidate

        raise ValueError(
            f"Strategy {strategy_id} was not found."
        )

    return candidates[0]


def prepare_signal_history(
    history: pd.DataFrame,
    signal_config: dict[str, Any],
) -> pd.DataFrame:
    data = generate_signal_history(
        history.copy(),
        config=signal_config,
    )

    if not isinstance(
        data,
        pd.DataFrame,
    ):
        raise TypeError(
            "generate_signal_history() did not return a DataFrame."
        )

    if "ATR" not in data.columns:
        raise ValueError(
            "Signal history does not contain ATR."
        )

    return data


def extract_signal_value(
    signal_result: Any,
) -> str:
    if isinstance(
        signal_result,
        dict,
    ):
        for key in (
            "signal",
            "direction",
            "action",
            "side",
        ):
            value = signal_result.get(
                key
            )

            if isinstance(
                value,
                str,
            ):
                normalized = (
                    value.strip().upper()
                )

                if normalized in {
                    "BUY",
                    "SELL",
                    "WAIT",
                    "ERROR",
                }:
                    return normalized

    if isinstance(
        signal_result,
        str,
    ):
        normalized = (
            signal_result.strip().upper()
        )

        if normalized in {
            "BUY",
            "SELL",
            "WAIT",
            "ERROR",
        }:
            return normalized

    for attribute in (
        "signal",
        "direction",
        "action",
        "side",
    ):
        value = getattr(
            signal_result,
            attribute,
            None,
        )

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value.strip().upper()
            )

            if normalized in {
                "BUY",
                "SELL",
                "WAIT",
                "ERROR",
            }:
                return normalized

    return "ERROR"


def get_signal_for_row(
    row: pd.Series,
    signal_config: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
]:
    try:
        result = generate_signal(
            row,
            config=signal_config,
        )

        signal = extract_signal_value(
            result
        )

        if isinstance(
            result,
            dict,
        ):
            return signal, result

        return signal, {
            "signal": signal,
            "raw_type": type(
                result
            ).__name__,
        }

    except Exception as exc:
        return "ERROR", {
            "signal": "ERROR",
            "error": str(exc),
        }


def apply_slippage(
    price: float,
    side: str,
    is_entry: bool,
) -> float:
    rate = (
        SLIPPAGE_PERCENT
        / 100.0
    )

    if side == "LONG":
        return (
            price * (1.0 + rate)
            if is_entry
            else price * (1.0 - rate)
        )

    return (
        price * (1.0 - rate)
        if is_entry
        else price * (1.0 + rate)
    )


def calculate_commission(
    notional: float,
) -> float:
    return abs(
        notional
    ) * (
        COMMISSION_PERCENT
        / 100.0
    )


def calculate_position_quantity(
    price: float,
) -> float:
    notional = (
        INITIAL_CAPITAL
        * POSITION_SIZE_PERCENT
        / 100.0
    )

    if price <= 0:
        return 0.0

    return (
        notional
        / price
    )


def build_risk_prices(
    side: str,
    entry_price: float,
    atr: float,
    risk_config: dict[str, float],
) -> tuple[
    float | None,
    float | None,
]:
    atr_value = clean_number(
        atr
    )

    if atr_value <= 0:
        return None, None

    stop_multiple = max(
        0.0,
        clean_number(
            risk_config.get(
                "stop_atr_multiple",
                2.0,
            ),
            2.0,
        ),
    )

    target_multiple = max(
        0.0,
        clean_number(
            risk_config.get(
                "target_atr_multiple",
                3.0,
            ),
            3.0,
        ),
    )

    if side == "LONG":
        stop_price = (
            entry_price
            - atr_value
            * stop_multiple
            if stop_multiple > 0
            else None
        )

        target_price = (
            entry_price
            + atr_value
            * target_multiple
            if target_multiple > 0
            else None
        )

    else:
        stop_price = (
            entry_price
            + atr_value
            * stop_multiple
            if stop_multiple > 0
            else None
        )

        target_price = (
            entry_price
            - atr_value
            * target_multiple
            if target_multiple > 0
            else None
        )

    return (
        stop_price,
        target_price,
    )


def open_position(
    side: str,
    market_price: float,
    atr: float,
    bar_index: int,
    timestamp: str,
    risk_config: dict[str, float],
) -> Position:
    execution_price = apply_slippage(
        market_price,
        side,
        is_entry=True,
    )

    quantity = calculate_position_quantity(
        execution_price
    )

    entry_commission = calculate_commission(
        quantity
        * execution_price
    )

    stop_price, target_price = (
        build_risk_prices(
            side=side,
            entry_price=execution_price,
            atr=atr,
            risk_config=risk_config,
        )
    )

    return Position(
        side=side,
        quantity=quantity,
        entry_price=execution_price,
        entry_bar=bar_index,
        entry_time=timestamp,
        entry_commission=entry_commission,
        stop_price=stop_price,
        target_price=target_price,
    )


def check_risk_exit(
    position: Position,
    row: pd.Series,
) -> str | None:
    high = clean_number(
        row.get("High")
    )

    low = clean_number(
        row.get("Low")
    )

    if position.side == "LONG":
        stop_hit = (
            position.stop_price is not None
            and low <= position.stop_price
        )

        target_hit = (
            position.target_price is not None
            and high >= position.target_price
        )

    else:
        stop_hit = (
            position.stop_price is not None
            and high >= position.stop_price
        )

        target_hit = (
            position.target_price is not None
            and low <= position.target_price
        )

    # Daily OHLC does not tell us which level was hit first.
    # Stop-first is deliberately conservative.
    if stop_hit:
        return "STOP_LOSS"

    if target_hit:
        return "TAKE_PROFIT"

    return None


def close_position(
    position: Position,
    market_price: float,
    bar_index: int,
    timestamp: str,
    reason: str,
    trade_id: int,
) -> Trade:
    execution_price = apply_slippage(
        market_price,
        position.side,
        is_entry=False,
    )

    if position.side == "LONG":
        gross_pnl = (
            execution_price
            - position.entry_price
        ) * position.quantity
    else:
        gross_pnl = (
            position.entry_price
            - execution_price
        ) * position.quantity

    exit_commission = calculate_commission(
        position.quantity
        * execution_price
    )

    slippage_cost = (
        abs(
            execution_price
            - market_price
        )
        * position.quantity
    )

    net_pnl = (
        gross_pnl
        - position.entry_commission
        - exit_commission
    )

    return Trade(
        trade_id=trade_id,
        side=position.side,
        entry_time=position.entry_time,
        exit_time=timestamp,
        entry_price=position.entry_price,
        exit_price=execution_price,
        quantity=position.quantity,
        gross_pnl=gross_pnl,
        entry_commission=position.entry_commission,
        exit_commission=exit_commission,
        slippage_cost=slippage_cost,
        net_pnl=net_pnl,
        bars_held=(
            bar_index
            - position.entry_bar
        ),
        exit_reason=reason,
    )


def unrealized_pnl(
    position: Position,
    market_price: float,
) -> float:
    if position.side == "LONG":
        return (
            market_price
            - position.entry_price
        ) * position.quantity

    return (
        position.entry_price
        - market_price
    ) * position.quantity


def calculate_metrics(
    trades: list[Trade],
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    if equity_curve:
        final_equity = clean_number(
            equity_curve[-1]["equity"]
        )

        peak = -float("inf")
        max_drawdown = 0.0

        for point in equity_curve:
            equity = clean_number(
                point["equity"]
            )

            peak = max(
                peak,
                equity,
            )

            if peak > 0:
                drawdown = (
                    peak - equity
                ) / peak * 100.0

                max_drawdown = max(
                    max_drawdown,
                    drawdown,
                )
    else:
        final_equity = INITIAL_CAPITAL
        max_drawdown = 0.0

    net_pnl = (
        final_equity
        - INITIAL_CAPITAL
    )

    return_percent = (
        net_pnl
        / INITIAL_CAPITAL
        * 100.0
        if INITIAL_CAPITAL > 0
        else 0.0
    )

    wins = [
        trade
        for trade in trades
        if trade.net_pnl > 0
    ]

    losses = [
        trade
        for trade in trades
        if trade.net_pnl < 0
    ]

    gross_profit = sum(
        trade.net_pnl
        for trade in wins
    )

    gross_loss = abs(
        sum(
            trade.net_pnl
            for trade in losses
        )
    )

    if gross_loss > 0:
        profit_factor: float | str = (
            gross_profit
            / gross_loss
        )
    elif gross_profit > 0:
        profit_factor = "INF"
    else:
        profit_factor = 0.0

    win_rate = (
        len(wins)
        / len(trades)
        * 100.0
        if trades
        else 0.0
    )

    average_trade = (
        net_pnl / len(trades)
        if trades
        else 0.0
    )

    return {
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(
            final_equity,
            2,
        ),
        "net_pnl": round(
            net_pnl,
            2,
        ),
        "return_percent": round(
            return_percent,
            4,
        ),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_percent": round(
            win_rate,
            2,
        ),
        "profit_factor": (
            round(
                profit_factor,
                4,
            )
            if isinstance(
                profit_factor,
                float,
            )
            else profit_factor
        ),
        "average_trade_pnl": round(
            average_trade,
            2,
        ),
        "max_drawdown_percent": round(
            max_drawdown,
            4,
        ),
    }


def paper_trade(
    history: pd.DataFrame,
    signal_config: dict[str, Any],
    risk_config: dict[str, float],
) -> tuple[
    list[Trade],
    list[dict[str, Any]],
    dict[str, int],
]:
    data = prepare_signal_history(
        history,
        signal_config,
    )

    trades: list[Trade] = []
    equity_curve: list[
        dict[str, Any]
    ] = []

    signal_counts = {
        "BUY": 0,
        "SELL": 0,
        "WAIT": 0,
        "ERROR": 0,
    }

    position: Position | None = None
    next_trade_id = 1

    for bar_index, (
        timestamp,
        row,
    ) in enumerate(
        data.iterrows()
    ):
        close_price = clean_number(
            row.get("Close")
        )

        if close_price <= 0:
            continue

        signal, raw_signal = (
            get_signal_for_row(
                row,
                signal_config,
            )
        )

        signal_counts[signal] = (
            signal_counts.get(
                signal,
                0,
            )
            + 1
        )

        timestamp_text = str(
            timestamp
        )

        if position is not None:
            exit_reason = (
                check_risk_exit(
                    position,
                    row,
                )
            )

            if exit_reason is None:
                opposite_signal = (
                    position.side == "LONG"
                    and signal == "SELL"
                ) or (
                    position.side == "SHORT"
                    and signal == "BUY"
                )

                if opposite_signal:
                    exit_reason = (
                        "OPPOSITE_SIGNAL"
                    )

            if exit_reason is None:
                max_holding = risk_config.get(
                    "max_holding_bars"
                )

                if max_holding is not None:
                    max_holding_int = int(
                        max(
                            1,
                            clean_number(
                                max_holding,
                                1.0,
                            ),
                        )
                    )

                    if (
                        bar_index
                        - position.entry_bar
                        >= max_holding_int
                    ):
                        exit_reason = (
                            "MAX_HOLDING_BARS"
                        )

            if exit_reason is not None:
                trade = close_position(
                    position=position,
                    market_price=close_price,
                    bar_index=bar_index,
                    timestamp=timestamp_text,
                    reason=exit_reason,
                    trade_id=next_trade_id,
                )

                trades.append(
                    trade
                )

                next_trade_id += 1
                position = None

        if (
            position is None
            and signal in {
                "BUY",
                "SELL",
            }
        ):
            side = (
                "LONG"
                if signal == "BUY"
                else "SHORT"
            )

            atr = clean_number(
                row.get("ATR")
            )

            position = open_position(
                side=side,
                market_price=close_price,
                atr=atr,
                bar_index=bar_index,
                timestamp=timestamp_text,
                risk_config=risk_config,
            )

        realized_pnl = sum(
            trade.net_pnl
            for trade in trades
        )

        equity = (
            INITIAL_CAPITAL
            + realized_pnl
        )

        if position is not None:
            equity += unrealized_pnl(
                position,
                close_price,
            )

        equity_curve.append(
            {
                "timestamp": timestamp_text,
                "close": round(
                    close_price,
                    6,
                ),
                "signal": signal,
                "equity": round(
                    equity,
                    4,
                ),
                "position": (
                    position.side
                    if position is not None
                    else None
                ),
                "raw_signal": raw_signal,
            }
        )

    if position is not None and len(data) > 0:
        final_timestamp = data.iloc[-1].name
        final_price = clean_number(
            data.iloc[-1].get("Close")
        )

        trade = close_position(
            position=position,
            market_price=final_price,
            bar_index=len(data) - 1,
            timestamp=str(
                final_timestamp
            ),
            reason="END_OF_DATA",
            trade_id=next_trade_id,
        )

        trades.append(
            trade
        )

        final_equity = (
            INITIAL_CAPITAL
            + sum(
                item.net_pnl
                for item in trades
            )
        )

        if equity_curve:
            equity_curve[-1][
                "equity"
            ] = round(
                final_equity,
                4,
            )

            equity_curve[-1][
                "position"
            ] = None

    return (
        trades,
        equity_curve,
        signal_counts,
    )


def save_result(
    result: dict[str, Any],
    strategy_id: str,
) -> Path:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    safe_id = (
        strategy_id
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    path = RESULTS_DIR / (
        f"paper_trading_"
        f"{safe_id}_"
        f"{timestamp}.json"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            result,
            handle,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    return path


def run(
    symbol: str,
    period: str,
    interval: str,
    strategy_id: str | None,
    selection_file: Path | None,
) -> Path:
    print("=" * 76)
    print(
        "📄 MARKET HQ PAPER TRADING ENGINE V1.3"
    )
    print("=" * 76)

    print(
        f"Research Only       : "
        f"{RESEARCH_ONLY}"
    )

    print(
        f"Execution Enabled   : "
        f"{EXECUTION_ENABLED}"
    )

    print(
        f"Symbol              : "
        f"{symbol}"
    )

    print(
        f"Period              : "
        f"{period}"
    )

    print(
        f"Interval            : "
        f"{interval}"
    )

    selected_file = (
        selection_file
        if selection_file is not None
        else find_latest_selection_file()
    )

    selection_data = (
        load_selection_file(
            selected_file
        )
    )

    candidates = (
        load_selection_candidates(
            selection_data
        )
    )

    strategy = choose_strategy(
        candidates,
        strategy_id,
    )

    selected_strategy_id = (
        get_strategy_id(
            strategy
        )
    )

    selected_strategy_name = (
        get_strategy_name(
            strategy
        )
    )

    (
        signal_config,
        risk_config,
    ) = normalize_strategy_parameters(
        strategy
    )

    print(
        f"Selection file      : "
        f"{selected_file.name}"
    )

    print(
        f"Strategy ID         : "
        f"{selected_strategy_id}"
    )

    print(
        f"Strategy name       : "
        f"{selected_strategy_name}"
    )

    print(
        "\n⚙️ Strategy parameters loaded"
    )

    print(
        "Signal config       : "
        f"{json.dumps(signal_config, ensure_ascii=False)}"
    )

    print(
        "Risk config         : "
        f"{json.dumps(risk_config, ensure_ascii=False)}"
    )

    # Explicit runtime guard.
    leaked = (
        set(signal_config)
        & RISK_CONFIG_KEYS
    )

    if leaked:
        raise RuntimeError(
            "STOP: Risk parameters leaked into "
            f"Signal Engine config: {sorted(leaked)}"
        )

    print(
        "\n📥 Loading market history..."
    )

    history = load_history(
        symbol=symbol,
        period=period,
        interval=interval,
    )

    print(
        f"Bars                : "
        f"{len(history)}"
    )

    print(
        f"Start               : "
        f"{history.index[0]}"
    )

    print(
        f"End                 : "
        f"{history.index[-1]}"
    )

    print(
        "\n🧮 Running historical virtual replay..."
    )

    (
        trades,
        equity_curve,
        signal_counts,
    ) = paper_trade(
        history=history,
        signal_config=signal_config,
        risk_config=risk_config,
    )

    metrics = calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
    )

    result = {
        "engine": (
            "MarketHQ Paper Trading Engine"
        ),
        "version": "V1.3",
        "created_at": utc_now(),
        "research_only": RESEARCH_ONLY,
        "execution_enabled": EXECUTION_ENABLED,
        "selection_file": str(
            selected_file
        ),
        "strategy": {
            "strategy_id": (
                selected_strategy_id
            ),
            "strategy_name": (
                selected_strategy_name
            ),
            "signal_config_used": (
                signal_config
            ),
            "risk_config_used": (
                risk_config
            ),
            "selection_record": strategy,
        },
        "market": {
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "bars": len(history),
            "start": str(
                history.index[0]
            ),
            "end": str(
                history.index[-1]
            ),
        },
        "simulation_config": {
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
            "one_position_at_a_time": True,
            "same_bar_stop_target_rule": (
                "STOP_FIRST"
            ),
        },
        "metrics": metrics,
        "signal_counts": signal_counts,
        "trades": [
            asdict(trade)
            for trade in trades
        ],
        "equity_curve": equity_curve,
        "tradingview": {
            "adapter_enabled": False,
            "role": (
                "future research visualization/"
                "alert adapter"
            ),
            "real_money_execution": False,
        },
    }

    result_path = save_result(
        result=result,
        strategy_id=selected_strategy_id,
    )

    print("\n" + "=" * 76)
    print(
        "📊 PAPER TRADING RESULT"
    )
    print("=" * 76)

    print(
        f"Final equity        : "
        f"{metrics['final_equity']}"
    )

    print(
        f"Net PnL             : "
        f"{metrics['net_pnl']}"
    )

    print(
        f"Return              : "
        f"{metrics['return_percent']}%"
    )

    print(
        f"Trades              : "
        f"{metrics['trades']}"
    )

    print(
        f"Wins / Losses       : "
        f"{metrics['wins']} / "
        f"{metrics['losses']}"
    )

    print(
        f"Win Rate            : "
        f"{metrics['win_rate_percent']}%"
    )

    print(
        f"Profit Factor       : "
        f"{metrics['profit_factor']}"
    )

    print(
        f"Average Trade       : "
        f"{metrics['average_trade_pnl']}"
    )

    print(
        f"Max Drawdown        : "
        f"{metrics['max_drawdown_percent']}%"
    )

    print(
        f"Signals             : "
        f"{signal_counts}"
    )

    print(
        f"\n💾 Saved             : "
        f"{result_path}"
    )

    return result_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ research-only "
            "paper trading engine V1.3."
        )
    )

    parser.add_argument(
        "--symbol",
        default="THYAO.IS",
        help=(
            "Symbol to replay. "
            "Default: THYAO.IS"
        ),
    )

    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=(
            "History period. "
            "Default: 1y"
        ),
    )

    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL,
        help=(
            "History interval. "
            "Default: 1d"
        ),
    )

    parser.add_argument(
        "--strategy-id",
        default=None,
        help=(
            "Specific strategy ID from "
            "Selection Engine."
        ),
    )

    parser.add_argument(
        "--selection-file",
        default=None,
        help=(
            "Specific strategy selection JSON file."
        ),
    )

    return parser.parse_args()


def main() -> int:
    if (
        not RESEARCH_ONLY
        or EXECUTION_ENABLED
    ):
        print(
            "SAFETY ERROR: Paper Trading Engine "
            "must remain research-only."
        )
        return 2

    args = parse_args()

    try:
        selection_file = (
            Path(
                args.selection_file
            ).resolve()
            if args.selection_file
            else None
        )

        run(
            symbol=args.symbol,
            period=args.period,
            interval=args.interval,
            strategy_id=args.strategy_id,
            selection_file=selection_file,
        )

        return 0

    except KeyboardInterrupt:
        print("\nStopped.")
        return 130

    except Exception as exc:
        print(
            f"\n❌ PAPER TRADING ERROR: {exc}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

