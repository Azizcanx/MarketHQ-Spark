
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name.lower() == "agents" else SCRIPT_DIR
DB_PATH = PROJECT_ROOT / "market_hq.db"
ARTIFACT_ROOT = PROJECT_ROOT / "research_artifacts"
SCHEMA_VERSION = "research_storage_v1"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def is_record(value: Any) -> bool:
    return isinstance(value, dict)

def first_record(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}

def text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return fallback

def nullable_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
            return int(number) if number.is_integer() else number
        except ValueError:
            return None
    return None

def first_value(root: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in root and root[key] is not None:
            return root[key]
    return default

def nested_record(root: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = root.get(key)
        if isinstance(value, dict):
            return value
    return {}

def ensure_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): ensure_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [ensure_jsonable(v) for v in value]
    return str(value)

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None

def required_tables() -> list[str]:
    return [
        "market_datasets",
        "market_dataset_versions",
        "research_experiments",
        "research_results",
        "research_artifacts",
        "research_memory",
        "research_dataset_usage",
    ]

def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(f"market_hq.db bulunamadı: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    missing = [t for t in required_tables() if not table_exists(conn, t)]
    if missing:
        raise RuntimeError(
            "Research Storage schema eksik. Önce research_storage_schema_v1.py "
            f"çalıştırılmalı. Eksik tablolar: {', '.join(missing)}"
        )
    return conn

def extract_date_scope(experiment: dict[str, Any]) -> dict[str, Any]:
    scope = first_record(experiment.get("dateScope"), experiment.get("date_scope"))
    return {
        "train_start": first_value(scope, "trainStartDate", "train_start", "trainStart"),
        "train_end": first_value(scope, "trainEndDate", "train_end", "trainEnd"),
        "validation_start": first_value(scope, "validationStartDate", "validation_start", "validationStart"),
        "validation_end": first_value(scope, "validationEndDate", "validation_end", "validationEnd"),
        "independent_start": first_value(
            scope, "independentSliceStartDate", "independent_start",
            "independentStartDate", "independentStart",
        ),
        "independent_end": first_value(
            scope, "independentSliceEndDate", "independent_end",
            "independentEndDate", "independentEnd",
        ),
        "selection_status": text(scope.get("selectionStatus"), "UNKNOWN"),
        "selection_source": text(scope.get("selectionSource")),
    }

def extract_execution_result(runner: dict[str, Any]) -> dict[str, Any]:
    execution = runner.get("researchExecution")
    if not isinstance(execution, dict):
        return {}
    result = execution.get("result")
    return result if isinstance(result, dict) else {}

def extract_metrics(normalized_result: dict[str, Any]) -> dict[str, Any]:
    value = normalized_result.get("normalizedMetrics")
    return value if isinstance(value, dict) else {}

def compact_validation(normalized_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": normalized_result.get("status"),
        "quality": ensure_jsonable(normalized_result.get("quality", {})),
        "conclusion": ensure_jsonable(normalized_result.get("conclusion", {})),
        "nextResearchInput": ensure_jsonable(normalized_result.get("nextResearchInput", {})),
    }

def extract_provider(experiment: dict[str, Any], execution: dict[str, Any]) -> str:
    for root in (
        execution,
        nested_record(execution, "dataProvenance", "data_provenance"),
        nested_record(experiment, "dataRequirements"),
    ):
        provider = text(root.get("provider"))
        if provider:
            return provider
    return "research_execution_adapter_v1"

def extract_row_count(execution: dict[str, Any]) -> int:
    candidates = [
        execution.get("rowCount"),
        execution.get("row_count"),
        execution.get("bars"),
        execution.get("barCount"),
        nested_record(execution, "dataProvenance").get("rowCount"),
        nested_record(execution, "dataProvenance").get("row_count"),
        nested_record(execution, "data").get("rowCount"),
    ]
    for value in candidates:
        number = nullable_number(value)
        if number is not None and number >= 0:
            return int(number)
    return 0

def source_hash(experiment: dict[str, Any], execution: dict[str, Any], descriptor: dict[str, Any]) -> tuple[str, str]:
    provenance = first_record(
        execution.get("dataProvenance"),
        execution.get("data_provenance"),
        experiment.get("provenance"),
    )
    for key in ("contentHash", "content_hash", "datasetHash", "dataset_hash"):
        value = text(provenance.get(key))
        if value:
            return value, "source_content_hash"
    return sha256_json(descriptor), "dataset_scope_fingerprint"

def make_artifact(experiment_id: str, result_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    directory = ARTIFACT_ROOT / experiment_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result_id}.json"
    raw = canonical_json(ensure_jsonable(payload)).encode("utf-8")
    path.write_bytes(raw)
    return {
        "artifact_id": f"artifact-{result_id}-full-result",
        "artifact_type": "FULL_RESEARCH_RESULT",
        "artifact_path": str(path),
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "row_count": None,
        "metadata": {"format": "json", "research_only": True, "contains_large_payloads": True},
    }

def persist(payload: dict[str, Any]) -> dict[str, Any]:
    experiment = first_record(payload.get("experiment"), payload.get("runnerExperiment"))
    normalized = first_record(payload.get("normalizedResult"), payload.get("result"))
    runner = first_record(payload.get("runner"))
    validation = first_record(payload.get("validation"))
    evidence = first_record(payload.get("evidence"))

    experiment_id = text(experiment.get("experimentId"))
    run_id = text(payload.get("runId"))
    strategy = first_record(experiment.get("strategy"))
    market = first_record(experiment.get("market"))
    scope = extract_date_scope(experiment)

    if not experiment_id:
        raise RuntimeError("Research Storage: experimentId eksik.")
    if scope["selection_status"].upper() != "RESOLVED":
        raise RuntimeError("Research Storage: dateScope RESOLVED değil.")
    independent_start = text(scope["independent_start"])
    independent_end = text(scope["independent_end"])
    if not independent_start or not independent_end:
        raise RuntimeError("Research Storage: independent date scope eksik.")

    strategy_id = text(strategy.get("strategyId"), "UNKNOWN_STRATEGY")
    strategy_name = text(strategy.get("name"), strategy_id)
    symbol = text(market.get("symbol"), "UNKNOWN")
    timeframe = text(market.get("timeframe"), "1d")

    execution = extract_execution_result(runner)
    provider = extract_provider(experiment, execution)
    row_count = extract_row_count(execution)

    dataset_key = f"{symbol}:{timeframe}:{provider}"
    descriptor = {
        "dataset_key": dataset_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "provider": provider,
        "independent_start": independent_start,
        "independent_end": independent_end,
        "row_count": row_count,
        "selection_source": scope["selection_source"],
    }
    dataset_hash, hash_type = source_hash(experiment, execution, descriptor)
    version_key = f"{dataset_key}:{dataset_hash[:16]}"

    config_payload = {
        "experiment_id": experiment_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "date_scope": scope,
        "research_question": experiment.get("researchQuestion"),
        "hypothesis": experiment.get("hypothesis"),
        "rule_definition": strategy.get("ruleDefinition"),
        "parameters": strategy.get("parameters", {}),
        "evaluation": experiment.get("evaluation", {}),
        "constraints": experiment.get("constraints", {}),
        "source": experiment.get("source", {}),
    }
    config_hash = sha256_json(config_payload)
    result_id = f"result-{experiment_id}-{run_id or 'unknown'}"
    result_payload = {
        "normalizedResult": normalized,
        "runner": runner,
        "validation": validation,
        "evidence": evidence,
        "persistedAt": utc_now(),
    }
    result_hash = sha256_json(result_payload)
    now = utc_now()
    conn = connect()

    try:
        with conn:
            row = conn.execute(
                "SELECT id FROM market_datasets WHERE dataset_key=? LIMIT 1",
                (dataset_key,),
            ).fetchone()
            if row:
                dataset_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE market_datasets
                    SET symbol=?, market=COALESCE(market, ?), timeframe=?,
                        provider=?, last_available_at=?, row_count=?, updated_at=?
                    WHERE id=?
                    """,
                    (symbol, "BIST", timeframe, provider, independent_end, row_count, now, dataset_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO market_datasets (
                        dataset_key, symbol, market, timeframe, provider, source_uri,
                        status, first_available_at, last_available_at, row_count,
                        metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_key, symbol, "BIST", timeframe, provider, None,
                        independent_start, independent_end, row_count,
                        canonical_json({"research_only": True, "created_by": "research_storage_adapter_v1"}),
                        now, now,
                    ),
                )
                dataset_id = int(cursor.lastrowid)

            row = conn.execute(
                "SELECT id FROM market_dataset_versions WHERE version_key=? LIMIT 1",
                (version_key,),
            ).fetchone()
            if row:
                dataset_version_id = int(row["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO market_dataset_versions (
                        dataset_id, version_key, content_hash, schema_version,
                        first_available_at, last_available_at, row_count, provider,
                        retrieval_params_json, artifact_path, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id, version_key, dataset_hash, SCHEMA_VERSION,
                        independent_start, independent_end, row_count, provider,
                        canonical_json({
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "selection_source": scope["selection_source"],
                            "selection_status": scope["selection_status"],
                        }),
                        None,
                        canonical_json({
                            "hash_type": hash_type,
                            "research_only": True,
                        }),
                        now,
                    ),
                )
                dataset_version_id = int(cursor.lastrowid)

            conn.execute(
                "UPDATE market_datasets SET current_version_id=?, updated_at=? WHERE id=?",
                (dataset_version_id, now, dataset_id),
            )

            experiment_status = "COMPLETED" if text(
                nested_record(runner, "researchExecution").get("status")
            ).upper() == "COMPLETED" else "INGESTED"

            experiment_values = (
                run_id or None,
                strategy_id,
                strategy_name,
                dataset_version_id,
                symbol,
                timeframe,
                scope["train_start"],
                scope["train_end"],
                scope["validation_start"],
                scope["validation_end"],
                independent_start,
                independent_end,
                text(experiment.get("researchQuestion")) or None,
                text(experiment.get("hypothesis")) or None,
                text(strategy.get("ruleDefinition")) or None,
                canonical_json(strategy.get("parameters", {})),
                canonical_json(first_record(experiment.get("costModel"), experiment.get("evaluation"))),
                canonical_json(experiment.get("source", {})),
                canonical_json({
                    "runId": run_id,
                    "dateScope": scope,
                    "researchOnly": True,
                }),
                config_hash,
                experiment_status,
                now,
                now,
            )

            row = conn.execute(
                "SELECT id FROM research_experiments WHERE experiment_id=? LIMIT 1",
                (experiment_id,),
            ).fetchone()
            if row:
                research_experiment_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE research_experiments
                    SET run_id=?, strategy_id=?, strategy_name=?, dataset_version_id=?,
                        symbol=?, timeframe=?, scope_train_start=?, scope_train_end=?,
                        scope_validation_start=?, scope_validation_end=?,
                        scope_independent_start=?, scope_independent_end=?,
                        research_question=?, hypothesis=?, rule_definition=?,
                        parameters_json=?, cost_model_json=?, feedback_json=?,
                        provenance_json=?, config_hash=?, status=?, updated_at=?
                    WHERE id=?
                    """,
                    (*experiment_values, research_experiment_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO research_experiments (
                        experiment_id, run_id, strategy_id, strategy_name, dataset_version_id,
                        symbol, timeframe, scope_train_start, scope_train_end,
                        scope_validation_start, scope_validation_end,
                        scope_independent_start, scope_independent_end,
                        research_question, hypothesis, rule_definition,
                        parameters_json, cost_model_json, feedback_json, provenance_json,
                        config_hash, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (experiment_id, *experiment_values),
                )
                research_experiment_id = int(cursor.lastrowid)

            conn.execute(
                """
                INSERT OR IGNORE INTO research_dataset_usage (
                    dataset_version_id, experiment_id, usage_role, created_at
                )
                VALUES (?, ?, 'research_input', ?)
                """,
                (dataset_version_id, research_experiment_id, now),
            )

            execution_status = text(
                nested_record(runner, "researchExecution").get("status"),
                "UNKNOWN",
            ).upper()
            normalized_status = text(normalized.get("status")) or None
            duration_ms = nullable_number(runner.get("durationMs"))
            metrics = extract_metrics(normalized)
            validation_json = compact_validation(normalized)

            result_values = (
                research_experiment_id,
                run_id or None,
                execution_status,
                normalized_status,
                text(runner.get("startedAt")) or None,
                now if execution_status == "COMPLETED" else None,
                duration_ms,
                canonical_json(metrics),
                canonical_json(validation_json),
                canonical_json(normalized.get("conclusion", {})),
                canonical_json(normalized.get("provenance", {})),
                result_hash,
                now,
            )

            row = conn.execute(
                "SELECT id FROM research_results WHERE result_id=? LIMIT 1",
                (result_id,),
            ).fetchone()
            if row:
                research_result_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE research_results
                    SET experiment_id=?, run_id=?, execution_status=?, validation_status=?,
                        started_at=?, completed_at=?, duration_ms=?, metrics_json=?,
                        validation_json=?, summary_json=?, provenance_json=?, result_hash=?
                    WHERE id=?
                    """,
                    (*result_values[:-1], research_result_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO research_results (
                        result_id, experiment_id, run_id, execution_status, validation_status,
                        started_at, completed_at, duration_ms, metrics_json, validation_json,
                        summary_json, provenance_json, result_hash, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (result_id, *result_values),
                )
                research_result_id = int(cursor.lastrowid)

            artifact = make_artifact(experiment_id, result_id, result_payload)
            conn.execute(
                """
                INSERT OR REPLACE INTO research_artifacts (
                    artifact_id, result_id, artifact_type, artifact_path, content_hash,
                    byte_size, row_count, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact["artifact_id"], research_result_id,
                    artifact["artifact_type"], artifact["artifact_path"],
                    artifact["content_hash"], artifact["byte_size"],
                    artifact["row_count"], canonical_json(artifact["metadata"]), now,
                ),
            )

        return {
            "enabled": True,
            "persisted": True,
            "schemaVersion": SCHEMA_VERSION,
            "dataset": {
                "id": dataset_id,
                "datasetKey": dataset_key,
                "versionId": dataset_version_id,
                "versionKey": version_key,
                "contentHash": dataset_hash,
                "hashType": hash_type,
            },
            "experiment": {
                "id": research_experiment_id,
                "experimentId": experiment_id,
                "configHash": config_hash,
            },
            "result": {
                "id": research_result_id,
                "resultId": result_id,
                "resultHash": result_hash,
            },
            "artifact": artifact,
            "safety": {
                "researchOnly": True,
                "liveExecutionEnabled": False,
                "brokerExecutionEnabled": False,
                "operationalDatabaseWriteEnabled": False,
                "researchStorageWritePerformed": True,
            },
        }
    finally:
        conn.close()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        conn = connect()
        try:
            print(json.dumps({
                "success": True,
                "schemaVersion": SCHEMA_VERSION,
                "database": str(DB_PATH),
                "tables": required_tables(),
            }, ensure_ascii=False))
        finally:
            conn.close()
        return

    raw = os.sys.stdin.read()
    if not raw.strip():
        raise SystemExit("Research Storage adapter stdin boş.")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("Research Storage adapter payload object olmalı.")
    print(json.dumps({"success": True, "storage": persist(payload)}, ensure_ascii=False))

if __name__ == "__main__":
    main()

