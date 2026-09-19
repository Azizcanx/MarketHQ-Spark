# -*- coding: utf-8 -*-
"""Agent Lifecycle — Phase J1.

Agent lifecycle state machine.
Separates identity (AgentProfile) from runtime state (AgentHealth) from execution state (AgentExecution).

States:
  REGISTERED → READY → RUNNING → COMPLETED
                          → FAILED
                          → DEGRADED

Lifecycle transitions are audited via ResearchAuditEvent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentLifecycleState(Enum):
    REGISTERED = "REGISTERED"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    DISABLED = "DISABLED"


@dataclass
class AgentExecution:
    """Single execution state for an agent.

    Tracks one execution instance.
    Distinct from AgentProfile (identity) and AgentHealth (runtime health).
    """
    execution_id: str = ""
    agent_id: str = ""
    agent_version: str = ""
    task_id: str = ""
    workspace_id: str = ""
    status: AgentLifecycleState = AgentLifecycleState.REGISTERED
    started_at: str = ""
    completed_at: str = ""
    result_reference: str = ""
    error_type: str = ""
    error_message: str = ""
    feature_availability: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id:
            self.execution_id = f"EXE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{id(self)}"

    def transition_to(self, new_state: AgentLifecycleState) -> None:
        self.status = new_state
        if new_state in (AgentLifecycleState.COMPLETED, AgentLifecycleState.FAILED):
            self.completed_at = datetime.now(timezone.utc).isoformat()
        if new_state == AgentLifecycleState.RUNNING:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def mark_error(self, error_type: str, error_message: str) -> None:
        self.status = AgentLifecycleState.FAILED
        self.error_type = error_type
        self.error_message = error_message
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_reference": self.result_reference,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "feature_availability": self.feature_availability,
            "metadata": self.metadata,
        }


class AgentLifecycleManager:
    """Manages agent lifecycle transitions with audit logging."""

    VALID_TRANSITIONS = {
        AgentLifecycleState.REGISTERED: {AgentLifecycleState.READY},
        AgentLifecycleState.READY: {AgentLifecycleState.RUNNING, AgentLifecycleState.DISABLED},
        AgentLifecycleState.RUNNING: {
            AgentLifecycleState.COMPLETED,
            AgentLifecycleState.FAILED,
            AgentLifecycleState.DEGRADED,
        },
        AgentLifecycleState.DEGRADED: {AgentLifecycleState.READY, AgentLifecycleState.FAILED},
        AgentLifecycleState.FAILED: {AgentLifecycleState.RECOVERING, AgentLifecycleState.DISABLED},
        AgentLifecycleState.RECOVERING: {AgentLifecycleState.READY, AgentLifecycleState.FAILED},
        AgentLifecycleState.DISABLED: set(),  # terminal
        AgentLifecycleState.COMPLETED: set(),  # terminal
    }

    def __init__(self) -> None:
        self._executions: dict[str, AgentExecution] = {}

    def create_execution(
        self,
        agent_id: str,
        agent_version: str,
        task_id: str,
        workspace_id: str,
    ) -> AgentExecution:
        execution = AgentExecution(
            agent_id=agent_id,
            agent_version=agent_version,
            task_id=task_id,
            workspace_id=workspace_id,
        )
        execution.transition_to(AgentLifecycleState.REGISTERED)
        self._executions[execution.execution_id] = execution
        return execution

    def get_execution(self, execution_id: str) -> AgentExecution | None:
        return self._executions.get(execution_id)

    def transition(
        self,
        execution_id: str,
        new_state: AgentLifecycleState,
    ) -> AgentExecution | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None

        allowed = self.VALID_TRANSITIONS.get(execution.status, set())
        if new_state not in allowed:
            return None

        execution.transition_to(new_state)
        return execution

    def is_valid_transition(
        self,
        from_state: AgentLifecycleState,
        to_state: AgentLifecycleState,
    ) -> bool:
        allowed = self.VALID_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    def get_executions_for_agent(self, agent_id: str) -> list[AgentExecution]:
        return [e for e in self._executions.values() if e.agent_id == agent_id]

    def get_active_executions(self) -> list[AgentExecution]:
        return [
            e for e in self._executions.values()
            if e.status in (AgentLifecycleState.RUNNING, AgentLifecycleState.DEGRADED)
        ]
