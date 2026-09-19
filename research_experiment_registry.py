# -*- coding: utf-8 -*-
"""Phase J5 — Research Experiment Registry.

Extends research_intelligence_engine with:
- Duplicate experiment detection (by config hash)
- Cached result reuse
- Provenance tracking
- Experiment status management
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from research_intelligence_model import (
    ExperimentRegistry,
    ExperimentStatus,
)


class DuplicatePolicy(Enum):
    """How to handle duplicate experiment configs."""
    BLOCK = "block"
    USE_CACHED = "use_cached"
    LOG_ONLY = "log_only"


@dataclass
class ExperimentRecord:
    """Extended experiment record with dedup support."""
    experiment_id: str = ""
    hypothesis_id: str = ""
    config_hash: str = ""
    dataset: str = ""
    cutoff: str = ""
    features: list[str] = field(default_factory=list)
    methodology: str = ""
    baseline: str = ""
    challenger: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.REGISTERED
    provenance: str = ""
    created_at: str = ""
    completed_at: str = ""
    duplicate_of: str = ""  # If this is a duplicate, points to original
    cached_result_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "config_hash": self.config_hash,
            "dataset": self.dataset,
            "cutoff": self.cutoff,
            "features": self.features,
            "methodology": self.methodology,
            "baseline": self.baseline,
            "challenger": self.challenger,
            "result": self.result,
            "status": self.status.value,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "duplicate_of": self.duplicate_of,
            "cached_result_used": self.cached_result_used,
        }


def compute_config_hash(
    hypothesis_id: str,
    dataset: str,
    cutoff: str,
    features: list[str],
    methodology: str,
    baseline: str = "",
    challenger: str = "",
) -> str:
    """Compute deterministic hash of experiment configuration."""
    config = {
        "hypothesis_id": hypothesis_id,
        "dataset": dataset,
        "cutoff": cutoff,
        "features": sorted(features),
        "methodology": methodology,
        "baseline": baseline,
        "challenger": challenger,
    }
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


class ResearchExperimentRegistryExtended:
    """Extended experiment registry with dedup and caching."""

    def __init__(
        self,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.USE_CACHED,
        max_experiments: int = 1000,
    ) -> None:
        self._experiments: dict[str, ExperimentRecord] = {}
        self._config_index: dict[str, str] = {}  # hash → experiment_id
        self._duplicate_policy = duplicate_policy
        self._max_experiments = max_experiments
        self._duplicate_count: int = 0

    def register(
        self,
        hypothesis_id: str,
        dataset: str,
        cutoff: str = "",
        features: list[str] | None = None,
        methodology: str = "",
        baseline: str = "",
        challenger: str = "",
        provenance: str = "",
    ) -> ExperimentRecord:
        """Register a new experiment, checking for duplicates."""
        features = features or []
        config_hash = compute_config_hash(
            hypothesis_id, dataset, cutoff, features, methodology, baseline, challenger
        )

        # Check for duplicate
        if config_hash in self._config_index:
            existing_id = self._config_index[config_hash]
            self._duplicate_count += 1

            if self._duplicate_policy == DuplicatePolicy.BLOCK:
                raise ValueError(
                    f"Duplicate experiment blocked: config_hash={config_hash}, "
                    f"existing_experiment={existing_id}"
                )
            elif self._duplicate_policy == DuplicatePolicy.USE_CACHED:
                existing = self._experiments[existing_id]
                # Return a new record pointing to cached result
                now = datetime.now(timezone.utc).isoformat()
                new_exp = ExperimentRecord(
                    experiment_id=f"EXP-CACHED-{hashlib.sha256(f'{now}{config_hash}'.encode()).hexdigest()[:10].upper()}",
                    hypothesis_id=hypothesis_id,
                    config_hash=config_hash,
                    dataset=dataset,
                    cutoff=cutoff,
                    features=features,
                    methodology=methodology,
                    baseline=baseline,
                    challenger=challenger,
                    result=existing.result,
                    status=ExperimentStatus.COMPLETED if existing.status == ExperimentStatus.COMPLETED else ExperimentStatus.REPRODUCED,
                    provenance=provenance or "ResearchExperimentRegistryExtended.register",
                    duplicate_of=existing_id,
                    cached_result_used=True,
                    created_at=now,
                )
                self._experiments[new_exp.experiment_id] = new_exp
                return new_exp
            # LOG_ONLY: continue to create new experiment

        # Create new experiment
        now = datetime.now(timezone.utc).isoformat()
        exp = ExperimentRecord(
            experiment_id=f"EXP-{hashlib.sha256(f'{now}{config_hash}'.encode()).hexdigest()[:12].upper()}",
            hypothesis_id=hypothesis_id,
            config_hash=config_hash,
            dataset=dataset,
            cutoff=cutoff,
            features=features,
            methodology=methodology,
            baseline=baseline,
            challenger=challenger,
            status=ExperimentStatus.REGISTERED,
            provenance=provenance or "ResearchExperimentRegistryExtended.register",
            created_at=now,
        )

        self._experiments[exp.experiment_id] = exp
        self._config_index[config_hash] = exp.experiment_id

        # Trim if needed
        while len(self._experiments) > self._max_experiments:
            oldest = next(iter(self._experiments))
            del self._experiments[oldest]

        return exp

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        """Get experiment by ID."""
        return self._experiments.get(experiment_id)

    def get_by_hash(self, config_hash: str) -> ExperimentRecord | None:
        """Get experiment by config hash."""
        if config_hash in self._config_index:
            return self._experiments.get(self._config_index[config_hash])
        return None

    def update_status(
        self, experiment_id: str, status: ExperimentStatus, result: dict[str, Any] | None = None
    ) -> bool:
        """Update experiment status and optional result."""
        exp = self._experiments.get(experiment_id)
        if not exp:
            return False
        exp.status = status
        if result:
            exp.result = result
        exp.completed_at = datetime.now(timezone.utc).isoformat()
        return True

    def get_duplicates_count(self) -> int:
        """Count duplicate attempts."""
        return self._duplicate_count

    def get_all(self) -> list[ExperimentRecord]:
        """Get all experiments."""
        return list(self._experiments.values())

    def count(self) -> int:
        """Total experiments."""
        return len(self._experiments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_count": self.count(),
            "config_index_count": len(self._config_index),
            "duplicate_count": self._duplicate_count,
            "duplicate_policy": self._duplicate_policy.value,
            "experiments": [e.to_dict() for e in self.get_all()],
        }