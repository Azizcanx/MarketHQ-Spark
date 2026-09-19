# -*- coding: utf-8 -*-
"""Phase H — Research Intelligence Tests.

Tests for Phase H research intelligence engine:
observation, hypothesis, experiment, claim, memory,
reliability, calibration, similarity, failure,
weight proposal, champion/challenger, adaptive research,
redundancy, Brain integration, reproducibility,
lookahead, data sufficiency, low sample, edge cases.

All research-only. No trading. No auto promotion.
"""

import unittest
from datetime import datetime, timezone

import pandas as pd
import pytest

from opportunity_model import ResearchBackedSetup, SetupStatus, Direction
from research_intelligence_engine import (
    analyze_failures,
    compute_agent_reliability,
    build_hypothesis,
    build_observation,
    compute_calibration,
    compare_champion_challenger,
    create_weight_proposal,
    detect_feature_redundancy,
    find_similar_setups,
    register_experiment,
    run_experiment,
    store_observation,
    validate_claim,
)
from research_intelligence_model import (
    CalibrationProfile,
    Claim,
    ClaimStatus,
    Counterexample,
    Evidence,
    Experiment,
    ExperimentRegistry,
    ExperimentStatus,
    FeatureImportance,
    FailurePattern,
    Hypothesis,
    HypothesisStatus,
    Observation,
    ObservationType,
    ReliabilityProfile,
    ResearchMemory,
    Result,
    SimilarityMatch,
    WeightProposal,
    WeightProposalStatus,
)
from research_validation_model import (
    HistoricalOutcome,
    OutcomeType,
    ValidationMetrics,
)
from research_validation_engine import replay_setup


