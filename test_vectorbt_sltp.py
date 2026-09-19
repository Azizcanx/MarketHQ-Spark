"""Tests for VectorBT engine SL/TP and LONG/SHORT support."""

import pandas as pd
import pytest

from agents.vectorbt_engine_v1 import (
    _compute_atr,
    _signals,
    _run_single,
    _strategy_params,
    run_vectorbt_backtest,
)


def make_ohlcv(n: int = 300, base_price: float = 300.0, trend: float = 0.05) -> pd.DataFrame:
    """Generate synthetic OHLCV data with a slight trend."""
    import numpy as np

    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = base_price * (1 + trend * np.arange(n) / n + rng.normal(0, 0.02, n).cumsum() * 0.01)
    high = close * (1 + rng.uniform(0.001, 0.01, n))
    low = close * (1 - rng.uniform(0.001, 0.01, n))
    volume = rng.integers(1_000_000, 10_000_000, n)
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


# ─── ATR ────────────────────────────────────────────────────────────────────

def test_atr_computed():
    data = make_ohlcv(200)
    atr = _compute_atr(data, period=14)
    assert len(atr) == 200
    assert atr.iloc[14:].notna().all()
    assert (atr.iloc[14:] > 0).all()


def test_atr_from_dataframe():
    data = make_ohlcv(100, base_price=100.0)
    atr = _compute_atr(data, period=10)
    assert atr.iloc[10] > 0


# ─── Strategy params ────────────────────────────────────────────────────────

def test_params_defaults_to_long():
    params = _strategy_params({"parameters": {"sma_fast": 10, "sma_slow": 50, "rsi_period": 14, "rsi_entry": 55}})
    assert params["direction"] == "LONG"
    assert params["sl_atr_multiple"] == 0.0
    assert params["tp_atr_multiple"] == 0.0


def test_params_short_direction():
    params = _strategy_params({"parameters": {"sma_fast": 10, "sma_slow": 50, "rsi_period": 14, "rsi_entry": 55, "direction": "SHORT"}})
    assert params["direction"] == "SHORT"


def test_params_sl_tp():
    params = _strategy_params({"parameters": {"sma_fast": 10, "sma_slow": 50, "rsi_period": 14, "rsi_entry": 55, "sl_atr_multiple": 2.0, "tp_atr_multiple": 3.0}})
    assert params["sl_atr_multiple"] == 2.0
    assert params["tp_atr_multiple"] == 3.0


def test_params_invalid_direction():
    with pytest.raises(ValueError, match="VECTORBT_DIRECTION_MUST_BE_LONG_OR_SHORT"):
        _strategy_params({"parameters": {"sma_fast": 10, "sma_slow": 50, "rsi_period": 14, "rsi_entry": 55, "direction": "BOTH"}})


# ─── Signals ────────────────────────────────────────────────────────────────

def test_signals_long_default():
    data = make_ohlcv(200)
    close = data["Close"]
    params = {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14, "rsi_entry": 50, "direction": "LONG"}
    entries, exits = _signals(close, params)
    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert len(entries) == len(close)


def test_signals_short_direction():
    data = make_ohlcv(200)
    close = data["Close"]
    params = {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14, "rsi_entry": 50, "direction": "SHORT"}
    entries, exits = _signals(close, params)
    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert len(entries) == len(close)


# ─── LONG SL / TP ────────────────────────────────────────────────────────────

def test_long_sl_triggered():
    """LONG'da SL seviyeye düşülürse pozisyon kapanır."""
    data = make_ohlcv(200, base_price=300.0, trend=0.0)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
            "sl_atr_multiple": 1.5, "tp_atr_multiple": 0.0,
            "direction": "LONG",
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "LONG"
    assert result["semantics"]["riskControlsApplied"] is True
    assert "stop_loss_atr" not in result["semantics"]["riskControlsNotApplied"]


def test_long_tp_triggered():
    """LONG'da TP seviyeye ulaşılırsa pozisyon kapanır."""
    data = make_ohlcv(200, base_price=300.0, trend=0.1)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
            "sl_atr_multiple": 0.0, "tp_atr_multiple": 2.0,
            "direction": "LONG",
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "LONG"
    assert result["semantics"]["riskControlsApplied"] is True
    assert "take_profit_atr" not in result["semantics"]["riskControlsNotApplied"]


# ─── SHORT SL / TP ───────────────────────────────────────────────────────────

def test_short_sl_triggered():
    """SHORT'ta SL seviyeye yukarı çıkılırsa pozisyon kapanır."""
    data = make_ohlcv(200, base_price=300.0, trend=-0.05)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
            "sl_atr_multiple": 1.5, "tp_atr_multiple": 0.0,
            "direction": "SHORT",
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "SHORT"
    assert result["semantics"]["riskControlsApplied"] is True


def test_short_tp_triggered():
    """SHORT'ta TP seviyeye aşağı düşülürse pozisyon kapanır."""
    data = make_ohlcv(200, base_price=300.0, trend=-0.1)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
            "sl_atr_multiple": 0.0, "tp_atr_multiple": 2.0,
            "direction": "SHORT",
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "SHORT"
    assert result["semantics"]["riskControlsApplied"] is True


# ─── SL/TP kapalı — mevcut davranış ─────────────────────────────────────────

def test_no_sl_tp_preserves_original_behavior():
    """SL/TP kapalıyken (default 0.0) mevcut SMA+RSI davranışı korunmalı."""
    data = make_ohlcv(200, base_price=300.0, trend=0.05)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    assert result["semantics"]["direction"] == "LONG"
    assert result["semantics"]["riskControlsApplied"] is False
    assert "stop_loss_atr" in result["semantics"]["riskControlsNotApplied"]
    assert "take_profit_atr" in result["semantics"]["riskControlsNotApplied"]
    # LONG only → short_positions applied (not in not-applied list)
    assert "short_positions" not in result["semantics"]["riskControlsNotApplied"]


def test_no_sl_tp_returns_series():
    """SL/TP kapalıyken returnSeries ve equitySeries dönmeli."""
    data = make_ohlcv(200, base_price=300.0, trend=0.05)
    strategy = {
        "parameters": {
            "sma_fast": 5, "sma_slow": 20,
            "rsi_period": 14, "rsi_entry": 50,
        }
    }
    backtest_config = {"initial_capital": 100_000, "commission_percent": 0.10, "slippage_percent": 0.05}
    result = run_vectorbt_backtest(data=data, strategy=strategy, backtest_config=backtest_config)
    assert result["status"] == "COMPLETED"
    best = result.get("best")
    assert best is not None
    assert "returnSeries" in best
    assert "equitySeries" in best
    assert len(best["returnSeries"]) > 0
    assert len(best["equitySeries"]) > 0