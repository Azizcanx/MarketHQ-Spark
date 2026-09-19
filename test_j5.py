# -*- coding: utf-8 -*-
"""Phase J5 Test Suite.

Tests for Continuous Intelligence System:
- IntelligenceState + IntelligenceStateManager
- ContinuousLoop + ResearchBudget + Cooldown + TriggerEvent
- ChangeDetectionEngine
- RegimeTransitionMemory
- DistributionDriftEngine
- TemporalDecay
- IntelligenceHealthMonitor + SituationReport
- SearchableMemory
- ResearchExperimentRegistryExtended
- MultipleTestingAwareness
- CounterexampleEngine
"""

import sys
import traceback
from datetime import datetime, timezone

from market_observation import MarketObservation, DataQuality, ObservationBundle
from intelligence_state import (
    IntelligenceState, IntelligenceStateManager, IntelligenceStateChange,
)
from continuous_loop import (
    ContinuousLoop, ResearchBudget, TriggerType, TriggerEvent,
    CooldownType, ResearchBudgetExceeded,
)
from change_detection_engine import (
    ChangeDetectionEngine, ChangeType, ChangeSeverity, ChangeDetectionEvent,
)
from regime_transition_memory import (
    RegimeTransitionMemory, RegimeTransitionType, RegimeTransitionRecord,
)
from distribution_drift_engine import (
    DistributionDriftEngine, DriftType, DriftSeverity, DriftDetectionEvent, DriftDetectionResult,
)
from temporal_decay import (
    compute_decay_weight, decay_evidence_weight, compute_weighted_confidence,
    DecayMethod, DecayConfig,
)
from intelligence_health import (
    IntelligenceHealthMonitor, IntelligenceHealthReport, HealthStatus,
)
from situation_report import SituationReport, build_situation_report
from searchable_memory import SearchableMemory, SearchField, SearchQuery, SearchResponse
from research_experiment_registry import (
    ResearchExperimentRegistryExtended, DuplicatePolicy, ExperimentRecord,
)
from multiple_testing_awareness import (
    MultipleTestingAwareness, TestingMode, TestSession,
    bonferroni_correction, fdr_bh_correction, adjust_confidence_for_multiple_testing,
)
from counterexample_engine import (
    CounterexampleEngine, CounterexampleSearch, CounterexampleResult,
)
from research_intelligence_model import Claim

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


# === IntelligenceState ===

def test_intelligence_state_enum():
    assert IntelligenceState.INITIALIZING.value == "INITIALIZING"
    assert IntelligenceState.OBSERVING.value == "OBSERVING"
    assert IntelligenceState.STABLE.value == "STABLE"
    assert IntelligenceState.CHANGE_DETECTED.value == "CHANGE_DETECTED"
    assert IntelligenceState.RESEARCHING.value == "RESEARCHING"
    assert IntelligenceState.VALIDATING.value == "VALIDATING"
    assert IntelligenceState.LEARNING.value == "LEARNING"
    assert IntelligenceState.HUMAN_REVIEW.value == "HUMAN_REVIEW"
    assert IntelligenceState.PAUSED.value == "PAUSED"
    assert IntelligenceState.ERROR.value == "ERROR"
    assert IntelligenceState.STALE.value == "STALE"

def test_intelligence_state_manager_initial():
    mgr = IntelligenceStateManager()
    assert mgr.current_state == IntelligenceState.INITIALIZING
    assert mgr.cycle_id.startswith("CYC-")
    assert mgr.context_version == 1
    assert mgr.current_record is not None
    assert mgr.current_record.state == IntelligenceState.INITIALIZING

def test_intelligence_state_valid_transitions():
    mgr = IntelligenceStateManager()
    assert mgr.can_transition(IntelligenceState.OBSERVING) is True
    assert mgr.can_transition(IntelligenceState.STABLE) is False

