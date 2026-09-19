# -*- coding: utf-8 -*-
"""Opportunity Engine — Phase E.

Research-only opportunity aggregation on top of Phase D strategy research agents.

Flow:
  AgentResults (7 strategy agents)
      ↓
  Opportunity Detection (correlation-aware aggregation)
      ↓
  Opportunity (structured opportunity context)
      ↓
  Setup Candidate (research-backed, NOT trade recommendation)
      ↓
  Brain Observation Bridge

No broker, no orders, no trading, no live execution.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_contract import AgentResult, AgentStatus, Claim, ClaimStatus, Evidence, EvidenceItem


# =========================================================
# ENUMS
# =========================================================

class OpportunityStatus(str, Enum):
    DETECTED = "DETECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    VALIDATED = "VALIDATED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


# =========================================================
# SOURCE AGENT RECORD
# =========================================================

@dataclass
class SourceAgent:
    """One agent's contribution to an opportunity."""
    agent_id: str = ""
    agent_version: str = "1.0"
    direction: str = "NEUTRAL"
    confidence: float = 0.0
    thesis: str = ""
    evidence_count: int = 0
    supporting_features: list[str] = field(default_factory=list)
    conflicting_features: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)
    unavailable_features: list[str] = field(default_factory=list)
    strategy_family: str = ""
    regime: str = "UNKNOWN"
    timestamp: str = ""
    status: str = "SUCCESS"


# =========================================================
# OPPORTUNITY MODEL
# =========================================================

@dataclass
class Opportunity:
    """Aggregated market opportunity from multiple strategy research agents.

    Research-only — NOT a trade recommendation.
    Confidence = evidence consistency, NOT win probability.
    """
    opportunity_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    detected_at: str = ""
    market_context: str = ""  # human-readable context summary
    regime: str = "UNKNOWN"
    direction: str = "UNKNOWN"
    thesis: str = ""
    status: str = OpportunityStatus.DETECTED
    confidence: float = 0.0
    uncertainty: float = 1.0

    # Agent results aggregation
    agent_results: list[dict[str, Any]] = field(default_factory=list)
    source_agents: list[SourceAgent] = field(default_factory=list)

    # Evidence breakdown
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    unavailable_evidence: list[dict[str, Any]] = field(default_factory=list)

    # Strategy family diversity
    strategy_families: list[str] = field(default_factory=list)
    strategy_count: int = 0
    independent_families: int = 0
    correlated_families: int = 0

    # Feature snapshot reference
    feature_snapshot_id: str = ""

    # Lifecycle timestamps
    first_detected_at: str = ""
    last_updated_at: str = ""
    validated_at: str = ""
    invalidated_at: str = ""
    expired_at: str = ""

    # Invalidation / expiry
    invalidation_reason: str = ""
    expiry_reason: str = ""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Setup candidate reference (Phase F)
    setup_candidate_id: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.opportunity_id:
            self.opportunity_id = f"OPP-{uuid.uuid4().hex[:10].upper()}"
        if not self.detected_at:
            self.detected_at = now
        if not self.first_detected_at:
            self.first_detected_at = now
        if not self.last_updated_at:
            self.last_updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "detected_at": self.detected_at,
            "market_context": self.market_context,
            "regime": self.regime,
            "direction": self.direction,
            "thesis": self.thesis,
            "status": self.status,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "agent_results": self.agent_results,
            "source_agents": [
                {
                    "agent_id": sa.agent_id,
                    "agent_version": sa.agent_version,
                    "direction": sa.direction,
                    "confidence": sa.confidence,
                    "thesis": sa.thesis,
                    "evidence_count": sa.evidence_count,
                    "supporting_features": sa.supporting_features,
                    "conflicting_features": sa.conflicting_features,
                    "required_features": sa.required_features,
                    "unavailable_features": sa.unavailable_features,
                    "strategy_family": sa.strategy_family,
                    "regime": sa.regime,
                    "timestamp": sa.timestamp,
                    "status": sa.status,
                }
                for sa in self.source_agents
            ],
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "unavailable_evidence": self.unavailable_evidence,
            "strategy_families": self.strategy_families,
            "strategy_count": self.strategy_count,
            "independent_families": self.independent_families,
            "correlated_families": self.correlated_families,
            "feature_snapshot_id": self.feature_snapshot_id,
            "first_detected_at": self.first_detected_at,
            "last_updated_at": self.last_updated_at,
            "validated_at": self.validated_at,
            "invalidated_at": self.invalidated_at,
            "expired_at": self.expired_at,
            "invalidation_reason": self.invalidation_reason,
            "expiry_reason": self.expiry_reason,
            "metadata": self.metadata,
            "setup_candidate_id": self.setup_candidate_id,
        }


