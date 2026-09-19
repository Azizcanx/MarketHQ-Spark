# -*- coding: utf-8 -*-
"""Phase H — Research Intelligence Engine.

MarketHQ research intelligence: observe, hypothesize, experiment,
validate, learn, report — all offline, research-only, no auto promotion.

All claims are OBSERVATIONS, not truths.
All weight proposals require human approval.
No live trading. No broker. No lookahead.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_intelligence_model import (
    CalibrationProfile,
    Claim,
    ClaimStatus,
    Counterexample,
    Evidence,
    Experiment,
    ExperimentRegistry,
    ExperimentStatus,
    FeatureImportance,
    FailurePattern,
    Hypothesis,
    HypothesisStatus,
    Observation,
    ObservationType,
    ReliabilityProfile,
    ResearchMemory,
    Result,
    SimilarityMatch,
    WeightProposal,
    WeightProposalStatus,
)
from research_validation_model import HistoricalOutcome, ValidationMetrics
from research_validation_engine import (
    audit_lookahead,
    compute_validation_metrics,
    replay_setup,
    validate_setups,
    walk_forward_validation,
)
from opportunity_model import ResearchBackedSetup

random.seed(42)


# ── Observation Builder ────────────────────────────────────────────

def build_observation(
    text: str,
    observation_type: ObservationType = ObservationType.OBSERVATION,
    context: dict[str, Any] | None = None,
    regime: str = "UNKNOWN",
    asset: str = "",
    timeframe: str = "",
    sample_size: int = 0,
    source_agent: str = "",
    evidence_trace: list[str] | None = None,
) -> Observation:
    """Create a research observation."""
    now = datetime.now(timezone.utc).isoformat()
    return Observation(
        observation_id=f"OBS-{hashlib.sha256(f'{now}{text}'.encode()).hexdigest()[:12].upper()}",
        observation_type=observation_type,
        text=text,
        context=context or {},
        regime=regime,
        asset=asset,
        timeframe=timeframe,
        sample_size=sample_size,
        validation_windows=[],
        reliability=0.0,
        status=ClaimStatus.UNTESTED,
        source_agent=source_agent,
        evidence_trace=evidence_trace or [],
        created_at=now,
        updated_at=now,
    )


# ── Hypothesis Builder ─────────────────────────────────────────────

def build_hypothesis(
    text: str,
    observation_ids: list[str] | None = None,
    confidence: float = 0.0,
) -> Hypothesis:
    """Create a research hypothesis."""
    now = datetime.now(timezone.utc).isoformat()
    return Hypothesis(
        hypothesis_id=f"HYP-{hashlib.sha256(f'{now}{text}'.encode()).hexdigest()[:12].upper()}",
        text=text,
        observation_ids=observation_ids or [],
        status=HypothesisStatus.PROPOSED,
        confidence=confidence,
        experiment_ids=[],
        created_at=now,
        updated_at=now,
    )


# ── Experiment Registry ────────────────────────────────────────────

def register_experiment(
    hypothesis_id: str,
    description: str,
    config: dict[str, Any] | None = None,
    baseline: str = "",
) -> ExperimentRegistry:
    """Register a research experiment."""
    now = datetime.now(timezone.utc).isoformat()
    config_str = json.dumps(config or {}, sort_keys=True)
    exp_hash = hashlib.sha256(
        f"{hypothesis_id}{description}{config_str}{now}".encode()
    ).hexdigest()[:16]
    return ExperimentRegistry(
        experiment_id=f"EXP-{exp_hash.upper()}",
        hypothesis=hypothesis_id,
        dataset=description,
        config=config or {},
        status=ExperimentStatus.REGISTERED,
        experiment_hash=exp_hash,
        created_at=now,
        baseline=baseline,
    )


def run_experiment(
    experiment: ExperimentRegistry,
    outcomes: list[HistoricalOutcome],
) -> ExperimentRegistry:
    """Run an experiment against historical outcomes."""
    metrics = compute_validation_metrics(outcomes)
    experiment.status = ExperimentStatus.COMPLETED
    experiment.result = {
        "n_outcomes": len(outcomes),
        "avg_realized_r": metrics.avg_r,
        "median_realized_r": metrics.median_r,
        "t1_rate": metrics.t1_hit_rate,
        "invalidation_rate": metrics.invalidation_rate,
        "no_entry_rate": metrics.n_no_entry,
        "ambiguous_rate": metrics.n_ambiguous,
        "mfe": metrics.avg_mfe,
        "mae": metrics.avg_mae,
    }
    experiment.completed_at = datetime.now(timezone.utc).isoformat()
    return experiment


# ── Claim Validation ───────────────────────────────────────────────

def validate_claim(
    claim: Claim,
    outcomes: list[HistoricalOutcome],
) -> Claim:
    """Re-validate a claim against historical outcomes."""
    if len(outcomes) < 5:
        claim.status = ClaimStatus.UNTESTED
        claim.limitations.append("INSUFFICIENT_SAMPLE")
        return claim

    metrics = compute_validation_metrics(outcomes)
    claim.sample_size = len(outcomes)
    claim.last_validated = datetime.now(timezone.utc).isoformat()

    # Determine status based on evidence consistency
    # NOT win probability — evidence consistency
    supporting = 0
    contradicting = 0
    for o in outcomes:
        if o.outcome_type in ("TARGET_1_REACHED", "TARGET_2_REACHED", "TARGET_3_REACHED"):
            supporting += 1
        elif o.outcome_type == "INVALIDATED":
            contradicting += 1

    total = supporting + contradicting
    if total == 0:
        claim.status = ClaimStatus.UNTESTED
        return claim

    consistency = supporting / total
    claim.confidence = consistency

    # Status transitions
    if len(outcomes) >= 30 and consistency >= 0.7:
        claim.status = ClaimStatus.SUPPORTED
    elif len(outcomes) >= 15 and consistency >= 0.55:
        claim.status = ClaimStatus.TESTED
    elif len(outcomes) >= 10 and consistency < 0.4:
        claim.status = ClaimStatus.REJECTED
    else:
        claim.status = ClaimStatus.UNSTABLE

    return claim


# ── Claim Stability (Phase J5) ──────────────────────────────────

def compute_claim_stability(
    claim: Claim,
    contradiction_count: int = 0,
    time_window_days: float = 90.0,
    regime_count: int = 1,
    asset_count: int = 1,
    timeframe_count: int = 1,
) -> float:
    """Compute claim stability score (0-1).

    Factors: sample size, temporal stability, regime stability,
    asset stability, timeframe stability, contradiction rate, recency.
    """
    if claim.sample_size < 3:
        return 0.0

    # Sample size factor
    sample_factor = min(claim.sample_size / 50.0, 1.0)

    # Contradiction penalty
    total_evidence = claim.sample_size
    contradiction_rate = contradiction_count / max(total_evidence, 1)
    contradiction_penalty = contradiction_rate * 0.5

    # Stability factors
    regime_penalty = 0.0 if regime_count <= 2 else min((regime_count - 2) * 0.05, 0.2)
    asset_penalty = 0.0 if asset_count <= 2 else min((asset_count - 2) * 0.05, 0.2)
    tf_penalty = 0.0 if timeframe_count <= 2 else min((timeframe_count - 2) * 0.05, 0.2)

    # Recency bonus (newer claims are more stable)
    recency_bonus = 0.05

    stability = (
        0.4 * sample_factor
        + 0.2 * (1.0 - contradiction_penalty)
        + 0.1 * (1.0 - regime_penalty)
        + 0.1 * (1.0 - asset_penalty)
        + 0.1 * (1.0 - tf_penalty)
        + recency_bonus
    )

    return max(0.0, min(1.0, stability))


# ── Information Value (Phase J5) ────────────────────────────────

def compute_information_value(
    uncertainty_before: float,
    uncertainty_after: float,
    evidence_gap: float = 0.0,
    task_cost: float = 1.0,
) -> float:
    """Compute expected information value of a research task.

    Higher value = more worth researching.
    NOT profit prediction.
    """
    reduction = max(0.0, uncertainty_before - uncertainty_after)
    iv = reduction + (evidence_gap * 0.3)
    if task_cost > 0:
        iv = iv / (1.0 + 0.1 * task_cost)
    return max(0.0, iv)


# ── Research Memory (continued) ─────────────────────────────────

def store_observation(
    observation: Observation,
) -> ResearchMemory:
    """Store an observation as research memory."""
    now = datetime.now(timezone.utc).isoformat()
    return ResearchMemory(
        memory_id=f"MEM-{observation.observation_id}",
        memory_type=observation.observation_type,
        observation=observation.text,
        claim_id="",
        evidence=observation.evidence_trace,
        context=observation.context,
        regime=observation.regime,
        asset=observation.asset,
        timeframe=observation.timeframe,
        sample_size=observation.sample_size,
        validation_windows=observation.validation_windows,
        reliability=observation.reliability,
        status=observation.status,
        created_at=now,
        updated_at=now,
    )


# ── Failure Memory ─────────────────────────────────────────────────

def analyze_failures(
    outcomes: list[HistoricalOutcome],
) -> list[FailurePattern]:
    """Identify common failure patterns from historical outcomes."""
    patterns: list[FailurePattern] = []
    now = datetime.now(timezone.utc).isoformat()

    # Pattern 1: High quality + invalidated
    high_quality_invalidated = [
        o for o in outcomes
        if o.outcome_type == "INVALIDATED"
    ]
    if high_quality_invalidated:
        patterns.append(FailurePattern(
            pattern_id=f"FP-{hashlib.sha256(f'high_quality_invalidated{now}'.encode()).hexdigest()[:10].upper()}",
            description="High quality setups that were invalidated",
            conditions={"quality": "high", "outcome": "invalidated"},
            sample_size=len(high_quality_invalidated),
            outcome="INVALIDATED",
            recurrence=len(high_quality_invalidated) / len(outcomes) if outcomes else 0.0,
            regimes=[],
            strategies=[],
            confidence=0.5,
            evidence=["Phase G failure analysis"],
            created_at=now,
        ))

    # Pattern 2: High confidence + invalidated
    high_conf_invalidated = [
        o for o in outcomes
        if o.outcome_type == "INVALIDATED"
    ]
    if high_conf_invalidated:
        patterns.append(FailurePattern(
            pattern_id=f"FP-{hashlib.sha256(f'high_conf_invalidated{now}'.encode()).hexdigest()[:10].upper()}",
            description="High confidence setups that were invalidated",
            conditions={"confidence": "high", "outcome": "invalidated"},
            sample_size=len(high_conf_invalidated),
            outcome="INVALIDATED",
            recurrence=len(high_conf_invalidated) / len(outcomes) if outcomes else 0.0,
            regimes=[],
            strategies=[],
            confidence=0.5,
            evidence=["Phase G failure analysis"],
            created_at=now,
        ))

    # Pattern 3: No-entry setups
    no_entry = [o for o in outcomes if o.no_entry]
    if no_entry:
        patterns.append(FailurePattern(
            pattern_id=f"FP-{hashlib.sha256(f'no_entry{now}'.encode()).hexdigest()[:10].upper()}",
            description="Setups that never reached entry zone",
            conditions={"outcome": "no_entry"},
            sample_size=len(no_entry),
            outcome="NO_ENTRY",
            recurrence=len(no_entry) / len(outcomes) if outcomes else 0.0,
            regimes=[],
            strategies=[],
            confidence=0.5,
            evidence=["Phase G no-entry analysis"],
            created_at=now,
        ))

    return patterns


# ── Similarity Engine ──────────────────────────────────────────────

def find_similar_setups(
    setup: ResearchBackedSetup,
    historical_setups: list[ResearchBackedSetup],
    top_k: int = 5,
) -> list[SimilarityMatch]:
    """Find historically similar setups."""
    matches: list[SimilarityMatch] = []
    now = datetime.now(timezone.utc).isoformat()

    for hist in historical_setups:
        matched = []
        mismatched = []

        if setup.symbol == hist.symbol:
            matched.append("symbol")
        else:
            mismatched.append("symbol")

        if setup.timeframe == hist.timeframe:
            matched.append("timeframe")
        else:
            mismatched.append("timeframe")

        if setup.direction == hist.direction:
            matched.append("direction")
        else:
            mismatched.append("direction")

        if setup.regime == hist.regime:
            matched.append("regime")
        else:
            mismatched.append("regime")

        if setup.setup_type == hist.setup_type:
            matched.append("setup_type")
        else:
            mismatched.append("setup_type")

        score = len(matched) / (len(matched) + len(mismatched)) if (matched or mismatched) else 0.0

        if score > 0 or top_k > 0:
            matches.append(SimilarityMatch(
                similarity_id=f"SIM-{hashlib.sha256(f'{setup.setup_id}{hist.setup_id}'.encode()).hexdigest()[:10].upper()}",
                setup_id=hist.setup_id,
                matched_dimensions=matched,
                mismatched_dimensions=mismatched,
                similarity_score=score,
                historical_outcome="",
                realized_r=0.0,
                regime=hist.regime,
                window_id="",
            ))

    # Sort by similarity score descending
    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches[:top_k]


# ── Agent Reliability ──────────────────────────────────────────────

def compute_agent_reliability(
    agent_name: str,
    outcomes: list[HistoricalOutcome],
) -> ReliabilityProfile:
    """Compute historical reliability for an agent."""
    now = datetime.now(timezone.utc).isoformat()
    profile_id = f"REL-{hashlib.sha256(f'{agent_name}{now}'.encode()).hexdigest()[:10].upper()}"

    if not outcomes:
        return ReliabilityProfile(
            profile_id=profile_id,
            name=agent_name,
            profile_type="agent",
            sample_size=0,
            created_at=now,
        )

    target_hits = sum(1 for o in outcomes if o.outcome_type in (
        "TARGET_1_REACHED", "TARGET_2_REACHED", "TARGET_3_REACHED"
    ))
    invalidations = sum(1 for o in outcomes if o.outcome_type == "INVALIDATED")
    total = len(outcomes)

    return ReliabilityProfile(
        profile_id=profile_id,
        name=agent_name,
        profile_type="agent",
        direction_agreement=0.0,  # Would need agent direction data
        outcome_correlation=0.0,  # Would need agent confidence data
        target_hit_rate=target_hits / total if total else 0.0,
        invalidation_rate=invalidations / total if total else 0.0,
        avg_realized_r=sum(o.realized_r for o in outcomes) / total,
        median_realized_r=sorted([o.realized_r for o in outcomes])[total // 2] if total else 0.0,
        sample_size=total,
        stability_score=0.0,  # Would need temporal data
        temporal_stability=0.0,
        created_at=now,
    )


# ── Weight Proposal ────────────────────────────────────────────────

def create_weight_proposal(
    weight_name: str,
    current_value: float,
    proposed_value: float,
    reason: str,
    evidence: list[str] | None = None,
    windows: list[str] | None = None,
    previous_adaptive_comparison: dict[str, Any] | None = None,
) -> WeightProposal:
    """Create a research weight proposal — OFFLINE only, not active."""
    now = datetime.now(timezone.utc).isoformat()
    return WeightProposal(
        proposal_id=f"WP-{hashlib.sha256(f'{weight_name}{now}'.encode()).hexdigest()[:12].upper()}",
        weight_name=weight_name,
        current_value=current_value,
        proposed_value=proposed_value,
        reason=reason,
        evidence=evidence or [],
        walk_forward_windows=windows or [],
        baseline_comparison={},
        status=WeightProposalStatus.PROPOSED,
        previous_adaptive_v1_comparison=previous_adaptive_comparison or {},
        created_at=now,
    )


# ── Champion / Challenger ──────────────────────────────────────────

@dataclass
class ChampionChallenger:
    """Champion vs Challenger comparison for offline research."""
    champion_name: str
    challenger_name: str
    champion_metrics: dict[str, Any] = field(default_factory=dict)
    challenger_metrics: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] = field(default_factory=dict)
    winner: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion_name": self.champion_name,
            "challenger_name": self.challenger_name,
            "champion_metrics": self.champion_metrics,
            "challenger_metrics": self.challenger_metrics,
            "comparison": self.comparison,
            "winner": self.winner,
            "created_at": self.created_at,
        }


def compare_champion_challenger(
    champion_name: str,
    challenger_name: str,
    champion_outcomes: list[HistoricalOutcome],
    challenger_outcomes: list[HistoricalOutcome],
) -> ChampionChallenger:
    """Compare champion vs challenger on historical outcomes."""
    now = datetime.now(timezone.utc).isoformat()

    champion_metrics = compute_validation_metrics(champion_outcomes)
    challenger_metrics = compute_validation_metrics(challenger_outcomes)

    comparison = {
        "avg_r_diff": challenger_metrics.avg_r - champion_metrics.avg_r,
        "t1_rate_diff": challenger_metrics.t1_hit_rate - champion_metrics.t1_hit_rate,
        "invalidation_diff": challenger_metrics.invalidation_rate - champion_metrics.invalidation_rate,
        "mfe_diff": challenger_metrics.avg_mfe - champion_metrics.avg_mfe,
        "mae_diff": challenger_metrics.avg_mae - champion_metrics.avg_mae,
    }

    winner = ""
    if challenger_metrics.avg_r > champion_metrics.avg_r:
        winner = challenger_name
    elif challenger_metrics.avg_r < champion_metrics.avg_r:
        winner = champion_name
    else:
        winner = "TIE"

    return ChampionChallenger(
        champion_name=champion_name,
        challenger_name=challenger_name,
        champion_metrics=asdict(champion_metrics),
        challenger_metrics=asdict(challenger_metrics),
        comparison=comparison,
        winner=winner,
        created_at=now,
    )


# ── Calibration ────────────────────────────────────────────────────

def compute_calibration(
    confidence_buckets: dict[str, list[float]],
    outcome_rates: dict[str, float],
) -> CalibrationProfile:
    """Compute calibration profile for confidence buckets."""
    now = datetime.now(timezone.utc).isoformat()
    buckets = []
    for bucket, outcomes in confidence_buckets.items():
        rate = outcome_rates.get(bucket, 0.0)
        buckets.append({
            "bucket": bucket,
            "n": len(outcomes),
            "outcome_rate": rate,
            "confidence_center": float(bucket.split("-")[0]) if "-" in bucket else 0.0,
        })

    return CalibrationProfile(
        profile_id=f"CAL-{hashlib.sha256(f'{now}'.encode()).hexdigest()[:10].upper()}",
        name="confidence_calibration",
        bucket_type="confidence",
        buckets=buckets,
        calibration_score=0.0,
        sample_size=sum(len(v) for v in confidence_buckets.values()),
        created_at=now,
    )


# ── Feature Redundancy ─────────────────────────────────────────────

def detect_feature_redundancy(
    features: list[str],
    correlation_matrix: dict[str, dict[str, float]],
    threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Detect highly correlated feature pairs."""
    redundant: list[dict[str, Any]] = []
    checked = set()
    for i, f1 in enumerate(features):
        for j, f2 in enumerate(features):
            if i >= j:
                continue
            key = tuple(sorted([f1, f2]))
            if key in checked:
                continue
            checked.add(key)
            corr = correlation_matrix.get(f1, {}).get(f2, 0.0)
            if abs(corr) >= threshold:
                redundant.append({
                    "feature_1": f1,
                    "feature_2": f2,
                    "correlation": corr,
                    "redundancy_group": f"RG-{hashlib.sha256(f'{f1}{f2}'.encode()).hexdigest()[:8].upper()}",
                })
    return redundant


# ── Research Dashboard ─────────────────────────────────────────────

@dataclass
class ResearchDashboard:
    """Machine-readable research dashboard for frontend/Brain."""
    total_observations: int = 0
    total_claims: int = 0
    supported_claims: int = 0
    unstable_claims: int = 0
    rejected_claims: int = 0
    untested_claims: int = 0
    experiments: int = 0
    active_proposals: int = 0
    agent_reliability_profiles: int = 0
    strategy_profiles: int = 0
    regime_profiles: int = 0
    failure_patterns: int = 0
    counterexamples: int = 0
    data_quality_issues: int = 0
    research_memory_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_observations": self.total_observations,
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "unstable_claims": self.unstable_claims,
            "rejected_claims": self.rejected_claims,
            "untested_claims": self.untested_claims,
            "experiments": self.experiments,
            "active_proposals": self.active_proposals,
            "agent_reliability_profiles": self.agent_reliability_profiles,
            "strategy_profiles": self.strategy_profiles,
            "regime_profiles": self.regime_profiles,
            "failure_patterns": self.failure_patterns,
            "counterexamples": self.counterexamples,
            "data_quality_issues": self.data_quality_issues,
            "research_memory_size": self.research_memory_size,
        }