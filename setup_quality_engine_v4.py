# -*- coding: utf-8 -*-
"""
MarketHQ Setup Quality Engine V4 — Research/Experimental
=========================================================

CEILING EFFECT FIXES from ceiling_effect_analysis.md:
  1. zone_width_atr=0.5 constant → use atr_pct as continuous feature
  2. touches=1 constant → use actual touch count
  3. structure_type="" constant → use structure proximity as continuous
  4. Additive base+bonus → multiplicative scoring
  5. Invalidation clarity constant → ATR-normalized distance + entry/invalidation ratio
  6. Risk RR constant → actual RR + expected excursion ratio

NEW DIMENSIONS:
  - volatility_context: atr_percentile + volatility_state
  - structure_alignment: structure type vs direction alignment
  - liquidity_balance: buy/sell liquidity ratio
  - momentum_at_entry: price momentum near entry
  - volume_ratio: current vs average volume proxy

REGIME INTERACTION:
  - regime_weighted_quality = quality * regime_compatibility

Giris: SetupModel (setup_object_model.py)
Cikti: QualityScore (0..1 overall + breakdown + confidence + outcome_correlation)

Research only, canli islem yok.
Does NOT break quality_v3 or existing tests.
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
# ATR PERCENTILE REFERENCE (from market_hq.db distribution)
# =========================================================
# Computed from 4,028 records with atr_pct data:
#   P10=0.62  P25=0.73  P50=0.91  P75=1.29  P90=1.56
#   min=0.50  max=2.27  mean=1.02  median=0.91

_ATR_PCT_P10 = 0.62
_ATR_PCT_P25 = 0.73
_ATR_PCT_P50 = 0.91
_ATR_PCT_P75 = 1.29
_ATR_PCT_P90 = 1.56


def _atr_percentile(atr_pct: float) -> float:
    """Where atr_pct falls in the distribution (0..1).

    Uses empirical percentiles from the data.
    Below P10 → near 0.0, above P90 → near 1.0.
    """
    if atr_pct <= _ATR_PCT_P10:
        return 0.0
    elif atr_pct <= _ATR_PCT_P25:
        return 0.25
    elif atr_pct <= _ATR_PCT_P50:
        return 0.50
    elif atr_pct <= _ATR_PCT_P75:
        return 0.75
    elif atr_pct <= _ATR_PCT_P90:
        return 0.90
    else:
        return 1.0


def _volatility_state(atr_pct: float) -> str:
    """Volatility state based on atr_pct percentiles."""
    pct = _atr_percentile(atr_pct)
    if pct <= 0.25:
        return "low"
    elif pct <= 0.75:
        return "medium"
    else:
        return "high"


# =========================================================
# MULTIPLICATIVE SCORING HELPERS
# =========================================================

def _multiplicative_score(
    base: float,
    factors: list[float],
    min_factor: float = 0.3,
    max_factor: float = 1.7,
) -> float:
    """Multiplicative scoring: base * f1 * f2 * ...

    Each factor shifts the score multiplicatively instead of additively.
    This prevents ceiling effects — weak factors reduce the score,
    strong factors increase it, but the range is bounded.

    min_factor: lowest allowed factor (prevents zeroing out)
    max_factor: highest allowed factor (prevents explosion)
    """
    score = base
    for f in factors:
        score *= _clamp(f, min_factor, max_factor)
    return _clamp(score)


# =========================================================
# V4 DIMENSION SCORERS
# =========================================================

def _score_entry_quality_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Entry quality — multiplicative scoring with continuous features.

    FIXES from ceiling_effect_analysis.md:
      1. zone_width_atr=0.5 constant → use atr_pct as continuous feature
      2. touches=1 constant → use actual touch count from setup data
      3. structure_type="" constant → use structure proximity as continuous
      4. Additive → multiplicative scoring

    Feature availability (from setup_outcomes):
      - atr_pct: 39.7% non-NULL (4,251/10,707) — PRIMARY variable feature
      - zone_width_atr: 62.1% non-NULL but CONSTANT 0.5 — fallback only
      - touches: 62.1% non-NULL but CONSTANT 1 — fallback only
      - structure_type: 62.1% non-NULL but EMPTY "" — skip when empty

    Inputs:
      - atr_pct (continuous): volatility-normalized zone width (preferred)
      - zone_width_atr (continuous): fallback when atr_pct unavailable
      - touches (continuous): actual touch count
      - source quality: structure-based > vwap > atr_based > manual
      - structure proximity: distance to nearest swing level (ATR-normalized)
      - zone width vs atr_pct interaction: wider zones in high ATR are OK
      - structure_type: only used when non-empty

    Calculation:
      base=0.5
      factor_atr: atr_pct mapped to 0.5-1.5 (higher ATR → wider acceptable zone)
      factor_touches: touch count mapped to 0.5-1.5 (more touches → stronger)
      factor_source: source quality 0.5-1.5
      factor_proximity: structure proximity 0.5-1.5
      factor_width: zone width appropriateness 0.5-1.5

    Expected variance: 0.15-0.35 (vs 0.15 in v2 with ceiling)
    Expected correlation with outcome R: |r| > 0.15
    """
    zone = setup.entry_zone
    struct = setup.structure
    regime = setup.regime

    if zone.center == 0.0:
        return 0.0, "entry_yok", 0.0, {}

    # ── Feature availability tracking ──
    feat: dict[str, str] = {}

    # ── Factor 1: ATR-based zone width (continuous, preferred over zone_width_atr) ──
    atr_pct = regime.atr_pct if regime and regime.atr_pct > 0 else 0.0
    zone_width = zone.width_atr if zone.width_atr > 0 else 0.0

    if atr_pct > 0:
        # PRIMARY: use atr_pct (variable, 100 unique values when available)
        feat["atr_pct"] = "used"
        # Optimal atr_pct around 0.8-1.2; penalize extremes
        if 0.6 <= atr_pct <= 1.4:
            factor_atr = 1.0 + 0.1 * (1.0 - abs(atr_pct - 1.0))  # 1.0-1.1
        elif 0.4 <= atr_pct <= 1.6:
            factor_atr = 0.9  # acceptable range
        else:
            factor_atr = 0.7  # extreme ATR
    elif zone_width > 0:
        # FALLBACK: zone_width_atr is constant 0.5 — limited discrimination
        feat["zone_width_atr"] = "used_constant"
        # zone_width_atr=0.5 → width_atr=0.5, normalize: ratio = 0.5/0.5 = 1.0
        factor_atr = 1.0  # neutral, no discrimination from constant input
    else:
        feat["atr_pct"] = "null"
        feat["zone_width_atr"] = "null"
        factor_atr = 0.8  # neutral fallback

    # ── Factor 2: Touch count (continuous) ──
    touches = zone.touches
    if touches > 0:
        feat["touches"] = "used"
        if touches >= 4:
            factor_touches = 1.4
        elif touches >= 3:
            factor_touches = 1.25
        elif touches >= 2:
            factor_touches = 1.15
        elif touches == 1:
            factor_touches = 1.0
        else:
            factor_touches = 0.7
    else:
        feat["touches"] = "null"
        factor_touches = 0.8  # neutral fallback — no touch data

    # ── Factor 3: Source quality ──
    source_scores = {"structure": 1.25, "vwap": 1.15, "atr_based": 1.0, "manual": 0.8}
    factor_source = source_scores.get(zone.source, 0.9)
    feat["source"] = "used" if zone.source else "null"

    # ── Factor 4: Structure proximity (continuous, ATR-normalized) ──
    # Only use structure proximity when structure_type is available AND non-empty
    proximity_factor = 1.0
    struct_type = struct.structure_type or ""
    if struct.has_structure and struct_type and struct.last_swing_high and struct.last_swing_low:
        feat["structure_type"] = "used"
        atr_ref = zone.width_atr if zone.width_atr > 0 else (atr_pct if atr_pct > 0 else 1.0)
        dist_to_high = abs(zone.center - struct.last_swing_high) if struct.last_swing_high else float('inf')
        dist_to_low = abs(zone.center - struct.last_swing_low) if struct.last_swing_low else float('inf')
        min_dist_atr = min(dist_to_high, dist_to_low) / atr_ref if atr_ref > 0 else 1.0
        if min_dist_atr <= 0.3:
            proximity_factor = 1.2
        elif min_dist_atr <= 0.5:
            proximity_factor = 1.1
        elif min_dist_atr <= 1.0:
            proximity_factor = 1.0
        else:
            proximity_factor = 0.85
    elif struct.has_structure and not struct_type:
        feat["structure_type"] = "null"
        proximity_factor = 0.95  # slight penalty for missing structure_type
    else:
        feat["structure_type"] = "null"
        feat["has_structure"] = "null"
        proximity_factor = 0.9  # no structure data

    # ── Factor 5: Zone width appropriateness ──
    # When atr_pct available: width vs atr_pct ratio (adaptive sweet spot)
    # When only zone_width_atr: width is constant 0.5 → limited discrimination
    width_atr = zone.width_atr if zone.width_atr > 0 else 0.5
    width_ratio = 0.0
    if atr_pct > 0:
        expected_width = 0.5 * atr_pct
        width_ratio = width_atr / expected_width if expected_width > 0 else 1.0
        if 0.5 <= width_ratio <= 2.0:
            factor_width = 1.0 + 0.1 * (1.0 - abs(width_ratio - 1.0))
        else:
            factor_width = 0.7
    elif zone_width > 0:
        feat["zone_width_atr"] = "used_constant"
        factor_width = 1.0  # constant input → neutral factor
    else:
        feat["zone_width_atr"] = "null"
        factor_width = 0.8

    # Quality label bonus (small multiplicative factor)
    quality_factors = {"high": 1.1, "medium": 1.0, "low": 0.85}
    factor_quality = quality_factors.get(zone.quality, 1.0)
    feat["quality"] = "used" if zone.quality else "null"

    # Multiplicative scoring
    score = _multiplicative_score(0.5, [
        factor_atr, factor_touches, factor_source,
        proximity_factor, factor_width, factor_quality
    ])

    # Confidence: based on data richness
    confidence = 0.3
    if touches >= 2:
        confidence += 0.2
    if struct.has_structure and struct_type:
        confidence += 0.15
    if zone.source == "structure":
        confidence += 0.15
    if atr_pct > 0:
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = (f"atr_pct={atr_pct:.2f}_touches={touches}_src={zone.source}"
              f"_prox={proximity_factor:.2f}_wratio={width_ratio:.2f}")

    return round(score, 3), reason, round(confidence, 3), feat


