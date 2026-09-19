# -*- coding: utf-8 -*-
"""
MarketHQ Schema Freeze V1.1
===========================

Amaç
-----
MarketHQ'nun Research -> Evidence -> Learning/Ranking katmanlarını
Dashboard Backend'e bağlamadan önce veri sözleşmesini (schema contract)
tek bir snapshot olarak dondurmak.

V1.1 DÜZELTME
-------------
Önceki V1, iki JSON sözleşmesini yanlış biçimde root-level key kontrolüyle
doğruluyordu:

    - V6 master JSON, strategy kaydını iç içe taşır.
    - Final Research Decision JSON, decision bilgisini obje içinde taşır.

Bu sürüm:
    - V6 için gerçek strategy record + ranking alanlarını recursively bulur.
    - Final Decision için gerçek payload içindeki decision objesini doğrular.
    - Önceki BLOCKED freeze kayıtlarını baseline kabul etmez.
    - Yalnızca başarılı FREEZE_READY snapshot'larını baseline olarak kullanır.

Bu motor:
    - mevcut SQLite tablolarını ve kolonlarını okur,
    - gerekli tabloların bulunup bulunmadığını doğrular,
    - kritik JSON çıktı sözleşmelerini gerçek yapıları üzerinden kontrol eder,
    - deterministic contract hash üretir,
    - başarılı freeze snapshot'ı JSON + SQLite audit tablosuna kaydeder.

ÖNEMLİ
-------
- Broker / order / execution yapmaz.
- learned_rules, claims, validations, observations içeriklerini değiştirmez.
- Knowledge verification state değiştirmez.
- Yeni learning rule üretmez.
- Freeze yalnızca şema / interface sözleşmesidir.
- Schema drift varsa BLOCKED verir.
- İlk başarılı çalıştırma baseline oluşturur.
- Daha sonraki başarılı çalıştırmalar baseline ile karşılaştırılır.

Çalıştırma:
    .venv\\Scripts\\python.exe .\\schema_freeze_v1.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"

PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
CONSOLIDATION_DIR = PROJECT_ROOT / "evidence_consolidation_results"
LEARNING_RANKING_DIR = PROJECT_ROOT / "learning_ranking_results"
FINAL_DECISION_DIR = PROJECT_ROOT / "final_research_decisions"

OUTPUT_DIR = PROJECT_ROOT / "schema_freeze_results"

ENGINE_NAME = "MARKETHQ_SCHEMA_FREEZE"
ENGINE_VERSION = "V1.1"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

TARGET_STRATEGY_ID = "STR-43839FA9C6"


# Critical operational tables that form the current data contract.
CORE_TABLES = [
    "knowledge_sources",
    "knowledge_items",
    "learning_experiments",
    "experiment_results",
    "learned_rules",
    "brain_nodes",
    "brain_edges",
    "brain_episodes",
    "brain_evidence",
    "brain_node_evidence",
    "brain_edge_evidence",
    "brain_claims",
    "brain_claim_evidence",
    "brain_learning_events",
    "brain_contradictions",
    "brain_research_queue",
    "brain_research_evidence_reviews",
    "brain_research_strategy_evidence_reviews",
    "brain_evidence_consolidations",
    "brain_strategy_learning_rankings",
]


# Exact minimum column contracts required by the current engines.
COLUMN_CONTRACTS: dict[str, list[str]] = {
    "knowledge_sources": [
        "id",
    ],
    "knowledge_items": [
        "id",
        "title",
        "item_type",
        "metadata_json",
    ],
    "learning_experiments": [
        "id",
    ],
    "experiment_results": [
        "id",
    ],
    "learned_rules": [
        "id",
    ],
    "brain_nodes": [
        "id",
        "node_type",
        "status",
    ],
    "brain_edges": [
        "id",
        "source_node_id",
        "target_node_id",
        "relation",
    ],
    "brain_episodes": [
        "id",
    ],
    "brain_evidence": [
        "id",
    ],
    "brain_node_evidence": [
        "node_id",
        "evidence_id",
    ],
    "brain_edge_evidence": [
        "edge_id",
        "evidence_id",
    ],
    "brain_claims": [
        "id",
        "claim_type",
        "status",
    ],
    "brain_claim_evidence": [
        "claim_id",
        "evidence_id",
    ],
    "brain_learning_events": [
        "id",
        "event_type",
        "score",
        "decision",
        "created_at",
        "metadata_json",
    ],
    "brain_contradictions": [
        "id",
    ],
    "brain_research_queue": [
        "id",
        "question",
        "priority",
        "status",
        "created_at",
        "updated_at",
        "metadata_json",
    ],
    "brain_research_evidence_reviews": [
        "id",
        "knowledge_item_id",
        "observation_id",
        "verdict",
        "score",
    ],
    "brain_research_strategy_evidence_reviews": [
        "id",
        "knowledge_item_id",
        "verdict",
        "score",
    ],
    "brain_evidence_consolidations": [
        "id",
        "strategy_id",
        "pooled_positive_ratio",
        "strategy_review_score",
        "verified",
        "consolidation_json",
        "created_at",
    ],
    "brain_strategy_learning_rankings": [
        "id",
        "strategy_id",
        "learning_score",
        "action",
        "input_fingerprint",
        "ranking_json",
        "created_at",
    ],
}


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass

    return default


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def latest_json(
    directory: Path,
    patterns: list[str],
) -> Path | None:
    if not directory.exists():
        return None

    candidates: list[Path] = []

    for pattern in patterns:
        candidates.extend(
            path
            for path in directory.glob(pattern)
            if path.is_file()
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return candidates[0]


def load_json_file(
    path: Path | None,
) -> Any:
    if path is None or not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> list[str]:
    if not table_exists(
        conn,
        table_name,
    ):
        return []

    rows = conn.execute(
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()

    return [
        norm(row["name"])
        for row in rows
    ]


def table_count(
    conn: sqlite3.Connection,
    table_name: str,
) -> int:
    if not table_exists(
        conn,
        table_name,
    ):
        return 0

    row = conn.execute(
        f'SELECT COUNT(*) AS n FROM "{table_name}"'
    ).fetchone()

    return int(
        row["n"] or 0
    )


def table_fingerprint_payload(
    tables: dict[str, Any],
) -> dict[str, Any]:
    return {
        name: {
            "exists": item["exists"],
            "columns": item["columns"],
            "required_columns": item[
                "required_columns"
            ],
        }
        for name, item in sorted(
            tables.items()
        )
    }


def recursive_find_strategy_record(
    payload: Any,
    strategy_id: str,
) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    seen: set[int] = set()

    def walk(value: Any) -> None:
        nonlocal found

        if found is not None:
            return

        if isinstance(value, dict):
            identity = id(value)

            if identity in seen:
                return

            seen.add(identity)

            row_id = norm(
                value.get("strategy_id")
                or value.get("id")
            )

            if (
                row_id.upper() == strategy_id.upper()
                and isinstance(
                    value.get("ranking"),
                    dict,
                )
            ):
                found = value
                return

            for child in value.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

                if found is not None:
                    return

        elif isinstance(value, list):
            for child in value:
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

                if found is not None:
                    return

    walk(payload)
    return found


def recursive_find_decision_object(
    payload: Any,
) -> dict[str, Any] | None:
    """
    Current Final Research Decision V3 writes:

        "decision": {
            "decision": "...",
            "action": "...",
            "composite_score": ...,
            "decision_confidence": ...
        }

    Older V1/V2 records can also have a similar nested structure.
    """
    if not isinstance(
        payload,
        dict,
    ):
        return None

    decision = payload.get(
        "decision"
    )

    if isinstance(
        decision,
        dict,
    ):
        return decision

    # Legacy/defensive recursive search.
    found: dict[str, Any] | None = None

    def walk(value: Any) -> None:
        nonlocal found

        if found is not None:
            return

        if isinstance(value, dict):
            candidate = value.get(
                "decision"
            )

            if isinstance(
                candidate,
                dict,
            ) and (
                "action" in candidate
                or "composite_score" in candidate
                or "decision_confidence" in candidate
            ):
                found = candidate
                return

            for child in value.values():
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

                if found is not None:
                    return

        elif isinstance(value, list):
            for child in value:
                if isinstance(
                    child,
                    (dict, list),
                ):
                    walk(child)

                if found is not None:
                    return

    walk(payload)
    return found


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA busy_timeout = 60000"
    )
    conn.execute(
        "PRAGMA foreign_keys = ON"
    )
    return conn


# ============================================================================
# SAFETY
# ============================================================================

def assert_research_only() -> None:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False"
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True"
        )


def safety_contract() -> dict[str, Any]:
    return {
        "research_only": True,
        "execution_enabled": False,
        "broker_execution": False,
        "live_orders": False,
        "learned_rules_changed": False,
        "claims_changed": False,
        "validations_changed": False,
        "observations_changed": False,
        "knowledge_verified_changed": False,
        "purpose": (
            "schema_and_interface_freeze_only"
        ),
    }


# ============================================================================
# TABLE AUDIT
# ============================================================================

def audit_tables(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for table_name in CORE_TABLES:
        exists = table_exists(
            conn,
            table_name,
        )

        columns = (
            table_columns(
                conn,
                table_name,
            )
            if exists
            else []
        )

        required = COLUMN_CONTRACTS.get(
            table_name,
            [],
        )

        missing = [
            column
            for column in required
            if column not in columns
        ]

        result[table_name] = {
            "exists": exists,
            "column_count": len(columns),
            "columns": columns,
            "required_columns": required,
            "missing_required_columns": missing,
            "row_count": (
                table_count(
                    conn,
                    table_name,
                )
                if exists
                else 0
            ),
            "contract_status": (
                "OK"
                if exists and not missing
                else (
                    "MISSING_TABLE"
                    if not exists
                    else "MISSING_COLUMNS"
                )
            ),
        }

    return result


# ============================================================================
# JSON AUDIT - V6
# ============================================================================

def audit_v6_pipeline() -> dict[str, Any]:
    path = latest_json(
        PIPELINE_DIR,
        [
            "strategy_pipeline_v6_*.json",
        ],
    )

    if path is None:
        return {
            "available": False,
            "status": "MISSING_FILE",
            "file": None,
        }

    payload = load_json_file(
        path
    )

    if not isinstance(
        payload,
        (dict, list),
    ):
        return {
            "available": False,
            "status": "INVALID_JSON_ROOT",
            "file": str(path),
        }

    strategy = recursive_find_strategy_record(
        payload,
        TARGET_STRATEGY_ID,
    )

    if strategy is None:
        return {
            "available": False,
            "status": "STRATEGY_RECORD_NOT_FOUND",
            "file": str(path),
            "strategy_id": TARGET_STRATEGY_ID,
        }

    ranking = strategy.get(
        "ranking"
    )

    if not isinstance(
        ranking,
        dict,
    ):
        return {
            "available": False,
            "status": "RANKING_OBJECT_MISSING",
            "file": str(path),
            "strategy_id": TARGET_STRATEGY_ID,
        }

    required_ranking = [
        "score",
        "classification",
        "cross_symbol_positive_ratio",
        "average_return",
        "cost_survival",
        "parameter_stability",
        "regime_stability",
        "wfo_positive_ratio",
    ]

    missing_ranking = [
        key
        for key in required_ranking
        if key not in ranking
    ]

    status = (
        "OK"
        if not missing_ranking
        else "MISSING_RANKING_KEYS"
    )

    return {
        "available": True,
        "status": status,
        "file": str(path),
        "strategy_id": norm(
            strategy.get("strategy_id")
            or strategy.get("id")
        ),
        "strategy_name": norm(
            strategy.get("strategy_name")
            or strategy.get("name")
            or strategy.get("title")
        ),
        "strategy_record_found": True,
        "ranking_keys_found": sorted(
            ranking.keys()
        ),
        "required_ranking_keys": required_ranking,
        "missing_ranking_keys": missing_ranking,
    }


# ============================================================================
# JSON AUDIT - CONSOLIDATION
# ============================================================================

def audit_consolidation() -> dict[str, Any]:
    path = latest_json(
        CONSOLIDATION_DIR,
        [
            f"evidence_consolidation_{TARGET_STRATEGY_ID}_*.json"
        ],
    )

    if path is None:
        return {
            "available": False,
            "status": "MISSING_FILE",
            "file": None,
        }

    payload = load_json_file(
        path
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "available": False,
            "status": "INVALID_JSON_ROOT",
            "file": str(path),
        }

    required_top = [
        "strategy_id",
        "consolidated_independent",
        "interpretation",
        "next_research_question",
    ]

    missing_top = [
        key
        for key in required_top
        if key not in payload
    ]

    independent = payload.get(
        "consolidated_independent"
    )

    interpretation = payload.get(
        "interpretation"
    )

    missing_nested: dict[str, list[str]] = {}

    if not isinstance(
        independent,
        dict,
    ):
        missing_nested[
            "consolidated_independent"
        ] = [
            "evidence_records",
            "symbols_across_records",
            "positive_full_runs",
            "negative_full_runs",
            "pooled_positive_ratio",
        ]
    else:
        keys = [
            "evidence_records",
            "symbols_across_records",
            "positive_full_runs",
            "negative_full_runs",
            "pooled_positive_ratio",
        ]

        missing = [
            key
            for key in keys
            if key not in independent
        ]

        if missing:
            missing_nested[
                "consolidated_independent"
            ] = missing

    if not isinstance(
        interpretation,
        dict,
    ):
        missing_nested[
            "interpretation"
        ] = [
            "independent_cross_time_consistency",
            "strategy_review_verdict",
            "strategy_review_score",
            "verified_status",
        ]
    else:
        keys = [
            "independent_cross_time_consistency",
            "strategy_review_verdict",
            "strategy_review_score",
            "verified_status",
        ]

        missing = [
            key
            for key in keys
            if key not in interpretation
        ]

        if missing:
            missing_nested[
                "interpretation"
            ] = missing

    status = (
        "OK"
        if (
            not missing_top
            and not missing_nested
        )
        else "MISSING_KEYS"
    )

    return {
        "available": True,
        "status": status,
        "file": str(path),
        "missing_top_keys": missing_top,
        "nested_missing_keys": missing_nested,
    }


# ============================================================================
# JSON AUDIT - LEARNING / RANKING
# ============================================================================

def audit_learning_ranking() -> dict[str, Any]:
    path = latest_json(
        LEARNING_RANKING_DIR,
        [
            f"learning_ranking_{TARGET_STRATEGY_ID}_*.json"
        ],
    )

    if path is None:
        return {
            "available": False,
            "status": "MISSING_FILE",
            "file": None,
        }

    payload = load_json_file(
        path
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "available": False,
            "status": "INVALID_JSON_ROOT",
            "file": str(path),
        }

    required_top = [
        "strategy_id",
        "research_only",
        "execution_enabled",
        "ranking",
        "evidence_context",
        "research_guidance",
        "safety",
    ]

    missing_top = [
        key
        for key in required_top
        if key not in payload
    ]

    ranking = payload.get(
        "ranking"
    )
    guidance = payload.get(
        "research_guidance"
    )
    safety = payload.get(
        "safety"
    )

    missing_nested: dict[str, list[str]] = {}

    if not isinstance(
        ranking,
        dict,
    ):
        missing_nested[
            "ranking"
        ] = [
            "learning_score",
            "action",
            "signals",
            "weights",
        ]
    else:
        keys = [
            "learning_score",
            "action",
            "signals",
            "weights",
        ]

        missing = [
            key
            for key in keys
            if key not in ranking
        ]

        if missing:
            missing_nested[
                "ranking"
            ] = missing

    if not isinstance(
        guidance,
        dict,
    ):
        missing_nested[
            "research_guidance"
        ] = [
            "next_research_question",
            "verification_status",
        ]
    else:
        keys = [
            "next_research_question",
            "verification_status",
        ]

        missing = [
            key
            for key in keys
            if key not in guidance
        ]

        if missing:
            missing_nested[
                "research_guidance"
            ] = missing

    if not isinstance(
        safety,
        dict,
    ):
        missing_nested[
            "safety"
        ] = [
            "learned_rules_changed",
            "claims_changed",
            "validations_changed",
            "observations_changed",
            "knowledge_verified_changed",
        ]
    else:
        keys = [
            "learned_rules_changed",
            "claims_changed",
            "validations_changed",
            "observations_changed",
            "knowledge_verified_changed",
        ]

        missing = [
            key
            for key in keys
            if key not in safety
        ]

        if missing:
            missing_nested[
                "safety"
            ] = missing

    status = (
        "OK"
        if (
            not missing_top
            and not missing_nested
        )
        else "MISSING_KEYS"
    )

    return {
        "available": True,
        "status": status,
        "file": str(path),
        "missing_top_keys": missing_top,
        "nested_missing_keys": missing_nested,
    }


# ============================================================================
# JSON AUDIT - FINAL DECISION
# ============================================================================

def audit_final_decision() -> dict[str, Any]:
    path = latest_json(
        FINAL_DECISION_DIR,
        [
            f"final_decision_{TARGET_STRATEGY_ID}_*.json"
        ],
    )

    if path is None:
        return {
            "available": False,
            "status": "MISSING_FILE",
            "file": None,
        }

    payload = load_json_file(
        path
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "available": False,
            "status": "INVALID_JSON_ROOT",
            "file": str(path),
        }

    decision = recursive_find_decision_object(
        payload
    )

    if decision is None:
        return {
            "available": False,
            "status": "DECISION_OBJECT_NOT_FOUND",
            "file": str(path),
        }

    # Current V3 contract uses these nested keys.
    required_nested = [
        "decision",
        "action",
        "composite_score",
        "decision_confidence",
    ]

    # Legacy payloads may keep only decision/action at nested level.
    # We still require the current V3 keys for a true freeze.
    missing = [
        key
        for key in required_nested
        if key not in decision
    ]

    status = (
        "OK"
        if not missing
        else "MISSING_DECISION_KEYS"
    )

    return {
        "available": True,
        "status": status,
        "file": str(path),
        "decision_object_found": True,
        "decision_keys_found": sorted(
            decision.keys()
        ),
        "required_decision_keys": required_nested,
        "missing_decision_keys": missing,
    }


def audit_json_contracts() -> dict[str, Any]:
    return {
        "v6_pipeline": audit_v6_pipeline(),
        "evidence_consolidation": audit_consolidation(),
        "learning_ranking": audit_learning_ranking(),
        "final_decision": audit_final_decision(),
    }


# ============================================================================
# BUILD SNAPSHOT
# ============================================================================

def build_schema_snapshot(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    tables = audit_tables(
        conn
    )

    json_contracts = (
        audit_json_contracts()
    )

    missing_tables = [
        name
        for name, item in tables.items()
        if item["contract_status"]
        == "MISSING_TABLE"
    ]

    missing_columns = {
        name: item[
            "missing_required_columns"
        ]
        for name, item in tables.items()
        if item[
            "missing_required_columns"
        ]
    }

    json_errors = {
        name: item
        for name, item in json_contracts.items()
        if item.get("status")
        != "OK"
    }

    database_ready = (
        not missing_tables
        and not missing_columns
    )

    json_ready = not json_errors

    contract_status = (
        "FREEZE_READY"
        if database_ready and json_ready
        else "FREEZE_BLOCKED"
    )

    dashboard_interface = {
        "required_sections": [
            "knowledge",
            "brain",
            "learning",
            "research",
            "strategy",
        ],
        "learning_ranking_table": (
            "brain_strategy_learning_rankings"
        ),
        "research_status_fields": [
            "research_only",
            "execution_enabled",
            "verified",
            "action",
            "learning_score",
        ],
    }

    snapshot = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "project_root": str(
            PROJECT_ROOT
        ),
        "database": str(
            DB_PATH
        ),
        "contract_status": contract_status,
        "tables": tables,
        "json_contracts": json_contracts,
        "dashboard_interface": dashboard_interface,
        "safety": safety_contract(),
        "drift_summary": {
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "json_contract_errors": sorted(
                json_errors.keys()
            ),
        },
    }

    # Contract hash deliberately excludes:
    # - timestamps
    # - row counts
    # - latest file paths
    # so the hash represents the interface contract rather than data volume.
    contract_material = {
        "tables": table_fingerprint_payload(
            tables
        ),
        "json_contracts": {
            name: {
                "status": item.get(
                    "status"
                ),
                "required_contract": {
                    key: value
                    for key, value in item.items()
                    if key.startswith(
                        "required_"
                    )
                },
            }
            for name, item in sorted(
                json_contracts.items()
            )
        },
        "dashboard_interface": dashboard_interface,
        "safety_contract": safety_contract(),
    }

    snapshot[
        "contract_hash"
    ] = sha256_text(
        compact_json(
            contract_material
        )
    )

    return snapshot


# ============================================================================
# BASELINE / DRIFT
# ============================================================================

def ensure_freeze_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_schema_freezes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            contract_hash TEXT NOT NULL,
            contract_status TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_schema_freezes_hash
        ON brain_schema_freezes(contract_hash)
        """
    )


