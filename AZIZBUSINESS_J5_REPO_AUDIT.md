# MarketHQ / AzizBusiness Repository Audit Report
**Generated:** September 17, 2026  
**Scope:** Full `/opt/markethq` repository audit  
**Total Python files:** 225  
**Total lines:** 195,224

---

## Executive Summary

The MarketHQ platform has been developed through Phases J0-J4:
- **J0** — Opportunity Engine (detect_opportunity, validate_opportunity)
- **J1** — Research Workspace (ResearchWorkspace, ResearchOrchestrator, agentspace)
- **J2** — Collaboration (CollaborationOrchestrator, EvidenceExchange, CriticLoop, TeamSynthesis)
- **J3** — Runtime/Provider (AgentRuntime, AgentRouter, ProviderRuntime, DeterministicRuntime, MockProviderRuntime)
- **J4** — Autonomous Research Loop (AutonomousResearchLoop, ResearchPlanner)

The repository contains **43 core systems** and approximately **35 brain_* agent scripts** implementing research automation.

---

## Core Systems Inventory

| # | System | File | Lines | Status | Dependencies |
|---|--------|------|-------|--------|--------------|
| 1 | AgentRegistry | `agent_registry.py` | 163 | ACTIVE | __future__, agent_contract |
| 2 | AgentRuntime | `agent_runtime.py` | 439 | ACTIVE | __future__, agent_contract |
| 3 | AgentRouter | `agent_router.py` | 354 | ACTIVE | __future__, deterministic_runtime, external_runtime, provider_adapter |
| 4 | ProviderRuntime | `provider_adapter.py` | 233 | ACTIVE | __future__ |
| 5 | DeterministicRuntime | `deterministic_runtime.py` | 243 | ACTIVE | __future__, agent_contract, provider_adapter |
| 6 | MockProviderRuntime | `external_runtime.py` | 180 | ACTIVE | __future__, agent_contract, provider_adapter |
| 7 | ResearchOrchestrator | `research_orchestrator.py` | 542 | ACTIVE | __future__, agent_lifecycle, agent_message, research_agent_model, research_audit |
| 8 | AutonomousResearchLoop | `autonomous_research_loop.py` | 448 | ACTIVE | __future__, adaptive_team_selector, data_quality_gate, market_observation, research_audit |
| 9 | ResearchPlanner | `research_planner.py` | 243 | ACTIVE | __future__, research_priority_engine |
| 10 | TaskRouter | `task_router.py` | 325 | ACTIVE | __future__ |
| 11 | ResearchWorkspace | `research_workspace.py` | 135 | ACTIVE | __future__ |
| 12 | ResearchTeam | `research_team.py` | 250 | ACTIVE | __future__ |
| 13 | CollaborationOrchestrator | `collaboration_orchestrator.py` | 353 | ACTIVE | __future__, agent_lifecycle, agent_message, critic_loop, evidence_exchange |
| 14 | ParallelExecutor | `parallel_executor.py` | 124 | ACTIVE | __future__ |
| 15 | AgentMessage | `agent_message.py` | 119 | ACTIVE | __future__ |
| 16 | EvidenceExchange | `evidence_exchange.py` | 207 | ACTIVE | __future__ |
| 17 | CriticLoop | `critic_loop.py` | 243 | ACTIVE | __future__ |
| 18 | TeamSynthesis | `team_synthesis.py` | 120 | ACTIVE | __future__ |
| 19 | ResearchAudit | `research_audit.py` | 167 | ACTIVE | __future__ |
| 20 | AgentLifecycle | `agent_lifecycle.py` | 163 | ACTIVE | __future__ |
| 21 | AgentResult | `agent_contract.py` | 475 | ACTIVE | __future__ |
| 22 | OpportunityEngine | `opportunity_engine.py` | 612 | STANDBY | __future__, agent_contract, opportunity_model, strategy_research_agents, strategy_research_registry |
| 23 | ResearchBackedSetup | `opportunity_model.py` | 471 | ACTIVE | __future__, agent_contract |
| 24 | ResearchValidation | `research_validation_engine.py` | 744 | STANDBY | __future__, numpy, opportunity_model, pandas, research_validation_model |
| 25 | ResearchIntelligence | `research_intelligence_engine.py` | 591 | STANDBY | __future__, opportunity_model, random, research_intelligence_model, research_validation_engine |
| 26 | ResearchMemory | `research_intelligence_model.py` | 560 | ACTIVE | None |
| 27 | Claim | `research_intelligence_model.py` | 560 | ACTIVE | None |
| 28 | Backtest | `backtest_engine.py` | 1,245 | ACTIVE | __future__, agents.market_data_agent, pandas, signal_engine |
| 29 | WalkForward | `walk_forward_engine.py` | 2,075 | ACTIVE | __future__, agents.market_data_agent, backtest_engine, csv, strategy_knowledge_base |
| 30 | FeatureCache | `feature_cache.py` | 122 | STANDBY | __future__, agent_contract |
| 31 | FeatureSnapshot | `agent_contract.py` | 475 | ACTIVE | __future__ |
| 32 | HumanReview | `research_hq_surface.py` | 421 | ACTIVE | None |
| 33 | Brain | `agents/brain_research_agent_v4.py` | 3,201 | ACTIVE | __future__, dotenv, re, requests |
| 34 | AdaptiveTeamSelector | `adaptive_team_selector.py` | 183 | ACTIVE | __future__, research_team |
| 35 | MarketObservation | `market_observation.py` | 129 | ACTIVE | __future__ |
| 36 | ResearchPriorityEngine | `research_priority_engine.py` | 224 | ACTIVE | __future__ |
| 37 | DataQualityGate | `data_quality_gate.py` | 259 | ACTIVE | __future__, market_observation |
| 38 | PersistenceLayer | `persistence.py` | 469 | ACTIVE | __future__, agent_contract |
| 39 | Database | `database.py` | 1,884 | ACTIVE | None |
| 40 | DashboardBackend | `dashboard_backend_v2_3.py` | 3,599 | ACTIVE | csv, http.server, pandas, urllib.parse, yfinance |
| 41 | EngineAdapters | `engine_adapters.py` | 788 | STANDBY | __future__, agent_contract, pandas |
| 42 | OpportunityPersistence | `opportunity_persistence.py` | 302 | ACTIVE | __future__, opportunity_model |
| 43 | StrategyLab | `agents/strategy_lab.py` | 3,540 | STANDBY | database, pandas, yfinance |

