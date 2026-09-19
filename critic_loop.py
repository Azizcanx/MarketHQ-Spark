# -*- coding: utf-8 -*-
"""Critic Loop — Phase J2.

Critic challenge and agent revision loop.
Finite loops only — no infinite autonomous iteration.

Critic does NOT produce "truth" or "trade good/bad".
Critic performs RESEARCH QUALITY CONTROL only.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ChallengeType(Enum):
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CONTRADICTION = "CONTRADICTION"
    INSUFFICIENT_FEATURE = "INSUFFICIENT_FEATURE"
    STALE_CONTEXT = "STALE_CONTEXT"
    PROVENANCE_ISSUE = "PROVENANCE_ISSUE"
    CONCURRENCY_RISK = "CONCURRENCY_RISK"
    DATA_QUALITY = "DATA_QUALITY"


class CriticVerdict(Enum):
    ACCEPT = "ACCEPT"
    CHALLENGE = "CHALLENGE"
    REQUEST_REVISION = "REQUEST_REVISION"
    REJECT = "REJECT"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class CriticChallenge:
    """A critic challenge to an agent's evidence."""
    challenge_id: str = ""
    evidence_id: str = ""
    agent_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    challenge_type: ChallengeType = ChallengeType.UNSUPPORTED_CLAIM
    description: str = ""
    finding: str = ""
    severity: str = "medium"  # low | medium | high | critical
    revision_requested: bool = False
    created_at: str = ""
    resolved: bool = False
    resolution: str = ""

    def __post_init__(self) -> None:
        if not self.challenge_id:
            self.challenge_id = f"CHL-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "evidence_id": self.evidence_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "challenge_type": self.challenge_type.value,
            "description": self.description,
            "finding": self.finding,
            "severity": self.severity,
            "revision_requested": self.revision_requested,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }


@dataclass
class CriticResult:
    """Result of a critic review."""
    critic_id: str = ""
    evidence_id: str = ""
    agent_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    verdict: CriticVerdict = CriticVerdict.ACCEPT
    challenges: list[CriticChallenge] = field(default_factory=list)
    iteration: int = 0
    can_proceed: bool = True
    message: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.critic_id:
            self.critic_id = f"CRIT-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "critic_id": self.critic_id,
            "evidence_id": self.evidence_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "verdict": self.verdict.value,
            "challenge_count": len(self.challenges),
            "iteration": self.iteration,
            "can_proceed": self.can_proceed,
            "message": self.message,
            "created_at": self.created_at,
        }


class CriticLoop:
    """Critic challenge-revision loop with finite iteration limit.

    Agent → Evidence → Critic → Challenge → Agent Revision → Updated Evidence

    Maximum iterations enforced — no infinite loops.
    """

    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations = max_iterations
        self.iteration = 0
        self.challenges: list[CriticChallenge] = []
        self.results: list[CriticResult] = []
        self._loop_limit_reached = False

    def review(
        self,
        evidence_id: str,
        evidence_payload: dict[str, Any],
        agent_id: str = "",
        workspace_id: str = "",
        task_id: str = "",
    ) -> CriticResult:
        """Review evidence and return critic result."""
        self.iteration += 1

        if self.iteration > self.max_iterations:
            self._loop_limit_reached = True
            return CriticResult(
                evidence_id=evidence_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
                task_id=task_id,
                verdict=CriticVerdict.INSUFFICIENT,
                iteration=self.iteration,
                can_proceed=False,
                message="LOOP_LIMIT_REACHED",
            )

        # Perform review (deterministic quality checks)
        challenges = self._analyze_evidence(evidence_payload, evidence_id, agent_id, workspace_id, task_id)
        self.challenges.extend(challenges)
        verdict = CriticVerdict.ACCEPT if not challenges else CriticVerdict.CHALLENGE
        can_proceed = len(challenges) == 0

        result = CriticResult(
            evidence_id=evidence_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            task_id=task_id,
            verdict=verdict,
            challenges=challenges,
            iteration=self.iteration,
            can_proceed=can_proceed,
            message=f"Iteration {self.iteration}: {verdict.value}" + (" — loop limit reached" if self._loop_limit_reached else ""),
        )
        self.results.append(result)
        return result

    def request_revision(self, evidence_id: str) -> bool:
        """Mark a challenge as requesting revision."""
        for ch in self.challenges:
            if ch.evidence_id == evidence_id and not ch.resolved:
                ch.revision_requested = True
                return True
        return False

    def resolve_challenge(self, challenge_id: str, resolution: str = "") -> bool:
        """Resolve a challenge."""
        for ch in self.challenges:
            if ch.challenge_id == challenge_id:
                ch.resolved = True
                ch.resolution = resolution
                return True
        return False

    def _analyze_evidence(
        self,
        payload: dict[str, Any],
        evidence_id: str,
        agent_id: str,
        workspace_id: str,
        task_id: str,
    ) -> list[CriticChallenge]:
        """Analyze evidence for quality issues."""
        challenges = []

        # Check for unsupported claims
        confidence = payload.get("confidence", 0.0)
        if confidence > 0.8 and not payload.get("supporting_features"):
            challenges.append(CriticChallenge(
                evidence_id=evidence_id, agent_id=agent_id,
                workspace_id=workspace_id, task_id=task_id,
                challenge_type=ChallengeType.UNSUPPORTED_CLAIM,
                description="High confidence but no supporting features",
                finding="Evidence lacks feature support",
                severity="high",
                revision_requested=True,
            ))

        # Check for missing evidence
        if not payload.get("direction") or payload.get("direction") == "UNKNOWN":
            challenges.append(CriticChallenge(
                evidence_id=evidence_id, agent_id=agent_id,
                workspace_id=workspace_id, task_id=task_id,
                challenge_type=ChallengeType.MISSING_EVIDENCE,
                description="No clear direction in evidence",
                finding="Direction unclear or neutral",
                severity="medium",
                revision_requested=False,
            ))

        return challenges

    def is_limit_reached(self) -> bool:
        return self._loop_limit_reached

    def to_dict(self) -> dict[str, Any]:
        return {
            "critic_id": self.results[0].critic_id if self.results else "",
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "limit_reached": self._loop_limit_reached,
            "challenge_count": len(self.challenges),
            "result_count": len(self.results),
        }