# -*- coding: utf-8 -*-
"""Task Router — Phase J1.

Deterministic capability-based routing for research tasks.
Routes tasks to appropriate agents based on capability match.

No random selection. Deterministic tie-breaking by agent_id alphabetical order.
Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RoutingStatus(Enum):
    ROUTED = "ROUTED"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    NO_CANDIDATE = "NO_CANDIDATE"
    DEGRADED = "DEGRADED"


@dataclass
class CapabilityDescriptor:
    capability_id: str
    description: str = ""
    required_features: list[str] = field(default_factory=list)
    optional_features: list[str] = field(default_factory=list)
    supported_regimes: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    supported_asset_types: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    cost_class: str = "low"  # low | medium | high
    deterministic: bool = True
    research_only: bool = True


@dataclass
class RoutingCandidate:
    agent_id: str
    agent_version: str
    capability: CapabilityDescriptor
    score: float = 0.0
    feature_availability: dict[str, bool] = field(default_factory=dict)


@dataclass
class RoutingResult:
    task_id: str
    agent_id: str
    agent_version: str
    capability_id: str
    status: RoutingStatus = RoutingStatus.ROUTED
    score: float = 0.0
    candidates_evaluated: int = 0
    reasoning: str = ""


class TaskRouter:
    """Deterministic capability-based task router.

    Routes research tasks to the best-matching agent based on:
    1. Capability match
    2. Required feature availability
    3. Symbol support
    4. Timeframe support
    5. Regime support
    6. Agent health
    7. Version compatibility

    Tie-breaking: deterministic alphabetical by agent_id.
    No random selection.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}
        self._agent_capabilities: dict[str, list[str]] = {}  # agent_id -> capability_ids

    def register_capability(
        self,
        capability_id: str,
        description: str = "",
        required_features: list[str] | None = None,
        optional_features: list[str] | None = None,
        supported_regimes: list[str] | None = None,
        supported_timeframes: list[str] | None = None,
        supported_asset_types: list[str] | None = None,
        dependencies: list[str] | None = None,
        cost_class: str = "low",
        deterministic: bool = True,
        research_only: bool = True,
    ) -> None:
        cap = CapabilityDescriptor(
            capability_id=capability_id,
            description=description,
            required_features=required_features or [],
            optional_features=optional_features or [],
            supported_regimes=supported_regimes or [],
            supported_timeframes=supported_timeframes or [],
            supported_asset_types=supported_asset_types or [],
            dependencies=dependencies or [],
            cost_class=cost_class,
            deterministic=deterministic,
            research_only=research_only,
        )
        self._capabilities[capability_id] = cap

    def register_agent_capability(self, agent_id: str, capability_id: str) -> None:
        if agent_id not in self._agent_capabilities:
            self._agent_capabilities[agent_id] = []
        if capability_id not in self._agent_capabilities[agent_id]:
            self._agent_capabilities[agent_id].append(capability_id)

    def find_candidates(
        self,
        required_capability: str,
        available_features: dict[str, bool] | None = None,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "",
        min_score: float = 0.0,
    ) -> list[RoutingCandidate]:
        """Find agents that can handle the required capability."""
        available_features = available_features or {}
        candidates = []

        for agent_id, cap_ids in self._agent_capabilities.items():
            if required_capability not in cap_ids:
                continue

            cap = self._capabilities.get(required_capability)
            if cap is None:
                continue

            score = self._score_candidate(
                cap, available_features, symbol, timeframe, regime,
            )

            if score >= min_score:
                candidates.append(RoutingCandidate(
                    agent_id=agent_id,
                    agent_version="1.0",
                    capability=cap,
                    score=score,
                    feature_availability=available_features,
                ))

        # Deterministic sort: score descending, then agent_id alphabetical
        candidates.sort(key=lambda c: (-c.score, c.agent_id))
        return candidates

    def route(
        self,
        task_id: str,
        required_capability: str,
        available_features: dict[str, bool] | None = None,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "",
        agent_version: str = "",
    ) -> RoutingResult:
        """Route a task to the best matching agent."""
        candidates = self.find_candidates(
            required_capability, available_features, symbol, timeframe, regime,
        )

        if not candidates:
            # Check if capability exists at all
            if required_capability not in self._capabilities:
                return RoutingResult(
                    task_id=task_id,
                    agent_id="",
                    agent_version="",
                    capability_id=required_capability,
                    status=RoutingStatus.CAPABILITY_MISMATCH,
                    candidates_evaluated=0,
                    reasoning=f"Capability '{required_capability}' not registered",
                )
            return RoutingResult(
                task_id=task_id,
                agent_id="",
                agent_version="",
                capability_id=required_capability,
                status=RoutingStatus.NO_CANDIDATE,
                candidates_evaluated=0,
                reasoning=f"No agent registered for capability '{required_capability}'",
            )

        best = candidates[0]

        # Check agent version compatibility
        if agent_version and best.agent_version != agent_version:
            return RoutingResult(
                task_id=task_id,
                agent_id=best.agent_id,
                agent_version=best.agent_version,
                capability_id=required_capability,
                status=RoutingStatus.DEGRADED,
                score=best.score,
                candidates_evaluated=len(candidates),
                reasoning=f"Version mismatch: need {agent_version}, have {best.agent_version}",
            )

        return RoutingResult(
            task_id=task_id,
            agent_id=best.agent_id,
            agent_version=best.agent_version,
            capability_id=required_capability,
            status=RoutingStatus.ROUTED,
            score=best.score,
            candidates_evaluated=len(candidates),
            reasoning=f"Routed to {best.agent_id} (score={best.score:.2f})",
        )

    def _score_candidate(
        self,
        cap: CapabilityDescriptor,
        available_features: dict[str, bool],
        symbol: str,
        timeframe: str,
        regime: str,
    ) -> float:
        score = 0.0

        # Required features
        required_available = sum(
            1 for f in cap.required_features if available_features.get(f, False)
        )
        if cap.required_features:
            score += (required_available / len(cap.required_features)) * 0.4

        # Optional features
        optional_available = sum(
            1 for f in cap.optional_features if available_features.get(f, False)
        )
        if cap.optional_features:
            score += (optional_available / len(cap.optional_features)) * 0.1

        # Regime support
        if cap.supported_regimes:
            if regime in cap.supported_regimes:
                score += 0.2
            else:
                score += 0.05

        # Timeframe support
        if cap.supported_timeframes:
            if timeframe in cap.supported_timeframes:
                score += 0.15
            else:
                score += 0.02

        # Asset type support
        if cap.supported_asset_types:
            asset_type = symbol.split(".")[-1] if "." in symbol else symbol
            if asset_type in cap.supported_asset_types:
                score += 0.1
            else:
                score += 0.01

        return round(score, 4)


