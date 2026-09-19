# -*- coding: utf-8 -*-
"""Phase J5 — Multiple Testing Awareness.

Tracks multiple hypothesis testing to prevent false confidence.

When many hypotheses are tested simultaneously, random chance
produces "significant" results. This module:

1. Tracks total tests per research cycle
2. Applies multiple testing correction to claim confidence
3. Labels exploratory vs confirmatory research
4. Prevents exploratory results from being treated as production truth
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TestingMode(Enum):
    """Research testing mode."""
    EXPLORATORY = "exploratory"
    CONFIRMATORY = "confirmatory"


@dataclass
class TestSession:
    """A session of multiple hypothesis tests."""
    session_id: str = ""
    testing_mode: TestingMode = TestingMode.EXPLORATORY
    hypothesis_count: int = 0
    tests_run: int = 0
    significant_results: int = 0
    bonferroni_threshold: float = 0.05
    fdr_threshold: float = 0.10
    created_at: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        if not self.session_id:
            now = datetime.now(timezone.utc).isoformat()
            self.session_id = f"SES-{hashlib.sha256(now.encode()).hexdigest()[:10].upper()}"
            if not self.created_at:
                self.created_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "testing_mode": self.testing_mode.value,
            "hypothesis_count": self.hypothesis_count,
            "tests_run": self.tests_run,
            "significant_results": self.significant_results,
            "bonferroni_threshold": self.bonferroni_threshold,
            "fdr_threshold": self.fdr_threshold,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


def bonferroni_correction(
    p_value: float,
    n_tests: int,
) -> float:
    """Apply Bonferroni correction to a p-value.

    Adjusted p = p_value * n_tests (capped at 1.0)
    """
    if n_tests <= 0:
        return p_value
    return min(p_value * n_tests, 1.0)


def fdr_bh_correction(
    p_values: list[float],
    q: float = 0.10,
) -> list[bool]:
    """Benjamini-Hochberg FDR correction.

    Returns list of booleans indicating whether each hypothesis
    is rejected at level q.
    """
    if not p_values:
        return []

    n = len(p_values)
    # Sort by p-value, keep original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    rejects = [False] * n

    for rank, (orig_idx, p) in enumerate(indexed, 1):
        threshold = (rank / n) * q
        if p <= threshold:
            rejects[orig_idx] = True
        else:
            break  # BH procedure: stop at first non-rejection

    return rejects


def adjust_confidence_for_multiple_testing(
    confidence: float,
    n_tests: int,
    mode: TestingMode = TestingMode.EXPLORATORY,
) -> float:
    """Adjust confidence based on number of tests run.

    Exploratory tests get stronger penalty.
    Confirmatory tests get lighter penalty.

    NEVER converts this to trading probability.
    """
    if n_tests <= 1:
        return confidence

    if mode == TestingMode.EXPLORATORY:
        # Stronger penalty for exploratory: sqrt scaling
        penalty = 1.0 / math.sqrt(n_tests)
    else:
        # Lighter penalty for confirmatory: log scaling
        penalty = 1.0 / (1.0 + math.log2(n_tests))

    return confidence * penalty


class MultipleTestingAwareness:
    """Tracks and corrects for multiple hypothesis testing."""

    def __init__(self, default_mode: TestingMode = TestingMode.EXPLORATORY) -> None:
        self._sessions: dict[str, TestSession] = {}
        self._default_mode = default_mode
        self._total_tests: int = 0
        self._total_significant: int = 0

    def create_session(
        self,
        testing_mode: TestingMode | None = None,
        hypothesis_count: int = 0,
    ) -> TestSession:
        """Create a new test session."""
        mode = testing_mode or self._default_mode
        session = TestSession(
            testing_mode=mode,
            hypothesis_count=hypothesis_count,
        )
        self._sessions[session.session_id] = session
        return session

    def record_test(
        self,
        session_id: str,
        p_value: float = 1.0,
        significant: bool = False,
    ) -> None:
        """Record a test result in a session."""
        session = self._sessions.get(session_id)
        if not session:
            return
        session.tests_run += 1
        self._total_tests += 1
        if significant:
            session.significant_results += 1
            self._total_significant += 1

    def get_session(self, session_id: str) -> TestSession | None:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def get_corrected_confidence(
        self,
        confidence: float,
        n_tests: int,
        mode: TestingMode | None = None,
    ) -> float:
        """Get confidence corrected for multiple testing."""
        m = mode or self._default_mode
        return adjust_confidence_for_multiple_testing(confidence, n_tests, m)

    def is_exploratory_result(self, session_id: str) -> bool:
        """Check if a session's results are exploratory.

        Exploratory results should NOT be treated as production truth.
        """
        session = self._sessions.get(session_id)
        if not session:
            return True  # Unknown → treat as exploratory
        return session.testing_mode == TestingMode.EXPLORATORY

    @property
    def total_tests(self) -> int:
        return self._total_tests

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tests": self._total_tests,
            "total_significant": self._total_significant,
            "sessions": len(self._sessions),
            "default_mode": self._default_mode.value,
        }