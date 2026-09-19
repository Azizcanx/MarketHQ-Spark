# -*- coding: utf-8 -*-
"""Phase J6 — Agent Reliability Tracker.

Tracks research reliability per agent — separate from health.

Health = "Can it execute?"
Reliability = "How useful/accurate has its research historically been?"

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from intelligence_state_j6 import AgentReliabilityProfile


class ReliabilityTracker:
    """Tracks and updates agent reliability profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, AgentReliabilityProfile] = {}

    def get_profile(self, agent_id: str) -> AgentReliabilityProfile:
        if agent_id not in self._profiles:
            self._profiles[agent_id] = AgentReliabilityProfile(agent_id=agent_id)
        return self._profiles[agent_id]

    def record_execution(
        self,
        agent_id: str,
        success: bool,
        useful_evidence: bool = False,
        contradicted: bool = False,
        outcome_aligned: bool = False,
        regime: str = "",
        timeframe: str = "",
        symbol: str = "",
    ) -> AgentReliabilityProfile:
        """Record an execution result and update reliability profile."""
        profile = self.get_profile(agent_id)
        profile.total_executions += 1
        profile.last_updated = datetime.now(timezone.utc).isoformat()

        if success:
            profile.successful_executions += 1
        else:
            profile.failed_executions += 1

        if useful_evidence:
            profile.useful_evidence_count += 1
        if contradicted:
            profile.contradicted_evidence_count += 1
        if outcome_aligned:
            profile.outcome_alignment_score = (
                profile.outcome_alignment_score * 0.8 + 0.2
            )
        elif success and not outcome_aligned:
            profile.outcome_alignment_score = (
                profile.outcome_alignment_score * 0.8 + 0.0
            )

        # Regime-specific
        if regime:
            regime_scores = profile.regime_specific_reliability
            if regime not in regime_scores:
                regime_scores[regime] = 0.5
            if outcome_aligned:
                regime_scores[regime] = min(1.0, regime_scores[regime] + 0.05)
            else:
                regime_scores[regime] = max(0.0, regime_scores[regime] - 0.05)

        # Timeframe-specific
        if timeframe:
            tf_scores = profile.timeframe_specific_reliability
            if timeframe not in tf_scores:
                tf_scores[timeframe] = 0.5
            if outcome_aligned:
                tf_scores[timeframe] = min(1.0, tf_scores[timeframe] + 0.05)
            else:
                tf_scores[timeframe] = max(0.0, tf_scores[timeframe] - 0.05)

        # Symbol-specific
        if symbol:
            sym_scores = profile.symbol_specific_reliability
            if symbol not in sym_scores:
                sym_scores[symbol] = 0.5
            if outcome_aligned:
                sym_scores[symbol] = min(1.0, sym_scores[symbol] + 0.05)
            else:
                sym_scores[symbol] = max(0.0, sym_scores[symbol] - 0.05)

        return profile

    def record_unavailable(self, agent_id: str) -> AgentReliabilityProfile:
        """Record an unavailable result (data missing, provider down)."""
        profile = self.get_profile(agent_id)
        profile.unavailable_results += 1
        profile.total_executions += 1
        profile.last_updated = datetime.now(timezone.utc).isoformat()
        return profile

    def mark_drift(self, agent_id: str, drift_detected: bool = True) -> None:
        """Mark that an agent's reliability may have drifted."""
        profile = self.get_profile(agent_id)
        profile.drift_detected = drift_detected
        profile.last_updated = datetime.now(timezone.utc).isoformat()

    def get_reliability_summary(self) -> dict[str, Any]:
        """Get summary of all agent reliability profiles."""
        profiles = {}
        for agent_id, profile in self._profiles.items():
            profiles[agent_id] = {
                "reliability_score": profile.reliability_score,
                "success_rate": profile.success_rate,
                "total_executions": profile.total_executions,
                "drift_detected": profile.drift_detected,
            }
        return profiles

    def get_reliable_agents(self, min_score: float = 0.5) -> list[str]:
        """Get agents with reliability score above threshold."""
        return [
            agent_id
            for agent_id, profile in self._profiles.items()
            if profile.reliability_score >= min_score
        ]

    def get_unreliable_agents(self, max_score: float = 0.3) -> list[str]:
        """Get agents with reliability score below threshold."""
        return [
            agent_id
            for agent_id, profile in self._profiles.items()
            if profile.reliability_score <= max_score
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            agent_id: profile.to_dict()
            for agent_id, profile in self._profiles.items()
        }