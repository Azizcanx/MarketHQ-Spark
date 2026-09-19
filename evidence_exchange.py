# -*- coding: utf-8 -*-
"""Evidence Exchange — Phase J2.

Structured evidence exchange between research agents.
Conflicts are preserved — never silently resolved.

Evidence is always tied to source agent, version, workspace, task, feature snapshot.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceType(Enum):
    OBSERVATION = "OBSERVATION"
    ANALYSIS = "ANALYSIS"
    CHALLENGE = "CHALLENGE"
    REVISION = "REVISION"
    SYNTHESIS = "SYNTHESIS"
    CRITIC_FINDING = "CRITIC_FINDING"


class EvidenceDisposition(Enum):
    SUPPORTING = "SUPPORTING"
    CONFLICTING = "CONFLICTING"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class AgentEvidence:
    """Structured evidence from an agent.

    Every evidence item is tied to:
    - source agent + version
    - workspace + task
    - feature snapshot
    - provenance chain

    Evidence disposition:
    - SUPPORTING: agrees with team thesis
    - CONFLICTING: disagrees with team thesis
    - NEUTRAL: neither supports nor conflicts
    - UNAVAILABLE: evidence missing (feature unavailable)

    CONFLICTING evidence is NEVER silently resolved.
    """
    evidence_id: str = ""
    agent_id: str = ""
    agent_version: str = ""
    workspace_id: str = ""
    task_id: str = ""
    evidence_type: EvidenceType = EvidenceType.OBSERVATION
    disposition: EvidenceDisposition = EvidenceDisposition.NEUTRAL
    payload: dict[str, Any] = field(default_factory=dict)
    feature_snapshot_id: str = ""
    data_cutoff: str = ""
    provenance_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0  # evidence confidence, NOT probability
    created_at: str = ""
    context_version: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id:
            self.evidence_id = f"EVD-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "evidence_type": self.evidence_type.value,
            "disposition": self.disposition.value,
            "payload": self.payload,
            "feature_snapshot_id": self.feature_snapshot_id,
            "data_cutoff": self.data_cutoff,
            "provenance_refs": self.provenance_refs,
            "evidence_refs": self.evidence_refs,
            "artifact_refs": self.artifact_refs,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "context_version": self.context_version,
        }


@dataclass
class EvidenceExchange:
    """Evidence exchange within a team collaboration.

    Collects all evidence from team members,
    preserves conflicts, tracks dispositions.
    """
    exchange_id: str = ""
    workspace_id: str = ""
    team_id: str = ""
    task_id: str = ""
    evidence_items: list[AgentEvidence] = field(default_factory=list)
    supporting: list[str] = field(default_factory=list)      # evidence_ids
    conflicting: list[str] = field(default_factory=list)     # evidence_ids
    neutral: list[str] = field(default_factory=list)         # evidence_ids
    unavailable: list[str] = field(default_factory=list)     # evidence_ids
    context_version: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.exchange_id:
            self.exchange_id = f"EXC-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def add_evidence(self, evidence: AgentEvidence) -> None:
        self.evidence_items.append(evidence)
        eid = evidence.evidence_id
        disp = evidence.disposition
        if disp == EvidenceDisposition.SUPPORTING:
            if eid not in self.supporting:
                self.supporting.append(eid)
        elif disp == EvidenceDisposition.CONFLICTING:
            if eid not in self.conflicting:
                self.conflicting.append(eid)
        elif disp == EvidenceDisposition.UNAVAILABLE:
            if eid not in self.unavailable:
                self.unavailable.append(eid)
        else:
            if eid not in self.neutral:
                self.neutral.append(eid)

    def get_conflicts(self) -> list[AgentEvidence]:
        """Get all conflicting evidence items."""
        return [e for e in self.evidence_items if e.evidence_id in self.conflicting]

    def get_unavailable_count(self) -> int:
        return len(self.unavailable)

    def has_conflicts(self) -> bool:
        return len(self.conflicting) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_id": self.exchange_id,
            "workspace_id": self.workspace_id,
            "team_id": self.team_id,
            "task_id": self.task_id,
            "evidence_count": len(self.evidence_items),
            "supporting": len(self.supporting),
            "conflicting": len(self.conflicting),
            "neutral": len(self.neutral),
            "unavailable": len(self.unavailable),
            "context_version": self.context_version,
            "created_at": self.created_at,
        }


class ConflictPreserver:
    """Ensures conflicts between agents are never silently resolved.

    When agents disagree:
    - CONFLICTING evidence is preserved
    - No automatic "truth" declared
    - Team synthesis reports conflict explicitly
    - Human review can resolve
    """

    @staticmethod
    def classify_disposition(agent_result: dict[str, Any], team_thesis: str | None = None) -> EvidenceDisposition:
        """Classify evidence disposition based on agent result vs team thesis."""
        direction = agent_result.get("direction", "NEUTRAL")

        if team_thesis is None:
            return EvidenceDisposition.NEUTRAL

        if direction == team_thesis:
            return EvidenceDisposition.SUPPORTING
        elif direction == "NEUTRAL" or direction == "UNKNOWN":
            return EvidenceDisposition.NEUTRAL
        else:
            return EvidenceDisposition.CONFLICTING

    @staticmethod
    def preserve_conflicts(evidence_items: list[AgentEvidence]) -> list[AgentEvidence]:
        """Return all evidence, ensuring conflicts are flagged."""
        return evidence_items  # All evidence preserved, conflicts already tagged

    @staticmethod
    def get_conflict_summary(exchange: EvidenceExchange) -> dict[str, Any]:
        """Summarize conflicts in an exchange."""
        conflicts = exchange.get_conflicts()
        return {
            "total_evidence": len(exchange.evidence_items),
            "conflicting_count": len(conflicts),
            "conflicting_agents": [c.agent_id for c in conflicts],
            "has_conflicts": exchange.has_conflicts(),
            "unavailable_count": exchange.get_unavailable_count(),
        }