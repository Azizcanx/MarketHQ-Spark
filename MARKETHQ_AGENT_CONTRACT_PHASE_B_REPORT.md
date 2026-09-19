# MarketHQ — Phase B Report: Agent Contract + Engine Adapter Layer

**Date:** 2026-09-16
**Status:** COMPLETE

---

## 1. OLUŞTURULAN MODELLER

| Model | Dosya | Açıklama |
|-------|-------|----------|
| `AgentResult` | `agent_contract.py` | Ortak agent output contract — agent_id, execution_id, timestamp, observation_timestamp, data_cutoff_timestamp, symbol, timeframe, status, direction, regime, confidence, uncertainty, evidence, supporting_features, conflicting_features, claims, reasoning, invalidation_conditions, source_engine, source_engine_version, opportunity_id, setup_id, data_quality, feature_availability, error_type, error_message |
| `Evidence` | `agent_contract.py` | Structured evidence container — supporting/conflicting/neutral lists + items list with EvidenceItem |
| `EvidenceItem` | `agent_contract.py` | Single evidence piece — evidence_id, type, feature, value, timestamp, data_cutoff_timestamp, direction, strength, source, explanation |
| `Claim` | `agent_contract.py` | Structured claim for Brain validation — claim_id, statement, source_agent, source_agent_version, observation_timestamp, data_cutoff_timestamp, evidence_refs, validation_status, feature, regime, timeframe, symbol, sample_size, confidence |
| `MarketContext` | `agent_contract.py` | Shared immutable context — symbol, timeframe, observation_timestamp, data_cutoff_timestamp, feature_snapshot, ohlcv_ref, dataset metadata, freeze() for immutability |
| `FeatureSnapshot` | `agent_contract.py` | Cached indicators — RSI, ATR, ADX, volume_ratio, regime, structure_type, liquidity_side, availability tracking, data quality score |
| `BaseAgentAdapter` | `agent_contract.py` | Abstract adapter base — run() → AgentResult, _error_result(), _success_result() |
| `AdapterInfo` | `agent_contract.py` | Adapter metadata — adapter_id, adapter_version, source_engine, source_engine_version |

### Status Enum
- `SUCCESS` — Agent executed successfully
- `PARTIAL` — Partial data, some features unavailable
- `INSUFFICIENT_DATA` — Not enough data
- `ERROR` — Execution failed

### Claim Status Enum
- `UNTESTED` — Not yet validated by Brain
- `TESTING` — Currently being validated
- `SUPPORTED` — Evidence supports the claim
- `WEAKENED` — Some evidence contradicts
- `REJECTED` — Evidence contradicts

---

## 2. ADAPTER'LAR

| Adapter | ID | Kaynak Engine | Durum |
|---------|-----|---------------|-------|
| `MarketDataAdapter` | market_data | market_data_pipeline | ✅ PASS |
| `RegimeAdapter` | regime | setup_engine_v1 (detect_regime) | ✅ PASS |
| `StructureAdapter` | structure | smc_structure_v1 | ✅ PASS — lookahead risk raporluyor |
| `MomentumVolatilityAdapter` | momentum_volatility | signal_engine | ✅ PASS |
| `StrategyAdapter` | strategy | strategy_registry_v1 | ✅ PASS |
| `SetupAdapter` | setup | setup_engine_v1 | ✅ PASS |
| `QualityAdapter` | quality | setup_quality_engine_v4 | ✅ PASS |
| `HistoricalEvidenceAdapter` | historical_evidence | setup_outcome_tracker | ✅ PASS |

Her adapter:
- `MarketContext` → `AgentResult`
- Hata yakalar, hiç exception fırlatmaz
- Engine metadata taşır
- Claims üretir (Brain validation için)
- Feature availability bildirir

---

## 3. SHARED CONTEXT

`MarketContext` immutable context paylaşım katmanı:
- `freeze()` — oluşturulduktan sonra değiştirilemez
- `process_ohlcv()` — OHLCV'den feature_snapshot otomatik doldurur
- Aynı symbol+timeframe+cutoff → aynı context → deterministic replay

---

## 4. FEATURE SNAPSHOT

`FeatureSnapshot` shared indicator cache:
- RSI, ATR, ADX, Volume Ratio, MACD, SMA, EMA, Bollinger
- Regime, structure_type, liquidity_side
- Availability tracking (her feature için bool)
- Null feature tracking
- Data quality score (0..1)