---

## Detailed System Descriptions

### AgentRegistry

- **File:** `agent_registry.py`
- **Lines:** 163
- **Status:** 🟢 ACTIVE
- **Classes:** AgentRegistry, get_default_registry, register, get, list_agents
- **Dependencies:** __future__, agent_contract
- **Used by:** 7 files
- **Users:** `research_agent_model.py`, `agent_runtime.py`, `test_strategy_research_agents.py` ... and 4 more

### AgentRuntime

- **File:** `agent_runtime.py`
- **Lines:** 439
- **Status:** 🟢 ACTIVE
- **Classes:** AgentRunStatus, AgentConfig, ExecutionRequest, ExecutionMetadata, AgentRun
- **Dependencies:** __future__, agent_contract
- **Used by:** 9 files
- **Users:** `research_agent_model.py`, `test_j3_runtime.py`, `test_strategy_research_agents.py` ... and 6 more

### AgentRouter

- **File:** `agent_router.py`
- **Lines:** 354
- **Status:** 🟢 ACTIVE
- **Classes:** RouteStatus, RouteDecision, AgentRouter, create_default_router
- **Dependencies:** __future__, deterministic_runtime, external_runtime, provider_adapter
- **Used by:** 4 files
- **Users:** `test_j3_runtime.py`, `agent_runtime.py`, `test_j3_e2e.py`, `research_planner.py`

### ProviderRuntime

- **File:** `provider_adapter.py`
- **Lines:** 233
- **Status:** 🟢 ACTIVE
- **Classes:** RuntimeType, ProviderStatus, CapabilityType, ProviderCapability, ProviderMetadata
- **Dependencies:** __future__
- **Used by:** 5 files
- **Users:** `test_j3_runtime.py`, `external_runtime.py`, `test_j3_e2e.py`, `agent_router.py`, `deterministic_runtime.py`