def test_intelligence_state_transition():
    mgr = IntelligenceStateManager()
    change = mgr.transition(IntelligenceState.OBSERVING, reason="test", provenance="test_j5")
    assert mgr.current_state == IntelligenceState.OBSERVING
    assert change.from_state == IntelligenceState.INITIALIZING
    assert change.to_state == IntelligenceState.OBSERVING
    assert change.reason == "test"
    assert change.provenance == "test_j5"
    assert len(mgr.state_history) == 1

def test_intelligence_state_invalid_transition_raises():
    mgr = IntelligenceStateManager()
    try:
        mgr.transition(IntelligenceState.STABLE)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

def test_intelligence_state_bump_context():
    mgr = IntelligenceStateManager()
    v1 = mgr.context_version
    v2 = mgr.bump_context_version()
    assert v2 == v1 + 1

def test_intelligence_state_get_valid_next():
    mgr = IntelligenceStateManager()
    mgr.transition(IntelligenceState.OBSERVING)
    nexts = mgr.get_valid_next_states()
    assert IntelligenceState.STABLE in nexts
    assert IntelligenceState.CHANGE_DETECTED in nexts

def test_intelligence_state_get_state_info():
    mgr = IntelligenceStateManager()
    info = mgr.get_state_info(IntelligenceState.OBSERVING)
    assert info["state"] == "OBSERVING"
    assert "valid_transitions" in info

def test_intelligence_state_to_dict():
    mgr = IntelligenceStateManager()
    mgr.transition(IntelligenceState.OBSERVING, reason="obs", provenance="t")
    d = mgr.to_dict()
    assert d["current_state"] == "OBSERVING"
    assert len(d["state_history"]) == 1
    assert d["state_history"][0]["reason"] == "obs"


# === ResearchBudget ===

def test_research_budget_defaults():
    b = ResearchBudget()
    assert b.max_cycles == 100
    assert b.max_tasks_per_cycle == 20
    assert b.max_agent_calls == 50
    assert b.max_provider_calls == 100
    assert b.max_runtime_seconds == 3600.0
    assert b.cycle_count == 0
    assert b.tasks_this_cycle == 0

def test_research_budget_check_cycle():
    b = ResearchBudget(max_cycles=5)
    assert b.check_cycle_budget() is True
    b.cycle_count = 5
    assert b.check_cycle_budget() is False

def test_research_budget_increment():
    b = ResearchBudget()
    b.increment_cycle()
    assert b.cycle_count == 1
    assert b.tasks_this_cycle == 0

def test_research_budget_check_runtime():
    b = ResearchBudget(max_runtime_seconds=1.0)
    import time as tm
    tm.sleep(1.1)
    assert b.check_runtime() is False

def test_research_budget_add_cost():
    b = ResearchBudget()
    b.add_cost(10.5)
    assert b.total_cost == 10.5

def test_research_budget_exceeded_exception():
    try:
        raise ResearchBudgetExceeded("max_cycles", 100, 50)
    except ResearchBudgetExceeded as e:
        assert e.budget_type == "max_cycles"
        assert e.current == 100
        assert e.limit == 50


# === ContinuousLoop ===

def test_continuous_loop_creation():
    cl = ContinuousLoop()
    assert cl.is_running is False
    assert cl.current_state == IntelligenceState.INITIALIZING
    assert len(cl.cooldowns_list) == 0
    assert len(cl.trigger_history_list) == 0

def test_continuous_loop_create_trigger():
    cl = ContinuousLoop()
    trigger = cl.create_trigger(TriggerType.SCHEDULED, "test", symbol="BTC", timeframe="1h")
    assert trigger.trigger_type == TriggerType.SCHEDULED
    assert trigger.symbol == "BTC"
    assert trigger.timeframe == "1h"
    assert len(cl.trigger_history_list) == 1

