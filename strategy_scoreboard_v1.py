# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Scoreboard V1 (research-only).

setup_feedback.jsonl'yi okur, strateji bazinda skor uretir:
  supported -> CONFIRMED sayisi / karar verilmis toplam.
Outcome PENDING olanlar skora girmez, sadece kapsama (coverage) sayilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CANDIDATES = [
    Path(__file__).resolve().parent / "agentspace" / "agentspace" / "logs" / "setup_feedback.jsonl",
    Path(__file__).resolve().parent / "agentspace" / "logs" / "setup_feedback.jsonl",
]


def _path() -> Path | None:
    for p in CANDIDATES:
        if p.exists():
            return p
    return None


def build_scoreboard() -> dict[str, Any]:
    p = _path()
    if p is None:
        return {"strategies": {}, "decided": 0, "pending": 0, "detail": "feedback yok"}
    per: dict[str, dict[str, int]] = {}
    by_symbol: dict[str, dict[str, int]] = {}
    decided = pending = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            outcome = r.get("outcome", "PENDING")
            if outcome == "PENDING":
                pending += 1
                continue
            decided += 1
            hit = outcome == "CONFIRMED"
            sym = by_symbol.setdefault(r.get("symbol", "UNKNOWN"), {"decided": 0, "confirmed": 0})
            sym["decided"] += 1
            if hit:
                sym["confirmed"] += 1
            for sid in r.get("supporting", []) or []:
                s = per.setdefault(sid, {"supported": 0, "confirmed": 0, "invalidated": 0})
                s["supported"] += 1
                s["confirmed" if hit else "invalidated"] += 1
    table = {}
    for sid, s in per.items():
        dec = s["confirmed"] + s["invalidated"]
        table[sid] = {**s, "hit_rate": round(s["confirmed"] / dec, 3) if dec else None}
    ranked = sorted(table.items(), key=lambda kv: (kv[1]["hit_rate"] is not None, kv[1]["hit_rate"] or 0), reverse=True)
    symbols = {k: {**v, "hit_rate": round(v["confirmed"] / v["decided"], 3)} for k, v in by_symbol.items()}
    return {"strategies": table, "ranking": [sid for sid, _ in ranked], "symbols": symbols, "decided": decided, "pending": pending}
