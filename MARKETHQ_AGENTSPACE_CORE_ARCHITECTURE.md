# MarketHQ AgentSpace Core Architecture

**Date:** 2026-09-16
**Phase:** J1
**Status:** IMPLEMENTED

---

## Overview

AgentSpace-inspired core layer for MarketHQ research platform. Adds agent identity, capability model, workspace, routing, audit, messaging, lifecycle, and team abstractions on top of existing MarketHQ research core.

**Research-only.** No trading, broker, orders, or auto promotion.

---

## Architecture

```
                    MARKET HQ
                       │
              ┌────────▼────────┐
              │ Agent Control   │
              │ Plane           │
              └────────┬────────┘
                       │
       ┌───────────────┼────────────────┐
       │               │                │
 Agent Identity   Capability        Agent Health
 (AgentProfile)   (TaskRouter)      (AgentHealth)
       │               │                │
       └───────────────┼────────────────┘
                       │
                Agent Registry
                (AgentRegistry)
                       │
                 Task Router
                (TaskRouter)
                       │
              Research Orchestrator
                (ResearchOrchestrator)
                       │
       ┌───────────────┼─────────────────┐
       │               │                 │
   Research        Critic            Intelligence
   Agents          Agents              Agents
       │               │                 │
       └───────────────┼─────────────────┘
                       │
                Shared Workspace
              (ResearchWorkspace)
                       │
              Research Artifacts
              (ResearchArtifact)
                       │
                 Provenance
              (ProvenanceNode)
                       │
                Human Review
                (HumanReview)
                       │
                    HQ Surface
              (research_hq_surface.py)
```

---

## 1. Agent Identity

### AgentProfile (extended)

| Field | Type | Description |
|---|---|---|
| agent_id | str | Immutable identity |
| agent_name | str | Display name |
| version | str | Agent version |
| role | str | Role (research, critic, synthesis) |
| family | str | Strategy family |
| capabilities | list[CapabilityType] | What agent can do |
| capability_details | dict | Detailed capability specs |
| required_features | list[str] | Required features |
| optional_features | list[str] | Optional features |
| supported_assets | list[str] | Supported symbols |
| supported_timeframes | list[str] | Supported timeframes |
| supported_regimes | list[str] | Supported regimes |
| limitations | list[str] | Known limitations |
| runtime_binding | str | Runtime binding (hermes) |
| status | AgentStatus | Current status |
| reliability_ref | str | Reference to reliability data |
| last_run | str | Last execution timestamp |
| health_state | str | Health state string |
| failure_count | int | Failure count |
| timeout_count | int | Timeout count |

### Identity vs Runtime State

| Concept | Model | Purpose |
|---|---|---|
| Identity | AgentProfile | Who the agent is (immutable metadata) |
| Runtime State | AgentHealth | Current health (mutable) |
| Execution | AgentExecution | Single run state (AgentLifecycleManager) |

---

## 2. Capability Model

### AgentCapability

| Field | Type | Description |
|---|---|---|
| capability | CapabilityType | What the agent does |
| required_features | list[str] | Must-have features |
| optional_features | list[str] | Nice-to-have features |
| supported_assets | list[str] | Supported asset types |
| supported_timeframes | list[str] | Supported timeframes |
| supported_regimes | list[str] | Supported regimes |
| limitations | list[str] | Known limitations |
| data_dependencies | list[str] | Required data sources |

### Capability Descriptors (TaskRouter)

| Capability | Required Features | Supported Regimes |
|---|---|---|
| trend_analysis | EMA_FAST, EMA_SLOW, ADX, ATR | All |
| breakout_analysis | BB_UPPER, BB_LOWER, VOLUME_RATIO, ATR | All |
| reversal_analysis | RSI, MACD, SMA_FAST, SMA_SLOW | All |
| momentum_analysis | RSI, MACD, VOLUME_RATIO | All |
| volatility_analysis | ATR, ATR_PCT, VOLUME_RATIO | All |
| liquidity_analysis | donchian_high, donchian_low | All |
| structure_analysis | structure, donchian_high, donchian_low | All |

