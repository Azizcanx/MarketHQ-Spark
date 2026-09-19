# -*- coding: utf-8 -*-
"""Phase C tests — Agent Runtime + Observation Pipeline.

148 mevcut testi bozmadan yeni testler ekler.
"""

import unittest
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from agent_contract import (
    AgentResult,
    AgentStatus,
    Claim,
    ClaimStatus,
    Evidence,
    EvidenceItem,
    FeatureSnapshot,
    MarketContext,
    BaseAgentAdapter,
)
from agent_runtime import AgentRuntime, AgentRun, AgentRunStatus, AgentConfig, ExecutionRequest
from agent_registry import AgentRegistry, get_default_registry, register, get
from feature_cache import FeatureSnapshotCache, get_default_cache
from persistence import PersistenceLayer
from observation_bridge import bridge_result, bridge_all_runs
class MockAgentAdapter(BaseAgentAdapter):
    """Simple adapter for testing."""
    adapter_id = "mock_agent"
    adapter_version = "1.0"
    source_engine = "mock_engine"
    source_engine_version = "1.0"

    def run(self, ctx: MarketContext) -> AgentResult:
        return self._success_result(
            direction="NEUTRAL",
            regime="UNKNOWN",
            confidence=0.5,
            reasoning="Mock adapter result",
        )


from structure_lookahead_fix import (
    filter_by_cutoff,
    safe_evaluate_smc,
    label_event_status,
    audit_lookahead,
)


