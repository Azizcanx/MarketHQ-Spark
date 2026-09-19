# MARKETHQ AGENTSPACE INTEGRATION AUDIT

**Date:** 2026-09-16
**Purpose:** Identify AgentSpace concepts that improve MarketHQ without duplication

---

## Audit Method

Studied AgentSpace/HKUDS concepts as architectural reference.
Mapped each to existing MarketHQ implementation.
Identified gaps and proposed extensions.

---

## 1. AgentRouter

**AgentSpace Concept:** Routes tasks to appropriate agent/runtime based on capability, availability, cost.

**MarketHQ Equivalent:** Strategy research agents dispatch via strategy_research_registry.py.

**Existing Implementation:**
- `strategy_research_registry.py` — agent registration
- `strategy_registry_v1.py` — strategy registry
- `agent_registry.py` — agent registry

**Gap:** No runtime selection/routing layer. All agents run via same mechanism.

**Proposed Extension:** Thin router in `research_orchestrator.py` that selects runtime based on capability + availability + cost.

**Files that should change:**
- New: `research_orchestrator.py`
- Extend: `strategy_research_registry.py` (add capability metadata)

**Files that should NOT change:**
- `agent_runtime.py`
- `agent_registry.py`
- `persistence.py`

**Priority:** Medium
**Risk:** Low — thin wrapper, no core logic change
**Justified:** Yes — enables runtime diversity without duplication

---

## 2. Unified Runtime Abstraction

**AgentSpace Concept:** Single abstraction over different execution backends.

**MarketHQ Equivalent:** `agent_runtime.py` — existing runtime abstraction.

**Existing Implementation:** `agent_runtime.py` already provides unified execution.

**Gap:** None — runtime abstraction exists.

**Proposed Extension:** Add runtime health/diagnostics to existing runtime.

**Files that should change:**
- Extend: `agent_runtime.py` (health diagnostics)

**Files that should NOT change:** None

**Priority:** Low
**Risk:** Low
**Justified:** Yes — extend, don't replace

---

## 3. Agent Registry / Digital Employee Model

**AgentSpace Concept:** Agents as digital employees with identity, capabilities, status.

**MarketHQ Equivalent:** `agent_registry.py` + `agent_contract.py` — existing agent registration.

**Existing Implementation:**
- `agent_contract.py` — agent interface
- `agent_registry.py` — agent registry
- `strategy_research_agents.py` — strategy agent adapters

**Gap:** No explicit capability model per agent. No health/status tracking per agent instance.

**Proposed Extension:** Add capability profile + health status to agent registry entries.

**Files that should change:**
- Extend: `agent_registry.py` (add capability + health fields)
- New: `research_intelligence_model.py` (already has ReliabilityProfile)

**Files that should NOT change:**
- `agent_contract.py`
- `strategy_research_agents.py`

**Priority:** High
**Risk:** Low — additive fields only
**Justified:** Yes — needed for orchestration + routing

---

## 4. Agent Identity

**AgentSpace Concept:** Each agent has unique identity, version, capabilities.

**MarketHQ Equivalent:** Agent name + version in registry.

**Existing Implementation:** Agent registry has name/version.

**Gap:** No unique agent_id for research context tracking.

**Proposed Extension:** Add agent_id to agent results for provenance.

**Files that should change:**
- Extend: AgentResult model (if needed)
- New: Agent identity in research orchestrator

**Files that should NOT change:** Core agent execution

**Priority:** Medium
**Risk:** Low
**Justified:** Yes — needed for provenance + audit trail

---

## 5. Agent Capabilities

**AgentSpace Concept:** Explicit capability declaration per agent.

**MarketHQ Equivalent:** Strategy family + agent type in registry.

**Existing Implementation:** `strategy_research_agents.py` — agents have strategy families.

**Gap:** No explicit capability list per agent (what data it needs, what it produces).

**Proposed Extension:** Add capability metadata to agent registry entries.

**Files that should change:**
- Extend: Agent registry entries with capability metadata

**Files that should NOT change:** Agent execution logic

**Priority:** High
**Risk:** Low — additive metadata
**Justified:** Yes — enables routing + gating

---

## 6. Task Orchestration

**AgentSpace Concept:** Central orchestration of agent tasks with dependencies.

**MarketHQ Equivalent:** No orchestration layer exists.

**Existing Implementation:** None — agents run independently.

**Gap:** No DAG-like task orchestration. No dependency tracking. No failure isolation.

**Proposed Extension:** `research_orchestrator.py` with task definitions + dependency resolution.

**Files that should change:**
- New: `research_orchestrator.py`

**Files that should NOT change:** Existing agent execution

**Priority:** High
**Risk:** Medium — new abstraction, must not duplicate AgentRuntime
**Justified:** Yes — needed for HQ orchestration

---

## 7. Scheduling

**AgentSpace Concept:** Task scheduling with periodic cycles.

**MarketHQ Equivalent:** Brain cycles (if any) + manual execution.

**Existing Implementation:** `brain_learning_pipeline.py` has some scheduling concepts.

**Gap:** No explicit periodic research cycle scheduler.

**Proposed Extension:** Research cycle scheduler integrated with existing brain cycles.

**Files that should change:**
- Extend: Brain cycle (if exists) or new scheduler module

**Files that should NOT change:** Agent execution

**Priority:** Medium
**Risk:** Low
**Justified:** Yes — enables autonomous research cycles

---

## 8. Runtime Diagnostics

**AgentSpace Concept:** Per-agent health + runtime diagnostics.

**MarketHQ Equivalent:** None explicit.

**Existing Implementation:** No health model for agents.

