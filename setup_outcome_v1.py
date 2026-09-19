# -*- coding: utf-8 -*-
"""
MarketHQ Setup Outcome V1 (research-only).

Setup'un ileriye donuk sonucu: hedefe mi stop'a mi once degdi?
  CONFIRMED   -> hedef once
  INVALIDATED -> stop once
  EXPIRED     -> ufukta ikisi de olmadi
  NO_SETUP    -> yon yoktu

backfill(): gecmis pencerelerde setup kur + sonucu feedback JSONL'ye yaz.
Boylece scoreboard gercek etiketle dolar. Canli islem yok.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from setup_engine_v1 import build_setup
from setup_feedback_v1 import log_setup_feedback


def evaluate_outcome(df: pd.DataFrame, setup: dict[str, Any], at_index: int, horizon: int = 20) -> str:
    if setup.get("direction") not in ("LONG", "SHORT"):
        return "NO_SETUP"
    tgt, stp = setup.get("target"), setup.get("invalidation")
    if not isinstance(tgt, (int, float)) or not isinstance(stp, (int, float)):
        return "NO_SETUP"
    fwd = df.iloc[at_index + 1: at_index + 1 + horizon]
    if fwd.empty:
        return "EXPIRED"
    is_long = setup["direction"] == "LONG"
    for _, bar in fwd.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        hit_t = (hi >= tgt) if is_long else (lo <= tgt)
        hit_s = (lo <= stp) if is_long else (hi >= stp)
        if hit_t and hit_s:
            return "INVALIDATED"  # ayni barda cift temas: yonu bilinmez, muhafazakar
        if hit_t:
            return "CONFIRMED"
        if hit_s:
            return "INVALIDATED"
    return "EXPIRED"


def _logged_keys() -> set[tuple[str, str]]:
    """Var olan (symbol, note) ciftleri — tekrar backfill'i onler."""
    from setup_feedback_v1 import FEEDBACK_PATH
    keys: set[tuple[str, str]] = set()
    try:
        with open(FEEDBACK_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    sym, note = str(r.get("symbol", "UNKNOWN")), str(r.get("note", ""))
                    keys.add((sym, note))
                    if sym != "UNKNOWN" and note.startswith("backfill idx="):
                        # eski format: "backfill idx=.." -> yeni formatla eslestir
                        keys.add((sym, f"backfill {sym} {note[len('backfill '):]}"))
                except (json.JSONDecodeError, AttributeError):
                    continue
    except FileNotFoundError:
        pass
    return keys


def backfill(df: pd.DataFrame, timeframe: str = "1h", horizon: int = 20, step: int = 20, min_bars: int = 80, symbol: str = "UNKNOWN") -> dict[str, Any]:
    counts: dict[str, int] = {}
    seen = _logged_keys()
    added = 0
    n = len(df)
    i = min_bars
    while i + horizon < n:
        window = df.iloc[:i]
        setup = build_setup(window, timeframe)
        setup["symbol"] = symbol
        outcome = evaluate_outcome(df, setup, i - 1, horizon)
        note = f"backfill {symbol} idx={i} horizon={horizon}"
        if outcome not in ("NO_SETUP", "EXPIRED") and (symbol, note) not in seen:
            log_setup_feedback(setup, outcome, note=note)
            seen.add((symbol, note))
            added += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        i += step
    return {"counts": counts, "windows": sum(counts.values()), "added": added}
