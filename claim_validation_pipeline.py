# -*- coding: utf-8 -*-
"""Phase J6 — Claim Validation Pipeline.

Every important research claim must have:
- claim_id, statement, source, evidence, sample size, time period
- symbols, timeframes, confidence/calibration information
- validation status, first_seen, last_tested, expiry/decay
- contradictory evidence, counterexamples

States: UNTESTED, TESTED, SUPPORTED, UNSTABLE, REJECTED, EXPIRED
No automatic conversion to SUPPORTED without evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_intelligence_model import Claim, ClaimStatus


class ClaimValidationPipeline:
    """Validates research claims through a structured pipeline."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._validation_history: dict[str, list[dict[str, Any]]] = {}

    def create_claim(
        self,
        claim_id: str,
        text: str,
        source: str = "",
        evidence: list[str] | None = None,
        sample_size: int = 0,
        validation_windows: list[str] | None = None,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        confidence: float = 0.0,
        stability: float = 0.0,
        effect_size: float = 0.0,
        limitations: list[str] | None = None,
        observation_ids: list[str] | None = None,
        experiment_ids: list[str] | None = None,
    ) -> Claim:
        """Create a new claim with full metadata."""
        now = datetime.now(timezone.utc).isoformat()
        claim = Claim(
            claim_id=claim_id,
            text=text,
            status=ClaimStatus.UNTESTED,
            evidence=evidence or [],
            sample_size=sample_size,
            validation_windows=validation_windows or [],
            first_observed=now,
            last_validated=now,
            confidence=confidence,
            stability=stability,
            effect_size=effect_size,
            limitations=limitations or [],
            observation_ids=observation_ids or [],
            experiment_ids=experiment_ids or [],
        )
        self._claims[claim_id] = claim
        self._validation_history[claim_id] = []
        self._log_validation(claim_id, "CREATED", "Claim created")
        return claim

    def add_evidence(self, claim_id: str, evidence_ref: str) -> bool:
        """Add evidence reference to a claim."""
        if claim_id not in self._claims:
            return False
        claim = self._claims[claim_id]
        claim.evidence.append(evidence_ref)
        claim.last_validated = datetime.now(timezone.utc).isoformat()
        self._log_validation(claim_id, "EVIDENCE_ADDED", f"Evidence: {evidence_ref}")
        return True

    def add_contradictory_evidence(self, claim_id: str, evidence_ref: str) -> bool:
        """Add contradictory evidence to a claim."""
        if claim_id not in self._claims:
            return False
        claim = self._claims[claim_id]
        claim.evidence.append(f"CONTRADICTED:{evidence_ref}")
        claim.last_validated = datetime.now(timezone.utc).isoformat()
        self._log_validation(claim_id, "CONTRADICTORY_EVIDENCE", f"Contradicted by: {evidence_ref}")
        return True

    def add_counterexample(self, claim_id: str, counterexample_ref: str) -> bool:
        """Add a counterexample to a claim."""
        if claim_id not in self._claims:
            return False
        claim = self._claims[claim_id]
        claim.limitations.append(f"COUNTEREXAMPLE:{counterexample_ref}")
        claim.last_validated = datetime.now(timezone.utc).isoformat()
        self._log_validation(claim_id, "COUNTEREXAMPLE", f"Counterexample: {counterexample_ref}")
        return True

    def update_status(
        self, claim_id: str, new_status: ClaimStatus, reason: str = ""
    ) -> Claim:
        """Update claim status with audit trail.

        IMPORTANT: No automatic conversion to SUPPORTED without evidence.
        """
        if claim_id not in self._claims:
            raise ValueError(f"Claim {claim_id} not found")

        claim = self._claims[claim_id]
        old_status = claim.status

        # Enforce: cannot go directly to SUPPORTED without evidence
        if new_status == ClaimStatus.SUPPORTED and len(claim.evidence) == 0:
            raise ValueError(
                f"Cannot promote claim {claim_id} to SUPPORTED without evidence"
            )

        # Enforce: cannot go to SUPPORTED if contradicted
        contradicted = any(
            e.startswith("CONTRADICTED:") for e in claim.evidence
        )
        if new_status == ClaimStatus.SUPPORTED and contradicted:
            raise ValueError(
                f"Cannot promote claim {claim_id} to SUPPORTED: has contradictory evidence"
            )

        claim.status = new_status
        claim.last_validated = datetime.now(timezone.utc).isoformat()
        self._log_validation(
            claim_id,
            f"{old_status.value}_TO_{new_status.value}",
            reason or f"Status change: {old_status.value} → {new_status.value}",
        )
        return claim

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def get_validation_history(self, claim_id: str) -> list[dict[str, Any]]:
        return self._validation_history.get(claim_id, [])

    def get_claims_by_status(self, status: ClaimStatus) -> list[Claim]:
        return [c for c in self._claims.values() if c.status == status]

    def get_all_claims(self) -> list[Claim]:
        return list(self._claims.values())

    def _log_validation(self, claim_id: str, action: str, detail: str) -> None:
        if claim_id not in self._validation_history:
            self._validation_history[claim_id] = []
        self._validation_history[claim_id].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "detail": detail,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": {k: self._to_claim_dict(v) for k, v in self._claims.items()},
            "validation_history": self._validation_history,
            "summary": {
                "total": len(self._claims),
                "untested": len(self.get_claims_by_status(ClaimStatus.UNTESTED)),
                "tested": len(self.get_claims_by_status(ClaimStatus.TESTED)),
                "supported": len(self.get_claims_by_status(ClaimStatus.SUPPORTED)),
                "unstable": len(self.get_claims_by_status(ClaimStatus.UNSTABLE)),
                "rejected": len(self.get_claims_by_status(ClaimStatus.REJECTED)),
            },
        }

    def _to_claim_dict(self, claim: Claim) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "text": claim.text,
            "status": claim.status.value,
            "evidence": claim.evidence,
            "sample_size": claim.sample_size,
            "validation_windows": claim.validation_windows,
            "first_observed": claim.first_observed,
            "last_validated": claim.last_validated,
            "confidence": claim.confidence,
            "stability": claim.stability,
            "effect_size": claim.effect_size,
            "limitations": claim.limitations,
            "version": claim.version,
            "parent_claim_id": claim.parent_claim_id,
            "observation_ids": claim.observation_ids,
            "experiment_ids": claim.experiment_ids,
        }