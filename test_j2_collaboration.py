# -*- coding: utf-8 -*-
"""Phase J2 — Multi-Agent Collaboration Tests."""

from __future__ import annotations

import pytest

from research_team import ResearchTeam, TeamStatus, TeamPurpose, create_team_from_template, TEAM_TEMPLATES
from task_delegation import DelegatedResearchTask, DelegationRules, DelegationStatus
from evidence_exchange import AgentEvidence, EvidenceExchange, EvidenceDisposition, EvidenceType, ConflictPreserver
from team_synthesis import TeamResearchResult, SynthesisStatus
from critic_loop import CriticLoop, CriticChallenge, ChallengeType, CriticVerdict, CriticResult
from collaboration_orchestrator import CollaborationOrchestrator, CollaborationStatus
from parallel_executor import ParallelExecutor, ParallelTask
from research_workspace import create_workspace
from agent_message import AgentMessage, MessageType


class TestResearchTeamModel:
    def test_team_creation(self):
        team = ResearchTeam(name="Test", purpose=TeamPurpose.MARKET_STRUCTURE, description="Test")
        assert team.team_id.startswith("TEAM-")
        assert team.status == TeamStatus.DRAFT

    def test_team_add_member(self):
        team = ResearchTeam(name="Test", purpose=TeamPurpose.CUSTOM)
        assert team.add_member("agent_1", "RESEARCHER", ["trend_analysis"]) is True
        assert "agent_1" in team.member_agent_ids

    def test_team_no_duplicate_members(self):
        team = ResearchTeam(name="Test", purpose=TeamPurpose.CUSTOM)
        team.add_member("agent_1", "RESEARCHER")
        assert team.add_member("agent_1", "RESEARCHER") is False

    def test_team_templates(self):
        for name in ["market_structure", "momentum_volatility", "breakout_research", "reversal_research", "full_market_research"]:
            assert name in TEAM_TEMPLATES

    def test_team_template_full_market(self):
        t = TEAM_TEMPLATES["full_market_research"]
        assert len(t["members"]) == 8

    def test_team_deterministic(self):
        t1 = create_team_from_template("full_market_research", "WS-001")
        t2 = create_team_from_template("full_market_research", "WS-001")
        assert t1.member_agent_ids == t2.member_agent_ids


class TestTaskDelegation:
    def test_delegation_creation(self):
        rules = DelegationRules()
        d = rules.create_delegation("TASK-001", "orch", "agent_1", "WS-001", "T1", "cap")
        assert d.task_id.startswith("DT-")
        assert d.status == DelegationStatus.PENDING

    def test_delegation_idempotent(self):
        rules = DelegationRules()
        d1 = rules.create_delegation("TASK-001", "orch", "agent_1", "WS-001", "T1", "cap")
        d2 = rules.create_delegation("TASK-001", "orch", "agent_1", "WS-001", "T1", "cap")
        assert d1.task_id == d2.task_id

    def test_delegation_accept(self):
        rules = DelegationRules()
        d = rules.create_delegation("TASK-001", "orch", "agent_1", "WS-001", "T1", "cap")
        assert d is not None
        r = rules.accept_delegation(d.task_id)
        assert r is not None
        assert r.status == DelegationStatus.ACCEPTED

    def test_delegation_complete(self):
        rules = DelegationRules()
        d = rules.create_delegation("TASK-001", "orch", "agent_1", "WS-001", "T1", "cap")
        rules.accept_delegation(d.task_id)
        r = rules.complete_delegation(d.task_id, "RESULT-001")
        assert r is not None
        assert r.status == DelegationStatus.COMPLETED

    def test_delegation_depth_limit(self):
        rules = DelegationRules(max_depth=2)
        with pytest.raises(ValueError):
            rules.create_delegation("T1", "orch", "a1", "WS", "T", "cap", depth=5)

    def test_delegation_chain(self):
        rules = DelegationRules()
        d1 = rules.create_delegation("TASK-001", "orch", "a1", "WS", "T", "cap")
        d2 = rules.create_delegation(d1.task_id, "orch", "a2", "WS", "T", "cap", depth=1)
        chain = rules.get_delegation_chain(d2.task_id)
        assert len(chain) == 2


