# -*- coding: utf-8 -*-
"""Phase H — Research Intelligence Models.

Core models for MarketHQ's research intelligence system.

Flow:
  Observation
    → Hypothesis
      → Experiment
        → Result
          → Claim
            → ResearchMemory

All research-only. No trading. No auto promotion.
No live execution. Offline learning only.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ObservationType(Enum):
    OBSERVATION = "observation"
    PATTERN = "pattern"
    FAILURE = "failure"
    SUCCESS_PATTERN = "success_pattern"
    CLAIM = "claim"
    COUNTEREXAMPLE = "counterexample"
    DATA_QUALITY = "data_quality"
    REGIME_PATTERN = "regime_pattern"
    STRATEGY_PATTERN = "strategy_pattern"


class ClaimStatus(Enum):
    UNTESTED = "untested"
    TESTED = "tested"
    SUPPORTED = "supported"
    UNSTABLE = "unstable"
    REJECTED = "rejected"


class HypothesisStatus(Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    UNSTABLE = "unstable"
    REJECTED = "rejected"


class ExperimentStatus(Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REPRODUCED = "reproduced"


class WeightProposalStatus(Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    ACCEPTED_FOR_RESEARCH = "accepted_for_research"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class ReviewStatus(Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    ACCEPTED_FOR_RESEARCH = "accepted_for_research"
    REJECTED = "rejected"
    NEEDS_MORE_DATA = "needs_more_data"


@dataclass
class Observation:
    """A single research observation from historical data."""
    observation_id: str
    observation_type: ObservationType
    text: str
    context: dict[str, Any] = field(default_factory=dict)
    regime: str = "UNKNOWN"
    asset: str = ""
    timeframe: str = ""
    sample_size: int = 0
    validation_windows: list[str] = field(default_factory=list)
    reliability: float = 0.0
    status: ClaimStatus = ClaimStatus.UNTESTED
    source_agent: str = ""
    evidence_trace: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "observation_type": self.observation_type.value,
            "text": self.text,
            "context": self.context,
            "regime": self.regime,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "sample_size": self.sample_size,
            "validation_windows": self.validation_windows,
            "reliability": self.reliability,
            "status": self.status.value,
            "source_agent": self.source_agent,
            "evidence_trace": self.evidence_trace,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Hypothesis:
    """A research hypothesis derived from observations."""
    hypothesis_id: str
    text: str
    observation_ids: list[str] = field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    confidence: float = 0.0
    experiment_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "text": self.text,
            "observation_ids": self.observation_ids,
            "status": self.status.value,
            "confidence": self.confidence,
            "experiment_ids": self.experiment_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Experiment:
    """A research experiment to test a hypothesis."""
    experiment_id: str
    hypothesis_id: str
    description: str
    config: dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.REGISTERED
    result_summary: dict[str, Any] = field(default_factory=dict)
    experiment_hash: str = ""
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "config": self.config,
            "status": self.status.value,
            "result_summary": self.result_summary,
            "experiment_hash": self.experiment_hash,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Result:
    """A single experiment result."""
    result_id: str
    experiment_id: str
    metrics: dict[str, Any] = field(default_factory=dict)
    window_id: str = ""
    sample_size: int = 0
    effect_size: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    stability_score: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "experiment_id": self.experiment_id,
            "metrics": self.metrics,
            "window_id": self.window_id,
            "sample_size": self.sample_size,
            "effect_size": self.effect_size,
            "confidence_interval": self.confidence_interval,
            "stability_score": self.stability_score,
            "created_at": self.created_at,
        }


@dataclass
class Claim:
    """A research claim with full traceability and status."""
    claim_id: str
    text: str
    status: ClaimStatus = ClaimStatus.UNTESTED
    evidence: list[str] = field(default_factory=list)
    sample_size: int = 0
    validation_windows: list[str] = field(default_factory=list)
    first_observed: str = ""
    last_validated: str = ""
    confidence: float = 0.0
    stability: float = 0.0
    effect_size: float = 0.0
    limitations: list[str] = field(default_factory=list)
    version: int = 1
    parent_claim_id: str = ""
    observation_ids: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "status": self.status.value,
            "evidence": self.evidence,
            "sample_size": self.sample_size,
            "validation_windows": self.validation_windows,
            "first_observed": self.first_observed,
            "last_validated": self.last_validated,
            "confidence": self.confidence,
            "stability": self.stability,
            "effect_size": self.effect_size,
            "limitations": self.limitations,
            "version": self.version,
            "parent_claim_id": self.parent_claim_id,
            "observation_ids": self.observation_ids,
            "experiment_ids": self.experiment_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Evidence:
    """A piece of evidence supporting or contradicting a claim."""
    evidence_id: str
    claim_id: str
    text: str
    evidence_type: str = "supporting"  # supporting | contradicting | neutral
    source: str = ""
    sample_size: int = 0
    window_id: str = ""
    reliability: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "claim_id": self.claim_id,
            "text": self.text,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "sample_size": self.sample_size,
            "window_id": self.window_id,
            "reliability": self.reliability,
            "created_at": self.created_at,
        }


@dataclass
class ResearchMemory:
    """Persistent research memory entry."""
    memory_id: str
    memory_type: ObservationType
    observation: str
    claim_id: str = ""
    evidence: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    regime: str = "UNKNOWN"
    asset: str = ""
    timeframe: str = ""
    sample_size: int = 0
    validation_windows: list[str] = field(default_factory=list)
    reliability: float = 0.0
    status: ClaimStatus = ClaimStatus.UNTESTED
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "observation": self.observation,
            "claim_id": self.claim_id,
            "evidence": self.evidence,
            "context": self.context,
            "regime": self.regime,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "sample_size": self.sample_size,
            "validation_windows": self.validation_windows,
            "reliability": self.reliability,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ReliabilityProfile:
    """Historical reliability profile for an agent or strategy."""
    profile_id: str
    name: str
    profile_type: str = "agent"  # agent | strategy | strategy_family
    family: str = ""
    regime: str = "UNKNOWN"
    timeframe: str = ""
    asset: str = ""
    direction_agreement: float = 0.0
    outcome_correlation: float = 0.0
    target_hit_rate: float = 0.0
    invalidation_rate: float = 0.0
    avg_realized_r: float = 0.0
    median_realized_r: float = 0.0
    sample_size: int = 0
    stability_score: float = 0.0
    temporal_stability: float = 0.0
    regime_specific: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "profile_type": self.profile_type,
            "family": self.family,
            "regime": self.regime,
            "timeframe": self.timeframe,
            "asset": self.asset,
            "direction_agreement": self.direction_agreement,
            "outcome_correlation": self.outcome_correlation,
            "target_hit_rate": self.target_hit_rate,
            "invalidation_rate": self.invalidation_rate,
            "avg_realized_r": self.avg_realized_r,
            "median_realized_r": self.median_realized_r,
            "sample_size": self.sample_size,
            "stability_score": self.stability_score,
            "temporal_stability": self.temporal_stability,
            "regime_specific": self.regime_specific,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class CalibrationProfile:
    """Calibration profile for confidence or quality scores."""
    profile_id: str
    name: str
    bucket_type: str = "confidence"  # confidence | quality
    buckets: list[dict[str, Any]] = field(default_factory=list)
    calibration_score: float = 0.0
    sample_size: int = 0
    regime_specific: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "bucket_type": self.bucket_type,
            "buckets": self.buckets,
            "calibration_score": self.calibration_score,
            "sample_size": self.sample_size,
            "regime_specific": self.regime_specific,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class FeatureImportance:
    """Feature importance analysis result."""
    feature_name: str
    importance_score: float = 0.0
    method: str = "correlation"  # correlation | permutation | rank
    direction: str = "unknown"  # positive | negative | unknown
    regime: str = "UNKNOWN"
    strategy: str = ""
    timeframe: str = ""
    asset: str = ""
    sample_size: int = 0
    stability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "importance_score": self.importance_score,
            "method": self.method,
            "direction": self.direction,
            "regime": self.regime,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "asset": self.asset,
            "sample_size": self.sample_size,
            "stability": self.stability,
        }


@dataclass
class WeightProposal:
    """A proposed weight change — OFFLINE only, not active."""
    proposal_id: str
    weight_name: str
    current_value: float = 0.0
    proposed_value: float = 0.0
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    walk_forward_windows: list[str] = field(default_factory=list)
    baseline_comparison: dict[str, Any] = field(default_factory=dict)
    status: WeightProposalStatus = WeightProposalStatus.PROPOSED
    previous_adaptive_v1_comparison: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "weight_name": self.weight_name,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "reason": self.reason,
            "evidence": self.evidence,
            "walk_forward_windows": self.walk_forward_windows,
            "baseline_comparison": self.baseline_comparison,
            "status": self.status.value,
            "previous_adaptive_v1_comparison": self.previous_adaptive_v1_comparison,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SimilarityMatch:
    """A historical setup similar to a new setup."""
    similarity_id: str
    setup_id: str
    matched_dimensions: list[str] = field(default_factory=list)
    mismatched_dimensions: list[str] = field(default_factory=list)
    similarity_score: float = 0.0
    historical_outcome: str = ""
    realized_r: float = 0.0
    regime: str = ""
    window_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "similarity_id": self.similarity_id,
            "setup_id": self.setup_id,
            "matched_dimensions": self.matched_dimensions,
            "mismatched_dimensions": self.mismatched_dimensions,
            "similarity_score": self.similarity_score,
            "historical_outcome": self.historical_outcome,
            "realized_r": self.realized_r,
            "regime": self.regime,
            "window_id": self.window_id,
        }


@dataclass
class FailurePattern:
    """A pattern of setup failures."""
    pattern_id: str
    description: str
    conditions: dict[str, Any] = field(default_factory=dict)
    sample_size: int = 0
    outcome: str = ""
    recurrence: float = 0.0
    regimes: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "conditions": self.conditions,
            "sample_size": self.sample_size,
            "outcome": self.outcome,
            "recurrence": self.recurrence,
            "regimes": self.regimes,
            "strategies": self.strategies,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "created_at": self.created_at,
        }


@dataclass
class Counterexample:
    """A historical case that contradicts a claim."""
    counterexample_id: str
    claim_id: str
    description: str
    conditions: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    realized_r: float = 0.0
    regime: str = ""
    sample_size: int = 0
    evidence: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "counterexample_id": self.counterexample_id,
            "claim_id": self.claim_id,
            "description": self.description,
            "conditions": self.conditions,
            "outcome": self.outcome,
            "realized_r": self.realized_r,
            "regime": self.regime,
            "sample_size": self.sample_size,
            "evidence": self.evidence,
            "created_at": self.created_at,
        }


@dataclass
class ExperimentRegistry:
    """Registry of research experiments."""
    experiment_id: str
    hypothesis: str
    dataset: str = ""
    cutoff_policy: str = ""
    train_windows: list[str] = field(default_factory=list)
    validation_windows: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    baseline: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.REGISTERED
    experiment_hash: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "dataset": self.dataset,
            "cutoff_policy": self.cutoff_policy,
            "train_windows": self.train_windows,
            "validation_windows": self.validation_windows,
            "features": self.features,
            "config": self.config,
            "baseline": self.baseline,
            "result": self.result,
            "status": self.status.value,
            "experiment_hash": self.experiment_hash,
            "created_at": self.created_at,
        }


# ── Phase J5 Extensions ────────────────────────────────────

class TestingMode(Enum):
    EXPLORATORY = "exploratory"
    CONFIRMATORY = "confirmatory"


@dataclass
class RegimeTransition:
    """Regime transition memory entry for J5."""
    transition_id: str = ""
    previous_regime: str = ""
    new_regime: str = ""
    transition_type: str = "unknown"
    symbol: str = ""
    timeframe: str = ""
    transition_context: dict[str, Any] = field(default_factory=dict)
    historical_frequency: int = 0
    historical_outcomes: list[str] = field(default_factory=list)
    research_findings: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    sample_size: int = 0
    confidence: float = 0.0
    detected_at: str = ""
    created_at: str = ""
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "previous_regime": self.previous_regime,
            "new_regime": self.new_regime,
            "transition_type": self.transition_type,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "transition_context": self.transition_context,
            "historical_frequency": self.historical_frequency,
            "historical_outcomes": self.historical_outcomes,
            "research_findings": self.research_findings,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
            "detected_at": self.detected_at,
            "created_at": self.created_at,
            "provenance": self.provenance,
        }


@dataclass
class OpportunityRecurrence:
    """Tracks recurrence of similar opportunity contexts."""
    recurrence_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    regime: str = ""
    structure: str = ""
    opportunity_type: str = ""
    historical_count: int = 0
    historical_outcomes: list[str] = field(default_factory=list)
    avg_realized_r: float = 0.0
    last_seen: str = ""
    created_at: str = ""
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recurrence_id": self.recurrence_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "structure": self.structure,
            "opportunity_type": self.opportunity_type,
            "historical_count": self.historical_count,
            "historical_outcomes": self.historical_outcomes,
            "avg_realized_r": self.avg_realized_r,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
            "provenance": self.provenance,
        }