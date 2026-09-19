# MARKETHQ SETUP ENGINE — PHASE F AUDIT

**Date:** 2026-09-16
**Phase:** F — Research-Backed Signal/Setup Engine
**Purpose:** Audit existing setup systems before building Phase F

---

## 1. Mevcut Setup Sistemleri

### 1.1 setup_engine_v1.py (251 satir)
- `build_setup(df, timeframe)` — raw setup dict uretir
- `detect_regime(last, df)` — multi-factor regime detection
- Entry: ATR-based zone (±0.5 ATR)
- Invalidation: ATR×2.0 stop-loss
- Target: ATR×3.0
- Strategy agreement from strategy_registry_v1
- Output: dict (setup_id, entry_price, entry_zone, invalidation, target, direction, etc.)

### 1.2 research_setup_engine.py (677 satir)
- `build_research_setup(df, symbol, timeframe)` — wraps setup_engine_v1
- Creates SetupModel from raw setup
- Adds: structure_info, liquidity_info, historical_validation
- Quality scoring via setup_quality_engine_v2
- WHY panel generation (markdown)
- Research flags (low confidence, regime penalty, etc.)
- Regime filter via regime_filter.py
- **EXECUTION_ENABLED = False** — research only
- CLI entry point: `python research_setup_engine.py SYMBOL TIMEFRAME`

### 1.3 setup_quality_engine_v4.py (2033 satir)
- 11 quality dimensions:
  1. entry_quality
  2. invalidation_clarity
  3. risk_reward
  4. structure_alignment
  5. volatility_context
  6. liquidity_balance
  7. momentum_at_entry
  8. volume_ratio
  9. regime_weighted_quality
  10. supporting_evidence
  11. conflicting_evidence
- Multiplicative scoring (not additive)
- Sample size adjustment
- Regime interaction
- **VERDICT: Experimental/Research — NOT production proven**
- Quality V4 overall ≠ win probability

### 1.4 setup_backtest_engine.py (713 satir)
- Backtest simulation engine
- Entry/exit checking, excursion computation
- Quality correlation analysis
- Portfolio metrics
- **Separate from setup generation**

### 1.5 setup_outcome_tracker.py (440 satir)
- Historical outcome tracking
- Signature-based dedup: symbol + timeframe + setup_type + regime + direction + atr_pct + zone_width + touches + structure_type
- `get_historical_stats()` — win rate, avg return, sample size
- `record_outcome()` — record setup outcome
- Survivorship bias note in notes
- **Near-duplicate detection with tolerance**

### 1.6 setup_object_model.py (487 satir)
- Rich SetupModel with 20+ sub-models
- MarketInfo, TimeframeInfo, RegimeInfo, BiasInfo
- StructureInfo, LiquidityInfo, EntryZone, Confirmation
- InvalidationLevel, TargetLevel, Targets, RiskReward
- Evidence, HistoricalValidation, QualityScore, Reasoning
- InvalidationConditions, Outcome, LearningMetadata

### 1.7 regime_filter.py (393 satir)
- Regime eligibility filter
- ALLOW / PENALTY / CONSERVATIVE
- Data-driven (not hardcoded)
- Used by research_setup_engine

### 1.8 smc_structure_v1.py (267 satir)
- SMC structure analysis
- Swing detection, BOS/CHoCH events
- Used by research_setup_engine for structure_info

### 1.9 structure_lookahead_fix.py (128 satir)
- Lookahead protection for structure detection
- Ensures structure uses cutoff-time data only

### 1.10 strategy_registry_v1.py (452 satir)
- Strategy execution registry
- `run_all_strategies_df()` — runs all strategies
- `agreement_summary()` — strategy agreement analysis
- Family-level breakdown

---

## 2. Çakışma / Çift Sistem Analizi

| Sistem | Amaç | Durum |
|--------|------|-------|
| setup_engine_v1 | Raw setup generation | Active (imported) |
| research_setup_engine | Research-backed setup with quality | Active (CLI) |
| setup_quality_engine_v4 | 11-dim quality scoring | Experimental |
| setup_backtest_engine | Backtest simulation | Separate |
| setup_outcome_tracker | Historical outcome tracking | Separate |
| Phase E Opportunity Engine | Opportunity aggregation | Active |

**CRITICAL FINDING:** Opportunity Engine (Phase E) ve Setup Engineler BİRBAĞIMLI DEĞİL.

- Opportunity Engine → Opportunity object
- Setup Engine → SetupModel from raw OHLCV
- Neither produces SetupCandidate from Opportunity
- Phase F bridges this gap

