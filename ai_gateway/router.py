# -*- coding: utf-8 -*-
"""Phase J9 — AI Router + Fallback Engine + Provider Health + Circuit Breaker."""

from __future__ import annotations

import time
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from ai_gateway.models import (
    AIRequest, ModelSpec, ProviderSpec, ProviderState,
    RoutingDecision, FallbackEvent, Tier, RoutingMode, ErrorType, Purpose,
)
from ai_gateway.registry import ProviderRegistry, ModelRegistry


class ProviderHealthTracker:
    """Tracks provider health independently from agent reliability."""

    def __init__(self) -> None:
        self._health: dict[str, dict] = {}

    def record_success(self, provider_id: str, latency_ms: int = 0) -> None:
        h = self._health.setdefault(provider_id, {
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "total_requests": 0,
            "total_failures": 0,
            "last_success": "",
            "last_failure": "",
            "last_error_type": "",
            "latency_ms": 0,
            "availability": 0.0,
            "cooldown_until": "",
            "health_score": 0.0,
        })
        h["consecutive_failures"] = 0
        h["consecutive_successes"] += 1
        h["total_requests"] += 1
        h["last_success"] = datetime.now(timezone.utc).isoformat()
        h["latency_ms"] = latency_ms
        h["availability"] = self._compute_availability(h)
        h["health_score"] = self._compute_score(h)

    def record_failure(self, provider_id: str,
                        error_type: str = "", latency_ms: int = 0) -> None:
        h = self._health.setdefault(provider_id, {
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "total_requests": 0,
            "total_failures": 0,
            "last_success": "",
            "last_failure": "",
            "last_error_type": "",
            "latency_ms": 0,
            "availability": 0.0,
            "cooldown_until": "",
            "health_score": 0.0,
        })
        h["consecutive_failures"] += 1
        h["consecutive_successes"] = 0
        h["total_requests"] += 1
        h["total_failures"] += 1
        h["last_failure"] = datetime.now(timezone.utc).isoformat()
        h["last_error_type"] = error_type
        h["latency_ms"] = latency_ms
        h["availability"] = self._compute_availability(h)
        h["health_score"] = self._compute_score(h)

    def get_health(self, provider_id: str) -> dict:
        h = self._health.get(provider_id, {})
        return {
            "provider_id": provider_id,
            "consecutive_failures": h.get("consecutive_failures", 0),
            "consecutive_successes": h.get("consecutive_successes", 0),
            "total_requests": h.get("total_requests", 0),
            "total_failures": h.get("total_failures", 0),
            "last_success": h.get("last_success", ""),
            "last_failure": h.get("last_failure", ""),
            "last_error_type": h.get("last_error_type", ""),
            "latency_ms": h.get("latency_ms", 0),
            "availability": h.get("availability", 0.0),
            "cooldown_until": h.get("cooldown_until", ""),
            "health_score": h.get("health_score", 0.0),
        }

    def is_in_cooldown(self, provider_id: str, cooldown_seconds: int = 60) -> bool:
        h = self._health.get(provider_id, {})
        cooldown_until = h.get("cooldown_until", 0)
        if not cooldown_until:
            return False
        try:
            return time.time() < cooldown_until
        except Exception:
            return False

    def set_cooldown(self, provider_id: str, seconds: int = 60) -> None:
        h = self._health.setdefault(provider_id, {})
        h["cooldown_until"] = (datetime.now(timezone.utc).timestamp() + seconds)

    def _compute_availability(self, h: dict) -> float:
        total = h.get("total_requests", 0)
        if total == 0:
            return 0.0
        failures = h.get("total_failures", 0)
        return round((total - failures) / total, 4)

    def _compute_score(self, h: dict) -> float:
        availability = h.get("availability", 0.0)
        successes = h.get("consecutive_successes", 0)
        failures = h.get("consecutive_failures", 0)
        score = availability * 100
        if failures > 0:
            score -= min(failures * 10, 50)
        score += min(successes * 2, 20)
        return max(0.0, min(100.0, round(score, 1)))

    def to_dict(self) -> dict:
        return {pid: self.get_health(pid) for pid in self._health}


class CircuitBreaker:
    """Circuit breaker for provider protection."""

    def __init__(self, failure_threshold: int = 5,
                 cooldown_seconds: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, str] = {}
        self._failure_counts: dict[str, int] = {}
        self._opened_at: dict[str, str] = {}

    def record_success(self, provider_id: str) -> None:
        self._states[provider_id] = "CLOSED"
        self._failure_counts[provider_id] = 0

    def record_failure(self, provider_id: str) -> None:
        self._failure_counts[provider_id] = self._failure_counts.get(provider_id, 0) + 1
        if self._failure_counts[provider_id] >= self.failure_threshold:
            self._states[provider_id] = "OPEN"
            self._opened_at[provider_id] = datetime.now(timezone.utc).isoformat()

    def is_open(self, provider_id: str) -> bool:
        if self._states.get(provider_id) != "OPEN":
            return False
        opened = self._opened_at.get(provider_id, "")
        if not opened:
            return True
        try:
            dt = datetime.fromisoformat(opened)
            elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
            if elapsed > self.cooldown_seconds:
                self._states[provider_id] = "HALF_OPEN"
                return False
            return True
        except Exception:
            return True

    def get_state(self, provider_id: str) -> str:
        return self._states.get(provider_id, "CLOSED")

    def reset(self, provider_id: str) -> None:
        self._states.pop(provider_id, None)
        self._failure_counts.pop(provider_id, None)
        self._opened_at.pop(provider_id, None)


