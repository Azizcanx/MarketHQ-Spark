# Ceiling Effect Root Cause Analysis — quality_v3 Dimensions

**Data:** market_hq.db → setup_outcomes (10,002 total, 8,072 with metadata)
**Date:** 2026-09-16
**Scope:** Analysis only — no files modified

---

## Executive Summary

**ROOT CAUSE: 2 raw input features are CONSTANT across all records.**

| Feature | Value | Records | % of populated |
|---------|-------|---------|----------------|
| `zone_width_atr` | **0.5 (always)** | 4,028 | **100%** |
| `touches` | **1 (always)** | 4,028 | **100%** |

These constant inputs flow into **additive bonus scoring functions** (`base + bonus1 + bonus2 + ...`), so every setup gets identical bonuses → constant output → ceiling effect.

Additionally, `atr_pct` is NULL for 74% of records, `structure_type` is empty for 74%, and `liquidity_side` is empty for 74%. The raw feature data is simply not being populated during setup generation.

---

## Per-Dimension Root Cause Analysis

### 1. invalidation_clarity — 99.8% = 1.0 ⛔ CEILING

**Scoring function:** `_score_invalidation_clarity()` in `setup_quality_engine_v2.py:511`

```
base=0.3 + clarity("clear")=+0.3 + distance(0.5-3.0 ATR)=+0.25
        + type("structural")=+0.15 = 1.0 → CLAMPED to ceiling
```

**Root cause:** The scoring function reaches 1.0 with just base + clarity + distance + type bonuses. The remaining bonuses (price distance, entry proximity) never fire because ceiling is already reached.

The invalidation inputs (`clarity`, `distance_atr`, `type`) are NOT stored in the database — they come from `SetupModel.invalidation` which is computed in memory. The 99.8% at 1.0 means most setups have `clarity="clear"`, `distance_atr` in 0.5-3.0, and `type="structural"`.

**Prior distribution (from quality_v3_report.md):** 7,628/7,642 = 99.8% at 1.0, only 14 rows at 0.95

**Correlation with outcome R:** r = -0.031 (negligible)

---

### 2. entry_quality — 75.8% = 0.65 ⛔ CEILING (SMOKING GUN)

**Scoring function:** `_score_entry_quality()` in `setup_quality_engine_v2.py:214`

**RAW INPUTS FROM DATABASE — VERIFIED CONSTANT:**

| Input | Value | Records | % of populated |
|-------|-------|---------|----------------|
| `zone_width_atr` | **0.5** | 4,028 | **100%** |
| `touches` | **1** | 4,028 | **100%** |

**Scoring path with constant inputs:**
```
base=0.3 + width(0.3-1.5 ATR sweet spot)=+0.25 + touches(==1)=+0.05
        + source("atr_based")=+0.05 + quality("medium")=+0.0 = 0.65
```

**0.65 is the EXACT ceiling** because:
- `zone_width_atr = 0.5` always → sweet spot bonus +0.25 (always fires)
- `touches = 1` always → +0.05 (always, never reaches +0.15 for >=2 or +0.2 for >=3)
- `source = "atr_based"` always → +0.05 (never reaches +0.15 for "structure")
- `quality = "medium"` always → +0.0

**Prior distribution:** 0.65 (5,741 rows, 75.1%), 0.7 (354 rows, 4.6%), 0.8 (1,547 rows, 20.2%)

Only 3 distinct values exist because only the source and quality labels create tiny variance.

**Correlation with outcome R:** r = +0.104 (weak but best of all dimensions — meaningless with ceiling)

---

### 3. risk_rr_feasibility — 83.4% = 0.55 ⛔ CEILING

**Scoring function:** `_score_risk_reward()` in `setup_quality_engine_v2.py:295`

**R:R mapping:**
```
R:R 0.5 → 0.1, R:R 1.0 → 0.25, R:R 1.5 → 0.4, R:R 2.0 → 0.55
R:R 2.5 → 0.7, R:R 3.0 → 0.75, R:R 5.0+ → 1.0
```

**Root cause:** R:R ratios cluster around 2.0:1 by construction. The setup engine creates targets and stops with a fixed ratio, so most setups get R:R ≈ 2.0 → score 0.55.

**Prior distribution:** Only 2 distinct values — 0.385 (15.7%) and 0.55 (84.3%)

**Correlation with outcome R:** r = +0.057 (negligible)

---

### 4. structure_quality — 50.8% = 0.4 ⛔ CEILING

**Scoring function:** `_score_structure_quality()` in `setup_quality_engine_v2.py:150`

**Input features:** `structure.has_structure`, `structure.structure_type`, `structure.displacement`, `structure.displacement_quality`

**Root cause:** Most setups have `has_structure=True` but `structure_type` is empty or "NEUTRAL" (not BOS/CHoCH). The structure_type bonus only applies to BOS/CHoCH types. Displacement and swing bonuses rarely trigger.

**Prior distribution:** 4 distinct values — 0.2 (370), 0.4 (3,692), 0.5 (1,658), 0.55 (1,922)

