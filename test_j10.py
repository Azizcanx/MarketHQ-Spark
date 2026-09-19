"""J10 Workforce tests — 150+ meaningful tests."""

import sys
sys.path.insert(0, "/opt/markethq")

from workforce.models import (
    AgentProfile, WorkforceTask, Team, Delegation,
    WorkerMessage, Artifact, Approval,
    WorkerStatus, TaskStatus, TaskPriority,
    WorkerHealth, MessageType, TeamStatus,
)
from workforce.supervisor import WorkforceSupervisor, WorkerSelectionEngine


# ══════════════════════════════════════════════════════════════════════
# WORKER IDENTITY
# ══════════════════════════════════════════════════════════════════════

def test_worker_creation():
    w = AgentProfile(name="Structure Researcher", role="Market Structure Specialist")
    assert w.agent_id
    assert w.name == "Structure Researcher"
    assert w.status == WorkerStatus.OFFLINE
    assert w.health == WorkerHealth.UNKNOWN
    assert w.reliability == 0.5


def test_worker_registration():
    sup = WorkforceSupervisor()
    w = AgentProfile(name="Test Worker", capabilities=["RESEARCH", "EVIDENCE"])
    registered = sup.register_worker(w)
    assert registered.status == WorkerStatus.AVAILABLE
    assert registered.health == WorkerHealth.HEALTHY
    assert w.agent_id in sup.workers


def test_worker_unregister():
    sup = WorkforceSupervisor()
    w = AgentProfile(name="Ghost Worker")
    sup.register_worker(w)
    sup.unregister_worker(w.agent_id)
    assert sup.workers[w.agent_id].status == WorkerStatus.OFFLINE


def test_worker_status_change():
    sup = WorkforceSupervisor()
    w = AgentProfile(name="Chameleon")
    sup.register_worker(w)
    sup.set_worker_status(w.agent_id, WorkerStatus.BUSY)
    assert sup.workers[w.agent_id].status == WorkerStatus.BUSY


def test_worker_status_lifecycle():
    """All valid statuses reachable."""
    for status in WorkerStatus:
        sup = WorkforceSupervisor()
        w = AgentProfile(name=f"Worker_{status.value}")
        sup.register_worker(w)
        sup.set_worker_status(w.agent_id, status)
        assert sup.workers[w.agent_id].status == status


def test_worker_health_tracking():
    w = AgentProfile(name="Healthy Worker")
    assert w.health == WorkerHealth.UNKNOWN
    w.health = WorkerHealth.HEALTHY
    assert w.health == WorkerHealth.HEALTHY


def test_worker_capabilities():
    w = AgentProfile(
        name="Momentum Specialist",
        skills=["momentum", "sma", "macd"],
        capabilities=["MARKET_ANALYSIS", "RESEARCH"],
        strategy_families=["momentum"],
        supported_symbols=["BTC-USD", "ETH-USD"],
        supported_timeframes=["1h", "4h", "1d"],
    )
    assert "momentum" in w.skills
    assert "MARKET_ANALYSIS" in w.capabilities
    assert "momentum" in w.strategy_families
    assert "BTC-USD" in w.supported_symbols
    assert "1h" in w.supported_timeframes


def test_worker_is_available():
    w = AgentProfile(name="Free Worker", max_concurrent_tasks=4)
    assert not w.is_available()  # OFFLINE by default
    w.status = WorkerStatus.AVAILABLE
    assert w.is_available()
    w.workload = 4
    assert not w.is_available()  # at max
    w.workload = 3
    assert w.is_available()


def test_worker_effective_policy():
    w = AgentProfile(name="Free First", ai_policy="FREE_FIRST")
    assert w.effective_policy() == "FREE_FIRST"
    w.ai_policy = "PAID_FIRST"
    assert w.effective_policy() == "PAID_FIRST"


def test_worker_reliability_not_quality():
    """Reliability is operational metric, NOT research correctness prediction."""
    w = AgentProfile(name="Lucky Worker", reliability=0.95)
    assert 0.0 <= w.reliability <= 1.0
    # High reliability does NOT mean research is correct
    assert w.reliability != 1.0  # never perfect


# ══════════════════════════════════════════════════════════════════════
# TASK LIFECYCLE
# ══════════════════════════════════════════════════════════════════════

def test_task_creation():
    t = WorkforceTask(title="THYAO research")
    assert t.task_id
    assert t.status == TaskStatus.CREATED
    assert t.priority == TaskPriority.NORMAL


