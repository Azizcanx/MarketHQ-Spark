from __future__ import annotations

"""MarketHQ VectorBT research engine V1."""

import json
import math
import sys
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from agents.strategy_adapter_v1 import ADAPTERS
from smc_structure_v1 import evaluate_smc

ENGINE = "VECTORBT"
ENGINE_VERSION = "1.0.0"


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    value = value.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    value = value.where(~((avg_gain == 0) & (avg_loss > 0)), 0.0)
    return value


def _prepare_close(data: pd.DataFrame) -> pd.Series:
    if not isinstance(data, pd.DataFrame):
        raise ValueError("VECTORBT_DATAFRAME_REQUIRED")
    if "Close" in data.columns:
        close = data["Close"]
    elif "close" in data.columns:
        close = data["close"]
    else:
        raise ValueError("VECTORBT_CLOSE_COLUMN_REQUIRED")
    close = pd.to_numeric(close, errors="coerce")
    close = close.replace([np.inf, -np.inf], np.nan).dropna()
    if len(close) < 3:
        raise ValueError("VECTORBT_INSUFFICIENT_CLOSE_DATA")
    return close


def _compute_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    if not isinstance(data, pd.DataFrame):
        raise ValueError("VECTORBT_DATAFRAME_REQUIRED")
    high = data["High"] if "High" in data.columns else data.get("high")
    low = data["Low"] if "Low" in data.columns else data.get("low")
    close = data["Close"] if "Close" in data.columns else data.get("close")
    if high is None or low is None or close is None:
        raise ValueError("VECTORBT_OHLCV_REQUIRED")
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


def _strategy_params(strategy: dict[str, Any]) -> dict[str, Any]:
    params = strategy.get("parameters")
    if not isinstance(params, dict):
        params = {}

    strategy_id = strategy.get("strategy_id", "")

    # ── Adapter-based strategy ──────────────────────────
    if strategy_id in ADAPTERS:
        direction = str(strategy.get("direction", "LONG")).upper()
        if direction not in ("LONG", "SHORT"):
            raise ValueError("VECTORBT_DIRECTION_MUST_BE_LONG_OR_SHORT")
        required = {
            "strategy_id": strategy_id,
            "direction": direction,
            "sl_atr_multiple": _finite(params.get("sl_atr_multiple"), 0.0),
            "tp_atr_multiple": _finite(params.get("tp_atr_multiple"), 0.0),
        }
        if strategy_id == "rs_benchmark_v1":
            required["benchmark"] = params.get("benchmark")
        elif strategy_id == "or_breakout_v1":
            required["lookback"] = _int(params.get("lookback"), 30)
        return required

    # ── Bridge strategies (9 real logics) ────────────────
    if strategy_id in BRIDGE_STRATEGIES:
        direction = str(strategy.get("direction", "LONG")).upper()
        if direction not in ("LONG", "SHORT"):
            raise ValueError("VECTORBT_DIRECTION_MUST_BE_LONG_OR_SHORT")
        required = {"strategy_id": strategy_id, "direction": direction}
        schema = BRIDGE_STRATEGIES[strategy_id]["param_schema"]
        for key, spec in schema.items():
            if key == "direction":
                continue
            default = spec.get("default")
            val = params.get(key, default)
            if spec["type"] == "int":
                val = _int(val, default)
            elif spec["type"] == "float":
                val = _finite(val, default)
            required[key] = val
        required["sl_atr_multiple"] = _finite(params.get("sl_atr_multiple"), 0.0)
        required["tp_atr_multiple"] = _finite(params.get("tp_atr_multiple"), 0.0)
        return required

    # ── Built-in SMA+RSI strategy ───────────────────────
    required = {
        "sma_fast": _int(params.get("sma_fast"), 0),
        "sma_slow": _int(params.get("sma_slow"), 0),
        "rsi_period": _int(params.get("rsi_period"), 0),
        "rsi_entry": _finite(params.get("rsi_entry"), None),
        "sl_atr_multiple": _finite(params.get("sl_atr_multiple"), 0.0),
        "tp_atr_multiple": _finite(params.get("tp_atr_multiple"), 0.0),
        "direction": str(params.get("direction", "LONG")).upper(),
    }
    if required["sma_fast"] <= 0:
        raise ValueError("VECTORBT_SMA_FAST_REQUIRED")
    if required["sma_slow"] <= 0:
        raise ValueError("VECTORBT_SMA_SLOW_REQUIRED")
    if required["rsi_period"] <= 0:
        raise ValueError("VECTORBT_RSI_PERIOD_REQUIRED")
    if required["rsi_entry"] is None:
        raise ValueError("VECTORBT_RSI_ENTRY_REQUIRED")
    if required["sma_fast"] >= required["sma_slow"]:
        raise ValueError("VECTORBT_SMA_FAST_MUST_BE_LESS_THAN_SLOW")
    if required["direction"] not in ("LONG", "SHORT"):
        raise ValueError("VECTORBT_DIRECTION_MUST_BE_LONG_OR_SHORT")
    return required


