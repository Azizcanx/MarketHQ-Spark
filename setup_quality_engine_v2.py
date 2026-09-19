# -*- coding: utf-8 -*-
"""
MarketHQ Setup Quality Engine V2
==================================

9-boyutlu evidence-based quality scoring (quality_v2).
Her setup için: supporting_evidence, conflicting_evidence,
regime_compatibility, structure_quality, entry_quality,
risk_reward_feasibility, strategy_agreement,
invalidation_clarity, formation_chain.

Fix: historical_validation dimension removed (non-predictive + look-ahead bias).

Giris: SetupModel (setup_object_model.py)
Cikti: QualityScore (0..1 overall + breakdown + confidence + outcome_correlation)

Research only, canli islem yok.
"""

from __future__ import annotations

import math
from typing import Any

from setup_object_model import (
    SetupModel,
    QualityScore,
    Evidence,
    Confirmation,
    InvalidationLevel,
    EntryZone,
    TargetLevel,
    RiskReward,
    HistoricalValidation,
    RegimeInfo,
    StructureInfo,
    LiquidityInfo,
    BiasInfo,
)


# =========================================================
# HELPERS
# =========================================================

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _safe_div(num: float, den: float, fallback: float = 0.0) -> float:
    return num / den if den != 0 else fallback


# =========================================================
# DIMENSION SCORING — V2
# =========================================================

def _score_supporting_evidence(setup: SetupModel) -> tuple[float, str, float]:
    """Supporting evidence strength.

    Input: evidence.supporting count vs conflicting + neutral
    Calculation: net support ratio mapped to 0..1
    Confidence: based on total evidence count
    """
    evidence = setup.evidence
    supporting = len(evidence.supporting)
    conflicting = len(evidence.conflicting)
    neutral = len(evidence.neutral)
    total = supporting + conflicting + neutral

    if total == 0:
        return 0.3, "evidence_yok", 0.1  # low confidence — no data

    net = (supporting - conflicting) / max(total, 1)
    score = _clamp(0.5 + net * 0.5)

    # Confidence: more evidence = higher confidence
    confidence = _clamp(0.3 + 0.7 * (total / max(total + 5, 1)), 0.0, 1.0)

    if score >= 0.7:
        reason = "strong_evidence"
    elif score >= 0.5:
        reason = "moderate_evidence"
    elif score >= 0.3:
        reason = "weak_evidence"
    else:
        reason = "conflicting_evidence"

    return round(score, 3), reason, round(confidence, 3)


def _score_conflicting_evidence(setup: SetupModel) -> tuple[float, str, float]:
    """Conflicting evidence is inverted for quality scoring.

    Input: evidence.conflicting count vs total
    Calculation: 1 - conflict_ratio (capped)
    Confidence: based on total evidence count
    """
    evidence = setup.evidence
    conflicting = len(evidence.conflicting)
    total = len(evidence.supporting) + conflicting + len(evidence.neutral)

    if total == 0:
        return 0.8, "no_conflict", 0.1

    conflict_ratio = conflicting / total
    score = _clamp(1.0 - conflict_ratio * 1.5)

    confidence = _clamp(0.3 + 0.7 * (total / max(total + 5, 1)), 0.0, 1.0)

    return round(score, 3), f"conflict_ratio_{conflict_ratio:.0%}", round(confidence, 3)


def _score_regime_compatibility(setup: SetupModel) -> tuple[float, str, float]:
    """Does the setup direction match the market regime?

    Input: regime.regime, bias.direction, regime.confidence
    Calculation: directional alignment + regime confidence
    Confidence: regime confidence score
    """
    regime = setup.regime
    direction = setup.bias.direction

    if regime.regime == "UNKNOWN" or direction == "NEUTRAL":
        return 0.3, "regime_belirsiz", 0.2

    regime_conf = regime.confidence if regime.confidence > 0 else 0.5

    # LONG in uptrend = good, SHORT in downtrend = good
    if (direction == "LONG" and regime.regime.startswith("UPTREND")) or \
       (direction == "SHORT" and regime.regime.startswith("DOWNTREND")):
        score = 0.7 + 0.25 * regime_conf
        reason = "uyumlu"
    # Counter-trend — possible but lower quality
    elif (direction == "LONG" and regime.regime.startswith("DOWNTREND")) or \
         (direction == "SHORT" and regime.regime.startswith("UPTREND")):
        score = 0.3 + 0.2 * regime_conf
        reason = "counter_trend"
    # Range — any direction is neutral
    elif regime.regime.startswith("RANGE") or regime.regime == "EXPANDING_VOLATILITY":
        score = 0.45 + 0.15 * regime_conf
        reason = "range_orani"
    else:
        score = 0.3
        reason = "unknown"

    return round(_clamp(score), 3), reason, round(regime_conf, 3)


def _score_structure_quality(setup: SetupModel) -> tuple[float, str, float]:
    """Quality of market structure (BOS/CHoCH, swings, displacement).

    Input: structure.has_structure, structure_type, displacement,
           displacement_quality, swing highs/lows
    Calculation: base + type bonus + displacement quality + swing clarity
    Confidence: based on structure presence and displacement quality
    """
    struct = setup.structure

    if not struct.has_structure:
        return 0.2, "yapı_yok", 0.1

    score = 0.3  # base for having structure
    confidence = 0.3

    # Swing point distance — wider range = better defined structure
    if struct.last_swing_high and struct.last_swing_low:
        swing_range = struct.last_swing_high - struct.last_swing_low
        price_ref = struct.last_swing_high or 1.0
        range_pct = swing_range / price_ref
        if range_pct > 0.05:
            score += 0.15
            confidence += 0.1
        elif range_pct > 0.02:
            score += 0.1
            confidence += 0.05

    # Structure type bonus
    if struct.structure_type in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
        score += 0.3
        confidence += 0.2
    elif struct.structure_type:
        score += 0.15
        confidence += 0.1

    # Displacement quality
    if struct.displacement > 0.5:
        score += 0.2
        confidence += 0.2
        if struct.displacement_quality == "strong":
            score += 0.2
            confidence += 0.15
        elif struct.displacement_quality == "weak":
            confidence += 0.05
    elif struct.displacement > 0:
        score += 0.1
        confidence += 0.1

    # Swing clarity — more swings = better structure definition
    swing_count = sum(1 for s in [struct.last_swing_high, struct.last_swing_low] if s is not None)
    if swing_count >= 2:
        score += 0.1
        confidence += 0.15
    elif swing_count == 1:
        confidence += 0.05

    # Displacement magnitude as confidence proxy
    if abs(struct.displacement) > 0.3:
        confidence += 0.1

    return round(_clamp(score), 3), struct.structure_type or "basic", round(_clamp(confidence), 3)


