# -*- coding: utf-8 -*-
"""Phase I — Agent Identity / Capability Model.

Extends existing AgentRegistry with explicit capability profiles.
No duplication of AgentRuntime / AgentRegistry / Brain.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class CapabilityType(Enum):
    TREND_DIRECTION = "trend_direction"
    TREND_STRENGTH = "trend_strength"
    MOMENTUM = "momentum"
    REVERSAL = "reversal"
    BREAKOUT = "breakout"
    LIQUIDITY = "liquidity"
    STRUCTURE = "structure"
    VOLATILITY = "volatility"
    REGIME = "regime"
    OPPORTUNITY = "opportunity"
    SETUP_SYNTHESIS = "setup_synthesis"
    VALIDATION = "validation"
    CRITIC = "critic"


@dataclass
class AgentCapability:
    """What an agent can do."""
    capability: CapabilityType
    required_features: list[str] = field(default_factory=list)
    optional_features: list[str] = field(default_factory=list)
    supported_assets: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    supported_regimes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    data_dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "required_features": self.required_features,
            "optional_features": self.optional_features,
            "supported_assets": self.supported_assets,
            "supported_timeframes": self.supported_timeframes,
            "supported_regimes": self.supported_regimes,
            "limitations": self.limitations,
            "data_dependencies": self.data_dependencies,
        }


@dataclass
class AgentProfile:
    """Research agent identity + capability profile."""
    agent_id: str
    agent_name: str
    version: str
    role: str = "research"
    family: str = ""
    capabilities: list[CapabilityType] = field(default_factory=list)
    capability_details: dict[str, AgentCapability] = field(default_factory=dict)
    required_features: list[str] = field(default_factory=list)
    optional_features: list[str] = field(default_factory=list)
    supported_assets: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    supported_regimes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    data_dependencies: list[str] = field(default_factory=list)
    runtime_binding: str = "hermes"
    status: AgentStatus = AgentStatus.READY
    reliability_ref: str = ""
    last_run: str = ""
    health_state: str = "healthy"
    failure_count: int = 0
    timeout_count: int = 0
    empty_output_count: int = 0
    unavailable_dependency_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "version": self.version,
            "role": self.role,
            "family": self.family,
            "capabilities": [c.value for c in self.capabilities],
            "required_features": self.required_features,
            "optional_features": self.optional_features,
            "supported_assets": self.supported_assets,
            "supported_timeframes": self.supported_timeframes,
            "supported_regimes": self.supported_regimes,
            "limitations": self.limitations,
            "data_dependencies": self.data_dependencies,
            "runtime_binding": self.runtime_binding,
            "status": self.status.value,
            "reliability_ref": self.reliability_ref,
            "last_run": self.last_run,
            "health_state": self.health_state,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "empty_output_count": self.empty_output_count,
            "unavailable_dependency_count": self.unavailable_dependency_count,
        }