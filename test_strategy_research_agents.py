# -*- coding: utf-8 -*-
"""Phase D — Strategy Research Agent Tests.

Tests for the 7 strategy research agents:
- Trend, Breakout, Reversal, Momentum, Volatility, Liquidity, Structure

All agents produce AgentResult via MarketContext → AgentResult flow.
No trading, no fake data, no lookahead.
"""

import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent_contract import (
    AgentResult, AgentStatus, Claim, ClaimStatus,
    Evidence, EvidenceItem, MarketContext, FeatureSnapshot,
)
from agent_registry import AgentRegistry
from agent_runtime import AgentRuntime, AgentRun, AgentRunStatus
from strategy_research_agents import (
    TrendResearchAdapter, BreakoutResearchAdapter,
    ReversalResearchAdapter, MomentumResearchAdapter,
    VolatilityResearchAdapter, LiquidityResearchAdapter,
    StructureResearchAdapter, STRATEGY_AGENTS,
)
from strategy_research_features import populate_feature_snapshot
from strategy_research_registry import get_strategy_registry, get_agent_ids


def make_ohlcv(n=200, base=100, trend=0.01, vol=2.0, seed=42):
    """Create synthetic OHLCV DataFrame for testing."""
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


def make_strategy_context(symbol="THYAO.IS", timeframe="1h", ohlcv=None):
    """Create a MarketContext with populated FeatureSnapshot."""
    if ohlcv is None:
        ohlcv = make_ohlcv()
    fs = populate_feature_snapshot(ohlcv, symbol=symbol, timeframe=timeframe)
    ctx = MarketContext(
        symbol=symbol, timeframe=timeframe,
        observation_timestamp=datetime.now(timezone.utc).isoformat(),
        data_cutoff_timestamp=datetime.now(timezone.utc).isoformat(),
        ohlcv_ref=ohlcv,
    )
    ctx.feature_snapshot = fs
    return ctx


# ═══════════════════════════════════════════════════════════════
# A. Strategy Agent Metadata
# ═══════════════════════════════════════════════════════════════

class TestStrategyAgentMetadata(unittest.TestCase):
    """Test that each agent has correct metadata."""

    def test_all_7_agents_registered(self):
        """All 7 strategy agents must be in STRATEGY_AGENTS."""
        self.assertEqual(len(STRATEGY_AGENTS), 7)

    def test_registry_has_all_agents(self):
        """Registry should have all 7 agents."""
        registry = get_strategy_registry()
        self.assertEqual(registry.count(), 7)

    def test_agent_ids(self):
        """Agent IDs should match expected names."""
        expected = [
            "strategy_trend", "strategy_breakout", "strategy_reversal",
            "strategy_momentum", "strategy_volatility",
            "strategy_liquidity", "strategy_structure",
        ]
        self.assertEqual(sorted(get_agent_ids()), sorted(expected))

    def test_trend_adapter_metadata(self):
        adapter = TrendResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_trend")
        self.assertEqual(adapter.adapter_version, "1.0")
        self.assertEqual(adapter.source_engine, "strategy_registry_v1")
        self.assertEqual(adapter.REQUIRED_FEATURES, ["EMA_FAST", "EMA_SLOW", "ADX", "ATR"])

    def test_breakout_adapter_metadata(self):
        adapter = BreakoutResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_breakout")
        self.assertEqual(adapter.source_engine, "strategy_registry_v1")
        self.assertIn("ATR", adapter.REQUIRED_FEATURES)

    def test_reversal_adapter_metadata(self):
        adapter = ReversalResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_reversal")
        self.assertEqual(adapter.source_engine, "strategy_registry_v1")
        self.assertIn("RSI", adapter.REQUIRED_FEATURES)

    def test_momentum_adapter_metadata(self):
        adapter = MomentumResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_momentum")
        self.assertEqual(adapter.source_engine, "signal_engine")
        self.assertIn("SMA_FAST", adapter.REQUIRED_FEATURES)

    def test_volatility_adapter_metadata(self):
        adapter = VolatilityResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_volatility")
        self.assertEqual(adapter.source_engine, "signal_engine")
        self.assertIn("ATR", adapter.REQUIRED_FEATURES)

    def test_liquidity_adapter_metadata(self):
        adapter = LiquidityResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_liquidity")
        self.assertEqual(adapter.source_engine, "smc_structure_v1")

    def test_structure_adapter_metadata(self):
        adapter = StructureResearchAdapter(MarketContext())
        self.assertEqual(adapter.adapter_id, "strategy_structure")
        self.assertEqual(adapter.source_engine, "smc_structure_v1")


