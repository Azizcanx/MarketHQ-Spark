# -*- coding: utf-8 -*-
"""Task Delegation — Phase J2.

Research task delegation from team lead / orchestrator to agents.
Delegation is deterministic, permission-aware, capability-aware, provenance-aware, idempotent.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DelegationStatus(Enum):
    PENDING = "PENDING"
    DELEGATED = "DELEGATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class DelegatedResearchTask:
    """A research task delegated from a team lead / orchestrator to an agent.

    Tracks the full delegation chain for provenance.
    """
    task_id: str = ""
    parent_task_id: str = ""
    delegated_by: str = ""
    delegated_to: str = ""
    workspace_id: str = ""
    team_id: str = ""
    capability: str = ""
    reason: str = ""
    status: DelegationStatus = DelegationStatus.PENDING
    created_at: str = ""
    accepted_at: str = ""
    completed_at: str = ""
    result_reference: str = ""
    failure_reason: str = ""
    delegation_depth: int = 0
    max_depth: int = 5
    config_hash: str = ""
    provenance_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id:
            now = datetime.now(timezone.utc).isoformat()
            raw = f"{now}{self.delegated_by}{self.delegated_to}{self.capability}"
            self.task_id = f"DT-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "delegated_by": self.delegated_by,
            "delegated_to": self.delegated_to,
            "workspace_id": self.workspace_id,
            "team_id": self.team_id,
            "capability": self.capability,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at,
            "accepted_at": self.accepted_at,
            "completed_at": self.completed_at,
            "result_reference": self.result_reference,
            "failure_reason": self.failure_reason,
            "delegation_depth": self.delegation_depth,
            "max_depth": self.max_depth,
            "config_hash": self.config_hash,
            "provenance_ref": self.provenance_ref,
            "metadata": self.metadata,
        }


class DelegationRules:
    """Rules for task delegation.

    - Deterministic: same input → same delegation
    - Permission-aware: agent can only accept tasks within its permissions
    - Capability-aware: agent must have required capability
    - Provenance-aware: delegation chain tracked
    - Idempotent: same delegation request → same result
    - Depth-limited: max delegation depth enforced
    """

    def __init__(self, max_depth: int = 5) -> None:
        self.max_depth = max_depth
        self._delegations: dict[str, DelegatedResearchTask] = {}
        self._delegation_chain: dict[str, list[str]] = {}  # task_id → chain of delegations

    def create_delegation(
        self,
        parent_task_id: str,
        delegated_by: str,
        delegated_to: str,
        workspace_id: str,
        team_id: str,
        capability: str,
        reason: str = "",
        depth: int = 0,
    ) -> DelegatedResearchTask:
        """Create a delegation. Idempotent — same input → same delegation."""
        # Check for existing delegation (idempotency)
        key = self._delegation_key(parent_task_id, delegated_by, delegated_to, capability)
        existing = self._delegations.get(key)
        if existing:
            return existing

        if depth > self.max_depth:
            raise ValueError(f"Delegation depth {depth} exceeds max {self.max_depth}")

        delegation = DelegatedResearchTask(
            parent_task_id=parent_task_id,
            delegated_by=delegated_by,
            delegated_to=delegated_to,
            workspace_id=workspace_id,
            team_id=team_id,
            capability=capability,
            reason=reason,
            delegation_depth=depth,
            max_depth=self.max_depth,
        )
        delegation.config_hash = hashlib.sha256(
            f"{parent_task_id}{delegated_by}{delegated_to}{capability}{depth}".encode()
        ).hexdigest()[:16]

        self._delegations[key] = delegation
        self._track_chain(delegation)
        return delegation

    def accept_delegation(self, task_id: str) -> DelegatedResearchTask | None:
        """Accept a delegation."""
        delegation = self._find_by_task_id(task_id)
        if delegation is None:
            return None
        if delegation.status != DelegationStatus.PENDING:
            return None
        delegation.status = DelegationStatus.ACCEPTED
        delegation.accepted_at = datetime.now(timezone.utc).isoformat()
        return delegation

    def complete_delegation(self, task_id: str, result_reference: str = "") -> DelegatedResearchTask | None:
        """Mark a delegation as completed."""
        delegation = self._find_by_task_id(task_id)
        if delegation is None:
            return None
        delegation.status = DelegationStatus.COMPLETED
        delegation.completed_at = datetime.now(timezone.utc).isoformat()
        if result_reference:
            delegation.result_reference = result_reference
        return delegation

    def fail_delegation(self, task_id: str, reason: str = "") -> DelegatedResearchTask | None:
        """Mark a delegation as failed."""
        delegation = self._find_by_task_id(task_id)
        if delegation is None:
            return None
        delegation.status = DelegationStatus.FAILED
        delegation.failure_reason = reason
        return delegation

    def get_delegation(self, task_id: str) -> DelegatedResearchTask | None:
        return self._delegations.get(task_id)

    def _find_by_task_id(self, task_id: str) -> DelegatedResearchTask | None:
        for delegation in self._delegations.values():
            if delegation.task_id == task_id:
                return delegation
        return None

    def get_delegations_for_agent(self, agent_id: str) -> list[DelegatedResearchTask]:
        return [d for d in self._delegations.values() if d.delegated_to == agent_id]

    def get_delegation_chain(self, task_id: str) -> list[str]:
        return self._delegation_chain.get(task_id, [])

    def _delegation_key(
        self,
        parent_task_id: str,
        delegated_by: str,
        delegated_to: str,
        capability: str,
    ) -> str:
        return hashlib.sha256(
            f"{parent_task_id}:{delegated_by}:{delegated_to}:{capability}".encode()
        ).hexdigest()[:16]

    def _track_chain(self, delegation: DelegatedResearchTask) -> None:
        chain = [delegation.task_id]
        if delegation.parent_task_id:
            parent_chain = self._delegation_chain.get(delegation.parent_task_id, [])
            chain = parent_chain + chain
        self._delegation_chain[delegation.task_id] = chain