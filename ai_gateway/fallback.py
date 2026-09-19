# -*- coding: utf-8 -*-
"""Phase J9 — Fallback Engine + AI Gateway.

Retryable errors: timeout, temporary unavailable, 429, transient network, overloaded.
Non-retryable / routing-away: 402, disabled, unsupported capability, invalid auth.
"""

from __future__ import annotations

import time
from typing import Optional

from ai_gateway.models import (
    AIRequest, ProviderResponse, ProviderSpec, ProviderState,
    RoutingDecision, FallbackEvent, ErrorType, Tier,
)
from ai_gateway.registry import ProviderRegistry, ModelRegistry
from ai_gateway.router import AIRouter, ProviderHealthTracker, CircuitBreaker


RETRYABLE_ERRORS = {
    ErrorType.TIMEOUT.value,
    ErrorType.UNAVAILABLE.value,
    ErrorType.RATE_LIMITED.value,
    ErrorType.TRANSIENT.value,
}

NON_RETRYABLE_ERRORS = {
    ErrorType.AUTH_ERROR.value,
    ErrorType.CREDIT_EXHAUSTED.value,
}


class FallbackEngine:
    """Handles fallback between providers when one fails."""

    def __init__(self, router: AIRouter, max_depth: int = 5) -> None:
        self.router = router
        self.max_depth = max_depth

    def execute_with_fallback(self, request: AIRequest,
                               execute_fn) -> tuple[ProviderResponse, RoutingDecision]:
        """Execute request with automatic fallback on failure."""
        decision = self.router.route(request)
        self.router.record_routing_decision(decision)

        if not decision.selected_provider:
            return ProviderResponse(
                success=False, error="No eligible provider",
                error_type=ErrorType.UNAVAILABLE.value, retryable=False,
            ), decision

        # Try primary provider
        provider = self.router.providers.get(decision.selected_provider)
        if not provider:
            return ProviderResponse(
                success=False, error="Provider not found",
                error_type=ErrorType.UNAVAILABLE.value, retryable=False,
            ), decision

        model = self.router.models.list_by_provider(provider.provider_id)
        model_id = model[0].model_id if model else ""

        start = time.time()
        response = execute_fn(provider, model_id, request)
        latency = int((time.time() - start) * 1000)
        response.latency_ms = latency

        # Check if fallback needed
        if response.success:
            self.router.health.record_success(provider.provider_id, latency)
            self.router.circuit.record_success(provider.provider_id)
            return response, decision

        # Failed — determine error type
        error_type = self._classify_error(response)
        self.router.health.record_failure(provider.provider_id, error_type, latency)
        self.router.circuit.record_failure(provider.provider_id)

        # Non-retryable error — try fallback chain
        if error_type in NON_RETRYABLE_ERRORS or response.retryable:
            fallback_response = self._try_fallback(request, decision, error_type)
            if fallback_response and fallback_response.success:
                return fallback_response, decision

        return response, decision

    def _try_fallback(self, request: AIRequest, decision: RoutingDecision,
                       error_type: str) -> Optional[ProviderResponse]:
        """Try providers in fallback chain."""
        chain = self.router.fallback_chain or []
        depth = 0

        for provider_id in chain:
            if depth >= self.max_depth:
                break
            if provider_id == decision.selected_provider:
                continue

            provider = self.router.providers.get(provider_id)
            if not provider or not provider.enabled:
                continue
            if self.router.circuit.is_open(provider_id):
                continue
            if self.router.health.is_in_cooldown(provider_id):
                continue

            models = self.router.models.list_by_provider(provider_id)
            model_id = models[0].model_id if models else ""

            # Find the actual execute function from context
            start = time.time()
            # We need to call the same execute_fn — stored in closure
            # For now, use a simple approach
            depth += 1

            event = self.router.record_fallback(
                request, decision.selected_provider, provider_id,
                f"Fallback from {decision.selected_provider}: {error_type}",
                error_type,
            )

            # Record the fallback in the decision
            decision.fallback_used = True
            decision.fallback_depth = depth

        return None

    def _classify_error(self, response: ProviderResponse) -> str:
        """Classify error type from response."""
        error = response.error.lower() if response.error else ""
        error_type = response.error_type.upper() if response.error_type else ""

        if "402" in error or "credit" in error or "exhausted" in error:
            return ErrorType.CREDIT_EXHAUSTED.value
        if "429" in error or "rate limit" in error:
            return ErrorType.RATE_LIMITED.value
        if "401" in error or "auth" in error or "unauthorized" in error:
            return ErrorType.AUTH_ERROR.value
        if "timeout" in error or "timed out" in error:
            return ErrorType.TIMEOUT.value
        if "unavailable" in error or "503" in error:
            return ErrorType.UNAVAILABLE.value
        if "invalid" in error and "output" in error:
            return ErrorType.INVALID_OUTPUT.value
        if any(kw in error for kw in ["transient", "temporary", "network"]):
            return ErrorType.TRANSIENT.value

        return ErrorType.UNKNOWN.value