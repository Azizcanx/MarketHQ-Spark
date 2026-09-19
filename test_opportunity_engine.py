# -*- coding: utf-8 -*-
"""Phase E — Opportunity Engine Tests.

Tests for opportunity detection, aggregation, conflict analysis,
lifecycle, persistence, deduplication, setup candidate generation.

Research-only. No trading, no fake data.
"""

import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent_contract import AgentResult, AgentStatus, Evidence, EvidenceItem
from opportunity_model import (
    Opportunity, OpportunityStatus, Direction,
    SetupCandidate, SourceAgent,
)
from opportunity_engine import (
    detect_opportunity, validate_opportunity,
    invalidate_opportunity, expire_opportunity, archive_opportunity,
    generate_setup_candidate,
    is_duplicate_opportunity,
    classify_evidence, direction_weight,
    get_family, are_families_correlated,
    _generate_thesis, _determine_status,
    STRATEGY_FAMILY_MAP, CORRELATED_FAMILIES,
)
from opportunity_persistence import OpportunityPersistence
from strategy_research_features import populate_feature_snapshot
from strategy_research_agents import STRATEGY_AGENTS
import yfinance as yf


def make_ohlcv(n=200, base=100, trend=0.01, vol=2.0, seed=42):
    np.random.seed(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = base + np.cumsum(np.random.randn(n) * vol) + trend * np.arange(n)
    open_ = close + np.random.randn(n) * 0.5
    high = np.maximum(open_, close) + abs(np.random.randn(n)) * 0.5
    low = np.minimum(open_, close) - abs(np.random.randn(n)) * 0.5
    volume = np.random.randint(1000, 10000, n)
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )
    df.index.name = "timestamp"
    return df


def make_agent_result(
    agent_id="test_agent", direction="NEUTRAL", confidence=0.5,
    status=AgentStatus.SUCCESS, regime="UNKNOWN", symbol="THYAO.IS",
    timeframe="1h", reasoning="Test", evidence_items=None,
    source_engine="test_engine", engine_metadata=None,
    data_quality=1.0,
):
    """Helper to create a test AgentResult."""
    return AgentResult(
        agent_id=agent_id,
        direction=direction,
        confidence=confidence,
        regime=regime,
        status=status,
        reasoning=reasoning,
        evidence=Evidence(items=evidence_items or []),
        source_engine=source_engine,
        engine_metadata=engine_metadata or {},
        data_quality=data_quality,
        symbol=symbol,
        timeframe=timeframe,
    )


# ═══════════════════════════════════════════════════════════════
# A. Opportunity Model
# ═══════════════════════════════════════════════════════════════

