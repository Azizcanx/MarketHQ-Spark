# MARKETHQ — PROVIDER ABSTRACTION

**Phase:** J3
**Date:** 2026-09-16
**Status:** GO

---

## Genel Bakış

Provider abstraction, MarketHQ core'unuzun provider bağımlılığını
tamamen soyutlar. Core hiçbir zaman spesifik bir provider'a bağımlı değildir.

## Mimari

```
MarketHQ Core
    ↓ (only uses ProviderRuntime interface)
ProviderRuntime (abstract)
    ├── DeterministicRuntime (local, deterministic)
    ├── MockProviderRuntime (test)
    └── ExternalProviderRuntime (J4: real API)
```

## ProviderRuntime Contract

```python
class ProviderRuntime:
    metadata: ProviderMetadata

    def execute(agent_id, agent_version, context, timeout, execution_id, idempotency_key, adapter) → execution_result
    def cancel(execution_id) → bool
    def health() → ProviderStatus
    def record_success()
    def record_failure()
    def to_dict() → dict
```

## ProviderMetadata

```
provider_id: str
runtime_id: str
runtime_type: RuntimeType (DETERMINISTIC_LOCAL | EXTERNAL_PROVIDER | MOCK)
provider_name: str
runtime_version: str
adapter_version: str
capabilities: list[ProviderCapability]
status: ProviderStatus (HEALTHY | DEGRADED | UNAVAILABLE | UNKNOWN)
max_retries: int
timeout_seconds: int
cost_policy: str (research_only | production)
created_at, updated_at: str
```

## CapabilityType Enum

| Value | Açıklama |
|---|---|
| DETERMINISTIC | Deterministic output |
| LLM | Large Language Model |
| STRUCTURED_OUTPUT | Structured output contract |
| TOOL_USE | Tool use support |
| STREAMING | Streaming support |
| CANCELLATION | Cancellation support |
| RETRY | Retry support |
| LOCAL | Local execution |
| EXTERNAL | External provider |
| MULTIMODAL | Multimodal support |

## ProviderCapability

Her capability'ın metadata'sı:
```
capability: CapabilityType
deterministic: bool
supports_cancellation: bool
supports_structured_output: bool
latency_class: str (low | medium | high)
cost_policy: str
required_features: list[str]
max_context_tokens: int
max_output_tokens: int
cost_per_1k_tokens: float
multimodal: bool
local: bool
```

## ProviderStatus

```
HEALTHY    → çalışıyor, route edilebilir
DEGRADED   → sorunlu, fallback denenebilir
UNAVAILABLE → çalışmıyor, atlanmalı
UNKNOWN    → durum bilinmiyor, atlanmalı
```

## Yeni Provider Eklemek

1. Yeni ProviderRuntime subclass oluştur
2. ProviderMetadata tanımla
3. ProviderCapability ekle
4. `router.register_runtime(runtime)` çağır
5. Test et
6. Core MarketHQ'ya hiçbir değişiklik yok

## Provider Registration

```python
from provider_adapter import ProviderMetadata, RuntimeType, ProviderCapability, CapabilityType, ProviderStatus

md = ProviderMetadata(
    provider_id="PRV-OPENAI",
    runtime_id="RT-OPENAI-001",
    runtime_type=RuntimeType.EXTERNAL_PROVIDER,
    provider_name="OpenAI",
    runtime_version="v1.0",
    adapter_version="v1.0",
    capabilities=[
        ProviderCapability(capability=CapabilityType.LLM, latency_class="medium"),
        ProviderCapability(capability=CapabilityType.STRUCTURED_OUTPUT),
    ],
    status=ProviderStatus.HEALTHY,
    max_retries=3,
    timeout_seconds=30,
    cost_policy="research_only",
)

router.register_runtime(ExternalProviderRuntime(md))
```

## Research-Only Güvenlik

Her provider'un cost_policy="research_only" olmalı.
Production policy kullanan provider lar research task'lara
route edilmemeli.

## Cost/Token Observability

```
input_tokens: int
output_tokens: int
total_tokens: int
estimated_cost: float (NOT real billing)
currency: str (default: USD)
```

Deterministic runtime için: cost=0, not_applicable.

## Model/Provider Versioning

Her execution'da:
```
provider_id, runtime_id
provider_name, runtime_version, adapter_version
model_id (if applicable)
config_hash
```

Bu bilgilerle "bu sonuç hangi runtime koşullarında üretildi?"
sorusu cevaplanabilir.

## Health Monitoring

```python
runtime.health()  # → ProviderStatus
runtime.failure_rate  # → float
runtime.record_success()  # → success count++
runtime.record_failure()  # → failure count++
```

## Failure Isolation

```
Provider crash
    ↓
runtime.health() = DEGRADED
    ↓
Router fallback chain
    ↓
Diğer provider'lar etkilenmez
    ↓
Audit'te PROVIDER_HEALTH_CHANGED kaydedilir
```

## No Duplicate Engines

Bu abstraction mevcut AgentRuntime'u DEĞİŞTİRMEZ.
Mevcut AgentRuntime V1 korunur, V2 olarak genişletilir.
TaskRouter mevcuttur, yeni oluşturulmaz.
CollaborationOrchestrator mevcuttur, yeniden yazılmaz.

Sadece provider/runtime katmanı yeni abstraction.