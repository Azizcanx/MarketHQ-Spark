# -*- coding: utf-8 -*-
"""
MarketHQ Pair Spread V1 (research-only, no live trading).

Iki sembolun gore li momentum farki: spread = A/B orani.
  - spread 20 barlik degisimi pozitif -> A, B'ye gore guclu (A_LEADS)
  - negatif -> B onde (B_LEADS)
Tek basina yon uretmez; setup'a baglam notu duser (cift-bacak on arastirma).
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

SPREAD_WINDOW = 20


def pair_spread(
    closes_a: list[float] | pd.Series,
    closes_b: list[float] | pd.Series,
    symbol_a: str = "A",
    symbol_b: str = "B",
    window: int = SPREAD_WINDOW,
) -> dict[str, Any]:
    try:
        a = pd.Series(closes_a, dtype=float).reset_index(drop=True)
        b = pd.Series(closes_b, dtype=float).reset_index(drop=True)
    except (ValueError, TypeError):
        return {"available": False, "detail": "seri hatasi"}
    n = min(len(a), len(b))
    if n < window + 1:
        return {"available": False, "detail": "yetersiz bar"}
    a, b = a.tail(n).reset_index(drop=True), b.tail(n).reset_index(drop=True)
    ratio = a / b.replace(0, float("nan"))
    if ratio.isna().any():
        return {"available": False, "detail": "sifir/NaN fiyat"}
    now, past = float(ratio.iloc[-1]), float(ratio.iloc[-1 - window])
    if not math.isfinite(now) or not math.isfinite(past) or past == 0:
        return {"available": False, "detail": "oran hesaplanamadi"}
    change = (now - past) / abs(past)
    leader = symbol_a if change > 0 else (symbol_b if change < 0 else "EVEN")
    return {
        "available": True,
        "pair": f"{symbol_a}/{symbol_b}",
        "leader": leader,
        "spread_change": round(change, 4),
        "note": f"{symbol_a}/{symbol_b} spread 20 barda {change:+.2%} -> onder: {leader}",
        "research_only": True,
    }