# =========================================================
# SETUP CANDIDATE (reference for Phase F)
# =========================================================

@dataclass
class SetupCandidate:
    """Research-backed setup candidate — NOT a trade recommendation.

    Entry/invalidation/target are CANDIDATES, not confirmed levels.
    Historical validation required before any confidence claim.
    """
    candidate_id: str = ""
    opportunity_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    direction: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    thesis: str = ""

    candidate_entry_zone: dict[str, float] = field(default_factory=dict)
    invalidation_candidate: dict[str, float] = field(default_factory=dict)
    target_candidate: dict[str, float] = field(default_factory=dict)

    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    historical_evidence_reference: str = ""
    quality_reference: str = ""
    uncertainty: float = 1.0
    status: str = "CANDIDATE"

    detected_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.candidate_id:
            self.candidate_id = f"CAND-{uuid.uuid4().hex[:10].upper()}"
        if not self.detected_at:
            self.detected_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "regime": self.regime,
            "thesis": self.thesis,
            "candidate_entry_zone": self.candidate_entry_zone,
            "invalidation_candidate": self.invalidation_candidate,
            "target_candidate": self.target_candidate,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "historical_evidence_reference": self.historical_evidence_reference,
            "quality_reference": self.quality_reference,
            "uncertainty": self.uncertainty,
            "status": self.status,
            "detected_at": self.detected_at,
            "updated_at": self.updated_at,
        }


# =========================================================
# PHASE F — RESEARCH-BACKED SETUP
# =========================================================

class SetupStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED_RESEARCH_SETUP = "CONFIRMED_RESEARCH_SETUP"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class UncertaintyType(str, Enum):
    MISSING_VOLUME = "missing_volume"
    MISSING_STRUCTURE = "missing_structure"
    LOW_SAMPLE = "low_sample"
    REGIME_INSTABILITY = "regime_instability"
    CONFLICTING_AGENTS = "conflicting_agents"
    INSUFFICIENT_HISTORY = "insufficient_history"
    FEATURE_UNAVAILABLE = "feature_unavailable"
    WEAK_ENTRY_GEOMETRY = "weak_entry_geometry"
    WEAK_TARGET_GEOMETRY = "weak_target_geometry"


@dataclass
class UncertaintyFlag:
    """A specific uncertainty affecting a research-backed setup."""
    type: UncertaintyType = UncertaintyType.MISSING_VOLUME
    description: str = ""
    severity: str = "medium"  # low, medium, high, critical
    feature: str = ""  # which feature is missing/unreliable

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, UncertaintyType) else str(self.type),
            "description": self.description,
            "severity": self.severity,
            "feature": self.feature,
        }


@dataclass
class EvidenceTrace:
    """Traceability link from setup assertion back to source."""
    assertion: str = ""
    source_agent: str = ""
    agent_run_id: str = ""
    feature_snapshot_id: str = ""
    timestamp: str = ""
    evidence_feature: str = ""
    evidence_value: float = 0.0
    evidence_direction: str = "NEUTRAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion": self.assertion,
            "source_agent": self.source_agent,
            "agent_run_id": self.agent_run_id,
            "feature_snapshot_id": self.feature_snapshot_id,
            "timestamp": self.timestamp,
            "evidence_feature": self.evidence_feature,
            "evidence_value": self.evidence_value,
            "evidence_direction": self.evidence_direction,
        }