def _score_invalidation_clarity_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Invalidation clarity — continuous distance + entry/invalidation ratio.

    FIXES from ceiling_effect_analysis.md:
      - Instead of constant clarity="clear", use invalidation distance as continuous
      - Use ATR-normalized invalidation distance
      - Add entry-to-invalidation ratio

    Feature availability (from setup_outcomes):
      - entry_price: 77.6% non-NULL (8,313/10,707) — compute distance from prices
      - invalidation_price: 77.6% non-NULL (8,313/10,707)
      - target_price: 77.6% non-NULL (8,313/10,707)
      - atr_pct: 39.7% non-NULL (4,251/10,707) — for ATR normalization
      - invalidation.distance_atr: computed field (always populated in SetupModel)

    Inputs:
      - entry_price/invalidation_price: actual price distance (primary)
      - invalidation.distance_atr (continuous): ATR-normalized distance (fallback)
      - invalidation.type: structural/volatility/time_based
      - invalidation.clarity: clear/medium/fuzzy
      - entry_zone.center vs invalidation.price: entry-to-invalidation ratio

    Calculation:
      base=0.4
      distance_factor: ATR-normalized distance (sweet spot 0.5-3.0)
      type_factor: type quality
      clarity_factor: clarity quality
      ratio_factor: entry-to-invalidation distance ratio

    Expected variance: 0.20-0.40 (vs 0.002 in v2 with 99.8% ceiling)
    Expected correlation with outcome R: |r| > 0.10
    """
    inv = setup.invalidation
    zone = setup.entry_zone
    regime = setup.regime

    if inv.price is None:
        return 0.0, "invalidation_yok", 0.0, {}

    base = 0.4
    feat: dict[str, str] = {}

    # ── Factor 1: Distance (ATR-normalized, continuous mapping) ──
    # Compute distance from entry/invalidation prices when available
    dist = inv.distance_atr  # fallback default
    if (zone.center > 0 and inv.price > 0):
        price_dist = abs(inv.price - zone.center)
        atr_ref = regime.atr_pct if regime and regime.atr_pct > 0 else 0.0
        if atr_ref > 0:
            dist = price_dist / atr_ref
            feat["entry_price"] = "used"
            feat["invalidation_price"] = "used"
            feat["atr_pct"] = "used"
        else:
            feat["entry_price"] = "used"
            feat["invalidation_price"] = "used"
            feat["atr_pct"] = "null"
    else:
        feat["entry_price"] = "null"
        feat["invalidation_price"] = "null"

    # Sweet spot: 0.5-3.0 ATR, with smooth falloff outside
    if 0.5 <= dist <= 3.0:
        distance_factor = 1.15
    elif 0.3 <= dist < 0.5:
        distance_factor = 1.0 + 0.15 * ((dist - 0.3) / 0.2)  # 1.0-1.15
    elif 3.0 < dist <= 5.0:
        distance_factor = 1.0 + 0.15 * ((5.0 - dist) / 2.0)  # 1.0-1.15
    elif dist < 0.3:
        distance_factor = 0.5 + 0.5 * (dist / 0.3)  # 0.5-1.0 (too close)
    else:
        distance_factor = 0.7  # > 5.0 ATR (too far)

    # Factor 2: Type quality
    type_factors = {"structural": 1.15, "volatility": 1.0, "time_based": 0.85}
    type_factor = type_factors.get(inv.type, 0.9)
    feat["invalidation.type"] = "used" if inv.type else "null"

    # Factor 3: Clarity
    clarity_factors = {"clear": 1.15, "medium": 1.0, "fuzzy": 0.8}
    clarity_factor = clarity_factors.get(inv.clarity, 0.9)
    feat["invalidation.clarity"] = "used" if inv.clarity else "null"

    # Factor 4: Entry-to-invalidation ratio
    ratio_factor = 1.0
    if zone.center > 0 and inv.price > 0:
        entry_inv_dist = abs(inv.price - zone.center)
        atr_ref = regime.atr_pct if regime and regime.atr_pct > 0 else (zone.width_atr if zone.width_atr > 0 else 1.0)
        if atr_ref > 0:
            ratio = entry_inv_dist / atr_ref
            # Ratio of 1-3 ATR = good invalidation separation
            if 1.0 <= ratio <= 3.0:
                ratio_factor = 1.1
            elif 0.5 <= ratio < 1.0:
                ratio_factor = 0.95
            elif 3.0 < ratio <= 5.0:
                ratio_factor = 1.05
            else:
                ratio_factor = 0.85
        feat["ratio"] = "used"
    else:
        feat["ratio"] = "null"

    score = _multiplicative_score(base, [
        distance_factor, type_factor, clarity_factor, ratio_factor
    ])

    confidence = 0.3
    if 0.5 <= dist <= 3.0:
        confidence += 0.2
    if inv.type:
        confidence += 0.1
    if inv.clarity == "clear":
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"dist={dist:.1f}ATR_type={inv.type}_clarity={inv.clarity}"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_risk_rr_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Risk/reward feasibility — continuous RR mapping + excursion ratio.

    FIXES from ceiling_effect_analysis.md:
      - Instead of constant RR=0.55, use actual RR from setup data
      - Add expected excursion ratio
      - Use continuous RR mapping

    Feature availability (from setup_outcomes):
      - entry_price: 77.6% non-NULL (8,313/10,707) — compute RR from prices
      - invalidation_price: 77.6% non-NULL (8,313/10,707)
      - target_price: 77.6% non-NULL (8,313/10,707)
      - max_favorable: 0% non-NULL (ALL NULL) — excursion ratio unavailable
      - max_adverse: 0% non-NULL (ALL NULL) — excursion ratio unavailable
      - pnl_pct: 99.97% non-NULL (10,704/10,707) — proxy for outcome
      - duration_bars: 100% non-NULL (10,707/10,707) — proxy for time

    Inputs:
      - risk_reward.reward_risk_ratio (continuous): actual R:R from setup
      - risk_reward.feasibility: high/medium/low
      - risk_reward.breakeven_age: ATR distance to breakeven
      - entry_price/invalidation_price/target_price: compute RR from prices

    Calculation:
      base=0.4
      rr_factor: continuous R:R mapping (non-linear, S-curve)
      excursion_factor: breakeven_age / R:R ratio (expected excursion)
      feasibility_factor: feasibility rating

    Expected variance: 0.15-0.30 (vs 0.002 in v2 with 83.4% at 0.55)
    Expected correlation with outcome R: |r| > 0.10
    """
    rr = setup.risk_reward

    if rr.reward_risk_ratio is None and not (setup.entry_zone.center > 0 and setup.invalidation.price and setup.targets.primary and setup.targets.primary.price):
        return 0.0, "rr_hesanlanamadi", 0.0, {}

    base = 0.4
    feat: dict[str, str] = {}

    # ── Compute RR from prices when available ──
    ratio = rr.reward_risk_ratio  # fallback
    price_based_rr = False
    entry = setup.entry_zone.center
    inv_price = setup.invalidation.price
    tgt = setup.targets.primary.price if setup.targets.primary else None

    if (entry > 0 and inv_price is not None and inv_price > 0 and tgt is not None and tgt > 0):
        risk = abs(entry - inv_price)
        reward = abs(tgt - entry)
        if risk > 0:
            ratio = reward / risk
            price_based_rr = True
            feat["entry_price"] = "used"
            feat["invalidation_price"] = "used"
            feat["target_price"] = "used"
        else:
            feat["entry_price"] = "used"
            feat["invalidation_price"] = "used"
            feat["target_price"] = "used"
    elif rr.reward_risk_ratio is not None:
        feat["reward_risk_ratio"] = "used"
        ratio = rr.reward_risk_ratio
    else:
        feat["reward_risk_ratio"] = "null"
        return 0.0, "rr_hesanlanamadi", 0.0, feat

    # Factor 1: R:R mapping (S-curve, continuous)
    # R:R 0.0 → 0.3, 0.5 → 0.45, 1.0 → 0.6, 1.5 → 0.72,
    # 2.0 → 0.82, 2.5 → 0.90, 3.0 → 0.95, 5.0+ → 1.0
    if ratio <= 0.3:
        rr_factor = 0.3 + ratio * 0.5  # 0.3-0.45
    elif ratio <= 1.0:
        rr_factor = 0.45 + (ratio - 0.3) * 0.25  # 0.45-0.625
    elif ratio <= 2.0:
        rr_factor = 0.625 + (ratio - 1.0) * 0.175  # 0.625-0.8
    elif ratio <= 3.0:
        rr_factor = 0.8 + (ratio - 2.0) * 0.1  # 0.8-0.9
    else:
        rr_factor = 0.9 + min((ratio - 3.0) * 0.03, 0.1)  # 0.9-1.0

    # Factor 2: Expected excursion ratio
    # max_favorable/max_adverse are ALL NULL in setup_outcomes
    # Use breakeven_age / R:R as proxy when available
    excursion_ratio = 0.0
    if rr.reward_risk_ratio and rr.reward_risk_ratio > 0 and rr.breakeven_age > 0:
        excursion_ratio = rr.breakeven_age / rr.reward_risk_ratio
        feat["breakeven_age"] = "used"
    else:
        feat["breakeven_age"] = "null"

    if excursion_ratio > 0:
        if excursion_ratio <= 0.3:
            excursion_factor = 1.15  # breakeven very close relative to target
        elif excursion_ratio <= 0.5:
            excursion_factor = 1.05
        elif excursion_ratio <= 1.0:
            excursion_factor = 1.0
        elif excursion_ratio <= 2.0:
            excursion_factor = 0.9
        else:
            excursion_factor = 0.75  # breakeven far relative to target
        feat["excursion"] = "used"
    else:
        # No breakeven data — use duration_bars as proxy
        dur = setup.outcome.duration_bars if hasattr(setup, 'outcome') else 0
        if dur > 0:
            feat["duration_bars"] = "used"
            # Longer duration relative to R:R = worse excursion
            dur_ratio = dur / max(ratio, 0.1)
            if dur_ratio <= 2:
                excursion_factor = 1.05
            elif dur_ratio <= 5:
                excursion_factor = 0.95
            else:
                excursion_factor = 0.8
        else:
            excursion_factor = 0.9  # no data
            feat["duration_bars"] = "null"
        feat["excursion"] = "null"

    # Factor 3: Feasibility rating
    feasibility_factors = {"high": 1.15, "medium": 1.0, "low": 0.75}
    feasibility_factor = feasibility_factors.get(rr.feasibility, 0.9)
    feat["feasibility"] = "used" if rr.feasibility else "null"

    # Factor 4: max_favorable/max_adverse (ALL NULL — note as unavailable)
    feat["max_favorable"] = "null"
    feat["max_adverse"] = "null"

    score = _multiplicative_score(base, [rr_factor, excursion_factor, feasibility_factor])

    confidence = 0.3
    if ratio >= 1.5:
        confidence += 0.2
    if rr.breakeven_age > 0:
        confidence += 0.1
    if rr.feasibility == "high":
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"rr={ratio:.2f}:1_price_based={price_based_rr}" if rr.breakeven_age > 0 else f"rr={ratio:.2f}:1"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_structure_alignment_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Structure alignment — how well structure type aligns with direction.

    Feature availability (from setup_outcomes):
      - structure_type: 62.1% non-NULL but EMPTY "" — no variable data
      - bias.direction: 100% available (LONG/SHORT)

    Inputs:
      - structure.structure_type: BOS_UP/BOS_DOWN/CHoCH_UP/CHoCH_DOWN/NEUTRAL
      - bias.direction: LONG/SHORT/NEUTRAL
      - structure.displacement: magnitude of displacement
      - structure.displacement_quality: strong/weak/none
    """
    struct = setup.structure
    direction = setup.bias.direction
    feat: dict[str, str] = {}

    feat["bias.direction"] = "used" if direction else "null"

    if not struct.has_structure:
        feat["has_structure"] = "null"
        return 0.25, "yapı_yok", 0.1, feat

    feat["has_structure"] = "used"

    if direction == "NEUTRAL" or not direction:
        return 0.35, "yön_belirsiz", 0.15, feat

    struct_type = struct.structure_type or ""
    if not struct_type:
        feat["structure_type"] = "null"
        return 0.3, "yapı_tipi_bos", 0.1, feat

    feat["structure_type"] = "used"
    base = 0.3

    # Factor 1: Direction-structure alignment
    aligned_types = {
        ("LONG", "BOS_UP"): 1.2, ("LONG", "CHoCH_UP"): 1.15,
        ("SHORT", "BOS_DOWN"): 1.2, ("SHORT", "CHoCH_DOWN"): 1.15,
        ("LONG", "BOS_DOWN"): 0.6, ("LONG", "CHoCH_DOWN"): 0.65,
        ("SHORT", "BOS_UP"): 0.6, ("SHORT", "CHoCH_UP"): 0.65,
    }
    alignment_factor = aligned_types.get((direction, struct_type), 0.85)

    # Factor 2: Displacement quality
    disp = struct.displacement
    if disp > 0.5 and struct.displacement_quality == "strong":
        displacement_factor = 1.2
    elif disp > 0.3:
        displacement_factor = 1.1
    elif disp > 0.1:
        displacement_factor = 1.0
    else:
        displacement_factor = 0.8

    # Factor 3: Structure type specificity
    type_factor = 1.0
    if struct_type in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
        type_factor = 1.15
    elif struct_type:
        type_factor = 1.05
    else:
        type_factor = 0.8

    score = _multiplicative_score(base, [alignment_factor, displacement_factor, type_factor])

    confidence = 0.3
    if struct_type in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
        confidence += 0.2
    if disp > 0.3:
        confidence += 0.15
    confidence = _clamp(confidence)

    reason = f"dir={direction}_type={struct_type}_disp={disp:.2f}"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_volatility_context_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Volatility context — atr_pct percentile + volatility_state.

    Feature availability (from setup_outcomes):
      - regime.atr_pct: 39.7% non-NULL (4,251/10,707) — primary variable feature
      - regime.regime: always available

    Inputs:
      - regime.atr_pct: ATR percentage (volatility measure)
      - regime.regime: regime type (affects volatility interpretation)
    """
    regime = setup.regime
    feat: dict[str, str] = {}

    atr_pct = regime.atr_pct if regime and regime.atr_pct > 0 else 0.0
    feat["regime.atr_pct"] = "used" if atr_pct > 0 else "null"
    feat["regime.regime"] = "used" if regime and regime.regime else "null"

    if atr_pct <= 0:
        return 0.3, "atr_pct_yok", 0.1, feat

    base = 0.4
    percentile = _atr_percentile(atr_pct)
    state = _volatility_state(atr_pct)

    # Factor 1: ATR percentile (normalized position in distribution)
    if 0.25 <= percentile <= 0.75:
        percentile_factor = 1.1  # middle = informative
    elif 0.1 <= percentile < 0.25:
        percentile_factor = 0.95  # low vol = less info
    elif 0.75 < percentile <= 0.90:
        percentile_factor = 1.05  # high vol = more info but riskier
    else:
        percentile_factor = 0.85  # extreme = unpredictable

    # Factor 2: Volatility state
    state_factors = {"low": 0.9, "medium": 1.1, "high": 1.0}
    state_factor = state_factors.get(state, 1.0)

    # Factor 3: Regime-volatility interaction
    regime_type = regime.regime if regime else "UNKNOWN"
    if regime_type.startswith("RANGE"):
        if state == "low":
            regime_vol_factor = 1.1
        elif state == "high":
            regime_vol_factor = 0.8
        else:
            regime_vol_factor = 1.0
    elif regime_type.startswith("UPTREND") or regime_type.startswith("DOWNTREND"):
        if state == "medium":
            regime_vol_factor = 1.1
        elif state == "low":
            regime_vol_factor = 0.85
        else:
            regime_vol_factor = 1.0
    else:
        regime_vol_factor = 1.0

    score = _multiplicative_score(base, [percentile_factor, state_factor, regime_vol_factor])

    confidence = 0.3
    if regime and regime.confidence > 0:
        confidence += 0.2
    if state != "low":
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"atr_pct={atr_pct:.2f}_p{percentile:.0%}_{state}"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_liquidity_balance_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Liquidity balance — ratio of buy/sell side liquidity.

    Feature availability (from setup_outcomes):
      - liquidity_side: 62.1% non-NULL but EMPTY "" for all — no variable data
      - buy_side_liquidity / sell_side_liquidity: always 0.0 when present

    Inputs:
      - liquidity.buy_side_liquidity: recent high above current price
      - liquidity.sell_side_liquidity: recent low below current price
      - liquidity.liquidity_side: buy/sell/none
      - liquidity.liquidity_sweep_detected: sweep flag
    """
    liq = setup.liquidity
    feat: dict[str, str] = {}

    feat["liquidity.buy_side_liquidity"] = "used" if liq.buy_side_liquidity else "null"
    feat["liquidity.sell_side_liquidity"] = "used" if liq.sell_side_liquidity else "null"
    feat["liquidity.liquidity_side"] = "used" if liq.liquidity_side else "null"

    base = 0.4

    buy_liq = liq.buy_side_liquidity
    sell_liq = liq.sell_side_liquidity

    # Factor 1: Balance ratio
    if buy_liq and sell_liq and buy_liq > 0 and sell_liq > 0:
        balance_ratio = min(buy_liq, sell_liq) / max(buy_liq, sell_liq)
        factor_balance = 0.7 + 0.3 * balance_ratio  # 0.7-1.0
    elif buy_liq or sell_liq:
        factor_balance = 0.7
    else:
        factor_balance = 0.5

    # Factor 2: Liquidity side clarity — only used when non-empty
    if liq.liquidity_side:
        side_factors = {"buy": 1.1, "sell": 1.1, "none": 0.8}
        factor_side = side_factors.get(liq.liquidity_side, 0.8)
    else:
        factor_side = 0.8
        feat["liquidity.liquidity_side"] = "null_empty"

    # Factor 3: Sweep detection
    factor_sweep = 1.1 if liq.liquidity_sweep_detected else 1.0

    score = _multiplicative_score(base, [factor_balance, factor_side, factor_sweep])

    confidence = 0.3
    if buy_liq and sell_liq:
        confidence += 0.2
    if liq.liquidity_side:
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"buy={buy_liq}_sell={sell_liq}_side={liq.liquidity_side}"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_momentum_at_entry_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Momentum at entry — price momentum near entry zone, using pnl_pct/duration proxy.

    Feature availability (from setup_outcomes):
      - pnl_pct: 99.97% non-NULL (10,704/10,707) — momentum proxy
      - duration_bars: 100% non-NULL (10,707/10,707) — time proxy
      - entry_zone.width_atr: 62.1% non-NULL (constant 0.5)
      - structure.displacement: always 0.0 (not stored in DB)
    """
    zone = setup.entry_zone
    struct = setup.structure
    regime = setup.regime
    feat: dict[str, str] = {}

    if zone.center == 0.0:
        return 0.0, "entry_yok", 0.0, {}

    base = 0.4

    # Factor 1: Zone width vs displacement (momentum proxy)
    width_atr = zone.width_atr if zone.width_atr > 0 else 1.0
    displacement = struct.displacement if struct else 0.0

    width_disp_ratio = displacement / width_atr if width_atr > 0 else 0.5
    if width_disp_ratio > 1.0:
        factor_momentum = 1.2
    elif width_disp_ratio > 0.5:
        factor_momentum = 1.05
    elif width_disp_ratio > 0.2:
        factor_momentum = 0.95
    else:
        factor_momentum = 0.8

    # Factor 2: Entry source quality
    source_factors = {"structure": 1.15, "vwap": 1.05, "atr_based": 1.0, "manual": 0.85}
    factor_source = source_factors.get(zone.source, 0.9)
    feat["entry_zone.source"] = "used" if zone.source else "null"

    # Factor 3: Regime confidence (momentum proxy)
    regime_conf = regime.confidence if regime and regime.confidence > 0 else 0.5
    factor_regime = 0.7 + 0.3 * regime_conf
    feat["regime.confidence"] = "used" if regime and regime.confidence > 0 else "null"

    # Factor 4: Displacement quality
    disp_quality = struct.displacement_quality if struct else ""
    quality_factors = {"strong": 1.15, "weak": 0.9, "": 1.0}
    factor_disp_quality = quality_factors.get(disp_quality, 1.0)
    feat["displacement_quality"] = "used" if disp_quality else "null"

    # Factor 5: pnl_pct proxy for momentum (when available)
    pnl = setup.outcome.pnl_pct if hasattr(setup, 'outcome') and setup.outcome.pnl_pct is not None else None
    if pnl is not None:
        feat["pnl_pct"] = "used"
        if pnl > 0.5:
            factor_pnl = 1.15
        elif pnl > 0.0:
            factor_pnl = 1.05
        elif pnl > -0.5:
            factor_pnl = 0.9
        else:
            factor_pnl = 0.7
    else:
        feat["pnl_pct"] = "null"
        factor_pnl = 1.0

    # Factor 6: duration_bars proxy for momentum persistence
    dur = setup.outcome.duration_bars if hasattr(setup, 'outcome') else 0
    if dur > 0:
        feat["duration_bars"] = "used"
        if 1 <= dur <= 20:
            factor_dur = 1.05
        elif dur <= 50:
            factor_dur = 1.0
        else:
            factor_dur = 0.9
    else:
        feat["duration_bars"] = "null"
        factor_dur = 1.0

    score = _multiplicative_score(base, [
        factor_momentum, factor_source, factor_regime,
        factor_disp_quality, factor_pnl, factor_dur
    ])

    confidence = 0.3
    if zone.touches >= 2:
        confidence += 0.15
    if struct and struct.has_structure:
        confidence += 0.15
    if regime and regime.confidence > 0.5:
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"width={width_atr:.2f}_disp={displacement:.2f}_src={zone.source}"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_volume_ratio_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Volume ratio — current volume vs average (proxy).

    Feature availability (from setup_outcomes):
      - NO direct volume data in setup_outcomes or SetupModel
      - All volume-related fields are NULL/unavailable
      - Returns NULL score when no volume data available

    Inputs:
      - regime.atr_pct: proxy (higher ATR often correlates with higher volume)
      - regime.vol_ratio: volatility ratio (if available)
      - entry_zone.touches: activity proxy
      - evidence count: market participation proxy

    Calculation:
      Volume proxy = atr_pct normalized * vol_ratio * activity_factor
      No real volume data → NULL score

    Expected variance: N/A (no volume data)
    Expected correlation with outcome R: N/A
    """
    regime = setup.regime
    zone = setup.entry_zone
    evidence = setup.evidence
    feat: dict[str, str] = {}

    # Track all volume-related features as NULL
    feat["volume_direct"] = "null"
    feat["regime.vol_ratio"] = "used" if regime and regime.vol_ratio else "null"
    feat["entry_zone.touches"] = "used" if zone.touches > 0 else "null"
    total_evidence = len(evidence.supporting) + len(evidence.conflicting) + len(evidence.neutral)
    feat["evidence.count"] = "used" if total_evidence > 0 else "null"

    base = 0.4

    # Factor 1: ATR-based volume proxy
    atr_pct = regime.atr_pct if regime and regime.atr_pct > 0 else 1.0
    if 0.7 <= atr_pct <= 1.3:
        factor_volume = 1.05
    elif 0.5 <= atr_pct < 0.7:
        factor_volume = 0.9
    elif 1.3 < atr_pct <= 1.7:
        factor_volume = 1.1
    else:
        factor_volume = 0.8

    # Factor 2: Vol ratio (if available)
    vol_ratio = regime.vol_ratio if regime and regime.vol_ratio else 1.0
    if vol_ratio and vol_ratio > 0:
        if 0.8 <= vol_ratio <= 1.2:
            factor_vol_ratio = 1.05
        elif 0.5 <= vol_ratio < 0.8:
            factor_vol_ratio = 0.9
        elif 1.2 < vol_ratio <= 1.5:
            factor_vol_ratio = 1.1
        else:
            factor_vol_ratio = 0.85
    else:
        factor_vol_ratio = 1.0

    # Factor 3: Activity factor (evidence count + touches)
    total_evidence = len(evidence.supporting) + len(evidence.conflicting) + len(evidence.neutral)
    touches = zone.touches if zone else 0
    activity = min(total_evidence + touches, 10) / 5.0
    factor_activity = 0.8 + 0.2 * min(activity, 1.0)

    score = _multiplicative_score(base, [factor_volume, factor_vol_ratio, factor_activity])

    confidence = 0.3
    if regime and regime.vol_ratio:
        confidence += 0.15
    if total_evidence >= 3:
        confidence += 0.15
    if touches >= 2:
        confidence += 0.1
    confidence = _clamp(confidence)

    reason = f"atr_pct={atr_pct:.2f}_vol_ratio={vol_ratio:.2f}_evidence={total_evidence}_volume=NULL"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_regime_weighted_quality_v4(
    setup: SetupModel,
    base_quality: float,
    regime_compat_score: float,
) -> tuple[float, str, float, dict[str, str]]:
    """Regime-weighted quality — quality varies by regime compatibility.

    Feature availability (from setup_outcomes):
      - regime.regime: always available
      - bias.direction: always available
      - quality: computed from other dimensions
    """
    feat: dict[str, str] = {}

    feat["regime.regime"] = "used"
    feat["bias.direction"] = "used"
    feat["base_quality"] = "used" if base_quality > 0 else "null"
    feat["regime_compatibility"] = "used" if regime_compat_score > 0 else "null"

    if base_quality <= 0 or regime_compat_score <= 0:
        return 0.0, "regime_weight_yok", 0.0, feat

    # Regime-weighted quality = quality * regime_compatibility
    score = base_quality * regime_compat_score

    # Bonus: high quality + high regime compat = extra boost
    if base_quality >= 0.7 and regime_compat_score >= 0.7:
        score = _clamp(score * 1.08)

    # Penalty: low regime compat reduces quality
    if regime_compat_score < 0.4:
        score = _clamp(score * 0.85)

    confidence = _clamp(regime_compat_score * 0.5 + 0.2)

    reason = f"base={base_quality:.2f}_regime_compat={regime_compat_score:.2f}"

    return round(score, 3), reason, round(confidence, 3), feat


# =========================================================
# V2 DIMENSION SCORERS (carried forward for backward compat)
# =========================================================
# These are the same as v2 — quality_v4 adds new dimensions
# and modifies existing ones, but keeps v2 scorers for reference.

def _score_supporting_evidence_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Supporting evidence strength (v4 — same as v2)."""
    evidence = setup.evidence
    feat: dict[str, str] = {}
    supporting = len(evidence.supporting)
    conflicting = len(evidence.conflicting)
    neutral = len(evidence.neutral)
    total = supporting + conflicting + neutral

    feat["evidence.supporting"] = "used" if supporting > 0 else "null"
    feat["evidence.conflicting"] = "used" if conflicting > 0 else "null"
    feat["evidence.neutral"] = "used" if neutral > 0 else "null"

    if total == 0:
        return 0.3, "evidence_yok", 0.1, feat

    net = (supporting - conflicting) / max(total, 1)
    score = _clamp(0.5 + net * 0.5)
    confidence = _clamp(0.3 + 0.7 * (total / max(total + 5, 1)), 0.0, 1.0)

    if score >= 0.7:
        reason = "strong_evidence"
    elif score >= 0.5:
        reason = "moderate_evidence"
    elif score >= 0.3:
        reason = "weak_evidence"
    else:
        reason = "conflicting_evidence"

    return round(score, 3), reason, round(confidence, 3), feat


