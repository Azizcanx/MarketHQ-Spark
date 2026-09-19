# MARKETHQ PHASE I — ARCHITECTURE REPORT

**Date:** 2026-09-16
**Phase:** I — Agentic HQ Orchestration + Decision Surface + Human Research Review

---

## 1. Current Architecture

MarketHQ remains:

```
RESEARCH → EXPERIMENT → BACKTEST → VALIDATION → LEARNING
→ BRAIN → OPPORTUNITY → RESEARCH-BACKED SETUP
→ CRITIC → HUMAN REVIEW → OUTCOME → LEARNING
```

## 2. What Was Reused

- `agent_runtime.py` — existing runtime abstraction (extended with health)
- `agent_registry.py` — existing registry (extended with capability metadata)
- `persistence.py` — existing DB persistence (additive tables only)
- `observation_bridge.py` — existing Brain bridge (unchanged)
- `opportunity_engine.py` — existing opportunity engine (unchanged)
- `research_validation_engine.py` — Phase G validation (unchanged)
- `research_intelligence_engine.py` — Phase H intelligence (unchanged)

## 3. What Was Extended

- `AgentProfile` — added capability + health + status
- `AgentHealth` — new health + diagnostics model
- `ResearchTask` — new task abstraction on top of AgentRuntime
- `ResearchOrchestrator` — new thin orchestration layer
- `ResearchWorkspace` — new context view (references Brain)
- `ProvenanceNode` — new provenance chain
- `HumanReview` — new human research review model
- `ResearchArtifact` — new artifact model with lifecycle
- `HQSynthesis` — new HQ synthesis layer
- `Permission` — new research permission model

## 4. What Was Added

- `research_agent_model.py` — agent identity + capability
- `research_orchestrator_model.py` — task + health models
- `research_orchestrator.py` — orchestration engine
- `research_hq_surface.py` — human review + HQ synthesis + permissions + artifacts + provenance
- `test_research_orchestration.py` — 123 Phase I tests

## 5. AgentSpace Concepts Adopted

1. AgentRouter → Thin runtime router in orchestrator
2. Agent capabilities → Capability metadata in registry
3. Task orchestration → Research orchestrator with DAG dependencies
4. Runtime diagnostics → Agent health model
5. Shared workspace context → Research workspace (references Brain)
6. Human approval gates → Human research review layer
7. Audit trail → Unified provenance chain
8. Permission boundaries → Research permission model
9. Output/artifact lifecycle → Artifact model with status

## 6. AgentSpace Concepts Rejected

1. Remote daemon/worker — MarketHQ is single-machine
2. Sandbox boundaries — Not applicable to research system
3. Digital employee model — Over-engineering for research agents
4. Wholesale AgentSpace adoption — Would duplicate MarketHQ engines

## 7. Phase H Quality Gate Findings

| Subsystem | Status | Ready for UI |
|-----------|--------|-------------|
| Research Memory | EXPERIMENTAL | NO |
| Claim Quality | UNSTABLE | NO |
| Reliability | EXPERIMENTAL | NO |
| Similarity | EXPERIMENTAL | NO |
| Adaptive Research | NOT TESTED | NO |
| Data Coverage | LIMITED | NO |
| Computational Cost | ACCEPTABLE | YES |
| Failure Modes | PARTIAL | NO |
| Temporal Stability | UNTESTED | NO |
| Sample Sizes | CRITICAL | NO |

## 8. Tests

- Phase A-F: 332
- Phase G: +69
- Phase H: +89
- Phase I: +123
- **Total: 613 PASS**

## 9. Performance

- Average agent execution: Not measured (research-only)
- Orchestration overhead: Minimal (in-memory)
- Feature-cache hit rate: N/A (no cache in Phase H/I)
- Duplicate computation: Not tracked
- Database writes: Minimal (no persistence layer yet)
- Dashboard query time: N/A (no dashboard)
- Historical similarity cost: O(n) per query
- Claim validation cost: O(n) per claim
- Memory query cost: O(n) per query

## 10. Data Limitations

- THYAO.IS 1h only
- Synthetic data in tests
- No multi-asset validation
- No multi-timeframe validation
- No survivorship bias assessment

## 11. Reliability Limitations

- Profiles computed on synthetic data only
- No real agent outcome tracking yet
- Regime-specific reliability needs regime-labeled outcomes
- Temporal stability needs time-series of outcomes

## 12. Claim Limitations

- All 20 Phase G claims are UNTESTED
- Validation uses simple consistency ratio
- No temporal stability measurement
- No regime-specific validation

## 13. Runtime Limitations

- Single-machine execution
- No distributed workers
- No runtime router (Phase I Step 11 deferred)
- Hermes only

## 14. Security Boundaries

- No broker integration
- No live trading
- No automatic order execution
- No trade execution authority
- No automatic claim promotion
- No automatic weight activation
- 12 explicit research permissions
- Trading permissions explicitly excluded

## 15. Known Bugs

- None critical
- Some LSP diagnostics are false positives (model field names)
- AgentHealth status comparison works correctly at runtime

## 16. Unresolved Issues

1. Persistence layer not implemented (in-memory only)
2. Research memory retrieval quality not validated
3. Similarity score outcome correlation not validated
4. Agent reliability needs real outcome data
5. Claim validation needs real data
6. Dashboard UI not built
7. Runtime router not implemented (Step 11 deferred)
8. Scheduler integration not implemented (Step 12 deferred)
9. Performance benchmarking not done
10. Adaptive research not validated

## 17. Phase J Recommendation

Phase I completes the research intelligence + HQ orchestration layer.

Phase J should be:
- UI / HQ Decision Surface / Human Review implementation
- Persistence layer (SQLite/JSON)
- Research memory retrieval + similarity validation
- Agent reliability with real outcome data
- Claim validation with real data
- Performance benchmarking
- Runtime router implementation
- Scheduler integration

**Do NOT auto-start Phase J.**
First validate Phase I results, then decide Phase J priorities based on:
- Research memory quality
- Claim quality
- Reliability stability
- Similarity usefulness
- Adaptive research results
- Data coverage
- Computational cost
- Unresolved limitations