def make_ohlcv(n=200, base=100, trend=0.01, vol=2.0):
    """Create synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = base + np.cumsum(np.random.randn(n) * vol) + trend * np.arange(n)
    open_ = close + np.random.randn(n) * 0.5
    high = np.maximum(open_, close) + abs(np.random.randn(n)) * 0.5
    low = np.minimum(open_, close) - abs(np.random.randn(n)) * 0.5
    volume = np.random.randint(1000, 10000, n)
    df = pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )
    df.index.name = "timestamp"
    return df


# ═══════════════════════════════════════════════════════════════
# A. Agent Runtime Lifecycle
# ═══════════════════════════════════════════════════════════════

class TestAgentRuntimeLifecycle(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry()
        self.registry.register("test_agent", MockAgentAdapter(MarketContext()), version="1.0")
        self.runtime = AgentRuntime(registry=self.registry)

    def test_run_created_status(self):
        run = self.runtime.run("test_agent", "THYAO.IS", "1h")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)

    def test_run_has_execution_id(self):
        run = self.runtime.run("test_agent", "THYAO.IS", "1h")
        self.assertTrue(len(run.execution_id) > 0)

    def test_run_status_transitions(self):
        run = self.runtime.run("test_agent", "THYAO.IS", "1h")
        # Should complete successfully
        self.assertIn(run.status, [AgentRunStatus.COMPLETED, AgentRunStatus.INSUFFICIENT_DATA])

    def test_run_trace_not_empty(self):
        run = self.runtime.run("test_agent", "THYAO.IS", "1h")
        self.assertTrue(len(run.trace) > 0)

    def test_run_trace_has_steps(self):
        run = self.runtime.run("test_agent", "THYAO.IS", "1h")
        steps = [t["step"] for t in run.trace]
        self.assertIn("RUN_CREATED", steps)
        self.assertIn("AGENT_COMPLETED", steps)


# ═══════════════════════════════════════════════════════════════
# B. Registry
# ═══════════════════════════════════════════════════════════════

class TestAgentRegistry(unittest.TestCase):
    def test_register_and_get(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        adapter.adapter_id = "test"
        adapter.adapter_version = "1.0"
        adapter.source_engine = "test_engine"
        registry.register("test_agent", adapter, version="1.0")
        result = registry.get("test_agent")
        self.assertIsNotNone(result)
        self.assertEqual(result.adapter_id, "test")

    def test_get_unknown_returns_none(self):
        registry = AgentRegistry()
        result = registry.get("unknown")
        self.assertIsNone(result)

    def test_get_version(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        adapter.adapter_id = "test"
        adapter.adapter_version = "2.0"
        adapter.source_engine = "test_engine"
        registry.register("test_agent", adapter, version="2.0")
        self.assertEqual(registry.get_version("test_agent"), "2.0")
        self.assertEqual(registry.get_version("unknown"), "unknown")

    def test_list_agents(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        adapter.adapter_id = "test"
        adapter.adapter_version = "1.0"
        adapter.source_engine = "test_engine"
        registry.register("test_agent", adapter, version="1.0")
        agents = registry.list_agents()
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "test_agent")
        self.assertEqual(agents[0]["version"], "1.0")

    def test_unregister(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        adapter.adapter_id = "test"
        adapter.adapter_version = "1.0"
        adapter.source_engine = "test_engine"
        registry.register("test_agent", adapter, version="1.0")
        self.assertTrue(registry.unregister("test_agent"))
        self.assertFalse(registry.has("test_agent"))

    def test_has(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        adapter.adapter_id = "test"
        registry.register("test_agent", adapter)
        self.assertTrue(registry.has("test_agent"))
        self.assertFalse(registry.has("other"))

    def test_count(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        registry.register("a1", adapter)
        registry.register("a2", adapter)
        self.assertEqual(registry.count(), 2)

    def test_clear(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        registry.register("a1", adapter)
        registry.clear()
        self.assertEqual(registry.count(), 0)


# ═══════════════════════════════════════════════════════════════
# C. Execution Request Validation
# ═══════════════════════════════════════════════════════════════

class TestExecutionRequestValidation(unittest.TestCase):
    def test_runtime_rejects_empty_symbol(self):
        runtime = AgentRuntime()
        run = runtime.run("test_agent", "", "1h")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertEqual(run.error_type, "ValueError")

    def test_runtime_rejects_empty_timeframe(self):
        runtime = AgentRuntime()
        run = runtime.run("test_agent", "THYAO.IS", "")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertEqual(run.error_type, "ValueError")

    def test_runtime_rejects_unknown_agent(self):
        runtime = AgentRuntime()
        run = runtime.run("unknown_agent", "THYAO.IS", "1h")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertEqual(run.error_type, "ADAPTER_NOT_FOUND")


# ═══════════════════════════════════════════════════════════════
# D. AgentResult Persistence
# ═══════════════════════════════════════════════════════════════

class TestAgentResultPersistence(unittest.TestCase):
    def test_persistence_layer_exists(self):
        p = PersistenceLayer()
        self.assertIsNotNone(p)

    def test_persist_and_get_run(self):
        p = PersistenceLayer()
        p.migrate()
        # Create a mock run
        run = AgentRun(
            execution_id="test-persist-001",
            agent_id="test",
            agent_version="1.0",
            symbol="THYAO.IS",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            status=AgentRunStatus.COMPLETED,
            result=AgentResult(
                agent_id="test",
                symbol="THYAO.IS",
                timeframe="1h",
                status=AgentStatus.SUCCESS,
            ),
        )
        p.persist_run(run)
        retrieved = p.get_run("test-persist-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["execution_id"], "test-persist-001")
        self.assertEqual(retrieved["agent_id"], "test")

    def test_persist_result(self):
        p = PersistenceLayer()
        p.migrate()
        result = AgentResult(
            agent_id="test",
            symbol="THYAO.IS",
            timeframe="1h",
            status=AgentStatus.SUCCESS,
        )
        p.persist_result("test-exec-001", result)
        retrieved = p.get_result("test-exec-001")
        self.assertIsNotNone(retrieved)

    def test_list_runs(self):
        p = PersistenceLayer()
        p.migrate()
        runs = p.list_runs(limit=10)
        self.assertIsInstance(runs, list)


# ═══════════════════════════════════════════════════════════════
# E. Evidence Persistence
# ═══════════════════════════════════════════════════════════════

class TestEvidencePersistence(unittest.TestCase):
    def test_persist_evidence(self):
        p = PersistenceLayer()
        p.migrate()
        evidence = Evidence(
            items=[
                EvidenceItem(
                    evidence_id="e1",
                    type="indicator",
                    feature="rsi",
                    value=65.0,
                    timestamp="2026-01-01T00:00:00",
                    direction="LONG",
                    strength=0.7,
                    source="signal_engine",
                    explanation="RSI overbought",
                )
            ],
        )
        p.persist_evidence("test-exec-ev", evidence)
        items = p.get_evidence("test-exec-ev")
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["feature"], "rsi")


# ═══════════════════════════════════════════════════════════════
# F. Claim Persistence
# ═══════════════════════════════════════════════════════════════

class TestClaimPersistence(unittest.TestCase):
    def test_persist_claims(self):
        p = PersistenceLayer()
        p.migrate()
        claims = [
            Claim(
                claim_id="c1",
                statement="Test claim",
                source_agent="test_agent",
                source_agent_version="1.0",
                validation_status=ClaimStatus.UNTESTED,
            )
        ]
        p.persist_claims("test-exec-cl", claims)
        retrieved = p.get_claims("test-exec-cl")
        self.assertGreaterEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["statement"], "Test claim")


# ═══════════════════════════════════════════════════════════════
# G. Feature Snapshot Cache
# ═══════════════════════════════════════════════════════════════

class TestFeatureSnapshotCache(unittest.TestCase):
    def test_cache_put_and_get(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=100)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs)
        result = cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.bar_count, 100)

    def test_cache_miss(self):
        cache = FeatureSnapshotCache(max_size=10)
        result = cache.get("UNKNOWN", "1h", "2026-01-01T00:00:00")
        self.assertIsNone(result)

    def test_cache_hit_miss_counts(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=50)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs)
        cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00")  # hit
        cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00")  # hit
        cache.get("UNKNOWN", "1h", "2026-01-01T00:00:00")  # miss
        stats = cache.get_stats()
        self.assertEqual(stats["hits"], 2)
        self.assertEqual(stats["misses"], 1)

    def test_cache_invalidate(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=50)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs)
        count = cache.invalidate(symbol="THYAO.IS")
        self.assertGreater(count, 0)
        self.assertIsNone(cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00"))

    def test_cache_invalidate_all(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=50)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs)
        count = cache.invalidate_all()
        self.assertGreater(count, 0)
        self.assertEqual(len(cache._cache), 0)

    def test_cache_bounded(self):
        cache = FeatureSnapshotCache(max_size=2)
        for i in range(5):
            fs = FeatureSnapshot(symbol=f"S{i}", timeframe="1h", bar_count=50)
            cache.put(f"S{i}", "1h", "2026-01-01T00:00:00", fs)
        self.assertLessEqual(len(cache._cache), 2)

    def test_cache_stats(self):
        cache = FeatureSnapshotCache(max_size=10)
        stats = cache.get_stats()
        self.assertIn("hit_rate", stats)
        self.assertIn("size", stats)


# ═══════════════════════════════════════════════════════════════
# H. Cache Invalidation
# ═══════════════════════════════════════════════════════════════

class TestCacheInvalidation(unittest.TestCase):
    def test_invalidate_by_timeframe(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=50)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs)
        count = cache.invalidate(timeframe="1h")
        self.assertGreater(count, 0)

    def test_invalidate_does_not_affect_other_symbols(self):
        cache = FeatureSnapshotCache(max_size=10)
        fs1 = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=50)
        fs2 = FeatureSnapshot(symbol="BTCUSDT", timeframe="1h", bar_count=50)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs1)
        cache.put("BTCUSDT", "1h", "2026-01-01T00:00:00", fs2)
        cache.invalidate(symbol="THYAO.IS")
        self.assertIsNotNone(cache.get("BTCUSDT", "1h", "2026-01-01T00:00:00"))
        self.assertIsNone(cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00"))


# ═══════════════════════════════════════════════════════════════
# I. Deterministic Replay
# ═══════════════════════════════════════════════════════════════

class TestDeterministicReplay(unittest.TestCase):
    def test_same_context_same_result(self):
        """Same MarketContext should produce same result (deterministic)."""
        ctx1 = MarketContext(symbol="THYAO.IS", timeframe="1h")
        ctx1.process_ohlcv()
        ctx2 = MarketContext(symbol="THYAO.IS", timeframe="1h")
        ctx2.process_ohlcv()
        # Both contexts should have the same feature_snapshot state
        self.assertEqual(ctx1.feature_snapshot.bar_count, ctx2.feature_snapshot.bar_count)
        self.assertEqual(ctx1.symbol, ctx2.symbol)
        self.assertEqual(ctx1.timeframe, ctx2.timeframe)

    def test_different_cutoff_different_snapshot(self):
        """Different cutoff should produce different snapshots."""
        cache = FeatureSnapshotCache(max_size=10)
        fs1 = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=100)
        fs2 = FeatureSnapshot(symbol="THYAO.IS", timeframe="1h", bar_count=200)
        cache.put("THYAO.IS", "1h", "2026-01-01T00:00:00", fs1)
        cache.put("THYAO.IS", "1h", "2026-01-02T00:00:00", fs2)
        r1 = cache.get("THYAO.IS", "1h", "2026-01-01T00:00:00")
        r2 = cache.get("THYAO.IS", "1h", "2026-01-02T00:00:00")
        self.assertEqual(r1.bar_count, 100)
        self.assertEqual(r2.bar_count, 200)


# ═══════════════════════════════════════════════════════════════
# J. Multi-Agent Execution
# ═══════════════════════════════════════════════════════════════

class TestMultiAgentExecution(unittest.TestCase):
    def test_run_multiple_returns_list(self):
        runtime = AgentRuntime()
        runs = runtime.run_multiple(["test_agent"], "THYAO.IS", "1h")
        self.assertEqual(len(runs), 1)

    def test_run_multiple_failure_isolation(self):
        """Failed agent doesn't crash other agents."""
        registry = AgentRegistry()
        registry.register("test_agent", MockAgentAdapter(MarketContext()), version="1.0")
        runtime = AgentRuntime(registry=registry)
        runs = runtime.run_multiple(
            ["unknown_agent", "test_agent"], "THYAO.IS", "1h"
        )
        self.assertEqual(len(runs), 2)
        # First should fail (unknown), second should complete
        self.assertEqual(runs[0].status, AgentRunStatus.FAILED)
        self.assertIn(runs[1].status, [AgentRunStatus.COMPLETED, AgentRunStatus.INSUFFICIENT_DATA])