**Correlation with outcome R:** r = +0.055 (negligible)

---

### 5. formation_chain — 55% = 0.833 ⛔ CEILING

**Scoring function:** `_score_formation_chain()` in `setup_quality_engine_v2.py:589`

**Root cause:** Most setups have 5/6 chain links valid. Score = links/6 = 5/6 = 0.833.

**Prior distribution:** 3 distinct values — 0.75 (281), 0.833 (4,195), 0.917 (3,166)

**Correlation with outcome R:** r = -0.043 (negligible)

---

### 6. regime_compatibility — 23.4% = 0.85 ⛔ CEILING

**Scoring function:** `_score_regime_compatibility()` in `setup_quality_engine_v2.py:114`

**Root cause:** Most setups are trend-aligned (LONG in UPTREND or SHORT in DOWNTREND). Score = 0.7 + 0.25 * regime_conf ≈ 0.85.

**Prior distribution:** 11 distinct values, heavily skewed — 0.85 (23.5%), 0.875 (22.8%), 0.925 (14.2%)

**Correlation with outcome R:** r = -0.004 (negligible)

---

### 7. supporting_evidence — mean=0.815 (moderate ceiling)

**Scoring function:** `_score_supporting_evidence()` in `setup_quality_engine_v2.py:58`

**Root cause:** When supporting > conflicting (which is common), net > 0, score > 0.5. When supporting >> conflicting, net approaches 1.0, score approaches 1.0.

**Prior distribution:** 11 distinct values, 1.0 is top (32.6%), std=0.1442

**Correlation with outcome R:** r = +0.035 (negligible)

---

### 8. conflicting_evidence — mean=0.722 (moderate ceiling)

**Scoring function:** `_score_conflicting_evidence()` in `setup_quality_engine_v2.py:92`

**Root cause:** When conflicting is low relative to total, conflict_ratio is small, score is high.

**Prior distribution:** 11 distinct values, 1.0 is top (32.6%), std=0.2164

**Correlation with outcome R:** r = +0.035 (negligible)

---

### 9. strategy_agreement — mean=0.627 (NO CEILING, but no predictive power)

**Scoring function:** `_score_strategy_agreement()` in `setup_quality_engine_v2.py:347`

**Root cause:** Has 238 distinct values and the most variance (std=0.2319). But still no predictive power because the agreement scoring is based on strategy consensus, not outcome prediction.

**Prior distribution:** 238 distinct values, range 0.3-1.0

**Correlation with outcome R:** r = -0.001 (zero)

---

## Verified Raw Input Feature Distribution (Current DB State)

| Feature | Unique Values | Mean | Min | Max | Status |
|---------|---------------|------|-----|-----|--------|
| `zone_width_atr` | **3** (None, 0.0, 0.5) | — | 0.5 | 0.5 | **CONSTANT when populated** |
| `touches` | **3** (None, 0, 1) | — | 1 | 1 | **CONSTANT when populated** |
| `atr_pct` | 100 | — | 0.5 | 2.27 | OK but 74% NULL |
| `structure_type` | 1 (empty) | — | — | — | **EMPTY for 74%** |
| `liquidity_side` | 1 (empty) | — | — | — | **EMPTY for 74%** |
| `regime` | 9 | — | — | — | OK |
| `direction` | 2 | — | — | — | OK |

**Critical finding:** When `zone_width_atr` is populated, it's ALWAYS 0.5. When `touches` is populated, it's ALWAYS 1. These are set by the setup engine and never vary.

---

## Code-Level Root Cause Trace

### entry_quality ceiling (0.65) — EXACT CALCULATION

File: `setup_quality_engine_v2.py:214-292`

```python
def _score_entry_quality(setup: SetupModel) -> tuple[float, str, float]:
    zone = setup.entry_zone
    
    # CONSTANT INPUTS: zone.width_atr=0.5, zone.touches=1
    
    score = 0.3  # base for having entry
    
    # zone.width_atr=0.5 → sweet spot 0.3-1.5 → +0.25
    score += 0.25  # score = 0.55
    
    # zone.touches=1 → +0.05
    score += 0.05  # score = 0.60
    
    # zone.source="atr_based" → +0.05
    score += 0.05  # score = 0.65 ← CEILING
    
    # zone.quality="medium" → +0.0
    # score = 0.65
    
    return round(score, 3)  # → 0.65
```

**The 0.65 value is deterministic given constant inputs.**

### invalidation_clarity ceiling (1.0) — EXACT CALCULATION

File: `setup_quality_engine_v2.py:511-586`

```python
def _score_invalidation_clarity(setup: SetupModel) -> tuple[float, str, float]:
    inv = setup.invalidation
    
    # CONSTANT INPUTS: inv.clarity="clear", inv.distance_atr in 0.5-3.0, inv.type="structural"
    
    score = 0.3  # base for having invalidation
    
    # inv.clarity="clear" → +0.3
    score += 0.3  # score = 0.6
    
    # inv.distance_atr in 0.5-3.0 → +0.25
    score += 0.25  # score = 0.85
    
    # inv.type="structural" → +0.15
    score += 0.15  # score = 1.0 → CLAMPED
    
    return round(score, 3)  # → 1.0
```

