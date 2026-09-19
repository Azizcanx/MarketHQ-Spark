# -*- coding: utf-8 -*-
"""
MarketHQ Research-Backed Signal/Setup Engine V1
=================================================

Girdi: sembol + timeframe + OHLCV DataFrame
Cikti: SetupModel (rich object) + WHY paneli (research-backed reasoning)

AKIŞ
----
1. setup_engine_v1.build_setup() -> raw setup
2. SetupModel olustur (structure, liquidity, evidence, historical)
3. setup_quality_engine_v2 ile 10-boyutlu quality scoring (quality_v2)
4. WHY paneli (markdown) uret
5. AgentSpace evidence + test card kaydet

GUVENLIK
--------
Research only. EXECUTION_ENABLED = False.
Canli islem yok, broker baglantisi yok.
"""

from __future__ import annotations

import math
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from setup_engine_v1 import build_setup, detect_regime
from strategy_registry_v1 import run_all_strategies_df, agreement_summary
from signal_engine import add_indicators, DEFAULT_CONFIG, calculate_risk_levels
from setup_object_model import (
    SetupModel, MarketInfo, TimeframeInfo, RegimeInfo, BiasInfo,
    StructureInfo, LiquidityInfo, EntryZone, Confirmation,
    InvalidationLevel, TargetLevel, Targets, RiskReward,
    Evidence, HistoricalValidation, QualityScore, Reasoning,
    InvalidationConditions, Outcome, LearningMetadata,
)
from setup_quality_engine_v2 import score_setup_quality_v2 as score_setup_quality
from regime_filter import apply_regime_filter, get_regime_filter_status
from setup_outcome_tracker import get_historical_stats


EXECUTION_ENABLED = False
ENGINE_NAME = "MARKETHQ_RESEARCH_SETUP_ENGINE"
ENGINE_VERSION = "V1"


def _atr_pct(atr: float | None, price: float) -> float | None:
    if atr is None or not math.isfinite(atr) or price <= 0:
        return None
    return round(atr / price * 100, 3)


def _reward_risk(entry: float | None, target: float | None, invalidation: float | None) -> dict[str, Any]:
    if not all(x is not None and math.isfinite(x) for x in (entry, target, invalidation)):
        return {"reward_risk": None, "reward": None, "risk": None}
    reward = abs(cast(float, target) - cast(float, entry))
    risk = abs(cast(float, entry) - cast(float, invalidation))
    if risk == 0:
        return {"reward_risk": None, "reward": reward, "risk": 0}
    return {
        "reward_risk": round(reward / risk, 2),
        "reward": round(reward, 4),
        "risk": round(risk, 4),
    }


def _build_structure_info(df: pd.DataFrame) -> StructureInfo:
    """SMC structure'dan StructureInfo cikar — BOS/CHoCH, sweep, displacement."""
    try:
        from smc_structure_v1 import find_swings, structure_events, SWING_ORDER, smc_signal_from_row
        from signal_engine import add_indicators

        enriched = add_indicators(df, DEFAULT_CONFIG)
        last = enriched.iloc[-1]
        atr = float(last.get("ATR", 0) or 0)

        swings = find_swings(df, order=SWING_ORDER)
        events = structure_events(df, swings, atr) if atr > 0 else []

        # Find last BOS/CHoCH event
        structure_type = ""
        displacement = 0.0
        last_swing_h: float | None = None
        last_swing_l: float | None = None

        for ev in reversed(events[-20:]):
            if ev.get("type") in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
                structure_type = ev["type"]
                displacement = ev.get("displacement", 0)
                break

        # Swing highs/lows
        swing_highs = []
        swing_lows = []
        for s in swings:
            if s["kind"] == "H":
                swing_highs.append({"price": s["price"], "idx": s["idx"]})
            else:
                swing_lows.append({"price": s["price"], "idx": s["idx"]})

        last_swing_high = swing_highs[-1]["price"] if swing_highs else None
        last_swing_low = swing_lows[-1]["price"] if swing_lows else None

        # Displacement quality
        disp_quality = "none"
        if abs(displacement) >= 0.5:
            disp_quality = "strong"
        elif abs(displacement) >= 0.2:
            disp_quality = "weak"

        return StructureInfo(
            has_structure=len(events) > 0,
            structure_type=structure_type,
            swing_highs=swing_highs[-5:],
            swing_lows=swing_lows[-5:],
            last_swing_high=last_swing_high,
            last_swing_low=last_swing_low,
            displacement=displacement,
            displacement_quality=disp_quality,
        )
    except Exception:
        return StructureInfo()


