# -*- coding: utf-8 -*-
"""Research Priority Engine — Phase J4.

Deterministic priority scoring for research opportunities.
Never makes trade predictions. Only decides research order.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PriorityLevel(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    BACKLOG = "BACKLOG"


@dataclass
class OpportunityCandidate:
    """A candidate opportunity from market observation."""
    opportunity_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    direction: str = "NEUTRAL"
    regime: str = "UNKNOWN"
    setup_candidates: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    unavailable_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty: float = 1.0
    source_agents: list[str] = field(default_factory=list)
    provenance_ref: str = ""
    observation_id: str = ""
    opportunity_type: str = "UNKNOWN"
    data_quality: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            self.opportunity_id = f"OPP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "regime": self.regime,
            "setup_candidates": self.setup_candidates,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "unavailable_evidence": self.unavailable_evidence,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "source_agents": self.source_agents,
            "provenance_ref": self.provenance_ref,
            "observation_id": self.observation_id,
            "opportunity_type": self.opportunity_type,
            "data_quality": self.data_quality,
        }


@dataclass
class ResearchTask:
    """A single research task for an agent."""
    task_id: str = ""
    agent_id: str = ""
    agent_version: str = ""
    symbol: str = ""
    timeframe: str = ""
    task_type: str = ""
    priority: PriorityLevel = PriorityLevel.MEDIUM
    capability_required: str = ""
    context_version: str = ""
    idempotency_key: str = ""
    timeout_seconds: int = 60
    max_retries: int = 2
    retry_count: int = 0
    created_at: str = ""
    deadline: str = ""
    dependencies: list[str] = field(default_factory=list)
    provenance_ref: str = ""
    error_type: str = ""
    error_message: str = ""
    status: str = "PENDING"

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"TASK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.idempotency_key:
            self.idempotency_key = hashlib.sha256(
                f"{self.agent_id}:{self.symbol}:{self.timeframe}:{self.task_type}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "task_type": self.task_type,
            "priority": self.priority.value,
            "capability_required": self.capability_required,
            "idempotency_key": self.idempotency_key,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "dependencies": self.dependencies,
            "status": self.status,
        }


class ResearchPriorityEngine:
    """Scores research opportunities by priority.

    Never predicts trade outcomes. Only decides research order.
    Deterministic scoring — no random.
    """

    def __init__(self) -> None:
        self._history: list[dict[str, Any]] = []

    def score(
        self,
        candidate: OpportunityCandidate,
        novelty: float = 0.5,
        evidence_strength: float = 0.5,
        evidence_conflict: float = 0.0,
        data_quality_score: float = 0.5,
        regime_relevance: float = 0.5,
        historical_recurrence: float = 0.0,
        uncertainty: float = 1.0,
        expected_research_value: float = 0.5,
        previous_failure_count: int = 0,
        agent_availability_score: float = 0.5,
        task_cost: float = 0.0,
    ) -> dict[str, Any]:
        """Score an opportunity candidate for research priority."""

        # Base score from opportunity confidence (research confidence, not win prob)
        base = candidate.confidence * 0.15

        # Factor weights
        score = (
            base
            + novelty * 0.15
            + evidence_strength * 0.15
            - evidence_conflict * 0.2
            + data_quality_score * 0.1
            + regime_relevance * 0.1
            + historical_recurrence * 0.05
            - uncertainty * 0.05
            + expected_research_value * 0.1
            - min(previous_failure_count, 5) * 0.03
            + agent_availability_score * 0.05
            - task_cost * 0.05
        )

        # Clamp 0-1
        score = max(0.0, min(1.0, score))

        # Determine priority level
        if score >= 0.7:
            level = PriorityLevel.CRITICAL
        elif score >= 0.5:
            level = PriorityLevel.HIGH
        elif score >= 0.3:
            level = PriorityLevel.MEDIUM
        elif score >= 0.1:
            level = PriorityLevel.LOW
        else:
            level = PriorityLevel.BACKLOG

        result = {
            "opportunity_id": candidate.opportunity_id,
            "score": round(score, 4),
            "priority": level.value,
            "level": level,
            "factors": {
                "base": round(base, 4),
                "novelty": novelty,
                "evidence_strength": evidence_strength,
                "evidence_conflict": evidence_conflict,
                "data_quality": data_quality_score,
                "regime_relevance": regime_relevance,
                "historical_recurrence": historical_recurrence,
                "uncertainty": uncertainty,
                "expected_research_value": expected_research_value,
                "previous_failures": previous_failure_count,
                "agent_availability": agent_availability_score,
                "task_cost": task_cost,
            },
            "symbol": candidate.symbol,
            "timeframe": candidate.timeframe,
            "regime": candidate.regime,
            "opportunity_type": candidate.opportunity_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._history.append(result)
        return result

    def rank(self, candidates: list[OpportunityCandidate]) -> list[dict[str, Any]]:
        """Rank multiple candidates by priority."""
        scored = []
        for c in candidates:
            s = self.score(c)
            scored.append(s)
        scored.sort(key=lambda x: -x["score"])
        return scored

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._history)