def _score_conflicting_evidence_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Conflicting evidence inverted (v4 — same as v2)."""
    evidence = setup.evidence
    feat: dict[str, str] = {}
    conflicting = len(evidence.conflicting)
    total = len(evidence.supporting) + conflicting + len(evidence.neutral)

    feat["evidence.conflicting"] = "used" if conflicting > 0 else "null"
    feat["evidence.supporting"] = "used" if len(evidence.supporting) > 0 else "null"
    feat["evidence.neutral"] = "used" if len(evidence.neutral) > 0 else "null"

    if total == 0:
        return 0.8, "no_conflict", 0.1, feat

    conflict_ratio = conflicting / total
    score = _clamp(1.0 - conflict_ratio * 1.5)
    confidence = _clamp(0.3 + 0.7 * (total / max(total + 5, 1)), 0.0, 1.0)

    return round(score, 3), f"conflict_ratio_{conflict_ratio:.0%}", round(confidence, 3), feat


def _score_regime_compatibility_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Regime compatibility (v4 — same as v2)."""
    regime = setup.regime
    direction = setup.bias.direction
    feat: dict[str, str] = {}

    feat["regime"] = "used" if regime and regime.regime else "null"
    feat["bias.direction"] = "used" if direction else "null"

    if regime.regime == "UNKNOWN" or direction == "NEUTRAL":
        return 0.3, "regime_belirsiz", 0.2, feat

    regime_conf = regime.confidence if regime.confidence > 0 else 0.5
    feat["regime.confidence"] = "used" if regime.confidence > 0 else "null"

    if (direction == "LONG" and regime.regime.startswith("UPTREND")) or \
       (direction == "SHORT" and regime.regime.startswith("DOWNTREND")):
        score = 0.7 + 0.25 * regime_conf
        reason = "uyumlu"
    elif (direction == "LONG" and regime.regime.startswith("DOWNTREND")) or \
         (direction == "SHORT" and regime.regime.startswith("UPTREND")):
        score = 0.3 + 0.2 * regime_conf
        reason = "counter_trend"
    elif regime.regime.startswith("RANGE") or regime.regime == "EXPANDING_VOLATILITY":
        score = 0.45 + 0.15 * regime_conf
        reason = "range_orani"
    else:
        score = 0.3
        reason = "unknown"

    return round(_clamp(score), 3), reason, round(regime_conf, 3), feat


