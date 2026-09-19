# -*- coding: utf-8 -*-
"""Research Audit Event — Phase J1.

Append-only audit trail for research execution.
Tracks all state changes in the research workspace.

Audit log is immutable — old entries are never modified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuditEventType(Enum):
    WORKSPACE_CREATED = "WORKSPACE_CREATED"
    WORKSPACE_STATUS_CHANGED = "WORKSPACE_STATUS_CHANGED"
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_DELEGATED = "TASK_DELEGATED"
    DELEGATION_ACCEPTED = "DELEGATION_ACCEPTED"
    DELEGATION_COMPLETED = "DELEGATION_COMPLETED"
    DELEGATION_FAILED = "DELEGATION_FAILED"
    AGENT_REGISTERED = "AGENT_REGISTERED"
    AGENT_HEALTH_CHANGED = "AGENT_HEALTH_CHANGED"
    AGENT_CAPABILITY_CHANGED = "AGENT_CAPABILITY_CHANGED"
    AGENT_LIFECYCLE_CHANGED = "AGENT_LIFECYCLE_CHANGED"
    TEAM_CREATED = "TEAM_CREATED"
    TEAM_MEMBER_ADDED = "TEAM_MEMBER_ADDED"
    TEAM_MEMBER_REMOVED = "TEAM_MEMBER_REMOVED"
    TEAM_STATUS_CHANGED = "TEAM_STATUS_CHANGED"
    MESSAGE_SENT = "MESSAGE_SENT"
    HANDOFF_CREATED = "HANDOFF_CREATED"
    ROUTING_DECISION = "ROUTING_DECISION"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    ARTIFACT_VERSION_CHANGED = "ARTIFACT_VERSION_CHANGED"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED"
    CLAIM_STATUS_CHANGED = "CLAIM_STATUS_CHANGED"
    OBSERVATION_CREATED = "OBSERVATION_CREATED"

    RUNTIME_SELECTED = "RUNTIME_SELECTED"
    RUNTIME_STARTED = "RUNTIME_STARTED"
    RUNTIME_COMPLETED = "RUNTIME_COMPLETED"
    RUNTIME_FAILED = "RUNTIME_FAILED"
    RUNTIME_TIMEOUT = "RUNTIME_TIMEOUT"
    RUNTIME_CANCELLED = "RUNTIME_CANCELLED"
    RUNTIME_RETRY = "RUNTIME_RETRY"
    ROUTING_REJECTED = "ROUTING_REJECTED"
    FALLBACK_SELECTED = "FALLBACK_SELECTED"
    OUTPUT_VALIDATED = "OUTPUT_VALIDATED"
    OUTPUT_REJECTED = "OUTPUT_REJECTED"
    PROVIDER_HEALTH_CHANGED = "PROVIDER_HEALTH_CHANGED"
    EXECUTION_DUPLICATE = "EXECUTION_DUPLICATE"
    IDENTITY_CHECK = "IDENTITY_CHECK"
    PROVIDER_REGISTERED = "PROVIDER_REGISTERED"
    PROVIDER_UNREGISTERED = "PROVIDER_UNREGISTERED"

    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    CRITIC_STARTED = "CRITIC_STARTED"
    CRITIC_COMPLETED = "CRITIC_COMPLETED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    MEMORY_UPDATED = "MEMORY_UPDATED"
    LEARNING_PROPOSED = "LEARNING_PROPOSED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    BASELINE_PROTECTED = "BASELINE_PROTECTED"
    WEIGHT_PROPOSAL = "WEIGHT_PROPOSAL"
    DATA_QUALITY_CHECK = "DATA_QUALITY_CHECK"
    # Phase J4: Autonomous Research Loop
    CYCLE_STARTED = "CYCLE_STARTED"
    CYCLE_COMPLETED = "CYCLE_COMPLETED"
    CYCLE_CANCELLED = "CYCLE_CANCELLED"
    OPPORTUNITY_DETECTED = "OPPORTUNITY_DETECTED"
    RESEARCH_PRIORITIZED = "RESEARCH_PRIORITIZED"
    AGENT_STARTED = "AGENT_STARTED"


@dataclass
class ResearchAuditEvent:
    """Immutable audit event for research execution.

    Every audit event records:
    - what happened
    - when it happened
    - who/what triggered it
    - the context (workspace, task, agent)
    - the before/after state
    - provenance reference

    Audit log is append-only. Old entries are never modified.
    """
    event_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    event_type: AuditEventType = AuditEventType.WORKSPACE_CREATED
    previous_state: str = ""
    new_state: str = ""
    timestamp: str = ""
    provenance_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""  # who triggered (for human actions)
    source_ref: str = ""  # reference to source of the event

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "event_type": self.event_type.value,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "timestamp": self.timestamp,
            "provenance_ref": self.provenance_ref,
            "metadata": self.metadata,
            "user_id": self.user_id,
            "source_ref": self.source_ref,
        }


class AuditLog:
    """Append-only audit log for a workspace."""

    def __init__(self) -> None:
        self._events: list[ResearchAuditEvent] = []

    def append(self, event: ResearchAuditEvent) -> None:
        self._events.append(event)

    def get_events(self, event_type: AuditEventType | None = None) -> list[ResearchAuditEvent]:
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.event_type == event_type]

    def get_events_for_workspace(self, workspace_id: str) -> list[ResearchAuditEvent]:
        return [e for e in self._events if e.workspace_id == workspace_id]

    def get_events_for_agent(self, agent_id: str) -> list[ResearchAuditEvent]:
        return [e for e in self._events if e.agent_id == agent_id]

    def get_state_history(self, entity_id: str) -> list[ResearchAuditEvent]:
        """Get all state changes for an entity."""
        return [
            e for e in self._events
            if e.previous_state or e.new_state
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": len(self._events),
            "events": [e.to_dict() for e in self._events],
        }
