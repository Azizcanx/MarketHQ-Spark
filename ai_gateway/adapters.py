# -*- coding: utf-8 -*-
"""Phase J9 — Provider Adapters.

Provider adapters normalize provider-specific responses.
Each adapter implements:
    generate(request) -> ProviderResponse
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from ai_gateway.models import (
    ProviderResponse, AIRequest, ProviderSpec, ModelSpec,
    ProviderState, ErrorType, Tier,
)


class ProviderAdapter:
    """Base adapter — normalize provider responses."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec) -> None:
        self.provider = provider
        self.model = model

    def generate(self, request: AIRequest) -> ProviderResponse:
        raise NotImplementedError

    def health_check(self) -> ProviderState:
        return ProviderState.AVAILABLE


class NousAdapter(ProviderAdapter):
    """Adapter for Nous AI provider — real HTTP implementation."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec,
                 api_key: str = "") -> None:
        super().__init__(provider, model)
        self.api_key = api_key
        self.base_url = "https://inference-api.nousresearch.com/v1"

    def generate(self, request: AIRequest) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="No API key configured",
                error_type=ErrorType.AUTH_ERROR.value,
                retryable=False,
            )

        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model.model_id,
                "messages": [{"role": "user", "content": request.user_input}],
                "max_tokens": 500,
                "temperature": 0.7,
            }
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if r.status_code == 402:
                return ProviderResponse(
                    success=False,
                    provider_id=self.provider.provider_id,
                    model_id=self.model.model_id,
                    error="Insufficient credits",
                    error_type=ErrorType.CREDIT_EXHAUSTED.value,
                    retryable=True,
                )
            if r.status_code == 429:
                return ProviderResponse(
                    success=False,
                    provider_id=self.provider.provider_id,
                    model_id=self.model.model_id,
                    error="Rate limited",
                    error_type=ErrorType.RATE_LIMITED.value,
                    retryable=True,
                )
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return ProviderResponse(
                success=True,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                output=content,
                usage=usage,
                latency_ms=0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error=str(e),
                error_type=ErrorType.UNAVAILABLE.value,
                retryable=True,
            )


class FreeProviderAdapter(ProviderAdapter):
    """Adapter for free-tier providers."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec,
                 simulate_response: Optional[str] = None) -> None:
        super().__init__(provider, model)
        self.simulate_response = simulate_response

    def generate(self, request: AIRequest) -> ProviderResponse:
        if not self.provider.configured:
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Provider not configured",
                error_type=ErrorType.UNAVAILABLE.value,
                retryable=True,
            )
        output = self.simulate_response or f"Response from {self.provider.provider_id}"
        return ProviderResponse(
            success=True,
            provider_id=self.provider.provider_id,
            model_id=self.model.model_id,
            output=output,
            usage={"input_tokens": 50, "output_tokens": 100, "total_tokens": 150},
            latency_ms=50,
        )


class DeterministicAdapter(ProviderAdapter):
    """Adapter for deterministic/local runtime."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec) -> None:
        super().__init__(provider, model)

    def generate(self, request: AIRequest) -> ProviderResponse:
        return ProviderResponse(
            success=True,
            provider_id=self.provider.provider_id,
            model_id=self.model.model_id,
            output=f"Deterministic: {request.purpose.value}",
            usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            latency_ms=5,
        )

    def health_check(self) -> ProviderState:
        return ProviderState.AVAILABLE