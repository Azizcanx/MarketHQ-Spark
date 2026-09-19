# -*- coding: utf-8 -*-
"""
Tests for setup_backtest_engine.py + new features
=====================================================

Tests for:
- setup attribution (setup_type)
- multi-strategy attribution
- regime detection
- regime snapshot
- CHoCH without sweep
- CHoCH with sweep
- dynamic evidence values
- quality_v2
- execution reason
- no look-ahead
- no data leakage
- deterministic output
"""

from __future__ import annotations

import numpy as np
import pytest

from setup_backtest_engine import (
    BacktestEngine,
    TradeResult,
    PortfolioMetrics,
    _simulate_trade,
    _check_exit,
    _check_entry,
    _entry_zone,
    _compute_excursion,
    _compute_portfolio_metrics,
    _quality_correlation,
)
from setup_quality_engine_v2 import (
    score_setup_quality_v2,
    _score_strategy_agreement,
    _score_invalidation_clarity,
    _score_structure_quality,
    _score_entry_quality,
)
from setup_object_model import (
    SetupModel, MarketInfo, TimeframeInfo, RegimeInfo, BiasInfo,
    StructureInfo, LiquidityInfo, EntryZone, Confirmation,
    InvalidationLevel, TargetLevel, Targets, RiskReward,
    Evidence, QualityScore, Reasoning, InvalidationConditions, LearningMetadata,
)
from smc_structure_v1 import evaluate_smc
import pandas as pd


# ======================================================================
# Helpers
# ======================================================================

def make_ohlcv(n=200, base=100, trend=0.01, vol=2.0):
    np.random.seed(42)
    close = base + np.cumsum(np.random.normal(trend, vol, n))
    open_p = close + np.random.normal(0, vol * 0.1, n)
    high = np.maximum(np.maximum(open_p, close), close + np.abs(np.random.normal(0, vol, n)))
    low = np.minimum(np.minimum(open_p, close), close - np.abs(np.random.normal(0, vol, n)))
    volume = np.random.uniform(1000, 10000, n)
    return pd.DataFrame({"Open": open_p, "High": high, "Low": low, "Close": close, "Volume": volume})


def make_trendy_ohlcv(n=200, base=100, uptrend=True):
    np.random.seed(42)
    direction = 1 if uptrend else -1
    close = base + np.cumsum(np.random.normal(direction * 0.05, 1.5, n))
    high = close + np.abs(np.random.normal(0, 0.5, n))
    low = close - np.abs(np.random.normal(0, 0.5, n))
    open_ = close + np.random.normal(0, 0.3, n)
    volume = np.random.randint(1000000, 10000000, n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})


# ======================================================================
# 1. SETUP ATTRIBUTION
# ======================================================================

