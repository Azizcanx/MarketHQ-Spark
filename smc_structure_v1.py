# -*- coding: utf-8 -*-
"""
MarketHQ SMC Structure V1 (research-only, no live trading).

Market Structure + Liquidity Sweep + BOS/CHoCH stratejisi.

Mantık (son bar sinyali, repaint yok — salınımlar sondan 1 bar önce kesinleşir):
  - Swing high/low: order-N fraktal pivotlar.
  - BOS: önceki kırılımla aynı yönde salınım kırılımı (trend devamı).
  - CHoCH: önceki kırılımın tersi yönde kırılım (yapı değişimi).
  - Liquidity sweep: kırılım öncesi lookback'te fitil salınım dışına taşar ama
    kapanış içeri döner (sell-side/buy-side likidite alımı).
  - Displacement filtresi: kırılım mumunun gövdesi >= 0.5xATR olmalı.

Sinyal:
  - sweep + CHoCH yukarı  -> LONG  (0.85)
  - BOS yukarı (sweepsiz)  -> LONG  (0.55)
  - sweep + CHoCH aşağı   -> SHORT (0.85)
  - BOS aşağı (sweepsiz)   -> SHORT (0.55)
  - aksi halde NEUTRAL.

Seviyeler (smc_* kolonları, gerekçe/audit için):
  - smc_invalidation: süpürülen ekstrem (yoksa son salınım) + tampon
  - smc_target: karşı likidite (yakın salınım) veya 2R geri dönüşü

Kullanım:
  from smc_structure_v1 import add_smc_structure, smc_signal_from_row
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

SWING_ORDER = 3
SWEEP_LOOKBACK = 10
DISPLACEMENT_ATR_MULT = 0.5
BUFFER_ATR_MULT = 0.1


def _f(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def find_swings(df: pd.DataFrame, order: int = SWING_ORDER) -> list[dict[str, Any]]:
    """Kesinleşmiş pivotlar (son `order` bar hariç — repaint engeli)."""
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    n = len(df)
    swings: list[dict[str, Any]] = []
    for i in range(order, n - order):
        window_h = high[i - order: i + order + 1]
        window_l = low[i - order: i + order + 1]
        if high[i] == window_h.max():
            swings.append({"idx": i, "price": float(high[i]), "kind": "H"})
        if low[i] == window_l.min():
            swings.append({"idx": i, "price": float(low[i]), "kind": "L"})
    return swings


def structure_events(df: pd.DataFrame, swings: list[dict[str, Any]], atr: float, order: int = SWING_ORDER) -> list[dict[str, Any]]:
    """Kapanış bazlı kırılım olayları: her barda o ana kadar kesinleşmiş salınımlara bakılır."""
    close = df["Close"].to_numpy(dtype=float)
    open_ = df["Open"].to_numpy(dtype=float)
    n = len(df)
    events: list[dict[str, Any]] = []
    by_idx: dict[int, list[dict[str, Any]]] = {}
    for s in swings:
        by_idx.setdefault(s["idx"], []).append(s)
    last_h: float | None = None
    last_l: float | None = None
    for j in range(n - 1):  # son bar sinyal barı, olay sayılmaz
        for s in by_idx.get(j - order, []):  # j anında kesinleşen salınımlar
            if s["kind"] == "H":
                last_h = s["price"]
            else:
                last_l = s["price"]
        body = abs(close[j] - open_[j])
        if body < DISPLACEMENT_ATR_MULT * atr:
            continue
        if last_h is not None and close[j] > last_h:
            events.append({"idx": j, "direction": "UP", "broken": last_h, "kind": "H"})
            last_h = None  # kırılan seviye tüketilir, sonraki salınım beklenir
        elif last_l is not None and close[j] < last_l:
            events.append({"idx": j, "direction": "DOWN", "broken": last_l, "kind": "L"})
            last_l = None
    return events


def swept_extreme(df: pd.DataFrame, swing_price: float, side: str, lookback: int = SWEEP_LOOKBACK) -> float | None:
    """Son `lookback` barda fitil-salınım taşması + içeri kapanış var mı? Varsa ekstremi döndür."""
    tail = df.tail(lookback + 1).iloc[:-1]  # sinyal barı hariç
    if tail.empty:
        return None
    if side == "sell":  # sell-side: low taşar, kapanış içeri döner
        wicks = tail[tail["Low"] < swing_price]
        if wicks.empty:
            return None
        reclaimed = wicks[wicks["Close"] > swing_price]
        if reclaimed.empty:
            return None
        return float(wicks["Low"].min())
    wicks = tail[tail["High"] > swing_price]
    if wicks.empty:
        return None
    reclaimed = wicks[wicks["Close"] < swing_price]
    if reclaimed.empty:
        return None
    return float(wicks["High"].max())


def _structure_state(events: list[dict[str, Any]], swings: list[dict[str, Any]]) -> str:
    """Market structure state string: last event type + swing pattern."""
    if events:
        last = events[-1]
        prev_dir = events[-2]["direction"] if len(events) >= 2 else None
        if prev_dir is not None and prev_dir != last["direction"]:
            ev_type = f"CHoCH_{last['direction']}"
        else:
            ev_type = f"BOS_{last['direction']}"
    else:
        ev_type = "NONE"
    # Last two swing highs/lows for structural context
    hs = [s for s in swings if s["kind"] == "H"]
    ls = [s for s in swings if s["kind"] == "L"]
    pattern = ""
    if len(hs) >= 2 and len(ls) >= 2:
        hh = hs[-1]["price"] > hs[-2]["price"]
        ll = ls[-1]["price"] > ls[-2]["price"]
        hl = hs[-1]["price"] < hs[-2]["price"]
        lh = ls[-1]["price"] < ls[-2]["price"]
        if hh and ll:
            pattern = "HH-LL"
        elif hh and lh:
            pattern = "HH-LH"
        elif hl and ll:
            pattern = "HL-LL"
        elif hl and lh:
            pattern = "HL-LH"
        elif hh:
            pattern = "HH"
        elif hl:
            pattern = "HL"
        elif lh:
            pattern = "LH"
        elif ll:
            pattern = "LL"
    return f"{ev_type}({pattern})" if pattern else ev_type


def evaluate_smc(df: pd.DataFrame) -> dict[str, Any]:
    neutral: dict[str, Any] = {
        "direction": "NEUTRAL", "confidence": 0.0, "reason": "yapı kırılımı yok",
        "event": None, "sweep": None, "invalidation": None, "target": None, "structure_state": "",
    }
    if len(df) < 30:
        return {**neutral, "reason": "yetersiz bar"}
    atr = _f(df["ATR"].iloc[-1]) if "ATR" in df.columns else None
    if atr is None or atr == 0:
        tr = (df["High"] - df["Low"]).tail(14).mean()
        atr = float(tr) if math.isfinite(float(tr)) else None
    if atr is None or atr == 0:
        return {**neutral, "reason": "ATR yok"}
    swings = find_swings(df)
    if len(swings) < 2:
        return {**neutral, "reason": "salınım yok"}
    events = structure_events(df, swings, atr)
    if not events:
        return neutral
    last = events[-1]
    prev_dir = events[-2]["direction"] if len(events) >= 2 else None
    is_choch = prev_dir is not None and prev_dir != last["direction"]
    tag = "CHoCH" if is_choch else "BOS"
    close = float(df["Close"].iloc[-1])
    state = _structure_state(events, swings)
    if last["direction"] == "UP":
        sweep = swept_extreme(df, last_l_price(swings, last["idx"]), "sell")
        if sweep is not None:
            inv = sweep - BUFFER_ATR_MULT * atr
            tgt = opposing_liquidity(swings, "H", close) or (close + 2 * (close - inv))
            return {"direction": "LONG", "confidence": 0.85, "reason": f"sweep+{tag} yukarı (likidite {sweep:.2f} alındı)",
                    "event": tag, "sweep": sweep, "invalidation": inv, "target": tgt, "structure_state": state}
        # CHoCH fires without sweep requirement; BOS without sweep continues trend
        if is_choch:
            inv = (last_l_price(swings, last["idx"]) if last_l_price(swings, last["idx"]) is not None else close - atr) - BUFFER_ATR_MULT * atr
            tgt = opposing_liquidity(swings, "H", close) or (close + 2 * (close - inv))
            return {"direction": "LONG", "confidence": 0.70, "reason": f"{tag} yukarı (sweepsiz yapı değişimi)",
                    "event": tag, "sweep": None, "invalidation": inv, "target": tgt, "structure_state": state}
        last_l = last_l_price(swings, last["idx"])
        inv = (last_l if last_l is not None else close - atr) - BUFFER_ATR_MULT * atr
        tgt = opposing_liquidity(swings, "H", close) or (close + 2 * (close - inv))
        return {"direction": "LONG", "confidence": 0.55, "reason": f"BOS yukarı (sweepsiz devam)",
                "event": tag, "sweep": None, "invalidation": inv, "target": tgt, "structure_state": state}
    else:
        sweep = swept_extreme(df, last_h_price(swings, last["idx"]), "buy")
        if sweep is not None:
            inv = sweep + BUFFER_ATR_MULT * atr
            tgt = opposing_liquidity(swings, "L", close) or (close - 2 * (inv - close))
            return {"direction": "SHORT", "confidence": 0.85, "reason": f"sweep+{tag} asagi (likidite {sweep:.2f} alindi)",
                    "event": tag, "sweep": sweep, "invalidation": inv, "target": tgt, "structure_state": state}
        # CHoCH fires without sweep requirement; BOS without sweep continues trend
        if is_choch:
            inv = (last_h_price(swings, last["idx"]) if last_h_price(swings, last["idx"]) is not None else close + atr) + BUFFER_ATR_MULT * atr
            tgt = opposing_liquidity(swings, "L", close) or (close - 2 * (inv - close))
            return {"direction": "SHORT", "confidence": 0.70, "reason": f"{tag} asagi (sweepsiz yapı değişimi)",
                    "event": tag, "sweep": None, "invalidation": inv, "target": tgt, "structure_state": state}
        last_h = last_h_price(swings, last["idx"])
        inv = (last_h if last_h is not None else close + atr) + BUFFER_ATR_MULT * atr
        tgt = opposing_liquidity(swings, "L", close) or (close - 2 * (inv - close))
        return {"direction": "SHORT", "confidence": 0.55, "reason": "BOS asagi (sweepsiz devam)",
                "event": tag, "sweep": None, "invalidation": inv, "target": tgt, "structure_state": state}


def last_l_price(swings: list[dict[str, Any]], before_idx: int) -> float | None:
    lows = [s["price"] for s in swings if s["kind"] == "L" and s["idx"] < before_idx]
    return lows[-1] if lows else None


def last_h_price(swings: list[dict[str, Any]], before_idx: int) -> float | None:
    highs = [s["price"] for s in swings if s["kind"] == "H" and s["idx"] < before_idx]
    return highs[-1] if highs else None


def opposing_liquidity(swings: list[dict[str, Any]], kind: str, ref: float) -> float | None:
    if kind == "H":
        above = [s["price"] for s in swings if s["kind"] == "H" and s["price"] > ref]
        return min(above) if above else None
    below = [s["price"] for s in swings if s["kind"] == "L" and s["price"] < ref]
    return max(below) if below else None


def add_smc_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Son bar SMC değerlendirmesini kolon olarak işler (registry uyumu)."""
    out = df.copy()
    res = evaluate_smc(out)
    out["SMC_DIR"] = res["direction"]
    out["SMC_CONF"] = res["confidence"]
    out["SMC_REASON"] = res["reason"]
    out["SMC_EVENT"] = res["event"]
    out["SMC_INV"] = res["invalidation"]
    out["SMC_TGT"] = res["target"]
    out["SMC_STRUCTURE_STATE"] = res.get("structure_state", "")
    return out


def smc_signal_from_row(row: pd.Series) -> dict[str, Any]:
    d = row.get("SMC_DIR", "NEUTRAL")
    try:
        conf = float(row.get("SMC_CONF", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "strategy_id": "smc_structure_v1",
        "direction": d if d in ("LONG", "SHORT") else "NEUTRAL",
        "confidence": conf if math.isfinite(conf) else 0.0,
        "reason": str(row.get("SMC_REASON", "SMC yok")),
        "event": row.get("SMC_EVENT"),
        "invalidation": _f(row.get("SMC_INV")),
        "target": _f(row.get("SMC_TGT")),
        "structure_state": str(row.get("SMC_STRUCTURE_STATE", "")),
    }
