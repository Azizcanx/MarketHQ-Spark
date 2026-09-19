# AgentSpace → MarketHQ Mapping

**Date:** 2026-09-16
**Phase:** J3

---

| AgentSpace Concept | MarketHQ Implementation | Status |
|---|---|---|
| Agent Registry | agent_registry.py | EXISTING (extended with capability query methods) |
| Agent Router | TaskRouter (task_router.py) + AgentRouter (agent_router.py) | NEW (J3) |
| Workspace | ResearchWorkspace (research_workspace.py) | NEW (J1) |
| Audit | ResearchAuditEvent + AuditLog (research_audit.py) | NEW (J1+J3) |
| Agent Health | AgentHealth (research_orchestrator_model.py) | EXISTING (extended with metrics) |
| Human Approval | HumanReview (research_hq_surface.py) | EXISTING (unchanged) |
| Agent Identity | AgentProfile (research_agent_model.py) | EXISTING (extended with metadata) |
| Capability | AgentCapability + ProviderCapability | EXISTING (extended) + NEW (J3) |
| Messaging | AgentMessage + AgentHandoff (agent_message.py) | NEW (J1+J2) |
| Team Model | ResearchTeam (research_team.py) | NEW (J2) |
| Task Delegation | DelegatedResearchTask (task_delegation.py) | NEW (J2) |
| Critic Loop | CriticLoop (critic_loop.py) | NEW (J2) |
| Evidence Exchange | EvidenceExchange (evidence_exchange.py) | NEW (J2) |
| Team Synthesis | TeamSynthesis (team_synthesis.py) | NEW (J2) |
| Runtime Binding | AgentRuntime (agent_runtime.py) V1 → V2 | EXISTING (extended with V2 lifecycle) |
| Provider Abstraction | ProviderRuntime + DeterministicRuntime + MockProviderRuntime | NEW (J3) |
| Artifact Versioning | ResearchArtifact + context_version | EXISTING (extended) |
| Permission Model | HumanReview + ResearchAuditEvent | EXISTING (extended) |
| Dependency Graph | ResearchOrchestrator (existing DAG) | EXISTING (unchanged) |
| Feature Snapshot | FeatureSnapshot (existing) | EXISTING (unchanged) |
| Brain Bridge | Brain + Workspace observation bridge | EXISTING (extended) |
| Deterministic Replay | FeatureSnapshot + agent versioning + idempotency | EXISTING (verified) + NEW (J3) |
| Future Invariance | Data cutoff isolation + execution metadata | EXISTING (verified) + NEW (J3) |
| Research Artifacts | ResearchArtifact + AgentResult | EXISTING (unchanged) |
| Provenance | ProvenanceNode + execution provenance chain | EXISTING (unchanged) + NEW (J3) |
| Human Review | HumanReview | EXISTING (unchanged) |
| Opportunity Engine | OpportunityEngine | EXISTING (unchanged) |
| Setup Synthesis | ResearchBackedSetup | EXISTING (unchanged) |
| Historical Evidence | Historical evidence replay | EXISTING (unchanged) |
| Registry/Runtime Contract | AgentRegistry + AgentRuntime | EXISTING (J0 fix preserved) |
| Duplicate Task Protection | seen_task_ids | EXISTING (J0 fix preserved) |
| Partial Failure Isolation | can_execute dependency-only | EXISTING (J0 fix preserved) |
| Execution Lifecycle | AgentRunStatus V1 → V2 (CREATED→QUEUED→RUNNING→COMPLETED+FAILED+TIMEOUT+CANCELLED+REJECTED) | NEW (J3) |
| Execution Metadata | ExecutionMetadata (tokens, cost, duration, versioning) | NEW (J3) |
| Health System | ProviderStatus + ProviderRuntime.health() | NEW (J3) |
| Fallback Chain | AgentRouter fallback chain | NEW (J3) |
| Retry/Timeout/Cancellation | Runtime-level timeout, retry, cancellation | NEW (J3) |
| Output Validation | AgentResult schema validation | NEW (J3) |
| Research-Only Enforcement | cost_policy=research_only on all providers | NEW (J3) |