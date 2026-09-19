# -*- coding: utf-8 -*-
"""Future invariance + lookahead tests for research validation pipeline.

Tests that setup geometry is frozen at cutoff time and is not affected
by future bars being added to the DataFrame.
"""

import pytest
import pandas as pd
import numpy as np

from research_setup_phase_f import build_research_backed_setup
from research_validation_engine import audit_lookahead, replay_setup
from research_validation_pipeline import generate_setups_at_cutoff
from opportunity_model import Opportunity


# ── helpers ────────────────────────────────────────────────────────────────

def make_ohlcv(n_bars: int = 200, base_price: float = 320.0) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with realistic columns."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="1h")
    close = base_price + np.cumsum(rng.normal(0, 0.5, n_bars))
    high = close + rng.uniform(0.1, 0.5, n_bars)
    low = close - rng.uniform(0.1, 0.5, n_bars)
    open_ = close + rng.normal(0, 0.2, n_bars)
    volume = rng.uniform(1_000_000, 5_000_000, n_bars)

    df = pd.DataFrame({
        "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume,
    }, index=idx)
    return df


def make_opportunity(symbol: str = "TEST.IS", direction: str = "LONG"):
    return Opportunity(
        symbol=symbol, timeframe="1h", direction=direction,
        regime="TRENDING_UP", confidence=0.65, uncertainty=0.35,
    )


# ═══════════════════════════════════════════════════════════════════════════
# FUTURE INVARIANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestFutureInvariance:
    """Setup geometry must not change when future bars are added."""

    @pytest.mark.parametrize("cutoff_idx", [50, 100, 150])
    def test_geometry_frozen_at_cutoff(self, cutoff_idx):
        """Geometry computed at cutoff must be identical whether or not
        future bars are present in the DataFrame."""
        df_full = make_ohlcv(250)
        df_past = df_full.iloc[: cutoff_idx + 1].copy()

        opp = make_opportunity()
        setup_past = build_research_backed_setup(opp, df=df_past, cutoff_idx=cutoff_idx)
        setup_full = build_research_backed_setup(opp, df=df_full, cutoff_idx=cutoff_idx)

        for field in ("entry_reference", "invalidation_price", "target_1", "target_2", "target_3"):
            assert getattr(setup_past, field) == getattr(setup_full, field), (
                f"{field} changed when future bars were added "
                f"(past={getattr(setup_past, field)}, full={getattr(setup_full, field)})"
            )

    @pytest.mark.parametrize("n_future", [5, 10, 20, 50])
    def test_geometry_stable_with_increasing_future_bars(self, n_future):
        """Adding more future bars should not change geometry at all."""
        cutoff_idx = 50
        df_base = make_ohlcv(200)
        df_past = df_base.iloc[: cutoff_idx + 1].copy()

        opp = make_opportunity()
        setup_past = build_research_backed_setup(opp, df=df_past, cutoff_idx=cutoff_idx)

        for n in [5, 10, 20, 50]:
            df_extended = df_base.iloc[: cutoff_idx + 1 + n].copy()
            setup_ext = build_research_backed_setup(opp, df=df_extended, cutoff_idx=cutoff_idx)

            for field in ("entry_reference", "invalidation_price", "target_1", "target_2", "target_3"):
                assert getattr(setup_past, field) == getattr(setup_ext, field), (
                    f"{field} changed with {n} future bars"
                )

    def test_entry_zone_unchanged_with_future_bars(self):
        """Entry zone geometry specifically must be invariant."""
        cutoff_idx = 50
        df_full = make_ohlcv(200)
        df_past = df_full.iloc[: cutoff_idx + 1].copy()

        opp = make_opportunity()
        setup_past = build_research_backed_setup(opp, df=df_past, cutoff_idx=cutoff_idx)
        setup_full = build_research_backed_setup(opp, df=df_full, cutoff_idx=cutoff_idx)

        assert setup_past.entry_zone_low == setup_full.entry_zone_low
        assert setup_past.entry_zone_high == setup_full.entry_zone_high
        assert setup_past.entry_method == setup_full.entry_method

    def test_invalidation_price_unchanged_with_future_bars(self):
        """Invalidation price must not shift when future bars are added."""
        cutoff_idx = 50
        df_full = make_ohlcv(200)
        df_past = df_full.iloc[: cutoff_idx + 1].copy()

        opp = make_opportunity()
        setup_past = build_research_backed_setup(opp, df=df_past, cutoff_idx=cutoff_idx)
        setup_full = build_research_backed_setup(opp, df=df_full, cutoff_idx=cutoff_idx)

        assert setup_past.invalidation_price == setup_full.invalidation_price
        assert setup_past.invalidation_type == setup_full.invalidation_type

    def test_targets_unchanged_with_future_bars(self):
        """T1/T2/T3 must not shift when future bars are added."""
        cutoff_idx = 50
        df_full = make_ohlcv(200)
        df_past = df_full.iloc[: cutoff_idx + 1].copy()

        opp = make_opportunity()
        setup_past = build_research_backed_setup(opp, df=df_past, cutoff_idx=cutoff_idx)
        setup_full = build_research_backed_setup(opp, df=df_full, cutoff_idx=cutoff_idx)

        assert setup_past.target_1 == setup_full.target_1
        assert setup_past.target_2 == setup_full.target_2
        assert setup_past.target_3 == setup_full.target_3
        assert setup_past.target_method == setup_full.target_method