def _signals(close: pd.Series, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    fast = close.rolling(params["sma_fast"], min_periods=params["sma_fast"]).mean()
    slow = close.rolling(params["sma_slow"], min_periods=params["sma_slow"]).mean()
    rsi_value = _rsi(close, params["rsi_period"])
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = ((fast < slow) & (rsi_value > params["rsi_entry"])).fillna(False)
        exits = ((fast > slow)).fillna(False)
    else:
        entries = ((fast > slow) & (rsi_value > params["rsi_entry"])).fillna(False)
        exits = ((fast < slow)).fillna(False)
    return entries, exits


# ============================================================
# 9 STRATEJİ SİNYAL FONKSİYONLARI
# ============================================================

def _ema_trend_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    fast = data["EMA_FAST"].rolling(params["ema_fast"], min_periods=params["ema_fast"]).mean()
    slow = data["EMA_SLOW"].rolling(params["ema_slow"], min_periods=params["ema_slow"]).mean()
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (fast < slow).fillna(False)
        exits = (fast > slow).fillna(False)
    else:
        entries = (fast > slow).fillna(False)
        exits = (fast < slow).fillna(False)
    return entries, exits


def _rsi_reversal_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    rsi = data["RSI"]
    oversold = params.get("rsi_oversold", 30)
    overbought = params.get("rsi_overbought", 70)
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (rsi > overbought).fillna(False)
        exits = (rsi < overbought).fillna(False)
    else:
        entries = (rsi < oversold).fillna(False)
        exits = (rsi > oversold).fillna(False)
    return entries, exits


def _donchian_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    period = params.get("donchian_period", 20)
    don_high = data["High"].rolling(period).max().shift(1)
    don_low = data["Low"].rolling(period).min().shift(1)
    close = data["Close"]
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (close < don_low).fillna(False)
        exits = (close > don_low).fillna(False)
    else:
        entries = (close > don_high).fillna(False)
        exits = (close < don_high).fillna(False)
    return entries, exits


def _supertrend_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    st_dir = data["ST_DIR"]
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (st_dir < 0).fillna(False)
        exits = (st_dir > 0).fillna(False)
    else:
        entries = (st_dir > 0).fillna(False)
        exits = (st_dir < 0).fillna(False)
    return entries, exits


def _adx_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    adx = data["ADX"]
    plus_di = data["PLUS_DI"]
    minus_di = data["MINUS_DI"]
    threshold = params.get("adx_threshold", 20.0)
    direction = params.get("direction", "LONG")
    valid = adx > threshold
    if direction == "SHORT":
        entries = (valid & (minus_di > plus_di)).fillna(False)
        exits = (~valid | (plus_di >= minus_di)).fillna(False)
    else:
        entries = (valid & (plus_di > minus_di)).fillna(False)
        exits = (~valid | (minus_di >= plus_di)).fillna(False)
    return entries, exits


def _vwap_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    vwap = data["VWAP"]
    close = data["Close"]
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (close < vwap).fillna(False)
        exits = (close > vwap).fillna(False)
    else:
        entries = (close > vwap).fillna(False)
        exits = (close < vwap).fillna(False)
    return entries, exits


def _bollinger_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    upper = data["BB_UPPER"]
    lower = data["BB_LOWER"]
    close = data["Close"]
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (close > upper).fillna(False)
        exits = (close < upper).fillna(False)
    else:
        entries = (close < lower).fillna(False)
        exits = (close > lower).fillna(False)
    return entries, exits


def _atr_breakout_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    body = (data["Close"] - data["Open"]).abs()
    atr = data["ATR"]
    is_bullish = data["Close"] > data["Open"]
    is_bearish = data["Close"] < data["Open"]
    breakout = body > (1.5 * atr)
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = (breakout & is_bearish).fillna(False)
        exits = (~breakout | is_bullish).fillna(False)
    else:
        entries = (breakout & is_bullish).fillna(False)
        exits = (~breakout | is_bearish).fillna(False)
    return entries, exits


def _stoch_reversal_signals(data: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    k = data["STOCH_K"]
    d = data["STOCH_D"]
    direction = params.get("direction", "LONG")
    if direction == "SHORT":
        entries = ((k > 80) & (k < d)).fillna(False)
        exits = ((k <= 80) | (k >= d)).fillna(False)
    else:
        entries = ((k < 20) & (k > d)).fillna(False)
        exits = ((k >= 20) | (k <= d)).fillna(False)
    return entries, exits


# ============================================================
# STRATEGY REGISTRY (Victor BT bridge)
# ============================================================

BRIDGE_STRATEGIES: dict[str, dict[str, Any]] = {
    "ema_trend_v1": {
        "signal_fn": _ema_trend_signals,
        "indicators": ["EMA_FAST", "EMA_SLOW"],
        "param_schema": {
            "ema_fast": {"type": "int", "default": 20, "min": 2},
            "ema_slow": {"type": "int", "default": 50, "min": 3},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "rsi_reversal_v1": {
        "signal_fn": _rsi_reversal_signals,
        "indicators": ["RSI"],
        "param_schema": {
            "rsi_period": {"type": "int", "default": 14, "min": 2},
            "rsi_oversold": {"type": "float", "default": 30},
            "rsi_overbought": {"type": "float", "default": 70},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "donchian_breakout_v1": {
        "signal_fn": _donchian_signals,
        "indicators": ["High", "Low"],
        "param_schema": {
            "donchian_period": {"type": "int", "default": 20, "min": 2},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "supertrend_v1": {
        "signal_fn": _supertrend_signals,
        "indicators": ["ST_DIR"],
        "param_schema": {
            "supertrend_period": {"type": "int", "default": 10, "min": 2},
            "supertrend_mult": {"type": "float", "default": 3.0},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "adx_v1": {
        "signal_fn": _adx_signals,
        "indicators": ["ADX", "PLUS_DI", "MINUS_DI"],
        "param_schema": {
            "adx_period": {"type": "int", "default": 14, "min": 2},
            "adx_threshold": {"type": "float", "default": 20.0},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "vwap_v1": {
        "signal_fn": _vwap_signals,
        "indicators": ["VWAP"],
        "param_schema": {
            "vwap_window": {"type": "int", "default": 20, "min": 2},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "bollinger_v1": {
        "signal_fn": _bollinger_signals,
        "indicators": ["BB_UPPER", "BB_LOWER"],
        "param_schema": {
            "bollinger_period": {"type": "int", "default": 20, "min": 2},
            "bollinger_std": {"type": "float", "default": 2.0},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "atr_breakout_v1": {
        "signal_fn": _atr_breakout_signals,
        "indicators": ["ATR", "Open", "Close"],
        "param_schema": {
            "atr_period": {"type": "int", "default": 14, "min": 2},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
    "stoch_reversal_v1": {
        "signal_fn": _stoch_reversal_signals,
        "indicators": ["STOCH_K", "STOCH_D"],
        "param_schema": {
            "stoch_k_period": {"type": "int", "default": 14, "min": 2},
            "stoch_d_period": {"type": "int", "default": 3, "min": 1},
            "direction": {"type": "str", "default": "LONG"},
        },
    },
}


def _adapter_signals(data: pd.DataFrame, params: dict[str, Any], direction: str) -> tuple[pd.Series, pd.Series]:
    """Adapter-based strategy: enrich → signal → VectorBT entries/exits."""
    strategy_id = params["strategy_id"]
    adapter = ADAPTERS[strategy_id]
    enrich_fn = adapter["enrich"]
    signal_fn = adapter["signal"]

    enrich_kwargs: dict[str, Any] = {}
    benchmark = None
    if strategy_id == "rs_benchmark_v1":
        benchmark = params.get("benchmark")
        if isinstance(benchmark, list):
            benchmark = pd.Series(benchmark, index=data.index[: len(benchmark)])
        if benchmark is not None:
            enrich_kwargs["benchmark"] = benchmark
    elif strategy_id == "or_breakout_v1":
        enrich_kwargs["lookback"] = params.get("lookback", 30)

    enriched = enrich_fn(data, **enrich_kwargs)

    # ── Vectorized signal generation from enrich columns ──
    entries = pd.Series(False, index=enriched.index)
    exits = pd.Series(False, index=enriched.index)

    if strategy_id == "rs_benchmark_v1":
        if benchmark is None or float(benchmark.sum()) == 0.0:
            return entries, exits
        bm = benchmark.reindex(enriched.index).ffill()
        window = params.get("rs_window", 20)
        asset_roll = data["Close"].rolling(window).mean()
        bm_roll = bm.rolling(window).mean()
        rs_ratio = asset_roll / bm_roll
        rs_trend = rs_ratio.pct_change()
        valid = rs_trend.notna() & bm_roll.notna()
        long_mask = valid & (rs_trend > 0)
        short_mask = valid & (rs_trend < 0)
        if direction == "LONG":
            entries = long_mask
            exits = ~long_mask & valid
        elif direction == "SHORT":
            entries = short_mask
            exits = ~short_mask & valid
        else:
            entries = long_mask | short_mask
            exits = ~entries & valid

    elif strategy_id == "smc_structure_v1":
        # Per-bar SMC direction (multi-bar logic needs per-bar evaluation)
        smc_dirs = []
        for i in range(len(enriched)):
            w = enriched.iloc[: i + 1]
            res = evaluate_smc(w)
            smc_dirs.append(res.get("direction", "NEUTRAL"))
        smc_dir = pd.Series(smc_dirs, index=enriched.index)
        long_mask = smc_dir == "LONG"
        short_mask = smc_dir == "SHORT"
        if direction == "LONG":
            entries = long_mask
            exits = ~long_mask
        elif direction == "SHORT":
            entries = short_mask
            exits = ~short_mask
        else:
            entries = long_mask | short_mask
            exits = ~(long_mask | short_mask)

    elif strategy_id == "or_breakout_v1":
        or_dir = enriched.get("OR_DIR", pd.Series(dtype=str))
        long_mask = or_dir == "LONG"
        short_mask = or_dir == "SHORT"
        if direction == "LONG":
            entries = long_mask
            exits = ~long_mask
        elif direction == "SHORT":
            entries = short_mask
            exits = ~short_mask
        else:
            entries = long_mask | short_mask
            exits = ~(long_mask | short_mask)

    return entries, exits


def _return_series(portfolio: Any) -> list[float]:
    try:
        values = np.asarray(portfolio.returns(), dtype=float).reshape(-1)
        return [float(x) for x in values if math.isfinite(float(x))]
    except Exception:
        return []


def _equity_series(portfolio: Any) -> list[float]:
    try:
        values = np.asarray(portfolio.value(), dtype=float).reshape(-1)
        return [float(x) for x in values if math.isfinite(float(x))]
    except Exception:
        return []


def _run_single(data: pd.DataFrame, params: dict[str, Any], init_cash: float, fees: float, slippage: float) -> dict[str, Any]:
    close = _prepare_close(data)
    direction = params.get("direction", "LONG")

    strategy_id = params.get("strategy_id", "")

    # ── Bridge strategies (9 real strategy logics) ──
    if strategy_id in BRIDGE_STRATEGIES:
        signal_fn = BRIDGE_STRATEGIES[strategy_id]["signal_fn"]
        entries, exits = signal_fn(data, params)

    # ── Adapter strategies (3 custom) ───────────────
    elif strategy_id in ADAPTERS:
        entries, exits = _adapter_signals(data, params, direction)

    # ── Built-in SMA+RSI fallback ───────────────────
    else:
        entries, exits = _signals(close, params)

    sl_mult = params.get("sl_atr_multiple", 0.0) or 0.0
    tp_mult = params.get("tp_atr_multiple", 0.0) or 0.0

    stop_prices: pd.Series | None = None
    target_prices: pd.Series | None = None

    if sl_mult > 0 or tp_mult > 0:
        try:
            atr = _compute_atr(data, period=14)
            atr_aligned = atr.reindex(close.index).ffill()
        except Exception:
            atr_aligned = pd.Series(0.0, index=close.index)

        stop_prices = pd.Series(float("nan"), index=close.index)
        target_prices = pd.Series(float("nan"), index=close.index)

        for idx in close.index[entries]:
            pos = close.index.get_loc(idx)
            entry_price = float(close.iloc[pos])
            atr_val = float(atr_aligned.iloc[pos])
            if not math.isfinite(atr_val) or atr_val <= 0:
                continue
            if direction == "SHORT":
                stop_prices.iloc[pos] = entry_price + atr_val * sl_mult
                target_prices.iloc[pos] = entry_price - atr_val * tp_mult
            else:
                stop_prices.iloc[pos] = entry_price - atr_val * sl_mult
                target_prices.iloc[pos] = entry_price + atr_val * tp_mult

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        sl_stop=stop_prices if stop_prices is not None else None,
        tp_stop=target_prices if target_prices is not None else None,
        use_stops=True,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        freq="1D",
    )
    final_value = _finite(portfolio.final_value())
    total_return_fraction = _finite(portfolio.total_return())
    max_drawdown_fraction = _finite(portfolio.max_drawdown())
    sharpe = _finite(portfolio.sharpe_ratio())
    trade_count = 0
    win_rate = None
    trade_pnls: list[float] = []
    try:
        trade_count = int(portfolio.trades.count())
    except Exception:
        pass
    try:
        win_rate = _finite(portfolio.trades.win_rate())
    except Exception:
        pass
    try:
        raw_pnls = portfolio.trades.pnl.values
        trade_pnls = [float(x) for x in np.asarray(raw_pnls).reshape(-1) if math.isfinite(float(x))]
    except Exception:
        pass
    net_pnl = final_value - init_cash if final_value is not None else None
    return {
        "status": "COMPLETED",
        "parameters": params,
        "metrics": {
            "net_return_percent": total_return_fraction * 100 if total_return_fraction is not None else None,
            "return_percent": total_return_fraction * 100 if total_return_fraction is not None else None,
            "total_return_percent": total_return_fraction * 100 if total_return_fraction is not None else None,
            "net_pnl": net_pnl,
            "profit": net_pnl,
            "max_drawdown_percent": max_drawdown_fraction * 100 if max_drawdown_fraction is not None else None,
            "sharpe_ratio": sharpe,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "final_value": final_value,
        },
        "tradePnls": trade_pnls,
        "returnSeries": _return_series(portfolio),
        "equitySeries": _equity_series(portfolio),
        "seriesMetadata": {"kind": "PORTFOLIO_PER_BAR", "frequency": "1D", "source": "VECTORBT_PORTFOLIO_RETURNS", "researchDiagnosticReady": True},
    }


def bridge_strategy_keys(base: dict[str, Any]) -> list[str]:
    """Return sweepable parameter keys for a bridge strategy."""
    strategy_id = base.get("strategy_id", "")
    if strategy_id not in BRIDGE_STRATEGIES:
        return []
    schema = BRIDGE_STRATEGIES[strategy_id]["param_schema"]
    return [k for k in schema if k != "direction"]


def _candidate_parameters(base: dict[str, Any], sweep: dict[str, Any] | None, parameter_candidates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if parameter_candidates:
        normalized_candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_candidate in parameter_candidates:
            if not isinstance(raw_candidate, dict):
                continue
            candidate = dict(base)
            candidate.update(raw_candidate)
            marker = json.dumps(candidate, sort_keys=True, default=str)
            if marker not in seen:
                seen.add(marker)
                normalized_candidates.append(candidate)
        if normalized_candidates:
            return normalized_candidates
    if not sweep:
        return [dict(base)]

    # Adapter-based strategies have different sweep keys
    strategy_id = base.get("strategy_id", "")
    if strategy_id in BRIDGE_STRATEGIES:
        keys = bridge_strategy_keys(base)
        if not keys and sweep:
            keys = list(sweep.keys())
        elif not keys:
            keys = list(base.keys())
    elif strategy_id in ADAPTERS:
        keys = list(sweep.keys()) if sweep else list(base.keys())
    else:
        keys = ["sma_fast", "sma_slow", "rsi_period", "rsi_entry", "sl_atr_multiple", "tp_atr_multiple"]

    values: list[list[Any]] = []
    for key in keys:
        raw = sweep.get(key)
        values.append(raw if isinstance(raw, list) and raw else [base.get(key)])
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for combo in product(*values):
        candidate = dict(base)
        for key, value in zip(keys, combo):
            candidate[key] = value
        marker = json.dumps(candidate, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            result.append(candidate)
    return result


def _select_best(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[tuple[float, float, dict[str, Any]]] = []
    for result in results:
        metrics = result.get("metrics", {})
        ret = _finite(metrics.get("net_return_percent"))
        sharpe = _finite(metrics.get("sharpe_ratio"), float("-inf"))
        if ret is not None:
            ranked.append((ret, sharpe if sharpe is not None else float("-inf"), result))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def _sharpe_from_returns(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size < 2:
        return None
    deviation = float(array.std(ddof=1))
    if deviation == 0:
        return 0.0
    return float(array.mean() / deviation)


def _build_candidate_fold_sharpes(
    data: pd.DataFrame,
    candidates: list[dict[str, Any]],
    init_cash: float,
    fees: float,
    slippage: float,
    *,
    train_bars: int = 252,
    oos_bars: int = 63,
    step_bars: int = 63,
) -> tuple[list[list[float]] | None, dict[str, Any]]:
    """Build candidate x fold Sharpe from real chronological OOS evaluations.

    Parameters are fixed before the folds run. Each fold uses a 252-bar
    chronological warm-up/train window followed by a 63-bar unseen OOS window.
    Indicators are calculated on the combined train+OOS window and only the
    final OOS bars contribute to the fold Sharpe. This is WFO-shaped validation
    without claiming optimizer fitting or purged CPCV.
    """
    close = _prepare_close(data)
    total = len(close)
    if len(candidates) < 4 or total < train_bars + oos_bars:
        return None, {"available": False, "reason": "WFO_CANDIDATE_MATRIX_INSUFFICIENT_INPUT", "foldCount": 0, "candidateCount": len(candidates)}

    fold_windows: list[tuple[int, int, int]] = []
    start = 0
    while start + train_bars + oos_bars <= total:
        fold_windows.append((start, start + train_bars, start + train_bars + oos_bars))
        start += step_bars
    if len(fold_windows) < 4:
        return None, {"available": False, "reason": "WFO_CANDIDATE_MATRIX_NEEDS_FOUR_FOLDS", "foldCount": len(fold_windows), "candidateCount": len(candidates)}

    matrix: list[list[float]] = []
    usable_candidates = 0
    for candidate in candidates:
        try:
            normalized = _strategy_params(
                {"parameters": candidate, "strategy_id": candidate.get("strategy_id", "")}
            )
            row: list[float] = []
            for fold_start, train_end, window_end in fold_windows:
                window = data.iloc[fold_start:window_end].copy()
                result = _run_single(window, normalized, init_cash, fees, slippage)
                returns = result.get("returnSeries") or []
                oos_returns = returns[-oos_bars:]
                sharpe = _sharpe_from_returns(oos_returns)
                if sharpe is None or not math.isfinite(float(sharpe)):
                    raise ValueError("WFO_OOS_SHARPE_UNAVAILABLE")
                row.append(float(sharpe))
            matrix.append(row)
            usable_candidates += 1
        except Exception:
            continue

    if usable_candidates < 4:
        return None, {"available": False, "reason": "WFO_CANDIDATE_MATRIX_NEEDS_FOUR_USABLE_CANDIDATES", "foldCount": len(fold_windows), "candidateCount": usable_candidates}

    return matrix, {
        "available": True,
        "type": "WFO_OOS_CANDIDATE_FOLD_SHARPE",
        "method": "MULTI_FOLD_WALK_FORWARD_OOS_CANDIDATE_MATRIX_V1",
        "foldCount": len(fold_windows),
        "candidateCount": usable_candidates,
        "trainBars": train_bars,
        "oosBars": oos_bars,
        "stepBars": step_bars,
        "parameterFittingPerformed": False,
        "notPurgedCPCV": True,
    }


def run_vectorbt_backtest(data: pd.DataFrame, strategy: dict[str, Any], backtest_config: dict[str, Any], parameter_sweep: dict[str, Any] | None = None, parameter_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    close = _prepare_close(data)

    strategy_id = strategy.get("strategy_id", "")

    # Unknown strategy_id → clear error before any validation
    if strategy_id and strategy_id not in ADAPTERS and strategy_id not in BRIDGE_STRATEGIES:
        return {
            "status": "FAILED",
            "engine": ENGINE,
            "engineVersion": ENGINE_VERSION,
            "researchOnly": True,
            "executionEnabled": False,
            "brokerExecutionEnabled": False,
            "databaseWriteEnabled": False,
            "error": f"UNKNOWN_STRATEGY: {strategy_id}",
            "known_strategies": list(ADAPTERS.keys()) + list(BRIDGE_STRATEGIES.keys()),
            "errors": [],
        }

    base = _strategy_params(strategy)
    initial_capital = _finite(backtest_config.get("initial_capital"), 100_000.0) or 100_000.0
    commission_percent = _finite(backtest_config.get("commission_percent"), 0.10) or 0.10
    slippage_percent = _finite(backtest_config.get("slippage_percent"), 0.05) or 0.05
    fees = commission_percent / 100.0
    slippage = slippage_percent / 100.0

    candidates = _candidate_parameters(base, parameter_sweep, parameter_candidates)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            normalized = _strategy_params(
                {"parameters": candidate, "strategy_id": candidate.get("strategy_id", "")}
            )
            results.append(_run_single(data, normalized, initial_capital, fees, slippage))
        except Exception as exc:
            errors.append({"parameters": candidate, "error": str(exc)})
    best = _select_best(results)

    candidate_fold_sharpes, fold_metadata = _build_candidate_fold_sharpes(
        data,
        candidates,
        initial_capital,
        fees,
        slippage,
    )
    try:
        from agents.overfit_validation_v1 import evaluate_overfit_diagnostics
        overfit_diagnostics = evaluate_overfit_diagnostics(
            results=results,
            selected=best,
            return_series=best.get("returnSeries") if isinstance(best, dict) else None,
            candidate_fold_sharpes=candidate_fold_sharpes,
        )
        overfit_diagnostics["candidateFoldMatrix"] = fold_metadata
    except Exception as exc:
        overfit_diagnostics = {"version": "1.2.0", "status": "INCONCLUSIVE", "reason": "OVERFIT_VALIDATION_UNAVAILABLE", "error": str(exc), "candidateFoldMatrix": fold_metadata, "researchOnly": True, "executionEnabled": False, "brokerExecutionEnabled": False, "databaseWriteEnabled": False}

    direction = base.get("direction", "LONG")
    has_sl = (base.get("sl_atr_multiple") or 0.0) > 0
    has_tp = (base.get("tp_atr_multiple") or 0.0) > 0
    risk_applied = has_sl or has_tp

    if strategy_id:
        if strategy_id in BRIDGE_STRATEGIES:
            signal_model = f"BRIDGE_{strategy_id.upper()}"
        elif strategy_id in ADAPTERS:
            signal_model = f"ADAPTER_{strategy_id.upper()}"
        else:
            signal_model = "UNKNOWN"
    else:
        signal_model = "SMA_FAST_GT_SMA_SLOW_AND_RSI_ABOVE_THRESHOLD"

    return {
        "status": "COMPLETED" if results else "FAILED",
        "engine": ENGINE,
        "engineVersion": ENGINE_VERSION,
        "researchOnly": True,
        "executionEnabled": False,
        "brokerExecutionEnabled": False,
        "databaseWriteEnabled": False,
        "semantics": {
            "signalModel": signal_model,
            "direction": direction,
            "riskControlsApplied": risk_applied,
            "riskControlsNotApplied": [k for k, v in {
                "stop_loss_atr": has_sl,
                "take_profit_atr": has_tp,
                "max_holding_bars": True,
                "short_positions": direction == "LONG",
            }.items() if not v],
        },
        "data": {"bars": len(close), "start": close.index.min().isoformat() if hasattr(close.index.min(), "isoformat") else str(close.index.min()), "end": close.index.max().isoformat() if hasattr(close.index.max(), "isoformat") else str(close.index.max())},
        "costModel": {"commissionPercent": commission_percent, "slippagePercent": slippage_percent, "fees": fees, "slippage": slippage, "initialCapital": initial_capital},
        "parameterSweep": {"requested": bool(parameter_sweep) or bool(parameter_candidates), "source": "SYSTEMATIC_TRADING_FRAMEWORK" if parameter_candidates else "VECTORBT_NATIVE", "candidateCount": len(candidates), "completedCount": len(results), "failedCount": len(errors)},
        "results": results,
        "best": best,
        "metrics": best.get("metrics") if isinstance(best, dict) else None,
        "overfitDiagnostics": overfit_diagnostics,
        "overfitFoldDiagnostics": fold_metadata,
        "errors": errors,
    }


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"status": "BLOCKED", "engine": ENGINE, "engineVersion": ENGINE_VERSION, "reason": "JSON_INPUT_REQUIRED"}, ensure_ascii=False))
        return 1
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON_OBJECT_REQUIRED")
        data_obj = payload.get("data", {})
        if not isinstance(data_obj, dict):
            raise ValueError("VECTORBT_DATA_OBJECT_REQUIRED")
        dates = data_obj.get("date", data_obj.get("dates"))
        closes = data_obj.get("close")
        if not isinstance(closes, list):
            raise ValueError("VECTORBT_CLOSE_LIST_REQUIRED")
        frame = pd.DataFrame({"Close": pd.to_numeric(closes, errors="coerce")})
        if isinstance(dates, list) and len(dates) == len(closes):
            frame.index = pd.to_datetime(dates, errors="coerce")
        result = run_vectorbt_backtest(data=frame, strategy=payload.get("strategy", {}), backtest_config={"initial_capital": payload.get("initCash", 100_000.0), "commission_percent": payload.get("commissionPercent", 0.10), "slippage_percent": payload.get("slippagePercent", 0.05)}, parameter_sweep=payload.get("parameterSweep") if isinstance(payload.get("parameterSweep"), dict) else None, parameter_candidates=payload.get("parameterCandidates") if isinstance(payload.get("parameterCandidates"), list) else None)
        print(json.dumps(_json_safe(result), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "engine": ENGINE, "engineVersion": ENGINE_VERSION, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())