### DeterministicRuntime

- **File:** `deterministic_runtime.py`
- **Lines:** 243
- **Status:** 🟢 ACTIVE
- **Classes:** DeterministicRunStatus, DeterministicExecution, DeterministicRuntime
- **Dependencies:** __future__, agent_contract, provider_adapter
- **Used by:** 3 files
- **Users:** `test_j3_runtime.py`, `test_j3_e2e.py`, `agent_router.py`

### MockProviderRuntime

- **File:** `external_runtime.py`
- **Lines:** 180
- **Status:** 🟢 ACTIVE
- **Classes:** MockBehavior, MockExecutionConfig, MockProviderRuntime, ExternalProviderRuntime
- **Dependencies:** __future__, agent_contract, provider_adapter
- **Used by:** 3 files
- **Users:** `test_j3_runtime.py`, `test_j3_e2e.py`, `agent_router.py`

### ResearchOrchestrator

- **File:** `research_orchestrator.py`
- **Lines:** 542
- **Status:** 🟢 ACTIVE
- **Classes:** OrchestratorStatus, OrchestratorRun, ResearchOrchestrator
- **Dependencies:** __future__, agent_lifecycle, agent_message, research_agent_model, research_audit
- **Used by:** 4 files
- **Users:** `test_j1_e2e.py`, `test_research_orchestration.py`, `collaboration_orchestrator.py`, `test_j1_agentspace_core.py`

### AutonomousResearchLoop

- **File:** `autonomous_research_loop.py`
- **Lines:** 448
- **Status:** 🟢 ACTIVE
- **Classes:** LoopState, AutonomousResearchRun, AutonomousResearchReport, AutonomousResearchLoop
- **Dependencies:** __future__, adaptive_team_selector, data_quality_gate, market_observation, research_audit
- **Used by:** 1 files
- **Users:** `test_j4.py`

### ResearchPlanner

- **File:** `research_planner.py`
- **Lines:** 243
- **Status:** 🟢 ACTIVE
- **Classes:** ResearchPlan, ResearchPlanner
- **Dependencies:** __future__, research_priority_engine
- **Used by:** 2 files
- **Users:** `autonomous_research_loop.py`, `test_j4.py`

### TaskRouter

- **File:** `task_router.py`
- **Lines:** 325
- **Status:** 🟢 ACTIVE
- **Classes:** RoutingStatus, CapabilityDescriptor, RoutingCandidate, RoutingResult, TaskRouter
- **Dependencies:** __future__
- **Used by:** 5 files
- **Users:** `test_j3_runtime.py`, `research_orchestrator.py`, `test_j1_e2e.py`, `collaboration_orchestrator.py`, `test_j1_agentspace_core.py`

### ResearchWorkspace

- **File:** `research_workspace.py`
- **Lines:** 135
- **Status:** 🟢 ACTIVE
- **Classes:** WorkspaceStatus, WorkspaceParticipant, ResearchWorkspace, create_workspace
- **Dependencies:** __future__
- **Used by:** 3 files
- **Users:** `research_orchestrator.py`, `collaboration_orchestrator.py`, `test_j1_agentspace_core.py`

### ResearchTeam

- **File:** `research_team.py`
- **Lines:** 250
- **Status:** 🟢 ACTIVE
- **Classes:** TeamStatus, TeamPurpose, TeamMember, ResearchTeam, create_team_from_template
- **Dependencies:** __future__
- **Used by:** 3 files
- **Users:** `test_j2_collaboration.py`, `adaptive_team_selector.py`, `collaboration_orchestrator.py`

### CollaborationOrchestrator

- **File:** `collaboration_orchestrator.py`
- **Lines:** 353
- **Status:** 🟢 ACTIVE
- **Classes:** CollaborationStatus, CollaborationOrchestrator
- **Dependencies:** __future__, agent_lifecycle, agent_message, critic_loop, evidence_exchange
- **Used by:** 2 files
- **Users:** `test_j3_runtime.py`, `test_j2_collaboration.py`