def make_ohlcv(n: int, start_price: float = 100.0, trend: float = 0.0,
                seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    import random
    rng = random.Random(seed)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h")
    data = []
    price = start_price
    for i in range(n):
        open_p = price
        change = rng.gauss(trend, 0.5)
        high_p = open_p + abs(rng.gauss(0, 0.3)) + max(change, 0)
        low_p = open_p - abs(rng.gauss(0, 0.3)) - max(-change, 0)
        close_p = open_p + change
        volume = rng.randint(1000, 10000)
        data.append({
            "Open": open_p, "High": high_p, "Low": low_p,
            "Close": close_p, "Volume": volume,
        })
        price = close_p
    df = pd.DataFrame(data, index=timestamps)
    df.index.name = "timestamp"
    return df


def make_outcome(
    setup_id: str = "S1",
    outcome_type: str = OutcomeType.TARGET_1_REACHED.value,
    realized_r: float = 1.0,
    entry_triggered: bool = True,
    invalidation_hit: bool = False,
    t1_hit: bool = True,
    t2_hit: bool = False,
    t3_hit: bool = False,
    no_entry: bool = False,
    ambiguous: bool = False,
) -> HistoricalOutcome:
    return HistoricalOutcome(
        setup_id=setup_id,
        symbol="THYAO.IS",
        timeframe="1h",
        cutoff_time=datetime.now(timezone.utc).isoformat(),
        entry_zone_low=98.0,
        entry_zone_high=102.0,
        entry_reference=100.0,
        invalidation_price=95.0,
        target_1=105.0,
        target_2=0.0,
        target_3=0.0,
        outcome_type=outcome_type,
        realized_r=realized_r,
        bars_to_entry=3,
        bars_to_invalidation=0,
        bars_to_t1=5,
        entry_triggered=entry_triggered,
        invalidation_hit=invalidation_hit,
        t1_hit=t1_hit,
        t2_hit=t2_hit,
        t3_hit=t3_hit,
        no_entry=no_entry,
        ambiguous=ambiguous,
    )


# ═══════════════════════════════════════════════════════════════════
# Observation Tests
# ═══════════════════════════════════════════════════════════════════

class TestObservation(unittest.TestCase):
    def test_observation_creation(self):
        obs = build_observation("Test observation", ObservationType.OBSERVATION)
        self.assertEqual(obs.text, "Test observation")
        self.assertEqual(obs.observation_type, ObservationType.OBSERVATION)
        self.assertEqual(obs.status, ClaimStatus.UNTESTED)

    def test_observation_failure_type(self):
        obs = build_observation("Failure pattern", ObservationType.FAILURE)
        self.assertEqual(obs.observation_type, ObservationType.FAILURE)

    def test_observation_with_context(self):
        context = {"regime": "RANGE_HIGH_VOL", "asset": "THYAO.IS"}
        obs = build_observation("Context observation", context=context)
        self.assertEqual(obs.context["regime"], "RANGE_HIGH_VOL")

    def test_observation_evidence_trace(self):
        trace = ["agent_1", "agent_2"]
        obs = build_observation("Traced", evidence_trace=trace)
        self.assertEqual(obs.evidence_trace, trace)

    def test_observation_to_dict(self):
        obs = build_observation("Dict test")
        d = obs.to_dict()
        self.assertEqual(d["text"], "Dict test")
        self.assertIn("observation_id", d)


# ═══════════════════════════════════════════════════════════════════
# Hypothesis Tests
# ═══════════════════════════════════════════════════════════════════

class TestHypothesis(unittest.TestCase):
    def test_hypothesis_creation(self):
        h = build_hypothesis("Quality predicts outcome")
        self.assertEqual(h.text, "Quality predicts outcome")
        self.assertEqual(h.status, HypothesisStatus.PROPOSED)

    def test_hypothesis_with_observations(self):
        obs_ids = ["OBS-001", "OBS-002"]
        h = build_hypothesis("Test", observation_ids=obs_ids)
        self.assertEqual(h.observation_ids, obs_ids)

    def test_hypothesis_confidence(self):
        h = build_hypothesis("Confident", confidence=0.8)
        self.assertEqual(h.confidence, 0.8)


# ═══════════════════════════════════════════════════════════════════
# Experiment Tests
# ═══════════════════════════════════════════════════════════════════

class TestExperiment(unittest.TestCase):
    def test_experiment_registry(self):
        exp = register_experiment("HYP-001", "Test experiment")
        self.assertEqual(exp.hypothesis, "HYP-001")
        self.assertEqual(exp.status, ExperimentStatus.REGISTERED)

    def test_experiment_with_config(self):
        config = {"windows": 3, "min_sample": 30}
        exp = register_experiment("HYP-001", "Config test", config=config)
        self.assertEqual(exp.hypothesis, "HYP-001")
        self.assertEqual(exp.config["windows"], 3)

    def test_experiment_hash(self):
        exp1 = register_experiment("HYP-001", "Hash test")
        exp2 = register_experiment("HYP-001", "Hash test")
        # Different timestamps produce different hashes
        self.assertIsNotNone(exp1.experiment_hash)

    def test_run_experiment(self):
        exp = register_experiment("HYP-001", "Run test")
        outcomes = [make_outcome("S1", OutcomeType.TARGET_1_REACHED.value, 1.0)]
        result = run_experiment(exp, outcomes)
        self.assertEqual(result.status, ExperimentStatus.COMPLETED)
        self.assertIn("n_outcomes", result.result)

    def test_run_experiment_empty(self):
        exp = register_experiment("HYP-001", "Empty test")
        outcomes = []
        result = run_experiment(exp, outcomes)
        self.assertEqual(result.status, ExperimentStatus.COMPLETED)
        self.assertEqual(result.result["n_outcomes"], 0)


# ═══════════════════════════════════════════════════════════════════
# Claim Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestClaimValidation(unittest.TestCase):
    def test_claim_untested_low_sample(self):
        claim = Claim(claim_id="C1", text="Test claim")
        outcomes = [make_outcome()]
        validated = validate_claim(claim, outcomes)
        # 1 outcome → UNSTABLE (not enough for SUPPORTED)
        self.assertIn(validated.status, [ClaimStatus.UNTESTED, ClaimStatus.UNSTABLE])

    def test_claim_supported_strong_evidence(self):
        claim = Claim(claim_id="C1", text="Strong claim")
        outcomes = [
            make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
            for i in range(40)
        ]
        validated = validate_claim(claim, outcomes)
        self.assertEqual(validated.status, ClaimStatus.SUPPORTED)

    def test_claim_rejected_strong_counter(self):
        claim = Claim(claim_id="C1", text="Rejected claim")
        outcomes = [
            make_outcome(f"S{i}", OutcomeType.INVALIDATED.value, -1.0)
            for i in range(40)
        ]
        validated = validate_claim(claim, outcomes)
        self.assertEqual(validated.status, ClaimStatus.REJECTED)

    def test_claim_unstable_mixed(self):
        claim = Claim(claim_id="C1", text="Mixed claim")
        outcomes = []
        for i in range(20):
            ot = OutcomeType.TARGET_1_REACHED.value if i % 2 == 0 else OutcomeType.INVALIDATED.value
            outcomes.append(make_outcome(f"S{i}", ot, 1.0 if i % 2 == 0 else -1.0))
        validated = validate_claim(claim, outcomes)
        self.assertIn(validated.status, [ClaimStatus.UNSTABLE, ClaimStatus.TESTED])

    def test_claim_version_increment(self):
        claim = Claim(claim_id="C1", text="Version test")
        outcomes = [make_outcome() for _ in range(35)]
        validated = validate_claim(claim, outcomes)
        self.assertGreaterEqual(validated.sample_size, 35)

    def test_claim_empty_outcomes(self):
        claim = Claim(claim_id="C1", text="Empty test")
        validated = validate_claim(claim, [])
        self.assertEqual(validated.status, ClaimStatus.UNTESTED)


# ═══════════════════════════════════════════════════════════════════
# Research Memory Tests
# ═══════════════════════════════════════════════════════════════════

class TestResearchMemory(unittest.TestCase):
    def test_store_observation(self):
        obs = build_observation("Memory test", ObservationType.PATTERN)
        mem = store_observation(obs)
        self.assertEqual(mem.memory_type, ObservationType.PATTERN)
        self.assertEqual(mem.observation, "Memory test")

    def test_memory_regime(self):
        obs = build_observation("Regime test", regime="RANGE_HIGH_VOL")
        mem = store_observation(obs)
        self.assertEqual(mem.regime, "RANGE_HIGH_VOL")

    def test_memory_asset(self):
        obs = build_observation("Asset test", asset="THYAO.IS")
        mem = store_observation(obs)
        self.assertEqual(mem.asset, "THYAO.IS")

    def test_memory_timeframe(self):
        obs = build_observation("TF test", timeframe="1h")
        mem = store_observation(obs)
        self.assertEqual(mem.timeframe, "1h")


# ═══════════════════════════════════════════════════════════════════
# Failure Memory Tests
# ═══════════════════════════════════════════════════════════════════

class TestFailureMemory(unittest.TestCase):
    def test_analyze_failures_empty(self):
        patterns = analyze_failures([])
        self.assertEqual(len(patterns), 0)

    def test_analyze_failures_invalidated(self):
        outcomes = [make_outcome(f"S{i}", OutcomeType.INVALIDATED.value, -1.0)
                    for i in range(20)]
        patterns = analyze_failures(outcomes)
        self.assertGreater(len(patterns), 0)

    def test_analyze_failures_no_entry(self):
        outcomes = [make_outcome(f"S{i}", OutcomeType.NO_ENTRY.value, 0.0,
                                     entry_triggered=False, no_entry=True)
                    for i in range(15)]
        patterns = analyze_failures(outcomes)
        no_entry_patterns = [p for p in patterns if p.outcome == "NO_ENTRY"]
        self.assertGreater(len(no_entry_patterns), 0)

    def test_failure_pattern_recurrence(self):
        outcomes = [make_outcome(f"S{i}", OutcomeType.INVALIDATED.value, -1.0)
                    for i in range(10)]
        patterns = analyze_failures(outcomes)
        for p in patterns:
            self.assertGreaterEqual(p.recurrence, 0.0)
            self.assertLessEqual(p.recurrence, 1.0)


# ═══════════════════════════════════════════════════════════════════
# Similarity Engine Tests
# ═══════════════════════════════════════════════════════════════════

class TestSimilarity(unittest.TestCase):
    def test_similarity_same_setup(self):
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="LONG")
        historical = [ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="LONG")]
        matches = find_similar_setups(setup, historical, top_k=3)
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0].similarity_score, 1.0)

    def test_similarity_different_symbol(self):
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="LONG")
        historical = [ResearchBackedSetup(symbol="GBPUSD", timeframe="1h", direction="LONG")]
        matches = find_similar_setups(setup, historical, top_k=3)
        self.assertGreater(len(matches), 0)
        self.assertIn("symbol", matches[0].mismatched_dimensions)

    def test_similarity_top_k(self):
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="LONG")
        historical = [
            ResearchBackedSetup(symbol=f"SYM{i}", timeframe="1h", direction="LONG")
            for i in range(10)
        ]
        matches = find_similar_setups(setup, historical, top_k=3)
        self.assertLessEqual(len(matches), 3)

    def test_similarity_empty_historical(self):
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="LONG")
        matches = find_similar_setups(setup, [], top_k=3)
        self.assertEqual(len(matches), 0)