# ═══════════════════════════════════════════════════════════════════════════
# LOOKAHEAD AUDIT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestLookaheadAudit:
    """audit_lookahead must detect and PASS future-invariant setups."""

    def test_audit_passes_with_cutoff_fix(self):
        """With cutoff_idx enforced, audit_lookahead must return PASS."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        setups = generate_setups_at_cutoff(df, cutoff_idx)
        assert setups, "No setups generated"

        result = audit_lookahead(setups, df, cutoff_idx)

        assert result["lookahead_status"] == "PASS", (
            f"Lookahead audit failed: {result.get('changes', [])}"
        )
        assert result["n_changes"] == 0

    def test_audit_reports_changes_without_cutoff(self):
        """Without cutoff_idx, future bars WOULD change geometry (vulnerability)."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        opp = make_opportunity()
        # Build setup WITHOUT cutoff_idx (vulnerable)
        setup_no_cutoff = build_research_backed_setup(opp, df=df.iloc[:cutoff_idx + 21])
        frozen = setup_no_cutoff.freeze()

        # Build setup WITH cutoff_idx (protected)
        setup_with_cutoff = build_research_backed_setup(
            opp, df=df.iloc[:cutoff_idx + 21], cutoff_idx=cutoff_idx
        )
        protected = setup_with_cutoff.freeze()

        # Without cutoff, geometry changes; with cutoff, it's stable
        changes_without = [
            f for f in ("invalidation_price", "target_1", "target_2", "target_3")
            if frozen.get(f) != protected.get(f)
        ]
        assert len(changes_without) > 0, (
            "Expected geometry to change without cutoff_idx — vulnerability not detected"
        )

    @pytest.mark.parametrize("cutoff_idx", [30, 50, 100])
    def test_audit_passes_at_different_cutoffs(self, cutoff_idx):
        """Lookahead audit must pass regardless of cutoff position."""
        df = make_ohlcv(250)
        setups = generate_setups_at_cutoff(df, cutoff_idx)
        if not setups:
            pytest.skip("No setups generated at this cutoff")

        result = audit_lookahead(setups, df, cutoff_idx)
        assert result["lookahead_status"] == "PASS"