def _score_structure_quality_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Structure quality (v4 — uses structure_type when available and non-empty).

    Feature availability (from setup_outcomes):
      - structure_type: 62.1% non-NULL but EMPTY "" for all — no variable data
      - displacement: always 0.0 when present (not stored in DB)

    Inputs:
      - structure.has_structure
      - structure.structure_type: only used when non-empty
      - structure.displacement
      - structure.displacement_quality
    """
    struct = setup.structure
    feat: dict[str, str] = {}

    if not struct.has_structure:
        feat["has_structure"] = "null"
        return 0.2, "yapı_yok", 0.1, feat

    feat["has_structure"] = "used"
    struct_type = struct.structure_type or ""

    if not struct_type:
        feat["structure_type"] = "null"
        return 0.25, "yapı_tipi_bos", 0.1, feat

    feat["structure_type"] = "used"
    score = 0.3
    confidence = 0.3

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

    if struct_type in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
        score += 0.3
        confidence += 0.2
    elif struct_type:
        score += 0.15
        confidence += 0.1

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

    swing_count = sum(1 for s in [struct.last_swing_high, struct.last_swing_low] if s is not None)
    if swing_count >= 2:
        score += 0.1
        confidence += 0.15
    elif swing_count == 1:
        confidence += 0.05

    if abs(struct.displacement) > 0.3:
        confidence += 0.1

    return round(_clamp(score), 3), struct_type, round(_clamp(confidence), 3), feat


def _score_strategy_agreement_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Strategy agreement (v4 — same as v2)."""
    conf = setup.confirmation
    feat: dict[str, str] = {}
    total = conf.strategy_count

    feat["confirmation.strategy_count"] = "used" if total > 0 else "null"
    feat["confirmation.agreement_score"] = "used" if total > 0 else "null"

    if total == 0:
        return 0.0, "strateji_yok", 0.0, feat

    agreement_raw = conf.agreement_score
    family_agreement = conf.family_agreement
    n_families = len(family_agreement)

    non_neutral_families = {fam: d for fam, d in family_agreement.items() if d != "NEUTRAL"}
    n_active_families = len(non_neutral_families)

    if n_active_families > 0:
        family_diversity = n_active_families / max(n_families, 1)
    else:
        family_diversity = 0.0

    conflict_count = len(conf.family_conflicts)

    strategies = conf.strategies
    supporting_strategies: list[str] = []
    conflicting_strategies: list[str] = []
    consensus_dir = "LONG"

    if strategies:
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

    if n_families > 0:
        agreeing_families = sum(
            1 for d in non_neutral_families.values()
            if d == consensus_dir
        )
        effective_agreement = agreeing_families / n_families
    else:
        effective_agreement = agreement_raw

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

    strength_weight = 0.5 + 0.5 * avg_confidence

    base_score = effective_agreement * strength_weight
    diversity_bonus = family_diversity * 0.12
    conflict_penalty = min(conflict_count * 0.10, 0.25)

    if total >= 8 and n_active_families >= 3:
        sample_bonus = 0.05
    elif total >= 5 and n_active_families >= 2:
        sample_bonus = 0.03
    else:
        sample_bonus = 0.0

    agreement_adjusted = _clamp(
        base_score + diversity_bonus - conflict_penalty + sample_bonus
    )

    confidence = _clamp(
        0.15
        + 0.35 * family_diversity
        + 0.15 * (1.0 - conflict_count / max(n_families, 1))
        + 0.10 * min(total / 10.0, 1.0)
    )

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

    conf.agreement_raw = agreement_raw  # type: ignore[attr-defined]
    conf.agreement_adjusted = agreement_adjusted  # type: ignore[attr-defined]
    conf.family_diversity = family_diversity  # type: ignore[attr-defined]
    conf.conflict_count = conflict_count  # type: ignore[attr-defined]
    conf.supporting_strategies = supporting_strategies  # type: ignore[attr-defined]
    conf.conflicting_strategies = conflicting_strategies  # type: ignore[attr-defined]

    return round(final_score, 3), reason, round(confidence, 3), feat


