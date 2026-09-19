# -*- coding: utf-8 -*-
"""Agent Router — Phase J3.

Central routing component: decides which runtime/provider handles an execution.
Deterministic capability-based routing with health-aware fallback.

Never makes financial/political decisions. Only selects execution backend.

Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from provider_adapter import ProviderRuntime, ProviderStatus, RuntimeType, CapabilityType, ProviderCapability
from deterministic_runtime import DeterministicRuntime, DeterministicRunStatus
from external_runtime import ExternalProviderRuntime, MockProviderRuntime, MockBehavior


class RouteStatus(Enum):
    ROUTED = "ROUTED"
    ROUTING_REJECTED = "ROUTING_REJECTED"
    FALLBACK_USED = "FALLBACK_USED"
    NO_PROVIDER = "NO_PROVIDER"
    HEALTH_DEGRADED = "HEALTH_DEGRADED"


@dataclass
class RouteDecision:
    """Result of a routing decision."""
    route_id: str = ""
    agent_id: str = ""
    task_id: str = ""
    selected_runtime: str = ""
    selected_provider: str = ""
    selected_runtime_type: str = ""
    status: RouteStatus = RouteStatus.ROUTED
    score: float = 0.0
    candidates_evaluated: int = 0
    fallback_reason: str = ""
    reasoning: str = ""
    correlation_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "selected_runtime": self.selected_runtime,
            "selected_provider": self.selected_provider,
            "selected_runtime_type": self.selected_runtime_type,
            "status": self.status.value,
            "score": self.score,
            "candidates_evaluated": self.candidates_evaluated,
            "fallback_reason": self.fallback_reason,
            "reasoning": self.reasoning,
            "correlation_id": self.correlation_id,
        }


class AgentRouter:
    """Routes agent execution requests to appropriate runtimes/providers.

    Routing criteria (deterministic, scored):
    1. Capability match
    2. Required features availability
    3. Runtime capability
    4. Provider availability
    5. Model availability
    6. Context requirements
    7. Latency requirement
    8. Cost policy
    9. Reliability/health
    10. Explicit task constraint

    Tie-breaking: deterministic alphabetical by runtime_id.
    No random selection.
    """

    def __init__(self) -> None:
        self._runtimes: dict[str, ProviderRuntime] = {}
        self._runtime_capabilities: dict[str, list[str]] = {}
        self._fallback_chain: list[str] = []

    def register_runtime(self, runtime: ProviderRuntime) -> None:
        """Register a runtime/provider."""
        self._runtimes[runtime.metadata.runtime_id] = runtime
        # Register capabilities
        for cap in runtime.metadata.capabilities:
            if cap.capability.value not in self._runtime_capabilities:
                self._runtime_capabilities[cap.capability.value] = []
            if runtime.metadata.runtime_id not in self._runtime_capabilities[cap.capability.value]:
                self._runtime_capabilities[cap.capability.value].append(runtime.metadata.runtime_id)

    def unregister_runtime(self, runtime_id: str) -> bool:
        """Unregister a runtime."""
        if runtime_id in self._runtimes:
            del self._runtimes[runtime_id]
            return True
        return False

    def get_runtime(self, runtime_id: str) -> ProviderRuntime | None:
        """Get runtime by ID."""
        return self._runtimes.get(runtime_id)

    def list_runtimes(self) -> list[dict[str, Any]]:
        """List all registered runtimes."""
        return [
            {
                "runtime_id": rid,
                "provider_id": rt.metadata.provider_id,
                "runtime_type": rt.metadata.runtime_type.value,
                "status": rt.metadata.status.value,
                "failure_rate": rt.failure_rate,
            }
            for rid, rt in self._runtimes.items()
        ]

    def set_fallback_chain(self, runtime_ids: list[str]) -> None:
        """Set fallback chain for degraded provider scenarios."""
        self._fallback_chain = runtime_ids

    def route(
        self,
        agent_id: str,
        task_id: str = "",
        required_capability: str = "",
        required_features: list[str] | None = None,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "",
        latency_requirement: str = "low",
        cost_policy: str = "research_only",
        deterministic_only: bool = True,
        context_version: str = "",
        explicit_runtime: str = "",
    ) -> RouteDecision:
        """Route an execution request to the best matching runtime."""
        import uuid
        from datetime import datetime, timezone

        route_id = f"ROUTE-{uuid.uuid4().hex[:8].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()
        required_features = required_features or []

        # If explicit runtime requested, try it first
        if explicit_runtime and explicit_runtime in self._runtimes:
            runtime = self._runtimes[explicit_runtime]
            if runtime.health() == ProviderStatus.HEALTHY:
                return RouteDecision(
                    route_id=route_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    selected_runtime=explicit_runtime,
                    selected_provider=runtime.metadata.provider_id,
                    selected_runtime_type=runtime.metadata.runtime_type.value,
                    status=RouteStatus.ROUTED,
                    score=1.0,
                    candidates_evaluated=1,
                    reasoning=f"Explicit runtime {explicit_runtime} selected",
                    correlation_id=route_id,
                    created_at=created_at,
                )
            # Explicit runtime unhealthy → fallback
            fallback = self._find_fallback(required_capability, required_features, latency_requirement, cost_policy, deterministic_only)
            if fallback:
                return RouteDecision(
                    route_id=route_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    selected_runtime=fallback.metadata.runtime_id,
                    selected_provider=fallback.metadata.provider_id,
                    selected_runtime_type=fallback.metadata.runtime_type.value,
                    status=RouteStatus.FALLBACK_USED,
                    score=0.5,
                    candidates_evaluated=1,
                    fallback_reason=f"Explicit runtime {explicit_runtime} unhealthy, fallback to {fallback.metadata.runtime_id}",
                    reasoning=f"Fallback: {explicit_runtime} degraded",
                    correlation_id=route_id,
                    created_at=created_at,
                )
            return RouteDecision(
                route_id=route_id, agent_id=agent_id, task_id=task_id,
                status=RouteStatus.NO_PROVIDER,
                reasoning=f"No healthy provider available, explicit={explicit_runtime}",
                correlation_id=route_id, created_at=created_at,
            )

        # Normal routing: find best candidate
        candidates = self._find_candidates(required_capability, required_features, latency_requirement, cost_policy, deterministic_only)

        if not candidates:
            # Try fallback chain
            fallback = self._find_fallback(required_capability, required_features, latency_requirement, cost_policy, deterministic_only)
            if fallback:
                return RouteDecision(
                    route_id=route_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    selected_runtime=fallback.metadata.runtime_id,
                    selected_provider=fallback.metadata.provider_id,
                    selected_runtime_type=fallback.metadata.runtime_type.value,
                    status=RouteStatus.FALLBACK_USED,
                    score=0.3,
                    candidates_evaluated=0,
                    fallback_reason="No direct match, used fallback chain",
                    reasoning=f"Fallback selected: {fallback.metadata.runtime_id}",
                    correlation_id=route_id,
                    created_at=created_at,
                )
            return RouteDecision(
                route_id=route_id, agent_id=agent_id, task_id=task_id,
                status=RouteStatus.NO_PROVIDER,
                reasoning=f"No provider for capability '{required_capability}'",
                correlation_id=route_id, created_at=created_at,
            )

        # Sort deterministically: score desc, then runtime_id alphabetical
        candidates.sort(key=lambda c: (-c[1], c[0]))
        best_runtime_id, best_score = candidates[0]
        best_runtime = self._runtimes[best_runtime_id]

        # Check health
        if best_runtime.health() != ProviderStatus.HEALTHY:
            # Try fallback
            fallback = self._find_fallback(required_capability, required_features, latency_requirement, cost_policy, deterministic_only)
            if fallback:
                return RouteDecision(
                    route_id=route_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    selected_runtime=fallback.metadata.runtime_id,
                    selected_provider=fallback.metadata.provider_id,
                    selected_runtime_type=fallback.metadata.runtime_type.value,
                    status=RouteStatus.FALLBACK_USED,
                    score=best_score * 0.5,
                    candidates_evaluated=len(candidates),
                    fallback_reason=f"Best runtime {best_runtime_id} unhealthy",
                    reasoning=f"Fallback: {best_runtime_id} degraded → {fallback.metadata.runtime_id}",
                    correlation_id=route_id,
                    created_at=created_at,
                )
            return RouteDecision(
                route_id=route_id, agent_id=agent_id, task_id=task_id,
                status=RouteStatus.HEALTH_DEGRADED,
                score=best_score,
                candidates_evaluated=len(candidates),
                reasoning=f"Best runtime {best_runtime_id} degraded, no fallback",
                correlation_id=route_id, created_at=created_at,
            )

        return RouteDecision(
            route_id=route_id,
            agent_id=agent_id,
            task_id=task_id,
            selected_runtime=best_runtime_id,
            selected_provider=best_runtime.metadata.provider_id,
            selected_runtime_type=best_runtime.metadata.runtime_type.value,
            status=RouteStatus.ROUTED,
            score=best_score,
            candidates_evaluated=len(candidates),
            reasoning=f"Routed to {best_runtime_id} (score={best_score:.2f})",
            correlation_id=route_id,
            created_at=created_at,
        )

    def _find_candidates(
        self,
        required_capability: str,
        required_features: list[str],
        latency_requirement: str,
        cost_policy: str,
        deterministic_only: bool,
    ) -> list[tuple[str, float]]:
        """Find candidate runtimes matching the requirements."""
        candidates = []
        for runtime_id, runtime in self._runtimes.items():
            if runtime.health() != ProviderStatus.HEALTHY:
                continue

            score = 0.0

            # Capability match
            caps = [c.capability.value for c in runtime.metadata.capabilities]
            if required_capability in caps:
                score += 0.4
            elif not required_capability:
                score += 0.2

            # Feature availability
            if required_features:
                feature_caps = [c for c in runtime.metadata.capabilities if c.required_features]
                available = set()
                for fc in feature_caps:
                    available.update(fc.required_features)
                feature_match = sum(1 for f in required_features if f in available)
                score += (feature_match / len(required_features)) * 0.3

            # Latency requirement
            for cap in runtime.metadata.capabilities:
                if cap.latency_class == latency_requirement:
                    score += 0.15
                    break

            # Cost policy — check metadata, not capability
            if runtime.metadata.cost_policy == cost_policy:
                score += 0.1

            # Deterministic preference
            if deterministic_only:
                for cap in runtime.metadata.capabilities:
                    if cap.deterministic:
                        score += 0.05
                        break

            candidates.append((runtime_id, score))

        return candidates

    def _find_fallback(
        self,
        required_capability: str,
        required_features: list[str],
        latency_requirement: str,
        cost_policy: str,
        deterministic_only: bool,
    ) -> ProviderRuntime | None:
        """Find a fallback runtime from the fallback chain."""
        for runtime_id in self._fallback_chain:
            runtime = self._runtimes.get(runtime_id)
            if runtime and runtime.health() == ProviderStatus.HEALTHY:
                return runtime
        # If no explicit fallback chain, try any healthy deterministic runtime
        for runtime_id, runtime in sorted(self._runtimes.items()):
            if runtime.health() == ProviderStatus.HEALTHY:
                for cap in runtime.metadata.capabilities:
                    if cap.deterministic:
                        return runtime
        return None


# ── Default router with deterministic runtime ──────────────────────────

def create_default_router() -> AgentRouter:
    """Create a default AgentRouter with deterministic local runtime."""
    router = AgentRouter()
    deterministic = DeterministicRuntime()
    router.register_runtime(deterministic)
    router.set_fallback_chain([deterministic.metadata.runtime_id])
    return router