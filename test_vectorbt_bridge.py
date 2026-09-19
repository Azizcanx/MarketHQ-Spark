"""Tests for VectorBT engine generic strategy bridge."""

import pandas as pd
import numpy as np
import pytest

from agents.vectorbt_engine_v1 import (
    _strategy_params,
    _signals,
    _adapter_signals,
    _run_single,
    _candidate_parameters,
    run_vectorbt_backtest,
)


def make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "Open": close - rng.uniform(-0.5, 0.5, n),
            "High": close + rng.uniform(0.1, 2, n),
            "Low": close - rng.uniform(0.1, 2, n),
            "Close": close,
            "Volume": rng.uniform(1_000_000, 5_000_000, n),
        },
        index=idx,
    )


# ── 1. Direct SMA+RSI strategies ────────────────────────

def test_sma_rsi_long_signal():
    """Mevcut SMA+RSI LONG davranışı bozulmamali."""
    df = make_ohlcv()
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "LONG",
        }
    }
    params = _strategy_params(strategy)
    close = df["Close"]
    entries, exits = _signals(close, params)
    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert len(entries) == len(df)


def test_sma_rsi_short_signal():
    """Mevcut SMA+RSI SHORT destegi."""
    df = make_ohlcv()
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "SHORT",
        }
    }
    params = _strategy_params(strategy)
    entries, exits = _signals(df["Close"], params)
    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)


def test_sma_rsi_builtin_validation():
    """Gecerli SMA+RSI parametreleri kabul edilmeli."""
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "LONG",
        }
    }
    params = _strategy_params(strategy)
    assert params["sma_fast"] == 5
    assert params["sma_slow"] == 20
    assert params["direction"] == "LONG"


def test_sma_rsi_invalid_params_rejected():
    """Gecersiz SMA+RSI parametreleri reddedilmeli."""
    strategy = {
        "parameters": {
            "sma_fast": 0,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
        }
    }
    with pytest.raises(ValueError, match="VECTORBT_SMA_FAST_REQUIRED"):
        _strategy_params(strategy)


# ── 2. Custom adapters ──────────────────────────────────

def test_adapter_smc_structure():
    """smc_structure_v1 adapter calismali."""
    df = make_ohlcv()
    strategy = {
        "strategy_id": "smc_structure_v1",
        "direction": "LONG",
        "parameters": {},
    }
    params = _strategy_params(strategy)
    assert params["strategy_id"] == "smc_structure_v1"
    entries, exits = _adapter_signals(df, params, "LONG")
    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert len(entries) == len(df)


def test_adapter_or_breakout():
    """or_breakout_v1 adapter calismali."""
    df = make_ohlcv()
    strategy = {
        "strategy_id": "or_breakout_v1",
        "direction": "LONG",
        "parameters": {"lookback": 30},
    }
    params = _strategy_params(strategy)
    assert params["lookback"] == 30
    entries, exits = _adapter_signals(df, params, "LONG")
    assert isinstance(entries, pd.Series)
    assert len(entries) == len(df)


def test_adapter_rs_benchmark():
    """rs_benchmark_v1 adapter calismali."""
    df = make_ohlcv()
    rng = np.random.default_rng(42)
    benchmark = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, len(df))), index=df.index)
    strategy = {
        "strategy_id": "rs_benchmark_v1",
        "direction": "LONG",
        "parameters": {"benchmark": benchmark.tolist()},
    }
    params = _strategy_params(strategy)
    assert params["strategy_id"] == "rs_benchmark_v1"
    entries, exits = _adapter_signals(df, params, "LONG")
    assert isinstance(entries, pd.Series)
    assert len(entries) == len(df)


# ── 3. LONG / SHORT ─────────────────────────────────────

def test_adapter_long_short_both():
    """Her adapter LONG ve SHORT desteklemeli."""
    df = make_ohlcv()
    bench_rng = np.random.default_rng(7)
    bench = (100 + np.cumsum(bench_rng.normal(0, 0.5, len(df)))).tolist()
    for sid in ("smc_structure_v1", "or_breakout_v1", "rs_benchmark_v1"):
        for direction in ("LONG", "SHORT"):
            strategy = {
                "strategy_id": sid,
                "direction": direction,
                "parameters": {},
            }
            if sid == "rs_benchmark_v1":
                # rs_benchmark deliberately produces zero signals without a
                # benchmark (safe default); give it one for signal coverage.
                strategy["parameters"] = {"benchmark": bench}
            params = _strategy_params(strategy)
            entries, exits = _adapter_signals(df, params, direction)
            # En az bir entry veya exit olmalı
            assert entries.any() or exits.any()