class AIRouter:
    """Centralized AI Router with routing policies and fallback."""

    def __init__(self,
                 provider_registry: ProviderRegistry,
                 model_registry: ModelRegistry,
                 health_tracker: ProviderHealthTracker,
                 circuit_breaker: CircuitBreaker) -> None:
        self.providers = provider_registry
        self.models = model_registry
        self.health = health_tracker
        self.circuit = circuit_breaker
        self.routing_mode: RoutingMode = RoutingMode.AUTO
        self.fallback_chain: list[str] = []
        self.routing_decisions: list[RoutingDecision] = []
        self.fallback_events: list[FallbackEvent] = []
        self._decision_counter = 0

    def set_routing_mode(self, mode: RoutingMode) -> None:
        self.routing_mode = mode

    def set_fallback_chain(self, chain: list[str]) -> None:
        self.fallback_chain = chain

    def route(self, request: AIRequest) -> RoutingDecision:
        """Route request to best provider/model based on policy."""
        self._decision_counter += 1
        route_id = f"RT-{self._decision_counter:06d}"
        timestamp = datetime.now(timezone.utc).isoformat()

        candidates = self._get_candidates(request)

        if not candidates:
            return RoutingDecision(
                route_id=route_id, request_id=request.request_id,
                mode=self.routing_mode.value,
                candidates_evaluated=len(candidates),
                reasoning="No eligible providers found",
                timestamp=timestamp,
                determinism_key=self._det_key(request, candidates),
            )

        # candidates is list of (ProviderSpec, [ModelSpec])
        selected_provider = candidates[0][0].provider_id
        selected_model = candidates[0][1][0].model_id if candidates[0][1] else ""

        return RoutingDecision(
            route_id=route_id, request_id=request.request_id,
            selected_provider=selected_provider,
            selected_model=selected_model,
            mode=self.routing_mode.value,
            candidates_evaluated=len(candidates),
            fallback_used=False,
            reasoning=f"Selected {selected_provider}/{selected_model} via {self.routing_mode.value}",
            timestamp=timestamp,
            determinism_key=self._det_key(request, candidates),
        )

    def record_fallback(self, request: AIRequest, from_provider: str,
                         to_provider: str, reason: str,
                         error_type: str = "", success: bool = False) -> FallbackEvent:
        """Record a fallback event."""
        event = FallbackEvent(
            event_id=f"FB-{len(self.fallback_events) + 1:06d}",
            request_id=request.request_id,
            from_provider=from_provider,
            to_provider=to_provider,
            reason=reason,
            error_type=error_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=success,
        )
        self.fallback_events.append(event)
        return event

    def record_routing_decision(self, decision: RoutingDecision) -> None:
        self.routing_decisions.append(decision)

    def _get_candidates(self, request: AIRequest) -> list:
        """Get eligible providers based on routing mode."""
        providers = self.providers.list_all()
        candidates = []

        for p in providers:
            if not p.enabled:
                continue
            if self.circuit.is_open(p.provider_id):
                continue
            if self.health.is_in_cooldown(p.provider_id):
                continue

            models = self.models.list_by_provider(p.provider_id)
            eligible_models = [m for m in models if m.enabled and m.availability]

            if not eligible_models:
                continue

            tier_match = True
            if request.allowed_tiers:
                tier_match = any(m.tier.value in request.allowed_tiers for m in eligible_models)

            if not tier_match:
                continue

            if request.preferred_provider and p.provider_id != request.preferred_provider:
                continue

            candidates.append((p, eligible_models))

        # Sort by routing mode
        if self.routing_mode == RoutingMode.FREE_FIRST:
            candidates.sort(key=lambda x: (x[0].tier != Tier.FREE, x[0].priority))
        elif self.routing_mode == RoutingMode.PAID_FIRST:
            candidates.sort(key=lambda x: (x[0].tier == Tier.FREE, -x[0].priority))
        elif self.routing_mode == RoutingMode.CHEAPEST_AVAILABLE:
            candidates.sort(key=lambda x: min(m.input_cost + m.output_cost for m in x[1]) if x[1] else 999)
        elif self.routing_mode == RoutingMode.LOCAL_FIRST:
            candidates.sort(key=lambda x: (x[0].type != "local", x[0].priority))
        elif self.routing_mode == RoutingMode.BEST_AVAILABLE:
            candidates.sort(key=lambda x: -self.health.get_health(x[0].provider_id).get("health_score", 0))
        elif self.routing_mode == RoutingMode.SPECIFIC_PROVIDER:
            if request.preferred_provider:
                candidates.sort(key=lambda x: x[0].provider_id != request.preferred_provider)
        elif self.routing_mode == RoutingMode.SPECIFIC_MODEL:
            if request.preferred_model:
                candidates.sort(key=lambda x: not any(m.model_id == request.preferred_model for m in x[1]))

        return candidates

    def _det_key(self, request: AIRequest, candidates: list) -> str:
        """Determinism key for reproducible routing."""
        pids = [c[0].provider_id for c in candidates]
        key_data = f"{request.request_id}:{self.routing_mode.value}:{pids}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "routing_mode": self.routing_mode.value,
            "fallback_chain": self.fallback_chain,
            "total_decisions": len(self.routing_decisions),
            "total_fallbacks": len(self.fallback_events),
        }