# ═══════════════════════════════════════════════════════════════════════════
# REPLAY INTEGRITY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestReplayIntegrity:
    """Outcome replay must use future bars, not setup geometry."""

    def test_replay_uses_future_bars_only(self):
        """Replay should evaluate outcomes against future bars, not modify geometry."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        setups = generate_setups_at_cutoff(df, cutoff_idx)
        assert setups

        setup = setups[0]
        frozen_geo = setup.freeze()

        # Replay against full df (future bars included for outcome)
        outcome = replay_setup(setup, df, cutoff_idx)

        # Geometry from setup must match frozen geometry
        assert setup.entry_reference == frozen_geo["entry_reference"]
        assert setup.invalidation_price == frozen_geo["invalidation_price"]
        assert setup.target_1 == frozen_geo["target_1"]
        assert setup.target_2 == frozen_geo["target_2"]
        assert setup.target_3 == frozen_geo["target_3"]

    def test_outcome_fields_populated(self):
        """Outcome must have correct fields populated from replay."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        setups = generate_setups_at_cutoff(df, cutoff_idx)
        assert setups

        outcome = replay_setup(setups[0], df, cutoff_idx)

        assert outcome.setup_id is not None
        assert outcome.symbol == "THYAO.IS"
        assert outcome.cutoff_time is not None

    def test_snapshot_id_contains_cutoff_idx(self):
        """feature_snapshot_id must embed cutoff_idx, not timestamp."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        setups = generate_setups_at_cutoff(df, cutoff_idx)
        assert setups

        snap = setups[0].feature_snapshot_id
        parts = snap.split("-")
        last = parts[-1]

        assert last.isdigit(), f"Snapshot ID last part must be cutoff idx, got: {snap}"
        assert int(last) == cutoff_idx, (
            f"Snapshot ID cutoff {last} != expected {cutoff_idx}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TARGET LOGIC FIX TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestTargetLogicFix:
    """Tests for the two replay target bugs."""

    def test_t2_hit_computes_realized_r(self):
        """T2'den çıkışta realized_r T2 fiyatına göre hesaplanmalı."""
        from research_validation_engine import replay_setup
        from opportunity_model import ResearchBackedSetup

        df = make_ohlcv(200)
        cutoff_idx = 50
        entry_price = float(df.iloc[cutoff_idx]["Close"])

        setup = ResearchBackedSetup(
            setup_id="TEST-T2-R",
            opportunity_id="OPP-TEST",
            symbol="TEST.IS", timeframe="1h",
            detected_at="2026-01-01T00:00:00+00:00",
            direction="SHORT", regime="TRENDING_UP",
            setup_type="test", strategy_family="", thesis="",
            entry_zone_low=entry_price * 0.999,
            entry_zone_high=entry_price * 1.001,
            entry_reference=entry_price,
            entry_method="test", entry_confirmation=[], entry_status="AVAILABLE",
            invalidation_price=entry_price * 1.02,
            invalidation_type="atr", invalidation_reason="test",
            invalidation_distance_atr=2.0,
            target_1=entry_price * 1.05,  # unreachable (above entry for SHORT)
            target_2=entry_price * 0.995,  # reachable
            target_3=entry_price * 0.990,
            target_method="test",
            stop_distance=entry_price * 0.02,
            target_distance_1=abs(entry_price * 1.05 - entry_price),
            target_distance_2=abs(entry_price * 0.995 - entry_price),
            target_distance_3=abs(entry_price * 0.990 - entry_price),
            rr_to_t1=None, rr_to_t2=None, rr_to_t3=None,
            supporting_evidence=[], conflicting_evidence=[],
            historical_evidence={}, structure_evidence={},
            regime_evidence={}, momentum_evidence={},
            liquidity_evidence={}, volatility_evidence={},
            uncertainty_flags=[], overall_uncertainty=0.5,
            quality_reference="test", confidence=0.65, uncertainty=0.35,
            data_availability=1.0, source_agents=[], evidence_traces=[],
            feature_snapshot_id="FS-TEST-1h-50", status="CANDIDATE",
        )

        outcome = replay_setup(setup, df, cutoff_idx)

        if outcome.t2_hit:
            assert setup.target_2 is not None
            t2 = float(setup.target_2)
            expected_r = (entry_price - t2) / entry_price * 100
            assert abs(outcome.realized_r - expected_r) < 0.1, (
                f"R should be based on T2 exit: expected ~{expected_r:.4f}, got {outcome.realized_r}"
            )

    def test_long_target_ordering_closest_first(self):
        """LONG'da T1 en yakın entry, T3 en uzak."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        opp = make_opportunity(direction="LONG")
        setup = build_research_backed_setup(opp, df=df.iloc[:cutoff_idx + 1], cutoff_idx=cutoff_idx)

        if setup.target_1 and setup.target_2 and setup.target_3:
            entry = setup.entry_reference or 300.0
            # T1 closest to entry, T3 furthest → T1 < T2 < T3 for LONG
            assert setup.target_1 <= setup.target_2, "LONG T1 should be <= T2"
            assert setup.target_2 <= setup.target_3, "LONG T2 should be <= T3"
            assert setup.target_1 >= entry, "LONG T1 should be above entry"

    def test_short_target_ordering_closest_first(self):
        """SHORT'ta T1 en yakın entry, T3 en uzak."""
        df = make_ohlcv(200)
        cutoff_idx = 50

        opp = make_opportunity(direction="SHORT")
        setup = build_research_backed_setup(opp, df=df.iloc[:cutoff_idx + 1], cutoff_idx=cutoff_idx)

        if setup.target_1 and setup.target_2 and setup.target_3:
            entry = setup.entry_reference or 300.0
            # T1 closest to entry, T3 furthest → T1 > T2 > T3 for SHORT
            assert setup.target_1 >= setup.target_2, "SHORT T1 should be >= T2"
            assert setup.target_2 >= setup.target_3, "SHORT T2 should be >= T3"
            assert setup.target_1 <= entry, "SHORT T1 should be below entry"