# MARKETHQ PHASE G AUDIT

**Date:** 2026-09-16
**Phase:** G — Research Validation & Historical Setup Intelligence
**Purpose:** Audit existing validation infrastructure before building Phase G

---

## 1. Mevcut Altyapı

### 1.1 backtest_engine.py (1244 satir)
- BacktestEngine class with trade simulation
- Entry/exit logic, MFE/MAE calculation
- Portfolio metrics
- Signal engine integration
- **Uses real OHLCV data**
- **Research-only (no broker)**

### 1.2 walk_forward_engine.py (2050+ satir)
- Full walk-forward optimization
- Parameter grid generation
- Train/validation split
- Parameter stability analysis
- Knowledge base integration
- **Chronological split**
- **Production pipeline**

### 1.3 setup_outcome_tracker.py (440 satir)
- Historical outcome tracking
- Signature-based dedup
- Near-duplicate detection
- `get_historical_stats()` — win rate, avg return, sample
- `record_outcome()` — record setup outcome
- Survivorship bias note
- **Pre-computed historical outcomes**

### 1.4 setup_backtest_engine.py (713 satir)
- Setup backtest simulation
- Entry/exit checking, excursion computation
- Quality correlation analysis
- Portfolio metrics
- **Separate from setup generation**

### 1.5 research_setup_engine.py (677 satir)
- Research-backed setup generation
- SetupModel + quality scoring + WHY panel
- CLI entry point
- **Research only (EXECUTION_ENABLED = False)**

### 1.6 setup_quality_engine_v4.py (2033 satir)
- 11-dimension quality scoring
- Multiplicative scoring
- Sample size adjustment
- **Experimental/Research — NOT production proven**

### 1.7 Phase E Opportunity Engine
- Opportunity aggregation from 7 strategy agents
- Evidence-based confidence
- Lifecycle management
- Persistence

### 1.8 Phase F Research-Backed Setup Engine
- Setup generation from Opportunity
- Entry zone, invalidation, targets, RR
- WHY panel, uncertainty flags, evidence traces
- Research-only

---

## 2. Çakışma / Çift Sistem Analizi

| Sistem | Amaç | Durum |
|--------|------|-------|
| backtest_engine | Signal backtest | Active |
| walk_forward_engine | Parameter optimization | Active |
| setup_backtest_engine | Setup backtest | Active |
| setup_outcome_tracker | Outcome tracking | Active |
| research_setup_engine | Setup generation | Active |
| Phase E Opportunity Engine | Opportunity aggregation | Active |
| Phase F Setup Engine | Setup from Opportunity | Active |
| **Phase G (NEW)** | **Historical validation** | **YOK** |

**CRITICAL FINDING:** Phase G should REUSE existing engines, not duplicate them.

- backtest_engine → outcome simulation
- walk_forward_engine → validation framework
- setup_outcome_tracker → historical evidence
- setup_backtest_engine → trade simulation

---

## 3. Veri Akışı

```
Historical OHLCV
    ↓
FeatureSnapshot @ cutoff T
    ↓
Research Agents (Phase D)
    ↓
AgentResults
    ↓
Opportunity Engine (Phase E)
    ↓
Opportunity
    ↓
Setup Engine (Phase F)
    ↓
ResearchBackedSetup
    ↓
OUTCOME SIMULATION (Phase G — NEW)
    ↓
Historical bars T+1, T+2, ...
    ↓
Outcome: entry_hit / invalidation / T1/T2/T3 / expired / ambiguous
    ↓
VALIDATION (Phase G — NEW)
    ↓
Metrics: hit rates, R distribution, MFE/MAE, calibration
    ↓
WALK-FORWARD (Phase G — NEW)
    ↓
Train/validation splits, drift detection
    ↓
FAILURE ANALYSIS (Phase G — NEW)
    ↓
Common failure patterns
    ↓
CLAIMS (Phase G — NEW)
    ↓
Tested / Supported / Unstable / Rejected / Untested
    ↓
BRAIN FEEDBACK (Phase G — NEW)
    ↓
Observations → Brain (UNTESTED, not truth)
```

---

## 4. Mevcut Leakage Riskleri

| Risk | Mevcut | Phase G |
|------|--------|---------|
| Future data in setup | ATR-based, no future | Reuse + audit |
| Historical evidence cutoff | setup_outcome_tracker | Add sample check |
| Quality V4 stability | Experimental | Test walk-forward |
| Agent confidence → outcome | Not tested | Phase G core |
| Lookahead in structure | structure_lookahead_fix | Reuse |
| Survivorship bias | setup_outcome_tracker notes | Audit |

---

## 5. Veri Eksiklikleri

| Eksik | Durum |
|-------|-------|
| MFE/MAE coverage | Low (fixed horizon) |
| Multi-timeframe | Not tested |
| Multi-asset | THYAO only |
| Outcome definitions | Single win/loss |
| Ambiguous bars | Not handled |
| No-entry analysis | Not tracked |
| Expiry analysis | Not tracked |
| Calibration | Not measured |
| Drift | Not measured |
| Bootstrap CIs | Not computed |

---

## 6. Implementation Plan

1. Audit (this doc)
2. ResearchValidationEngine — historical replay + outcome simulation
3. ValidationMetrics — all metrics specified
4. WalkForwardValidator — chronological validation
5. FailureAnalyzer — common failure patterns
6. ClaimModel — research claims with status
7. BrainFeedback — validated observations
8. Persistence — validation tables
9. Tests (60+)
10. Documentation

---

## 7. Audit Summary

**Reuse:**
- backtest_engine (trade simulation)
- walk_forward_engine (validation framework)
- setup_outcome_tracker (historical evidence)
- setup_backtest_engine (trade simulation)
- structure_lookahead_fix (lookahead protection)

**New:**
- Historical replay system
- Outcome simulator
- Validation metrics
- Walk-forward analysis
- Failure analysis
- Claim model
- Brain feedback
- Machine-readable output

**Do NOT create:**
- New backtest engine
- New walk-forward engine
- New outcome tracker
- New quality engine
- Duplicate trade simulation
