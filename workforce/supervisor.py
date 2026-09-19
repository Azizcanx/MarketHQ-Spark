"""Worker Selection Engine + Workforce Supervisor — J10."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from workforce.models import (
    AgentProfile, Delegation, TaskPriority, TaskStatus,
    Team, WorkforceTask, WorkerHealth, WorkerStatus,
)


class WorkerSelectionEngine:
    """Deterministic worker selection based on capability matching."""

    def __init__(self):
        self.workers: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> None:
        self.workers[profile.agent_id] = profile
        profile.status = WorkerStatus.AVAILABLE
        profile.health = WorkerHealth.HEALTHY
        profile.last_heartbeat = datetime.now(timezone.utc).isoformat()

    def unregister(self, agent_id: str) -> None:
        if agent_id in self.workers:
            self.workers[agent_id].status = WorkerStatus.OFFLINE

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        return self.workers.get(agent_id)

    def list_available(self) -> list[AgentProfile]:
        return [w for w in self.workers.values() if w.is_available()]

    def select(
        self,
        requirements: list[str],
        capabilities: list[str] | None = None,
        skill: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        strategy_family: str | None = None,
        preferred_agent: str | None = None,
        min_reliability: float = 0.0,
    ) -> Optional[AgentProfile]:
        """Deterministic worker selection.

        Factors:
        - required capability match
        - skill match
        - supported asset/timeframe
        - strategy family
        - availability
        - workload (lower is better)
        - health
        - reliability
        - current task count
        - explicit user preference
        """
        candidates = self.list_available()
        if not candidates:
            return None

        # Prefer explicit user preference
        if preferred_agent and preferred_agent in self.workers:
            w = self.workers[preferred_agent]
            if w.is_available():
                return w

        # Score each candidate
        scored = []
        for w in candidates:
            score = 0.0
            # Capability match
            if capabilities:
                for cap in capabilities:
                    if cap in w.capabilities:
                        score += 3.0
                    if cap in w.skills:
                        score += 1.0
            # Skill match
            if skill and skill in w.skills:
                score += 2.0
            # Asset support
            if symbol and symbol in w.supported_symbols:
                score += 1.5
            # Timeframe support
            if timeframe and timeframe in w.supported_timeframes:
                score += 1.0
            # Strategy family
            if strategy_family and strategy_family in w.strategy_families:
                score += 1.5
            # Health bonus
            if w.health == WorkerHealth.HEALTHY:
                score += 1.0
            elif w.health == WorkerHealth.DEGRADED:
                score += 0.5
            # Reliability (operational metric, NOT prediction of correctness)
            score += w.reliability * 0.5
            # Workload penalty (prefer lower workload)
            score -= (w.workload / max(w.max_concurrent_tasks, 1)) * 2.0
            # Current task count
            score -= w.workload * 0.3

            scored.append((score, w.agent_id, w))

        if not scored:
            return None

        # Deterministic sort: score desc, then agent_id for stability
        scored.sort(key=lambda x: (-x[0], x[1]))
        best = scored[0][2]

        # Minimum reliability gate
        if best.reliability < min_reliability:
            return None

        return best


class WorkforceSupervisor:
    """Central workforce management — dispatch, queue, retry, reassignment."""

    def __init__(self):
        self.selection = WorkerSelectionEngine()
        self.tasks: dict[str, WorkforceTask] = {}
        self.workers: dict[str, AgentProfile] = {}
        self.teams: dict[str, Team] = {}
        self.delegations: dict[str, Delegation] = {}
        self.approvals: dict[str, Any] = {}
        self.max_delegation_depth = 3
        self.max_children_per_task = 8

    # ─── Worker management ──────────────────────────────────────────

    def register_worker(self, profile: AgentProfile) -> AgentProfile:
        self.workers[profile.agent_id] = profile
        self.selection.register(profile)
        return profile

    def unregister_worker(self, agent_id: str) -> None:
        if agent_id in self.workers:
            self.workers[agent_id].status = WorkerStatus.OFFLINE
            self.selection.unregister(agent_id)

    def set_worker_status(self, agent_id: str, status: WorkerStatus) -> Optional[AgentProfile]:
        w = self.workers.get(agent_id)
        if w:
            w.status = status
            w.updated_at = datetime.now(timezone.utc).isoformat()
        return w

    def heartbeat(self, agent_id: str, current_task: Optional[str] = None, queue_size: int = 0) -> Optional[dict]:
        w = self.workers.get(agent_id)
        if not w:
            return None
        w.last_heartbeat = datetime.now(timezone.utc).isoformat()
        w.current_task_id = current_task
        w.queue_size = queue_size
        return {
            "agent_id": agent_id,
            "status": w.status.value,
            "last_seen": w.last_heartbeat,
            "current_task": current_task,
            "queue_size": queue_size,
        }

    # ─── Task lifecycle ──────────────────────────────────────────────

    def create_task(self, task: WorkforceTask) -> WorkforceTask:
        self.tasks[task.task_id] = task
        task.status = TaskStatus.CREATED
        return task

    def get_task(self, task_id: str) -> Optional[WorkforceTask]:
        return self.tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[WorkforceTask]:
        if status:
            return [t for t in self.tasks.values() if t.status == status]
        return list(self.tasks.values())

    def assign_task(self, task_id: str, agent_id: str) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        worker = self.workers.get(agent_id)
        if not task or not worker:
            return None
        if not task.can_transition(TaskStatus.ASSIGNED):
            return None
        if not worker.is_available():
            return None

        task.assigned_agent = agent_id
        task.status = TaskStatus.ASSIGNED
        task.assigned_at = datetime.now(timezone.utc).isoformat()
        worker.workload += 1
        worker.updated_at = datetime.now(timezone.utc).isoformat()
        return task

    def start_task(self, task_id: str) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        if not task or not task.can_transition(TaskStatus.RUNNING):
            return None
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or datetime.now(timezone.utc).isoformat()
        return task

    def complete_task(self, task_id: str, result: dict | None = None) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        if not task or not task.can_transition(TaskStatus.COMPLETED):
            return None
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.result = result
        # Release worker
        if task.assigned_agent and task.assigned_agent in self.workers:
            w = self.workers[task.assigned_agent]
            w.workload = max(0, w.workload - 1)
            w.tasks_completed += 1
            w.updated_at = datetime.now(timezone.utc).isoformat()
        return task

    def fail_task(self, task_id: str, error: str, retry: bool = True) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        if not task or not task.can_transition(TaskStatus.FAILED):
            return None
        task.error = error
        task.retry_count += 1
        if retry and task.retry_count <= task.max_retries:
            task.status = TaskStatus.QUEUED
        else:
            task.status = TaskStatus.FAILED
            if task.assigned_agent and task.assigned_agent in self.workers:
                w = self.workers[task.assigned_agent]
                w.workload = max(0, w.workload - 1)
                w.tasks_failed += 1
                w.updated_at = datetime.now(timezone.utc).isoformat()
        return task

    def reassign_task(self, task_id: str, new_agent_id: str) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        if not task or not task.can_transition(TaskStatus.REASSIGNED):
            return None
        old_agent = task.assigned_agent
        task.assigned_agent = new_agent_id
        task.status = TaskStatus.REASSIGNED
        task.retry_count += 1
        if old_agent and old_agent in self.workers:
            self.workers[old_agent].workload = max(0, self.workers[old_agent].workload - 1)
        if new_agent_id in self.workers:
            self.workers[new_agent_id].workload += 1
        return task

    def cancel_task(self, task_id: str) -> Optional[WorkforceTask]:
        task = self.tasks.get(task_id)
        if not task or not task.can_transition(TaskStatus.CANCELLED):
            return None
        task.status = TaskStatus.CANCELLED
        if task.assigned_agent and task.assigned_agent in self.workers:
            self.workers[task.assigned_agent].workload = max(
                0, self.workers[task.assigned_agent].workload - 1
            )
        return task

    # ─── Dependencies ─────────────────────────────────────────────────

    def check_dependencies(self, task_id: str) -> bool:
        """Return True if all dependencies are COMPLETED."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def unblock_dependents(self, completed_task_id: str) -> list[WorkforceTask]:
        """Unblock tasks waiting on completed_task_id."""
        unblocked = []
        for task in self.tasks.values():
            if completed_task_id in task.dependencies and task.status == TaskStatus.BLOCKED:
                if self.check_dependencies(task.task_id):
                    task.status = TaskStatus.QUEUED
                    unblocked.append(task)
        return unblocked

    # ─── Delegation ───────────────────────────────────────────────────

    def delegate(
        self,
        parent_task_id: str,
        delegating_agent: str,
        target_agent: str,
        reason: str = "",
        requirements: list[str] | None = None,
    ) -> Optional[Delegation]:
        parent = self.tasks.get(parent_task_id)
        if not parent:
            return None
        # Check delegation depth
        depth = 0
        current = parent
        while current.parent_task_id and depth < self.max_delegation_depth:
            depth += 1
            current = self.tasks.get(current.parent_task_id)
            if not current:
                break
        if depth >= self.max_delegation_depth:
            return None
        # Check max children
        if len(parent.child_task_ids) >= self.max_children_per_task:
            return None

        delegation = Delegation(
            parent_task_id=parent_task_id,
            child_task_id=uuid.uuid4().hex[:10].upper(),
            delegating_agent=delegating_agent,
            target_agent=target_agent,
            reason=reason,
            requirements=requirements or [],
            current_depth=depth,
        )
        self.delegations[delegation.delegation_id] = delegation
        parent.child_task_ids.append(delegation.child_task_id)
        return delegation

    # ─── Team management ──────────────────────────────────────────────

    def create_team(self, team: Team) -> Team:
        self.teams[team.team_id] = team
        return team

    def get_team(self, team_id: str) -> Optional[Team]:
        return self.teams.get(team_id)

    def add_member(self, team_id: str, agent_id: str) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team or agent_id in team.members:
            return None
        team.members.append(agent_id)
        team.updated_at = datetime.now(timezone.utc).isoformat()
        return team

    def remove_member(self, team_id: str, agent_id: str) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team or agent_id not in team.members:
            return None
        team.members.remove(agent_id)
        team.updated_at = datetime.now(timezone.utc).isoformat()
        return team

    # ─── Approval ─────────────────────────────────────────────────────

    def request_approval(
        self, task_id: str, agent_id: str, reason: str, action: str
    ) -> dict:
        approval = {
            "approval_id": uuid.uuid4().hex[:10].upper(),
            "task_id": task_id,
            "agent_id": agent_id,
            "reason": reason,
            "action": action,
            "status": "PENDING",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        self.approvals[approval["approval_id"]] = approval
        return approval

    def decide_approval(
        self, approval_id: str, decision: str, decided_by: str
    ) -> Optional[dict]:
        approval = self.approvals.get(approval_id)
        if not approval or approval["status"] != "PENDING":
            return None
        approval["status"] = decision
        approval["decided_by"] = decided_by
        approval["decided_at"] = datetime.now(timezone.utc).isoformat()
        return approval

    # ─── Dispatch ─────────────────────────────────────────────────────

    def dispatch(
        self,
        requirements: list[str],
        capabilities: list[str] | None = None,
        skill: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        strategy_family: str | None = None,
        preferred_agent: str | None = None,
        **task_kwargs: Any,
    ) -> tuple[Optional[WorkforceTask], Optional[AgentProfile]]:
        """Create task + assign worker in one call."""
        task = WorkforceTask(
            requirements=requirements,
            **task_kwargs,
        )
        self.create_task(task)

        worker = self.selection.select(
            requirements=requirements,
            capabilities=capabilities,
            skill=skill,
            symbol=symbol,
            timeframe=timeframe,
            strategy_family=strategy_family,
            preferred_agent=preferred_agent,
        )
        if worker:
            self.assign_task(task.task_id, worker.agent_id)
        return task, worker

    # ─── Health ───────────────────────────────────────────────────────

    def stale_tasks(self, threshold_seconds: int = 300) -> list[WorkforceTask]:
        """Tasks RUNNING without heartbeat for too long."""
        stale = []
        now = datetime.now(timezone.utc)
        for task in self.tasks.values():
            if task.status != TaskStatus.RUNNING:
                continue
            if not task.heartbeats:
                stale.append(task)
                continue
            last_hb_str = task.heartbeats[-1]
            try:
                last_hb = datetime.fromisoformat(last_hb_str)
                if (now - last_hb).total_seconds() > threshold_seconds:
                    stale.append(task)
            except (ValueError, TypeError):
                stale.append(task)
        return stale

    # ─── Status summary ───────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "workers": len(self.workers),
            "workers_available": len(self.list_available()),
            "workers_busy": sum(1 for w in self.workers.values() if w.status == WorkerStatus.BUSY),
            "tasks_total": len(self.tasks),
            "tasks_running": sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING),
            "tasks_queued": sum(1 for t in self.tasks.values() if t.status == TaskStatus.QUEUED),
            "tasks_completed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            "tasks_failed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            "teams": len(self.teams),
            "approvals_pending": sum(1 for a in self.approvals.values() if a["status"] == "PENDING"),
        }

    def list_available(self) -> list[AgentProfile]:
        return self.selection.list_available()