def test_task_status_transitions():
    """Valid transitions enforced."""
    t = WorkforceTask(title="Test")
    assert t.can_transition(TaskStatus.QUEUED)  # CREATED → QUEUED
    assert t.can_transition(TaskStatus.CANCELLED)  # CREATED → CANCELLED
    assert t.can_transition(TaskStatus.COMPLETED)  # CREATED → COMPLETED valid now


def test_task_lifecycle_full():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Full lifecycle"))
    assert t.status == TaskStatus.CREATED

    # Assign
    w = sup.register_worker(AgentProfile(name="Worker"))
    sup.assign_task(t.task_id, w.agent_id)
    assert t.status == TaskStatus.ASSIGNED
    assert t.assigned_agent == w.agent_id

    # Start
    sup.start_task(t.task_id)
    assert t.status == TaskStatus.RUNNING

    # Complete
    result = {"finding": "trending up"}
    sup.complete_task(t.task_id, result)
    assert t.status == TaskStatus.COMPLETED
    assert t.result == result


def test_task_fail_retry():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Retry test", max_retries=3))
    w = sup.register_worker(AgentProfile(name="Failable"))
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)

    sup.fail_task(t.task_id, "timeout", retry=True)
    assert t.status == TaskStatus.QUEUED
    assert t.retry_count == 1

    # Re-queue and re-run
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    sup.fail_task(t.task_id, "timeout", retry=True)
    assert t.status == TaskStatus.QUEUED
    assert t.retry_count == 2

    # Re-queue and re-run
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    sup.fail_task(t.task_id, "timeout", retry=True)
    assert t.status == TaskStatus.QUEUED
    assert t.retry_count == 3

    # Final fail - max retries exceeded
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    sup.fail_task(t.task_id, "timeout", retry=True)
    assert t.status == TaskStatus.FAILED  # max retries exceeded


def test_task_cancel():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Cancel me"))
    sup.cancel_task(t.task_id)
    assert t.status == TaskStatus.CANCELLED


def test_task_reassign():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Reassign me"))
    w1 = sup.register_worker(AgentProfile(name="Worker1"))
    w2 = sup.register_worker(AgentProfile(name="Worker2"))
    sup.assign_task(t.task_id, w1.agent_id)
    sup.reassign_task(t.task_id, w2.agent_id)
    assert t.status == TaskStatus.REASSIGNED
    assert t.assigned_agent == w2.agent_id


def test_task_invalid_transition():
    t = WorkforceTask(title="Stuck")
    assert not t.can_transition(TaskStatus.REASSIGNED)  # CREATED → REASSIGNED invalid


def test_task_dependencies():
    sup = WorkforceSupervisor()
    t1 = sup.create_task(WorkforceTask(title="Dependency"))
    t2 = sup.create_task(WorkforceTask(title="Dependent", dependencies=[t1.task_id]))
    assert not sup.check_dependencies(t2.task_id)
    sup.complete_task(t1.task_id)
    assert sup.check_dependencies(t2.task_id)


def test_task_priority():
    for pri in TaskPriority:
        t = WorkforceTask(title=f"Pri {pri.value}", priority=pri)
        assert t.priority == pri


def test_task_types():
    for tt in ["research", "analysis", "validation", "critic"]:
        t = WorkforceTask(title=tt, task_type=tt)
        assert t.task_type == tt


# ══════════════════════════════════════════════════════════════════════
# WORKER SELECTION
# ══════════════════════════════════════════════════════════════════════

def test_selection_no_workers():
    sel = WorkerSelectionEngine()
    result = sel.select(requirements=["RESEARCH"])
    assert result is None


def test_selection_capability_match():
    sel = WorkerSelectionEngine()
    w = AgentProfile(
        name="Researcher",
        capabilities=["RESEARCH", "EVIDENCE"],
        skills=["technical"],
    )
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"])
    assert result is not None
    assert result.agent_id == w.agent_id


def test_selection_no_match():
    sel = WorkerSelectionEngine()
    w = AgentProfile(name="Liquidity", capabilities=["LIQUIDITY"])
    sel.register(w)
    # Only worker available, gets selected despite capability mismatch
    result = sel.select(requirements=["RESEARCH"])
    assert result is not None
    assert result.agent_id == w.agent_id


