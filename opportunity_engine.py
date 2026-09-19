# -*- coding: utf-8 -*-
"""Opportunity Engine — detection, aggregation, conflict analysis, thesis.

Phase E core: aggregates Phase D strategy research agent results into
structured Opportunity objects.

Research-only. No trading, no orders, no execution.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from agent_contract import AgentResult, AgentStatus
from opportunity_model import (
    Opportunity, OpportunityStatus, Direction,
    SetupCandidate, SourceAgent,
)
from strategy_research_agents import STRATEGY_AGENTS
from strategy_research_registry import get_strategy_registry


# =========================================================
# STRATEGY FAMILY METADATA
# =========================================================

STRATEGY_FAMILY_MAP = {
    "strategy_trend": "trend",
    "strategy_breakout": "breakout",
    "strategy_reversal": "mean_reversion",
    "strategy_momentum": "momentum",
    "strategy_volatility": "volatility",
    "strategy_liquidity": "liquidity",
    "strategy_structure": "structure",
}

# Families that are correlation-prone (same underlying signal)
CORRELATED_FAMILIES: dict[str, set[str]] = {
    "trend": {"trend", "breakout"},  # trend-following strategies correlate
    "breakout": {"trend", "breakout"},
    "mean_reversion": {"mean_reversion"},
    "momentum": {"momentum"},
    "volatility": {"volatility"},
    "liquidity": {"liquidity", "structure"},  # liquidity often tied to structure
    "structure": {"liquidity", "structure"},
}


def get_family(agent_id: str) -> str:
    return STRATEGY_FAMILY_MAP.get(agent_id, "unknown")


def are_families_correlated(fam_a: str, fam_b: str) -> bool:
    """Check if two families are correlated (not independent evidence)."""
    if fam_a == fam_b:
        return True
    correlated = CORRELATED_FAMILIES.get(fam_a, {fam_a})
    return fam_b in correlated


# =========================================================
# EVIDENCE CLASSIFICATION
# =========================================================

def classify_evidence(agent_result: AgentResult) -> str:
    """Classify an agent's result as supporting, conflicting, or unavailable."""
    if agent_result.status == AgentStatus.INSUFFICIENT_DATA:
        return "unavailable"
    if agent_result.status == AgentStatus.ERROR:
        return "unavailable"
    if agent_result.direction == "NEUTRAL" and agent_result.confidence < 0.2:
        return "unavailable"
    return "supporting"


def direction_weight(direction: str, opportunity_direction: str) -> int:
    """+1 for same direction, -1 for opposite, 0 for neutral."""
    if direction == opportunity_direction:
        return 1
    if direction in ("LONG", "SHORT") and direction != opportunity_direction:
        return -1
    return 0


# =========================================================
# OPPORTUNITY DETECTION
# =========================================================

