# -*- coding: utf-8 -*-
"""Phase J6 — Production-Grade Intelligence State.

Extends J5 IntelligenceState with J6 fields:
- current market observation
- active regime
- regime transitions
- detected opportunities
- active research runs
- recent outcomes
- research memory
- failure memory
- counterexamples
- claim status
- agent reliability
- strategy-family reliability
- drift state
- data quality
- uncertainty
- pending research
- human review state
- last successful research cycle
- next recommended research action

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class IntelligenceState(Enum):
    INITIALIZING = "INITIALIZING"
    OBSERVING = "OBSERVING"
    STABLE = "STABLE"
    CHANGE_DETECTED = "CHANGE_DETECTED"
    RESEARCHING = "RESEARCHING"
    VALIDATING = "VALIDATING"
    LEARNING = "LEARNING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    STALE = "STALE"


VALID_TRANSITIONS: dict[IntelligenceState, list[IntelligenceState]] = {
    IntelligenceState.INITIALIZING: [
        IntelligenceState.OBSERVING,
        IntelligenceState.ERROR,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.OBSERVING: [
        IntelligenceState.STABLE,
        IntelligenceState.CHANGE_DETECTED,
        IntelligenceState.ERROR,
        IntelligenceState.PAUSED,
        IntelligenceState.STALE,
    ],
    IntelligenceState.STABLE: [
        IntelligenceState.OBSERVING,
        IntelligenceState.CHANGE_DETECTED,
        IntelligenceState.RESEARCHING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.STALE,
    ],
    IntelligenceState.CHANGE_DETECTED: [
        IntelligenceState.RESEARCHING,
        IntelligenceState.OBSERVING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.RESEARCHING: [
        IntelligenceState.VALIDATING,
        IntelligenceState.LEARNING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.VALIDATING: [
        IntelligenceState.LEARNING,
        IntelligenceState.RESEARCHING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.LEARNING: [
        IntelligenceState.STABLE,
        IntelligenceState.OBSERVING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.HUMAN_REVIEW: [
        IntelligenceState.RESEARCHING,
        IntelligenceState.LEARNING,
        IntelligenceState.STABLE,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.PAUSED: [
        IntelligenceState.OBSERVING,
        IntelligenceState.INITIALIZING,
        IntelligenceState.RESEARCHING,
    ],
    IntelligenceState.ERROR: [
        IntelligenceState.INITIALIZING,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.STALE: [
        IntelligenceState.OBSERVING,
        IntelligenceState.RESEARCHING,
        IntelligenceState.PAUSED,
    ],
}


@dataclass
class IntelligenceStateChange:
    timestamp: str
    from_state: IntelligenceState
    to_state: IntelligenceState
    cycle_id: str
    reason: str
    provenance: str
    context_version: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "cycle_id": self.cycle_id,
            "reason": self.reason,
            "provenance": self.provenance,
            "context_version": self.context_version,
            "metadata": self.metadata,
        }


@dataclass
class IntelligenceStateRecord:
    state: IntelligenceState
    cycle_id: str
    entered_at: str
    reason: str
    provenance: str
    context_version: int
    last_transition: IntelligenceStateChange | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "cycle_id": self.cycle_id,
            "entered_at": self.entered_at,
            "reason": self.reason,
            "provenance": self.provenance,
            "context_version": self.context_version,
            "last_transition": (
                self.last_transition.to_dict() if self.last_transition else None
            ),
            "metadata": self.metadata,
        }


@dataclass
class AgentReliabilityProfile:
    """Tracks research reliability per agent (separate from health).

    Health = "Can it execute?"
    Reliability = "How useful/accurate has its research historically been?"
    """
    agent_id: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    unavailable_results: int = 0
    useful_evidence_count: int = 0
    contradicted_evidence_count: int = 0
    outcome_alignment_score: float = 0.0  # 0-1
    regime_specific_reliability: dict[str, float] = field(default_factory=dict)
    timeframe_specific_reliability: dict[str, float] = field(default_factory=dict)
    symbol_specific_reliability: dict[str, float] = field(default_factory=dict)
    drift_detected: bool = False
    last_updated: str = ""

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def reliability_score(self) -> float:
        """Composite reliability score (0-1)."""
        if self.total_executions == 0:
            return 0.0
        w_useful = 0.3
        w_contradicted = 0.3
        w_alignment = 0.4
        useful_ratio = self.useful_evidence_count / max(
            self.useful_evidence_count + self.contradicted_evidence_count, 1
        )
        return (
            w_useful * useful_ratio
            + w_contradicted * (1 - min(self.contradicted_evidence_count / max(self.total_executions, 1), 1))
            + w_alignment * self.outcome_alignment_score
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "unavailable_results": self.unavailable_results,
            "useful_evidence_count": self.useful_evidence_count,
            "contradicted_evidence_count": self.contradicted_evidence_count,
            "outcome_alignment_score": self.outcome_alignment_score,
            "success_rate": self.success_rate,
            "reliability_score": self.reliability_score,
            "regime_specific_reliability": self.regime_specific_reliability,
            "timeframe_specific_reliability": self.timeframe_specific_reliability,
            "symbol_specific_reliability": self.symbol_specific_reliability,
            "drift_detected": self.drift_detected,
            "last_updated": self.last_updated,
        }


@dataclass
class DriftState:
    """Current drift state for the system."""
    regime_drift_detected: bool = False
    regime_drift_magnitude: float = 0.0
    regime_drift_severity: str = "NONE"
    data_drift_detected: bool = False
    data_drift_magnitude: float = 0.0
    model_drift_detected: bool = False
    research_drift_detected: bool = False
    last_checked: str = ""
    affected_symbols: list[str] = field(default_factory=list)
    affected_timeframes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_drift_detected": self.regime_drift_detected,
            "regime_drift_magnitude": self.regime_drift_magnitude,
            "regime_drift_severity": self.regime_drift_severity,
            "data_drift_detected": self.data_drift_detected,
            "data_drift_magnitude": self.data_drift_magnitude,
            "model_drift_detected": self.model_drift_detected,
            "research_drift_detected": self.research_drift_detected,
            "last_checked": self.last_checked,
            "affected_symbols": self.affected_symbols,
            "affected_timeframes": self.affected_timeframes,
        }


@dataclass
class IntelligenceStateJ6:
    """J6 Intelligence State — production-grade research intelligence.

    Represents the full system state including:
    - current market observation
    - active regime
    - regime transitions
    - detected opportunities
    - active research runs
    - recent outcomes
    - research memory
    - failure memory
    - counterexamples
    - claim status
    - agent reliability
    - strategy-family reliability
    - drift state
    - data quality
    - uncertainty
    - pending research
    - human review state
    - last successful research cycle
    - next recommended research action
    """
    state: IntelligenceState = IntelligenceState.INITIALIZING
    cycle_id: str = ""
    entered_at: str = ""
    reason: str = ""
    provenance: str = ""
    context_version: int = 1

    # J6 additions
    current_observation: dict[str, Any] = field(default_factory=dict)
    active_regime: str = "UNKNOWN"
    regime_transitions: list[dict[str, Any]] = field(default_factory=list)
    detected_opportunities: list[dict[str, Any]] = field(default_factory=list)
    active_research_runs: list[dict[str, Any]] = field(default_factory=list)
    recent_outcomes: list[dict[str, Any]] = field(default_factory=list)
    research_memory: list[dict[str, Any]] = field(default_factory=list)
    failure_memory: list[dict[str, Any]] = field(default_factory=list)
    counterexamples: list[dict[str, Any]] = field(default_factory=list)
    claim_status: dict[str, str] = field(default_factory=dict)
    agent_reliability: dict[str, AgentReliabilityProfile] = field(default_factory=dict)
    strategy_family_reliability: dict[str, float] = field(default_factory=dict)
    drift_state: DriftState = field(default_factory=DriftState)
    data_quality: str = "UNKNOWN"
    uncertainty: float = 1.0  # 0-1, higher = more uncertain
    pending_research: list[dict[str, Any]] = field(default_factory=list)
    human_review_state: str = "NONE"  # NONE, REVIEW_REQUIRED, APPROVED, REJECTED, DEFERRED
    last_successful_cycle: str = ""
    next_recommended_action: str = ""

    # J6 priority explanation
    research_priority_explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "cycle_id": self.cycle_id,
            "entered_at": self.entered_at,
            "reason": self.reason,
            "provenance": self.provenance,
            "context_version": self.context_version,
            "current_observation": self.current_observation,
            "active_regime": self.active_regime,
            "regime_transitions": self.regime_transitions,
            "detected_opportunities": self.detected_opportunities,
            "active_research_runs": self.active_research_runs,
            "recent_outcomes": self.recent_outcomes,
            "research_memory": self.research_memory,
            "failure_memory": self.failure_memory,
            "counterexamples": self.counterexamples,
            "claim_status": self.claim_status,
            "agent_reliability": {
                k: v.to_dict() for k, v in self.agent_reliability.items()
            },
            "strategy_family_reliability": self.strategy_family_reliability,
            "drift_state": self.drift_state.to_dict(),
            "data_quality": self.data_quality,
            "uncertainty": self.uncertainty,
            "pending_research": self.pending_research,
            "human_review_state": self.human_review_state,
            "last_successful_cycle": self.last_successful_cycle,
            "next_recommended_action": self.next_recommended_action,
            "research_priority_explanation": self.research_priority_explanation,
        }