# -*- coding: utf-8 -*-
"""Phase J4 Test Suite.

Tests for:
- MarketObservation model
- ResearchPriorityEngine
- ResearchPlanner
- AdaptiveTeamSelector
- DataQualityGate
- AutonomousResearchLoop (full cycle)
"""

import sys
import traceback
from datetime import datetime, timezone

from market_observation import MarketObservation, ObservationBundle, DataQuality
from research_priority_engine import (
    OpportunityCandidate, ResearchPriorityEngine, PriorityLevel, ResearchTask,
)
from research_planner import ResearchPlanner, ResearchPlan
from adaptive_team_selector import AdaptiveTeamSelector, TeamSelection, AgentReliability
from data_quality_gate import DataQualityGateChecker, DataQualityGateResult
from autonomous_research_loop import (
    AutonomousResearchLoop, AutonomousResearchRun, AutonomousResearchReport, LoopState,
)

passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  PASS: {name}")
    except Exception as e:
        failed += 1
        errors.append((name, traceback.format_exc()))
        print(f"  FAIL: {name} — {e}")


# === MarketObservation ===

def test_market_observation_creation():
    obs = MarketObservation(
        symbol="THYAO.IS", timeframe="1h",
        data_quality=DataQuality.GOOD, bar_count=100,
        ohlcv_available=True, source="BIST"
    )
    assert obs.observation_id.startswith("OBS-")
    assert obs.symbol == "THYAO.IS"
    d = obs.to_dict()
    assert d["symbol"] == "THYAO.IS"
    assert d["data_quality"] == "GOOD"

def test_observation_bundle():
    obs1 = MarketObservation(symbol="THYAO.IS", data_quality=DataQuality.GOOD)
    obs2 = MarketObservation(symbol="THYAO.IS", data_quality=DataQuality.DEGRADED)
    bundle = ObservationBundle(observations=[obs1, obs2])
    assert bundle.total_count == 2
    assert bundle.quality_summary.get("GOOD") == 1
    assert bundle.quality_summary.get("DEGRADED") == 1
    assert bundle.error_count == 0

def test_data_quality_enum():
    assert DataQuality.GOOD.value == "GOOD"
    assert DataQuality.NO_DATA.value == "NO_DATA"
    assert DataQuality.INSUFFICIENT.value == "INSUFFICIENT"


# === ResearchPriorityEngine ===

def test_priority_engine_score():
    engine = ResearchPriorityEngine()
    cand = OpportunityCandidate(
        symbol="THYAO.IS", timeframe="1h", direction="LONG",
        confidence=0.8, regime="TRENDING"
    )
    result = engine.score(cand, novelty=0.8, evidence_strength=0.9, evidence_conflict=0.1)
    assert "score" in result
    assert "priority" in result
    assert 0 <= result["score"] <= 1

def test_priority_level_assignment():
    engine = ResearchPriorityEngine()
    # High score should give CRITICAL or HIGH
    cand = OpportunityCandidate(confidence=0.95)
    result = engine.score(cand, novelty=0.95, evidence_strength=0.95)
    assert result["priority"] in ("CRITICAL", "HIGH")

def test_priority_rank():
    engine = ResearchPriorityEngine()
    cands = [
        OpportunityCandidate(symbol="A", confidence=0.9),
        OpportunityCandidate(symbol="B", confidence=0.3),
        OpportunityCandidate(symbol="C", confidence=0.6),
    ]
    ranked = engine.rank(cands)
    assert ranked[0]["symbol"] == "A"
    assert ranked[-1]["symbol"] == "B"

def test_research_task_idempotency():
    t1 = ResearchTask(agent_id="agent-1", symbol="THYAO.IS", timeframe="1h", task_type="ANALYZE")
    t2 = ResearchTask(agent_id="agent-1", symbol="THYAO.IS", timeframe="1h", task_type="ANALYZE")
    assert t1.idempotency_key == t2.idempotency_key
    t3 = ResearchTask(agent_id="agent-2", symbol="THYAO.IS", timeframe="1h", task_type="ANALYZE")
    assert t1.idempotency_key != t3.idempotency_key


