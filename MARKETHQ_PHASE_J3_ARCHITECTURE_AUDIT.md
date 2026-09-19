# MARKETHQ PHASE J3 — ARCHITECTURE AUDIT

**Date:** 2026-09-16
**Purpose:** Audit current MarketHQ architecture against J3 Agent Runtime + AgentRouter + Provider Abstraction requirements

---

## Current Runtime Architecture

### agent_runtime.py — AgentRuntime V2

- AgentRunStatus: CREATED, RUNNING, COMPLETED, FAILED, INSUFFICIENT_DATA
- AgentRun: execution_id, agent_id, agent_version, symbol, timeframe, started_at, completed_at, status, error, result, trace
- AgentConfig: agent_id, version, enabled, parameters
- ExecutionRequest: symbol, timeframe, observation_timestamp, data_cutoff_timestamp, parameters
- Missing: TIMEOUT, CANCELLED, REJECTED statuses
- Missing: runtime_id, provider_id, model_id, retry_count, correlation_id
- Missing: timeout, cancellation, idempotency

### agent_registry.py — AgentRegistry

- Stores adapter instances (not classes — J0 fix)
- Methods: register, get, get_version, list_agents, unregister, has, count, clear
- J1 extensions: find_by_capability, find_by_strategy_family, find_by_symbol, find_by_timeframe, get_health
- Missing: provider-aware registration, runtime binding

### agent_contract.py — Agent Contract

- AgentResult: universal agent output contract
- Evidence, Claim, MarketContext, FeatureSnapshot
- BaseAgentAdapter: base class for all adapters
- AgentStatus: SUCCESS, PARTIAL, INSUFFICIENT_DATA, ERROR
- Has: source_engine, source_engine_version, data_quality, feature_availability
- Missing: runtime metadata, provider metadata, cost/token metadata

### engine_adapters.py — Engine Adapters

- TechnicalIndicatorsEngine: computes indicators
- MarketContextEnriched: enriches context
- Has provider/engine abstraction
- Missing: provider capability model, health

### strategy_research_agents.py — Strategy Research Agents

- 7 agents: Trend, Breakout, Reversal, Momentum, Volatility, Liquidity, Structure
- Each extends BaseAgentAdapter
- Missing: runtime binding, provider assignment

### strategy_research_registry.py — Strategy Registry

- Minimal registry for strategy agents
- Missing: capability query, health tracking

---

## Current Orchestration Architecture

### research_orchestrator.py — ResearchOrchestrator

- DAG-based task execution with dependency resolution
- J1 extensions: workspace, routing, messaging, audit
- Missing: provider-aware execution, runtime selection

### research_orchestrator_model.py — Orchestrator Models

- ResearchTask, AgentHealth, TaskStatus
- HealthStatus: READY, RUNNING, DEGRADED, FAILED, UNAVAILABLE, DISABLED
- Missing: runtime health, provider health

### collaboration_orchestrator.py — CollaborationOrchestrator

- Team formation, delegation, evidence exchange, synthesis, critic loop
- Missing: runtime binding for collaboration tasks

### task_router.py — TaskRouter

- Capability-based deterministic routing
- CapabilityDescriptor with scoring
- Missing: runtime capability matching, provider capability

### research_workspace.py — ResearchWorkspace

- Shared research context
- J2 extensions: context_version, message budget
- Missing: runtime context, execution context

---

## Current Audit & Lifecycle

### research_audit.py — Audit Log

- AuditEventType: 30+ event types
- ResearchAuditEvent: immutable audit events
- AuditLog: append-only
- Missing: runtime-specific events (RUNTIME_SELECTED, RUNTIME_STARTED, etc.)

### agent_lifecycle.py — AgentLifecycleManager

- AgentLifecycleState: REGISTERED, READY, RUNNING, COMPLETED, FAILED, DEGRADED, RECOVERING, DISABLED
- AgentExecution: single execution state
- Missing: runtime lifecycle, provider lifecycle

---

## Current Persistence

### persistence.py — PersistenceLayer

- SQLite-based persistence
- Idempotent migrations
- Missing: execution history, runtime provider tables, provider health tables

---

## Current Intelligence

### research_intelligence_model.py — Research Intelligence Model

- Observation, Hypothesis, Experiment, Claim, CalibrationProfile, ReliabilityProfile, ResearchMemory
- Claim lifecycle: UNTESTED → TESTED → SUPPORTED/UNSTABLE/REJECTED
- Missing: runtime metadata on claims, provider version on claims

