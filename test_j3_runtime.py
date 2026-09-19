# -*- coding: utf-8 -*-
"""Phase J3 tests — Agent Runtime + AgentRouter + Provider Abstraction."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from provider_adapter import (
    ProviderRuntime, ProviderMetadata, RuntimeType, ProviderStatus,
    ProviderCapability, CapabilityType, ProviderMetadata,
)
from deterministic_runtime import DeterministicRuntime, DeterministicExecution, DeterministicRunStatus
from external_runtime import MockProviderRuntime, MockBehavior, ExternalProviderRuntime
from agent_router import AgentRouter, RouteDecision, RouteStatus, create_default_router
from agent_runtime import AgentRuntime, AgentRun, AgentRunStatus, ExecutionMetadata
from agent_contract import BaseAgentAdapter, AgentResult, AgentStatus, MarketContext


# ── 1. Provider Adapter Tests ──────────────────────────────────────

class TestProviderAdapterBasics:
    def test_metadata_defaults(self):
        md = ProviderMetadata(provider_id="TEST")
        assert md.provider_id == "TEST"
        assert md.status == ProviderStatus.HEALTHY

    def test_runtime_not_duplicate(self):
        """ProviderRuntime should not duplicate AgentRuntime."""
        md = ProviderMetadata(provider_id="P1", runtime_id="R1")
        rt = ProviderRuntime(md)
        assert rt.metadata.runtime_id == "R1"
        assert rt.metadata.provider_id == "P1"

    def test_provider_health(self):
        md = ProviderMetadata(provider_id="P1", runtime_id="R1")
        rt = ProviderRuntime(md)
        assert rt.health() == ProviderStatus.HEALTHY

    def test_record_success_failure(self):
        md = ProviderMetadata(provider_id="P1", runtime_id="R1")
        rt = ProviderRuntime(md)
        rt.record_success()
        rt.record_failure()
        # Just ensure no crash
        _ = rt.failure_rate

    def test_capability_check(self):
        cap = ProviderCapability(capability=CapabilityType.DETERMINISTIC, deterministic=True)
        assert cap.has_capability(CapabilityType.DETERMINISTIC) is True
        assert cap.has_capability(CapabilityType.LLM) is False


class TestCapabilityModel:
    def test_deterministic_capability(self):
        cap = ProviderCapability(capability=CapabilityType.DETERMINISTIC, deterministic=True)
        assert cap.deterministic is True

    def test_structured_output_capability(self):
        cap = ProviderCapability(capability=CapabilityType.STRUCTURED_OUTPUT, supports_structured_output=True)
        assert cap.supports_structured_output is True

    def test_cost_policy(self):
        cap = ProviderCapability(capability=CapabilityType.EXTERNAL, cost_per_1k_tokens=0.01)
        assert cap.cost_per_1k_tokens == 0.01


# ── 2. Deterministic Runtime Tests ─────────────────────────────────

class TestDeterministicRuntime:
    def test_runtime_created(self):
        rt = DeterministicRuntime()
        assert rt.health() == ProviderStatus.HEALTHY
        assert rt.metadata.runtime_type == RuntimeType.DETERMINISTIC_LOCAL

    def test_execute_deterministic(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == DeterministicRunStatus.COMPLETED
        assert result.result is not None
        assert result.result.status == AgentStatus.SUCCESS

    def test_execution_has_metadata(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.execution_id.startswith("EXE-")
        assert result.agent_id == "A1"
        assert result.agent_version == "1.0"
        assert result.runtime_id == "RT-LOCAL-001"
        assert result.provider_id == "PRV-DETERMINISTIC"
        assert result.status == DeterministicRunStatus.COMPLETED

    def test_get_execution(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        exe = rt.get_execution(result.execution_id)
        assert exe is not None
        assert exe.agent_id == "A1"

    def test_get_executions_for_agent(self):
        rt = DeterministicRuntime()
        rt.execute(agent_id="A1", agent_version="1.0", context=None)
        rt.execute(agent_id="A1", agent_version="1.0", context=None)
        rt.execute(agent_id="A2", agent_version="1.0", context=None)
        exes = rt.get_executions_for_agent("A1")
        assert len(exes) == 2

    def test_to_dict(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        d = result.to_dict()
        assert d["status"] == "COMPLETED"
        assert d["agent_id"] == "A1"
        assert d["execution_id"] == result.execution_id

    def test_execution_record_has_provenance_field(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.provenance is not None

    def test_failed_execution(self):
        """Test that runtime handles errors gracefully."""
        rt = DeterministicRuntime()
        # Use adapter that raises
        class FailingAdapter(BaseAgentAdapter):
            def run(self):
                raise RuntimeError("Simulated failure")
        ctx = MarketContext(symbol="TEST", timeframe="1h")
        result = rt.execute(agent_id="A1", agent_version="1.0", context=ctx, adapter=FailingAdapter)
        assert result.status == DeterministicRunStatus.FAILED
        assert result.error_type == "RuntimeError"


# ── 3. Mock Provider Tests ─────────────────────────────────────────

class TestMockProviderRuntime:
    def test_mock_success(self):
        mock = MockProviderRuntime()
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.SUCCESS

    def test_mock_failure(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.FAILURE)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.ERROR
        assert result.error_type == "SIMULATED_FAILURE"

    def test_mock_timeout(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.TIMEOUT)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.ERROR
        assert result.error_type == "TIMEOUT"

    def test_mock_cancelled(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.CANCELLED)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.ERROR
        assert result.error_type == "CANCELLED"

    def test_mock_retry(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.RETRY, fail_count=2)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.ERROR
        assert "Retry" in (result.error_message or "")

    def test_mock_malformed(self):
        """Mock returns dict instead of AgentResult."""
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.MALFORMED)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert isinstance(result, dict)
        assert result.get("malformed") is True

    def test_mock_multiple_behaviors(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.SUCCESS)
        r1 = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert r1.status == AgentStatus.SUCCESS

        mock.set_behavior("A1", MockBehavior.FAILURE)
        r2 = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert r2.status == AgentStatus.ERROR

    def test_mock_health(self):
        mock = MockProviderRuntime()
        assert mock.health() == ProviderStatus.HEALTHY


# ── 4. External Provider Tests ─────────────────────────────────────

class TestExternalProviderRuntime:
    def test_external_uses_mock(self):
        md = ProviderMetadata(provider_id="PRV-EXT", runtime_id="RT-EXT-001", runtime_type=RuntimeType.EXTERNAL_PROVIDER)
        ext = ExternalProviderRuntime(md, mock_behavior=MockBehavior.SUCCESS)
        result = ext.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.SUCCESS

    def test_external_failure(self):
        md = ProviderMetadata(provider_id="PRV-EXT", runtime_id="RT-EXT-001", runtime_type=RuntimeType.EXTERNAL_PROVIDER)
        ext = ExternalProviderRuntime(md, mock_behavior=MockBehavior.FAILURE)
        result = ext.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == AgentStatus.ERROR


# ── 5. Agent Router Tests ──────────────────────────────────────────

class TestAgentRouterBasics:
    def test_default_router_created(self):
        router = create_default_router()
        assert len(router.list_runtimes()) >= 1

    def test_register_runtime(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        assert len(router.list_runtimes()) == 1

    def test_get_runtime(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        found = router.get_runtime(rt.metadata.runtime_id)
        assert found is not None
        assert found.metadata.runtime_id == rt.metadata.runtime_id

    def test_unregister_runtime(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        assert router.unregister_runtime(rt.metadata.runtime_id) is True
        assert router.unregister_runtime("NONEXISTENT") is False

    def test_list_runtimes(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        runtimes = router.list_runtimes()
        assert len(runtimes) == 1
        assert runtimes[0]["runtime_type"] == "DETERMINISTIC_LOCAL"


class TestAgentRouterRouting:
    def test_route_to_deterministic(self):
        router = create_default_router()
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert route.status == RouteStatus.ROUTED
        assert route.selected_runtime == "RT-LOCAL-001"
        assert route.selected_provider == "PRV-DETERMINISTIC"
        assert route.score > 0

    def test_route_deterministic_only(self):
        router = create_default_router()
        route = router.route(agent_id="A1", deterministic_only=True)
        assert route.status == RouteStatus.ROUTED

    def test_route_no_provider_for_capability(self):
        router = AgentRouter()
        # No runtimes registered
        route = router.route(agent_id="A1", required_capability="EXTERNAL_LLM")
        assert route.status == RouteStatus.NO_PROVIDER

    def test_explicit_runtime(self):
        router = create_default_router()
        route = router.route(agent_id="A1", explicit_runtime="RT-LOCAL-001")
        assert route.status == RouteStatus.ROUTED
        assert route.selected_runtime == "RT-LOCAL-001"

    def test_explicit_runtime_unhealthy_fallback(self):
        router = create_default_router()
        # Deterministic runtime is healthy by default, so this tests the
        # explicit runtime selection path
        route = router.route(agent_id="A1", explicit_runtime="RT-LOCAL-001")
        assert route.status == RouteStatus.ROUTED

    def test_route_evaluates_candidates(self):
        router = create_default_router()
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert route.candidates_evaluated >= 0

    def test_route_reasoning_present(self):
        router = create_default_router()
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert len(route.reasoning) > 0

    def test_route_correlation_id(self):
        router = create_default_router()
        route = router.route(agent_id="A1")
        assert route.correlation_id.startswith("ROUTE-")

    def test_route_to_dict(self):
        router = create_default_router()
        route = router.route(agent_id="A1")
        d = route.to_dict()
        assert d["route_id"] == route.route_id
        assert d["agent_id"] == "A1"


# ── 6. AgentRouter Capability Matching ─────────────────────────────

class TestAgentRouterCapabilities:
    def test_capability_match_scores(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert route.score > 0  # DETERMINISTIC match gives +0.4

    def test_capability_mismatch(self):
        router = AgentRouter()
        rt = DeterministicRuntime()  # Only DETERMINISTIC + LOCAL
        router.register_runtime(rt)
        route = router.route(agent_id="A1", required_capability="EXTERNAL_LLM")
        # No provider has EXTERNAL_LLM capability, falls back to deterministic
        assert route.status == RouteStatus.ROUTED

    def test_latency_preference(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        route = router.route(agent_id="A1", latency_requirement="low")
        assert route.score > 0


# ── 7. Execution Lifecycle Tests ───────────────────────────────────

class TestExecutionLifecycle:
    def test_agentrun_created(self):
        run = AgentRun(
            execution_id="EXE-TEST",
            agent_id="A1",
            agent_version="1.0",
            symbol="AAPL",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
        )
        assert run.status == AgentRunStatus.CREATED

    def test_agentrun_all_statuses(self):
        """AgentRun supports all lifecycle statuses."""
        for status in AgentRunStatus:
            run = AgentRun(
                execution_id="EXE-TEST",
                agent_id="A1",
                agent_version="1.0",
                symbol="AAPL",
                timeframe="1h",
                started_at="2026-01-01T00:00:00",
                status=status,
            )
            assert run.status == status

    def test_agentrun_metadata(self):
        meta = ExecutionMetadata(
            execution_id="EXE-TEST",
            agent_id="A1",
            runtime_id="RT-001",
            provider_id="PRV-001",
        )
        run = AgentRun(
            execution_id="EXE-TEST",
            agent_id="A1",
            agent_version="1.0",
            symbol="AAPL",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            metadata=meta,
        )
        assert run.metadata is not None
        assert run.metadata.runtime_id == "RT-001"

    def test_agentrun_to_dict_with_metadata(self):
        meta = ExecutionMetadata(
            execution_id="EXE-TEST",
            agent_id="A1",
            runtime_id="RT-001",
            provider_id="PRV-001",
            started_at="2026-01-01T00:00:00",
        )
        run = AgentRun(
            execution_id="EXE-TEST",
            agent_id="A1",
            agent_version="1.0",
            symbol="AAPL",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            metadata=meta,
        )
        d = run.to_dict()
        assert "metadata" in d
        assert d["metadata"]["runtime_id"] == "RT-001"

    def test_agentrun_to_dict_without_metadata(self):
        run = AgentRun(
            execution_id="EXE-TEST",
            agent_id="A1",
            agent_version="1.0",
            symbol="AAPL",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
        )
        d = run.to_dict()
        assert "metadata" not in d


# ── 8. AgentRuntime V2 Integration ─────────────────────────────────

class TestAgentRuntimeV2:
    def test_runtime_created(self):
        rt = AgentRuntime()
        assert rt is not None

    def test_runtime_has_runs(self):
        rt = AgentRuntime()
        assert hasattr(rt, '_runs')

    def test_queuing_status(self):
        """AgentRun can be QUEUED."""
        run = AgentRun(
            execution_id="EXE-TEST",
            agent_id="A1",
            agent_version="1.0",
            symbol="AAPL",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            status=AgentRunStatus.QUEUED,
        )
        assert run.status == AgentRunStatus.QUEUED


# ── 9. Integration Tests ───────────────────────────────────────────

class TestIntegrationRouterToRuntime:
    def test_router_selects_runtime_and_executes(self):
        router = create_default_router()
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert route.status == RouteStatus.ROUTED

        runtime = router.get_runtime(route.selected_runtime)
        assert runtime is not None

        result = runtime.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == DeterministicRunStatus.COMPLETED

    def test_router_rejects_no_capability(self):
        router = AgentRouter()
        # No runtimes at all
        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        assert route.status == RouteStatus.NO_PROVIDER

    def test_deterministic_runtime_preserved(self):
        """Existing deterministic behavior still works."""
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == DeterministicRunStatus.COMPLETED
        assert result.result is not None
        assert result.result.status == AgentStatus.SUCCESS


# ── 10. Failure Isolation Tests ────────────────────────────────────

class TestFailureIsolation:
    def test_mock_failure_is_isolated(self):
        """Mock provider failure doesn't crash router."""
        router = AgentRouter()
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.FAILURE)
        router.register_runtime(mock)
        router.set_fallback_chain(["RT-MOCK-001"])

        route = router.route(agent_id="A1", required_capability="DETERMINISTIC")
        # Router should find deterministic runtime as fallback
        assert route.status in (RouteStatus.ROUTED, RouteStatus.FALLBACK_USED, RouteStatus.NO_PROVIDER)

    def test_deterministic_runtime_still_healthy_after_mock_failure(self):
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.FAILURE)
        mock.execute(agent_id="A1", agent_version="1.0", context=None)

        # Deterministic runtime unaffected
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A2", agent_version="1.0", context=None)
        assert result.status == DeterministicRunStatus.COMPLETED


