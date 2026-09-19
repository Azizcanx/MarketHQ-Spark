# -*- coding: utf-8 -*-
"""Adaptive Team Selector — Phase J4.

Selects research team members based on opportunity type, regime,
data availability, historical failure, and agent reliability.

Uses existing ResearchTeam system — extends it, doesn't duplicate.

Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_team import ResearchTeam, TeamStatus


@dataclass
class AgentReliability:
    """Agent reliability metrics."""
    agent_id: str = ""
    historical_success_rate: float = 0.0
    evidence_quality_avg: float = 0.0
    consistency_score: float = 0.0
    validation_support_rate: float = 0.0
    contradiction_rate: float = 0.0
    failure_rate: float = 0.0
    unavailable_rate: float = 0.0
    regime_specific_reliability: dict[str, float] = field(default_factory=dict)
    timeframe_specific_reliability: dict[str, float] = field(default_factory=dict)

    def overall_score(self) -> float:
        """Overall reliability score 0-1."""
        return (
            self.historical_success_rate * 0.3
            + self.evidence_quality_avg * 0.2
            + self.consistency_score * 0.2
            + self.validation_support_rate * 0.15
            - self.contradiction_rate * 0.1
            - self.failure_rate * 0.15
        )


@dataclass
class TeamSelection:
    """Result of adaptive team selection."""
    selection_id: str = ""
    opportunity_id: str = ""
    agent_ids: list[str] = field(default_factory=list)
    agent_types: list[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    expected_research_value: float = 0.0
    created_at: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.selection_id:
            self.selection_id = f"SEL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "opportunity_id": self.opportunity_id,
            "agent_ids": self.agent_ids,
            "agent_types": self.agent_types,
            "reason": self.reason,
            "confidence": self.confidence,
            "expected_research_value": self.expected_research_value,
        }


class AdaptiveTeamSelector:
    """Selects appropriate research team for each opportunity.

    Factors:
    - opportunity type
    - regime
    - data availability
    - historical failure
    - agent reliability
    """

    # Opportunity type → preferred agent types
    OPPORTUNITY_AGENT_MAP: dict[str, list[str]] = {
        "breakout": ["structure", "trend", "momentum", "volatility", "liquidity", "historical", "critic"],
        "trend_continuation": ["trend", "momentum", "structure", "historical", "critic"],
        "reversal": ["structure", "liquidity", "momentum", "historical", "critic"],
        "mean_reversion": ["volatility", "structure", "liquidity", "historical", "critic"],
        "momentum_shift": ["momentum", "trend", "volatility", "historical", "critic"],
        "liquidity_event": ["liquidity", "structure", "volatility", "historical", "critic"],
        "range": ["volatility", "structure", "liquidity", "historical"],
        "unknown": ["structure", "trend", "momentum", "volatility", "liquidity", "historical", "critic"],
    }

    def __init__(self) -> None:
        self._selections: dict[str, TeamSelection] = {}
        self._agent_reliability: dict[str, AgentReliability] = {}

    def register_reliability(self, reliability: AgentReliability) -> None:
        """Register agent reliability metrics."""
        self._agent_reliability[reliability.agent_id] = reliability

    def select_team(
        self,
        opportunity_id: str,
        opportunity_type: str,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "UNKNOWN",
        data_availability_score: float = 0.5,
        historical_failure_count: int = 0,
        reliability_scores: dict[str, float] | None = None,
    ) -> TeamSelection:
        """Select team for an opportunity."""

        # Get preferred agents for opportunity type
        preferred = self.OPPORTUNITY_AGENT_MAP.get(
            opportunity_type.lower(),
            self.OPPORTUNITY_AGENT_MAP["unknown"],
        )

        # Score and rank agents by reliability
        agent_scores = []
        for agent_type in preferred:
            agent_id = f"{agent_type}_agent"
            reliability = self._agent_reliability.get(agent_id)

            score = 0.5  # default
            if reliability:
                score = reliability.overall_score()
            if reliability_scores and agent_id in reliability_scores:
                score = reliability_scores[agent_id]

            # Penalize failed agents
            score -= min(historical_failure_count * 0.05, 0.3)

            # Boost for data availability
            score += data_availability_score * 0.1

            score = max(0.0, min(1.0, score))
            agent_scores.append((agent_id, agent_type, score))

        # Sort by score desc, then agent_type alphabetical for determinism
        agent_scores.sort(key=lambda x: (-x[2], x[1]))

        # Select top agents (max 7, min 3)
        max_agents = min(7, max(3, len(agent_scores)))
        selected = agent_scores[:max_agents]

        agent_ids = [s[0] for s in selected]
        agent_types = [s[1] for s in selected]

        # Reason
        reason = (
            f"Selected {len(selected)} agents for {opportunity_type}: "
            + ", ".join(f"{t}({s[2]:.2f})" for t, _, s in zip(agent_types, agent_ids, selected))
        )

        selection = TeamSelection(
            opportunity_id=opportunity_id,
            agent_ids=agent_ids,
            agent_types=agent_types,
            reason=reason,
            confidence=sum(s[2] for s in selected) / max(len(selected), 1),
            expected_research_value=sum(s[2] for s in selected) / max(len(selected), 1),
        )

        self._selections[selection.selection_id] = selection
        return selection

    def get_selection(self, selection_id: str) -> TeamSelection | None:
        return self._selections.get(selection_id)

    def list_selections(self) -> list[TeamSelection]:
        return list(self._selections.values())