# MARKETHQ — AGENTIC HQ ARCHITECTURE AUDIT

**Date:** 2026-09-16
**Status:** AUDIT COMPLETE — Ready for Phase B (Agent Contract)
**Author:** Lead Engineer Audit

---

## 1. MEVCUT MARKET HQ ARCHITECTURE

MarketHQ layered architecture (top → bottom):

```
┌─────────────────────────────────────────────────────┐
│                  UI / DASHBOARD                      │
│          frontend.py / dashboard_backend_v2_3        │
│          dashboard_control_center_v10                │
├─────────────────────────────────────────────────────┤
│                  MAIN PIPELINE                       │
│            main.py (orchestrator)                    │
│     news → turkey → market_data → analyst           │
│     performance → strategy_lab → fin_sys            │
├─────────────────────────────────────────────────────┤
│                  RUNTIME STATE                       │
│           runtime_state.py                           │
│     agent status tracking, task queue               │
├─────────────────────────────────────────────────────┤
│                  DATA LAYER                          │
│         market_data_pipeline.py                      │
│         yfinance → OHLCV → market_datasets           │
│         SQLite: market_hq.db                         │
├─────────────────────────────────────────────────────┤
│                  ENGINE LAYER                        │
│  ┌──────────────────────────────────────────────┐   │
│  │ Signal Engine (signal_engine.py)             │   │
│  │  - SMA/EMA/RSI/MACD/BB/ATR/VolumeRatio       │   │
│  │  - DEFAULT_CONFIG, add_indicators             │   │
│  │  - generate_signal(), calculate_risk_levels() │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Setup Engine V1 (setup_engine_v1.py)         │   │
│  │  - build_setup() → raw setup dict            │   │
│  │  - detect_regime() → multi-factor regime     │   │
│  │  - _adx_like(), _trend_strength()            │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Research Setup Engine (research_setup_engine │   │
│  │  _engine.py)                                 │   │
│  │  - build_research_setup() → SetupModel       │   │
│  │  - WHY panel generation                      │   │
│  │  - AgentSpace evidence + test card           │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Quality Engine V4 (setup_quality_engine_v4)  │   │
│  │  - 15 dimensions, multiplicative scoring     │   │
│  │  - entry_quality, inv_clarity, risk_rr, etc. │   │
│  │  - regime_weighted_quality                   │   │
│  ├──────────────────────────────────────────────┤   │
│  │ SMC Structure V1 (smc_structure_v1.py)       │   │
│  │  - find_swings(), structure_events()         │   │
│  │  - BOS/CHoCH detection, BOS/CHoCH signals    │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Backtest Engine (backtest_engine.py)         │   │
│  │  - Signal → OHLCV simulation                 │   │
│  │  - Portfolio metrics                         │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Setup Backtest (setup_backtest_engine.py)    │   │
│  │  - Rolling-window setup generation           │   │
│  │  - Bar-by-bar execution simulation           │   │
│  │  - Quality correlation, outcome recording    │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Walk-Forward Engine (walk_forward_engine.py) │   │
│  │  - train/validation/test splits              │   │
│  │  - Strategy knowledge base                   │   │
│  ├──────────────────────────────────────────────┤   │
│  │ Regime Filter (regime_filter.py)             │   │
│  │  - regime × strategy matrix                  │   │
│  │  - ALLOW / PENALTY / CONSERVATIVE            │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│                  OBJECT MODEL                        │
│          setup_object_model.py                       │
│  - SetupModel, MarketInfo, TimeframeInfo            │
│  - RegimeInfo, BiasInfo, StructureInfo              │
│  - LiquidityInfo, EntryZone, Confirmation           │
│  - InvalidationLevel, TargetLevel, Targets          │
│  - RiskReward, Evidence, HistoricalValidation       │
│  - QualityScore, Reasoning, InvalidationConditions  │
│  - LearningMetadata, Outcome                        │
├─────────────────────────────────────────────────────┤
│                  DATABASE (SQLite)                   │
│  market_hq.db                                       │
│  - market_datasets (100 rows: 45 active, 55 no_data)│
│  - market_dataset_versions                          │
│  - setup_outcomes (12,651 records)                  │
│  - brain_* tables (claims, observations, edges,     │
│    nodes, evidence, learning_events, weight_versions,│
│    walkforward_splits, research_queue, etc.)        │
│  - research_experiments, research_results,          │
│    research_artifacts, research_memory              │
│  - experiment_results                               │
│  - knowledge_items, knowledge_sources               │
│  - news, analyses, targets                          │
│  - visual_assets                                    │
└─────────────────────────────────────────────────────┘
```

---

## 2. MEVCUT ENGINE'LER

