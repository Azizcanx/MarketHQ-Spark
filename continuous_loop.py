# -*- coding: utf-8 -*-
"""Phase J5 — Continuous Loop.
Wraps AutonomousResearchLoop for continuous operation with:
- Event-driven triggers (scheduled, opportunity_detected, regime_changed, drift_detected,
  claim_weakened, validation_failed, human_requested, recurring_research, manual_review)
- Research budget (max cycles, max tasks/cycle, max agent calls, max runtime, max parallelism)
- Cooldown (duplicate research prevention per symbol/timeframe/hypothesis/claim/task)
- Continuous state management (uses IntelligenceStateManager)

Uses existing AutonomousResearchLoop — never duplicates it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from intelligence_state import IntelligenceState, IntelligenceStateManager
from autonomous_research_loop import (
    AutonomousResearchLoop,
    AutonomousResearchRun,
    AutonomousResearchReport,
    LoopState,
)


class TriggerType(Enum):
    """Event-driven research triggers."""

    SCHEDULED = "scheduled"
    OPPORTUNITY_DETECTED = "opportunity_detected"
    REGIME_CHANGED = "regime_changed"
    DRIFT_DETECTED = "drift_detected"
    CLAIM_WEAKENED = "claim_weakened"
    VALIDATION_FAILED = "validation_failed"
    DATA_RESTORED = "data_restored"
    HUMAN_REQUESTED = "human_requested"
    RECURRING_RESEARCH = "recurring_research"
    MANUAL_REVIEW = "manual_review"


@dataclass
class TriggerEvent:
    """An event that triggers a research cycle."""

    trigger_type: TriggerType
    timestamp: str
    provenance: str
    context: dict[str, Any] = field(default_factory=dict)
    symbol: str = ""
    timeframe: str = ""
    cycle_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type.value,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
            "context": self.context,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "cycle_id": self.cycle_id,
        }


class CooldownType(Enum):
    """Types of cooldown scopes."""

    OPPORTUNITY = "opportunity"
    SYMBOL = "symbol"
    TIMEFRAME = "timeframe"
    HYPOTHESIS = "hypothesis"
    CLAIM = "claim"
    RESEARCH_TASK = "research_task"


@dataclass
class CooldownEntry:
    """A cooldown entry preventing duplicate research."""

    cooldown_type: CooldownType
    key: str  # e.g., symbol+timeframe, hypothesis_id, claim_id
    expires_at: str
    created_at: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def is_expired(self) -> bool:
        """Check if cooldown has expired."""
        if not self.expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "cooldown_type": self.cooldown_type.value,
            "key": self.key,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "reason": self.reason,
            "is_expired": self.is_expired(),
        }


class ResearchBudgetExceeded(Exception):
    """Raised when research budget is exceeded."""

    def __init__(self, budget_type: str, current: int, limit: int) -> None:
        self.budget_type = budget_type
        self.current = current
        self.limit = limit
        super().__init__(
            f"Research budget exceeded: {budget_type} "
            f"current={current}, limit={limit}"
        )


@dataclass
class ResearchBudget:
    """Research budget constraints for continuous operation."""

    max_cycles: int = 100
    max_tasks_per_cycle: int = 20
    max_agent_calls: int = 50
    max_retries: int = 3
    max_provider_calls: int = 100
    max_runtime_seconds: float = 3600.0  # 1 hour per cycle
    max_cost: float | None = None  # Optional cost limit
    max_parallelism: int = 5

    cycle_count: int = 0
    tasks_this_cycle: int = 0
    agent_calls: int = 0
    provider_calls: int = 0
    total_runtime_seconds: float = 0.0
    total_cost: float = 0.0

    start_time: str = ""

    def __post_init__(self) -> None:
        self.start_time = datetime.now(timezone.utc).isoformat()

    def check_cycle_budget(self) -> bool:
        """Check if another cycle is allowed."""
        return self.cycle_count < self.max_cycles

    def check_task_budget(self) -> bool:
        """Check if another task is allowed this cycle."""
        return self.tasks_this_cycle < self.max_tasks_per_cycle

    def check_agent_budget(self) -> bool:
        """Check if another agent call is allowed."""
        return self.agent_calls < self.max_agent_calls

    def check_provider_budget(self) -> bool:
        """Check if another provider call is allowed."""
        return self.provider_calls < self.max_provider_calls

    def check_runtime(self, elapsed: float | None = None) -> bool:
        """Check if runtime budget is still available."""
        if elapsed is None:
            elapsed = time.time() - (
                float(datetime.fromisoformat(self.start_time).timestamp()) if self.start_time else time.time()
            )
        return elapsed < self.max_runtime_seconds

    def increment_cycle(self) -> None:
        self.cycle_count += 1
        self.tasks_this_cycle = 0

    def increment_task(self) -> None:
        self.tasks_this_cycle += 1

    def increment_agent_call(self) -> None:
        self.agent_calls += 1

    def increment_provider_call(self) -> None:
        self.provider_calls += 1

    def add_runtime(self, seconds: float) -> None:
        self.total_runtime_seconds += seconds

    def add_cost(self, cost: float) -> None:
        self.total_cost += cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cycles": self.max_cycles,
            "max_tasks_per_cycle": self.max_tasks_per_cycle,
            "max_agent_calls": self.max_agent_calls,
            "max_retries": self.max_retries,
            "max_provider_calls": self.max_provider_calls,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_cost": self.max_cost,
            "max_parallelism": self.max_parallelism,
            "cycle_count": self.cycle_count,
            "tasks_this_cycle": self.tasks_this_cycle,
            "agent_calls": self.agent_calls,
            "provider_calls": self.provider_calls,
            "total_runtime_seconds": self.total_runtime_seconds,
            "total_cost": self.total_cost,
            "start_time": self.start_time,
        }


class ContinuousLoop:
    """Continuous research loop manager.

    Wraps AutonomousResearchLoop for continuous operation with:
    - Event-driven triggers
    - Research budget enforcement
    - Cooldown management
    - Intelligence state management

    Uses existing AutonomousResearchLoop — never duplicates it.
    """

    def __init__(
        self,
        autonomous_loop: AutonomousResearchLoop | None = None,
        budget: ResearchBudget | None = None,
        state_manager: IntelligenceStateManager | None = None,
    ) -> None:
        self.autonomous_loop = autonomous_loop or AutonomousResearchLoop()
        self.budget = budget or ResearchBudget()
        self.state_manager = state_manager or IntelligenceStateManager()
        self.cooldowns: list[CooldownEntry] = []
        self.trigger_history: list[TriggerEvent] = []
        self._running: bool = False
        self._start_time: str = ""

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_state(self) -> IntelligenceState:
        return self.state_manager.current_state

    @property
    def cooldowns_list(self) -> list[CooldownEntry]:
        return list(self.cooldowns)

    @property
    def trigger_history_list(self) -> list[TriggerEvent]:
        return list(self.trigger_history)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_trigger(
        self,
        trigger_type: TriggerType,
        provenance: str,
        symbol: str = "",
        timeframe: str = "",
        context: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Create a trigger event."""
        now = self._now()
        cycle_id = self.state_manager.cycle_id

        trigger = TriggerEvent(
            trigger_type=trigger_type,
            timestamp=now,
            provenance=provenance,
            context=context or {},
            symbol=symbol,
            timeframe=timeframe,
            cycle_id=cycle_id,
        )
        self.trigger_history.append(trigger)
        return trigger

    def is_in_cooldown(self, cooldown_type: CooldownType, key: str) -> bool:
        """Check if a specific key is in cooldown."""
        now = datetime.now(timezone.utc)

        for entry in self.cooldowns:
            if entry.cooldown_type == cooldown_type and entry.key == key:
                if not entry.is_expired():
                    return True
                # Clean up expired entries
                self.cooldowns.remove(entry)

        return False

    def add_cooldown(
        self,
        cooldown_type: CooldownType,
        key: str,
        duration_seconds: float,
        reason: str = "",
    ) -> CooldownEntry:
        """Add a cooldown entry."""
        now = datetime.now(timezone.utc)
        expires_at = (now.timestamp() + duration_seconds)

        # Convert back to ISO format
        try:
            expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            expires_at_iso = ""

        entry = CooldownEntry(
            cooldown_type=cooldown_type,
            key=key,
            expires_at=expires_at_iso,
            created_at=now.isoformat(),
            reason=reason or f"cooldown_{cooldown_type.value}",
        )
        self.cooldowns.append(entry)
        return entry

    def clean_expired_cooldowns(self) -> int:
        """Remove expired cooldown entries. Returns count removed."""
        before = len(self.cooldowns)
        self.cooldowns = [c for c in self.cooldowns if not c.is_expired()]
        return before - len(self.cooldowns)

    def _check_budget(self, trigger: TriggerEvent) -> None:
        """Check all budget constraints. Raises if exceeded."""
        if not self.budget.check_cycle_budget():
            raise ResearchBudgetExceeded("max_cycles", self.budget.cycle_count, self.budget.max_cycles)

        if not self.budget.check_runtime():
            raise ResearchBudgetExceeded("max_runtime", self.budget.total_runtime_seconds, self.budget.max_runtime_seconds)

        if self.budget.max_cost is not None and self.budget.total_cost >= self.budget.max_cost:
            raise ResearchBudgetExceeded("max_cost", self.budget.total_cost, self.budget.max_cost)

    def _update_state_for_trigger(self, trigger: TriggerEvent) -> None:
        """Update intelligence state based on trigger type."""
        state_map: dict[TriggerType, IntelligenceState] = {
            TriggerType.SCHEDULED: IntelligenceState.OBSERVING,
            TriggerType.OPPORTUNITY_DETECTED: IntelligenceState.CHANGE_DETECTED,
            TriggerType.REGIME_CHANGED: IntelligenceState.CHANGE_DETECTED,
            TriggerType.DRIFT_DETECTED: IntelligenceState.CHANGE_DETECTED,
            TriggerType.CLAIM_WEAKENED: IntelligenceState.RESEARCHING,
            TriggerType.VALIDATION_FAILED: IntelligenceState.RESEARCHING,
            TriggerType.DATA_RESTORED: IntelligenceState.OBSERVING,
            TriggerType.HUMAN_REQUESTED: IntelligenceState.HUMAN_REVIEW,
            TriggerType.RECURRING_RESEARCH: IntelligenceState.OBSERVING,
            TriggerType.MANUAL_REVIEW: IntelligenceState.HUMAN_REVIEW,
        }

        target_state = state_map.get(trigger.trigger_type, IntelligenceState.OBSERVING)

        try:
            self.state_manager.transition(
                target_state,
                reason=f"trigger_{trigger.trigger_type.value}",
                provenance=f"ContinuousLoop._update_state_for_trigger ({trigger.provenance})",
            )
        except ValueError:
            # If transition invalid, stay in current state with note
            pass

    def run_cycle(
        self,
        trigger: TriggerEvent | None = None,
        symbol_scope: str = "",
        timeframe_scope: str = "",
    ) -> AutonomousResearchReport:
        """Run a single research cycle.

        If trigger is None, uses SCHEDULED trigger.
        """
        if trigger is None:
            trigger = self.create_trigger(
                TriggerType.SCHEDULED,
                "ContinuousLoop.run_cycle",
                symbol_scope,
                timeframe_scope,
            )

        self._check_budget(trigger)
        self._update_state_for_trigger(trigger)
        self.budget.increment_cycle()
        self.budget.increment_task()  # This cycle counts as a task

        cycle_start = time.time()

        try:
            # Run the autonomous loop cycle
            report = self.autonomous_loop.run_cycle(
                symbol_scope=symbol_scope,
                timeframe_scope=timeframe_scope,
            )

            cycle_duration = time.time() - cycle_start
            self.budget.add_runtime(cycle_duration)

            return report

        except ResearchBudgetExceeded:
            raise
        except Exception as e:
            self.budget.add_runtime(time.time() - cycle_start)
            raise

    def run_continuous(
        self,
        max_cycles: int | None = None,
        symbol_scope: str = "",
        timeframe_scope: str = "",
    ) -> list[AutonomousResearchReport]:
        """Run continuous research cycles until budget exhausted or max_cycles reached.

        Returns list of reports from each cycle.
        """
        if max_cycles is None:
            max_cycles = self.budget.max_cycles

        self._running = True
        self._start_time = self._now()
        reports: list[AutonomousResearchReport] = []

        # Initialize state
        self.state_manager.transition(
            IntelligenceState.INITIALIZING,
            reason="continuous_operation_start",
            provenance="ContinuousLoop.run_continuous",
        )
        self.state_manager.transition(
            IntelligenceState.OBSERVING,
            reason="continuous_operation_observing",
            provenance="ContinuousLoop.run_continuous",
        )

        cycle_count = 0

        while cycle_count < max_cycles and self.budget.check_cycle_budget():
            cycle_count += 1
            self.budget.increment_cycle()

            trigger = self.create_trigger(
                TriggerType.SCHEDULED,
                "ContinuousLoop.run_continuous",
                symbol_scope,
                timeframe_scope,
            )

            try:
                report = self.run_cycle(trigger, symbol_scope, timeframe_scope)
                reports.append(report)

                # Update state based on cycle result
                if report.validation_status == "VALIDATED":
                    self.state_manager.transition(
                        IntelligenceState.LEARNING,
                        reason=f"cycle_{cycle_count}_validated",
                        provenance="ContinuousLoop.run_continuous",
                    )
                elif report.conflict_count > 0:
                    self.state_manager.transition(
                        IntelligenceState.RESEARCHING,
                        reason=f"cycle_{cycle_count}_conflicts",
                        provenance="ContinuousLoop.run_continuous",
                    )

            except ResearchBudgetExceeded:
                self.state_manager.transition(
                    IntelligenceState.PAUSED,
                    reason="budget_exceeded",
                    provenance="ContinuousLoop.run_continuous",
                )
                break

            except Exception as e:
                self.state_manager.transition(
                    IntelligenceState.ERROR,
                    reason=f"cycle_error: {str(e)[:100]}",
                    provenance="ContinuousLoop.run_continuous",
                )
                # Continue to next cycle if budget allows
                if not self.budget.check_cycle_budget():
                    break
                continue

        # Finalize
        self.state_manager.transition(
            IntelligenceState.STABLE,
            reason=f"continuous_operation_complete_{len(reports)}_cycles",
            provenance="ContinuousLoop.run_continuous",
        )
        self._running = False

        return reports

    def stop(self) -> None:
        """Stop the continuous loop."""
        self._running = False
        self.state_manager.transition(
            IntelligenceState.PAUSED,
            reason="manual_stop",
            provenance="ContinuousLoop.stop",
        )

    def get_status(self) -> dict[str, Any]:
        """Get current loop status."""
        return {
            "running": self._running,
            "current_state": self.current_state.value,
            "cycle_id": self.state_manager.cycle_id,
            "context_version": self.state_manager.context_version,
            "budget": self.budget.to_dict(),
            "active_cooldowns": [c.to_dict() for c in self.cooldowns if not c.is_expired()],
            "trigger_count": len(self.trigger_history),
            "state_history": [t.to_dict() for t in self.state_manager.state_history],
            "start_time": self._start_time,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "current_state": self.current_state.value,
            "cycle_id": self.state_manager.cycle_id,
            "budget": self.budget.to_dict(),
            "cooldowns": [c.to_dict() for c in self.cooldowns],
            "triggers": [t.to_dict() for t in self.trigger_history],
            "state_manager": self.state_manager.to_dict(),
            "start_time": self._start_time,
        }