# Pre-built capability descriptors for strategy research agents
DEFAULT_CAPABILITIES = {
    "trend_analysis": CapabilityDescriptor(
        capability_id="trend_analysis",
        description="Analyze trend direction, strength, and persistence",
        required_features=["EMA_FAST", "EMA_SLOW", "ADX", "ATR"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "breakout_analysis": CapabilityDescriptor(
        capability_id="breakout_analysis",
        description="Detect breakout opportunities from consolidation",
        required_features=["BB_UPPER", "BB_LOWER", "VOLUME_RATIO", "ATR"],
        supported_regimes=["RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "reversal_analysis": CapabilityDescriptor(
        capability_id="reversal_analysis",
        description="Identify potential reversal points",
        required_features=["RSI", "MACD", "SMA_FAST", "SMA_SLOW"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "momentum_analysis": CapabilityDescriptor(
        capability_id="momentum_analysis",
        description="Assess momentum strength and direction",
        required_features=["RSI", "MACD", "VOLUME_RATIO"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "volatility_analysis": CapabilityDescriptor(
        capability_id="volatility_analysis",
        description="Analyze volatility context and risk",
        required_features=["ATR", "ATR_PCT", "VOLUME_RATIO"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "liquidity_analysis": CapabilityDescriptor(
        capability_id="liquidity_analysis",
        description="Assess liquidity balance and levels",
        required_features=["donchian_high", "donchian_low"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
    "structure_analysis": CapabilityDescriptor(
        capability_id="structure_analysis",
        description="Analyze market structure (BOS, CHoCH, liquidity)",
        required_features=["structure", "donchian_high", "donchian_low"],
        supported_regimes=["TRENDING", "RANGE_HIGH", "RANGE_LOW", "UNKNOWN"],
        supported_timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
        cost_class="low",
    ),
}
