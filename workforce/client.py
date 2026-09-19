"""Workforce API client for Next.js frontend."""

import re
from typing import Any

BASE = "http://localhost:9999/api/workforce"


async def api_get(path: str) -> Any:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE}{path}") as resp:
            return await resp.json()


async def api_post(path: str, body: dict | None = None) -> Any:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE}{path}", json=body or {}) as resp:
            return await resp.json()


async def get_workers(status: str | None = None) -> dict:
    params = f"?status={status}" if status else ""
    return await api_get(f"/workers{params}")


async def get_worker(agent_id: str) -> dict:
    return await api_get(f"/workers/{agent_id}")


async def get_teams() -> dict:
    return await api_get("/teams")


async def get_tasks(status: str | None = None) -> dict:
    params = f"?status={status}" if status else ""
    return await api_get(f"/tasks{params}")


async def get_task(task_id: str) -> dict:
    return await api_get(f"/tasks/{task_id}")


async def create_task(title: str, description: str = "", priority: str = "NORMAL") -> dict:
    return await api_post("/tasks", {"title": title, "description": description, "priority": priority})


async def assign_task(task_id: str, agent_id: str) -> dict:
    return await api_post(f"/tasks/{task_id}/assign", {"agent_id": agent_id})


async def start_task(task_id: str) -> dict:
    return await api_post(f"/tasks/{task_id}/start")


async def complete_task(task_id: str, result: dict | None = None) -> dict:
    return await api_post(f"/tasks/{task_id}/complete", {"result": result or {}})


async def fail_task(task_id: str, error: str = "Unknown") -> dict:
    return await api_post(f"/tasks/{task_id}/fail", {"error": error})


async def cancel_task(task_id: str) -> dict:
    return await api_post(f"/tasks/{task_id}/cancel")


async def get_approvals(status: str = "PENDING") -> dict:
    return await api_get(f"/approvals?status={status}")


async def decide_approval(approval_id: str, decision: str, decided_by: str = "patron") -> dict:
    return await api_post(f"/approvals/{approval_id}", {"decision": decision, "decided_by": decided_by})


async def get_overview() -> dict:
    return await api_get("/overview")


async def get_health() -> dict:
    return await api_get("/health")