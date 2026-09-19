# Quality Calibration Report

**Dataset**: `setup_outcomes` — 10707 records | Generated: 2026-09-16

## Quality Score Distribution

| Stat | Value |
|------|-------|
| Count | 10698 |
| Mean | 0.5089 |
| Median | 0.6000 |
| Std | 0.2611 |
| Min | 0.0000 |
| Max | 0.9000 |
| P10 | 0.0000 |
| P25 | 0.4900 |
| P75 | 0.6770 |
| P90 | 0.7350 |

## Histogram Buckets

| Bucket | n | WR | Avg R |
|--------|---|-----|-------|
| [0.0-0.1) | 2021 | 0.3335 | -0.4998 |
| [0.3-0.4) | 22 | 0.2273 | -0.2109 |
| [0.4-0.5) | 729 | 0.1495 | -1.3387 |
| [0.5-0.6) | 2378 | 0.3305 | -0.8528 |
| [0.6-0.7) | 3408 | 0.4947 | 0.1464 |
| [0.7-0.8) | 1607 | 0.6248 | 0.5084 |
| [0.8-0.9) | 290 | 0.5207 | 0.0893 |
| [0.9-1.0) | 243 | 0.7037 | 0.5000 |

## Quality Quartile Calibration

| Quartile | n | WR | WR 95% CI | Avg R |
|----------|---|-----|-----------|-------|
| Q1 (0-25%) | 2677 | 0.2910 | [0.2907, 0.2913] | -0.6651 |
| Q2 (25-50%) | 3545 | 0.4279 | [0.4277, 0.4282] | -0.5179 |
| Q3 (50-75%) | 1806 | 0.3981 | [0.3976, 0.3986] | -0.0250 |
| Q4 (75-100%) | 2670 | 0.5884 | [0.5880, 0.5888] | 0.4142 |

## Regime × Quality Interaction

| Regime | n | Avg QS | WR | Avg R |
|--------|---|--------|-----|-------|
| DOWNTREND | 985 | 0.5885 | 0.5655 | 0.2207 |
| DOWNTREND_STRONG | 839 | 0.4249 | 0.3921 | -0.5840 |
| DOWNTREND_WEAK | 2428 | 0.4077 | 0.3575 | -0.4708 |
| RANGE | 680 | 0.4479 | 0.3662 | -0.3099 |
| RANGE_HIGH_VOL | 415 | 0.4666 | 0.1060 | -2.9287 |
| RANGE_LOW_VOL | 1313 | 0.6542 | 0.4684 | 0.5508 |
| UPTREND | 2335 | 0.6239 | 0.6527 | 0.4296 |
| UPTREND_STRONG | 389 | 0.4127 | 0.2314 | -0.6686 |
| UPTREND_WEAK | 1314 | 0.4138 | 0.2359 | -0.8977 |

## Strategy × Quality Interaction

| Strategy | n | Avg QS | WR |
|----------|---|--------|-----|
| auto | 1597 | 0.4751 | 0.4289 |
| bv_test | 360 | 0.7000 | 0.6500 |
| fallback_r | 45 | 0.4000 | 0.0000 |
| fallback_test | 40 | 0.7000 | 1.0000 |
| fb_track | 32 | 0.7000 | 1.0000 |
| indicator_downtrend_long | 637 | 0.3701 | 0.2951 |
| indicator_downtrend_short | 2611 | 0.4211 | 0.3822 |
| indicator_range_long | 1031 | 0.5683 | 0.2502 |
| indicator_range_short | 681 | 0.6712 | 0.5800 |
| indicator_short | 41 | 0.6020 | 0.5854 |
| indicator_uptrend_long | 1577 | 0.4193 | 0.2365 |
| indicator_uptrend_short | 124 | 0.3272 | 0.1935 |
| la_test | 270 | 0.6000 | 1.0000 |
| rep_test | 270 | 0.6000 | 0.5000 |
| sync_test | 45 | 0.7000 | 1.0000 |
| ts_test | 150 | 0.7000 | 1.0000 |
| weight_test | 855 | 0.7000 | 0.6526 |
| wf_test | 270 | 0.6000 | 0.5000 |

## Timeframe × Quality Interaction

| Timeframe | n | Avg QS | WR |
|-----------|---|--------|-----|
| 1d | 279 | 0.6949 | 0.9534 |
| 1h | 10076 | 0.4982 | 0.3993 |
| 4h | 342 | 0.6711 | 0.8684 |

## Walk-Forward / OOS Analysis

| Period | n | WR | Avg QS | Avg R |
|--------|---|-----|--------|-------|
| P1_early | 3569 | 0.3802 | 0.5658 | -0.3817 |
| P2_mid | 3569 | 0.3488 | 0.3382 | -0.3370 |
| P3_late | 3569 | 0.5559 | 0.6230 | 0.0010 |

## Feature Stability Across Walk-Forward Periods

| Feature | P1 (early) | P2 (mid) | P3 (late) |
|---------|-----------|----------|----------|
| supporting_evidence | 0.0694 | 0.0502 | 0.0195 |
| conflicting_evidence | 0.0694 | 0.0502 | 0.0195 |
| regime_compatibility | 0.0486 | -0.0415 | 0.0403 |
| structure_quality | 0.0481 | -0.0084 | -0.0195 |
| entry_quality | 0.1174 | 0.1013 | 0.0615 |
| risk_rr | 0.0765 | 0.0235 | 0.0000 |
| invalidation_clarity | -0.0329 | -0.0760 | -0.0452 |
| strategy_agreement | -0.0426 | 0.0624 | -0.0111 |
| formation_chain | 0.0018 | -0.0907 | -0.2157 |
| structure_alignment | 0.0486 | -0.0415 | 0.0403 |
| volatility_context | N/A | 0.0278 | 0.1363 |
| liquidity_balance | 0.0000 | 0.0000 | -0.3686 |
| momentum_at_entry | 0.3947 | 0.4689 | 0.6202 |
| volume_ratio | N/A | N/A | N/A |
| regime_weighted_quality | 0.0859 | 0.0790 | 0.0976 |

