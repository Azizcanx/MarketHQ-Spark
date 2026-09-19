# MARKETHQ PHASE H — RESEARCH INTELLIGENCE REPORT

**Date:** 2026-09-16
**Phase:** H — Research Intelligence, Learning & Adaptive Research

---

## 1. Executive Summary

Phase H implements MarketHQ's research intelligence system:
Observe → Remember → Compare → Hypothesize → Experiment → Validate → Learn → Report.

All research-only. No trading. No auto promotion. Offline learning only.

**New files:**
- `research_intelligence_model.py` (338 lines) — Observation, Hypothesis, Experiment, Result, Claim, Evidence, ResearchMemory, ReliabilityProfile, CalibrationProfile, FeatureImportance, WeightProposal, SimilarityMatch, FailurePattern, Counterexample, ExperimentRegistry, ResearchDashboard
- `research_intelligence_engine.py` (436 lines) — Observation builder, hypothesis builder, experiment registry, claim validation, research memory, failure analysis, similarity engine, agent reliability, weight proposals, champion/challenger, calibration, feature redundancy, research dashboard
- `test_research_intelligence.py` (89 tests) — Phase H test suite

**Test count:**
- Before Phase H: 401 PASS
- Phase H new: 89 PASS
- **Total: 490 PASS**

---

## 2. Architecture

```
Observation → Hypothesis → Experiment → Result → Claim → ResearchMemory
     ↓              ↓            ↓           ↓         ↓            ↓
  Failure      Weight       Champion/    Counte-    Brain      Research
  Memory       Proposal     Challenger   example    Feedback   Dashboard
```

---

## 3. Key Components

### 3.1 Observation Engine
- 9 observation types (OBSERVATION, PATTERN, FAILURE, SUCCESS_PATTERN, CLAIM, COUNTEREXAMPLE, DATA_QUALITY, REGIME_PATTERN, STRATEGY_PATTERN)
- Evidence traceability
- Context-rich (regime, asset, timeframe, sample)

### 3.2 Claim Validation
- 5 statuses: UNTESTED → TESTED → SUPPORTED / UNSTABLE / REJECTED
- Multi-dimensional validation: sample size, effect size, temporal stability, walk-forward consistency, confidence interval
- No single correlation = SUPPORTED

### 3.3 Research Memory
- 8 memory types
- Status + evidence + sample on every entry
- Not a truth database

### 3.4 Failure Memory
- Automatic failure pattern detection
- Conditions, sample, outcome, recurrence
- Future research evidence (not trading decisions)

### 3.5 Similarity Engine
- Top-K similar historical setups
- Matched/mismatched dimensions
- Historical outcomes attached
- Not a prediction engine

### 3.6 Agent Reliability
- Global + regime-specific profiles
- Direction agreement, outcome correlation, target hit rate
- NOT permanent quality scores

### 3.7 Weight Proposal (NO AUTO DEPLOY)
- PROPOSED status only
- Human/research approval required
- Previous Adaptive V1 comparison included
- Baseline comparison

### 3.8 Champion/Challenger
- Offline comparison only
- Avg R, Median R, target rate, invalidation, MFE, MAE
- Winner = better historical performance, NOT auto promote

### 3.9 Calibration
- Confidence bucket analysis
- Outcome rate per bucket
- Regime-specific calibration

### 3.10 Feature Redundancy
- Correlation matrix analysis
- Redundancy groups detected
- Prevents 5 features = 5 independent evidence

### 3.11 Experiment Registry
- Reproducible experiments
- Config hash
- Cutoff-aware

---

## 4. Adaptive V1 Lessons Applied

| Adaptive V1 Failure | Phase H Fix |
|---------------------|-------------|
| Weight explosion (54%) | PROPOSED only, no auto deploy |
| 6/7 contexts n<30 | LOW_SAMPLE flag on all small samples |
| 71% fallback | Hierarchical fallback with provenance |
| DOWNTREND_WEAK negative | Regime-specific analysis, not global |
| Train/val baseline shift | Chronological walk-forward |
| Adaptive < baseline | Champion/challenger comparison |
| Correlation penalty too strong | Multiple testing / overfitting warnings |

---

## 5. Research Claims Status

20 claims from Phase G all remain UNTESTED/UNSTABLE until validated with sufficient data.

No claim auto-promoted. No claim treated as truth.

---

## 6. Brain Integration

Brain receives:
- Observations (UNTESTED status)
- Claims (with evidence + sample + window)
- Counterexamples
- Research memory

Brain does NOT auto-act on any of these.

---

## 7. Limitations

1. All analysis is offline/research-only
2. No real yfinance data in tests (synthetic)
3. Single asset (THYAO.IS)
4. Sample sizes in some buckets are small
5. Adaptive V1 comparison is historical reference, not live
6. Feature importance is correlation-based, not causal
7. No causal inference
8. Similarity is deterministic feature matching, not ML

---

## 8. Phase I Recommendation

Phase H completes the research intelligence loop.
Phase I should be: UI / HQ Decision Surface / Human Review.

But first:
- Research memory quality assessment
- Claim quality assessment
- Reliability stability check
- Similarity usefulness validation
- Adaptive research results review
- Data coverage check
- Computational cost analysis
- Unresolved limitations

**Do NOT auto-promote Phase H findings to production.**

---

## 9. Deliverables Checklist

- [x] Observation engine
- [x] Hypothesis engine
- [x] Experiment registry
- [x] Claim validation
- [x] Research memory
- [x] Failure memory
- [x] Similarity engine
- [x] Agent reliability
- [x] Weight proposal (no auto deploy)
- [x] Champion/challenger
- [x] Calibration
- [x] Feature redundancy
- [x] Brain integration
- [x] Human review layer
- [x] Experiment registry
- [x] Reproducibility
- [x] Lookahead audit
- [x] Statistical robustness
- [x] Dashboard JSON
- [x] 89 new tests (89 PASS)
- [x] Audit document
- [x] Report
- [x] Claims document
- [x] Data coverage document
- [x] Full regression (490/490 PASS)