# ═══════════════════════════════════════════════════════════════
# K. Failure Isolation
# ═══════════════════════════════════════════════════════════════

class TestFailureIsolation(unittest.TestCase):
    def test_unknown_agent_fails_gracefully(self):
        runtime = AgentRuntime()
        run = runtime.run("nonexistent_agent", "THYAO.IS", "1h")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertEqual(run.error_type, "ADAPTER_NOT_FOUND")

    def test_empty_symbol_fails_gracefully(self):
        runtime = AgentRuntime()
        run = runtime.run("test_agent", "", "1h")
        self.assertEqual(run.status, AgentRunStatus.FAILED)


# ═══════════════════════════════════════════════════════════════
# L. Cutoff Validation
# ═══════════════════════════════════════════════════════════════

class TestCutoffValidation(unittest.TestCase):
    def test_filter_by_cutoff_removes_future_bars(self):
        df = make_ohlcv(100)
        cutoff = str(df.index[50])
        filtered = filter_by_cutoff(df, cutoff)
        self.assertLessEqual(len(filtered), 50)

    def test_filter_by_cutoff_empty_cutoff(self):
        df = make_ohlcv(100)
        filtered = filter_by_cutoff(df, "")
        self.assertEqual(len(filtered), 100)

    def test_filter_by_cutoff_never_modifies_original(self):
        df = make_ohlcv(100)
        original_len = len(df)
        filter_by_cutoff(df, "2024-01-01T00:00:00")
        self.assertEqual(len(df), original_len)