class TestEvidenceExchange:
    def test_evidence_creation(self):
        e = AgentEvidence(agent_id="a1", evidence_type=EvidenceType.OBSERVATION, payload={"d": "LONG"}, disposition=EvidenceDisposition.SUPPORTING)
        assert e.evidence_id.startswith("EVD-")

    def test_exchange_add(self):
        ex = EvidenceExchange()
        e1 = AgentEvidence(agent_id="a1", evidence_type=EvidenceType.OBSERVATION, payload={"d": "LONG"}, disposition=EvidenceDisposition.SUPPORTING)
        e2 = AgentEvidence(agent_id="a2", evidence_type=EvidenceType.OBSERVATION, payload={"d": "SHORT"}, disposition=EvidenceDisposition.CONFLICTING)
        ex.add_evidence(e1)
        ex.add_evidence(e2)
        assert len(ex.evidence_items) == 2
        assert len(ex.conflicting) == 1

    def test_conflict_preserved(self):
        ex = EvidenceExchange()
        e1 = AgentEvidence(agent_id="a1", evidence_type=EvidenceType.OBSERVATION, payload={"d": "LONG"}, disposition=EvidenceDisposition.SUPPORTING)
        e2 = AgentEvidence(agent_id="a2", evidence_type=EvidenceType.OBSERVATION, payload={"d": "SHORT"}, disposition=EvidenceDisposition.CONFLICTING)
        ex.add_evidence(e1)
        ex.add_evidence(e2)
        assert ex.has_conflicts()

    def test_unavailable_evidence(self):
        ex = EvidenceExchange()
        e = AgentEvidence(agent_id="a1", evidence_type=EvidenceType.OBSERVATION, payload={}, disposition=EvidenceDisposition.UNAVAILABLE)
        ex.add_evidence(e)
        assert ex.get_unavailable_count() == 1

    def test_classify_disposition(self):
        cp = ConflictPreserver()
        assert cp.classify_disposition({"direction": "LONG"}, "LONG") == EvidenceDisposition.SUPPORTING
        assert cp.classify_disposition({"direction": "SHORT"}, "LONG") == EvidenceDisposition.CONFLICTING
        assert cp.classify_disposition({"direction": "NEUTRAL"}, "LONG") == EvidenceDisposition.NEUTRAL


class TestTeamSynthesis:
    def test_synthesis_create(self):
        r = TeamResearchResult(team_id="T1", workspace_id="WS", participating_agents=["a1"])
        assert r.result_id.startswith("TRR-")

    def test_synthesis_add_evidence(self):
        r = TeamResearchResult(team_id="T1", workspace_id="WS", participating_agents=["a1"])
        r.add_evidence("a1", {"direction": "LONG"}, "SUPPORTING")
        r.add_evidence("a2", {"direction": "SHORT"}, "CONFLICTING")
        assert len(r.supporting_evidence) == 1
        assert len(r.conflicting_evidence) == 1

    def test_synthesis_confidence(self):
        r = TeamResearchResult(team_id="T1", workspace_id="WS", participating_agents=["a1"])
        r.add_evidence("a1", {"direction": "LONG"}, "SUPPORTING")
        r.add_evidence("a2", {"direction": "SHORT"}, "CONFLICTING")
        r.add_evidence("a3", {"direction": "NEUTRAL"}, "NEUTRAL")
        c = r.compute_confidence()
        assert 0.0 <= c <= 1.0

    def test_synthesis_conflicted(self):
        r = TeamResearchResult(team_id="T1", workspace_id="WS", participating_agents=["a1", "a2"])
        r.add_evidence("a1", {"direction": "LONG"}, "SUPPORTING")
        r.add_evidence("a2", {"direction": "SHORT"}, "CONFLICTING")
        r.confidence = r.compute_confidence()
        r.transition_to(SynthesisStatus.CONFLICTED)
        assert r.has_conflicts()
        assert r.status == SynthesisStatus.CONFLICTED

    def test_synthesis_partial(self):
        r = TeamResearchResult(team_id="T1", workspace_id="WS", participating_agents=["a1"])
        r.add_evidence("a1", {"direction": "LONG"}, "SUPPORTING")
        r.add_evidence("a2", {"direction": "NEUTRAL"}, "UNAVAILABLE")
        assert r.is_partial()


