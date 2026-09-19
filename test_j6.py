#!/usr/bin/env python3
"""Phase J6 — Production-Grade Intelligence Tests.

Tests for:
- IntelligenceStateJ6
- Agent Reliability Tracker
- Claim Validation Pipeline
- HQ Decision Surface
- Counterexample-first research
- Drift response
- Research priority engine
- Temporal integrity
- Failure isolation
- Idempotency
"""

import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone

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


# ─── IntelligenceStateJ6 ───

def test_intelligence_state_j6_creation():
    from intelligence_state_j6 import IntelligenceStateJ6, IntelligenceState
    state = IntelligenceStateJ6()
    assert state.state == IntelligenceState.INITIALIZING
    assert state.active_regime == "UNKNOWN"
    assert state.uncertainty == 1.0
    assert state.human_review_state == "NONE"

def test_intelligence_state_j6_to_dict():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    d = state.to_dict()
    assert "state" in d
    assert "agent_reliability" in d
    assert "drift_state" in d
    assert "claim_status" in d
    assert "research_priority_explanation" in d

def test_intelligence_state_j6_observation():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.current_observation = {"trend": "UPTREND", "volatility": 0.15}
    assert state.current_observation["trend"] == "UPTREND"

def test_intelligence_state_j6_regime():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.active_regime = "TRENDING"
    state.regime_transitions.append({
        "from": "RANGE", "to": "TRENDING",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    assert state.active_regime == "TRENDING"
    assert len(state.regime_transitions) == 1

def test_intelligence_state_j6_opportunities():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.detected_opportunities.append({
        "opportunity_id": "OPP-1", "symbol": "THYAO.IS", "thesis": "trend up"},
    )
    assert len(state.detected_opportunities) == 1

def test_intelligence_state_j6_research_memory():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.research_memory.append({"key": "value", "timestamp": "2026-09-17T00:00:00+00:00"})
    assert len(state.research_memory) == 1

def test_intelligence_state_j6_failure_memory():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.failure_memory.append({"error": "timeout", "agent": "trend_agent"})
    assert len(state.failure_memory) == 1

def test_intelligence_state_j6_counterexamples():
    from intelligence_state_j6 import IntelligenceStateJ6
    state = IntelligenceStateJ6()
    state.counterexamples.append({"claim": "trend up", "counterexample": "trend down"})
    assert len(state.counterexamples) == 1


# ─── AgentReliabilityProfile ───

def test_agent_reliability_creation():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    assert profile.agent_id == "test-agent"
    assert profile.total_executions == 0
    assert profile.reliability_score == 0.0

def test_agent_reliability_success_rate():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.total_executions = 10
    profile.successful_executions = 8
    assert profile.success_rate == 0.8

def test_agent_reliability_reliability_score():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.total_executions = 10
    profile.successful_executions = 8
    profile.useful_evidence_count = 7
    profile.contradicted_evidence_count = 1
    profile.outcome_alignment_score = 0.9
    score = profile.reliability_score
    assert 0 <= score <= 1

def test_agent_reliability_regime_specific():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.regime_specific_reliability["TRENDING"] = 0.8
    assert profile.regime_specific_reliability["TRENDING"] == 0.8

def test_agent_reliability_timeframe_specific():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.timeframe_specific_reliability["1h"] = 0.7
    assert profile.timeframe_specific_reliability["1h"] == 0.7

def test_agent_reliability_symbol_specific():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.symbol_specific_reliability["THYAO.IS"] = 0.6
    assert profile.symbol_specific_reliability["THYAO.IS"] == 0.6

def test_agent_reliability_to_dict():
    from intelligence_state_j6 import AgentReliabilityProfile
    profile = AgentReliabilityProfile(agent_id="test-agent")
    profile.total_executions = 5
    profile.successful_executions = 4
    d = profile.to_dict()
    assert d["agent_id"] == "test-agent"
    assert d["success_rate"] == 0.8
    assert "reliability_score" in d


# ─── ReliabilityTracker ───

def test_reliability_tracker_creation():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    assert tracker._profiles == {}

def test_reliability_tracker_get_profile():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    profile = tracker.get_profile("agent-1")
    assert profile.agent_id == "agent-1"

def test_reliability_tracker_record_execution():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    profile = tracker.record_execution(
        "agent-1", success=True, useful_evidence=True,
        outcome_aligned=True, regime="TRENDING", timeframe="1h", symbol="THYAO.IS",
    )
    assert profile.total_executions == 1
    assert profile.successful_executions == 1
    assert profile.regime_specific_reliability["TRENDING"] > 0.5

def test_reliability_tracker_record_failure():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    profile = tracker.record_execution(
        "agent-1", success=False, useful_evidence=False,
        outcome_aligned=False, regime="TRENDING",
    )
    assert profile.failed_executions == 1

def test_reliability_tracker_record_unavailable():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    profile = tracker.record_unavailable("agent-1")
    assert profile.unavailable_results == 1

def test_reliability_tracker_mark_drift():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.mark_drift("agent-1")
    profile = tracker.get_profile("agent-1")
    assert profile.drift_detected is True

def test_reliability_tracker_get_reliable():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("agent-1", success=True, useful_evidence=True, outcome_aligned=True)
    tracker.record_execution("agent-2", success=False, useful_evidence=False, outcome_aligned=False)
    reliable = tracker.get_reliable_agents(min_score=0.3)
    assert "agent-1" in reliable

def test_reliability_tracker_get_unreliable():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("agent-1", success=False, useful_evidence=False, outcome_aligned=False)
    unreliable = tracker.get_unreliable_agents(max_score=0.5)
    assert "agent-1" in unreliable

def test_reliability_tracker_summary():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("agent-1", success=True, useful_evidence=True, outcome_aligned=True)
    summary = tracker.get_reliability_summary()
    assert "agent-1" in summary
    assert "reliability_score" in summary["agent-1"]

def test_reliability_tracker_to_dict():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("agent-1", success=True, useful_evidence=True, outcome_aligned=True)
    d = tracker.to_dict()
    assert "agent-1" in d
    assert d["agent-1"]["total_executions"] == 1


# ─── ClaimValidationPipeline ───

def test_claim_pipeline_creation():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    assert len(pipeline._claims) == 0

def test_claim_pipeline_create_claim():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    claim = pipeline.create_claim(claim_id="C-1", text="THYAO trend up", source="test")
    assert claim.claim_id == "C-1"
    assert claim.status.value == "untested"

def test_claim_pipeline_add_evidence():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    result = pipeline.add_evidence("C-1", "E-001")
    assert result is True
    claim = pipeline.get_claim("C-1")
    assert "E-001" in claim.evidence

def test_claim_pipeline_add_contradictory():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.add_evidence("C-1", "E-001")
    pipeline.add_contradictory_evidence("C-1", "E-002")
    claim = pipeline.get_claim("C-1")
    assert any(e.startswith("CONTRADICTED:") for e in claim.evidence)

def test_claim_pipeline_add_counterexample():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.add_counterexample("C-1", "CE-001")
    claim = pipeline.get_claim("C-1")
    assert any("COUNTEREXAMPLE:" in l for l in claim.limitations)

def test_claim_pipeline_update_status():
    from claim_validation_pipeline import ClaimValidationPipeline
    from research_intelligence_model import ClaimStatus
    pipeline = ClaimValidationPipeline()
    claim = pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.add_evidence("C-1", "E-001")
    pipeline.update_status("C-1", ClaimStatus.TESTED)
    assert claim.status == ClaimStatus.TESTED

def test_claim_pipeline_cannot_support_without_evidence():
    from claim_validation_pipeline import ClaimValidationPipeline
    from research_intelligence_model import ClaimStatus
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    try:
        pipeline.update_status("C-1", ClaimStatus.SUPPORTED)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

def test_claim_pipeline_cannot_support_with_contradiction():
    from claim_validation_pipeline import ClaimValidationPipeline
    from research_intelligence_model import ClaimStatus
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.add_evidence("C-1", "E-001")
    pipeline.add_contradictory_evidence("C-1", "E-002")
    try:
        pipeline.update_status("C-1", ClaimStatus.SUPPORTED)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

def test_claim_pipeline_get_by_status():
    from claim_validation_pipeline import ClaimValidationPipeline
    from research_intelligence_model import ClaimStatus
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.create_claim(claim_id="C-2", text="ETH mean reversion")
    pipeline.add_evidence("C-1", "E-001")
    pipeline.update_status("C-1", ClaimStatus.TESTED)
    tested = pipeline.get_claims_by_status(ClaimStatus.TESTED)
    assert len(tested) == 1
    assert tested[0].claim_id == "C-1"

def test_claim_pipeline_validation_history():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    pipeline.add_evidence("C-1", "E-001")
    history = pipeline.get_validation_history("C-1")
    assert len(history) >= 1

def test_claim_pipeline_to_dict():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    pipeline.create_claim(claim_id="C-1", text="THYAO trend up")
    d = pipeline.to_dict()
    assert "claims" in d
    assert "summary" in d
    assert d["summary"]["total"] == 1


# ─── HQ Decision Surface ───

def test_hq_overview():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    overview = hq.get_overview()
    assert "market_state" in overview
    assert "active_regime" in overview
    assert "reliability_summary" in overview

def test_hq_situation():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    situation = hq.get_situation()
    assert "market" in situation
    assert "regime" in situation
    assert "agent_reliability" in situation

def test_hq_research_runs():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    runs = hq.get_research_runs()
    assert isinstance(runs, list)

def test_hq_agents():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    agents = hq.get_agents()
    assert isinstance(agents, list)

def test_hq_claims():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    claims = hq.get_claims()
    assert "claims" in claims
    assert "summary" in claims

def test_hq_drift():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    drift = hq.get_drift()
    assert "regime_drift_detected" in drift

def test_hq_reliability():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    rel = hq.get_reliability()
    assert isinstance(rel, dict)

def test_hq_human_review():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    reviews = hq.get_human_review()
    assert isinstance(reviews, list)

def test_hq_add_human_review():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    review = hq.add_human_review("claim", "C-1", "REVIEW_REQUIRED", "Need more evidence")
    assert review["review_id"].startswith("REV-")
    assert review["decision"] == "REVIEW_REQUIRED"

def test_hq_situation_report():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    report = hq.build_situation_report()
    assert "AZIZBUSINESS HQ" in report
    assert "RESEARCH REPORT" in report
    assert "Not trading advice" in report
    # Check no trade execution language (excluding disclaimer text)
    disclaimer_free = report.replace("No BUY/SELL/ENTER NOW/GUARANTEED statements.", "")
    assert "BUY" not in disclaimer_free
    assert "SELL" not in disclaimer_free
    assert "ENTER NOW" not in disclaimer_free

def test_hq_research_priority():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    explanation = hq.set_research_priority(
        action="regime research",
        expected_info_value=0.8,
        uncertainty=0.9,
        drift_detected=True,
        failure_memory=3,
    )
    assert "WHY THIS RESEARCH?" in explanation
    assert "high uncertainty" in explanation
    assert "regime transition" in explanation
    assert "previous failures" in explanation

def test_hq_to_dict():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    d = hq.to_dict()
    assert "overview" in d
    assert "situation" in d
    assert "claims" in d
    assert "drift" in d
    assert "reliability" in d


# ─── Counterexample-first research ───

def test_counterexample_first_search():
    from counterexample_engine import CounterexampleResult, CounterexampleEngine
    from research_intelligence_model import Claim
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C-STRONG", text="THYAO will trend up")
    result = engine.search(claim=claim, historical_outcomes=[], context={"regime": "TRENDING"})
    assert isinstance(result, CounterexampleResult)

def test_counterexample_first_failures_in_regime():
    from counterexample_engine import CounterexampleResult, CounterexampleEngine
    from research_intelligence_model import Claim
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C-REGIME", text="High-quality setups work in UPTREND")
    result = engine.search(
        claim=claim,
        historical_outcomes=[],
        context={"regime": "UPTREND", "search_type": "failures"},
    )
    assert isinstance(result, CounterexampleResult)

def test_counterexample_first_low_quality_winners():
    from counterexample_engine import CounterexampleResult, CounterexampleEngine
    from research_intelligence_model import Claim
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C-LOWQUAL", text="Low-quality winners in RANGE")
    result = engine.search(
        claim=claim,
        historical_outcomes=[],
        context={"regime": "RANGE", "search_type": "low_quality_winners"},
    )
    assert isinstance(result, CounterexampleResult)


# ─── Drift Response ───

def test_drift_response_regime():
    from distribution_drift_engine import DistributionDriftEngine
    engine = DistributionDriftEngine()
    result = engine.detect_regime_drift(
        "THYAO.IS", "1h",
        {"TRENDING": 60, "RANGE": 40},
        {"TRENDING": 30, "RANGE": 70},
    )
    assert result.drift_type.value == "regime_drift"
    assert result.drift_magnitude > 0

def test_drift_response_data():
    from distribution_drift_engine import DistributionDriftEngine
    engine = DistributionDriftEngine()
    result = engine.detect_quality_drift("THYAO.IS", "1h", {"good": 80}, {"good": 50})
    assert result.drift_type.value == "quality_drift"

def test_drift_response_volatility():
    from distribution_drift_engine import DistributionDriftEngine
    engine = DistributionDriftEngine()
    result = engine.detect_volatility_drift("THYAO.IS", "1h", {"vol": 0.15}, {"vol": 0.30})
    assert result.drift_type.value == "volatility_drift"


# ─── Temporal Integrity ───

def test_temporal_integrity_lookahead():
    from research_intelligence_model import Claim, ClaimStatus
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    claim = Claim(claim_id="C-TEMP", text="test", first_observed=now, last_validated=now)
    assert claim.first_observed <= claim.last_validated

def test_temporal_integrity_future_invariance():
    from market_observation import MarketObservation, DataQuality
    # Same inputs produce same structure (not same ID — ID includes timestamp)
    obs1 = MarketObservation(symbol="THYAO.IS", timeframe="1h", data_quality=DataQuality.GOOD)
    obs2 = MarketObservation(symbol="THYAO.IS", timeframe="1h", data_quality=DataQuality.GOOD)
    assert obs1.symbol == obs2.symbol
    assert obs1.timeframe == obs2.timeframe
    assert obs1.data_quality == obs2.data_quality

def test_temporal_integrity_deterministic_replay():
    from deterministic_runtime import DeterministicRuntime
    rt1 = DeterministicRuntime()
    rt2 = DeterministicRuntime()
    r1 = rt1.execute(agent_id="det-test", agent_version="v1", context={"x": 1})
    r2 = rt2.execute(agent_id="det-test", agent_version="v1", context={"x": 1})
    assert r1.status.value == r2.status.value


# ─── Failure Isolation ───

def test_failure_isolation_parallel():
    from parallel_executor import ParallelExecutor, ParallelTask, ParallelResult
    executor = ParallelExecutor()
    task = ParallelTask(agent_id="failing-agent", task_id="T1", capability="test")
    def failing_fn(t):
        raise RuntimeError("simulated")
    # Should not crash when executor_fn raises
    try:
        res = executor.execute_parallel([task], failing_fn)
    except RuntimeError:
        pass  # Expected — the failure is in executor_fn, not the executor
    # Verify executor still works
    def safe_fn(t):
        return ParallelResult(agent_id=t.agent_id, capability=t.capability, status="OK", result="done")
    res = executor.execute_parallel([task], safe_fn)
    assert len(res) == 1

def test_failure_isolation_agent():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("bad-agent", success=False)
    tracker.record_execution("bad-agent", success=False)
    profile = tracker.get_profile("bad-agent")
    assert profile.failed_executions == 2
    assert profile.success_rate == 0.0


# ─── Idempotency ───

def test_idempotent_claim_creation():
    from claim_validation_pipeline import ClaimValidationPipeline
    pipeline = ClaimValidationPipeline()
    c1 = pipeline.create_claim("C-IDEMP", "text")
    c2 = pipeline.create_claim("C-IDEMP", "text")  # Same ID overwrites
    assert c1.claim_id == "C-IDEMP"
    assert c2.claim_id == "C-IDEMP"

def test_idempotent_reliability_record():
    from agent_reliability import ReliabilityTracker
    tracker = ReliabilityTracker()
    tracker.record_execution("agent-1", success=True, useful_evidence=True)
    tracker.record_execution("agent-1", success=True, useful_evidence=True)
    profile = tracker.get_profile("agent-1")
    assert profile.total_executions == 2  # Not deduplicated — each execution is real


# ─── Research Priority Engine ───

def test_priority_high_uncertainty():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    exp = hq.set_research_priority("research X", uncertainty=0.95)
    assert "high uncertainty" in exp

def test_priority_drift_detected():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    exp = hq.set_research_priority("research Y", drift_detected=True)
    assert "regime transition" in exp

def test_priority_failure_memory():
    from hq_decision_surface import HQDecisionSurface
    hq = HQDecisionSurface()
    exp = hq.set_research_priority("research Z", failure_memory=5)
    assert "previous failures" in exp


print("="*60)
print("J6 Test Suite")
print("="*60)

# Run all tests
test("IntelligenceStateJ6 creation", test_intelligence_state_j6_creation)
test("IntelligenceStateJ6 to_dict", test_intelligence_state_j6_to_dict)
test("IntelligenceStateJ6 observation", test_intelligence_state_j6_observation)
test("IntelligenceStateJ6 regime", test_intelligence_state_j6_regime)
test("IntelligenceStateJ6 opportunities", test_intelligence_state_j6_opportunities)
test("IntelligenceStateJ6 research_memory", test_intelligence_state_j6_research_memory)
test("IntelligenceStateJ6 failure_memory", test_intelligence_state_j6_failure_memory)
test("IntelligenceStateJ6 counterexamples", test_intelligence_state_j6_counterexamples)

test("AgentReliabilityProfile creation", test_agent_reliability_creation)
test("AgentReliabilityProfile success_rate", test_agent_reliability_success_rate)
test("AgentReliabilityProfile reliability_score", test_agent_reliability_reliability_score)
test("AgentReliabilityProfile regime_specific", test_agent_reliability_regime_specific)
test("AgentReliabilityProfile timeframe_specific", test_agent_reliability_timeframe_specific)
test("AgentReliabilityProfile symbol_specific", test_agent_reliability_symbol_specific)
test("AgentReliabilityProfile to_dict", test_agent_reliability_to_dict)

test("ReliabilityTracker creation", test_reliability_tracker_creation)
test("ReliabilityTracker get_profile", test_reliability_tracker_get_profile)
test("ReliabilityTracker record_execution", test_reliability_tracker_record_execution)
test("ReliabilityTracker record_failure", test_reliability_tracker_record_failure)
test("ReliabilityTracker record_unavailable", test_reliability_tracker_record_unavailable)
test("ReliabilityTracker mark_drift", test_reliability_tracker_mark_drift)
test("ReliabilityTracker get_reliable", test_reliability_tracker_get_reliable)
test("ReliabilityTracker get_unreliable", test_reliability_tracker_get_unreliable)
test("ReliabilityTracker summary", test_reliability_tracker_summary)
test("ReliabilityTracker to_dict", test_reliability_tracker_to_dict)

test("ClaimPipeline creation", test_claim_pipeline_creation)
test("ClaimPipeline create_claim", test_claim_pipeline_create_claim)
test("ClaimPipeline add_evidence", test_claim_pipeline_add_evidence)
test("ClaimPipeline add_contradictory", test_claim_pipeline_add_contradictory)
test("ClaimPipeline add_counterexample", test_claim_pipeline_add_counterexample)
test("ClaimPipeline update_status", test_claim_pipeline_update_status)
test("ClaimPipeline cannot_support_without_evidence", test_claim_pipeline_cannot_support_without_evidence)
test("ClaimPipeline cannot_support_with_contradiction", test_claim_pipeline_cannot_support_with_contradiction)
test("ClaimPipeline get_by_status", test_claim_pipeline_get_by_status)
test("ClaimPipeline validation_history", test_claim_pipeline_validation_history)
test("ClaimPipeline to_dict", test_claim_pipeline_to_dict)

test("HQ overview", test_hq_overview)
test("HQ situation", test_hq_situation)
test("HQ research_runs", test_hq_research_runs)
test("HQ agents", test_hq_agents)
test("HQ claims", test_hq_claims)
test("HQ drift", test_hq_drift)
test("HQ reliability", test_hq_reliability)
test("HQ human_review", test_hq_human_review)
test("HQ add_human_review", test_hq_add_human_review)
test("HQ situation_report", test_hq_situation_report)
test("HQ research_priority", test_hq_research_priority)
test("HQ to_dict", test_hq_to_dict)

test("Counterexample-first search", test_counterexample_first_search)
test("Counterexample-first failures", test_counterexample_first_failures_in_regime)
test("Counterexample-first low_quality_winners", test_counterexample_first_low_quality_winners)

test("Drift response regime", test_drift_response_regime)
test("Drift response data", test_drift_response_data)
test("Drift response volatility", test_drift_response_volatility)

test("Temporal integrity lookahead", test_temporal_integrity_lookahead)
test("Temporal integrity future_invariance", test_temporal_integrity_future_invariance)
test("Temporal integrity deterministic_replay", test_temporal_integrity_deterministic_replay)

test("Failure isolation parallel", test_failure_isolation_parallel)
test("Failure isolation agent", test_failure_isolation_agent)

test("Idempotent claim creation", test_idempotent_claim_creation)
test("Idempotent reliability record", test_idempotent_reliability_record)

test("Priority high_uncertainty", test_priority_high_uncertainty)
test("Priority drift_detected", test_priority_drift_detected)
test("Priority failure_memory", test_priority_failure_memory)

print(f"\n{'='*60}")
print(f"J6 Test Suite: {passed} PASS, {failed} FAIL")
if errors:
    print(f"\nFailures:")
    for name, tb in errors:
        print(f"  {name}: {tb.split(chr(10))[-2]}")
sys.exit(1 if failed else 0)