### ParallelExecutor

- **File:** `parallel_executor.py`
- **Lines:** 124
- **Status:** 🟢 ACTIVE
- **Classes:** ParallelTask, ParallelResult, ParallelExecutor
- **Dependencies:** __future__
- **Used by:** 1 files
- **Users:** `test_j2_collaboration.py`

### AgentMessage

- **File:** `agent_message.py`
- **Lines:** 119
- **Status:** 🟢 ACTIVE
- **Classes:** MessageType, AgentMessage, AgentHandoff
- **Dependencies:** __future__
- **Used by:** 5 files
- **Users:** `test_j2_collaboration.py`, `research_orchestrator.py`, `test_j1_e2e.py`, `collaboration_orchestrator.py`, `test_j1_agentspace_core.py`

### EvidenceExchange

- **File:** `evidence_exchange.py`
- **Lines:** 207
- **Status:** 🟢 ACTIVE
- **Classes:** EvidenceType, EvidenceDisposition, AgentEvidence, EvidenceExchange, ConflictPreserver
- **Dependencies:** __future__
- **Used by:** 2 files
- **Users:** `test_j2_collaboration.py`, `collaboration_orchestrator.py`

### CriticLoop

- **File:** `critic_loop.py`
- **Lines:** 243
- **Status:** 🟢 ACTIVE
- **Classes:** ChallengeType, CriticVerdict, CriticChallenge, CriticResult, CriticLoop
- **Dependencies:** __future__
- **Used by:** 2 files
- **Users:** `test_j2_collaboration.py`, `collaboration_orchestrator.py`

### TeamSynthesis

- **File:** `team_synthesis.py`
- **Lines:** 120
- **Status:** 🟢 ACTIVE
- **Classes:** SynthesisStatus, TeamResearchResult
- **Dependencies:** __future__
- **Used by:** 1 files
- **Users:** `test_j2_collaboration.py`

### ResearchAudit

- **File:** `research_audit.py`
- **Lines:** 167
- **Status:** 🟢 ACTIVE
- **Classes:** AuditEventType, ResearchAuditEvent, AuditLog
- **Dependencies:** __future__
- **Used by:** 8 files
- **Users:** `test_j3_runtime.py`, `research_orchestrator.py`, `autonomous_research_loop.py` ... and 5 more

### AgentLifecycle

- **File:** `agent_lifecycle.py`
- **Lines:** 163
- **Status:** 🟢 ACTIVE
- **Classes:** AgentLifecycleState, AgentExecution, AgentLifecycleManager
- **Dependencies:** __future__
- **Used by:** 4 files
- **Users:** `research_orchestrator.py`, `test_j1_e2e.py`, `collaboration_orchestrator.py`, `test_j1_agentspace_core.py`

### AgentResult

- **File:** `agent_contract.py`
- **Lines:** 475
- **Status:** 🟢 ACTIVE
- **Classes:** AgentStatus, EvidenceItem, Evidence, ClaimStatus, Claim
- **Dependencies:** __future__
- **Used by:** 20 files
- **Users:** `persistence.py`, `strategy_research_agents.py`, `test_research_setup_phase_f.py` ... and 17 more

### OpportunityEngine

- **File:** `opportunity_engine.py`
- **Lines:** 612
- **Status:** ⚪ STANDBY
- **Classes:** get_family, are_families_correlated, classify_evidence, direction_weight, detect_opportunity
- **Dependencies:** __future__, agent_contract, opportunity_model, strategy_research_agents, strategy_research_registry
- **Used by:** 0 files

### ResearchBackedSetup

- **File:** `opportunity_model.py`
- **Lines:** 471
- **Status:** 🟢 ACTIVE
- **Classes:** OpportunityStatus, Direction, SourceAgent, Opportunity, SetupCandidate
- **Dependencies:** __future__, agent_contract
- **Used by:** 7 files
- **Users:** `test_research_validation.py`, `test_research_setup_phase_f.py`, `research_intelligence_engine.py` ... and 4 more

