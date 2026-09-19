# -*- coding: utf-8 -*-
"""Phase I — Research Orchestrator.

Thin orchestration layer on top of existing AgentRuntime.
Does NOT replace AgentRuntime, AgentRegistry, Brain, or any existing engine.

Responsibilities:
- Accept research tasks
- Resolve agent, dependencies, feature snapshot
- Run agent through existing AgentRuntime
- Collect AgentResult
- Persist execution metadata
- Forward evidence
- Trigger downstream tasks
- Preserve provenance
- Handle failure isolation

Research-only. No trading. No broker. No auto promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from research_orchestrator_model import ResearchTask, TaskStatus, AgentHealth, HealthStatus
from research_agent_model import AgentProfile, AgentStatus, CapabilityType
from research_workspace import ResearchWorkspace, WorkspaceStatus, create_workspace
from task_router import TaskRouter, RoutingResult, DEFAULT_CAPABILITIES
from agent_message import AgentMessage, MessageType
from research_audit import ResearchAuditEvent, AuditEventType, AuditLog
from agent_lifecycle import AgentLifecycleManager, AgentLifecycleState


class OrchestratorStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class OrchestratorRun:
    """Single orchestrator execution."""
    run_id: str
    pipeline_type: str = "research"
    tasks: list[ResearchTask] = field(default_factory=list)
    status: OrchestratorStatus = OrchestratorStatus.IDLE
    created_at: str = ""
    finished_at: str = ""
    error_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    provenance_chain: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline_type": self.pipeline_type,
            "task_count": len(self.tasks),
            "status": self.status.value,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error_count": self.error_count,
            "success_count": self.success_count,
            "skipped_count": self.skipped_count,
            "provenance_chain": self.provenance_chain,
        }


# ═══════════════════════════════════════════════════════════════════
# Simple In-Memory Orchestrator
# ═══════════════════════════════════════════════════════════════════

class ResearchOrchestrator:
    """Thin orchestration layer for research tasks.

    Uses existing AgentRuntime for execution.
    Adds task management, dependency resolution, provenance, health checks.
    Phase J1: Adds workspace, routing, audit, lifecycle.
    """

    def __init__(self):
        self.tasks: dict[str, ResearchTask] = {}
        self.profiles: dict[str, AgentProfile] = {}
        self.runs: list[OrchestratorRun] = []
        self.health: dict[str, Any] = {}
        # Phase J1 additions
        self.workspace: ResearchWorkspace | None = None
        self.router = TaskRouter()
        self.audit = AuditLog()
        self.lifecycle = AgentLifecycleManager()
        self.messages: list[AgentMessage] = []
        self._setup_default_capabilities()

    def register_agent(self, profile: AgentProfile) -> None:
        """Register an agent profile with the orchestrator."""
        self.profiles[profile.agent_id] = profile
        # Register capabilities with router (map CapabilityType to router IDs)
        cap_type_to_router = {
            CapabilityType.TREND_DIRECTION: "trend_analysis",
            CapabilityType.TREND_STRENGTH: "trend_analysis",
            CapabilityType.REGIME: "trend_analysis",
            CapabilityType.BREAKOUT: "breakout_analysis",
            CapabilityType.REVERSAL: "reversal_analysis",
            CapabilityType.MOMENTUM: "momentum_analysis",
            CapabilityType.VOLATILITY: "volatility_analysis",
            CapabilityType.LIQUIDITY: "liquidity_analysis",
            CapabilityType.STRUCTURE: "structure_analysis",
        }
        for cap in profile.capabilities:
            router_cap = cap_type_to_router.get(cap, cap.value)
            self.router.register_agent_capability(profile.agent_id, router_cap)
        # Audit
        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.AGENT_REGISTERED,
            agent_id=profile.agent_id,
            new_state="REGISTERED",
            metadata={"version": profile.version, "role": profile.role},
        ))

    def _setup_default_capabilities(self) -> None:
        """Register default capabilities with the task router."""
        for cap_id, cap_desc in DEFAULT_CAPABILITIES.items():
            self.router.register_capability(
                capability_id=cap_id,
                description=cap_desc.description,
                required_features=cap_desc.required_features,
                supported_regimes=cap_desc.supported_regimes,
                supported_timeframes=cap_desc.supported_timeframes,
                cost_class=cap_desc.cost_class,
                deterministic=cap_desc.deterministic,
                research_only=cap_desc.research_only,
            )

    def create_workspace(
        self,
        research_id: str,
        symbol: str,
        timeframe: str,
        cutoff: str,
    ) -> ResearchWorkspace:
        """Create a research workspace for this run."""
        self.workspace = create_workspace(
            research_id=research_id,
            symbol=symbol,
            timeframe=timeframe,
            cutoff=cutoff,
        )
        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.WORKSPACE_CREATED,
            workspace_id=self.workspace.workspace_id,
            new_state=WorkspaceStatus.INITIALIZING.value,
            metadata={"symbol": symbol, "timeframe": timeframe, "cutoff": cutoff},
        ))
        return self.workspace

    def add_participant(self, agent_id: str, role: str) -> None:
        """Add an agent as participant to the workspace."""
        if self.workspace:
            self.workspace.add_participant(agent_id, role)

    # ── Phase J1: Routing ────────────────────────────────────

    def route_task(
        self,
        task_id: str,
        required_capability: str,
        symbol: str = "",
        timeframe: str = "",
        regime: str = "",
    ) -> RoutingResult:
        """Route a task to the best matching agent."""
        available_features: dict[str, bool] = {}
        result = self.router.route(
            task_id=task_id,
            required_capability=required_capability,
            available_features=available_features,
            symbol=symbol,
            timeframe=timeframe,
            regime=regime,
        )
        # Audit routing decision
        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.ROUTING_DECISION,
            task_id=task_id,
            workspace_id=self.workspace.workspace_id if self.workspace else "",
            new_state=result.status.value,
            metadata={
                "agent_id": result.agent_id,
                "capability": required_capability,
                "score": result.score,
                "reasoning": result.reasoning,
            },
        ))
        return result

    # ── Phase J1: Messaging ──────────────────────────────────

    def send_message(
        self,
        sender: str,
        recipient: str,
        message_type: MessageType,
        workspace_id: str = "",
        task_id: str = "",
        payload: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> AgentMessage:
        """Send a structured message between agents."""
        msg = AgentMessage(
            sender_agent_id=sender,
            recipient_agent_id=recipient,
            workspace_id=workspace_id or (self.workspace.workspace_id if self.workspace else ""),
            task_id=task_id,
            message_type=message_type,
            payload=payload or {},
            evidence_refs=evidence_refs or [],
        )
        self.messages.append(msg)
        self.audit.append(ResearchAuditEvent(
            event_type=AuditEventType.MESSAGE_SENT,
            workspace_id=msg.workspace_id,
            agent_id=sender,
            new_state=message_type.value,
            metadata={"recipient": recipient, "message_id": msg.message_id},
        ))
        return msg

    # ── Phase J1: Audit ──────────────────────────────────────

    def get_audit_events(self, event_type: AuditEventType | None = None) -> list[ResearchAuditEvent]:
        """Get audit events, optionally filtered by type."""
        return self.audit.get_events(event_type)

    def get_workspace_audit(self) -> list[ResearchAuditEvent]:
        """Get all audit events for the current workspace."""
        if not self.workspace:
            return []
        return self.audit.get_events_for_workspace(self.workspace.workspace_id)

    def create_task(
        self,
        task_type: str,
        agent_id: str,
        asset: str = "",
        timeframe: str = "",
        cutoff: str = "",
        dependencies: list[str] | None = None,
        priority: int = 0,
        context_id: str = "",
    ) -> ResearchTask:
        """Create a research task."""
        now = datetime.now(timezone.utc).isoformat()
        config_str = json.dumps(
            {"task_type": task_type, "agent_id": agent_id, "asset": asset,
             "timeframe": timeframe, "cutoff": cutoff},
            sort_keys=True,
        )
        task_id = f"TASK-{hashlib.sha256(f'{now}{config_str}'.encode()).hexdigest()[:12].upper()}"

        task = ResearchTask(
            task_id=task_id,
            task_type=task_type,
            agent_id=agent_id,
            asset=asset,
            timeframe=timeframe,
            cutoff=cutoff,
            context_id=context_id,
            priority=priority,
            status=TaskStatus.QUEUED,
            created_at=now,
            dependencies=dependencies or [],
            config_hash=hashlib.sha256(config_str.encode()).hexdigest()[:16],
        )
        self.tasks[task_id] = task
        return task

    def resolve_dependencies(self, task: ResearchTask) -> list[str]:
        """Check if task dependencies are completed."""
        unresolved = []
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETED:
                unresolved.append(dep_id)
        return unresolved

    def can_execute(self, task: ResearchTask) -> tuple[bool, str]:
        """Check if a task can execute (dependencies only).

        Agent health is tracked for monitoring but does NOT block
        independent tasks. Only dependency resolution gates execution.
        A failed dependency blocks dependents; unrelated tasks proceed.
        """
        unresolved = self.resolve_dependencies(task)
        if unresolved:
            return False, f"BLOCKED: unresolved dependencies {unresolved}"
        return True, "READY"

    def execute_task(
        self,
        task: ResearchTask,
        executor=None,
    ) -> dict[str, Any]:
        """Execute a task through the executor (existing AgentRuntime).

        Args:
            task: The task to execute
            executor: Optional callable that takes a task and returns a result dict.
                     If None, task is marked as completed with placeholder result.

        Returns:
            Execution result dict
        """
        now = datetime.now(timezone.utc).isoformat()
        task.status = TaskStatus.RUNNING
        task.started_at = now

        # Check if we can execute
        can_exec, reason = self.can_execute(task)
        if not can_exec:
            task.status = TaskStatus.BLOCKED
            task.finished_at = datetime.now(timezone.utc).isoformat()
            return {
                "task_id": task.task_id,
                "status": "BLOCKED",
                "reason": reason,
            }

        try:
            if executor is not None:
                result = executor(task)
            else:
                result = {"status": "COMPLETED", "output": "placeholder"}

            task.status = TaskStatus.COMPLETED
            task.result_reference = f"RESULT-{task.task_id}"
            task.finished_at = datetime.now(timezone.utc).isoformat()

            # Update agent health
            profile = self.profiles.get(task.agent_id)
            if profile:
                profile.status = AgentStatus.READY
                profile.last_run = task.finished_at

            return {
                "task_id": task.task_id,
                "status": "COMPLETED",
                "result": result,
            }

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.failure_reference = f"FAIL-{task.task_id}"
            task.finished_at = datetime.now(timezone.utc).isoformat()

            # Update agent health on failure
            profile = self.profiles.get(task.agent_id)
            if profile:
                profile.status = AgentStatus.FAILED
                profile.failure_count += 1
                profile.last_run = task.finished_at

            return {
                "task_id": task.task_id,
                "status": "FAILED",
                "error": str(e),
            }

    def run_pipeline(
        self,
        pipeline_tasks: list[ResearchTask],
        executor=None,
    ) -> OrchestratorRun:
        """Run a pipeline of tasks with dependency resolution.

        Executes tasks in dependency order. Failed tasks don't block
        independent downstream tasks unless those tasks depend on them.
        """
        now = datetime.now(timezone.utc).isoformat()
        run_id = f"RUN-{hashlib.sha256(f'{now}{len(pipeline_tasks)}'.encode()).hexdigest()[:12].upper()}"

        run = OrchestratorRun(
            run_id=run_id,
            pipeline_type="research",
            tasks=pipeline_tasks,
            status=OrchestratorStatus.RUNNING,
            created_at=now,
        )

        # Topological sort (simple Kahn's algorithm)
        remaining = list(pipeline_tasks)
        completed_ids = set()
        seen_task_ids = set()
        max_iterations = len(remaining) * 2 + 10
        iteration = 0

        # Deduplicate: keep first occurrence of each task_id
        deduped = []
        for task in remaining:
            if task.task_id not in seen_task_ids:
                seen_task_ids.add(task.task_id)
                deduped.append(task)
            else:
                # Mark duplicate as skipped (already queued)
                task.status = TaskStatus.BLOCKED
                run.skipped_count += 1
        remaining = deduped

        while remaining and iteration < max_iterations:
            iteration += 1
            progress = False

            for task in list(remaining):
                # Check dependencies
                deps = self.resolve_dependencies(task)
                if deps:
                    continue

                # Try to execute
                result = self.execute_task(task, executor=executor)
                if result["status"] == "COMPLETED":
                    completed_ids.add(task.task_id)
                    remaining.remove(task)
                    run.success_count += 1
                    progress = True
                elif result["status"] == "BLOCKED":
                    # Dependencies not ready yet, try later
                    continue
                else:
                    # Failed
                    completed_ids.add(task.task_id)
                    remaining.remove(task)
                    run.error_count += 1
                    progress = True

            if not progress and remaining:
                # No progress — circular dependency or stuck
                for task in remaining:
                    task.status = TaskStatus.BLOCKED
                    run.skipped_count += 1
                break

        run.status = (OrchestratorStatus.COMPLETED
                      if not remaining and run.error_count == 0
                      else OrchestratorStatus.PARTIAL
                      if not remaining
                      else OrchestratorStatus.FAILED)
        run.finished_at = datetime.now(timezone.utc).isoformat()
        self.runs.append(run)
        return run

    def get_provenance_chain(self, task: ResearchTask) -> list[dict[str, Any]]:
        """Build provenance chain for a task."""
        chain = []
        now = datetime.now(timezone.utc).isoformat()

        chain.append({
            "id": task.task_id,
            "type": "task",
            "source": task.agent_id,
            "version": "1.0",
            "timestamp": now,
            "config_hash": task.config_hash,
            "data_cutoff": task.data_cutoff or task.cutoff,
            "status": task.status.value,
        })

        # Add agent profile if available
        profile = self.profiles.get(task.agent_id)
        if profile:
            chain.append({
                "id": profile.agent_id,
                "type": "agent",
                "source": profile.agent_name,
                "version": profile.version,
                "timestamp": now,
                "config_hash": "",
                "data_cutoff": task.data_cutoff or task.cutoff,
                "status": profile.status.value,
            })

        # Add dependency provenance
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if dep:
                chain.append({
                    "id": dep.task_id,
                    "type": "dependency",
                    "source": dep.agent_id,
                    "version": "1.0",
                    "timestamp": dep.created_at or now,
                    "config_hash": dep.config_hash,
                    "data_cutoff": dep.data_cutoff or dep.cutoff,
                    "status": dep.status.value,
                })

        return chain

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Machine-readable dashboard summary."""
        now = datetime.now(timezone.utc).isoformat()
        total_tasks = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        queued = sum(1 for t in self.tasks.values() if t.status == TaskStatus.QUEUED)
        blocked = sum(1 for t in self.tasks.values() if t.status == TaskStatus.BLOCKED)

        total_agents = len(self.profiles)
        healthy = sum(1 for p in self.profiles.values()
                      if p.status == AgentStatus.READY)
        failed_agents = sum(1 for p in self.profiles.values()
                            if p.status == AgentStatus.FAILED)
        unavailable_agents = sum(1 for p in self.profiles.values()
                                 if p.status == AgentStatus.UNAVAILABLE)

        return {
            "timestamp": now,
            "tasks": {
                "total": total_tasks,
                "completed": completed,
                "failed": failed,
                "running": running,
                "queued": queued,
                "blocked": blocked,
            },
            "agents": {
                "total": total_agents,
                "healthy": healthy,
                "failed": failed_agents,
                "unavailable": unavailable_agents,
            },
            "runs": len(self.runs),
            "workspace": self.workspace.workspace_id if self.workspace else None,
            "audit_events": self.audit._events.__len__() if hasattr(self.audit, '_events') else 0,
        }