def detect_opportunity(
    agent_results: list[AgentResult],
    symbol: str = "",
    timeframe: str = "",
    regime: str = "UNKNOWN",
    feature_snapshot_id: str = "",
) -> Opportunity:
    """Aggregate agent results into an Opportunity.

    Args:
        agent_results: List of AgentResult from strategy research agents
        symbol: Symbol being analyzed
        timeframe: Timeframe
        regime: Current market regime
        feature_snapshot_id: FeatureSnapshot cache key

    Returns:
        Opportunity with aggregated evidence, conflict analysis, thesis
    """
    now = datetime.now(timezone.utc).isoformat()

    # Filter to valid results
    valid_results = [r for r in agent_results if r.status not in (AgentStatus.ERROR,)]

    if not valid_results:
        return Opportunity(
            symbol=symbol,
            timeframe=timeframe,
            regime=regime,
            direction="UNKNOWN",
            status=OpportunityStatus.DETECTED,
            confidence=0.0,
            uncertainty=1.0,
            detected_at=now,
            feature_snapshot_id=feature_snapshot_id,
            market_context="No valid agent results",
            thesis="Insufficient research evidence — no agent results available.",
        )

    # --- Classify evidence ---
    supporting: list[AgentResult] = []
    conflicting: list[AgentResult] = []
    unavailable: list[AgentResult] = []

    for r in valid_results:
        classification = classify_evidence(r)
        if classification == "unavailable":
            unavailable.append(r)
        elif r.direction in ("LONG", "SHORT"):
            # Check if it conflicts with existing supporting
            if supporting and any(
                s.direction != r.direction for s in supporting
            ):
                # Check if this is a minority or majority
                same_dir = [s for s in supporting if s.direction == r.direction]
                opp_dir = [s for s in supporting if s.direction != r.direction]
                if len(same_dir) >= len(opp_dir):
                    supporting.append(r)
                else:
                    conflicting.append(r)
            else:
                supporting.append(r)
        else:
            # NEUTRAL or UNKNOWN — not supporting, not conflicting
            unavailable.append(r)

    # --- Determine opportunity direction ---
    long_count = sum(1 for r in supporting if r.direction == "LONG")
    short_count = sum(1 for r in supporting if r.direction == "SHORT")

    if long_count > short_count and long_count >= 2:
        opp_direction = "LONG"
    elif short_count > long_count and short_count >= 2:
        opp_direction = "SHORT"
    elif long_count == short_count and long_count > 0:
        opp_direction = "UNKNOWN"  # Conflict, no clear direction
    elif supporting:
        opp_direction = supporting[0].direction if supporting else "UNKNOWN"
    else:
        opp_direction = "UNKNOWN"

    # --- Strategy family diversity ---
    families_seen = set()
    independent_families = set()
    correlated_families = set()

    for r in supporting:
        fam = get_family(r.agent_id)
        families_seen.add(fam)

    # Check independence
    for fam in families_seen:
        is_independent = True
        for existing in independent_families:
            if are_families_correlated(fam, existing):
                is_independent = False
                correlated_families.add(fam)
                break
        if is_independent:
            independent_families.add(fam)

    # --- Confidence (evidence consistency, NOT win probability) ---
    # Based on: direction agreement, family independence, data quality,
    #            agent confidence, supporting agent ratio
    direction_agreement = 0.0
    if supporting:
        total = len(supporting)
        same_dir = max(long_count, short_count)
        direction_agreement = same_dir / total if total > 0 else 0.0

    family_factor = len(independent_families) / max(len(families_seen), 1)

    # Data quality average
    avg_quality = sum(r.data_quality for r in supporting) / max(len(supporting), 1)

    # Agent confidence average (observation strength, not win probability)
    avg_agent_confidence = sum(r.confidence for r in supporting) / max(len(supporting), 1)

    # Supporting ratio: how many of total agents support this direction
    supporting_ratio = len(supporting) / max(len(valid_results), 1)

    # Weighted confidence: agreement * independence * data_quality * agent_conf * ratio
    confidence = (direction_agreement * family_factor * avg_quality *
                  avg_agent_confidence * supporting_ratio)
    confidence = max(0.0, min(1.0, confidence))

    uncertainty = 1.0 - confidence

    # --- Build source agents ---
    source_agents = []
    for r in valid_results:
        fam = get_family(r.agent_id)
        source_agents.append(SourceAgent(
            agent_id=r.agent_id,
            agent_version=r.agent_version,
            direction=r.direction,
            confidence=r.confidence,
            thesis=r.reasoning[:200] if r.reasoning else "",
            evidence_count=len(r.evidence.items),
            supporting_features=r.supporting_features,
            conflicting_features=r.conflicting_features,
            required_features=r.engine_metadata.get("required_features", []),
            unavailable_features=r.engine_metadata.get("unavailable_features", []),
            strategy_family=fam,
            regime=r.regime,
            timestamp=r.timestamp,
            status=r.status.value,
        ))

    # --- Build evidence lists ---
    supporting_evidence = []
    conflicting_evidence = []
    unavailable_evidence = []

    for r in supporting:
        for item in r.evidence.items:
            supporting_evidence.append({
                "agent_id": r.agent_id,
                "feature": item.feature,
                "value": item.value,
                "direction": item.direction,
                "strength": item.strength,
                "source": item.source,
                "explanation": item.explanation,
            })

    for r in conflicting:
        for item in r.evidence.items:
            conflicting_evidence.append({
                "agent_id": r.agent_id,
                "feature": item.feature,
                "value": item.value,
                "direction": item.direction,
                "strength": item.strength,
                "source": item.source,
                "explanation": item.explanation,
            })

    for r in unavailable:
        for item in r.evidence.items:
            unavailable_evidence.append({
                "agent_id": r.agent_id,
                "feature": item.feature,
                "value": item.value,
                "direction": item.direction,
                "strength": item.strength,
                "source": item.source,
                "explanation": item.explanation,
            })

    # --- Market context summary ---
    market_context = _build_market_context(
        opp_direction, regime, supporting, conflicting, independent_families
    )

    # --- Thesis ---
    thesis = _generate_thesis(
        opp_direction, regime, supporting, conflicting, independent_families
    )

    # --- Status ---
    status = _determine_status(
        opp_direction, confidence, len(conflicting), len(unavailable)
    )

    return Opportunity(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime,
        direction=opp_direction,
        thesis=thesis,
        status=status,
        confidence=round(confidence, 3),
        uncertainty=round(uncertainty, 3),
        detected_at=now,
        last_updated_at=now,
        feature_snapshot_id=feature_snapshot_id,
        market_context=market_context,
        agent_results=[r.to_dict() if hasattr(r, 'to_dict') else _agent_result_dict(r) for r in valid_results],
        source_agents=source_agents,
        supporting_evidence=supporting_evidence,
        conflicting_evidence=conflicting_evidence,
        unavailable_evidence=unavailable_evidence,
        strategy_families=list(families_seen),
        strategy_count=len(valid_results),
        independent_families=len(independent_families),
        correlated_families=len(correlated_families),
    )