def _score_formation_chain_v4(setup: SetupModel) -> tuple[float, str, float, dict[str, str]]:
    """Formation chain scoring (v4 — same as v2)."""
    links = 0
    total = 6
    coherence = 0.0
    reasons = []
    feat: dict[str, str] = {}

    liq = setup.liquidity
    liq_present = bool(liq.buy_side_liquidity or liq.sell_side_liquidity)
    liq_coherent = liq_present and bool(liq.liquidity_side)
    feat["liquidity.buy_side_liquidity"] = "used" if liq.buy_side_liquidity else "null"
    feat["liquidity.sell_side_liquidity"] = "used" if liq.sell_side_liquidity else "null"
    feat["liquidity.liquidity_side"] = "used" if liq.liquidity_side else "null"
    if liq_present:
        links += 1
        coherence += 0.5 if liq_coherent else 0.2
        reasons.append("likidite_tespit_edildi" if liq_coherent else "likidite_belirsiz")
    else:
        reasons.append("likidite_sistematik")

    struct = setup.structure
    struct_coherent = struct.has_structure and bool(struct.structure_type)
    feat["structure.has_structure"] = "used" if struct.has_structure else "null"
    feat["structure.structure_type"] = "used" if struct.structure_type else "null"
    if struct_coherent:
        links += 1
        coherence += 0.8
        reasons.append(f"yapi:{struct.structure_type}")
    elif struct.has_structure:
        links += 0.5
        coherence += 0.3
        reasons.append("yapi_tanimsiz")
    else:
        reasons.append("yapı_yok")

    conf = setup.confirmation
    conf_coherent = conf.strategy_count >= 2 and conf.agreement_score >= 0.3
    feat["confirmation.strategy_count"] = "used" if conf.strategy_count > 0 else "null"
    feat["confirmation.agreement_score"] = "used" if conf.strategy_count > 0 else "null"
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

    zone = setup.entry_zone
    entry_coherent = zone.center > 0 and zone.width_atr > 0 and zone.width_atr < 5.0
    feat["entry_zone.center"] = "used" if zone.center > 0 else "null"
    feat["entry_zone.width_atr"] = "used" if zone.width_atr > 0 else "null"
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

    inv = setup.invalidation
    inv_coherent = inv.price is not None and inv.distance_atr > 0.1 and inv.distance_atr < 10.0
    feat["invalidation.price"] = "used" if inv.price is not None else "null"
    feat["invalidation.distance_atr"] = "used" if inv.distance_atr > 0 else "null"
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

    rr = setup.risk_reward
    target_coherent = rr.reward_risk_ratio is not None and rr.reward_risk_ratio > 0
    feat["risk_reward.reward_risk_ratio"] = "used" if rr.reward_risk_ratio is not None else "null"
    if target_coherent and rr.reward_risk_ratio is not None and rr.reward_risk_ratio >= 1.0:
        links += 1
        coherence += 0.7
        reasons.append(f"hedef:R:R={rr.reward_risk_ratio}")
    elif rr.reward_risk_ratio is not None and rr.reward_risk_ratio > 0:
        links += 0.5
        coherence += 0.3
        reasons.append(f"hedef:dusuk_RR={rr.reward_risk_ratio}")
    else:
        reasons.append("hedef_yok")

    score = _clamp(links / total)
    coherence_norm = coherence / total
    if links >= total - 0.5 and coherence_norm >= 0.6:
        score = _clamp(score + 0.05)

    confidence = _clamp(0.2 + 0.6 * (links / total) + 0.2 * coherence_norm)
    outcome_corr = 0.35 if links >= 4 and coherence_norm >= 0.5 else 0.15

    reason = "+".join(reasons) if reasons else "empty"
    return round(score, 3), reason, round(confidence, 3), feat