def test_builtin_long_short():
    """SMA+RSI hem LONG hem SHORT calismali."""
    df = make_ohlcv()
    for direction in ("LONG", "SHORT"):
        strategy = {
            "parameters": {
                "sma_fast": 5,
                "sma_slow": 20,
                "rsi_period": 14,
                "rsi_entry": 50,
                "direction": direction,
            }
        }
        params = _strategy_params(strategy)
        entries, exits = _signals(df["Close"], params)
        assert isinstance(entries, pd.Series)
        assert isinstance(exits, pd.Series)


# ── 4. SL/TP ────────────────────────────────────────────

def test_sltp_long():
    """LONG stratejide ATR SL/TP hesaplaniyor."""
    df = make_ohlcv()
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "LONG",
            "sl_atr_multiple": 2.0,
            "tp_atr_multiple": 3.0,
        }
    }
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"
    assert result["metrics"]["trade_count"] >= 0


def test_sltp_short():
    """SHORT stratejide ATR SL/TP hesaplaniyor."""
    df = make_ohlcv()
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "SHORT",
            "sl_atr_multiple": 2.0,
            "tp_atr_multiple": 3.0,
        }
    }
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"


def test_sltp_disabled():
    """SL/TP kapaliyken mevcut davranis korunmeli."""
    df = make_ohlcv()
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "LONG",
            "sl_atr_multiple": 0.0,
            "tp_atr_multiple": 0.0,
        }
    }
    params = _strategy_params(strategy)
    result = _run_single(df, params, 100_000, 0.1, 0.05)
    assert result["status"] == "COMPLETED"


# ── 5. Unknown strategy ──────────────────────────────────

def test_unknown_strategy_id():
    """Bilinmeyen strategy_id net hata dondurmeli."""
    df = make_ohlcv()
    strategy = {
        "strategy_id": "unknown_v999",
        "direction": "LONG",
        "parameters": {},
    }
    result = run_vectorbt_backtest(
        df, strategy,
        {"initial_capital": 100_000},
    )
    assert result["status"] == "FAILED"
    assert "UNKNOWN_STRATEGY" in result.get("error", "")
    assert "unknown_v999" in result.get("error", "")


# ── 6. SMA+RSI regression ───────────────────────────────

def test_sma_rsi_regression_long():
    """SMA+RSI LONG backtest regression — boyle bir sonuç cikmalidir."""
    df = make_ohlcv(n=100)
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "LONG",
        }
    }
    result = run_vectorbt_backtest(
        df, strategy,
        {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05},
    )
    assert result["status"] == "COMPLETED"
    assert result["engine"] == "VECTORBT"
    assert result["semantics"]["signalModel"] == "SMA_FAST_GT_SMA_SLOW_AND_RSI_ABOVE_THRESHOLD"
    assert result["semantics"]["direction"] == "LONG"


def test_sma_rsi_regression_short():
    """SMA+RSI SHORT backtest regression."""
    df = make_ohlcv(n=100)
    strategy = {
        "parameters": {
            "sma_fast": 5,
            "sma_slow": 20,
            "rsi_period": 14,
            "rsi_entry": 50,
            "direction": "SHORT",
        }
    }
    result = run_vectorbt_backtest(
        df, strategy,
        {"initial_capital": 100_000},
    )
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "SHORT"


# ── 7. Candidate parameters ─────────────────────────────

def test_candidate_params_adapter():
    """Adapter strateji sweep parametreleri duzgun olmalidir."""
    base = {"strategy_id": "smc_structure_v1", "direction": "LONG", "sl_atr_multiple": 2.0}
    sweep = {"direction": ["LONG", "SHORT"]}
    candidates = _candidate_parameters(base, sweep, None)
    assert len(candidates) == 2
    assert all("strategy_id" in c for c in candidates)


def test_candidate_params_builtin():
    """Built-in strateji sweep parametreleri duzgun olmalidir."""
    base = {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14, "rsi_entry": 50}
    sweep = {"sma_fast": [5, 10], "sma_slow": [20, 30]}
    candidates = _candidate_parameters(base, sweep, None)
    assert len(candidates) == 4