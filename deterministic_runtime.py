# -*- coding: utf-8 -*-
"""Deterministic Runtime — Phase J3.

Local deterministic runtime for MarketHQ research agents.
Uses existing BaseAgentAdapter + AgentResult contract.

No external provider calls. No API keys. No billing.
Research-only. No trading. No broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from provider_adapter import ProviderRuntime, ProviderMetadata, RuntimeType, ProviderStatus, ProviderCapability, CapabilityType
from agent_contract import BaseAgentAdapter, AgentResult, AgentStatus


class DeterministicRunStatus(Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class DeterministicExecution:
    """Single deterministic execution record."""
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
    status: DeterministicRunStatus = DeterministicRunStatus.CREATED
    error_type: str = ""
    error_message: str = ""
    retry_count: int = 0
    timeout_seconds: int = 0
    cancelled: bool = False
    result: AgentResult | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id:
            self.execution_id = f"EXE-{uuid.uuid4().hex[:10].upper()}"
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "runtime_id": self.runtime_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "context_version": self.context_version,
            "input_version": self.input_version,
            "output_version": self.output_version,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
            "cancelled": self.cancelled,
            "result": self.result.to_dict() if self.result else None,
            "provenance": self.provenance,
            "metadata": self.metadata,
        }


class DeterministicRuntime(ProviderRuntime):
    """Local deterministic runtime for research agents.

    Uses existing BaseAgentAdapter + AgentResult contract.
    No external calls. Fully deterministic.
    """

    def __init__(self, metadata: ProviderMetadata | None = None) -> None:
        if metadata is None:
            metadata = ProviderMetadata(
                provider_id="PRV-DETERMINISTIC",
                runtime_id="RT-LOCAL-001",
                runtime_type=RuntimeType.DETERMINISTIC_LOCAL,
                provider_name="MarketHQ Deterministic Runtime",
                runtime_version="1.0.0",
                adapter_version="1.0.0",
                capabilities=[
                    ProviderCapability(capability=CapabilityType.DETERMINISTIC, deterministic=True, latency_class="low"),
                    ProviderCapability(capability=CapabilityType.LOCAL, latency_class="low"),
                ],
                status=ProviderStatus.HEALTHY,
                max_retries=0,
                timeout_seconds=60,
                cost_policy="research_only",
            )
        super().__init__(metadata)
        self._executions: dict[str, DeterministicExecution] = {}
        self._idempotency_keys: dict[str, str] = {}  # idempotency_key → execution_id

    def execute(
        self,
        agent_id: str,
        agent_version: str,
        context: Any,
        timeout_seconds: int = 60,
        execution_id: str = "",
        idempotency_key: str = "",
        adapter: BaseAgentAdapter | None = None,
    ) -> DeterministicExecution:
        """Execute an agent deterministically."""

        # Idempotency check
        if idempotency_key and idempotency_key in self._idempotency_keys:
            existing_id = self._idempotency_keys[idempotency_key]
            existing = self._executions.get(existing_id)
            if existing:
                return existing

        exe = DeterministicExecution(
            execution_id=execution_id or f"EXE-{uuid.uuid4().hex[:10].upper()}",
            agent_id=agent_id,
            agent_version=agent_version,
            runtime_id=self.metadata.runtime_id,
            provider_id=self.metadata.provider_id,
            model_id="deterministic-local",
            task_id=getattr(context, 'task_id', '') if context else '',
            workspace_id=getattr(context, 'workspace_id', '') if context else '',
            context_version=getattr(context, 'context_version', '') if context else '',
            input_version=getattr(context, 'data_cutoff_timestamp', '') if context else '',
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
        )
        exe.status = DeterministicRunStatus.RUNNING
        exe.started_at = datetime.now(timezone.utc).isoformat()

        try:
            if adapter is None:
                # Create a minimal result for deterministic execution
                result = AgentResult(
                    agent_id=agent_id,
                    agent_version=agent_version,
                    status=AgentStatus.SUCCESS,
                    direction="NEUTRAL",
                    confidence=0.0,
                    uncertainty=1.0,
                    symbol=getattr(context, 'symbol', '') if context else '',
                    timeframe=getattr(context, 'timeframe', '') if context else '',
                )
            elif hasattr(adapter, 'run'):
                # Use the existing adapter contract
                if isinstance(adapter, type):
                    adapter = adapter(context)
                result = adapter.run()
            else:
                result = AgentResult(
                    agent_id=agent_id,
                    agent_version=agent_version,
                    status=AgentStatus.SUCCESS,
                    direction="NEUTRAL",
                    confidence=0.0,
                    uncertainty=1.0,
                )

            exe.result = result
            exe.status = DeterministicRunStatus.COMPLETED
            exe.output_version = getattr(result, 'execution_id', '') or ''
            self.metadata.status = ProviderStatus.HEALTHY

        except Exception as e:
            exe.status = DeterministicRunStatus.FAILED
            exe.error_type = type(e).__name__
            exe.error_message = str(e)
            self.metadata.status = ProviderStatus.DEGRADED

        exe.finished_at = datetime.now(timezone.utc).isoformat()
        if exe.started_at:
            try:
                from datetime import datetime as dt
                start = dt.fromisoformat(exe.started_at)
                finish = dt.fromisoformat(exe.finished_at)
                exe.duration_ms = int((finish - start).total_seconds() * 1000)
            except Exception:
                exe.duration_ms = 0

        self._executions[exe.execution_id] = exe
        if idempotency_key:
            self._idempotency_keys[idempotency_key] = exe.execution_id

        self.record_success() if exe.status == DeterministicRunStatus.COMPLETED else self.record_failure()
        return exe

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        exe = self._executions.get(execution_id)
        if exe is None:
            return False
        if exe.status in (DeterministicRunStatus.RUNNING, DeterministicRunStatus.QUEUED):
            exe.status = DeterministicRunStatus.CANCELLED
            exe.cancelled = True
            exe.finished_at = datetime.now(timezone.utc).isoformat()
        return True

    def get_execution(self, execution_id: str) -> DeterministicExecution | None:
        return self._executions.get(execution_id)

    def get_executions_for_agent(self, agent_id: str) -> list[DeterministicExecution]:
        return [e for e in self._executions.values() if e.agent_id == agent_id]

    def health(self) -> ProviderStatus:
        return self._metadata.status

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["executions"] = len(self._executions)
        return base