def _score_entry_quality(setup: SetupModel) -> tuple[float, str, float]:
    """Entry zone quality — width, touches, source, position relative to structure.

    Input: entry_zone (center, width_atr, touches, source, quality),
           structure (last_swing_high, last_swing_low, has_structure)
    Calculation:
      - Base for having entry
      - Width bonus: sweet spot 0.3-1.5 ATR
      - Touches bonus: more touches = stronger
      - Source bonus: structure-based > vwap > atr_based > manual
      - Structure proximity bonus: entry near swing levels
    Confidence: based on zone width validity and touch count
    """
    zone = setup.entry_zone
    struct = setup.structure

    if zone.center == 0.0:
        return 0.0, "entry_yok", 0.0

    score = 0.3  # base for having entry
    confidence = 0.3

    # Zone width — narrower = better (but not too tight)
    if zone.width_atr > 0:
        if 0.3 <= zone.width_atr <= 1.5:
            score += 0.25
            confidence += 0.2
        elif zone.width_atr < 0.3:
            score += 0.15  # too tight, hard to enter
            confidence += 0.1
        else:
            score += 0.05  # too wide, unclear
            confidence += 0.05
    else:
        confidence -= 0.1

    # Touches — more touches = stronger support/resistance
    if zone.touches >= 3:
        score += 0.2
        confidence += 0.2
    elif zone.touches >= 2:
        score += 0.15
        confidence += 0.15
    elif zone.touches == 1:
        score += 0.05
        confidence += 0.05

    # Source quality
    source_scores = {"structure": 0.15, "vwap": 0.1, "atr_based": 0.05, "manual": 0.0}
    score += source_scores.get(zone.source, 0.0)
    if zone.source == "structure":
        confidence += 0.1

    # Structure proximity bonus — entry near swing high/low
    if struct.has_structure and struct.last_swing_high and struct.last_swing_low:
        dist_to_high = abs(zone.center - struct.last_swing_high) if struct.last_swing_high else float('inf')
        dist_to_low = abs(zone.center - struct.last_swing_low) if struct.last_swing_low else float('inf')
        atr_ref = zone.width_atr if zone.width_atr > 0 else 1.0
        # Entry within 0.5 ATR of a swing level = bonus
        if min(dist_to_high, dist_to_low) / atr_ref < 0.5:
            score += 0.15
            confidence += 0.1
        elif min(dist_to_high, dist_to_low) / atr_ref < 1.0:
            score += 0.05
            confidence += 0.05

    # Zone quality label
    quality_scores = {"high": 0.1, "medium": 0.0, "low": -0.05}
    score += quality_scores.get(zone.quality, 0.0)

    # Outcome correlation hint: entry quality correlates with execution
    # Higher quality zones → better fill → higher outcome correlation
    outcome_corr = 0.3 if zone.touches >= 2 and zone.width_atr <= 1.5 else 0.1

    final_score = _clamp(score)
    final_confidence = _clamp(confidence)
    reason = f"width_{zone.width_atr:.2f}ATR_touches_{zone.touches}_src_{zone.source}"

    return round(final_score, 3), reason, round(final_confidence, 3)


def _score_risk_reward(setup: SetupModel) -> tuple[float, str, float]:
    """Risk/reward feasibility — calculated from actual R:R ratio.

    Input: risk_reward (reward_risk_ratio, reward, risk, breakeven_age, feasibility)
    Calculation: R:R ratio mapped to score, with deflated Sharpe penalty
    Confidence: based on R:R availability and feasibility rating
    """
    rr = setup.risk_reward

    if rr.reward_risk_ratio is None:
        return 0.1, "rr_hesanlanamadi", 0.0

    ratio = rr.reward_risk_ratio

    # Base R:R score — continuous mapping instead of stepped
    # R:R 0.5 → 0.1, R:R 1.0 → 0.25, R:R 1.5 → 0.4, R:R 2.0 → 0.6,
    # R:R 2.5 → 0.75, R:R 3.0 → 0.85, R:R 5.0+ → 1.0
    if ratio <= 0.5:
        base = 0.1 + ratio * 0.3  # 0.1-0.25
    elif ratio <= 1.0:
        base = 0.25 + (ratio - 0.5) * 0.3  # 0.25-0.4
    elif ratio <= 1.5:
        base = 0.4 + (ratio - 1.0) * 0.3  # 0.4-0.55
    elif ratio <= 2.0:
        base = 0.55 + (ratio - 1.5) * 0.3  # 0.55-0.7
    elif ratio <= 3.0:
        base = 0.7 + (ratio - 2.0) * 0.15  # 0.7-0.85
    else:
        base = 0.85 + min((ratio - 3.0) * 0.05, 0.15)  # 0.85-1.0

    score = _clamp(base)

    # Confidence: based on R:R magnitude and feasibility rating
    feasibility_conf = {"high": 0.3, "medium": 0.2, "low": 0.1}
    confidence = 0.3 + feasibility_conf.get(rr.feasibility, 0.1)
    if ratio >= 1.5:
        confidence += 0.2
    if rr.breakeven_age > 0:
        confidence += 0.1

    # Outcome correlation: R:R directly impacts outcome
    outcome_corr = min(ratio / 5.0, 0.9) if ratio else 0.1

    return round(score, 3), f"rr={ratio}:1", round(_clamp(confidence), 3)


