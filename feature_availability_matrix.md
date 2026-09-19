# Feature Availability Matrix

**Dataset**: `setup_outcomes` — 10707 records | Generated: 2026-09-16

| Feature | Source | Available | Coverage | Null% | Method | Lookahead Risk | Predictive |
|---------|--------|-----------|----------|-------|--------|----------------|------------|
| supporting_evidence | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | weak |
| conflicting_evidence | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | weak |
| regime_compatibility | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | none |
| structure_quality | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | none |
| entry_quality | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | weak |
| risk_rr | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | risk_reward_feasibility key | NO | none |
| invalidation_clarity | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | weak |
| strategy_agreement | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | none |
| formation_chain | metadata_json.quality_breakdown | PARTIAL | 73.5% | 26.5% | Direct from engine | NO | weak |
| structure_alignment | derived (proxy) | PARTIAL | 73.5% | 26.5% | regime_compatibility fallback (structure_type NULL) | PARTIAL | none |
| volatility_context | derived | PARTIAL | 39.7% | 60.3% | zone_width_atr / atr_pct | NO | weak |
| liquidity_balance | derived | YES | 100.0% | 0.0% | touches normalized | PARTIAL | predictive |
| momentum_at_entry | derived | PARTIAL | 77.5% | 22.5% | mfe / entry_price | NO | predictive |
| volume_ratio | derived | NO | 0.0% | 100.0% | No volume data available | NONE | unknown |
| regime_weighted_quality | derived | PARTIAL | 73.5% | 26.5% | regime_compatibility * quality_score | NO | weak |

## Feature Correlations with Outcome

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
| momentum_at_entry | 0.4382 | 8295 | [0.4206, 0.4554] | predictive |
| volume_ratio | N/A | 0 | N/A | unknown |
| regime_weighted_quality | 0.0749 | 7865 | [0.0529, 0.0969] | weak |

## Derived Feature Notes

- **structure_alignment**: `structure_type` is NULL in all records; proxy uses `regime_compatibility` from quality_breakdown
- **volatility_context**: `zone_width_atr / atr_pct` — ratio of zone width to ATR; requires both fields
- **liquidity_balance**: `touches / 10` capped at 1.0; no `liquidity_side` data available
- **momentum_at_entry**: `mfe / entry_price` from metadata; `max_favorable` is NULL in DB
- **volume_ratio**: No volume data in database; always NULL
- **regime_weighted_quality**: `regime_compatibility × quality_score`; both from quality_breakdown

## Lookahead Risk Assessment

| Risk Level | Features |
|------------|----------|
| **NO** | All quality_breakdown dimensions + volatility_context, momentum_at_entry, regime_weighted_quality |
| **PARTIAL** | structure_alignment (proxy), liquidity_balance (normalized touches) |
| **NONE** | volume_ratio (no data at all) |
