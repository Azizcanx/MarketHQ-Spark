# MARKETHQ — AGENT RUNTIME ARCHITECTURE

**Phase:** J3
**Date:** 2026-09-16
**Status:** GO

---

## Genel Bakış

Agent Runtime V2, mevcut AgentRuntime'u bozmadan genişletir.
Yeni execution lifecycle + metadata + router integration ekler.

## Mevcut AgentRuntime (V1) — KORUNDU

```
AgentRuntime
├── run(agent_id, symbol, timeframe, ...) → AgentRun
├── run_multiple(agent_ids, ...) → list[AgentRun]
├── get_run(execution_id) → AgentRun
├── list_runs(agent_id, symbol, status) → list[AgentRun]
└── _build_context(symbol, timeframe, ...) → MarketContext
```

## AgentRuntime V2 — EKLENEN

```
AgentRuntime (V2 = V1 + genişleme)
├── execute_with_router(agent_id, agent_version, router, ...) → AgentRun
│   ├── Route → AgentRouter
│   ├── Execute → ProviderRuntime
│   ├── Validate → AgentResult
│   ├── Audit → ResearchAuditEvent
│   └── Metadata → ExecutionMetadata
├── _runs: dict[execution_id, AgentRun]
└── ExecutionMetadata (yeni)
```

## ExecutionLifecycle

```
CREATED → QUEUED → RUNNING → COMPLETED
                    ↓         ↓
                FAILED    TIMEOUT
                    ↓
                CANCELLED
                    ↓
                REJECTED (no provider)
```

## ExecutionMetadata

Her execution için:

```
execution_id, agent_id, agent_version
runtime_id, provider_id, model_id
task_id, workspace_id, context_version
input_version, output_version, correlation_id
idempotency_key
started_at, finished_at, duration_ms
input_tokens, output_tokens, total_tokens
estimated_cost, currency
retry_count, timeout_seconds
cancelled, fallback_reason, routing_reasoning
provider_metadata, audit_events
```

## AgentRun Status Genişlemesi

```
AgentRunStatus:
├── CREATED  (yeni run oluşturuldu)
├── QUEUED   (runtime'a gönderildi)
├── RUNNING  (çalışıyor)
├── COMPLETED (başarılı)
├── FAILED   (hata)
├── TIMEOUT  (zaman aşımı)
├── CANCELLED (iptal edildi)
├── REJECTED (provider bulunamadı)
└── INSUFFICIENT_DATA (mevcut)
```

## AgentResult Contract — DEĞİŞMEDI

```
AgentResult:
├── agent_id, agent_version
├── status: AgentStatus
├── direction: LONG|SHORT|NEUTRAL
├── confidence: float (NOT win probability)
├── uncertainty: float
├── symbol, timeframe
├── evidence: Evidence
├── claims: list[Claim]
├── reasoning, invalidation_conditions
├── source_engine, source_engine_version
├── engine_metadata: dict
├── opportunity_id, setup_id
├── data_quality, feature_availability
└── error_type, error_message
```

## Research-Only Güvenlik

Runtime hiçbir zaman:
- Broker bağlamaz
- Order göndermez
- Trade açmaz
- Gerçek para kullanmaz
- Otomatik yatırım kararı vermez

## Determinism

Deterministic runtime:
- Aynı input + aynı context version + aynı config → aynı output
- Gerçek LLM yok → deterministic by design
- External provider deterministik değilse → replay fixture

## Provider Değiştirilebilirlik

```
MarketHQ Core
    ↓
AgentRouter (seçer)
    ↓
ProviderRuntime (abstract)
    ├── DeterministicRuntime (local)
    ├── MockProviderRuntime (test)
    └── ExternalProviderRuntime (J4)
```

Provider değiştirilmek istenirse:
1. Yeni ProviderRuntime implement et
2. `router.register_runtime(new_runtime)` ekle
3. Core MarketHQ'ya dokunma

## Failure Isolation

```
Provider crash
    ↓
Runtime.status = DEGRADED
    ↓
Router fallback chain
    ↓
Diğer agentlar devam eder
    ↓
Audit'te açıkça FAILURE kaydedilir
    ↓
Team Synthesis failure'ı gösterir
```

## Audit Integration

Her execution için audit olayları:
```
RUNTIME_SELECTED → RUNTIME_STARTED → RUNTIME_COMPLETED/FAILED/TIMEOUT/CANCELLED
ROUTING_REJECTED → FALLBACK_SELECTED → OUTPUT_VALIDATED/REJECTED
PROVIDER_HEALTH_CHANGED
EXECUTION_DUPLICATE
IDENTITY_CHECK
```

## Persistence

Execution history:
- In-memory: `AgentRuntime._runs`, `DeterministicRuntime._executions`
- Audit: `ResearchAuditEvent` → `AuditLog`
- Migration: additive, idempotent, safe, no DELETE

## Observability

HQ sorularını cevaplar:
- Hangi agent çalıştı? → agent_id
- Hangi task için? → task_id
- Hangi runtime seçildi? → runtime_id
- Neden seçildi? → routing_reasoning
- Ne kadar sürdü? → duration_ms
- Başarısız mı? → status, error_type
- Retry oldu mu? → retry_count
- Fallback mı? → fallback_reason
- Context version? → context_version
- Output validation? → OUTPUT_VALIDATED/REJECTED
- Provenance? → provenance chain
- Token/cost? → input/output/total_tokens, estimated_cost