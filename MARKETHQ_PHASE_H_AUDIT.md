# MARKETHQ PHASE H AUDIT

**Date:** 2026-09-16
**Phase:** H — Research Intelligence, Learning & Adaptive Research

---

## 1. Mevcut Learning Infrastructure

### 1.1 brain_learning_pipeline.py (1313 satir)
- Brain Learning Pipeline V1
- Learning event pipeline: setup_outcome → learning_event → brain_claim_candidate
- Claim lifecycle: CANDIDATE → VALIDATED → PROMOTED
- Weight versioning: weight_v1
- Hierarchical fallback: strategy+regime+timeframe → strategy+regime → strategy global → neutral
- Walk-forward train/validation split
- **Adaptive V1 weight computation**

### 1.2 research_storage_schema_v1.py (489 satir)
- market_datasets, dataset_versions
- research_experiments, research_results
- research_memory (learning_json)
- SQL schema definitions

### 1.3 analysis.py (325 satir)
- Adaptive weighting analysis
- Baseline vs adaptive comparison
- Quality score as adaptive weight

### 1.4 setup_outcome_tracker.py
- Historical outcome tracking
- Signature-based dedup
- get_historical_stats()

### 1.5 persistence.py
- DB persistence for all models
- Observation bridge

### 1.6 observation_bridge.py
- Brain observation bridge
- Claims → Brain

---

## 2. Adaptive V1 Failure Analysis

From previous session:

| Issue | Detail |
|-------|--------|
| Weight explosion | 1 weight reached 54% |
| Sample size | 6/7 contexts n<30 |
| Fallback | 71% fallback rate |
| DOWNTREND_WEAK | Negative expectancy |
| Train/val shift | Baseline shift between windows |
| Adaptive < baseline | Underperformed baseline |
| Correlation penalty | Too strong |

---

## 3. Duplicate Functionality

| Existing | New Phase H | Action |
|----------|-------------|--------|
| brain_learning_pipeline.py | research_intelligence_engine.py | REUSE pipeline, EXTEND with research loop |
| research_storage_schema_v1.py | research_intelligence_model.py | REUSE schema, EXTEND models |
| setup_outcome_tracker.py | research_memory | REUSE outcomes, EXTEND memory |
| analysis.py | adaptive research | REUSE comparison, EXTEND with champion/challenger |
| observation_bridge.py | Brain integration | REUSE bridge, EXTEND with research observations |

---

## 4. Implementation Plan

1. Audit (this doc)
2. Research Intelligence Models
3. Claim Validation Engine
4. Research Memory
5. Failure Memory / Counterexamples
6. Similarity Engine
7. Agent Reliability
8. Weight Proposal (no auto deploy)
9. Champion/Challenger
10. Adaptive Research (offline only)
11. Experiment Registry
12. Brain Integration
13. Tests (100+)
14. Documentation

---

## 5. Critical Constraints

- NO auto weight deployment
- NO auto strategy promotion
- NO production alpha claims
- NO lookahead
- NO fake data
- Research-only, offline
- All learning is OBSERVATION, not TRUTH