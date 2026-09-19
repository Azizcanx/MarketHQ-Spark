from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

ADAPTER_NAME = "research_memory_adapter_v1"

SCHEMA_VERSION = "research_storage_v1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DB_FILE = os.path.join(PROJECT_ROOT, "market_hq.db")


REQUIRED_TABLES = (
    "research_experiments",
    "research_results",
    "research_memory",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> str:
    return str(value)


def compact_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=json_default,
        )
    except Exception:
        return json.dumps(
            {"value": str(value)},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_stdin_json() -> Dict[str, Any]:
    raw = sys.stdin.read()

    if not raw or not raw.strip():
        raise ValueError("No JSON input received on stdin.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON input: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Input JSON root must be an object.")

    return payload


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def verify_required_tables(
    connection: sqlite3.Connection,
) -> None:
    missing = [
        table
        for table in REQUIRED_TABLES
        if not table_exists(connection, table)
    ]

    if missing:
        raise RuntimeError(
            "Required research storage tables are missing: "
            + ", ".join(missing)
        )


def get_experiment(
    connection: sqlite3.Connection,
    experiment_id: str,
) -> Optional[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            id,
            experiment_id,
            run_id,
            strategy_id,
            strategy_name,
            dataset_version_id,
            symbol,
            timeframe,
            scope_train_start,
            scope_train_end,
            scope_validation_start,
            scope_validation_end,
            scope_independent_start,
            scope_independent_end,
            research_question,
            hypothesis,
            rule_definition,
            parameters_json,
            cost_model_json,
            feedback_json,
            provenance_json,
            config_hash,
            status,
            created_at,
            updated_at
        FROM research_experiments
        WHERE experiment_id = ?
        LIMIT 1
        """,
        (experiment_id,),
    ).fetchone()


def get_result_by_result_id(
    connection: sqlite3.Connection,
    result_id: str,
) -> Optional[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            id,
            result_id,
            experiment_id,
            run_id,
            execution_status,
            validation_status,
            started_at,
            completed_at,
            duration_ms,
            metrics_json,
            validation_json,
            summary_json,
            provenance_json,
            result_hash,
            created_at
        FROM research_results
        WHERE result_id = ?
        LIMIT 1
        """,
        (result_id,),
    ).fetchone()


def get_latest_result_for_experiment(
    connection: sqlite3.Connection,
    experiment_row_id: int,
) -> Optional[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            id,
            result_id,
            experiment_id,
            run_id,
            execution_status,
            validation_status,
            started_at,
            completed_at,
            duration_ms,
            metrics_json,
            validation_json,
            summary_json,
            provenance_json,
            result_hash,
            created_at
        FROM research_results
        WHERE experiment_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (experiment_row_id,),
    ).fetchone()


def build_memory_key(
    experiment_id: str,
    result_row_id: Optional[int],
) -> str:
    if result_row_id is None:
        return f"experiment-learning:{experiment_id}:latest"

    return (
        f"experiment-learning:"
        f"{experiment_id}:"
        f"{result_row_id}"
    )


def normalize_confidence(
    value: Any,
) -> Optional[float]:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number < 0:
        number = 0.0

    if number > 1:
        number = 1.0

    return number


def normalize_status(
    value: Any,
) -> str:
    if value is None:
        return "ACTIVE"

    status = str(value).strip().upper()

    if not status:
        return "ACTIVE"

    return status[:100]


def normalize_memory_type(
    value: Any,
) -> str:
    if value is None:
        return "EXPERIMENT_LEARNING"

    memory_type = str(value).strip().upper()

    if not memory_type:
        return "EXPERIMENT_LEARNING"

    return memory_type[:100]


def normalize_title(
    value: Any,
) -> str:
    if value is None:
        return "MarketHQ Research Experiment Learning"

    title = str(value).strip()

    if not title:
        return "MarketHQ Research Experiment Learning"

    return title[:500]


def normalize_summary(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value)[:10000]


def normalize_decision(
    value: Any,
) -> Optional[str]:
    if value is None:
        return None

    decision = str(value).strip()

    if not decision:
        return None

    return decision[:200]


def extract_input(
    payload: Dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    value = payload.get(key)

    if value is not None:
        return value

    # Learning Agent V7 sends the complete Research Memory object
    # under payload["memory"]. Preserve root-level compatibility while
    # also supporting the nested memory contract.
    memory = payload.get("memory")

    if isinstance(memory, dict):
        nested_value = memory.get(key)

        if nested_value is not None:
            return nested_value

    return default


def build_evidence_payload(
    payload: Dict[str, Any],
    experiment_row: sqlite3.Row,
    result_row: Optional[sqlite3.Row],
) -> Dict[str, Any]:
    evidence = extract_input(
        payload,
        "evidence",
        {},
    )

    if not isinstance(evidence, dict):
        evidence = {
            "value": evidence,
        }

    result_evidence: Dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "experiment": {
            "experimentId": experiment_row["experiment_id"],
            "databaseId": experiment_row["id"],
            "strategyId": experiment_row["strategy_id"],
            "symbol": experiment_row["symbol"],
            "timeframe": experiment_row["timeframe"],
        },
    }

    if result_row is not None:
        result_evidence["result"] = {
            "resultId": result_row["result_id"],
            "databaseId": result_row["id"],
            "executionStatus": result_row["execution_status"],
            "validationStatus": result_row["validation_status"],
        }

    result_evidence["inputEvidence"] = evidence

    return result_evidence


def build_learning_payload(
    payload: Dict[str, Any],
    experiment_row: sqlite3.Row,
    result_row: Optional[sqlite3.Row],
) -> Dict[str, Any]:
    learning = extract_input(
        payload,
        "learning",
        {},
    )

    if not isinstance(learning, dict):
        learning = {
            "value": learning,
        }

    result_learning: Dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": experiment_row["experiment_id"],
        "experimentDatabaseId": experiment_row["id"],
    }

    if result_row is not None:
        result_learning["resultId"] = result_row["result_id"]
        result_learning["resultDatabaseId"] = result_row["id"]

    result_learning["inputLearning"] = learning

    return result_learning


