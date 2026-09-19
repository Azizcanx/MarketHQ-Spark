# -*- coding: utf-8 -*-
"""Strategy Research Agent Registry — Phase D.

Registers all 7 strategy research agents in the AgentRegistry.
Uses explicit registration (no auto-discovery).

Usage:
    from strategy_research_registry import get_strategy_registry
    registry = get_strategy_registry()
    run = runtime.run("strategy_trend", "THYAO.IS", "1h")
"""

from __future__ import annotations

from agent_registry import AgentRegistry
from strategy_research_agents import STRATEGY_AGENTS


def get_strategy_registry() -> AgentRegistry:
    """Create and populate registry with all strategy research agents."""
    registry = AgentRegistry()
    for agent_id, adapter_cls in STRATEGY_AGENTS.items():
        registry.register(agent_id, adapter_cls, version="1.0")
    return registry


def get_agent_ids() -> list[str]:
    """Return all registered strategy agent IDs."""
    return list(STRATEGY_AGENTS.keys())


# Default global registry
_default_registry = get_strategy_registry()


def get_default_registry() -> AgentRegistry:
    return _default_registry