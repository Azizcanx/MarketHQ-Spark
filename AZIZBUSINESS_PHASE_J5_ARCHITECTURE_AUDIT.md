# AZIZBUSINESS PHASE J5 — ARCHITECTURE AUDIT

**Date:** 2026-09-17
**Purpose:** Audit before implementing Continuous Intelligence System

---

## 1. Repo Snapshot

### Location
`/opt/markethq` — 225 Python files, 195,224 lines, `market_hq.db` (13.5MB)

### Phase Progression
- J0 → Opportunity Engine (detect_opportunity, validate_opportunity)
- J1 → Research Workspace (ResearchWorkspace, ResearchOrchestrator, agentspace)
- J2 → Collaboration (CollaborationOrchestrator, EvidenceExchange, CriticLoop, TeamSynthesis)
- J3 → Runtime/Provider (AgentRuntime, AgentRouter, ProviderRuntime, DeterministicRuntime, MockProviderRuntime)
- J4 → Autonomous Research Loop (AutonomousResearchLoop, ResearchPlanner, AdaptiveTeamSelector, MarketObservation, ResearchPriorityEngine, DataQualityGate)

### Established Loop (J4)
```
OBSERVE → DETECT → PRIORITIZE → PLAN → DELEGATE → RESEARCH
→ COLLABORATE → CRITIC → SYNTHESIZE → VALIDATE → REMEMBER → LEARN
→ REPORT → WAIT → OBSERVE (cycle repeats)
```

---

## 2. Mevcut Sistemler (Kullanılabilir Altyapı)

### Core Runtime (J1/J3 — ACTIVE)
- `agent_registry.py` — AgentRegistry, register/get/list_agents
- `agent_runtime.py` — AgentRunStatus, AgentConfig, ExecutionRequest, ExecutionMetadata, AgentRun
- `agent_router.py` — RouteStatus, RouteDecision, AgentRouter, create_default_router
- `provider_adapter.py` — RuntimeType, ProviderStatus, CapabilityType, ProviderCapability, ProviderMetadata
- `deterministic_runtime.py` — DeterministicRunStatus, DeterministicExecution, DeterministicRuntime
- `external_runtime.py` — MockBehavior, MockExecutionConfig, MockProviderRuntime, ExternalProviderRuntime
- `agent_contract.py` — AgentResult, EvidenceItem, Evidence, ClaimStatus, Claim, FeatureSnapshot (475 lines, 20 dosya kullanıyor)

### Orchestration (J1/J2 — ACTIVE)
- `research_orchestrator.py` — OrchestratorStatus, OrchestratorRun, ResearchOrchestrator (542 lines)
- `research_team.py` — TeamStatus, TeamPurpose, TeamMember, ResearchTeam, create_team_from_template (250 lines)
- `collaboration_orchestrator.py` — CollaborationStatus, CollaborationOrchestrator (353 lines)
- `parallel_executor.py` — ParallelTask, ParallelResult, ParallelExecutor (124 lines)
- `agent_message.py` — MessageType, AgentMessage, AgentHandoff (119 lines)
- `evidence_exchange.py` — EvidenceType, EvidenceDisposition, AgentEvidence, EvidenceExchange, ConflictPreserver (207 lines)
- `critic_loop.py` — ChallengeType, CriticVerdict, CriticChallenge, CriticResult, CriticLoop (243 lines)
- `team_synthesis.py` — SynthesisStatus, TeamResearchResult (120 lines)

