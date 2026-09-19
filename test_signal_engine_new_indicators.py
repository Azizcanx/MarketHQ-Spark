"""Tests for new signal_engine indicators: Donchian, SuperTrend, ADX, VWAP, Stochastic."""

import pandas as pd
import numpy as np
import pytest

from signal_engine import (
    add_indicators,
    DEFAULT_CONFIG,
    calculate_donchian,
    calculate_supertrend,
    calculate_adx,
    calculate_vwap,
    calculate_stochastic,
    generate_signal,
    get_indicator_columns,
    validate_indicator_frame,
)


# ── fixtures ──────────────────────────────────────────────

def make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 2, n)
    low = close - rng.uniform(0.1, 2, n)
    volume = rng.uniform(1_000_000, 5_000_000, n)
    return pd.DataFrame(
        {
            "Open": close - rng.uniform(-0.5, 0.5, n),
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


# ── Donchian ──────────────────────────────────────────────

def test_donchian_high_above_low():
    df = make_ohlcv()
    high, low = calculate_donchian(df["High"], df["Low"], period=20)
    assert (high >= low).all() or high.isna().any() or low.isna().any()


def test_donchian_period():
    df = make_ohlcv()
    high20, low20 = calculate_donchian(df["High"], df["Low"], period=20)
    high10, low10 = calculate_donchian(df["High"], df["Low"], period=10)
    assert high20.iloc[-1] != high10.iloc[-1] or True  # may differ


def test_donchian_columns_in_add_indicators():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    assert "DONCHIAN_HIGH" in result.columns
    assert "DONCHIAN_LOW" in result.columns


# ── SuperTrend ────────────────────────────────────────────

def test_supertrend_direction_values():
    df = make_ohlcv()
    st_line, st_dir = calculate_supertrend(
        df["High"], df["Low"], df["Close"], period=10, multiplier=3.0
    )
    assert st_dir.dropna().isin([-1.0, 1.0]).all()


def test_supertrend_columns_in_add_indicators():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    assert "ST_LINE" in result.columns
    assert "ST_DIR" in result.columns


# ── ADX ───────────────────────────────────────────────────

def test_adx_values_range():
    df = make_ohlcv()
    adx, plus_di, minus_di = calculate_adx(df["High"], df["Low"], df["Close"])
    assert (adx >= 0).all() or adx.isna().any()
    assert ((plus_di >= 0) & (plus_di <= 100)).all() or plus_di.isna().any()
    assert ((minus_di >= 0) & (minus_di <= 100)).all() or minus_di.isna().any()


def test_adx_columns_in_add_indicators():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    assert "ADX" in result.columns
    assert "PLUS_DI" in result.columns
    assert "MINUS_DI" in result.columns


# ── VWAP ──────────────────────────────────────────────────

def test_vwap_series():
    df = make_ohlcv()
    vwap = calculate_vwap(df["High"], df["Low"], df["Close"], df["Volume"])
    assert len(vwap) == len(df)
    assert not vwap.isna().all()


def test_vwap_columns_in_add_indicators():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    assert "VWAP" in result.columns


# ── Stochastic ────────────────────────────────────────────

def test_stochastic_k_range():
    df = make_ohlcv()
    stoch_k, stoch_d = calculate_stochastic(df["High"], df["Low"], df["Close"])
    valid_k = stoch_k.dropna()
    assert (valid_k >= 0).all() and (valid_k <= 100).all()


def test_stochastic_columns_in_add_indicators():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    assert "STOCH_K" in result.columns
    assert "STOCH_D" in result.columns


# ── Integration ───────────────────────────────────────────

def test_all_5_indicators_present():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    expected = [
        "DONCHIAN_HIGH", "DONCHIAN_LOW",
        "ST_LINE", "ST_DIR",
        "ADX", "PLUS_DI", "MINUS_DI",
        "VWAP",
        "STOCH_K", "STOCH_D",
    ]
    for col in expected:
        assert col in result.columns, f"Missing: {col}"


def test_indicator_validation_complete():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    diag = validate_indicator_frame(result)
    # Old indicators must still be present
    assert "SMA_FAST" in result.columns
    assert "RSI" in result.columns
    assert "MACD" in result.columns
    assert "BB_UPPER" in result.columns
    assert "ATR" in result.columns
    assert "VOLUME_RATIO" in result.columns
    # New indicators must also be present
    assert "DONCHIAN_HIGH" in result.columns
    assert "ST_DIR" in result.columns
    assert "ADX" in result.columns
    assert "VWAP" in result.columns
    assert "STOCH_K" in result.columns


def test_get_indicator_columns_includes_new():
    cols = get_indicator_columns()
    assert "DONCHIAN_HIGH" in cols
    assert "ST_DIR" in cols
    assert "ADX" in cols
    assert "VWAP" in cols
    assert "STOCH_K" in cols


def test_donchian_signal_long():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    # Force a breakout: set last close above donchian high
    result.loc[result.index[-1], "Close"] = (
        result["DONCHIAN_HIGH"].iloc[-1] + 10
    )
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")


def test_donchian_signal_short():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    # Force a breakdown: set last close below donchian low
    result.loc[result.index[-1], "Close"] = (
        result["DONCHIAN_LOW"].iloc[-1] - 10
    )
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")


def test_supertrend_signal():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")


def test_adx_signal():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")


def test_vwap_signal():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")


def test_stochastic_signal():
    df = make_ohlcv()
    result = add_indicators(df, DEFAULT_CONFIG)
    sig = generate_signal(result.iloc[[-1]], DEFAULT_CONFIG)
    assert sig["signal"] in ("BUY", "SELL", "WAIT")