### Capability Discovery

When a task requires a capability:
1. TaskRouter checks registered capabilities
2. Finds agents with matching capability
3. Scores candidates by feature availability, symbol/timeframe/regime support
4. Returns best match (deterministic, alphabetical tie-breaking)
5. If no match → CAPABILITY_MISMATCH or NO_CANDIDATE

---

## 3. Agent Registry

### Extended Registry Methods

| Method | Description |
|---|---|
| find_by_capability(cap) | Find agents supporting a capability |
| find_by_strategy_family(family) | Find agents by strategy family |
| find_by_symbol(symbol) | Find agents supporting a symbol |
| find_by_timeframe(timeframe) | Find agents supporting a timeframe |
| get_health(agent_id) | Get health info for an agent |

### Registry/Runtime Contract (J0 preserved)

- Registry stores agent definitions (classes or instances)
- Runtime instantiates per execution
- J0 fix: runtime detects class → instantiates with context
- Contract protected by tests

---

## 4. Agent Health

### Health States

| State | Meaning |
|---|---|
| READY | Healthy, ready for tasks |
| RUNNING | Currently executing |
| DEGRADED | Partially available |
| FAILED | Failed, needs attention |
| UNAVAILABLE | Dependency unavailable |
| DISABLED | Explicitly disabled |

### Health Metrics

| Metric | Description |
|---|---|
| success_count | Successful executions |
| failure_count | Failed executions |
| last_success | Timestamp of last success |
| last_failure | Timestamp of last failure |
| last_error | Last error message |
| consecutive_failures | Consecutive failures |
| average_latency | Average execution time |
| current_state | Current health state |
| last_task_id | Last executed task ID |

### Reliability ≠ Health

- Reliability: Historical accuracy (Phase H)
- Health: Runtime status (current)
- Kept separate, not conflated

---

## 5. Task Router

### Routing Algorithm

1. Capability match → filter candidates
2. Required feature availability → score candidates
3. Symbol support → score candidates
4. Timeframe support → score candidates
5. Regime support → score candidates
6. Agent health → score candidates
7. Version compatibility → validate
8. Tie-breaking → alphabetical by agent_id (deterministic)

### Routing Result

| Status | Meaning |
|---|---|
| ROUTED | Successfully routed to agent |
| CAPABILITY_MISMATCH | Capability not registered |
| NO_CANDIDATE | No agent for capability |
| DEGRADED | Version mismatch |

---

## 6. Research Workspace

### Workspace Model

| Field | Type | Description |
|---|---|---|
| workspace_id | str | Unique workspace ID |
| research_id | str | Research run ID |
| symbol | str | Trading symbol |
| timeframe | str | Timeframe |
| cutoff | str | Historical cutoff |
| created_at | str | Creation timestamp |
| participants | list[WorkspaceParticipant] | Agent participants |
| tasks | list[str] | Task IDs |
| artifacts | list[str] | Artifact IDs |
| observations | list[str] | Observation IDs |
| claims | list[str] | Claim IDs |
| opportunities | list[str] | Opportunity IDs |
| setups | list[str] | Setup IDs |
| status | WorkspaceStatus | Current status |
| failure_reason | str | Failure reason if any |

### Workspace Lifecycle

```
CREATED → INITIALIZING → ACTIVE → REVIEW → COMPLETED
                                   → FAILED
```

### Shared Context

All agents in a workspace share:
- Symbol / Timeframe / Cutoff
- Feature snapshot
- Dataset reference
- Workspace ID

No agent-private mutable state. All state flows through workspace.

---

## 7. Structured Messaging

### AgentMessage

| Field | Type | Description |
|---|---|---|
| message_id | str | Unique message ID |
| sender_agent_id | str | Sender agent |
| recipient_agent_id | str | Recipient agent |
| workspace_id | str | Workspace context |
| task_id | str | Task context |
| message_type | MessageType | REQUEST/RESPONSE/EVIDENCE/CHALLENGE/HANDOFF/STATUS/DELEGATION |
| payload | dict | Structured payload |
| evidence_refs | list[str] | Evidence references |
| provenance_ref | str | Provenance reference |
| created_at | str | Timestamp |
| responded_to | str | Parent message ID |