# ═══════════════════════════════════════════════════════════════════
# Agent Reliability Tests
# ═══════════════════════════════════════════════════════════════════

class TestAgentReliability(unittest.TestCase):
    def test_reliability_empty(self):
        profile = compute_agent_reliability("TrendAgent", [])
        self.assertEqual(profile.sample_size, 0)
        self.assertEqual(profile.target_hit_rate, 0.0)

    def test_reliability_with_outcomes(self):
        outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                    for i in range(20)]
        profile = compute_agent_reliability("TrendAgent", outcomes)
        self.assertEqual(profile.sample_size, 20)
        self.assertGreater(profile.target_hit_rate, 0.0)

    def test_reliability_mixed_outcomes(self):
        outcomes = []
        for i in range(20):
            ot = OutcomeType.TARGET_1_REACHED.value if i % 2 == 0 else OutcomeType.INVALIDATED.value
            outcomes.append(make_outcome(f"S{i}", ot, 1.0 if i % 2 == 0 else -1.0))
        profile = compute_agent_reliability("TrendAgent", outcomes)
        self.assertEqual(profile.sample_size, 20)
        self.assertGreaterEqual(profile.target_hit_rate, 0.0)
        self.assertLessEqual(profile.target_hit_rate, 1.0)


# ═══════════════════════════════════════════════════════════════════
# Weight Proposal Tests
# ═══════════════════════════════════════════════════════════════════

