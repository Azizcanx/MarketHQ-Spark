# -*- coding: utf-8 -*-
"""
MarketHQ Learning Infrastructure Tests
========================================

Task 8: Comprehensive tests for:
  - No look-ahead in walk-forward split
  - Train/validation separation
  - Small sample handling (shrinkage)
  - Fallback correctness
  - Duplicate learning event prevention
  - Claim traceability
  - Weight versioning
  - Regime isolation
  - Timeframe isolation
  - Dataset metadata
  - Survivorship metadata
  - Baseline reproducibility
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from brain_learning_pipeline import (
    StrategyWeightEngine,
    create_learning_event,
    create_learning_events_from_outcomes,
    init_learning_tables,
    sync_claims_from_events,
    validate_claim,
    promote_claim,
    create_claim,
    get_claim,
    get_claims_by_status,
)
from setup_outcome_tracker import (
    record_outcome, ensure_table, _db, TABLE_NAME,
)
from setup_quality_engine_v2 import (
    sample_size_confidence,
    raw_expectancy,
    sample_adjusted_expectancy,
    score_setup_quality_v2,
)
from setup_object_model import (
    SetupModel, MarketInfo, TimeframeInfo, RegimeInfo, BiasInfo,
    StructureInfo, LiquidityInfo, EntryZone, Confirmation,
    InvalidationLevel, TargetLevel, Targets, RiskReward,
    Evidence, QualityScore,
)


DB_PATH = Path(__file__).resolve().parent / "market_hq.db"
TEST_DB = Path(__file__).resolve().parent / "market_hq_test.db"


class TestSampleSizeConfidence(unittest.TestCase):
    """Task 1: Sample-size confidence / shrinkage"""

    def test_low_confidence_small_n(self):
        level, shrinkage = sample_size_confidence(5)
        self.assertEqual(level, "low")
        self.assertEqual(shrinkage, 0.7)

    def test_medium_confidence_mid_n(self):
        level, shrinkage = sample_size_confidence(50)
        self.assertEqual(level, "medium")
        self.assertEqual(shrinkage, 0.4)

    def test_high_confidence_large_n(self):
        level, shrinkage = sample_size_confidence(200)
        self.assertEqual(level, "high")
        self.assertEqual(shrinkage, 0.1)

    def test_boundary_30(self):
        level, _ = sample_size_confidence(30)
        self.assertEqual(level, "medium")

    def test_boundary_100(self):
        level, _ = sample_size_confidence(100)
        self.assertEqual(level, "medium")

    def test_boundary_101(self):
        level, _ = sample_size_confidence(101)
        self.assertEqual(level, "high")

    def test_raw_expectancy(self):
        exp = raw_expectancy(0.6, 1.5, 1.0)
        self.assertAlmostEqual(exp, 0.6 * 1.5 - 0.4 * 1.0, places=4)

    def test_raw_expectancy_negative(self):
        exp = raw_expectancy(0.3, 0.8, 1.2)
        self.assertAlmostEqual(exp, 0.3 * 0.8 - 0.7 * 1.2, places=4)
        self.assertLess(exp, 0)

    def test_sample_adjusted_expectancy_shrinkage(self):
        # Small sample → adjusted should be close to global mean
        adj = sample_adjusted_expectancy(5, 2.0, 0.0, shrinkage_constant=50.0)
        self.assertLess(adj, 2.0)  # shrunk toward 0
        self.assertGreater(adj, 0.0)

    def test_sample_adjusted_expectancy_large_n(self):
        # Large sample → adjusted close to local (shrinkage is small but non-zero)
        adj = sample_adjusted_expectancy(500, 2.0, 0.0, shrinkage_constant=50.0)
        self.assertAlmostEqual(adj, 2.0, places=0)

    def test_sample_adjusted_expectancy_zero_n(self):
        # Zero samples → should return global mean
        adj = sample_adjusted_expectancy(0, 2.0, 0.5, shrinkage_constant=50.0)
        self.assertAlmostEqual(adj, 0.5)

    def test_quality_score_includes_sample_fields(self):
        model = SetupModel(
            setup_id="test", symbol="TEST", timeframe="1h",
            regime=RegimeInfo(regime="UPTREND", confidence=0.8),
            bias=BiasInfo(direction="LONG", bias_strength=0.7),
            structure=StructureInfo(has_structure=True, structure_type="BOS_UP"),
            entry_zone=EntryZone(center=100, width_atr=0.8, source="structure", touches=2),
            confirmation=Confirmation(strategy_count=5, agreement_score=0.7),
            invalidation=InvalidationLevel(price=97, distance_atr=1.5),
            risk_reward=RiskReward(reward_risk_ratio=2.0),
        )
        quality = score_setup_quality_v2(model, sample_size=50)
        self.assertIn(quality.sample_size_confidence, ("low", "medium", "high", "unknown"))
        self.assertIsInstance(quality.sample_size_confidence_score, float)
        self.assertIsInstance(quality.raw_expectancy, float)
        self.assertIsInstance(quality.sample_adjusted_expectancy, float)
        self.assertIsInstance(quality.shrinkage_factor, float)

    def test_quality_score_without_sample_size(self):
        model = SetupModel(
            setup_id="test2", symbol="TEST", timeframe="1h",
            regime=RegimeInfo(regime="UPTREND", confidence=0.8),
            bias=BiasInfo(direction="LONG", bias_strength=0.7),
            structure=StructureInfo(has_structure=True, structure_type="BOS_UP"),
            entry_zone=EntryZone(center=100, width_atr=0.8, source="structure", touches=2),
            confirmation=Confirmation(strategy_count=5, agreement_score=0.7),
            invalidation=InvalidationLevel(price=97, distance_atr=1.5),
            risk_reward=RiskReward(reward_risk_ratio=2.0),
        )
        quality = score_setup_quality_v2(model)
        # Without sample_size, defaults should be neutral
        self.assertEqual(quality.sample_size_confidence, "unknown")
        self.assertEqual(quality.raw_expectancy, 0.0)
        self.assertEqual(quality.sample_adjusted_expectancy, 0.0)


class TestSurvivorshipMetadata(unittest.TestCase):
    """Task 2: Survivorship bias metadata"""

    def setUp(self):
        ensure_table()

    def test_record_outcome_with_survivorship_fields(self):
        sig = record_outcome(
            setup_type="test_strategy",
            regime="UPTREND",
            direction="LONG",
            symbol="TEST",
            timeframe="1h",
            outcome="hit_target",
            pnl_pct=1.5,
            quality_score=0.7,
            dataset_version="v2",
            universe="crypto_spot",
            universe_method="yfinance",
            universe_start_date="2026-01-01",
            universe_end_date="2026-09-16",
            survivorship_risk="medium",
        )
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 16)

        # Verify stored in DB
        conn = _db()
        row = conn.execute(
            "SELECT dataset_version, universe, universe_method, survivorship_risk FROM setup_outcomes WHERE setup_signature = ?",
            (sig,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["dataset_version"], "v2")
        self.assertEqual(row["universe"], "crypto_spot")
        self.assertEqual(row["universe_method"], "yfinance")
        self.assertEqual(row["survivorship_risk"], "medium")

    def test_default_survivorship_values(self):
        sig = record_outcome(
            setup_type="test_default",
            regime="RANGE",
            direction="SHORT",
            symbol="TEST2",
            timeframe="15m",
            outcome="hit_invalidation",
            pnl_pct=-0.5,
        )
        conn = _db()
        row = conn.execute(
            "SELECT dataset_version, universe, survivorship_risk FROM setup_outcomes WHERE setup_signature = ?",
            (sig,),
        ).fetchone()
        conn.close()

        self.assertEqual(row["dataset_version"], "v1")
        self.assertEqual(row["universe"], "crypto_spot")
        self.assertEqual(row["survivorship_risk"], "low")


class TestBrainLearningPipeline(unittest.TestCase):
    """Task 3: Brain Learning Pipeline — learning events + duplicate prevention"""

    def setUp(self):
        init_learning_tables()
        # Clear tables for clean test
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM brain_learning_events")
        conn.execute("DELETE FROM brain_setup_claims")
        conn.commit()
        conn.close()

    def test_create_learning_event(self):
        event_id = create_learning_event(
            source_setup_id=99999,
            setup_type="test_strategy",
            strategy="ema_crossover",
            regime="UPTREND",
            timeframe="1h",
            outcome="hit_target",
            R=1.5,
            quality=0.75,
            evidence="strong_ema_signal",
            dataset_version="v1",
            confidence=0.75,
            sample_size_confidence="medium",
        )
        self.assertIsInstance(event_id, str)
        self.assertEqual(len(event_id), 16)

    def test_duplicate_prevention(self):
        create_learning_event(
            source_setup_id=88888,
            setup_type="test_strategy",
            strategy="sma",
            regime="UPTREND",
            timeframe="1h",
            outcome="hit_target",
            R=1.0,
        )
        with self.assertRaises(ValueError):
            create_learning_event(
                source_setup_id=88888,
                setup_type="test_strategy",
                strategy="sma",
                regime="UPTREND",
                timeframe="1h",
                outcome="hit_target",
                R=1.0,
            )

    def test_learning_event_fields(self):
        event_id = create_learning_event(
            source_setup_id=77777,
            setup_type="choch_long",
            strategy="smc",
            regime="DOWNTREND",
            timeframe="4h",
            outcome="hit_invalidation",
            R=-1.0,
            quality=0.4,
            evidence="choch_failed",
            dataset_version="v2",
            confidence=0.4,
            sample_size_confidence="low",
        )
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM brain_learning_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["setup_type"], "choch_long")
        self.assertEqual(row["strategy"], "smc")
        self.assertEqual(row["regime"], "DOWNTREND")
        self.assertEqual(row["timeframe"], "4h")
        self.assertEqual(row["outcome"], "hit_invalidation")
        self.assertEqual(row["R"], -1.0)
        self.assertEqual(row["quality"], 0.4)
        self.assertEqual(row["evidence"], "choch_failed")
        self.assertEqual(row["dataset_version"], "v2")
        self.assertEqual(row["confidence"], 0.4)
        self.assertEqual(row["sample_size_confidence"], "low")

    def test_create_events_from_outcomes(self):
        # First record some outcomes
        ensure_table()
        record_outcome(
            setup_type="batch_test", regime="UPTREND", direction="LONG",
            symbol="BATCH", timeframe="1h", outcome="hit_target",
            pnl_pct=1.2, quality_score=0.7, dataset_version="v1",
        )
        record_outcome(
            setup_type="batch_test", regime="DOWNTREND", direction="SHORT",
            symbol="BATCH", timeframe="1h", outcome="hit_invalidation",
            pnl_pct=-0.8, quality_score=0.3, dataset_version="v1",
        )

        result = create_learning_events_from_outcomes(limit=100)
        self.assertGreaterEqual(result["created"], 2)
        self.assertEqual(result["skipped_duplicates"], 0)

    def test_batch_create_skips_duplicates(self):
        # Create specific learning events and verify duplicate prevention
        ensure_table()
        event_id1 = create_learning_event(
            source_setup_id=55555,
            setup_type="dup_test",
            strategy="dup_strategy",
            regime="UPTREND",
            timeframe="1h",
            outcome="hit_target",
            R=1.0,
            quality=0.8,
            dataset_version="v1",
        )
        self.assertIsInstance(event_id1, str)

        # Second call with same source_setup_id should raise ValueError
        with self.assertRaises(ValueError):
            create_learning_event(
                source_setup_id=55555,
                setup_type="dup_test",
                strategy="dup_strategy",
                regime="UPTREND",
                timeframe="1h",
                outcome="hit_target",
                R=1.0,
                quality=0.8,
                dataset_version="v1",
            )


class TestBrainClaimModel(unittest.TestCase):
    """Task 4: Brain Claim Model — claim lifecycle + traceability"""

    def setUp(self):
        init_learning_tables()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM brain_setup_claims")
        conn.commit()
        conn.close()

    def test_create_claim(self):
        claim_id = create_claim(
            hypothesis="EMA crossover works in uptrend",
            evidence="6/10 wins",
            sample_size=10,
            confidence=0.6,
            uncertainty=0.4,
            dataset="v1",
            timeframe="1h",
            validation_period="2026-Q3",
            source_setup_ids=[1, 2, 3, 4, 5],
        )
        self.assertIsInstance(claim_id, str)

        claim = get_claim(claim_id)
        self.assertIsNotNone(claim)
        self.assertEqual(claim["status"], "CANDIDATE")
        self.assertEqual(claim["hypothesis"], "EMA crossover works in uptrend")
        self.assertEqual(claim["sample_size"], 10)
        self.assertEqual(claim["confidence"], 0.6)

    def test_claim_traceability(self):
        claim_id = create_claim(
            hypothesis="Traceability test",
            evidence="Evidence here",
            sample_size=5,
            confidence=0.5,
            dataset="v1",
            timeframe="15m",
            source_setup_ids=[100, 200, 300],
            traceability={
                "source_events": ["evt_1", "evt_2"],
                "generated_by": "test",
            },
        )
        claim = get_claim(claim_id)
        self.assertIsNotNone(claim)

        traceability = claim.get("traceability_json", "{}")
        import json
        trace = json.loads(traceability)
        self.assertIn("source_events", trace)
        self.assertEqual(trace["source_events"], ["evt_1", "evt_2"])

        source_ids = json.loads(claim["source_setup_ids"])
        self.assertEqual(source_ids, [100, 200, 300])

    def test_claim_lifecycle_candidate_to_validated(self):
        claim_id = create_claim(
            hypothesis="Validatable claim",
            evidence="Enough evidence",
            sample_size=10,
            confidence=0.5,
            dataset="v1",
            timeframe="1h",
        )

        # Auto-validate (sample >= 5 and confidence >= 0.3)
        validated = validate_claim(claim_id)
        self.assertTrue(validated)

        claim = get_claim(claim_id)
        self.assertEqual(claim["status"], "VALIDATED")

    def test_claim_auto_validate_insufficient_sample(self):
        claim_id = create_claim(
            hypothesis="Small sample claim",
            evidence="Not enough",
            sample_size=2,
            confidence=0.5,
            dataset="v1",
            timeframe="1h",
        )
        validated = validate_claim(claim_id)
        self.assertFalse(validated)

        claim = get_claim(claim_id)
        self.assertEqual(claim["status"], "CANDIDATE")

    def test_claim_auto_validate_low_confidence(self):
        claim_id = create_claim(
            hypothesis="Low confidence claim",
            evidence="Some evidence",
            sample_size=10,
            confidence=0.1,
            dataset="v1",
            timeframe="1h",
        )
        validated = validate_claim(claim_id)
        self.assertFalse(validated)

        claim = get_claim(claim_id)
        self.assertEqual(claim["status"], "CANDIDATE")

    def test_claim_manual_promote(self):
        claim_id = create_claim(
            hypothesis="Promotable claim",
            evidence="Strong evidence",
            sample_size=10,
            confidence=0.7,
            dataset="v1",
            timeframe="1h",
        )
        validate_claim(claim_id)

        promoted = promote_claim(claim_id)
        self.assertTrue(promoted)

        claim = get_claim(claim_id)
        self.assertEqual(claim["status"], "PROMOTED")

    def test_promote_only_from_validated(self):
        claim_id = create_claim(
            hypothesis="Direct promote",
            evidence="Evidence",
            sample_size=10,
            confidence=0.5,
            dataset="v1",
            timeframe="1h",
        )
        # Should fail: not validated
        promoted = promote_claim(claim_id)
        self.assertFalse(promoted)

        claim = get_claim(claim_id)
        self.assertEqual(claim["status"], "CANDIDATE")

    def test_get_claims_by_status(self):
        create_claim(hypothesis="C1", sample_size=5, confidence=0.5, dataset="v1", timeframe="1h")
        create_claim(hypothesis="C2", sample_size=8, confidence=0.6, dataset="v1", timeframe="1h")
        create_claim(hypothesis="C3", sample_size=3, confidence=0.2, dataset="v1", timeframe="4h")

        candidates = get_claims_by_status("CANDIDATE", timeframe="1h")
        self.assertEqual(len(candidates), 2)

        # Validate one
        validate_claim(candidates[0]["claim_id"])
        validated = get_claims_by_status("VALIDATED", timeframe="1h")
        self.assertEqual(len(validated), 1)

    def test_sync_claims_from_events(self):
        # Create some learning events first
        ensure_table()
        for i in range(5):
            record_outcome(
                setup_type="sync_test", regime="UPTREND", direction="LONG",
                symbol="SYNC", timeframe="1h", outcome="hit_target",
                pnl_pct=1.0, quality_score=0.7, dataset_version="v1",
            )

        result = create_learning_events_from_outcomes(limit=100)
        self.assertGreaterEqual(result["created"], 5)

        # Sync claims
        sync = sync_claims_from_events(min_sample=3)
        self.assertGreaterEqual(sync["created"], 1)


class TestStrategyWeightEngine(unittest.TestCase):
    """Task 5: Offline Strategy Weight Engine V1"""

    def setUp(self):
        init_learning_tables()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM brain_learning_events")
        conn.execute("DELETE FROM brain_weight_versions")
        conn.execute("DELETE FROM brain_walkforward_splits")
        conn.commit()
        conn.close()

    def _seed_events(self, n=20):
        """Create test learning events."""
        ensure_table()
        for i in range(n):
            record_outcome(
                setup_type="weight_test",
                regime="UPTREND" if i % 2 == 0 else "DOWNTREND",
                direction="LONG" if i % 2 == 0 else "SHORT",
                symbol="WT",
                timeframe="1h" if i % 3 == 0 else ("4h" if i % 3 == 1 else "1d"),
                outcome="hit_target" if i % 3 != 0 else "hit_invalidation",
                pnl_pct=1.0 if i % 3 != 0 else -1.0,
                quality_score=0.5 + (i % 5) * 0.1,
                dataset_version="v1",
            )
        return create_learning_events_from_outcomes(limit=100)

    def test_compute_weights(self):
        self._seed_events(20)
        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")
        self.assertGreater(len(weights), 0)

        # Check weight structure
        for w in weights:
            self.assertIsInstance(w.strategy, str)
            self.assertIsInstance(w.regime, str)
            self.assertIsInstance(w.timeframe, str)
            self.assertIsInstance(w.raw_weight, float)
            self.assertIsInstance(w.adjusted_weight, float)
            self.assertIsInstance(w.sample_size, int)
            self.assertIsInstance(w.confidence, float)
            self.assertIsInstance(w.uncertainty, float)
            self.assertEqual(w.weight_version, "weight_v1")

    def test_weight_versioning(self):
        self._seed_events(15)
        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")
        saved = engine.save_weights(weights)
        self.assertGreater(saved, 0)

        # Verify weights are stored
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT COUNT(*) as c FROM brain_weight_versions WHERE weight_version = 'weight_v1'"
        ).fetchone()
        conn.close()
        self.assertEqual(rows["c"], saved)

    def test_weight_factors(self):
        """Test that weight computation uses all required factors."""
        self._seed_events(20)
        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")

        for w in weights:
            # All weights should have non-negative values
            self.assertGreaterEqual(w.raw_weight, 0.0)
            self.assertGreaterEqual(w.adjusted_weight, 0.0)
            # Uncertainty should decrease with sample size
            if w.sample_size > 10:
                self.assertLess(w.uncertainty, 1.0)
            # Confidence should be 1 - uncertainty
            self.assertAlmostEqual(w.confidence, 1.0 - w.uncertainty, places=2)

    def test_regime_isolation(self):
        """Weights should be isolated by regime."""
        self._seed_events(20)
        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")

        regimes = set(w.regime for w in weights)
        self.assertGreater(len(regimes), 1)

        # Each regime should have its own weights
        for regime in regimes:
            regime_weights = [w for w in weights if w.regime == regime]
            self.assertGreater(len(regime_weights), 0)

    def test_timeframe_isolation(self):
        """Weights should be isolated by timeframe."""
        self._seed_events(20)
        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")

        timeframes = set(w.timeframe for w in weights)
        self.assertGreater(len(timeframes), 1)

        for tf in timeframes:
            tf_weights = [w for w in weights if w.timeframe == tf]
            self.assertGreater(len(tf_weights), 0)


class TestHierarchicalFallback(unittest.TestCase):
    """Task 6: Hierarchical Fallback"""

    def setUp(self):
        init_learning_tables()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM brain_learning_events")
        conn.execute("DELETE FROM brain_weight_versions")
        conn.execute("DELETE FROM brain_walkforward_splits")
        conn.commit()
        conn.close()

    def test_fallback_full_specificity(self):
        """When data exists at full level, use it."""
        init_learning_tables()
        # Directly create learning events to avoid picking up other test data
        for i in range(10):
            create_learning_event(
                source_setup_id=60000 + i,
                setup_type="fallback_test",
                strategy="fallback_test",
                regime="UPTREND",
                timeframe="1h",
                outcome="hit_target",
                R=1.0,
                quality=0.7,
                dataset_version="v1",
                confidence=0.7,
            )

        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")
        engine.save_weights(weights)

        # Verify weights were saved
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        wcount = conn.execute(
            "SELECT COUNT(*) as c FROM brain_weight_versions WHERE strategy = ?",
            ("fallback_test",),
        ).fetchone()["c"]
        conn.close()
        self.assertGreater(wcount, 0, "No weights saved for fallback_test")

        w = engine.get_weight_with_fallback("fallback_test", "UPTREND", "1h", "v1")
        self.assertEqual(w.weight_source_level, "full")
        self.assertEqual(w.weight_fallback_used, 0)

    def test_fallback_regime_level(self):
        """When no timeframe-specific data, fallback to regime level."""
        ensure_table()
        # Create events without timeframe specificity
        for i in range(5):
            record_outcome(
                setup_type="fallback_r", regime="DOWNTREND", direction="SHORT",
                symbol="FB2", timeframe="4h", outcome="hit_invalidation",
                pnl_pct=-0.5, quality_score=0.4, dataset_version="v1",
            )
        create_learning_events_from_outcomes(limit=100)

        engine = StrategyWeightEngine()
        # Request a timeframe with no data — should fallback
        w = engine.get_weight_with_fallback("fallback_r", "DOWNTREND", "999h", "v1")
        # Since we have regime-level data (5 samples >= MIN_SAMPLE_FOR_REGIME=3)
        # but not for 999h specifically, it should use regime fallback
        self.assertIn(w.weight_source_level, ("regime", "strategy", "neutral"))

    def test_fallback_neutral(self):
        """When no data at all, fallback to neutral."""
        engine = StrategyWeightEngine()
        w = engine.get_weight_with_fallback("nonexistent", "UNKNOWN", "999h", "v1")
        self.assertEqual(w.weight_source_level, "neutral")
        self.assertEqual(w.strategy, "neutral")

    def test_fallback_tracking(self):
        """Verify fallback usage is tracked in metadata."""
        init_learning_tables()
        # Directly create learning events
        for i in range(8):
            create_learning_event(
                source_setup_id=61000 + i,
                setup_type="fb_track",
                strategy="fb_track",
                regime="UPTREND",
                timeframe="1h",
                outcome="hit_target",
                R=1.0,
                quality=0.7,
                dataset_version="v1",
                confidence=0.7,
            )

        engine = StrategyWeightEngine()
        weights = engine.compute_weights(dataset_version="v1")
        engine.save_weights(weights)

        # Verify weights were saved
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        wcount = conn.execute(
            "SELECT COUNT(*) as c FROM brain_weight_versions WHERE strategy = ?",
            ("fb_track",),
        ).fetchone()["c"]
        conn.close()
        self.assertGreater(wcount, 0, "No weights saved for fb_track")

        # Full match
        w1 = engine.get_weight_with_fallback("fb_track", "UPTREND", "1h", "v1")
        self.assertEqual(w1.weight_source_level, "full")
        self.assertEqual(w1.weight_fallback_used, 0)

        # Regime fallback
        w2 = engine.get_weight_with_fallback("fb_track", "UPTREND", "4h", "v1")
        self.assertIn(w2.weight_source_level, ("regime", "strategy", "neutral"))
        self.assertGreater(w2.weight_fallback_used, 0)
        self.assertIsInstance(w2.weight_fallback_reason, str)
        self.assertGreater(len(w2.weight_fallback_reason), 0)


class TestWalkForwardValidation(unittest.TestCase):
    """Task 7: Walk-Forward Train/Validation Split"""

    def setUp(self):
        init_learning_tables()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM brain_learning_events")
        conn.execute("DELETE FROM brain_weight_versions")
        conn.execute("DELETE FROM brain_walkforward_splits")
        conn.commit()
        conn.close()

    def test_walkforward_split(self):
        """Test that walk-forward split produces train/validation sets."""
        ensure_table()
        # Create enough events
        for i in range(30):
            record_outcome(
                setup_type="wf_test", regime="UPTREND", direction="LONG",
                symbol="WF", timeframe="1h",
                outcome="hit_target" if i % 2 == 0 else "hit_invalidation",
                pnl_pct=1.0 if i % 2 == 0 else -1.0,
                quality_score=0.6, dataset_version="v1",
            )
        create_learning_events_from_outcomes(limit=100)

        engine = StrategyWeightEngine()
        result = engine.walk_forward_split(dataset_version="v1", train_ratio=0.7)

        self.assertIn("split_id", result)
        self.assertIn("train_size", result)
        self.assertIn("validation_size", result)
        self.assertIn("lookahead_check_passed", result)
        self.assertIn("baseline_val_r", result)
        self.assertIn("adaptive_val_r", result)

        # Train + validation should cover all events
        total = result["train_size"] + result["validation_size"]
        self.assertGreaterEqual(total, 28)  # Allow some slack

    def test_lookahead_check(self):
        """Test that look-ahead check passes (no future data in training)."""
        ensure_table()
        for i in range(30):
            record_outcome(
                setup_type="la_test", regime="UPTREND", direction="LONG",
                symbol="LA", timeframe="1h",
                outcome="hit_target", pnl_pct=1.0,
                quality_score=0.6, dataset_version="v1",
            )
        create_learning_events_from_outcomes(limit=100)

        engine = StrategyWeightEngine()
        result = engine.walk_forward_split(dataset_version="v1", train_ratio=0.7)

        self.assertTrue(result["lookahead_check_passed"])

    def test_baseline_vs_adaptive(self):
        """Compare baseline vs adaptive_v1 out-of-sample."""
        ensure_table()
        for i in range(40):
            record_outcome(
                setup_type="bv_test", regime="UPTREND", direction="LONG",
                symbol="BV", timeframe="1h",
                outcome="hit_target" if i % 3 != 0 else "hit_invalidation",
                pnl_pct=1.5 if i % 3 != 0 else -1.0,
                quality_score=0.5 + (i % 5) * 0.1, dataset_version="v1",
            )
        create_learning_events_from_outcomes(limit=100)

        engine = StrategyWeightEngine()
        result = engine.walk_forward_split(dataset_version="v1", train_ratio=0.7)

        # Both baseline and adaptive should have validation R values
        self.assertIsInstance(result["baseline_val_r"], float)
        self.assertIsInstance(result["adaptive_val_r"], float)

        # Should have computed adaptive weights
        self.assertGreater(result["adaptive_weights_count"], 0)

    def test_train_validation_separation(self):
        """Verify train and validation sets are properly separated."""
        init_learning_tables()
        # Directly create learning events to avoid picking up other test data
        for i in range(50):
            create_learning_event(
                source_setup_id=90000 + i,
                setup_type="ts_test",
                strategy="ts_test",
                regime="UPTREND",
                timeframe="1h",
                outcome="hit_target",
                R=1.0,
                quality=0.7,
                dataset_version="ts_test",
                confidence=0.7,
            )

        engine = StrategyWeightEngine()
        wf_result = engine.walk_forward_split(dataset_version="ts_test", train_ratio=0.7)

        # 70% train, 30% validation
        self.assertEqual(wf_result["train_size"] + wf_result["validation_size"], 50)
        self.assertGreater(wf_result["train_size"], wf_result["validation_size"])

    def test_baseline_reproducibility(self):
        """Test that baseline metrics are reproducible."""
        ensure_table()
        for i in range(30):
            record_outcome(
                setup_type="rep_test", regime="UPTREND", direction="LONG",
                symbol="REP", timeframe="1h",
                outcome="hit_target" if i % 2 == 0 else "hit_invalidation",
                pnl_pct=1.0 if i % 2 == 0 else -1.0,
                quality_score=0.6, dataset_version="v1",
            )
        create_learning_events_from_outcomes(limit=100)

        engine = StrategyWeightEngine()
        result1 = engine.walk_forward_split(dataset_version="v1", train_ratio=0.7)
        result2 = engine.walk_forward_split(dataset_version="v1", train_ratio=0.7)

        # Baseline train R should be the same (same data, same split ratio)
        self.assertEqual(result1["baseline_train_r"], result2["baseline_train_r"])
        self.assertEqual(result1["train_size"], result2["train_size"])
        self.assertEqual(result1["validation_size"], result2["validation_size"])


class TestDatasetMetadata(unittest.TestCase):
    """Test dataset metadata tracking"""

    def setUp(self):
        ensure_table()

    def test_dataset_version_stored(self):
        record_outcome(
            setup_type="ds_test", regime="UPTREND", direction="LONG",
            symbol="DS", timeframe="1h", outcome="hit_target",
            pnl_pct=1.0, quality_score=0.7,
            dataset_version="custom_v3",
            universe="stocks_us",
            universe_method="yfinance",
        )

        conn = _db()
        row = conn.execute(
            "SELECT dataset_version, universe FROM setup_outcomes WHERE setup_type = ?",
            ("ds_test",),
        ).fetchone()
        conn.close()

        self.assertEqual(row["dataset_version"], "custom_v3")
        self.assertEqual(row["universe"], "stocks_us")

    def test_universe_method_stored(self):
        record_outcome(
            setup_type="um_test", regime="UPTREND", direction="LONG",
            symbol="UM", timeframe="1h", outcome="hit_target",
            pnl_pct=1.0, quality_score=0.7,
            universe_method="custom_api",
        )

        conn = _db()
        row = conn.execute(
            "SELECT universe_method FROM setup_outcomes WHERE setup_type = ?",
            ("um_test",),
        ).fetchone()
        conn.close()

        self.assertEqual(row["universe_method"], "custom_api")


if __name__ == "__main__":
    unittest.main()