### Research Intelligence (J4/H — ACTIVE/ STANDBY)
- `research_intelligence_model.py` — ObservationType, ClaimStatus, HypothesisStatus, ExperimentStatus, WeightProposalStatus, Observation, Hypothesis, Experiment, Result, Claim, Evidence, ResearchMemory, ReliabilityProfile, CalibrationProfile, FeatureImportance, WeightProposal, SimilarityMatch, FailurePattern (560 lines, 29 dosya kullanıyor)
- `research_intelligence_engine.py` — build_observation, build_hypothesis, register_experiment, run_experiment, ChampionChallenger, ResearchDashboard (591 lines, STANDBY)
- `research_priority_engine.py` — PriorityLevel, OpportunityCandidate, ResearchTask, ResearchPriorityEngine (224 lines)
- `research_planner.py` — ResearchPlan, ResearchPlanner (243 lines)
- `adaptive_team_selector.py` — AgentReliability, TeamSelection, AdaptiveTeamSelector (183 lines)
- `market_observation.py` — DataQuality, MarketObservation, ObservationBundle (129 lines)
- `data_quality_gate.py` — DataQualityGateResult, DataQualityCheck, DataQualityGate, DataQualityGateChecker (259 lines)

### Validation + Persistence (J0/G/F — ACTIVE/STANDBY)
- `opportunity_model.py` — OpportunityStatus, Direction, SourceAgent, Opportunity, SetupCandidate (471 lines, 7 dosya kullanıyor)
- `opportunity_engine.py` — get_family, are_families_correlated, classify_evidence, direction_weight, detect_opportunity (612 lines, STANDBY — J0, kullanılmıyor)
- `research_validation_engine.py` — replay_setup, _check_entry, _check_invalidation, _check_target, _compute_r, validate_setups, walk_forward_validation, compute_validation_metrics, audit_lookahead (744 lines, STANDBY)
- `research_validation_model.py` — HistoricalOutcome, ValidationMetrics, DataSufficiency, OutcomeType, ResearchClaim, ClaimStatus (8692 header parse edilmiş)
- `persistence.py` — PersistenceLayer (469 lines, agent_runs/agent_results/evidence_items/agent_claims/feature_snapshots tabloları)
- `database.py` — utc_now, get_connection, init_db, upsert_news, upsert_news_batch (1,884 lines)
- `opportunity_persistence.py` — OpportunityPersistence (302 lines)

### Human Review + HQ (J0/I — ACTIVE)
- `research_hq_surface.py` — ReviewStatus, Permission, HumanReview, ArtifactType, ResearchArtifact, ProvenanceNode (421 lines)
- `research_audit.py` — AuditEventType, ResearchAuditEvent, AuditLog (167 lines, 8 dosya kullanıyor)

### Brain (H — ACTIVE, monolithic)
- `agents/brain_research_agent_v4.py` — 3,201 lines (utama agent)
- 34 sibling brain_* script → ~37,000 lines
- `brain_learning_pipeline.py` — BrainClaim (ayrı Claim sistemi)
- `agents/brain_research_observation_bridge_v3.py` — 1,280 lines
- `agents/brain_research_evidence_update_v2.py` — 1,465 lines
- `agents/brain_research_queue_hygiene_v2.py` — 670 lines
- `paper_trading_engine_v1.py` — 2,043 lines
- `paper_evidence_aggregator_v2_3.py` — 1,380 lines
- `paper_evidence_brain_bridge_v1.py` — 2,553 lines
- `paper_feedback_learning_engine_v1.py` — 1,908 lines

### Backtest/Walk-Forward (J0/G — ACTIVE)
- `backtest_engine.py` — safe_float, utc_timestamp, merge_config, validate_ohlcv, prepare_data (1,245 lines, 19 dosya kullanıyor)
- `walk_forward_engine.py` — safe_float, safe_int, get_metrics, get_metric, get_trade_count (2,075 lines, 2 dosya kullanıyor)

### J4 Loop (ACTIVE)
- `autonomous_research_loop.py` — LoopState, AutonomousResearchRun, AutonomousResearchReport, AutonomousResearchLoop (448 lines, 1 dosya kullanıyor — test_j4.py)

---

## 3. Duplicate Riskleri (J5'te Dikkat)

### 3.1 Ayrı Claim Sistemleri
- `research_intelligence_model.py` → `Claim` (ClaimStatus: UNTESTED/TESTED/SUPPORTED/UNSTABLE/REJECTED)
- `brain_learning_pipeline.py` → `BrainClaim`
- `agent_contract.py` → `ClaimStatus` + `Claim`
→ **J5 tek Claim lifecycle kullanmalı.** research_intelligence_model.py'nın Claim'ini genişlet.