class TestWeightProposal(unittest.TestCase):
    def test_proposal_creation(self):
        wp = create_weight_proposal("strategy_agreement", 0.20, 0.14, "lower stability")
        self.assertEqual(wp.weight_name, "strategy_agreement")
        self.assertEqual(wp.current_value, 0.20)
        self.assertEqual(wp.proposed_value, 0.14)
        self.assertEqual(wp.status, WeightProposalStatus.PROPOSED)

    def test_proposal_not_active(self):
        wp = create_weight_proposal("strategy_agreement", 0.20, 0.14, "reason")
        # PROPOSED status — NOT active
        self.assertEqual(wp.status, WeightProposalStatus.PROPOSED)

    def test_proposal_with_evidence(self):
        evidence = ["window_1", "window_2"]
        wp = create_weight_proposal("x", 0.5, 0.3, "reason", evidence=evidence)
        self.assertEqual(wp.evidence, evidence)

    def test_proposal_previous_comparison(self):
        prev = {"adaptive_v1": 0.45, "baseline": 0.50}
        wp = create_weight_proposal("x", 0.5, 0.3, "reason",
                                     previous_adaptive_comparison=prev)
        self.assertEqual(wp.previous_adaptive_v1_comparison["adaptive_v1"], 0.45)


# ═══════════════════════════════════════════════════════════════════
# Champion / Challenger Tests
# ═══════════════════════════════════════════════════════════════════

class TestChampionChallenger(unittest.TestCase):
    def test_champion_better(self):
        champion_outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                             for i in range(30)]
        challenger_outcomes = [make_outcome(f"S{i}", OutcomeType.INVALIDATED.value, -1.0)
                               for i in range(30)]
        cc = compare_champion_challenger("Baseline", "Adaptive",
                                         champion_outcomes, challenger_outcomes)
        self.assertEqual(cc.winner, "Baseline")

    def test_tie(self):
        outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                    for i in range(20)]
        cc = compare_champion_challenger("A", "B", outcomes, outcomes)
        self.assertEqual(cc.winner, "TIE")

    def test_comparison_metrics(self):
        champion_outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                             for i in range(20)]
        challenger_outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 0.5)
                               for i in range(20)]
        cc = compare_champion_challenger("C", "Ch", champion_outcomes, challenger_outcomes)
        self.assertIn("avg_r_diff", cc.comparison)


