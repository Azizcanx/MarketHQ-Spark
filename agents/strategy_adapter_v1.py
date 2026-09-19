# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Adapter V1
=============================
Victor BT entegrasyonu için 3 strateji adapter'i.

Her adapter:
  - enrich(df) → df          # indikatör/kolon ekle
  - signal(row) → dict       # {strategy_id, direction, confidence, reason}
  - params_schema() → dict   # parametre spesifikasyonu

Mevcut strateji hesaplamalarını yeniden kullanır:
  - smc_structure_v1 → smc_signal_from_row()
  - opening_range_v1 → or_signal_from_row()
  - strategy_registry_v1 → compute_rs()

Victor BT'ye dokunulmaz.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from smc_structure_v1 import add_smc_structure, smc_signal_from_row
from opening_range_v1 import add_opening_range, or_signal_from_row
from strategy_registry_v1 import compute_rs


# ============================================================
# RS BENCHMARK ADAPTER
# ============================================================

def enrich_rs_benchmark(
    df: pd.DataFrame,
    benchmark: pd.Series | list[float] | None = None,
    rs_window: int = 20,
) -> pd.DataFrame:
    """Benchmark-relative strength hesapla ve kolon ekle."""
    out = df.copy()
    now, trend = compute_rs(df, benchmark, window=rs_window)
    out["RS_NOW"] = now
    out["RS_TREND"] = trend
    return out


def signal_rs_benchmark(row: pd.Series) -> dict[str, Any]:
    """RS benchmark sinyal üret."""
    try:
        rs_trend = float(row.get("RS_TREND"))
    except (TypeError, ValueError):
        rs_trend = 0.0

    if not math.isfinite(rs_trend):
        return {
            "strategy_id": "rs_benchmark_v1",
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "reason": "benchmark yok",
        }

    if rs_trend > 0:
        conf = min(abs(rs_trend) * 30, 1.0)
        return {
            "strategy_id": "rs_benchmark_v1",
            "direction": "LONG",
            "confidence": conf,
            "reason": f"benchmark'a gore guclu ({rs_trend:+.2%})",
        }

    if rs_trend < 0:
        conf = min(abs(rs_trend) * 30, 1.0)
        return {
            "strategy_id": "rs_benchmark_v1",
            "direction": "SHORT",
            "confidence": conf,
            "reason": f"benchmark'a gore zayif ({rs_trend:+.2%})",
        }

    return {
        "strategy_id": "rs_benchmark_v1",
        "direction": "NEUTRAL",
        "confidence": 0.0,
        "reason": "benchmark'a esit",
    }


def params_schema_rs_benchmark() -> dict[str, Any]:
    return {
        "strategy_id": "rs_benchmark_v1",
        "family": "relative",
        "requires_benchmark": True,
        "params": {
            "rs_window": {"type": "int", "default": 20, "min": 5, "max": 60},
        },
    }


# ============================================================
# SMC STRUCTURE ADAPTER
# ============================================================

def enrich_smc(df: pd.DataFrame) -> pd.DataFrame:
    """SMC yapı hesapla ve kolon ekle."""
    return add_smc_structure(df)


def signal_smc(row: pd.Series) -> dict[str, Any]:
    """SMC sinyal üret (mevcut smc_signal_from_row'ı kullan)."""
    res = smc_signal_from_row(row)
    return {
        "strategy_id": "smc_structure_v1",
        "direction": res.get("direction", "NEUTRAL"),
        "confidence": res.get("confidence", 0.0),
        "reason": res.get("reason", "SMC yok"),
    }


def params_schema_smc() -> dict[str, Any]:
    return {
        "strategy_id": "smc_structure_v1",
        "family": "structure",
        "requires_benchmark": False,
        "params": {},
    }


# ============================================================
# OPENING RANGE ADAPTER
# ============================================================

def enrich_or(df: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    """Acilis araligi hesapla ve kolon ekle."""
    return add_opening_range(df, lookback=lookback)


def signal_or(row: pd.Series) -> dict[str, Any]:
    """OR sinyal üret (mevcut or_signal_from_row'ı kullan)."""
    res = or_signal_from_row(row)
    return {
        "strategy_id": "or_breakout_v1",
        "direction": res.get("direction", "NEUTRAL"),
        "confidence": res.get("confidence", 0.0),
        "reason": res.get("reason", "acilis araligi yok"),
    }


def params_schema_or() -> dict[str, Any]:
    return {
        "strategy_id": "or_breakout_v1",
        "family": "breakout",
        "requires_benchmark": False,
        "params": {
            "lookback": {"type": "int", "default": 30, "min": 5, "max": 60},
        },
    }


# ============================================================
# REGISTRY
# ============================================================

ADAPTERS: dict[str, dict[str, Any]] = {
    "rs_benchmark_v1": {
        "enrich": enrich_rs_benchmark,
        "signal": signal_rs_benchmark,
        "params_schema": params_schema_rs_benchmark,
        "requires_benchmark": True,
    },
    "smc_structure_v1": {
        "enrich": enrich_smc,
        "signal": signal_smc,
        "params_schema": params_schema_smc,
        "requires_benchmark": False,
    },
    "or_breakout_v1": {
        "enrich": enrich_or,
        "signal": signal_or,
        "params_schema": params_schema_or,
        "requires_benchmark": False,
    },
}


def get_adapter(strategy_id: str) -> dict[str, Any] | None:
    return ADAPTERS.get(strategy_id)


def run_adapter(strategy_id: str, df: pd.DataFrame, **kwargs) -> dict[str, Any]:
    """Tek çağrışta enrich + signal."""
    adapter = ADAPTERS.get(strategy_id)
    if adapter is None:
        raise ValueError(f"BILINMIYON_STRATEJI: {strategy_id}")

    enrich_fn = adapter["enrich"]
    signal_fn = adapter["signal"]

    if strategy_id == "rs_benchmark_v1":
        enriched = enrich_fn(df, benchmark=kwargs.get("benchmark"))
    elif strategy_id == "or_breakout_v1":
        enriched = enrich_fn(df, lookback=kwargs.get("lookback", 30))
    else:
        enriched = enrich_fn(df)

    row = enriched.iloc[-1]
    result = signal_fn(row)
    result["enriched_bars"] = len(enriched)
    return result