### 3.2 Opportunity/New Opportunity Yapısı
- `opportunity_engine.py` (J0) → detect_opportunity (612 lines, STANDBY)
- `opportunity_model.py` → Opportunity + SetupCandidate + ResearchBackedSetup (471 lines, ACTIVE)
→ **J5 opportunity_engine.py'si değil, opportunity_model.py'i genişletmeli.**

### 3.3 Validation Motoru
- `research_validation_engine.py` (744 lines, STANDBY) → replay_setup, validate_setups, walk_forward_validation
- Validation logikası başka yerlere inlined olabilir
→ **J5 validation engine'ini aktif kullanmalı, duplicate validation yazaplasticçı.**

### 3.4 Persistence Katmanı
- `persistence.py` → agent_runs, agent_results, evidence_items, agent_claims, feature_snapshots
- `research_storage_schema_v1.py` → research storage
- `research_memory_query_adapter_v1.py` → memory query
→ **J5 yeni intelligence tabloları eklerken persistence.py'ye ekleme yapmalı, yeni persistence yafaplasticçı.**

### 3.5 Brain Monolit
- `brain_research_agent_v4.py` (3,201 lines) + 34 sibling → ~37,000 lines
→ **J5 brain_'u refactor etmez. Mevcut brain_* script'leriyle çalışır, onları duplicate etmez.**

### 3.6 Strategy Pipeline Çoğulluğu
- `strategy_research_pipeline_v5.py` (3,512)
- `strategy_research_pipeline_v6.py` (3,088)
- `strategy_research_pipeline.py` (2,678 legacy)
→ **J5 bunları consonant etmez, mevcut en aktif olanla çalışır.**

---

## 4. J5'ın Mevcut Sistemlere Eklemesi (Yeni Component = Sadece Eksik olanlar)

### 4.1 IntelligenceState (YENİ — küçük)
Mevcut `LoopState` (autonomous_research_loop.py) cycle içi state makine.
J5'e **system-wide IntelligenceState** gerekli:
- INITIALIZING, OBSERVING, STABLE, CHANGE_DETECTED, RESEARCHING, VALIDATING, LEARNING, HUMAN_REVIEW, PAUSED, ERROR, STALE
- State değişim audit ile
- Cycle_id, timestamp, reason, provenance, context_version taşır

→ ** autonomous_research_loop.py'daki LoopState ile karıştırmama.** Bu system-level, LoopState cycle-level.

### 4.2 ContinuousLoop (YENİ — AutonomousResearchLoop'u genişletir)
Mevcut `AutonomousResearchLoop` bir cycle çalışır → durur → rapor verir.
J5'e **continuous operation** gerekli:
- Event-driven trigger'lar (scheduled, opportunity_detected, regime_changed, drift_detected, claim_weakened, validation_failed, human_requested)
- Cooldown (duplicate research prevention)
- ResearchBudget (max cycles, max tasks, max agent calls, max runtime)
- ContinuousLoop → AutonomousResearchLoop'u managed lifecycle ile sarmalar

→ **AutonomousResearchLoop'u silme, onu içinde kullan.**

### 4.3 ChangeDetectionEngine (YENİ — genişletilebilir)
Mevcut `market_observation.py` → DataQuality, MarketObservation, ObservationBundle
J5'e **change detection** gerekli:
- Regime transition, volatility transition, momentum transition, trend transition, liquidity change, structure change, feature distribution change, opportunity frequency change, setup distribution change, historical behavior drift, agent evidence drift
- ChangeDetectionEvent → trigger oluşturur (prediction değil, "araştırma yapılmasını gerektirir")

→ **market_observation.py ile integration.** ObservationBundle üzerine change detection katmanı.