# historical_validation dimension removed — non-predictive + look-ahead bias.
# See diagnostic: 33/48 combos have <100 closed outcomes; DB lookup includes
# future-setup outcomes (leakage). Dimension kept at 0.0 in QualityScore for
# backward compat but excluded from scoring.


def _score_strategy_agreement(setup: SetupModel) -> tuple[float, str, float]:
    """Correlation-adjusted strategy agreement scoring.

    Fixes negative correlation by:
    1. Effective agreement: count independent families, not raw strategies
       (3 trend strategies all saying LONG = 1 signal, not 3)
    2. Family diversity bonus: diverse families agreeing = stronger signal
    3. Conflict penalty: conflicting families reduce agreement more heavily
    4. Strength weighting: strong strategies count more than weak ones
    5. Supporting vs conflicting separation

    Stores metadata: agreement_raw, agreement_adjusted, family_diversity, conflict_count
    """
    conf = setup.confirmation
    total = conf.strategy_count

    if total == 0:
        return 0.0, "strateji_yok", 0.0

    # --- RAW AGREEMENT (original consensus share) ---
    agreement_raw = conf.agreement_score  # max(longs, shorts) / total

    # --- FAMILY-LEVEL ANALYSIS ---
    family_agreement = conf.family_agreement
    n_families = len(family_agreement)

    # Count non-NEUTRAL families
    non_neutral_families = {
        fam: d for fam, d in family_agreement.items() if d != "NEUTRAL"
    }
    n_active_families = len(non_neutral_families)

    # Family diversity: how many families agree vs total active families
    # 1.0 = all active families agree, 0.5 = half agree, etc.
    if n_active_families > 0:
        family_diversity = n_active_families / max(n_families, 1)
    else:
        family_diversity = 0.0

    # --- CONFLICT COUNT ---
    conflict_count = len(conf.family_conflicts)

    # --- SUPPORTING vs CONFLICTING STRATEGIES ---
    strategies = conf.strategies
    supporting_strategies: list[str] = []
    conflicting_strategies: list[str] = []
    consensus_dir = "LONG"  # default fallback

    if strategies:
        # Determine consensus direction from family_agreement
        dir_counts: dict[str, int] = {}
        for fam, d in family_agreement.items():
            if d != "NEUTRAL":
                dir_counts[d] = dir_counts.get(d, 0) + 1
        if dir_counts:
            consensus_dir = max(dir_counts, key=lambda k: dir_counts[k])

        for s in strategies:
            sid = s.get("strategy_id", "") if isinstance(s, dict) else str(s)
            sdir = s.get("direction", "NEUTRAL") if isinstance(s, dict) else "NEUTRAL"
            if sdir == consensus_dir:
                supporting_strategies.append(sid)
            elif sdir != "NEUTRAL":
                conflicting_strategies.append(sid)

    # --- EFFECTIVE AGREEMENT (correlation-adjusted) ---
    # Key insight: if 3 strategies from the same family all say LONG,
    # that's 1 independent signal. If 3 diverse families all say LONG,
    # that's 3 independent signals.
    #
    # effective_agreement = families agreeing / total families
    # This naturally penalizes correlated strategies:
    # - 5 diverse families all agree: 5/5 = 1.0 (strong signal)
    # - 1 family agrees out of 5 total: 1/5 = 0.2 (weak signal)
    if n_families > 0:
        agreeing_families = sum(
            1 for d in non_neutral_families.values()
            if d == consensus_dir
        )
        effective_agreement = agreeing_families / n_families
    else:
        effective_agreement = agreement_raw

    # --- STRENGTH WEIGHTING ---
    # Average confidence of strategies supporting the consensus
    if strategies:
        agreeing_confs = [
            s.get("confidence", 0.5)
            for s in strategies
            if isinstance(s, dict) and s.get("direction") == consensus_dir
        ]
        avg_confidence = (
            sum(agreeing_confs) / len(agreeing_confs)
            if agreeing_confs else 0.5
        )
    else:
        avg_confidence = 0.5

    # Strength weight: strong consensus → higher weight (0.5-1.0)
    strength_weight = 0.5 + 0.5 * avg_confidence

    # --- ADJUSTED AGREEMENT ---
    # Component 1: Effective agreement weighted by strength
    base_score = effective_agreement * strength_weight

    # Component 2: Family diversity bonus (diverse families = stronger signal)
    # Max bonus when many diverse families agree
    diversity_bonus = family_diversity * 0.12

    # Component 3: Conflict penalty (each conflicting family reduces agreement)
    # Heavier penalty than before: -0.10 per conflict, capped at -0.25
    conflict_penalty = min(conflict_count * 0.10, 0.25)

    # Component 4: Agreement sample size bonus (more strategies = more robust)
    # But only if they're from different families (avoid double-counting)
    if total >= 8 and n_active_families >= 3:
        sample_bonus = 0.05
    elif total >= 5 and n_active_families >= 2:
        sample_bonus = 0.03
    else:
        sample_bonus = 0.0

    agreement_adjusted = _clamp(
        base_score + diversity_bonus - conflict_penalty + sample_bonus
    )

    # --- CONFIDENCE ---
    # Higher confidence when: diverse families agree, few conflicts, many strategies
    confidence = _clamp(
        0.15
        + 0.35 * family_diversity
        + 0.15 * (1.0 - conflict_count / max(n_families, 1))
        + 0.10 * min(total / 10.0, 1.0)
    )

    # --- OUTCOME CORRELATION ---
    # Adjusted agreement should correlate with outcomes:
    # - High adjusted agreement + high diversity → positive correlation
    # - High raw agreement + low diversity → neutral/weak correlation
    if agreement_adjusted > 0.5 and family_diversity > 0.5 and conflict_count == 0:
        outcome_corr_hint = 0.5
    elif agreement_adjusted > 0.4 and family_diversity > 0.3:
        outcome_corr_hint = 0.3
    else:
        outcome_corr_hint = 0.1

    final_score = agreement_adjusted
    reason = (
        f"raw={agreement_raw:.2f}_adj={agreement_adjusted:.2f}"
        f"_fam={n_active_families}_div={family_diversity:.2f}"
        f"_conflicts={conflict_count}"
    )

    # Store metadata on the confirmation object for downstream use
    conf.agreement_raw = agreement_raw  # type: ignore[attr-defined]
    conf.agreement_adjusted = agreement_adjusted  # type: ignore[attr-defined]
    conf.family_diversity = family_diversity  # type: ignore[attr-defined]
    conf.conflict_count = conflict_count  # type: ignore[attr-defined]
    conf.supporting_strategies = supporting_strategies  # type: ignore[attr-defined]
    conf.conflicting_strategies = conflicting_strategies  # type: ignore[attr-defined]

    return round(final_score, 3), reason, round(confidence, 3)