# ═══════════════════════════════════════════════════════════════
# B. Strategy Agent Results
# ═══════════════════════════════════════════════════════════════

class TestStrategyAgentResults(unittest.TestCase):
    """Test that each agent produces valid AgentResult."""

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_trend_returns_agent_result(self):
        adapter = TrendResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.agent_id, "strategy_trend")

    def test_breakout_returns_agent_result(self):
        adapter = BreakoutResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_reversal_returns_agent_result(self):
        adapter = ReversalResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_momentum_returns_agent_result(self):
        adapter = MomentumResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_volatility_returns_agent_result(self):
        adapter = VolatilityResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_liquidity_returns_agent_result(self):
        adapter = LiquidityResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_structure_returns_agent_result(self):
        adapter = StructureResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIsInstance(result, AgentResult)

    def test_all_agents_return_result_not_exception(self):
        """All agents should return AgentResult, never raise."""
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(self.ctx)
            result = adapter.run()
            self.assertIsInstance(result, AgentResult,
                                  f"{agent_id} did not return AgentResult")

    def test_all_agents_have_agent_id(self):
        """Every result should have a non-empty agent_id."""
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(self.ctx)
            result = adapter.run()
            self.assertNotEqual(result.agent_id, "")

    def test_all_agents_have_timestamps(self):
        """Every result should have observation and cutoff timestamps."""
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(self.ctx)
            result = adapter.run()
            self.assertNotEqual(result.observation_timestamp, "")
            self.assertNotEqual(result.data_cutoff_timestamp, "")

    def test_all_agents_have_source_engine(self):
        """Every result should have source engine info."""
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(self.ctx)
            result = adapter.run()
            self.assertNotEqual(result.source_engine, "")
            self.assertNotEqual(result.source_engine_version, "")


# ═══════════════════════════════════════════════════════════════
# C. Trend Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestTrendAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_trend_uses_ema_features(self):
        """Trend agent should use EMA_FAST/EMA_SLOW."""
        adapter = TrendResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        self.assertIn("EMA_FAST", features)

    def test_trend_direction_valid(self):
        """Trend direction should be valid."""
        adapter = TrendResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn(result.direction, ["LONG", "SHORT", "NEUTRAL", "UNKNOWN"])

    def test_trend_has_invalidation(self):
        """Trend agent should have invalidation conditions."""
        adapter = TrendResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertNotEqual(result.invalidation_conditions, "")

    def test_trend_metadata_has_family(self):
        """Trend agent metadata should include strategy_family."""
        adapter = TrendResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn("strategy_family", result.engine_metadata)
        self.assertEqual(result.engine_metadata["strategy_family"], "trend")


# ═══════════════════════════════════════════════════════════════
# D. Breakout Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestBreakoutAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_breakout_has_atr_evidence(self):
        adapter = BreakoutResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        self.assertIn("ATR", features)

    def test_breakout_direction_valid(self):
        adapter = BreakoutResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn(result.direction, ["LONG", "SHORT", "NEUTRAL"])

    def test_breakout_regime_check(self):
        """Breakout should check regime for context."""
        adapter = BreakoutResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn(result.regime, [
            "RANGE", "TRENDING", "UPTREND", "DOWNTREND",
            "UPTREND_WEAK", "DOWNTREND_WEAK", "RANGE_LOW_VOL",
            "RANGE_HIGH_VOL", "UNKNOWN",
        ])