class TestCriticLoop:
    def test_critic_accept(self):
        loop = CriticLoop(max_iterations=3)
        r = loop.review("EVD-001", {"direction": "LONG", "confidence": 0.7, "supporting_features": ["EMA"]})
        assert r.verdict == CriticVerdict.ACCEPT
        assert r.can_proceed is True

    def test_critic_challenge(self):
        loop = CriticLoop(max_iterations=3)
        r = loop.review("EVD-002", {"direction": "LONG", "confidence": 0.9})
        assert r.verdict == CriticVerdict.CHALLENGE
        assert r.can_proceed is False

    def test_critic_loop_limit(self):
        loop = CriticLoop(max_iterations=2)
        result = None
        for i in range(5):
            result = loop.review(f"EVD-{i}", {"direction": "LONG", "confidence": 0.9})
        assert loop.is_limit_reached()
        assert result is not None
        assert result.verdict == CriticVerdict.INSUFFICIENT

    def test_critic_no_truth(self):
        loop = CriticLoop(max_iterations=3)
        r = loop.review("EVD-001", {"direction": "LONG", "confidence": 0.5})
        assert r.verdict in (CriticVerdict.ACCEPT, CriticVerdict.CHALLENGE)

    def test_critic_resolve(self):
        loop = CriticLoop(max_iterations=3)
        loop.review("EVD-001", {"direction": "LONG", "confidence": 0.9})  # No supporting features → challenge
        assert len(loop.challenges) > 0
        ch_id = loop.challenges[0].challenge_id
        assert loop.resolve_challenge(ch_id, "Updated") is True

    def test_critic_request_revision(self):
        loop = CriticLoop(max_iterations=3)
        loop.review("EVD-001", {"direction": "LONG", "confidence": 0.9})  # No supporting features → challenge
        assert len(loop.challenges) > 0
        assert loop.request_revision("EVD-001") is True