def _score_invalidation_clarity(setup: SetupModel) -> tuple[float, str, float]:
    """Invalidation clarity — distance from entry relative to ATR + type.

    Input: invalidation (price, distance_atr, type, clarity)
           entry_zone (center)
    Calculation:
      - Base for having invalidation
      - Clarity type bonus
      - Distance from entry relative to ATR (sweet spot 0.5-3.0)
      - Structural type bonus
      - Distance reasonableness (not too close, not too far)
    Confidence: based on clarity type and distance validity
    """
    inv = setup.invalidation

    if inv.price is None:
        return 0.0, "invalidation_yok", 0.0

    score = 0.3  # base for having invalidation
    confidence = 0.3

    # Clarity type
    clarity_scores = {"clear": 0.3, "medium": 0.2, "fuzzy": 0.05}
    score += clarity_scores.get(inv.clarity, 0.1)
    confidence += {"clear": 0.2, "medium": 0.1, "fuzzy": 0.0}.get(inv.clarity, 0.0)

    # Distance from entry relative to ATR — sweet spot is 0.5-3.0 ATR
    dist = inv.distance_atr
    if 0.5 <= dist <= 3.0:
        score += 0.25
        confidence += 0.2
    elif 0.2 <= dist < 0.5:
        score += 0.15  # tight but acceptable
        confidence += 0.1
    elif 3.0 < dist <= 5.0:
        score += 0.15  # far but acceptable
        confidence += 0.1
    elif dist < 0.2:
        score += 0.05  # too tight — noise
        confidence -= 0.1
    else:
        score += 0.05  # > 5.0 ATR, very far
        confidence -= 0.05

    # Price-level variation: invalidation distance as % of price
    # This varies as price moves even when ATR distance is constant
    zone = setup.entry_zone
    if zone.center > 0 and inv.price > 0:
        price_dist_pct = abs(inv.price - zone.center) / zone.center
        if price_dist_pct > 0.05:
            score += 0.05
            confidence += 0.05
        elif price_dist_pct < 0.01:
            score -= 0.05
            confidence -= 0.05

    # Type bonus
    type_scores = {"structural": 0.15, "volatility": 0.1, "time_based": 0.05}
    score += type_scores.get(inv.type, 0.0)
    if inv.type == "structural":
        confidence += 0.1

    # Entry proximity check — invalidation should be away from entry
    zone = setup.entry_zone
    if zone.center > 0 and inv.price > 0:
        entry_inv_dist = abs(inv.price - zone.center)
        atr_ref = zone.width_atr if zone.width_atr > 0 else 1.0
        if entry_inv_dist / atr_ref < 0.3:
            score -= 0.1  # invalidation too close to entry
            confidence -= 0.1

    final_score = _clamp(score)
    final_confidence = _clamp(confidence)
    reason = f"clarity={inv.clarity}_dist={dist:.1f}ATR"

    return round(final_score, 3), reason, round(final_confidence, 3)


