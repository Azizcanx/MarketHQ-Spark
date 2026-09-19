# -*- coding: utf-8 -*-
"""Agent Runtime V2 — execution lifecycle for Phase C."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_contract import (
    AgentResult,
    BaseAgentAdapter,
    MarketContext,
    AgentStatus,
)


class AgentRunStatus(Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class AgentConfig:
    agent_id: str
    version: str
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRequest:
    symbol: str
    timeframe: str
    observation_timestamp: str
    data_cutoff_timestamp: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionMetadata:
    """Runtime execution metadata for observability."""
    execution_id: str = ""
    agent_id: str = ""
    agent_version: str = ""
    runtime_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    task_id: str = ""
    workspace_id: str = ""
    context_version: str = ""
    input_version: str = ""
    output_version: str = ""
    correlation_id: str = ""
    idempotency_key: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "USD"
    retry_count: int = 0
    timeout_seconds: int = 0
    cancelled: bool = False
    fallback_reason: str = ""
    routing_reasoning: str = ""
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentRun:
    execution_id: str
    agent_id: str
    agent_version: str
    symbol: str
    timeframe: str
    started_at: str
    completed_at: str | None = None
    observation_timestamp: str = ""
    data_cutoff_timestamp: str = ""
    status: AgentRunStatus = AgentRunStatus.CREATED
    error_type: str = ""
    error_message: str = ""
    result: AgentResult | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    metadata: ExecutionMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "observation_timestamp": self.observation_timestamp,
            "data_cutoff_timestamp": self.data_cutoff_timestamp,
            "status": self.status.value,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "result": self.result.to_dict() if self.result else None,
            "trace": self.trace,
        }
        if self.metadata:
            d["metadata"] = {
                "execution_id": self.metadata.execution_id,
                "runtime_id": self.metadata.runtime_id,
                "provider_id": self.metadata.provider_id,
                "model_id": self.metadata.model_id,
                "context_version": self.metadata.context_version,
                "input_version": self.metadata.input_version,
                "output_version": self.metadata.output_version,
                "correlation_id": self.metadata.correlation_id,
                "idempotency_key": self.metadata.idempotency_key,
                "started_at": self.metadata.started_at,
                "finished_at": self.metadata.finished_at,
                "duration_ms": self.metadata.duration_ms,
                "input_tokens": self.metadata.input_tokens,
                "output_tokens": self.metadata.output_tokens,
                "total_tokens": self.metadata.total_tokens,
                "estimated_cost": self.metadata.estimated_cost,
                "currency": self.metadata.currency,
                "retry_count": self.metadata.retry_count,
                "timeout_seconds": self.metadata.timeout_seconds,
                "cancelled": self.metadata.cancelled,
                "fallback_reason": self.metadata.fallback_reason,
                "routing_reasoning": self.metadata.routing_reasoning,
            }
        return d


class AgentRuntime:
    def __init__(
        self,
        registry: "AgentRegistry" = None,
        cache: "FeatureSnapshotCache" = None,
        persistence: "PersistenceLayer" = None,
    ) -> None:
        from agent_registry import AgentRegistry
        from feature_cache import FeatureSnapshotCache
        from persistence import PersistenceLayer
        self.registry = registry or AgentRegistry()
        self.cache = cache or FeatureSnapshotCache()
        self.persistence = persistence or PersistenceLayer()
        self._runs: dict[str, AgentRun] = {}

    def run(
        self,
        agent_id: str,
        symbol: str,
        timeframe: str,
        observation_timestamp: str = "",
        data_cutoff_timestamp: str = "",
        parameters: dict[str, Any] | None = None,
        context: "MarketContext | None" = None,
    ) -> AgentRun:
        execution_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        run = AgentRun(
            execution_id=execution_id,
            agent_id=agent_id,
            agent_version=self.registry.get_version(agent_id),
            symbol=symbol,
            timeframe=timeframe,
            started_at=now,
            observation_timestamp=observation_timestamp or now,
            data_cutoff_timestamp=data_cutoff_timestamp or now,
            status=AgentRunStatus.RUNNING,
        )
        self._runs[execution_id] = run
        self._trace(run, "RUN_CREATED", f"Agent {agent_id} started")
        try:
            if not symbol or not timeframe:
                raise ValueError("symbol and timeframe are required")
            adapter = self.registry.get(agent_id)
            if adapter is None:
                run.status = AgentRunStatus.FAILED
                run.error_type = "ADAPTER_NOT_FOUND"
                run.error_message = f"No adapter for {agent_id}"
                self._trace(run, "ADAPTER_NOT_FOUND", run.error_message)
                return run
            ctx = context or self._build_context(
                symbol=symbol, timeframe=timeframe,
                observation_timestamp=run.observation_timestamp,
                data_cutoff_timestamp=run.data_cutoff_timestamp,
            )
            # Support both class and instance registration
            if isinstance(adapter, type):
                adapter = adapter(ctx)
                result = adapter.run()
            else:
                result = adapter.run(ctx)
            run.result = result
            if result.status == AgentStatus.ERROR:
                run.status = AgentRunStatus.FAILED
                run.error_type = result.error_type or "AGENT_ERROR"
                run.error_message = result.error_message or "Unknown error"
            elif result.status == AgentStatus.INSUFFICIENT_DATA:
                run.status = AgentRunStatus.INSUFFICIENT_DATA
            else:
                run.status = AgentRunStatus.COMPLETED
            self._trace(run, "AGENT_COMPLETED", f"Status: {result.status.value}")
        except Exception as exc:
            run.status = AgentRunStatus.FAILED
            run.error_type = type(exc).__name__
            run.error_message = str(exc)
            self._trace(run, "EXECUTION_ERROR", str(exc))
        finally:
            run.completed_at = datetime.now(timezone.utc).isoformat()
        try:
            self.persistence.persist_run(run)
        except Exception:
            pass
        return run

    def get_run(self, execution_id: str) -> AgentRun | None:
        return self._runs.get(execution_id)

    def run_multiple(
        self,
        agent_ids: list[str],
        symbol: str,
        timeframe: str,
        observation_timestamp: str = "",
        data_cutoff_timestamp: str = "",
    ) -> list[AgentRun]:
        runs = []
        for aid in agent_ids:
            run = self.run(agent_id=aid, symbol=symbol, timeframe=timeframe,
                          observation_timestamp=observation_timestamp,
                          data_cutoff_timestamp=data_cutoff_timestamp)
            runs.append(run)
        return runs

    def execute_with_router(
        self,
        agent_id: str,
        agent_version: str,
        router: Any,
        context: Any = None,
        timeout_seconds: int = 60,
        idempotency_key: str = "",
        task_id: str = "",
        workspace_id: str = "",
        context_version: str = "",
        required_capability: str = "",
        required_features: list[str] | None = None,
        deterministic_only: bool = True,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "",
        latency_requirement: str = "low",
        cost_policy: str = "research_only",
        explicit_runtime: str = "",
    ) -> AgentRun:
        """Execute agent via AgentRouter with full metadata tracking.

        Routes through AgentRouter → selected Runtime → AgentResult → Audit.
        """
        import uuid
        from datetime import datetime, timezone

        execution_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        correlation_id = execution_id

        # Build execution metadata
        meta = ExecutionMetadata(
            execution_id=execution_id,
            agent_id=agent_id,
            agent_version=agent_version,
            task_id=task_id,
            workspace_id=workspace_id,
            context_version=context_version,
            input_version=getattr(context, 'data_cutoff_timestamp', '') if context else '',
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            started_at=now,
            timeout_seconds=timeout_seconds,
        )

        run = AgentRun(
            execution_id=execution_id,
            agent_id=agent_id,
            agent_version=agent_version,
            symbol=symbol or (getattr(context, 'symbol', '') if context else ''),
            timeframe=timeframe or (getattr(context, 'timeframe', '') if context else ''),
            started_at=now,
            status=AgentRunStatus.QUEUED,
            metadata=meta,
        )
        self._runs[execution_id] = run

        # Route
        route = router.route(
            agent_id=agent_id,
            task_id=task_id,
            required_capability=required_capability,
            required_features=required_features,
            symbol=run.symbol,
            timeframe=run.timeframe,
            regime=regime,
            latency_requirement=latency_requirement,
            cost_policy=cost_policy,
            deterministic_only=deterministic_only,
            context_version=context_version,
            explicit_runtime=explicit_runtime,
        )
        meta.routing_reasoning = route.reasoning
        meta.fallback_reason = route.fallback_reason

        if route.status.value in ("ROUTING_REJECTED", "NO_PROVIDER"):
            run.status = AgentRunStatus.REJECTED
            run.error_type = "NO_PROVIDER"
            run.error_message = route.reasoning
            run.completed_at = datetime.now(timezone.utc).isoformat()
            return run

        # Get selected runtime
        selected_runtime = router.get_runtime(route.selected_runtime)
        if selected_runtime is None:
            run.status = AgentRunStatus.FAILED
            run.error_type = "RUNTIME_NOT_FOUND"
            run.error_message = f"Runtime {route.selected_runtime} not found"
            run.completed_at = datetime.now(timezone.utc).isoformat()
            return run

        meta.runtime_id = route.selected_runtime
        meta.provider_id = route.selected_provider
        run.status = AgentRunStatus.RUNNING

        # Execute
        try:
            result = selected_runtime.execute(
                agent_id=agent_id,
                agent_version=agent_version,
                context=context,
                timeout_seconds=timeout_seconds,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                adapter=None,
            )

            # Convert to AgentResult if needed
            if hasattr(result, 'to_dict'):
                # External runtime returns dict-like
                ar = AgentResult(
                    agent_id=agent_id,
                    agent_version=agent_version,
                    status=AgentStatus.SUCCESS,
                    symbol=run.symbol,
                    timeframe=run.timeframe,
                    confidence=0.0,
                    uncertainty=1.0,
                )
            else:
                ar = result

            run.result = ar
            run.status = AgentRunStatus.COMPLETED
            meta.output_version = getattr(ar, 'execution_id', '') or ''
            meta.duration_ms = getattr(result, 'duration_ms', 0) if hasattr(result, 'duration_ms') else 0

            # Token/cost metadata
            if hasattr(result, 'metadata'):
                rm = result.metadata
                meta.input_tokens = getattr(rm, 'input_tokens', 0)
                meta.output_tokens = getattr(rm, 'output_tokens', 0)
                meta.total_tokens = getattr(rm, 'total_tokens', 0)
                meta.estimated_cost = getattr(rm, 'estimated_cost', 0.0)

        except Exception as exc:
            run.status = AgentRunStatus.FAILED
            run.error_type = type(exc).__name__
            run.error_message = str(exc)
            meta.provider_id = route.selected_provider

        run.completed_at = datetime.now(timezone.utc).isoformat()
        meta.finished_at = run.completed_at

        # Duration
        if meta.started_at and meta.finished_at:
            try:
                start = datetime.fromisoformat(meta.started_at)
                finish = datetime.fromisoformat(meta.finished_at)
                meta.duration_ms = int((finish - start).total_seconds() * 1000)
            except Exception:
                pass

        return run

    def _build_context(
        self, symbol: str, timeframe: str,
        observation_timestamp: str, data_cutoff_timestamp: str,
    ) -> MarketContext:
        cached = self.cache.get(symbol, timeframe, data_cutoff_timestamp)
        if cached is not None:
            return cached
        ctx = MarketContext(
            symbol=symbol, timeframe=timeframe,
            observation_timestamp=observation_timestamp,
            data_cutoff_timestamp=data_cutoff_timestamp,
        )
        return ctx

    def _trace(self, run: AgentRun, step: str, detail: str) -> None:
        run.trace.append({
            "step": step, "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def list_runs(
        self,
        agent_id: str | None = None,
        symbol: str | None = None,
        status: AgentRunStatus | None = None,
    ) -> list[AgentRun]:
        runs = list(self._runs.values())
        if agent_id:
            runs = [r for r in runs if r.agent_id == agent_id]
        if symbol:
            runs = [r for r in runs if r.symbol == symbol]
        if status:
            runs = [r for r in runs if r.status == status]
        return runs