class TestCollaborationOrchestrator:
    def test_create_team(self):
        orch = CollaborationOrchestrator()
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        team = orch.create_team("full_market_research", ws.workspace_id)
        assert orch.team is not None
        assert len(orch.team.member_agent_ids) == 8

    def test_add_member(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        assert orch.add_member("new_agent", "RESEARCHER", ["structure_analysis"]) is True

    def test_delegate_task(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        d = orch.delegate_task("T1", "lead", "structure_agent", "structure_analysis", "Analyze")
        assert d is not None
        assert orch.status == CollaborationStatus.DELEGATING

    def test_accept_delegation(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        d = orch.delegate_task("T1", "lead", "structure_agent", "structure_analysis")
        assert d is not None
        assert orch.accept_delegation(d.task_id) is True

    def test_submit_evidence(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        e = orch.submit_evidence("trend_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "LONG", "confidence": 0.7}, EvidenceDisposition.SUPPORTING)
        assert e.evidence_id.startswith("EVD-")
        assert orch.evidence_count == 1

    def test_synthesize(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        orch.submit_evidence("trend_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "LONG", "confidence": 0.7}, EvidenceDisposition.SUPPORTING)
        orch.submit_evidence("liquidity_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "NEUTRAL", "confidence": 0.3}, EvidenceDisposition.NEUTRAL)
        s = orch.synthesize()
        assert orch.synthesis is not None

    def test_critic_review(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        r = orch.critic_review("EVD-001", "trend_agent", {"direction": "LONG", "confidence": 0.7, "supporting_features": ["EMA"]})
        assert isinstance(r, CriticResult)

    def test_loop_limit(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        result = None
        for i in range(5):
            result = orch.critic_review(f"EVD-{i}", "trend_agent", {"direction": "LONG", "confidence": 0.9})
        assert orch.is_loop_limit_reached()
        assert result is not None
        assert result.verdict == CriticVerdict.INSUFFICIENT

    def test_send_message(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        m = orch.send_message("a1", "a2", MessageType.REQUEST, payload={"q": "analyze"})
        assert len(orch.messages) == 1

    def test_handoff(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        h = orch.create_handoff("a1", "a2", "Done", evidence_refs=["EVD-001"])
        assert len(orch.handoffs) == 1

    def test_failure_isolation(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        orch.mark_agent_failed("trend_agent")
        assert orch.team is not None

    def test_summary(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        s = orch.get_summary()
        assert s["team_id"] is not None
        assert s["members"] == 4

    def test_audit(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        events = orch.get_audit_events()
        assert len(events) >= 1

    def test_full_flow(self):
        orch = CollaborationOrchestrator()
        ws = create_workspace("J2-FLOW", "THYAO.IS", "1h", "2026-01-01")
        team = orch.create_team("market_structure", ws.workspace_id)
        d1 = orch.delegate_task("T1", "lead", "structure_agent", "structure_analysis", "Analyze")
        d2 = orch.delegate_task("T1", "lead", "trend_agent", "trend_analysis", "Trend")
        orch.accept_delegation(d1.task_id)
        orch.accept_delegation(d2.task_id)
        orch.submit_evidence("structure_agent", "1.0.0", EvidenceType.OBSERVATION, {"structure": "BULLISH", "confidence": 0.7}, EvidenceDisposition.SUPPORTING)
        orch.submit_evidence("trend_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "LONG", "confidence": 0.6}, EvidenceDisposition.SUPPORTING)
        orch.critic_review("EVD-001", "structure_agent", {"structure": "BULLISH", "confidence": 0.7, "supporting_features": ["s"]})
        synthesis = orch.synthesize()
        assert synthesis is not None
        summary = orch.get_summary()
        assert summary["delegations"] == 2

    def test_collaboration_with_conflict(self):
        orch = CollaborationOrchestrator()
        ws = create_workspace("J2-CONFLICT", "THYAO.IS", "1h", "2026-01-01")
        orch.create_team("market_structure", ws.workspace_id)
        orch.submit_evidence("trend_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "LONG", "confidence": 0.7}, EvidenceDisposition.SUPPORTING)
        orch.submit_evidence("reversal_agent", "1.0.0", EvidenceType.OBSERVATION, {"direction": "SHORT", "confidence": 0.6}, EvidenceDisposition.CONFLICTING)
        synthesis = orch.synthesize()
        assert synthesis.has_conflicts()
        assert synthesis.status == SynthesisStatus.CONFLICTED

    def test_parallel_in_collaboration(self):
        orch = CollaborationOrchestrator()
        orch.create_team("market_structure", "WS-001")
        pe = ParallelExecutor()
        tasks = [ParallelTask(agent_id=a, agent_version="1.0", capability="cap") for a in ["trend_agent", "structure_agent", "liquidity_agent"]]
        results = pe.execute_parallel(tasks, lambda t: {"agent": t.agent_id, "ok": True})
        assert len(results) == 3
        assert pe.all_succeeded()

    def test_deterministic_team(self):
        t1 = create_team_from_template("full_market_research", "WS-001")
        t2 = create_team_from_template("full_market_research", "WS-001")
        assert t1.member_agent_ids == t2.member_agent_ids


class TestParallelExecution:
    def test_parallel_execution(self):
        exe = ParallelExecutor()
        tasks = [ParallelTask(agent_id="b", capability="c"), ParallelTask(agent_id="a", capability="c"), ParallelTask(agent_id="c", capability="c")]
        results = exe.execute_parallel(tasks, lambda t: {"agent": t.agent_id})
        assert results[0].agent_id == "a"
        assert results[1].agent_id == "b"
        assert results[2].agent_id == "c"

    def test_parallel_no_duplicates(self):
        exe = ParallelExecutor()
        tasks = [ParallelTask(agent_id="a", capability="c"), ParallelTask(agent_id="a", capability="c")]
        count = 0
        def fn(t):
            nonlocal count
            count += 1
            return {"ok": True}
        results = exe.execute_parallel(tasks, fn)
        assert len(results) == 1
        assert count == 1

    def test_parallel_failure_isolation(self):
        exe = ParallelExecutor()
        tasks = [ParallelTask(agent_id="a", capability="c"), ParallelTask(agent_id="b", capability="c")]
        results = exe.execute_parallel(tasks, lambda t: {"ok": True} if t.agent_id == "b" else exec('raise Exception("fail")') or {})
        assert results[0].status == "FAILED"
        assert results[1].status == "COMPLETED"

    def test_parallel_successful(self):
        exe = ParallelExecutor()
        results = exe.execute_parallel([ParallelTask(agent_id="a", capability="c")], lambda t: {"ok": True})
        assert exe.all_succeeded()
        assert not exe.has_failures()

    def test_failure_isolation_check(self):
        exe = ParallelExecutor()
        # Failed agent in the dependent list gets tracked
        affected = exe.failure_isolation_check("a", ["a", "b", "c"])
        assert "a" in affected
        assert "b" not in affected


class TestMessageBudget:
    def test_workspace_message_limit(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert ws.can_send_message() is True
        for _ in range(100):
            ws.increment_message_count()
        assert ws.can_send_message() is False

    def test_workspace_bump_context(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert ws.context_version == 1
        ws.bump_context_version()
        assert ws.context_version == 2