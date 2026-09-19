# -*- coding: utf-8 -*-
"""Phase J5 — Temporal Decay.

Configurable, deterministic, transparent decay for historical evidence.
Old evidence is NOT discarded but weighted less than new evidence.

Decay is NEVER converted to trading probability.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DecayMethod(Enum):
    """Decay calculation methods."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"


@dataclass
class DecayConfig:
    """Configuration for temporal decay."""
    method: DecayMethod = DecayMethod.EXPONENTIAL
    half_life_days: float = 90.0
    min_weight: float = 0.1
    max_weight: float = 1.0
    reference_date: str = ""

    def __post_init__(self) -> None:
        if not self.reference_date:
            self.reference_date = datetime.now(timezone.utc).isoformat()


@dataclass
class DecayScore:
    """Decay score for a piece of evidence or claim."""
    evidence_id: str = ""
    original_weight: float = 1.0
    decayed_weight: float = 1.0
    age_days: float = 0.0
    half_life_days: float = 90.0
    method: str = "exponential"
    calculated_at: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "original_weight": self.original_weight,
            "decayed_weight": self.decayed_weight,
            "age_days": round(self.age_days, 2),
            "half_life_days": self.half_life_days,
            "method": self.method,
            "calculated_at": self.calculated_at,
            "created_at": self.created_at,
        }


def compute_decay_weight(
    created_at: str,
    reference_date: str | None = None,
    method: DecayMethod = DecayMethod.EXPONENTIAL,
    half_life_days: float = 90.0,
    min_weight: float = 0.1,
    max_weight: float = 1.0,
) -> float:
    """Compute decay weight for evidence based on age.

    Args:
        created_at: ISO timestamp of evidence creation
        reference_date: ISO timestamp to calculate age from
        method: Decay method
        half_life_days: Days for weight to halve
        min_weight: Minimum weight floor
        max_weight: Maximum weight ceiling

    Returns:
        Weight between min_weight and max_weight
    """
    if not reference_date:
        reference_date = datetime.now(timezone.utc).isoformat()

    try:
        created = datetime.fromisoformat(created_at)
        ref = datetime.fromisoformat(reference_date)
    except (ValueError, TypeError):
        return max_weight

    age_days = (ref - created).total_seconds() / 86400.0

    if age_days <= 0:
        return max_weight

    if method == DecayMethod.LINEAR:
        # Linear decay: weight decreases linearly with age
        decay = max(0.0, 1.0 - (age_days / (half_life_days * 2)))
        weight = min_weight + (max_weight - min_weight) * decay
    elif method == DecayMethod.STEP:
        # Step decay: full weight for first half-life, then halved
        if age_days <= half_life_days:
            weight = max_weight
        elif age_days <= half_life_days * 2:
            weight = (max_weight + min_weight) / 2
        else:
            weight = min_weight
    else:
        # Exponential decay (default)
        # weight = max_weight * (0.5 ^ (age_days / half_life_days))
        exponent = -age_days / half_life_days
        raw = math.pow(2.0, exponent)
        weight = min_weight + (max_weight - min_weight) * raw

    return max(min_weight, min(max_weight, weight))


def decay_evidence_weight(
    evidence_id: str,
    created_at: str,
    config: DecayConfig | None = None,
) -> DecayScore:
    """Compute decay score for a single evidence item."""
    cfg = config or DecayConfig()
    weight = compute_decay_weight(
        created_at=created_at,
        reference_date=cfg.reference_date,
        method=cfg.method,
        half_life_days=cfg.half_life_days,
        min_weight=cfg.min_weight,
        max_weight=cfg.max_weight,
    )

    try:
        created = datetime.fromisoformat(created_at)
        ref = datetime.fromisoformat(cfg.reference_date)
        age_days = (ref - created).total_seconds() / 86400.0
    except (ValueError, TypeError):
        age_days = 0.0

    return DecayScore(
        evidence_id=evidence_id,
        original_weight=1.0,
        decayed_weight=weight,
        age_days=age_days,
        half_life_days=cfg.half_life_days,
        method=cfg.method.value,
        calculated_at=datetime.now(timezone.utc).isoformat(),
        created_at=created_at,
    )


def compute_weighted_confidence(
    items: list[dict[str, Any]],
    date_field: str = "created_at",
    id_field: str = "id",
    config: DecayConfig | None = None,
) -> float:
    """Compute confidence weighted by temporal decay.

    Args:
        items: List of dicts with 'confidence'/'weight' and date field
        date_field: Key for creation date
        id_field: Key for item identifier
        config: Decay configuration

    Returns:
        Weighted confidence (0-1), 0 if no items
    """
    if not items:
        return 0.0

    cfg = config or DecayConfig()
    total_weight = 0.0
    weighted_sum = 0.0

    for item in items:
        created_at = item.get(date_field, "")
        confidence = item.get("confidence", item.get("weight", 0.5))

        decay_score = compute_decay_weight(
            created_at=created_at,
            reference_date=cfg.reference_date,
            method=cfg.method,
            half_life_days=cfg.half_life_days,
            min_weight=cfg.min_weight,
            max_weight=cfg.max_weight,
        )

        total_weight += decay_score
        weighted_sum += confidence * decay_score

    if total_weight == 0:
        return 0.0

    return weighted_sum / total_weight