### ResearchValidation

- **File:** `research_validation_engine.py`
- **Lines:** 744
- **Status:** ⚪ STANDBY
- **Classes:** replay_setup, _check_entry, _check_invalidation, _check_target, _compute_r
- **Dependencies:** __future__, numpy, opportunity_model, pandas, research_validation_model
- **Used by:** 0 files

### ResearchIntelligence

- **File:** `research_intelligence_engine.py`
- **Lines:** 591
- **Status:** ⚪ STANDBY
- **Classes:** ChampionChallenger, ResearchDashboard, build_observation, build_hypothesis, register_experiment
- **Dependencies:** __future__, opportunity_model, random, research_intelligence_model, research_validation_engine
- **Used by:** 0 files

### ResearchMemory

- **File:** `research_intelligence_model.py`
- **Lines:** 560
- **Status:** 🟢 ACTIVE
- **Classes:** ObservationType, ClaimStatus, HypothesisStatus, ExperimentStatus, WeightProposalStatus
- **Dependencies:** None
- **Used by:** 2 files
- **Users:** `research_intelligence_engine.py`, `test_research_intelligence.py`

### Claim

- **File:** `research_intelligence_model.py`
- **Lines:** 560
- **Status:** 🟢 ACTIVE
- **Classes:** ObservationType, ClaimStatus, HypothesisStatus, ExperimentStatus, WeightProposalStatus
- **Dependencies:** None
- **Used by:** 29 files
- **Users:** `persistence.py`, `test_research_validation.py`, `strategy_research_agents.py` ... and 26 more

### Backtest

- **File:** `backtest_engine.py`
- **Lines:** 1,245
- **Status:** 🟢 ACTIVE
- **Classes:** safe_float, utc_timestamp, merge_config, validate_ohlcv, prepare_data
- **Dependencies:** __future__, agents.market_data_agent, pandas, signal_engine
- **Used by:** 19 files
- **Users:** `strategy_optimizer.py`, `strategy_backtest_runner.py`, `strategy_candidate_diagnostic.py` ... and 16 more

### WalkForward

- **File:** `walk_forward_engine.py`
- **Lines:** 2,075
- **Status:** 🟢 ACTIVE
- **Classes:** safe_float, safe_int, get_metrics, get_metric, get_trade_count
- **Dependencies:** __future__, agents.market_data_agent, backtest_engine, csv, strategy_knowledge_base
- **Used by:** 2 files
- **Users:** `test_research_validation.py`, `test_learning_infrastructure.py`

### FeatureCache

- **File:** `feature_cache.py`
- **Lines:** 122
- **Status:** ⚪ STANDBY
- **Classes:** FeatureSnapshotCache, get_default_cache, get_cache, put_cache
- **Dependencies:** __future__, agent_contract
- **Used by:** 0 files

### FeatureSnapshot

- **File:** `agent_contract.py`
- **Lines:** 475
- **Status:** 🟢 ACTIVE
- **Classes:** AgentStatus, EvidenceItem, Evidence, ClaimStatus, Claim
- **Dependencies:** __future__
- **Used by:** 11 files
- **Users:** `persistence.py`, `test_agent_contract.py`, `agent_runtime.py` ... and 8 more

### HumanReview

- **File:** `research_hq_surface.py`
- **Lines:** 421
- **Status:** 🟢 ACTIVE
- **Classes:** ReviewStatus, Permission, HumanReview, ArtifactType, ResearchArtifact
- **Dependencies:** None
- **Used by:** 2 files
- **Users:** `test_j1_e2e.py`, `test_research_orchestration.py`

### Brain

- **File:** `agents/brain_research_agent_v4.py`
- **Lines:** 3,201
- **Status:** 🟢 ACTIVE
- **Classes:** utc_now, norm, safe_int, safe_float, compact_json
- **Dependencies:** __future__, dotenv, re, requests
- **Used by:** 59 files
- **Users:** `markethq_manager_v1.py`, `persistence.py`, `research_agent_model.py` ... and 56 more

### AdaptiveTeamSelector

