# MarketHQ — Phase C Report: Agent Runtime + Observation Pipeline

**Date:** 2026-09-16
**Status:** COMPLETE

---

## 1. PHASE C MİMARİSİ

```
MARKET DATA
     ↓
MARKET CONTEXT (process_ohlcv → FeatureSnapshot)
     ↓
FEATURE SNAPSHOT CACHE (symbol, timeframe, cutoff)
     ↓
AGENT RUNTIME (lifecycle: CREATED → RUNNING → COMPLETED/FAILED)
     ↓
AGENT REGISTRY (agent_id → adapter mapping)
     ↓
ADAPTER (8 engine adapters)
     ↓
AGENT RESULT (structured output)
     ↓
PERSISTENCE LAYER (DB: agent_runs, results, evidence, claims, snapshots)
     ↓
BRAIN OBSERVATION BRIDGE (AgentResult → brain_observations/claims)
     ↓
LOOKAHEAD PROTECTION (cutoff enforcement)
```

---

## 2. AGENT RUNTIME

**File:** `agent_runtime.py` (200 lines)

### Lifecycle States
- `CREATED` — run initialized
- `RUNNING` — adapter executing
- `COMPLETED` — success
- `FAILED` — error captured
- `INSUFFICIENT_DATA` — partial data

### Key Methods
- `run(agent_id, symbol, timeframe, ...)` — execute single agent
- `run_multiple(agent_ids, ...)` — sequential multi-agent
- `get_run(execution_id)` — retrieve run record
- `list_runs(agent_id, symbol, status)` — filtered listing

### Features
- Input validation (symbol/timeframe required)
- Adapter not found → structured FAILED error
- Exception isolation → one failure doesn't crash runtime
- Execution trace (step-by-step log)
- Persistence (best effort, never crashes runtime)
- Shared FeatureSnapshotCache integration

---

## 3. AGENT REGISTRY

**File:** `agent_registry.py` (80 lines)

### Features
- Deterministic: explicit registration, no auto-discovery
- Version-aware: each adapter has version
- Global default registry + instance-based registry
- `register(agent_id, adapter, version)` → void
- `get(agent_id)` → adapter | None
- `list_agents()` → metadata list
- `unregister(agent_id)` → bool

---

## 4. FEATURE SNAPSHOT CACHE

**File:** `feature_cache.py` (95 lines)

### Cache Key
`(symbol, timeframe, data_cutoff_timestamp)`

### Features
- LRU eviction (bounded by max_size)
- Hit/miss/invalidation metrics
- Invalidation by symbol, timeframe, or all
- Deterministic: same key → same snapshot

### Metrics
- `hits`, `misses`, `invalidations`
- `hit_rate`
- `size`, `max_size`

---

## 5. PERSISTENCE LAYER

**File:** `persistence.py` (200 lines)

### New Tables (safe, idempotent migration)
| Table | Purpose |
|-------|---------|
| `agent_runs` | Execution lifecycle records |
| `agent_results` | Serialized AgentResult payloads |
| `evidence_items` | Structured evidence items |
| `agent_claims` | Claims for Brain validation |
| `feature_snapshots` | Cached feature data |

### Indexes
- `idx_agent_runs_agent_id`, `idx_agent_runs_symbol`, `idx_agent_runs_status`, `idx_agent_runs_cutoff`
- `idx_evidence_exec`, `idx_claims_exec`
- `idx_feature_snap_key` (unique on symbol+timeframe+cutoff)

### Methods
- `migrate()` — safe idempotent schema creation
- `persist_run()` / `get_run()` / `list_runs()`
- `persist_result()` / `get_result()`
- `persist_evidence()` / `get_evidence()`
- `persist_claims()` / `get_claims()`
- `persist_feature_snapshot()` / `get_feature_snapshot()`
- `stats()` — table counts

### DB Safety
- `INSERT OR REPLACE` for idempotency
- Foreign key constraints
- Existing data preserved (no DELETE)
- Schema migration recorded in `schema_migrations`

---

## 6. STRUCTURE LOOKAHEAD AUDIT + FIX

**File:** `structure_lookahead_fix.py` (90 lines)

### Audit Findings (smc_structure_v1.py)
| Function | Risk | Status |
|----------|------|--------|
| `find_swings()` | LOW | Safe — `range(order, n-order)` |
| `structure_events()` | LOW | Safe — `range(n-1)` excludes last bar |
| `swept_extreme()` | LOW | Safe — `tail(lookback+1).iloc[:-1]` |
| `evaluate_smc()` | MEDIUM | Uses last bar for ATR/close |

### Fix
- `filter_by_cutoff(df, cutoff)` — filters bars before cutoff timestamp
- `safe_evaluate_smc(df, cutoff)` — wraps evaluate_smc with cutoff protection
- `label_event_status(event_index, total_bars)` — CONFIRMED/UNCONFIRMED
- `audit_lookahead(df)` — audit report

### Lookahead Protection Model
- Each structure observation bounded by `data_cutoff_timestamp`
- Event status: UNCONFIRMED → CONFIRMED_LATER
- Future confirmation ≠ input to current snapshot

---

## 7. BRAIN OBSERVATION BRIDGE

**File:** `observation_bridge.py` (110 lines)

### Bridges AgentResult → Brain Tables
| Source | Target Table |
|--------|-------------|
| AgentResult | brain_observations |
| Evidence items | brain_evidence |
| Claims | brain_claims |
| Observation→Evidence link | brain_observation_evidence |

### Design Decisions
- Does NOT modify existing Brain engines
- Only adds observation records
- Claims stored as UNTESTED (no auto-validation)
- Evidence linked to observations via observation_date
- Metadata JSON preserves full traceability