def build_metadata_payload(
    payload: Dict[str, Any],
    experiment_row: sqlite3.Row,
    result_row: Optional[sqlite3.Row],
) -> Dict[str, Any]:
    metadata = extract_input(
        payload,
        "metadata",
        {},
    )

    if not isinstance(metadata, dict):
        metadata = {
            "value": metadata,
        }

    result_metadata: Dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "database": DB_FILE,
        "experimentDatabaseId": experiment_row["id"],
        "experimentId": experiment_row["experiment_id"],
    }

    if result_row is not None:
        result_metadata["resultDatabaseId"] = result_row["id"]
        result_metadata["resultId"] = result_row["result_id"]

    result_metadata["inputMetadata"] = metadata

    return result_metadata


def persist_memory(
    connection: sqlite3.Connection,
    *,
    experiment_row: sqlite3.Row,
    result_row: Optional[sqlite3.Row],
    memory_type: str,
    title: str,
    summary: str,
    decision: Optional[str],
    confidence: Optional[float],
    status: str,
    evidence: Dict[str, Any],
    learning: Dict[str, Any],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:

    experiment_db_id = int(experiment_row["id"])

    result_db_id: Optional[int] = None

    if result_row is not None:
        result_db_id = int(result_row["id"])

    memory_key = build_memory_key(
        experiment_row["experiment_id"],
        result_db_id,
    )

    now = utc_now()

    evidence_json = compact_json(evidence)
    learning_json = compact_json(learning)
    metadata_json = compact_json(metadata)

    content_for_hash = {
        "memoryKey": memory_key,
        "memoryType": memory_type,
        "title": title,
        "summary": summary,
        "decision": decision,
        "confidence": confidence,
        "status": status,
        "evidence": evidence,
        "learning": learning,
        "metadata": metadata,
    }

    memory_hash = sha256_text(
        compact_json(content_for_hash)
    )

    metadata_with_hash = dict(metadata)
    metadata_with_hash["memoryHash"] = memory_hash

    metadata_json = compact_json(
        metadata_with_hash
    )

    existing = connection.execute(
        """
        SELECT
            id
        FROM research_memory
        WHERE memory_key = ?
        LIMIT 1
        """,
        (memory_key,),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO research_memory (
                memory_key,
                experiment_id,
                result_id,
                memory_type,
                title,
                summary,
                decision,
                confidence,
                status,
                evidence_json,
                learning_json,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                memory_key,
                experiment_db_id,
                result_db_id,
                memory_type,
                title,
                summary,
                decision,
                confidence,
                status,
                evidence_json,
                learning_json,
                metadata_json,
                now,
                now,
            ),
        )

        memory_db_id = int(cursor.lastrowid)

        operation = "INSERTED"

    else:
        memory_db_id = int(existing["id"])

        connection.execute(
            """
            UPDATE research_memory
            SET
                experiment_id = ?,
                result_id = ?,
                memory_type = ?,
                title = ?,
                summary = ?,
                decision = ?,
                confidence = ?,
                status = ?,
                evidence_json = ?,
                learning_json = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                experiment_db_id,
                result_db_id,
                memory_type,
                title,
                summary,
                decision,
                confidence,
                status,
                evidence_json,
                learning_json,
                metadata_json,
                now,
                memory_db_id,
            ),
        )

        operation = "UPDATED"

    connection.commit()

    return {
        "memoryDatabaseId": memory_db_id,
        "memoryKey": memory_key,
        "operation": operation,
        "experimentDatabaseId": experiment_db_id,
        "experimentId": experiment_row["experiment_id"],
        "resultDatabaseId": result_db_id,
        "resultId": (
            result_row["result_id"]
            if result_row is not None
            else None
        ),
        "memoryHash": memory_hash,
    }


def main() -> None:
    safety = {
        "researchOnly": True,
        "liveExecutionEnabled": False,
        "brokerExecutionEnabled": False,
        "operationalDatabaseWriteEnabled": False,
        "researchStorageWritePerformed": False,
    }

    connection: Optional[sqlite3.Connection] = None

    try:
        payload = read_stdin_json()

        if not os.path.exists(DB_FILE):
            raise RuntimeError(
                f"Database not found: {DB_FILE}"
            )

        experiment_id_raw = extract_input(
            payload,
            "experimentId",
        )

        if experiment_id_raw is None:
            raise ValueError(
                "experimentId is required."
            )

        experiment_id = str(
            experiment_id_raw
        ).strip()

        if not experiment_id:
            raise ValueError(
                "experimentId cannot be empty."
            )

        result_id_raw = extract_input(
            payload,
            "resultId",
        )

        result_id: Optional[str] = None

        if result_id_raw is not None:
            result_id = str(
                result_id_raw
            ).strip()

            if not result_id:
                result_id = None

        memory_type = normalize_memory_type(
            extract_input(
                payload,
                "memoryType",
            )
        )

        title = normalize_title(
            extract_input(
                payload,
                "title",
            )
        )

        summary = normalize_summary(
            extract_input(
                payload,
                "summary",
            )
        )

        decision = normalize_decision(
            extract_input(
                payload,
                "decision",
            )
        )

        confidence = normalize_confidence(
            extract_input(
                payload,
                "confidence",
            )
        )

        status = normalize_status(
            extract_input(
                payload,
                "status",
            )
        )

        connection = sqlite3.connect(
            DB_FILE
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        verify_required_tables(
            connection
        )

        experiment_row = get_experiment(
            connection,
            experiment_id,
        )

        if experiment_row is None:
            raise RuntimeError(
                "Experiment not found. "
                f"experiment_id={experiment_id}"
            )

        experiment_db_id = int(
            experiment_row["id"]
        )

        result_row: Optional[sqlite3.Row] = None

        if result_id is not None:
            result_row = get_result_by_result_id(
                connection,
                result_id,
            )

            if result_row is None:
                raise RuntimeError(
                    "Result not found. "
                    f"result_id={result_id}"
                )

            result_experiment_db_id = int(
                result_row["experiment_id"]
            )

            if result_experiment_db_id != experiment_db_id:
                raise RuntimeError(
                    "Result does not belong to supplied experiment. "
                    f"result_id={result_id}, "
                    f"experiment_id={experiment_id}, "
                    f"database_experiment_id={result_experiment_db_id}, "
                    f"expected_database_experiment_id={experiment_db_id}"
                )

        else:
            result_row = get_latest_result_for_experiment(
                connection,
                experiment_db_id,
            )

        evidence = build_evidence_payload(
            payload,
            experiment_row,
            result_row,
        )

        learning = build_learning_payload(
            payload,
            experiment_row,
            result_row,
        )

        metadata = build_metadata_payload(
            payload,
            experiment_row,
            result_row,
        )

        persisted = persist_memory(
            connection,
            experiment_row=experiment_row,
            result_row=result_row,
            memory_type=memory_type,
            title=title,
            summary=summary,
            decision=decision,
            confidence=confidence,
            status=status,
            evidence=evidence,
            learning=learning,
            metadata=metadata,
        )

        safety["researchStorageWritePerformed"] = True

        response = {
            "success": True,
            "persisted": True,
            "operation": persisted["operation"],
            "adapter": ADAPTER_NAME,
            "schemaVersion": SCHEMA_VERSION,
            "database": DB_FILE,
            "memory": persisted,
            "safety": safety,
        }

        print(
            json.dumps(
                response,
                ensure_ascii=False,
                separators=(",", ":"),
                default=json_default,
            )
        )

    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        response = {
            "success": False,
            "persisted": False,
            "operation": "FAILED",
            "error": str(exc),
            "adapter": ADAPTER_NAME,
            "schemaVersion": SCHEMA_VERSION,
            "safety": safety,
        }

        print(
            json.dumps(
                response,
                ensure_ascii=False,
                separators=(",", ":"),
                default=json_default,
            )
        )

        sys.exit(1)

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()