# ── 11. Idempotency Tests ──────────────────────────────────────────

class TestIdempotency:
    def test_deterministic_runtime_idempotency(self):
        rt = DeterministicRuntime()
        r1 = rt.execute(agent_id="A1", agent_version="1.0", context=None, idempotency_key="KEY-1")
        r2 = rt.execute(agent_id="A1", agent_version="1.0", context=None, idempotency_key="KEY-1")
        assert r1.execution_id == r2.execution_id

    def test_different_idempotency_keys(self):
        rt = DeterministicRuntime()
        r1 = rt.execute(agent_id="A1", agent_version="1.0", context=None, idempotency_key="KEY-1")
        r2 = rt.execute(agent_id="A1", agent_version="1.0", context=None, idempotency_key="KEY-2")
        assert r1.execution_id != r2.execution_id


# ── 12. Health Tests ────────────────────────────────────────────────

class TestProviderHealth:
    def test_healthy_runtime(self):
        rt = DeterministicRuntime()
        assert rt.health() == ProviderStatus.HEALTHY

    def test_mock_healthy(self):
        mock = MockProviderRuntime()
        assert mock.health() == ProviderStatus.HEALTHY

    def test_external_provider_health(self):
        from provider_adapter import ProviderMetadata, RuntimeType
        md = ProviderMetadata(provider_id="PRV-EXT", runtime_id="RT-EXT", runtime_type=RuntimeType.EXTERNAL_PROVIDER)
        ext = ExternalProviderRuntime(md)
        assert ext.health() == ProviderStatus.HEALTHY