### Message Types

- REQUEST — Agent asks another for analysis
- RESPONSE — Agent responds to a request
- EVIDENCE — Agent shares research evidence
- CHALLENGE — Agent challenges another's finding
- HANDOFF — Agent passes context to another
- STATUS — Agent status update
- DELEGATION — Orchestrator delegates task to agent

### Handoff Model

| Field | Type | Description |
|---|---|---|
| handoff_id | str | Unique handoff ID |
| source_agent_id | str | Source agent |
| destination_agent_id | str | Destination agent |
| workspace_id | str | Workspace |
| task_id | str | Task |
| reason | str | Why handoff |
| evidence_refs | list[str] | Evidence refs |
| artifact_refs | list[str] | Artifact refs |
| observation_refs | list[str] | Observation refs |
| context_snapshot | dict | Context at handoff time |

---

## 8. Agent Lifecycle

### States

```
REGISTERED → READY → RUNNING → COMPLETED
                         → FAILED
                         → DEGRADED
```

### Transitions

| From | To | Valid |
|---|---|---|
| REGISTERED | READY | ✓ |
| READY | RUNNING | ✓ |
| READY | DISABLED | ✓ |
| RUNNING | COMPLETED | ✓ |
| RUNNING | FAILED | ✓ |
| RUNNING | DEGRADED | ✓ |
| DEGRADED | READY | ✓ |
| DEGRADED | FAILED | ✓ |
| FAILED | RECOVERING | ✓ |
| FAILED | DISABLED | ✓ |
| RECOVERING | READY | ✓ |
| RECOVERING | FAILED | ✓ |

---

## 9. Audit Log

### Audit Events

| Event Type | Description |
|---|---|
| WORKSPACE_CREATED | Workspace created |
| WORKSPACE_STATUS_CHANGED | Workspace status changed |
| TASK_CREATED | Task created |
| TASK_STARTED | Task started |
| TASK_COMPLETED | Task completed |
| TASK_FAILED | Task failed |
| TASK_BLOCKED | Task blocked by dependency |
| AGENT_REGISTERED | Agent registered |
| AGENT_HEALTH_CHANGED | Agent health changed |
| AGENT_CAPABILITY_CHANGED | Agent capability changed |
| AGENT_LIFECYCLE_CHANGED | Agent lifecycle state changed |
| MESSAGE_SENT | Message sent between agents |
| HANDOFF_CREATED | Handoff created |
| ARTIFACT_CREATED | Artifact created |
| ARTIFACT_VERSION_CHANGED | Artifact version changed |
| CLAIM_SUBMITTED | Claim submitted |
| CLAIM_STATUS_CHANGED | Claim status changed |
| OBSERVATION_CREATED | Observation created |
| OPPORTUNITY_DETECTED | Opportunity detected |
| SETUP_GENERATED | Setup generated |
| BRAIN_OBSERVATION_SENT | Observation sent to Brain |
| HUMAN_REVIEW_SUBMITTED | Human review submitted |
| HUMAN_REVIEW_DECISION | Human review decision |
| PERMISSION_CHECK | Permission check |
| SECURITY_VIOLATION | Security boundary violation |
| ROUTING_DECISION | Routing decision |
| DETERMINISM_CHECK | Determinism verification |
| FUTURE_INVARIANCE_CHECK | Future invariance check |

### Audit Properties

- Append-only: old entries never modified
- Each event has: event_id, workspace_id, task_id, agent_id, event_type, timestamp, provenance_ref, metadata

---

## 10. Agent Versioning

- Each agent has a version string (e.g., "1.0.0")
- Version snapshot stored per execution
- Replay uses same version
- Version mismatch → explicit error

---

