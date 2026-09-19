# MARKETHQ — Strategy Research Phase D Report

Date: 2026-09-16
Status: COMPLETE

---

## What Was Built

Phase D adds **7 Strategy Research Agents** on top of the existing deterministic MarketHQ engine stack.

Each agent:
- Takes `MarketContext` (shared feature snapshot)
- Runs deterministic strategy logic (no LLM)
- Produces `AgentResult` with structured observation
- Generates `Evidence` + `Claim` (UNTESTED validation status)
- Respects lookahead protection via data cutoff

---

## Agents Created

| Agent ID | Class | Family | Engine | Key Features |
|---|---|---|---|---|
| strategy_trend | TrendResearchAdapter | trend | strategy_registry_v1 | EMA_FAST, EMA_SLOW, ADX, ATR |
| strategy_breakout | BreakoutResearchAdapter | breakout | strategy_registry_v1 | ATR, donchian_high, donchian_low |
| strategy_reversal | ReversalResearchAdapter | mean_reversion | strategy_registry_v1 | RSI, BOLL_UPPER, BOLL_LOWER |
| strategy_momentum | MomentumResearchAdapter | momentum | signal_engine | SMA_FAST, SMA_SLOW, ADX |
| strategy_volatility | VolatilityResearchAdapter | volatility | signal_engine | ATR, volatility_state |
| strategy_liquidity | LiquidityResearchAdapter | liquidity | smc_structure_v1 | structure, liquidity |
| strategy_structure | StructureResearchAdapter | structure | smc_structure_v1 | structure_events, BOS, CHoCH |

---

## Architecture

```
MarketContext (shared, immutable)
    ↓ FeatureSnapshot (populated by strategy_research_features.py)
Strategy Research Logic (per-agent)
    ↓ AgentResult (structured observation)
    ↓ Evidence + Claims
    ↓ Persistence + Brain Observation Bridge
```

**Key principle**: Agents observe, they don't trade. No broker, no orders, no execution.

---

## Integration Points

1. **AgentRegistry**: All 7 agents registered via `strategy_research_registry.py`
2. **AgentRuntime**: Compatible — agents work through runtime.run()
3. **FeatureSnapshot cache**: Reused across agents (same symbol+timeframe+cutoff)
4. **Persistence**: AgentResult/Evidence/Claim persisted via PersistenceLayer
5. **Brain bridge**: Observation bridge connects to brain_observations table

---

## Feature Population

**New module**: `strategy_research_features.py` — `populate_feature_snapshot()`

Computes ALL indicators from OHLCV in one pass:
- signal_engine: SMA, EMA, RSI, MACD, BB, ATR, Volume Ratio
- strategy_registry_v1: Donchian, SuperTrend, ADX, VWAP, Stochastic, SMC, Opening Range
- smc_structure_v1: Swing events, BOS/CHoCH, structure_type, liquidity_side
- setup_engine_v1: Regime detection

This solves the "agents return INSUFFICIENT_DATA" problem by pre-populating the FeatureSnapshot.

---

## Tests

**New**: 64 tests in `test_strategy_research_agents.py`

Coverage:
- Agent metadata (7 agents registered)
- AgentResult structure (all 7 return valid results)
- Agent-specific logic (trend EMA, breakout ATR, reversal RSI, etc.)
- Feature dependency tracking
- Unavailable feature handling (INSUFFICIENT_DATA / PARTIAL)
- Direction handling (LONG/SHORT/NEUTRAL/UNKNOWN)
- Confidence separation (NOT win probability)
- Claim creation (all UNTESTED)
- Evidence creation (source, feature, direction)
- Runtime integration
- Cache reuse
- Multi-symbol / multi-timeframe
- Lookahead protection
- Deterministic replay

**Total**: 191 tests pass (127 existing + 64 new)

---

## What Phase D Did NOT Include (per spec)

- ❌ Opportunity Engine (Phase E)
- ❌ HQ Synthesis (Phase E)
- ❌ Critic Agent (Phase E)
- ❌ LLM-based strategy calculation (LLM only for orchestration, later)
- ❌ Reliability scoring (learning phase)
- ❌ Any trading/broker/order logic

---

## Known Limitations

1. **structure_type/liquidity_side**: 0% coverage in historical data
2. **momentum_at_entry**: r=0.438 correlation, NOT predictive edge
3. **liquidity_balance**: r=-0.278 correlation, NOT predictive
4. **No OOS validation**: Claims are UNTESTED
5. **Adapter interface mismatch**: Runtime passes ctx to run() but agents use self.context
6. **No real-time data**: Uses yfinance historical snapshots

---

## Phase E Readiness

Phase D output feeds into Phase E:

```
Strategy Research Agents → AgentResult → Evidence → Claims
    ↓
Opportunity Engine (Phase E)
    ↓
HQ Synthesis (Phase E)
    ↓
Critic Agent (Phase E)
```

All 7 agents produce structured AgentResult with:
- direction (LONG/SHORT/NEUTRAL/UNKNOWN)
- confidence (observation strength, 0-1)
- evidence (structured items with source/feature/value)
- claims (UNTESTED, ready for Brain validation)
- engine_metadata (feature dependencies, unavailable features)

Phase E can consume this output directly.

---

## Files Changed/Created

| File | Action | Description |
|---|---|---|
| strategy_research_agents.py | Existing (fixed) | 7 research agents, syntax fix |
| strategy_research_features.py | **Created** | Feature population from OHLCV |
| strategy_research_registry.py | **Created** | AgentRegistry registration |
| test_strategy_research_agents.py | **Created** | 64 Phase D tests |
| MARKETHQ_STRATEGY_AGENT_MAP.md | Existing | Updated with agent details |
| MARKETHQ_STRATEGY_RESEARCH_PHASE_D_REPORT.md | **Created** | This report |

---

*Phase D complete. Ready for Phase E — Opportunity Engine.*