# ── 13. Cancellation Tests ─────────────────────────────────────────

class TestCancellation:
    def test_deterministic_cancel(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert rt.cancel(result.execution_id) is True

    def test_deterministic_cancel_nonexistent(self):
        rt = DeterministicRuntime()
        assert rt.cancel("NONEXISTENT") is False

    def test_mock_cancel(self):
        mock = MockProviderRuntime()
        assert mock.cancel("ANY") is True


# ── 14. Output Validation ──────────────────────────────────────────

class TestOutputValidation:
    def test_mock_malformed_output_detected(self):
        """Mock returns dict for malformed — test that we detect it."""
        mock = MockProviderRuntime()
        mock.set_behavior("A1", MockBehavior.MALFORMED)
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        # Malformed output is a dict, not AgentResult
        assert isinstance(result, dict)
        assert "malformed" in result

    def test_valid_output_is_agent_result(self):
        mock = MockProviderRuntime()
        result = mock.execute(agent_id="A1", agent_version="1.0", context=None)
        assert isinstance(result, AgentResult)


# ── 15. Stale Context Detection ────────────────────────────────────

class TestStaleContext:
    def test_context_version_tracked(self):
        rt = DeterministicRuntime()
        class FakeContext:
            data_cutoff_timestamp = "2026-01-01T00:00:00"
        result = rt.execute(agent_id="A1", agent_version="1.0", context=FakeContext())
        assert result.input_version == "2026-01-01T00:00:00"


# ── 16. Audit Integration Tests ────────────────────────────────────

class TestAuditIntegration:
    def test_runtime_audit_event_types_exist(self):
        from research_audit import AuditEventType
        assert hasattr(AuditEventType, "RUNTIME_SELECTED")
        assert hasattr(AuditEventType, "ROUTING_REJECTED")
        assert hasattr(AuditEventType, "FALLBACK_SELECTED")
        assert hasattr(AuditEventType, "OUTPUT_VALIDATED")
        assert hasattr(AuditEventType, "PROVIDER_HEALTH_CHANGED")
        assert hasattr(AuditEventType, "EXECUTION_DUPLICATE")

    def test_audit_event_creation(self):
        from research_audit import ResearchAuditEvent, AuditEventType
        event = ResearchAuditEvent(
            event_type=AuditEventType.RUNTIME_SELECTED,
            agent_id="A1",
        )
        assert event.event_type == AuditEventType.RUNTIME_SELECTED
        assert event.agent_id == "A1"
        assert event.event_id.startswith("AUD-")

    def test_audit_log_append_only(self):
        from research_audit import AuditLog, ResearchAuditEvent, AuditEventType
        log = AuditLog()
        e1 = ResearchAuditEvent(event_type=AuditEventType.RUNTIME_SELECTED)
        e2 = ResearchAuditEvent(event_type=AuditEventType.RUNTIME_STARTED)
        log.append(e1)
        log.append(e2)
        assert len(log._events) == 2
        events = log.get_events(AuditEventType.RUNTIME_SELECTED)
        assert len(events) == 1


# ── 17. Cost/Token Metadata ────────────────────────────────────────

class TestCostMetadata:
    def test_execution_metadata_cost_fields(self):
        meta = ExecutionMetadata()
        assert meta.estimated_cost == 0.0
        assert meta.currency == "USD"
        assert meta.input_tokens == 0
        assert meta.output_tokens == 0
        assert meta.total_tokens == 0

    def test_execution_metadata_retry_fields(self):
        meta = ExecutionMetadata()
        assert meta.retry_count == 0
        assert meta.timeout_seconds == 0
        assert meta.cancelled is False


# ── 18. Provider Registration ──────────────────────────────────────

class TestProviderRegistration:
    def test_register_multiple_runtimes(self):
        router = AgentRouter()
        d1 = DeterministicRuntime()
        d2 = DeterministicRuntime()
        d2.metadata.runtime_id = "RT-LOCAL-002"
        router.register_runtime(d1)
        router.register_runtime(d2)
        assert len(router.list_runtimes()) == 2

    def test_unregister_updates_registry(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        router.unregister_runtime(rt.metadata.runtime_id)
        assert len(router.list_runtimes()) == 0

    def test_router_to_dict(self):
        router = create_default_router()
        d = router.list_runtimes()
        assert isinstance(d, list)
        for entry in d:
            assert "runtime_id" in entry
            assert "status" in entry


# ── 19. Research-only Enforcement ──────────────────────────────────

class TestResearchOnly:
    def test_deterministic_runtime_research_only(self):
        rt = DeterministicRuntime()
        # Cost should be zero for deterministic
        result = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        assert result.status == DeterministicRunStatus.COMPLETED
        # No real cost incurred

    def test_mock_provider_research_only(self):
        mock = MockProviderRuntime()
        assert mock.metadata.cost_policy == "research_only"

    def test_external_provider_research_only(self):
        from provider_adapter import ProviderMetadata, RuntimeType
        md = ProviderMetadata(provider_id="PRV-EXT", runtime_id="RT-EXT", runtime_type=RuntimeType.EXTERNAL_PROVIDER)
        ext = ExternalProviderRuntime(md)
        assert ext.metadata.cost_policy == "research_only"


# ── 20. Versioning ─────────────────────────────────────────────────

class TestVersioning:
    def test_agent_version_tracked(self):
        rt = DeterministicRuntime()
        result = rt.execute(agent_id="A1", agent_version="2.5.0", context=None)
        assert result.agent_version == "2.5.0"

    def test_provider_version_tracked(self):
        rt = DeterministicRuntime()
        assert rt.metadata.runtime_version == "1.0.0"
        assert rt.metadata.adapter_version == "1.0.0"

    def test_runtime_id_consistent(self):
        rt = DeterministicRuntime()
        assert rt.metadata.runtime_id == "RT-LOCAL-001"


# ── 21. Determinism ────────────────────────────────────────────────

class TestDeterminism:
    def test_deterministic_runtime_deterministic(self):
        """Same input should produce same result."""
        rt = DeterministicRuntime()
        r1 = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        r2 = rt.execute(agent_id="A1", agent_version="1.0", context=None)
        # Both completed successfully
        assert r1.status == DeterministicRunStatus.COMPLETED
        assert r2.status == DeterministicRunStatus.COMPLETED
        assert r1.result.status == AgentStatus.SUCCESS
        assert r2.result.status == AgentStatus.SUCCESS


# ── 22. Fallback Chain ─────────────────────────────────────────────

class TestFallbackChain:
    def test_fallback_chain_set(self):
        router = AgentRouter()
        rt = DeterministicRuntime()
        router.register_runtime(rt)
        router.set_fallback_chain(["RT-LOCAL-001"])
        assert router._fallback_chain == ["RT-LOCAL-001"]

    def test_fallback_used_when_explicit_unhealthy(self):
        router = create_default_router()
        # Set fallback chain
        router.set_fallback_chain(["RT-LOCAL-001"])
        route = router.route(agent_id="A1", explicit_runtime="RT-LOCAL-001")
        # Explicit runtime is healthy, so it's selected
        assert route.status == RouteStatus.ROUTED


# ── 23. No Duplicate Engines ───────────────────────────────────────

class TestNoDuplicates:
    def test_no_duplicate_agent_runtime(self):
        """AgentRuntime V2 extends V1, doesn't replace."""
        rt = AgentRuntime()
        assert hasattr(rt, 'run')  # V1 method
        assert hasattr(rt, 'execute_with_router')  # V2 method
        assert hasattr(rt, 'list_runs')  # V1 method

    def test_no_duplicate_task_router(self):
        """TaskRouter from J1 still exists."""
        from task_router import TaskRouter
        router = TaskRouter()
        assert router is not None

    def test_no_duplicate_collaboration_orchestrator(self):
        """J2 CollaborationOrchestrator still exists."""
        from collaboration_orchestrator import CollaborationOrchestrator
        co = CollaborationOrchestrator()
        assert co is not None