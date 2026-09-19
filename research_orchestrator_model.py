# -*- coding: utf-8 -*-
"""Phase I — Agent Health + Runtime Diagnostics.

Lightweight health model on top of existing AgentRuntime.
Tracks readiness, failures, timeouts, data dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass
class AgentHealth:
    """Health + diagnostics for a research agent."""
    agent_id: str
    agent_name: str
    status: HealthStatus = HealthStatus.READY
    last_run: str = ""
    last_success: str = ""
    last_failure: str = ""
    failure_count: int = 0
    timeout_count: int = 0
    empty_output_count: int = 0
    unavailable_dependency_count: int = 0
    runtime_provider: str = "hermes"
    execution_duration_ms: int = 0
    health_reason: str = ""
    data_dependency_failures: list[str] = field(default_factory=list)
    error_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "last_run": self.last_run,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "empty_output_count": self.empty_output_count,
            "unavailable_dependency_count": self.unavailable_dependency_count,
            "runtime_provider": self.runtime_provider,
            "execution_duration_ms": self.execution_duration_ms,
            "health_reason": self.health_reason,
            "data_dependency_failures": self.data_dependency_failures,
            "error_history": self.error_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def mark_success(self, duration_ms: int = 0) -> None:
        self.status = HealthStatus.READY
        self.last_success = datetime.now(timezone.utc).isoformat()
        self.last_run = self.last_success
        self.execution_duration_ms = duration_ms
        self.health_reason = ""

    def mark_failure(self, reason: str = "", timeout: bool = False) -> None:
        self.failure_count += 1
        if timeout:
            self.timeout_count += 1
        self.last_failure = datetime.now(timezone.utc).isoformat()
        self.last_run = self.last_failure
        self.status = HealthStatus.FAILED
        self.health_reason = reason
        self.error_history.append({
            "timestamp": self.last_failure,
            "reason": reason,
            "timeout": timeout,
        })

    def mark_unavailable(self, reason: str = "") -> None:
        self.status = HealthStatus.UNAVAILABLE
        self.health_reason = reason
        self.unavailable_dependency_count += 1
        self.last_run = datetime.now(timezone.utc).isoformat()

    def mark_degraded(self, reason: str = "") -> None:
        self.status = HealthStatus.DEGRADED
        self.health_reason = reason
        self.last_run = datetime.now(timezone.utc).isoformat()

    def reset_health(self) -> None:
        self.status = HealthStatus.READY
        self.health_reason = ""
        self.error_history.clear()


# ═══════════════════════════════════════════════════════════════════
# Research Task Abstraction
# ═══════════════════════════════════════════════════════════════════

class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    WAITING_REVIEW = "waiting_review"


@dataclass
class ResearchTask:
    """Unified research task on top of existing AgentRuntime.

    Does NOT replace AgentRuntime.
    Wraps agent execution with metadata, dependencies, provenance.
    """
    task_id: str
    task_type: str
    agent_id: str
    asset: str = ""
    timeframe: str = ""
    cutoff: str = ""
    context_id: str = ""
    priority: int = 0
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    dependencies: list[str] = field(default_factory=list)
    result_reference: str = ""
    failure_reference: str = ""
    config_hash: str = ""
    data_cutoff: str = ""
    provenance_node_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "agent_id": self.agent_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "cutoff": self.cutoff,
            "context_id": self.context_id,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dependencies": self.dependencies,
            "result_reference": self.result_reference,
            "failure_reference": self.failure_reference,
            "config_hash": self.config_hash,
            "data_cutoff": self.data_cutoff,
            "provenance_node_id": self.provenance_node_id,
        }