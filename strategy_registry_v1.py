# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Registry V1 (research-only, no live trading).

Katman: signal_engine.py uzerinde strateji-bazli sinyal uretimi.
Her strateji LONG / SHORT / NEUTRAL uretir + agreement sayimi.

Pilot aileler (7):
  - ema_trend (trend)
  - rsi_reversal (mean-reversion)
  - donchian_breakout (breakout)
  - supertrend_v1 (trend)
  - adx_v1 (trend-strength filter)
  - vwap_v1 (volume-anchored)
  - bollinger_v1 (mean-reversion)

Kullanim:
  from strategy_registry_v1 import run_all_strategies_df, agreement_summary
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from signal_engine import add_indicators, DEFAULT_CONFIG
from smc_structure_v1 import add_smc_structure, smc_signal_from_row
from opening_range_v1 import add_opening_range, or_signal_from_row


STRATEGIES = [
    {"strategy_id": "ema_trend_v1", "family": "trend", "description": "EMA20 vs EMA50 cross"},
    {"strategy_id": "rsi_reversal_v1", "family": "mean_reversion", "description": "RSI oversold/overbought"},
    {"strategy_id": "donchian_breakout_v1", "family": "breakout", "description": "Donchian N=20 breakout"},
    {"strategy_id": "supertrend_v1", "family": "trend", "description": "SuperTrend(10,3) yönü"},
    {"strategy_id": "adx_v1", "family": "trend", "description": "ADX>20 + DI yönü"},
    {"strategy_id": "vwap_v1", "family": "volume", "description": "Close vs 20-bar VWAP"},
    {"strategy_id": "bollinger_v1", "family": "mean_reversion", "description": "BB disi reversal"},
    {"strategy_id": "atr_breakout_v1", "family": "breakout", "description": "ATR genisleme kirilimi"},
    {"strategy_id": "stoch_reversal_v1", "family": "mean_reversion", "description": "Stokastik asiri bolge donusu"},
    {"strategy_id": "rs_benchmark_v1", "family": "relative", "description": "Benchmark'a gore goreli guc (opsiyonel)"},
    {"strategy_id": "smc_structure_v1", "family": "structure", "description": "Sweep+BOS/CHoCH yapi kirilimi"},
    {"strategy_id": "or_breakout_v1", "family": "breakout", "description": "Acilis araligi kirilimi"},
]

DONCHIAN_PERIOD = 20
SUPERTREND_PERIOD = 10
SUPERTREND_MULT = 3.0
ADX_PERIOD = 14
ADX_THRESHOLD = 20.0
VWAP_WINDOW = 20