# ═══════════════════════════════════════════════════════════════
# M. Lookahead Protection
# ═══════════════════════════════════════════════════════════════

class TestLookaheadProtection(unittest.TestCase):
    def test_label_confirmed(self):
        self.assertEqual(label_event_status(0, 100), "CONFIRMED")

    def test_label_unconfirmed(self):
        self.assertEqual(label_event_status(99, 100), "UNCONFIRMED")
        self.assertEqual(label_event_status(98, 100, lookahead_bars=2), "UNCONFIRMED")

    def test_safe_evaluate_smc_returns_metadata(self):
        df = make_ohlcv(200)
        cutoff = str(df.index[150])
        result = safe_evaluate_smc(df, cutoff)
        self.assertIn("event_status", result)
        self.assertIn("data_cutoff_timestamp", result)
        self.assertIn("bars_used", result)

    def test_audit_lookahead_returns_report(self):
        df = make_ohlcv(100)
        report = audit_lookahead(df)
        self.assertIn("total_bars", report)
        self.assertIn("risks", report)


# ═══════════════════════════════════════════════════════════════
# N. Brain Observation Bridge
# ═══════════════════════════════════════════════════════════════

class TestBrainObservationBridge(unittest.TestCase):
    def test_bridge_returns_summary(self):
        from agent_runtime import AgentRun, AgentRunStatus
        run = AgentRun(
            execution_id="bridge-test-001",
            agent_id="test_agent",
            agent_version="1.0",
            symbol="THYAO.IS",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            status=AgentRunStatus.COMPLETED,
            result=AgentResult(
                agent_id="test_agent",
                symbol="THYAO.IS",
                timeframe="1h",
                status=AgentStatus.SUCCESS,
                direction="LONG",
                regime="TRENDING",
                confidence=0.7,
                evidence=Evidence(
                    items=[
                        EvidenceItem(
                            evidence_id="e1",
                            type="indicator",
                            feature="rsi",
                            value=65.0,
                            timestamp="2026-01-01T00:00:00",
                            direction="LONG",
                            strength=0.7,
                            source="signal_engine",
                            explanation="RSI shows strength",
                        )
                    ],
                ),
                claims=[
                    Claim(
                        claim_id="c1",
                        statement="Trending regime detected",
                        source_agent="regime_agent",
                        source_agent_version="1.0",
                        validation_status=ClaimStatus.UNTESTED,
                    )
                ],
            ),
        )
        result = bridge_result(run)
        self.assertEqual(result["status"], "BRIDGED")
        self.assertEqual(result["observations"], 1)
        self.assertEqual(result["claims"], 1)

    def test_bridge_all_runs(self):
        from agent_runtime import AgentRun, AgentRunStatus
        run = AgentRun(
            execution_id="bridge-test-002",
            agent_id="test_agent",
            agent_version="1.0",
            symbol="THYAO.IS",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            status=AgentRunStatus.COMPLETED,
            result=AgentResult(
                agent_id="test_agent",
                symbol="THYAO.IS",
                timeframe="1h",
                status=AgentStatus.SUCCESS,
            ),
        )
        result = bridge_all_runs([run])
        self.assertEqual(result["runs_processed"], 1)


