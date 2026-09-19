# Feature Engineering Research: Outcome-Predictive Features for Quality Scoring

## Data Overview

- **Table**: `setup_outcomes` in `market_hq.db`
- **Total rows**: 10,002 (9,999 closed outcomes, 3 open)
- **Rows with full price data**: 8,087
- **Rows with atr_pct**: 4,028 (50.2%)
- **Rows with quality_score**: 9,995 (99.9%)
- **Rows with structure_type/liquidity_side**: 5,940 (all empty strings — not populated)
- **Overall win rate** (pnl_pct > 0): 35.7%
- **Overall avg pnl**: -0.41%

---

## FEATURE-BY-FEATURE ANALYSIS

### STRUCTURE

| Feature | Computable? | Variance | Missingness | Correlation (r) | Monotonicity | Sample |
|---------|-------------|----------|-------------|-----------------|--------------|--------|
| swing_depth | NO — needs OHLCV bars | — | 100% | — | — | 0 |
| bos_magnitude | NO — needs OHLCV bars | — | 100% | — | — | 0 |
| choch_magnitude | NO — needs OHLCV bars | — | 100% | — | — | 0 |
| distance_from_structure | NO — zone_width_atr is binary (0/0.5) | Zero | 41% | None | None | 0 |
| structure_confirmations | PARTIAL — touches column | Zero (binary 0/1) | 50.2% | None | None | 4,028 |
| structure_age | NO — no structure timestamps | — | 100% | — | — | 0 |

**Verdict**: None computable from current schema. `touches` is binary with zero variance. `structure_type` and `liquidity_side` columns exist but are empty strings for all 5,940 populated rows.

### ENTRY

| Feature | Computable? | Variance | Missingness | Correlation (r) | Monotonicity | Sample |
|---------|-------------|----------|-------------|-----------------|--------------|--------|
| entry_to_zone_distance | NO — needs zone boundaries | — | 100% | — | — | 0 |
| atr_normalized_distance | PARTIAL — stop_atr (4,028 rows) | Low | 50.2% | -0.001 | Mixed | 4,028 |
| confirmation_strength | NO — no confirmation metric | — | 100% | — | — | 0 |
| candle_displacement | NO — needs OHLCV bars | — | 100% | — | — | 0 |
| momentum_at_entry | NO — needs price series | — | 100% | — | — | 0 |
| volume_confirmation | NO — no volume data | — | 100% | — | — | 0 |

**Verdict**: `stop_atr` (stop distance / ATR) has low variance and zero predictive power (r=-0.001). No entry features are computable from current data.

### RISK

| Feature | Computable? | Variance | Missingness | Correlation (r) | Monotonicity | Sample |
|---------|-------------|----------|-------------|-----------------|--------------|--------|
| stop_distance / ATR | YES — stop_atr | Low | 50.2% | -0.001 | Mixed | 4,028 |
| target_distance / ATR | YES — target_atr | Low | 50.2% | -0.008 | Mixed | 4,028 |
| RR | YES | Moderate | 0% | 0.08 | Positive (weak) | 8,087 |
| expected_excursion | NO — max_favorable/max_adverse are NULL | — | 100% | — | — | 0 |
| distance_to_opposing_liquidity | NO — no liquidity data | — | 100% | — | — | 0 |

**Verdict**: RR has weak but positive monotonic relationship with pnl (r=0.08, higher RR → better avg_pnl). Stop/target ATR ratios show no predictive power. Expected excursion unavailable.

### REGIME

| Feature | Computable? | Variance | Missingness | Correlation (r) | Monotonicity | Sample |
|---------|-------------|----------|-------------|-----------------|--------------|--------|
| ADX | NO — no ADX data | — | 100% | — | — | 0 |
| ATR_percentile | YES — from atr_pct | High | 50.2% | -0.28 | Negative | 4,028 |
| volume_percentile | NO — no volume data | — | 100% | — | — | 0 |
| trend_strength | NO — no metric | — | 100% | — | — | 0 |
| volatility_state | PARTIAL — atr_pct proxy | High | 50.2% | -0.28 | Negative | 4,028 |
| structure_alignment | YES — regime x direction | Moderate | 0% | -0.004 | None | 8,087 |