def _f(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def add_donchian(df: pd.DataFrame, period: int = DONCHIAN_PERIOD) -> pd.DataFrame:
    out = df.copy()
    out["don_high"] = out["High"].rolling(period).max().shift(1)
    out["don_low"] = out["Low"].rolling(period).min().shift(1)
    return out


def _ema_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    ef, es = row.get("EMA_FAST"), row.get("EMA_SLOW")
    try:
        ef, es = float(ef), float(es)
    except (TypeError, ValueError):
        return {"strategy_id": "ema_trend_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "EMA yok"}
    if ef > es:
        return {"strategy_id": "ema_trend_v1", "direction": "LONG", "confidence": min(abs(ef - es) / es * 100, 1.0), "reason": f"EMA20({ef:.2f})>EMA50({es:.2f})"}
    if ef < es:
        return {"strategy_id": "ema_trend_v1", "direction": "SHORT", "confidence": min(abs(ef - es) / es * 100, 1.0), "reason": f"EMA20({ef:.2f})<EMA50({es:.2f})"}
    return {"strategy_id": "ema_trend_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "EMA esit"}


def _rsi_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    try:
        rsi = float(row.get("RSI"))
    except (TypeError, ValueError):
        return {"strategy_id": "rsi_reversal_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "RSI yok"}
    os_ = cfg.get("rsi_oversold", 30)
    ob = cfg.get("rsi_overbought", 70)
    if rsi < os_:
        return {"strategy_id": "rsi_reversal_v1", "direction": "LONG", "confidence": (os_ - rsi) / os_, "reason": f"RSI {rsi:.1f}<{os_} oversold"}
    if rsi > ob:
        return {"strategy_id": "rsi_reversal_v1", "direction": "SHORT", "confidence": (rsi - ob) / (100 - ob), "reason": f"RSI {rsi:.1f}>{ob} overbought"}
    return {"strategy_id": "rsi_reversal_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": f"RSI {rsi:.1f} notr"}


def _donchian_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    try:
        c, h, l = float(row.get("Close")), float(row.get("don_high")), float(row.get("don_low"))
    except (TypeError, ValueError):
        return {"strategy_id": "donchian_breakout_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "Donchian yok"}
    if c > h:
        return {"strategy_id": "donchian_breakout_v1", "direction": "LONG", "confidence": 0.8, "reason": f"Close {c:.2f}>DonHigh {h:.2f}"}
    if c < l:
        return {"strategy_id": "donchian_breakout_v1", "direction": "SHORT", "confidence": 0.8, "reason": f"Close {c:.2f}<DonLow {l:.2f}"}
    return {"strategy_id": "donchian_breakout_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "kanal ici"}


def add_supertrend(df: pd.DataFrame, period: int = SUPERTREND_PERIOD, mult: float = SUPERTREND_MULT) -> pd.DataFrame:
    out = df.copy()
    high, low, close = out["High"], out["Low"], out["Close"]
    hl2 = (high + low) / 2
    atr = (high - low).rolling(period).mean()  # basit ATR; sinyal_engine ATR'si de mevcut
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    st = pd.Series(index=out.index, dtype=float)
    direction = pd.Series(index=out.index, dtype=float)
    for i in range(len(out)):
        if i == 0:
            st.iloc[i] = lower.iloc[i]
            direction.iloc[i] = 1.0
            continue
        prev_st = st.iloc[i - 1]
        c = close.iloc[i]
        ub, lb = upper.iloc[i], lower.iloc[i]
        if pd.isna(ub) or pd.isna(lb) or pd.isna(c):
            st.iloc[i] = prev_st
            direction.iloc[i] = direction.iloc[i - 1]
            continue
        if direction.iloc[i - 1] == 1.0:
            lb = max(lb, prev_st) if pd.notna(prev_st) else lb
            if c < lb:
                direction.iloc[i] = -1.0
                st.iloc[i] = ub
            else:
                direction.iloc[i] = 1.0
                st.iloc[i] = lb
        else:
            ub = min(ub, prev_st) if pd.notna(prev_st) else ub
            if c > ub:
                direction.iloc[i] = 1.0
                st.iloc[i] = lb
            else:
                direction.iloc[i] = -1.0
                st.iloc[i] = ub
    out["ST_LINE"] = st
    out["ST_DIR"] = direction
    return out


def add_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.DataFrame:
    out = df.copy()
    high, low, close = out["High"], out["Low"], out["Close"]
    up = high.diff()
    dn = -low.diff()
    plus_dm = ((up > dn) & (up > 0)).astype(float) * up
    minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_w = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    out["PLUS_DI"] = plus_di
    out["MINUS_DI"] = minus_di
    out["ADX"] = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return out


def add_vwap(df: pd.DataFrame, window: int = VWAP_WINDOW) -> pd.DataFrame:
    out = df.copy()
    tp = (out["High"] + out["Low"] + out["Close"]) / 3
    pv = tp * out["Volume"].replace(0, float("nan"))
    out["VWAP"] = pv.rolling(window).sum() / out["Volume"].rolling(window).sum()
    return out


def add_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    out = df.copy()
    ll = out["Low"].rolling(k_period).min()
    hh = out["High"].rolling(k_period).max()
    rng = (hh - ll).replace(0, float("nan"))
    out["STOCH_K"] = 100 * (out["Close"] - ll) / rng
    out["STOCH_D"] = out["STOCH_K"].rolling(d_period).mean()
    return out


def _supertrend_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    d = _f(row.get("ST_DIR"))
    if d is None:
        return {"strategy_id": "supertrend_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "SuperTrend yok"}
    if d > 0:
        return {"strategy_id": "supertrend_v1", "direction": "LONG", "confidence": 0.7, "reason": "SuperTrend LONG"}
    return {"strategy_id": "supertrend_v1", "direction": "SHORT", "confidence": 0.7, "reason": "SuperTrend SHORT"}


def _adx_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    adx, pdi, mdi = _f(row.get("ADX")), _f(row.get("PLUS_DI")), _f(row.get("MINUS_DI"))
    if adx is None or pdi is None or mdi is None:
        return {"strategy_id": "adx_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "ADX yok"}
    if adx < ADX_THRESHOLD:
        return {"strategy_id": "adx_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": f"ADX {adx:.1f} trendsiz"}
    conf = min((adx - ADX_THRESHOLD) / 30 + 0.5, 1.0)
    if pdi > mdi:
        return {"strategy_id": "adx_v1", "direction": "LONG", "confidence": conf, "reason": f"ADX {adx:.1f} +DI>-DI"}
    return {"strategy_id": "adx_v1", "direction": "SHORT", "confidence": conf, "reason": f"ADX {adx:.1f} -DI>+DI"}


def _vwap_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    c, v = _f(row.get("Close")), _f(row.get("VWAP"))
    if c is None or v is None or v == 0:
        return {"strategy_id": "vwap_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "VWAP yok"}
    dev = (c - v) / v
    if dev > 0:
        return {"strategy_id": "vwap_v1", "direction": "LONG", "confidence": min(abs(dev) * 50, 1.0), "reason": f"Close VWAP uzeri ({dev:+.2%})"}
    if dev < 0:
        return {"strategy_id": "vwap_v1", "direction": "SHORT", "confidence": min(abs(dev) * 50, 1.0), "reason": f"Close VWAP alti ({dev:+.2%})"}
    return {"strategy_id": "vwap_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "VWAP esit"}


def _bollinger_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    c, u, l = _f(row.get("Close")), _f(row.get("BB_UPPER")), _f(row.get("BB_LOWER"))
    if c is None or u is None or l is None:
        return {"strategy_id": "bollinger_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "BB yok"}
    if c < l:
        return {"strategy_id": "bollinger_v1", "direction": "LONG", "confidence": 0.7, "reason": f"Close {c:.2f}<BB alt {l:.2f}"}
    if c > u:
        return {"strategy_id": "bollinger_v1", "direction": "SHORT", "confidence": 0.7, "reason": f"Close {c:.2f}>BB ust {u:.2f}"}
    return {"strategy_id": "bollinger_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "BB ici"}


def _atr_breakout_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    o, c, h, l, atr = (_f(row.get(k)) for k in ("Open", "Close", "High", "Low", "ATR"))
    if o is None or c is None or h is None or l is None or atr is None or atr == 0:
        return {"strategy_id": "atr_breakout_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "ATR veri yok"}
    body = abs(c - o)
    if body < 1.5 * atr:
        return {"strategy_id": "atr_breakout_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "genisleme yok"}
    conf = min(body / (2.5 * atr), 1.0)
    if c > o:
        return {"strategy_id": "atr_breakout_v1", "direction": "LONG", "confidence": conf, "reason": f"govde {body:.2f}>1.5xATR yonu LONG"}
    return {"strategy_id": "atr_breakout_v1", "direction": "SHORT", "confidence": conf, "reason": f"govde {body:.2f}>1.5xATR yonu SHORT"}


def _stoch_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    k, d = _f(row.get("STOCH_K")), _f(row.get("STOCH_D"))
    if k is None or d is None:
        return {"strategy_id": "stoch_reversal_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "Stokastik yok"}
    if k < 20 and d < 20 and k > d:
        return {"strategy_id": "stoch_reversal_v1", "direction": "LONG", "confidence": 0.7, "reason": f"%K {k:.1f} asiri satimdan dondu"}
    if k > 80 and d > 80 and k < d:
        return {"strategy_id": "stoch_reversal_v1", "direction": "SHORT", "confidence": 0.7, "reason": f"%K {k:.1f} asiri alimdan dondu"}
    return {"strategy_id": "stoch_reversal_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": f"%K {k:.1f} notr"}


def _rs_signal(row: pd.Series, cfg: dict, rs_ratio: float | None = None, rs_trend: float | None = None) -> dict[str, Any]:
    if rs_ratio is None or rs_trend is None:
        return {"strategy_id": "rs_benchmark_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "benchmark yok"}
    if rs_trend > 0:
        return {"strategy_id": "rs_benchmark_v1", "direction": "LONG", "confidence": min(abs(rs_trend) * 30, 1.0), "reason": f"benchmark'a gore guclu ({rs_trend:+.2%})"}
    if rs_trend < 0:
        return {"strategy_id": "rs_benchmark_v1", "direction": "SHORT", "confidence": min(abs(rs_trend) * 30, 1.0), "reason": f"benchmark'a gore zayif ({rs_trend:+.2%})"}
    return {"strategy_id": "rs_benchmark_v1", "direction": "NEUTRAL", "confidence": 0.0, "reason": "benchmark'a esit"}


def compute_rs(df: pd.DataFrame, benchmark: pd.Series | list[float] | None, window: int = 20) -> tuple[float | None, float | None]:
    """Fiyat/benchmark oraninin window'luk degisimi. Hizalanmis benchmark close serisi ister."""
    if benchmark is None:
        return None, None
    try:
        b = pd.Series(benchmark).reset_index(drop=True).tail(len(df)).reset_index(drop=True)
        c = df["Close"].reset_index(drop=True).tail(len(b)).reset_index(drop=True)
    except (ValueError, TypeError, KeyError):
        return None, None
    if len(c) < window + 1:
        return None, None
    ratio = c / b.replace(0, float("nan"))
    if ratio.isna().any():
        return None, None
    now = float(ratio.iloc[-1])
    past = float(ratio.iloc[-1 - window])
    if past == 0 or not math.isfinite(now) or not math.isfinite(past):
        return None, None
    return now, (now - past) / abs(past)


def _smc_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    res = smc_signal_from_row(row)
    res["family"] = "structure"
    return res


def _or_signal(row: pd.Series, cfg: dict) -> dict[str, Any]:
    res = or_signal_from_row(row)
    res["family"] = "breakout"
    return res


def run_all_strategies_row(row: pd.Series, config: dict | None = None, rs: tuple[float | None, float | None] | None = None) -> list[dict[str, Any]]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    out = [
        _ema_signal(row, cfg), _rsi_signal(row, cfg), _donchian_signal(row, cfg),
        _supertrend_signal(row, cfg), _adx_signal(row, cfg),
        _vwap_signal(row, cfg), _bollinger_signal(row, cfg),
        _atr_breakout_signal(row, cfg), _stoch_signal(row, cfg),
        _rs_signal(row, cfg, *(rs or (None, None))),
        _smc_signal(row, cfg), _or_signal(row, cfg),
    ]
    for r in out:
        r["family"] = next(s["family"] for s in STRATEGIES if s["strategy_id"] == r["strategy_id"])
    return out


def _enrich(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    out = add_donchian(add_indicators(df, config))
    out = add_supertrend(out)
    out = add_adx(out)
    out = add_vwap(out)
    out = add_stochastic(out)
    out = add_smc_structure(out)
    out = add_opening_range(out)
    return out


def run_all_strategies_df(df: pd.DataFrame, config: dict | None = None, benchmark: pd.Series | list[float] | None = None) -> list[dict[str, Any]]:
    rs = compute_rs(df, benchmark)
    return run_all_strategies_row(_enrich(df, config).iloc[-1], config, rs=rs)


def agreement_summary(results: list[dict[str, Any]], regime: str | None = None) -> dict[str, Any]:
    longs = sum(1 for r in results if r["direction"] == "LONG")
    shorts = sum(1 for r in results if r["direction"] == "SHORT")
    neuts = sum(1 for r in results if r["direction"] == "NEUTRAL")
    total = len(results) or 1
    if longs >= 2 and longs > shorts:
        consensus = "LONG"
    elif shorts >= 2 and shorts > longs:
        consensus = "SHORT"
    else:
        consensus = "NO_CONSENSUS"
    out: dict[str, Any] = {
        "long": longs, "short": shorts, "neutral": neuts,
        "consensus": consensus,
        "conflict": longs > 0 and shorts > 0,
        "total": len(results),
        "share": round(max(longs, shorts) / total, 3),
        # Agreement score (0..1) based on consensus strength
        "agreement_score": round(max(longs, shorts) / total, 3) if consensus != "NO_CONSENSUS" else 0.0,
        # Family breakdown using ACTUAL family names from strategy results
        "family_breakdown": {},
        # Per-strategy data for correlation-adjusted scoring
        "strategy_details": [
            {
                "strategy_id": r.get("strategy_id", ""),
                "family": r.get("family", ""),
                "direction": r.get("direction", "NEUTRAL"),
                "confidence": r.get("confidence", 0.0),
            }
            for r in results
        ],
    }

    # Populate family_breakdown from results using actual family field
    family_dirs: dict[str, set[str]] = {}
    for r in results:
        fam = r.get("family", "unknown")
        d = r.get("direction", "NEUTRAL")
        if d != "NEUTRAL":
            family_dirs.setdefault(fam, set()).add(d)
    out["family_breakdown"] = {fam: list(dirs) for fam, dirs in family_dirs.items()}
    def _base_regime(regime: str) -> str:
        """Map enriched regime names back to base for weighting logic."""
        if regime in ("UPTREND_STRONG", "UPTREND_WEAK"):
            return "UPTREND"
        if regime in ("DOWNTREND_STRONG", "DOWNTREND_WEAK"):
            return "DOWNTREND"
        if regime in ("RANGE_LOW_VOL", "RANGE_HIGH_VOL", "EXPANDING_VOLATILITY"):
            return "RANGE"
        return regime

    base_regime = _base_regime(regime) if regime else None
    if base_regime:
        out["weighted"] = regime_weighted_vote(results, base_regime)
    return out


TREND_FAMILIES = {"trend", "breakout", "volume"}
MR_FAMILIES = {"mean_reversion"}

_EVO_CACHE: dict[str, Any] = {"mtime": 0.0, "statuses": {}}


def _evolution_statuses() -> dict[str, str]:
    """strategy_evolution_latest.json'dan status haritasi (mtime onbellekli)."""
    import os as _os
    from pathlib import Path as _Path
    import json as _json
    p = _Path(__file__).resolve().parent / "agentspace" / "agentspace" / "logs" / "strategy_evolution_latest.json"
    try:
        mt = _os.path.getmtime(p)
    except OSError:
        return {}
    if mt != _EVO_CACHE["mtime"]:
        try:
            rep = _json.loads(p.read_text(encoding="utf-8"))
            _EVO_CACHE["statuses"] = {k: v.get("status", "WATCH") for k, v in rep.get("strategies", {}).items()}
        except (ValueError, AttributeError, OSError):
            _EVO_CACHE["statuses"] = {}
        _EVO_CACHE["mtime"] = mt
    return _EVO_CACHE["statuses"]


def regime_weighted_vote(results: list[dict[str, Any]], regime: str, statuses: dict[str, str] | None = None) -> dict[str, Any]:
    """Rejime gore aile agirlikli oy: trendde trend/breakout, yatayda mean-reversion agirlikli.
    Evrim durumlari carpan uygular: DEMOTE x0.25, PROMOTE x1.25."""
    if statuses is None:
        statuses = _evolution_statuses()
    long_w = short_w = 0.0
    voters: list[str] = []
    demoted: list[str] = []
    for r in results:
        fam = r.get("family", "")
        if regime in ("UPTREND", "DOWNTREND"):
            w = 1.5 if fam in TREND_FAMILIES else (0.5 if fam in MR_FAMILIES else 1.0)
        elif regime == "RANGE":
            w = 1.5 if fam in MR_FAMILIES else (0.5 if fam in TREND_FAMILIES else 1.0)
        else:
            w = 1.0
        st = statuses.get(r["strategy_id"], "WATCH")
        if st == "DEMOTE":
            w *= 0.25
            demoted.append(r["strategy_id"])
        elif st == "PROMOTE":
            w *= 1.25
        # Rejim-momentum: trend yönündeki oylar güçlenir, tersi zayıflar
        if regime == "UPTREND":
            w *= 1.25 if r["direction"] == "LONG" else (0.75 if r["direction"] == "SHORT" else 1.0)
        elif regime == "DOWNTREND":
            w *= 1.25 if r["direction"] == "SHORT" else (0.75 if r["direction"] == "LONG" else 1.0)
        if r["direction"] == "LONG":
            long_w += w * (0.5 + r.get("confidence", 0.5))
            voters.append(r["strategy_id"])
        elif r["direction"] == "SHORT":
            short_w += w * (0.5 + r.get("confidence", 0.5))
            voters.append(r["strategy_id"])
    if long_w > short_w and long_w >= 1.0:
        lean = "LONG"
    elif short_w > long_w and short_w >= 1.0:
        lean = "SHORT"
    else:
        lean = "NO_LEAN"
    return {"lean": lean, "long_w": round(long_w, 2), "short_w": round(short_w, 2), "regime": regime, "demoted": demoted}
