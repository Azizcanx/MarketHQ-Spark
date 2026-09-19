# -*- coding: utf-8 -*-
"""Phase J5 — Situation Report.

Research-first market situation summary for HQ UI.
Presents findings — never trading instructions.

NOT "do this trade". Research context only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SituationReport:
    """Situation report for AzizBusiness HQ.

    Presents research findings, market context, and open items.
    NEVER issues trading instructions or guarantees.
    """

    report_id: str = ""
    generated_at: str = ""
    market_context: dict[str, Any] = field(default_factory=dict)
    active_opportunities: list[dict[str, Any]] = field(default_factory=list)
    recent_changes: list[dict[str, Any]] = field(default_factory=list)
    regime: str = "UNKNOWN"
    research_findings: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    failed_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    recent_memory: list[dict[str, Any]] = field(default_factory=list)
    uncertainty_flags: list[str] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    human_review_items: list[dict[str, Any]] = field(default_factory=list)
    intelligence_state: str = "OBSERVING"
    cycle_id: str = ""
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.report_id:
            now = datetime.now(timezone.utc).isoformat()
            self.report_id = f"SRPT-{hashlib.sha256(now.encode()).hexdigest()[:10].upper()}"
            if not self.generated_at:
                self.generated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "market_context": self.market_context,
            "active_opportunities": self.active_opportunities,
            "recent_changes": self.recent_changes,
            "regime": self.regime,
            "research_findings": self.research_findings,
            "conflict_count": len(self.conflicts),
            "validation_summary": self.validation_summary,
            "failed_hypothesis_count": len(self.failed_hypotheses),
            "recent_memory_count": len(self.recent_memory),
            "uncertainty_flags": self.uncertainty_flags,
            "data_quality": self.data_quality,
            "human_review_count": len(self.human_review_items),
            "intelligence_state": self.intelligence_state,
            "cycle_id": self.cycle_id,
            "provenance": self.provenance,
        }

    def summary_text(self) -> str:
        """Human-readable summary — research context, NOT trading advice."""
        lines = [
            f"Situation Report {self.report_id}",
            f"Generated: {self.generated_at}",
            f"Regime: {self.regime}",
            f"Intelligence State: {self.intelligence_state}",
            f"Active Opportunities: {len(self.active_opportunities)}",
            f"Recent Changes: {len(self.recent_changes)}",
            f"Conflicts: {len(self.conflicts)}",
            f"Failed Hypotheses: {len(self.failed_hypotheses)}",
            f"Uncertainty Flags: {len(self.uncertainty_flags)}",
            f"Human Review Items: {len(self.human_review_items)}",
        ]
        if self.uncertainty_flags:
            lines.append(f"Uncertainty: {'; '.join(self.uncertainty_flags)}")
        return "\n".join(lines)


def build_situation_report(
    market_context: dict[str, Any] | None = None,
    active_opportunities: list[dict[str, Any]] | None = None,
    recent_changes: list[dict[str, Any]] | None = None,
    regime: str = "UNKNOWN",
    research_findings: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    validation_summary: dict[str, Any] | None = None,
    failed_hypotheses: list[dict[str, Any]] | None = None,
    recent_memory: list[dict[str, Any]] | None = None,
    uncertainty_flags: list[str] | None = None,
    data_quality: dict[str, Any] | None = None,
    human_review_items: list[dict[str, Any]] | None = None,
    intelligence_state: str = "OBSERVING",
    cycle_id: str = "",
    provenance: str = "",
) -> SituationReport:
    """Build a situation report from research components."""
    return SituationReport(
        market_context=market_context or {},
        active_opportunities=active_opportunities or [],
        recent_changes=recent_changes or [],
        regime=regime,
        research_findings=research_findings or [],
        conflicts=conflicts or [],
        validation_summary=validation_summary or {},
        failed_hypotheses=failed_hypotheses or [],
        recent_memory=recent_memory or [],
        uncertainty_flags=uncertainty_flags or [],
        data_quality=data_quality or {},
        human_review_items=human_review_items or [],
        intelligence_state=intelligence_state,
        cycle_id=cycle_id,
        provenance=provenance or "build_situation_report",
    )