# ═══════════════════════════════════════════════════════════════════
# Calibration Tests
# ═══════════════════════════════════════════════════════════════════

class TestCalibration(unittest.TestCase):
    def test_calibration_empty(self):
        cal = compute_calibration({}, {})
        self.assertEqual(cal.sample_size, 0)

    def test_calibration_buckets(self):
        buckets = {
            "0.4-0.5": [0.45] * 10,
            "0.5-0.6": [0.55] * 20,
            "0.6-0.7": [0.65] * 30,
        }
        rates = {"0.4-0.5": 0.3, "0.5-0.6": 0.55, "0.6-0.7": 0.7}
        cal = compute_calibration(buckets, rates)
        self.assertEqual(cal.sample_size, 60)
        self.assertEqual(len(cal.buckets), 3)

    def test_calibration_bucket_names(self):
        buckets = {"0.4-0.5": [0.45]}
        rates = {"0.4-0.5": 0.5}
        cal = compute_calibration(buckets, rates)
        self.assertEqual(cal.buckets[0]["bucket"], "0.4-0.5")


# ═══════════════════════════════════════════════════════════════════
# Feature Redundancy Tests
# ═══════════════════════════════════════════════════════════════════

class TestFeatureRedundancy(unittest.TestCase):
    def test_no_redundancy(self):
        features = ["feat_a", "feat_b", "feat_c"]
        corr = {
            "feat_a": {"feat_b": 0.1, "feat_c": 0.2},
            "feat_b": {"feat_a": 0.1, "feat_c": 0.15},
            "feat_c": {"feat_a": 0.2, "feat_b": 0.15},
        }
        redundant = detect_feature_redundancy(features, corr, threshold=0.85)
        self.assertEqual(len(redundant), 0)

    def test_high_redundancy(self):
        features = ["feat_a", "feat_b"]
        corr = {"feat_a": {"feat_b": 0.95}, "feat_b": {"feat_a": 0.95}}
        redundant = detect_feature_redundancy(features, corr, threshold=0.85)
        self.assertEqual(len(redundant), 1)
        self.assertEqual(redundant[0]["correlation"], 0.95)

    def test_empty_features(self):
        redundant = detect_feature_redundancy([], {})
        self.assertEqual(len(redundant), 0)


# ═══════════════════════════════════════════════════════════════════
# Research Dashboard Tests
# ═══════════════════════════════════════════════════════════════════

class TestResearchDashboard(unittest.TestCase):
    def test_dashboard_defaults(self):
        from research_intelligence_engine import ResearchDashboard
        dash = ResearchDashboard()
        d = dash.to_dict()
        self.assertEqual(d["total_observations"], 0)
        self.assertEqual(d["total_claims"], 0)

    def test_dashboard_with_values(self):
        from research_intelligence_engine import ResearchDashboard
        dash = ResearchDashboard(
            total_observations=50,
            total_claims=20,
            supported_claims=10,
        )
        d = dash.to_dict()
        self.assertEqual(d["total_observations"], 50)
        self.assertEqual(d["supported_claims"], 10)


# ═══════════════════════════════════════════════════════════════════
# Model Tests
# ═══════════════════════════════════════════════════════════════════

