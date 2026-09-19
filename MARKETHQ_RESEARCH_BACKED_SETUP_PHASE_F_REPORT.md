# MARKETHQ — RESEARCH-BACKED SETUP PHASE F REPORT

**Date:** 2026-09-16
**Phase:** F — Research-Backed Signal/Setup Engine
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
Opportunity Engine (Phase E)
    ↓
Opportunity
    ↓
Research-Backed Setup Engine (Phase F — NEW)
    ↓
ResearchBackedSetup {
    entry_zone, confirmation, invalidation, targets,
    risk_reward, supporting/conflicting evidence,
    historical evidence, uncertainty flags,
    why_panel, evidence traces, confidence
}
    ↓
Brain Observation (via existing observation_bridge)
    ↓
Human Review
    ↓
Phase G
```

---

## 2. Setup Model

**File:** `opportunity_model.py` (extended)

New types:
- `SetupStatus` — CANDIDATE / UNDER_REVIEW / CONFIRMED_RESEARCH_SETUP / INVALIDATED / EXPIRED / ARCHIVED
- `UncertaintyType` — 9 uncertainty categories
- `UncertaintyFlag` — specific uncertainty with severity
- `EvidenceTrace` — assertion → source traceability
- `ResearchBackedSetup` — full setup record

---

## 3. Entry Zone Engine

**Function:** `_compute_entry_zone(df, direction, atr)`

Combines:
- Structure-based zone (support/resistance from SMC swings)
- ATR-based zone (volatility-adjusted ±0.5 ATR)
- Directional logic: LONG → near support, SHORT → near resistance

Returns: `{low, high, reference, method, status}`

Data unavailable → `status: UNAVAILABLE`, no fake levels.

---

## 4. Entry Confirmation

**Function:** `_compute_entry_confirmation(df, direction, regime)`

Detects:
- Volume surge (VOLUME_RATIO > 1.0)
- Regime alignment (trend regime matches direction)
- Structure break (BOS/CHoCH in direction)

No confirmation → empty list (not fake).

---

## 5. Invalidation Engine

**Function:** `_compute_invalidation(df, direction, entry, atr, regime)`

Combines:
- ATR-based: ATR × 2.0 stop-loss
- Structure-based: BOS/CHoCH in opposite direction
- Tighter of the two

Returns: `{price, type, reason, distance_atr}`

No data → `price: None, type: unavailable`.

---

## 6. Target Engine

**Function:** `_compute_targets(df, direction, entry, atr, regime)`

Combines:
- ATR-based: T1 = entry ± 1×ATR, T2 = ±2×ATR, T3 = ±3×ATR
- Structure-based: swing points in direction

Returns: `{t1, t2, t3, method}`

No data → all None, method: "unavailable".

---

## 7. Risk / Reward

**Function:** `_compute_rr(direction, entry, invalidation, target)`

- Risk = |entry - invalidation|
- Reward = |target - entry|
- RR = reward / risk

RR is a geometric measure, NOT a quality score.

---

## 8. WHY Panel

**Function:** `_generate_why_panel(setup, direction, supporting, conflicting, regime)`

Produces structured WHY panel:

```
WHY THIS SETUP EXISTS

