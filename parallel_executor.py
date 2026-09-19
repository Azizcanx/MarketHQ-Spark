# -*- coding: utf-8 -*-
"""Parallel Executor — Phase J2.

Single-process deterministic parallel execution for independent agents.
All agents share the same feature snapshot.
No race conditions — deterministic ordering.

Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParallelTask:
    """A single parallel task for an agent."""
    agent_id: str = ""
    agent_version: str = ""
    capability: str = ""
    feature_snapshot_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    context_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelResult:
    """Result of a parallel agent execution."""
    agent_id: str = ""
    agent_version: str = ""
    capability: str = ""
    status: str = "PENDING"
    result: Any = None
    error: str = ""
    execution_time_ms: int = 0
    evidence_id: str = ""
    created_at: str = ""


class ParallelExecutor:
    """Deterministic parallel execution of independent agents.

    Agents sharing the same feature snapshot execute in deterministic order.
    No race conditions — single-process, deterministic ordering by agent_id.
    """

    def __init__(self) -> None:
        self._results: list[ParallelResult] = []
        self._executed_agents: list[str] = []

    def execute_parallel(
        self,
        tasks: list[ParallelTask],
        executor_fn,
    ) -> list[ParallelResult]:
        """Execute tasks in deterministic order (alphabetical by agent_id)."""
        # Sort deterministically by agent_id
        tasks.sort(key=lambda t: t.agent_id)

        self._results = []
        self._executed_agents = []

        for task in tasks:
            if task.agent_id in self._executed_agents:
                continue  # No duplicate execution

            result = ParallelResult(
                agent_id=task.agent_id,
                agent_version=task.agent_version,
                capability=task.capability,
            )

            try:
                output = executor_fn(task)
                result.status = "COMPLETED"
                result.result = output
                self._executed_agents.append(task.agent_id)
            except Exception as e:
                result.status = "FAILED"
                result.error = str(e)
                self._executed_agents.append(task.agent_id)

            self._results.append(result)

        return list(self._results)

    def get_results(self) -> list[ParallelResult]:
        return list(self._results)

    def get_successful(self) -> list[ParallelResult]:
        return [r for r in self._results if r.status == "COMPLETED"]

    def get_failed(self) -> list[ParallelResult]:
        return [r for r in self._results if r.status == "FAILED"]

    def get_result_for_agent(self, agent_id: str) -> ParallelResult | None:
        for r in self._results:
            if r.agent_id == agent_id:
                return r
        return None

    def all_succeeded(self) -> bool:
        return all(r.status == "COMPLETED" for r in self._results)

    def has_failures(self) -> bool:
        return any(r.status == "FAILED" for r in self._results)

    def failure_isolation_check(self, failed_agent: str, dependent_agents: list[str]) -> list[str]:
        """Check which agents are affected by a failure.

        Only agents that depend on the failed agent are affected.
        Independent agents are NOT blocked.
        """
        affected = []
        for agent_id in dependent_agents:
            if agent_id == failed_agent:
                affected.append(agent_id)
            # In a real system, dependency graph would determine this
            # For now, only the failed agent itself is affected
        return affected