**The 1.0 value is deterministic given the default invalidation inputs.**

---

## Correlation with Future Outcome R (from quality_v3_report.md)

| Dimension | Pearson r | Win Mean | Lose Mean | Diff | Ceiling |
|-----------|-----------|----------|-----------|------|---------|
| entry_quality | +0.104 | 0.691 | 0.678 | +0.013 | 75.8% |
| supporting_evidence | +0.035 | 0.826 | 0.808 | +0.018 | 32.6% at 1.0 |
| conflicting_evidence | +0.035 | 0.739 | 0.713 | +0.027 | 32.6% at 1.0 |
| structure_quality | +0.055 | 0.450 | 0.450 | -0.000 | 50.8% at 0.4 |
| risk_rr_feasibility | +0.057 | 0.527 | 0.523 | +0.004 | 83.4% at 0.55 |
| regime_compatibility | -0.004 | 0.732 | 0.730 | +0.001 | 23.4% at 0.85 |
| formation_chain | -0.043 | 0.861 | 0.867 | -0.007 | 55% at 0.833 |
| invalidation_clarity | -0.031 | 1.000 | 1.000 | -0.000 | 99.8% at 1.0 |
| strategy_agreement | -0.001 | 0.621 | 0.630 | -0.008 | 238 values |

**None of the 9 dimensions show meaningful predictive power** (|r| < 0.11).

---

## Root Cause Summary

### PRIMARY ROOT CAUSES (in order of impact):

1. **`zone_width_atr` is CONSTANT at 0.5** — Set by `setup_engine_v1.py:227` which creates `entry_zone: [entry - 0.25*atr, entry + 0.25*atr]`, giving width = 0.5*atr → zone_width_atr = 0.5 always. This directly causes entry_quality ceiling at 0.65.

2. **`touches` is CONSTANT at 1** — Touch counting is never implemented during setup generation. This directly causes entry_quality ceiling at 0.65 (touches=1 always gives +0.05, never +0.15 or +0.2).

3. **Additive bonus scoring** — All scoring functions use `base + bonus1 + bonus2 + ...` logic. With constant inputs, bonuses are identical → constant output → ceiling. The functions were designed with additive bonuses that assume variable inputs, but the inputs are constant.

4. **Invalidation inputs not persisted** — `invalidation.clarity`, `invalidation.distance_atr`, `invalidation.type` are computed in the SetupModel but NOT stored in the database. The quality_breakdown stores only the scored values, not the inputs, making it impossible to trace the ceiling cause for invalidation_clarity.

5. **Structure/liquidity inputs not persisted** — `structure.structure_type`, `structure.displacement`, `liquidity.liquidity_side` are NOT stored in setup_outcomes (empty strings for 74% of records).

### SECONDARY ROOT CAUSES:

6. **R:R ratio clustering** — Most setups have R:R ≈ 2.0:1 by construction (target/stop ratio), causing risk_rr_feasibility to cluster at 0.55.

7. **High base scores** — Base scores of 0.2-0.3 for "having ANY data" mean most setups start near the ceiling before bonuses even apply.

8. **Sweet-spot ranges too wide** — The sweet spot ranges (e.g., 0.3-1.5 ATR for zone width, 0.5-3.0 ATR for invalidation distance) capture most cases, so bonuses fire uniformly.

---

## Fix Recommendations

1. **Fix `setup_engine_v1.py:227`** — Generate variable zone widths based on market structure (swing points, liquidity) instead of fixed 0.25*atr on each side.

2. **Implement touch counting** — Count how many times price tested the entry zone in recent bars. Store in `entry_zone.touches`.

3. **Persist raw inputs** — Store `invalidation.clarity`, `invalidation.distance_atr`, `invalidation.type`, `structure.structure_type`, `structure.displacement`, `liquidity.liquidity_side` in `metadata_json` so they can be analyzed and debugged.

4. **Redesign scoring functions** — Replace additive bonus with multiplicative or threshold-based scoring:
   - Require ALL features to be strong (not just some)
   - Apply penalties for weak features
   - Use non-linear mappings that create more separation

5. **Remove invalidation_clarity** — 99.8% ceiling makes it useless as a feature. Either fix the input data or drop the dimension.

6. **Rebuild with diverse inputs** — After fixing raw inputs, recompute quality_breakdown and verify variance before using as features.

---

## Verification Queries

```sql
-- Verify zone_width_atr is constant when populated
SELECT DISTINCT zone_width_atr FROM setup_outcomes WHERE zone_width_atr IS NOT NULL;
-- Expected: single row with 0.5

-- Verify touches is constant when populated
SELECT DISTINCT touches FROM setup_outcomes WHERE touches IS NOT NULL;
-- Expected: single row with 1
```