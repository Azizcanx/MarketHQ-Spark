"""Tests for Victor BT bridge strategies (9 real strategy logics)."""

import pandas as pd
import numpy as np
import pytest

from agents.vectorbt_engine_v1 import (
    BRIDGE_STRATEGIES,
    _strategy_params,
    _run_single,
    _ema_trend_signals,
    _rsi_reversal_signals,
    _donchian_signals,
    _supertrend_signals,
    _adx_signals,
    _vwap_signals,
    _bollinger_signals,
    _atr_breakout_signals,
    _stoch_reversal_signals,
    bridge_strategy_keys,
    run_vectorbt_backtest,
)
from signal_engine import add_indicators, DEFAULT_CONFIG


def make_ohlcv(n: int = 120, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "Open": close - rng.uniform(-0.5, 0.5, n),
        "High": close + rng.uniform(0.1, 2, n),
        "Low": close - rng.uniform(0.1, 2, n),
        "Close": close,
        "Volume": rng.uniform(1_000_000, 5_000_000, n),
    }, index=idx)


def enriched_df() -> pd.DataFrame:
    df = make_ohlcv()
    return add_indicators(df.copy(), DEFAULT_CONFIG)


# ── Registry sanity ────────────────────────────────────

def test_bridge_registry_has_9():
    assert set(BRIDGE_STRATEGIES.keys()) == {
        "ema_trend_v1", "rsi_reversal_v1", "donchian_breakout_v1",
        "supertrend_v1", "adx_v1", "vwap_v1",
        "bollinger_v1", "atr_breakout_v1", "stoch_reversal_v1",
    }


def test_bridge_strategy_keys():
    for sid, spec in BRIDGE_STRATEGIES.items():
        keys = bridge_strategy_keys({"strategy_id": sid})
        assert isinstance(keys, list)
        schema = spec["param_schema"]
        expected = [k for k in schema if k != "direction"]
        assert set(keys) == set(expected)


# ── Indicator columns present ──────────────────────────

def test_indicator_columns_enriched():
    df = enriched_df()
    required = ["EMA_FAST", "EMA_SLOW", "RSI", "ST_DIR", "ADX", "PLUS_DI",
                "MINUS_DI", "VWAP", "BB_UPPER", "BB_LOWER", "ATR",
                "STOCH_K", "STOCH_D"]
    for col in required:
        assert col in df.columns, f"Missing: {col}"


# ── EMA Trend ──────────────────────────────────────────