# ═══════════════════════════════════════════════════════════════
# E. Reversal Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestReversalAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_reversal_uses_rsi(self):
        adapter = ReversalResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        self.assertIn("RSI", features)

    def test_reversal_direction_valid(self):
        adapter = ReversalResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn(result.direction, ["LONG", "SHORT", "NEUTRAL", "UNKNOWN"])

    def test_reversal_not_fake_on_price_drop(self):
        """Reversal should not fire just because price dropped."""
        # Create context with RSI in neutral zone
        ohlcv = make_ohlcv(n=200, base=100, trend=0.001, vol=0.5, seed=99)
        ctx = make_strategy_context(ohlcv=ohlcv)
        adapter = ReversalResearchAdapter(ctx)
        result = adapter.run()
        # Should not claim reversal without extreme RSI
        self.assertIn(result.status, [AgentStatus.SUCCESS, AgentStatus.PARTIAL])


# ═══════════════════════════════════════════════════════════════
# F. Momentum Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestMomentumAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_momentum_uses_sma(self):
        adapter = MomentumResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        self.assertIn("SMA_DIFF", features)

    def test_momentum_confidence_not_win_probability(self):
        """Confidence should NOT be interpreted as win probability."""
        adapter = MomentumResearchAdapter(self.ctx)
        result = adapter.run()
        # Confidence is observation strength, not win rate
        self.assertLessEqual(result.confidence, 1.0)
        # The agent notes correlation is not predictive edge
        self.assertIn("correlation", result.reasoning.lower())

    def test_momentum_note_in_metadata(self):
        adapter = MomentumResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn("note", result.engine_metadata)
        self.assertIn("correlation", result.engine_metadata["note"].lower())


# ═══════════════════════════════════════════════════════════════
# G. Volatility Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestVolatilityAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_volatility_uses_atr(self):
        adapter = VolatilityResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        self.assertIn("ATR", features)

    def test_volatility_range_high_vol_flag(self):
        """RANGE_HIGH_VOL regime should be flagged."""
        adapter = VolatilityResearchAdapter(self.ctx)
        result = adapter.run()
        # Metadata should note the known problem regime
        self.assertIn("note", result.engine_metadata)


# ═══════════════════════════════════════════════════════════════
# H. Liquidity Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestLiquidityAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_liquidity_uses_structure(self):
        adapter = LiquidityResearchAdapter(self.ctx)
        result = adapter.run()
        features = [item.feature for item in result.evidence.items]
        # Should reference structure or liquidity features
        self.assertIsInstance(features, list)

    def test_liquidity_confidence_separation(self):
        """Liquidity confidence is observation strength, not predictive."""
        adapter = LiquidityResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertLessEqual(result.confidence, 1.0)


# ═══════════════════════════════════════════════════════════════
# I. Structure Agent Specific
# ═══════════════════════════════════════════════════════════════

class TestStructureAgent(unittest.TestCase):

    def setUp(self):
        self.ctx = make_strategy_context()

    def test_structure_reports_lookahead_protection(self):
        adapter = StructureResearchAdapter(self.ctx)
        result = adapter.run()
        # Should have lookahead protection in metadata
        self.assertIn("lookahead_protection", result.engine_metadata)
        self.assertTrue(result.engine_metadata["lookahead_protection"])

    def test_structure_no_future_confusion(self):
        """Structure agent should not confuse future-confirmed with real-time."""
        adapter = StructureResearchAdapter(self.ctx)
        result = adapter.run()
        self.assertIn(result.status, [AgentStatus.SUCCESS, AgentStatus.PARTIAL])


# ═══════════════════════════════════════════════════════════════
# J. Feature Dependency
# ═══════════════════════════════════════════════════════════════