def _agent_result_dict(r: AgentResult) -> dict[str, Any]:
    """Serialize AgentResult to dict for Opportunity storage."""
    return {
        "agent_id": r.agent_id,
        "agent_version": r.agent_version,
        "direction": r.direction,
        "regime": r.regime,
        "confidence": r.confidence,
        "uncertainty": r.uncertainty,
        "status": r.status.value,
        "reasoning": r.reasoning,
        "invalidation_conditions": r.invalidation_conditions,
        "source_engine": r.source_engine,
        "engine_metadata": r.engine_metadata,
        "evidence_items": [
            {
                "feature": item.feature,
                "value": item.value,
                "direction": item.direction,
                "strength": item.strength,
                "source": item.source,
            }
            for item in r.evidence.items
        ],
        "claims": [
            {
                "statement": c.statement,
                "validation_status": c.validation_status.value,
            }
            for c in r.claims
        ],
    }


# =========================================================
# HELPER: Market Context
# =========================================================

def _build_market_context(
    direction: str,
    regime: str,
    supporting: list[AgentResult],
    conflicting: list[AgentResult],
    independent_families: set[str],
) -> str:
    parts = []
    parts.append(f"Regime: {regime}")
    parts.append(f"Direction consensus: {direction}")
    parts.append(f"Independent families: {len(independent_families)}")
    parts.append(f"Supporting agents: {len(supporting)}")
    if conflicting:
        parts.append(f"Conflicting agents: {len(conflicting)}")
    return "; ".join(parts)


# =========================================================
# HELPER: Thesis Generation (deterministic template)
# =========================================================

def _generate_thesis(
    direction: str,
    regime: str,
    supporting: list[AgentResult],
    conflicting: list[AgentResult],
    independent_families: set[str],
) -> str:
    """Generate deterministic research-oriented thesis."""

    if direction == "UNKNOWN" and not supporting:
        return "Insufficient research evidence for directional thesis."

    parts = []

    # Direction context
    dir_text = direction.lower()
    parts.append(f"Research agents detect {dir_text}-oriented market context")

    # Regime
    if regime and regime != "UNKNOWN":
        parts.append(f"under {regime.lower()} regime")

    # Independent evidence
    if independent_families:
        families_str = ", ".join(sorted(independent_families))
        parts.append(f"from {len(independent_families)} independent strategy family/families ({families_str})")

    # Supporting count
    parts.append(f"({len(supporting)} supporting agent(s)")

    # Conflicting
    if conflicting:
        parts.append(f", {len(conflicting)} conflicting")

    parts.append(")")

    # Uncertainty note
    parts.append("Evidence-based observation, not a trade recommendation.")

    return " ".join(parts)


# =========================================================
# HELPER: Status Determination
# =========================================================

def _determine_status(
    direction: str,
    confidence: float,
    conflict_count: int,
    unavailable_count: int,
) -> str:
    """Determine opportunity lifecycle status."""
    if direction == "UNKNOWN":
        return OpportunityStatus.DETECTED.value
    if conflict_count >= 2:
        return OpportunityStatus.UNDER_REVIEW.value
    if confidence < 0.2:
        return OpportunityStatus.UNDER_REVIEW.value
    if unavailable_count >= 3:
        return OpportunityStatus.UNDER_REVIEW.value
    return OpportunityStatus.DETECTED.value


# =========================================================
# LIFECYCLE MANAGEMENT
# =========================================================

def validate_opportunity(
    opp: Opportunity,
    min_independent_families: int = 2,
    min_confidence: float = 0.15,
) -> Opportunity:
    """Validate an opportunity against research criteria.

    VALIDATED ≠ trade will succeed.
    Only means research validation criteria are met.
    """
    now = datetime.now(timezone.utc).isoformat()

    if opp.direction == "UNKNOWN":
        opp.status = OpportunityStatus.DETECTED.value
        return opp

    if opp.independent_families >= min_independent_families and opp.confidence >= min_confidence:
        opp.status = OpportunityStatus.VALIDATED.value
        opp.validated_at = now
    else:
        opp.status = OpportunityStatus.UNDER_REVIEW.value

    opp.last_updated_at = now
    return opp


