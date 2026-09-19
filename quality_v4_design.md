# Quality V4 — Design Document (Updated)

**Date:** 2026-09-16
**Status:** Research/Experimental
**Purpose:** Fix ceiling effects in quality scoring by replacing constant inputs and additive scoring with continuous features and multiplicative scoring. Added feature usage tracking.

---

## Root Cause (from ceiling_effect_analysis.md)

| Feature | Problem | Records | Effect |
|---------|---------|---------|--------|
| `zone_width_atr` | Constant 0.5 | 4,028 | entry_quality ceiling at 0.65 |
| `touches` | Constant 1 | 4,028 | entry_quality ceiling at 0.65 |
| `structure_type` | Constant "" | 5,940 | structure_quality ceiling at 0.4 |

Additive base+bonus scoring with constant inputs → constant outputs → ceiling effects.

---

## Actual Data Availability (verified from market_hq.db, 10,707 records)

| Feature | Non-NULL | % | Notes |
|---------|----------|---|-------|
| `atr_pct` | 4,251 | 39.7% | PRIMARY variable feature for entry/volatility |
| `zone_width_atr` | 6,645 | 62.1% | **Always 0.5 when populated** — constant |
| `touches` | 6,645 | 62.1% | **Always 1 when populated** — constant |
| `structure_type` | 6,645 | 62.1% | **Always "" when populated** — empty |
| `liquidity_side` | 6,645 | 62.1% | **Always "" when populated** — empty |
| `entry_price` | 8,313 | 77.6% | Used for RR and invalidation distance |
| `invalidation_price` | 8,313 | 77.6% | Used for RR and invalidation distance |
| `target_price` | 8,313 | 77.6% | Used for RR computation |
| `max_favorable` | 0 | 0% | **ALL NULL** — excursion ratio unavailable |
| `max_adverse` | 0 | 0% | **ALL NULL** — excursion ratio unavailable |
| `pnl_pct` | 10,704 | 99.97% | Momentum proxy |
| `duration_bars` | 10,707 | 100% | Time proxy |

**Key insight:** atr_pct, zone_width_atr, touches, structure_type, liquidity_side all come from the same 4,251 records. When atr_pct is available, the other 4 features are also available but constant/empty.

---

## Fixes Applied

### 1. entry_quality (multiplicative, continuous)

**Old (v2):** `base=0.3 + width_bonus + touches_bonus + source_bonus + proximity_bonus`
- zone_width_atr always 0.5 → sweet spot bonus always fires
- touches always 1 → only +0.05, never reaches +0.15/+0.20
- 3 distinct values: 0.65, 0.70, 0.80

**New (v4):** `base=0.5 * atr_factor * touches_factor * source_factor * proximity_factor * width_factor * quality_factor`
- **atr_pct as primary zone width measure** (variable, 100 unique values when available)
- zone_width_atr used only as fallback (constant 0.5 — limited discrimination)
- touches used when > 0 (constant 1 when available — limited discrimination)
- structure_type checked for non-empty before structure proximity
- Zone width vs atr_pct ratio (adaptive sweet spot)
- Expected variance: 0.15–0.35
- Expected correlation with outcome R: |r| > 0.15

### 2. invalidation_clarity (continuous distance)

**Old (v2):** `base=0.3 + clarity("clear")=+0.3 + distance(0.5-3.0 ATR)=+0.25 + type("structural")=+0.15 = 1.0`
- 99.8% at 1.0 ceiling
- Only 14 rows at 0.95

**New (v4):** `base=0.4 * distance_factor * type_factor * clarity_factor * ratio_factor`
- **Distance computed from entry_price/invalidation_price** when available (ATR-normalized)
- Fallback to inv.distance_atr when prices unavailable
- Entry-to-invalidation ratio (distance from entry / ATR)
- Smooth falloff outside sweet spot (no hard clamping)
- Expected variance: 0.20–0.40
- Expected correlation with outcome R: |r| > 0.10

### 3. risk_rr (continuous RR mapping)

**Old (v2):** Stepped R:R mapping, most at 0.55 (R:R=2.0)
- 83.4% at 0.55 ceiling
- Only 2 distinct values: 0.385, 0.55

