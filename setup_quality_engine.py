# -*- coding: utf-8 -*-
"""
MarketHQ Setup Quality Engine V1
==================================

9 boyutlu evidence-based quality scoring.
Her setup için: supporting evidence, conflicting evidence, regime compatibility,
structure quality, entry quality, risk/reward feasibility, historical validation,
strategy agreement, invalidation clarity.

Giris: SetupModel (setup_object_model.py)
Cikti: QualityScore (0..1 overall + breakdown)

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
# DIMENSION SCORING
# =========================================================

def _score_supporting_evidence(setup: SetupModel) -> tuple[float, str]:
    """Supporting evidence strength."""
    evidence = setup.evidence
    supporting = len(evidence.supporting)
    conflicting = len(evidence.conflicting)
    neutral = len(evidence.neutral)
    total = supporting + conflicting + neutral

    if total == 0:
        return 0.3, "evidence_yok"

    net = (supporting - conflicting) / max(total, 1)
    score = max(0.0, min(1.0, 0.5 + net * 0.5))

    if score >= 0.7:
        reason = "strong_evidence"
    elif score >= 0.5:
        reason = "moderate_evidence"
    elif score >= 0.3:
        reason = "weak_evidence"
    else:
        reason = "conflicting_evidence"

    return round(score, 3), reason


def _score_conflicting_evidence(setup: SetupModel) -> tuple[float, str]:
    """Conflicting evidence is inverted for quality scoring."""
    evidence = setup.evidence
    conflicting = len(evidence.conflicting)
    total = len(evidence.supporting) + conflicting + len(evidence.neutral)

    if total == 0:
        return 0.8, "no_conflict"

    conflict_ratio = conflicting / total
    score = max(0.0, 1.0 - conflict_ratio * 1.5)

    return round(score, 3), f"conflict_ratio_{conflict_ratio:.0%}"


def _score_regime_compatibility(setup: SetupModel) -> tuple[float, str]:
    """Does the setup direction match the market regime?"""
    regime = setup.regime.regime
    direction = setup.bias.direction

    if regime == "UNKNOWN" or direction == "NEUTRAL":
        return 0.3, "regime_belirsiz"

    # LONG in uptrend = good, SHORT in downtrend = good
    if (direction == "LONG" and regime.startswith("UPTREND")) or \
       (direction == "SHORT" and regime.startswith("DOWNTREND")):
        return 0.85, "uyumlu"

    # Counter-trend — possible but lower quality
    if (direction == "LONG" and regime.startswith("DOWNTREND")) or \
       (direction == "SHORT" and regime.startswith("UPTREND")):
        return 0.4, "counter_trend"

    # Range — any direction is neutral
    if regime.startswith("RANGE") or regime == "EXPANDING_VOLATILITY":
        return 0.55, "range_orani"

    return 0.3, "unknown"


def _score_structure_quality(setup: SetupModel) -> tuple[float, str]:
    """Quality of market structure (BOS/CHoCH, swings, displacement)."""
    struct = setup.structure

    if not struct.has_structure:
        return 0.2, "yapı_yok"

    score = 0.3  # base for having structure

    # Structure type bonus
    if struct.structure_type in ("BOS_UP", "BOS_DOWN", "CHoCH_UP", "CHoCH_DOWN"):
        score += 0.3

    # Displacement quality
    if struct.displacement > 0.5:
        score += 0.2
        if struct.displacement_quality == "strong":
            score += 0.2
    elif struct.displacement > 0:
        score += 0.1

    # Swing clarity
    if struct.last_swing_high and struct.last_swing_low:
        score += 0.1

    return round(min(score, 1.0), 3), struct.structure_type or "basic"


def _score_entry_quality(setup: SetupModel) -> tuple[float, str]:
    """Entry zone quality — width, touches, source."""
    zone = setup.entry_zone

    if zone.center == 0.0:
        return 0.0, "entry_yok"

    score = 0.4  # base for having entry

    # Zone width — narrower = better (but not too tight)
    if zone.width_atr > 0:
        if 0.3 <= zone.width_atr <= 1.5:
            score += 0.3  # sweet spot
        elif zone.width_atr < 0.3:
            score += 0.15  # too tight, hard to enter
        else:
            score += 0.1  # too wide, unclear

    # Touches — more touches = stronger support/resistance
    if zone.touches >= 2:
        score += 0.2
    elif zone.touches == 1:
        score += 0.1

    # Source quality
    if zone.source == "structure":
        score += 0.1  # structure-based entries are higher quality

    return round(min(score, 1.0), 3), f"width_{zone.width_atr:.2f}ATR_touches_{zone.touches}"


def _score_risk_reward(setup: SetupModel) -> tuple[float, str]:
    """Risk/reward feasibility — includes Deflated Sharpe adjustment."""
    rr = setup.risk_reward

    if rr.reward_risk_ratio is None:
        return 0.1, "rr_hesanlanamadi"

    ratio = rr.reward_risk_ratio

    # Base R:R score
    if ratio >= 3.0:
        base = 0.9
    elif ratio >= 2.0:
        base = 0.75
    elif ratio >= 1.5:
        base = 0.55
    elif ratio >= 1.0:
        base = 0.35
    else:
        base = 0.15

    # Deflated Sharpe penalty — if historical deflated Sharpe is low, reduce score
    hv = setup.historical_validation
    if hv.available and hv.avg_return is not None and hv.win_rate is not None:
        # Simple deflated Sharpe proxy
        if hv.win_rate < 0.4 and hv.avg_return < 0:
            base *= 0.7  # penalize overfit-looking setups

    return round(min(base, 1.0), 3), f"rr={ratio}:1{'_deflated' if hv.available and hv.win_rate and hv.win_rate < 0.4 else ''}"


def _score_historical_validation(setup: SetupModel) -> tuple[float, str]:
    """Historical validation score."""
    hv = setup.historical_validation

    if not hv.available:
        return 0.2, "tarihsel_yok"

    if hv.similar_count == 0:
        return 0.2, "benzer_setup_yok"

    score = 0.3  # base for having historical data

    if hv.win_rate is not None:
        if hv.win_rate >= 0.65:
            score += 0.35
        elif hv.win_rate >= 0.55:
            score += 0.25
        elif hv.win_rate >= 0.45:
            score += 0.15
        else:
            score += 0.05
    else:
        score += 0.05  # some credit for having data

    if hv.avg_return is not None and hv.avg_return > 0:
        score += 0.15
    elif hv.avg_return is not None and hv.avg_return < 0:
        score -= 0.1

    return round(max(0.0, min(1.0, score)), 3), f"winrate_{hv.win_rate:.0%}_n={hv.similar_count}" if hv.win_rate else f"n={hv.similar_count}"


def _score_strategy_agreement(setup: SetupModel) -> tuple[float, str]:
    """Strategy agreement quality — not just count but family diversity."""
    confirm = setup.confirmation

    total = confirm.strategy_count
    if total == 0:
        return 0.0, "strateji_yok"

    score = 0.3  # base

    # Agreement score
    score += confirm.agreement_score * 0.4

    # Family diversity — more families = better
    family_count = len(confirm.family_agreement)
    if family_count >= 4:
        score += 0.2
    elif family_count >= 3:
        score += 0.15
    elif family_count >= 2:
        score += 0.1

    # Disqualifiers penalty
    disqualifiers = len(confirm.disqualifiers)
    if disqualifiers > 0:
        score -= 0.1 * disqualifiers

    return round(max(0.0, min(1.0, score)), 3), f"families={family_count}_agree={confirm.agreement_score:.0%}"


def _score_invalidation_clarity(setup: SetupModel) -> tuple[float, str]:
    """How clear is the invalidation level?"""
    inv = setup.invalidation

    if inv.price is None:
        return 0.0, "invalidation_yok"

    score = 0.4  # base for having invalidation

    # Clarity type
    if inv.clarity == "clear":
        score += 0.35
    elif inv.clarity == "medium":
        score += 0.2
    else:
        score += 0.05

    # Distance — too close = noisy, too far = risky
    if 0.3 <= inv.distance_atr <= 3.0:
        score += 0.25
    elif inv.distance_atr < 0.3:
        score += 0.05  # too tight
    else:
        score += 0.15  # far but acceptable

    # Type
    if inv.type == "structural":
        score += 0.05  # structural stops are more reliable

    return round(min(score, 1.0), 3), f"clarity={inv.clarity}_dist={inv.distance_atr:.1f}ATR"


def _score_formation_chain(setup: SetupModel) -> tuple[float, str]:
    """
    Setup formation chain scoring:
    Liquidity -> Structure -> Confirmation -> Entry -> Invalidation -> Targets

    Each link must be present and coherent for high score.
    """
    links = 0
    total = 6
    reasons = []

    # 1. Liquidity
    liq = setup.liquidity
    if liq.buy_side_liquidity or liq.sell_side_liquidity:
        links += 1
        reasons.append("likidite_tespit_edildi")
    else:
        reasons.append("likidite_sistematik")

    # 2. Structure
    struct = setup.structure
    if struct.has_structure and struct.structure_type:
        links += 1
        reasons.append(f"yapi:{struct.structure_type}")
    else:
        reasons.append("yapı_yok")

    # 3. Confirmation
    conf = setup.confirmation
    if conf.strategy_count >= 3 and conf.agreement_score >= 0.3:
        links += 1
        reasons.append(f"onay:{conf.agreement_score:.0%}")
    elif conf.strategy_count >= 1:
        links += 1
        reasons.append(f"zayif_onay:{conf.agreement_score:.0%}")
    else:
        reasons.append("onay_yok")

    # 4. Entry Zone
    zone = setup.entry_zone
    if zone.center > 0 and zone.width_atr > 0:
        links += 1
        reasons.append(f"entry_zone:{zone.width_atr:.2f}ATR")
    else:
        reasons.append("entry_yok")

    # 5. Invalidation
    inv = setup.invalidation
    if inv.price is not None and inv.distance_atr > 0:
        links += 1
        reasons.append(f"invalidation:{inv.distance_atr:.1f}ATR")
    else:
        reasons.append("invalidation_yok")

    # 6. Targets
    rr = setup.risk_reward
    if rr.reward_risk_ratio is not None and rr.reward_risk_ratio >= 1.0:
        links += 1
        reasons.append(f"hedef:R:R={rr.reward_risk_ratio}")
    else:
        reasons.append("hedef_yok")

    score = links / total
    reason = "+".join(reasons) if reasons else "empty"
    return round(score, 3), reason


# =========================================================
# MAIN SCORING
# =========================================================

# Dimension weights — sum should be ~1.0
DIMENSION_WEIGHTS = {
    "supporting_evidence": 0.11,
    "conflicting_evidence": 0.07,
    "regime_compatibility": 0.11,
    "structure_quality": 0.11,
    "entry_quality": 0.13,
    "risk_reward_feasibility": 0.12,
    "historical_validation": 0.09,
    "strategy_agreement": 0.09,
    "invalidation_clarity": 0.07,
    "formation_chain": 0.10,
}

# Dimension scoring functions in order
DIMENSION_SCORERS = [
    ("supporting_evidence", _score_supporting_evidence),
    ("conflicting_evidence", _score_conflicting_evidence),
    ("regime_compatibility", _score_regime_compatibility),
    ("structure_quality", _score_structure_quality),
    ("entry_quality", _score_entry_quality),
    ("risk_reward_feasibility", _score_risk_reward),
    ("historical_validation", _score_historical_validation),
    ("strategy_agreement", _score_strategy_agreement),
    ("invalidation_clarity", _score_invalidation_clarity),
    ("formation_chain", _score_formation_chain),
]


def score_setup_quality(setup: SetupModel) -> QualityScore:
    """
    Calculate 9-dimension quality score for a setup.

    Returns QualityScore with overall score, per-dimension scores,
    breakdown dict, and flags.
    """
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    flags: list[str] = []

    for dim_name, scorer in DIMENSION_SCORERS:
        score, reason = scorer(setup)
        scores[dim_name] = score
        reasons[dim_name] = reason

        # Flag low dimensions
        if score < 0.3:
            flags.append(f"DÜŞÜK_{dim_name.upper()}: {reason}")
        elif score < 0.5:
            flags.append(f"ORTA_{dim_name.upper()}: {reason}")

    # Weighted overall
    overall = sum(
        scores.get(dim, 0.0) * DIMENSION_WEIGHTS.get(dim, 0.0)
        for dim in DIMENSION_WEIGHTS
    )

    # Bonus: if all dims >= 0.5, boost
    if all(s >= 0.5 for s in scores.values()):
        overall = min(1.0, overall * 1.05)

    # Penalty: if conflicting evidence is high, reduce
    if scores.get("conflicting_evidence", 1.0) < 0.4:
        overall *= 0.85

    overall = round(max(0.0, min(1.0, overall)), 3)

    return QualityScore(
        overall=overall,
        supporting_evidence=scores.get("supporting_evidence", 0.0),
        conflicting_evidence=scores.get("conflicting_evidence", 0.0),
        regime_compatibility=scores.get("regime_compatibility", 0.0),
        structure_quality=scores.get("structure_quality", 0.0),
        entry_quality=scores.get("entry_quality", 0.0),
        risk_reward_feasibility=scores.get("risk_reward_feasibility", 0.0),
        historical_validation=scores.get("historical_validation", 0.0),
        strategy_agreement=scores.get("strategy_agreement", 0.0),
        invalidation_clarity=scores.get("invalidation_clarity", 0.0),
        formation_chain=scores.get("formation_chain", 0.0),
        breakdown={dim: round(scores.get(dim, 0.0), 3) for dim in DIMENSION_WEIGHTS},
        flags=flags,
    )


def diagnose_setup(setup: SetupModel) -> dict[str, Any]:
    """Full diagnosis — scores + per-dimension reasoning."""
    quality = score_setup_quality(setup)

    diagnosis = {
        "setup_id": setup.setup_id,
        "symbol": setup.symbol,
        "overall_quality": quality.overall,
        "dimensions": {},
        "flags": quality.flags,
        "verdict": _verdict(quality.overall),
    }

    for dim_name, _ in DIMENSION_SCORERS:
        score_val = getattr(quality, dim_name, 0.0)
        # Get reason from breakdown
        diagnosis["dimensions"][dim_name] = {
            "score": score_val,
            "weight": DIMENSION_WEIGHTS.get(dim_name, 0),
            "weighted": round(score_val * DIMENSION_WEIGHTS.get(dim_name, 0), 4),
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