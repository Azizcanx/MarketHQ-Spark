# MARKETHQ PHASE G — RESEARCH VALIDATION REPORT

**Date:** 2026-09-16
**Phase:** G — Research Validation & Historical Setup Intelligence

---

## 1. Executive Summary

Phase G implements historical validation of Research-Backed Setups against real OHLCV data. No live trading, no broker, no fake data.

**Files created:**
- `research_validation_model.py` (302 lines) — validation models
- `research_validation_engine.py` (735 lines) — replay + validation engine
- `test_research_validation.py` (69 tests) — Phase G test suite
- `MARKETHQ_PHASE_G_AUDIT.md` — audit document
- `MARKETHQ_RESEARCH_VALIDATION_PHASE_G_REPORT.md` — this report
- `MARKETHQ_PHASE_G_CLAIMS.md` — research claims
- `MARKETHQ_PHASE_G_DATA_COVERAGE.md` — data coverage

**Test count:**
- Before Phase G: 332 PASS
- Phase G new: 69 PASS
- **Total: 401 PASS**

---

## 2. Historical Replay Architecture

```
Historical OHLCV (cutoff T)
    ↓
FeatureSnapshot @ T
    ↓
Research Agents (7 strategies)
    ↓
AgentResults
    ↓
Opportunity Engine
    ↓
ResearchBackedSetup
    ↓
Outcome Simulator (real bars T+1, T+2...)
    ↓
HistoricalOutcome (entry/invalidation/T1/T2/T3/MFE/MAE)
    ↓
ValidationMetrics
    ↓
Walk-Forward Splits
    ↓
Failure Analysis
    ↓
Research Claims (TESTED/UNSTABLE/REJECTED/UNTESTED)
```

---

## 3. Outcome Simulation

**Simulation engine:** `replay_setup()` in research_validation_engine.py

**Entry rule:** Deterministic — zone touch at first bar where low ≤ entry_zone_high AND high ≥ entry_zone_low

**Invalidation:** LONG: low ≤ invalidation_price | SHORT: high ≥ invalidation_price

**Target:** Price ≥ target for LONG, price ≤ target for SHORT

**OHLC ambiguity:** When entry/invalidation/target hit same bar → AMBIGUOUS

**Outcome types:**
- TARGET_1_REACHED, TARGET_2_REACHED, TARGET_3_REACHED
- INVALIDATED
- EXPIRED
- NO_ENTRY
- INCOMPLETE_DATA
- AMBIGUOUS

---

## 4. Key Findings

### Entry Zone Geometry
- Entry zone width depends on ATR and structure
- No-entry cases tracked separately (not counted as losses)

### Invalidation
- Invalidation distance measured in ATR multiples
- ATR=0 handled (UNAVAILABLE)

### Target Hit Rates
- T1, T2, T3 tracked independently
- Target-before-invalidation rate computed

### MFE/MAE
- Computed over full horizon and pre-outcome windows
- AMBIGUOUS bars excluded from MFE/MAE

### Walk-Forward
- Chronological train/validation splits
- 3+ windows recommended
- Per-window metrics + drift detection

### Lookahead Audit
- Future bars don't change setup geometry (PASS)
- Setup fingerprint immutable after cutoff

---

## 5. Claims Model

All research claims are explicitly status-labeled:

| Claim | Status |
|-------|--------|
| High-quality setups have higher T1 hit rate | UNTESTED |
| Quality correlation with realized R is walk-forward stable | UNSTABLE |
| Agent confidence correlates with outcome | UNTESTED |
| Evidence consistency predicts outcome | UNTESTED |

Claims require: sample ≥ 30, temporal validation, no hindsight leakage.

---

## 6. Limitations

1. **Single asset (THYAO.IS)** — multi-asset analysis pending
2. **Single timeframe** — 15m/1h/4h isolation pending
3. **No real yfinance data in tests** — synthetic data used; real data test has network dependency
4. **Quality V4 not validated** — experimental, not production proven
5. **Sample sizes** — small N in some buckets flagged as LOW_SAMPLE
6. **Survivorship bias** — not assessed (single symbol)
7. **No auto promotion** — observations only, no weight updates

---

## 7. Brain Integration

Validated observations can flow to Brain via observation_bridge.py:
- Format: observation + evidence + sample + window + status
- Status: UNTESTED (not truth)
- No automatic strategy promotion

---

## 8. Phase H Recommendation

Phase G results should inform Phase H priorities:
- If validation shows strong patterns → Phase H learning loop
- If data insufficient → more data collection
- If geometry weak → Phase F iteration
- If lookahead risk → fix before any production use

**Do NOT auto-promote Phase G findings to production.**

---

## 9. Deliverables Checklist

- [x] Historical replay engine
- [x] Outcome simulation
- [x] Validation metrics
- [x] Walk-forward validation
- [x] Calibration analysis
- [x] Failure analysis
- [x] Claim model with status
- [x] Brain feedback interface
- [x] Machine-readable output
- [x] 69 new tests (69 PASS)
- [x] Audit document
- [x] Report
- [x] Claims document
- [x] Data coverage document
- [x] Full regression (401/401 PASS)