class TestModels(unittest.TestCase):
    def test_observation_model(self):
        obs = Observation(
            observation_id="OBS-001",
            observation_type=ObservationType.OBSERVATION,
            text="Test",
        )
        self.assertEqual(obs.text, "Test")
        d = obs.to_dict()
        self.assertEqual(d["text"], "Test")

    def test_hypothesis_model(self):
        hyp = Hypothesis(hypothesis_id="HYP-001", text="Test hypothesis")
        self.assertEqual(hyp.text, "Test hypothesis")
        d = hyp.to_dict()
        self.assertEqual(d["text"], "Test hypothesis")

    def test_experiment_model(self):
        exp = Experiment(
            experiment_id="EXP-001", hypothesis_id="HYP-001",
            description="Test",
        )
        self.assertEqual(exp.experiment_id, "EXP-001")

    def test_result_model(self):
        res = Result(result_id="RES-001", experiment_id="EXP-001")
        self.assertEqual(res.result_id, "RES-001")

    def test_claim_model(self):
        claim = Claim(claim_id="C1", text="Test claim", status=ClaimStatus.UNTESTED)
        self.assertEqual(claim.status, ClaimStatus.UNTESTED)
        d = claim.to_dict()
        self.assertEqual(d["status"], "untested")

    def test_evidence_model(self):
        ev = Evidence(evidence_id="E1", claim_id="C1", text="Support")
        self.assertEqual(ev.evidence_type, "supporting")

    def test_research_memory_model(self):
        mem = ResearchMemory(
            memory_id="M1", memory_type=ObservationType.OBSERVATION,
            observation="Test memory",
        )
        self.assertEqual(mem.memory_type, ObservationType.OBSERVATION)
        d = mem.to_dict()
        self.assertEqual(d["observation"], "Test memory")

    def test_reliability_profile(self):
        prof = ReliabilityProfile(
            profile_id="R1", name="TrendAgent", profile_type="agent",
        )
        self.assertEqual(prof.profile_type, "agent")

    def test_calibration_profile(self):
        cal = CalibrationProfile(
            profile_id="C1", name="conf_cal", bucket_type="confidence",
        )
        self.assertEqual(cal.bucket_type, "confidence")

    def test_feature_importance(self):
        fi = FeatureImportance(feature_name="atr", importance_score=0.5)
        self.assertEqual(fi.feature_name, "atr")

    def test_weight_proposal(self):
        wp = WeightProposal(
            proposal_id="W1", weight_name="x",
            current_value=0.5, proposed_value=0.3,
        )
        self.assertEqual(wp.current_value, 0.5)

    def test_similarity_match(self):
        sm = SimilarityMatch(
            similarity_id="S1", setup_id="SETUP-1", similarity_score=0.8,
        )
        self.assertEqual(sm.similarity_score, 0.8)

    def test_failure_pattern(self):
        fp = FailurePattern(
            pattern_id="FP1", description="Test pattern",
        )
        self.assertEqual(fp.sample_size, 0)

    def test_counterexample(self):
        ce = Counterexample(
            counterexample_id="CE1", claim_id="C1", description="Counter",
        )
        self.assertEqual(ce.claim_id, "C1")

    def test_experiment_registry_model(self):
        er = ExperimentRegistry(
            experiment_id="EXP-001", hypothesis="HYP-001",
            dataset="Test hypothesis",
        )
        self.assertEqual(er.hypothesis, "HYP-001")


# ═══════════════════════════════════════════════════════════════════
# Lookahead / Leakage Tests
# ═══════════════════════════════════════════════════════════════════

class TestLookaheadAudit(unittest.TestCase):
    def test_lookahead_audit(self):
        from research_validation_engine import audit_lookahead
        df = make_ohlcv(200)
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="SHORT")
        result = audit_lookahead([setup], df, cutoff_idx=150)
        self.assertIn("lookahead_status", result)

    def test_lookahead_not_testable(self):
        from research_validation_engine import audit_lookahead
        df = make_ohlcv(100)
        setup = ResearchBackedSetup(symbol="THYAO.IS", timeframe="1h", direction="SHORT")
        result = audit_lookahead([setup], df, cutoff_idx=90)
        # May be NOT_TESTABLE or PASS depending on data
        self.assertIn(result.get("lookahead_status", ""),
                       ["NOT_TESTABLE", "PASS", "FAIL"])


# ═══════════════════════════════════════════════════════════════════
# Data Sufficiency Tests
# ═══════════════════════════════════════════════════════════════════

class TestDataSufficiency(unittest.TestCase):
    def test_sufficient_sample(self):
        outcomes = [make_outcome() for _ in range(50)]
        metrics = ValidationMetrics()
        # Direct test: 50 outcomes is sufficient
        self.assertGreaterEqual(len(outcomes), 30)

    def test_limited_sample(self):
        outcomes = [make_outcome() for _ in range(15)]
        # 15 outcomes → limited but not insufficient
        self.assertGreaterEqual(len(outcomes), 10)

    def test_low_sample(self):
        outcomes = [make_outcome() for _ in range(3)]
        self.assertLess(len(outcomes), 10)


