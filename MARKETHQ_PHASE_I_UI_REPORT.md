# MARKETHQ PHASE I — UI REPORT

**Date:** 2026-09-16
**Phase:** I

---

## HQ Decision Surface

The main dashboard shows:

### 1. Market Overview
- Monitored assets
- Timeframe
- Regime
- Volatility
- Data health

### 2. Active Opportunities
For each:
- Asset
- Timeframe
- Direction
- Opportunity thesis
- Status
- Evidence consistency
- Uncertainty
- Supporting agents
- Conflicting agents
- Last update

### 3. Research-Backed Setups
For each:
- Setup type
- Entry zone
- Confirmation
- Invalidation
- Targets
- Geometric RR
- Research confidence (NOT probability)
- Uncertainty flags
- Evidence trace
- Historical evidence
- Validation state

### 4. Critic
- Objections
- Contradictions
- Missing evidence
- Invalidation concerns
- Data limitations

### 5. Research Memory
- Relevant past observations
- Failure patterns
- Counterexamples
- Similar historical setups
- Relevant claims

### 6. Claims
- Claim text
- Status (UNTESTED/TESTED/SUPPORTED/UNSTABLE/REJECTED)
- Sample size
- Effect size
- Temporal stability
- Supporting evidence
- Counterexamples

### 7. Experiments
- Hypothesis
- Configuration hash
- Baseline
- Challenger
- Result
- Status

### 8. Agent Health
- Agent name
- Status (READY/RUNNING/DEGRADED/FAILED/UNAVAILABLE/DISABLED)
- Last run
- Failure count
- Dependency health
- Runtime

### 9. Human Review Queue
- UNREVIEWED
- NEEDS_MORE_DATA
- REVIEWED
- ACCEPTED_FOR_RESEARCH
- REJECTED

## UI Rules

1. Research confidence is NOT probability
2. Geometric RR is NOT expected return
3. Similarity is NOT prediction
4. Weight proposals are NOT active weights
5. Claims are NOT truths
6. Memory is NOT truth database
7. Every number preserves sample size
8. No misleading aggregate statistics
9. Unavailable data is shown, not hidden
10. Conflicting evidence is shown, not smoothed

## UI Limitations

- Dashboard is research-first, not trading-first
- No buy/sell signals
- No order management
- No portfolio view
- No P&L tracking
- No trade history
- No execution controls

## UI Next Steps

Phase I UI is a research dashboard.
Trading terminal is NOT in scope.
Any future trading UI must be explicitly separated
and require explicit human approval per trade.