**New (v4):** `base=0.4 * rr_factor * excursion_factor * feasibility_factor`
- **RR computed from entry_price/invalidation_price/target_price** when available
- S-curve continuous R:R mapping (0.0–1.0)
- **max_favorable/max_adverse: ALL NULL** — excursion ratio uses breakeven_age/R:R proxy or duration_bars proxy
- Feasibility rating as multiplicative factor
- Expected variance: 0.15–0.30
- Expected correlation with outcome R: |r| > 0.10

### 4. structure_quality (NULL-safe)

**Old (v2):** Used structure_type even when empty string
- Empty structure_type → "basic" reason, low score

**New (v4):** Checks structure_type is non-empty before using
- Empty structure_type → returns 0.25 with "yapı_tipi_bos" reason
- Tracks feature usage: has_structure, structure_type

---

## New Dimensions

### 5. structure_alignment

**What:** How well market structure aligns with trade direction
**Input:** structure.structure_type + bias.direction
**Method:** Aligned types (BOS_UP+LONG, CHoCH_DOWN+SHORT) score high; counter-aligned score low
**Why:** A BOS_UP in a LONG direction is fundamentally different from BOS_UP in SHORT
**Expected variance:** 0.20–0.35
**Correlation target:** |r| > 0.05

### 6. volatility_context

**What:** Volatility state from atr_pct percentile distribution
**Input:** regime.atr_pct → percentile + volatility_state
**Method:** atr_percentile (0–1) + volatility_state (low/medium/high)
**Why:** Same setup in high vs low volatility has different quality implications
**Expected variance:** 0.25–0.40
**Correlation target:** |r| > 0.05

**Percentile thresholds (from market_hq.db):**
- P10=0.62, P25=0.73, P50=0.94, P75=1.34, P90=1.58
- Low: atr_pct < 0.73, Medium: 0.73–1.34, High: > 1.34

### 7. liquidity_balance

**What:** Ratio of buy-side to sell-side liquidity
**Input:** liquidity.buy_side_liquidity / sell_side_liquidity
**Method:** balance_ratio = min(buy, sell) / max(buy, sell); both sides present = higher score
**Why:** Balanced liquidity = more institutional presence = stronger setup
**Expected variance:** 0.15–0.30
**Correlation target:** |r| > 0.05

### 8. momentum_at_entry

**What:** Price momentum near entry zone
**Input:** entry_zone.width_atr + structure.displacement + source quality + pnl_pct + duration_bars
**Method:** displacement/width ratio + source quality + regime confidence + pnl/duration proxy
**Why:** Narrow zone + high displacement = strong momentum signal; positive pnl = momentum held
**Expected variance:** 0.15–0.30
**Correlation target:** |r| > 0.05

### 9. volume_ratio

**What:** Current volume vs average (proxy)
**Input:** regime.atr_pct (proxy) + regime.vol_ratio + evidence count + touches
**Method:** Volume proxy from ATR pct, vol_ratio, activity indicators
**Note:** No direct volume data in setup_outcomes — returns proxy score
**Expected variance:** 0.15–0.30
**Correlation target:** |r| > 0.05

### 10. regime_weighted_quality

**What:** Quality score modulated by regime compatibility
**Input:** overall_quality * regime_compatibility
**Method:** regime_weighted_quality = quality * regime_compatibility
**Why:** Same setup in different regimes has different quality
**Expected variance:** 0.10–0.25
**Correlation target:** |r| > 0.08

---

## Dimension Weights (V4)

| Dimension | Weight | Change from V2 |
|-----------|--------|----------------|
| supporting_evidence | 0.08 | 0.12 → 0.08 |
| conflicting_evidence | 0.06 | 0.08 → 0.06 |
| regime_compatibility | 0.08 | 0.12 → 0.08 |
| structure_quality | 0.08 | 0.12 → 0.08 |
| entry_quality | 0.12 | 0.14 → 0.12 |
| risk_reward_feasibility | 0.10 | 0.13 → 0.10 |
| strategy_agreement | 0.06 | 0.10 → 0.06 |
| invalidation_clarity | 0.06 | 0.08 → 0.06 |
| formation_chain | 0.08 | 0.11 → 0.08 |
| structure_alignment | 0.08 | NEW |
| volatility_context | 0.08 | NEW |
| liquidity_balance | 0.06 | NEW |
| momentum_at_entry | 0.06 | NEW |
| volume_ratio | 0.06 | NEW |
| regime_weighted_quality | 0.10 | NEW |
| **Total** | **1.00** | |