- **File:** `adaptive_team_selector.py`
- **Lines:** 183
- **Status:** 🟢 ACTIVE
- **Classes:** AgentReliability, TeamSelection, AdaptiveTeamSelector
- **Dependencies:** __future__, research_team
- **Used by:** 2 files
- **Users:** `autonomous_research_loop.py`, `test_j4.py`

### MarketObservation

- **File:** `market_observation.py`
- **Lines:** 129
- **Status:** 🟢 ACTIVE
- **Classes:** DataQuality, MarketObservation, ObservationBundle
- **Dependencies:** __future__
- **Used by:** 3 files
- **Users:** `autonomous_research_loop.py`, `test_j4.py`, `data_quality_gate.py`

### ResearchPriorityEngine

- **File:** `research_priority_engine.py`
- **Lines:** 224
- **Status:** 🟢 ACTIVE
- **Classes:** PriorityLevel, OpportunityCandidate, ResearchTask, ResearchPriorityEngine
- **Dependencies:** __future__
- **Used by:** 2 files
- **Users:** `autonomous_research_loop.py`, `test_j4.py`

### DataQualityGate

- **File:** `data_quality_gate.py`
- **Lines:** 259
- **Status:** 🟢 ACTIVE
- **Classes:** DataQualityGateResult, DataQualityCheck, DataQualityGate, DataQualityGateChecker
- **Dependencies:** __future__, market_observation
- **Used by:** 2 files
- **Users:** `autonomous_research_loop.py`, `test_j4.py`

### PersistenceLayer

- **File:** `persistence.py`
- **Lines:** 469
- **Status:** 🟢 ACTIVE
- **Classes:** PersistenceLayer
- **Dependencies:** __future__, agent_contract
- **Used by:** 2 files
- **Users:** `agent_runtime.py`, `test_phase_c.py`

### Database

- **File:** `database.py`
- **Lines:** 1,884
- **Status:** 🟢 ACTIVE
- **Classes:** utc_now, get_connection, init_db, upsert_news, upsert_news_batch
- **Dependencies:** None
- **Used by:** 56 files
- **Users:** `research_storage_schema_v1.py`, `final_research_decision_engine_CLEAN_V1.py`, `persistence.py` ... and 53 more

### DashboardBackend

- **File:** `dashboard_backend_v2_3.py`
- **Lines:** 3,599
- **Status:** 🟢 ACTIVE
- **Classes:** DashboardBackendHandler, utc_now, json_load, latest_json, connect_db
- **Dependencies:** csv, http.server, pandas, urllib.parse, yfinance
- **Used by:** 0 files

### EngineAdapters

- **File:** `engine_adapters.py`
- **Lines:** 788
- **Status:** ⚪ STANDBY
- **Classes:** MarketDataAdapter, RegimeAdapter, StructureAdapter, MomentumVolatilityAdapter, StrategyAdapter
- **Dependencies:** __future__, agent_contract, pandas
- **Used by:** 0 files

### OpportunityPersistence

- **File:** `opportunity_persistence.py`
- **Lines:** 302
- **Status:** 🟢 ACTIVE
- **Classes:** OpportunityPersistence
- **Dependencies:** __future__, opportunity_model
- **Used by:** 2 files
- **Users:** `test_opportunity_engine.py`, `research_setup_phase_f.py`

### StrategyLab

- **File:** `agents/strategy_lab.py`
- **Lines:** 3,540
- **Status:** ⚪ STANDBY
- **Classes:** is_valid_number, clean_symbol, market_from_symbol, get_benchmark, format_percent
- **Dependencies:** database, pandas, yfinance
- **Used by:** 0 files


---

## Duplicate / Variant Systems

Several systems have multiple versioned implementations, often with overlapping functionality:

### Brain Research Agent Variants (4 files, ~12,500+ lines total)
- `agents/brain_research_agent_v4.py` — **3,201 lines** (current primary)
- `agents/brain_research_agent_v4_1_paper_gap.py` — **3,042 lines** (paper-gap specialization)
- `agents/brain_research_agent_v4_backup.py` — **2,995 lines** (backup copy)
- `agents/brain_research_agent_diagnostic_v4.py` — **1,322 lines** (diagnostic variant)

