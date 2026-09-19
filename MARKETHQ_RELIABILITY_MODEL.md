# MARKETHQ RELIABILITY MODEL

**Date:** 2026-09-16
**Phase:** H

---

## Reliability Profile

Each agent/strategy gets a reliability profile:

- profile_id
- name
- profile_type (agent | strategy | strategy_family)
- family
- regime
- timeframe
- asset
- direction_agreement
- outcome_correlation
- target_hit_rate
- invalidation_rate
- avg_realized_r
- median_realized_r
- sample_size
- stability_score
- temporal_stability
- regime_specific

## Reliability ≠ Permanent Quality

Reliability is HISTORICAL, not permanent.
It changes as new data arrives.
Small samples flagged as LOW_SAMPLE.

## Regime-Specific Reliability

Global reliability AND regime-specific:

Trend Agent:
- UPTREND: n=50, target_rate=0.65
- DOWNTREND: n=30, target_rate=0.40
- RANGE: n=20, target_rate=0.35

Each regime needs n ≥ 30 for reliability.

## Strategy Family Reliability

7 families × regime × timeframe × asset.

Not ranking — context dependency analysis.

## Calibration

Confidence buckets → outcome rates.

Not probability calibration.
Just empirical observation.

## Agent Reliability Limitations

1. Correlation ≠ causation
2. Past ≠ future
3. Small sample = unreliable
4. Regime change invalidates old profiles
5. Single asset = limited generalizability