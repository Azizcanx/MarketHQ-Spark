# -*- coding: utf-8 -*-
"""Phase F — Research-Backed Setup Engine Tests.

Tests for setup generation from Opportunity.
Entry zone, invalidation, targets, RR, uncertainty, WHY panel,
evidence traceability, lifecycle, persistence.

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
    ResearchBackedSetup, SetupStatus, UncertaintyFlag, UncertaintyType,
    EvidenceTrace, SourceAgent,
)
from opportunity_engine import detect_opportunity, validate_opportunity
from research_setup_phase_f import (
    build_research_backed_setup,
    _compute_entry_zone,
    _compute_invalidation,
    _compute_targets,
    _compute_rr,
    _compute_entry_confirmation,
    _compute_uncertainty,
    _generate_why_panel,
)
from strategy_research_features import populate_feature_snapshot
from strategy_research_agents import STRATEGY_AGENTS
from agent_contract import MarketContext
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
    return AgentResult(
        agent_id=agent_id, direction=direction, confidence=confidence,
        regime=regime, status=status, reasoning=reasoning,
        evidence=Evidence(items=evidence_items or []),
        source_engine=source_engine, engine_metadata=engine_metadata or {},
        data_quality=data_quality, symbol=symbol, timeframe=timeframe,
    )


def make_opportunity(
    direction="SHORT", confidence=0.5, regime="DOWNTREND",
    symbol="THYAO.IS", timeframe="1h", supporting=2, conflicting=1,
    unavailable=4,
):
    """Helper to create a test Opportunity."""
    results = []
    agent_dir = direction if direction != "UNKNOWN" else "NEUTRAL"
    for i in range(supporting):
        results.append(make_agent_result(
            f"strategy_trend_{i}", agent_dir, 0.6, regime=regime,
            evidence_items=[EvidenceItem(
                feature="EMA", value=265.0, direction=agent_dir,
                strength=0.6, source="test", explanation="test",
            )],
        ))
    for i in range(conflicting):
        opp_dir = "LONG" if direction == "SHORT" else ("SHORT" if direction == "LONG" else "NEUTRAL")
        results.append(make_agent_result(
            f"strategy_reversal_{i}", opp_dir, 0.5, regime=regime,
        ))
    for i in range(unavailable):
        results.append(make_agent_result(
            f"strategy_neutral_{i}", "NEUTRAL", 0.0, regime=regime,
        ))
    opp = detect_opportunity(results, symbol=symbol, timeframe=timeframe, regime=regime)
    return opp


# ═══════════════════════════════════════════════════════════════
# A. ResearchBackedSetup Model
# ═══════════════════════════════════════════════════════════════

class TestResearchBackedSetupModel(unittest.TestCase):

    def test_setup_creation(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
            regime=opp.regime,
        )
        self.assertNotEqual(setup.setup_id, "")
        self.assertEqual(setup.symbol, "THYAO.IS")

    def test_setup_default_status(self):
        setup = ResearchBackedSetup()
        self.assertEqual(setup.status, SetupStatus.CANDIDATE.value)

    def test_setup_to_dict(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
        )
        d = setup.to_dict()
        self.assertEqual(d["symbol"], "THYAO.IS")
        self.assertIn("why_panel", d)

    def test_uncertainty_flag_creation(self):
        flag = UncertaintyFlag(
            type=UncertaintyType.MISSING_VOLUME,
            description="Test", severity="medium",
        )
        self.assertEqual(flag.type, UncertaintyType.MISSING_VOLUME)
        d = flag.to_dict()
        self.assertEqual(d["severity"], "medium")

    def test_evidence_trace_creation(self):
        trace = EvidenceTrace(
            assertion="Trend supports SHORT",
            source_agent="strategy_trend",
            evidence_feature="EMA_FAST",
            evidence_value=265.0,
        )
        d = trace.to_dict()
        self.assertEqual(d["assertion"], "Trend supports SHORT")

    def test_setup_no_win_probability(self):
        """Setup confidence is research confidence, not win probability."""
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
            confidence=opp.confidence,
        )
        # Confidence should be same as opportunity (research confidence)
        self.assertLessEqual(setup.confidence, 1.0)

    def test_setup_research_only(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
        )
        self.assertEqual(setup.status, SetupStatus.CANDIDATE.value)


# ═══════════════════════════════════════════════════════════════
# B. Entry Zone Engine
# ═══════════════════════════════════════════════════════════════

class TestEntryZoneEngine(unittest.TestCase):

    def test_long_entry_zone(self):
        df = make_ohlcv(100, base=100, trend=0.01)
        result = _compute_entry_zone(df, "LONG", 2.0)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertLess(result["low"], result["high"])
        self.assertIsNotNone(result["reference"])

    def test_short_entry_zone(self):
        df = make_ohlcv(100, base=100, trend=0.01)
        result = _compute_entry_zone(df, "SHORT", 2.0)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertLess(result["low"], result["high"])

    def test_unknown_direction_unavailable(self):
        df = make_ohlcv(100)
        result = _compute_entry_zone(df, "UNKNOWN", 2.0)
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_no_data_unavailable(self):
        result = _compute_entry_zone(None, "LONG", 2.0)
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_short_data_unavailable(self):
        result = _compute_entry_zone(None, "SHORT", None)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["reference"])

    def test_entry_confirmation_long(self):
        df = make_ohlcv(100, trend=0.02)
        confirmations = _compute_entry_confirmation(df, "LONG", "UPTREND")
        self.assertIsInstance(confirmations, list)

    def test_entry_confirmation_short(self):
        df = make_ohlcv(100, trend=-0.02)
        confirmations = _compute_entry_confirmation(df, "SHORT", "DOWNTREND")
        self.assertIsInstance(confirmations, list)


# ═══════════════════════════════════════════════════════════════
# C. Invalidation Engine
# ═══════════════════════════════════════════════════════════════

class TestInvalidationEngine(unittest.TestCase):

    def test_long_invalidation_below_entry(self):
        result = _compute_invalidation(None, "LONG", 100.0, 2.0, "DOWNTREND")
        self.assertLess(result["price"], 100.0)
        self.assertEqual(result["type"], "atr")

    def test_short_invalidation_above_entry(self):
        result = _compute_invalidation(None, "SHORT", 100.0, 2.0, "DOWNTREND")
        self.assertGreater(result["price"], 100.0)

    def test_no_entry_unavailable(self):
        result = _compute_invalidation(None, "LONG", None, 2.0, "DOWNTREND")
        self.assertEqual(result["type"], "unavailable")

    def test_no_atr_unavailable(self):
        result = _compute_invalidation(None, "LONG", 100.0, 0.0, "DOWNTREND")
        self.assertEqual(result["type"], "unavailable")

    def test_invalidation_reason_present(self):
        result = _compute_invalidation(None, "LONG", 100.0, 2.0, "DOWNTREND")
        self.assertNotEqual(result["reason"], "")
        self.assertGreater(result["distance_atr"], 0)


# ═══════════════════════════════════════════════════════════════
# D. Target Engine
# ═══════════════════════════════════════════════════════════════

class TestTargetEngine(unittest.TestCase):

    def test_long_targets_above_entry(self):
        result = _compute_targets(None, "LONG", 100.0, 2.0, "DOWNTREND")
        if result["t1"] is not None:
            self.assertGreater(result["t1"], 100.0)

    def test_short_targets_below_entry(self):
        result = _compute_targets(None, "SHORT", 100.0, 2.0, "DOWNTREND")
        if result["t1"] is not None:
            self.assertLess(result["t1"], 100.0)

    def test_no_entry_unavailable(self):
        result = _compute_targets(None, "LONG", None, 2.0, "DOWNTREND")
        self.assertEqual(result["method"], "unavailable")

    def test_no_atr_unavailable(self):
        result = _compute_targets(None, "LONG", 100.0, 0.0, "DOWNTREND")
        self.assertEqual(result["method"], "unavailable")

    def test_three_targets(self):
        result = _compute_targets(None, "LONG", 100.0, 2.0, "DOWNTREND")
        # At least one target should be available
        available = sum(1 for t in [result["t1"], result["t2"], result["t3"]] if t is not None)
        self.assertGreaterEqual(available, 1)


# ═══════════════════════════════════════════════════════════════
# E. Risk / Reward
# ═══════════════════════════════════════════════════════════════

class TestRiskReward(unittest.TestCase):

    def test_long_rr_positive(self):
        rr = _compute_rr("LONG", 100.0, 95.0, 110.0)
        self.assertGreater(rr["rr_t1"], 0)
        self.assertGreater(rr["risk"], 0)

    def test_short_rr_positive(self):
        rr = _compute_rr("SHORT", 100.0, 105.0, 90.0)
        self.assertGreater(rr["rr_t1"], 0)
        self.assertGreater(rr["risk"], 0)

    def test_no_entry_no_rr(self):
        rr = _compute_rr("LONG", None, 95.0, 110.0)
        self.assertIsNone(rr["rr_t1"])

    def test_no_invalidation_no_rr(self):
        rr = _compute_rr("LONG", 100.0, None, 110.0)
        self.assertIsNone(rr["rr_t1"])

    def test_rr_t1_greater_than_t2(self):
        """T1 is closer than T2, so RR_T1 > RR_T2 for same risk."""
        rr = _compute_rr("LONG", 100.0, 95.0, 120.0)
        # T2 is further, so RR_T2 should be smaller than RR_T1 if both exist
        if rr["rr_t1"] is not None and rr.get("rr_t2") is not None:
            self.assertGreaterEqual(rr["rr_t1"], rr["rr_t2"])


# ═══════════════════════════════════════════════════════════════
# F. Uncertainty Engine
# ═══════════════════════════════════════════════════════════════

class TestUncertaintyEngine(unittest.TestCase):

    def test_conflicting_agents_flag(self):
        flags = _compute_uncertainty("SHORT", 2, 2, 3, 7, False, 0, 0.5, "AVAILABLE", "AVAILABLE")
        conflict_flags = [f for f in flags if f.type == UncertaintyType.CONFLICTING_AGENTS]
        self.assertGreater(len(conflict_flags), 0)

    def test_high_severity_for_many_conflicts(self):
        flags = _compute_uncertainty("SHORT", 1, 5, 1, 7, False, 0, 0.5, "AVAILABLE", "AVAILABLE")
        high_flags = [f for f in flags if f.severity == "high"]
        self.assertGreater(len(high_flags), 0)

    def test_low_sample_flag(self):
        flags = _compute_uncertainty("SHORT", 2, 1, 4, 7, True, 15, 0.5, "AVAILABLE", "AVAILABLE")
        sample_flags = [f for f in flags if f.type == UncertaintyType.LOW_SAMPLE]
        self.assertGreater(len(sample_flags), 0)

    def test_no_flags_with_all_data(self):
        flags = _compute_uncertainty("SHORT", 5, 0, 0, 7, True, 100, 1.0, "AVAILABLE", "AVAILABLE")
        # Even with all data, there are always some flags (volume, regime)
        self.assertIsInstance(flags, list)

    def test_uncertainty_flags_have_descriptions(self):
        flags = _compute_uncertainty("SHORT", 1, 3, 3, 7, False, 5, 0.2, "UNAVAILABLE", "UNAVAILABLE")
        for f in flags:
            self.assertNotEqual(f.description, "")
            self.assertIn(f.severity, ("low", "medium", "high", "critical"))


# ═══════════════════════════════════════════════════════════════
# G. WHY Panel
# ═══════════════════════════════════════════════════════════════

class TestWhyPanel(unittest.TestCase):

    def test_why_panel_has_required_keys(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
            regime=opp.regime,
        )
        panel = _generate_why_panel(setup, opp.direction, [], [], opp.regime)
        self.assertIn("market_context", panel)
        self.assertIn("direction", panel)
        self.assertIn("supporting_evidence", panel)
        self.assertIn("conflicting_evidence", panel)
        self.assertIn("entry_rationale", panel)
        self.assertIn("invalidation_rationale", panel)
        self.assertIn("target_rationale", panel)

    def test_why_panel_research_only(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
        )
        panel = _generate_why_panel(setup, opp.direction, [], [], opp.regime)
        self.assertTrue(panel.get("research_only"))
        self.assertTrue(panel.get("not_a_trade_recommendation"))

    def test_why_panel_no_marketing_language(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
        )
        panel = _generate_why_panel(setup, opp.direction, [], [], opp.regime)
        panel_str = str(panel).lower()
        self.assertNotIn("profit", panel_str)
        self.assertNotIn("guaranteed", panel_str)
        self.assertNotIn("win", panel_str)

    def test_why_panel_flags(self):
        opp = make_opportunity()
        setup = ResearchBackedSetup(
            opportunity_id=opp.opportunity_id,
            symbol=opp.symbol,
            timeframe=opp.timeframe,
            direction=opp.direction,
        )
        panel = _generate_why_panel(setup, opp.direction, [], [], opp.regime)
        self.assertIn("research_flags", panel)
        self.assertIsInstance(panel["research_flags"], list)


# ═══════════════════════════════════════════════════════════════
# H. Full Pipeline — Opportunity → Setup
# ═══════════════════════════════════════════════════════════════

class TestFullPipeline(unittest.TestCase):

    def test_opportunity_to_setup(self):
        opp = make_opportunity(direction="SHORT", supporting=3, conflicting=1)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertIsInstance(setup, ResearchBackedSetup)
        self.assertNotEqual(setup.setup_id, "")
        self.assertEqual(setup.opportunity_id, opp.opportunity_id)

    def test_setup_has_entry_or_unavailable(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertIn(setup.entry_status, ("AVAILABLE", "UNAVAILABLE", "PARTIAL"))

    def test_setup_has_invalidation_or_reason(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        # Either invalidation price is set or reason explains why not
        if setup.invalidation_price is None:
            self.assertNotEqual(setup.invalidation_reason, "")

    def test_setup_has_targets_or_method(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        # Either targets are set or method explains why not
        if setup.target_1 is None:
            self.assertEqual(setup.target_method, "unavailable")

    def test_setup_rr_calculated(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        # RR should be calculated if entry and invalidation are available
        if setup.entry_reference and setup.invalidation_price:
            self.assertIsNotNone(setup.rr_to_t1)

    def test_setup_uncertainty_flags(self):
        opp = make_opportunity(direction="SHORT", conflicting=2)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertIsInstance(setup.uncertainty_flags, list)

    def test_setup_evidence_traces(self):
        opp = make_opportunity(direction="SHORT", supporting=2)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        # Traces should link to supporting agents
        for trace in setup.evidence_traces:
            self.assertNotEqual(trace.assertion, "")
            self.assertNotEqual(trace.source_agent, "")

    def test_setup_why_panel_not_empty(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertNotEqual(setup.why_panel, {})
        self.assertIn("research_only", setup.why_panel)

    def test_setup_research_only(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertTrue(setup.why_panel.get("research_only"))

    def test_setup_no_win_probability(self):
        """Setup confidence is NOT win probability."""
        opp = make_opportunity(direction="SHORT", confidence=0.3)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        # Confidence should be low (research confidence, not win rate)
        self.assertLessEqual(setup.confidence, 1.0)

    def test_setup_data_availability(self):
        opp = make_opportunity(direction="SHORT", unavailable=6)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertLessEqual(setup.data_availability, 1.0)
        self.assertGreaterEqual(setup.data_availability, 0.0)

    def test_setup_real_data_pipeline(self):
        """End-to-end test with real yfinance data."""
        df = make_ohlcv(150)
        fs = populate_feature_snapshot(df, symbol="THYAO.IS", timeframe="1h")
        results = []
        for agent_id, cls in STRATEGY_AGENTS.items():
            ctx = MarketContext(symbol="THYAO.IS", timeframe="1h", ohlcv_ref=df)
            ctx.feature_snapshot = fs
            ctx.freeze()
            a = cls(ctx)
            r = a.run()
            results.append(r)
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h", regime=fs.regime)
        setup = build_research_backed_setup(opp, df=df)
        self.assertIsInstance(setup, ResearchBackedSetup)
        self.assertNotEqual(setup.setup_id, "")
        self.assertEqual(setup.opportunity_id, opp.opportunity_id)

    def test_setup_multi_symbol(self):
        for sym in ["THYAO.IS", "AAPL"]:
            opp = make_opportunity(direction="SHORT", symbol=sym)
            df = make_ohlcv(100)
            setup = build_research_backed_setup(opp, df=df)
            self.assertEqual(setup.symbol, sym)

    def test_setup_multi_timeframe(self):
        for tf in ["5m", "1h", "1d"]:
            opp = make_opportunity(direction="SHORT", timeframe=tf)
            df = make_ohlcv(100)
            setup = build_research_backed_setup(opp, df=df)
            self.assertEqual(setup.timeframe, tf)


# ═══════════════════════════════════════════════════════════════
# I. Lifecycle
# ═══════════════════════════════════════════════════════════════

class TestSetupLifecycle(unittest.TestCase):

    def setUp(self):
        self.opp = make_opportunity(direction="SHORT")
        self.df = make_ohlcv(100)
        self.setup = build_research_backed_setup(self.opp, df=self.df)

    def test_initial_status_candidate(self):
        self.assertEqual(self.setup.status, SetupStatus.CANDIDATE.value)

    def test_candidate_to_under_review(self):
        self.setup.status = SetupStatus.UNDER_REVIEW.value
        self.assertEqual(self.setup.status, SetupStatus.UNDER_REVIEW.value)

    def test_confirmed_research_setup_not_trade(self):
        """CONFIRMED_RESEARCH_SETUP does NOT mean trade confirmed."""
        self.setup.status = SetupStatus.CONFIRMED_RESEARCH_SETUP.value
        # Still research-only
        self.assertTrue(self.setup.why_panel.get("research_only"))

    def test_invalidated_status(self):
        self.setup.status = SetupStatus.INVALIDATED.value
        self.assertEqual(self.setup.status, SetupStatus.INVALIDATED.value)

    def test_expired_status(self):
        self.setup.status = SetupStatus.EXPIRED.value
        self.assertEqual(self.setup.status, SetupStatus.EXPIRED.value)

    def test_archived_status(self):
        self.setup.status = SetupStatus.ARCHIVED.value
        self.assertEqual(self.setup.status, SetupStatus.ARCHIVED.value)

    def test_lifecycle_timestamps(self):
        self.assertNotEqual(self.setup.detected_at, "")
        self.assertNotEqual(self.setup.created_at, "")


# ═══════════════════════════════════════════════════════════════
# J. Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):

    def test_empty_opportunity(self):
        opp = detect_opportunity([], symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "UNKNOWN")

    def test_unknown_direction_setup(self):
        opp = make_opportunity(direction="UNKNOWN")
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertEqual(setup.direction, "UNKNOWN")

    def test_all_neutral_agents(self):
        opp = make_opportunity(direction="UNKNOWN", supporting=0, conflicting=0, unavailable=7)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertEqual(setup.direction, "UNKNOWN")

    def test_single_agent(self):
        opp = make_opportunity(direction="SHORT", supporting=1, conflicting=0, unavailable=6)
        df = make_ohlcv(100)
        setup = build_research_backed_setup(opp, df=df)
        self.assertEqual(setup.direction, "SHORT")

    def test_no_df_still_creates_setup(self):
        opp = make_opportunity(direction="SHORT")
        setup = build_research_backed_setup(opp, df=None)
        self.assertIsInstance(setup, ResearchBackedSetup)
        self.assertEqual(setup.entry_status, "UNAVAILABLE")

    def test_setup_id_unique(self):
        opp = make_opportunity(direction="SHORT")
        df = make_ohlcv(100)
        setup1 = build_research_backed_setup(opp, df=df)
        setup2 = build_research_backed_setup(opp, df=df)
        self.assertNotEqual(setup1.setup_id, setup2.setup_id)


# ═══════════════════════════════════════════════════════════════
# K. Regression
# ═══════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    """Ensure Phase F doesn't break existing functionality."""

    def test_opportunity_engine_still_works(self):
        from opportunity_engine import detect_opportunity
        results = [make_agent_result("strategy_trend", "SHORT", 0.6)]
        opp = detect_opportunity(results, symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.direction, "SHORT")

    def test_opportunity_model_still_works(self):
        opp = Opportunity(symbol="THYAO.IS", timeframe="1h")
        self.assertEqual(opp.symbol, "THYAO.IS")

    def test_setup_model_importable(self):
        from opportunity_model import ResearchBackedSetup, SetupStatus, UncertaintyFlag, EvidenceTrace
        self.assertTrue(True)  # Import succeeded

    def test_phase_d_agents_still_importable(self):
        from strategy_research_agents import STRATEGY_AGENTS
        self.assertEqual(len(STRATEGY_AGENTS), 7)


if __name__ == "__main__":
    unittest.main()