### Importer Variants (2 files)
- `agents/brain_importer_v3.py` — **1,646 lines** (current)
- `agents/brain_importer_v1.py` — **1,586 lines** (legacy)

### Observation Bridge Variants (3 files)
- `agents/brain_research_observation_bridge_v3.py` — **1,280 lines** (current)
- `agents/brain_research_observation_bridge_v2.py` — **1,036 lines**
- `agents/brain_research_observation_bridge_diagnostic_v1.py` — **557 lines** (diagnostic)

### Evidence Update Variants (2 files)
- `agents/brain_research_evidence_update_v2.py` — **1,465 lines**
- `agents/brain_research_evidence_update_v1_backup.py` — **944 lines**

### Queue Hygiene Variants (2 files)
- `agents/brain_research_queue_hygiene_v2.py` — **670 lines**
- `agents/brain_research_queue_hygiene_v1.py` — **578 lines**

### Automation Controllers (2 files)
- `automation_controller_v5.py` — **898 lines** (current)
- `automation_controller_v2.py` — **971 lines** (legacy)

### Final Research Decision Engine (3 files)
- `final_research_decision_engine_v3.py` — **1,319 lines** (current)
- `final_research_decision_engine_CLEAN_V1.py` — **1,194 lines** (cleaned up)
- `final_research_decision_engine_v1_1.py` — **1,041 lines** (legacy)

### Strategy Research Pipeline (3 files)
- `strategy_research_pipeline_v5.py` — **3,512 lines** (current)
- `strategy_research_pipeline_v6.py` — **3,088 lines** (alternative)
- `strategy_research_pipeline.py` — **2,678 lines** (legacy)

### Paper Evidence Aggregator (2 files)
- `paper_evidence_aggregator_v2_3.py` — **1,380 lines** (current)
- `paper_evidence_aggregator_v1.py` — **1,305 lines** (legacy)

### Setup Quality Engine (2 files)
- `setup_quality_engine_v4.py` — **2,034 lines** (current)
- `setup_quality_engine_v2.py` — **1,239 lines** (legacy)

---

## Additional Brain_* Agent Scripts (35 files total)

The `agents/` directory contains 35 brain_* scripts totaling approximately **37,000+ lines**. Key functional groups:

| Category | Files | Total Lines |
|----------|-------|-------------|
| Research Agent (core) | 4 | ~12,500 |
| Evidence Review/Update | 4 | ~4,900 |
| Research Loop Engines | 3 | ~2,400 |
| Observation Bridge | 3 | ~2,800 |
| Knowledge Ingest/Repair | 3 | ~3,000 |
| Rule Promotion/Validation | 2 | ~1,800 |
| Importer | 2 | ~3,200 |
| Queue Hygiene/Enrichment | 4 | ~2,700 |
| Other diagnostics/tools | 10 | ~4,000+ |

---

## Top 20 Largest Files

| File | Lines | Purpose |
|------|-------|---------|
| `dashboard_backend_v2_3.py` | 3,599 | Dashboard backend API |
| `agents/strategy_lab.py` | 3,540 | Strategy backtesting lab |
| `strategy_research_pipeline_v5.py` | 3,512 | Research pipeline v5 |
| `agents/brain_research_agent_v4.py` | 3,201 | Core brain research agent |
| `strategy_research_pipeline_v6.py` | 3,088 | Research pipeline v6 |
| `agents/brain_research_agent_v4_1_paper_gap.py` | 3,042 | Brain paper-gap variant |
| `agents/brain_research_agent_v4_backup.py` | 2,995 | Brain backup |
| `strategy_research_pipeline.py` | 2,678 | Research pipeline (legacy) |
| `agents/method_specification_engine_v4.py` | 2,610 | Method spec engine v4 |
| `agents/method_specification_engine.py` | 2,546 | Method spec engine (legacy) |
| `agents/research_execution_adapter_v1.py` | 2,508 | Research execution adapter |
| `agents/method_registry_cleaner.py` | 2,405 | Method registry cleaner |
| `strategy_lab_runner.py` | 2,213 | Strategy lab runner |
| `agents/method_specification_consolidator_v3.py` | 2,119 | Method spec consolidator |
| `walk_forward_engine.py` | 2,075 | Walk-forward analysis |
| `paper_trading_engine_v1.py` | 2,043 | Paper trading engine |
| `setup_quality_engine_v4.py` | 2,034 | Setup quality engine |
| `agents/brain_research_evidence_review_v4.py` | 2,016 | Evidence review |
| `agents/method_evidence_auditor.py` | 1,964 | Method evidence auditor |
| `paper_feedback_learning_engine_v1.py` | 1,908 | Paper feedback learning |