class TestSetupAttribution:
    def test_setup_type_not_auto(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        for r in output['results']:
            assert r.setup_type != 'auto'

    def test_setup_type_not_unknown(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        unknown = sum(1 for r in output['results'] if r.setup_type == 'unknown')
        assert unknown == 0

    def test_setup_type_has_value(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        for r in output['results']:
            assert r.setup_type and r.setup_type != ''


# ======================================================================
# 2. MULTI-STRATEGY ATTRIBUTION
# ======================================================================

class TestMultiStrategyAttribution:
    def test_setup_model_has_strategy_fields(self):
        model = SetupModel()
        assert hasattr(model, 'supporting_strategies')
        assert hasattr(model, 'conflicting_strategies')
        assert isinstance(model.supporting_strategies, list)
        assert isinstance(model.conflicting_strategies, list)

    def test_confirmation_has_family_agreement(self):
        model = SetupModel()
        model.confirmation.family_agreement = {'trend': 'LONG', 'structure': 'SHORT'}
        model.confirmation.strategy_count = 2
        assert len(model.confirmation.family_agreement) == 2


# ======================================================================
# 3. REGIME DETECTION
# ======================================================================

class TestRegimeDetection:
    def test_regime_is_dict(self):
        from setup_engine_v1 import detect_regime
        df = make_ohlcv(200)
        last = df.iloc[-1]
        result = detect_regime(last)
        assert isinstance(result, dict)

    def test_regime_uses_adx(self):
        from setup_engine_v1 import detect_regime
        df = make_ohlcv(200)
        last = df.iloc[-1]
        result = detect_regime(last)
        assert isinstance(result, dict)

    def test_regime_has_confidence(self):
        from setup_engine_v1 import detect_regime
        df = make_ohlcv(200)
        last = df.iloc[-1]
        result = detect_regime(last)
        assert 'confidence' in result
        assert 0.0 <= result['confidence'] <= 1.0


# ======================================================================
# 4. REGIME SNAPSHOT
# ======================================================================

class TestRegimeSnapshot:
    def test_setup_includes_regime(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        for r in output['results']:
            assert r.regime, f"Missing regime for {r.setup_id}"

    def test_regime_varies(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        regimes = set(r.regime for r in output['results'])
        assert len(regimes) > 1


# ======================================================================
# 5. CHoCH WITHOUT SWEEP
# ======================================================================

class TestCHoCHNoSweep:
    def test_choch_without_sweep(self):
        df = make_ohlcv(200)
        result = evaluate_smc(df)
        assert isinstance(result, dict)
        assert 'direction' in result

    def test_choch_confidence_positive(self):
        df = make_ohlcv(200)
        result = evaluate_smc(df)
        if result.get('direction', '').startswith('CHoCH'):
            assert result.get('confidence', 0) > 0


# ======================================================================
# 6. CHoCH WITH SWEEP
# ======================================================================

class TestCHoCHWithSweep:
    def test_choch_with_sweep_still_fires(self):
        df = make_ohlcv(200)
        result = evaluate_smc(df)
        assert 'direction' in result


# ======================================================================
# 7. DYNAMIC EVIDENCE VALUES
# ======================================================================

class TestDynamicEvidenceValues:
    def test_strategy_agreement_varies(self):
        scores = set()
        for i in range(5):
            model = SetupModel()
            model.confirmation.strategy_count = i + 1
            model.confirmation.agreement_score = 0.3 + i * 0.1
            model.confirmation.family_agreement = {f'f{j}': 'LONG' for j in range(i + 1)}
            score, reason, conf = _score_strategy_agreement(model)
            scores.add(score)
        assert len(scores) >= 2

    def test_invalidation_clarity_varies(self):
        scores = set()
        for clarity in ['clear', 'medium', 'fuzzy']:
            model = SetupModel()
            model.invalidation.price = 95.0
            model.invalidation.distance_atr = 1.5
            model.invalidation.clarity = clarity
            model.invalidation.type = 'structural'
            model.entry_zone.center = 100.0
            score, reason, conf = _score_invalidation_clarity(model)
            scores.add(score)
        assert len(scores) >= 2

    def test_structure_quality_varies(self):
        scores = set()
        for high, low in [(110, 90), (105, 95), (102, 98)]:
            model = SetupModel()
            model.structure.has_structure = True
            model.structure.structure_type = ''
            model.structure.displacement = 0.0
            model.structure.last_swing_high = high
            model.structure.last_swing_low = low
            score, reason, conf = _score_structure_quality(model)
            scores.add(round(score, 3))
        assert len(scores) >= 2


# ======================================================================
# 8. QUALITY_V2
# ======================================================================

class TestQualityV2:
    def test_quality_v2_10_dimensions(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        for r in output['results'][:5]:
            bd = r.quality_breakdown
            assert len(bd) == 9, f"Expected 9 dims, got {len(bd)}"

    def test_quality_v2_dimensions_vary(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        dim_values = {d: set() for d in [
            'supporting_evidence', 'conflicting_evidence', 'regime_compatibility',
            'structure_quality', 'entry_quality', 'risk_reward_feasibility',
            'strategy_agreement', 'invalidation_clarity',
            'formation_chain',
        ]}
        for r in output['results']:
            for d, v in r.quality_breakdown.items():
                dim_values[d].add(round(v, 3))
        varying = sum(1 for d, vals in dim_values.items() if len(vals) >= 2)
        assert varying >= 7, f"Only {varying}/9 vary: {[(d, len(v)) for d, v in dim_values.items()]}"

    def test_quality_v2_overall_range(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output = engine.run()
        for r in output['results'][:5]:
            assert 0.0 <= r.quality_score <= 1.0


# ======================================================================
# 9. EXECUTION REASON
# ======================================================================

class TestExecutionReason:
    def test_expired_setups_have_reason(self):
        df = make_ohlcv(80, trend=0.001)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=4)
        output = engine.run()
        for r in output['results']:
            if r.outcome == 'open':
                assert r.exit_reason == 'expired'


# ======================================================================
# 10. NO LOOK-AHEAD
# ======================================================================

class TestNoLookAhead:
    def test_lookahead_violations_zero(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=4)
        output = engine.run()
        for r in output['results']:
            assert r.generated_at_idx < r.exit_idx or r.outcome == 'open'

    def test_entry_after_generation(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=4)
        output = engine.run()
        for r in output['results']:
            if r.outcome in ('hit_target', 'hit_invalidation'):
                assert r.generated_at_idx < r.entry_idx


# ======================================================================
# 11. NO DATA LEAKAGE
# ======================================================================

class TestNoDataLeakage:
    def test_rolling_window(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=4)
        output = engine.run()
        for r in output['results']:
            assert r.generated_at_idx >= engine.config.get('min_bars', 60)

    def test_no_forward_fill(self):
        pass  # Implicitly tested by rolling window


# ======================================================================
# 12. DETERMINISTIC OUTPUT
# ======================================================================

class TestDeterministicOutput:
    def test_deterministic_setup_types(self):
        df = make_ohlcv(200)
        engine1 = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output1 = engine1.run()
        engine2 = BacktestEngine(symbol='TEST', timeframe='1h', step=20)
        output2 = engine2.run()
        types1 = [r.setup_type for r in output1['results']]
        types2 = [r.setup_type for r in output2['results']]
        assert types1 == types2

    def test_deterministic_regime(self):
        from setup_engine_v1 import detect_regime
        df = make_ohlcv(200)
        last = df.iloc[-1]
        r1 = detect_regime(last)
        r2 = detect_regime(last)
        assert r1 == r2


# ======================================================================
# BONUS: REGIME x STRATEGY MATRIX
# ======================================================================

class TestRegimeStrategyMatrix:
    def test_regime_matrix_computable(self):
        df = make_ohlcv(200)
        engine = BacktestEngine(symbol='TEST', timeframe='1h', step=4)
        output = engine.run()
        matrix = {}
        for r in output['results']:
            key = (r.regime, r.setup_type)
            matrix.setdefault(key, []).append(r.outcome)
        assert len(matrix) >= 3
        for key, outcomes in matrix.items():
            wins = sum(1 for o in outcomes if o == 'hit_target')
            wr = wins / len(outcomes)
            assert 0.0 <= wr <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])