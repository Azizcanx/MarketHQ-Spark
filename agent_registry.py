# -*- coding: utf-8 -*-
"""Agent Adapter Registry — deterministic, version-aware adapter discovery.

Maps agent_id → adapter instance. Explicit registration, no auto-discovery.
"""

from __future__ import annotations

from typing import Any

from agent_contract import BaseAgentAdapter


class AgentRegistry:
    """Central registry for agent adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAgentAdapter] = {}
        self._versions: dict[str, str] = {}

    def register(
        self,
        agent_id: str,
        adapter: BaseAgentAdapter,
        version: str = "1.0.0",
    ) -> None:
        """Register an adapter for an agent_id."""
        self._adapters[agent_id] = adapter
        self._versions[agent_id] = version

    def get(self, agent_id: str) -> BaseAgentAdapter | None:
        """Get adapter by agent_id. Returns None if not found."""
        return self._adapters.get(agent_id)

    def get_version(self, agent_id: str) -> str:
        """Get adapter version for an agent_id."""
        return self._versions.get(agent_id, "unknown")

    def list_agents(self) -> list[dict[str, str]]:
        """List all registered agents with metadata."""
        return [
            {
                "agent_id": aid,
                "version": self._versions[aid],
                "adapter_type": type(adapter).__name__,
                "source_engine": adapter.source_engine,
            }
            for aid, adapter in self._adapters.items()
        ]

    def unregister(self, agent_id: str) -> bool:
        """Remove an adapter. Returns True if it existed."""
        if agent_id in self._adapters:
            del self._adapters[agent_id]
            del self._versions[agent_id]
            return True
        return False

    def has(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._adapters

    def count(self) -> int:
        """Number of registered agents."""
        return len(self._adapters)

    def clear(self) -> None:
        """Remove all adapters."""
        self._adapters.clear()
        self._versions.clear()

    # ── Phase J1 capability query methods ──────────────────────

    def find_by_capability(self, capability: str) -> list[dict[str, Any]]:
        """Find agents that support a specific capability."""
        results = []
        for aid, adapter in self._adapters.items():
            if hasattr(adapter, "capabilities") and capability in adapter.capabilities:
                results.append({
                    "agent_id": aid,
                    "version": self._versions[aid],
                    "adapter_type": type(adapter).__name__,
                    "source_engine": adapter.source_engine,
                })
        return results

    def find_by_strategy_family(self, family: str) -> list[dict[str, Any]]:
        """Find agents by strategy family."""
        results = []
        for aid, adapter in self._adapters.items():
            if hasattr(adapter, "strategy_family") and adapter.strategy_family == family:
                results.append({
                    "agent_id": aid,
                    "version": self._versions[aid],
                    "adapter_type": type(adapter).__name__,
                    "source_engine": adapter.source_engine,
                })
        return results

    def find_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """Find agents that support a specific symbol."""
        results = []
        for aid, adapter in self._adapters.items():
            if hasattr(adapter, "supported_symbols"):
                if symbol in adapter.supported_symbols:
                    results.append({
                        "agent_id": aid,
                        "version": self._versions[aid],
                        "adapter_type": type(adapter).__name__,
                        "source_engine": adapter.source_engine,
                    })
        return results

    def find_by_timeframe(self, timeframe: str) -> list[dict[str, Any]]:
        """Find agents that support a specific timeframe."""
        results = []
        for aid, adapter in self._adapters.items():
            if hasattr(adapter, "supported_timeframes"):
                if timeframe in adapter.supported_timeframes:
                    results.append({
                        "agent_id": aid,
                        "version": self._versions[aid],
                        "adapter_type": type(adapter).__name__,
                        "source_engine": adapter.source_engine,
                    })
        return results

    def get_health(self, agent_id: str) -> dict[str, Any] | None:
        """Get health info for a specific agent."""
        adapter = self._adapters.get(agent_id)
        if adapter is None:
            return None
        return {
            "agent_id": agent_id,
            "version": self._versions[agent_id],
            "status": getattr(adapter, "status", "unknown"),
        }


# Global default registry
_default_registry = AgentRegistry()


def get_default_registry() -> AgentRegistry:
    """Get the global default registry."""
    return _default_registry


def register(
    agent_id: str, adapter: BaseAgentAdapter, version: str = "1.0.0"
) -> None:
    """Register an adapter in the global registry."""
    _default_registry.register(agent_id, adapter, version)


def get(agent_id: str) -> BaseAgentAdapter | None:
    """Get an adapter from the global registry."""
    return _default_registry.get(agent_id)


def list_agents() -> list[dict[str, str]]:
    """List all registered agents."""
    return _default_registry.list_agents()