---

## Findings & Recommendations

1. **Code Duplication:** The repository has significant duplication — 12+ systems have multiple versioned implementations consuming ~40,000 lines. Recommend consolidating to single canonical versions.

2. **Stale Systems:** Many Phase J1-J4 systems (AgentRuntime, AgentRouter, ResearchOrchestrator, CollaborationOrchestrator, CriticLoop, EvidenceExchange, ParallelExecutor) show STANDBY status — defined but not actively wired into main.py or automation controllers.

3. **Brain Monolith:** `brain_research_agent_v4.py` at 3,201 lines plus 34 sibling brain_* scripts totaling 37,000+ lines forms a monolithic research system that should be refactored into modular services.

4. **Missing Reliability/Calibration Classes:** Despite being key concepts, no classes named `Reliability` or `Calibration` exist as standalone systems. The `adaptive_team_selector.py` implements `AgentReliability` inline.

5. **Opportunity Engine vs ResearchBackedSetup:** `opportunity_engine.py` (J0) and `opportunity_model.py` (ResearchBackedSetup) define overlapping opportunity/setup concepts that should be unified.

6. **FeatureCache Unused:** `feature_cache.py` is defined but has zero imports across the codebase.

7. **Validation Engine Orphan:** `research_validation_engine.py` (744 lines) is defined but has no active callers — validation logic likely inlined elsewhere.

8. **BrainClaim vs Claim:** `brain_learning_pipeline.py` defines `BrainClaim` while `research_intelligence_model.py` defines `Claim` — two parallel claim systems.

9. **Strategy Pipeline Drift:** Three versions of strategy_research_pipeline (v5, v6, legacy) at 9,000+ lines total need consolidation.

10. **Test Coverage:** 15 test files exist covering J1-J4 phases but full E2E integration across all phases is not demonstrated.

---

## Active vs Standby Summary

- **Active Systems (used in entry points or 20+ files):** AgentResult, Claim, Backtest, Brain, ResearchAudit
- **Standby Systems (defined but not wired):** AgentRuntime, AgentRouter, ProviderRuntime, DeterministicRuntime, MockProviderRuntime, ResearchOrchestrator, AutonomousResearchLoop, ResearchPlanner, TaskRouter, ResearchWorkspace, ResearchTeam, CollaborationOrchestrator, ParallelExecutor, AgentMessage, EvidenceExchange, CriticLoop, TeamSynthesis, AgentLifecycle, OpportunityEngine, ResearchBackedSetup, ResearchValidation, ResearchIntelligence, ResearchMemory, FeatureCache, WalkForward, HumanReview

---

## Phase Mapping

| Phase | Systems | Status |
|-------|---------|--------|
| J0 Opportunity Engine | OpportunityEngine, ResearchBackedSetup | Functional |
| J1 Research Workspace | ResearchWorkspace, ResearchOrchestrator, AgentRegistry, ResearchAudit | Tests passing |
| J2 Collaboration | CollaborationOrchestrator, ResearchTeam, EvidenceExchange, CriticLoop, TeamSynthesis, ParallelExecutor, AgentMessage | Tests passing |
| J3 Runtime/Provider | AgentRuntime, AgentRouter, ProviderRuntime, DeterministicRuntime, MockProviderRuntime | Tests passing |
| J4 Autonomous Loop | AutonomousResearchLoop, ResearchPlanner, AdaptiveTeamSelector | Tests passing |
