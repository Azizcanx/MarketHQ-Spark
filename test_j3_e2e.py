# -*- coding: utf-8 -*-
"""Phase J3 E2E — Real data THYAO.IS 1h.

Full pipeline: Market Data → Agent Router → Runtime → AgentResult → Audit → Provenance.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime, timezone

from provider_adapter import ProviderMetadata, RuntimeType, ProviderStatus, ProviderCapability, CapabilityType
from deterministic_runtime import DeterministicRuntime, DeterministicExecution, DeterministicRunStatus
from external_runtime import MockProviderRuntime, MockBehavior
from agent_router import AgentRouter, RouteStatus, create_default_router
from agent_runtime import AgentRuntime, AgentRun, AgentRunStatus, ExecutionMetadata
from agent_contract import BaseAgentAdapter, AgentResult, AgentStatus, MarketContext
from research_audit import AuditLog, ResearchAuditEvent, AuditEventType


def load_thyao_data():
    """Load THYAO.IS 1h data."""
    import json
    with open("/opt/markethq/data/ohlcv/THYAO.IS__1h.json") as f:
        data = json.load(f)
    bars = data.get("bars", [])
    df = pd.DataFrame(bars)
    # Rename timestamp to date for compatibility
    if "timestamp" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"timestamp": "date"})
    return df


def test_e2e_deterministic_runtime_with_real_data():
    """E2E: Deterministic runtime with real market data."""
    df = load_thyao_data()
    assert len(df) > 0, "No data loaded"

    rt = DeterministicRuntime()
    context = MarketContext(
        symbol="THYAO.IS",
        timeframe="1h",
        observation_timestamp=df['date'].iloc[-1],
        data_cutoff_timestamp=df['date'].iloc[-1],
    )
    result = rt.execute(
        agent_id="TREND",
        agent_version="1.0",
        context=context,
        timeout_seconds=60,
    )
    assert result.status == DeterministicRunStatus.COMPLETED
    assert result.result is not None
    assert result.result.status == AgentStatus.SUCCESS
    return result


def test_e2e_router_with_real_data():
    """E2E: Router selects runtime with real data context."""
    df = load_thyao_data()

    router = create_default_router()
    route = router.route(
        agent_id="TREND",
        task_id="TASK-E2E-001",
        required_capability="DETERMINISTIC",
        symbol="THYAO.IS",
        timeframe="1h",
        regime="TRENDING",
        deterministic_only=True,
    )
    assert route.status == RouteStatus.ROUTED
    assert route.selected_runtime == "RT-LOCAL-001"
    assert route.selected_provider == "PRV-DETERMINISTIC"
    assert len(route.reasoning) > 0
    return route


def test_e2e_agentruntime_v2_with_router():
    """E2E: AgentRuntime V2 execute_with_router."""
    df = load_thyao_data()

    agent_rt = AgentRuntime()
    router = create_default_router()

    context = MarketContext(
        symbol="THYAO.IS",
        timeframe="1h",
        observation_timestamp=df['date'].iloc[-1],
        data_cutoff_timestamp=df['date'].iloc[-1],
    )

    run = agent_rt.execute_with_router(
        agent_id="TREND",
        agent_version="1.0",
        router=router,
        context=context,
        task_id="TASK-E2E-002",
        workspace_id="WS-E2E",
        context_version="v1",
        required_capability="DETERMINISTIC",
        deterministic_only=True,
    )
    assert run.status == AgentRunStatus.COMPLETED
    assert run.result is not None
    assert run.metadata is not None
    assert run.metadata.runtime_id == "RT-LOCAL-001"
    assert run.metadata.provider_id == "PRV-DETERMINISTIC"
    assert run.metadata.context_version == "v1"
    return run


def test_e2e_mock_provider_failure_isolation():
    """E2E: Mock provider failure, deterministic fallback."""
    router = AgentRouter()
    mock = MockProviderRuntime()
    mock.set_behavior("FAILING_AGENT", MockBehavior.FAILURE)
    router.register_runtime(mock)

    det = DeterministicRuntime()
    router.register_runtime(det)
    router.set_fallback_chain(["RT-LOCAL-001"])

    # Mock fails
    route = router.route(agent_id="FAILING_AGENT", required_capability="DETERMINISTIC")
    assert route.status == RouteStatus.ROUTED  # Falls through to deterministic

    # Deterministic works independently
    result = det.execute(agent_id="SAFE_AGENT", agent_version="1.0", context=None)
    assert result.status == DeterministicRunStatus.COMPLETED


def test_e2e_audit_with_runtime_events():
    """E2E: Audit log captures runtime events."""
    log = AuditLog()

    # Simulate runtime lifecycle events
    log.append(ResearchAuditEvent(
        event_type=AuditEventType.RUNTIME_SELECTED,
        agent_id="TREND",
        metadata={"runtime_id": "RT-LOCAL-001", "provider_id": "PRV-DETERMINISTIC"},
    ))
    log.append(ResearchAuditEvent(
        event_type=AuditEventType.RUNTIME_STARTED,
        agent_id="TREND",
    ))
    log.append(ResearchAuditEvent(
        event_type=AuditEventType.RUNTIME_COMPLETED,
        agent_id="TREND",
        metadata={"duration_ms": 450},
    ))

    events = log.get_events()
    assert len(events) == 3

    runtime_events = log.get_events(AuditEventType.RUNTIME_SELECTED)
    assert len(runtime_events) == 1
    assert runtime_events[0].agent_id == "TREND"

    return log


def test_e2e_full_pipeline():
    """E2E: Full pipeline — router → runtime → audit → result."""
    df = load_thyao_data()

    # 1. Router selects runtime
    router = create_default_router()
    route = router.route(
        agent_id="TREND",
        required_capability="DETERMINISTIC",
        symbol="THYAO.IS",
        timeframe="1h",
        deterministic_only=True,
    )
    assert route.status == RouteStatus.ROUTED

    # 2. Runtime executes
    rt = DeterministicRuntime()
    context = MarketContext(
        symbol="THYAO.IS",
        timeframe="1h",
        observation_timestamp=df['date'].iloc[-1],
        data_cutoff_timestamp=df['date'].iloc[-1],
    )
    exec_result = rt.execute(
        agent_id="TREND",
        agent_version="1.0",
        context=context,
        timeout_seconds=60,
    )
    assert exec_result.status == DeterministicRunStatus.COMPLETED

    # 3. Audit
    log = AuditLog()
    log.append(ResearchAuditEvent(
        event_type=AuditEventType.RUNTIME_SELECTED,
        agent_id="TREND",
        metadata={"runtime_id": route.selected_runtime, "provider_id": route.selected_provider},
    ))
    log.append(ResearchAuditEvent(
        event_type=AuditEventType.RUNTIME_COMPLETED,
        agent_id="TREND",
        metadata={"execution_id": exec_result.execution_id, "duration_ms": exec_result.duration_ms},
    ))

    # 4. Result
    assert exec_result.result.status == AgentStatus.SUCCESS
    assert exec_result.result.symbol == "THYAO.IS"
    assert exec_result.result.timeframe == "1h"

    return {
        "route": route,
        "execution": exec_result,
        "audit_events": len(log._events),
    }


if __name__ == "__main__":
    print("E2E 1: Deterministic runtime with real data...")
    r1 = test_e2e_deterministic_runtime_with_real_data()
    print(f"  ✓ {r1.status.value} — {r1.execution_id}")

    print("E2E 2: Router with real data...")
    r2 = test_e2e_router_with_real_data()
    print(f"  ✓ {r2.status.value} → {r2.selected_runtime}")

    print("E2E 3: AgentRuntime V2 with router...")
    r3 = test_e2e_agentruntime_v2_with_router()
    print(f"  ✓ {r3.status.value} — runtime={r3.metadata.runtime_id}")

    print("E2E 4: Mock failure isolation...")
    r4 = test_e2e_mock_provider_failure_isolation()
    print(f"  ✓ Failure isolated, deterministic fallback works")

    print("E2E 5: Audit with runtime events...")
    r5 = test_e2e_audit_with_runtime_events()
    print(f"  ✓ {r5._events[0].event_type.value} logged")

    print("E2E 6: Full pipeline...")
    r6 = test_e2e_full_pipeline()
    print(f"  ✓ Route: {r6['route'].status.value}, Exec: {r6['execution'].status.value}, Audit: {r6['audit_events']} events")

    print("\nAll E2E tests passed!")