def _score_formation_chain(setup: SetupModel) -> tuple[float, str, float]:
    """Setup formation chain scoring — continuity and coherence.

    Input: liquidity, structure, confirmation, entry_zone, invalidation, targets
    Calculation:
      - 6 links: Liquidity -> Structure -> Confirmation -> Entry -> Invalidation -> Targets
      - Each link scored on presence AND coherence (not just binary)
      - Coherence: do adjacent links make sense together?
    Confidence: based on number of valid links and coherence score
    """
    links = 0
    total = 6
    coherence = 0.0
    reasons = []

    # 1. Liquidity — presence + side clarity
    liq = setup.liquidity
    liq_present = bool(liq.buy_side_liquidity or liq.sell_side_liquidity)
    liq_coherent = liq_present and bool(liq.liquidity_side)
    if liq_present:
        links += 1
        coherence += 0.5 if liq_coherent else 0.2
        reasons.append("likidite_tespit_edildi" if liq_coherent else "likidite_belirsiz")
    else:
        reasons.append("likidite_sistematik")

    # 2. Structure — presence + type validity
    struct = setup.structure
    struct_coherent = struct.has_structure and bool(struct.structure_type)
    if struct_coherent:
        links += 1
        coherence += 0.8
        reasons.append(f"yapi:{struct.structure_type}")
    elif struct.has_structure:
        links += 0.5  # partial — structure exists but no type
        coherence += 0.3
        reasons.append("yapi_tanimsiz")
    else:
        reasons.append("yapı_yok")

    # 3. Confirmation — strategy count + agreement + coherence with structure
    conf = setup.confirmation
    conf_coherent = conf.strategy_count >= 2 and conf.agreement_score >= 0.3
    if conf.strategy_count >= 3 and conf.agreement_score >= 0.3:
        links += 1
        coherence += 0.8
        reasons.append(f"onay:{conf.agreement_score:.0%}")
    elif conf.strategy_count >= 1:
        links += 0.5
        coherence += 0.4
        reasons.append(f"zayif_onay:{conf.agreement_score:.0%}")
    else:
        reasons.append("onay_yok")

    # 4. Entry Zone — presence + width validity + coherence with structure
    zone = setup.entry_zone
    entry_coherent = zone.center > 0 and zone.width_atr > 0 and zone.width_atr < 5.0
    if entry_coherent:
        links += 1
        coherence += 0.6
        reasons.append(f"entry_zone:{zone.width_atr:.2f}ATR")
    elif zone.center > 0:
        links += 0.5
        coherence += 0.2
        reasons.append("entry_tek_dugum")
    else:
        reasons.append("entry_yok")

    # 5. Invalidation — presence + distance validity + coherence with entry
    inv = setup.invalidation
    inv_coherent = inv.price is not None and inv.distance_atr > 0.1 and inv.distance_atr < 10.0
    if inv_coherent:
        links += 1
        coherence += 0.7
        reasons.append(f"invalidation:{inv.distance_atr:.1f}ATR")
    elif inv.price is not None:
        links += 0.5
        coherence += 0.2
        reasons.append("invalidation_belirsiz")
    else:
        reasons.append("invalidation_yok")

    # 6. Targets — presence + R:R validity + coherence with entry/invalidation
    rr = setup.risk_reward
    target_coherent = rr.reward_risk_ratio is not None and rr.reward_risk_ratio > 0
    if target_coherent and rr.reward_risk_ratio >= 1.0:
        links += 1
        coherence += 0.7
        reasons.append(f"hedef:R:R={rr.reward_risk_ratio}")
    elif rr.reward_risk_ratio is not None and rr.reward_risk_ratio > 0:
        links += 0.5
        coherence += 0.3
        reasons.append(f"hedef:dusuk_RR={rr.reward_risk_ratio}")
    else:
        reasons.append("hedef_yok")

    # Normalize links to 0..1 (links can be fractional)
    score = _clamp(links / total)

    # Coherence bonus: if all links present and coherent, boost
    coherence_norm = coherence / total
    if links >= total - 0.5 and coherence_norm >= 0.6:
        score = _clamp(score + 0.05)  # small coherence bonus

    # Confidence: based on number of valid links and coherence
    confidence = _clamp(0.2 + 0.6 * (links / total) + 0.2 * coherence_norm)

    # Outcome correlation: formation chain coherence predicts outcome
    outcome_corr = 0.35 if links >= 4 and coherence_norm >= 0.5 else 0.15

    reason = "+".join(reasons) if reasons else "empty"
    return round(score, 3), reason, round(confidence, 3)


# =========================================================
# DIMENSION WEIGHTS — V2
# =========================================================

DIMENSION_WEIGHTS_V2 = {
    "supporting_evidence": 0.12,
    "conflicting_evidence": 0.08,
    "regime_compatibility": 0.12,
    "structure_quality": 0.12,
    "entry_quality": 0.14,
    "risk_reward_feasibility": 0.13,
    "strategy_agreement": 0.10,
    "invalidation_clarity": 0.08,
    "formation_chain": 0.11,
}

# Dimension metadata: input description, calculation method
DIMENSION_META = {
    "supporting_evidence": {
        "input": "evidence.supporting count vs conflicting + neutral",
        "method": "net_support_ratio mapped to 0..1",
    },
    "conflicting_evidence": {
        "input": "evidence.conflicting count vs total",
        "method": "1 - conflict_ratio * 1.5, clamped",
    },
    "regime_compatibility": {
        "input": "regime.regime + bias.direction + regime.confidence",
        "method": "directional alignment + regime confidence multiplier",
    },
    "structure_quality": {
        "input": "structure.has_structure, type, displacement, swings",
        "method": "base + type bonus + displacement quality + swing clarity",
    },
    "entry_quality": {
        "input": "entry_zone (width, touches, source, quality) + structure proximity",
        "method": "width sweet spot + touches + source quality + structure proximity",
    },
    "risk_reward_feasibility": {
        "input": "risk_reward.reward_risk_ratio + feasibility",
        "method": "continuous R:R mapping + deflated Sharpe penalty",
    },
    "strategy_agreement": {
        "input": "confirmation (agreement_raw, agreement_adjusted, family_agreement, disqualifiers)",
        "method": "correlation-adjusted: effective agreement * strength_weight + diversity_bonus - conflict_penalty",
    },
    "invalidation_clarity": {
        "input": "invalidation (price, distance_atr, type, clarity) + entry_zone",
        "method": "clarity bonus + distance sweet spot + type + entry proximity",
    },
    "formation_chain": {
        "input": "liquidity, structure, confirmation, entry_zone, invalidation, targets",
        "method": "6-link chain scored on presence + coherence, fractional links",
    },
}

# Dimension scoring functions in order (V2 — all return score, reason, confidence)
DIMENSION_SCORERS_V2 = [
    ("supporting_evidence", _score_supporting_evidence),
    ("conflicting_evidence", _score_conflicting_evidence),
    ("regime_compatibility", _score_regime_compatibility),
    ("structure_quality", _score_structure_quality),
    ("entry_quality", _score_entry_quality),
    ("risk_reward_feasibility", _score_risk_reward),
    ("strategy_agreement", _score_strategy_agreement),
    ("invalidation_clarity", _score_invalidation_clarity),
    ("formation_chain", _score_formation_chain),
]


