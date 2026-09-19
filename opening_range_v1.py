# -*- coding: utf-8 -*-
"""
MarketHQ Opening Range Breakout V1 (research-only, no live trading).

Açılış aralığı kırılımı (günlük bar öncesi günün range'i proxy):
  - OR_HIGH = önceki barın High'ı (+ buffer)
  - OR_LOW  = önceki barın Low'u  (- buffer)
  - Kapanış OR_HIGH üstü -> LONG
  - Kapanış OR_LOW altı  -> SHORT
  - Aralık içi          -> NEUTRAL

Parametreler: lookback=1, buffer ATR oranı 0.1.
Confidence: dışarı taşmanın ATR'ye oranı ile ölçeklenir (max 0.8).

Kullanım:
  from opening_range_v1 import add_opening_range, or_signal_from_row
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

LOOKBACK = 1
BUFFER_ATR_MULT = 0.1
MAX_CONF = 0.8


def _f(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _atr(df: pd.DataFrame) -> float | None:
    if "ATR" in df.columns:
        atr = _f(df["ATR"].iloc[-1])
        if atr and atr > 0:
            return atr
    tr = (df["High"] - df["Low"]).tail(14).mean()
    try:
        tr = float(tr)
    except (TypeError, ValueError):
        return None
    return tr if math.isfinite(tr) and tr > 0 else None


def evaluate_or(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict[str, Any]:
    neutral: dict[str, Any] = {
        "direction": "NEUTRAL", "confidence": 0.0,
        "reason": "aralık içi kapanış", "or_high": None, "or_low": None,
    }
    if len(df) < lookback + 1:
        return {**neutral, "reason": "yetersiz bar"}
    atr = _atr(df)
    if atr is None or atr == 0:
        return {**neutral, "reason": "ATR yok"}
    prev = df.iloc[-(lookback + 1):-1]
    or_high = float(prev["High"].to_numpy(dtype=float).max()) + BUFFER_ATR_MULT * atr
    or_low = float(prev["Low"].to_numpy(dtype=float).min()) - BUFFER_ATR_MULT * atr
    close = float(df["Close"].iloc[-1])
    if close > or_high:
        excess = (close - or_high) / atr
        conf = min(MAX_CONF, 0.3 + 0.5 * excess)
        return {"direction": "LONG", "confidence": round(max(0.0, conf), 3),
                "reason": f"kapanış açılış aralığı üstünde ({close:.2f} > {or_high:.2f}, taşma {excess:.2f} ATR)",
                "or_high": or_high, "or_low": or_low}
    if close < or_low:
        excess = (or_low - close) / atr
        conf = min(MAX_CONF, 0.3 + 0.5 * excess)
        return {"direction": "SHORT", "confidence": round(max(0.0, conf), 3),
                "reason": f"kapanış açılış aralığı altında ({close:.2f} < {or_low:.2f}, taşma {excess:.2f} ATR)",
                "or_high": or_high, "or_low": or_low}
    return {**neutral, "reason": f"kapanış aralık içinde ({or_low:.2f}–{or_high:.2f})",
            "or_high": or_high, "or_low": or_low}


def add_opening_range(df: pd.DataFrame, lookback: int = LOOKBACK) -> pd.DataFrame:
    """Son bar OR değerlendirmesini kolon olarak işler (registry uyumu)."""
    out = df.copy()
    res = evaluate_or(out, lookback=lookback)
    out["OR_HIGH"] = res["or_high"]
    out["OR_LOW"] = res["or_low"]
    out["OR_DIR"] = res["direction"]
    out["OR_CONF"] = res["confidence"]
    out["OR_REASON"] = res["reason"]
    return out


def or_signal_from_row(row: pd.Series) -> dict[str, Any]:
    d = row.get("OR_DIR", "NEUTRAL")
    try:
        conf = float(row.get("OR_CONF", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "strategy_id": "or_breakout_v1",
        "direction": d if d in ("LONG", "SHORT") else "NEUTRAL",
        "confidence": conf if math.isfinite(conf) else 0.0,
        "reason": str(row.get("OR_REASON", "açılış aralığı yok")),
    }
