# -*- coding: utf-8 -*-
"""Phase J9 — AI Provider Gateway.

Main gateway that ties together:
- Provider Registry
- Model Registry
- AI Router
- Fallback Engine
- Provider Health
- Circuit Breaker
- Observability
"""

from __future__ import annotations

import time
import uuid
import threading
from datetime import datetime, timezone
from typing import Optional

from ai_gateway.models import (
    AIRequest, ProviderResponse, RoutingDecision, FallbackEvent,
    ProviderSpec, ModelSpec, ProviderState, ErrorType, Purpose,
)
from ai_gateway.registry import ProviderRegistry, ModelRegistry
from ai_gateway.router import AIRouter, ProviderHealthTracker, CircuitBreaker
from ai_gateway.fallback import FallbackEngine


# ─── Singleton ───

_gateway_instance: AIGateway | None = None
_gateway_lock = threading.Lock()


def get_gateway() -> AIGateway:
    global _gateway_instance
    if _gateway_instance is None:
        with _gateway_lock:
            if _gateway_instance is None:
                _gateway_instance = AIGateway()
                _register_defaults(_gateway_instance)
    return _gateway_instance


def _register_defaults(gateway: AIGateway) -> None:
    """Register default providers for testing."""
    from ai_gateway.models import ProviderSpec, ModelSpec, Tier, ProviderState

    free_p1 = ProviderSpec(
        provider_id="FREE-A", name="Free Provider A", tier=Tier.FREE,
        enabled=True, configured=True, capabilities=["reasoning", "structured_output"],
    )
    gateway.register_provider(free_p1)
    gateway.register_model(ModelSpec(
        model_id="FREE-A-M1", provider_id="FREE-A", display_name="Free Model A",
        tier=Tier.FREE, capabilities=["reasoning", "structured_output"],
        reasoning=True, structured_output=True, enabled=True,
    ))

    free_p2 = ProviderSpec(
        provider_id="FREE-B", name="Free Provider B", tier=Tier.FREE,
        enabled=True, configured=True, capabilities=["reasoning"],
    )
    gateway.register_provider(free_p2)
    gateway.register_model(ModelSpec(
        model_id="FREE-B-M1", provider_id="FREE-B", display_name="Free Model B",
        tier=Tier.FREE, capabilities=["reasoning"],
        reasoning=True, enabled=True,
    ))

    # Nous AI — real provider, configured if API key available
    api_key = ""
    try:
        import json
        with open("/home/markethq/.hermes/auth.json") as f:
            auth = json.load(f)
        api_key = auth.get("providers", {}).get("nous", {}).get("access_token", "")
    except Exception:
        pass

    nous_configured = bool(api_key)
    nous_p = ProviderSpec(
        provider_id="NOUS", name="Nous AI", tier=Tier.PAID,
        enabled=True, configured=nous_configured, capabilities=["reasoning", "structured_output", "tool_support"],
    )
    gateway.register_provider(nous_p)
    gateway.register_model(ModelSpec(
        model_id="NOUS-M1", provider_id="NOUS", display_name="Nous DeepSeek",
        tier=Tier.PAID, capabilities=["reasoning", "structured_output"],
        reasoning=True, structured_output=True, tool_support=True,
        pricing_status="VERIFIED" if nous_configured else "UNKNOWN",
    ))
    # Store API key for adapter use
    gateway._nous_api_key = api_key

    det_p = ProviderSpec(
        provider_id="DET", name="Deterministic Local", type="local",
        tier=Tier.FREE, enabled=True, configured=True,
        capabilities=["deterministic"],
    )
    gateway.register_provider(det_p)
    gateway.register_model(ModelSpec(
        model_id="DET-M1", provider_id="DET", display_name="Local Deterministic",
        tier=Tier.FREE, capabilities=["deterministic"],
        reasoning=False, structured_output=True, enabled=True,
    ))