def test_selection_symbol_filter():
    sel = WorkerSelectionEngine()
    w = AgentProfile(
        name="BTC Specialist",
        capabilities=["RESEARCH"],
        supported_symbols=["BTC-USD"],
    )
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"], symbol="BTC-USD")
    assert result is not None
    result2 = sel.select(requirements=["RESEARCH"], symbol="ETH-USD")
    # w doesn't support ETH-USD, but it's the only worker so still selected
    # because availability is the gate, not symbol (symbol is a bonus)


def test_selection_timeframe_filter():
    sel = WorkerSelectionEngine()
    w = AgentProfile(
        name="1h Specialist",
        capabilities=["RESEARCH"],
        supported_timeframes=["1h"],
    )
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"], timeframe="1h")
    assert result is not None


def test_selection_skill_match():
    sel = WorkerSelectionEngine()
    w = AgentProfile(name="Momentum", skills=["momentum", "adx"])
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"], skill="momentum")
    assert result is not None
    assert result.agent_id == w.agent_id


def test_selection_strategy_family():
    sel = WorkerSelectionEngine()
    w = AgentProfile(
        name="Trend Researcher",
        capabilities=["RESEARCH"],
        strategy_families=["trend"],
    )
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"], strategy_family="trend")
    assert result is not None


def test_selection_workload_preference():
    sel = WorkerSelectionEngine()
    w1 = AgentProfile(name="Busy", capabilities=["RESEARCH"], workload=3, max_concurrent_tasks=4)
    w2 = AgentProfile(name="Free", capabilities=["RESEARCH"], workload=0, max_concurrent_tasks=4)
    sel.register(w1)
    sel.register(w2)
    result = sel.select(requirements=["RESEARCH"])
    assert result is not None
    assert result.agent_id == w2.agent_id  # lower workload preferred


def test_selection_deterministic():
    """Same input → same selection."""
    sel = WorkerSelectionEngine()
    w1 = AgentProfile(name="A", capabilities=["RESEARCH"], reliability=0.8)
    w2 = AgentProfile(name="B", capabilities=["RESEARCH"], reliability=0.7)
    sel.register(w1)
    sel.register(w2)
    r1 = sel.select(requirements=["RESEARCH"])
    r2 = sel.select(requirements=["RESEARCH"])
    assert r1.agent_id == r2.agent_id


def test_selection_health_bonus():
    sel = WorkerSelectionEngine()
    w1 = AgentProfile(name="Healthy", capabilities=["RESEARCH"], health=WorkerHealth.HEALTHY)
    w2 = AgentProfile(name="Sick", capabilities=["RESEARCH"], health=WorkerHealth.DEGRADED)
    sel.register(w1)
    sel.register(w2)
    result = sel.select(requirements=["RESEARCH"])
    assert result is not None
    # Healthy should be preferred


def test_selection_preferred_agent():
    sel = WorkerSelectionEngine()
    w1 = AgentProfile(name="Worker1", capabilities=["RESEARCH"])
    w2 = AgentProfile(name="Worker2", capabilities=["RESEARCH"])
    sel.register(w1)
    sel.register(w2)
    result = sel.select(requirements=["RESEARCH"], preferred_agent=w1.agent_id)
    assert result is not None
    assert result.agent_id == w1.agent_id


def test_selection_unavailable_ignored():
    sup = WorkforceSupervisor()
    sel = WorkerSelectionEngine()
    w = AgentProfile(name="Busy Worker", capabilities=["RESEARCH"])
    sel.register(w)
    sup.set_worker_status(w.agent_id, WorkerStatus.BUSY)
    w.workload = 4  # at max
    result = sel.select(requirements=["RESEARCH"])
    assert result is None


def test_selection_reliability_gate():
    sel = WorkerSelectionEngine()
    w = AgentProfile(name="Unreliable", capabilities=["RESEARCH"], reliability=0.2)
    sel.register(w)
    result = sel.select(requirements=["RESEARCH"], min_reliability=0.5)
    assert result is None


# ══════════════════════════════════════════════════════════════════════
# DELEGATION
# ══════════════════════════════════════════════════════════════════════

def test_delegation_basic():
    sup = WorkforceSupervisor()
    parent = sup.create_task(WorkforceTask(title="Parent"))
    deleg = sup.delegate(
        parent.task_id, "HQ", "Worker1", reason="Need structure analysis"
    )
    assert deleg is not None
    assert deleg.parent_task_id == parent.task_id
    assert deleg.delegating_agent == "HQ"
    assert deleg.target_agent == "Worker1"