### 4.4 RegimeTransitionMemory (YENİ — ResearchMemory genişletmesi)
Mevcut `research_intelligence_model.py` → ResearchMemory
J5'e **regime transition memory** gerekli:
- previous regime, new regime, transition context, historical frequency, outcomes, research findings, supporting evidence, conflicting evidence, sample size, confidence, timestamps
- RANGE_LOW_VOL → EXPANDING_VOLATILITY → UPTREND gibi geçişleri saklar

→ **ResearchMemory'e yeni memory_type ekler (REGIME_TRANSITION).**

### 4.5 DistributionDriftEngine (YENİ)
Mevcut: yok (Benzer bir şey research_intelligence_engine.py'da Champions/Challenger ama drift yok)
J5'e **distribution drift** gerekli:
- quality distribution, regime distribution, setup distribution, strategy family distribution, feature distribution, outcome distribution, duration, RR, volatility, evidence distribution
- Drift tespit → DRIFT_DETECTED event
- Otomatik "strateji artık çalışmıyor" değildir — validation trigger'ıdır

→ **Yeni component. research_intelligence_model.py'a DriftEvent/SimilarityMatch genişletmesi.**

### 4.6 FailureMemory + Counterexample (YENİ — research_intelligence_model genişletmesi)
Mevcut:
- `research_intelligence_model.py` → FailurePattern (pattern_id, description, conditions, sample_size, outcome, recurrence, regimes, strategies, confidence, evidence)
- `research_intelligence_model.py` → Counterexample (zaten enum'da: ObservationType.COUNTEREXAMPLE)
- `research_intelligence_engine.py` → FailurePattern + Counterexample kullanıyor

J5'e **failure memory** + **counterexample engine** gerekli:
- Failed hypothesis, rejected claim, invalidated setup, bad regime assumption, weak evidence, critic rejection, data issue, lookahead violation, sample insufficiency, model instability, false recurrence
- Counterexample: claim_id, matching_context, contradictory_context, outcome, evidence, timestamp, provenance
- Counterexample bulunduğunda claim otomatik REJECT değil — WEAKENED veya UNSTABLE

→ **research_intelligence_model.py'daki FailurePattern ve Counterexample'ı genişlet. research_intelligence_engine.py'yı aktif kullan.**

### 4.7 ClaimStability (YENİ — Claim lifecycle genişletmesi)
Mevcut:
- `Claim` → stability: float = 0.0 (zaten var!)
- ClaimStatus → UNTESTED/TESTED/SUPPORTED/UNSTABLE/REJECTED

J5'e **claim stability measurement** gerekli:
- sample size, temporal stability, regime stability, asset stability, timeframe stability, validation stability, contradiction rate, recency, data quality
- SUPPORTED olsa bile sonsuza supported kalmalı değil — yeni evidence ile yeniden değerlendirilmeli

→ **Claim stability score hesabını research_intelligence_engine.py'ye ekle. Claim modeli zaten stability字段 var.**

### 4.8 TemporalDecay (YENİ — Evidence/Claim üzerine)
Mevcut: yok (Benzer Kavram yok)
J5'e **temporal decay** gerekli:
- Configurable, deterministic, transparent
- Eski evidence yok sayılmaz ama yeni evidence ile aynı ağırlıkta kabul edilmez
- Trading probability'a dönüştürme — ASLA

→ **Yeni component. Evidence ve Claim'lerin created_at/last_validated üzerinden decay score hesaplar.**

### 4.9 ResearchBudget + Cooldown (YENİ — ContinuousLoop içinde)
Mevcut:
- `AutonomousResearchLoop` → max_cycles: int = 100, cycle_count: int = 0
- `ResearchWorkspace` → budget/InProgress
- `adaptive_team_selector.py` → AgentReliability

J5'e **research budget** + **cooldown** gerekli:
- max cycles, max tasks/cycle, max agent calls, max retries, max provider calls, max runtime, max cost, max parallelism
- Budget aşılırsa BUDGET_EXCEEDED → kontrollü şekilde dur
- Cooldown: opportunity, symbol, timeframe, hypothesis, claim, research task bazında

→ **ContinuousLoop içinde budget/cooldown yönetimi.**

### 4.10 EventDrivenTriggers (YENİ — trigger registry)
Mevcut: yok (Benzer Kavram — AutonomousResearchLoop trigger: "manual" string)
J5'e **event-driven triggers** gerekli:
- scheduled, opportunity_detected, regime_changed, drift_detected, claim_weakened, validation_failed, data_restored, human_requested, recurring_research, manual_review
- Her trigger provenance taşır

→ **Yeni trigger registry. AutonomousResearchLoop'u event-driven hale getirir.**

### 4.11 SituationReport (YENİ — research_hq_surface genişletmesi)
Mevcut:
- `research_hq_surface.py` → HumanReview, ResearchArtifact, ProvenanceNode

J5'e **situation report** gerekli:
- current market context, active opportunities, recent changes, regime, research findings, conflicts, validation, failed hypotheses, recent memory, uncertainty, data quality, human review items
- "şunu kesin yap" demez, araştırma bulgularını sunar

→ **research_hq_surface.py'ye SituationReport ekleme.**

### 4.12 IntelligenceHealth (YENİ — operational metrics)
Mevcut: yok
J5'e **intelligence health** gerekli:
- data health, agent health, research throughput, validation throughput, failure rate, stale research, unresolved conflicts, claim instability, drift alerts, memory growth, queue depth, provider health, budget usage
- Trading performance dashboard'a dönüştürme

→ **Yeni metrics collector.**

### 4.13 SearchableKnowledge (YENİ — research_memory_query genişletmesi)
Mevcut:
- `research_memory_query_adapter_v1.py` → memory query

J5'e **searchable knowledge** gerekli:
- symbol, timeframe, regime, setup, agent, hypothesis, claim, date, failure, evidence, experiment

→ **research_memory_query_adapter_v1.py'yi genişlet.**

### 4.14 ResearchExperimentRegistry (YENİ — research_intelligence_engine genişletmesi)
Mevcut:
- `research_intelligence_engine.py` → register_experiment, run_experiment
- `research_intelligence_model.py` → ExperimentRegistry, ExperimentStatus, Result

J5'e **experiment registry gelişme** gerekli:
- experiment_id, hypothesis_id, config_hash, dataset, cutoff, features, methodology, baseline, challenger, result, status, provenance
- Aynı config tekrar → duplicate experiment engelle veya cached result kullan

→ **research_intelligence_engine.py'yi genişlet, yeni registry yafaplasticçı.**

### 4.15 ChampionChallenger (Mevcut — research_intelligence_engine.py)
Mevcut:
- `research_intelligence_engine.py` → ChampionChallenger (zaten var!)
- `research_intelligence_model.py` → WeightProposal, WeightProposalStatus

J5'e **champion/challenger** gerekli:
- New candidate: CHALLENGER
- Current baseline: CHAMPION
- Comparison: validation, calibration, stability, sample size, regime robustness, temporal robustness, fallback rate, complexity
- **AUTO PROMOTION YOK** — J5'te dahil

→ **Mevcut ChampionChallenger'ı J5 kurallarına göre kullan (no auto-promotion).**

### 4.16 AgentPerformanceDrift (YENİ — adaptive_team_selector genişletmesi)
Mevcut:
- `adaptive_team_selector.py` → AgentReliability (direction_agreement, outcome_correlation, target_hit_rate, invalidation_rate, avg_realized_r, median_realized_r, sample_size, stability_score, temporal_stability)

J5'e **agent performance drift** gerekli:
- historical reliability, recent reliability, evidence quality, failure rate, contradiction rate, latency, unavailable rate
- Recent degradation → RESEARCH_ROUTING sinyali (agent silinmez/disable edilmez, human review)

→ **adaptive_team_selector.py'yi genişlet. AgentReliability'yi drift score ile augment et.**

### 4.17 StrategyFamilyDrift (YENİ — opportunity_model/research_intelligence genişletmesi)
Mevcut:
- `opportunity_model.py` → strategy_families, strategy_count, independent_families
- `research_intelligence_model.py` → ReliabilityProfile (profile_type: agent | strategy | strategy_family)

J5'e **strategy family drift** gerekli:
- regime, timeframe, symbol, evidence, validation, historical stability, failure rate
- Otomatik PROMOTION YOK — sadece RESEARCH STATUS

→ **ReliabilityProfile'ı strategy family bazında augment et.**

### 4.18 MultipleTestingAwareness (YENİ — claim/experiment metadata)
Mevcut: yok
J5'e **multiple testing awareness** gerekli:
-çok sayıda hypothesis test edildiğinde multiple testing riski görünür
- Claim confidence otomatik şişirilmez
- EXPLORATORY vs CONFIRMATORY ayrımı
- Exploratory result: production truth değildir

→ **Hypothesis/Claim'a testing_mode: EXPLORATORY | CONFIRMATORY ekleme.**

---

## 5. Sıralama: Ne Yeniden Yazılmıyor, Ne Geniştiliyor

### 5.1 Mevcut Sistemleri Kullan + Genişlet (J5 Bu Yoldan Gider)

| Mevcut Sistem | J5 Ne Yapıyor? |
|---|---|
| `research_intelligence_model.py` (Claim, Hypothesis, Experiment, ResearchMemory, FailurePattern, Counterexample) | Genişletilir — temporal decay, claim stability measurement, regime transition memory, searchable metadata |
| `research_intelligence_engine.py` (build_observation, build_hypothesis, register_experiment, run_experiment, ChampionChallenger) | Aktif kullanılır — claim stability score hesabı, distribution drift, multiple testing awareness eklenir |
| `autonomous_research_loop.py` (LoopState, AutonomousResearchRun, AutonomousResearchLoop) | Genişletilir — ContinuousLoop ile sarmalar, event-driven trigger, cooldown, budget |
| `market_observation.py` (MarketObservation, ObservationBundle, DataQuality) | Genişletilir — change detection katmanı |
| `opportunity_model.py` (Opportunity, SetupCandidate, ResearchBackedSetup) | Genişletilir — opportunity recurrence, setup memory |
| `research_hq_surface.py` (HumanReview, ResearchArtifact, ProvenanceChain) | Genişletilir — SituationReport |
| `adaptive_team_selector.py` (AgentReliability, AdaptiveTeamSelector) | Genişletilir — agent performance drift, strategy family drift |
| `research_memory_query_adapter_v1.py` | Genişletilir — searchable knowledge |
| `persistence.py` (PersistenceLayer) | Genişletilir — yeni intelligence tabloları |
| `research_priority_engine.py` (ResearchPriorityEngine) | Kullanılır — information value measurement eklenir |
| `agent_contract.py` (AgentResult, Evidence, Claim, FeatureSnapshot) | Kullanılır — özel değişiklik yok |
| `research_audit.py` (AuditLog, ResearchAuditEvent) | Kullanılır — IntelligenceState değişimleri audit edilir |

### 5.2 Yeni Component'ler (Sadece Eksik olanlar)

1. **`intelligence_state.py`** — IntelligenceState enum + IntelligenceStateManager + state transition audit
2. **`continuous_loop.py`** — ContinuousLoop (AutonomousResearchLoop'u sarar), event-driven trigger, cooldown, budget
3. **`change_detection_engine.py`** — ChangeDetectionEngine + ChangeDetectionEvent
4. **`regime_transition_memory.py`** — RegimeTransitionMemory (ResearchMemory genişlemesi, ayrı manage edilir)
5. **`distribution_drift_engine.py`** — DistributionDriftEngine + DriftDetectionEvent
6. **`temporal_decay.py`** — TemporalDecay (evidence/claim score hesaplayan util)
7. **`intelligence_health.py`** — IntelligenceHealth metrics collector
8. **`situation_report.py`** — SituationReport model + builder (research_hq_surface ile birlikte)
9. **`searchable_memory.py`** — SearchableMemory (research_memory_query_adapter_v1 genişlemesi)
10. **`research_experiment_registry.py`** — genişletilmiş experiment registry (research_intelligence_engine genişlemesi)
11. **`multiple_testing_awareness.py`** — EXPLORATORY/CONFIRMATORY ayrım + multiple testing risk göstergesi
12. **`counterexample_engine.py`** — Counterexample ara+ bulma + claim weakening (research_intelligence_model kullanır)

### 5.3 Asla Yapılmayacak (J5 Boundaries)

- Yeni Brain — brain_* script'leri untouched
- Yeni AgentRuntime/AgentRouter — untouched
- Yeni OpportunityEngine — opportunity_model.py genişletilir
- Yeni ValidationEngine — research_validation_engine.py aktif kullanılır
- Yeni PersistenceLayer — persistence.py genişletilir
- Yeni MemorySystem — research_intelligence_model.py genişletilir
- Yeni ClaimSystem — research_intelligence_model.py Claim'ı genişletilir
- Trading execution ekranı — ASLA
- Broker/order/auto trade — ASLA

---

## 6. J4 → J5 Mapping (Ne Ottoman?)

### J4 Loop (mevcut)
```
OBSERVE → DETECT → PRIORITIZE → PLAN → DELEGATE → RESEARCH
→ COLLABORATE → CRITIC → SYNTHESIZE → VALIDATE → REMEMBER → LEARN
→ REPORT → WAIT → OBSERVE
```

### J5 Loop (genişletilmiş)
```
OBSERVE → DETECT → PRIORITIZE → RESEARCH → COLLABORATE → CRITIC
→ SYNTHESIZE → VALIDATE → REMEMBER → COMPARE WITH PAST
→ DETECT CHANGE → FORM HYPOTHESES → RUN EXPERIMENTS → LEARN
→ UPDATE RESEARCH STATE → MONITOR → REPEAT
```

Farklar:
1. **COMPARE WITH PAST** — regime transition memory, failure memory, counterexample
2. **DETECT CHANGE** — change detection engine, distribution drift
3. **FORM HYPOTHESES → RUN EXPERIMENTS** — champion/challenger, research experiment registry
4. **LEARN → UPDATE RESEARCH STATE** — claim stability, temporal decay, adaptive research
5. **MONITOR → REPEAT** — ContinuousLoop, event-driven triggers, cooldown

---

## 7. Eksiklikler (J5'te Doldurulacak)

1. ** IntelligenceState** — yok (LoopState cycle-scoped)
2. ** ChangeDetection** — yok (market_observation sadece data quality)
3. ** RegimeTransitionMemory** — yok (ResearchMemory sahip ama transition specialization yok)
4. ** DistributionDrift** — yok
5. ** FailureMemory (active)** — FailurePattern defined ama active engine yok
6. ** CounterexampleEngine (active)** — Counterexample enum defined ama active engine yok
7. ** ClaimStability measurement (active)** — Claim.stability var ama calculation logic yok
8. ** TemporalDecay** — yok
9. ** AdaptiveResearch (information value)** — ResearchPriorityEngine var ama information value yok
10. ** ResearchBudget (active)** — max_cycles var ama comprehensive budget yok
11. ** Cooldown** — yok
12. ** EventDrivenTriggers** — yok (trigger: "manual" string)
13. ** HumanResearchRequest pipeline** — yok (human review var ama request→plan→agents→critic→synthesis→report pipeline yok)
14. ** SituationReport** — yok
15. ** IntelligenceHealth** — yok
16. ** SearchableKnowledge (active)** — memory query var ama full search yok
17. ** ExperimentRegistry (active)** — register_experiment var ama deduplicated, cached result yok
18. ** ChampionChallenger (active)** — var ama no-auto-promotion rules hayata geçmeli
19. ** AgentPerformanceDrift** — AgentReliability var ama drift detection yok
20. ** StrategyFamilyDrift** — ReliabilityProfile var ama family bazında drift yok
21. ** MultipleTestingAwareness** — yok
22. ** DataDrift/MarketDrift/ModelDrift/ResearchDrift ayrımı** — yok
23. ** OpportunityRecurrence (active)** — SimilarityMatch var ama active recurrence engine yok

---

## 8. IDEMPOTENT/REGRESSION KORLARI

- Mevcut tabloları silme
- Mevcut Claim/Hypothesis/Experiment modelini overwrite etme
- Mevcut AutonomousResearchLoop'u silme
- Mevcut brain_research_agent_v4.py'yi dokunma
- Mevcut persistence tablolarına overwrite etme
- Mevcut research_validation_engine.py'yi silme
- Mevcut opportunity_model.py'yi overwrite etme
- Mevcut research_intelligence_model.py'yi overwrite etme — sadece genişlet

---

## 9. J5 Implementation Öncesi Kararlar

### 9.1 Claim Lifecycle
→ `research_intelligence_model.py` Claim'ini kullan. Stability score calculation eklenir.
→ ClaimStatus: UNTESTED → TESTED → SUPPORTED → (WEAKENED | UNSTABLE) → REJECTED
→ WEAKENED: counterexample/weak evidence/chart come
→ UNSTABLE: contradiction/instability

### 9.2 Memory
→ `research_intelligence_model.py` ResearchMemory'yi kullan.
→ Yeni memory_type'lar: REGIME_TRANSITION, FAILURE_PATTERN, COUNTEREXAMPLE, DECAY_RECORD
→ Active memory engine: research_intelligence_engine.py'yi genişlet

### 9.3 Change Detection
→ `market_observation.py` ObservationBundle üzerine change detection katmanı
→ ChangeDetectionEngine: regime, volatility, momentum, trend, liquidity, structure, feature distribution, opportunity frequency, setup distribution, behavior drift, evidence drift

### 9.4 Drift
→ DistributionDriftEngine: quality, regime, setup, strategy family, feature, outcome, duration, RR, volatility, evidence distributions
→ 4 drift türü ayrımı: DATA_DRIFT / MARKET_DRIFT / MODEL_DRIFT / RESEARCH_DRIFT

### 9.5 Continuous Operation
→ `autonomous_research_loop.py` üzerine ContinuousLoop katmanı
→ Event-driven triggers + cooldown + budget

### 9.6 Human Research Request
→ `research_hq_surface.py` HumanReview üzerine request pipeline
→ Human Request → ResearchPlan → Agents → Critic → Synthesis → Report (mevcut AutonomousResearchLoop engine'lerini kullanır)

---

## 10. PROHIBITIONS (J5 için de geçerli J4 prohibitions + yeni)

KESİNELIŞLE:
- broker integration
- live trading
- order execution
- auto buy/sell
- real-money action
- automatic strategy promotion
- automatic weight deployment
- fake production data
- future leakage
- lookahead
- duplicate engines (yeni Brain, yeni Memory, yeni Validation, yeni Opportunity, yeni Claim)
- duplicate persistence
- unlimited agents / infinite research loop / infinite critic loop
- hidden decision logic
- unsupported prediction
- guaranteed performance claims
- stability/adaptation'ı trading decision'a dönüştürme
- claim stability'yi win probability'ya dönüştürme
- temporal decay'ı position sizing'a dönüştürme
- information value'ı profit prediction'a dönüştürme

---

## 11. AZIZBUSINESS_PHASE_J5_ARCHITECTURE_AUDIT.md — OLUŞTURULDU

Bu dosya oluşturuldu. Implementation'a geçilebilir.

**Audit sonucu:** Mevcut sistemler J5 için güçlü altyapı. Tekrar Yazılacak hiçbir core engine yok. Eksik olanlar (intelligence state, change detection, drift, failure memory, claim stability, temporal decay, continuous loop, situation report, intelligence health) yeni küçük component'ler veya mevcut sistemlerin genişletmesi olarak eklenir.