def _build_liquidity_info(df: pd.DataFrame, setup: dict[str, Any]) -> LiquidityInfo:
    """Liquidity context from price action."""
    try:
        atr = setup.get("atr") or 0
        entry = setup.get("entry_price") or 0

        lookback = 20
        recent_high = float(df["High"].tail(lookback).max()) if len(df) >= lookback else entry
        recent_low = float(df["Low"].tail(lookback).min()) if len(df) >= lookback else entry

        buy_liq = recent_high if recent_high > entry else None
        sell_liq = recent_low if recent_low < entry else None

        sweep_detected = False
        sweep_side = ""
        sweep_dist = 0.0

        # Check if price swept beyond recent high/low then closed back
        if len(df) >= 3:
            last_close = float(df["Close"].iloc[-1])
            prev_high = float(df["High"].iloc[-2])
            prev_low = float(df["Low"].iloc[-2])
            if prev_high > recent_high * 1.001 and last_close < prev_high:
                sweep_detected = True
                sweep_side = "sell"
                sweep_dist = (prev_high - last_close) / atr if atr else 0
            elif prev_low < recent_low * 0.999 and last_close > prev_low:
                sweep_detected = True
                sweep_side = "buy"
                sweep_dist = (last_close - prev_low) / atr if atr else 0

        desc_parts = []
        if buy_liq:
            desc_parts.append(f"buy-side likidite: {buy_liq:.4f}")
        if sell_liq:
            desc_parts.append(f"sell-side likidite: {sell_liq:.4f}")
        if sweep_detected:
            desc_parts.append(f"sweep algilandi ({sweep_side}-side, {sweep_dist:.2f} ATR)")

        return LiquidityInfo(
            buy_side_liquidity=buy_liq,
            sell_side_liquidity=sell_liq,
            liquidity_sweep_detected=sweep_detected,
            liquidity_side=sweep_side,
            sweep_distance_atr=sweep_dist,
            description="; ".join(desc_parts) if desc_parts else "likidite analizi yapıldı",
        )
    except Exception:
        return LiquidityInfo()


def _build_historical_validation(
    symbol: str,
    regime: str,
    direction: str,
    setup_type: str,
) -> HistoricalValidation:
    """Look up similar setups from setup_outcomes tracker with survivorship correction."""
    try:
        from setup_outcome_tracker import get_historical_stats

        stats = get_historical_stats(
            symbol=symbol,
            regime=regime,
            direction=direction,
            setup_type=setup_type,
            min_samples=3,
        )

        # Survivorship bias note
        notes = stats.get("notes", "")
        if stats.get("available"):
            notes += " | Survivorship bias: DB sadece mevcut sembolleri içeriyor, iptal edilenler eksik"

        return HistoricalValidation(
            available=stats.get("available", False),
            similar_count=stats.get("similar_count", 0),
            win_rate=stats.get("win_rate"),
            avg_return=stats.get("avg_return"),
            avg_return_20d=stats.get("avg_return_20d"),
            best_return=stats.get("best_return"),
            worst_return=stats.get("worst_return"),
            regime_match=regime,
            lookup_method="setup_signature",
            notes=notes,
        )
    except Exception:
        return HistoricalValidation(available=False, notes="Lookup hatasi")


def _classify_setup_type(
    regime: str,
    structure_type: str,
    agreement_summary_str: str,
) -> str:
    """Derive setup type signature from regime + structure + agreement."""
    parts = []

    # Structure component
    if structure_type:
        if "CHoCH" in structure_type:
            parts.append("choch")
        elif "BOS" in structure_type:
            parts.append("bos")
        else:
            parts.append(structure_type.lower())
    else:
        parts.append("indicator")

    # Regime component
    if regime.startswith("UPTREND"):
        parts.append("uptrend")
    elif regime.startswith("DOWNTREND"):
        parts.append("downtrend")
    elif regime.startswith("RANGE"):
        parts.append("range")
    elif regime == "EXPANDING_VOLATILITY":
        parts.append("expanding_vol")

    # Direction component
    if "LONG" in agreement_summary_str:
        parts.append("long")
    elif "SHORT" in agreement_summary_str:
        parts.append("short")

    return "_".join(parts) if parts else "unknown"