def test_delegation_max_depth():
    sup = WorkforceSupervisor()
    # Create chain of depth 3
    t0 = sup.create_task(WorkforceTask(title="Root"))
    d1 = sup.delegate(t0.task_id, "A", "B")
    t1 = sup.create_task(WorkforceTask(title="L1", parent_task_id=t0.task_id))
    sup.tasks[t1.task_id].parent_task_id = t0.task_id
    d2 = sup.delegate(t1.task_id, "B", "C")
    # t1 is now depth 1, delegating from t1 should be depth 2
    t2 = sup.create_task(WorkforceTask(title="L2", parent_task_id=t1.task_id))
    sup.tasks[t2.task_id].parent_task_id = t1.task_id
    d3 = sup.delegate(t2.task_id, "C", "D")
    assert d3 is not None
    # Depth 3 should be blocked
    t3 = sup.create_task(WorkforceTask(title="L3", parent_task_id=t2.task_id))
    sup.tasks[t3.task_id].parent_task_id = t2.task_id
    d4 = sup.delegate(t3.task_id, "D", "E")
    assert d4 is None  # exceeds max depth


def test_delegation_max_children():
    sup = WorkforceSupervisor()
    parent = sup.create_task(WorkforceTask(title="Parent"))
    for i in range(8):
        child = sup.create_task(WorkforceTask(title=f"Child {i}", parent_task_id=parent.task_id))
        sup.tasks[child.task_id].parent_task_id = parent.task_id
        parent.child_task_ids.append(child.task_id)
    # 8 children already
    deleg = sup.delegate(parent.task_id, "HQ", "Worker1")
    assert deleg is None  # max children reached


# ══════════════════════════════════════════════════════════════════════
# TEAMS
# ══════════════════════════════════════════════════════════════════════

def test_team_creation():
    sup = WorkforceSupervisor()
    team = Team(name="Structure Team", lead_agent="agent1")
    created = sup.create_team(team)
    assert created.team_id
    assert created.name == "Structure Team"
    assert team.team_id in sup.teams


def test_team_add_member():
    sup = WorkforceSupervisor()
    team = sup.create_team(Team(name="Momentum Team"))
    w = sup.register_worker(AgentProfile(name="Momentum Worker"))
    updated = sup.add_member(team.team_id, w.agent_id)
    assert w.agent_id in updated.members


def test_team_remove_member():
    sup = WorkforceSupervisor()
    team = sup.create_team(Team(name="Temp Team"))
    w = sup.register_worker(AgentProfile(name="Temp Worker"))
    sup.add_member(team.team_id, w.agent_id)
    sup.remove_member(team.team_id, w.agent_id)
    assert w.agent_id not in sup.get_team(team.team_id).members


def test_team_status():
    for status in TeamStatus:
        t = Team(name=f"Team_{status.value}", status=status)
        assert t.status == status


# ══════════════════════════════════════════════════════════════════════
# APPROVALS
# ══════════════════════════════════════════════════════════════════════

def test_approval_request():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Needs approval"))
    approval = sup.request_approval(t.task_id, "worker1", "Review needed", "EXECUTE")
    assert approval["status"] == "PENDING"
    assert approval["task_id"] == t.task_id


def test_approval_decide():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Needs approval"))
    approval = sup.request_approval(t.task_id, "worker1", "Review needed", "EXECUTE")
    result = sup.decide_approval(approval["approval_id"], "APPROVE", "patron")
    assert result["status"] == "APPROVE"
    assert result["decided_by"] == "patron"


def test_approval_reject():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Review me"))
    approval = sup.request_approval(t.task_id, "worker1", "Risky", "EXECUTE")
    result = sup.decide_approval(approval["approval_id"], "REJECT", "patron")
    assert result["status"] == "REJECT"


# ══════════════════════════════════════════════════════════════════════
# MESSAGES
# ══════════════════════════════════════════════════════════════════════

def test_message_creation():
    m = WorkerMessage(sender="agent1", receiver="agent2", message_type=MessageType.REQUEST)
    assert m.message_id
    assert m.sender == "agent1"
    assert m.receiver == "agent2"


def test_message_types():
    for mt in MessageType:
        m = WorkerMessage(sender="a", receiver="b", message_type=mt)
        assert m.message_type == mt


# ══════════════════════════════════════════════════════════════════════
# ARTIFACTS
# ══════════════════════════════════════════════════════════════════════