---

## Scoring Method: Multiplicative vs Additive

**Additive (v2):** `score = base + bonus1 + bonus2 + ...`
- Problem: constant inputs → constant bonuses → constant output (ceiling)
- Each bonus adds independently, so max score is always reachable

**Multiplicative (v4):** `score = base * factor1 * factor2 * ...`
- Each factor shifts the score multiplicatively
- Weak factors reduce the score significantly
- Strong factors increase it, but bounded by min_factor=0.3, max_factor=1.7
- No ceiling effect — if any dimension is weak, overall drops

---

## Feature Usage Tracking (NEW)

Each dimension scorer now returns feature usage info:
- `feature_usage`: dict mapping feature_name → "used" | "null" | "null_empty" | "used_constant"
- `feature_availability`: aggregate report of which features were used vs NULL across all dimensions

**Feature availability summary (10,707 records):**

| Feature | Status | Used By |
|---------|--------|---------|
| atr_pct | 39.7% available | entry_quality, invalidation_clarity, volatility_context, volume_ratio |
| entry_price | 77.6% available | invalidation_clarity, risk_rr |
| invalidation_price | 77.6% available | invalidation_clarity, risk_rr |
| target_price | 77.6% available | risk_rr |
| pnl_pct | 99.97% available | momentum_at_entry |
| duration_bars | 100% available | momentum_at_entry, risk_rr |
| zone_width_atr | 62.1% available (constant 0.5) | entry_quality (fallback) |
| touches | 62.1% available (constant 1) | entry_quality (fallback) |
| structure_type | 62.1% available (always "") | structure_quality, structure_alignment (skipped when empty) |
| liquidity_side | 62.1% available (always "") | liquidity_balance (skipped when empty) |
| max_favorable | 0% available (ALL NULL) | risk_rr (unavailable) |
| max_adverse | 0% available (ALL NULL) | risk_rr (unavailable) |
| vol_ratio | regime-dependent | volume_ratio |

---

## Expected Improvements

| Dimension | V2 Variance | V4 Expected Variance | V2 Ceiling | V4 Target |
|-----------|-------------|---------------------|------------|-----------|
| entry_quality | 0.15 | 0.15–0.35 | 75.8% at 0.65 | <50% at any single value |
| invalidation_clarity | 0.002 | 0.20–0.40 | 99.8% at 1.0 | <30% at any single value |
| risk_rr_feasibility | 0.002 | 0.15–0.30 | 83.4% at 0.55 | <40% at any single value |
| structure_alignment | N/A | 0.20–0.35 | N/A | >0.15 |
| volatility_context | N/A | 0.25–0.40 | N/A | >0.15 |
| liquidity_balance | N/A | 0.15–0.30 | N/A | >0.10 |
| momentum_at_entry | N/A | 0.15–0.30 | N/A | >0.10 |
| volume_ratio | N/A | 0.15–0.30 | N/A | >0.10 |
| regime_weighted_quality | N/A | 0.10–0.25 | N/A | >0.08 |

---

## Compatibility

- **quality_v3:** Unchanged — `setup_quality_engine.py` not modified
- **quality_v2:** Unchanged — `setup_quality_engine_v2.py` not modified
- **Existing tests:** Unchanged — v2/v3 tests continue to pass
- **QualityScore dataclass:** Extended — new fields `feature_usage` and `feature_availability` added
- **setup_object_model.py:** Extended — QualityScore has new fields

---

## File Location

- Engine: `/opt/markethq/setup_quality_engine_v4.py`
- Design: `/opt/markethq/quality_v4_design.md`
- Object Model: `/opt/markethq/setup_object_model.py`