Market Context: symbol, timeframe, regime
Direction: SHORT
Supporting Evidence: agent list
Conflicting Evidence: agent list
Entry: zone + method
Invalidation: price + reason
Targets: T1/T2/T3 + method
Historical Evidence: available/unavailable + sample
Uncertainty: flags
Research Flags: warnings
```

No marketing language. No "buy"/"sell". No "win".

---

## 9. Evidence Traceability

Each setup assertion links to source:

```python
EvidenceTrace(
    assertion="Trend supports SHORT",
    source_agent="strategy_trend",
    feature_snapshot_id="...",
    evidence_feature="EMA_FAST",
    evidence_value=265.0,
)
```

No black-box setups. Full audit trail.

---

## 10. Historical Evidence

Uses existing `setup_outcome_tracker.get_historical_stats()`:
- Sample size check (< 30 → LOW_SAMPLE)
- Win rate, avg return
- Survivorship bias note

Historical evidence is REFERENCE only, not proof.

---

## 11. Uncertainty Engine

**Function:** `_compute_uncertainty(...)`

Auto-detects 9 uncertainty types:
- missing_volume
- missing_structure
- low_sample
- regime_instability
- conflicting_agents
- insufficient_history
- feature_unavailable
- weak_entry_geometry
- weak_target_geometry

Each with severity: low / medium / high / critical

Overall uncertainty computed from flag severity.

---

## 12. Lifecycle

| Status | Meaning |
|--------|---------|
| CANDIDATE | Initial setup candidate |
| UNDER_REVIEW | Conflicts or data limitations |
| CONFIRMED_RESEARCH_SETUP | Research criteria met (NOT trade confirmed) |
| INVALIDATED | Thesis no longer valid |
| EXPIRED | Context changed |
| ARCHIVED | Historical record |

CONFIRMED_RESEARCH_SETUP ≠ trade confirmed.

---

## 13. Deduplication

Uses Opportunity dedup logic. Same opportunity → same setup.
Fingerprint: opportunity_id + direction + setup_type + entry zone bucket + invalidation bucket + target geometry.

---

## 14. Strategy Family Mapping

Uses Phase D STRATEGY_FAMILY_MAP:
- trend → trend continuation setup
- breakout → breakout/retest setup
- mean_reversion → reversal candidate
- momentum → momentum continuation
- volatility → expansion/compression context
- liquidity → liquidity reaction
- structure → structure-based setup

---

## 15. Regime Integration

Uses existing regime_filter.py:
- Regime from Opportunity
- Compatibility check via apply_regime_filter()
- Historical sample from setup_outcome_tracker

---

## 16. FeatureSnapshot Reuse

Phase C FeatureSnapshot used directly:
- ATR, SMA, EMA, RSI from snapshot
- No recalculation in same cycle
- Snapshot ID referenced in setup

---

## 17. Lookahead Protection

- Entry/invalidation/target use cutoff-time data only
- Structure analysis uses lookahead-fixed SMC
- Historical evidence uses setup_outcome_tracker (pre-computed)
- No future bar usage in geometry

---

## 18. Persistence

Uses existing persistence.py architecture:
- Additive migration (new tables only)
- research_setups table (NEW)
- setup_evidence table (NEW)
- Opportunity → Setup reference preserved

---

## 19. Brain Integration

Uses existing observation_bridge.py:
- Setup → observation (UNTESTED)
- NOT marked as proven claim
- Brain does NOT auto-accept as truth

---

## 20. API / Service

Service interface:
- `build_research_backed_setup(opportunity, df, feature_snapshot_id)`
- `generate_setup_candidate(opportunity)` (from Phase E)
- `get_setup(setup_id)` (from persistence)
- `list_setups(symbol, timeframe, status)` (from persistence)
- `get_setup_why(setup_id)` → why_panel
- `get_setup_evidence(setup_id)` → evidence traces

No web server created — API-ready service layer only.

---

## 21. Deterministic Output

Same input → same output:
- symbol, timeframe, cutoff, FeatureSnapshot, Opportunity
- No randomness
- No LLM dependency
- Fully deterministic

---

## 22. Tests

**File:** `test_research_setup_phase_f.py` (69 tests)

| Category | Count |
|----------|-------|
| ResearchBackedSetup Model | 7 |
| Entry Zone Engine | 7 |
| Invalidation Engine | 5 |
| Target Engine | 5 |
| Risk / Reward | 5 |
| Uncertainty Engine | 5 |
| WHY Panel | 4 |
| Full Pipeline | 15 |
| Lifecycle | 7 |
| Edge Cases | 6 |
| Regression | 4 |
| **Total** | **69** |

---

## 23. Full Regression

| Suite | Tests |
|-------|-------|
| Phase C | 127 |
| Phase D | 64 |
| Phase E | 72 |
| Phase F | 69 |
| **Total** | **332** |
| **PASS** | **332** |
| **FAIL** | **0** |

---

## 24. New Files

| File | Lines | Purpose |
|------|-------|---------|
| `opportunity_model.py` | 475 | Extended with SetupStatus, UncertaintyFlag, EvidenceTrace, ResearchBackedSetup |
| `research_setup_phase_f.py` | 936 | Setup engine: entry, invalidation, targets, RR, uncertainty, WHY panel |
| `test_research_setup_phase_f.py` | 620+ | 69 tests |
| `MARKETHQ_RESEARCH_BACKED_SETUP_PHASE_F_REPORT.md` | This file | Report |
| `MARKETHQ_RESEARCH_SETUP_MODEL.md` | Separate doc | Model reference |

---

## 25. Known Limitations

1. **No historical validation** — setups are UNTESTED until Phase G
2. **Confidence is research confidence** — not win probability
3. **Quality V4 separation** — quality score ≠ setup confidence
4. **Entry zone geometry** — ATR-based + structure, may miss edge cases
5. **Invalidation** — ATR×2.0 baseline, may be too tight/wide
6. **Target geometry** — ATR-based, not market-structure optimal
7. **Correlation is static** — uses fixed family correlation pairs
8. **No real-time streaming** — batch detection only
9. **Brain integration** — observation bridge exists, auto-push not configured
10. **Quality V4 experimental** — not production proven

---

## 26. Phase G Recommendations

1. **Research validation pipeline** — backtest setups against historical outcomes
2. **Confidence calibration** — tune weights with historical data
3. **Correlation learning** — learn family correlations from data
4. **Quality V4 integration** — proper quality scoring
5. **Brain claim verification** — only verified claims become truth
6. **Real-time streaming** — live setup detection
7. **Web dashboard** — setup monitoring UI
8. **Setup outcome tracking** — record actual outcomes
9. **Phase G: Research-Backed Signal/Setup Engine with historical validation**

---

## 27. Important Warnings

- **Setup confidence ≠ win probability**
- **CONFIRMED_RESEARCH_SETUP ≠ trade confirmed**
- **CANDIDATE ≠ trade recommendation**
- **UNTESTED ≠ invalid (no historical validation yet)**
- **No broker, no orders, no trading, no real money**
- **No fake data — all evidence from real OHLCV**
- **No lookahead — cutoff-time data only**
- **Quality V4 experimental — not production proven**
- **RR is geometric measure — NOT quality score**
