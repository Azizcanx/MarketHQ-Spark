from __future__ import annotations

"""Workforce FastAPI endpoints — J16 live HQ wiring."""

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from repository_pg import PostgresRepository
from workforce.execution import WorkforceExecutionService
from workforce.models import (
    AgentProfile,
    TaskStatus,
    Team,
    TeamStatus,
    WorkforceTask,
    WorkerStatus,
)
from workforce.monitoring import metrics
from workforce.sse import broadcast_event, subscribe, subscriber_count, unsubscribe
from workforce.supervisor import WorkforceSupervisor

router = APIRouter(prefix="/api/workforce", tags=["workforce"])

_supervisor: WorkforceSupervisor | None = None
_exec_service: WorkforceExecutionService | None = None
_task_idempotency: dict[str, str] = {}
_complete_idempotency: set[str] = set()
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_tokens() -> set[str]:
    raw = os.environ.get("AZIZ_API_TOKENS", "dev-token")
    return {t.strip() for t in raw.split(",") if t.strip()}


def require_auth(authorization: str | None = Header(default=None)) -> str:
    if os.environ.get("AZIZ_REQUIRE_AUTH", "1").strip().lower() in {"0", "false", "no"}:
        return "auth-disabled"
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth scheme")
    token = authorization.split(" ", 1)[1].strip()
    if token not in _valid_tokens():
        raise HTTPException(status_code=403, detail="Forbidden")
    return token


def get_supervisor() -> WorkforceSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = WorkforceSupervisor()
        _bootstrap_workers(_supervisor)
    return _supervisor


def get_execution_service() -> WorkforceExecutionService:
    global _exec_service
    if _exec_service is None:
        _exec_service = WorkforceExecutionService(supervisor=get_supervisor())
    return _exec_service


def _bootstrap_workers(sup: WorkforceSupervisor) -> None:
    if sup.workers:
        return
    defaults = [
        AgentProfile(
            agent_id="structure-001",
            name="Structure Worker",
            role="structure",
            capabilities=["RESEARCH", "MARKET_STRUCTURE"],
            skills=["structure", "thyao"],
            supported_symbols=["THYAO.IS", "BTC-USD"],
            supported_timeframes=["1h", "4h", "1d"],
            status=WorkerStatus.AVAILABLE,
            reliability=0.8,
        ),
        AgentProfile(
            agent_id="liquidity-001",
            name="Liquidity Worker",
            role="liquidity",
            capabilities=["RESEARCH", "LIQUIDITY_ANALYSIS"],
            skills=["liquidity"],
            supported_symbols=["THYAO.IS"],
            supported_timeframes=["1h", "1d"],
            status=WorkerStatus.AVAILABLE,
            reliability=0.75,
        ),
        AgentProfile(
            agent_id="critic-001",
            name="Critic Worker",
            role="critic",
            capabilities=["REVIEW", "CRITICISM"],
            skills=["critic"],
            supported_symbols=["THYAO.IS"],
            supported_timeframes=["1h", "4h", "1d"],
            status=WorkerStatus.AVAILABLE,
            reliability=0.85,
        ),
    ]
    for w in defaults:
        sup.register_worker(w)


def _persist_brain_memory(task: WorkforceTask, result: dict[str, Any]) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql://"):
        return
    try:
        repo = PostgresRepository(db_url)
        repo.migrate()
        obs = repo.create_observation(task.task_id, "WORKER_RESULT", {
            "status": result.get("status"),
            "summary": result.get("summary"),
            "provider": result.get("provider_metadata", {}).get("provider_id"),
            "task_id": task.task_id,
        })
        metrics.brain_observation()
        repo.create_memory(task.input_data.get("symbol", "UNKNOWN"), {
            "task_id": task.task_id,
            "observation_id": obs.get("id"),
            "result": result,
        }, source="workforce")
        metrics.memory_write()
        repo.create_audit_event("TASK_PIPELINE_COMPLETED", task.task_id, {
            "status": task.status.value,
            "assigned_agent": task.assigned_agent,
            "completed_at": task.completed_at,
        })
        repo.close()
    except Exception:
        pass


def _run_task_pipeline(task_id: str) -> None:
    sup = get_supervisor()
    task = sup.get_task(task_id)
    if not task:
        return

    if task.assigned_agent:
        sup.start_task(task_id)
        metrics.increment("task_started")
        broadcast_event("task.started", {"task_id": task_id, "worker_id": task.assigned_agent, "status": "RUNNING"})

    result = get_execution_service().execute_task(task_id)
    refreshed = sup.get_task(task_id)
    if not refreshed:
        return

    if refreshed.status == TaskStatus.COMPLETED:
        metrics.task_completed()
        broadcast_event("task.completed", {
            "task_id": task_id,
            "worker_id": refreshed.assigned_agent,
            "status": "COMPLETED",
            "result": result,
        })
        _persist_brain_memory(refreshed, result)
    elif refreshed.status in {TaskStatus.QUEUED, TaskStatus.FAILED}:
        metrics.task_failed()
        if result.get("provider_metadata", {}).get("fallback_used"):
            metrics.ai_fallback()
            broadcast_event("ai.fallback", {"task_id": task_id, "result": result})
        broadcast_event("task.failed", {
            "task_id": task_id,
            "worker_id": refreshed.assigned_agent,
            "status": refreshed.status.value,
            "error": result.get("error"),
        })


