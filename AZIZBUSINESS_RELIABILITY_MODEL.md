# AZIZBUSINESS RELIABILITY MODEL

**Date:** 2026-09-17

---

## Overview

Agent reliability tracking — separate from agent health.

### Health ≠ Reliability

**Health** = "Can it execute?"
- Agent is running
- Agent responds to requests
- Agent doesn't crash

**Reliability** = "How useful/accurate has its research historically been?"
- Quality of evidence produced
- Outcome alignment
- Regime-specific performance
- Timeframe-specific performance
- Symbol-specific performance

## Reliability Profile

Each agent has a reliability profile tracking:

- Total executions
- Successful executions
- Failed executions
- Unavailable results
- Useful evidence count
- Contradicted evidence count
- Outcome alignment score (0-1)
- Regime-specific reliability
- Timeframe-specific reliability
- Symbol-specific reliability
- Drift detection flag
- Last updated timestamp

### Reliability Score (Composite)

```
reliability_score =
  0.3 * (useful_evidence / (useful_evidence + contradicted_evidence))
+ 0.3 * (1 - min(contradicted / total, 1))
+ 0.4 * outcome_alignment_score
```

## Tracking Methods

### Record Execution

```python
tracker.record_execution(
    agent_id="trend_agent",
    success=True,
    useful_evidence=True,
    contradicted=False,
    outcome_aligned=True,
    regime="TRENDING",
    timeframe="1h",
    symbol="THYAO.IS",
)
```

### Record Unavailable

```python
tracker.record_unavailable("agent-id")
```

### Mark Drift

```python
tracker.mark_drift("agent-id", drift_detected=True)
```

## Queries

### Get Reliable Agents

```python
reliable = tracker.get_reliable_agents(min_score=0.5)
```

### Get Unreliable Agents

```python
unreliable = tracker.get_unreliable_agents(max_score=0.3)
```

### Get Summary

```python
summary = tracker.get_reliability_summary()
```

## Regime-Specific Reliability

Reliability is tracked per regime:
- TRENDING
- RANGE
- RANGE_LOW_VOL
- etc.

If an agent performs well in TRENDING but poorly in RANGE,
the reliability profile reflects this.

## Timeframe-Specific Reliability

Reliability is tracked per timeframe:
- 15m
- 1h
- 4h
- daily

## Symbol-Specific Reliability

Reliability is tracked per symbol:
- THYAO.IS
- AAPL
- etc.

## Drift Response

When drift is detected for an agent:
1. Mark agent as drifted
2. Trigger reliability review
3. Reduce priority for drifted agent
4. Require human review if severe

## Integration with HQ

Reliability is exposed via:
- /reliability — all agent reliability summary
- /agents/{id} — specific agent reliability profile
- /hq/overview — reliability summary in overview
- /hq/situation — agent reliability in situation report

## Limitations

- Reliability is based on historical data
- Small sample sizes → unreliable estimates
- Regime changes may invalidate past reliability
- Requires sufficient executions for meaningful scores
- Minimum 10 executions recommended for reliability score