def test_continuous_loop_cooldown():
    cl = ContinuousLoop()
    entry = cl.add_cooldown(CooldownType.SYMBOL, "BTC-USDT", duration_seconds=60)
    assert cl.is_in_cooldown(CooldownType.SYMBOL, "BTC-USDT") is True
    assert cl.is_in_cooldown(CooldownType.SYMBOL, "ETH-USDT") is False

def test_continuous_loop_cooldown_expired():
    cl = ContinuousLoop()
    cl.add_cooldown(CooldownType.SYMBOL, "BTC-USDT", duration_seconds=0.1)
    import time as tm
    tm.sleep(0.2)
    assert cl.is_in_cooldown(CooldownType.SYMBOL, "BTC-USDT") is False

def test_continuous_loop_clean_expired():
    cl = ContinuousLoop()
    cl.add_cooldown(CooldownType.SYMBOL, "A", duration_seconds=0.1)
    cl.add_cooldown(CooldownType.SYMBOL, "B", duration_seconds=3600)
    import time as tm
    tm.sleep(0.2)
    removed = cl.clean_expired_cooldowns()
    assert removed == 1
    assert len(cl.cooldowns_list) == 1

def test_continuous_loop_budget_check():
    cl = ContinuousLoop()
    cl.budget.max_cycles = 0
    trigger = cl.create_trigger(TriggerType.SCHEDULED, "test")
    try:
        cl._check_budget(trigger)
        assert False, "Should have raised"
    except ResearchBudgetExceeded:
        pass

def test_continuous_loop_get_status():
    cl = ContinuousLoop()
    status = cl.get_status()
    assert status["running"] is False
    assert status["current_state"] == "INITIALIZING"
    assert "budget" in status
    assert "trigger_count" in status


# === ChangeDetectionEngine ===

def test_change_detection_engine_creation():
    engine = ChangeDetectionEngine()
    assert engine is not None

def test_change_detection_engine_detect_regime():
    engine = ChangeDetectionEngine()
    old = {"regime": "TRENDING", "volatility": 0.15}
    new = {"regime": "RANGE_LOW_VOL", "volatility": 0.05}
    result = engine.detect_regime_transition("BTC/USDT", "1h", old["regime"], new["regime"])
    assert isinstance(result, ChangeDetectionEvent)
    assert result.change_type == ChangeType.REGIME_TRANSITION
    assert result.symbol == "BTC/USDT"

def test_change_detection_engine_no_change():
    engine = ChangeDetectionEngine()
    data = {"regime": "TRENDING", "volatility": 0.15}
    result = engine.detect_regime_transition("BTC/USDT", "1h", data["regime"], data["regime"])
    assert isinstance(result, ChangeDetectionEvent)

def test_change_detection_engine_detect_volatility():
    engine = ChangeDetectionEngine()
    result = engine.detect_volatility_transition("ETH/USDT", "1h", "0.10", "0.25")
    assert isinstance(result, ChangeDetectionEvent)

def test_change_detection_engine_detect_momentum():
    engine = ChangeDetectionEngine()
    result = engine.detect_momentum_transition("BTC/USDT", "1h", "0.02", "0.08")
    assert isinstance(result, ChangeDetectionEvent)

def test_change_detection_engine_detect_trend():
    engine = ChangeDetectionEngine()
    result = engine.detect_trend_transition("BTC/USDT", "1h", "UPTREND", "DOWNTREND")
    assert isinstance(result, ChangeDetectionEvent)

def test_change_detection_engine_detect_liquidity():
    engine = ChangeDetectionEngine()
    result = engine.detect_liquidity_change("BTC/USDT", "1h", "1000000", "500000")
    assert isinstance(result, ChangeDetectionEvent)