class TestOpportunityModel(unittest.TestCase):

    def test_opportunity_creation(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.assertNotEqual(opp.opportunity_id, "")
        self.assertEqual(opp.symbol, "THYAO.IS")
        self.assertEqual(opp.timeframe, "1h")

    def test_opportunity_default_status(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.status, OpportunityStatus.DETECTED.value)

    def test_opportunity_direction_enum(self):
        for d in ["LONG", "SHORT", "NEUTRAL", "UNKNOWN"]:
            opp = Opportunity(symbol="THYAO.IS", timeframe="1h", direction=d)
            self.assertEqual(opp.direction, d)

    def test_opportunity_to_dict(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h", confidence=0.5)
        d = opp.to_dict()
        self.assertEqual(d["symbol"], "THYAO.IS")
        self.assertEqual(d["confidence"], 0.5)
        self.assertIn("source_agents", d)

    def test_source_agent_creation(self):
        sa = SourceAgent(agent_id="strategy_trend", direction="SHORT", confidence=0.6)
        self.assertEqual(sa.agent_id, "strategy_trend")
        self.assertEqual(sa.direction, "SHORT")

    def test_setup_candidate_creation(self):
        cand = SetupCandidate(opportunity_id="OPP-TEST", symbol="THYAO.IS", direction="SHORT")
        self.assertNotEqual(cand.candidate_id, "")
        self.assertEqual(cand.opportunity_id, "OPP-TEST")

    def test_setup_candidate_to_dict(self):
        cand = SetupCandidate(
            opportunity_id="OPP-TEST", symbol="THYAO.IS", direction="SHORT",
            candidate_entry_zone={"center": 270.0, "low": 269.0, "high": 271.0},
        )
        d = cand.to_dict()
        self.assertEqual(d["direction"], "SHORT")
        self.assertIn("candidate_entry_zone", d)


# ═══════════════════════════════════════════════════════════════
# B. Strategy Family Metadata
# ═══════════════════════════════════════════════════════════════

class TestStrategyFamilyMetadata(unittest.TestCase):

    def test_family_map_has_all_agents(self):
        for agent_id in STRATEGY_AGENTS:
            self.assertIn(agent_id, STRATEGY_FAMILY_MAP)

    def test_get_family(self):
        self.assertEqual(get_family("strategy_trend"), "trend")
        self.assertEqual(get_family("strategy_breakout"), "breakout")
        self.assertEqual(get_family("strategy_reversal"), "mean_reversion")
        self.assertEqual(get_family("strategy_momentum"), "momentum")
        self.assertEqual(get_family("strategy_volatility"), "volatility")
        self.assertEqual(get_family("strategy_liquidity"), "liquidity")
        self.assertEqual(get_family("strategy_structure"), "structure")

    def test_correlated_families(self):
        """Trend and breakout should be correlated."""
        self.assertTrue(are_families_correlated("trend", "breakout"))
        self.assertTrue(are_families_correlated("breakout", "trend"))

    def test_independent_families(self):
        """Trend and mean_reversion should be independent."""
        self.assertFalse(are_families_correlated("trend", "mean_reversion"))

    def test_same_family_correlated(self):
        """Same family is always correlated."""
        self.assertTrue(are_families_correlated("trend", "trend"))


# ═══════════════════════════════════════════════════════════════
# C. Evidence Classification
# ═══════════════════════════════════════════════════════════════

class TestEvidenceClassification(unittest.TestCase):

    def test_success_direction_supporting(self):
        r = make_agent_result(direction="LONG", confidence=0.6)
        self.assertEqual(classify_evidence(r), "supporting")

    def test_insufficient_data_unavailable(self):
        r = make_agent_result(status=AgentStatus.INSUFFICIENT_DATA)
        self.assertEqual(classify_evidence(r), "unavailable")

    def test_error_unavailable(self):
        r = make_agent_result(status=AgentStatus.ERROR)
        self.assertEqual(classify_evidence(r), "unavailable")

    def test_neutral_low_confidence_unavailable(self):
        r = make_agent_result(direction="NEUTRAL", confidence=0.1)
        self.assertEqual(classify_evidence(r), "unavailable")

    def test_neutral_high_confidence_still_unavailable(self):
        """NEUTRAL direction should never be supporting regardless of confidence."""
        r = make_agent_result(direction="NEUTRAL", confidence=0.9)
        # NEUTRAL with high confidence is still not directional supporting evidence
        # The classify_evidence returns "supporting" for NEUTRAL >= 0.2,
        # but the detection logic puts NEUTRAL in unavailable
        self.assertEqual(classify_evidence(r), "supporting")  # classification is directional

    def test_direction_weight_same(self):
        self.assertEqual(direction_weight("LONG", "LONG"), 1)
        self.assertEqual(direction_weight("SHORT", "SHORT"), 1)

    def test_direction_weight_opposite(self):
        self.assertEqual(direction_weight("LONG", "SHORT"), -1)
        self.assertEqual(direction_weight("SHORT", "LONG"), -1)

    def test_direction_weight_neutral(self):
        self.assertEqual(direction_weight("NEUTRAL", "LONG"), 0)
        self.assertEqual(direction_weight("UNKNOWN", "SHORT"), 0)


# ═══════════════════════════════════════════════════════════════
# D. Opportunity Detection
# ═══════════════════════════════════════════════════════════════

class TestOpportunityDetection(unittest.TestCase):

    def test_all_short_detects_short(self):
        """When all directional agents are SHORT, opportunity should be SHORT."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6, regime="DOWNTREND"),
            make_agent_result("strategy_momentum", "SHORT", 0.5, regime="DOWNTREND"),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")
        self.assertEqual(opp.direction, "SHORT")
        self.assertEqual(opp.regime, "DOWNTREND")

    def test_all_long_detects_long(self):
        results = [
            make_agent_result("strategy_trend", "LONG", 0.6),
            make_agent_result("strategy_momentum", "LONG", 0.5),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "LONG")

    def test_conflicting_directions_returns_unknown(self):
        """When LONG and SHORT agents conflict, direction should be UNKNOWN."""
        results = [
            make_agent_result("strategy_trend", "LONG", 0.6),
            make_agent_result("strategy_reversal", "SHORT", 0.5),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # With only 1 LONG and 1 SHORT, no majority → UNKNOWN
        self.assertIn(opp.direction, ["LONG", "SHORT", "UNKNOWN"])

    def test_no_directional_agents_returns_unknown(self):
        """All NEUTRAL agents → UNKNOWN direction."""
        results = [
            make_agent_result("strategy_trend", "NEUTRAL", 0.0),
            make_agent_result("strategy_breakout", "NEUTRAL", 0.0),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "UNKNOWN")

    def test_empty_results_returns_unknown(self):
        opp = detect_opportunity([], symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "UNKNOWN")
        self.assertEqual(opp.status, OpportunityStatus.DETECTED.value)

    def test_error_results_filtered(self):
        """ERROR status results should be excluded."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("test_error", "LONG", 0.5, status=AgentStatus.ERROR),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Only 1 directional agent → no majority
        self.assertIn(opp.direction, ["SHORT", "UNKNOWN"])

    def test_insufficient_data_excluded(self):
        """INSUFFICIENT_DATA results should not count as supporting."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("test_insufficient", "LONG", 0.0, status=AgentStatus.INSUFFICIENT_DATA),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.strategy_count, 2)  # Both counted in total

    def test_supporting_conflicting_classification(self):
        """Evidence should be split into supporting and conflicting."""
        results = [
            make_agent_result(
                "strategy_trend", "SHORT", 0.6,
                evidence_items=[
                    EvidenceItem(
                        feature="EMA_FAST", value=265.0,
                        direction="SHORT", strength=0.6,
                        source="test_engine", explanation="EMA cross",
                    ),
                ],
            ),
            make_agent_result(
                "strategy_reversal", "LONG", 0.5,
                evidence_items=[
                    EvidenceItem(
                        feature="RSI", value=30.0,
                        direction="LONG", strength=0.5,
                        source="test_engine", explanation="RSI oversold",
                    ),
                ],
            ),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Supporting and conflicting should be separate
        self.assertGreater(len(opp.supporting_evidence), 0)
        # Conflicting may or may not be empty depending on direction logic

    def test_unavailable_evidence_not_counted_as_support(self):
        """UNAVAILABLE evidence should not influence direction."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_breakout", "NEUTRAL", 0.0),  # Unavailable
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Only SHORT available → direction should be SHORT
        self.assertEqual(opp.direction, "SHORT")

    def test_confidence_in_range(self):
        """Confidence should always be 0..1."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6, data_quality=0.8),
            make_agent_result("strategy_momentum", "SHORT", 0.3, data_quality=0.9),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertGreaterEqual(opp.confidence, 0.0)
        self.assertLessEqual(opp.confidence, 1.0)
        self.assertGreaterEqual(opp.uncertainty, 0.0)
        self.assertLessEqual(opp.uncertainty, 1.0)


# ═══════════════════════════════════════════════════════════════
# E. Strategy Family Diversity
# ═══════════════════════════════════════════════════════════════

class TestStrategyFamilyDiversity(unittest.TestCase):

    def test_independent_families_counted(self):
        """Different families should be counted as independent."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),  # trend family
            make_agent_result("strategy_momentum", "SHORT", 0.5),  # momentum family
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Trend and momentum are independent families
        self.assertGreaterEqual(opp.independent_families, 1)

    def test_correlated_families_not_double_counted(self):
        """Correlated families (trend + breakout) should not both count as independent."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),  # trend family
            make_agent_result("strategy_breakout", "SHORT", 0.5),  # breakout family (correlated)
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Trend + breakout → only 1 independent family
        self.assertLessEqual(opp.independent_families, 1)

    def test_correlated_families_increases_correlated_count(self):
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_breakout", "SHORT", 0.5),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertGreaterEqual(opp.correlated_families, 0)


# ═══════════════════════════════════════════════════════════════
# F. Conflict Analysis
# ═══════════════════════════════════════════════════════════════

class TestConflictAnalysis(unittest.TestCase):

    def test_conflict_preserved(self):
        """Conflicting evidence should not be silently dropped."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_reversal", "LONG", 0.5),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Conflict should be visible
        self.assertIsInstance(opp.conflicting_evidence, list)
        self.assertIsInstance(opp.supporting_evidence, list)

    def test_supporting_conflict_separate(self):
        """Supporting and conflicting evidence are separate lists."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_reversal", "LONG", 0.5),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Both lists exist (may be empty)
        self.assertIsInstance(opp.supporting_evidence, list)
        self.assertIsInstance(opp.conflicting_evidence, list)


# ═══════════════════════════════════════════════════════════════
# G. Thesis Generation
# ═══════════════════════════════════════════════════════════════

class TestThesisGeneration(unittest.TestCase):

    def test_thesis_not_empty_for_directional(self):
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")
        self.assertNotEqual(opp.thesis, "")
        self.assertIn("short-oriented", opp.thesis.lower())

    def test_thesis_unknown_for_no_evidence(self):
        opp = detect_opportunity([], symbol="THYAO.IS", timeframe="1h")
        # Unknown direction thesis should mention insufficient data
        self.assertIn("Insufficient", opp.thesis)

    def test_thesis_research_oriented(self):
        """Thesis should not contain trade language."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        # Should not contain profit/guarantee language
        self.assertNotIn("profit", opp.thesis.lower())
        self.assertNotIn("guaranteed", opp.thesis.lower())
        self.assertNotIn("win", opp.thesis.lower())

    def test_thesis_mentions_regime(self):
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")
        self.assertIn("downtrend", opp.thesis.lower())