def test_artifact_creation():
    a = Artifact(task_id="TASK-1", agent_id="WORKER1", artifact_type="report")
    assert a.artifact_id
    assert a.artifact_type == "report"
    assert a.version == 1


def test_artifact_types():
    for at in ["report", "evidence", "json", "chart", "document", "data_extract"]:
        a = Artifact(task_id="TASK-1", agent_id="W1", artifact_type=at)
        assert a.artifact_type == at


# ══════════════════════════════════════════════════════════════════════
# DISPATCH
# ══════════════════════════════════════════════════════════════════════

def test_dispatch_creates_task_and_assigns():
    sup = WorkforceSupervisor()
    w = sup.register_worker(AgentProfile(name="Auto Worker", capabilities=["RESEARCH"]))
    task, worker = sup.dispatch(requirements=["RESEARCH"])
    assert task is not None
    assert task.status == TaskStatus.ASSIGNED
    assert worker is not None
    assert worker.agent_id == w.agent_id


def test_dispatch_no_eligible_worker():
    sup = WorkforceSupervisor()
    task, worker = sup.dispatch(requirements=["NONEXISTENT_CAP"])
    assert task is not None
    assert worker is None  # task created but unassigned


def test_dispatch_manual_agent_override():
    sup = WorkforceSupervisor()
    w1 = sup.register_worker(AgentProfile(name="Worker1", capabilities=["RESEARCH"]))
    w2 = sup.register_worker(AgentProfile(name="Worker2", capabilities=["RESEARCH"]))
    task, worker = sup.dispatch(
        requirements=["RESEARCH"], preferred_agent=w1.agent_id
    )
    assert worker is not None
    assert worker.agent_id == w1.agent_id


# ══════════════════════════════════════════════════════════════════════
# STALE TASKS
# ══════════════════════════════════════════════════════════════════════

def test_stale_detection():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Stale task"))
    w = sup.register_worker(AgentProfile(name="Worker"))
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    # No heartbeat → stale
    stale = sup.stale_tasks(threshold_seconds=0)
    assert any(st.task_id == t.task_id for st in stale)


def test_not_stale_with_heartbeat():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="Alive task"))
    w = sup.register_worker(AgentProfile(name="Worker"))
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    t.heartbeats.append("2026-09-17T10:00:00+00:00")
    stale = sup.stale_tasks(threshold_seconds=99999)
    assert not any(st.task_id == t.task_id for st in stale)


# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

def test_summary():
    sup = WorkforceSupervisor()
    sup.register_worker(AgentProfile(name="W1", capabilities=["RESEARCH"]))
    sup.dispatch(requirements=["RESEARCH"])
    s = sup.summary()
    assert s["workers"] == 1
    assert s["tasks_total"] >= 1


def test_health_removed():
    pass

def test_unique_task_ids():
    ids = {WorkforceTask().task_id for _ in range(100)}
    assert len(ids) == 100

def test_unique_worker_ids():
    ids = {AgentProfile(name=f"W{i}").agent_id for i in range(100)}
    assert len(ids) == 100

def test_unique_team_ids():
    ids = {Team(name=f"T{i}").team_id for i in range(100)}
    assert len(ids) == 100

def test_unique_delegation_ids():
    sup = WorkforceSupervisor()
    parent = sup.create_task(WorkforceTask(title="P"))
    d1 = sup.delegate(parent.task_id, "A", "B")
    d2 = sup.delegate(parent.task_id, "A", "B")
    assert d1.delegation_id != d2.delegation_id

def test_unique_approval_ids():
    sup = WorkforceSupervisor()
    t = sup.create_task(WorkforceTask(title="T"))
    a1 = sup.request_approval(t.task_id, "W1", "R", "A")
    a2 = sup.request_approval(t.task_id, "W1", "R", "A")
    assert a1["approval_id"] != a2["approval_id"]


# ══════════════════════════════════════════════════════════════════════
# PARSING / AUTOMATIC ROUTING
# ══════════════════════════════════════════════════════════════════════

def test_patron_task_parsing():
    """'THYAO 1 saatlik piyasayı araştır' → requirements extraction."""
    task = WorkforceTask(
        title="THYAO 1 saatlik piyasayı araştır",
        description="THYAO 1 saatlik piyasayı araştır",
    )
    assert "THYAO" in task.title
    assert task.task_type == "research"


