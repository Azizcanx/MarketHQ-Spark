# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Evolution V1 (research-only, no live trading).

Döngünün eksik halkası: Learning -> Brain -> Strategy Evolution.

Ne yapar:
  - setup_feedback.jsonl'deki etiketli sonuclari strateji x rejim matrisinde toplar
  - PROMOTE / WATCH / DEMOTE kararlari uretir (orneklem buyudukce guven artar)
  - Piyasa-geneli gozlemleri cikarir (orn: DOWNTREND setup'lari duzensiz basarisizsa
    kisa-yon arastirmasi onerir)
  - Brain/arastirma kuyrugunun tuketecegi somut arastirma sorulari uretir

Esikler (kucuk orneklemde muhafazakar):
  - n>=5 ve hit_rate>=0.60 -> PROMOTE
  - n>=5 ve hit_rate<=0.25 -> DEMOTE
  - aksi halde WATCH (+ ihtiyac: kac etiket daha gerektigi)

Yazma: agentspace/agentspace/logs/strategy_evolution_latest.json (atomik degil,
tek yazar varsayimi; DB'ye dokunmaz, learned_rules'a yazmaz).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANDIDATES = [
    Path(__file__).resolve().parent / "agentspace" / "agentspace" / "logs" / "setup_feedback.jsonl",
    Path(__file__).resolve().parent / "agentspace" / "logs" / "setup_feedback.jsonl",
]

OUT_PATH = Path(__file__).resolve().parent / "agentspace" / "agentspace" / "logs" / "strategy_evolution_latest.json"

PROMOTE_MIN_N = 5
PROMOTE_HR = 0.60
DEMOTE_MIN_N = 5
DEMOTE_HR = 0.25


def load_decided() -> list[dict[str, Any]]:
    for p in CANDIDATES:
        if p.exists():
            path = p
            break
    else:
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("outcome") in ("CONFIRMED", "INVALIDATED"):
                out.append(r)
    return out


def brain_db_snapshot() -> dict[str, Any]:
    """market_hq.db'den SALT-OKUNUR Brain gorunumu (yazma yok)."""
    import sqlite3 as _sq
    db = Path(__file__).resolve().parent / "market_hq.db"
    if not db.exists():
        return {"available": False, "detail": "db yok"}
    try:
        conn = _sq.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        try:
            rows = conn.execute(
                "SELECT strategy_id, action, learning_score FROM brain_strategy_learning_rankings"
            ).fetchall()
            by_action: dict[str, int] = {}
            for _, act, _ in rows:
                by_action[str(act)] = by_action.get(str(act), 0) + 1
            return {
                "available": True,
                "rankings": len(rows),
                "distinct_strategies": len({r[0] for r in rows}),
                "by_action": by_action,
            }
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "detail": str(e)[:120]}


def build_evolution() -> dict[str, Any]:
    rows = load_decided()
    per: dict[str, dict[str, Any]] = {}
    regime_agg: dict[str, dict[str, int]] = {}

    def hit(r: dict[str, Any]) -> bool:
        return r.get("outcome") == "CONFIRMED"

    for r in rows:
        reg = str(r.get("regime", "UNKNOWN"))
        ra = regime_agg.setdefault(reg, {"n": 0, "confirmed": 0})
        ra["n"] += 1
        if hit(r):
            ra["confirmed"] += 1
        for sid in r.get("supporting", []) or []:
            s = per.setdefault(sid, {"n": 0, "confirmed": 0, "by_regime": {}})
            s["n"] += 1
            if hit(r):
                s["confirmed"] += 1
            br = s["by_regime"].setdefault(reg, {"n": 0, "confirmed": 0})
            br["n"] += 1
            if hit(r):
                br["confirmed"] += 1

    strategies: dict[str, Any] = {}
    for sid, s in per.items():
        hr = s["confirmed"] / s["n"]
        if s["n"] >= PROMOTE_MIN_N and hr >= PROMOTE_HR:
            status, need = "PROMOTE", 0
        elif s["n"] >= DEMOTE_MIN_N and hr <= DEMOTE_HR:
            status, need = "DEMOTE", 0
        else:
            status = "WATCH"
            need = max(0, PROMOTE_MIN_N - s["n"])
        reg_detail = {k: {"n": v["n"], "hit_rate": round(v["confirmed"] / v["n"], 3)} for k, v in s["by_regime"].items()}
        strategies[sid] = {
            "n": s["n"], "hit_rate": round(hr, 3), "status": status,
            "labels_needed": need, "by_regime": reg_detail,
        }

    regimes = {k: {"n": v["n"], "hit_rate": round(v["confirmed"] / v["n"], 3)} for k, v in regime_agg.items()}

    observations: list[str] = []
    questions: list[str] = []
    down = regime_agg.get("DOWNTREND")
    if down and down["n"] >= 5 and down["confirmed"] / down["n"] <= 0.25:
        observations.append(f"DOWNTREND setup'lari duzensiz basarisiz (n={down['n']}, hit={down['confirmed']/down['n']:.0%})")
        questions.append("Dususte LONG setup'lari neden sistematik gecersiz kaliyor — kisa-yon kurallari icin bagimsiz arastirma ac")
    for sid, s in strategies.items():
        if s["status"] == "DEMOTE":
            observations.append(f"{sid} DEMOTE sinirinda (n={s['n']}, hit={s['hit_rate']})")
            questions.append(f"{sid} hangi rejimde tamamen cope atilmali, hangi rejimde agirligi dusurulmeli — rejim-kosullu arastirma ac")
            break
    weak_syms = [k for k, v in regimes.items() if v["n"] >= 3 and v["hit_rate"] <= 0.34 and k != "DOWNTREND"]
    if weak_syms and len(questions) < 3:
        questions.append(f"Zayif rejimler ({', '.join(weak_syms)}) icin mean-reversion agirlikli pilot arastirma ac")
    if not questions:
        questions.append("Etiket sayisi artana kadar mevcut dagilimi koru; yeni sembole (BNB/XRP) backfill ile kapsami genislet")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decided": len(rows),
        "strategies": strategies,
        "regimes": regimes,
        "observations": observations,
        "suggested_research_questions": questions[:3],
        "brain_db": brain_db_snapshot(),
        "research_only": True,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