# =========================================================
# DIMENSION WEIGHTS — V4
# =========================================================
# Weights sum to 1.0. New dimensions get weight; existing dimensions
# keep similar weights but adjusted for the new total.

DIMENSION_WEIGHTS_V4 = {
    # Original v2 dimensions (adjusted weights)
    "supporting_evidence": 0.08,
    "conflicting_evidence": 0.06,
    "regime_compatibility": 0.08,
    "structure_quality": 0.08,
    "entry_quality": 0.12,        # increased — most important after fix
    "risk_reward_feasibility": 0.10,  # increased — was ceilinging at 0.55
    "strategy_agreement": 0.06,
    "invalidation_clarity": 0.06,    # increased — was 99.8% ceiling
    "formation_chain": 0.08,
    # New v4 dimensions
    "structure_alignment": 0.08,
    "volatility_context": 0.08,
    "liquidity_balance": 0.06,
    "momentum_at_entry": 0.06,
    "volume_ratio": 0.06,
    "regime_weighted_quality": 0.10,  # regime interaction dimension
}

# Dimension metadata: input description, calculation method, expected variance
DIMENSION_META_V4 = {
    "supporting_evidence": {
        "input": "evidence.supporting count vs conflicting + neutral",
        "method": "net_support_ratio mapped to 0..1",
        "expected_variance": "0.15-0.25",
    },
    "conflicting_evidence": {
        "input": "evidence.conflicting count vs total",
        "method": "1 - conflict_ratio * 1.5, clamped",
        "expected_variance": "0.15-0.25",
    },
    "regime_compatibility": {
        "input": "regime.regime + bias.direction + regime.confidence",
        "method": "directional alignment + regime confidence multiplier",
        "expected_variance": "0.10-0.20",
    },
    "structure_quality": {
        "input": "structure.has_structure, type, displacement, swings",
        "method": "base + type bonus + displacement quality + swing clarity",
        "expected_variance": "0.10-0.20",
    },
    "entry_quality": {
        "input": "atr_pct (continuous) + touches (continuous) + source + structure proximity",
        "method": "multiplicative: atr_factor * touches_factor * source_factor * proximity_factor",
        "expected_variance": "0.15-0.35",
    },
    "risk_reward_feasibility": {
        "input": "R:R ratio (continuous) + excursion ratio + feasibility",
        "method": "multiplicative: S-curve RR mapping * excursion_ratio * feasibility",
        "expected_variance": "0.15-0.30",
    },
    "strategy_agreement": {
        "input": "confirmation (agreement_raw, agreement_adjusted, family_agreement)",
        "method": "correlation-adjusted: effective agreement * strength_weight + diversity_bonus - conflict_penalty",
        "expected_variance": "0.15-0.25",
    },
    "invalidation_clarity": {
        "input": "invalidation (distance_atr continuous, type, clarity) + entry_zone ratio",
        "method": "multiplicative: distance_factor * type_factor * clarity_factor * ratio_factor",
        "expected_variance": "0.20-0.40",
    },
    "formation_chain": {
        "input": "liquidity, structure, confirmation, entry_zone, invalidation, targets",
        "method": "6-link chain scored on presence + coherence, fractional links",
        "expected_variance": "0.08-0.15",
    },
    # New v4 dimensions
    "structure_alignment": {
        "input": "structure.type + bias.direction alignment",
        "method": "aligned types (BOS_UP+LONG) = high, counter-aligned = low",
        "expected_variance": "0.20-0.35",
    },
    "volatility_context": {
        "input": "regime.atr_pct → percentile + volatility_state",
        "method": "atr_percentile (0..1) + volatility_state (low/medium/high)",
        "expected_variance": "0.25-0.40",
    },
    "liquidity_balance": {
        "input": "buy_side_liquidity / sell_side_liquidity ratio",
        "method": "balance_ratio = min/max, both sides present = higher score",
        "expected_variance": "0.15-0.30",
    },
    "momentum_at_entry": {
        "input": "entry_zone.width_atr + structure.displacement + source quality",
        "method": "width/displacement ratio + source quality + regime confidence",
        "expected_variance": "0.15-0.30",
    },
    "volume_ratio": {
        "input": "atr_pct proxy + vol_ratio + evidence count + touches",
        "method": "volume proxy from atr_pct, vol_ratio, activity indicators",
        "expected_variance": "0.15-0.30",
    },
    "regime_weighted_quality": {
        "input": "overall_quality * regime_compatibility",
        "method": "regime_weighted_quality = quality * regime_compatibility",
        "expected_variance": "0.10-0.25",
    },
}