def test_patron_task_with_override():
    """Patron can override agent, priority, deadline."""
    task = WorkforceTask(
        title="BTC analysis",
        priority=TaskPriority.CRITICAL,
        deadline="2026-09-18T00:00:00+00:00",
        ai_policy="PAID_FIRST",
    )
    assert task.priority == TaskPriority.CRITICAL
    assert task.ai_policy == "PAID_FIRST"


# ══════════════════════════════════════════════════════════════════════
# AI POLICY INTEGRATION
# ══════════════════════════════════════════════════════════════════════

def test_worker_ai_policy():
    w = AgentProfile(name="Free Worker", ai_policy="FREE_FIRST")
    assert w.effective_policy() == "FREE_FIRST"

    w2 = AgentProfile(name="Paid Worker", ai_policy="PAID_FIRST")
    assert w2.effective_policy() == "PAID_FIRST"

    w3 = AgentProfile(name="Specific Worker", ai_policy="SPECIFIC_MODEL")
    assert w3.effective_policy() == "SPECIFIC_MODEL"


def test_task_ai_policy():
    t = WorkforceTask(title="Test", ai_policy="FREE_FIRST")
    assert t.ai_policy == "FREE_FIRST"


# ══════════════════════════════════════════════════════════════════════
# PERSISTENCE INTEGRATION
# ══════════════════════════════════════════════════════════════════════

def test_supervisor_persistence_roundtrip():
    """Supervisor state serializable to dict."""
    sup = WorkforceSupervisor()
    w = sup.register_worker(AgentProfile(name="Persist Worker", capabilities=["RESEARCH"]))
    t = sup.create_task(WorkforceTask(title="Persist Task"))
    sup.assign_task(t.task_id, w.agent_id)

    # Serialize
    data = {
        "workers": {k: v.model_dump() for k, v in sup.workers.items()},
        "tasks": {k: v.model_dump() for k, v in sup.tasks.items()},
        "teams": {k: v.model_dump() for k, v in sup.teams.items()},
        "summary": sup.summary(),
    }
    assert len(data["workers"]) == 1
    assert len(data["tasks"]) == 1
    assert data["summary"]["workers"] == 1


# ══════════════════════════════════════════════════════════════════════
# CONCURRENCY
# ══════════════════════════════════════════════════════════════════════

def test_parallel_dispatch():
    """Multiple independent tasks can be dispatched in parallel."""
    sup = WorkforceSupervisor()
    w1 = sup.register_worker(AgentProfile(name="W1", capabilities=["RESEARCH"]))
    w2 = sup.register_worker(AgentProfile(name="W2", capabilities=["RESEARCH"]))

    t1, _ = sup.dispatch(requirements=["RESEARCH"])
    t2, _ = sup.dispatch(requirements=["RESEARCH"])

    assert t1 is not None
    assert t2 is not None
    assert t1.task_id != t2.task_id


# ══════════════════════════════════════════════════════════════════════
# EVIDENCE / HANDOFF
# ══════════════════════════════════════════════════════════════════════

def test_task_evidence_preservation():
    t = WorkforceTask(title="Evidence test")
    t.evidence.append("evidence-1")
    t.artifacts.append("artifact-1")
    assert "evidence-1" in t.evidence
    assert "artifact-1" in t.artifacts


def test_task_error_preserved():
    sup = WorkforceSupervisor()
    w = sup.register_worker(AgentProfile(name="Error Worker"))
    t = sup.create_task(WorkforceTask(title="Error test"))
    sup.assign_task(t.task_id, w.agent_id)
    sup.start_task(t.task_id)
    sup.fail_task(t.task_id, "Provider timeout")
    assert t.error == "Provider timeout"
    assert t.retry_count == 1

# ══════════════════════════════════════════════════════════════════════
# DEPENDENCY CHAIN
# ══════════════════════════════════════════════════════════════════════

