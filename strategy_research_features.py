# -*- coding: utf-8 -*-
"""Strategy Research Feature Population — fills FeatureSnapshot from OHLCV.

Single source of truth for indicator computation used by strategy research agents.
Replaces ad-hoc per-adapter population with one deterministic function.

Usage:
    from strategy_research_features import populate_feature_snapshot
    fs = populate_feature_snapshot(ohlcv_df, symbol="THYAO.IS", timeframe="1h")
    ctx = MarketContext(symbol=symbol, timeframe=timeframe, ohlcv_ref=ohlcv_df)
    ctx.feature_snapshot = fs
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from agent_contract import FeatureSnapshot
from signal_engine import add_indicators, DEFAULT_CONFIG
from strategy_registry_v1 import _enrich
from setup_engine_v1 import detect_regime
from smc_structure_v1 import find_swings, structure_events, SWING_ORDER


def populate_feature_snapshot(
    ohlcv: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "",
    observation_timestamp: str = "",
    data_cutoff_timestamp: str = "",
) -> FeatureSnapshot:
    """Compute all indicators and return a populated FeatureSnapshot.

    Deterministic: same OHLCV → same snapshot.
    """
    if ohlcv is None or ohlcv.empty:
        return FeatureSnapshot(
            symbol=symbol, timeframe=timeframe, bar_count=0,
            data_quality_score=0.0,
        )

    df = ohlcv.copy()
    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    n = len(df)

    # --- Indicator computation ---
    # Signal engine base indicators
    try:
        enriched = add_indicators(df, DEFAULT_CONFIG)
    except Exception:
        enriched = df.copy()

    # Strategy registry enrichment (Donchian, SuperTrend, ADX, VWAP, Stoch, SMC, OR)
    try:
        enriched = _enrich(enriched)
    except Exception:
        pass

    last = enriched.iloc[-1] if n > 0 else None
    prev = enriched.iloc[-2] if n > 1 else None

    # --- Populate snapshot ---
    fs = FeatureSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        observation_timestamp=observation_timestamp or str(datetime.now(timezone.utc)),
        data_cutoff_timestamp=data_cutoff_timestamp or (str(df.index[-1]) if n > 0 else ""),
        bar_count=n,
    )

    # Signal engine indicators
    for col, attr in [
        ("SMA_FAST", "sma_fast"), ("SMA_SLOW", "sma_slow"),
        ("EMA_FAST", "ema_fast"), ("EMA_SLOW", "ema_slow"),
        ("RSI", "rsi"), ("ATR", "atr"),
        ("VOLUME_RATIO", "volume_ratio"),
        ("ADX", "adx"), ("MACD", "macd"), ("MACD_SIGNAL", "macd_signal"),
        ("BB_UPPER", "bollinger_upper"), ("BB_LOWER", "bollinger_lower"),
    ]:
        if col in enriched.columns and last is not None:
            val = last.get(col)
            try:
                v = float(val) if val is not None and not pd.isna(val) else None
            except (TypeError, ValueError):
                v = None
            if attr is not None:
                setattr(fs, attr, v if (v is not None and math.isfinite(v)) else None)
            # Track in available_features
            fs.available_features[col] = True

    # ADX trend
    if fs.adx is not None:
        fs.adx_trend = "TRENDING" if fs.adx > 20 else "RANGING"

    # Bollinger available flag
    fs.available_features["BOLL_UPPER"] = "BB_UPPER" in enriched.columns
    fs.available_features["BOLL_LOWER"] = "BB_LOWER" in enriched.columns

    # ATR %
    if fs.atr is not None and last is not None:
        close_val = last.get("Close")
        try:
            c = float(close_val) if close_val is not None and not pd.isna(close_val) else None
            fs.atr_pct = (fs.atr / c * 100) if (c and c > 0 and math.isfinite(fs.atr)) else None
        except (TypeError, ValueError):
            fs.atr_pct = None

    # Strategy registry additions
    for col, attr in [
        ("ST_DIR", None),  # supertrend direction — not a direct snapshot field
        ("ADX", "adx"),  # already handled
        ("PLUS_DI", None), ("MINUS_DI", None),
        ("VWAP", None),
        ("STOCH_K", None), ("STOCH_D", None),
        ("don_high", None), ("don_low", None),
    ]:
        pass  # metadata already in available_features via columns check

    # Donchian availability
    fs.available_features["donchian_high"] = "don_high" in enriched.columns
    fs.available_features["donchian_low"] = "don_low" in enriched.columns

    # Volume anchored
    fs.available_features["VWAP"] = "VWAP" in enriched.columns

    # Regime
    try:
        if last is not None:
            regime_result = detect_regime(last, enriched)
            fs.regime = regime_result.get("regime", "UNKNOWN")
    except Exception:
        fs.regime = "UNKNOWN"

    # Structure / liquidity from SMC
    try:
        atr_val = fs.atr or 0.0
        swings = find_swings(enriched, order=SWING_ORDER) if n >= 5 else []
        events = structure_events(enriched, swings, atr_val) if atr_val > 0 and swings else []
        fs.available_features["structure"] = len(events) > 0 or "structure_events" in enriched.columns

        # Latest structure type
        for ev in reversed(events[-20:]):
            if ev.get("type") in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
                fs.structure_type = ev["type"]
                break

        # Liquidity side
        fs.liquidity_side = _detect_liquidity_side(events, enriched)
        fs.available_features["liquidity"] = bool(fs.liquidity_side)
    except Exception:
        fs.available_features["structure"] = False
        fs.available_features["liquidity"] = False

    # Momentum at entry (simplified: SMA diff percentage)
    if fs.sma_fast is not None and fs.sma_slow is not None and fs.sma_slow != 0:
        fs.momentum_at_entry = (fs.sma_fast - fs.sma_slow) / abs(fs.sma_slow)

    # Volatility context (ATR-based)
    if fs.atr is not None:
        close_val = last.get("Close") if last is not None else None
        try:
            c = float(close_val) if close_val is not None and not pd.isna(close_val) else None
            fs.volatility_context = (fs.atr / c) if (c and c > 0) else None
        except (TypeError, ValueError):
            fs.volatility_context = None

    # Liquidity balance (simplified: volume ratio proxy)
    fs.liquidity_balance = fs.volume_ratio

    fs.null_count = int(df.isnull().sum().sum())

    # Data quality
    total_cells = n * len(df.columns) if n > 0 and len(df.columns) > 0 else 1
    fs.data_quality_score = max(0.0, 1.0 - (fs.null_count / total_cells))

    # Available features tracking
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        fs.available_features[col] = bool(col in df.columns)
        if col in df.columns:
            try:
                fs.null_features[col] = bool(df[col].isnull().any())
            except (ValueError, TypeError):
                fs.null_features[col] = False

    return fs


def _detect_liquidity_side(events: list[dict], df: pd.DataFrame) -> str:
    """Detect liquidity sweep side from structure events."""
    if not events:
        return ""
    for ev in reversed(events[-10:]):
        etype = ev.get("type", "")
        if etype in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
            if etype in ("BOS_UP", "CHoCH_UP"):
                return "above"
            if etype in ("BOS_DOWN", "CHoCH_DOWN"):
                return "below"
    return ""