**Gap:** No agent health tracking, no failure diagnostics, no timeout tracking.

**Proposed Extension:** Agent health model + runtime diagnostics.

**Files that should change:**
- New: Agent health model (extend research_intelligence_model.py)
- New: Health diagnostics in orchestrator

**Files that should NOT change:** Agent execution logic

**Priority:** High
**Risk:** Low — additive, doesn't change execution
**Justified:** Yes — needed for reliability + failure isolation

---

## 9. Shared Workspace Context

**AgentSpace Concept:** Shared context for agents to access.

**MarketHQ Equivalent:** `observation_bridge.py` + Brain + persistence.

**Existing Implementation:** Brain + observation bridge.

**Gap:** No explicit shared workspace context abstraction. Brain and workspace are conflated.

**Proposed Extension:** Separate workspace context (references Brain) from Brain itself.

**Files that should change:**
- New: `research_workspace.py`
- Do NOT change: Brain / observation_bridge.py

**Files that should NOT change:** Brain internals

**Priority:** Medium
**Risk:** Low — additive abstraction
**Justified:** Yes — separates context view from learning system

---

## 10. Human Approval Gates

**AgentSpace Concept:** Human approval checkpoints in agent workflows.

**MarketHQ Equivalent:** No human review layer exists.

**Existing Implementation:** None.

**Gap:** No human research review abstraction.

**Proposed Extension:** Human research review model + status tracking.

**Files that should change:**
- New: Human review model + API

**Files that should NOT change:** Agent execution

**Priority:** High
**Risk:** Low — additive
**Justified:** Yes — Phase I goal #1

---

## 11. Audit Trail

**AgentSpace Concept:** Complete audit trail for every agent action.

**MarketHQ Equivalent:** `persistence.py` + DB tables.

**Existing Implementation:** Some audit trail in DB (agent_runs, agent_results, evidence_items).

**Gap:** No unified provenance chain from setup → opportunity → agent → evidence → validation → claim → review.

**Proposed Extension:** Unified provenance chain.

**Files that should change:**
- Extend: `persistence.py` (add provenance tables)
- New: Provenance builder in orchestrator

**Files that should NOT change:** Existing audit tables (additive only)

**Priority:** High
**Risk:** Medium — DB schema extension needed
**Justified:** Yes — critical for research integrity

---

## 12. Output/Artifact Lifecycle

**AgentSpace Concept:** Artifact lifecycle management (create → review → archive).

**MarketHQ Equivalent:** None explicit.

**Existing Implementation:** Reports as markdown files, DB persistence.

**Gap:** No explicit artifact lifecycle management. No versioning of research artifacts.

**Proposed Extension:** Artifact model with lifecycle status.

**Files that should change:**
- New: Artifact model in research_intelligence_model.py

**Files that should NOT change:** Existing report generation

**Priority:** Low
**Risk:** Low
**Justified:** Yes — but lower priority than orchestration + review

---

## 13. Remote Daemon / Worker Architecture

**AgentSpace Concept:** Remote execution workers.

**MarketHQ Equivalent:** None — single-machine research system.

**Existing Implementation:** Single-machine execution via AgentRuntime.

**Gap:** None — MarketHQ is single-machine, no distributed execution needed.

**Proposed Extension:** None.

**Files that should change:** None

**Files that should NOT change:** None

**Priority:** None
**Risk:** N/A
**Justified:** No — MarketHQ is not a distributed system

---

## 14. Permission Boundaries

**AgentSpace Concept:** Fine-grained permissions per agent/task.

**MarketHQ Equivalent:** None explicit.

**Existing Implementation:** No permission model.

**Gap:** No permission boundaries between research and execution.

**Proposed Extension:** Research permission model (Step 14 in Phase I plan).

**Files that should change:**
- New: Permission model

**Files that should NOT change:** Agent execution (permissions checked at orchestration level)

**Priority:** High
**Risk:** Low — additive, no execution change
**Justified:** Yes — safety boundary for research system

---

## 15. Sandbox Boundaries

**AgentSpace Concept:** Execution sandboxing per agent.

**MarketHQ Equivalent:** None — agents run in same process.

**Existing Implementation:** No sandboxing.

**Gap:** None — MarketHQ is a research system, not a multi-tenant execution platform.

**Proposed Extension:** None.

**Files that should change:** None

**Files that should NOT change:** None

**Priority:** None
**Risk:** N/A
**Justified:** No — not applicable to MarketHQ's scale/architecture

---

## Summary: AgentSpace Ideas Adopted vs Rejected

### Adopted (extend MarketHQ, don't replace)
1. AgentRouter → Thin runtime router in orchestrator
2. Agent capabilities → Add capability metadata to registry
3. Task orchestration → Research orchestrator with DAG dependencies
4. Runtime diagnostics → Agent health model
5. Shared workspace context → Research workspace (references Brain)
6. Human approval gates → Human research review layer
7. Audit trail → Unified provenance chain
8. Permission boundaries → Research permission model
9. Output/artifact lifecycle → Artifact model with status

### Rejected (not applicable)
1. Remote daemon/worker — MarketHQ is single-machine
2. Sandbox boundaries — Not applicable to research system
3. Digital employee model — Over-engineering for research agents
4. Wholesale AgentSpace adoption — Would duplicate MarketHQ engines

### Extended (existing MarketHQ)
1. AgentRuntime — existing, extend with health
2. AgentRegistry — existing, extend with capabilities
3. Brain — existing, workspace references it, doesn't duplicate it
4. Persistence — existing, additive tables only
5. Observation bridge — existing, keep as-is