@dataclass
class ResearchBackedSetup:
    """Research-backed setup candidate derived from an Opportunity.

    NOT a trade recommendation. Entry/invalidation/target are CANDIDATES.
    Historical validation required before any confidence claim.

    Flow:
      Opportunity → ResearchBackedSetup → Brain Observation → Human Review
    """
    setup_id: str = ""
    opportunity_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    detected_at: str = ""
    direction: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    setup_type: str = ""
    strategy_family: str = ""
    thesis: str = ""

    # Entry
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    entry_reference: float | None = None
    entry_method: str = ""
    entry_confirmation: list[str] = field(default_factory=list)
    entry_status: str = "UNAVAILABLE"  # AVAILABLE / UNAVAILABLE / PARTIAL

    # Invalidation
    invalidation_price: float | None = None
    invalidation_type: str = ""
    invalidation_reason: str = ""
    invalidation_distance_atr: float = 0.0

    # Targets
    target_1: float | None = None
    target_2: float | None = None
    target_3: float | None = None
    target_method: str = ""

    # Risk / Reward
    stop_distance: float = 0.0
    target_distance_1: float = 0.0
    target_distance_2: float = 0.0
    target_distance_3: float = 0.0
    rr_to_t1: float | None = None
    rr_to_t2: float | None = None
    rr_to_t3: float | None = None

    # Evidence
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    historical_evidence: dict[str, Any] = field(default_factory=dict)
    structure_evidence: dict[str, Any] = field(default_factory=dict)
    regime_evidence: dict[str, Any] = field(default_factory=dict)
    momentum_evidence: dict[str, Any] = field(default_factory=dict)
    liquidity_evidence: dict[str, Any] = field(default_factory=dict)
    volatility_evidence: dict[str, Any] = field(default_factory=dict)

    # Uncertainty
    uncertainty_flags: list[UncertaintyFlag] = field(default_factory=list)
    overall_uncertainty: float = 1.0

    # Meta
    quality_reference: str = ""
    confidence: float = 0.0  # research confidence, NOT win probability
    uncertainty: float = 1.0
    data_availability: float = 0.0  # 0..1, how much data is available
    source_agents: list[dict[str, Any]] = field(default_factory=list)
    evidence_traces: list[EvidenceTrace] = field(default_factory=list)
    feature_snapshot_id: str = ""
    created_at: str = ""
    expires_at: str = ""
    status: str = SetupStatus.CANDIDATE

    # WHY panel
    why_panel: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.setup_id:
            self.setup_id = f"SETUP-{uuid.uuid4().hex[:10].upper()}"
        if not self.detected_at:
            self.detected_at = now
        if not self.created_at:
            self.created_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_id": self.setup_id,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "detected_at": self.detected_at,
            "direction": self.direction,
            "regime": self.regime,
            "setup_type": self.setup_type,
            "strategy_family": self.strategy_family,
            "thesis": self.thesis,
            "entry_zone_low": self.entry_zone_low,
            "entry_zone_high": self.entry_zone_high,
            "entry_reference": self.entry_reference,
            "entry_method": self.entry_method,
            "entry_confirmation": self.entry_confirmation,
            "entry_status": self.entry_status,
            "invalidation_price": self.invalidation_price,
            "invalidation_type": self.invalidation_type,
            "invalidation_reason": self.invalidation_reason,
            "invalidation_distance_atr": self.invalidation_distance_atr,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "target_3": self.target_3,
            "target_method": self.target_method,
            "stop_distance": self.stop_distance,
            "target_distance_1": self.target_distance_1,
            "target_distance_2": self.target_distance_2,
            "target_distance_3": self.target_distance_3,
            "rr_to_t1": self.rr_to_t1,
            "rr_to_t2": self.rr_to_t2,
            "rr_to_t3": self.rr_to_t3,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "historical_evidence": self.historical_evidence,
            "structure_evidence": self.structure_evidence,
            "regime_evidence": self.regime_evidence,
            "momentum_evidence": self.momentum_evidence,
            "liquidity_evidence": self.liquidity_evidence,
            "volatility_evidence": self.volatility_evidence,
            "uncertainty_flags": [uf.to_dict() for uf in self.uncertainty_flags],
            "overall_uncertainty": self.overall_uncertainty,
            "quality_reference": self.quality_reference,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "data_availability": self.data_availability,
            "source_agents": self.source_agents,
            "evidence_traces": [et.to_dict() for et in self.evidence_traces],
            "feature_snapshot_id": self.feature_snapshot_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "why_panel": self.why_panel,
        }

    def freeze(self) -> dict[str, Any]:
        """Capture setup geometry at cutoff time.

        Returns immutable snapshot of entry/invalidation/target geometry.
        Future bars should not change this — only outcome replay uses them.
        """
        return {
            "entry_zone_low": self.entry_zone_low,
            "entry_zone_high": self.entry_zone_high,
            "entry_reference": self.entry_reference,
            "invalidation_price": self.invalidation_price,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "target_3": self.target_3,
            "direction": self.direction,
            "entry_method": self.entry_method,
            "target_method": self.target_method,
            "invalidation_type": self.invalidation_type,
        }