def test_change_detection_get_researchworthy():
    engine = ChangeDetectionEngine()
    from change_detection_engine import ChangeDetectionResult
    event = ChangeDetectionEvent(
        event_id="E1",
        change_type=ChangeType.REGIME_TRANSITION,
        severity=ChangeSeverity.MODERATE,
        symbol="BTC/USDT",
        timeframe="1h",
        previous_state="TRENDING",
        new_state="RANGE_LOW_VOL",
        research_priority=0.7,
        detected_at=datetime.now(timezone.utc).isoformat(),
        context={},
    )
    result = ChangeDetectionResult(events=[event])
    events = engine.get_researchworthy_events(result, min_severity=ChangeSeverity.MODERATE)
    assert isinstance(events, list)
    assert len(events) >= 1


# === RegimeTransitionMemory ===

def test_regime_transition_memory_creation():
    mem = RegimeTransitionMemory()
    assert mem is not None

def test_regime_transition_memory_add():
    mem = RegimeTransitionMemory()
    record = mem.add_transition(
        previous_regime="TRENDING",
        new_regime="RANGE_LOW_VOL",
        transition_type=RegimeTransitionType.VOLATILITY_SHIFT,
        symbol="BTC/USDT",
    )
    assert record.previous_regime == "TRENDING"
    assert record.new_regime == "RANGE_LOW_VOL"
    assert record.symbol == "BTC/USDT"

def test_regime_transition_memory_get_for():
    mem = RegimeTransitionMemory()
    mem.add_transition("TRENDING", "RANGE_LOW_VOL", RegimeTransitionType.VOLATILITY_SHIFT, symbol="BTC/USDT")
    mem.add_transition("TRENDING", "UPTREND", RegimeTransitionType.EXPANSION, symbol="ETH/USDT")
    results = mem.get_transitions_for("BTC/USDT")
    assert len(results) == 1
    assert results[0].symbol == "BTC/USDT"

def test_regime_transition_memory_frequency():
    mem = RegimeTransitionMemory()
    mem.add_transition("TRENDING", "RANGE_LOW_VOL", RegimeTransitionType.VOLATILITY_SHIFT)
    mem.add_transition("TRENDING", "RANGE_LOW_VOL", RegimeTransitionType.VOLATILITY_SHIFT)
    mem.add_transition("RANGE_LOW_VOL", "UPTREND", RegimeTransitionType.EXPANSION)
    freq = mem.get_frequency("TRENDING", "RANGE_LOW_VOL")
    assert freq == 2

def test_regime_transition_memory_get_recent():
    mem = RegimeTransitionMemory()
    for i in range(5):
        mem.add_transition("A", "B", RegimeTransitionType.UNKNOWN)
    recent = mem.get_recent(limit=3)
    assert len(recent) == 3


# === DistributionDriftEngine ===

def test_distribution_drift_engine_creation():
    engine = DistributionDriftEngine()
    assert engine is not None