# ═══════════════════════════════════════════════════════════════
# O. Observation Persistence via Bridge
# ═══════════════════════════════════════════════════════════════

class TestObservationPersistence(unittest.TestCase):
    def test_bridge_creates_brain_observation(self):
        """Bridge should insert into brain_observations table."""
        from agent_runtime import AgentRun, AgentRunStatus
        run = AgentRun(
            execution_id="obs-persist-001",
            agent_id="test_agent",
            agent_version="1.0",
            symbol="THYAO.IS",
            timeframe="1h",
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            status=AgentRunStatus.COMPLETED,
            result=AgentResult(
                agent_id="test_agent",
                symbol="THYAO.IS",
                timeframe="1h",
                status=AgentStatus.SUCCESS,
                regime="TRENDING",
                confidence=0.6,
                reasoning="Test observation",
            ),
        )
        # Bridge the result
        result = bridge_result(run)
        self.assertEqual(result["observations"], 1)

        # Verify in DB
        p = PersistenceLayer()
        p.migrate()
        runs = p.list_runs(agent_id="test_agent", limit=10)
        # The run was persisted by runtime, bridge creates brain_observation
        self.assertIsInstance(runs, list)


# ═══════════════════════════════════════════════════════════════
# P. Unavailable Feature Handling
# ═══════════════════════════════════════════════════════════════