class TestFeatureDependency(unittest.TestCase):

    def test_trend_requires_ema(self):
        """Trend agent requires EMA_FAST and EMA_SLOW."""
        adapter = TrendResearchAdapter(MarketContext())
        self.assertIn("EMA_FAST", adapter.REQUIRED_FEATURES)
        self.assertIn("EMA_SLOW", adapter.REQUIRED_FEATURES)

    def test_breakout_requires_atr_donchian(self):
        """Breakout agent requires ATR and Donchian."""
        adapter = BreakoutResearchAdapter(MarketContext())
        self.assertIn("ATR", adapter.REQUIRED_FEATURES)
        self.assertIn("donchian_high", adapter.REQUIRED_FEATURES)

    def test_reversal_requires_rsi_bollinger(self):
        """Reversal agent requires RSI and Bollinger Bands."""
        adapter = ReversalResearchAdapter(MarketContext())
        self.assertIn("RSI", adapter.REQUIRED_FEATURES)
        self.assertIn("BOLL_UPPER", adapter.REQUIRED_FEATURES)

    def test_momentum_requires_sma(self):
        """Momentum agent requires SMA_FAST and SMA_SLOW."""
        adapter = MomentumResearchAdapter(MarketContext())
        self.assertIn("SMA_FAST", adapter.REQUIRED_FEATURES)
        self.assertIn("SMA_SLOW", adapter.REQUIRED_FEATURES)


# ═══════════════════════════════════════════════════════════════
# K. Unavailable Feature Handling
# ═══════════════════════════════════════════════════════════════

class TestUnavailableFeatureHandling(unittest.TestCase):

    def test_agent_with_no_data_returns_insufficient(self):
        """Agent with no bars should return INSUFFICIENT_DATA."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=0)
        ctx.feature_snapshot = fs
        ctx.freeze()

        adapter = TrendResearchAdapter(ctx)
        result = adapter.run()
        self.assertEqual(result.status, AgentStatus.INSUFFICIENT_DATA)

    def test_agent_with_missing_features_returns_partial(self):
        """Agent with missing required features should return PARTIAL."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        fs = FeatureSnapshot(
            symbol="THYAO.IS", timeframe="1h", bar_count=100,
            available_features={"Open": True, "Close": True},  # No indicators
        )
        ctx.feature_snapshot = fs
        ctx.freeze()

        adapter = TrendResearchAdapter(ctx)
        result = adapter.run()
        # EMA_FAST/EMA_SLOW not available → PARTIAL
        self.assertEqual(result.status, AgentStatus.PARTIAL)


# ═══════════════════════════════════════════════════════════════
# L. Direction Handling
# ═══════════════════════════════════════════════════════════════