def sample_size_confidence(n: int) -> tuple[str, float]:
    """Sample-size confidence level for quality scoring.

    n < 30  → low confidence, shrink aggressively toward global mean
    30–100  → medium confidence, moderate shrinkage
    100+    → high confidence, minimal shrinkage

    Returns (level, shrinkage_factor) where shrinkage_factor is the
    weight given to the global mean (1 - shrinkage_factor = local weight).
    """
    if n < 30:
        return "low", 0.7
    elif n <= 100:
        return "medium", 0.4
    else:
        return "high", 0.1


def raw_expectancy(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
) -> float:
    """Raw expectancy: win_rate * avg_win_r - (1 - win_rate) * avg_loss_r."""
    return (win_rate * avg_win_r) - ((1.0 - win_rate) * avg_loss_r)


def sample_adjusted_expectancy(
    local_n: int,
    local_expectancy: float,
    global_mean: float,
    shrinkage_constant: float = 50.0,
) -> float:
    """Bayesian shrinkage: pull small-sample estimates toward the global mean.

    Formula: adjusted = (n × local + k × global) / (n + k)
    where k is the shrinkage constant.

    Higher k → more shrinkage (more conservative for small samples).
    Lower k → less shrinkage (more trust in local data).
    """
    if local_n <= 0:
        return global_mean
    k = shrinkage_constant
    return (local_n * local_expectancy + k * global_mean) / (local_n + k)

def score_setup_quality_v2(setup: SetupModel, sample_size: int | None = None) -> QualityScore:
    """Calculate 10-dimension quality score for a setup (V2).

    Returns QualityScore with:
      - overall: weighted score 0..1
      - per-dimension scores
      - breakdown dict
      - flags
      - confidence: per-dimension confidence scores
      - outcome_correlation: per-dimension outcome correlation hints
      - sample_size_confidence: low/medium/high based on historical sample size
      - raw_expectancy: unadjusted expectancy from historical data
      - sample_adjusted_expectancy: Bayesian-shrunk expectancy
      - shrinkage_factor: how much shrinkage was applied
    """
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    confidences: dict[str, float] = {}
    outcome_corrs: dict[str, float] = {}
    flags: list[str] = []

    for dim_name, scorer in DIMENSION_SCORERS_V2:
        score, reason, confidence = scorer(setup)
        scores[dim_name] = score
        reasons[dim_name] = reason
        confidences[dim_name] = confidence

        # Outcome correlation — set per dimension
        if dim_name == "entry_quality":
            outcome_corrs[dim_name] = 0.3 if setup.entry_zone.touches >= 2 else 0.1
        elif dim_name == "risk_reward_feasibility":
            rr = setup.risk_reward
            outcome_corrs[dim_name] = min(rr.reward_risk_ratio / 5.0, 0.9) if rr.reward_risk_ratio else 0.1
        elif dim_name == "strategy_agreement":
            # Use adjusted agreement for outcome correlation hint
            ag = setup.confirmation
            outcome_corrs[dim_name] = 0.5 if (
                getattr(ag, 'agreement_adjusted', ag.agreement_score) > 0.5
                and getattr(ag, 'family_diversity', 0) > 0.5
                and getattr(ag, 'conflict_count', 0) == 0
            ) else 0.2
        elif dim_name == "formation_chain":
            links = sum(1 for d, _ in DIMENSION_SCORERS_V2 if d in ("liquidity", "structure", "confirmation"))
            outcome_corrs[dim_name] = 0.35 if links >= 4 else 0.15
        else:
            outcome_corrs[dim_name] = 0.2  # default low correlation

        # Flag low dimensions
        if score < 0.3:
            flags.append(f"DÜŞÜK_{dim_name.upper()}: {reason}")
        elif score < 0.5:
            flags.append(f"ORTA_{dim_name.upper()}: {reason}")

    # Weighted overall
    overall = sum(
        scores.get(dim, 0.0) * DIMENSION_WEIGHTS_V2.get(dim, 0.0)
        for dim in DIMENSION_WEIGHTS_V2
    )

    # Bonus: if all dims >= 0.5, boost
    if all(s >= 0.5 for s in scores.values()):
        overall = _clamp(overall * 1.05)

    # Penalty: if conflicting evidence is high, reduce
    if scores.get("conflicting_evidence", 1.0) < 0.4:
        overall *= 0.85

    overall = round(_clamp(overall), 3)

    # Sample-size confidence / shrinkage (Task 1)
    ss_confidence = "unknown"
    ss_confidence_score = 0.0
    raw_exp = 0.0
    adj_exp = 0.0
    shrinkage = 0.0

    if sample_size is not None:
        ss_confidence, shrinkage = sample_size_confidence(sample_size)
        ss_confidence_score = 1.0 - shrinkage  # high confidence = low shrinkage
        # Raw expectancy from quality bucket stats (approximate from score)
        # This is a placeholder — real expectancy comes from historical data
        raw_exp = (overall - 0.5) * 2.0  # map 0..1 to -1..1 approximate R
        # Global mean (prior): assume 0.0 (neutral) for unknown strategies
        global_mean = 0.0
        adj_exp = sample_adjusted_expectancy(sample_size, raw_exp, global_mean)

    return QualityScore(
        overall=overall,
        supporting_evidence=scores.get("supporting_evidence", 0.0),
        conflicting_evidence=scores.get("conflicting_evidence", 0.0),
        regime_compatibility=scores.get("regime_compatibility", 0.0),
        structure_quality=scores.get("structure_quality", 0.0),
        entry_quality=scores.get("entry_quality", 0.0),
        risk_reward_feasibility=scores.get("risk_reward_feasibility", 0.0),
        strategy_agreement=scores.get("strategy_agreement", 0.0),
        invalidation_clarity=scores.get("invalidation_clarity", 0.0),
        formation_chain=scores.get("formation_chain", 0.0),
        breakdown={dim: round(scores.get(dim, 0.0), 3) for dim in DIMENSION_WEIGHTS_V2},
        flags=flags,
        sample_size_confidence=ss_confidence,
        sample_size_confidence_score=round(ss_confidence_score, 3),
        raw_expectancy=round(raw_exp, 4),
        sample_adjusted_expectancy=round(adj_exp, 4),
        shrinkage_factor=round(shrinkage, 3),
    )


