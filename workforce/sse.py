"""SSE event broadcaster — J16 live events with ordering + IDs."""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from typing import Any

# Simple in-memory event bus
_subscribers: list[Any] = []
_seq = itertools.count(1)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def broadcast_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Broadcast an SSE event to all subscribers.

    Event schema:
      event_id, sequence, event, timestamp, task_id, worker_id, data
    """
    payload = {
        "event_id": str(uuid.uuid4()),
        "sequence": next(_seq),
        "event": event_type,
        "timestamp": _iso_now(),
        "task_id": data.get("task_id"),
        "worker_id": data.get("worker_id") or data.get("agent_id"),
        "data": data,
    }
    for sub in list(_subscribers):
        try:
            sub.put_nowait(payload)
        except Exception:
            pass
    return payload


def subscribe() -> Any:
    """Create a queue subscriber for SSE stream."""
    import asyncio

    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: Any) -> None:
    """Remove a subscriber."""
    if queue in _subscribers:
        _subscribers.remove(queue)


def subscriber_count() -> int:
    return len(_subscribers)
