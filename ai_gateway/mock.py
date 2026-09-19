# -*- coding: utf-8 -*-
"""Phase J9 — Mock Provider Adapters for Testing.

Simulates: SUCCESS, TIMEOUT, 402, 429, AUTH_ERROR, UNAVAILABLE, INVALID_OUTPUT.
"""

from __future__ import annotations

from ai_gateway.models import (
    ProviderResponse, AIRequest, ProviderSpec, ModelSpec,
    ProviderState, ErrorType, Tier,
)
from ai_gateway.adapters import ProviderAdapter


class MockFreeProviderAdapter(ProviderAdapter):
    """Mock free provider — configurable behavior."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec,
                 behavior: str = "SUCCESS",
                 error_type: str = "",
                 delay_ms: int = 0) -> None:
        super().__init__(provider, model)
        self.behavior = behavior
        self.error_type = error_type
        self.delay_ms = delay_ms

    def generate(self, request: AIRequest) -> ProviderResponse:
        import time
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000)

        if self.behavior == "SUCCESS":
            return ProviderResponse(
                success=True,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                output=f"Mock free response for {request.purpose.value}",
                usage={"input_tokens": 50, "output_tokens": 100, "total_tokens": 150},
                latency_ms=self.delay_ms,
            )
        elif self.behavior == "TIMEOUT":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Request timed out",
                error_type=ErrorType.TIMEOUT.value,
                retryable=True,
            )
        elif self.behavior == "CREDIT_EXHAUSTED":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="402 Credit exhausted",
                error_type=ErrorType.CREDIT_EXHAUSTED.value,
                retryable=False,
            )
        elif self.behavior == "RATE_LIMITED":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="429 Rate limited",
                error_type=ErrorType.RATE_LIMITED.value,
                retryable=True,
            )
        elif self.behavior == "AUTH_ERROR":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="401 Unauthorized",
                error_type=ErrorType.AUTH_ERROR.value,
                retryable=False,
            )
        elif self.behavior == "UNAVAILABLE":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Service unavailable",
                error_type=ErrorType.UNAVAILABLE.value,
                retryable=True,
            )
        elif self.behavior == "INVALID_OUTPUT":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Invalid output format",
                error_type=ErrorType.INVALID_OUTPUT.value,
                retryable=False,
            )
        elif self.behavior == "TRANSIENT":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Transient error",
                error_type=ErrorType.TRANSIENT.value,
                retryable=True,
            )
        else:
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error=f"Unknown behavior: {self.behavior}",
                error_type=ErrorType.UNKNOWN.value,
                retryable=False,
            )


class MockNousAdapter(ProviderAdapter):
    """Mock Nous provider — simulates credit exhaustion."""

    def __init__(self, provider: ProviderSpec, model: ModelSpec,
                 behavior: str = "SUCCESS") -> None:
        super().__init__(provider, model)
        self.behavior = behavior

    def generate(self, request: AIRequest) -> ProviderResponse:
        if self.behavior == "SUCCESS":
            return ProviderResponse(
                success=True,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                output="Nous response",
                usage={"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
                latency_ms=200,
            )
        elif self.behavior == "CREDIT_EXHAUSTED":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="402 Credit exhausted",
                error_type=ErrorType.CREDIT_EXHAUSTED.value,
                retryable=False,
            )
        elif self.behavior == "TIMEOUT":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Timeout",
                error_type=ErrorType.TIMEOUT.value,
                retryable=True,
            )
        elif self.behavior == "RATE_LIMITED":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="429",
                error_type=ErrorType.RATE_LIMITED.value,
                retryable=True,
            )
        elif self.behavior == "AUTH_ERROR":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Auth failed",
                error_type=ErrorType.AUTH_ERROR.value,
                retryable=False,
            )
        elif self.behavior == "UNAVAILABLE":
            return ProviderResponse(
                success=False,
                provider_id=self.provider.provider_id,
                model_id=self.model.model_id,
                error="Unavailable",
                error_type=ErrorType.UNAVAILABLE.value,
                retryable=True,
            )
        return ProviderResponse(
            success=False,
            provider_id=self.provider.provider_id,
            model_id=self.model.model_id,
            error="Unknown",
            error_type=ErrorType.UNKNOWN.value,
            retryable=False,
        )