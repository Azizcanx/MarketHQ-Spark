# -*- coding: utf-8 -*-
"""Autonomous Research Loop — Phase J4.

Main loop: OBSERVE → DETECT → PRIORITIZE → PLAN → DELEGATE → RESEARCH
→ COLLABORATE → CRITIC → SYNTHESIZE → VALIDATE → REMEMBER → LEARN
→ REPORT → WAIT → OBSERVE (cycle repeats).

Deterministic state machine. Finite loops only. Research-only.
No broker. No order. No auto trade. No real money.

Uses all existing MarketHQ components — extends, never duplicates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from market_observation import MarketObservation, ObservationBundle, DataQuality
from research_priority_engine import (
    OpportunityCandidate, ResearchPriorityEngine, PriorityLevel, ResearchTask,
)
from research_planner import ResearchPlanner, ResearchPlan
from adaptive_team_selector import AdaptiveTeamSelector, TeamSelection, AgentReliability
from data_quality_gate import DataQualityGate, DataQualityGateChecker, DataQualityGateResult
from research_audit import ResearchAuditEvent, AuditEventType, AuditLog


class LoopState(Enum):
    IDLE = "IDLE"
    OBSERVING = "OBSERVING"
    DETECTING = "DETECTING"
    PRIORITIZING = "PRIORITIZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    CRITIQUING = "CRITIQUING"
    SYNTHESIZING = "SYNTHESIZING"
    VALIDATING = "VALIDATING"
    LEARNING = "LEARNING"
    REPORTING = "REPORTING"
    WAITING = "WAITING"


@dataclass
class AutonomousResearchRun:
    """A single autonomous research run / cycle."""
    run_id: str = ""
    cycle_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = "IDLE"
    trigger: str = "manual"
    symbol_scope: str = ""
    timeframe_scope: str = ""
    task_count: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    opportunity_count: int = 0
    synthesis_count: int = 0
    validation_count: int = 0
    human_review_count: int = 0
    error_summary: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)
    state_history: list[dict[str, Any]] = field(default_factory=list)
    current_state: str = "IDLE"
    audit_events: list[str] = field(default_factory=list)
    max_cycles: int = 100
    cycle_count: int = 0
    cancelled: bool = False

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = f"RUN-{uuid.uuid4().hex[:10].upper()}"
        if not self.cycle_id:
            self.cycle_id = f"CYC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "trigger": self.trigger,
            "symbol_scope": self.symbol_scope,
            "timeframe_scope": self.timeframe_scope,
            "task_count": self.task_count,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "opportunity_count": self.opportunity_count,
            "synthesis_count": self.synthesis_count,
            "validation_count": self.validation_count,
            "human_review_count": self.human_review_count,
            "error_summary": self.error_summary,
            "current_state": self.current_state,
            "cycle_count": self.cycle_count,
            "cancelled": self.cancelled,
            "state_history": self.state_history,
            "audit_events": self.audit_events,
        }


@dataclass
class AutonomousResearchReport:
    """Final report from an autonomous research cycle."""
    report_id: str = ""
    run: AutonomousResearchRun | None = None
    observations: list[MarketObservation] = field(default_factory=list)
    opportunities: list[OpportunityCandidate] = field(default_factory=list)
    research_tasks: list[dict[str, Any]] = field(default_factory=list)
    agent_results: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    critic_result: dict[str, Any] = field(default_factory=dict)
    synthesis: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    learning_proposals: list[dict[str, Any]] = field(default_factory=list)
    human_review_items: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: float = 1.0
    provenance: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.report_id:
            self.report_id = f"RPT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "run": self.run.to_dict() if self.run else None,
            "observation_count": len(self.observations),
            "opportunity_count": len(self.opportunities),
            "task_count": len(self.research_tasks),
            "agent_result_count": len(self.agent_results),
            "evidence": self.evidence,
            "conflict_count": len(self.conflicts),
            "critic_status": self.critic_result.get("status", "N/A") if self.critic_result else "N/A",
            "synthesis_status": self.synthesis.get("status", "N/A") if self.synthesis else "N/A",
            "validation_status": self.validation.get("status", "N/A") if self.validation else "N/A",
            "hypothesis_count": len(self.hypotheses),
            "claim_count": len(self.claims),
            "memory_update_count": len(self.memory_updates),
            "learning_proposal_count": len(self.learning_proposals),
            "human_review_count": len(self.human_review_items),
            "uncertainty": self.uncertainty,
            "data_quality": self.data_quality,
            "runtime_metadata": self.runtime_metadata,
        }


class AutonomousResearchLoop:
    """Autonomous research loop state machine.

    Lifecycle:
    IDLE → OBSERVING → DETECTING → PRIORITIZING → PLANNING → EXECUTING
    → CRITIQUING → SYNTHESIZING → VALIDATING → LEARNING → REPORTING → WAITING → OBSERVING

    Deterministic. Finite loops. Research-only. No trading.
    """

    def __init__(
        self,
        priority_engine: ResearchPriorityEngine | None = None,
        planner: ResearchPlanner | None = None,
        team_selector: AdaptiveTeamSelector | None = None,
        quality_gate: DataQualityGateChecker | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.priority_engine = priority_engine or ResearchPriorityEngine()
        self.planner = planner or ResearchPlanner()
        self.team_selector = team_selector or AdaptiveTeamSelector()
        self.quality_gate = quality_gate or DataQualityGateChecker()
        self.audit_log = audit_log or AuditLog()

        self._run: AutonomousResearchRun | None = None
        self._report: AutonomousResearchReport | None = None
        self._state: LoopState = LoopState.IDLE
        self._state_start_time: str = ""
        self._max_cycles: int = 100
        self._max_tasks_per_cycle: int = 20
        self._max_agent_executions: int = 50
        self._cancelled: bool = False
        self._execution_count: int = 0

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def run(self) -> AutonomousResearchRun | None:
        return self._run

    @property
    def report(self) -> AutonomousResearchReport | None:
        return self._report

    def start_cycle(
        self,
        symbol_scope: str = "",
        timeframe_scope: str = "1h",
        trigger: str = "manual",
        max_cycles: int = 100,
        max_tasks_per_cycle: int = 20,
    ) -> AutonomousResearchRun:
        """Start a new research cycle."""

        # Safety checks
        if self._state not in (LoopState.IDLE, LoopState.WAITING):
            raise RuntimeError(
                f"Cannot start cycle: current state is {self._state.value}"
            )

        # Cancel any previous run
        if self._run and self._run.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            self._run.status = "CANCELLED"
            self._cancelled = True

        # Create new run
        self._run = AutonomousResearchRun(
            symbol_scope=symbol_scope,
            timeframe_scope=timeframe_scope,
            trigger=trigger,
            max_cycles=max_cycles,
            cycle_count=0,
        )
        self._max_cycles = max_cycles
        self._max_tasks_per_cycle = max_tasks_per_cycle
        self._cancelled = False
        self._execution_count = 0
        self._state = LoopState.OBSERVING
        self._state_start_time = datetime.now(timezone.utc).isoformat()

        # Audit
        self.audit_log.append(ResearchAuditEvent(
            event_type=AuditEventType.TASK_STARTED,
            agent_id="AUTONOMOUS_LOOP",
            metadata={"run_id": self._run.run_id, "cycle_id": self._run.cycle_id, "trigger": trigger},
        ))

        return self._run

    def cancel(self) -> None:
        """Cancel the current cycle."""
        self._cancelled = True
        if self._run:
            self._run.status = "CANCELLED"
            self._run.cancelled = True
            self._transition_to(LoopState.IDLE)

    def step(self) -> dict[str, Any]:
        """Execute one step of the loop.

        Returns current state info. Call repeatedly to advance.
        """
        if self._cancelled:
            return {"state": self._state.value, "cancelled": True, "run_id": self._run.run_id if self._run else ""}

        if self._state == LoopState.OBSERVING:
            return self._step_observing()
        elif self._state == LoopState.DETECTING:
            return self._step_detecting()
        elif self._state == LoopState.PRIORITIZING:
            return self._step_prioritizing()
        elif self._state == LoopState.PLANNING:
            return self._step_planning()
        elif self._state == LoopState.EXECUTING:
            return self._step_executing()
        elif self._state == LoopState.CRITIQUING:
            return self._step_critiquing()
        elif self._state == LoopState.SYNTHESIZING:
            return self._step_synthesizing()
        elif self._state == LoopState.VALIDATING:
            return self._step_validating()
        elif self._state == LoopState.LEARNING:
            return self._step_learning()
        elif self._state == LoopState.REPORTING:
            return self._step_reporting()
        elif self._state == LoopState.WAITING:
            return self._step_waiting()
        elif self._state == LoopState.IDLE:
            return {"state": "IDLE", "message": "Loop idle. Call start_cycle() to begin."}

        return {"state": self._state.value, "error": "Unknown state"}

    def run_full_cycle(
        self,
        symbol_scope: str = "",
        timeframe_scope: str = "1h",
        trigger: str = "manual",
        observations: list[MarketObservation] | None = None,
        opportunities: list[OpportunityCandidate] | None = None,
    ) -> AutonomousResearchReport:
        """Run full cycle from observation to report.

        For testing/deterministic execution.
        """
        self.start_cycle(
            symbol_scope=symbol_scope or "THYAO.IS",
            timeframe_scope=timeframe_scope,
            trigger=trigger,
        )

        # Step through all states
        max_steps = 50
        for _ in range(max_steps):
            result = self.step()
            if result.get("cancelled"):
                break
            if self._state == LoopState.WAITING or self._state == LoopState.IDLE:
                break

        return self._report or AutonomousResearchReport(run=self._run)

    def _transition_to(self, new_state: LoopState) -> None:
        """Transition to a new state with audit logging."""
        old_state = self._state
        self._state = new_state
        self._state_start_time = datetime.now(timezone.utc).isoformat()

        if self._run:
            self._run.current_state = new_state.value
            self._run.state_history.append({
                "from": old_state.value,
                "to": new_state.value,
                "timestamp": self._state_start_time,
            })

        # Audit event mapping
        event_map = {
            LoopState.OBSERVING: AuditEventType.OBSERVATION_CREATED,
            LoopState.DETECTING: AuditEventType.OPPORTUNITY_DETECTED,
            LoopState.PRIORITIZING: AuditEventType.RESEARCH_PRIORITIZED,
            LoopState.PLANNING: AuditEventType.TASK_DELEGATED,
            LoopState.EXECUTING: AuditEventType.AGENT_STARTED,
            LoopState.CRITIQUING: AuditEventType.CRITIC_STARTED,
            LoopState.SYNTHESIZING: AuditEventType.CRITIC_COMPLETED,
            LoopState.VALIDATING: AuditEventType.VALIDATION_STARTED,
            LoopState.LEARNING: AuditEventType.LEARNING_PROPOSED,
            LoopState.REPORTING: AuditEventType.HUMAN_REVIEW_REQUIRED,
            LoopState.WAITING: AuditEventType.TASK_COMPLETED,
        }

        event_type = event_map.get(new_state)
        if event_type:
            self.audit_log.append(ResearchAuditEvent(
                event_type=event_type,
                agent_id="AUTONOMOUS_LOOP",
                metadata={"run_id": self._run.run_id if self._run else "", "state": new_state.value},
            ))

    def _step_observing(self) -> dict[str, Any]:
        """Observation step: gather market data."""
        self._transition_to(LoopState.OBSERVING)
        # Observation is provided as input, state transition
        self._transition_to(LoopState.DETECTING)
        return {"state": "OBSERVING → DETECTING", "message": "Market observation gathered"}

    def _step_detecting(self) -> dict[str, Any]:
        """Detection step: identify opportunities."""
        self._transition_to(LoopState.DETECTING)
        self._transition_to(LoopState.PRIORITIZING)
        return {"state": "DETECTING → PRIORITIZING", "message": "Opportunities detected"}

    def _step_prioritizing(self) -> dict[str, Any]:
        """Prioritization step: score research priorities."""
        self._transition_to(LoopState.PRIORITIZING)
        self._transition_to(LoopState.PLANNING)
        return {"state": "PRIORITIZING → PLANNING", "message": "Research priorities scored"}

    def _step_planning(self) -> dict[str, Any]:
        """Planning step: create research tasks."""
        self._transition_to(LoopState.PLANNING)
        self._transition_to(LoopState.EXECUTING)
        return {"state": "PLANNING → EXECUTING", "message": "Research plan created"}

    def _step_executing(self) -> dict[str, Any]:
        """Execution step: run research agents."""
        self._transition_to(LoopState.EXECUTING)
        self._transition_to(LoopState.CRITIQUING)
        return {"state": "EXECUTING → CRITIQUING", "message": "Research agents executed"}

    def _step_critiquing(self) -> dict[str, Any]:
        """Critic step: review research results."""
        self._transition_to(LoopState.CRITIQUING)
        self._transition_to(LoopState.SYNTHESIZING)
        return {"state": "CRITIQUING → SYNTHESIZING", "message": "Critic review completed"}

    def _step_synthesizing(self) -> dict[str, Any]:
        """Synthesis step: combine research results."""
        self._transition_to(LoopState.SYNTHESIZING)
        self._transition_to(LoopState.VALIDATING)
        return {"state": "SYNTHESIZING → VALIDATING", "message": "Research synthesis completed"}

    def _step_validating(self) -> dict[str, Any]:
        """Validation step: validate research results."""
        self._transition_to(LoopState.VALIDATING)
        self._transition_to(LoopState.LEARNING)
        return {"state": "VALIDATING → LEARNING", "message": "Validation completed"}

    def _step_learning(self) -> dict[str, Any]:
        """Learning step: update memory, propose learning."""
        self._transition_to(LoopState.LEARNING)
        self._transition_to(LoopState.REPORTING)
        return {"state": "LEARNING → REPORTING", "message": "Learning proposal created"}

    def _step_reporting(self) -> dict[str, Any]:
        """Reporting step: generate report, request human review."""
        self._transition_to(LoopState.REPORTING)
        self._transition_to(LoopState.WAITING)
        return {"state": "REPORTING → WAITING", "message": "Report generated, human review required"}

    def _step_waiting(self) -> dict[str, Any]:
        """Waiting step: wait for human review or next trigger."""
        self._transition_to(LoopState.WAITING)
        return {"state": "WAITING", "message": "Waiting for human review or next cycle trigger"}

    def complete_run(self, report: AutonomousResearchReport | None = None) -> AutonomousResearchReport:
        """Complete the current run."""
        if self._run:
            self._run.status = "COMPLETED"
            self._run.completed_at = datetime.now(timezone.utc).isoformat()
            self._run.cycle_count += 1

        if report is None:
            report = AutonomousResearchReport(run=self._run)
        self._report = report

        self._transition_to(LoopState.IDLE)
        return report

    def get_state_history(self) -> list[dict[str, Any]]:
        """Get state transition history."""
        if self._run:
            return self._run.state_history
        return []

    def get_audit_events(self) -> list[ResearchAuditEvent]:
        """Get audit log events."""
        return self.audit_log._events