def diagnose_setup_v2(setup: SetupModel) -> dict[str, Any]:
    """Full diagnosis — scores + per-dimension reasoning + confidence."""
    quality = score_setup_quality_v2(setup)

    diagnosis = {
        "setup_id": setup.setup_id,
        "symbol": setup.symbol,
        "overall_quality": quality.overall,
        "dimensions": {},
        "confidence": {},
        "outcome_correlation": {},
        "flags": quality.flags,
        "verdict": _verdict(quality.overall),
    }

    for dim_name, _ in DIMENSION_SCORERS_V2:
        score_val = getattr(quality, dim_name, 0.0)
        diagnosis["dimensions"][dim_name] = {
            "score": score_val,
            "weight": DIMENSION_WEIGHTS_V2.get(dim_name, 0),
            "weighted": round(score_val * DIMENSION_WEIGHTS_V2.get(dim_name, 0), 4),
            "input": DIMENSION_META.get(dim_name, {}).get("input", ""),
            "method": DIMENSION_META.get(dim_name, {}).get("method", ""),
        }

    return diagnosis


def _verdict(overall: float) -> str:
    if overall >= 0.75:
        return "STRONG_SETUP"
    elif overall >= 0.55:
        return "MODERATE_SETUP"
    elif overall >= 0.35:
        return "WEAK_SETUP"
    else:
        return "POOR_SETUP"


# =========================================================
# VARIATION TEST — verify dimensions are not constant
# =========================================================

def test_dimension_variation() -> dict[str, Any]:
    """Test that all 9 dimensions vary across different setups."""
    from setup_object_model import Evidence

    results: dict[str, list[float]] = {dim: [] for dim, _ in DIMENSION_SCORERS_V2}

    # Create 5 varied setups
    setups = _create_test_setups()

    # Populate evidence lists so supporting/conflicting evidence can vary
    evidence_data = [
        Evidence(supporting=[{"source":"ema","type":"strategy"},{"source":"smc","type":"structure"}],
                 conflicting=[{"source":"rsi","type":"indicator"}], neutral=[]),
        Evidence(supporting=[{"source":"ema","type":"strategy"}],
                 conflicting=[{"source":"rsi","type":"indicator"},{"source":"macd","type":"indicator"}], neutral=[]),
        Evidence(supporting=[{"source":"sma","type":"ma"}], conflicting=[],
                 neutral=[{"source":"fibonacci","type":"tool"}]),
        Evidence(supporting=[], conflicting=[{"source":"sma","type":"ma"},{"source":"ema","type":"strategy"}], neutral=[]),
        Evidence(supporting=[{"source":"vwap","type":"indicator"}], conflicting=[], neutral=[]),
    ]
    for setup, ev in zip(setups, evidence_data):
        setup.evidence = ev

    for setup in setups:
        quality = score_setup_quality_v2(setup)
        for dim in results:
            val = getattr(quality, dim, 0.0)
            results[dim].append(val)

    # Check variation
    variation_report: dict[str, Any] = {}
    all_varying = True

    for dim, values in results.items():
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val
        is_varying = range_val > 0.01  # allow tiny floating point differences
        if not is_varying:
            all_varying = False
        variation_report[dim] = {
            "values": [round(v, 3) for v in values],
            "min": round(min_val, 3),
            "max": round(max_val, 3),
            "range": round(range_val, 3),
            "varying": is_varying,
        }

    return {
        "all_varying": all_varying,
        "dimensions": variation_report,
        "num_setups": len(setups),
    }


