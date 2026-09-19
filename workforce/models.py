"""Workforce domain models — J10 Agent Workforce Architecture.

Workers, Tasks, Teams, Artifacts, Approvals.
Extends existing AzizBusiness agents without replacing them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────

class WorkerStatus(str, Enum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REASSIGNED = "REASSIGNED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MessageType(str, Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    EVIDENCE = "EVIDENCE"
    CHALLENGE = "CHALLENGE"
    HANDOFF = "HANDOFF"
    STATUS = "STATUS"
    CLARIFICATION = "CLARIFICATION"
    REVISION_REQUEST = "REVISION_REQUEST"


class ApprovalAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


class WorkerHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


# ─── Worker Profile ───────────────────────────────────────────────────────

class AgentProfile(BaseModel):
    """First-class workforce worker identity."""

    agent_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12].upper())
    name: str
    display_name: str = ""
    description: str = ""
    role: str = ""
    department: str = "research"
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    strategy_families: list[str] = Field(default_factory=list)
    supported_symbols: list[str] = Field(default_factory=list)
    supported_timeframes: list[str] = Field(default_factory=list)
    status: WorkerStatus = WorkerStatus.OFFLINE
    health: WorkerHealth = WorkerHealth.UNKNOWN
    reliability: float = 0.5  # 0.0 – 1.0, operational metric only
    workload: int = 0
    max_concurrent_tasks: int = 4
    ai_policy: str = "FREE_FIRST"
    workspace_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    # Operational
    current_task_id: Optional[str] = None
    queue_size: int = 0
    last_heartbeat: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_duration_ms: int = 0
    timeout_count: int = 0
    retry_count: int = 0
    provider_failures: int = 0
    permissions: list[str] = Field(default_factory=lambda: ["WORKER"])
    ai_provider_id: Optional[str] = None  # override AI provider for this worker

    def is_available(self) -> bool:
        return self.status == WorkerStatus.AVAILABLE and self.workload < self.max_concurrent_tasks

    def effective_policy(self) -> str:
        return self.ai_policy or "FREE_FIRST"


# ─── Workforce Task ────────────────────────────────────────────────────────

class WorkforceTask(BaseModel):
    """First-class task — the fundamental unit of work."""

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    title: str = ""
    description: str = ""
    created_by: str = "patron"
    owner: str = "patron"
    assigned_agent: Optional[str] = None
    assigned_team: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.CREATED
    task_type: str = "research"
    input_data: dict[str, Any] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    expected_output: str = ""
    dependencies: list[str] = Field(default_factory=list)
    parent_task_id: Optional[str] = None
    child_task_ids: list[str] = Field(default_factory=list)
    deadline: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[dict[str, Any]] = None
    artifacts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    ai_policy: str = "FREE_FIRST"
    workspace_id: Optional[str] = None
    audit_id: Optional[str] = None
    # Execution tracking
    execution_id: Optional[str] = None
    attempt_id: Optional[str] = None
    assigned_at: Optional[str] = None
    heartbeats: list[str] = Field(default_factory=list)

    def can_transition(self, new_status: TaskStatus) -> bool:
        """Enforce valid status transitions."""
        transitions: dict[TaskStatus, list[TaskStatus]] = {
            TaskStatus.CREATED: [TaskStatus.QUEUED, TaskStatus.ASSIGNED, TaskStatus.COMPLETED, TaskStatus.CANCELLED],
            TaskStatus.QUEUED: [TaskStatus.ASSIGNED, TaskStatus.REASSIGNED, TaskStatus.CANCELLED],
            TaskStatus.ASSIGNED: [TaskStatus.ACCEPTED, TaskStatus.RUNNING, TaskStatus.REASSIGNED, TaskStatus.CANCELLED],
            TaskStatus.ACCEPTED: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.BLOCKED],
            TaskStatus.RUNNING: [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.WAITING, TaskStatus.BLOCKED],
            TaskStatus.WAITING: [TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.FAILED],
            TaskStatus.BLOCKED: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
            TaskStatus.REVIEW: [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REASSIGNED],
            TaskStatus.COMPLETED: [],
            TaskStatus.FAILED: [TaskStatus.QUEUED, TaskStatus.CANCELLED],
            TaskStatus.CANCELLED: [],
            TaskStatus.EXPIRED: [],
            TaskStatus.REASSIGNED: [TaskStatus.QUEUED],
        }
        return new_status in transitions.get(self.status, [])


# ─── Delegation ────────────────────────────────────────────────────────────

class Delegation(BaseModel):
    """Parent → child task delegation."""

    delegation_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    parent_task_id: str
    child_task_id: str
    delegating_agent: str
    target_agent: str
    reason: str = ""
    requirements: list[str] = Field(default_factory=list)
    max_depth: int = 3
    current_depth: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Team ──────────────────────────────────────────────────────────────────

class TeamStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISBANDED = "DISBANDED"


class Team(BaseModel):
    """First-class team — department / project team."""

    team_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    name: str
    description: str = ""
    lead_agent: Optional[str] = None
    members: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    workload: int = 0
    workspace_id: Optional[str] = None
    permissions: list[str] = Field(default_factory=lambda: ["WORKER"])
    task_queue: list[str] = Field(default_factory=list)
    status: TeamStatus = TeamStatus.ACTIVE
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Message ───────────────────────────────────────────────────────────────

class WorkerMessage(BaseModel):
    """Worker-to-worker communication."""

    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    sender: str
    receiver: str
    task_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    message_type: MessageType = MessageType.REQUEST
    workspace_version: int = 1
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ─── Artifact ──────────────────────────────────────────────────────────────

class Artifact(BaseModel):
    """Worker-produced output artifact."""

    artifact_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    task_id: str
    agent_id: str
    artifact_type: str  # report, evidence, json, chart, document
    version: int = 1
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: dict[str, Any] = Field(default_factory=dict)


# ─── Approval ──────────────────────────────────────────────────────────────

class Approval(BaseModel):
    """Human approval request."""

    approval_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10].upper())
    task_id: str
    agent_id: str
    reason: str = ""
    action: str = ""
    result: Optional[dict[str, Any]] = None
    evidence: list[str] = Field(default_factory=list)
    risk_level: str = "LOW"
    uncertainty: float = 0.5
    requested_action: str = ""
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, REVISION_REQUESTED
    requested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision: Optional[str] = None