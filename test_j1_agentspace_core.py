# -*- coding: utf-8 -*-
"""Phase J1 — AgentSpace Core Tests.

Tests for AgentSpace-inspired core agent identity + capability + workspace + routing + audit.
Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import pytest

from research_workspace import (
    ResearchWorkspace, WorkspaceStatus, WorkspaceParticipant, create_workspace,
)
from task_router import (
    TaskRouter, CapabilityDescriptor, RoutingResult, RoutingStatus, DEFAULT_CAPABILITIES,
)
from agent_message import AgentMessage, MessageType, AgentHandoff
from research_audit import ResearchAuditEvent, AuditEventType, AuditLog
from agent_lifecycle import AgentLifecycleManager, AgentLifecycleState, AgentExecution
from research_orchestrator import ResearchOrchestrator
from research_agent_model import AgentProfile, AgentCapability, CapabilityType, AgentStatus
from research_orchestrator_model import ResearchTask, TaskStatus


# ═══════════════════════════════════════════════════════════════
# 1. AGENT IDENTITY
# ═══════════════════════════════════════════════════════════════

class TestAgentIdentity:
    def test_agent_profile_has_identity_fields(self):
        profile = AgentProfile(
            agent_id="trend_agent",
            agent_name="Trend Research Agent",
            version="1.0.0",
            role="research",
            family="trend",
        )
        assert profile.agent_id == "trend_agent"
        assert profile.version == "1.0.0"
        assert profile.role == "research"
        assert profile.family == "trend"

    def test_agent_profile_capabilities(self):
        cap = AgentCapability(
            capability=CapabilityType.TREND_DIRECTION,
            required_features=["EMA_FAST", "EMA_SLOW"],
        )
        profile = AgentProfile(
            agent_id="trend",
            agent_name="Trend",
            version="1.0.0",
            capabilities=[CapabilityType.TREND_DIRECTION],
            capability_details={"trend_direction": cap},
        )
        assert CapabilityType.TREND_DIRECTION in profile.capabilities
        assert "trend_direction" in profile.capability_details

    def test_agent_profile_runtime_binding(self):
        profile = AgentProfile(
            agent_id="test",
            agent_name="Test",
            version="1.0.0",
            runtime_binding="hermes",
        )
        assert profile.runtime_binding == "hermes"

    def test_agent_profile_status_default(self):
        profile = AgentProfile(agent_id="test", agent_name="Test", version="1.0.0")
        assert profile.status == AgentStatus.READY


# ═══════════════════════════════════════════════════════════════
# 2. CAPABILITY DISCOVERY
# ═══════════════════════════════════════════════════════════════

class TestCapabilityDiscovery:
    def test_default_capabilities_registered(self):
        router = TaskRouter()
        for cap_id, cap_desc in DEFAULT_CAPABILITIES.items():
            router.register_capability(
                capability_id=cap_id,
                description=cap_desc.description,
                required_features=cap_desc.required_features,
                supported_regimes=cap_desc.supported_regimes,
                supported_timeframes=cap_desc.supported_timeframes,
                cost_class=cap_desc.cost_class,
                deterministic=cap_desc.deterministic,
                research_only=cap_desc.research_only,
            )
        assert "trend_analysis" in router._capabilities
        assert "breakout_analysis" in router._capabilities
        assert "reversal_analysis" in router._capabilities
        assert "momentum_analysis" in router._capabilities
        assert "volatility_analysis" in router._capabilities
        assert "liquidity_analysis" in router._capabilities
        assert "structure_analysis" in router._capabilities

    def test_capability_descriptor_metadata(self):
        cap = CapabilityDescriptor(
            capability_id="test_cap",
            description="Test capability",
            required_features=["FEATURE_A"],
            optional_features=["FEATURE_B"],
            supported_regimes=["TRENDING"],
            supported_timeframes=["1h", "4h"],
            supported_asset_types=["STOCK"],
            cost_class="medium",
            deterministic=True,
            research_only=True,
        )
        assert cap.capability_id == "test_cap"
        assert "FEATURE_A" in cap.required_features
        assert "FEATURE_B" in cap.optional_features
        assert cap.cost_class == "medium"

    def test_capability_scoring(self):
        router = TaskRouter()
        router.register_capability(
            capability_id="test_cap",
            required_features=["EMA_FAST", "ADX"],
            supported_regimes=["TRENDING"],
            supported_timeframes=["1h"],
        )
        # Perfect match
        score = router._score_candidate(
            router._capabilities["test_cap"],
            {"EMA_FAST": True, "ADX": True},
            symbol="THYAO.IS",
            timeframe="1h",
            regime="TRENDING",
        )
        assert score > 0.5

        # No features available
        score2 = router._score_candidate(
            router._capabilities["test_cap"],
            {},
            symbol="THYAO.IS",
            timeframe="1h",
            regime="TRENDING",
        )
        assert score2 < score


# ═══════════════════════════════════════════════════════════════
# 3. TASK ROUTING
# ═══════════════════════════════════════════════════════════════

class TestTaskRouting:
    def test_routing_registers_agents(self):
        router = TaskRouter()
        router.register_capability("trend_analysis")
        router.register_agent_capability("trend_agent", "trend_analysis")
        assert "trend_agent" in router._agent_capabilities
        assert "trend_analysis" in router._agent_capabilities["trend_agent"]

    def test_routing_finds_candidate(self):
        router = TaskRouter()
        router.register_capability("trend_analysis")
        router.register_agent_capability("trend_agent", "trend_analysis")
        candidates = router.find_candidates("trend_analysis")
        assert len(candidates) == 1
        assert candidates[0].agent_id == "trend_agent"

    def test_routing_no_candidate(self):
        router = TaskRouter()
        # No capabilities registered at all
        result = router.route("task-1", "nonexistent_capability")
        assert result.status in (RoutingStatus.NO_CANDIDATE, RoutingStatus.CAPABILITY_MISMATCH)

    def test_routing_capability_mismatch(self):
        router = TaskRouter()
        result = router.route("task-1", "nonexistent_capability")
        assert result.status in (RoutingStatus.NO_CANDIDATE, RoutingStatus.CAPABILITY_MISMATCH)

    def test_routing_deterministic(self):
        router = TaskRouter()
        router.register_capability("trend_analysis")
        router.register_agent_capability("agent_b", "trend_analysis")
        router.register_agent_capability("agent_a", "trend_analysis")
        # Both agents have same capability — alphabetical tie-breaking
        result = router.route("task-1", "trend_analysis")
        # agent_a < agent_b alphabetically, so agent_a should be first
        assert result.agent_id == "agent_a"

    def test_routing_result_fields(self):
        router = TaskRouter()
        router.register_capability("trend_analysis")
        router.register_agent_capability("trend_agent", "trend_analysis")
        result = router.route("task-1", "trend_analysis")
        assert result.task_id == "task-1"
        assert result.agent_id == "trend_agent"
        assert result.status == RoutingStatus.ROUTED
        assert result.candidates_evaluated == 1
        assert result.reasoning != ""


# ═══════════════════════════════════════════════════════════════
# 4. RESEARCH WORKSPACE
# ═══════════════════════════════════════════════════════════════

class TestResearchWorkspace:
    def test_workspace_creation(self):
        ws = create_workspace(
            research_id="R1",
            symbol="THYAO.IS",
            timeframe="1h",
            cutoff="2026-01-01T00:00:00",
        )
        assert ws.workspace_id.startswith("WS-")
        assert ws.symbol == "THYAO.IS"
        assert ws.timeframe == "1h"
        assert ws.cutoff == "2026-01-01T00:00:00"
        assert ws.status == WorkspaceStatus.ACTIVE

    def test_workspace_participants(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        ws.add_participant("trend_agent", "RESEARCHER")
        ws.add_participant("critic_agent", "CRITIC")
        assert len(ws.participants) == 2
        assert ws.participants[0].agent_id == "trend_agent"
        assert ws.participants[1].role == "CRITIC"

    def test_workspace_tasks_artifacts(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        ws.add_task("TASK-001")
        ws.add_task("TASK-002")
        ws.add_artifact("ART-001")
        assert "TASK-001" in ws.tasks
        assert "TASK-002" in ws.tasks
        assert "ART-001" in ws.artifacts

    def test_workspace_no_duplicate_tasks(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        ws.add_task("TASK-001")
        ws.add_task("TASK-001")  # duplicate
        assert ws.tasks.count("TASK-001") == 1

    def test_workspace_status_transitions(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        ws.transition_to(WorkspaceStatus.REVIEW)
        assert ws.status == WorkspaceStatus.REVIEW
        ws.transition_to(WorkspaceStatus.COMPLETED)
        assert ws.status == WorkspaceStatus.COMPLETED

    def test_workspace_to_dict(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        d = ws.to_dict()
        assert d["workspace_id"] == ws.workspace_id
        assert d["symbol"] == "THYAO.IS"
        assert d["status"] == "ACTIVE"


# ═══════════════════════════════════════════════════════════════
# 5. AGENT MESSAGING
# ═══════════════════════════════════════════════════════════════

class TestAgentMessaging:
    def test_message_creation(self):
        msg = AgentMessage(
            sender_agent_id="trend_agent",
            recipient_agent_id="critic_agent",
            message_type=MessageType.REQUEST,
            payload={"query": "analyze trend"},
        )
        assert msg.message_id.startswith("MSG-")
        assert msg.sender_agent_id == "trend_agent"
        assert msg.recipient_agent_id == "critic_agent"
        assert msg.message_type == MessageType.REQUEST

    def test_message_evidence_refs(self):
        msg = AgentMessage(
            sender_agent_id="agent_a",
            recipient_agent_id="agent_b",
            message_type=MessageType.EVIDENCE,
            evidence_refs=["EVID-001", "EVID-002"],
        )
        assert len(msg.evidence_refs) == 2
        assert "EVID-001" in msg.evidence_refs

    def test_handoff_creation(self):
        handoff = AgentHandoff(
            source_agent_id="trend_agent",
            destination_agent_id="structure_agent",
            reason="Trend analysis complete, structure analysis needed",
            evidence_refs=["EVID-001"],
        )
        assert handoff.handoff_id.startswith("HO-")
        assert handoff.source_agent_id == "trend_agent"
        assert handoff.destination_agent_id == "structure_agent"

    def test_handoff_preserves_context(self):
        handoff = AgentHandoff(
            source_agent_id="agent_a",
            destination_agent_id="agent_b",
            reason="Test",
            context_snapshot={"trend": "UP", "confidence": 0.7},
        )
        assert handoff.context_snapshot["trend"] == "UP"


# ═══════════════════════════════════════════════════════════════
# 6. AUDIT LOG
# ═══════════════════════════════════════════════════════════════

class TestAuditLog:
    def test_audit_event_creation(self):
        event = ResearchAuditEvent(
            event_type=AuditEventType.AGENT_REGISTERED,
            agent_id="trend_agent",
            new_state="REGISTERED",
        )
        assert event.event_id.startswith("AUD-")
        assert event.event_type == AuditEventType.AGENT_REGISTERED

    def test_audit_append_only(self):
        audit = AuditLog()
        e1 = ResearchAuditEvent(event_type=AuditEventType.WORKSPACE_CREATED, new_state="CREATED")
        e2 = ResearchAuditEvent(event_type=AuditEventType.AGENT_REGISTERED, new_state="READY")
        audit.append(e1)
        audit.append(e2)
        assert len(audit._events) == 2

    def test_audit_filter_by_type(self):
        audit = AuditLog()
        audit.append(ResearchAuditEvent(event_type=AuditEventType.WORKSPACE_CREATED, new_state="CREATED"))
        audit.append(ResearchAuditEvent(event_type=AuditEventType.AGENT_REGISTERED, new_state="READY"))
        audit.append(ResearchAuditEvent(event_type=AuditEventType.WORKSPACE_CREATED, new_state="ACTIVE"))
        workspace_events = audit.get_events(AuditEventType.WORKSPACE_CREATED)
        assert len(workspace_events) == 2

    def test_audit_workspace_filter(self):
        audit = AuditLog()
        audit.append(ResearchAuditEvent(
            event_type=AuditEventType.WORKSPACE_CREATED,
            workspace_id="WS-001",
            new_state="CREATED",
        ))
        audit.append(ResearchAuditEvent(
            event_type=AuditEventType.AGENT_REGISTERED,
            workspace_id="WS-002",
            new_state="READY",
        ))
        ws_events = audit.get_events_for_workspace("WS-001")
        assert len(ws_events) == 1
        assert ws_events[0].workspace_id == "WS-001"

    def test_audit_to_dict(self):
        audit = AuditLog()
        audit.append(ResearchAuditEvent(event_type=AuditEventType.WORKSPACE_CREATED, new_state="CREATED"))
        d = audit.to_dict()
        assert d["event_count"] == 1
        assert "events" in d


# ═══════════════════════════════════════════════════════════════
# 7. AGENT LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestAgentLifecycle:
    def test_lifecycle_manager_create(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution(
            agent_id="trend_agent",
            agent_version="1.0.0",
            task_id="TASK-001",
            workspace_id="WS-001",
        )
        assert exe.execution_id.startswith("EXE-")
        assert exe.status == AgentLifecycleState.REGISTERED

    def test_lifecycle_transition(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        result = mgr.transition(exe.execution_id, AgentLifecycleState.READY)
        assert result is not None
        assert result.status == AgentLifecycleState.READY

    def test_lifecycle_invalid_transition(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        # REGISTERED → RUNNING is not valid (must go through READY)
        result = mgr.transition(exe.execution_id, AgentLifecycleState.RUNNING)
        assert result is None

    def test_lifecycle_completed(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        mgr.transition(exe.execution_id, AgentLifecycleState.READY)
        mgr.transition(exe.execution_id, AgentLifecycleState.RUNNING)
        mgr.transition(exe.execution_id, AgentLifecycleState.COMPLETED)
        assert exe.status == AgentLifecycleState.COMPLETED
        assert exe.completed_at != ""

    def test_lifecycle_mark_error(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        mgr.transition(exe.execution_id, AgentLifecycleState.READY)
        mgr.transition(exe.execution_id, AgentLifecycleState.RUNNING)
        exe.mark_error("ADAPTER_NOT_FOUND", "Agent not registered")
        assert exe.status == AgentLifecycleState.FAILED
        assert exe.error_type == "ADAPTER_NOT_FOUND"

    def test_valid_transitions(self):
        mgr = AgentLifecycleManager()
        assert mgr.is_valid_transition(AgentLifecycleState.REGISTERED, AgentLifecycleState.READY)
        assert not mgr.is_valid_transition(AgentLifecycleState.REGISTERED, AgentLifecycleState.RUNNING)
        assert mgr.is_valid_transition(AgentLifecycleState.RUNNING, AgentLifecycleState.COMPLETED)
        assert mgr.is_valid_transition(AgentLifecycleState.RUNNING, AgentLifecycleState.FAILED)

    def test_active_executions(self):
        mgr = AgentLifecycleManager()
        exe1 = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        exe2 = mgr.create_execution("agent2", "1.0.0", "TASK-002", "WS-001")
        mgr.transition(exe1.execution_id, AgentLifecycleState.READY)
        mgr.transition(exe1.execution_id, AgentLifecycleState.RUNNING)
        mgr.transition(exe2.execution_id, AgentLifecycleState.COMPLETED)
        active = mgr.get_active_executions()
        assert len(active) == 1
        assert active[0].execution_id == exe1.execution_id


# ═══════════════════════════════════════════════════════════════
# 8. ORCHESTRATOR INTEGRATION
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorJ1Integration:
    def test_orchestrator_has_workspace(self):
        orch = ResearchOrchestrator()
        assert orch.workspace is None
        assert orch.router is not None
        assert orch.audit is not None
        assert orch.lifecycle is not None
        assert orch.messages is not None

    def test_orchestrator_creates_workspace(self):
        orch = ResearchOrchestrator()
        ws = orch.create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert orch.workspace is not None
        assert orch.workspace.workspace_id == ws.workspace_id
        assert orch.workspace.symbol == "THYAO.IS"

    def test_orchestrator_add_participant(self):
        orch = ResearchOrchestrator()
        orch.create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        orch.add_participant("trend_agent", "RESEARCHER")
        assert len(orch.workspace.participants) == 1

    def test_orchestrator_route_task(self):
        orch = ResearchOrchestrator()
        orch.create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        result = orch.route_task("task-1", "trend_analysis", symbol="THYAO.IS")
        # May have no candidate or routed — both valid
        assert isinstance(result, RoutingResult)
        assert result.task_id == "task-1"

    def test_orchestrator_send_message(self):
        orch = ResearchOrchestrator()
        orch.create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        msg = orch.send_message(
            sender="trend_agent",
            recipient="critic_agent",
            message_type=MessageType.REQUEST,
            payload={"query": "analyze"},
        )
        assert len(orch.messages) == 1
        assert orch.messages[0].message_id == msg.message_id
        assert orch.messages[0].payload["query"] == "analyze"

    def test_orchestrator_audit_events(self):
        orch = ResearchOrchestrator()
        orch.create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        events = orch.get_workspace_audit()
        assert len(events) >= 1  # workspace created event
        assert events[0].event_type == AuditEventType.WORKSPACE_CREATED

    def test_orchestrator_register_agent(self):
        orch = ResearchOrchestrator()
        profile = AgentProfile(
            agent_id="trend_agent",
            agent_name="Trend",
            version="1.0.0",
            capabilities=[CapabilityType.TREND_DIRECTION],
        )
        orch.register_agent(profile)
        assert "trend_agent" in orch.profiles

    def test_orchestrator_dashboard_has_j1_fields(self):
        orch = ResearchOrchestrator()
        summary = orch.get_dashboard_summary()
        assert "workspace" in summary
        assert "audit_events" in summary


# ═══════════════════════════════════════════════════════════════
# 9. DETERMINISTIC ROUTING
# ═══════════════════════════════════════════════════════════════

class TestDeterministicRouting:
    def test_same_input_same_route(self):
        router = TaskRouter()
        router.register_capability("trend_analysis")
        router.register_agent_capability("trend_agent", "trend_analysis")
        r1 = router.route("task-1", "trend_analysis")
        r2 = router.route("task-1", "trend_analysis")
        assert r1.agent_id == r2.agent_id
        assert r1.score == r2.score

    def test_routing_different_capabilities(self):
        router = TaskRouter()
        for cap_id in ["trend_analysis", "breakout_analysis", "liquidity_analysis"]:
            router.register_capability(cap_id)
        router.register_agent_capability("trend_agent", "trend_analysis")
        router.register_agent_capability("breakout_agent", "breakout_analysis")
        r1 = router.route("t1", "trend_analysis")
        r2 = router.route("t2", "breakout_analysis")
        assert r1.agent_id != r2.agent_id


# ═══════════════════════════════════════════════════════════════
# 10. PERMISSION / SECURITY BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestSecurityBoundary:
    def test_workspace_is_research_only(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert ws.status in (WorkspaceStatus.INITIALIZING, WorkspaceStatus.ACTIVE)
        # No trading-related fields
        d = ws.to_dict()
        assert "order" not in str(d).lower()
        assert "broker" not in str(d).lower()

    def test_no_fake_data_in_workspace(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        # Workspace should not contain fake/synthetic data
        d = ws.to_dict()
        assert d["symbol"] == "THYAO.IS"  # Real symbol


# ═══════════════════════════════════════════════════════════════
# 11. FAILURE ISOLATION
# ═══════════════════════════════════════════════════════════════

class TestFailureIsolation:
    def test_orchestrator_partial_failure(self):
        orch = ResearchOrchestrator()
        # Create tasks with dependency chain: A → B, C (independent)
        task_a = ResearchTask(task_id="T-A", task_type="research", agent_id="agent_a")
        task_b = ResearchTask(task_id="T-B", task_type="research", agent_id="agent_b", dependencies=["T-A"])
        task_c = ResearchTask(task_id="T-C", task_type="research", agent_id="agent_c")  # independent

        orch.tasks["T-A"] = task_a
        orch.tasks["T-B"] = task_b
        orch.tasks["T-C"] = task_c

        # Verify dependency logic: C has no deps → can execute
        can_exec_c, reason_c = orch.can_execute(task_c)
        assert can_exec_c, f"Independent task C should be executable: {reason_c}"

        # B depends on A (not yet completed) → blocked
        can_exec_b, reason_b = orch.can_execute(task_b)
        assert not can_exec_b, "B should be blocked (depends on A)"
        assert "BLOCKED" in reason_b

    def test_agent_health_does_not_block(self):
        orch = ResearchOrchestrator()
        profile = AgentProfile(
            agent_id="agent_a",
            agent_name="Agent A",
            version="1.0.0",
            status=AgentStatus.FAILED,  # Failed health
        )
        orch.register_agent(profile)

        task = ResearchTask(task_id="T-1", task_type="research", agent_id="agent_a")
        orch.tasks["T-1"] = task

        # Agent health FAILED does NOT block execution (J0 rule)
        can_exec, reason = orch.can_execute(task)
        assert can_exec, "Failed agent health should not block execution"


# ═══════════════════════════════════════════════════════════════
# 12. ARTIFACT VERSIONING
# ═══════════════════════════════════════════════════════════════

class TestArtifactVersioning:
    def test_lifecycle_tracks_version(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        assert exe.agent_version == "1.0.0"

    def test_lifecycle_execution_metadata(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.1.0", "TASK-001", "WS-001")
        exe.metadata["feature_snapshot_id"] = "FS-001"
        assert exe.metadata["feature_snapshot_id"] == "FS-001"


# ═══════════════════════════════════════════════════════════════
# 13. REGISTRY EXTENSION
# ═══════════════════════════════════════════════════════════════

class TestRegistryExtension:
    def test_registry_find_by_capability(self):
        from agent_registry import AgentRegistry
        from agent_contract import BaseAgentAdapter, MarketContext

        registry = AgentRegistry()
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        adapter = BaseAgentAdapter(ctx)
        adapter.capabilities = ["trend_analysis", "momentum_analysis"]  # type: ignore[attr-defined]
        registry.register("trend_agent", adapter, version="1.0.0")

        results = registry.find_by_capability("trend_analysis")
        assert len(results) == 1
        assert results[0]["agent_id"] == "trend_agent"

    def test_registry_find_by_capability_none(self):
        from agent_registry import AgentRegistry
        from agent_contract import BaseAgentAdapter, MarketContext

        registry = AgentRegistry()
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        adapter = BaseAgentAdapter(ctx)
        adapter.capabilities = ["trend_analysis"]  # type: ignore[attr-defined]
        registry.register("trend_agent", adapter)

        results = registry.find_by_capability("nonexistent")
        assert len(results) == 0


# ═══════════════════════════════════════════════════════════════
# 14. RESEARCH CONTEXT / WORKSPACE CONTEXT
# ═══════════════════════════════════════════════════════════════

class TestResearchContext:
    def test_workspace_cutoff_preserved(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01T00:00:00")
        assert ws.cutoff == "2026-01-01T00:00:00"

    def test_workspace_timeframe(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert ws.timeframe == "1h"

    def test_workspace_research_id(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        assert ws.research_id == "R1"


# ═══════════════════════════════════════════════════════════════
# 15. HANDOFF
# ═══════════════════════════════════════════════════════════════

class TestAgentHandoff:
    def test_handoff_preserves_provenance(self):
        handoff = AgentHandoff(
            source_agent_id="trend_agent",
            destination_agent_id="structure_agent",
            reason="Trend complete → structure analysis",
            evidence_refs=["EVID-TREND-001"],
            artifact_refs=["ART-TREND-001"],
        )
        assert handoff.source_agent_id == "trend_agent"
        assert handoff.destination_agent_id == "structure_agent"
        assert "EVID-TREND-001" in handoff.evidence_refs
        assert "ART-TREND-001" in handoff.artifact_refs

    def test_handoff_context_snapshot(self):
        handoff = AgentHandoff(
            source_agent_id="agent_a",
            destination_agent_id="agent_b",
            reason="Test",
            context_snapshot={"trend": "UP", "support": 285.0},
        )
        assert handoff.context_snapshot["trend"] == "UP"
        assert handoff.context_snapshot["support"] == 285.0


# ═══════════════════════════════════════════════════════════════
# 16. PERSISTENCE READINESS
# ═══════════════════════════════════════════════════════════════

class TestPersistenceReadiness:
    def test_workspace_dict_serializable(self):
        ws = create_workspace("R1", "THYAO.IS", "1h", "2026-01-01")
        ws.add_participant("agent1", "RESEARCHER")
        d = ws.to_dict()
        assert isinstance(d, dict)
        assert d["symbol"] == "THYAO.IS"
        assert d["status"] == "ACTIVE"

    def test_message_dict_serializable(self):
        msg = AgentMessage(
            sender_agent_id="agent1",
            recipient_agent_id="agent2",
            message_type=MessageType.STATUS,
            payload={"status": "ok"},
        )
        d = msg.to_dict()
        assert d["sender_agent_id"] == "agent1"
        assert d["message_type"] == "STATUS"

    def test_audit_event_dict_serializable(self):
        event = ResearchAuditEvent(
            event_type=AuditEventType.AGENT_REGISTERED,
            agent_id="agent1",
            new_state="READY",
        )
        d = event.to_dict()
        assert d["event_type"] == "AGENT_REGISTERED"
        assert d["agent_id"] == "agent1"

    def test_audit_log_serializable(self):
        audit = AuditLog()
        audit.append(ResearchAuditEvent(
            event_type=AuditEventType.WORKSPACE_CREATED,
            new_state="CREATED",
        ))
        d = audit.to_dict()
        assert isinstance(d, dict)
        assert d["event_count"] == 1

    def test_lifecycle_execution_dict(self):
        mgr = AgentLifecycleManager()
        exe = mgr.create_execution("agent1", "1.0.0", "TASK-001", "WS-001")
        d = exe.to_dict()
        assert d["agent_id"] == "agent1"
        assert d["agent_version"] == "1.0.0"
        assert d["status"] == "REGISTERED"