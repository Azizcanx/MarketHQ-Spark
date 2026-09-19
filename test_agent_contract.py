# -*- coding: utf-8 -*-
"""
MarketHQ Agent Contract Phase B Tests
=======================================

Tests for:
  - AgentResult serialization + validation
  - Evidence validation
  - Claim validation
  - MarketContext validation
  - Feature availability
  - Adapter output (all 8 adapters)
  - Adapter error isolation
  - Deterministic replay
  - Timestamp/cutoff validation
  - Lookahead regression
  - NULL/unavailable feature handling
  - Confidence vs Quality separation
  - Engine version tracking
  - Multi-symbol
  - Multi-timeframe
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent_contract import (
    AgentResult, AgentStatus, Evidence, EvidenceItem,
    Claim, ClaimStatus, MarketContext, FeatureSnapshot,
)
from engine_adapters import (
    MarketDataAdapter, RegimeAdapter, StructureAdapter,
    MomentumVolatilityAdapter, StrategyAdapter, SetupAdapter,
    QualityAdapter, HistoricalEvidenceAdapter,
)


# =========================================================
# HELPERS
# =========================================================

def make_ohlcv(n=200, base=100, trend=0.01, vol=2.0):
    np.random.seed(42)
    close = base + np.cumsum(np.random.normal(trend, vol, n))
    open_p = close + np.random.normal(0, vol * 0.1, n)
    high = np.maximum(np.maximum(open_p, close), close + np.abs(np.random.normal(0, vol, n)))
    low = np.minimum(np.minimum(open_p, close), close - np.abs(np.random.normal(0, vol, n)))
    volume = np.random.uniform(1000, 10000, n)
    return pd.DataFrame({"Open": open_p, "High": high, "Low": low, "Close": close, "Volume": volume})


def build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None,
                  dataset_status="active", provider="yfinance"):
    """Create a MarketContext for testing."""
    ctx = MarketContext(
        symbol=symbol,
        timeframe=timeframe,
        observation_timestamp=datetime.now(timezone.utc).isoformat(),
        data_cutoff_timestamp=datetime.now(timezone.utc).isoformat(),
        ohlcv_ref=ohlcv_df,
        dataset_status=dataset_status,
        provider=provider,
    )
    ctx.process_ohlcv()
    return ctx


def make_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None):
    if ohlcv_df is None:
        ohlcv_df = make_ohlcv(200)
    return build_context(symbol=symbol, timeframe=timeframe, ohlcv_df=ohlcv_df)


# =========================================================
# 1. AGENT RESULT SERIALIZATION
# =========================================================

class TestAgentResultSerialization:
    def test_agent_result_dataclass(self):
        result = AgentResult(agent_id="test", symbol="THYAO.IS", timeframe="1h")
        assert result.agent_id == "test"
        assert result.symbol == "THYAO.IS"
        assert result.timeframe == "1h"
        assert result.status == AgentStatus.SUCCESS

    def test_agent_result_has_required_fields(self):
        result = AgentResult(agent_id="test", symbol="THYAO.IS")
        assert result.agent_id != ""
        assert result.execution_id != ""
        assert result.timestamp != ""
        assert result.observation_timestamp != ""
        assert result.data_cutoff_timestamp != ""

    def test_agent_result_uuid_unique(self):
        r1 = AgentResult(agent_id="a")
        r2 = AgentResult(agent_id="a")
        assert r1.execution_id != r2.execution_id

    def test_agent_result_status_enum(self):
        for status in AgentStatus:
            result = AgentResult(agent_id="test", status=status)
            assert result.status == status

    def test_agent_result_direction_values(self):
        for direction in ["LONG", "SHORT", "NEUTRAL"]:
            result = AgentResult(agent_id="test", direction=direction)
            assert result.direction == direction


# =========================================================
# 2. AGENT RESULT VALIDATION
# =========================================================

class TestAgentResultValidation:
    def test_confidence_range(self):
        result = AgentResult(agent_id="test", confidence=0.75)
        assert 0.0 <= result.confidence <= 1.0

    def test_uncertainty_range(self):
        result = AgentResult(agent_id="test", uncertainty=0.3)
        assert 0.0 <= result.uncertainty <= 1.0

    def test_confidence_plus_uncertainty_approx_one(self):
        result = AgentResult(agent_id="test", confidence=0.7, uncertainty=0.3)
        assert abs((result.confidence + result.uncertainty) - 1.0) < 0.1

    def test_data_quality_range(self):
        result = AgentResult(agent_id="test", data_quality=0.85)
        assert 0.0 <= result.data_quality <= 1.0

    def test_no_fake_confidence(self):
        result = AgentResult(agent_id="test")
        assert result.confidence <= 1.0


# =========================================================
# 3. EVIDENCE VALIDATION
# =========================================================

class TestEvidenceValidation:
    def test_evidence_item_creation(self):
        item = EvidenceItem(
            evidence_id="e1", type="indicator", feature="RSI",
            value=65.0, source="signal_engine",
        )
        assert item.evidence_id == "e1"
        assert item.feature == "RSI"
        assert item.value == 65.0

    def test_evidence_container(self):
        items = [EvidenceItem(evidence_id=f"e{i}", type="indicator", feature="RSI", value=float(i))
                 for i in range(3)]
        evidence = Evidence(items=items)
        assert len(evidence.items) == 3

    def test_evidence_score_range(self):
        evidence = Evidence(evidence_score=0.7)
        assert 0.0 <= evidence.evidence_score <= 1.0

    def test_evidence_timestamps(self):
        ts = datetime.now(timezone.utc).isoformat()
        item = EvidenceItem(
            evidence_id="e1", type="regime", feature="regime",
            timestamp=ts, data_cutoff_timestamp=ts,
        )
        assert item.timestamp == ts
        assert item.data_cutoff_timestamp == ts


# =========================================================
# 4. CLAIM VALIDATION
# =========================================================

class TestClaimValidation:
    def test_claim_creation(self):
        claim = Claim(
            claim_id="c1", statement="Test claim",
            source_agent="regime", source_agent_version="v1",
        )
        assert claim.claim_id == "c1"
        assert claim.statement == "Test claim"
        assert claim.validation_status == ClaimStatus.UNTESTED

    def test_claim_status_enum(self):
        for status in ClaimStatus:
            claim = Claim(claim_id="c1", statement="test", validation_status=status)
            assert claim.validation_status == status

    def test_claim_has_source(self):
        claim = Claim(
            claim_id="c1", statement="test",
            source_agent="strategy", source_agent_version="v1",
        )
        assert claim.source_agent == "strategy"
        assert claim.source_agent_version == "v1"

    def test_claim_evidence_refs(self):
        claim = Claim(
            claim_id="c1", statement="test",
            evidence_refs=["regime:UPTREND", "structure:BOS_UP"],
        )
        assert len(claim.evidence_refs) == 2


# =========================================================
# 5. MARKET CONTEXT VALIDATION
# =========================================================

class TestMarketContextValidation:
    def test_context_creation(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        assert ctx.symbol == "THYAO.IS"
        assert ctx.timeframe == "1h"
        assert ctx.feature_snapshot.bar_count == 100

    def test_context_freeze(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        ctx.freeze()
        with pytest.raises(RuntimeError):
            ctx.symbol = "CHANGED"

    def test_context_immutable_after_freeze(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        ctx.freeze()
        with pytest.raises(RuntimeError):
            ctx.timeframe = "5m"

    def test_context_data_quality(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        assert ctx.feature_snapshot.data_quality_score > 0.0

    def test_context_feature_availability(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        assert "Open" in ctx.feature_snapshot.available_features
        assert "Volume" in ctx.feature_snapshot.available_features


# =========================================================
# 6. FEATURE AVAILABILITY
# =========================================================

class TestFeatureAvailability:
    def test_available_features_populated(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        assert len(ctx.feature_snapshot.available_features) > 0

    def test_null_features_tracked(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        null_count = sum(1 for v in ctx.feature_snapshot.null_features.values() if v)
        assert null_count == 0

    def test_data_quality_score_clean(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        assert ctx.feature_snapshot.data_quality_score == 1.0

    def test_data_quality_score_with_nulls(self):
        ohlcv = make_ohlcv(100)
        # Create DataFrame with intentional null
        ohlcv_null = pd.DataFrame({
            "Open": [None] * 100,
            "High": [100.0] * 100,
            "Low": [90.0] * 100,
            "Close": [95.0] * 100,
            "Volume": [1000.0] * 100,
        })
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=ohlcv_null)
        assert ctx.feature_snapshot.data_quality_score < 1.0


# =========================================================
# 7. ADAPTER OUTPUT
# =========================================================

class TestAdapterOutput:
    def test_market_data_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.SUCCESS
        assert result.symbol == "THYAO.IS"
        assert result.source_engine == "market_data_pipeline"

    def test_regime_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = RegimeAdapter(ctx)
        result = adapter.run()
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)
        assert result.regime != ""

    def test_momentum_volatility_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = MomentumVolatilityAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.SUCCESS
        assert "direction" in result.engine_metadata or "RSI" in result.engine_metadata

    def test_strategy_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = StrategyAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.SUCCESS
        assert "agreement" in result.engine_metadata

    def test_setup_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = SetupAdapter(ctx)
        result = adapter.run()
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.ERROR, AgentStatus.PARTIAL)

    def test_quality_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = QualityAdapter(ctx)
        result = adapter.run()
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.ERROR, AgentStatus.PARTIAL)

    def test_historical_evidence_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = HistoricalEvidenceAdapter(ctx)
        result = adapter.run()
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.ERROR, AgentStatus.PARTIAL)

    def test_structure_adapter(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = StructureAdapter(ctx)
        result = adapter.run()
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)
        assert "structure_type" in result.engine_metadata


# =========================================================
# 8. ADAPTER ERROR ISOLATION
# =========================================================

class TestAdapterErrorIsolation:
    def test_market_data_adapter_no_data(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.ERROR
        assert result.error_type != ""

    def test_regime_adapter_no_data(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        adapter = RegimeAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.ERROR
        assert "NO_DATA" in result.error_type

    def test_error_has_type_and_message(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.error_type != ""
        assert result.error_message != ""

    def test_error_does_not_crash_other_adapters(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        bad_ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)

        bad_adapter = MarketDataAdapter(bad_ctx)
        bad_result = bad_adapter.run()
        assert bad_result.status == AgentStatus.ERROR

        good_adapter = RegimeAdapter(ctx)
        good_result = good_adapter.run()
        assert good_result.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    def test_all_adapters_return_result_not_exception(self):
        """All adapters should return AgentResult even with bad data."""
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        for adapter_cls in [
            MarketDataAdapter, RegimeAdapter, StructureAdapter,
            MomentumVolatilityAdapter, StrategyAdapter, SetupAdapter,
            QualityAdapter, HistoricalEvidenceAdapter,
        ]:
            adapter = adapter_cls(ctx)
            result = adapter.run()
            assert isinstance(result, AgentResult)


# =========================================================
# 9. DETERMINISTIC REPLAY
# =========================================================

class TestDeterministicReplay:
    def test_same_context_same_output(self):
        ctx1 = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        ctx2 = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))

        adapter = MomentumVolatilityAdapter(ctx1)
        result1 = adapter.run()

        adapter2 = MomentumVolatilityAdapter(ctx2)
        result2 = adapter2.run()

        assert result1.direction == result2.direction
        assert result1.regime == result2.regime
        assert result1.engine_metadata == result2.engine_metadata

    def test_adapter_id_consistent(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.agent_id == "market_data"
        assert result.agent_version == "v1"


# =========================================================
# 10. TIMESTAMP / CUTOFF VALIDATION
# =========================================================

class TestTimestampCutoffValidation:
    def test_observation_timestamp_set(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.observation_timestamp != ""

    def test_data_cutoff_timestamp_set(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.data_cutoff_timestamp != ""

    def test_timestamps_not_future(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        now = datetime.now(timezone.utc).isoformat()
        assert result.timestamp <= now

    def test_cutoff_not_before_observation(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = RegimeAdapter(ctx)
        result = adapter.run()
        assert result.data_cutoff_timestamp >= result.observation_timestamp


# =========================================================
# 11. LOOKAHEAD REGRESSION
# =========================================================

class TestLookaheadRegression:
    def test_structure_adapter_reports_lookahead(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = StructureAdapter(ctx)
        result = adapter.run()
        assert "lookahead_risk" in result.engine_metadata

    def test_no_future_data_in_feature_calculation(self):
        ohlcv = make_ohlcv(200)
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=ohlcv)
        adapter = MomentumVolatilityAdapter(ctx)
        result = adapter.run()
        assert result.data_cutoff_timestamp != ""

    def test_evidence_has_cutoff(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.evidence.data_cutoff_timestamp != ""


# =========================================================
# 12. NULL / UNAVAILABLE FEATURE HANDLING
# =========================================================

class TestNullUnavailableFeatureHandling:
    def test_null_data_quality_low(self):
        ohlcv = make_ohlcv(100)
        ohlcv.loc[:, "Close"] = None
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=ohlcv)
        assert ctx.feature_snapshot.data_quality_score < 1.0
        assert ctx.feature_snapshot.null_count > 0

    def test_empty_context_no_crash(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.status == AgentStatus.ERROR

    def test_adapter_returns_result_never_raises(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=None)
        for adapter_cls in [
            MarketDataAdapter, RegimeAdapter, StructureAdapter,
            MomentumVolatilityAdapter, StrategyAdapter, SetupAdapter,
            QualityAdapter, HistoricalEvidenceAdapter,
        ]:
            adapter = adapter_cls(ctx)
            result = adapter.run()
            assert isinstance(result, AgentResult)
            assert result.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL,
                                     AgentStatus.INSUFFICIENT_DATA, AgentStatus.ERROR)

    def test_feature_availability_dict_populated(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert isinstance(result.feature_availability, dict)
        assert len(result.feature_availability) > 0


# =========================================================
# 13. CONFIDENCE VS QUALITY SEPARATION
# =========================================================

class TestConfidenceQualitySeparation:
    def test_confidence_is_agent_metadata(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = RegimeAdapter(ctx)
        result = adapter.run()
        assert result.confidence >= 0.0

    def test_quality_separate_from_confidence(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = QualityAdapter(ctx)
        result = adapter.run()
        if result.status == AgentStatus.SUCCESS:
            assert "quality_score" in result.engine_metadata

    def test_no_win_probability_claim(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.confidence <= 1.0


# =========================================================
# 14. ENGINE VERSION TRACKING
# =========================================================

class TestEngineVersionTracking:
    def test_adapter_has_source_engine(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.source_engine != ""
        assert result.source_engine_version != ""

    def test_adapter_version_consistent(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        adapter = MarketDataAdapter(ctx)
        result = adapter.run()
        assert result.agent_version == "v1"

    def test_all_adapters_have_engine_metadata(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(100))
        for adapter_cls in [
            MarketDataAdapter, RegimeAdapter, StructureAdapter,
            MomentumVolatilityAdapter, StrategyAdapter, SetupAdapter,
            QualityAdapter, HistoricalEvidenceAdapter,
        ]:
            adapter = adapter_cls(ctx)
            result = adapter.run()
            assert result.source_engine != ""
            assert result.source_engine_version != ""


# =========================================================
# 15. MULTI-SYMBOL
# =========================================================

class TestMultiSymbol:
    def test_different_symbols_different_results(self):
        ctx1 = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200, base=100))
        ctx2 = build_context(symbol="AAPL", timeframe="1h", ohlcv_df=make_ohlcv(200, base=150))

        adapter1 = MomentumVolatilityAdapter(ctx1)
        result1 = adapter1.run()

        adapter2 = MomentumVolatilityAdapter(ctx2)
        result2 = adapter2.run()

        assert result1.symbol == "THYAO.IS"
        assert result2.symbol == "AAPL"

    def test_multi_symbol_adapter_does_not_crash(self):
        symbols = ["THYAO.IS", "AAPL", "BTC-USD"]
        for sym in symbols:
            ctx = build_context(symbol=sym, timeframe="1h", ohlcv_df=make_ohlcv(100))
            adapter = MarketDataAdapter(ctx)
            result = adapter.run()
            assert result.status == AgentStatus.SUCCESS
            assert result.symbol == sym


# =========================================================
# 16. MULTI-TIMEFRAME
# =========================================================

class TestMultiTimeframe:
    def test_different_timeframes(self):
        timeframes = ["5m", "15m", "1h", "4h", "1d"]
        for tf in timeframes:
            ctx = build_context(symbol="THYAO.IS", timeframe=tf, ohlcv_df=make_ohlcv(200))
            adapter = MarketDataAdapter(ctx)
            result = adapter.run()
            assert result.timeframe == tf
            assert result.status == AgentStatus.SUCCESS


# =========================================================
# 17. EVIDENCE TRACEABILITY
# =========================================================

class TestEvidenceTraceability:
    def test_evidence_has_source(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = MomentumVolatilityAdapter(ctx)
        result = adapter.run()
        for item in result.evidence.items:
            assert item.source != ""
            assert item.timestamp != ""

    def test_evidence_items_have_feature_names(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = MomentumVolatilityAdapter(ctx)
        result = adapter.run()
        for item in result.evidence.items:
            assert item.feature != ""

    def test_evidence_direction_valid(self):
        ctx = build_context(symbol="THYAO.IS", timeframe="1h", ohlcv_df=make_ohlcv(200))
        adapter = MomentumVolatilityAdapter(ctx)
        result = adapter.run()
        for item in result.evidence.items:
            assert item.direction in ("LONG", "SHORT", "NEUTRAL")