**Verdict**: `atr_pct` (volatility proxy) is the strongest numeric feature: r=-0.28 with pnl, clear negative monotonicity. Low volatility (atr_pct 0.7-1.0) → 37% WR; high volatility (atr_pct 1.6+) → 5% WR. `structure_alignment` has zero predictive power.

### LIQUIDITY

| Feature | Computable? | Variance | Missingness | Correlation (r) | Monotonicity | Sample |
|---------|-------------|----------|-------------|-----------------|--------------|--------|
| sweep_magnitude | NO — no sweep data | — | 100% | — | — | 0 |
| liquidity_distance | NO — no liquidity data | — | 100% | — | — | 0 |
| repeated_touches | PARTIAL — touches column | Zero (binary) | 50.2% | None | None | 4,028 |
| liquidity_age | NO — no liquidity timestamps | — | 100% | — | — | 0 |
| distance_to_opposing_liquidity | NO — no liquidity data | — | 100% | — | — | 0 |

**Verdict**: None computable. `touches` is binary with zero variance.

---

## KEY FINDINGS

### 1. quality_score — BEST SINGLE FEATURE (Monotonic, Strong Bucket Separation)

| Quality Score | n | Avg PnL | Win Rate | Target Rate |
|--------------|---|---------|----------|-------------|
| 0.7-0.8 | 1,515 | +0.50 | 61.8% | 61.8% |
| 0.8+ | 425 | +0.26 | 59.8% | 59.8% |
| 0.5-0.7 | 5,370 | -0.29 | 41.6% | 41.6% |
| 0.3-0.5 | 661 | -1.18 | 17.3% | 17.3% |
| 0-0.3 | 2,021 | -0.50 | 33.4% | 33.4% |

- r=0.06 with pnl_pct (weak linear correlation but strong bucket separation)
- Clear monotonic: higher QS → higher win rate
- **Exception**: DOWNTREND_WEAK + high QS has 3.4% WR (n=29, likely noise)

### 2. atr_pct — STRONGEST VOLATILITY FEATURE (Negative Monotonic)

| atr_pct Range | n | Avg PnL | Win Rate |
|--------------|---|---------|----------|
| 0.7-1.0 | 1,523 | -0.07 | 37.4% |
| 1.0-1.3 | 748 | +0.07 | 42.3% |
| 1.3-1.6 | 617 | -0.31 | 35.7% |
| 1.6+ | 370 | -3.41 | 5.4% |

- r=-0.28 with pnl_pct (moderate negative correlation)
- Decile 5 (mid-atr): 52.6% WR, avg_pnl=+0.52 (best)
- Decile 10 (highest atr): 5.0% WR, avg_pnl=-3.38 (worst)

### 3. regime — STRONGEST CATEGORICAL FEATURE

| Regime | Direction | n | Avg PnL | Win Rate |
|--------|-----------|---|---------|----------|
| RANGE_LOW_VOL | SHORT | 592 | +1.24 | 58.6% |
| UPTREND | LONG | 1,938 | +0.43 | 65.1% |
| DOWNTREND | SHORT | 862 | +0.23 | 56.8% |
| RANGE_LOW_VOL | LONG | 691 | -0.05 | 36.6% |
| RANGE_HIGH_VOL | LONG | 297 | -3.70 | 0.0% |
| UPTREND_WEAK | LONG | 1,171 | -0.86 | 23.7% |

### 4. quality_score x regime — STRONGEST INTERACTION

| Regime | QS Level | n | Avg PnL | Win Rate |
|--------|----------|---|---------|----------|
| UPTREND | high | 659 | +0.73 | 81.9% |
| RANGE_LOW_VOL | high | 460 | +1.23 | 61.5% |
| DOWNTREND | high | 401 | +0.31 | 59.6% |
| DOWNTREND_WEAK | high | 29 | -2.61 | 3.4% |
| UPTREND_WEAK | high | 252 | -0.85 | 27.0% |
| RANGE_HIGH_VOL | low | 377 | -3.04 | 10.3% |