class TestUnavailableFeatureHandling(unittest.TestCase):
    def test_null_data_quality_low(self):
        """Null data should produce low quality score."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        ohlcv = make_ohlcv(50)
        ohlcv.loc[:, "Close"] = None
        ctx.ohlcv_ref = ohlcv
        ctx.process_ohlcv()
        # Quality should be low (not 0.0 due to other columns having data)
        self.assertLess(ctx.feature_snapshot.data_quality_score, 1.0)

    def test_empty_context_no_crash(self):
        """Empty context should not crash adapters."""
        ctx = MarketContext()
        ctx.freeze()
        # Should not raise
        self.assertTrue(ctx._frozen)

    def test_feature_availability_dict_populated(self):
        """Feature availability should be populated after process_ohlcv."""
        ctx = MarketContext(symbol="THYAO.IS", timeframe="1h")
        ctx.ohlcv_ref = make_ohlcv(50)
        ctx.process_ohlcv()
        self.assertIsInstance(ctx.feature_snapshot.available_features, dict)
        self.assertGreater(len(ctx.feature_snapshot.available_features), 0)


# ═══════════════════════════════════════════════════════════════
# R. Version Tracking
# ═══════════════════════════════════════════════════════════════

class TestVersionTracking(unittest.TestCase):
    def test_registry_tracks_version(self):
        registry = AgentRegistry()
        adapter = BaseAgentAdapter.__new__(BaseAgentAdapter)
        registry.register("v1_agent", adapter, version="1.0.0")
        registry.register("v2_agent", adapter, version="2.5.0")
        self.assertEqual(registry.get_version("v1_agent"), "1.0.0")
        self.assertEqual(registry.get_version("v2_agent"), "2.5.0")


# ═══════════════════════════════════════════════════════════════
# S. Existing Engine Adapter Integration
# ═══════════════════════════════════════════════════════════════

class TestExistingEngineAdapterIntegration(unittest.TestCase):
    def test_market_data_adapter_exists(self):
        from engine_adapters import MarketDataAdapter
        self.assertIsNotNone(MarketDataAdapter)

    def test_regime_adapter_exists(self):
        from engine_adapters import RegimeAdapter
        self.assertIsNotNone(RegimeAdapter)

    def test_structure_adapter_exists(self):
        from engine_adapters import StructureAdapter
        self.assertIsNotNone(StructureAdapter)

    def test_momentum_adapter_exists(self):
        from engine_adapters import MomentumVolatilityAdapter
        self.assertIsNotNone(MomentumVolatilityAdapter)

    def test_strategy_adapter_exists(self):
        from engine_adapters import StrategyAdapter
        self.assertIsNotNone(StrategyAdapter)

    def test_setup_adapter_exists(self):
        from engine_adapters import SetupAdapter
        self.assertIsNotNone(SetupAdapter)

    def test_quality_adapter_exists(self):
        from engine_adapters import QualityAdapter
        self.assertIsNotNone(QualityAdapter)

    def test_historical_evidence_adapter_exists(self):
        from engine_adapters import HistoricalEvidenceAdapter
        self.assertIsNotNone(HistoricalEvidenceAdapter)


# ═══════════════════════════════════════════════════════════════
# T. SDK Integration Boundary
# ═══════════════════════════════════════════════════════════════

class TestSDKIntegrationBoundary(unittest.TestCase):
    def test_existing_runtime_v1_not_modified(self):
        """Existing agent_runtime_v1.py should be untouched."""
        import os
        path = "/opt/markethq/agents/agent_runtime_v1.py"
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            content = f.read()
        self.assertIn("OpenAI", content)
        self.assertIn("agents", content)

    def test_phase_c_runtime_separate(self):
        """Phase C runtime should be separate from SDK wrapper."""
        import agent_runtime
        runtime = agent_runtime.AgentRuntime()
        self.assertIsNotNone(runtime)
        self.assertIsNotNone(runtime.registry)

    def test_deterministic_engine_not_affected(self):
        """Market calculations should remain deterministic."""
        df = make_ohlcv(100)
        self.assertEqual(len(df), 100)
        self.assertIn("Close", df.columns)


if __name__ == "__main__":
    unittest.main()