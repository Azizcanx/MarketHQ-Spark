# MARKETHQ PHASE J1 — ARCHITECTURE AUDIT

**Date:** 2026-09-16
**Purpose:** Audit current MarketHQ architecture against AgentSpace-inspired requirements

---

## 1. What Already Exists

### Core Execution
- `agent_runtime.py` — AgentRuntime (execution lifecycle) ✓
- `agent_registry.py` — AgentRegistry (adapter registry) ✓
- `agent_contract.py` — AgentResult, BaseAgentAdapter, MarketContext ✓
- `strategy_research_agents.py` — 7 Strategy Research Adapters ✓
- `strategy_research_registry.py` — Strategy registry ✓

### Phase I / J0
- `research_agent_model.py` — AgentProfile, AgentCapability, AgentStatus ✓
- `research_orchestrator_model.py` — ResearchTask, AgentHealth, TaskStatus ✓
- `research_orchestrator.py` — ResearchOrchestrator (DAG, dependency resolution) ✓
- `research_hq_surface.py` — HumanReview, ResearchArtifact, ProvenanceNode ✓
- `research_intelligence_model.py` — Observation, Hypothesis, Experiment, Claim ✓
- `research_intelligence_engine.py` — Research Intelligence Engine ✓

### Persistence
- `persistence.py` — PersistenceLayer (SQLite) ✓

### Opportunity / Setup
- `opportunity_model.py` — Opportunity, ResearchBackedSetup ✓
- `opportunity_engine.py` — OpportunityEngine ✓

### Research Intelligence
- `research_intelligence_model.py` — ResearchMemory, ReliabilityProfile, CalibrationProfile ✓
- `research_intelligence_engine.py` — Claim validation, weight proposals ✓

### Brain
- `brain_learning_pipeline.py` — Adaptive V1 (reference) ✓

---

## 2. What's Missing

| J1 Requirement | Status | Needed |
|---|---|---|
| Agent identity (detailed metadata) | MISSING | New fields on AgentProfile |
| Capability model (rich metadata) | PARTIAL | AgentCapability exists but basic |
| Capability discovery / routing | MISSING | TaskRouter needed |
| Agent health (detailed metrics) | PARTIAL | AgentHealth exists but basic |
| Agent lifecycle states | MISSING | No lifecycle state machine |
| ResearchWorkspace | MISSING | No workspace abstraction |
| Agent-to-agent messaging | MISSING | No message model |
| Agent handoff | MISSING | No handoff model |
| Team model | MISSING | No team abstraction |
| Permission model | MISSING | No permission system |
| Audit log | MISSING | No audit event model |
| Artifact versioning | MISSING | No version tracking |
| Agent versioning | MISSING | No version snapshot |
| Runtime binding abstraction | MISSING | No runtime binding |
| Workspace lifecycle | MISSING | No workspace state machine |
| Brain bridge | MISSING | No workspace→Brain bridge |
| Deterministic routing | MISSING | No routing algorithm |
| Failure chaos testing | MISSING | No chaos test |
| Structured messaging | MISSING | No message model |

---

## 3. What's Duplicate

| Potential Duplicate | Status | Action |
|---|---|---|
| AgentProfile (research_agent_model) vs AgentRegistry entries | DIFFERENT PURPOSE | Keep both |
| AgentHealth (orchestrator_model) vs AgentStatus | DIFFERENT PURPOSE | Keep both |
| ResearchTask vs AgentRun | DIFFERENT PURPOSE | Keep both |
| ResearchArtifact vs AgentResult | DIFFERENT PURPOSE | Keep both |
| ResearchMemory vs FeatureSnapshot | DIFFERENT PURPOSE | Keep both |

---

## 4. What Should Be Extended (Not Replaced)

| Component | Extension |
|---|---|
| AgentProfile | Add identity metadata fields |
| AgentCapability | Add capability metadata |
| AgentRegistry | Add capability query methods |
| AgentHealth | Add health metrics |
| ResearchOrchestrator | Add routing + workspace integration |
| ResearchTask | Add workspace + delegation metadata |
| HumanReview | Add permission gates |
| ResearchArtifact | Add versioning + audit |

---

## 5. What Should NOT Be Touched

| Component | Reason |
|---|---|
| agent_runtime.py core | J0 fix is sufficient |
| agent_contract.py core | AgentResult contract stable |
| strategy_research_agents.py | Phase D agents working |
| opportunity_model.py | Phase E model stable |
| opportunity_engine.py | Phase E engine working |
| research_intelligence_model.py | Phase H model stable |
| research_intelligence_engine.py | Phase H engine working |
| persistence.py | Stable, no duplicate needed |
| brain_learning_pipeline.py | Reference only |

---

## 6. Implementation Plan

### New Files
1. `research_workspace.py` — ResearchWorkspace model
2. `task_router.py` — TaskRouter with capability discovery
3. `agent_message.py` — AgentMessage model
4. `research_audit.py` — ResearchAuditEvent model
5. `agent_lifecycle.py` — Agent lifecycle state machine

### Extended Files
1. `research_agent_model.py` — Extend AgentProfile + AgentCapability
2. `research_orchestrator_model.py` — Extend AgentHealth
3. `agent_registry.py` — Add capability query methods
4. `research_orchestrator.py` — Add routing + workspace integration
5. `research_hq_surface.py` — Add permission gates + artifact versioning

### Test Files
1. `test_j1_agentspace_core.py` — 100+ new tests

---

## 7. Mapping: AgentSpace → MarketHQ

| AgentSpace Concept | MarketHQ Implementation | Status |
|---|---|---|
| Agent Registry | agent_registry.py + strategy_research_registry.py | EXISTING |
| Agent Router | task_router.py | NEW |
| Workspace | research_workspace.py | NEW |
| Audit | research_audit.py | NEW |
| Agent Health | research_orchestrator_model.py | EXISTING (extended) |
| Human Approval | research_hq_surface.py | EXISTING (extended) |
| Agent Identity | research_agent_model.py | EXISTING (extended) |
| Capability | research_agent_model.py | EXISTING (extended) |
| Messaging | agent_message.py | NEW |
| Team Model | research_workspace.py (team field) | NEW |
| Task Delegation | research_orchestrator.py | EXISTING (extended) |
| Critic Loop | research_intelligence_engine.py | EXISTING |
| Runtime Binding | agent_runtime.py | EXISTING (extended) |
