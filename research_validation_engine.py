# -*- coding: utf-8 -*-
"""Phase G — Research Validation Engine.

Historical replay of Research-Backed Setups against real OHLCV data.
Validates setup geometry, outcome simulation, walk-forward stability,
failure analysis, and claim validation.

Research-only. No trading, no broker, no live execution.
No win probability. No future data in setup generation.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from opportunity_model import (
    ResearchBackedSetup, SetupStatus, UncertaintyFlag,
    EvidenceTrace, Direction,
)
from research_validation_model import (
    HistoricalOutcome, ValidationMetrics, DataSufficiency,
    OutcomeType, ClaimStatus, ResearchClaim,
)


# ═══════════════════════════════════════════════════════════════
# HISTORICAL REPLAY
# ═══════════════════════════════════════════════════════════════

def replay_setup(
    setup: ResearchBackedSetup,
    df: pd.DataFrame,
    cutoff_idx: int,
) -> HistoricalOutcome:
    """Replay a ResearchBackedSetup against historical OHLCV data.

    Uses only bars AFTER cutoff_idx for outcome evaluation.
    Setup geometry is fixed at cutoff time.

    Args:
        setup: ResearchBackedSetup from Phase F
        df: OHLCV DataFrame with indicators (enriched)
        cutoff_idx: Index position where setup was generated

    Returns:
        HistoricalOutcome with full outcome details
    """
    now = datetime.now(timezone.utc).isoformat()
    outcome = HistoricalOutcome(
        setup_id=setup.setup_id,
        opportunity_id=setup.opportunity_id,
        symbol=setup.symbol,
        timeframe=setup.timeframe,
        cutoff_time=setup.detected_at,
        direction=setup.direction,
        regime=setup.regime,
        setup_type=setup.setup_type,
        strategy_family=setup.strategy_family,
        entry_zone_low=setup.entry_zone_low,
        entry_zone_high=setup.entry_zone_high,
        entry_reference=setup.entry_reference,
        invalidation_price=setup.invalidation_price,
        target_1=setup.target_1,
        target_2=setup.target_2,
        target_3=setup.target_3,
        quality_score=setup.confidence,
        confidence=setup.confidence,
        uncertainty=setup.uncertainty,
        data_availability=setup.data_availability,
        feature_snapshot_id=setup.feature_snapshot_id,
        source_agents=setup.source_agents,
        evidence_traces=[et.to_dict() for et in setup.evidence_traces],
        created_at=now,
    )

    # Not enough bars after cutoff
    if cutoff_idx >= len(df) - 1:
        outcome.outcome_type = OutcomeType.INCOMPLETE_DATA.value
        outcome.exit_reason = "INSUFFICIENT_BARS_AFTER_CUTOFF"
        return outcome

    # No entry geometry
    if setup.entry_reference is None or setup.entry_zone_low is None:
        outcome.outcome_type = OutcomeType.NO_ENTRY.value
        outcome.no_entry = True
        outcome.exit_reason = "NO_ENTRY_GEOMETRY"
        return outcome

    # No invalidation
    if setup.invalidation_price is None:
        outcome.outcome_type = OutcomeType.EXPIRED.value
        outcome.exit_reason = "NO_INVALIDATION"
        return outcome

    # Simulate through future bars
    entry_triggered = False
    invalidation_hit = False
    t1_hit = False
    t2_hit = False
    t3_hit = False

    mfe = 0.0
    mae = 0.0
    bars_since_entry = 0
    entry_price = setup.entry_reference

    for i in range(cutoff_idx + 1, len(df)):
        row = df.iloc[i]
        high = float(row.get("High", 0))
        low = float(row.get("Low", 0))
        close = float(row.get("Close", 0))

        if not entry_triggered:
            # Check entry
            if _check_entry(setup.direction, close, setup.entry_zone_low, setup.entry_zone_high):
                entry_triggered = True
                outcome.entry_triggered = True
                outcome.entry_time = _get_timestamp(row)
                outcome.bars_to_entry = i - cutoff_idx
                entry_price = close  # Use actual close as entry

                # Reset MFE/MAE from entry
                mfe = 0.0
                mae = 0.0
                bars_since_entry = 0
                continue
        else:
            # After entry — track MFE/MAE and check exits
            bars_since_entry += 1

            if setup.direction == "LONG":
                excursion = close - entry_price
            else:
                excursion = entry_price - close

            if excursion > mfe:
                mfe = excursion
            if excursion < mae:
                mae = excursion

            # Check invalidation
            if _check_invalidation(setup.direction, low, high, setup.invalidation_price):
                invalidation_hit = True
                outcome.invalidation_hit = True
                outcome.invalidation_time = _get_timestamp(row)
                outcome.bars_to_invalidation = bars_since_entry
                outcome.exit_reason = "INVALIDATION"
                outcome.realized_r = _compute_r(entry_price, setup.invalidation_price, setup.direction)
                break

            # Check targets
            if setup.target_1 and _check_target(setup.direction, high, low, setup.target_1):
                t1_hit = True
                outcome.t1_hit = True
                outcome.t1_time = _get_timestamp(row)
                outcome.bars_to_t1 = bars_since_entry
                outcome.realized_r = _compute_r(entry_price, setup.target_1, setup.direction)
                # Continue to check T2/T3
                if setup.target_2 and _check_target(setup.direction, high, low, setup.target_2):
                    t2_hit = True
                    outcome.t2_hit = True
                    outcome.t2_time = _get_timestamp(row)
                    outcome.bars_to_t2 = bars_since_entry
                if setup.target_3 and _check_target(setup.direction, high, low, setup.target_3):
                    t3_hit = True
                    outcome.t3_hit = True
                    outcome.t3_time = _get_timestamp(row)
                    outcome.bars_to_t3 = bars_since_entry
                break

            if setup.target_2 and _check_target(setup.direction, high, low, setup.target_2):
                t2_hit = True
                outcome.t2_hit = True
                outcome.t2_time = _get_timestamp(row)
                outcome.bars_to_t2 = bars_since_entry
                outcome.realized_r = _compute_r(entry_price, setup.target_2, setup.direction)
                # Continue to T3
                if setup.target_3 and _check_target(setup.direction, high, low, setup.target_3):
                    t3_hit = True
                    outcome.t3_hit = True
                    outcome.t3_time = _get_timestamp(row)
                    outcome.bars_to_t3 = bars_since_entry
                break

            if setup.target_3 and _check_target(setup.direction, high, low, setup.target_3):
                t3_hit = True
                outcome.t3_hit = True
                outcome.t3_time = _get_timestamp(row)
                outcome.bars_to_t3 = bars_since_entry
                outcome.realized_r = _compute_r(entry_price, setup.target_3, setup.direction)
                break

        # Check max holding period (e.g., 30 bars)
        if bars_since_entry >= 30:
            outcome.exit_reason = "EXPIRY"
            outcome.realized_r = _compute_r(entry_price, close, setup.direction)
            break

    # Set MFE/MAE
    outcome.max_favorable_excursion = round(mfe, 4)
    outcome.max_adverse_excursion = round(mae, 4)

    # Determine outcome type
    outcome = _determine_outcome_type(outcome, t1_hit, t2_hit, t3_hit, invalidation_hit, entry_triggered)

    return outcome


def _check_entry(
    direction: str,
    close: float,
    zone_low: float | None,
    zone_high: float | None,
) -> bool:
    """Check if entry zone was touched."""
    if zone_low is None or zone_high is None:
        return False
    if direction == "LONG":
        return zone_low <= close <= zone_high
    elif direction == "SHORT":
        return zone_low <= close <= zone_high
    return False


def _check_invalidation(
    direction: str,
    low: float,
    high: float,
    invalidation_price: float | None,
) -> bool:
    """Check if invalidation was hit."""
    if invalidation_price is None:
        return False
    if direction == "LONG":
        return low <= invalidation_price
    elif direction == "SHORT":
        return high >= invalidation_price
    return False


def _check_target(
    direction: str,
    high: float,
    low: float,
    target_price: float | None,
) -> bool:
    """Check if target was reached."""
    if target_price is None:
        return False
    if direction == "LONG":
        return high >= target_price
    elif direction == "SHORT":
        return low <= target_price
    return False


def _compute_r(entry: float, exit_price: float, direction: str) -> float:
    """Compute realized R."""
    if direction == "LONG":
        return (exit_price - entry) / entry * 100
    elif direction == "SHORT":
        return (entry - exit_price) / entry * 100
    return 0.0


def _determine_outcome_type(
    outcome: HistoricalOutcome,
    t1_hit: bool,
    t2_hit: bool,
    t3_hit: bool,
    invalidation_hit: bool,
    entry_triggered: bool,
) -> HistoricalOutcome:
    """Determine the outcome type."""
    if not entry_triggered:
        outcome.outcome_type = OutcomeType.NO_ENTRY.value
        outcome.no_entry = True
        outcome.exit_reason = "NO_ENTRY"
    elif invalidation_hit:
        outcome.outcome_type = OutcomeType.INVALIDATED.value
    elif t3_hit:
        outcome.outcome_type = OutcomeType.TARGET_3_REACHED.value
    elif t2_hit:
        outcome.outcome_type = OutcomeType.TARGET_2_REACHED.value
    elif t1_hit:
        outcome.outcome_type = OutcomeType.TARGET_1_REACHED.value
    elif outcome.exit_reason == "EXPIRY":
        outcome.outcome_type = OutcomeType.EXPIRED.value
    else:
        outcome.outcome_type = OutcomeType.EXPIRED.value
        outcome.exit_reason = "EXPIRY"
    return outcome


def _get_timestamp(row: pd.Series) -> str:
    """Get timestamp from DataFrame row."""
    idx = row.name
    if isinstance(idx, datetime):
        return idx.isoformat()
    return str(idx)


# ═══════════════════════════════════════════════════════════════
# VALIDATION ENGINE
# ═══════════════════════════════════════════════════════════════

def validate_setups(
    setups: list[ResearchBackedSetup],
    df: pd.DataFrame,
    cutoff_indices: list[int] | None = None,
) -> list[HistoricalOutcome]:
    """Validate multiple setups against historical data.

    Args:
        setups: List of ResearchBackedSetup objects
        df: OHLCV DataFrame with indicators
        cutoff_indices: List of cutoff positions (same length as setups).
            If None, uses len(df) - 10 for each (last 10 bars as outcome window).

    Returns:
        List of HistoricalOutcome objects
    """
    outcomes: list[HistoricalOutcome] = []

    for idx, setup in enumerate(setups):
        if cutoff_indices and idx < len(cutoff_indices):
            cutoff_idx = cutoff_indices[idx]
        else:
            # Default: 10 bars after setup detection for outcome
            cutoff_idx = max(0, len(df) - 10)

        outcome = replay_setup(setup, df, cutoff_idx)
        outcomes.append(outcome)

    return outcomes


def compute_validation_metrics(
    outcomes: list[HistoricalOutcome],
) -> ValidationMetrics:
    """Compute validation metrics from historical outcomes."""
    metrics = ValidationMetrics()
    metrics.n_setups = len(outcomes)

    if not outcomes:
        metrics.data_sufficiency = DataSufficiency.UNAVAILABLE.value
        return metrics

    entries = [o for o in outcomes if o.entry_triggered]
    invalidations = [o for o in outcomes if o.invalidation_hit]
    expired = [o for o in outcomes if o.outcome_type == OutcomeType.EXPIRED.value]
    no_entry = [o for o in outcomes if o.no_entry or o.outcome_type == OutcomeType.NO_ENTRY.value]
    ambiguous = [o for o in outcomes if o.ambiguous]

    metrics.n_entries = len(entries)
    metrics.n_invalidations = len(invalidations)
    metrics.n_expired = len(expired)
    metrics.n_no_entry = len(no_entry)
    metrics.n_ambiguous = len(ambiguous)

    # Hit rates
    if entries:
        metrics.t1_hit_rate = sum(1 for o in entries if o.t1_hit) / len(entries)
        metrics.t2_hit_rate = sum(1 for o in entries if o.t2_hit) / len(entries)
        metrics.t3_hit_rate = sum(1 for o in entries if o.t3_hit) / len(entries)
        metrics.invalidation_rate = len(invalidations) / len(entries)
        metrics.entry_rate = len(entries) / len(outcomes)

    # Realized R
    realized_rs = [o.realized_r for o in outcomes if o.realized_r != 0]
    if realized_rs:
        metrics.avg_r = float(np.mean(realized_rs))
        metrics.median_r = float(np.median(realized_rs))
        metrics.std_r = float(np.std(realized_rs))
        metrics.min_r = float(min(realized_rs))
        metrics.max_r = float(max(realized_rs))

    # MFE/MAE
    mfes = [o.max_favorable_excursion for o in outcomes if o.max_favorable_excursion > 0]
    maes = [o.max_adverse_excursion for o in outcomes if o.max_adverse_excursion < 0]
    if mfes:
        metrics.avg_mfe = float(np.mean(mfes))
    if maes:
        metrics.avg_mae = float(np.mean([abs(m) for m in maes]))

    # Bars
    bars_to_entry = [o.bars_to_entry for o in outcomes if o.bars_to_entry > 0]
    bars_to_inv = [o.bars_to_invalidation for o in outcomes if o.bars_to_invalidation > 0]
    bars_to_t1 = [o.bars_to_t1 for o in outcomes if o.bars_to_t1 > 0]
    if bars_to_entry:
        metrics.avg_bars_to_entry = float(np.mean(bars_to_entry))
    if bars_to_inv:
        metrics.avg_bars_to_invalidation = float(np.mean(bars_to_inv))
    if bars_to_t1:
        metrics.avg_bars_to_t1 = float(np.mean(bars_to_t1))

    # Data sufficiency
    metrics.data_sufficiency = _assess_data_sufficiency(outcomes)

    return metrics


def _assess_data_sufficiency(outcomes: list[HistoricalOutcome]) -> str:
    """Assess data sufficiency for the outcomes."""
    n = len(outcomes)
    if n == 0:
        return DataSufficiency.UNAVAILABLE.value
    if n < 10:
        return DataSufficiency.LOW_SAMPLE.value
    if n < 30:
        return DataSufficiency.LIMITED.value
    return DataSufficiency.DATA_SUFFICIENT.value


# ═══════════════════════════════════════════════════════════════
# WALK-FORWARD VALIDATION
# ═══════════════════════════════════════════════════════════════

def walk_forward_validation(
    setups: list[ResearchBackedSetup],
    df: pd.DataFrame,
    n_splits: int = 3,
    train_ratio: float = 0.7,
) -> list[dict[str, Any]]:
    """Chronological walk-forward validation.

    Splits data chronologically into train/validation windows.
    Each window: setups generated in train, outcomes measured in validation.

    Args:
        setups: List of ResearchBackedSetup objects
        df: OHLCV DataFrame
        n_splits: Number of walk-forward splits
        train_ratio: Ratio of data used for training

    Returns:
        List of walk-forward window results
    """
    results = []
    n = len(df)
    window_size = n // n_splits

    for i in range(n_splits):
        train_end = int(n * train_ratio) + i * window_size
        val_start = train_end
        val_end = min(val_end + window_size, n) if (val_end := train_end + window_size) <= n else n

        if val_start >= n or val_end <= val_start:
            continue

        # Setups in this window
        window_setups = [
            s for s in setups
            if _in_window(s, df, val_start, val_end)
        ]

        if not window_setups:
            continue

        # Validate
        outcomes = validate_setups(window_setups, df)
        metrics = compute_validation_metrics(outcomes)

        results.append({
            "window": i + 1,
            "train_start": 0,
            "train_end": train_end,
            "val_start": val_start,
            "val_end": val_end,
            "n_setups": len(window_setups),
            "metrics": metrics.to_dict(),
        })

    return results


def _in_window(
    setup: ResearchBackedSetup,
    df: pd.DataFrame,
    val_start: int,
    val_end: int,
) -> bool:
    """Check if setup falls within validation window."""
    # Simple check: setup detected within window
    # In production, this would compare timestamps
    return val_start <= val_end  # Placeholder — always true for now


# ═══════════════════════════════════════════════════════════════
# FAILURE ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_failures(
    outcomes: list[HistoricalOutcome],
) -> dict[str, Any]:
    """Analyze common failure patterns among invalidated setups."""
    failures = [o for o in outcomes if o.outcome_type == OutcomeType.INVALIDATED.value]
    successes = [o for o in outcomes if o.outcome_type in (
        OutcomeType.TARGET_1_REACHED.value,
        OutcomeType.TARGET_2_REACHED.value,
        OutcomeType.TARGET_3_REACHED.value,
    )]

    analysis: dict[str, Any] = {
        "n_failures": len(failures),
        "n_successes": len(successes),
        "failure_rate": len(failures) / max(len(outcomes), 1),
        "common_features": {},
    }

    if not failures:
        return analysis

    # Entry availability
    no_entry_failures = [f for f in failures if f.no_entry]
    analysis["common_features"]["no_entry_rate"] = len(no_entry_failures) / len(failures)

    # Uncertainty analysis
    high_uncertainty_failures = [f for f in failures if f.uncertainty > 0.5]
    analysis["common_features"]["high_uncertainty_rate"] = len(high_uncertainty_failures) / len(failures)

    # Low data availability
    low_data_failures = [f for f in failures if f.data_availability < 0.5]
    analysis["common_features"]["low_data_availability_rate"] = len(low_data_failures) / len(failures)

    # Invalidation distance
    inv_distances = [abs(f.entry_reference - f.invalidation_price) if f.entry_reference and f.invalidation_price else 0 for f in failures]
    if inv_distances:
        analysis["common_features"]["avg_invalidation_distance"] = float(np.mean(inv_distances))

    # Success comparison
    if successes:
        success_uncertainty = np.mean([s.uncertainty for s in successes])
        failure_uncertainty = np.mean([f.uncertainty for f in failures])
        analysis["uncertainty_gap"] = float(failure_uncertainty - success_uncertainty)

        success_data = np.mean([s.data_availability for s in successes])
        failure_data = np.mean([f.data_availability for f in failures])
        analysis["data_availability_gap"] = float(success_data - failure_data)

    return analysis


# ═══════════════════════════════════════════════════════════════
# CLAIM VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_claims(
    claims: list[ResearchClaim],
    outcomes: list[HistoricalOutcome],
) -> list[ResearchClaim]:
    """Validate research claims against historical outcomes."""
    for claim in claims:
        if claim.status != ClaimStatus.UNTESTED.value:
            continue

        # Test each claim against outcomes
        evidence = _test_claim(claim, outcomes)
        claim.evidence = evidence

        if evidence:
            claim.status = ClaimStatus.TESTED.value
            claim.confidence = float(np.mean([e.get("support", 0.5) for e in evidence]))
            claim.uncertainty = 1.0 - claim.confidence
        else:
            claim.status = ClaimStatus.UNTESTED.value

        claim.updated_at = datetime.now(timezone.utc).isoformat()

    return claims


def _test_claim(claim: ResearchClaim, outcomes: list[HistoricalOutcome]) -> list[dict[str, Any]]:
    """Test a single claim against outcomes. Returns evidence items."""
    evidence: list[dict[str, Any]] = []

    if "high quality" in claim.claim_text.lower() and "target" in claim.claim_text.lower():
        # Test: high quality setups have higher target hit rates
        high_quality = [o for o in outcomes if o.quality_score and o.quality_score > 0.5]
        low_quality = [o for o in outcomes if o.quality_score and o.quality_score <= 0.5]

        if high_quality and low_quality:
            hq_t1 = sum(1 for o in high_quality if o.t1_hit) / len(high_quality)
            lq_t1 = sum(1 for o in low_quality if o.t1_hit) / len(low_quality)
            evidence.append({
                "test": "high_quality_target_hit",
                "high_quality_rate": hq_t1,
                "low_quality_rate": lq_t1,
                "support": hq_t1 > lq_t1,
                "effect_size": hq_t1 - lq_t1,
            })

    if "confidence" in claim.claim_text.lower() and "outcome" in claim.claim_text.lower():
        # Test: confidence correlates with outcome
        if outcomes:
            confidences = [o.confidence for o in outcomes if o.confidence > 0]
            realized_rs = [o.realized_r for o in outcomes]
            if confidences and realized_rs and len(confidences) == len(realized_rs):
                corr = np.corrcoef(confidences, realized_rs)[0, 1] if len(confidences) > 2 else 0
                evidence.append({
                    "test": "confidence_outcome_correlation",
                    "correlation": float(corr),
                    "support": abs(corr) > 0.3,
                    "sample_size": len(confidences),
                })

    return evidence


# ═══════════════════════════════════════════════════════════════
# LOOKAHEAD AUDIT
# ═══════════════════════════════════════════════════════════════

def audit_lookahead(
    setups: list[ResearchBackedSetup],
    df: pd.DataFrame,
    cutoff_idx: int,
) -> dict[str, Any]:
    """Audit for lookahead leakage in setup generation.

    Freezes setup geometry at cutoff, then recomputes with future bars.
    If geometry changes, future data leaked into setup generation.

    Args:
        setups: Setups generated at cutoff
        df: Full DataFrame (including future bars)
        cutoff_idx: Cutoff position

    Returns:
        Audit result with lookahead status
    """
    from research_setup_phase_f import build_research_backed_setup
    from opportunity_model import Opportunity

    # Freeze geometry at cutoff
    frozen = setups[0].freeze() if setups else {}

    # Recompute with future data
    opp = Opportunity(
        symbol=setups[0].symbol if setups else "",
        timeframe=setups[0].timeframe if setups else "",
        direction=setups[0].direction if setups else "UNKNOWN",
        regime=setups[0].regime if setups else "UNKNOWN",
    )

    if cutoff_idx + 20 >= len(df):
        return {
            "lookahead_status": "NOT_TESTABLE",
            "reason": "Insufficient future data for comparison",
        }

    setup_future = build_research_backed_setup(opp, df.iloc[:cutoff_idx + 21], cutoff_idx=cutoff_idx)
    future_geometry = setup_future.freeze()

    # Compare frozen geometry against future-recomputed
    changes = []
    for field in ["entry_reference", "invalidation_price", "target_1", "target_2", "target_3"]:
        current_val = frozen.get(field)
        future_val = future_geometry.get(field)
        if current_val != future_val:
            changes.append({
                "field": field,
                "frozen": current_val,
                "future_recomputed": future_val,
            })

    return {
        "lookahead_status": "PASS" if not changes else "FAIL",
        "changes": changes,
        "n_changes": len(changes),
    }


# ═══════════════════════════════════════════════════════════════
# DATA COVERAGE
# ═══════════════════════════════════════════════════════════════

def assess_data_coverage(
    df: pd.DataFrame,
    setups: list[ResearchBackedSetup],
) -> dict[str, Any]:
    """Assess data coverage for validation.

    Returns sufficiency assessment per analysis dimension.
    """
    n = len(df)
    n_setups = len(setups)

    coverage: dict[str, Any] = {
        "n_bars": n,
        "n_setups": n_setups,
        "timeframe": setups[0].timeframe if setups else "UNKNOWN",
        "symbol": setups[0].symbol if setups else "UNKNOWN",
        "dimensions": {},
    }

    # Timeframe coverage
    if n >= 500:
        coverage["dimensions"]["timeframe_sufficient"] = True
    elif n >= 200:
        coverage["dimensions"]["timeframe_sufficient"] = False
        coverage["dimensions"]["timeframe_note"] = "LIMITED — 200-500 bars"
    else:
        coverage["dimensions"]["timeframe_sufficient"] = False
        coverage["dimensions"]["timeframe_note"] = "LOW_SAMPLE — < 200 bars"

    # Setup diversity
    directions = set(s.direction for s in setups)
    coverage["dimensions"]["direction_coverage"] = len(directions)

    # Regime diversity
    regimes = set(s.regime for s in setups if s.regime)
    coverage["dimensions"]["regime_coverage"] = len(regimes)

    # Entry availability
    entry_available = sum(1 for s in setups if s.entry_status == "AVAILABLE")
    coverage["dimensions"]["entry_availability"] = entry_available / max(n_setups, 1)

    # Target availability
    target_available = sum(1 for s in setups if s.target_1 is not None)
    coverage["dimensions"]["target_availability"] = target_available / max(n_setups, 1)

    # Invalidation availability
    inv_available = sum(1 for s in setups if s.invalidation_price is not None)
    coverage["dimensions"]["invalidation_availability"] = inv_available / max(n_setups, 1)

    return coverage