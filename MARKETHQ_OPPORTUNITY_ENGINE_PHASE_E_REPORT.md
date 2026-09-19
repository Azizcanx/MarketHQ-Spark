# MARKETHQ — OPPORTUNITY ENGINE PHASE E REPORT

**Date:** 2026-09-16
**Phase:** E — Opportunity Engine
**Status:** COMPLETE
**Research-only:** Yes — no broker, no orders, no trading

---

## 1. Architecture

```
Market Data (yfinance OHLCV)
    ↓
FeatureSnapshot (Phase C cache)
    ↓
Strategy Research Agents (Phase D — 7 agents)
    ↓
AgentResult[]
    ↓
OPPORTUNITY ENGINE (Phase E — NEW)
    ↓
Opportunity {
    direction, thesis, confidence, uncertainty,
    supporting_evidence, conflicting_evidence, unavailable_evidence,
    strategy_families, independent_families, correlated_families,
    lifecycle_status, source_agents, feature_snapshot_id
}
    ↓
Setup Candidate (CANDIDATE status — not a trade)
    ↓
Brain Observation (via existing observation_bridge)
    ↓
Phase F — Research-Backed Signal/Setup Engine
```

---

## 2. Opportunity Object Model

**File:** `opportunity_model.py` (259 lines)

Core dataclasses:
- `Opportunity` — lifecycle record with 20+ fields
- `SourceAgent` — per-agent traceability
- `SetupCandidate` — candidate entry/invalidation/target (not a trade)

Enums:
- `Direction` — LONG / SHORT / NEUTRAL / UNKNOWN
- `OpportunityStatus` — DETECTED / UNDER_REVIEW / VALIDATED / INVALIDATED / EXPIRED / ARCHIVED

---

## 3. Aggregation Logic

**File:** `opportunity_engine.py` (569 lines + helper)

### Detection Flow

1. Filter to valid results (exclude ERROR)
2. Classify each agent result: supporting / conflicting / unavailable
3. Determine direction by majority of supporting agents
4. Compute strategy family diversity (correlated vs independent)
5. Calculate confidence (NOT win probability)
6. Generate deterministic thesis
7. Set initial status (DETECTED or UNDER_REVIEW)

### Confidence Formula

```
confidence = direction_agreement × family_factor × avg_quality × avg_agent_confidence × supporting_ratio
```

- **direction_agreement:** fraction of supporting agents agreeing on direction
- **family_factor:** independent families / total families seen
- **avg_quality:** average data_quality from FeatureSnapshot
- **avg_agent_confidence:** average agent confidence (observation strength)
- **supporting_ratio:** supporting agents / total valid agents

This is evidence consistency — NEVER win probability.

---

## 4. Evidence Model

Per opportunity, evidence is split into 3 lists:

- **supporting_evidence:** agents with same direction as opportunity
- **conflicting_evidence:** agents with opposite direction
- **unavailable_evidence:** NEUTRAL/UNKNOWN/INSUFFICIENT_DATA/ERROR agents

Conflicting evidence is NEVER deleted. It's always visible for audit.

---

## 5. Conflict Model

Examples:

| Agent | Direction | Classification |
|-------|-----------|----------------|
| Trend | SHORT | supporting |
| Momentum | SHORT | supporting |
| Reversal | LONG | conflicting |
| Breakout | NEUTRAL | unavailable |

The conflict is preserved in the Opportunity record and never resolved away.

---

## 6. Strategy Family Handling

Uses Phase D metadata (`STRATEGY_FAMILY_MAP`):

- **trend** family: strategy_trend, strategy_breakout (correlated)
- **mean_reversion** family: strategy_reversal
- **momentum** family: strategy_momentum
- **volatility** family: strategy_volatility
- **liquidity** family: strategy_liquidity
- **structure** family: strategy_structure

Correlation pairs: `(trend, breakout)`, `(breakout, trend)`

Only INDEPENDENT families increase the confidence family_factor.

---

## 7. Regime Integration

Uses existing regime engine:
- Regime passed from FeatureSnapshot
- Included in Opportunity
- Referenced in thesis
- NOT duplicated — reuses Phase C regime system

---

## 8. Lifecycle

| Status | Meaning |
|--------|---------|
| DETECTED | First meaningful evidence formed |
| UNDER_REVIEW | Multiple agents but conflicts/data limitations |
| VALIDATED | Validation criteria met (research only) |
| INVALIDATED | Supporting conditions no longer valid |
| EXPIRED | Time window expired |
| ARCHIVED | Historical record |

VALIDATED ≠ trade will succeed. It means research validation criteria were met.

---

## 9. Deduplication