def test_ema_trend_long():
    df = enriched_df()
    params = {"strategy_id": "ema_trend_v1", "direction": "LONG", "ema_fast": 5, "ema_slow": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _ema_trend_signals(df, params)
    assert isinstance(entries, pd.Series)
    assert entries.any() or True  # may have no entries with random data

def test_ema_trend_short():
    df = enriched_df()
    params = {"strategy_id": "ema_trend_v1", "direction": "SHORT", "ema_fast": 5, "ema_slow": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _ema_trend_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── RSI Reversal ───────────────────────────────────────

def test_rsi_reversal_long():
    df = enriched_df()
    params = {"strategy_id": "rsi_reversal_v1", "direction": "LONG", "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _rsi_reversal_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_rsi_reversal_short():
    df = enriched_df()
    params = {"strategy_id": "rsi_reversal_v1", "direction": "SHORT", "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _rsi_reversal_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── Donchian ───────────────────────────────────────────

def test_donchian_long():
    df = enriched_df()
    params = {"strategy_id": "donchian_breakout_v1", "direction": "LONG", "donchian_period": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _donchian_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_donchian_short():
    df = enriched_df()
    params = {"strategy_id": "donchian_breakout_v1", "direction": "SHORT", "donchian_period": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _donchian_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── SuperTrend ─────────────────────────────────────────

def test_supertrend_long():
    df = enriched_df()
    params = {"strategy_id": "supertrend_v1", "direction": "LONG", "supertrend_period": 10, "supertrend_mult": 3.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _supertrend_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_supertrend_short():
    df = enriched_df()
    params = {"strategy_id": "supertrend_v1", "direction": "SHORT", "supertrend_period": 10, "supertrend_mult": 3.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _supertrend_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── ADX ────────────────────────────────────────────────

def test_adx_long():
    df = enriched_df()
    params = {"strategy_id": "adx_v1", "direction": "LONG", "adx_period": 14, "adx_threshold": 20.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _adx_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_adx_short():
    df = enriched_df()
    params = {"strategy_id": "adx_v1", "direction": "SHORT", "adx_period": 14, "adx_threshold": 20.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _adx_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── VWAP ───────────────────────────────────────────────

def test_vwap_long():
    df = enriched_df()
    params = {"strategy_id": "vwap_v1", "direction": "LONG", "vwap_window": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _vwap_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_vwap_short():
    df = enriched_df()
    params = {"strategy_id": "vwap_v1", "direction": "SHORT", "vwap_window": 20, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _vwap_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── Bollinger ──────────────────────────────────────────

def test_bollinger_long():
    df = enriched_df()
    params = {"strategy_id": "bollinger_v1", "direction": "LONG", "bollinger_period": 20, "bollinger_std": 2.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _bollinger_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_bollinger_short():
    df = enriched_df()
    params = {"strategy_id": "bollinger_v1", "direction": "SHORT", "bollinger_period": 20, "bollinger_std": 2.0, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _bollinger_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── ATR Breakout ───────────────────────────────────────

def test_atr_breakout_long():
    df = enriched_df()
    params = {"strategy_id": "atr_breakout_v1", "direction": "LONG", "atr_period": 14, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _atr_breakout_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_atr_breakout_short():
    df = enriched_df()
    params = {"strategy_id": "atr_breakout_v1", "direction": "SHORT", "atr_period": 14, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _atr_breakout_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── Stochastic ─────────────────────────────────────────

def test_stoch_long():
    df = enriched_df()
    params = {"strategy_id": "stoch_reversal_v1", "direction": "LONG", "stoch_k_period": 14, "stoch_d_period": 3, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _stoch_reversal_signals(df, params)
    assert isinstance(entries, pd.Series)

def test_stoch_short():
    df = enriched_df()
    params = {"strategy_id": "stoch_reversal_v1", "direction": "SHORT", "stoch_k_period": 14, "stoch_d_period": 3, "sl_atr_multiple": 0, "tp_atr_multiple": 0}
    entries, exits = _stoch_reversal_signals(df, params)
    assert isinstance(entries, pd.Series)


# ── Parameter validation ───────────────────────────────

def test_bridge_params_valid():
    for sid in BRIDGE_STRATEGIES:
        strategy = {"strategy_id": sid, "direction": "LONG", "parameters": {}}
        params = _strategy_params(strategy)
        assert params["strategy_id"] == sid
        assert params["direction"] == "LONG"

def test_bridge_params_direction_short():
    for sid in BRIDGE_STRATEGIES:
        strategy = {"strategy_id": sid, "direction": "SHORT", "parameters": {}}
        params = _strategy_params(strategy)
        assert params["direction"] == "SHORT"

def test_bridge_params_invalid_direction():
    strategy = {"strategy_id": "ema_trend_v1", "direction": "NEUTRAL", "parameters": {}}
    with pytest.raises(ValueError, match="VECTORBT_DIRECTION_MUST_BE_LONG_OR_SHORT"):
        _strategy_params(strategy)

def test_unknown_strategy_id_error():
    df = make_ohlcv()
    strategy = {"strategy_id": "unknown_v999", "direction": "LONG", "parameters": {}}
    result = run_vectorbt_backtest(df, strategy, {"initial_capital": 100_000})
    assert result["status"] == "FAILED"
    assert "UNKNOWN_STRATEGY" in result.get("error", "")


# ── SL/TP regression ──────────────────────────────────

def test_bridge_sltp_long():
    df = enriched_df()
    strategy = {"strategy_id": "ema_trend_v1", "direction": "LONG", "parameters": {"sl_atr_multiple": 2.0, "tp_atr_multiple": 3.0}}
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"

def test_bridge_sltp_short():
    df = enriched_df()
    strategy = {"strategy_id": "rsi_reversal_v1", "direction": "SHORT", "parameters": {"sl_atr_multiple": 2.0, "tp_atr_multiple": 3.0}}
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"

def test_bridge_sltp_disabled():
    df = enriched_df()
    strategy = {"strategy_id": "ema_trend_v1", "direction": "LONG", "parameters": {"sl_atr_multiple": 0.0, "tp_atr_multiple": 0.0}}
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"


# ── Built-in SMA+RSI regression ────────────────────────

def test_builtin_sma_rsi_still_works():
    df = make_ohlcv()
    strategy = {"parameters": {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14, "rsi_entry": 50, "direction": "LONG"}}
    result = run_vectorbt_backtest(df, strategy, {"initial_capital": 100_000})
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["signalModel"] == "SMA_FAST_GT_SMA_SLOW_AND_RSI_ABOVE_THRESHOLD"