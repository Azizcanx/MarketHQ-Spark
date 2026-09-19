"""Tests for strategy_adapter_v1: rs_benchmark, smc_structure, or_breakout."""

import pandas as pd
import numpy as np
import pytest

from agents.strategy_adapter_v1 import (
    ADAPTERS,
    get_adapter,
    run_adapter,
    enrich_rs_benchmark,
    signal_rs_benchmark,
    params_schema_rs_benchmark,
    enrich_smc,
    signal_smc,
    params_schema_smc,
    enrich_or,
    signal_or,
    params_schema_or,
)


def make_ohlcv(n: int = 50, seed: int = 42) -> pd.DataFrame:
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


# ── Registry ──────────────────────────────────────────────

def test_adapter_registry_has_3():
    assert set(ADAPTERS.keys()) == {
        "rs_benchmark_v1",
        "smc_structure_v1",
        "or_breakout_v1",
    }


def test_get_adapter_exists():
    for sid in ADAPTERS:
        adapter = get_adapter(sid)
        assert adapter is not None
        assert "enrich" in adapter
        assert "signal" in adapter
        assert "params_schema" in adapter


def test_get_adapter_missing():
    assert get_adapter("unknown_v1") is None


# ── RS Benchmark ──────────────────────────────────────────

def test_rs_benchmark_enrich_adds_columns():
    df = make_ohlcv()
    benchmark = pd.Series(100 + np.cumsum(np.random.default_rng(42).normal(0, 0.5, len(df))), index=df.index)
    result = enrich_rs_benchmark(df, benchmark=benchmark)
    assert "RS_NOW" in result.columns
    assert "RS_TREND" in result.columns


def test_rs_benchmark_signal_direction():
    df = make_ohlcv()
    rng = np.random.default_rng(42)
    benchmark = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, len(df))), index=df.index)
    result = enrich_rs_benchmark(df, benchmark=benchmark)
    sig = signal_rs_benchmark(result.iloc[-1])
    assert sig["strategy_id"] == "rs_benchmark_v1"
    assert sig["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert 0.0 <= sig["confidence"] <= 1.0


def test_rs_benchmark_no_benchmark():
    df = make_ohlcv()
    result = enrich_rs_benchmark(df, benchmark=None)
    sig = signal_rs_benchmark(result.iloc[-1])
    assert sig["direction"] == "NEUTRAL"
    assert sig["confidence"] == 0.0


def test_rs_benchmark_params_schema():
    schema = params_schema_rs_benchmark()
    assert schema["strategy_id"] == "rs_benchmark_v1"
    assert schema["requires_benchmark"] is True
    assert "rs_window" in schema["params"]


# ── SMC Structure ─────────────────────────────────────────

def test_smc_enrich_adds_columns():
    df = make_ohlcv()
    result = enrich_smc(df)
    assert "SMC_DIR" in result.columns
    assert "SMC_CONF" in result.columns
    assert "SMC_REASON" in result.columns


def test_smc_signal_direction():
    df = make_ohlcv()
    result = enrich_smc(df)
    sig = signal_smc(result.iloc[-1])
    assert sig["strategy_id"] == "smc_structure_v1"
    assert sig["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert 0.0 <= sig["confidence"] <= 1.0


def test_smc_params_schema():
    schema = params_schema_smc()
    assert schema["strategy_id"] == "smc_structure_v1"
    assert schema["requires_benchmark"] is False


# ── Opening Range ─────────────────────────────────────────

def test_or_enrich_adds_columns():
    df = make_ohlcv()
    result = enrich_or(df)
    assert "OR_DIR" in result.columns
    assert "OR_CONF" in result.columns
    assert "OR_REASON" in result.columns


def test_or_signal_direction():
    df = make_ohlcv()
    result = enrich_or(df)
    sig = signal_or(result.iloc[-1])
    assert sig["strategy_id"] == "or_breakout_v1"
    assert sig["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert 0.0 <= sig["confidence"] <= 1.0


def test_or_params_schema():
    schema = params_schema_or()
    assert schema["strategy_id"] == "or_breakout_v1"
    assert schema["requires_benchmark"] is False
    assert "lookback" in schema["params"]


# ── Integration ───────────────────────────────────────────

def test_run_adapter_smc():
    df = make_ohlcv()
    result = run_adapter("smc_structure_v1", df)
    assert result["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert result["enriched_bars"] == len(df)


def test_run_adapter_or():
    df = make_ohlcv()
    result = run_adapter("or_breakout_v1", df)
    assert result["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert result["enriched_bars"] == len(df)


def test_run_adapter_rs():
    df = make_ohlcv()
    rng = np.random.default_rng(42)
    benchmark = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, len(df))), index=df.index)
    result = run_adapter("rs_benchmark_v1", df, benchmark=benchmark)
    assert result["direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert result["enriched_bars"] == len(df)


def test_run_adapter_unknown():
    df = make_ohlcv()
    with pytest.raises(ValueError, match="BILINMIYON_STRATEJI"):
        run_adapter("unknown_v1", df)


def test_all_adapters_produce_valid_signal():
    df = make_ohlcv()
    rng = np.random.default_rng(42)
    benchmark = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, len(df))), index=df.index)

    for sid, adapter in ADAPTERS.items():
        if sid == "rs_benchmark_v1":
            result = run_adapter(sid, df, benchmark=benchmark)
        elif sid == "or_breakout_v1":
            result = run_adapter(sid, df, lookback=30)
        else:
            result = run_adapter(sid, df)

        assert result["direction"] in ("LONG", "SHORT", "NEUTRAL")
        assert result["enriched_bars"] == len(df)