Same symbol + timeframe + direction + regime → same opportunity (update, not create).
Archived opportunities don't block new ones.
Different regime or direction → new opportunity.

---

## 10. Persistence

**File:** `opportunity_persistence.py` (330 lines)

Tables:
- `opportunities` — full Opportunity record as JSON
- `opportunity_evidence` — evidence items per opportunity

Features:
- Idempotent migration (adds tables if missing)
- Save, retrieve, list, update, delete, set_status
- Evidence CRUD
- Feature snapshot reference stored

---

## 11. Brain Integration

Uses existing `observation_bridge.py`:
- Opportunity can be pushed as observation
- Labeled as UNTESTED (no historical validation yet)
- NOT marked as proven claim

---

## 12. Setup Candidate

**File:** `opportunity_engine.py` — `generate_setup_candidate()`

Setup Candidate fields:
- symbol, timeframe, direction, opportunity_id, regime
- thesis
- candidate_entry_zone (CANDIDATE, not confirmed)
- invalidation_candidate (CANDIDATE)
- target_candidate (CANDIDATE)
- supporting/conflicting evidence references
- historical_evidence_reference
- quality_reference
- uncertainty

Status: CANDIDATE — not a trade recommendation.

---

## 13. Lookahead Protection

- Opportunity uses FeatureSnapshot (cutoff-time data only)
- No future bars used in detection
- Replay tests verify determinism
- Feature snapshot ID stored for audit

---

## 14. Multi-Asset / Multi-Timeframe

- Parametric: symbol and timeframe are inputs
- Data unavailable → UNAVAILABLE status
- Not hardcoded to THYAO.IS / 1h

---

## 15. Tests

**File:** `test_opportunity_engine.py` (72 tests, 7 categories)

| Category | Count |
|----------|-------|
| Opportunity Model | 7 |
| Strategy Family Metadata | 4 |
| Evidence Classification | 8 |
| Opportunity Detection | 11 |
| Strategy Family Diversity | 3 |
| Conflict Analysis | 2 |
| Thesis Generation | 4 |
| Lifecycle | 7 |
| Deduplication | 5 |
| Persistence | 7 |
| Setup Candidate | 3 |
| Multi-Symbol/Timeframe | 2 |
| Lookahead Protection | 2 |
| Edge Cases | 4 |
| Regression | 3 |
| **Total** | **72** |

---

## 16. Full Regression

| Suite | Tests |
|-------|-------|
| Phase C | 127 |
| Phase D | 64 |
| Phase E | 72 |
| **Total** | **263** |
| **PASS** | **263** |
| **FAIL** | **0** |

---

## 17. New Files

| File | Lines | Purpose |
|------|-------|---------|
| `opportunity_model.py` | 259 | Opportunity dataclasses, enums |
| `opportunity_engine.py` | 569 | Detection, aggregation, conflict, thesis, lifecycle |
| `opportunity_persistence.py` | 330 | DB tables, CRUD, migration |
| `test_opportunity_engine.py` | 800+ | 72 tests |
| `MARKETHQ_OPPORTUNITY_ENGINE_PHASE_E_REPORT.md` | This file | Report |
| `MARKETHQ_OPPORTUNITY_MODEL.md` | Separate doc | Object model reference |

---

## 18. Known Limitations

1. **No historical validation** — opportunities are UNTESTED until Phase F
2. **Confidence is evidence consistency** — not win probability
3. **Quality V4 separation** — quality score ≠ opportunity confidence
4. **Correlation is static** — uses fixed family correlation pairs
5. **Deduplication threshold** — same symbol+timeframe+direction+regime; may need tuning
6. **No real-time streaming** — batch detection only
7. **Brain integration** — observation bridge exists, but auto-push not configured

---

## 19. Phase F Recommendations

1. **Research-Backed Signal/Setup Engine** — entry zone, invalidation, target with research backing
2. **Historical validation pipeline** — backtest opportunities against historical outcomes
3. **Quality V4 integration** — proper quality scoring separate from confidence
4. **Brain claim verification** — only verified claims become truth
5. **Real-time streaming** — live opportunity detection
6. **Web dashboard** — opportunity monitoring UI
7. **Confidence calibration** — tune weights with historical data
8. **Correlation learning** — learn family correlations from data

---

## 20. Important Warnings

- **Opportunity confidence ≠ win probability**
- **VALIDATED ≠ trade will succeed**
- **CANDIDATE ≠ trade recommendation**
- **UNTESTED = no historical validation yet**
- **No broker, no orders, no trading, no real money**
- **No fake data** — all evidence from real OHLCV
- **No lookahead** — cutoff-time data only
