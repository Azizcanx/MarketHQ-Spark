# -*- coding: utf-8 -*-
"""Collaboration Orchestrator — Phase J2.

Orchestrates multi-agent collaboration within a research team.
Manages team formation, task delegation, evidence exchange, synthesis, critic loops.

Does NOT replace ResearchOrchestrator (workflow lifecycle).
Does NOT replace TaskRouter (agent selection).
Does NOT replace AgentRuntime (execution).

CollaborationOrchestrator:
→ team coordination
→ delegation
→ message coordination
→ evidence aggregation
→ team synthesis
→ critic loop

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from research_team import ResearchTeam, TeamStatus, TEAM_TEMPLATES, create_team_from_template
from task_delegation import DelegatedResearchTask, DelegationRules, DelegationStatus
from evidence_exchange import (
    AgentEvidence, EvidenceExchange, EvidenceDisposition, EvidenceType, ConflictPreserver,
)
from team_synthesis import TeamResearchResult, SynthesisStatus
from critic_loop import CriticLoop, CriticChallenge, ChallengeType, CriticVerdict
from agent_message import AgentMessage, MessageType, AgentHandoff
from research_audit import ResearchAuditEvent, AuditEventType, AuditLog
from agent_lifecycle import AgentLifecycleManager, AgentLifecycleState
from research_workspace import ResearchWorkspace, WorkspaceStatus


class CollaborationStatus(Enum):
    IDLE = "IDLE"
    FORMING = "FORMING"
    DELEGATING = "DELEGATING"
    RESEARCHING = "RESEARCHING"
    EVIDENCE_EXCHANGE = "EVIDENCE_EXCHANGE"
    SYNTHESIZING = "SYNTHESIZING"
    CRITICIZING = "CRITICIZING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    LOOP_LIMIT_REACHED = "LOOP_LIMIT_REACHED"


class CollaborationOrchestrator:
    """Orchestrates multi-agent collaboration within a research team."""

    def __init__(self) -> None:
        self.team: ResearchTeam | None = None
        self.delegations = DelegationRules()
        self.evidence_exchange = EvidenceExchange()
        self.synthesis: TeamResearchResult | None = None
        self.critic_loop = CriticLoop()
        self.lifecycle = AgentLifecycleManager()
        self.audit = AuditLog()
        self.messages: list[AgentMessage] = []
        self.handoffs: list[AgentHandoff] = []
        self.status = CollaborationStatus.IDLE
        self.delegation_count = 0
        self.message_count = 0
        self.evidence_count = 0
        self.iteration = 0

    # ── Team Formation ──────────────────────────────────────

    def create_team(self, template_name: str, workspace_id: str) -> ResearchTeam:
        """Create a team from a deterministic template."""
        self.team = create_team_from_template(template_name, workspace_id)
        self.status = CollaborationStatus.FORMING
        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.AGENT_REGISTERED,
            workspace_id=workspace_id,
            new_state=TeamStatus.FORMING.value,
            metadata={"team_id": self.team.team_id, "template": template_name},
        ))
        return self.team

    def add_member(self, agent_id: str, role: str = "RESEARCHER", capabilities: list[str] | None = None) -> bool:
        """Add a member to the team. Returns False if duplicate."""
        if self.team is None:
            return False
        result = self.team.add_member(agent_id, role, capabilities)
        if result:
            self.audit.append(ResearchAuditEvent(
                event_type=AuditEventType.AGENT_REGISTERED,
                workspace_id=self.team.workspace_id,
                agent_id=agent_id,
                new_state="TEAM_MEMBER_ADDED",
            ))
        return result

    # ── Task Delegation ─────────────────────────────────────

    def delegate_task(
        self,
        parent_task_id: str,
        delegated_by: str,
        delegated_to: str,
        capability: str,
        reason: str = "",
        depth: int = 0,
    ) -> DelegatedResearchTask | None:
        """Delegate a research task to a team member."""
        if self.team is None:
            return None

        try:
            delegation = self.delegations.create_delegation(
                parent_task_id=parent_task_id,
                delegated_by=delegated_by,
                delegated_to=delegated_to,
                workspace_id=self.team.workspace_id,
                team_id=self.team.team_id,
                capability=capability,
                reason=reason,
                depth=depth,
            )
            self.delegation_count += 1
            self.status = CollaborationStatus.DELEGATING

            self.audit.append(ResearchAuditEvent(
                event_type=AuditEventType.TASK_CREATED,
                workspace_id=self.team.workspace_id,
                agent_id=delegated_to,
                new_state="DELEGATED",
                metadata={"task_id": delegation.task_id, "capability": capability, "depth": depth},
            ))
            return delegation
        except ValueError as e:
            # Max depth exceeded or other delegation rule violation
            return None

    def accept_delegation(self, task_id: str) -> bool:
        """Accept a delegation."""
        delegation = self.delegations.accept_delegation(task_id)
        if delegation:
            self.audit.append(ResearchAuditEvent(
                event_type=AuditEventType.TASK_STARTED,
                workspace_id=delegation.workspace_id,
                agent_id=delegation.delegated_to,
                new_state="ACCEPTED",
            ))
            return True
        return False

    # ── Evidence Exchange ────────────────────────────────────

    def submit_evidence(
        self,
        agent_id: str,
        agent_version: str,
        evidence_type: EvidenceType,
        payload: dict[str, Any],
        disposition: EvidenceDisposition = EvidenceDisposition.NEUTRAL,
        feature_snapshot_id: str = "",
        data_cutoff: str = "",
        provenance_refs: list[str] | None = None,
    ) -> AgentEvidence:
        """Submit evidence from an agent to the team exchange."""
        evidence = AgentEvidence(
            agent_id=agent_id,
            agent_version=agent_version,
            workspace_id=self.team.workspace_id if self.team else "",
            evidence_type=evidence_type,
            disposition=disposition,
            payload=payload,
            feature_snapshot_id=feature_snapshot_id,
            data_cutoff=data_cutoff,
            provenance_refs=provenance_refs or [],
        )
        self.evidence_exchange.add_evidence(evidence)
        self.evidence_count += 1

        if self.team:
            self.audit.append(ResearchAuditEvent(
                event_type=AuditEventType.OBSERVATION_CREATED,
                workspace_id=self.team.workspace_id,
                agent_id=agent_id,
                new_state=disposition.value,
                metadata={"evidence_id": evidence.evidence_id},
            ))
        return evidence

    # ── Team Synthesis ───────────────────────────────────────

    def synthesize(self) -> TeamResearchResult:
        """Synthesize team evidence into a research result."""
        if self.team is None:
            raise RuntimeError("No team formed")

        self.status = CollaborationStatus.SYNTHESIZING

        result = TeamResearchResult(
            team_id=self.team.team_id,
            workspace_id=self.team.workspace_id,
            participating_agents=list(self.team.member_agent_ids),
        )

        # Aggregate evidence
        for evidence in self.evidence_exchange.evidence_items:
            result.add_evidence(evidence.agent_id, evidence.payload, evidence.disposition.value)

        # Compute confidence (evidence consistency, NOT win probability)
        result.confidence = result.compute_confidence()
        result.direction = self._determine_direction(result)

        # Set status
        if result.has_conflicts():
            result.transition_to(SynthesisStatus.CONFLICTED)
        elif result.is_partial():
            result.transition_to(SynthesisStatus.PARTIAL)
        else:
            result.transition_to(SynthesisStatus.COMPLETED)

        self.synthesis = result
        self.status = CollaborationStatus.COMPLETED if result.status != SynthesisStatus.FAILED else CollaborationStatus.FAILED

        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.OPPORTUNITY_DETECTED,
            workspace_id=self.team.workspace_id,
            new_state=result.status.value,
            metadata={"confidence": result.confidence, "direction": result.direction},
        ))
        return result

    def _determine_direction(self, result: TeamResearchResult) -> str:
        """Determine direction from supporting evidence.

        Does NOT declare truth — just aggregates supporting directions.
        """
        if not result.supporting_evidence:
            return "NEUTRAL"
        directions = [e.get("direction", "NEUTRAL") for e in result.supporting_evidence]
        # Simple majority of supporting directions
        from collections import Counter
        counts = Counter(directions)
        return counts.most_common(1)[0][0] if counts else "NEUTRAL"

    # ── Critic Loop ──────────────────────────────────────────

    def critic_review(
        self,
        evidence_id: str,
        agent_id: str,
        evidence_payload: dict[str, Any],
    ) -> CriticResult:
        """Run critic review on evidence."""
        self.status = CollaborationStatus.CRITICIZING
        result = self.critic_loop.review(
            evidence_id=evidence_id,
            evidence_payload=evidence_payload,
        )
        return result

    def request_revision(self, evidence_id: str) -> bool:
        """Request agent revision."""
        return self.critic_loop.request_revision(evidence_id)

    def is_loop_limit_reached(self) -> bool:
        """Check if critic loop limit was reached."""
        return self.critic_loop.is_limit_reached()

    # ── Messaging ────────────────────────────────────────────

    def send_message(
        self,
        sender: str,
        recipient: str,
        message_type: MessageType,
        payload: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> AgentMessage:
        """Send a message within the team."""
        msg = AgentMessage(
            sender_agent_id=sender,
            recipient_agent_id=recipient,
            workspace_id=self.team.workspace_id if self.team else "",
            message_type=message_type,
            payload=payload or {},
            evidence_refs=evidence_refs or [],
        )
        self.messages.append(msg)
        self.message_count += 1
        return msg

    # ── Handoff ──────────────────────────────────────────────

    def create_handoff(
        self,
        source: str,
        destination: str,
        reason: str,
        evidence_refs: list[str] | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> AgentHandoff:
        """Create a handoff between agents."""
        handoff = AgentHandoff(
            source_agent_id=source,
            destination_agent_id=destination,
            reason=reason,
            evidence_refs=evidence_refs or [],
            context_snapshot=context_snapshot or {},
        )
        self.handoffs.append(handoff)
        return handoff

    # ── Failure Isolation ────────────────────────────────────

    def mark_agent_failed(self, agent_id: str) -> None:
        """Mark an agent as failed — does NOT fail the whole team."""
        if self.team:
            self.audit.append(ResearchAuditEvent(
                event_type=AuditEventType.AGENT_HEALTH_CHANGED,
                workspace_id=self.team.workspace_id,
                agent_id=agent_id,
                new_state="FAILED",
            ))

    def get_team_status(self) -> CollaborationStatus:
        """Get current collaboration status."""
        return self.status

    # ── Audit ────────────────────────────────────────────────

    def get_audit_events(self) -> list[ResearchAuditEvent]:
        """Get all audit events for this collaboration."""
        return self.audit._events  # type: ignore[return-value]

    # ── Dashboard ────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get collaboration summary."""
        return {
            "team_id": self.team.team_id if self.team else None,
            "status": self.status.value,
            "members": len(self.team.member_agent_ids) if self.team else 0,
            "delegations": self.delegation_count,
            "messages": self.message_count,
            "evidence_items": self.evidence_count,
            "synthesis": self.synthesis.result_id if self.synthesis else None,
            "critic_iterations": self.critic_loop.iteration,
            "loop_limit_reached": self.critic_loop.is_limit_reached(),
        }