# MARKETHQ PHASE I — END-TO-END RESEARCH REPORT

**Date:** 2026-09-16
**Asset:** THYAO.IS
**Timeframe:** 1h
**Data:** 531 real bars (Jun 25 - Sep 16, 2026)
**Cutoff:** Sep 9, 2026 (481 bars)

---

## Pipeline Execution

| Stage | Status | Details |
|---|---|---|
| DATA | ✓ | THYAO.IS 1h real OHLCV from yfinance |
| FEATURE SNAPSHOT | ✓ | ATR=2.41, RSI=69.2, ADX=30.7, 24 features |
| REGIME | ✓ | 9-strategy regime matrix computed |
| STRATEGY AGENTS | ✗ | All 7 agents fail (ADAPTER_NOT_FOUND) |
| OPPORTUNITY ENGINE | ✓ | 1 opportunity (no agent evidence) |
| SETUP SYNTHESIS | ✗ | 0 setups (no agent evidence) |
| HISTORICAL EVIDENCE | ✗ | 0 outcomes |
| CRITIC | ✗ | 0 findings |
| RESEARCH INTELLIGENCE | ✓ | 7 observations |
| HQ SYNTHESIS | ✓ | Synthesis generated |
| PROVENANCE | ✓ | 15 nodes, 0 missing |
| HUMAN REVIEW | ✓ | Review created |

## Critical Blocker

Strategy research agents (Trend, Breakout, Reversal, Momentum, Volatility, Liquidity, Structure) are non-functional in end-to-end mode.

**Root cause:** AgentRegistry stores adapter CLASSES, AgentRuntime.run() calls `adapter.run(ctx)` on the class. The adapter expects to be instantiated with context first.

**Evidence:**
```
Status: FAILED
Error type: AttributeError
Error msg: 'MarketContext' object has no attribute 'context'
```

The MarketContext is being passed as `self` to the adapter's `run()` method.

## Fix Required

In `agent_runtime.py`, change:
```python
result = adapter.run(ctx)
```
to:
```python
adapter_instance = adapter(ctx)
result = adapter_instance.run()
```

Or update the registry to store instances instead of classes.

## What Works End-to-End

1. Data loading (yfinance real data)
2. Feature snapshot computation
3. Regime analysis
4. Opportunity engine (degraded mode — no agent evidence)
5. Research intelligence (observations, failure analysis)
6. HQ synthesis (works with UNAVAILABLE agents)
7. Provenance chain (complete)
8. Human review model

## What Does NOT Work End-to-End

1. Strategy research agents (registry/runtime bug)
2. Research-backed setup generation (no agent evidence)
3. Historical evidence replay (no setups)
4. Critic analysis (no outcomes)

## Determinism Verified

- FeatureSnapshot: Identical across runs ✓
- Agent execution: Consistent failures ✓
- Pipeline: Reproducible ✓