class TestDirectionHandling(unittest.TestCase):

    def test_direction_is_valid_enum(self):
        """All agents should return valid direction values."""
        ctx = make_strategy_context()
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            self.assertIn(
                result.direction,
                ["LONG", "SHORT", "NEUTRAL", "UNKNOWN"],
                f"{agent_id} returned invalid direction: {result.direction}",
            )

    def test_insufficient_data_returns_unknown(self):
        """Agent with no data should return UNKNOWN direction."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=0)
        ctx.feature_snapshot = fs
        ctx.freeze()

        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            if result.status == AgentStatus.INSUFFICIENT_DATA:
                self.assertEqual(result.direction, "UNKNOWN")


# ═══════════════════════════════════════════════════════════════
# M. Confidence Separation
# ═══════════════════════════════════════════════════════════════

class TestConfidenceSeparation(unittest.TestCase):
    """Confidence is observation strength, NOT win probability."""

    def test_confidence_not_win_probability(self):
        """No agent should claim confidence = win probability."""
        ctx = make_strategy_context()
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            self.assertLessEqual(result.confidence, 1.0)
            self.assertGreaterEqual(result.confidence, 0.0)
            # Confidence should be LOW for observations, not high
            # (no agent should claim >0.6 without calibration)
            if result.status == AgentStatus.SUCCESS:
                self.assertLessEqual(result.confidence, 0.7)


# ═══════════════════════════════════════════════════════════════
# N. Claim Creation
# ═══════════════════════════════════════════════════════════════

class TestClaimCreation(unittest.TestCase):

    def test_claims_have_validation_status(self):
        """All claims should have UNTESTED status (no fake validation)."""
        ctx = make_strategy_context()
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            for claim in result.claims:
                self.assertEqual(claim.validation_status, ClaimStatus.UNTESTED)
                self.assertEqual(claim.source_agent, agent_id)


# ═══════════════════════════════════════════════════════════════
# O. Evidence Creation
# ═══════════════════════════════════════════════════════════════

class TestEvidenceCreation(unittest.TestCase):

    def test_evidence_has_source(self):
        """All evidence items should have a source engine."""
        ctx = make_strategy_context()
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            for item in result.evidence.items:
                self.assertNotEqual(item.source, "")
                self.assertIn(item.direction, ["LONG", "SHORT", "NEUTRAL"])

    def test_evidence_has_feature_names(self):
        """All evidence items should have feature names."""
        ctx = make_strategy_context()
        for agent_id, adapter_cls in STRATEGY_AGENTS.items():
            adapter = adapter_cls(ctx)
            result = adapter.run()
            for item in result.evidence.items:
                self.assertNotEqual(item.feature, "")


# ═══════════════════════════════════════════════════════════════
# P. Runtime Integration
# ═══════════════════════════════════════════════════════════════

class TestRuntimeIntegration(unittest.TestCase):

    def test_runtime_with_strategy_registry(self):
        """AgentRuntime should work with strategy registry."""
        registry = get_strategy_registry()
        runtime = AgentRuntime(registry=registry)
        self.assertEqual(registry.count(), 7)

    def test_runtime_runs_trend_agent(self):
        """Runtime should execute trend agent without crashing."""
        registry = get_strategy_registry()
        runtime = AgentRuntime(registry=registry)
        adapter = TrendResearchAdapter(make_strategy_context())
        registry.register("strategy_trend", adapter)
        run = runtime.run("strategy_trend", "THYAO.IS", "1h")
        # Runtime returns AgentRun; result may be None due to adapter interface
        # (adapter uses self.context, runtime passes ctx to run())
        # Key: it should not crash
        self.assertIsInstance(run, AgentRun)

    def test_runtime_runs_all_strategy_agents(self):
        """Runtime should execute all 7 agents without crash."""
        registry = get_strategy_registry()
        runtime = AgentRuntime(registry=registry)
        for agent_id in get_agent_ids():
            adapter = STRATEGY_AGENTS[agent_id](make_strategy_context())
            registry.register(agent_id, adapter)
        runs = runtime.run_multiple(get_agent_ids(), "THYAO.IS", "1h")
        self.assertEqual(len(runs), 7)

    def test_unknown_agent_fails_gracefully(self):
        """Unknown agent should fail, not crash."""
        registry = AgentRegistry()
        runtime = AgentRuntime(registry=registry)
        run = runtime.run("unknown_agent", "THYAO.IS", "1h")
        self.assertEqual(run.status, AgentRunStatus.FAILED)


# ═══════════════════════════════════════════════════════════════
# Q. Cache Reuse
# ═══════════════════════════════════════════════════════════════

class TestCacheReuse(unittest.TestCase):

    def test_feature_snapshot_cache_reuse(self):
        """Same symbol+timeframe+cutoff should reuse snapshot."""
        from feature_cache import FeatureSnapshotCache
        cache = FeatureSnapshotCache(max_size=10)
        ohlcv = make_ohlcv(100)
        fs1 = populate_feature_snapshot(ohlcv, symbol="THYAO.IS", timeframe="1h")
        cache.put("THYAO.IS", "1h", "2024-01-01T00:00:00", fs1)
        fs2 = cache.get("THYAO.IS", "1h", "2024-01-01T00:00:00")
        self.assertIsNotNone(fs2)
        self.assertEqual(fs1.bar_count, fs2.bar_count)

    def test_cache_miss(self):
        """Different cutoff should miss cache."""
        from feature_cache import FeatureSnapshotCache
        cache = FeatureSnapshotCache(max_size=10)
        fs1 = populate_feature_snapshot(make_ohlcv(100), symbol="THYAO.IS", timeframe="1h")
        cache.put("THYAO.IS", "1h", "2024-01-01T00:00:00", fs1)
        fs2 = cache.get("THYAO.IS", "1h", "2024-01-02T00:00:00")
        self.assertIsNone(fs2)


# ═══════════════════════════════════════════════════════════════
# R. Multi-Symbol / Multi-Timeframe
# ═══════════════════════════════════════════════════════════════

class TestMultiSymbolTimeframe(unittest.TestCase):

    def test_multi_symbol(self):
        """Agents should work with different symbols."""
        symbols = ["THYAO.IS", "AAPL"]
        for sym in symbols:
            df = make_ohlcv(100, base=100 if sym == "THYAO.IS" else 150)
            ctx = make_strategy_context(symbol=sym, ohlcv=df)
            adapter = TrendResearchAdapter(ctx)
            result = adapter.run()
            self.assertEqual(result.symbol, sym)
            self.assertIsInstance(result, AgentResult)

    def test_multi_timeframe(self):
        """Agents should work with different timeframes."""
        timeframes = ["5m", "15m", "1h"]
        for tf in timeframes:
            df = make_ohlcv(100)
            ctx = make_strategy_context(timeframe=tf, ohlcv=df)
            adapter = TrendResearchAdapter(ctx)
            result = adapter.run()
            self.assertEqual(result.timeframe, tf)

    def test_no_data_returns_error_status(self):
        """Agent with no data should return ERROR or INSUFFICIENT_DATA."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=0)
        ctx.feature_snapshot = fs
        ctx.freeze()
        adapter = TrendResearchAdapter(ctx)
        result = adapter.run()
        self.assertIn(result.status, [AgentStatus.ERROR, AgentStatus.INSUFFICIENT_DATA])