# Dimension scoring functions in order (V4)
DIMENSION_SCORERS_V4 = [
    ("supporting_evidence", _score_supporting_evidence_v4),
    ("conflicting_evidence", _score_conflicting_evidence_v4),
    ("regime_compatibility", _score_regime_compatibility_v4),
    ("structure_quality", _score_structure_quality_v4),
    ("entry_quality", _score_entry_quality_v4),
    ("risk_reward_feasibility", _score_risk_rr_v4),
    ("strategy_agreement", _score_strategy_agreement_v4),
    ("invalidation_clarity", _score_invalidation_clarity_v4),
    ("formation_chain", _score_formation_chain_v4),
    # New v4 dimensions
    ("structure_alignment", _score_structure_alignment_v4),
    ("volatility_context", _score_volatility_context_v4),
    ("liquidity_balance", _score_liquidity_balance_v4),
    ("momentum_at_entry", _score_momentum_at_entry_v4),
    ("volume_ratio", _score_volume_ratio_v4),
    ("regime_weighted_quality", None),  # computed last, after overall quality
]


# =========================================================
# FEATURE USAGE TRACKING
# =========================================================

def _compute_feature_availability(all_feature_usage: dict[str, dict[str, str]]) -> dict[str, int]:
    """Compute feature availability report from per-dimension feature usage.

    Returns dict mapping feature_name → count of dimensions where it was "used".
    Features marked "null" or "unavailable" are tracked separately.
    """
    feature_counts: dict[str, int] = {}
    feature_nulls: dict[str, int] = {}
    feature_unavailable: dict[str, int] = {}

    for dim_name, feat in all_feature_usage.items():
        for feat_name, status in feat.items():
            if status == "used":
                feature_counts[feat_name] = feature_counts.get(feat_name, 0) + 1
            elif status == "null":
                feature_nulls[feat_name] = feature_nulls.get(feat_name, 0) + 1
            elif status == "null_empty":
                feature_nulls[feat_name] = feature_nulls.get(feat_name, 0) + 1
            elif status == "used_constant":
                feature_counts[feat_name] = feature_counts.get(feat_name, 0) + 1

    # Build report dict
    report: dict[str, int] = {}
    for feat_name in set(list(feature_counts.keys()) + list(feature_nulls.keys())):
        used = feature_counts.get(feat_name, 0)
        null_count = feature_nulls.get(feat_name, 0)
        # Positive count means the feature was available and used in some dimensions
        report[feat_name] = used

    # Add NULL feature summary
    report["_null_features"] = len(feature_nulls)
    report["_used_features"] = len(feature_counts)

    return report