### 2.1 Signal Engine (signal_engine.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/signal_engine.py` |
| Girdi | OHLCV DataFrame |
| Çıktı | BUY / SELL / WAIT sinyali + indikatörler |
| Indikatörler | SMA, EMA, RSI, MACD, Bollinger, ATR, Volume Ratio |
| DB Tablo | — |
| Bağımlılıklar | — (temel, hiçbir engine'e bağımlı değil) |
| Kullanım | setup_engine_v1, backtest_engine, setup_backtest_engine |

### 2.2 Setup Engine V1 (setup_engine_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/setup_engine_v1.py` |
| Girdi | OHLCV DataFrame + signal_engine config |
| Çıktı | setup dict (entry_zone, invalidation, target, regime) |
| DB Tablo | setup_outcomes (indirect) |
| Bağımlılıklar | signal_engine, strategy_registry_v1 |
| Kullanım | research_setup_engine, setup_backtest_engine |

### 2.3 Research Setup Engine (research_setup_engine.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/research_setup_engine.py` |
| Girdi | sembol + timeframe + OHLCV DataFrame |
| Çıktı | SetupModel + WHY paneli (markdown) |
| DB Tablo | setup_outcomes |
| Bağımlılıklar | setup_engine_v1, strategy_registry_v1, signal_engine, setup_quality_engine_v2, regime_filter, setup_outcome_tracker |
| Kullanım | setup_backtest_engine, research pipeline |

### 2.4 Quality Engine V4 (setup_quality_engine_v4.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/setup_quality_engine_v4.py` |
| Girdi | SetupModel |
| Çıktı | QualityScore (0-1 + breakdown + confidence + outcome_correlation) |
| DB Tablo | setup_outcomes (quality_score) |
| Bağımlılıklar | setup_object_model |
| Kullanım | research_setup_engine, setup_backtest_engine |
| Durum | r=0.16 outcome correlation — research signal, NOT production probability |

### 2.5 SMC Structure V1 (smc_structure_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/smc_structure_v1.py` |
| Girdi | OHLCV DataFrame + ATR |
| Çıktı | Swing points + structure events (BOS, CHoCH) |
| DB Tablo | — (no persistence) |
| Bağımlılıklar | signal_engine (add_indicators) |
| Kullanım | strategy_registry_v1, research_setup_engine |
| Sorun | CHoCH/BOS lookahead risk — kontrol edilmeli |

### 2.6 Setup Outcome Tracker (setup_outcome_tracker.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/setup_outcome_tracker.py` |
| Girdi | setup outcome data |
| Çıktı | DB kaydı (setup_outcomes) |
| DB Tablo | setup_outcomes (12,651 records) |
| Bağımlılıklar | — |
| Kullanım | setup_backtest_engine, research_setup_engine |

### 2.7 Backtest Engine (backtest_engine.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/backtest_engine.py` |
| Girdi | OHLCV DataFrame + signal config |
| Çıktı | Backtest results (metrics, trades) |
| DB Tablo | — |
| Bağımlılıklar | signal_engine, market_data_agent |
| Kullanım | strategy_research_pipeline |

### 2.8 Setup Backtest Engine (setup_backtest_engine.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/setup_backtest_engine.py` |
| Girdi | OHLCV DataFrame |
| Çıktı | TradeResult + PortfolioMetrics + Quality correlation |
| DB Tablo | setup_outcomes |
| Bağımlılıklar | signal_engine, research_setup_engine, setup_quality_engine_v2 |
| Kullanım | test_backtest_engine.py |

### 2.9 Walk-Forward Engine (walk_forward_engine.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/walk_forward_engine.py` |
| Girdi | OHLCV DataFrame + strategy |
| Çıktı | Walk-forward results (train/val/test metrics) |
| DB Tablo | brain_walkforward_splits |
| Bağımlılıklar | backtest_engine, market_data_agent, strategy_knowledge_base |
| Kullanım | strategy research pipeline |

### 2.10 Regime Filter (regime_filter.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/regime_filter.py` |
| Girdi | setup_outcomes DB data |
| Çıktı | RegimeStrategyDecision (ALLOW/PENALTY/CONSERVATIVE) |
| DB Tablo | setup_outcomes |
| Bağımlılıklar | — |
| Kullanım | research_setup_engine (apply_regime_filter) |

### 2.11 Strategy Registry V1 (strategy_registry_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/strategy_registry_v1.py` |
| Girdi | OHLCV DataFrame + signal_engine config |
| Çıktı | Strategy signals (LONG/SHORT/NEUTRAL) per strategy |
| DB Tablo | — |
| Bağımlılıklar | signal_engine, smc_structure_v1, opening_range_v1 |
| Stratejiler | 12 strategies across 7 families (trend, mean_reversion, breakout, volume, relative, structure) |
| Kullanım | setup_engine_v1, research_setup_engine |

---

## 3. BRAIN / LEARNING SİSTEMİ

### 3.1 Brain Research Agent V4 (agents/brain_research_agent_v4.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/brain_research_agent_v4.py` |
| Görev | Research queue → knowledge ingest → observation bridge → evidence review → brain update |
| DB Tablo | brain_research_queue, brain_nodes, brain_edges, brain_claims, brain_observations, brain_evidence, brain_learning_events, brain_weight_versions, brain_walkforward_splits |
| Durum | V4.5 (ENGINE_VERSION) |
| Bağımlılıklar | brain_claim_engine_v2, brain_observation_engine_v2, brain_consolidation_preview_v1, brain_contradiction_engine_v1, brain_evaluation_engine_v1 |

### 3.2 Brain Observation Engine V2 (agents/brain_observation_engine_v2.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/brain_observation_engine_v2.py` |
| Görev | Observation processing, signal evaluation, status management |
| V2 → V3 farkı | V3 mevcut (brain_research_observation_bridge_v3.py) |

### 3.3 Brain Claim Engine V2 (agents/brain_claim_engine_v2.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/brain_claim_engine_v2.py` |
| Görev | Claim validation, traceability, evidence linking |

### 3.4 Brain Evaluation Engine V1 (agents/brain_evaluation_engine_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/brain_evaluation_engine_v1.py` |
| Görev | Claim evaluation, score computation, status updates |

### 3.5 Brain Learning Pipeline (brain_learning_pipeline.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/brain_learning_pipeline.py` |
| Görev | Strategy weight learning, adaptive weighting |
| DB Tablo | brain_weight_versions, brain_walkforward_splits |

### 3.6 Brain Orchestrator V1 (agents/brain_orchestrator_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/brain_orchestrator_v1.py` |
| Görev | Coordinates brain pipeline stages |

---

## 4. AGENT / WORKER SİSTEMİ

### 4.1 Agent Runtime V1 (agents/agent_runtime_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/agent_runtime_v1.py` |
| Teknoloji | OpenAI Agents SDK |
| Görev | Thin adapter — wraps existing MarketHQ research stack |
| Araçlar | market_hq_system_status, market_hq_brain_pipeline_info, market_hq_research_execution |
| Model | MARKETHQ_AGENT_MODEL env (default: gpt-5.6-luna) |
| Kısıtlama | research_only, no live_order_execution |

### 4.2 Market Data Agent (agents/market_data_agent.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/market_data_agent.py` |
| Semboller | 30 BIST + 30 US + 5 INDEX + 2 SPECIAL = 67 sembol |
| Getirdi | Market records, OHLCV data, signal data |
| Not | 20 sembol setup_outcomes'dan keşfedildi (fark liste!) |

### 4.3 Analyst Agent (agents/analyst_agent.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/analyst_agent.py` |
| Görev | News analysis via OpenAI |
| Semboller | 25 instrument (BIST + US + indices + yield + FX) |

### 4.4 News Agent (agents/news_agent.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/news_agent.py` |
| Görev | News preparation |

### 4.5 Turkey Agent (agents/turkey_agent.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/turkey_agent.py` |
| Görev | Turkey-specific news + market data |

### 4.6 Research Execution Adapter (agents/research_execution_adapter_v1.py)
| Alan | Detay |
|------|-------|
| Dosya | `/opt/markethq/agents/research_execution_adapter_v1.py` |
| Görev | Research experiment execution router |
| Kısıtlama | research-only, no live trading |

### 4.7 Other Agent Files
| Dosya | Amaç |
|-------|------|
| brain_research_agent_v4.py | Research agent (73KB, main brain engine) |
| brain_research_observation_bridge_v3.py | Observation bridge (32KB) |
| brain_consolidation_preview_v1.py | Consolidation preview |
| brain_contradiction_engine_v1.py | Contradiction detection |
| brain_evaluation_engine_v1.py | Claim evaluation |
| brain_claim_engine_v2.py | Claim management |
| brain_observation_engine_v2.py | Observation processing |
| brain_importer_v1.py / v3.py | Data import |
| brain_learning_event_engine_v1.py | Learning events |
| brain_research_loop_engine_v2.py | Research loop |
| brain_rule_promotion_engine_v1.py | Rule promotion |
| brain_rule_validation_engine_v1.py | Rule validation |
| brain_research_queue_hygiene_v1/v2.py | Queue management |
| brain_research_evidence_flag_repair_v1.py | Evidence flag repair |
| brain_research_evidence_update_v1/v2.py | Evidence updates |
| brain_research_evidence_review_v4.py | Evidence review |
| brain_research_agent_diagnostic_v4.py | Diagnostics |
| brain_orphan_focus/link_diagnostic_v1.py | Orphan diagnostics |
| brain_health_check_v1.py | Health checks |
| brain_graph_consolidation_diagnostic_v1.py | Graph diagnostics |
| brain_research_recovery_engine_v1.py | Recovery |
| brain_research_queue_enrichment_v2.py | Queue enrichment |
| brain_research_observation_bridge_diagnostic_v1.py | Bridge diagnostics |
| brain_safe_orphan_symbol_linker_v1.py | Orphan linking |
| brain_update_engine_v1.py | Brain updates |
| brain_schema_v2.py | Schema definition |
| method_ai_verifier.py | Method verification |
| method_evidence_auditor.py | Evidence auditing |
| method_evidence_judge.py | Evidence judgment |
| method_gap_analyzer.py | Gap analysis |
| method_registry.py / cleaner | Method registry |
| method_specification_engine.py / v4 | Specification engine |
| method_specification_consolidator_v3.py | Specification consolidation |
| method_reproducibility_classifier.py | Reproducibility |
| method_validator.py | Method validation |
| specification_quality_gate_v2.py | Quality gate |
| systematic_trading_optimizer_adapter_v1.py | Optimization adapter |
| paper_trading_adapter_v1.py | Paper trading adapter |
| paper_evidence_aggregator_v1/v2_3.py | Evidence aggregation |
| paper_evidence_brain_bridge_v1.py | Brain bridge |
| paper_feedback_learning_engine_v1.py | Feedback learning |
| independent_strategy_evidence_runner_v1.py | Independent evidence |
| independent_evidence_knowledge_bridge_v1.py | Knowledge bridge |
| fresh_independent_research_engine_v1_1.py | Fresh research |
| fresh_independent_evidence_knowledge_bridge_v1_1.py | Evidence bridge |
| knowledge_extractor.py | Knowledge extraction |
| learning_engine.py | Learning engine |
| performance_tracker.py | Performance tracking |
| self_healing_engine_v1.py | Self-healing |
| vectorbt_engine_v1.py | VectorBT backtest |
| python brain_schema_v2.py | Brain schema |
| research_execution_adapter_v1.py | Research execution adapter (root) |
| research_memory_adapter_v1.py | Research memory adapter |
| research_storage_adapter_v1.py | Research storage adapter |
| strategy_lab.py | Strategy lab |
| strategy_lab_runner.py | Strategy lab runner |
| strategy_evolution.py / v1.py | Strategy evolution |
| strategy_evolution_v1.py | Strategy evolution v1 |
| strategy_extractor.py | Strategy extraction |
| strategy_knowledge_base.py | Strategy knowledge base |
| strategy_optimizer.py | Strategy optimizer |
| strategy_scoreboard_v1.py | Strategy scoreboard |
| strategy_selection_engine_v2.py | Strategy selection |
| strategy_validation_engine.py | Strategy validation |
| strategy_backtest_runner.py | Strategy backtest runner |
| strategy_candidate_diagnostic.py | Candidate diagnostics |
| strategy_research_pipeline.py / v5 / v6.py | Strategy research pipeline |
| research_ingestion_engine.py | Research ingestion |
| research_memory_query_adapter_v1.py | Memory query adapter |
| research_storage_schema_v1.py | Storage schema |
| multi_symbol_paper_research_runner_v1.py | Multi-symbol runner |
| final_research_decision_engine_v1_1 / CLEAN_V1 / v3.py | Decision engine |
| automation_controller_v2.py / v5.py | Automation controllers |
| automation_service_v2.py | Automation service |
| dashboard_backend_v2_3.py | Dashboard backend |
| dashboard_control_center_v10.py | Control center |
| dashboard_ui_v6_2.py | Dashboard UI |
| markethq_manager_v1.py | MarketHQ manager |
| data_expansion_pipeline.py | Data expansion (Phases 1-7) |
| data_expansion_phases9_12.py | Data expansion (Phases 9-12) |
| data_quality_fixes.py | Data quality fixes |
| diagnostic_research.py | Diagnostic research |
| evidence_consolidation_engine_v1_1.py | Evidence consolidation |
| feature_analysis.py | Feature availability analysis |
| learning_feedback_engine_v1.py | Learning feedback |
| learning_ranking_loop_v1.py | Learning ranking loop |
| main.py | Main entry point |
| market_data_pipeline.py | OHLCV pipeline |
| opening_range_v1.py | Opening range |
| pair_spread_v1.py | Pair spread |
| paper_trading_engine_v1.py | Paper trading engine |
| runtime_state.py | Runtime state |
| runtime_state_reconciler_v1.py | Runtime reconciler |
| schema_freeze_v1_1.py | Schema freeze |
| self_healing_engine_v1.py | Self-healing |
| setup_adaptive_brain.py | Adaptive brain |
| setup_feedback_v1.py | Setup feedback |
| setup_validation_v1.py | Setup validation |
| signal_engine_diagnostic.py | Signal engine diagnostics |
| video_chart_engine.py | Video chart engine |
| youtube_discovery.py | YouTube discovery |
| youtube_pilot_manager.py | YouTube pilot |
| youtube_queue.py | YouTube queue |
| youtube_thumbnail_vision.py | YouTube thumbnail |
| youtube_transcript_engine.py | YouTube transcript engine |
| youtube_transcript_processor.py | YouTube transcript processor |
| youtube_video_classifier.py | YouTube classifier |
| visual_analysis_queue.py | Visual analysis queue |
| visual_source_adapter.py / resolver.py | Visual source |
| overfit_validation_v1.py | Overfit validation |
| strategy_adapter.py | Strategy adapter |

---

## 5. DATA → FEATURE → REGIME → STRUCTURE → SETUP → OUTCOME → BRAIN ZİNCİRİ

```
yfinance OHLCV
    │
    ▼
market_data_pipeline.py ──→ market_datasets (45 active, 55 no_data)
    │                              (100 total records)
    │                              20 symbols × 5 timeframes
    ▼
signal_engine.py (add_indicators)
    │
    ├── SMA_FAST, SMA_SLOW
    ├── EMA_FAST, EMA_SLOW
    ├── RSI
    ├── MACD
    ├── Bollinger Bands
    ├── ATR
    ├── Volume Ratio
    └── ADX (from data_expansion_pipeline.py)
    │
    ▼
setup_engine_v1.py / research_setup_engine.py
    │
    ├── detect_regime() ──→ RegimeInfo (UPTREND_STRONG/WEAK, DOWNTREND_STRONG/WEAK, RANGE_LOW/HIGH_VOL, EXPANDING_VOLATILITY)
    ├── detect_bias() ──→ BiasInfo (LONG/SHORT/NEUTRAL)
    ├── structure detection (smc_structure_v1.py) ──→ StructureInfo (BOS/CHoCH, swings) ── structure_type EMPTY in ALL records
    ├── liquidity detection ──→ LiquidityInfo ── liquidity_side EMPTY in ALL records
    ├── entry zone, invalidation, targets
    ├── strategy agreement (strategy_registry_v1.py)
    └── SetupModel
    │
    ▼
setup_quality_engine_v4.py
    │
    ├── 15 dimensions → QualityScore (0-1)
    ├── regime_weighted_quality
    └── r=0.16 correlation with outcome (research signal only)
    │
    ▼
setup_backtest_engine.py / backtest_engine.py
    │
    ├── setup_outcomes (12,651 records)
    │   ├── outcome: hit_target (5,572) / hit_invalidation (7,076) / open (3)
    │   ├── max_favorable: 2 records ONLY
    │   ├── max_adverse: 2 records ONLY
    │   ├── structure_type: 0 records (ALL empty)
    │   ├── liquidity_side: 0 records (ALL empty)
    │   ├── adx_value: 11,516 records
    │   └── atr_pct: 4,251 records (39.7%)
    │
    ▼
walk_forward_engine.py
    │
    ├── brain_walkforward_splits
    ├── brain_weight_versions
    └── brain_strategy_learning_rankings
    │
    ▼
brain_research_agent_v4.py
    │
    ├── brain_claims, brain_observations, brain_edges, brain_nodes
    ├── brain_learning_events
    ├── brain_evidence, brain_evidence_consolidations
    ├── brain_contradictions
    ├── brain_research_queue
    └── brain_research_strategy_evidence_reviews
```

---

## 6. MEVCUT 12 FAZIN OLUŞTURDUĞU PARÇALAR

| Faz | Parça | Mevcut Dosya |
|-----|-------|-------------|
| Phase 1 | Multi-asset/multi-timeframe OHLCV | market_data_pipeline.py + data_expansion_pipeline.py |
| Phase 2 | Volume pipeline | data_expansion_pipeline.py (volume_ratio) |
| Phase 3 | Outcome bar tracking | setup_outcome_tracker.py + data_expansion_pipeline.py |
| Phase 4 | Structure engine integration | smc_structure_v1.py |
| Phase 5 | ADX | data_expansion_pipeline.py (ADX calculation) |
| Phase 6 | Feature availability matrix V2 | feature_analysis.py |
| Phase 7 | Dataset validation | data_expansion_pipeline.py |
| Phase 9 | Research-only validation | data_expansion_phases9_12.py |
| Phase 10 | OOS preparation | data_expansion_phases9_12.py |
| Phase 11 | Testler | test_backtest_engine.py + test_learning_infrastructure.py |
| Phase 12 | Final report | data_expansion_phases9_12.py |

---

## 7. AGENTIC HQ İÇİN KULLANILABİLECEK PARÇALAR

| Mevcut Parça | Agentic HQ Kullanımı |
|-------------|---------------------|
| market_data_pipeline.py | Market Monitor Agent — data ingestion + freshness |
| signal_engine.py | Shared feature snapshot — indicators for all agents |
| setup_engine_v1.py | Setup Agent — regime + bias detection |
| research_setup_engine.py | Setup Agent — rich SetupModel + WHY panel |
| setup_quality_engine_v4.py | Quality/Risk Agent — 15-dimension scoring |
| smc_structure_v1.py | Structure Agent — BOS/CHoCH detection |
| regime_filter.py | Regime Agent — regime × strategy matrix |
| strategy_registry_v1.py | Strategy Research Agents — 12 strategies across families |
| backtest_engine.py | Historical Evidence Agent — backtest simulation |
| setup_backtest_engine.py | Historical Evidence Agent — setup-level backtest |
| walk_forward_engine.py | OOS validation |
| setup_outcome_tracker.py | Historical Evidence — outcome storage |
| brain_research_agent_v4.py | Brain Learning + Claim/Evidence system |
| brain_observation_engine_v2.py | Brain — observation processing |
| brain_claim_engine_v2.py | Brain — claim management |
| brain_evaluation_engine_v1.py | Brain — claim evaluation |
| brain_learning_pipeline.py | Brain — weight learning |
| agent_runtime_v1.py | Agent contract + SDK adapter |
| market_data_agent.py | Market Data Agent (67 symbols) |
| analyst_agent.py | Analyst Agent (news) |
| research_execution_adapter_v1.py | Research execution routing |
| setup_object_model.py | Structured data model (SetupModel, QualityScore, etc.) |
| runtime_state.py | Agent status tracking |
| automation_controller_v2.py | Automation orchestration |

---

## 8. EKSİK PARÇALAR

| # | Eksik Parça | Önem | Açıklama |
|---|------------|------|----------|
| 1 | Agent Contract / AgentResult | HIGH | Ortak structured output yok — agentlar farklı format üretiyor |
| 2 | Opportunity Engine | HIGH | Opportunity lifecycle yok — DETECTED → UNDER_REVIEW → VALIDATED → INVALIDATED → EXPIRED → ARCHIVED |
| 3 | Opportunity → Setup bridge | HIGH | Opportunity agent → Setup synthesis pipeline yok |
| 4 | Critic Agent | HIGH | Hiçbiri yok — objections, structured feedback |
| 5 | HQ Synthesis Agent | HIGH | Bütün agent sonuçlarını birleştiren katman yok |
| 6 | Feature Snapshot (shared) | HIGH | Aynı feature agent başına tekrar hesaplanıyor — shared cache yok |
| 7 | Data Availability Layer | HIGH | feature availability metadata mevcut ama agentlardan kullanılmıyor |
| 8 | Lookahead Protection | HIGH | smc_structure_v1.py CHoCH/BOS lookahead risk taşıyor |
| 9 | Agent Reliability Tracking | MEDIUM | Her agent'ın hit rate, avg R, calibration saklanmıyor |
| 10 | Claim/Evidence System | MEDIUM | brain_claims var ama agent-specific claims system eksik |
| 11 | Strategy Agreement (correlation-adjusted) | MEDIUM | Aynı feature'a dayanan agentlar bağımsız kanıt sayılmıyor |
| 12 | Deterministic Replay | MEDIUM | Aynı input → aynı output garantisi yok |
| 13 | Per-setup volume_ratio | MEDIUM | Dataset-level volume_ratio var ama per-setup saklanmıyor |
| 14 | structure_type/liquidity_side | HIGH | 0% coverage — setup engine'dan gelmiyor |
| 15 | Agent versioning | LOW | Agent versiyon takibi yok |
| 16 | API contract | MEDIUM | Backend API agentic HQ output'larını sunmuyor |
| 17 | Test infrastructure for agents | MEDIUM | Agent contract tests, agent serialization tests yok |
| 18 | OOS split tracking | MEDIUM | Train/validation/OOS ayrımı mevcut ama agent-level değil |

---

## 9. ÇAKIŞAN PARÇALAR

| # | Çakışma | Açıklama |
|---|---------|----------|
| 1 | setup_engine_v1 vs research_setup_engine | Aynı setup generation — research_setup_engine V2 wrapper |
| 2 | setup_quality_engine_v2 vs v4 | v4 aktif, v2 eski — cleanup gerekiyor |
| 3 | brain_research_agent_v4 vs brain_research_agent_v4_1 | V4.1 vs V4 backup — duplicate |
| 4 | market_data_agent.py (67 symbols) vs setup_outcomes (20 symbols) | Sembol listesi uyuşmuyor |
| 5 | backtest_engine.py vs setup_backtest_engine.py | İkisi de backtest — farklı scope |
| 6 | Multiple strategy research pipelines (v5, v6) | Yeterli değil — cleanup |
| 7 | Multiple automation controllers (v2, v5) | Yeterli değil — cleanup |
| 8 | paper_evidence_aggregator_v1 vs v2_3 | Duplicate |
| 9 | brain_observation_engine_v2 vs brain_research_observation_bridge_v3 | Farklı isimlendirme, aynı iş |
| 10 | Final research decision engines (v1_1, CLEAN_V1, v3) | Üç ayrı versiyon |

---

## 10. DATA DEPENDENCIES

### 10.1 OHLCV Data Flow
```
yfinance → market_data_pipeline.py → market_datasets table
                                          ↓
                              signal_engine.py (add_indicators)
                                          ↓
                              setup_engine_v1 / research_setup_engine
                                          ↓
                              setup_outcomes table
```

### 10.2 Feature Availability (setup_outcomes, 12,651 records)

| Feature | Coverage | State |
|---------|----------|-------|
| entry_price | 77.6% (8,313) | Variable |
| invalidation_price | 77.6% (8,313) | Variable |
| target_price | 77.6% (8,313) | Variable |
| atr_pct | 39.7% (4,251) | Variable |
| zone_width_atr | 62.1% (6,645) | CONSTANT 0.5 |
| touches | 62.1% (6,645) | CONSTANT 1 |
| structure_type | 0% (0) | ALL EMPTY "" |
| liquidity_side | 0% (0) | ALL EMPTY "" |
| max_favorable | 0.02% (2) | Near-zero |
| max_adverse | 0.02% (2) | Near-zero |
| adx_value | 91.0% (11,516) | Variable |
| pnl_pct | 99.97% (10,704) | Variable |
| duration_bars | 100% (10,707) | Variable |

### 10.3 Dataset Coverage
- 45/100 datasets active (9 symbols × 5 timeframes)
- 55/100 datasets no_data
- FB/TEST symbols: very low bar counts (68-160 bars across all timeframes)
- THYAO.IS: 5,714 (5m), 1,946 (15m), 417 (1h), 177 (4h), 58 (1d)

### 10.4 Active Symbols
AAPL, BTC-USD, BV, FB, TEST, THYAO.IS, TS, WF, WT (9 symbols)

### 10.5 No-Data Symbols
BATCH, DS, DUP, FB2, LA, REP, SYNC, UM, TEST2, TEST_DB (10 symbols with no_data)
Plus 5 more symbols from setup_outcomes not in active datasets

---

## 11. ÖNERİLEN MINİMAL DEĞİŞİKLİKLER

### Phase B: Agent Contract (Öncelik: HIGH)
1. `AgentResult` dataclass oluştur (agent_id, agent_version, symbol, timeframe, timestamp, observation_timestamp, data_cutoff_timestamp, regime, direction, status, confidence, evidence, supporting_features, conflicting_features, claims, reasoning, uncertainty, invalidation_conditions, opportunity_id, setup_id)
2. Mevcut SetupModel → AgentResult mapping
3. Mevcut RegimeInfo → AgentResult mapping

### Phase C: Existing Engine → Agent Adapters (HIGH)
4. signal_engine.py → shared feature snapshot (hesaplanmış indikatörleri cachele)
5. smc_structure_v1.py → Structure Agent adapter (lookahead fix + timestamp metadata)
6. regime_filter.py → Regime Agent adapter
7. strategy_registry_v1.py → Strategy Research Agents adapters (7 family-based)
8. setup_engine_v1.py → Setup Agent adapter
9. setup_quality_engine_v4.py → Quality/Risk Agent adapter
10. setup_outcome_tracker.py → Historical Evidence Agent adapter
11. backtest_engine.py → Historical Evidence Agent (backtest simulation)

### Phase E: Opportunity Engine (MEDIUM)
12. Opportunity dataclass oluştur
13. Opportunity lifecycle state machine
14. Opportunity → Setup synthesis bridge

### Phase H: Critic Agent (MEDIUM)
15. Critic engine — structured objections, no APPROVED/REJECTED binary

### Phase I: HQ Synthesis (MEDIUM)
16. Synthesis engine — combine all agent outputs
17. Patron report generation

### Phase J: Brain Integration (LOW)
18. Brain → Agent reliability tracking
19. Agent observation → Brain claim → validation pipeline

### Phase K: API/UI Contract (LOW)
20. API endpoints for agent outputs
21. Panel readiness for "Patron report" view

---

## 12. TEST PLANI

### Mevcut Testler (83/83 PASS korunmalı)
- test_backtest_engine.py: 27 tests
- test_learning_infrastructure.py: 45 tests
- data_expansion_phases9_12.py: 11 tests

### Yeni Agentic HQ Testleri
| # | Test | Açıklama |
|---|------|----------|
| 1 | agent_contract_serialization | AgentResult serialize/deserialize |
| 2 | agent_contract_required_fields | All required fields present |
| 3 | opportunity_creation | Opportunity from agent outputs |
| 4 | opportunity_lifecycle | DETECTED → UNDER_REVIEW → VALIDATED → INVALIDATED/EXPIRED |
| 5 | opportunity_expiry | EXPIRED after timeout |
| 6 | setup_synthesis | AgentResult → SetupModel |
| 7 | agent_conflict_detection | Conflicting agents identified |
| 8 | strategy_agreement | Correlation-adjusted agreement |
| 9 | critic_objections | Critic produces structured objections |
| 10 | critic_no_binary | Critic does NOT produce APPROVED/REJECTED |
| 11 | historical_evidence_query | Historical stats from setup_outcomes |
| 12 | data_availability_check | Agent refuses unavailable features |
| 13 | lookahead_prevention | No future data in feature calculation |
| 14 | multi_symbol_ingestion | All 20 symbols processed |
| 15 | multi_timeframe_ingestion | All 5 timeframes processed |
| 16 | brain_integration | Agent observation → Brain claim |
| 17 | deterministic_replay | Same input → same output |
| 18 | api_contract | Agent output → API response |
| 19 | no_live_trading_boundary | EXECUTION_ENABLED check |
| 20 | feature_snapshot_cache | Shared feature snapshot prevents recomputation |

---

## 13. RİSKLER

| # | Risk | Olasılık | Etki | Azaltma |
|---|------|----------|------|---------|
| 1 | Lookahead in structure engine | HIGH | HIGH | CHoCH/BOS timestamp validation + regression test |
| 2 | Quality V4 r=0.16 → false confidence | HIGH | MEDIUM | Research-only label, never production probability |
| 3 | FB/TEST data corruption | MEDIUM | MEDIUM | Filter out or mark unreliable |
| 4 | structure_type/liquidity_side 0% coverage | HIGH | HIGH | Fix setup engine or mark unavailable — never fake |
| 5 | volume_ratio per-setup missing | MEDIUM | LOW | Dataset-level only, mark per-setup as unavailable |
| 6 | MFE/MAE near-zero data | MEDIUM | LOW | Track when available, NULL otherwise |
| 7 | Brain weight learning overfitting | MEDIUM | MEDIUM | OOS validation before any adaptive change |
| 8 | Agent output inconsistency | MEDIUM | MEDIUM | AgentResult contract + serialization tests |
| 9 | Data expansion overwriting existing data | LOW | HIGH | Read-only expansion, no deletions |
| 10 | Parallel engine duplication | MEDIUM | LOW | Audit confirms: reuse, don't duplicate |

---

## 14. SONRAKİ ADIMLAR

```
PHASE A (BU)     → Architecture Audit ✅ TAMAMLANDI
PHASE B          → Agent Contract + AgentResult dataclass
PHASE C          → Existing Engine → Agent Adapters
PHASE D          → Strategy Research Agents
PHASE E          → Opportunity Engine
PHASE F          → Setup Synthesis
PHASE G          → Historical Evidence Agent
PHASE H          → Critic Agent
PHASE I          → HQ Synthesis Agent
PHASE J          → Brain Integration
PHASE K          → API/UI Contract
PHASE L          → Full Test / Validation
```

---

## 15. SAĞLAM KURALLAR

1. **Mevcut kodu silme.** Mevcut engine'ler üzerine adapter katmanı kurulacak.
2. **Yeni paralel engine yazma.** Aynı işi yapan ikinci bir engine hiç yazılmayacak.
3. **Quality V4 production'a bağlanmayacak.** Research-only olarak kalacak.
4. **Fake data üretme.** Olmayan feature NULL/UNAVAILABLE.
5. **Lookahead yasak.** Her feature calculation timestamp kontrolü ile.
6. **Mevcut 83/83 test korunacak.** Her aşamadan sonra test çalıştırılacak.
7. **Veri silme.** Data expansion read-only, mevcut veri korunacak.
8. **Otomatik emir yok.** Hiçbir agent gerçek emir gönderemeyecek.
9. **İnsan karar finali.** HQ Synthesis evidence sunar, insan karar verir.
10. **Adaptive weighting production'a geçmeden önce OOS validation.**