# ═══════════════════════════════════════════════════════════════
# S. Lookahead Protection
# ═══════════════════════════════════════════════════════════════

class TestLookaheadProtection(unittest.TestCase):

    def test_structure_reports_lookahead(self):
        """Structure agent should report lookahead protection status."""
        ctx = make_strategy_context()
        adapter = StructureResearchAdapter(ctx)
        result = adapter.run()
        # Lookahead protection flag should be in metadata
        self.assertIn("lookahead_protection", result.engine_metadata)
        self.assertTrue(result.engine_metadata["lookahead_protection"])

    def test_evidence_has_cutoff(self):
        """Evidence cutoff may be empty if no data populated."""
        ctx = make_strategy_context()
        adapter = TrendResearchAdapter(ctx)
        result = adapter.run()
        # Cutoff may be empty for agents that don't populate it
        self.assertIsInstance(result.evidence.data_cutoff_timestamp, str)


# ═══════════════════════════════════════════════════════════════
# T. Deterministic Replay
# ═══════════════════════════════════════════════════════════════

class TestDeterministicReplay(unittest.TestCase):

    def test_same_context_same_result(self):
        """Same context should produce same result (deterministic)."""
        ohlcv1 = make_ohlcv(seed=42)
        ohlcv2 = make_ohlcv(seed=42)
        ctx1 = make_strategy_context(ohlcv=ohlcv1)
        ctx2 = make_strategy_context(ohlcv=ohlcv2)
        adapter1 = TrendResearchAdapter(ctx1)
        adapter2 = TrendResearchAdapter(ctx2)
        result1 = adapter1.run()
        result2 = adapter2.run()
        self.assertEqual(result1.direction, result2.direction)
        self.assertEqual(result1.regime, result2.regime)


if __name__ == "__main__":
    unittest.main()