@router.get("/workers")
async def list_workers(status: WorkerStatus | None = Query(None), _: str = Depends(require_auth)):
    sup = get_supervisor()
    workers = list(sup.workers.values())
    if status:
        workers = [w for w in workers if w.status == status]
    return {"workers": [w.model_dump() for w in workers]}


@router.get("/workers/{agent_id}")
async def get_worker(agent_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    w = sup.workers.get(agent_id)
    if not w:
        raise HTTPException(status_code=404, detail=f"Worker {agent_id} not found")
    return w.model_dump()


@router.post("/workers/{agent_id}/pause")
async def pause_worker(agent_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    w = sup.set_worker_status(agent_id, WorkerStatus.PAUSED)
    if not w:
        raise HTTPException(status_code=404, detail=f"Worker {agent_id} not found")
    broadcast_event("worker.status", {"worker_id": agent_id, "status": "PAUSED"})
    return w.model_dump()


@router.post("/workers/{agent_id}/resume")
async def resume_worker(agent_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    w = sup.set_worker_status(agent_id, WorkerStatus.AVAILABLE)
    if not w:
        raise HTTPException(status_code=404, detail=f"Worker {agent_id} not found")
    broadcast_event("worker.status", {"worker_id": agent_id, "status": "AVAILABLE"})
    return w.model_dump()


@router.post("/workers/{agent_id}/heartbeat")
async def worker_heartbeat(agent_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    hb = sup.heartbeat(agent_id, current_task=body.get("current_task"), queue_size=body.get("queue_size", 0))
    if not hb:
        raise HTTPException(status_code=404, detail=f"Worker {agent_id} not found")
    return hb


@router.get("/teams")
async def list_teams(_: str = Depends(require_auth)):
    sup = get_supervisor()
    return {"teams": [t.model_dump() for t in sup.teams.values()]}


@router.post("/teams")
async def create_team(team: Team, _: str = Depends(require_auth)):
    sup = get_supervisor()
    created = sup.create_team(team)
    broadcast_event("team.updated", {"team_id": created.team_id, "name": created.name})
    return created.model_dump()


@router.get("/teams/{team_id}")
async def get_team(team_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    t = sup.get_team(team_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return t.model_dump()


@router.patch("/teams/{team_id}")
async def update_team(team_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    t = sup.get_team(team_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    if "name" in body:
        t.name = body["name"]
    if "description" in body:
        t.description = body["description"]
    if "lead_agent" in body:
        t.lead_agent = body["lead_agent"]
    if "status" in body:
        t.status = TeamStatus(body["status"])
    t.updated_at = _now()
    broadcast_event("team.updated", {"team_id": team_id})
    return t.model_dump()


@router.get("/tasks")
async def list_tasks(
    status: TaskStatus | None = Query(None),
    assigned_agent: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: str = Depends(require_auth),
):
    sup = get_supervisor()
    tasks = sup.list_tasks(status)
    if assigned_agent:
        tasks = [t for t in tasks if t.assigned_agent == assigned_agent]
    tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]
    return {"tasks": [t.model_dump() for t in tasks]}


@router.post("/tasks")
async def create_task(task: WorkforceTask, request: Request, idempotency_key: str | None = Header(default=None), _: str = Depends(require_auth)):
    sup = get_supervisor()
    task_key = idempotency_key or task.input_data.get("idempotency_key")

    if task_key and task_key in _task_idempotency:
        existing = sup.get_task(_task_idempotency[task_key])
        if existing:
            return existing.model_dump()

    created = sup.create_task(task)
    metrics.task_created()
    metrics.ai_request()
    broadcast_event("task.created", {"task_id": created.task_id, "title": created.title, "status": created.status.value})

    worker = sup.selection.select(
        requirements=created.requirements,
        symbol=created.input_data.get("symbol"),
        timeframe=created.input_data.get("timeframe"),
    )
    if not worker:
        avail = sup.list_available()
        worker = avail[0] if avail else None

    if worker:
        sup.assign_task(created.task_id, worker.agent_id)
        metrics.increment("worker_assignment")
        broadcast_event("task.assigned", {
            "task_id": created.task_id,
            "worker_id": worker.agent_id,
            "status": "ASSIGNED",
            "assigned_at": _now(),
        })

    if task_key:
        _task_idempotency[task_key] = created.task_id

    threading.Thread(target=_run_task_pipeline, args=(created.task_id,), daemon=True).start()
    return created.model_dump()


@router.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    agent_id = body.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    task = sup.assign_task(task_id, agent_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot assign task")
    metrics.increment("worker_assignment")
    broadcast_event("task.assigned", {"task_id": task_id, "worker_id": agent_id, "status": "ASSIGNED"})
    return task.model_dump()


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    task = sup.start_task(task_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot start task")
    metrics.increment("task_started")
    broadcast_event("task.started", {"task_id": task_id, "worker_id": task.assigned_agent, "status": "RUNNING"})
    return task.model_dump()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    t = sup.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return t.model_dump()


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: dict[str, Any], idempotency_key: str | None = Header(default=None), _: str = Depends(require_auth)):
    with _lock:
        if idempotency_key and idempotency_key in _complete_idempotency:
            existing = get_supervisor().get_task(task_id)
            if existing:
                return existing.model_dump()

        sup = get_supervisor()
        task = sup.complete_task(task_id, body.get("result"))
        if not task:
            existing = sup.get_task(task_id)
            if existing and existing.status == TaskStatus.COMPLETED:
                return existing.model_dump()
            raise HTTPException(status_code=400, detail="Cannot complete task")

        metrics.task_completed()
        broadcast_event("task.completed", {"task_id": task_id, "worker_id": task.assigned_agent, "status": "COMPLETED"})
        if idempotency_key:
            _complete_idempotency.add(idempotency_key)
        return task.model_dump()


@router.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    retry = body.get("retry", True)
    task = sup.fail_task(task_id, body.get("error", "Unknown error"), retry=retry)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot fail task")
    metrics.task_failed()
    broadcast_event("task.failed", {"task_id": task_id, "worker_id": task.assigned_agent, "retry": retry})
    return task.model_dump()


@router.post("/tasks/{task_id}/reassign")
async def reassign_task(task_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    new_agent = body.get("agent_id")
    if not new_agent:
        raise HTTPException(status_code=400, detail="agent_id required")
    task = sup.reassign_task(task_id, new_agent)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot reassign task")
    metrics.task_reassigned()
    broadcast_event("task.reassigned", {"task_id": task_id, "worker_id": new_agent})
    return task.model_dump()


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, _: str = Depends(require_auth)):
    sup = get_supervisor()
    task = sup.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    broadcast_event("task.cancelled", {"task_id": task_id})
    return task.model_dump()


@router.get("/approvals")
async def list_approvals(status: str = Query("PENDING"), _: str = Depends(require_auth)):
    sup = get_supervisor()
    approvals = [a for a in sup.approvals.values() if a["status"] == status.upper()]
    return {"approvals": approvals}


@router.post("/approvals/{approval_id}")
async def decide_approval(approval_id: str, body: dict[str, Any], _: str = Depends(require_auth)):
    sup = get_supervisor()
    decision = body.get("decision", "").upper()
    decided_by = body.get("decided_by", "patron")
    result = sup.decide_approval(approval_id, decision, decided_by)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    broadcast_event("approval.decided", {"approval_id": approval_id, "decision": decision})
    return result


@router.get("/overview")
async def workforce_overview(_: str = Depends(require_auth)):
    return get_supervisor().summary()


@router.get("/health")
async def workforce_health(_: str = Depends(require_auth)):
    sup = get_supervisor()
    workers = list(sup.workers.values())
    return {
        "workers": len(workers),
        "available": sum(1 for w in workers if w.status == WorkerStatus.AVAILABLE),
        "busy": sum(1 for w in workers if w.status == WorkerStatus.BUSY),
        "offline": sum(1 for w in workers if w.status == WorkerStatus.OFFLINE),
        "stale_tasks": len(sup.stale_tasks()),
        "metrics": metrics.get_all_counters(),
        "sse_subscribers": subscriber_count(),
    }


@router.get("/sse")
async def sse_stream(request: Request, _: str = Depends(require_auth)):
    metrics.sse_connection()

    async def event_generator():
        import asyncio

        queue = subscribe()
        last_seq = 0
        try:
            yield f"data: {json.dumps({'event':'sse.connected','event_id':'init','timestamp':_now(),'sequence':0,'data':{'hydration':True}})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    seq = int(event.get("sequence", 0))
                    if seq <= last_seq:
                        continue
                    last_seq = seq
                    yield f"id: {event['event_id']}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {{\"timestamp\": \"{_now()}\"}}\n\n"
        finally:
            unsubscribe(queue)
            metrics.sse_reconnect()

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )