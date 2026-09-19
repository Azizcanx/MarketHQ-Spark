# MARKETHQ ADAPTIVE RESEARCH REPORT

**Date:** 2026-09-16
**Phase:** H

---

## Adaptive Research Approach

Phase H implements OFFLINE adaptive research only.
No automatic weight deployment. No production promotion.

## Three Approaches Compared

1. **Fixed weights** — baseline, no adaptation
2. **Regime-aware weights** — weights per regime context
3. **Reliability-adjusted weights** — weights adjusted by historical reliability

All tested on same historical windows.
Chronological split, no random shuffle.

## Weight Proposal System

Every weight change is a PROPOSAL, not deployment.

Proposal contains:
- current value
- proposed value
- reason (evidence-based)
- walk-forward windows
- baseline comparison
- previous Adaptive V1 comparison
- status: PROPOSED (not active)

Human/research approval required for any change.

## Adaptive V1 Comparison

Previous Adaptive V1 failure benchmarks:
- 7 weights, 1 reached 54%
- 6/7 contexts n<30
- 71% fallback rate
- DOWNTREND_WEAK negative expectancy
- Train/validation baseline shift
- Adaptive underperformed baseline
- Correlation penalty too strong

New adaptive research includes `previous_adaptive_v1_comparison` field
on every weight proposal.

## Champion/Challenger

Offline comparison framework:
- Champion = current baseline
- Challenger = research proposal
- Compare on: Avg R, Median R, target rate, invalidation, MFE, MAE, stability, sample, worst window, drift
- Winner = better historical performance
- NOT auto-promoted

## Results Format

Every adaptive research result:
- experiment_id
- hypothesis
- config
- baseline_comparison
- champion_metrics
- challenger_metrics
- winner
- status: PROPOSED / UNDER_REVIEW / REJECTED

## Key Constraint

Adaptive research produces WEIGHT PROPOSALS.
NOT active weight changes.
NOT production deployment.
NOT strategy activation.
NOT quality weight replacement.

All changes require explicit human/research approval.