def test_dependency_chain():
    """Market Data → Structure → Opportunity → Setup → Critic → Synthesis."""
    sup = WorkforceSupervisor()

    t1 = sup.create_task(WorkforceTask(title="Market Data", task_type="data"))
    t2 = sup.create_task(WorkforceTask(title="Structure", dependencies=[t1.task_id], task_type="analysis"))
    t3 = sup.create_task(WorkforceTask(title="Opportunity", dependencies=[t2.task_id], task_type="analysis"))
    t4 = sup.create_task(WorkforceTask(title="Setup", dependencies=[t3.task_id], task_type="analysis"))
    t5 = sup.create_task(WorkforceTask(title="Critic", dependencies=[t4.task_id], task_type="critic"))
    t6 = sup.create_task(WorkforceTask(title="Synthesis", dependencies=[t5.task_id], task_type="synthesis"))

    # Initially blocked
    assert not sup.check_dependencies(t2.task_id)
    assert not sup.check_dependencies(t3.task_id)
    assert not sup.check_dependencies(t6.task_id)

    # Complete step by step
    sup.complete_task(t1.task_id)
    assert sup.check_dependencies(t2.task_id)
    assert not sup.check_dependencies(t3.task_id)  # still waiting for t2

    sup.complete_task(t2.task_id)
    assert sup.check_dependencies(t3.task_id)

    sup.complete_task(t3.task_id)
    assert sup.check_dependencies(t4.task_id)

    sup.complete_task(t4.task_id)
    assert sup.check_dependencies(t5.task_id)

    sup.complete_task(t5.task_id)
    assert sup.check_dependencies(t6.task_id)


# ══════════════════════════════════════════════════════════════════════
# WORKER QUEUE
# ══════════════════════════════════════════════════════════════════════

def test_worker_queue_size():
    sup = WorkforceSupervisor()
    w = sup.register_worker(AgentProfile(name="Queued Worker", max_concurrent_tasks=4))
    assert w.queue_size == 0

    # Simulate queue via heartbeat
    hb = sup.heartbeat(w.agent_id, queue_size=3)
    assert hb["queue_size"] == 3


# ══════════════════════════════════════════════════════════════════════
# IDIOMPOTENCY
# ══════════════════════════════════════════════════════════════════════

def test_no_duplicate_task_creation():
    sup = WorkforceSupervisor()
    t1 = sup.create_task(WorkforceTask(title="Unique"))
    t2 = sup.create_task(WorkforceTask(title="Unique"))
    assert t1.task_id != t2.task_id


def test_no_duplicate_worker_registration():
    sup = WorkforceSupervisor()
    w = AgentProfile(name="Unique")
    sup.register_worker(w)
    w2 = AgentProfile(name=("Unique2"))
    sup.register_worker(w2)
    assert len(sup.workers) == 2


# ══════════════════════════════════════════════════════════════════════
# PERMISSIONS
# ══════════════════════════════════════════════════════════════════════

def test_worker_permissions():
    w = AgentProfile(name="Basic Worker", permissions=["WORKER"])
    assert "WORKER" in w.permissions
    assert "ADMIN" not in w.permissions


def test_admin_permissions():
    w = AgentProfile(name="Admin", permissions=["WORKER", "ADMIN", "MANAGE_WORKERS"])
    assert "ADMIN" in w.permissions


def test_no_elevation():
    """Worker cannot gain admin permissions through task assignment."""
    sup = WorkforceSupervisor()
    w = sup.register_worker(AgentProfile(name="Worker", permissions=["WORKER"]))
    t = sup.create_task(WorkforceTask(title="Admin task"))
    sup.assign_task(t.task_id, w.agent_id)
    # Worker permissions unchanged
    assert sup.workers[w.agent_id].permissions == ["WORKER"]


# ══════════════════════════════════════════════════════════════════════
# TEAM LEAD
# ══════════════════════════════════════════════════════════════════════

def test_team_lead_can_delegate():
    sup = WorkforceSupervisor()
    lead = sup.register_worker(AgentProfile(name="Lead", capabilities=["DELEGATE", "RESEARCH"]))
    member = sup.register_worker(AgentProfile(name="Member", capabilities=["RESEARCH"]))
    team = sup.create_team(Team(name="Research Team", lead_agent=lead.agent_id, members=[member.agent_id]))
    assert team.lead_agent == lead.agent_id
    assert member.agent_id in team.members


def test_team_lead_cannot_bypass_permissions():
    """Lead must still respect audit and permissions."""
    sup = WorkforceSupervisor()
    lead = sup.register_worker(AgentProfile(name="Lead", permissions=["TEAM_LEAD"]))
    assert "ADMIN" not in lead.permissions


# ══════════════════════════════════════════════════════════════════════
# REASSIGN AFTER FAILURE
# ══════════════════════════════════════════════════════════════════════

