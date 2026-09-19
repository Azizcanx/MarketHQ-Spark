# -*- coding: utf-8 -*-
"""Brain Observation Bridge — AgentResult → Brain tables.

Maps AgentRun results to existing brain_observations/brain_claims tables.
Does NOT modify existing Brain engines — only adds observation records.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agent_contract import AgentResult, Claim, Evidence

DB_PATH = "/opt/markethq/market_hq.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: Any) -> str:
    """Normalize a value to string for DB storage."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bridge_result(run: Any) -> dict[str, Any]:
    """Bridge an AgentRun to Brain observation format.

    Creates observation records from AgentResult for the brain tables.
    Returns summary of what was bridged.
    """
    result = run.result
    if result is None:
        return {"status": "NO_RESULT", "observations": 0, "claims": 0}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    observations_created = 0
    claims_created = 0

    # ─── Create observation from AgentResult ───
    obs_key = f"agent_{result.agent_id}_{run.execution_id}"
    cursor.execute(
        """INSERT OR IGNORE INTO brain_observations
        (observation_key, method_name, symbol, timeframe, market_regime,
         confidence, status, first_observation_date, last_observation_date,
         observation_text, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            obs_key,
            result.source_engine,
            result.symbol,
            result.timeframe,
            result.regime,
            result.confidence,
            result.status.value,
            result.observation_timestamp,
            result.observation_timestamp,
            result.reasoning,
            json.dumps({
                "execution_id": run.execution_id,
                "agent_version": result.agent_version,
                "source_engine": result.source_engine,
                "source_engine_version": result.source_engine_version,
                "data_cutoff_timestamp": result.data_cutoff_timestamp,
                "direction": result.direction,
                "error_type": result.error_type,
                "error_message": result.error_message,
                "feature_availability": result.feature_availability,
                "data_quality": result.data_quality,
            }),
            utc_now(),
        ),
    )
    observations_created += 1

    # ─── Create evidence records from AgentResult evidence items ───
    for item in result.evidence.items:
        cursor.execute(
            """INSERT INTO brain_evidence
            (evidence_type, source_table, source_id, polarity, strength,
             observation_date, content_hash, note, metadata_json, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.type,
                result.source_engine,
                0,  # source_id — not applicable for agent observations
                "supports" if item.direction == result.direction else "neutral",
                item.strength,
                item.timestamp,
                "",  # content_hash — not computed for agent evidence
                item.explanation,
                json.dumps({
                    "feature": item.feature,
                    "value": item.value,
                    "data_cutoff_timestamp": item.data_cutoff_timestamp,
                }),
                utc_now(),
            ),
        )

    # ─── Create claims from AgentResult claims ───
    for claim in result.claims:
        claim_key = f"claim_{claim.claim_id}_{run.execution_id}"
        cursor.execute(
            """INSERT OR IGNORE INTO brain_claims
            (claim_key, subject_node_id, predicate, object_node_id,
             claim_text, claim_type, status, confidence, valid_from,
             valid_to, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                claim_key,
                0,  # subject_node_id — not yet linked
                claim.statement,
                0,  # object_node_id — not yet linked
                claim.statement,
                claim.feature or "general",
                claim.validation_status.value,
                claim.confidence,
                claim.observation_timestamp,
                "",  # valid_to — not set
                json.dumps({
                    "source_agent": claim.source_agent,
                    "source_agent_version": claim.source_agent_version,
                    "evidence_refs": claim.evidence_refs,
                    "regime": claim.regime,
                    "timeframe": claim.timeframe,
                    "symbol": claim.symbol,
                    "sample_size": claim.sample_size,
                }),
            ),
        )
        claims_created += 1

    # ─── Link observation to evidence ───
    cursor.execute(
        """INSERT OR IGNORE INTO brain_observation_evidence
        (observation_id, evidence_id)
        SELECT (SELECT id FROM brain_observations WHERE observation_key = ?), id
        FROM brain_evidence WHERE observation_date = ?""",
        (obs_key, result.observation_timestamp),
    )

    conn.commit()
    conn.close()

    return {
        "status": "BRIDGED",
        "observations": observations_created,
        "evidence_items": len(result.evidence.items),
        "claims": claims_created,
        "execution_id": run.execution_id,
    }


def bridge_all_runs(runs: list[Any]) -> dict[str, Any]:
    """Bridge multiple AgentRuns to Brain tables."""
    total_obs = 0
    total_claims = 0
    for run in runs:
        result = bridge_result(run)
        total_obs += result.get("observations", 0)
        total_claims += result.get("claims", 0)
    return {
        "status": "BRIDGED",
        "runs_processed": len(runs),
        "total_observations": total_obs,
        "total_claims": total_claims,
    }