def invalidate_opportunity(
    opp: Opportunity,
    reason: str = "Market conditions changed",
) -> Opportunity:
    """Mark opportunity as invalidated."""
    opp.status = OpportunityStatus.INVALIDATED.value
    opp.invalidation_reason = reason
    opp.invalidated_at = datetime.now(timezone.utc).isoformat()
    opp.last_updated_at = opp.invalidated_at
    return opp


def expire_opportunity(
    opp: Opportunity,
    reason: str = "Time window expired",
) -> Opportunity:
    """Mark opportunity as expired."""
    opp.status = OpportunityStatus.EXPIRED.value
    opp.expiry_reason = reason
    opp.expired_at = datetime.now(timezone.utc).isoformat()
    opp.last_updated_at = opp.expired_at
    return opp


def archive_opportunity(opp: Opportunity) -> Opportunity:
    """Archive a completed opportunity."""
    opp.status = OpportunityStatus.ARCHIVED.value
    opp.last_updated_at = datetime.now(timezone.utc).isoformat()
    return opp


# =========================================================
# DEDUPLICATION
# =========================================================

OPPORTUNITY_THRESHOLD = {
    "symbol": True,
    "timeframe": True,
    "direction": True,
    "regime": True,
    "confidence_delta": 0.3,  # Within 0.3 confidence → same opportunity
}


def is_duplicate_opportunity(
    new_opp: Opportunity,
    existing_opps: list[Opportunity],
) -> tuple[bool, str | None]:
    """Check if new opportunity is a duplicate of an existing one.

    Returns (is_duplicate, existing_opportunity_id_or_None).

    Same symbol + timeframe + direction + similar confidence + same regime
    → duplicate (update existing instead of creating new).
    """
    for existing in existing_opps:
        if existing.status in (OpportunityStatus.ARCHIVED.value, OpportunityStatus.EXPIRED.value):
            continue

        if (existing.symbol == new_opp.symbol and
            existing.timeframe == new_opp.timeframe and
            existing.direction == new_opp.direction and
            existing.regime == new_opp.regime):

            conf_delta = abs(existing.confidence - new_opp.confidence)
            if conf_delta <= OPPORTUNITY_THRESHOLD["confidence_delta"]:
                return True, existing.opportunity_id

    return False, None


# =========================================================
# SETUP CANDIDATE GENERATION
# =========================================================

def generate_setup_candidate(
    opp: Opportunity,
) -> SetupCandidate:
    """Generate a research-backed setup candidate from an opportunity.

    Entry/invalidation/target are CANDIDATES, not confirmed levels.
    Requires Phase F (Research-Backed Signal/Setup Engine) for confirmation.
    """
    now = datetime.now(timezone.utc).isoformat()

    return SetupCandidate(
        opportunity_id=opp.opportunity_id,
        symbol=opp.symbol,
        timeframe=opp.timeframe,
        direction=opp.direction,
        regime=opp.regime,
        thesis=opp.thesis,
        supporting_evidence=opp.supporting_evidence[:5],  # Top 5
        conflicting_evidence=opp.conflicting_evidence[:3],  # Top 3
        uncertainty=opp.uncertainty,
        status="CANDIDATE",
        detected_at=now,
        updated_at=now,
    )


# =========================================================
# BATCH DETECTION
# =========================================================

def detect_all_opportunities(
    symbol: str,
    timeframe: str,
    regime: str = "UNKNOWN",
    feature_snapshot_id: str = "",
) -> list[Opportunity]:
    """Run all strategy agents and detect opportunities.

    Convenience function for full pipeline execution.
    """
    registry = get_strategy_registry()
    from agent_runtime import AgentRuntime
    runtime = AgentRuntime(registry=registry)

    # Run all agents
    agent_ids = list(STRATEGY_AGENTS.keys())
    runs = runtime.run_multiple(agent_ids, symbol, timeframe)

    # Collect results
    agent_results = []
    for run in runs:
        if run.result:
            agent_results.append(run.result)

    # Detect opportunity
    opp = detect_opportunity(
        agent_results=agent_results,
        symbol=symbol,
        timeframe=timeframe,
        regime=regime,
        feature_snapshot_id=feature_snapshot_id,
    )

    return [opp]