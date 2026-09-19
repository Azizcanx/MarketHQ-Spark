# -*- coding: utf-8 -*-
"""Team Synthesis — Phase J2.

Collaborative synthesis of agent evidence into team research result.
Synthesis preserves conflicts, does NOT declare automatic truth.

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SynthesisStatus(Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    CONFLICTED = "CONFLICTED"
    FAILED = "FAILED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class TeamResearchResult:
    """Collaborative research result from a team of agents.

    Confidence = research evidence consistency/confidence, NOT win probability.
    Conflicts are preserved, not resolved automatically.
    """
    result_id: str = ""
    team_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    participating_agents: list[str] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    neutral_evidence: list[dict[str, Any]] = field(default_factory=list)
    unavailable_evidence: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    thesis: str = ""
    direction: str = "NEUTRAL"
    confidence: float = 0.0
    artifacts: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    critic_findings: list[str] = field(default_factory=list)
    revision_count: int = 0
    status: SynthesisStatus = SynthesisStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.result_id:
            self.result_id = f"TRR-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def add_evidence(self, agent_id: str, evidence: dict[str, Any], disposition: str = "NEUTRAL") -> None:
        entry = {"agent_id": agent_id, **evidence}
        if disposition == "SUPPORTING":
            self.supporting_evidence.append(entry)
        elif disposition == "CONFLICTING":
            self.conflicting_evidence.append(entry)
        elif disposition == "UNAVAILABLE":
            self.unavailable_evidence.append(entry)
        else:
            self.neutral_evidence.append(entry)

    def compute_confidence(self) -> float:
        """Compute evidence confidence (NOT win probability).

        Based on consistency of supporting vs conflicting evidence.
        """
        total = len(self.supporting_evidence) + len(self.conflicting_evidence) + len(self.neutral_evidence)
        if total == 0:
            return 0.0
        support_score = len(self.supporting_evidence)
        conflict_score = len(self.conflicting_evidence) * 0.3
        neutral_score = len(self.neutral_evidence) * 0.5
        return round(min(1.0, (support_score + neutral_score) / (total + 0.001)), 4)

    def has_conflicts(self) -> bool:
        return len(self.conflicting_evidence) > 0

    def is_partial(self) -> bool:
        return len(self.unavailable_evidence) > 0 or len(self.conflicting_evidence) > 0

    def transition_to(self, new_status: SynthesisStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "team_id": self.team_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "participating_agents": self.participating_agents,
            "supporting_count": len(self.supporting_evidence),
            "conflicting_count": len(self.conflicting_evidence),
            "neutral_count": len(self.neutral_evidence),
            "unavailable_count": len(self.unavailable_evidence),
            "unresolved_questions": self.unresolved_questions,
            "thesis": self.thesis,
            "direction": self.direction,
            "confidence": self.confidence,
            "artifacts": self.artifacts,
            "critic_findings": self.critic_findings,
            "revision_count": self.revision_count,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }