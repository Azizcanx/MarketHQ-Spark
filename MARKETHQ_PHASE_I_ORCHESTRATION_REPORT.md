# MARKETHQ PHASE I — ORCHESTRATION REPORT

**Date:** 2026-09-16
**Phase:** I

---

## Research Orchestrator

The orchestrator is a thin layer on top of existing AgentRuntime.
It does NOT replace AgentRuntime, AgentRegistry, Brain, or any existing engine.

## Architecture

```
ResearchTask
    ↓
ResearchOrchestrator
    ↓
AgentRuntime (existing)
    ↓
AgentResult
    ↓
Persistence + Provenance
```

## Responsibilities

1. Accept research tasks
2. Resolve agent, dependencies, feature snapshot
3. Run agent through existing AgentRuntime
4. Collect AgentResult
5. Persist execution metadata
6. Forward evidence
7. Trigger downstream research tasks
8. Preserve provenance
9. Handle failure isolation

## DAG-like Dependencies

Tasks can declare dependencies on other tasks.
The orchestrator resolves dependencies before execution.
Circular dependencies are detected and reported.

## Pipeline Example

```
MARKET_SCAN
    ↓
REGIME_RESEARCH
    ↓
STRATEGY_RESEARCH
    ↓
OPPORTUNITY_DETECTION
    ↓
SETUP_SYNTHESIS
    ↓
HISTORICAL_EVIDENCE
    ↓
CRITIC
    ↓
HQ SYNTHESIS
    ↓
HUMAN REVIEW
```

## Failure Isolation

When an agent fails:
1. Task marked FAILED
2. Agent health updated
3. Downstream tasks with dependency on failed task are BLOCKED
4. Independent tasks continue
5. Error is recorded in provenance chain

## No Silent Failures

Every failure is:
- Recorded in task status
- Recorded in agent health
- Recorded in provenance chain
- Reported in orchestrator run summary

## Provider Unavailable

If Hermes is unavailable:
1. Task marked BLOCKED
2. Agent health marked UNAVAILABLE
3. No fake research output produced
4. Fallback to other runtime requires explicit configuration
5. Fallback reason is recorded in provenance

## Key Guarantees

- No duplicate engines
- No runtime replacement
- No silent fallback
- No fake output
- Every failure is visible
- Every success is traced
- Every task has provenance