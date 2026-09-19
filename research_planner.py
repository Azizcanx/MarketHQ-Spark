# -*- coding: utf-8 -*-
"""Research Planner — Phase J4.

Creates research tasks from opportunity candidates.
Uses existing agents + J3 AgentRouter for execution planning.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_priority_engine import OpportunityCandidate, PriorityLevel


# Known strategy research agents from existing system
STRATEGY_AGENTS = {
    "trend": "strategy_trend_research_agent",
    "breakout": "strategy_breakout_research_agent",
    "mean_reversion": "strategy_reversal_research_agent",
    "momentum": "strategy_momentum_research_agent",
    "volatility": "strategy_volatility_research_agent",
    "liquidity": "strategy_liquidity_research_agent",
    "structure": "strategy_structure_research_agent",
    "historical": "historical_evidence_agent",
    "critic": "research_critic_agent",
}

# Capability mapping for agents
AGENT_CAPABILITIES = {
    "strategy_trend_research_agent": "TREND",
    "strategy_breakout_research_agent": "BREAKOUT",
    "strategy_reversal_research_agent": "REVERSAL",
    "strategy_momentum_research_agent": "MOMENTUM",
    "strategy_volatility_research_agent": "VOLATILITY",
    "strategy_liquidity_research_agent": "LIQUIDITY",
    "strategy_structure_research_agent": "STRUCTURE",
    "historical_evidence_agent": "HISTORICAL",
    "research_critic_agent": "CRITIC",
}

# Agent type to capability mapping
AGENT_TYPE_CAPABILITY = {
    "trend": "TREND",
    "breakout": "BREAKOUT",
    "reversal": "REVERSAL",
    "mean_reversion": "REVERSAL",
    "momentum": "MOMENTUM",
    "volatility": "VOLATILITY",
    "liquidity": "LIQUIDITY",
    "structure": "STRUCTURE",
    "historical": "HISTORICAL",
    "critic": "CRITIC",
}


@dataclass
class ResearchPlan:
    """A complete research plan for an opportunity."""
    plan_id: str = ""
    opportunity_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    regime: str = ""
    opportunity_type: str = ""
    tasks: list[Any] = field(default_factory=list)
    priority: str = "MEDIUM"
    timeout_seconds: int = 300
    max_parallel: int = 3
    idempotency_key: str = ""
    created_at: str = ""
    deadline: str = ""
    context_version: str = ""
    provenance_ref: str = ""
    status: str = "PLANNED"
    error_type: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = f"PLAN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.idempotency_key:
            self.idempotency_key = hashlib.sha256(
                f"{self.opportunity_id}:{self.symbol}:{self.timeframe}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "opportunity_type": self.opportunity_type,
            "task_count": len(self.tasks),
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "max_parallel": self.max_parallel,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


class ResearchPlanner:
    """Creates research tasks from opportunity candidates.

    Uses existing agent capabilities + opportunity type to
    determine which agents to assign.
    """

    # Opportunity type → agent types mapping
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
        self._plans: dict[str, ResearchPlan] = {}
        self._tasks_by_idempotency: dict[str, str] = {}  # idempotency_key → task_id

    def create_plan(
        self,
        candidate: OpportunityCandidate,
        priority: PriorityLevel = PriorityLevel.MEDIUM,
        context_version: str = "",
        timeout_seconds: int = 300,
        max_parallel: int = 3,
    ) -> ResearchPlan:
        """Create a research plan from an opportunity candidate."""

        # Determine which agent types to use
        agent_types = self.OPPORTUNITY_AGENT_MAP.get(
            candidate.opportunity_type.lower(),
            self.OPPORTUNITY_AGENT_MAP["unknown"],
        )

        # Create tasks
        tasks = []
        for agent_type in agent_types:
            agent_id = STRATEGY_AGENTS.get(agent_type, f"agent_{agent_type}")
            capability = AGENT_TYPE_CAPABILITY.get(agent_type, agent_type.upper())

            task = self._create_task(
                agent_id=agent_id,
                agent_version="1.0",
                symbol=candidate.symbol,
                timeframe=candidate.timeframe,
                task_type=agent_type,
                capability_required=capability,
                priority=priority,
                context_version=context_version,
                idempotency_key=f"{candidate.opportunity_id}:{agent_type}:{candidate.symbol}:{candidate.timeframe}",
                timeout_seconds=timeout_seconds,
                provenance_ref=candidate.provenance_ref,
            )
            tasks.append(task)

        plan = ResearchPlan(
            opportunity_id=candidate.opportunity_id,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            regime=candidate.regime,
            opportunity_type=candidate.opportunity_type,
            tasks=tasks,
            priority=priority.value,
            timeout_seconds=timeout_seconds,
            max_parallel=max_parallel,
            context_version=context_version,
            provenance_ref=candidate.provenance_ref,
        )

        self._plans[plan.plan_id] = plan
        return plan

    def _create_task(
        self,
        agent_id: str,
        agent_version: str,
        symbol: str,
        timeframe: str,
        task_type: str,
        capability_required: str,
        priority: PriorityLevel,
        context_version: str,
        idempotency_key: str,
        timeout_seconds: int,
        provenance_ref: str,
    ) -> Any:
        """Create a single research task."""
        from research_priority_engine import ResearchTask

        # Check duplicate via idempotency
        if idempotency_key in self._tasks_by_idempotency:
            existing_task_id = self._tasks_by_idempotency[idempotency_key]
            # Return a marker task indicating duplicate
            return {
                "task_id": f"DUP-{existing_task_id}",
                "agent_id": agent_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "task_type": task_type,
                "status": "DUPLICATE_SKIPPED",
                "idempotency_key": idempotency_key,
            }

        task = ResearchTask(
            agent_id=agent_id,
            agent_version=agent_version,
            symbol=symbol,
            timeframe=timeframe,
            task_type=task_type,
            priority=priority,
            capability_required=capability_required,
            context_version=context_version,
            idempotency_key=idempotency_key,
            timeout_seconds=timeout_seconds,
            provenance_ref=provenance_ref,
        )
        self._tasks_by_idempotency[idempotency_key] = task.task_id
        return task.to_dict()

    def get_plan(self, plan_id: str) -> ResearchPlan | None:
        return self._plans.get(plan_id)

    def get_task_by_idempotency(self, idempotency_key: str) -> str | None:
        return self._tasks_by_idempotency.get(idempotency_key)

    def list_plans(self) -> list[ResearchPlan]:
        return list(self._plans.values())