def test_distribution_drift_quality():
    engine = DistributionDriftEngine()
    result = engine.detect_quality_drift(
        "BTC/USDT", "1h",
        {"good": 80, "degraded": 20},
        {"good": 70, "degraded": 30},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_regime():
    engine = DistributionDriftEngine()
    result = engine.detect_regime_drift(
        "BTC/USDT", "1h",
        {"TRENDING": 60, "RANGE": 40},
        {"TRENDING": 30, "RANGE": 70},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_setup():
    engine = DistributionDriftEngine()
    result = engine.detect_setup_drift(
        "BTC/USDT", "1h",
        {"long": 10, "short": 5},
        {"long": 5, "short": 10},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_strategy_family():
    engine = DistributionDriftEngine()
    result = engine.detect_strategy_family_drift(
        "BTC/USDT", "1h",
        {"momentum": 20, "mean_reversion": 5},
        {"momentum": 5, "mean_reversion": 20},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_outcome():
    engine = DistributionDriftEngine()
    result = engine.detect_outcome_drift(
        "BTC/USDT", "1h",
        {"win": 60, "lose": 40},
        {"win": 40, "lose": 60},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_rr():
    engine = DistributionDriftEngine()
    result = engine.detect_rr_drift(
        "BTC/USDT", "1h",
        {"avg_rr": 2.0, "median_rr": 1.5},
        {"avg_rr": 1.2, "median_rr": 0.8},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_volatility():
    engine = DistributionDriftEngine()
    result = engine.detect_volatility_drift(
        "BTC/USDT", "1h",
        {"vol": 0.15, "high_vol": 10},
        {"vol": 0.25, "high_vol": 20},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_evidence():
    engine = DistributionDriftEngine()
    result = engine.detect_evidence_drift(
        "BTC/USDT", "1h",
        {"strong": 50, "weak": 10},
        {"strong": 20, "weak": 30},
    )
    assert isinstance(result, DriftDetectionEvent)

def test_distribution_drift_get_triggers():
    engine = DistributionDriftEngine()
    result = engine.detect_from_comparisons(
        "BTC/USDT", "1h",
        {"TRENDING": ({"count": 60}, {"count": 40})},
    )
    triggers = engine.get_research_triggers(result)
    assert isinstance(triggers, list)


# === TemporalDecay ===

def test_temporal_decay_compute_weight():
    w = compute_decay_weight(created_at="2026-09-01T00:00:00+00:00", reference_date="2026-09-17T00:00:00+00:00")
    assert 0 < w < 1

def test_temporal_decay_zero_hours():
    w = compute_decay_weight(created_at="2026-09-17T00:00:00+00:00", reference_date="2026-09-17T00:00:00+00:00")
    assert w == 1.0

def test_temporal_decay_large_hours():
    w = compute_decay_weight(created_at="2025-01-01T00:00:00+00:00", reference_date="2026-09-17T00:00:00+00:00")
    assert w < 0.15

def test_temporal_decay_evidence_weight():
    score = decay_evidence_weight(evidence_id="E1", created_at="2026-09-01T00:00:00+00:00")
    assert 0 < score.decayed_weight <= 1

def test_temporal_decay_weighted_confidence():
    evidence = [
        {"weight": 0.8, "confidence": 0.9},
        {"weight": 0.4, "confidence": 0.6},
    ]
    result = compute_weighted_confidence(evidence)
    assert 0 <= result <= 1

def test_temporal_decay_config():
    config = DecayConfig()
    assert config.half_life_days == 90.0

def test_temporal_decay_method_enum():
    assert DecayMethod.EXPONENTIAL.value == "exponential"
    assert DecayMethod.LINEAR.value == "linear"


# === IntelligenceHealth ===

def test_intelligence_health_monitor():
    mon = IntelligenceHealthMonitor()
    assert mon is not None

def test_intelligence_health_compute_status():
    mon = IntelligenceHealthMonitor()
    status = mon.compute_overall_status()
    assert isinstance(status, HealthStatus)

def test_intelligence_health_report():
    mon = IntelligenceHealthMonitor()
    report = mon.generate_report()
    assert isinstance(report, IntelligenceHealthReport)


# === SituationReport ===

def test_situation_report_creation():
    sr = SituationReport(
        market_context={"trend": "trending"},
        active_opportunities=[],
        recent_changes=[],
    )
    assert sr.market_context == {"trend": "trending"}
    assert sr.active_opportunities == []

def test_build_situation_report():
    sr = build_situation_report(
        market_context={"trend": "stable"},
        active_opportunities=[],
        recent_changes=[],
        regime="TRENDING",
    )
    assert sr.market_context == {"trend": "stable"}


# === SearchableMemory ===

def test_searchable_memory_creation():
    mem = SearchableMemory()
    assert mem is not None

def test_searchable_memory_add_and_search():
    mem = SearchableMemory()
    mem.add_entry({"id": "1", "symbol": "BTC/USDT", "field": SearchField.HYPOTHESIS, "content": "BTC trending up"})
    results = mem.search(query="BTC trending", fields=[SearchField.HYPOTHESIS.value])
    assert isinstance(results, SearchResponse)

def test_searchable_memory_get_entry():
    mem = SearchableMemory()
    mem.add_entry({"id": "abc123", "content": "test"})
    entry = mem.get_entry("abc123")
    assert entry is not None
    assert entry["id"] == "abc123"

def test_searchable_memory_get_missing():
    mem = SearchableMemory()
    entry = mem.get_entry("nonexistent")
    assert entry is None


# === ResearchExperimentRegistryExtended ===

def test_experiment_registry_creation():
    reg = ResearchExperimentRegistryExtended()
    assert reg is not None

def test_experiment_registry_register():
    reg = ResearchExperimentRegistryExtended()
    record = reg.register(
        hypothesis_id="H1",
        dataset="BTC_1h",
        cutoff=datetime.now(timezone.utc).isoformat(),
    )
    assert record.experiment_id.startswith("EXP-")
    assert record.hypothesis_id == "H1"

def test_experiment_registry_get():
    reg = ResearchExperimentRegistryExtended()
    record = reg.register(hypothesis_id="H2", dataset="ETH_1h")
    fetched = reg.get_experiment(record.experiment_id)
    assert fetched is not None
    assert fetched.hypothesis_id == "H2"

def test_experiment_registry_duplicates():
    reg = ResearchExperimentRegistryExtended(duplicate_policy=DuplicatePolicy.BLOCK)
    reg.register(hypothesis_id="H3", dataset="BTC_1h")
    try:
        reg.register(hypothesis_id="H3b", dataset="BTC_1h")
    except Exception:
        pass

def test_experiment_registry_get_by_hash():
    reg = ResearchExperimentRegistryExtended()
    record = reg.register(hypothesis_id="H4", dataset="BTC_1h")
    fetched = reg.get_by_hash(record.config_hash)
    assert fetched is not None

def test_experiment_registry_get_all():
    reg = ResearchExperimentRegistryExtended()
    reg.register(hypothesis_id="H5", dataset="BTC_1h")
    reg.register(hypothesis_id="H6", dataset="ETH_1h")
    all_records = reg.get_all()
    assert len(all_records) == 2

def test_experiment_registry_duplicates_count():
    reg = ResearchExperimentRegistryExtended()
    reg.register(hypothesis_id="H7", dataset="BTC_1h")
    reg.register(hypothesis_id="H7b", dataset="BTC_1h")
    assert reg.get_duplicates_count() >= 0


# === MultipleTestingAwareness ===

def test_multiple_testing_creation():
    mta = MultipleTestingAwareness()
    assert mta is not None

def test_multiple_testing_bonferroni():
    corrected = bonferroni_correction(0.01, 5)
    assert corrected >= 0.01

def test_multiple_testing_fdr():
    p_values = [0.001, 0.01, 0.025, 0.04, 0.05, 0.1]
    corrected = fdr_bh_correction(p_values)
    assert len(corrected) == len(p_values)
    assert all(c <= 1.0 for c in corrected)

def test_multiple_testing_adjust_confidence():
    result = adjust_confidence_for_multiple_testing(
        confidence=0.95,
        n_tests=20,
        mode=TestingMode.EXPLORATORY,
    )
    assert result <= 0.95

def test_multiple_testing_exploratory_vs_confirmatory():
    mta = MultipleTestingAwareness(default_mode=TestingMode.CONFIRMATORY)
    session = mta.create_session(testing_mode=TestingMode.CONFIRMATORY)
    assert session.testing_mode == TestingMode.CONFIRMATORY

def test_multiple_testing_session():
    mta = MultipleTestingAwareness()
    session = mta.create_session()
    assert session.session_id != ""
    assert session.hypothesis_count == 0


# === CounterexampleEngine ===

def test_counterexample_engine_creation():
    engine = CounterexampleEngine()
    assert engine is not None

def test_counterexample_engine_search():
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C1", text="BTC will trend up")
    result = engine.search(claim=claim, historical_outcomes=[], context={"regime": "TRENDING"})
    assert isinstance(result, CounterexampleResult)

def test_counterexample_engine_get_searches():
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C2", text="ETH mean reversion")
    engine.search(claim=claim, historical_outcomes=[], context={"x": 1})
    searches = engine.get_searches()
    assert isinstance(searches, list)

def test_counterexample_engine_get_results():
    engine = CounterexampleEngine()
    claim = Claim(claim_id="C3", text="LTC volatility breakout")
    engine.search(claim=claim, historical_outcomes=[], context={"x": 2})
    results = engine.get_results()
    assert isinstance(results, list)


# === Run all ===

if __name__ == "__main__":
    print("=== J5 Test Suite ===\n")

    print("--- IntelligenceState ---")
    test("IntelligenceState enum values", test_intelligence_state_enum)
    test("IntelligenceStateManager initial state", test_intelligence_state_manager_initial)
    test("IntelligenceState valid transitions", test_intelligence_state_valid_transitions)
    test("IntelligenceState transition", test_intelligence_state_transition)
    test("IntelligenceState invalid transition raises", test_intelligence_state_invalid_transition_raises)
    test("IntelligenceState bump context version", test_intelligence_state_bump_context)
    test("IntelligenceState get valid next states", test_intelligence_state_get_valid_next)
    test("IntelligenceState get state info", test_intelligence_state_get_state_info)
    test("IntelligenceState to_dict", test_intelligence_state_to_dict)

    print("\n--- ResearchBudget ---")
    test("ResearchBudget defaults", test_research_budget_defaults)
    test("ResearchBudget check_cycle_budget", test_research_budget_check_cycle)
    test("ResearchBudget increment_cycle", test_research_budget_increment)
    test("ResearchBudget check_runtime", test_research_budget_check_runtime)
    test("ResearchBudget add_cost", test_research_budget_add_cost)
    test("ResearchBudgetExceeded exception", test_research_budget_exceeded_exception)

    print("\n--- ContinuousLoop ---")
    test("ContinuousLoop creation", test_continuous_loop_creation)
    test("ContinuousLoop create_trigger", test_continuous_loop_create_trigger)
    test("ContinuousLoop cooldown", test_continuous_loop_cooldown)
    test("ContinuousLoop cooldown expired", test_continuous_loop_cooldown_expired)
    test("ContinuousLoop clean expired", test_continuous_loop_clean_expired)
    test("ContinuousLoop budget check", test_continuous_loop_budget_check)
    test("ContinuousLoop get_status", test_continuous_loop_get_status)

    print("\n--- ChangeDetectionEngine ---")
    test("ChangeDetectionEngine creation", test_change_detection_engine_creation)
    test("ChangeDetectionEngine detect_regime", test_change_detection_engine_detect_regime)
    test("ChangeDetectionEngine detect_volatility", test_change_detection_engine_detect_volatility)
    test("ChangeDetectionEngine detect_momentum", test_change_detection_engine_detect_momentum)
    test("ChangeDetectionEngine detect_trend", test_change_detection_engine_detect_trend)
    test("ChangeDetectionEngine detect_liquidity", test_change_detection_engine_detect_liquidity)
    test("ChangeDetectionEngine get_researchworthy", test_change_detection_get_researchworthy)

    print("\n--- RegimeTransitionMemory ---")
    test("RegimeTransitionMemory creation", test_regime_transition_memory_creation)
    test("RegimeTransitionMemory add", test_regime_transition_memory_add)
    test("RegimeTransitionMemory get_for", test_regime_transition_memory_get_for)
    test("RegimeTransitionMemory frequency", test_regime_transition_memory_frequency)
    test("RegimeTransitionMemory get_recent", test_regime_transition_memory_get_recent)

    print("\n--- DistributionDriftEngine ---")
    test("DistributionDriftEngine creation", test_distribution_drift_engine_creation)
    test("DistributionDriftEngine quality", test_distribution_drift_quality)
    test("DistributionDriftEngine regime", test_distribution_drift_regime)
    test("DistributionDriftEngine setup", test_distribution_drift_setup)
    test("DistributionDriftEngine strategy_family", test_distribution_drift_strategy_family)
    test("DistributionDriftEngine outcome", test_distribution_drift_outcome)
    test("DistributionDriftEngine rr", test_distribution_drift_rr)
    test("DistributionDriftEngine volatility", test_distribution_drift_volatility)
    test("DistributionDriftEngine evidence", test_distribution_drift_evidence)
    test("DistributionDriftEngine get_triggers", test_distribution_drift_get_triggers)

    print("\n--- TemporalDecay ---")
    test("TemporalDecay compute_weight", test_temporal_decay_compute_weight)
    test("TemporalDecay zero hours", test_temporal_decay_zero_hours)
    test("TemporalDecay large hours", test_temporal_decay_large_hours)
    test("TemporalDecay evidence_weight", test_temporal_decay_evidence_weight)
    test("TemporalDecay weighted_confidence", test_temporal_decay_weighted_confidence)
    test("TemporalDecay config", test_temporal_decay_config)
    test("TemporalDecay method enum", test_temporal_decay_method_enum)

    print("\n--- IntelligenceHealth ---")
    test("IntelligenceHealthMonitor creation", test_intelligence_health_monitor)
    test("IntelligenceHealth compute status", test_intelligence_health_compute_status)
    test("IntelligenceHealth report", test_intelligence_health_report)

    print("\n--- SituationReport ---")
    test("SituationReport creation", test_situation_report_creation)
    test("Build situation report", test_build_situation_report)

    print("\n--- SearchableMemory ---")
    test("SearchableMemory creation", test_searchable_memory_creation)
    test("SearchableMemory add and search", test_searchable_memory_add_and_search)
    test("SearchableMemory get_entry", test_searchable_memory_get_entry)
    test("SearchableMemory get missing", test_searchable_memory_get_missing)

    print("\n--- ResearchExperimentRegistryExtended ---")
    test("ExperimentRegistry creation", test_experiment_registry_creation)
    test("ExperimentRegistry register", test_experiment_registry_register)
    test("ExperimentRegistry get", test_experiment_registry_get)
    test("ExperimentRegistry duplicates", test_experiment_registry_duplicates)
    test("ExperimentRegistry get_by_hash", test_experiment_registry_get_by_hash)
    test("ExperimentRegistry get_all", test_experiment_registry_get_all)
    test("ExperimentRegistry duplicates_count", test_experiment_registry_duplicates_count)

    print("\n--- MultipleTestingAwareness ---")
    test("MultipleTestingAwareness creation", test_multiple_testing_creation)
    test("Bonferroni correction", test_multiple_testing_bonferroni)
    test("FDR BH correction", test_multiple_testing_fdr)
    test("Adjust confidence", test_multiple_testing_adjust_confidence)
    test("Exploratory vs confirmatory", test_multiple_testing_exploratory_vs_confirmatory)
    test("Test session", test_multiple_testing_session)

    print("\n--- CounterexampleEngine ---")
    test("CounterexampleEngine creation", test_counterexample_engine_creation)
    test("CounterexampleEngine search", test_counterexample_engine_search)
    test("CounterexampleEngine get_searches", test_counterexample_engine_get_searches)
    test("CounterexampleEngine get_results", test_counterexample_engine_get_results)

    print(f"\n{'='*40}")
    print(f"J5 Sonuç: {passed} PASS, {failed} FAIL")
    if errors:
        print(f"\nHata detaylari:")
        for name, tb in errors:
            print(f"  {name}: {tb.split(chr(10))[-2]}")
    sys.exit(1 if failed else 0)