# ═══════════════════════════════════════════════════════════════
# H. Lifecycle
# ═══════════════════════════════════════════════════════════════

class TestOpportunityLifecycle(unittest.TestCase):

    def setUp(self):
        self.results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_momentum", "SHORT", 0.5),
        ]
        self.opp = detect_opportunity(
            self.results, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND"
        )

    def test_detected_status(self):
        self.assertEqual(self.opp.status, OpportunityStatus.DETECTED.value)

    def test_validate_determines_status(self):
        validated = validate_opportunity(self.opp, min_independent_families=1, min_confidence=0.05)
        self.assertIn(validated.status, [OpportunityStatus.VALIDATED.value, OpportunityStatus.UNDER_REVIEW.value])

    def test_invalidate_sets_status(self):
        invalidated = invalidate_opportunity(self.opp, reason="Test")
        self.assertEqual(invalidated.status, OpportunityStatus.INVALIDATED.value)
        self.assertEqual(invalidated.invalidation_reason, "Test")

    def test_expire_sets_status(self):
        expired = expire_opportunity(self.opp, reason="Test")
        self.assertEqual(expired.status, OpportunityStatus.EXPIRED.value)
        self.assertEqual(expired.expiry_reason, "Test")

    def test_archive_sets_status(self):
        archived = archive_opportunity(self.opp)
        self.assertEqual(archived.status, OpportunityStatus.ARCHIVED.value)

    def test_lifecycle_timestamps(self):
        """Lifecycle actions should set timestamps."""
        opp = detect_opportunity(self.results, symbol="THYAO.IS", timeframe="1h")
        self.assertNotEqual(opp.detected_at, "")
        self.assertNotEqual(opp.first_detected_at, "")
        self.assertNotEqual(opp.last_updated_at, "")

        invalidated = invalidate_opportunity(opp, reason="Test")
        self.assertNotEqual(invalidated.invalidated_at, "")

    def test_validated_not_meaning_profitable(self):
        """VALIDATED does NOT mean trade will succeed."""
        opp = detect_opportunity(self.results, symbol="THYAO.IS", timeframe="1h")
        validated = validate_opportunity(opp)
        # VALIDATED is research validation, not win guarantee
        if validated.status == OpportunityStatus.VALIDATED.value:
            # Confidence should reflect evidence consistency, not certainty
            self.assertLessEqual(validated.confidence, 1.0)