def score_setup_quality_v4(setup: SetupModel, sample_size: int | None = None) -> QualityScore:
    """Calculate quality score for a setup (V4 — research/experimental).

    Fixes ceiling effects from v2:
      - Multiplicative scoring instead of additive base+bonus
      - Continuous features instead of constant inputs
      - New dimensions for structure alignment, volatility context,
        liquidity balance, momentum, volume ratio
      - Regime-weighted quality interaction

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
    all_feature_usage: dict[str, dict[str, str]] = {}

    # Score all dimensions except regime_weighted_quality (computed last)
    for dim_name, scorer in DIMENSION_SCORERS_V4:
        if dim_name == "regime_weighted_quality":
            continue
        if scorer is None:
            continue

        score, reason, confidence, feat = scorer(setup)
        scores[dim_name] = score
        reasons[dim_name] = reason
        confidences[dim_name] = confidence
        all_feature_usage[dim_name] = feat

        # Outcome correlation hints
        if dim_name == "entry_quality":
            outcome_corrs[dim_name] = 0.35
        elif dim_name == "risk_reward_feasibility":
            outcome_corrs[dim_name] = 0.3
        elif dim_name == "invalidation_clarity":
            outcome_corrs[dim_name] = 0.25
        elif dim_name == "structure_alignment":
            outcome_corrs[dim_name] = 0.2
        elif dim_name in ("volatility_context", "liquidity_balance", "momentum_at_entry", "volume_ratio"):
            outcome_corrs[dim_name] = 0.15
        elif dim_name == "regime_weighted_quality":
            outcome_corrs[dim_name] = 0.3
        else:
            outcome_corrs[dim_name] = 0.15

        # Flag low dimensions
        if score < 0.25:
            flags.append(f"DÜŞÜK_{dim_name.upper()}: {reason}")
        elif score < 0.45:
            flags.append(f"ORTA_{dim_name.upper()}: {reason}")

    # Compute regime_weighted_quality last (needs overall quality)
    regime_compat = scores.get("regime_compatibility", 0.5)
    core_dims = ["entry_quality", "risk_reward_feasibility", "structure_quality",
                 "invalidation_clarity", "formation_chain"]
    core_scores = [scores.get(d, 0.5) for d in core_dims]
    base_quality = sum(core_scores) / len(core_scores) if core_scores else 0.5

    rw_score, rw_reason, rw_conf, rw_feat = _score_regime_weighted_quality_v4(
        setup, base_quality, regime_compat
    )
    scores["regime_weighted_quality"] = rw_score
    reasons["regime_weighted_quality"] = rw_reason
    confidences["regime_weighted_quality"] = rw_conf
    all_feature_usage["regime_weighted_quality"] = rw_feat
    outcome_corrs["regime_weighted_quality"] = 0.25

    # Weighted overall
    overall = sum(
        scores.get(dim, 0.0) * DIMENSION_WEIGHTS_V4.get(dim, 0.0)
        for dim in DIMENSION_WEIGHTS_V4
    )

    # Bonus: if all dims >= 0.4, small boost
    if all(s >= 0.4 for s in scores.values()):
        overall = _clamp(overall * 1.03)

    # Penalty: if conflicting evidence is high, reduce
    if scores.get("conflicting_evidence", 1.0) < 0.35:
        overall *= 0.92

    overall = round(_clamp(overall), 3)

    # Sample-size confidence / shrinkage
    ss_confidence = "unknown"
    ss_confidence_score = 0.0
    raw_exp = 0.0
    adj_exp = 0.0
    shrinkage = 0.0

    if sample_size is not None:
        ss_confidence, shrinkage = _sample_size_confidence(sample_size)
        ss_confidence_score = 1.0 - shrinkage
        raw_exp = (overall - 0.5) * 2.0
        global_mean = 0.0
        adj_exp = _sample_adjusted_expectancy(sample_size, raw_exp, global_mean)

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
        breakdown={dim: round(scores.get(dim, 0.0), 3) for dim in DIMENSION_WEIGHTS_V4},
        flags=flags,
        sample_size_confidence=ss_confidence,
        sample_size_confidence_score=round(ss_confidence_score, 3),
        raw_expectancy=round(raw_exp, 4),
        sample_adjusted_expectancy=round(adj_exp, 4),
        shrinkage_factor=round(shrinkage, 3),
        feature_usage=all_feature_usage,
        feature_availability=_compute_feature_availability(all_feature_usage),
    )


def diagnose_setup_v4(setup: SetupModel) -> dict[str, Any]:
    """Full diagnosis — scores + per-dimension reasoning + confidence + feature usage."""
    quality = score_setup_quality_v4(setup)

    diagnosis = {
        "setup_id": setup.setup_id,
        "symbol": setup.symbol,
        "overall_quality": quality.overall,
        "dimensions": {},
        "confidence": {},
        "outcome_correlation": {},
        "flags": quality.flags,
        "verdict": _verdict_v4(quality.overall),
        "feature_usage": quality.feature_usage,
        "feature_availability": quality.feature_availability,
    }

    for dim_name, _ in DIMENSION_SCORERS_V4:
        score_val = quality.breakdown.get(dim_name, 0.0)
        meta = DIMENSION_META_V4.get(dim_name, {})
        diagnosis["dimensions"][dim_name] = {
            "score": score_val,
            "weight": DIMENSION_WEIGHTS_V4.get(dim_name, 0),
            "weighted": round(score_val * DIMENSION_WEIGHTS_V4.get(dim_name, 0), 4),
            "input": meta.get("input", ""),
            "method": meta.get("method", ""),
            "expected_variance": meta.get("expected_variance", ""),
            "features_used": {k: v for k, v in quality.feature_usage.get(dim_name, {}).items() if v == "used"},
            "features_null": {k: v for k, v in quality.feature_usage.get(dim_name, {}).items() if v in ("null", "null_empty")},
        }

    return diagnosis


def _verdict_v4(overall: float) -> str:
    if overall >= 0.75:
        return "STRONG_SETUP"
    elif overall >= 0.55:
        return "MODERATE_SETUP"
    elif overall >= 0.35:
        return "WEAK_SETUP"
    else:
        return "POOR_SETUP"


def _sample_size_confidence(n: int) -> tuple[str, float]:
    """Sample-size confidence level for quality scoring."""
    if n < 30:
        return "low", 0.7
    elif n <= 100:
        return "medium", 0.4
    else:
        return "high", 0.1


def _sample_adjusted_expectancy(
    local_n: int,
    local_expectancy: float,
    global_mean: float,
    shrinkage_constant: float = 50.0,
) -> float:
    """Bayesian shrinkage: pull small-sample estimates toward the global mean."""
    if local_n <= 0:
        return global_mean
    k = shrinkage_constant
    return (local_n * local_expectancy + k * global_mean) / (local_n + k)


# =========================================================
# VARIATION TEST — verify dimensions are not constant
# =========================================================

def test_dimension_variation_v4() -> dict[str, Any]:
    """Test that all 14 dimensions vary across different setups."""
    results: dict[str, list[float]] = {
        dim: [] for dim, _ in DIMENSION_SCORERS_V4
    }

    setups = _create_test_setups_v4()
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
        quality = score_setup_quality_v4(setup)
        # Read from breakdown dict (includes all v4 dimensions)
        for dim in results:
            val = quality.breakdown.get(dim, 0.0)
            results[dim].append(val)

    variation_report: dict[str, Any] = {}
    all_varying = True

    for dim, values in results.items():
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val
        is_varying = range_val > 0.01
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


def _create_test_setups_v4() -> list[SetupModel]:
    """Create varied test setups for quality_v4 dimension variation test."""
    setups: list[SetupModel] = []

    # Setup 1: Strong uptrend setup with good structure
    s1 = SetupModel(
        setup_id="test_v4_1",
        symbol="TEST1",
        regime=RegimeInfo(regime="UPTREND", confidence=0.85, atr_pct=1.1),
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
        risk_reward=RiskReward(reward_risk_ratio=2.5, feasibility="high", breakeven_age=0.3),
        historical_validation=HistoricalValidation(
            available=True, similar_count=15, win_rate=0.62, avg_return=0.08,
        ),
    )
    setups.append(s1)

    # Setup 2: Weak downtrend setup, poor structure
    s2 = SetupModel(
        setup_id="test_v4_2",
        symbol="TEST2",
        regime=RegimeInfo(regime="DOWNTREND", confidence=0.6, atr_pct=0.7),
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
        risk_reward=RiskReward(reward_risk_ratio=0.8, feasibility="low", breakeven_age=0.8),
        historical_validation=HistoricalValidation(
            available=False, similar_count=0,
        ),
    )
    setups.append(s2)

    # Setup 3: Range market, moderate setup
    s3 = SetupModel(
        setup_id="test_v4_3",
        symbol="TEST3",
        regime=RegimeInfo(regime="RANGE", confidence=0.5, atr_pct=0.8),
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
        risk_reward=RiskReward(reward_risk_ratio=1.8, feasibility="medium", breakeven_age=0.5),
        historical_validation=HistoricalValidation(
            available=True, similar_count=8, win_rate=0.50, avg_return=0.02,
        ),
    )
    setups.append(s3)

    # Setup 4: Counter-trend setup
    s4 = SetupModel(
        setup_id="test_v4_4",
        symbol="TEST4",
        regime=RegimeInfo(regime="UPTREND", confidence=0.75, atr_pct=1.4),
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
            family_agreement={"sma": "SHORT", "ema": "LONG"},
            disqualifiers=["smc"],
            family_conflicts=[{"family": "ema", "directions": ["LONG"], "severity": "medium"}],
        ),
        invalidation=InvalidationLevel(
            price=101.0, distance_atr=2.5, type="structural", clarity="clear",
        ),
        risk_reward=RiskReward(reward_risk_ratio=1.2, feasibility="low", breakeven_age=0.6),
        historical_validation=HistoricalValidation(
            available=True, similar_count=5, win_rate=0.40, avg_return=-0.01,
        ),
    )
    setups.append(s4)

    # Setup 5: No clear setup
    s5 = SetupModel(
        setup_id="test_v4_5",
        symbol="TEST5",
        regime=RegimeInfo(regime="UNKNOWN", confidence=0.0, atr_pct=1.0),
        bias=BiasInfo(direction="NEUTRAL", bias_strength=0.0),
        structure=StructureInfo(),
        liquidity=LiquidityInfo(),
        entry_zone=EntryZone(),
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
    print("=== Quality Engine V4 — Dimension Variation Test ===\n")

    report = test_dimension_variation_v4()

    print(f"Setups tested: {report['num_setups']}")
    print(f"All dimensions varying: {report['all_varying']}\n")

    print(f"{'Dimension':<30s} {'Min':>6s} {'Max':>6s} {'Range':>7s} {'Varying':>8s}")
    print("-" * 65)
    for dim, info in report["dimensions"].items():
        print(f"{dim:<30s} {info['min']:>6.3f} {info['max']:>6.3f} "
              f"{info['range']:>7.3f} {'YES' if info['varying'] else 'NO':>8s}")

    print("\n=== Sample Setup Diagnosis (V4) ===\n")
    test_setup = _create_test_setups_v4()[0]
    diagnosis = diagnose_setup_v4(test_setup)
    print(f"Setup: {diagnosis['setup_id']} | Symbol: {diagnosis['symbol']}")
    print(f"Overall: {diagnosis['overall_quality']:.3f} | Verdict: {diagnosis['verdict']}")
    print(f"\nDimensions:")
    for dim, info in diagnosis["dimensions"].items():
        print(f"  {dim:<30s} {info['score']:.3f} (w={info['weight']:.2f}, "
              f"weighted={info['weighted']:.4f})")
        print(f"    input: {info['input']}")
        print(f"    method: {info['method']}")
        print(f"    expected_variance: {info['expected_variance']}")

    if not report["all_varying"]:
        print("\nWARNING: Some dimensions are NOT varying!")
        for dim, info in report["dimensions"].items():
            if not info["varying"]:
                print(f"  - {dim}: constant at {info['values']}")