---

## 8. OPENAI AGENTS SDK DECISION

**Decision: NOT INTEGRATED in Phase C**

### Reasoning
1. `agents/agent_runtime_v1.py` already wraps existing stack as SDK agent
2. Phase C goal: deterministic runtime, not LLM orchestration
3. Existing 8 adapters are deterministic — no LLM needed
4. SDK integration adds hallucination risk for market calculations
5. Research-only constraint: no auto-trading, no execution

### Future Consideration (Phase D/E)
- LLM for: reasoning synthesis, natural language explanation, research orchestration, critic, HQ synthesis
- LLM NOT for: OHLC, ATR, ADX, BOS, CHoCH, regime, backtest, outcomes
- If integrated: minimal, isolated, optional boundary

---

## 9. EXISTING SYSTEMS PRESERVED

| System | Status |
|--------|--------|
| agent_runtime_v1.py (SDK wrapper) | ✅ Untouched |
| brain_research_agent_v4.py | ✅ Untouched |
| brain_observation_engine_v2.py | ✅ Untouched |
| brain_research_observation_bridge_v3.py | ✅ Untouched |
| All 8 engine adapters | ✅ Unmodified |
| agent_contract.py | ✅ Extended (added to_dict) |
| engine_adapters.py | ✅ Unmodified |
| All brain DB tables | ✅ Preserved |
| setup_outcomes (12,651) | ✅ Preserved |
| market_datasets (100) | ✅ Preserved |

---

## 10. TEST SONUÇLARI

| Test Seti | Count | Status |
|-----------|-------|--------|
| Mevcut backtest engine | 27 | ✅ PASS |
| Mevcut learning infrastructure | 45 | ✅ PASS |
| Data expansion phases 9-12 | 11 | ✅ PASS |
| Phase B agent contract | 65 | ✅ PASS |
| **Yeni Phase C** | **62** | ✅ PASS |
| **TOPLAM** | **210** | ✅ 210/210 PASS |

### Phase C Test Detayları
- Agent runtime lifecycle ✅
- Registry ✅
- Execution request validation ✅
- AgentResult persistence ✅
- AgentRun persistence ✅
- Evidence persistence ✅
- Claim persistence ✅
- Feature snapshot cache ✅
- Cache invalidation ✅
- Deterministic replay ✅
- Multi-agent execution ✅
- Failure isolation ✅
- Cutoff validation ✅
- Lookahead protection ✅
- Brain observation bridge ✅
- Observation persistence ✅
- Unavailable feature handling ✅
- Version tracking ✅
- Existing engine adapter integration ✅
- SDK integration boundary ✅

---

## 11. YENİ DOSYALAR

| Dosya | Satır | Açıklama |
|-------|-------|----------|
| `agent_runtime.py` | 200 | AgentRuntime lifecycle + AgentRun |
| `agent_registry.py` | 80 | AgentAdapterRegistry |
| `feature_cache.py` | 95 | FeatureSnapshotCache (LRU) |
| `persistence.py` | 200 | DB persistence + migration |
| `observation_bridge.py` | 110 | Brain observation bridge |
| `structure_lookahead_fix.py` | 90 | Lookahead audit + protection |
| `test_phase_c.py` | 680 | 62 Phase C test |
| `MARKETHQ_AGENT_RUNTIME_PHASE_C_REPORT.md` | — | Bu dosya |

---

## 12. KALAN RİSKLER

| # | Risk | Önem | Azaltma |
|---|------|------|---------|
| 1 | smc_structure_v1 lookahead | MEDIUM | filter_by_cutoff + safe_evaluate_smc |
| 2 | Quality V4 r=0.16 | MEDIUM | Research-only label |
| 3 | FB/TEST data corruption | MEDIUM | Filter out veya mark unreliable |
| 4 | volume_ratio per-setup missing | LOW | Dataset-level mevcut |
| 5 | Brain claim validation | LOW | Claims stored as UNTESTED |
| 6 | OpenAI SDK integration | LOW | Phase D/E'de değerlendirilecek |
| 7 | Agent reliability tracking | MEDIUM | Phase D'de |
| 8 | Cache thread safety | LOW | Single-threaded for now |
| 9 | Feature snapshot DB persistence | LOW | feature_snapshots table created |

---

## 13. PHASE D HAZIRLIĞI

Phase C sonunda hazır:

✅ Agent Runtime — execution lifecycle
✅ Agent Registry — adapter discovery
✅ FeatureSnapshotCache — shared feature cache
✅ PersistenceLayer — DB operations + migration
✅ Brain Observation Bridge — AgentResult → brain tables
✅ Lookahead Protection — cutoff enforcement
✅ 8 Engine Adapters — working
✅ 210 Tests — all PASS

Phase D olacak:
- Strategy Research Agents (Trend, Breakout, Reversal)
- Opportunity Detection Engine
- Setup Intelligence Engine
- Critic Agent
- HQ Synthesis
- Full Brain Learning Pipeline

---

## 14. ÖNEMLİ KARARLAR

1. **AgentRuntime V2 yeni** — V1 SDK wrapper untouched
2. **AgentRegistry explicit** — no auto-discovery
3. **Cache in-memory** — Redis not needed yet
4. **DB migration safe** — INSERT OR REPLACE, no DELETE
5. **Lookahead audit completed** — filter_by_cutoff implemented
6. **Brain bridge read-only** — existing engines untouched
7. **No LLM integration** — deterministic only
8. **210 tests pass** — 148 existing + 62 new
9. **Research-only** — no broker, no trading, no execution
10. **Existing 83 tests preserved** — 72/72 + 11/11 + 65/65 + 62/62