**NO DUPLICATE ENGINE RISK:** Phase F should NOT create a new setup engine. It should:
1. Take Opportunity as input
2. Use existing setup_engine_v1 for geometry (entry/invalidation/target)
3. Use existing quality engines for scoring
4. Add opportunity context, uncertainty, why panel
5. Reference Phase D agents for evidence traceability

---

## 3. Entry Zone Analizi

**Mevcut:** setup_engine_v1 → ATR-based ±0.5 ATR zone
**research_setup_engine:** Same, wrapped in EntryZone model
**Phase F:** Should use opportunity context to refine entry zone
- Opportunity direction → LONG/SHORT
- Opportunity supporting agents → trend, momentum, liquidity
- Opportunity conflicting agents → reversal
- Entry zone should reflect structure, not just ATR

---

## 4. Invalidation Analizi

**Mevcut:** ATR×2.0 stop-loss
**Phase F:** Should add:
- Structure-based invalidation (BOS/CHoCH invalidation)
- Liquidity-based invalidation
- Strategy-specific invalidation from Phase D agents

---

## 5. Target Analizi

**Mevcut:** ATR×3.0 target
**Phase F:** Should add:
- Structure-based targets (next swing, liquidity pool)
- Multiple targets (T1, T2, T3) with methodology
- Quality V4 target geometry (experimental)

---

## 6. WHY Panel Analizi

**Mevcut:** research_setup_engine.format_why_panel() — markdown output
**Phase F:** Should enhance:
- Add opportunity context (supporting/conflicting/unavailable evidence)
- Add agent traceability (which agents contributed)
- Add uncertainty flags
- Add historical evidence status
- Add regime compatibility

---

## 7. Lookahead Riskleri

| Risk | Mevcut | Phase F |
|------|--------|---------|
| Structure lookahead | structure_lookahead_fix.py handles | Reuse |
| Target future data | ATR-based (no future) | Keep ATR-based |
| Invalidation future data | ATR-based (no future) | Keep ATR-based |
| Historical evidence | setup_outcome_tracker | Add sample size check |
| Quality scoring | quality_v4 (experimental) | Mark as experimental |

---

## 8. DB Schema Audit

**Existing tables:**
- `opportunities` — Phase E table (exists)
- `opportunity_evidence` — Phase E table (exists)
- `setup_outcomes` — historical outcomes (exists)
- `brain_observations` — brain observations (exists)
- `brain_claims` — brain claims (exists)
- `agent_runs`, `agent_results`, `evidence_items` — agent tracking (exists)
- `feature_snapshots` — feature cache (exists)

**Phase F needs:**
- `research_setups` — setup records (NEW)
- `setup_evidence` — setup evidence items (NEW)

Both additive, idempotent migration.

---

## 9. Duplicate System Riskleri

| Risk | Status | Mitigation |
|------|--------|------------|
| Opportunity Engine + Setup Engine overlap | LOW | Opportunity → Setup pipeline, not parallel |
| setup_engine_v1 + research_setup_engine | MEDIUM | research_setup_engine wraps v1, reuse |
| Quality V4 + Opportunity confidence | MEDIUM | Separate concepts, documented |
| Phase F + research_setup_engine | HIGH if duplicate | Phase F BRIDGES, not replaces |

**KEY DECISION:** Phase F should REUSE research_setup_engine for geometry, not duplicate it. Phase F adds:
- Opportunity context bridge
- Agent traceability
- Uncertainty engine
- Research-only framing
- Why panel enhancement

---

## 10. Implementation Plan

1. Audit (this doc)
2. Opportunity → Setup bridge (opportunity_model.py extension)
3. ResearchBackedSetup model
4. Entry zone engine (reuse setup_engine_v1 + opportunity context)
5. Invalidation engine (reuse + structure-based)
6. Target engine (reuse + multiple targets)
7. WHY panel (enhance existing)
8. Evidence traceability (Phase D agents → Setup)
9. Uncertainty engine
10. Persistence (research_setups table)
11. Brain integration (reuse observation_bridge)
12. Tests (40+)
13. Documentation

---

## 11. Audit Summary

**Existing systems to reuse:**
- setup_engine_v1 (geometry)
- research_setup_engine (SetupModel + WHY panel)
- setup_quality_engine_v4 (experimental quality)
- setup_outcome_tracker (historical evidence)
- regime_filter (regime compatibility)
- smc_structure_v1 (structure analysis)
- structure_lookahead_fix (lookahead protection)

**New in Phase F:**
- Opportunity → Setup bridge
- ResearchBackedSetup model (enhanced)
- Agent traceability
- Uncertainty engine
- research_setups persistence

**Do NOT create:**
- New parallel setup engine
- New quality engine
- New regime system
- New structure analysis
- New historical evidence system
