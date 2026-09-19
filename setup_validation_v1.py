# -*- coding: utf-8 -*-
"""
MarketHQ Setup Validation V1 (research-only).

Walk-forward + perturbasyon + maliyet soku + Monte Carlo:
  - walk-forward: veriyi k parcaya bol, her pencerede consensus yonu karsilastir
  - perturbasyon: kapanisa gurultu ekle, yonu tekrar olc
  - maliyet soku: fee+slippage katlanirken setup edge (hedef-risk-maliyet) korunuyor mu
  - monte_carlo: getiri dagilimindan uretilen patikalarda yon tutarliligi
Cikti: 0..1 skorlar + detay. Canli islem yok.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from setup_engine_v1 import build_setup


def walk_forward_stability(df: pd.DataFrame, folds: int = 3, timeframe: str = "1h", config: dict | None = None) -> dict[str, Any]:
    n = len(df)
    dirs = []
    for i in range(folds):
        a = int(i * n / folds)
        b = int((i + 1) * n / folds)
        chunk = df.iloc[a:b]
        if len(chunk) < 60:
            continue
        dirs.append(build_setup(chunk, timeframe, config)["direction"])
    if not dirs:
        return {"stability": 0.0, "windows": []}
    top = max(set(dirs), key=dirs.count)
    return {"stability": dirs.count(top) / len(dirs), "windows": dirs, "dominant": top}


def perturbation_robustness(df: pd.DataFrame, trials: int = 5, noise_pct: float = 0.003, seed: int = 7, timeframe: str = "1h", config: dict | None = None) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    base = build_setup(df, timeframe, config)["direction"]
    same = 0
    dirs = []
    close = df["Close"].to_numpy(dtype=float)
    for _ in range(trials):
        noisy = df.copy()
        noisy["Close"] = close * (1 + rng.normal(0, noise_pct, len(close)))
        noisy["High"] = df["High"].to_numpy(dtype=float) * (1 + rng.normal(0, noise_pct / 2, len(close)))
        noisy["Low"] = df["Low"].to_numpy(dtype=float) * (1 + rng.normal(0, noise_pct / 2, len(close)))
        d = build_setup(noisy, timeframe, config)["direction"]
        dirs.append(d)
        if d == base:
            same += 1
    return {"robustness": same / trials, "base": base, "trials": dirs}


def cost_shock_edge(setup: dict[str, Any], fee_pct: float = 0.001, slippage_atr_frac: float = 0.1, shocks: tuple[float, ...] = (1.0, 2.0, 3.0)) -> dict[str, Any]:
    """Hedef-risk-maliyet edge'i sok seviyelerinde test eder."""
    entry, tgt, stp, atr = setup.get("entry_price"), setup.get("target"), setup.get("invalidation"), setup.get("atr")
    if setup.get("direction") not in ("LONG", "SHORT") or not all(isinstance(x, (int, float)) for x in (entry, tgt, stp)):
        return {"applicable": False, "score": None, "detail": "setup yok"}
    reward, risk = abs(tgt - entry), abs(entry - stp)
    base_cost = entry * fee_pct * 2 + (atr or 0) * slippage_atr_frac
    edges = [round(reward - risk - base_cost * m, 4) for m in shocks]
    passed = sum(1 for e in edges if e > 0)
    return {"applicable": True, "score": passed / len(shocks), "edges": edges, "shocks": list(shocks)}


def monte_carlo_consensus(df: pd.DataFrame, trials: int = 20, seed: int = 42, timeframe: str = "1h", config: dict | None = None) -> dict[str, Any]:
    """Gecmis getiri dagilimindan bootstrap patika uret, yon tutarliligini olc."""
    rng = np.random.default_rng(seed)
    close = df["Close"].to_numpy(dtype=float)
    rets = np.diff(np.log(close))
    rets = rets[np.isfinite(rets)]
    if len(rets) < 30:
        return {"robustness": 0.0, "base": None, "detail": "yetersiz veri"}
    base = build_setup(df, timeframe, config)["direction"]
    vol = df["Volume"].to_numpy(dtype=float)
    mean_vol = float(np.nanmean(vol)) if np.isfinite(np.nanmean(vol)) else 1000.0
    n = len(close)
    same = 0
    for _ in range(trials):
        path = np.empty(n)
        path[0] = close[0]
        path[1:] = close[0] * np.exp(np.cumsum(rng.choice(rets, size=n - 1)))
        synth = pd.DataFrame({
            "Open": path,
            "High": path * 1.002,
            "Low": path * 0.998,
            "Close": path,
            "Volume": np.full(n, mean_vol),
        })
        if build_setup(synth, timeframe, config)["direction"] == base:
            same += 1
    return {"robustness": same / trials, "base": base, "trials": trials}


def validate_setup(df: pd.DataFrame, timeframe: str = "1h", config: dict | None = None) -> dict[str, Any]:
    wf = walk_forward_stability(df, timeframe=timeframe, config=config)
    pt = perturbation_robustness(df, timeframe=timeframe, config=config)
    setup = build_setup(df, timeframe, config)
    fee_pct = (config or {}).get("fee_pct", 0.001)
    slip = (config or {}).get("slippage_atr_frac", 0.1)
    cs = cost_shock_edge(setup, fee_pct=fee_pct, slippage_atr_frac=slip)
    mc = monte_carlo_consensus(df, timeframe=timeframe, config=config)
    parts = [wf["stability"], pt["robustness"], mc["robustness"]]
    if cs.get("applicable"):
        parts.append(cs["score"])
    score = round(sum(parts) / len(parts), 3)
    return {
        "score": score,
        "walk_forward": wf,
        "perturbation": pt,
        "cost_shock": cs,
        "monte_carlo": mc,
        "robust": score >= 0.6,
        "research_only": True,
    }
