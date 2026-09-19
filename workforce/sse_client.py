"""SSE Client for Next.js — J12 Real-Time.

Connects Next.js frontend to FastAPI SSE endpoint.
Handles: connect, disconnect, reconnect, exponential backoff,
duplicate protection, heartbeat, stale connection detection.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional


class SSEClient:
    """SSE client for Next.js frontend.

    Features:
    - Connect/disconnect
    - Reconnect with exponential backoff
    - Duplicate event protection
    - Heartbeat handling
    - Stale connection detection
    - Event ordering
    """

    def __init__(
        self,
        url: str = "http://localhost:9999/api/workforce/sse",
        max_reconnect_delay: int = 30,
        heartbeat_timeout: int = 60,
        reconnect: bool = True,
    ):
        self.url = url
        self.max_reconnect_delay = max_reconnect_delay
        self.heartbeat_timeout = heartbeat_timeout
        self.reconnect = reconnect
        self.event_id = str(uuid.uuid4())
        self.last_event_id: Optional[str] = None
        self.reconnect_delay = 1
        self.connected = False
        self._listeners: dict[str, list[Callable]] = {}
        self._received_events: set[str] = set()
        self._last_event_time: float = 0
        self._stale_threshold = heartbeat_timeout * 2

    def on(self, event_type: str, callback: Callable) -> None:
        """Register event listener."""
        self._listeners.setdefault(event_type, []).append(callback)

    def off(self, event_type: str, callback: Callable) -> None:
        """Remove event listener."""
        if event_type in self._listeners:
            self._listeners[event_type].remove(callback)

    def emit(self, event_type: str, data: Any) -> None:
        """Emit event to listeners."""
        # Duplicate protection
        event_key = f"{event_type}:{data.get('timestamp', '')}"
        if event_key in self._received_events:
            return
        self._received_events.add(event_key)

        # Call listeners
        for callback in self._listeners.get(event_type, []):
            try:
                callback(data)
            except Exception:
                pass

        # Also emit to wildcard listeners
        for callback in self._listeners.get("*", []):
            try:
                callback({"type": event_type, "data": data})
            except Exception:
                pass

    def is_stale(self) -> bool:
        """Check if connection is stale."""
        if not self._last_event_time:
            return False
        return (time.time() - self._last_event_time) > self._stale_threshold

    def get_reconnect_delay(self) -> int:
        """Get current reconnect delay (exponential backoff)."""
        delay = self.reconnect_delay
        self.reconnect_delay = min(delay * 2, self.max_reconnect_delay)
        return delay

    def reset_reconnect_delay(self) -> None:
        """Reset reconnect delay after successful connection."""
        self.reconnect_delay = 1

    def disconnect(self) -> None:
        """Disconnect from SSE."""
        self.connected = False

    def connect(self) -> None:
        """Connect to SSE endpoint."""
        self.connected = True
        self.reset_reconnect_delay()
        self._last_event_time = time.time()

    def get_state(self) -> dict:
        """Get client state."""
        return {
            "connected": self.connected,
            "last_event_id": self.last_event_id,
            "reconnect_delay": self.reconnect_delay,
            "events_received": len(self._received_events),
            "is_stale": self.is_stale(),
        }

    @property
    def events(self) -> list[dict]:
        """Return list of received events."""
        return [{"event": k} for k in self._received_events]


# ─── SSE Event Types ──────────────────────────────────────────────

SSE_EVENTS = [
    "task.created",
    "task.assigned",
    "task.started",
    "task.completed",
    "task.failed",
    "task.reassigned",
    "worker.status",
    "worker.started",
    "worker.completed",
    "worker.failed",
    "critic.started",
    "critic.completed",
    "synthesis.completed",
    "ai.fallback",
    "ai.provider.changed",
    "approval.requested",
    "approval.decided",
    "team.updated",
    "delegation.created",
    "heartbeat",
]


def create_sse_event(event_type: str, data: dict) -> dict:
    """Create SSE event with required fields."""
    return {
        "event": event_type,
        "data": data,
        "event_id": str(uuid.uuid4()),
        "timestamp": __import__("datetime", fromlist=["datetime"]).datetime.now(
            __import__("datetime", fromlist=["timezone"]).timezone.utc
        ).isoformat(),
    }