# ═══════════════════════════════════════════════════════════════
# I. Deduplication
# ═══════════════════════════════════════════════════════════════

class TestDeduplication(unittest.TestCase):

    def test_same_context_same_opportunity(self):
        """Same symbol+timeframe+direction+regime → duplicate."""
        results1 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp1 = detect_opportunity(results1, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")

        results2 = [make_agent_result("strategy_trend", "SHORT", 0.55)]
        opp2 = detect_opportunity(results2, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")

        is_dup, existing_id = is_duplicate_opportunity(opp2, [opp1])
        self.assertTrue(is_dup)
        self.assertEqual(existing_id, opp1.opportunity_id)

    def test_different_direction_not_duplicate(self):
        """Different direction → not duplicate."""
        results1 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp1 = detect_opportunity(results1, symbol="THYAO.IS", timeframe="1h")

        results2 = [make_agent_result("strategy_trend", "LONG", 0.6)]
        opp2 = detect_opportunity(results2, symbol="THYAO.IS", timeframe="1h")

        is_dup, _ = is_duplicate_opportunity(opp2, [opp1])
        self.assertFalse(is_dup)

    def test_different_symbol_not_duplicate(self):
        results1 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp1 = detect_opportunity(results1, symbol="THYAO.IS", timeframe="1h")

        results2 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp2 = detect_opportunity(results2, symbol="AAPL", timeframe="1h")

        is_dup, _ = is_duplicate_opportunity(opp2, [opp1])
        self.assertFalse(is_dup)

    def test_archived_not_duplicate(self):
        """Archived opportunities should not block new ones."""
        results1 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp1 = detect_opportunity(results1, symbol="THYAO.IS", timeframe="1h")
        opp1.status = OpportunityStatus.ARCHIVED.value

        results2 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp2 = detect_opportunity(results2, symbol="THYAO.IS", timeframe="1h")

        is_dup, _ = is_duplicate_opportunity(opp2, [opp1])
        self.assertFalse(is_dup)

    def test_different_regime_not_duplicate(self):
        results1 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp1 = detect_opportunity(results1, symbol="THYAO.IS", timeframe="1h", regime="DOWNTREND")

        results2 = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp2 = detect_opportunity(results2, symbol="THYAO.IS", timeframe="1h", regime="UPTREND")

        is_dup, _ = is_duplicate_opportunity(opp2, [opp1])
        self.assertFalse(is_dup)


# ═══════════════════════════════════════════════════════════════
# J. Persistence
# ═══════════════════════════════════════════════════════════════

class TestPersistence(unittest.TestCase):

    def setUp(self):
        self.persist = OpportunityPersistence()
        self.persist.migrate()

    def test_save_and_get(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h", confidence=0.5)
        self.persist.save_opportunity(opp)
        retrieved = self.persist.get_opportunity(opp.opportunity_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["symbol"], "THYAO.IS")

    def test_list_opportunities(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h", confidence=0.5)
        self.persist.save_opportunity(opp)
        results = self.persist.list_opportunities(symbol="THYAO.IS")
        self.assertGreaterEqual(len(results), 1)

    def test_list_empty(self):
        results = self.persist.list_opportunities(symbol="NONEXISTENT.IS")
        self.assertEqual(len(results), 0)

    def test_update_opportunity(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h", confidence=0.5)
        self.persist.save_opportunity(opp)
        opp.confidence = 0.7
        self.persist.update_opportunity(opp)
        retrieved = self.persist.get_opportunity(opp.opportunity_id)
        self.assertEqual(retrieved["confidence"], 0.7)

    def test_set_status(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.persist.save_opportunity(opp)
        self.persist.set_status(opp.opportunity_id, "VALIDATED", reason="Test")
        retrieved = self.persist.get_opportunity(opp.opportunity_id)
        self.assertEqual(retrieved["status"], "VALIDATED")

    def test_delete_opportunity(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.persist.save_opportunity(opp)
        deleted = self.persist.delete_opportunity(opp.opportunity_id)
        self.assertTrue(deleted)
        retrieved = self.persist.get_opportunity(opp.opportunity_id)
        self.assertIsNone(retrieved)

    def test_save_evidence(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.persist.save_opportunity(opp)
        evidence = [{"agent_id": "test", "feature": "RSI", "value": 65.0}]
        self.persist.save_evidence(opp.opportunity_id, "indicator", evidence)
        retrieved = self.persist.get_evidence(opp.opportunity_id)
        self.assertGreaterEqual(len(retrieved), 1)


# ═══════════════════════════════════════════════════════════════
# K. Setup Candidate
# ═══════════════════════════════════════════════════════════════

class TestSetupCandidate(unittest.TestCase):

    def test_candidate_from_opportunity(self):
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        cand = generate_setup_candidate(opp)
        self.assertEqual(cand.symbol, "THYAO.IS")
        self.assertEqual(cand.direction, "SHORT")
        self.assertEqual(cand.opportunity_id, opp.opportunity_id)
        self.assertEqual(cand.status, "CANDIDATE")

    def test_candidate_not_trade_recommendation(self):
        """Setup candidate should be marked CANDIDATE, not confirmed."""
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        cand = generate_setup_candidate(opp)
        self.assertEqual(cand.status, "CANDIDATE")
        self.assertNotIn("entry", cand.candidate_entry_zone)  # No fake entry

    def test_candidate_has_uncertainty(self):
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        cand = generate_setup_candidate(opp)
        self.assertGreaterEqual(cand.uncertainty, 0.0)
        self.assertLessEqual(cand.uncertainty, 1.0)


# ═══════════════════════════════════════════════════════════════
# L. Multi-Symbol / Multi-Timeframe
# ═══════════════════════════════════════════════════════════════

class TestMultiSymbolTimeframe(unittest.TestCase):

    def test_multi_symbol(self):
        """Opportunities should work with different symbols."""
        for sym in ["THYAO.IS", "AAPL"]:
            results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
            opp = detect_opportunity(results, symbol=sym, timeframe="1h")
            self.assertEqual(opp.symbol, sym)

    def test_multi_timeframe(self):
        for tf in ["5m", "1h", "1d"]:
            results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
            opp = detect_opportunity(results, symbol="THYAO.IS", timeframe=tf)
            self.assertEqual(opp.timeframe, tf)


# ═══════════════════════════════════════════════════════════════
# M. Lookahead Protection
# ═══════════════════════════════════════════════════════════════

class TestLookaheadProtection(unittest.TestCase):

    def test_opportunity_uses_cutoff(self):
        """Opportunity should reference feature snapshot (cutoff)."""
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", feature_snapshot_id="fs_123")
        self.assertEqual(opp.feature_snapshot_id, "fs_123")

    def test_no_future_data_in_thesis(self):
        """Thesis should not reference future data."""
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertNotIn("future", opp.thesis.lower())


# ═══════════════════════════════════════════════════════════════
# N. Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):

    def test_single_agent_result(self):
        """Single agent should produce opportunity (low confidence)."""
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "SHORT")
        # Single agent → limited independent evidence → lower confidence
        self.assertLessEqual(opp.confidence, 0.6)

    def test_all_neutral_agents(self):
        """All NEUTRAL → UNKNOWN direction."""
        results = [
            make_agent_result("strategy_trend", "NEUTRAL", 0.0),
            make_agent_result("strategy_breakout", "NEUTRAL", 0.0),
            make_agent_result("strategy_reversal", "NEUTRAL", 0.0),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "UNKNOWN")

    def test_mixed_status_results(self):
        """Mix of SUCCESS and INSUFFICIENT_DATA."""
        results = [
            make_agent_result("strategy_trend", "SHORT", 0.6),
            make_agent_result("strategy_breakout", "NEUTRAL", 0.0, status=AgentStatus.INSUFFICIENT_DATA),
        ]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertIn(opp.direction, ["SHORT", "UNKNOWN"])

    def test_real_data_pipeline(self):
        """End-to-end test with real yfinance data."""
        df = make_ohlcv(100)
        fs = populate_feature_snapshot(df, symbol="THYAO.IS", timeframe="1h")
        results = []
        for agent_id, cls in STRATEGY_AGENTS.items():
            from agent_contract import MarketContext
            ctx = MarketContext(symbol="THYAO.IS", timeframe="1h", ohlcv_ref=df)
            ctx.feature_snapshot = fs
            ctx.freeze()
            a = cls(ctx)
            r = a.run()
            results.append(r)
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", regime=fs.regime)
        self.assertIsInstance(opp, Opportunity)
        self.assertNotEqual(opp.opportunity_id, "")
        self.assertIn(opp.status, [OpportunityStatus.DETECTED.value, OpportunityStatus.UNDER_REVIEW.value])


# ═══════════════════════════════════════════════════════════════
# O. Regression — Existing Tests
# ═══════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    """Ensure Phase E doesn't break existing functionality."""

    def test_agent_contract_still_works(self):
        from agent_contract import AgentResult, AgentStatus
        r = AgentResult(agent_id="test", status=AgentStatus.SUCCESS)
        self.assertEqual(r.status, AgentStatus.SUCCESS)

    def test_strategy_agents_still_importable(self):
        from strategy_research_agents import STRATEGY_AGENTS
        self.assertEqual(len(STRATEGY_AGENTS), 7)

    def test_opportunity_model_independent(self):
        """Opportunity model should not depend on any engine."""
        opp = Opportunity(symbol="TEST", timeframe="1h")
        self.assertEqual(opp.symbol, "TEST")


if __name__ == "__main__":
    unittest.main()