# MarketHQ Research Team Model — AgentSpace Mapping

**Date:** 2026-09-16
**Phase:** J2

---

| AgentSpace Concept | MarketHQ Implementation | Status |
|---|---|---|
| Agent Teams | ResearchTeam (research_team.py) | NEW |
| Team Templates | TEAM_TEMPLATES (research_team.py) | NEW |
| Agent Messaging | AgentMessage (agent_message.py) | EXTENDED (+ CLARIFICATION, REVISION_REQUEST) |
| Task Delegation | DelegatedResearchTask + DelegationRules (task_delegation.py) | NEW |
| Shared Workspace | ResearchWorkspace (research_workspace.py) | EXISTING (extended) |
| Agent Health | AgentHealth (research_orchestrator_model.py) | EXISTING |
| Agent Router | TaskRouter (task_router.py) | EXISTING |
| Audit | AuditLog + ResearchAuditEvent (research_audit.py) | EXISTING (extended) |
| Human Approval | HumanReview (research_hq_surface.py) | EXISTING |
| Agent Identity | AgentProfile (research_agent_model.py) | EXISTING |
| Capability | AgentCapability (research_agent_model.py) | EXISTING |
| Critic Loop | CriticLoop (critic_loop.py) | NEW |
| Evidence Exchange | EvidenceExchange + AgentEvidence (evidence_exchange.py) | NEW |
| Team Synthesis | TeamResearchResult (team_synthesis.py) | NEW |
| Parallel Execution | ParallelExecutor (parallel_executor.py) | NEW |
| Collaboration Orchestrator | CollaborationOrchestrator (collaboration_orchestrator.py) | NEW |
| Dependency Graph | ResearchOrchestrator (research_orchestrator.py) | EXISTING |
| Feature Snapshot | FeatureSnapshot (existing) | EXISTING |
| Brain Bridge | Brain + Workspace observation | EXISTING |
| Deterministic Replay | FeatureSnapshot + agent versioning | EXISTING |
| Future Invariance | Data cutoff isolation | EXISTING |
| Research Artifacts | ResearchArtifact + AgentResult | EXISTING |
| Provenance | ProvenanceNode | EXISTING |
| Opportunity Engine | OpportunityEngine | EXISTING |
| Setup Synthesis | ResearchBackedSetup | EXISTING |
| Historical Evidence | Historical evidence replay | EXISTING |
| Registry/Runtime Contract | AgentRegistry + AgentRuntime | EXISTING (J0 fix) |
| Duplicate Task Protection | seen_task_ids | EXISTING (J0 fix) |
| Partial Failure Isolation | can_execute dependency-only | EXISTING (J0 fix) |
