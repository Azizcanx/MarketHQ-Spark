# -*- coding: utf-8 -*-
"""
MarketHQ Setup Engine V1 (research-only, no live trading).

Girdi: OHLCV DataFrame
Cikti: setup dict -> entry zone, invalidation, target, timeframe,
       destekleyen/karsit stratejiler, rejim, agreement.

Bagimlilik: strategy_registry_v1 + signal_engine (ATR, entry price).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from signal_engine import add_indicators, DEFAULT_CONFIG, calculate_risk_levels
from strategy_registry_v1 import run_all_strategies_df, agreement_summary, add_donchian


def _adx_like(df: pd.DataFrame, period: int = 14) -> float:
    """ADX-like trend strength from OHLCV — no external dependency."""
    try:
        import numpy as np
        high = df["High"].astype(float).to_numpy()
        low = df["Low"].astype(float).to_numpy()
        close = df["Close"].astype(float).to_numpy()
        n = len(df)
        if n < period + 1:
            return 0.0
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(period).mean().to_numpy()
        up_move = high - np.roll(high, 1)
        dn_move = np.roll(low, 1) - low
        plus_dm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
        plus_di = 100.0 * pd.Series(plus_dm).rolling(period).mean().to_numpy() / atr
        minus_di = 100.0 * pd.Series(minus_dm).rolling(period).mean().to_numpy() / atr
        dx = np.where((plus_di + minus_di) > 0, 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0.0)
        adx = float(pd.Series(dx).rolling(period).mean().iloc[-1])
        return adx if np.isfinite(adx) else 0.0
    except Exception:
        return 0.0


def _trend_strength(last: pd.Series) -> tuple[float, float]:
    """Returns (adx_value, atr_pct)."""
    import math
    c = float(last.get("Close", 0))
    atr = float(last.get("ATR", 0) or 0)
    atr_pct = (atr / c * 100) if c > 0 and atr > 0 and math.isfinite(atr) else 0.0
    return (0.0, atr_pct)


def detect_regime(last: pd.Series, df: pd.DataFrame | None = None) -> dict[str, Any]:
    """
    Multi-factor regime detection.

    Returns dict with keys: regime, confidence, detail, factors.
    Replaces single-string SMA-cross-only detection.
    """
    import math
    try:
        c = float(last["Close"])
        sf = float(last["SMA_FAST"])
        ss = float(last["SMA_SLOW"])
    except (TypeError, ValueError, KeyError):
        return {"regime": "UNKNOWN", "confidence": 0.0, "detail": "veri eksik", "factors": {}}

    if any(not math.isfinite(x) for x in (c, sf, ss)):
        return {"regime": "UNKNOWN", "confidence": 0.0, "detail": "gecersiz veri", "factors": {}}

    # --- Trend direction ---
    if c > sf > ss:
        trend_dir = "UP"
    elif c < sf < ss:
        trend_dir = "DOWN"
    else:
        trend_dir = "NEUTRAL"

    # --- ADX-like trend strength ---
    adx_val = 0.0
    if df is not None and len(df) >= 20:
        adx_val = _adx_like(df)
    # Fallback: SMA separation ratio as proxy
    if adx_val == 0.0 and ss > 0:
        adx_val = abs(sf - ss) / ss * 100  # proxy: % separation between SMAs

    # --- ATR normalized volatility ---
    atr = float(last.get("ATR", 0) or 0)
    atr_pct = (atr / c * 100) if c > 0 and atr > 0 and math.isfinite(atr) else 0.0

    # --- Volume confirmation ---
    vol_ratio = float(last.get("VOLUME_RATIO", 0) or 0)
    vol_confirmed = vol_ratio > 1.0 if math.isfinite(vol_ratio) else False

    # --- Price structure (HH/HL vs LH/LL in last ~10 bars) ---
    hh_count = 0
    ll_count = 0
    hl_count = 0
    lh_count = 0
    if df is not None and len(df) >= 10:
        recent = df.tail(10)
        highs = recent["High"].to_numpy()
        lows = recent["Low"].to_numpy()
        for i in range(2, len(recent) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                if lows[i] > lows[i - 1] and lows[i] > lows[i + 1]:
                    hh_count += 1
                else:
                    hl_count += 1
            elif lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    lh_count += 1
                else:
                    ll_count += 1

    structure_score = hh_count - ll_count  # positive = bullish structure

    # --- ADX thresholds ---
    strong_threshold = 25.0
    weak_threshold = 15.0

    factors = {
        "trend_dir": trend_dir,
        "adx": round(adx_val, 1),
        "atr_pct": round(atr_pct, 2),
        "vol_ratio": round(vol_ratio, 2) if math.isfinite(vol_ratio) else None,
        "vol_confirmed": vol_confirmed,
        "hh_count": hh_count,
        "ll_count": ll_count,
        "structure_score": structure_score,
    }

    # --- Regime classification ---
    confidence = 0.5

    # If ADX says strong trend but SMA cross says NEUTRAL, re-classify direction
    # from price structure instead
    effective_dir = trend_dir
    if trend_dir == "NEUTRAL" and adx_val >= weak_threshold:
        if structure_score > 0:
            effective_dir = "UP"
        elif structure_score < 0:
            effective_dir = "DOWN"

    if effective_dir == "UP":
        if adx_val >= strong_threshold and vol_confirmed:
            regime = "UPTREND_STRONG"
            confidence = 0.9
        elif adx_val >= strong_threshold or (adx_val >= weak_threshold and vol_confirmed):
            regime = "UPTREND_WEAK"
            confidence = 0.7
        else:
            regime = "UPTREND_WEAK"
            confidence = 0.6
    elif effective_dir == "DOWN":
        if adx_val >= strong_threshold and vol_confirmed:
            regime = "DOWNTREND_STRONG"
            confidence = 0.9
        elif adx_val >= strong_threshold or (adx_val >= weak_threshold and vol_confirmed):
            regime = "DOWNTREND_WEAK"
            confidence = 0.7
        else:
            regime = "DOWNTREND_WEAK"
            confidence = 0.6
    else:
        # NEUTRAL — check volatility character
        if atr_pct > 1.5:
            # High vol in range — could be expanding
            if adx_val > 15 and structure_score != 0:
                regime = "EXPANDING_VOLATILITY"
                confidence = 0.75
            else:
                regime = "RANGE_HIGH_VOL"
                confidence = 0.65
        else:
            regime = "RANGE_LOW_VOL"
            confidence = 0.6

    # Detail string
    detail_parts = [
        f"dir={trend_dir}",
        f"adx={adx_val:.1f}",
        f"atr%={atr_pct:.2f}",
        f"vol={vol_ratio:.2f}" if math.isfinite(vol_ratio) else "vol=N/A",
        f"struct_score={structure_score}",
    ]
    detail = " | ".join(detail_parts)

    return {
        "regime": regime,
        "confidence": confidence,
        "detail": detail,
        "factors": factors,
    }


def build_setup(df: pd.DataFrame, timeframe: str = "1h", config: dict | None = None, benchmark: pd.Series | list[float] | None = None, symbol: str = "UNKNOWN") -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    enriched = add_donchian(add_indicators(df, config))
    last = enriched.iloc[-1]
    results = run_all_strategies_df(df, config, benchmark=benchmark)
    regime_result = detect_regime(last, df)
    regime = regime_result.get("regime", "UNKNOWN") if isinstance(regime_result, dict) else regime_result
    agree = agreement_summary(results, regime=regime)

    entry = float(last["Close"])
    atr = last.get("ATR")
    try:
        atr = float(atr)
    except (TypeError, ValueError):
        atr = None

    direction = agree["consensus"]  # LONG / SHORT / NO_CONSENSUS
    supporting = [r["strategy_id"] for r in results if r["direction"] == direction]
    opposing = [r["strategy_id"] for r in results if r["direction"] in ("LONG", "SHORT") and r["direction"] != direction]

    setup: dict[str, Any] = {
        "setup_id": f"setup_{timeframe}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_price": entry,
        "entry_zone": [entry - 0.25 * atr, entry + 0.25 * atr] if atr else [entry, entry],
        "atr": atr,
        "regime": regime,
        "regime_detail": regime_result if isinstance(regime_result, dict) else {"regime": regime},
        "supporting": supporting,
        "opposing": opposing,
        "agreement": agree,
        "strategies": results,
        "research_only": True,
    }

    if direction in ("LONG", "SHORT"):
        sig = "BUY" if direction == "LONG" else "SELL"
        risk = calculate_risk_levels(signal=sig, entry_price=entry, atr=atr, config=cfg)
        setup["invalidation"] = risk["stop_loss"]
        setup["target"] = risk["take_profit"]
        setup["invalidation_rule"] = f"{direction} iptal: kapanis stop ({risk['stop_loss']}) disi"
        setup["target_rule"] = f"ATR x{cfg.get('target_atr_multiple', 3.0)} hedef ({risk['take_profit']})"
    else:
        setup["invalidation"] = None
        setup["target"] = None
        setup["invalidation_rule"] = "Konsensus yok: setup uretilmedi"
        setup["target_rule"] = "Konsensus yok: hedef uretilmedi"

    return setup