### 5. duration_bars — WEAK MODERATE FEATURE

| Duration | n | Avg PnL | Win Rate |
|----------|---|---------|----------|
| 60+ bars | 230 | +1.96 | 81.3% |
| 31-60 bars | 283 | -0.71 | 43.1% |
| 6-15 bars | 2,850 | -0.18 | 38.1% |
| 1-5 bars | 3,073 | -0.56 | 31.0% |

### 6. RR — WEAK BUT MONOTONIC

| RR Range | n | Avg PnL | Win Rate |
|----------|---|---------|----------|
| RR>2 | 2,036 | -0.15 | 32.3% |
| RR 1-2 | 2,285 | -0.43 | 35.9% |
| RR<1 | 2,019 | -0.58 | 40.0% |

---

## PROMISING FEATURES SUMMARY

| Rank | Feature | Type | Predictive Power | Action |
|------|---------|------|-----------------|--------|
| 1 | **quality_score** | Numeric | Strong (bucket) | Use as primary feature |
| 2 | **atr_pct** | Numeric | Strong (negative monotonic) | Add as volatility feature |
| 3 | **regime** | Categorical | Very strong | Use as categorical feature |
| 4 | **quality_score x regime** | Interaction | Very strong | Add interaction term |
| 5 | **duration_bars** | Numeric | Moderate | Use with caution |
| 6 | **RR** | Numeric | Weak monotonic | Low priority |

## NOT PROMISING FEATURES

| Feature | Reason |
|---------|--------|
| stop_atr / target_atr | Zero predictive power (r≈0) |
| structure_alignment | r=-0.004, no pattern |
| touches | Binary, zero variance |
| zone_width_atr | Binary, zero variance |
| RR (alone) | Weak, non-monotonic in deciles |

## MISSING DATA — REQUIRES SCHEMA CHANGES

### Critical Gaps (no way to compute)
- **swing_depth, bos_magnitude, choch_magnitude** — need OHLCV bar data
- **distance_from_structure** — need zone boundary data
- **structure_age** — need structure formation timestamps
- **entry_to_zone_distance** — need zone boundaries
- **confirmation_strength** — need confirmation metric
- **candle_displacement** — need OHLCV bar data
- **momentum_at_entry** — need price series
- **volume_confirmation** — need volume data
- **ADX** — need price series
- **volume_percentile** — need volume data
- **trend_strength** — need trend metric
- **sweep_magnitude** — need sweep data
- **liquidity_distance** — need liquidity data
- **liquidity_age** — need liquidity timestamps
- **expected_excursion** — max_favorable/max_adverse are NULL

### Partial Gaps (50% missing)
- atr_pct, zone_width_atr, touches — only 4,028 of 8,087 rows populated

### Schema Issues
- `structure_type` and `liquidity_side` columns exist but are empty strings (5,940 rows)
- `metadata_json` has setup_id/engine/version but no feature data

## RECOMMENDATIONS

1. **Populate structure_type and liquidity_side** — these columns exist but are empty. The setup engine should fill them.

2. **Add OHLCV bar data** — swing_depth, BOS magnitude, CHoCH magnitude, candle_displacement, momentum_at_entry all require bar-level data. Consider adding a `bars_json` or similar column.

3. **Add volume data** — volume_confirmation and volume_percentile need volume fields.

4. **Add liquidity tracking** — sweep_magnitude, liquidity_distance, liquidity_age, distance_to_opposing_liquidity all need liquidity event data.

5. **Add ADX** — can be computed from price data if added to schema.

6. **Fix expected_excursion** — max_favorable/max_adverse are NULL for all rows; the engine should populate these.

7. **Quality score is the strongest predictor** — the current quality_score already captures much of the predictive signal. Focus on improving the quality score algorithm rather than engineering new features from incomplete data.

8. **Regime x Quality interaction is the strongest combined signal** — 81.9% win rate for UPTREND + high quality vs 23.7% for UPTREND_WEAK + low quality. This interaction alone explains most of the predictive power.