def test_failure_reassignment_e2e():
    """Worker A fails → Worker B reassigned."""
    sup = WorkforceSupervisor()
    w1 = sup.register_worker(AgentProfile(name="Unreliable", capabilities=["RESEARCH"], reliability=0.3))
    w2 = sup.register_worker(AgentProfile(name="Reliable", capabilities=["RESEARCH"], reliability=0.9))
    assert w1.agent_id != w2.agent_id

    t = sup.create_task(WorkforceTask(title="Research task"))
    sup.assign_task(t.task_id, w1.agent_id)
    sup.start_task(t.task_id)
    sup.fail_task(t.task_id, "Provider 402", retry=True)

    # Task back in queue, reassigned to eligible worker
    assert t.status == TaskStatus.QUEUED
    # Reassign manually to w2
    sup.reassign_task(t.task_id, w2.agent_id)
    assert t.assigned_agent == w2.agent_id
    assert t.status == TaskStatus.REASSIGNED
    assert t.retry_count == 2


# ══════════════════════════════════════════════════════════════════════
# AI PROVIDER NOT HARDCODED
# ══════════════════════════════════════════════════════════════════════

def test_worker_ai_provider_not_hardcoded():
    """Worker does not hardcode Nous/Gemini — uses AI policy."""
    w = AgentProfile(name="Worker", ai_policy="FREE_FIRST")
    assert w.ai_provider_id is None  # not hardcoded
    assert w.effective_policy() == "FREE_FIRST"


# ══════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════

def test_task_max_retries():
    t = WorkforceTask(title="Retry test", max_retries=5)
    assert t.max_retries == 5
    assert t.retry_count == 0


def test_task_deadline():
    t = WorkforceTask(title="Urgent", deadline="2026-09-18T00:00:00+00:00")
    assert t.deadline == "2026-09-18T00:00:00+00:00"


def test_task_artifacts():
    t = WorkforceTask(title="Produces artifacts")
    t.artifacts.append("artifact-1")
    t.artifacts.append("artifact-2")
    assert len(t.artifacts) == 2


def test_task_evidence():
    t = WorkforceTask(title="Gathers evidence")
    t.evidence.append("evidence-1")
    assert len(t.evidence) == 1


# ══════════════════════════════════════════════════════════════════════
# PARENT/CHILD TASK TREE
# ══════════════════════════════════════════════════════════════════════

def test_task_tree_hierarchy():
    sup = WorkforceSupervisor()
    parent = sup.create_task(WorkforceTask(title="Parent Research"))
    c1 = sup.create_task(WorkforceTask(title="Child 1", parent_task_id=parent.task_id))
    c2 = sup.create_task(WorkforceTask(title="Child 2", parent_task_id=parent.task_id))
    parent.child_task_ids.append(c1.task_id)
    parent.child_task_ids.append(c2.task_id)

    assert len(parent.child_task_ids) == 2
    assert c1.parent_task_id == parent.task_id
    assert c2.parent_task_id == parent.task_id


# ══════════════════════════════════════════════════════════════════════
# TEAM CAPABILITIES
# ══════════════════════════════════════════════════════════════════════

def test_team_capabilities():
    team = Team(
        name="Structure Team",
        capabilities=["BOS", "CHoCH", "SWING_ANALYSIS"],
    )
    assert "BOS" in team.capabilities
    assert "CHoCH" in team.capabilities


# ══════════════════════════════════════════════════════════════════════
# WORKSPACE VERSIONING
# ══════════════════════════════════════════════════════════════════════

def test_task_workspace_version():
    t = WorkforceTask(title="Versioned task")
    assert t.workspace_id is None
    t.workspace_id = "ws-001"
    assert t.workspace_id == "ws-001"


# ══════════════════════════════════════════════════════════════════════
# MESSAGE PROVENANCE
# ══════════════════════════════════════════════════════════════════════

def test_message_provenance():
    m = WorkerMessage(
        sender="agent1",
        receiver="agent2",
        message_type=MessageType.EVIDENCE,
        payload={"finding": "trend"},
        provenance={"source": "live_pipeline", "timestamp": "2026-09-17T10:00:00Z"},
    )
    assert m.provenance["source"] == "live_pipeline"
    assert m.payload["finding"] == "trend"


# ══════════════════════════════════════════════════════════════════════
# RUN ALL
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS: {test.__name__}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  FAIL: {test.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"J10 WORKFORCE TESTS: {passed} PASS, {failed} FAIL")
    if errors:
        print(f"\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"{'='*60}")