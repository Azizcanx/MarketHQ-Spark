# Feature Predictiveness Analysis: quality_v3 Dimensions

**Source:** market_hq.db → setup_outcomes (7,232 closed outcomes with quality_breakdown)
**Date:** 2026-09-16

---

## Summary

None of the 9 quality_v3 dimensions show meaningful predictive power against actual R-multiple outcomes. All Pearson correlations are near zero (|r| < 0.11). The root cause is severe ceiling effects — most dimensions have very few distinct values and are nearly constant.

---

## Per-Dimension Results

| Dimension | n | Mean R | Win Rate | r (Pearson) | Stability | Interpretation |
|-----------|---|--------|----------|-------------|-----------|----------------|
| regime_compatibility | 7,232 | -0.403 | 35.7% | +0.0002 | -0.006 | Negligible |
| structure_quality | 7,232 | -0.403 | 35.7% | +0.070 | +0.039 | Negligible |
| entry_quality | 7,232 | -0.403 | 35.7% | +0.102 | +0.114 | Weak |
| formation_chain | 7,232 | -0.403 | 35.7% | -0.022 | -0.044 | Negligible |
| risk_reward_feasibility | 7,232 | -0.403 | 35.7% | +0.066 | +0.041 | Negligible |
| strategy_agreement | 7,232 | -0.403 | 35.7% | +0.012 | -0.001 | Negligible |
| invalidation_clarity | 7,232 | -0.403 | 35.7% | -0.031 | -0.031 | Negligible |
| supporting_evidence | 7,232 | -0.403 | 35.7% | +0.037 | +0.037 | Negligible |
| conflicting_evidence | 7,232 | -0.403 | 35.7% | +0.037 | +0.037 | Negligible |

## Data Quality Issues

### Ceiling Effects (Critical)
- **invalidation_clarity**: 99.8% = 1.0 (only 14 rows differ)
- **entry_quality**: 75.8% = 0.65 (only 3 distinct values)
- **risk_reward_feasibility**: 83.4% = 0.55 (only 2 distinct values)
- **structure_quality**: 50.8% = 0.4 (only 4 distinct values)
- **formation_chain**: 55% = 0.833 (only 3 distinct values)
- **regime_compatibility**: 23.4% = 0.85 (11 distinct values, heavily skewed)

### Winners vs Losers Mean Differences
All differences are trivially small (|diff| < 0.03):
- supporting_evidence: +0.019 (largest)
- conflicting_evidence: +0.028
- entry_quality: +0.013

### Other Checks
- **Missingness**: 0% across all dimensions
- **Leakage check**: No dimension correlates with quality_score (all r ≈ 0.000)
- **Inter-dimension correlations**: None exceed |r| > 0.3 (dimensions are independent)
- **Quality_score vs outcome**: r = +0.091 (also negligible)

## Interpretation

1. **Dimensions are not predictive of outcomes** — no dimension distinguishes winners from losers in a statistically meaningful way.

2. **Dimensions appear to be assigned heuristically** — the limited variance and lack of correlation with quality_score suggests the quality_breakdown values are assigned by rule-based logic rather than computed from outcome data.

3. **The quality scoring system is broken** — quality_score itself has negligible correlation with outcome (r=0.091), and the quality_breakdown dimensions don't improve on that.

4. **Strategy agreement has the most variance** (238 distinct values) but still shows no predictive power (r=0.012).

5. **Overall strategy performance is negative** — mean outcome is -0.403R with a 35.7% win rate, meaning the setups are losing money on average.

## Recommendations

1. **Fix the quality_breakdown computation** — dimensions need more variance to be useful. Current values are mostly constant.
2. **Remove invalidation_clarity from the model** — 99.8% ceiling makes it useless as a feature.
3. **Investigate why quality_score doesn't correlate with outcomes** — the scoring logic may be misaligned with actual performance.
4. **Consider dropping all 9 dimensions** as features until the quality computation is fixed — they add noise, not signal.