def latest_successful_freeze(
    conn: sqlite3.Connection,
) -> sqlite3.Row | None:
    """
    Baseline only comes from FREEZE_READY snapshots.
    A previous BLOCKED scan must never become a baseline.
    """
    if not table_exists(
        conn,
        "brain_schema_freezes",
    ):
        return None

    return conn.execute(
        """
        SELECT *
        FROM brain_schema_freezes
        WHERE contract_status='FREEZE_READY'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def compare_with_baseline(
    conn: sqlite3.Connection,
    current: dict[str, Any],
) -> dict[str, Any]:
    previous = latest_successful_freeze(
        conn
    )

    if previous is None:
        return {
            "baseline_exists": False,
            "status": "INITIAL_FREEZE",
            "previous_freeze_id": None,
            "previous_contract_hash": None,
            "current_contract_hash": current[
                "contract_hash"
            ],
            "hash_changed": False,
            "drift": False,
        }

    previous_hash = norm(
        previous["contract_hash"]
    )

    current_hash = norm(
        current["contract_hash"]
    )

    changed = (
        previous_hash
        != current_hash
    )

    return {
        "baseline_exists": True,
        "status": (
            "DRIFT_DETECTED"
            if changed
            else "NO_DRIFT"
        ),
        "previous_freeze_id": int(
            previous["id"]
        ),
        "previous_contract_hash": previous_hash,
        "current_contract_hash": current_hash,
        "hash_changed": changed,
        "drift": changed,
    }


def freeze_is_safe_to_publish(
    snapshot: dict[str, Any],
    comparison: dict[str, Any],
) -> bool:
    if snapshot[
        "contract_status"
    ] != "FREEZE_READY":
        return False

    if comparison.get(
        "drift"
    ):
        return False

    return True


# ============================================================================
# SAVE
# ============================================================================

def save_freeze(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO brain_schema_freezes (
            engine,
            engine_version,
            contract_hash,
            contract_status,
            snapshot_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ENGINE_NAME,
            ENGINE_VERSION,
            snapshot["contract_hash"],
            snapshot["contract_status"],
            compact_json(
                snapshot
            ),
            snapshot["created_at"],
        ),
    )

    return int(
        cur.lastrowid
    )


def save_json(
    report: dict[str, Any],
) -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        OUTPUT_DIR
        / (
            f"schema_freeze_"
            f"{timestamp}.json"
        )
    )

    output_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return output_path


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    snapshot: dict[str, Any],
    comparison: dict[str, Any],
    record_id: int,
    output_path: Path,
    publishable: bool,
) -> None:
    tables = snapshot[
        "tables"
    ]

    json_contracts = snapshot[
        "json_contracts"
    ]

    print("=" * 82)
    print("MARKETHQ SCHEMA FREEZE V1.1")
    print("=" * 82)
    print()

    print(
        f"Database        : {DB_PATH}"
    )

    print(
        f"Contract Status : "
        f"{snapshot['contract_status']}"
    )

    print(
        f"Contract Hash   : "
        f"{snapshot['contract_hash']}"
    )

    print()

    print("TABLE CONTRACTS")
    print("-" * 82)

    for name in CORE_TABLES:
        item = tables[name]

        print(
            f"{name:<42}"
            f"{item['contract_status']}"
        )

    print()

    print("JSON CONTRACTS")
    print("-" * 82)

    for name, item in json_contracts.items():
        print(
            f"{name:<30}"
            f"{item.get('status', 'UNKNOWN')}"
        )

        if item.get(
            "status"
        ) != "OK":
            print(
                f"  file    : "
                f"{item.get('file', 'N/A')}"
            )

            if item.get(
                "missing_top_keys"
            ):
                print(
                    "  missing : "
                    + ", ".join(
                        item[
                            "missing_top_keys"
                        ]
                    )
                )

            if item.get(
                "missing_ranking_keys"
            ):
                print(
                    "  ranking : "
                    + ", ".join(
                        item[
                            "missing_ranking_keys"
                        ]
                    )
                )

            if item.get(
                "missing_decision_keys"
            ):
                print(
                    "  decision: "
                    + ", ".join(
                        item[
                            "missing_decision_keys"
                        ]
                    )
                )

            if item.get(
                "nested_missing_keys"
            ):
                print(
                    "  nested  : "
                    + compact_json(
                        item[
                            "nested_missing_keys"
                        ]
                    )
                )

    print()

    print("BASELINE / DRIFT")
    print("-" * 82)

    print(
        f"Baseline exists : "
        f"{comparison['baseline_exists']}"
    )

    print(
        f"Baseline status : "
        f"{comparison['status']}"
    )

    print(
        f"Hash changed    : "
        f"{comparison['hash_changed']}"
    )

    print()

    print("DASHBOARD INTERFACE")
    print("-" * 82)

    interface = snapshot[
        "dashboard_interface"
    ]

    print(
        "Required sections: "
        + ", ".join(
            interface[
                "required_sections"
            ]
        )
    )

    print(
        "Learning table   : "
        f"{interface['learning_ranking_table']}"
    )

    print()

    print("SAFETY")
    print("-" * 82)

    print(
        f"Research Only       : "
        f"{snapshot['safety']['research_only']}"
    )

    print(
        f"Execution Enabled   : "
        f"{snapshot['safety']['execution_enabled']}"
    )

    print(
        "learned_rules       : unchanged"
    )

    print(
        "claims              : unchanged"
    )

    print(
        "validations         : unchanged"
    )

    print(
        "observations        : unchanged"
    )

    print(
        "Knowledge Verified  : unchanged"
    )

    print()

    print(
        f"Freeze record   : "
        f"{record_id}"
    )

    print(
        f"Saved snapshot  : "
        f"{output_path}"
    )

    print()

    if publishable:
        print(
            "RUN STATUS      : SUCCESS"
        )
    else:
        print(
            "RUN STATUS      : BLOCKED"
        )


# ============================================================================
# MAIN
# ============================================================================

def run() -> dict[str, Any]:
    assert_research_only()

    conn = open_db()

    try:
        ensure_freeze_table(
            conn
        )

        snapshot = build_schema_snapshot(
            conn
        )

        comparison = compare_with_baseline(
            conn,
            snapshot,
        )

        publishable = freeze_is_safe_to_publish(
            snapshot,
            comparison,
        )

        record_id = save_freeze(
            conn,
            snapshot,
        )

        conn.commit()

        report = {
            **snapshot,
            "baseline_comparison": comparison,
            "publishable": publishable,
            "freeze_record_id": record_id,
        }

        output_path = save_json(
            report
        )

        print_report(
            snapshot=snapshot,
            comparison=comparison,
            record_id=record_id,
            output_path=output_path,
            publishable=publishable,
        )

        if not publishable:
            if comparison.get(
                "drift"
            ):
                raise RuntimeError(
                    "Schema Freeze blocked: "
                    "successful baseline ile contract hash değişmiş."
                )

            raise RuntimeError(
                "Schema Freeze blocked: "
                "contract incomplete."
            )

        return report

    except sqlite3.Error:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run()

