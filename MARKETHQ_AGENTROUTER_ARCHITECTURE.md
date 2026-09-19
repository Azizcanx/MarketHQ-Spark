# MARKETHQ — AGENTROUTER ARCHITECTURE

**Phase:** J3
**Date:** 2026-09-16
**Status:** GO

---

## Genel Bakış

AgentRouter, MarketHQ'nın merkezi routing bileşeni.
Agent execution request'larını uygun runtime/provider'a yönlendirir.

## Sorumluluk

```
AgentTask Request
    ↓
AgentRouter.route()
    ↓ 10 kriterle scoring
En uygun runtime seç
    ↓
Health check + fallback
    ↓
RouteDecision
```

## Routing Kriterleri (deterministic, weighted)

| Kriter | Ağırlık | Açıklama |
|---|---|---|
| Capability match | 0.4 | Agent capability → runtime capability |
| Feature availability | 0.3 | Gerekli feature'lar mevcut mu |
| Latency requirement | 0.15 | low/medium/high latency |
| Cost policy | 0.1 | research_only / production |
| Deterministic preference | 0.05 | Sadece deterministic runtime |

## Tie-Breaking

Eşit skorda: runtime_id'ye göre alphabetical.
Random yok. Deterministic.

## RouteDecision

```
RouteDecision:
├── route_id
├── agent_id, task_id
├── selected_runtime, selected_provider, selected_runtime_type
├── status: ROUTED | ROUTING_REJECTED | FALLBACK_USED | NO_PROVIDER | HEALTH_DEGRADED
├── score: float
├── candidates_evaluated: int
├── fallback_reason: str
├── reasoning: str (neden bu runtime seçildi)
├── correlation_id
└── created_at
```

## Fallback Chain

```
Primary runtime (DETERMINISTIC_LOCAL)
    ↓ degrade
Fallback chain (explicit list)
    ↓ no fallback
NO_PROVIDER / ROUTING_REJECTED
```

Fallback chain:
1. Explicit fallback list (router.set_fallback_chain)
2. Any healthy deterministic runtime
3. NO_PROVIDER

## Capability Mismatch

Eğer hiçbir runtime istenen capability'ı desteklemiyorsa:
- Router en uygun runtime'ı seçer (düşük skorla)
- NOT: ROUTING_REJECTED değil, ROUTED with low score
- Çünkü fallback mantığı çalışması için bir provider seçilmeli

## Health-Aware Routing

```
runtime.health() == HEALTHY → seçilebilir
runtime.health() == DEGRADED → fallback chain denenecek
runtime.health() == UNAVAILABLE → atlanacak
runtime.health() == UNKNOWN → atlanacak
```

## Idempotency

Aynı idempotency_key ile tekrarlı request → aynı execution_id döner.
Duplicate execution engellenir.

## Explicit Runtime

Task spesifik olarak bir runtime belirtilebilir:
```python
router.route(agent_id="A1", explicit_runtime="RT-LOCAL-001")
```

Eğer explicit runtime degrade ise → fallback chain kullanılır.

## Research-Only

Router hiçbir zaman finansal/politik karar vermez.
Sadece execution backend seçer.

## No Financial Prediction

Router "bu agent daha yüksek kazanma oranına sahip" gibi
bir şey yapmaz. Kesinlikle.

## Audit Integration

Her routing kararı audit'e kaydedilir:
```
RUNTIME_SELECTED → RUNTIME_STARTED → RUNTIME_COMPLETED/FAILED
ROUTING_REJECTED → FALLBACK_SELECTED
```

## Provider Registration

```python
router = AgentRouter()
router.register_runtime(DeterministicRuntime())
router.register_runtime(MockProviderRuntime())
router.set_fallback_chain(["RT-LOCAL-001"])
```

## Test Kapsamı

- 87 unit test
- 6 E2E test (real THYAO.IS data)
- Capability matching
- Fallback chain
- Health-aware routing
- Idempotency
- Explicit runtime
- No duplicate engines