### research_intelligence_engine.py — Research Intelligence Engine

- Claim validation, weight proposals
- Missing: runtime-aware validation

---

## Current Opportunity / Setup

### opportunity_model.py — Opportunity Model

- Opportunity, ResearchBackedSetup
- Missing: runtime metadata on opportunities

### opportunity_engine.py — Opportunity Engine

- Detects opportunities from agent results
- Missing: runtime-aware opportunity detection

---

## Current Brain Integration

### brain_learning_pipeline.py — Brain Learning Pipeline

- Adaptive learning pipeline
- Missing: runtime-aware observation ingestion

---

## Current Brain-Research Bridge

### observation_bridge.py — Observation Bridge

- Bridges observations to Brain
- Missing: runtime metadata on observations

---

## Current HQ Surface

### research_hq_surface.py — Research HQ Surface

- HumanReview, ResearchArtifact, ProvenanceNode
- Missing: runtime metadata on artifacts, provenance extension

---

## J3 Gaps Analysis

| J3 Requirement | Status | Needed |
|---|---|---|
| Runtime execution lifecycle (V2) | PARTIAL | Extend AgentRunStatus + AgentRun |
| AgentRouter | MISSING | New file |
| Provider abstraction | MISSING | New file |
| Local/deterministic runtime | PARTIAL | Extend AgentRuntime |
| External provider runtime | MISSING | New file + mock |
| Provider capability model | MISSING | New file |
| Health + availability | MISSING | New file |
| Retry/timeout/cancellation | MISSING | Extend AgentRuntime |
| Idempotency | MISSING | New mechanism |
| Failure isolation | PARTIAL | Extend |
| Output validation | MISSING | New mechanism |
| Structured output | MISSING | New mechanism |
| Cost/token observability | MISSING | New fields |
| Model/provider versioning | MISSING | New fields |
| Provenance extension | MISSING | Extend |
| Workspace integration | MISSING | Extend |
| Collaboration integration | MISSING | Extend |
| Research-only security | MISSING | Enforce |
| Brain integration | MISSING | Extend |
| Persistence extension | MISSING | Extend |
| Audit extension | MISSING | Extend |
| Mock provider | MISSING | New file |
| Determinism | MISSING | New tests |
| Future invariance | MISSING | New tests |
| Performance | MISSING | New tests |
| Observability | MISSING | New fields |

---

## What Will NOT Be Touched

| Component | Reason |
|---|---|
| agent_contract.py core | AgentResult contract stable |
| strategy_research_agents.py | Phase D agents working |
| opportunity_model.py | Phase E model stable |
| opportunity_engine.py | Phase E engine working |
| research_intelligence_model.py | Phase H model stable |
| research_intelligence_engine.py | Phase H engine working |
| brain_learning_pipeline.py | Reference only |
| persistence.py core | Stable, additive changes only |
| research_hq_surface.py | Core surface stable |
| research_orchestrator.py core | Workflow stable, add runtime binding |
| task_router.py core | Routing stable, add capability matching |
| research_workspace.py core | Workspace stable, add runtime context |
| research_audit.py core | Audit stable, add runtime events |
| agent_lifecycle.py core | Lifecycle stable, add runtime states |
| research_team.py core | Team stable |
| task_delegation.py core | Delegation stable |
| evidence_exchange.py core | Evidence stable |
| team_synthesis.py core | Synthesis stable |
| critic_loop.py core | Critic stable |
| collaboration_orchestrator.py core | Collaboration stable |
| parallel_executor.py core | Parallel stable |

---

## What Will Be Extended

| Component | Extension |
|---|---|
| agent_runtime.py | + Runtime V2 lifecycle, timeout, cancellation, idempotency |
| agent_registry.py | + provider-aware registration |
| research_orchestrator.py | + runtime binding |
| research_workspace.py | + runtime context |
| research_audit.py | + runtime events |
| agent_lifecycle.py | + runtime lifecycle |
| persistence.py | + execution/provider tables |
| agent_message.py | + runtime metadata |
| research_team.py | + runtime binding |

---

## What Will Be Created

| File | Purpose |
|---|---|
| agent_router.py | AgentRouter — execution → runtime/provider |
| provider_adapter.py | ProviderRuntime abstraction |
| deterministic_runtime.py | Local deterministic runtime |
| external_runtime.py | External provider runtime + mock |
| runtime_health.py | Runtime/provider health |
| execution_validator.py | Output validation |
| runtime_persistence.py | Runtime-specific persistence |
| test_j3_runtime.py | 80+ new tests |