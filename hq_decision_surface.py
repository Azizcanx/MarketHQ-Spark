# -*- coding: utf-8 -*-
"""Phase J6 — HQ Decision Surface API.

Exposes stable API contracts for:
- /hq/overview
- /hq/situation
- /research/runs
- /research/runs/{id}
- /agents
- /agents/{id}
- /opportunities
- /opportunities/{id}
- /setups
- /claims
- /memory
- /drift
- /reliability
- /human-review

Research-only. No trading. No broker.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from intelligence_state_j6 import (
    IntelligenceStateJ6,
    AgentReliabilityProfile,
    DriftState,
)
from claim_validation_pipeline import ClaimValidationPipeline
from agent_reliability import ReliabilityTracker
from research_intelligence_model import Claim, ClaimStatus


class HQDecisionSurface:
    """HQ Decision Surface — AI research command center API.

    Provides all data surfaces needed for the AzizBusiness HQ UI:
    1. HQ Overview
    2. Opportunity Center
    3. Research Runs
    4. Agent Board
    5. Claims
    6. Intelligence Timeline
    7. Human Review
    8. Situation Report
    """

    def __init__(self) -> None:
        self.intelligence = IntelligenceStateJ6()
        self.claims = ClaimValidationPipeline()
        self.reliability = ReliabilityTracker()
        self.research_runs: list[dict[str, Any]] = []
        self.human_reviews: list[dict[str, Any]] = []

    # --- /hq/overview ---
    def get_overview(self) -> dict[str, Any]:
        """HQ Overview: current market state, active research, health, reliability."""
        return {
            "market_state": self.intelligence.current_observation,
            "active_regime": self.intelligence.active_regime,
            "active_research_runs": len(self.intelligence.active_research_runs),
            "detected_opportunities": len(self.intelligence.detected_opportunities),
            "research_health": self.intelligence.state.value,
            "agent_health": "OPERATIONAL",
            "reliability_summary": self.reliability.get_reliability_summary(),
            "uncertainty": self.intelligence.uncertainty,
            "pending_human_review": self.intelligence.human_review_state,
            "data_quality": self.intelligence.data_quality,
            "last_successful_cycle": self.intelligence.last_successful_cycle,
            "next_recommended_action": self.intelligence.next_recommended_action,
        }

    # --- /hq/situation ---
    def get_situation(self) -> dict[str, Any]:
        """Full situation report."""
        return {
            "market": self.intelligence.current_observation,
            "regime": self.intelligence.active_regime,
            "important_changes": self.intelligence.regime_transitions[-5:] if self.intelligence.regime_transitions else [],
            "detected_opportunities": self.intelligence.detected_opportunities,
            "strong_evidence": [
                c for c in self.claims.get_all_claims()
                if c.status == ClaimStatus.SUPPORTED
            ],
            "conflicting_evidence": [
                c for c in self.claims.get_all_claims()
                if c.status == ClaimStatus.UNSTABLE
            ],
            "historical_context": self.intelligence.research_memory[-10:] if self.intelligence.research_memory else [],
            "agent_reliability": self.reliability.get_reliability_summary(),
            "research_running": self.intelligence.active_research_runs,
            "uncertainty": self.intelligence.uncertainty,
            "recommended_next_research": self.intelligence.next_recommended_action,
        }

    # --- /research/runs ---
    def get_research_runs(self) -> list[dict[str, Any]]:
        return self.research_runs

    def get_research_run(self, run_id: str) -> dict[str, Any] | None:
        for run in self.research_runs:
            if run.get("run_id") == run_id:
                return run
        return None

    # --- /agents ---
    def get_agents(self) -> list[dict[str, Any]]:
        return [
            {"agent_id": aid, **profile.to_dict()}
            for aid, profile in self.reliability._profiles.items()
        ]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        profile = self.reliability._profiles.get(agent_id)
        if profile:
            return profile.to_dict()
        return None

    # --- /opportunities ---
    def get_opportunities(self) -> list[dict[str, Any]]:
        return self.intelligence.detected_opportunities

    def get_opportunity(self, opp_id: str) -> dict[str, Any] | None:
        for opp in self.intelligence.detected_opportunities:
            if opp.get("opportunity_id") == opp_id:
                return opp
        return None

    # --- /setups ---
    def get_setups(self) -> list[dict[str, Any]]:
        return self.intelligence.research_memory

    # --- /claims ---
    def get_claims(self) -> dict[str, Any]:
        return self.claims.to_dict()

    def get_claim(self, claim_id: str) -> Claim | None:
        return self.claims.get_claim(claim_id)

    # --- /memory ---
    def get_memory(self) -> list[dict[str, Any]]:
        return self.intelligence.research_memory

    # --- /drift ---
    def get_drift(self) -> dict[str, Any]:
        return self.intelligence.drift_state.to_dict()

    # --- /reliability ---
    def get_reliability(self) -> dict[str, Any]:
        return self.reliability.get_reliability_summary()

    # --- /human-review ---
    def get_human_review(self) -> list[dict[str, Any]]:
        return self.human_reviews

    def add_human_review(
        self, review_type: str, claim_id: str, decision: str, notes: str = ""
    ) -> dict[str, Any]:
        """Add human review — never silently alters research history."""
        review = {
            "review_id": f"REV-{uuid.uuid4().hex[:8].upper()}",
            "review_type": review_type,
            "claim_id": claim_id,
            "decision": decision,  # REVIEW_REQUIRED, APPROVED, REJECTED, DEFERRED
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.human_reviews.append(review)
        self.intelligence.human_review_state = decision
        return review

    # --- Situation Report (§15) ---
    def build_situation_report(self) -> str:
        """Build HQ Situation Report — research report, NOT trading advice."""
        overview = self.get_overview()
        situation = self.get_situation()

        lines = [
            "AZIZBUSINESS HQ — CURRENT SITUATION",
            "=" * 50,
            "",
            "Market:",
            f"  Observation: {overview['market_state']}",
            f"  Data Quality: {overview['data_quality']}",
            f"  Uncertainty: {overview['uncertainty']:.2f}",
            "",
            "Regime:",
            f"  Active: {overview['active_regime']}",
            f"  Changes: {len(situation.get('important_changes', []))}",
            "",
            "Important Changes:",
        ]
        for change in situation.get("important_changes", [])[:5]:
            lines.append(f"  - {change}")

        lines += [
            "",
            "Detected Opportunities:",
        ]
        for opp in situation.get("detected_opportunities", [])[:5]:
            lines.append(f"  - {opp}")

        lines += [
            "",
            "Strong Evidence:",
        ]
        for claim in situation.get("strong_evidence", [])[:5]:
            lines.append(f"  - {claim}")

        lines += [
            "",
            "Conflicting Evidence:",
        ]
        for claim in situation.get("conflicting_evidence", [])[:5]:
            lines.append(f"  - {claim}")

        lines += [
            "",
            "Historical Context:",
        ]
        for mem in situation.get("historical_context", [])[:5]:
            lines.append(f"  - {mem}")

        lines += [
            "",
            "Agent Reliability:",
        ]
        for agent_id, rel in situation.get("agent_reliability", {}).items():
            lines.append(f"  - {agent_id}: score={rel.get('reliability_score', 0):.2f}")

        lines += [
            "",
            "Research Running:",
        ]
        for run in situation.get("research_running", [])[:5]:
            lines.append(f"  - {run}")

        lines += [
            "",
            f"Uncertainty: {overview['uncertainty']:.2f}",
            f"Recommended Next Research: {overview.get('next_recommended_action', 'N/A')}",
            "",
            "---",
            "This is a RESEARCH REPORT. Not trading advice.",
            "No BUY/SELL/ENTER NOW/GUARANTEED statements.",
        ]

        return "\n".join(lines)

    # --- Priority Engine with auditable explanation (§12) ---
    def set_research_priority(
        self,
        action: str,
        expected_info_value: float = 0.5,
        uncertainty: float = 0.5,
        impact: str = "medium",
        data_available: bool = True,
        historical_instability: float = 0.0,
        drift_detected: bool = False,
        recurrence: float = 0.0,
        failure_memory: int = 0,
        claim_instability: float = 0.0,
        research_cost: str = "low",
    ) -> str:
        """Set research priority with auditable explanation."""
        reasons = []
        if uncertainty > 0.7:
            reasons.append("high uncertainty")
        if drift_detected:
            reasons.append("recent regime transition / drift detected")
        if data_available:
            reasons.append("sufficient data")
        if failure_memory > 0:
            reasons.append(f"{failure_memory} previous failures")
        if claim_instability > 0.5:
            reasons.append("claim instability")
        if historical_instability > 0.5:
            reasons.append("historical instability")

        explanation = (
            f"WHY THIS RESEARCH? — {action}\n"
            f"  - expected info value: {expected_info_value:.2f}\n"
            f"  - uncertainty: {uncertainty:.2f}\n"
            f"  - impact: {impact}\n"
            f"  - data available: {data_available}\n"
            f"  - research cost: {research_cost}\n"
            f"  - reasons: {', '.join(reasons) if reasons else 'routine monitoring'}"
        )

        self.intelligence.next_recommended_action = action
        self.intelligence.research_priority_explanation = explanation
        return explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "overview": self.get_overview(),
            "situation": self.get_situation(),
            "research_runs": self.research_runs,
            "agents": self.get_agents(),
            "claims": self.claims.to_dict(),
            "drift": self.get_drift(),
            "reliability": self.get_reliability(),
            "human_reviews": self.human_reviews,
            "situation_report": self.build_situation_report(),
        }