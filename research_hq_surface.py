# -*- coding: utf-8 -*-
"""Phase I — Human Research Review + HQ Synthesis + Permissions + Artifacts.

All research-only. No trading. No auto promotion.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any


class ReviewStatus(Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    ACCEPTED_FOR_RESEARCH = "accepted_for_research"
    REJECTED = "rejected"
    NEEDS_MORE_DATA = "needs_more_data"


class Permission(Enum):
    READ_MARKET_DATA = "read_market_data"
    READ_RESEARCH_MEMORY = "read_research_memory"
    READ_EXPERIMENTS = "read_experiments"
    CREATE_OBSERVATION = "create_observation"
    CREATE_HYPOTHESIS = "create_hypothesis"
    CREATE_EXPERIMENT = "create_experiment"
    CREATE_CLAIM = "create_claim"
    CREATE_OPPORTUNITY = "create_opportunity"
    CREATE_SETUP = "create_setup"
    REQUEST_HUMAN_REVIEW = "request_human_review"
    WRITE_RESEARCH_ARTIFACT = "write_research_artifact"
    RUN_BACKTEST = "run_backtest"


# ═══════════════════════════════════════════════════════════════════
# Human Research Review
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HumanReview:
    """Human research review of a research artifact.

    NOT trade approval. Research artifact review only.
    """
    review_id: str
    artifact_id: str
    artifact_type: str = ""  # opportunity / setup / claim / experiment / observation
    reviewer_notes: str = ""
    status: ReviewStatus = ReviewStatus.UNREVIEWED
    reviewed_at: str = ""
    reviewer_id: str = ""
    requested_data: list[str] = field(default_factory=list)
    rejection_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    cutoff: str = ""
    data_availability: dict[str, Any] = field(default_factory=dict)
    uncertainty_flags: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    agent_provenance: list[dict[str, Any]] = field(default_factory=list)
    validation_state: str = ""
    historical_evidence: str = ""
    failure_patterns: list[str] = field(default_factory=list)
    counterexamples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "reviewer_notes": self.reviewer_notes,
            "status": self.status.value,
            "reviewed_at": self.reviewed_at,
            "reviewer_id": self.reviewer_id,
            "requested_data": self.requested_data,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cutoff": self.cutoff,
            "data_availability": self.data_availability,
            "uncertainty_flags": self.uncertainty_flags,
            "conflicting_evidence": self.conflicting_evidence,
            "supporting_evidence": self.supporting_evidence,
            "agent_provenance": self.agent_provenance,
            "validation_state": self.validation_state,
            "historical_evidence": self.historical_evidence,
            "failure_patterns": self.failure_patterns,
            "counterexamples": self.counterexamples,
        }


# ═══════════════════════════════════════════════════════════════════
# Research Artifact
# ═══════════════════════════════════════════════════════════════════

class ArtifactType(Enum):
    REPORT = "report"
    EVIDENCE_BUNDLE = "evidence_bundle"
    EXPERIMENT_RESULT = "experiment_result"
    VALIDATION_REPORT = "validation_report"
    CLAIM_REPORT = "claim_report"
    FEATURE_ANALYSIS = "feature_analysis"
    BACKTEST_ARTIFACT = "backtest_artifact"
    CHART = "chart"
    JSON_SNAPSHOT = "json_snapshot"


@dataclass
class ResearchArtifact:
    """Research output artifact with full lineage.

    Never overwritten silently. Versioned.
    """
    artifact_id: str
    artifact_type: ArtifactType
    source_run: str = ""
    agent_id: str = ""
    version: str = "1.0"
    config_hash: str = ""
    data_cutoff: str = ""
    created_at: str = ""
    status: ReviewStatus = ReviewStatus.UNREVIEWED
    content_ref: str = ""  # reference to file/DB record
    lineage: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type.value,
            "source_run": self.source_run,
            "agent_id": self.agent_id,
            "version": self.version,
            "config_hash": self.config_hash,
            "data_cutoff": self.data_cutoff,
            "created_at": self.created_at,
            "status": self.status.value,
            "content_ref": self.content_ref,
            "lineage": self.lineage,
        }


# ═══════════════════════════════════════════════════════════════════
# Provenance Chain
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ProvenanceNode:
    """Single node in a research provenance chain."""
    node_id: str
    node_type: str  # setup / opportunity / agent / result / evidence / snapshot / memory / validation / claim / review
    source: str = ""
    version: str = "1.0"
    timestamp: str = ""
    config_hash: str = ""
    data_cutoff: str = ""
    status: str = ""
    missing_provenance: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "source": self.source,
            "version": self.version,
            "timestamp": self.timestamp,
            "config_hash": self.config_hash,
            "data_cutoff": self.data_cutoff,
            "status": self.status,
            "missing_provenance": self.missing_provenance,
        }


def build_provenance_chain(
    setup_id: str = "",
    opportunity_id: str = "",
    agent_results: list[dict[str, Any]] | None = None,
    evidence: list[str] | None = None,
    feature_snapshot_id: str = "",
    research_memory: list[str] | None = None,
    historical_evidence: str = "",
    validation_id: str = "",
    claim_id: str = "",
    review_id: str = "",
) -> list[ProvenanceNode]:
    """Build a provenance chain from setup through to human review.

    Missing provenance is explicitly marked, never assumed.
    """
    now = datetime.now(timezone.utc).isoformat()
    chain: list[ProvenanceNode] = []

    if setup_id:
        chain.append(ProvenanceNode(
            node_id=setup_id, node_type="setup",
            source="research_setup_phase_f", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="setup", node_type="setup",
            source="", timestamp=now, missing_provenance=True,
        ))

    if opportunity_id:
        chain.append(ProvenanceNode(
            node_id=opportunity_id, node_type="opportunity",
            source="opportunity_engine", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="opportunity", node_type="opportunity",
            source="", timestamp=now, missing_provenance=True,
        ))

    if agent_results:
        for i, ar in enumerate(agent_results):
            chain.append(ProvenanceNode(
                node_id=f"agent_result_{i}", node_type="agent_result",
                source=ar.get("agent_name", ""), timestamp=now,
                config_hash=ar.get("config_hash", ""),
            ))
    else:
        chain.append(ProvenanceNode(
            node_id="agent_results", node_type="agent_result",
            source="", timestamp=now, missing_provenance=True,
        ))

    if evidence:
        for i, ev in enumerate(evidence):
            chain.append(ProvenanceNode(
                node_id=f"evidence_{i}", node_type="evidence",
                source=ev, timestamp=now,
            ))
    else:
        chain.append(ProvenanceNode(
            node_id="evidence", node_type="evidence",
            source="", timestamp=now, missing_provenance=True,
        ))

    if feature_snapshot_id:
        chain.append(ProvenanceNode(
            node_id=feature_snapshot_id, node_type="feature_snapshot",
            source="feature_cache", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="feature_snapshot", node_type="feature_snapshot",
            source="", timestamp=now, missing_provenance=True,
        ))

    if research_memory:
        for i, mem in enumerate(research_memory):
            chain.append(ProvenanceNode(
                node_id=f"memory_{i}", node_type="research_memory",
                source=mem, timestamp=now,
            ))

    if historical_evidence:
        chain.append(ProvenanceNode(
            node_id="historical_evidence", node_type="historical_evidence",
            source=historical_evidence, timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="historical_evidence", node_type="historical_evidence",
            source="", timestamp=now, missing_provenance=True,
        ))

    if validation_id:
        chain.append(ProvenanceNode(
            node_id=validation_id, node_type="validation",
            source="research_validation_engine", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="validation", node_type="validation",
            source="", timestamp=now, missing_provenance=True,
        ))

    if claim_id:
        chain.append(ProvenanceNode(
            node_id=claim_id, node_type="claim",
            source="claim_engine", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="claim", node_type="claim",
            source="", timestamp=now, missing_provenance=True,
        ))

    if review_id:
        chain.append(ProvenanceNode(
            node_id=review_id, node_type="human_review",
            source="human_reviewer", timestamp=now,
        ))
    else:
        chain.append(ProvenanceNode(
            node_id="review", node_type="human_review",
            source="", timestamp=now, missing_provenance=True,
        ))

    return chain


# ═══════════════════════════════════════════════════════════════════
# HQ Synthesis
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HQSynthesis:
    """Research-first synthesis of market context, opportunities, setups.

    Preserves disagreement. Does NOT turn mixed signals into false consensus.
    """
    synthesis_id: str
    market_context: dict[str, Any] = field(default_factory=dict)
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    setups: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    historical_evidence: str = ""
    validation_state: str = ""
    uncertainty_flags: list[str] = field(default_factory=list)
    critic_findings: list[str] = field(default_factory=list)
    research_memory_refs: list[str] = field(default_factory=list)
    relevant_claims: list[str] = field(default_factory=list)
    agent_disagreement: dict[str, list[str]] = field(default_factory=dict)
    data_availability: dict[str, str] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "synthesis_id": self.synthesis_id,
            "market_context": self.market_context,
            "opportunities": self.opportunities,
            "setups": self.setups,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "historical_evidence": self.historical_evidence,
            "validation_state": self.validation_state,
            "uncertainty_flags": self.uncertainty_flags,
            "critic_findings": self.critic_findings,
            "research_memory_refs": self.research_memory_refs,
            "relevant_claims": self.relevant_claims,
            "agent_disagreement": self.agent_disagreement,
            "data_availability": self.data_availability,
            "created_at": self.created_at,
        }


def synthesize_hq(
    agent_directions: dict[str, str],
    agent_confidences: dict[str, float] | None = None,
    uncertainty_flags: list[str] | None = None,
    supporting_agents: list[str] | None = None,
    conflicting_agents: list[str] | None = None,
    unavailable_agents: list[str] | None = None,
    market_context: dict[str, Any] | None = None,
    setups: list[Any] | None = None,
    critic_findings: list[str] | None = None,
    research_memory_refs: list[str] | None = None,
    relevant_claims: list[str] | None = None,
    validation_state: str = "",
    historical_evidence: str = "",
) -> HQSynthesis:
    """Synthesize HQ research output preserving disagreement.

    Example:
        Trend: SHORT, Momentum: NEUTRAL, Liquidity: SHORT, Structure: UNAVAILABLE
        → "Evidence is mixed; trend and liquidity support SHORT,
           momentum is neutral, structure data is unavailable."
    """
    now = datetime.now(timezone.utc).isoformat()

    # Build disagreement map
    disagreement: dict[str, list[str]] = {}
    all_agents = set(list(agent_directions.keys())
                     + (list(agent_confidences.keys()) if agent_confidences else []))
    for agent in all_agents:
        directions = set()
        if agent in agent_directions:
            directions.add(agent_directions[agent])
        if agent in (agent_confidences or {}):
            directions.add(f"conf={agent_confidences[agent]:.2f}")
        disagreement[agent] = list(directions)

    # Build synthesis text
    long_count = sum(1 for d in agent_directions.values() if d == "LONG")
    short_count = sum(1 for d in agent_directions.values() if d == "SHORT")
    neutral_count = sum(1 for d in agent_directions.values() if d == "NEUTRAL")
    unavailable_count = len(unavailable_agents or [])

    parts = []
    if long_count > 0:
        parts.append(f"{long_count} agent(s) support LONG")
    if short_count > 0:
        parts.append(f"{short_count} agent(s) support SHORT")
    if neutral_count > 0:
        parts.append(f"{neutral_count} agent(s) are NEUTRAL")
    if unavailable_count > 0:
        parts.append(f"{unavailable_count} agent(s) unavailable")

    synthesis_text = "Evidence is mixed; " + "; ".join(parts) + "." if parts else "No agent signals."

    return HQSynthesis(
        synthesis_id=f"SYN-{hashlib.sha256(f'{now}{agent_directions}'.encode()).hexdigest()[:12].upper()}",
        market_context=market_context or {},
        supporting_evidence=supporting_agents or [],
        conflicting_evidence=conflicting_agents or [],
        historical_evidence=historical_evidence,
        validation_state=validation_state,
        uncertainty_flags=uncertainty_flags or [],
        critic_findings=critic_findings or [],
        research_memory_refs=research_memory_refs or [],
        relevant_claims=relevant_claims or [],
        agent_disagreement=disagreement,
        data_availability={},
        created_at=now,
    )