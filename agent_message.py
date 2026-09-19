# -*- coding: utf-8 -*-
"""Agent Message Model — Phase J1.

Structured messaging between agents for research collaboration.
No arbitrary hidden state. Every message is provenance-aware.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageType(Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    EVIDENCE = "EVIDENCE"
    CHALLENGE = "CHALLENGE"
    HANDOFF = "HANDOFF"
    STATUS = "STATUS"
    CLARIFICATION = "CLARIFICATION"
    REVISION_REQUEST = "REVISION_REQUEST"


@dataclass
class AgentMessage:
    """Structured message between agents.

    Every message carries:
    - source (who sent it)
    - destination (who receives it)
    - workspace context
    - task context
    - structured payload
    - evidence references
    - provenance

    Message payloads must be structured and provenance-aware.
    No arbitrary hidden state.
    """
    message_id: str = ""
    sender_agent_id: str = ""
    recipient_agent_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    message_type: MessageType = MessageType.STATUS
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    provenance_ref: str = ""
    created_at: str = ""
    responded_to: str = ""  # message_id this responds to

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = f"MSG-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_agent_id": self.sender_agent_id,
            "recipient_agent_id": self.recipient_agent_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "message_type": self.message_type.value,
            "payload": self.payload,
            "evidence_refs": self.evidence_refs,
            "provenance_ref": self.provenance_ref,
            "created_at": self.created_at,
            "responded_to": self.responded_to,
        }


@dataclass
class AgentHandoff:
    """Handoff between agents for collaborative research.

    Source agent passes research context to destination agent.
    Provenance is preserved across the handoff.
    """
    handoff_id: str = ""
    source_agent_id: str = ""
    destination_agent_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    observation_refs: list[str] = field(default_factory=list)
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.handoff_id:
            self.handoff_id = f"HO-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "source_agent_id": self.source_agent_id,
            "destination_agent_id": self.destination_agent_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "artifact_refs": self.artifact_refs,
            "observation_refs": self.observation_refs,
            "context_snapshot": self.context_snapshot,
            "created_at": self.created_at,
        }
