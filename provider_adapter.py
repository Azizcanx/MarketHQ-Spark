# -*- coding: utf-8 -*-
"""Provider Runtime Abstraction — Phase J3.

Abstract contract for all provider runtimes (local deterministic, external LLM, etc.).
MarketHQ core never depends on a specific provider — only on this abstraction.

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RuntimeType(Enum):
    DETERMINISTIC_LOCAL = "DETERMINISTIC_LOCAL"
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    MOCK = "MOCK"


class ProviderStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CapabilityType(Enum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    STRUCTURED_OUTPUT = "structured_output"
    TOOL_USE = "tool_use"
    STREAMING = "streaming"
    CANCELLATION = "cancellation"
    RETRY = "retry"
    LOCAL = "local"
    EXTERNAL = "external"
    MULTIMODAL = "multimodal"


@dataclass
class ProviderCapability:
    """What a provider/runtime can do."""
    capability: CapabilityType
    required_features: list[str] = field(default_factory=list)
    supported_regimes: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    supported_asset_types: list[str] = field(default_factory=list)
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    deterministic: bool = False
    supports_cancellation: bool = False
    supports_streaming: bool = False
    supports_structured_output: bool = False
    cost_per_1k_tokens: float = 0.0
    latency_class: str = "low"  # low | medium | high

    def has_capability(self, cap: CapabilityType) -> bool:
        return self.capability == cap


@dataclass
class ProviderMetadata:
    """Metadata about a provider/runtime."""
    provider_id: str = ""
    runtime_id: str = ""
    runtime_type: RuntimeType = RuntimeType.DETERMINISTIC_LOCAL
    provider_name: str = ""
    runtime_version: str = "1.0.0"
    adapter_version: str = "1.0.0"
    capabilities: list[ProviderCapability] = field(default_factory=list)
    status: ProviderStatus = ProviderStatus.HEALTHY
    max_retries: int = 3
    timeout_seconds: int = 30
    cost_policy: str = "research_only"  # research_only | production
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.provider_id:
            self.provider_id = f"PRV-{uuid.uuid4().hex[:8].upper()}"
        if not self.runtime_id:
            self.runtime_id = f"RT-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "runtime_id": self.runtime_id,
            "runtime_type": self.runtime_type.value,
            "provider_name": self.provider_name,
            "runtime_version": self.runtime_version,
            "adapter_version": self.adapter_version,
            "capabilities": [c.capability.value for c in self.capabilities],
            "status": self.status.value,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "cost_policy": self.cost_policy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProviderRuntime:
    """Abstract base for all provider runtimes.

    Every runtime must implement:
    - health() → ProviderStatus
    - execute(agent_id, context, ...) → AgentResult
    - cancel(execution_id) → bool
    - metadata() → ProviderMetadata

    MarketHQ core NEVER depends on a specific provider.
    Only on this abstraction.
    """

    def __init__(self, metadata: ProviderMetadata) -> None:
        self._metadata = metadata
        self._execution_count = 0
        self._failure_count = 0

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def health(self) -> ProviderStatus:
        """Check runtime health."""
        return self._metadata.status

    def execute(
        self,
        agent_id: str,
        agent_version: str,
        context: Any,
        timeout_seconds: int = 30,
        execution_id: str = "",
    ) -> Any:
        """Execute an agent. Returns AgentResult or compatible output."""
        raise NotImplementedError("Subclasses must implement execute()")

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        raise NotImplementedError("Subclasses must implement cancel()")

    def record_success(self) -> None:
        self._execution_count += 1

    def record_failure(self) -> None:
        self._failure_count += 1

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def failure_rate(self) -> float:
        total = self._execution_count + self._failure_count
        if total == 0:
            return 0.0
        return round(self._failure_count / total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self._metadata.to_dict(),
            "execution_count": self._execution_count,
            "failure_count": self._failure_count,
            "failure_rate": self.failure_rate,
        }


# ── Default provider metadata ──────────────────────────────────────────

DEFAULT_DETERMINISTIC_METADATA = ProviderMetadata(
    provider_id="PRV-DETERMINISTIC",
    runtime_id="RT-LOCAL-001",
    runtime_type=RuntimeType.DETERMINISTIC_LOCAL,
    provider_name="MarketHQ Deterministic Runtime",
    runtime_version="1.0.0",
    adapter_version="1.0.0",
    capabilities=[
        ProviderCapability(
            capability=CapabilityType.DETERMINISTIC,
            deterministic=True,
            supports_cancellation=False,
            latency_class="low",
        ),
        ProviderCapability(
            capability=CapabilityType.LOCAL,
            latency_class="low",
        ),
    ],
    status=ProviderStatus.HEALTHY,
    max_retries=0,
    timeout_seconds=60,
    cost_policy="research_only",
)

DEFAULT_MOCK_METADATA = ProviderMetadata(
    provider_id="PRV-MOCK",
    runtime_id="RT-MOCK-001",
    runtime_type=RuntimeType.MOCK,
    provider_name="MarketHQ Mock Provider",
    runtime_version="1.0.0",
    adapter_version="1.0.0",
    capabilities=[
        ProviderCapability(
            capability=CapabilityType.DETERMINISTIC,
            deterministic=True,
            supports_cancellation=True,
            supports_structured_output=True,
            latency_class="low",
        ),
        ProviderCapability(
            capability=CapabilityType.LOCAL,
            latency_class="low",
        ),
    ],
    status=ProviderStatus.HEALTHY,
    max_retries=3,
    timeout_seconds=30,
    cost_policy="research_only",
)