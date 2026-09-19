# -*- coding: utf-8 -*-
"""Research Team Model — Phase J2.

Research teams are collaboration abstractions, NOT trading desks.
Teams compose agents for structured research workflows.

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TeamStatus(Enum):
    DRAFT = "DRAFT"
    FORMING = "FORMING"
    ACTIVE = "ACTIVE"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class TeamPurpose(Enum):
    MARKET_STRUCTURE = "market_structure"
    MOMENTUM_VOLATILITY = "momentum_volatility"
    BREAKOUT_RESEARCH = "breakout_research"
    REVERSAL_RESEARCH = "reversal_research"
    FULL_MARKET_RESEARCH = "full_market_research"
    CUSTOM = "custom"


@dataclass
class TeamMember:
    agent_id: str
    role: str  # RESEARCHER | CRITIC | SYNTHESIZER | REVIEWER | COORDINATOR
    capabilities: list[str] = field(default_factory=list)
    joined_at: str = ""
    health_status: str = "healthy"


@dataclass
class ResearchTeam:
    """Research team — collaboration abstraction for research workflow.

    NOT a trading desk. Research collaboration only.
    Team members are agents with specific capabilities.
    """
    team_id: str = ""
    name: str = ""
    purpose: TeamPurpose = TeamPurpose.CUSTOM
    description: str = ""
    member_agent_ids: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    workflow: list[str] = field(default_factory=list)
    status: TeamStatus = TeamStatus.DRAFT
    version: str = "1.0.0"
    workspace_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    team_lead_agent_id: str = ""
    max_iterations: int = 3
    max_messages: int = 100
    max_delegations: int = 20

    def __post_init__(self) -> None:
        if not self.team_id:
            self.team_id = f"TEAM-{uuid.uuid4().hex[:10].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        self._members: list[TeamMember] = []

    def add_member(self, agent_id: str, role: str = "RESEARCHER", capabilities: list[str] | None = None) -> bool:
        """Add a member to the team. Returns False if already a member."""
        if agent_id in self.member_agent_ids:
            return False
        self.member_agent_ids.append(agent_id)
        self._members.append(TeamMember(
            agent_id=agent_id, role=role,
            capabilities=capabilities or [],
            joined_at=datetime.now(timezone.utc).isoformat(),
        ))
        self._update_updated()
        return True

    def remove_member(self, agent_id: str) -> bool:
        """Remove a member from the team."""
        if agent_id not in self.member_agent_ids:
            return False
        self.member_agent_ids.remove(agent_id)
        self._update_updated()
        return True

    def is_member(self, agent_id: str) -> bool:
        return agent_id in self.member_agent_ids

    def get_member_roles(self) -> dict[str, str]:
        """Get agent_id → role mapping for all members."""
        return {m.agent_id: m.role for m in self._members}

    def set_team_lead(self, agent_id: str) -> None:
        if agent_id in self.member_agent_ids:
            self.team_lead_agent_id = agent_id
            self._update_updated()

    def transition_to(self, new_status: TeamStatus) -> None:
        self.status = new_status
        self._update_updated()

    def _update_updated(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "purpose": self.purpose.value,
            "description": self.description,
            "member_agent_ids": self.member_agent_ids,
            "required_capabilities": self.required_capabilities,
            "workflow": self.workflow,
            "status": self.status.value,
            "version": self.version,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "team_lead_agent_id": self.team_lead_agent_id,
            "max_iterations": self.max_iterations,
            "max_messages": self.max_messages,
            "max_delegations": self.max_delegations,
        }


# ── Deterministic Team Templates ─────────────────────────────────────────

TEAM_TEMPLATES: dict[str, dict[str, Any]] = {
    "market_structure": {
        "name": "Market Structure Team",
        "purpose": TeamPurpose.MARKET_STRUCTURE,
        "description": "Analyzes market structure, BOS, CHoCH, liquidity",
        "members": [
            ("structure_agent", "RESEARCHER", ["structure_analysis"]),
            ("trend_agent", "RESEARCHER", ["trend_analysis"]),
            ("liquidity_agent", "RESEARCHER", ["liquidity_analysis"]),
            ("critic_agent", "CRITIC", []),
        ],
        "required_capabilities": ["structure_analysis", "trend_analysis", "liquidity_analysis"],
        "workflow": ["feature_snapshot", "regime", "parallel_agents", "evidence_exchange", "synthesis", "critic", "opportunity"],
        "max_iterations": 3,
    },
    "momentum_volatility": {
        "name": "Momentum & Volatility Team",
        "purpose": TeamPurpose.MOMENTUM_VOLATILITY,
        "description": "Analyzes momentum and volatility context",
        "members": [
            ("momentum_agent", "RESEARCHER", ["momentum_analysis"]),
            ("volatility_agent", "RESEARCHER", ["volatility_analysis"]),
            ("trend_agent", "RESEARCHER", ["trend_analysis"]),
            ("critic_agent", "CRITIC", []),
        ],
        "required_capabilities": ["momentum_analysis", "volatility_analysis", "trend_analysis"],
        "workflow": ["feature_snapshot", "regime", "parallel_agents", "evidence_exchange", "synthesis", "critic", "opportunity"],
        "max_iterations": 3,
    },
    "breakout_research": {
        "name": "Breakout Research Team",
        "purpose": TeamPurpose.BREAKOUT_RESEARCH,
        "description": "Detects breakout opportunities from consolidation",
        "members": [
            ("breakout_agent", "RESEARCHER", ["breakout_analysis"]),
            ("structure_agent", "RESEARCHER", ["structure_analysis"]),
            ("momentum_agent", "RESEARCHER", ["momentum_analysis"]),
            ("volatility_agent", "RESEARCHER", ["volatility_analysis"]),
            ("critic_agent", "CRITIC", []),
        ],
        "required_capabilities": ["breakout_analysis", "structure_analysis", "momentum_analysis", "volatility_analysis"],
        "workflow": ["feature_snapshot", "regime", "parallel_agents", "evidence_exchange", "synthesis", "critic", "opportunity"],
        "max_iterations": 3,
    },
    "reversal_research": {
        "name": "Reversal Research Team",
        "purpose": TeamPurpose.REVERSAL_RESEARCH,
        "description": "Identifies potential reversal points",
        "members": [
            ("reversal_agent", "RESEARCHER", ["reversal_analysis"]),
            ("structure_agent", "RESEARCHER", ["structure_analysis"]),
            ("liquidity_agent", "RESEARCHER", ["liquidity_analysis"]),
            ("momentum_agent", "RESEARCHER", ["momentum_analysis"]),
            ("critic_agent", "CRITIC", []),
        ],
        "required_capabilities": ["reversal_analysis", "structure_analysis", "liquidity_analysis", "momentum_analysis"],
        "workflow": ["feature_snapshot", "regime", "parallel_agents", "evidence_exchange", "synthesis", "critic", "opportunity"],
        "max_iterations": 3,
    },
    "full_market_research": {
        "name": "Full Market Research Team",
        "purpose": TeamPurpose.FULL_MARKET_RESEARCH,
        "description": "Comprehensive market research with all strategy agents",
        "members": [
            ("trend_agent", "RESEARCHER", ["trend_analysis"]),
            ("breakout_agent", "RESEARCHER", ["breakout_analysis"]),
            ("reversal_agent", "RESEARCHER", ["reversal_analysis"]),
            ("momentum_agent", "RESEARCHER", ["momentum_analysis"]),
            ("volatility_agent", "RESEARCHER", ["volatility_analysis"]),
            ("liquidity_agent", "RESEARCHER", ["liquidity_analysis"]),
            ("structure_agent", "RESEARCHER", ["structure_analysis"]),
            ("critic_agent", "CRITIC", []),
        ],
        "required_capabilities": [
            "trend_analysis", "breakout_analysis", "reversal_analysis",
            "momentum_analysis", "volatility_analysis", "liquidity_analysis",
            "structure_analysis",
        ],
        "workflow": ["feature_snapshot", "regime", "parallel_agents", "evidence_exchange", "synthesis", "critic", "opportunity", "setup", "intelligence", "hq"],
        "max_iterations": 3,
    },
}


def create_team_from_template(template_name: str, workspace_id: str = "") -> ResearchTeam:
    """Create a team from a deterministic template."""
    template = TEAM_TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"Unknown team template: {template_name}")

    team = ResearchTeam(
        name=template["name"],
        purpose=template["purpose"],
        description=template["description"],
        required_capabilities=template["required_capabilities"],
        workflow=template["workflow"],
        max_iterations=template["max_iterations"],
        workspace_id=workspace_id,
    )

    for agent_id, role, capabilities in template["members"]:
        team.add_member(agent_id, role, capabilities)

    if team.member_agent_ids:
        team.team_lead_agent_id = team.member_agent_ids[0]

    team.transition_to(TeamStatus.ACTIVE)
    return team