## 11. Runtime Binding Abstraction

### Current

- DETERMINISTIC_LOCAL runtime only
- Hermes agent via Nous Portal OAuth

### Future (J3)

- AgentRouter / provider runtime
- Claude, Codex, Gemini, OpenAI, Hermes providers
- Cost/resource metadata

---

## 12. Permission Model

### Permission Levels

| Permission | Description |
|---|---|
| READ_MARKET_DATA | Read market data |
| READ_FEATURES | Read computed features |
| WRITE_OBSERVATION | Write observations |
| WRITE_ARTIFACT | Write artifacts |
| REQUEST_RESEARCH | Request research |
| REQUEST_REVIEW | Request human review |

### Explicitly Excluded

- PLACE_ORDER
- EXECUTE_TRADE
- ACCESS_BROKER

Research-only boundary enforced at code level.

---

## 13. Team Model

### ResearchTeam

| Field | Type | Description |
|---|---|---|
| team_id | str | Unique team ID |
| name | str | Team name |
| purpose | str | Team purpose |
| members | list[str] | Agent IDs |
| capabilities | list[str] | Team capabilities |
| workflow | list[str] | Workflow steps |
| workspace_id | str | Bound workspace |

### Example

"Trend & Momentum Research Team":
- Members: trend_agent, momentum_agent, volatility_agent, critic_agent
- Purpose: Trend & momentum research collaboration

---

## 14. Brain Integration

- Workspace → Brain observation bridge
- Observations sent as OBSERVATION type (not "truth")
- Claim lifecycle preserved: UNTESTED → TESTED → SUPPORTED/UNSTABLE/REJECTED
- Weight proposal: PROPOSED only, no auto promotion

---

## 15. Artifact Model

### Artifact Types

- AgentResult — Agent execution output
- Observation — Research observation
- Evidence — Structured evidence
- Claim — Research claim
- Opportunity — Detected opportunity
- Setup — Research-backed setup
- CriticResult — Critic analysis
- ResearchReport — Final report

### Artifact Provenance

Every artifact linked to:
- Source agent
- Source task
- Workspace
- Version
- Provenance chain

---

## 16. Persistence

### New Tables (when needed)

- research_workspaces — Workspace state
- agent_messages — Agent messages
- agent_audit_events — Audit events

### Migration Rules

- Idempotent
- Non-destructive
- Backward compatible
- Foreign keys verified
- Orphan records tested

---

## 17. Failure Isolation

- Agent FAILED → only dependents blocked
- Independent agents continue
- Workspace: PARTIAL/DEGRADED, not SYSTEM FAILED
- J0 rule preserved: health monitoring only, not blocking

---

## 18. Security Boundary

### Enforced

- No broker connection
- No order placement
- No real-money execution
- No autonomous trading
- No wallet/exchange credentials
- No financial transaction

### Verification

All new code reviewed for:
- No hidden trading logic
- No order placement
- No broker calls
- Research-only payload

---

## 19. Determinism

- Same inputs → same routing
- Same feature snapshot → same agent results
- Version pinning per execution
- Replay with same version

---

## 20. Future Invariance

- Past cutoff unaffected by future data
- Feature snapshot computed at cutoff
- Routing deterministic across time

---

## Files Created

| File | Purpose |
|---|---|
| research_workspace.py | ResearchWorkspace model |
| task_router.py | TaskRouter with capability discovery |
| agent_message.py | AgentMessage + AgentHandoff |
| research_audit.py | ResearchAuditEvent + AuditLog |
| agent_lifecycle.py | AgentLifecycleManager + AgentExecution |
| test_j1_agentspace_core.py | 63 J1 unit tests |
| test_j1_e2e.py | Real E2E test |

## Files Extended

| File | Extension |
|---|---|
| agent_registry.py | + capability query methods |
| research_orchestrator.py | + workspace/routing/messaging/audit |
| research_agent_model.py | Already has AgentProfile/CapabilityType |
| research_orchestrator_model.py | Already has AgentHealth/ResearchTask |
