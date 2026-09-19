# -*- coding: utf-8 -*-
"""Phase J9 — AI Provider Gateway Domain Models.

ModelSpec, ProviderSpec, AIRequest, AIResponse,
ProviderHealth, RoutingDecision, FallbackEvent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Tier(Enum):
    FREE = "FREE"
    FREE_TIER = "FREE_TIER"
    PAID = "PAID"
    UNKNOWN = "UNKNOWN"


class ProviderState(Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN = "UNKNOWN"


class ErrorType(Enum):
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    TRANSIENT = "TRANSIENT"
    UNKNOWN = "UNKNOWN"


class RoutingMode(Enum):
    AUTO = "AUTO"
    FREE_FIRST = "FREE_FIRST"
    PAID_FIRST = "PAID_FIRST"
    SPECIFIC_PROVIDER = "SPECIFIC_PROVIDER"
    SPECIFIC_MODEL = "SPECIFIC_MODEL"
    CHEAPEST_AVAILABLE = "CHEAPEST_AVAILABLE"
    BEST_AVAILABLE = "BEST_AVAILABLE"
    LOCAL_FIRST = "LOCAL_FIRST"


class Purpose(Enum):
    RESEARCH = "RESEARCH"
    ANALYSIS = "ANALYSIS"
    SYNTHESIS = "SYNTHESIS"
    CRITIQUE = "CRITIQUE"
    CLASSIFICATION = "CLASSIFICATION"
    EXTRACTION = "EXTRACTION"
    CHAT = "CHAT"
    SITUATION_REPORT = "SITUATION_REPORT"


@dataclass
class ModelSpec:
    model_id: str
    provider_id: str
    display_name: str = ""
    model_family: str = ""
    tier: Tier = Tier.UNKNOWN
    input_cost: float = 0.0
    output_cost: float = 0.0
    context_window: int = 0
    capabilities: list[str] = field(default_factory=list)
    reasoning: bool = False
    structured_output: bool = False
    tool_support: bool = False
    availability: bool = True
    enabled: bool = True
    priority: int = 0
    timeout: int = 30
    max_retries: int = 3
    version: str = "1.0.0"
    pricing_status: str = "UNKNOWN"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "model_family": self.model_family,
            "tier": self.tier.value,
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "context_window": self.context_window,
            "capabilities": self.capabilities,
            "reasoning": self.reasoning,
            "structured_output": self.structured_output,
            "tool_support": self.tool_support,
            "availability": self.availability,
            "enabled": self.enabled,
            "priority": self.priority,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "version": self.version,
            "pricing_status": self.pricing_status,
            "metadata": self.metadata,
        }


@dataclass
class ProviderSpec:
    provider_id: str
    name: str
    type: str = "llm"
    enabled: bool = True
    tier: Tier = Tier.UNKNOWN
    auth_required: bool = True
    configured: bool = False
    state: ProviderState = ProviderState.UNKNOWN
    capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    priority: int = 0
    rate_limit: int = 0
    last_error: str = ""
    last_success: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "tier": self.tier.value,
            "auth_required": self.auth_required,
            "configured": self.configured,
            "state": self.state.value,
            "capabilities": self.capabilities,
            "models": self.models,
            "priority": self.priority,
            "rate_limit": self.rate_limit,
            "last_error": self.last_error,
            "last_success": self.last_success,
            "metadata": self.metadata,
        }


@dataclass
class AIRequest:
    request_id: str = ""
    agent_id: str = ""
    task_id: str = ""
    team_id: Optional[str] = None
    purpose: Purpose = Purpose.RESEARCH
    system_instruction: str = ""
    user_input: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    requested_capabilities: list[str] = field(default_factory=list)
    preferred_provider: Optional[str] = None
    preferred_model: Optional[str] = None
    allowed_tiers: list[str] = field(default_factory=list)
    max_cost: float = 0.0
    max_latency: int = 0
    fallback_enabled: bool = True
    structured_output_required: bool = False
    timeout: int = 30
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        d["purpose"] = self.purpose.value
        return d


@dataclass
class ProviderResponse:
    success: bool = False
    provider_id: str = ""
    model_id: str = ""
    output: str = ""
    structured_output: Any = None
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""
    error_type: str = ""
    retryable: bool = False
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "output": self.output[:500] if self.output else "",
            "structured_output": self.structured_output,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "error_type": self.error_type,
            "retryable": self.retryable,
            "request_id": self.request_id,
            "metadata": self.metadata,
        }


@dataclass
class ProviderHealth:
    provider_id: str
    status: ProviderState = ProviderState.UNKNOWN
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_success: str = ""
    last_failure: str = ""
    last_error_type: str = ""
    latency_ms: int = 0
    availability: float = 0.0
    cooldown_until: str = ""
    health_score: float = 0.0
    total_requests: int = 0
    total_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "last_error_type": self.last_error_type,
            "latency_ms": self.latency_ms,
            "availability": self.availability,
            "cooldown_until": self.cooldown_until,
            "health_score": self.health_score,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
        }


@dataclass
class RoutingDecision:
    route_id: str = ""
    request_id: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    mode: str = ""
    candidates_evaluated: int = 0
    fallback_used: bool = False
    fallback_depth: int = 0
    reasoning: str = ""
    timestamp: str = ""
    determinism_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "request_id": self.request_id,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "mode": self.mode,
            "candidates_evaluated": self.candidates_evaluated,
            "fallback_used": self.fallback_used,
            "fallback_depth": self.fallback_depth,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "determinism_key": self.determinism_key,
        }


@dataclass
class FallbackEvent:
    event_id: str = ""
    request_id: str = ""
    from_provider: str = ""
    to_provider: str = ""
    reason: str = ""
    error_type: str = ""
    timestamp: str = ""
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "from_provider": self.from_provider,
            "to_provider": self.to_provider,
            "reason": self.reason,
            "error_type": self.error_type,
            "timestamp": self.timestamp,
            "success": self.success,
        }