# === ResearchPlanner ===

def test_research_planner_creation():
    planner = ResearchPlanner()
    assert planner is not None

def test_research_plan():
    plan = ResearchPlan()
    assert plan is not None


# === AdaptiveTeamSelector ===

def test_adaptive_team_selector():
    selector = AdaptiveTeamSelector()
    assert selector is not None


# === DataQualityGate ===

def test_data_quality_gate_creation():
    gate = DataQualityGateChecker()
    assert gate is not None


# === AutonomousResearchLoop ===

def test_loop_creation():
    loop = AutonomousResearchLoop()
    assert loop.state == LoopState.IDLE

def test_start_cycle():
    loop = AutonomousResearchLoop()
    run = loop.start_cycle(symbol_scope="THYAO.IS", timeframe_scope="1h")
    assert run.run_id.startswith("RUN-")
    assert run.cycle_id.startswith("CYC-")
    assert loop.state == LoopState.OBSERVING

def test_full_cycle_deterministic():
    loop = AutonomousResearchLoop()
    report = loop.run_full_cycle(symbol_scope="THYAO.IS")
    assert isinstance(report, AutonomousResearchReport)
    assert report.report_id.startswith("RPT-")
    assert report.run is not None
    assert len(report.run.state_history) > 0

def test_cancel_cycle():
    loop = AutonomousResearchLoop()
    loop.start_cycle(symbol_scope="X")
    loop.cancel()
    assert loop.state == LoopState.IDLE
    assert loop.run.cancelled is True

def test_double_start_raises():
    loop = AutonomousResearchLoop()
    loop.start_cycle(symbol_scope="A")
    try:
        loop.start_cycle(symbol_scope="B")
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass  # expected

def test_state_history():
    loop = AutonomousResearchLoop()
    loop.run_full_cycle(symbol_scope="THYAO.IS")
    history = loop.get_state_history()
    assert len(history) > 0
    assert all("from" in h and "to" in h for h in history)

def test_audit_events():
    loop = AutonomousResearchLoop()
    loop.run_full_cycle(symbol_scope="THYAO.IS")
    events = loop.get_audit_events()
    assert len(events) > 0

def test_complete_run():
    loop = AutonomousResearchLoop()
    loop.run_full_cycle(symbol_scope="THYAO.IS")
    report = loop.complete_run()
    assert report.run.status == "COMPLETED"
    assert loop.state == LoopState.IDLE

def test_loop_safety_max_cycles():
    loop = AutonomousResearchLoop()
    run = loop.start_cycle(max_cycles=5)
    assert run.max_cycles == 5


# === Run all ===

def run_all():
    print("\n=== Phase J4 Tests ===\n")

    print("[MarketObservation]")
    test("MarketObservation creation", test_market_observation_creation)
    test("ObservationBundle", test_observation_bundle)
    test("DataQuality enum", test_data_quality_enum)

    print("\n[ResearchPriorityEngine]")
    test("Score calculation", test_priority_engine_score)
    test("Priority level assignment", test_priority_level_assignment)
    test("Rank candidates", test_priority_rank)
    test("ResearchTask idempotency", test_research_task_idempotency)

    print("\n[ResearchPlanner]")
    test("Planner creation", test_research_planner_creation)
    test("ResearchPlan creation", test_research_plan)

    print("\n[AdaptiveTeamSelector]")
    test("Selector creation", test_adaptive_team_selector)

    print("\n[DataQualityGate]")
    test("Gate creation", test_data_quality_gate_creation)

    print("\n[AutonomousResearchLoop]")
    test("Loop creation", test_loop_creation)
    test("Start cycle", test_start_cycle)
    test("Full cycle deterministic", test_full_cycle_deterministic)
    test("Cancel cycle", test_cancel_cycle)
    test("Double start raises", test_double_start_raises)
    test("State history", test_state_history)
    test("Audit events", test_audit_events)
    test("Complete run", test_complete_run)
    test("Safety max_cycles", test_loop_safety_max_cycles)

    print(f"\n=== Results: {passed} PASS, {failed} FAIL ===")
    if errors:
        print("\nFailures:")
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)
    return failed == 0

if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