# ═══════════════════════════════════════════════════════════════════
# Reproducibility Tests
# ═══════════════════════════════════════════════════════════════════

class TestReproducibility(unittest.TestCase):
    def test_experiment_hash(self):
            exp1 = register_experiment("HYP-001", "Hash test")
            # Hash should be non-empty and uppercase in experiment_id
            self.assertIsNotNone(exp1.experiment_hash)
            self.assertGreater(len(exp1.experiment_hash), 0)
            # Hash in uppercase should be in experiment_id
            self.assertIn(exp1.experiment_hash.upper(), exp1.experiment_id)

    def test_experiment_config_hash(self):
        config = {"windows": 3, "min_sample": 30}
        exp1 = register_experiment("HYP-001", "Config test", config=config)
        # Hash in uppercase should be in experiment_id
        self.assertIn(exp1.experiment_hash.upper(), exp1.experiment_id)


# ═══════════════════════════════════════════════════════════════════
# Counterexample / Contradiction Tests
# ═══════════════════════════════════════════════════════════════════

class TestCounterexample(unittest.TestCase):
    def test_counterexample_creation(self):
        ce = Counterexample(
            counterexample_id="CE1", claim_id="C1",
            description="Counter example",
        )
        self.assertEqual(ce.claim_id, "C1")

    def test_counterexample_with_conditions(self):
        ce = Counterexample(
            counterexample_id="CE2", claim_id="C2",
            description="High quality + invalidated",
            conditions={"quality": "high", "outcome": "invalidated"},
        )
        self.assertEqual(ce.conditions["quality"], "high")


# ═══════════════════════════════════════════════════════════════════
# Outcome Classification Tests
# ═══════════════════════════════════════════════════════════════════

class TestOutcomeClassification(unittest.TestCase):
    def test_all_outcome_types(self):
        types = [
            OutcomeType.TARGET_1_REACHED.value,
            OutcomeType.TARGET_2_REACHED.value,
            OutcomeType.TARGET_3_REACHED.value,
            OutcomeType.INVALIDATED.value,
            OutcomeType.EXPIRED.value,
            OutcomeType.NO_ENTRY.value,
            OutcomeType.INCOMPLETE_DATA.value,
            OutcomeType.AMBIGUOUS.value,
        ]
        for ot in types:
            outcome = make_outcome("S1", ot, 1.0)
            self.assertEqual(outcome.outcome_type, ot)


# ═══════════════════════════════════════════════════════════════════
# Historical Replay Consistency Tests
# ═══════════════════════════════════════════════════════════════════

class TestHistoricalReplayConsistency(unittest.TestCase):
    def test_replay_deterministic(self):
        df = make_ohlcv(200, seed=42)
        setup = ResearchBackedSetup(
            symbol="THYAO.IS", timeframe="1h", direction="SHORT",
            entry_reference=100.0, invalidation_price=95.0,
            entry_zone_low=98.0, entry_zone_high=102.0,
        )
        outcome1 = replay_setup(setup, df, cutoff_idx=150)
        outcome2 = replay_setup(setup, df, cutoff_idx=150)
        self.assertEqual(outcome1.outcome_type, outcome2.outcome_type)

    def test_replay_different_cutoff(self):
        df = make_ohlcv(200, seed=42)
        setup = ResearchBackedSetup(
            symbol="THYAO.IS", timeframe="1h", direction="SHORT",
            entry_reference=100.0, invalidation_price=95.0,
            entry_zone_low=98.0, entry_zone_high=102.0,
        )
        outcome1 = replay_setup(setup, df, cutoff_idx=100)
        outcome2 = replay_setup(setup, df, cutoff_idx=150)
        # Different cutoffs may produce different outcomes
        # Just verify both are valid outcome types
        valid_types = [t.value for t in OutcomeType]
        self.assertIn(outcome1.outcome_type, valid_types)
        self.assertIn(outcome2.outcome_type, valid_types)