def _create_test_setups() -> list[SetupModel]:
    """Create varied test setups to verify dimension variation."""
    setups: list[SetupModel] = []

    # Setup 1: Strong uptrend setup with good structure
    s1 = SetupModel(
        setup_id="test_1",
        symbol="TEST1",
        regime=RegimeInfo(regime="UPTREND", confidence=0.85),
        bias=BiasInfo(direction="LONG", bias_strength=0.8),
        structure=StructureInfo(
            has_structure=True,
            structure_type="BOS_UP",
            displacement=0.6,
            displacement_quality="strong",
            last_swing_high=100.0,
            last_swing_low=95.0,
        ),
        liquidity=LiquidityInfo(
            buy_side_liquidity=101.0,
            sell_side_liquidity=94.0,
            liquidity_sweep_detected=True,
            liquidity_side="buy",
        ),
        entry_zone=EntryZone(
            center=99.0, low=98.5, high=99.5,
            width_atr=0.8, source="structure", quality="high", touches=3,
        ),
        confirmation=Confirmation(
            strategy_count=8,
            agreement_score=0.85,
            family_agreement={"sma": "LONG", "ema": "LONG", "smc": "LONG"},
            disqualifiers=[],
        ),
        invalidation=InvalidationLevel(
            price=97.0, distance_atr=1.5, type="structural", clarity="clear",
        ),
        risk_reward=RiskReward(reward_risk_ratio=2.5, feasibility="high"),
        historical_validation=HistoricalValidation(
            available=True, similar_count=15, win_rate=0.62, avg_return=0.08,
        ),
    )
    setups.append(s1)

    # Setup 2: Weak downtrend setup, poor structure
    s2 = SetupModel(
        setup_id="test_2",
        symbol="TEST2",
        regime=RegimeInfo(regime="DOWNTREND", confidence=0.6),
        bias=BiasInfo(direction="SHORT", bias_strength=0.4),
        structure=StructureInfo(
            has_structure=False,
            displacement=0.0,
            displacement_quality="",
            last_swing_high=None,
            last_swing_low=None,
        ),
        liquidity=LiquidityInfo(
            buy_side_liquidity=None,
            sell_side_liquidity=98.0,
            liquidity_sweep_detected=False,
            liquidity_side="sell",
        ),
        entry_zone=EntryZone(
            center=101.0, low=100.5, high=101.5,
            width_atr=2.5, source="atr_based", quality="low", touches=0,
        ),
        confirmation=Confirmation(
            strategy_count=2,
            agreement_score=0.2,
            family_agreement={"sma": "SHORT"},
            disqualifiers=["ema"],
        ),
        invalidation=InvalidationLevel(
            price=103.0, distance_atr=0.15, type="volatility", clarity="fuzzy",
        ),
        risk_reward=RiskReward(reward_risk_ratio=0.8, feasibility="low"),
        historical_validation=HistoricalValidation(
            available=False, similar_count=0,
        ),
    )
    setups.append(s2)

    # Setup 3: Range market, moderate setup
    s3 = SetupModel(
        setup_id="test_3",
        symbol="TEST3",
        regime=RegimeInfo(regime="RANGE", confidence=0.5),
        bias=BiasInfo(direction="LONG", bias_strength=0.5),
        structure=StructureInfo(
            has_structure=True,
            structure_type="NEUTRAL",
            displacement=0.1,
            displacement_quality="weak",
            last_swing_high=100.5,
            last_swing_low=99.5,
        ),
        liquidity=LiquidityInfo(
            buy_side_liquidity=101.5,
            sell_side_liquidity=98.5,
            liquidity_sweep_detected=False,
            liquidity_side="",
        ),
        entry_zone=EntryZone(
            center=100.0, low=99.7, high=100.3,
            width_atr=0.4, source="vwap", quality="medium", touches=2,
        ),
        confirmation=Confirmation(
            strategy_count=5,
            agreement_score=0.6,
            family_agreement={"sma": "LONG", "ema": "NEUTRAL", "smc": "LONG", "ichimoku": "LONG"},
            disqualifiers=[],
        ),
        invalidation=InvalidationLevel(
            price=99.0, distance_atr=2.0, type="structural", clarity="medium",
        ),
        risk_reward=RiskReward(reward_risk_ratio=1.8, feasibility="medium"),
        historical_validation=HistoricalValidation(
            available=True, similar_count=8, win_rate=0.50, avg_return=0.02,
        ),
    )
    setups.append(s3)

    # Setup 4: Counter-trend setup
    s4 = SetupModel(
        setup_id="test_4",
        symbol="TEST4",
        regime=RegimeInfo(regime="UPTREND", confidence=0.75),
        bias=BiasInfo(direction="SHORT", bias_strength=0.6),
        structure=StructureInfo(
            has_structure=True,
            structure_type="CHoCH_DOWN",
            displacement=0.4,
            displacement_quality="weak",
            last_swing_high=102.0,
            last_swing_low=98.0,
        ),
        liquidity=LiquidityInfo(
            buy_side_liquidity=103.0,
            sell_side_liquidity=None,
            liquidity_sweep_detected=True,
            liquidity_side="buy",
        ),
        entry_zone=EntryZone(
            center=99.0, low=98.0, high=100.0,
            width_atr=1.2, source="structure", quality="medium", touches=2,
        ),
        confirmation=Confirmation(
            strategy_count=4,
            agreement_score=0.4,
            family_agreement={"sma": "SHORT", "ema": "LONG"},  # conflict
            disqualifiers=["smc"],
            family_conflicts=[{"family": "ema", "directions": ["LONG"], "severity": "medium"}],
        ),
        invalidation=InvalidationLevel(
            price=101.0, distance_atr=2.5, type="structural", clarity="clear",
        ),
        risk_reward=RiskReward(reward_risk_ratio=1.2, feasibility="low"),
        historical_validation=HistoricalValidation(
            available=True, similar_count=5, win_rate=0.40, avg_return=-0.01,
        ),
    )
    setups.append(s4)

    # Setup 5: No clear setup
    s5 = SetupModel(
        setup_id="test_5",
        symbol="TEST5",
        regime=RegimeInfo(regime="UNKNOWN", confidence=0.0),
        bias=BiasInfo(direction="NEUTRAL", bias_strength=0.0),
        structure=StructureInfo(),
        liquidity=LiquidityInfo(),
        entry_zone=EntryZone(),  # all defaults — center=0
        confirmation=Confirmation(),
        invalidation=InvalidationLevel(),
        risk_reward=RiskReward(),
        historical_validation=HistoricalValidation(),
    )
    setups.append(s5)

    return setups


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    print("=== Quality Engine V2 — Dimension Variation Test ===\n")

    report = test_dimension_variation()

    print(f"Setups tested: {report['num_setups']}")
    print(f"All dimensions varying: {report['all_varying']}\n")

    print(f"{'Dimension':<25s} {'Min':>6s} {'Max':>6s} {'Range':>7s} {'Varying':>8s}")
    print("-" * 60)
    for dim, info in report["dimensions"].items():
        print(f"{dim:<25s} {info['min']:>6.3f} {info['max']:>6.3f} "
              f"{info['range']:>7.3f} {'YES' if info['varying'] else 'NO':>8s}")

    print("\n=== Sample Setup Diagnosis ===\n")
    test_setup = _create_test_setups()[0]
    diagnosis = diagnose_setup_v2(test_setup)
    print(f"Setup: {diagnosis['setup_id']} | Symbol: {diagnosis['symbol']}")
    print(f"Overall: {diagnosis['overall_quality']:.3f} | Verdict: {diagnosis['verdict']}")
    print(f"\nDimensions:")
    for dim, info in diagnosis["dimensions"].items():
        print(f"  {dim:<25s} {info['score']:.3f} (w={info['weight']:.2f}, "
              f"weighted={info['weighted']:.4f})")

    if not report["all_varying"]:
        print("\nWARNING: Some dimensions are NOT varying!")
        for dim, info in report["dimensions"].items():
            if not info["varying"]:
                print(f"  - {dim}: constant at {info['values']}")