class AIGateway:
    """Central AI Provider Gateway.

    Agents call the gateway, not providers directly.
    Gateway handles routing, fallback, health, observability.
    """

    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.health = ProviderHealthTracker()
        self.circuit = CircuitBreaker()
        self.router = AIRouter(self.providers, self.models, self.health, self.circuit)
        self.fallback = FallbackEngine(self.router)
        self._requests: dict[str, dict] = {}
        self._usage: list[dict] = []
        self._audit_log: list[dict] = []

    # ─── Provider Management ───

    def register_provider(self, spec: ProviderSpec) -> None:
        self.providers.register(spec)
        self._audit("PROVIDER_REGISTERED", f"Provider {spec.provider_id} registered")

    def remove_provider(self, provider_id: str) -> None:
        self.providers.remove(provider_id)
        self._audit("PROVIDER_REMOVED", f"Provider {provider_id} removed")

    def set_provider_state(self, provider_id: str, state: ProviderState) -> None:
        self.providers.set_state(provider_id, state)
        self._audit("PROVIDER_STATE_CHANGED", f"{provider_id} → {state.value}")

    # ─── Model Management ───

    def register_model(self, spec: ModelSpec) -> None:
        self.models.register(spec)

    def get_model(self, model_id: str) -> ModelSpec | None:
        return self.models.get(model_id)

    # ─── AI Request ───

    def generate(self, request: AIRequest,
                 execute_fn=None) -> tuple[ProviderResponse, RoutingDecision]:
        """Main entry point: route and execute AI request."""
        request_id = request.request_id or f"REQ-{uuid.uuid4().hex[:12]}"
        request.request_id = request_id

        # Record request
        self._requests[request_id] = {
            "request": request.to_dict(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "attempts": [],
        }

        self._audit("AI_REQUEST_STARTED", f"Request {request_id}", {
            "agent_id": request.agent_id,
            "purpose": request.purpose.value,
            "mode": self.router.routing_mode.value,
        })

        # Execute with fallback
        if execute_fn:
            response, decision = self.fallback.execute_with_fallback(
                request, execute_fn,
            )
        else:
            # No execute function — return routing decision only
            decision = self.router.route(request)
            self.router.record_routing_decision(decision)
            response = ProviderResponse(
                success=False,
                error="No execute function provided",
                error_type=ErrorType.UNAVAILABLE.value,
                retryable=False,
            )

        # Record usage
        self._record_usage(request, response, decision)

        # Record audit
        self._audit("AI_REQUEST_COMPLETED", f"Request {request_id}", {
            "success": response.success,
            "provider": response.provider_id,
            "model": response.model_id,
            "fallback_used": decision.fallback_used,
            "fallback_depth": decision.fallback_depth,
            "latency_ms": response.latency_ms,
        })

        return response, decision

    # ─── Observability ───

    def get_usage(self) -> list[dict]:
        return self._usage

    def get_audit_log(self) -> list[dict]:
        return self._audit_log

    def get_request(self, request_id: str) -> dict | None:
        return self._requests.get(request_id)

    def get_health_summary(self) -> dict:
        return {
            "providers": self.providers.count(),
            "models": self.models.count(),
            "routing_mode": self.router.routing_mode.value,
            "fallback_chain": self.router.fallback_chain,
            "health": self.health.to_dict(),
            "circuit_states": {
                pid: self.circuit.get_state(pid)
                for pid in self.providers._providers
            },
        }

    # ─── Internal ───

    def _record_usage(self, request: AIRequest, response: ProviderResponse,
                      decision: RoutingDecision) -> None:
        usage = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "task_id": request.task_id,
            "provider_id": response.provider_id,
            "model_id": response.model_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": response.latency_ms,
            "input_tokens": response.usage.get("input_tokens"),
            "output_tokens": response.usage.get("output_tokens"),
            "total_tokens": response.usage.get("total_tokens"),
            "estimated_cost": None,
            "pricing_status": "UNKNOWN",
            "success": response.success,
            "fallback_used": decision.fallback_used,
            "fallback_depth": decision.fallback_depth,
            "error_type": response.error_type,
        }
        self._usage.append(usage)

    def _audit(self, event_type: str, message: str,
               metadata: Optional[dict] = None) -> None:
        entry = {
            "event_type": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._audit_log.append(entry)

    def to_dict(self) -> dict:
        return {
            "providers": self.providers.to_dict(),
            "models": self.models.to_dict(),
            "health": self.health.to_dict(),
            "router": self.router.to_dict(),
            "usage_count": len(self._usage),
            "audit_count": len(self._audit_log),
        }