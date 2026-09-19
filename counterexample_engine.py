# -*- coding: utf-8 -*-
"""Phase J5 — Counterexample Engine.

Finds counterexamples to claims and weakens claims accordingly.

A counterexample:
- claim_id
- matching_context
- contradictory_context
- outcome
- evidence
- timestamp
- provenance

When a counterexample is found:
- Claim is NOT auto-rejected
- Claim is marked WEAKENED or UNSTABLE
- Human review may be triggered
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_intelligence_model import (
    Claim,
    ClaimStatus,
    Counterexample as ModelCounterexample,
)


@dataclass
class CounterexampleSearch:
    """A single counterexample search result."""
    counterexample_id: str = ""
    claim_id: str = ""
    matching_context: dict[str, Any] = field(default_factory=dict)
    contradictory_context: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    evidence: list[str] = field(default_factory=list)
    timestamp: str = ""
    provenance: str = ""
    severity: str = "minor"  # minor | moderate | significant | major

    def __post_init__(self) -> None:
        if not self.counterexample_id:
            now = datetime.now(timezone.utc).isoformat()
            self.counterexample_id = (
                f"CE-{hashlib.sha256(f'{now}{self.claim_id}'.encode()).hexdigest()[:10].upper()}"
            )
            if not self.timestamp:
                self.timestamp = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "counterexample_id": self.counterexample_id,
            "claim_id": self.claim_id,
            "matching_context": self.matching_context,
            "contradictory_context": self.contradictory_context,
            "outcome": self.outcome,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
            "severity": self.severity,
        }


@dataclass
class CounterexampleResult:
    """Result of a counterexample search against a claim."""
    claim_id: str = ""
    claim_text: str = ""
    original_status: str = ""
    new_status: str = ""
    counterexamples: list[CounterexampleSearch] = field(default_factory=list)
    weakened: bool = False
    stability_score_before: float = 0.0
    stability_score_after: float = 0.0
    human_review_triggered: bool = False
    search_timestamp: str = ""
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "original_status": self.original_status,
            "new_status": self.new_status,
            "counterexample_count": len(self.counterexamples),
            "counterexamples": [c.to_dict() for c in self.counterexamples],
            "weakened": self.weakened,
            "stability_score_before": self.stability_score_before,
            "stability_score_after": self.stability_score_after,
            "human_review_triggered": self.human_review_triggered,
            "search_timestamp": self.search_timestamp,
            "provenance": self.provenance,
        }


def _compute_stability(
    claim: Claim,
    counterexample_count: int,
) -> float:
    """Compute claim stability after counterexample search."""
    base = claim.stability
    # Each counterexample reduces stability
    penalty = min(counterexample_count * 0.15, 0.6)
    return max(0.0, base - penalty)


def _determine_new_status(
    original_status: ClaimStatus,
    counterexample_count: int,
    severity: str,
) -> ClaimStatus:
    """Determine new claim status after counterexample found."""
    if counterexample_count == 0:
        return original_status

    if original_status == ClaimStatus.SUPPORTED:
        if severity in ("significant", "major") or counterexample_count >= 3:
            return ClaimStatus.UNSTABLE
        return ClaimStatus.TESTED

    if original_status == ClaimStatus.TESTED:
        if severity in ("significant", "major") or counterexample_count >= 2:
            return ClaimStatus.UNSTABLE
        return ClaimStatus.UNTESTED

    return original_status


class CounterexampleEngine:
    """Searches for counterexamples to claims and weakens them.

    Never auto-rejects a claim. Only weakens or marks unstable.
    Human review determines final disposition.
    """

    def __init__(
        self,
        auto_weaken: bool = True,
        max_counterexamples_per_claim: int = 10,
    ) -> None:
        self._searches: list[CounterexampleSearch] = []
        self._results: list[CounterexampleResult] = []
        self._auto_weaken = auto_weaken
        self._max_counterexamples = max_counterexamples_per_claim

    def search(
        self,
        claim: Claim,
        historical_outcomes: list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> CounterexampleResult:
        """Search for counterexamples to a claim.

        Args:
            claim: The claim to test
            historical_outcomes: Historical outcomes to search
            context: Additional context for matching

        Returns:
            CounterexampleResult with findings
        """
        now = datetime.now(timezone.utc).isoformat()
        counterexamples: list[CounterexampleSearch] = []

        if not historical_outcomes:
            # No data to search — return empty result
            result = CounterexampleResult(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                original_status=claim.status.value if isinstance(claim.status, ClaimStatus) else str(claim.status),
                new_status=claim.status.value if isinstance(claim.status, ClaimStatus) else str(claim.status),
                counterexamples=[],
                weakened=False,
                stability_score_before=claim.stability,
                stability_score_after=claim.stability,
                human_review_triggered=False,
                search_timestamp=now,
                provenance="CounterexampleEngine.search (no data)",
            )
            self._results.append(result)
            return result

        # Search for contradictory outcomes
        for outcome in historical_outcomes:
            outcome_type = getattr(outcome, "outcome_type", "")
            outcome_context = getattr(outcome, "context", {}) or {}

            # Check if this outcome contradicts the claim
            # Simple heuristic: if outcome was invalidated and claim context matches
            if outcome_type == "INVALIDATED":
                # Check context overlap
                claim_context = claim.observation_ids
                if claim_context:
                    # Check for matching dimensions
                    matching_dims = [
                        dim for dim in claim_context
                        if str(outcome_context.get(dim, "")).lower() == "match"
                    ]
                else:
                    matching_dims = []

                ce = CounterexampleSearch(
                    claim_id=claim.claim_id,
                    matching_context={"observation_ids": claim_context},
                    contradictory_context={
                        "outcome_type": outcome_type,
                        "realized_r": getattr(outcome, "realized_r", 0.0),
                        "context": outcome_context,
                    },
                    outcome=outcome_type,
                    evidence=[f"Outcome {outcome_type} contradicts claim context"],
                    provenance="CounterexampleEngine.search",
                    severity="moderate" if len(matching_dims) > 0 else "minor",
                )
                counterexamples.append(ce)

        # Limit results
        counterexamples = counterexamples[:self._max_counterexamples]

        # Determine new status
        original_status = claim.status
        severity = "major" if len(counterexamples) >= 3 else ("significant" if len(counterexamples) >= 2 else "minor")
        new_status = _determine_new_status(original_status, len(counterexamples), severity)

        # Apply weakening if enabled
        weakened = False
        if self._auto_weaken and new_status != original_status:
            claim.status = new_status
            claim.stability = _compute_stability(claim, len(counterexamples))
            claim.version += 1
            claim.limitations.append(f"COUNTEREXAMPLE_{len(counterexamples)}_FOUND")
            weakened = True

        # Trigger human review for significant weakening
        human_review_triggered = severity in ("significant", "major") and weakened

        result = CounterexampleResult(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            original_status=original_status.value if isinstance(original_status, ClaimStatus) else str(original_status),
            new_status=new_status.value if isinstance(new_status, ClaimStatus) else str(new_status),
            counterexamples=counterexamples,
            weakened=weakened,
            stability_score_before=claim.stability,
            stability_score_after=claim.stability,
            human_review_triggered=human_review_triggered,
            search_timestamp=now,
            provenance="CounterexampleEngine.search",
        )

        self._searches.extend(counterexamples)
        self._results.append(result)
        return result

    def get_searches(self) -> list[CounterexampleSearch]:
        """Get all counterexample searches."""
        return list(self._searches)

    def get_results(self) -> list[CounterexampleResult]:
        """Get all counterexample results."""
        return list(self._results)

    def count(self) -> int:
        """Total searches performed."""
        return len(self._searches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_count": self.count(),
            "result_count": len(self._results),
            "auto_weaken": self._auto_weaken,
            "latest_result": self._results[-1].to_dict() if self._results else None,
        }