---

## 5. ENGINE MAPPING

| Mevcut Engine | Adapter | Agent ID |
|---------------|---------|----------|
| market_data_pipeline.py | MarketDataAdapter | market_data |
| setup_engine_v1.py (detect_regime) | RegimeAdapter | regime |
| smc_structure_v1.py | StructureAdapter | structure |
| signal_engine.py | MomentumVolatilityAdapter | momentum_volatility |
| strategy_registry_v1.py | StrategyAdapter | strategy |
| setup_engine_v1.py (build_setup) | SetupAdapter | setup |
| setup_quality_engine_v4.py | QualityAdapter | quality |
| setup_outcome_tracker.py | HistoricalEvidenceAdapter | historical_evidence |

---

## 6. DUPLICATE ENGINE FINDINGS

| Çakışma | Durum |
|---------|-------|
| setup_engine_v1 + research_setup_engine | Araştırıldı — research_setup_engine V2 wrapper, adapter üzerinden izole |
| quality_engine_v2 + v4 | v4 aktif, v2 kullanılmıyor — cleanup öncesi izole |
| 3 final decision engine | Araştırıldı — dependency map oluşturulacak |
| Brain V2/V3/V4 | V4 aktif — adapter'dan izole |

**Bu fazda silinmedi.** Sadece adapter üzerinden izol edildi.

---

## 7. LOOKAHEAD FINDINGS

| Engine | Lookahead Risk | Durum |
|--------|----------------|-------|
| smc_structure_v1 | HIGH — CHoCH/BOS future bar kullanabilir | ⚠️ Raporluyor, düzeltmedi |
| signal_engine | LOW — rolling window | ✅ |
| regime_filter | LOW — historical data only | ✅ |
| setup_engine_v1 | LOW — uses current bar only | ✅ |

**StructureAdapter** lookahead riskini `engine_metadata.lookahead_risk` ve `lookahead_details` olarak raporluyor. Sessiz düzeltme yapılmadı — minimum riskyapı.

---

## 8. STRUCTURE COVERAGE FINDINGS

| Alan | Coverage | Durum |
|------|----------|-------|
| structure_type | 0% (0/12651) | NULL/UNAVAILABLE — fake değil |
| liquidity_side | 0% (0/12651) | NULL/UNAVAILABLE — fake değil |
| max_favorable | 0.02% (2/12651) | NULL — limited |
| max_adverse | 0.02% (2/12651) | NULL — limited |
| adx_value | 91% (11516) | ✅ Variable |
| atr_pct | 39.7% (4251) | ✅ Variable |

**Sahte doldurma YOK.** Tüm boş alan NULL/UNAVAILABLE olarak işaretli.

---

## 9. DB DEĞİŞİKLİKLERİ

DB'ye yeni tablo eklenmedi — mevcut yapı korundu.