## Feature → Outcome Correlations

| Feature | r | n | 95% CI | Predictive Status |
|---------|---|---|--------|-------------------|
| supporting_evidence | 0.0575 | 7865 | [0.0355, 0.0795] | weak |
| conflicting_evidence | 0.0575 | 7865 | [0.0354, 0.0795] | weak |
| regime_compatibility | 0.0041 | 7865 | [-0.0180, 0.0262] | none |
| structure_quality | -0.0064 | 7865 | [-0.0285, 0.0157] | none |
| entry_quality | 0.1010 | 7865 | [0.0791, 0.1229] | weak |
| risk_rr | 0.0317 | 7865 | [0.0096, 0.0538] | none |
| invalidation_clarity | -0.0576 | 7865 | [-0.0796, -0.0355] | weak |
| strategy_agreement | -0.0173 | 7865 | [-0.0394, 0.0048] | none |
| formation_chain | -0.0752 | 7865 | [-0.0971, -0.0531] | weak |
| structure_alignment | 0.0041 | 7865 | [-0.0180, 0.0262] | none |
| volatility_context | 0.0677 | 4251 | [0.0377, 0.0975] | weak |
| liquidity_balance | -0.2775 | 10707 | [-0.2949, -0.2599] | predictive |
| momentum_at_entry | 0.4382 | 8167 | [0.4205, 0.4556] | predictive |
| regime_weighted_quality | 0.0749 | 7865 | [0.0529, 0.0969] | weak |

## Feature Redundancy (|r| > 0.3)

| Feature 1 | Feature 2 | r | n |
|-----------|-----------|---|---|
| supporting_evidence | conflicting_evidence | 1.0000 | 7865 |
| regime_compatibility | formation_chain | 0.3546 | 7865 |
| regime_compatibility | structure_alignment | 1.0000 | 7865 |
| structure_quality | strategy_agreement | 0.4471 | 7865 |
| structure_quality | formation_chain | 0.4317 | 7865 |
| structure_quality | volatility_context | -0.6432 | 4251 |
| entry_quality | strategy_agreement | -0.5332 | 7865 |
| risk_rr | regime_weighted_quality | -0.3526 | 7865 |
| strategy_agreement | formation_chain | 0.5502 | 7865 |
| formation_chain | structure_alignment | 0.3546 | 7865 |

## Regime × Quality Detailed (WR by quartile within regime)

| Regime | QS Bin | n | WR | Notes |
|--------|--------|---|-----|-------|
| DOWNTREND | low | 271 | 0.4317 | |
| DOWNTREND | mid | 540 | 0.6593 | |
| DOWNTREND | high | 174 | 0.4828 | |
| DOWNTREND_STRONG | low | 268 | 0.4478 | |
| DOWNTREND_STRONG | mid | 362 | 0.3232 | |
| DOWNTREND_STRONG | high | 209 | 0.4402 | |
| DOWNTREND_WEAK | low | 700 | 0.3486 | |
| DOWNTREND_WEAK | mid | 1124 | 0.3541 | |
| DOWNTREND_WEAK | high | 604 | 0.3742 | |
| RANGE | low | 178 | 0.3820 | |
| RANGE | mid | 346 | 0.3757 | |
| RANGE | high | 156 | 0.3269 | |
| RANGE_HIGH_VOL | low | 109 | 0.0367 | |
| RANGE_HIGH_VOL | mid | 251 | 0.0120 | |
| RANGE_HIGH_VOL | high | 55 | 0.6727 | |
| RANGE_LOW_VOL | low | 329 | 0.2492 | |
| RANGE_LOW_VOL | mid | 662 | 0.5015 | |
| RANGE_LOW_VOL | high | 322 | 0.6242 | |
| UPTREND | low | 1278 | 0.6033 | |
| UPTREND | mid | 739 | 0.7104 | |
| UPTREND | high | 318 | 0.7170 | |
| UPTREND_STRONG | low | 120 | 0.2500 | |
| UPTREND_STRONG | mid | 180 | 0.2278 | |
| UPTREND_STRONG | high | 89 | 0.2135 | |
| UPTREND_WEAK | low | 444 | 0.1937 | |
| UPTREND_WEAK | mid | 583 | 0.2401 | |
| UPTREND_WEAK | high | 287 | 0.2927 | |

## Key Findings

1. **Quality score is weakly predictive**: Q4 (75-100%) WR=0.588 vs Q1 WR=0.291
2. **momentum_at_entry is the strongest feature**: r=0.438 with outcome
3. **liquidity_balance shows negative correlation**: r=-0.278 — higher touch counts associate with misses
4. **High redundancy**: supporting_evidence ↔ conflicting_evidence (r=1.0), regime_compatibility ↔ formation_chain (r=0.35)
5. **Regime matters**: UPTREND regimes show WR>0.65 at high QS; RANGE_HIGH_VOL shows extreme negative avg R (-2.93)
6. **Walk-forward instability**: P1 WR=0.380, P2 WR=0.349, P3 WR=0.556 — quality degrades in mid-period
7. **volume_ratio**: No data available — cannot assess
8. **structure_alignment**: Proxy only (structure_type NULL) — use regime_compatibility instead
