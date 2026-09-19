# -*- coding: utf-8 -*-
"""Mock Provider Runtime — Phase J3.

Test provider for deterministic testing without real API calls.
Supports: success, timeout, failure, malformed output, cancellation, retry simulation.

Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from provider_adapter import ProviderRuntime, ProviderMetadata, RuntimeType, ProviderStatus, ProviderCapability, CapabilityType
from agent_contract import AgentResult, AgentStatus


class MockBehavior(Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    FAILURE = "FAILURE"
    MALFORMED = "MALFORMED"
    CANCELLED = "CANCELLED"
    RETRY = "RETRY"


@dataclass
class MockExecutionConfig:
    """Configuration for mock execution behavior."""
    behavior: MockBehavior = MockBehavior.SUCCESS
    delay_seconds: int = 0
    fail_once_then_succeed: bool = False
    fail_count: int = 0
    malformed_output: bool = False
    timeout_after_seconds: int = 0


class MockProviderRuntime(ProviderRuntime):
    """Mock provider for testing without real API calls."""

    def __init__(self, metadata: ProviderMetadata | None = None) -> None:
        if metadata is None:
            metadata = ProviderMetadata(
                provider_id="PRV-MOCK",
                runtime_id="RT-MOCK-001",
                runtime_type=RuntimeType.MOCK,
                provider_name="MarketHQ Mock Provider",
                runtime_version="1.0.0",
                adapter_version="1.0.0",
                capabilities=[
                    ProviderCapability(capability=CapabilityType.DETERMINISTIC, deterministic=True, supports_cancellation=True, supports_structured_output=True, latency_class="low"),
                    ProviderCapability(capability=CapabilityType.LOCAL, latency_class="low"),
                ],
                status=ProviderStatus.HEALTHY,
                max_retries=3,
                timeout_seconds=30,
                cost_policy="research_only",
            )
        super().__init__(metadata)
        self._execution_count = 0
        self._behaviors: dict[str, MockExecutionConfig] = {}
        self._call_count: dict[str, int] = {}

    def set_behavior(self, agent_id: str, behavior: MockBehavior, **kwargs: Any) -> None:
        """Set mock behavior for an agent."""
        self._behaviors[agent_id] = MockExecutionConfig(behavior=behavior, **kwargs)

    def execute(
        self,
        agent_id: str,
        agent_version: str,
        context: Any,
        timeout_seconds: int = 30,
        execution_id: str = "",
        idempotency_key: str = "",
        adapter: Any = None,
    ) -> Any:
        """Execute with mock behavior."""
        config = self._behaviors.get(agent_id, MockExecutionConfig())
        self._execution_count += 1
        self._call_count[agent_id] = self._call_count.get(agent_id, 0) + 1

        # Handle retry simulation
        if config.behavior == MockBehavior.RETRY:
            current_count = self._call_count.get(agent_id, 0)
            if config.fail_count > 0 and current_count <= config.fail_count:
                result = AgentResult(
                    agent_id=agent_id, agent_version=agent_version,
                    status=AgentStatus.ERROR, error_type="SIMULATED_RETRY",
                    error_message=f"Retry {current_count}/{config.fail_count}",
                )
                return result

        # Handle failure
        if config.behavior == MockBehavior.FAILURE:
            result = AgentResult(
                agent_id=agent_id, agent_version=agent_version,
                status=AgentStatus.ERROR, error_type="SIMULATED_FAILURE",
                error_message="Simulated provider failure",
            )
            return result

        # Handle malformed output
        if config.behavior == MockBehavior.MALFORMED:
            # Return a dict instead of AgentResult to simulate malformed output
            return {"malformed": True, "no_status": True}

        # Handle timeout
        if config.behavior == MockBehavior.TIMEOUT:
            result = AgentResult(
                agent_id=agent_id, agent_version=agent_version,
                status=AgentStatus.ERROR, error_type="TIMEOUT",
                error_message="Simulated timeout",
            )
            return result

        # Handle cancellation
        if config.behavior == MockBehavior.CANCELLED:
            result = AgentResult(
                agent_id=agent_id, agent_version=agent_version,
                status=AgentStatus.ERROR, error_type="CANCELLED",
                error_message="Simulated cancellation",
            )
            return result

        # Default: success
        result = AgentResult(
            agent_id=agent_id,
            agent_version=agent_version,
            status=AgentStatus.SUCCESS,
            direction="NEUTRAL",
            confidence=0.5,
            uncertainty=0.5,
            symbol=getattr(context, 'symbol', '') if context else '',
            timeframe=getattr(context, 'timeframe', '') if context else '',
        )
        return result

    def cancel(self, execution_id: str) -> bool:
        return True

    def health(self) -> ProviderStatus:
        return self._metadata.status


class ExternalProviderRuntime(ProviderRuntime):
    """External provider runtime abstraction.

    J3: Interface only — real API integration in J4.
    Currently uses mock behavior for testing.
    """

    def __init__(self, metadata: ProviderMetadata, mock_behavior: MockBehavior = MockBehavior.SUCCESS) -> None:
        super().__init__(metadata)
        self._mock = MockProviderRuntime()
        self._mock_behavior = mock_behavior

    def execute(
        self,
        agent_id: str,
        agent_version: str,
        context: Any,
        timeout_seconds: int = 30,
        execution_id: str = "",
        idempotency_key: str = "",
        adapter: Any = None,
    ) -> Any:
        """Execute via external provider (mock for now)."""
        self._mock.set_behavior(agent_id, self._mock_behavior)
        return self._mock.execute(agent_id, agent_version, context, timeout_seconds, execution_id, idempotency_key, adapter)

    def cancel(self, execution_id: str) -> bool:
        return self._mock.cancel(execution_id)

    def health(self) -> ProviderStatus:
        return self._mock.health()