Yeni alanlar mevcut tablolarda:
- `market_datasets.adx_value`, `adx_trend` (Phase 5'den)
- `setup_outcomes.adx_value`, `adx_trend` (Phase 5'ten)

Gelecek fazlar için önerilen yeni tablolar:
- `agent_runs` — agent çalıştırma kayıtları
- `agent_results` — AgentResult serialization
- `evidence` — structured evidence
- `claims` — Brain validation için claims
- `feature_snapshots` — shared cache

Bu fazda OLUŞTURULMADI — yalnızca contract tanımlandı.

---

## 10. API DEĞİŞİKLİKLERİ

Yeni API endpoint önerileri ( Phase K'de implement edilecek):

| Endpoint | Açıklama |
|----------|----------|
| `GET /agents` | Aktif agent listesi |
| `GET /agents/{id}` | Agent detay + version |
| `GET /agent-runs/{id}` | AgentResult detay |
| `GET /feature-snapshot/{symbol}/{timeframe}` | Shared feature snapshot |
| `GET /evidence/{agent_run_id}` | Evidence items |
| `GET /claims` | Brain validation queue |

---

## 11. TEST SONUÇLARI

| Test Seti | Count | Status |
|-----------|-------|--------|
| Mevcut backtest engine | 27 | ✅ PASS |
| Mevcut learning infrastructure | 45 | ✅ PASS |
| Data expansion phases 9-12 | 11 | ✅ PASS |
| **Yeni Phase B agent contract** | **65** | ✅ PASS |
| **TOPLAM** | **148** | ✅ 148/148 PASS |

### Phase B Test Detayları
- AgentResult serialization ✅
- AgentResult validation ✅
- Evidence validation ✅
- Claim validation ✅
- MarketContext validation ✅
- Feature availability ✅
- Adapter output (8 adapter) ✅
- Adapter error isolation ✅
- Deterministic replay ✅
- Timestamp/cutoff validation ✅
- Lookahead regression ✅
- NULL/unavailable feature handling ✅
- Confidence vs Quality separation ✅
- Engine version tracking ✅
- Multi-symbol ✅
- Multi-timeframe ✅
- Evidence traceability ✅

---

## 12. KALAN RİSKLER

| # | Risk | Önem | Azaltma |
|---|------|------|---------|
| 1 | smc_structure_v1 lookahead | HIGH | StructureAdapter raporluyor — düzeltme Phase C'de |
| 2 | Quality V4 r=0.16 | MEDIUM | Research-only label korundu |
| 3 | FB/TEST data corruption | MEDIUM | Filter out veya mark unreliable |
| 4 | volume_ratio per-setup missing | LOW | Dataset-level mevcut |
| 5 | Duplicate engine cleanup | MEDIUM | Dependency map sonraki fazda |
| 6 | Brain integration | LOW | Phase J'de |
| 7 | API contract | LOW | Phase K'de |
| 8 | Agent reliability tracking | MEDIUM | Phase C'de |

---

## 13. PHASE C İÇİN HAZIR PARÇALAR

Phase C (Existing Engine → Agent Runtime) için hazır:

✅ AgentResult contract — tüm agentlar bu formatı kullanabilir
✅ 8 adapter — mevcut engine'ler adapter üzerinden AgentResult üretiyor
✅ MarketContext — shared feature snapshot mekanizması
✅ FeatureSnapshot — indicator cache
✅ Evidence + Claim — Brain validation için structured format
✅ Error isolation — bir agent hata verdiğinde diğerleri etkilenmez
✅ Deterministic replay — aynı input → aynı output
✅ Lookahead audit — structure engine lookahead riski tespit edildi
✅ Lookahead protection — data_cutoff_timestamp izlenimi
✅ 148 test — tümü PASS

Phase C'de yapılacak:
- OpenAI Agents SDK integration (agent_runtime_v1.py → AgentResult)
- Agent orchestration pipeline
- Shared feature snapshot cache (in-memory)
- Brain ↔ Agent observation bridge
- Claim → Brain validation pipeline
- Agent reliability tracking

---

## 14. DEĞİŞEN DOSYALAR

| Dosya | Durum |
|-------|-------|
| `agent_contract.py` | ✅ Yeni — AgentResult, Evidence, Claim, MarketContext, FeatureSnapshot, BaseAgentAdapter |
| `engine_adapters.py` | ✅ Yeni — 8 adapter (MarketData, Regime, Structure, MomentumVolatility, Strategy, Setup, Quality, HistoricalEvidence) |
| `test_agent_contract.py` | ✅ Yeni — 65 test |
| `MARKETHQ_AGENT_CONTRACT_PHASE_B_REPORT.md` | ✅ Bu dosya |

**Mevcut dosyalar DEĞİŞTİRİLMEDİ:**
- setup_object_model.py ✅ korundu
- setup_quality_engine_v4.py ✅ korundu
- smc_structure_v1.py ✅ korundu
- signal_engine.py ✅ korundu
- setup_engine_v1.py ✅ korundu
- market_data_pipeline.py ✅ korundu
- Tüm mevcut testler ✅ PASS

---

## 15. ÖNEMLİ KARARLAR

1. **AgentResult generic tutuldu** — strategy-specific alanlar engine_metadata'da
2. **Mevcut engine'ler değiştirilmedi** — adapter üzerine katmanlandı
3. **Lookahead sessiz düzeltilmedi** — StructureAdapter raporluyor, düzeltme Phase C
4. **Sahte data üretilmedi** — NULL/UNAVAILABLE kullanıldı
5. **Quality V4 production probability değildir** — research signal olarak label'ı korundu
6. **Duplicate engine'ler silinmedi** — dependency map sonraki fazda
7. **DB schema değiştirilmedi** — yeni tablular Phase C'de
8. **Mevcut 83 test korundu** — 72/72 + 11/11 + 65/65 = 148/148
