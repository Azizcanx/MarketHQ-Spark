# -*- coding: utf-8 -*-
"""Phase J5 — Intelligence State System.
Continuous intelligence state machine with audit trail.

System-wide states (different from cycle-level LoopState):
- INITIALIZING, OBSERVING, STABLE, CHANGE_DETECTED, RESEARCHING,
  VALIDATING, LEARNING, HUMAN_REVIEW, PAUSED, ERROR, STALE

State transitions are auditable with timestamp, cycle_id, reason,
provenance, and context_version.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class IntelligenceState(Enum):
    """System-wide intelligence states for continuous operation."""

    INITIALIZING = "INITIALIZING"
    OBSERVING = "OBSERVING"
    STABLE = "STABLE"
    CHANGE_DETECTED = "CHANGE_DETECTED"
    RESEARCHING = "RESEARCHING"
    VALIDATING = "VALIDATING"
    LEARNING = "LEARNING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    STALE = "STALE"


# Valid state transitions (directed graph)
VALID_TRANSITIONS: dict[IntelligenceState, list[IntelligenceState]] = {
    IntelligenceState.INITIALIZING: [
        IntelligenceState.OBSERVING,
        IntelligenceState.ERROR,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.OBSERVING: [
        IntelligenceState.STABLE,
        IntelligenceState.CHANGE_DETECTED,
        IntelligenceState.ERROR,
        IntelligenceState.PAUSED,
        IntelligenceState.STALE,
    ],
    IntelligenceState.STABLE: [
        IntelligenceState.OBSERVING,
        IntelligenceState.CHANGE_DETECTED,
        IntelligenceState.RESEARCHING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.STALE,
    ],
    IntelligenceState.CHANGE_DETECTED: [
        IntelligenceState.RESEARCHING,
        IntelligenceState.OBSERVING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.RESEARCHING: [
        IntelligenceState.VALIDATING,
        IntelligenceState.LEARNING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.VALIDATING: [
        IntelligenceState.LEARNING,
        IntelligenceState.RESEARCHING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.LEARNING: [
        IntelligenceState.STABLE,
        IntelligenceState.OBSERVING,
        IntelligenceState.HUMAN_REVIEW,
        IntelligenceState.PAUSED,
        IntelligenceState.ERROR,
    ],
    IntelligenceState.HUMAN_REVIEW: [
        IntelligenceState.RESEARCHING,
        IntelligenceState.LEARNING,
        IntelligenceState.STABLE,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.PAUSED: [
        IntelligenceState.OBSERVING,
        IntelligenceState.INITIALIZING,
        IntelligenceState.RESEARCHING,
    ],
    IntelligenceState.ERROR: [
        IntelligenceState.INITIALIZING,
        IntelligenceState.OBSERVING,
        IntelligenceState.PAUSED,
    ],
    IntelligenceState.STALE: [
        IntelligenceState.OBSERVING,
        IntelligenceState.RESEARCHING,
        IntelligenceState.PAUSED,
    ],
}


@dataclass
class IntelligenceStateChange:
    """A single state transition record."""

    timestamp: str
    from_state: IntelligenceState
    to_state: IntelligenceState
    cycle_id: str
    reason: str
    provenance: str
    context_version: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "cycle_id": self.cycle_id,
            "reason": self.reason,
            "provenance": self.provenance,
            "context_version": self.context_version,
            "metadata": self.metadata,
        }


@dataclass
class IntelligenceStateRecord:
    """Current intelligence state with full context."""

    state: IntelligenceState
    cycle_id: str
    entered_at: str
    reason: str
    provenance: str
    context_version: int
    last_transition: IntelligenceStateChange | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "cycle_id": self.cycle_id,
            "entered_at": self.entered_at,
            "reason": self.reason,
            "provenance": self.provenance,
            "context_version": self.context_version,
            "last_transition": (
                self.last_transition.to_dict() if self.last_transition else None
            ),
            "metadata": self.metadata,
        }


class IntelligenceStateManager:
    """Manages system-wide intelligence state with audit trail.

    Ensures only valid state transitions occur and records every
    transition with full provenance.
    """

    def __init__(self, initial_state: IntelligenceState = IntelligenceState.INITIALIZING) -> None:
        self._current_state: IntelligenceState = initial_state
        self._cycle_id: str = f"CYC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        self._context_version: int = 1
        self._state_history: list[IntelligenceStateChange] = []
        self._current_record: IntelligenceStateRecord | None = None
        self._state_reason: dict[IntelligenceState, str] = {}
        self._state_provenance: dict[IntelligenceState, str] = {}

        # Initialize
        now = datetime.now(timezone.utc).isoformat()
        self._current_record = IntelligenceStateRecord(
            state=initial_state,
            cycle_id=self._cycle_id,
            entered_at=now,
            reason="system_initialization",
            provenance="IntelligenceStateManager.__init__",
            context_version=self._context_version,
            metadata={},
        )

    @property
    def current_state(self) -> IntelligenceState:
        return self._current_state

    @property
    def cycle_id(self) -> str:
        return self._cycle_id

    @property
    def context_version(self) -> int:
        return self._context_version

    @property
    def state_history(self) -> list[IntelligenceStateChange]:
        return list(self._state_history)

    @property
    def current_record(self) -> IntelligenceStateRecord | None:
        return self._current_record

    def can_transition(self, new_state: IntelligenceState) -> bool:
        """Check if transition from current state to new_state is valid."""
        current = self._current_state
        return new_state in VALID_TRANSITIONS.get(current, [])

    def get_valid_next_states(self) -> list[IntelligenceState]:
        """Return all valid next states from current state."""
        return list(VALID_TRANSITIONS.get(self._current_state, []))

    def transition(
        self,
        new_state: IntelligenceState,
        reason: str = "",
        provenance: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IntelligenceStateChange:
        """Execute a state transition with validation and audit.

        Args:
            new_state: Target state
            reason: Why this transition is happening
            provenance: Source/component initiating the transition
            metadata: Additional context

        Returns:
            The IntelligenceStateChange record

        Raises:
            ValueError: If transition is invalid
        """
        if not self.can_transition(new_state):
            raise ValueError(
                f"Invalid state transition: {self._current_state.value} "
                f"→ {new_state.value}. Valid transitions: "
                f"{[s.value for s in self.get_valid_next_states()]}"
            )

        now = datetime.now(timezone.utc).isoformat()
        transition = IntelligenceStateChange(
            timestamp=now,
            from_state=self._current_state,
            to_state=new_state,
            cycle_id=self._cycle_id,
            reason=reason or f"state_transition_{new_state.value.lower()}",
            provenance=provenance or "IntelligenceStateManager.transition",
            context_version=self._context_version,
            metadata=metadata or {},
        )

        # Update current state
        self._current_state = new_state
        self._state_reason[new_state] = reason or transition.reason
        self._state_provenance[new_state] = provenance or transition.provenance
        self._state_history.append(transition)

        # Update current record
        self._current_record = IntelligenceStateRecord(
            state=new_state,
            cycle_id=self._cycle_id,
            entered_at=now,
            reason=transition.reason,
            provenance=transition.provenance,
            context_version=self._context_version,
            last_transition=transition,
            metadata=metadata or {},
        )

        return transition

    def bump_context_version(self) -> int:
        """Increment context version (e.g., after memory update)."""
        self._context_version += 1
        return self._context_version

    def set_cycle_id(self, new_cycle_id: str) -> None:
        """Update cycle_id (e.g., new research cycle starts)."""
        self._cycle_id = new_cycle_id

    def get_state_info(self, state: IntelligenceState) -> dict[str, Any]:
        """Get information about a specific state."""
        return {
            "state": state.value,
            "reason": self._state_reason.get(state, ""),
            "provenance": self._state_provenance.get(state, ""),
            "valid_transitions": [s.value for s in VALID_TRANSITIONS.get(state, [])],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self._current_state.value,
            "cycle_id": self._cycle_id,
            "context_version": self._context_version,
            "state_history": [t.to_dict() for t in self._state_history],
            "current_record": self._current_record.to_dict() if self._current_record else None,
        }