def build_research_setup(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    timeframe: str = "1h",
    config: dict[str, Any] | None = None,
    benchmark: pd.Series | list[float] | None = None,
) -> dict[str, Any]:
    """
    Research-backed setup uret — SetupModel + quality scoring.

    Returns backward-compatible dict (setup, why_panel, confidence, ...)
    PLUS 'model' key with the SetupModel object.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    # Step 1: raw setup
    raw_setup = build_setup(df, timeframe, config, benchmark=benchmark, symbol=symbol)

    # Step 2: enriched data
    enriched = add_indicators(df, config)
    last = enriched.iloc[-1]
    results = run_all_strategies_df(df, config, benchmark=benchmark)
    regime_result = detect_regime(last, df)
    regime = regime_result.get("regime", "UNKNOWN") if isinstance(regime_result, dict) else regime_result
    agree = agreement_summary(results, regime=regime)

    # Family-level conflict detection — use actual family field from strategy results
    family_dirs: dict[str, set[str]] = {}
    for r in results:
        fam = r.get("family", "unknown")
        d = r.get("direction", "NEUTRAL")
        if d != "NEUTRAL":
            family_dirs.setdefault(fam, set()).add(d)
    conflicts = [
        {"family": fam, "directions": list(dirs), "severity": "high"}
        for fam, dirs in family_dirs.items()
        if len({d for d in dirs if d != "NEUTRAL"}) > 1
    ]

    # Step 3: structure + liquidity
    structure_info = _build_structure_info(df)
    liquidity_info = _build_liquidity_info(df, raw_setup)

    # Step 4: reward:risk
    entry = raw_setup.get("entry_price", 0)
    target = raw_setup.get("target")
    invalidation = raw_setup.get("invalidation")
    rr = _reward_risk(entry, target, invalidation)

    # Step 5: historical validation
    direction = raw_setup.get("direction", "NEUTRAL")
    setup_type = _classify_setup_type(regime, structure_info.structure_type, direction)
    hist_val = _build_historical_validation(symbol, regime, direction, setup_type)

    # Step 6: Build SetupModel
    atr = raw_setup.get("atr")
    sma_fast = float(last.get("SMA_FAST", 0) or 0)
    sma_slow = float(last.get("SMA_SLOW", 0) or 0)
    factors = regime_result.get("factors", {}) if isinstance(regime_result, dict) else {}
    reg = RegimeInfo(
        regime=regime,
        confidence=regime_result.get("confidence", 0.8) if isinstance(regime_result, dict) else 0.8,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        detail=regime_result.get("detail", f"SMA_FAST={sma_fast:.2f} vs SMA_SLOW={sma_slow:.2f}") if isinstance(regime_result, dict) else f"SMA_FAST={sma_fast:.2f} > SMA_SLOW={sma_slow:.2f}" if sma_fast > sma_slow else f"SMA_FAST={sma_fast:.2f} < SMA_SLOW={sma_slow:.2f}",
        adx=factors.get("adx", 0.0),
        atr_pct=factors.get("atr_pct", 0.0),
        vol_ratio=factors.get("vol_ratio"),
        vol_confirmed=factors.get("vol_confirmed", False),
        structure_score=factors.get("structure_score", 0),
    )

    bias = BiasInfo(
        direction=direction,
        bias_strength=agree.get("agreement_score", 0),
        reason=f"{agree.get('consensus', 'NO_CONSENSUS')} konsensüsü — {agree.get('total_strategies', 0)} strateji",
    )

    zone_width = 0.5 * atr if atr else 0.2
    zone = EntryZone(
        center=entry,
        low=raw_setup.get("entry_zone", [entry, entry])[0],
        high=raw_setup.get("entry_zone", [entry, entry])[1],
        width_atr=zone_width / atr if atr else 0.25,
        source="atr_based",
        quality="medium",
        touches=1,
    )

    conf = Confirmation(
        strategy_count=len(results),
        strategies=[{"strategy_id": r.get("strategy_id"), "direction": r.get("direction"), "confidence": r.get("confidence")} for r in results],
        family_agreement={
            fam: (dirs[0] if dirs else "NEUTRAL")
            for fam, dirs in agree.get("family_breakdown", {}).items()
        },
        agreement_score=agree.get("agreement_score", 0),
        strongest_indicator="",
        disqualifiers=[c["family"] for c in conflicts],
        family_conflicts=conflicts,
    )

    inv_clarity = "clear" if invalidation else "fuzzy"
    inv = InvalidationLevel(
        price=invalidation,
        distance_atr=abs(entry - invalidation) / atr if (invalidation and atr) else 0,
        type="structural",
        clarity=inv_clarity,
        reasoning=f"ATR×2.0 stop-loss — {invalidation:.4f}",
    )

    tgt_primary = None
    if target:
        tgt_primary = TargetLevel(
            price=target,
            distance_atr=abs(target - entry) / atr if atr else 0,
            type="ATR_target",
            priority="primary",
            reasoning=f"ATR×3.0 hedef — {target:.4f}",
        )

    targets = Targets(primary=tgt_primary)

    rr_obj = RiskReward(
        reward_risk_ratio=rr.get("reward_risk"),
        reward=rr.get("reward"),
        risk=rr.get("risk"),
        breakeven_age=0.5,
        feasibility="high" if rr.get("reward_risk") and rr["reward_risk"] >= 2 else "medium" if rr.get("reward_risk") and rr["reward_risk"] >= 1.5 else "low",
    )

    evidence = Evidence(
        supporting=[{"source": s, "type": "strategy"} for s in raw_setup.get("supporting", [])],
        conflicting=[{"source": s, "type": "strategy"} for s in raw_setup.get("opposing", [])],
        evidence_score=agree.get("agreement_score", 0),
    )

    reasoning = Reasoning(
        entry_rationale=[
            f"Entry zone [{zone.low:.4f}, {zone.high:.4f}] — ATR bazli ±{zone.width_atr:.2f}x ATR",
            f"Rejim: {regime} — {'yukari' if direction == 'LONG' else 'asagi'} direction",
            f"Strateji destegi: {len(raw_setup.get('supporting', []))}/{len(results)} strateji",
        ],
        invalidation_rationale=[f"Stop-loss {invalidation:.4f} — entry'den {abs(entry - invalidation):.4f} uzakta"] if invalidation else ["Konsensus yok — invalidation yok"],
        target_rationale=[f"Hedef {target:.4f} — {rr.get('reward_risk', '?')}:1 R:R"] if target else ["Konsensus yok — hedef yok"],
        regime_context=regime,
        agreement_summary=f"{agree.get('consensus', '?')} ({agree.get('agreement_score', 0):.0%})",
        key_insight=f"Setup: {setup_type} | Regime: {regime} | Direction: {direction}",
        warnings=[],
    )

    model = SetupModel(
        setup_id=raw_setup.get("setup_id", ""),
        symbol=symbol,
        timeframe=timeframe,
        generated_at=datetime.now().isoformat(),
        market=MarketInfo(symbol=symbol),
        timeframe_info=TimeframeInfo(timeframe=timeframe, bar_count=len(df)),
        regime=reg,
        bias=bias,
        structure=structure_info,
        liquidity=liquidity_info,
        setup_type=setup_type,
        entry_zone=zone,
        confirmation=conf,
        invalidation=inv,
        targets=targets,
        risk_reward=rr_obj,
        supporting_strategies=raw_setup.get("supporting", []),
        conflicting_strategies=raw_setup.get("opposing", []),
        evidence=evidence,
        historical_validation=hist_val,
        reasoning=reasoning,
        invalidation_conditions=InvalidationConditions(
            price_condition=f"Kapanis {invalidation:.4f} altina cikarsa iptal" if invalidation else "",
            time_condition="",
            alternative_signal="",
        ),
        research_only=True,
        engine=ENGINE_NAME,
        version=ENGINE_VERSION,
    )

    # Step 7: Quality scoring
    # Get sample size for confidence / shrinkage
    hist_stats = get_historical_stats(
        symbol=symbol, regime=regime,
        direction=direction, setup_type=setup_type, min_samples=0,
    )
    sample_size = hist_stats.get("similar_count", 0)

    quality = score_setup_quality(model, sample_size=sample_size)
    model.quality = quality

    # Step 7b: Regime filter — data-driven eligibility/penalty
    regime = reg.regime
    setup_type = setup_type
    filter_decision = apply_regime_filter(model)

    # Extract filter decision for return dict
    filter_status = getattr(model, "regime_filter_status", filter_decision.status)
    filter_compat = getattr(model, "regime_compatibility", filter_decision.compatibility)
    filter_reason = getattr(model, "regime_reason", filter_decision.reason)

    # Step 8: Learning metadata
    model.learning_metadata = LearningMetadata(
        setup_type_signature=setup_type,
        regime=regime,
        confirmation_combo=",".join(model.confirmation.family_agreement.keys()),
        learning_priority=quality.overall,
        next_research_question=f"Bu setup tipi ({setup_type}) {regime} ortaminda ne kadar surekli calisir?",
    )

    # Step 9: Research flags
    flags = _research_flags(model, quality)
    model.quality.flags = flags

    # Backward-compatible return
    # Use model.quality.overall (post-regime-filter) not quality.overall (pre-filter)
    filtered_quality = model.quality
    return {
        "setup": raw_setup,
        "model": model,
        "why_panel": {
            "entry_rationale": reasoning.entry_rationale,
            "invalidation_rationale": reasoning.invalidation_rationale,
            "target_rationale": reasoning.target_rationale,
            "regime_context": regime,
            "agreement_analysis": {
                "total_strategies": len(results),
                "consensus": agree.get("consensus", "NO_CONSENSUS"),
                "agreement_score": agree.get("agreement_score", 0),
                "direction_counts": agree.get("direction_counts", {}),
                "family_breakdown": agree.get("family_breakdown", {}),
            },
            "reward_risk": rr,
            "atr_pct": _atr_pct(atr, entry),
            "research_flags": flags,
        },
        "confidence": {
            "score": filtered_quality.overall,
            "factors": filtered_quality.breakdown,
            "max_possible": 1.0,
        },
        "quality": {
            "overall": filtered_quality.overall,
            "breakdown": filtered_quality.breakdown,
            "flags": filtered_quality.flags,
            "verdict": _verdict(filtered_quality.overall),
        },
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "research_only": True,
        "generated_at": datetime.now().isoformat(),
        "regime_filter_status": filter_status,
        "regime_compatibility": filter_compat,
        "regime_reason": filter_reason,
    }


def _research_flags(model: SetupModel, quality: QualityScore) -> list[str]:
    flags = []

    if quality.overall < 0.3:
        flags.append("DUSUK_GUVENLILIK: setup bilincli olarak kullanilmali")
    elif quality.overall < 0.55:
        flags.append("ORTA_GUVENLILIK: ek onay oneren setup")

    # Data-driven regime filter instead of hardcoded RANGE blocking
    regime_status = getattr(model, "regime_filter_status", None)
    if regime_status == "PENALTY":
        flags.append(f"REGIME_PENALTY: {getattr(model, 'regime_reason', '')}")
        flags.append("KALITE_DUSURULDU: negatif beklenti, riskli ortam")
    elif regime_status == "CONSERVATIVE":
        flags.append(f"REGIME_CONSERVATIVE: {getattr(model, 'regime_reason', '')}")
        flags.append("DUSUK_GUVENLILIK: siniz veri, ek onay oneren")

    if not model.supporting_strategies:
        flags.append("STRATEJI_DESTEGI_YOK: consensus yoksa setup zayıf")

    if model.risk_reward.reward_risk_ratio and model.risk_reward.reward_risk_ratio < 1.5:
        flags.append("KOTAJIZI_DUSUK: reward:risk yetersiz")

    atr_pct_val = _atr_pct(model.timeframe_info.bar_count, model.entry_zone.center)
    if atr_pct_val and atr_pct_val > 3.0:
        flags.append("YUKSEK_VOLATILITE: ATR geniş, invalidation uzakta")

    flags.append("RESEARCH_ONLY: canli islem yok")
    return flags


def _verdict(overall: float) -> str:
    if overall >= 0.75:
        return "STRONG_SETUP"
    elif overall >= 0.55:
        return "MODERATE_SETUP"
    elif overall >= 0.35:
        return "WEAK_SETUP"
    else:
        return "POOR_SETUP"


def format_why_panel(setup_result: dict[str, Any]) -> str:
    """WHY paneli — SetupModel formatindan markdown."""
    model = setup_result.get("model")
    if model:
        from setup_object_model import format_setup_markdown
        return format_setup_markdown(model)

    # Fallback to old dict format
    wp = setup_result["why_panel"]
    conf = setup_result["confidence"]
    setup = setup_result["setup"]

    lines = [
        "## 🔬 Research WHY Paneli",
        "",
        f"**Sembol:** {setup.get('symbol', '?')} | **Dönem:** {setup.get('timeframe', '?')} | **Rejim:** {wp.get('regime_context', '?')}",
        f"**Yön:** {setup.get('direction', '?')} | **Güven:** {conf.get('score', 0):.0%}",
        "",
        "### Entry Gerekcesi",
    ]
    for r in wp.get("entry_rationale", []):
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### Invalidation Gerekcesi")
    for r in wp.get("invalidation_rationale", []):
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### Hedef Gerekcesi")
    for r in wp.get("target_rationale", []):
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### ⚠️ Araştırma Bayrakları")
    for flag in wp.get("research_flags", []):
        lines.append(f"- {flag}")

    # Regime filter status (dict format fallback)
    rf_status = setup.get("regime_filter_status")
    if rf_status:
        rf_compat = setup.get("regime_compatibility", 0.0)
        rf_reason = setup.get("regime_reason", "")
        lines.append("")
        lines.append("### Regime Filter")
        lines.append(f"- Durum: {rf_status}")
        lines.append(f"- Uyum: {rf_compat:.0%}")
        lines.append(f"- Sebep: {rf_reason}")

    lines.append("")
    lines.append(f"*Sonuç: {setup_result['generated_at']} — {ENGINE_NAME} {ENGINE_VERSION}*")
    return "\n".join(lines)


# CLI entry point
def main() -> None:
    import sys

    if len(sys.argv) < 3:
        print(f"Kullanim: python3 {sys.argv[0]} SYMBOL TIMEFRAME")
        print("Ornek: python3 research_setup_engine.py THYAO.IS 1h")
        sys.exit(1)

    symbol = sys.argv[1]
    timeframe = sys.argv[2]

    import yfinance as yf

    period_map = {"1m": "5d", "5m": "10d", "15m": "20d", "1h": "60d", "4h": "6mo", "1d": "2y"}
    period = period_map.get(timeframe, "60d")
    yf_sym = symbol.replace(".IS", ".IS")
    df = yf.download(yf_sym, period=period, interval=timeframe.replace("m", "m").replace("h", "h").replace("d", "1d"))

    if df is None or df.empty:
        print(f"❌ Veri alınamadı: {symbol} {timeframe}")
        sys.exit(1)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ Eksik sütunlar: {missing}")
        sys.exit(1)

    print(f"📊 {symbol} {timeframe} — {len(df)} bar")

    result = build_research_setup(df, symbol=symbol, timeframe=timeframe)
    model = result["model"]
    quality = model.quality

    print(f"\n{'='*60}")
    print(f"  SETUP: {model.bias.direction} | Entry: {model.entry_zone.center:.4f}")
    print(f"  Type: {model.setup_type} | Regime: {model.regime.regime}")
    print(f"  Quality: {quality.overall:.0%} — {_verdict(quality.overall)}")
    print(f"  Breakdown:")
    for dim, score in quality.breakdown.items():
        print(f"    {dim}: {score:.0%}")
    print(f"  R:R: {model.risk_reward.reward_risk_ratio}:1")
    print(f"{'='*60}")

    print(f"\n{format_why_panel(result)}")

    if not EXECUTION_ENABLED:
        print("\n🛡️  RESEARCH ONLY — canlı emir gönderilmedi")

    # Save evidence
    evidence_dir = Path(__file__).resolve().parent / "agentspace" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = evidence_dir / f"research_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    evidence_file.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n📋 Evidence: {evidence_file}")


if __name__ == "__main__":
    main()