# -*- coding: utf-8 -*-
"""Research Workspace — Phase J1.

Shared research context for agent collaboration.
References Brain, observations, artifacts, claims without duplicating them.

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WorkspaceStatus(Enum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class WorkspaceParticipant:
    agent_id: str
    role: str  # RESEARCHER | CRITIC | SYNTHESIZER | REVIEWER
    joined_at: str = ""


@dataclass
class ResearchWorkspace:
    """Shared research context for a single research run.

    All agent executions, tasks, artifacts, observations, claims,
    opportunities, and setups within a research run share this workspace.

    NOT a trading workspace. Research-only context.
    """
    workspace_id: str = ""
    research_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    cutoff: str = ""
    created_at: str = ""
    participants: list[WorkspaceParticipant] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)       # task_ids
    artifacts: list[str] = field(default_factory=list)    # artifact_ids
    observations: list[str] = field(default_factory=list) # observation_ids
    claims: list[str] = field(default_factory=list)       # claim_ids
    opportunities: list[str] = field(default_factory=list) # opportunity_ids
    setups: list[str] = field(default_factory=list)        # setup_ids
    status: WorkspaceStatus = WorkspaceStatus.CREATED
    failure_reason: str = ""
    # Phase J2 additions
    context_version: int = 1
    max_messages: int = 100
    message_count: int = 0

    def __post_init__(self) -> None:
        if not self.workspace_id:
            self.workspace_id = f"WS-{uuid.uuid4().hex[:10].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "research_id": self.research_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "cutoff": self.cutoff,
            "created_at": self.created_at,
            "participants": [p.__dict__ for p in self.participants],
            "tasks": self.tasks,
            "artifacts": self.artifacts,
            "observations": self.observations,
            "claims": self.claims,
            "opportunities": self.opportunities,
            "setups": self.setups,
            "status": self.status.value,
            "failure_reason": self.failure_reason,
            "context_version": self.context_version,
            "max_messages": self.max_messages,
            "message_count": self.message_count,
        }

    def add_participant(self, agent_id: str, role: str) -> None:
        self.participants.append(WorkspaceParticipant(
            agent_id=agent_id, role=role,
            joined_at=datetime.now(timezone.utc).isoformat(),
        ))

    def add_task(self, task_id: str) -> None:
        if task_id not in self.tasks:
            self.tasks.append(task_id)

    def add_artifact(self, artifact_id: str) -> None:
        if artifact_id not in self.artifacts:
            self.artifacts.append(artifact_id)

    def increment_message_count(self) -> None:
        self.message_count += 1

    def can_send_message(self) -> bool:
        return self.message_count < self.max_messages

    def bump_context_version(self) -> None:
        self.context_version += 1

    def transition_to(self, new_status: WorkspaceStatus) -> None:
        self.status = new_status


# Convenience factory
def create_workspace(
    research_id: str,
    symbol: str,
    timeframe: str,
    cutoff: str,
) -> ResearchWorkspace:
    ws = ResearchWorkspace(
        research_id=research_id,
        symbol=symbol,
        timeframe=timeframe,
        cutoff=cutoff,
    )
    ws.transition_to(WorkspaceStatus.INITIALIZING)
    ws.transition_to(WorkspaceStatus.ACTIVE)
    return ws