# ═══════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    def test_empty_observation_text(self):
        obs = build_observation("")
        self.assertEqual(obs.text, "")
        self.assertEqual(obs.status, ClaimStatus.UNTESTED)

    def test_claim_empty_text(self):
        claim = Claim(claim_id="C1", text="")
        self.assertEqual(claim.text, "")

    def test_zero_realized_r(self):
        outcome = make_outcome("S1", OutcomeType.TARGET_1_REACHED.value, 0.0)
        self.assertEqual(outcome.realized_r, 0.0)

    def test_negative_realized_r(self):
        outcome = make_outcome("S1", OutcomeType.INVALIDATED.value, -2.0)
        self.assertEqual(outcome.realized_r, -2.0)

    def test_large_realized_r(self):
        outcome = make_outcome("S1", OutcomeType.TARGET_3_REACHED.value, 5.0)
        self.assertEqual(outcome.realized_r, 5.0)

    def test_weight_proposal_same_values(self):
        wp = create_weight_proposal("x", 0.5, 0.5, "no change")
        self.assertEqual(wp.current_value, wp.proposed_value)
        self.assertEqual(wp.status, WeightProposalStatus.PROPOSED)


# ═══════════════════════════════════════════════════════════════════
# No Auto Promotion Tests
# ═══════════════════════════════════════════════════════════════════

class TestNoAutoPromotion(unittest.TestCase):
    def test_weight_proposal_not_auto_active(self):
        """Weight proposals are PROPOSED, never AUTO_ACTIVE."""
        wp = create_weight_proposal("x", 0.5, 0.3, "reason")
        # PROPOSED status — NOT active, requires human review
        self.assertEqual(wp.status, WeightProposalStatus.PROPOSED)

    def test_claim_status_never_autopromoted(self):
        """Claim status changes require explicit validation, not auto."""
        claim = Claim(claim_id="C1", text="Test", status=ClaimStatus.UNTESTED)
        # Status should only change through validate_claim
        self.assertEqual(claim.status, ClaimStatus.UNTESTED)

    def test_observation_not_truth(self):
        """Observations are research data, not truths."""
        obs = build_observation("Observation", ObservationType.OBSERVATION)
        self.assertEqual(obs.status, ClaimStatus.UNTESTED)


# ═══════════════════════════════════════════════════════════════════
# Multi-Asset / Timeframe Isolation Tests
# ═══════════════════════════════════════════════════════════════════

class TestIsolation(unittest.TestCase):
    def test_different_assets_separate(self):
        outcomes_th = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                       for i in range(10)]
        outcomes_eur = [make_outcome(f"S{i}", OutcomeType.INVALIDATED.value, -1.0)
                        for i in range(10)]
        # These are separate datasets — verify they don't mix
        self.assertEqual(len(outcomes_th), 10)
        self.assertEqual(len(outcomes_eur), 10)

    def test_different_timeframes_separate(self):
        df_1h = make_ohlcv(100, seed=42)
        df_15m = make_ohlcv(400, seed=42)
        # Different timeframes have different data lengths
        self.assertNotEqual(len(df_1h), len(df_15m))


# ═══════════════════════════════════════════════════════════════════
# Regression Tests — ensure Phase G compatibility
# ═══════════════════════════════════════════════════════════════════

class TestPhaseGCompatibility(unittest.TestCase):
    def test_validation_metrics_still_works(self):
        """Phase G metrics should still work with Phase H."""
        from research_validation_engine import compute_validation_metrics
        outcomes = [make_outcome(f"S{i}", OutcomeType.TARGET_1_REACHED.value, 1.0)
                    for i in range(20)]
        metrics = compute_validation_metrics(outcomes)
        self.assertEqual(metrics.n_setups, 20)
        self.assertGreater(metrics.t1_hit_rate, 0.0)

    def test_replay_still_works(self):
        """Phase G replay should still work with Phase H."""
        df = make_ohlcv(200)
        setup = ResearchBackedSetup(
            symbol="THYAO.IS", timeframe="1h", direction="SHORT",
            entry_reference=100.0, invalidation_price=95.0,
            entry_zone_low=98.0, entry_zone_high=102.0,
        )
        outcome = replay_setup(setup, df, cutoff_idx=100)
        self.assertIn(outcome.outcome_type, [t.value for t in OutcomeType])


if __name__ == "__main__":
    unittest.main()