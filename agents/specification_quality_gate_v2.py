from __future__ import annotations

import json
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# MARKET HQ
# FIN[SYS] SPECIFICATION QUALITY GATE V1
#
# Amaç:
#   Method Specification Engine'in ürettiği specification kayıtlarını ikinci
#   bir kalite katmanından geçirmek.
#
# Çıktılar:
#   SPEC_READY
#   PARTIAL
#   REFERENCE_ONLY
#   DUPLICATE_VARIANT
#
# Kritik prensip:
#   "Semi-computable" otomatik olarak "Python'a hazır" kabul edilmez.
#   Kaynakta olmayan kural/parametre icat edilmez.
#
# Bu dosya:
#   - method_registry ve knowledge_items verisini okumaz.
#   - method_specifications tablosunu denetler.
#   - Eski specification verilerini silmez.
#   - quality gate kolonlarını ayrı bir tabloda tutar.
# ============================================================================


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "market_hq.db"
OUTPUT_PATH = BASE_DIR / "specification_quality_gate_v1.json"

ENGINE_NAME = "FIN_SYS_SPECIFICATION_QUALITY_GATE_V2"
ENGINE_VERSION = "2.0"


# ============================================================================
# CONSTANTS
# ============================================================================

CRITICAL_FIELDS = (
    "inputs",
    "parameters",
    "signal_rules",
    "entry_rules",
    "exit_rules",
    "timeframe",
)

SECONDARY_FIELDS = (
    "filters",
    "market_scope",
    "risk_rules",
)

REQUIRED_JSON_FIELDS = (
    "inputs",
    "parameters",
    "signal_rules",
    "entry_rules",
    "exit_rules",
    "filters",
    "market_scope",
    "risk_rules",
    "missing_fields",
    "ambiguities",
    "linked_knowledge_ids",
    "linked_source_ids",
    "evidence_notes",
)

DUPLICATE_STRIP_PATTERNS = (
    r"\s+python\s+sinyal\s+tarama\s+kodu\b",
    r"\s+python\s+sinyal\s+kodu\b",
    r"\s+python\s+tarama\s+kodu\b",
    r"\s+python\s+kodu\b",
    r"\s+pine\s+script\b",
    r"\s+tradingview\b",
)


# ============================================================================
# DATAMODEL
# ============================================================================


@dataclass
class GateResult:
    method_id: int
    method_name: str
    canonical_key: str

    original_computability: str
    gate_status: str

    completeness: float
    confidence: float

    critical_score: float
    evidence_score: float
    distinct_rule_score: float

    duplicate_group_key: str | None = None
    duplicate_group_size: int = 1
    duplicate_rank: int = 1

    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    linked_knowledge_count: int = 0
    linked_source_count: int = 0

    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# HELPERS
# ============================================================================


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def norm(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        clean_text(value),
    )
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    return text.lower()


def safe_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default

    if isinstance(value, (dict, list)):
        return value

    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def as_list(value: Any) -> list[Any]:
    parsed = safe_json(value, value)

    if isinstance(parsed, list):
        return parsed

    if parsed in (None, ""):
        return []

    return [parsed]


def as_string_list(value: Any) -> list[str]:
    result: list[str] = []

    for item in as_list(value):
        text = clean_text(item)
        if text and text not in result:
            result.append(text)

    return result


def as_dict(value: Any) -> dict[str, Any]:
    parsed = safe_json(value, {})

    if isinstance(parsed, dict):
        return parsed

    return {}


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ============================================================================
# DATABASE
# ============================================================================


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
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


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    if not table_exists(
        conn,
        table_name,
    ):
        return set()

    return {
        str(row["name"])
        for row in conn.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    }


def ensure_schema(
    conn: sqlite3.Connection,
) -> None:
    """
    Quality gate tablosunu güvenli şekilde oluşturur.

    NOT:
    sqlite3.Connection.execute() tek SQL statement çalıştırır.
    Bu yüzden CREATE TABLE ve CREATE INDEX komutları ayrı execute()
    çağrılarıyla yürütülür.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS specification_quality_gate (
            method_id INTEGER PRIMARY KEY,
            method_name TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            original_computability TEXT NOT NULL,
            gate_status TEXT NOT NULL,
            completeness REAL NOT NULL,
            confidence REAL NOT NULL,
            critical_score REAL NOT NULL,
            evidence_score REAL NOT NULL,
            distinct_rule_score REAL NOT NULL,
            duplicate_group_key TEXT,
            duplicate_group_size INTEGER NOT NULL DEFAULT 1,
            duplicate_rank INTEGER NOT NULL DEFAULT 1,
            blockers_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            linked_knowledge_count INTEGER NOT NULL DEFAULT 0,
            linked_source_count INTEGER NOT NULL DEFAULT 0,
            generated_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quality_gate_status
        ON specification_quality_gate(gate_status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quality_gate_confidence
        ON specification_quality_gate(confidence DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quality_gate_completeness
        ON specification_quality_gate(completeness DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quality_gate_duplicate
        ON specification_quality_gate(duplicate_group_key)
        """
    )

    conn.commit()


# ============================================================================
# LOAD SPECIFICATIONS
# ============================================================================


def load_specifications(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    if not table_exists(
        conn,
        "method_specifications",
    ):
        raise RuntimeError(
            "method_specifications tablosu bulunamadı. "
            "Önce Method Specification Engine V3/V4 çalıştırılmalı."
        )

    columns = table_columns(
        conn,
        "method_specifications",
    )

    required = {
        "method_id",
        "method_name",
        "canonical_key",
        "category",
        "objective",
        "inputs_json",
        "parameters_json",
        "signal_rules_json",
        "entry_rules_json",
        "exit_rules_json",
        "filters_json",
        "timeframe",
        "market_scope_json",
        "risk_rules_json",
        "linked_knowledge_ids_json",
        "linked_source_ids_json",
        "evidence_state",
        "evidence_notes_json",
        "confidence",
        "completeness",
        "computability",
        "missing_fields_json",
        "ambiguities_json",
    }

    missing = required - columns

    if missing:
        raise RuntimeError(
            "method_specifications eksik kolonlar: "
            + ", ".join(sorted(missing))
        )

    return conn.execute(
        """
        SELECT
            method_id,
            method_name,
            canonical_key,
            category,
            objective,

            inputs_json,
            parameters_json,
            signal_rules_json,
            entry_rules_json,
            exit_rules_json,
            filters_json,

            timeframe,
            market_scope_json,
            risk_rules_json,

            linked_knowledge_ids_json,
            linked_source_ids_json,

            evidence_state,
            evidence_notes_json,

            confidence,
            completeness,
            computability,

            missing_fields_json,
            ambiguities_json
        FROM method_specifications
        ORDER BY method_id ASC
        """
    ).fetchall()


# ============================================================================
# NORMALIZATION / DUPLICATE DETECTION
# ============================================================================


def duplicate_group_key(
    method_name: str,
    canonical_key_value: str,
) -> str:
    """
    Sadece sunum biçimlerini temizler.
    Farklı yöntem adlarını fuzzy similarity ile birleştirmez.
    """

    text = norm(
        canonical_key_value
        or method_name
    )

    text = re.sub(
        r"\bfin\s*\[sys\]\b",
        "",
        text,
    )

    for pattern in DUPLICATE_STRIP_PATTERNS:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"\(\s*(?:python|tradingview|pine)[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(?:v\d+|version\s*\d+)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def build_duplicate_groups(
    rows: list[sqlite3.Row],
) -> dict[str, list[sqlite3.Row]]:
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        key = duplicate_group_key(
            row["method_name"],
            row["canonical_key"],
        )

        if not key:
            key = f"method:{row['method_id']}"

        groups[key].append(
            row
        )

    return groups


# ============================================================================
# QUALITY SCORING
# ============================================================================


def field_present(
    row: sqlite3.Row,
    field_name: str,
) -> bool:
    if field_name == "timeframe":
        return bool(
            clean_text(
                row["timeframe"]
            )
        )

    if field_name == "objective":
        return bool(
            clean_text(
                row["objective"]
            )
        )

    if field_name in {
        "inputs",
        "parameters",
        "signal_rules",
        "entry_rules",
        "exit_rules",
        "filters",
        "market_scope",
        "risk_rules",
        "missing_fields",
        "ambiguities",
        "linked_knowledge_ids",
        "linked_source_ids",
        "evidence_notes",
    }:
        json_column = (
            f"{field_name}_json"
        )

        value = safe_json(
            row[json_column],
            [],
        )

        if isinstance(value, dict):
            return bool(value)

        if isinstance(value, list):
            return len(value) > 0

        return bool(value)

    return False


def linked_knowledge_ids(
    row: sqlite3.Row,
) -> list[str]:
    return as_string_list(
        row["linked_knowledge_ids_json"]
    )


def linked_source_ids(
    row: sqlite3.Row,
) -> list[str]:
    return as_string_list(
        row["linked_source_ids_json"]
    )


def rule_signature(
    row: sqlite3.Row,
) -> str:
    signal = as_string_list(
        row["signal_rules_json"]
    )
    entry = as_string_list(
        row["entry_rules_json"]
    )
    exit_rules = as_string_list(
        row["exit_rules_json"]
    )

    blob = "|".join(
        [
            *signal[:10],
            *entry[:10],
            *exit_rules[:10],
        ]
    )

    return norm(blob)


def compute_critical_score(
    row: sqlite3.Row,
) -> float:
    present = sum(
        1.0
        for field_name in CRITICAL_FIELDS
        if field_present(
            row,
            field_name,
        )
    )

    return round(
        present
        / len(CRITICAL_FIELDS)
        * 100.0,
        1,
    )


def compute_evidence_score(
    row: sqlite3.Row,
) -> float:
    score = 0.0

    knowledge_count = len(
        linked_knowledge_ids(row)
    )

    source_count = len(
        linked_source_ids(row)
    )

    evidence_state = norm(
        row["evidence_state"]
    )

    if knowledge_count > 0:
        score += 45.0

    if source_count > 0:
        score += 35.0

    if evidence_state == "linked_source":
        score += 20.0

    elif evidence_state == "knowledge_only":
        score += 10.0

    # Registry-only kaynakta sayı 0 kalır.
    return min(
        100.0,
        round(score, 1),
    )


def compute_distinct_rule_score(
    row: sqlite3.Row,
) -> float:
    signal = as_string_list(
        row["signal_rules_json"]
    )
    entry = as_string_list(
        row["entry_rules_json"]
    )
    exit_rules = as_string_list(
        row["exit_rules_json"]
    )

    non_empty_groups = sum(
        1
        for group in (
            signal,
            entry,
            exit_rules,
        )
        if group
    )

    unique_rules = len(
        {
            norm(rule)
            for rule in (
                signal
                + entry
                + exit_rules
            )
            if norm(rule)
        }
    )

    score = (
        non_empty_groups
        / 3.0
        * 60.0
    )

    score += min(
        40.0,
        unique_rules * 8.0,
    )

    return round(
        min(
            100.0,
            score,
        ),
        1,
    )


def make_blockers(
    row: sqlite3.Row,
    critical_score: float,
    evidence_score: float,
) -> list[str]:
    blockers: list[str] = []

    missing = as_string_list(
        row["missing_fields_json"]
    )

    for field_name in (
        "signal_rules",
        "entry_rules",
        "exit_rules",
        "timeframe",
    ):
        if field_name in missing:
            blockers.append(
                f"missing_{field_name}"
            )

    if not linked_knowledge_ids(row):
        blockers.append(
            "no_linked_knowledge"
        )

    if (
        safe_float(row["confidence"]) < 60.0
    ):
        blockers.append(
            "low_confidence"
        )

    if (
        safe_float(row["completeness"]) < 60.0
    ):
        blockers.append(
            "low_completeness"
        )

    if critical_score < 66.7:
        blockers.append(
            "critical_spec_incomplete"
        )

    if evidence_score < 45.0:
        blockers.append(
            "weak_evidence_link"
        )

    return list(
        dict.fromkeys(
            blockers
        )
    )


def make_warnings(
    row: sqlite3.Row,
    critical_score: float,
    evidence_score: float,
    distinct_rule_score: float,
) -> list[str]:
    warnings: list[str] = []

    missing = set(
        as_string_list(
            row["missing_fields_json"]
        )
    )

    if "parameters" in missing:
        warnings.append(
            "parameters_missing"
        )

    if "filters" in missing:
        warnings.append(
            "filters_missing"
        )

    if "market_scope" in missing:
        warnings.append(
            "market_scope_missing"
        )

    if "risk_rules" in missing:
        warnings.append(
            "risk_rules_missing"
        )

    if evidence_score < 80.0:
        warnings.append(
            "evidence_not_strong"
        )

    if distinct_rule_score < 70.0:
        warnings.append(
            "rules_not_sufficiently_distinct"
        )

    ambiguities = as_string_list(
        row["ambiguities_json"]
    )

    if ambiguities:
        warnings.append(
            "source_contains_ambiguities"
        )

    if (
        safe_float(row["completeness"]) < 80.0
    ):
        warnings.append(
            "completeness_below_80"
        )

    return list(
        dict.fromkeys(
            warnings
        )
    )


# ============================================================================
# GATE DECISION
# ============================================================================


def decide_gate_status(
    row: sqlite3.Row,
    critical_score: float,
    evidence_score: float,
    distinct_rule_score: float,
    duplicate_group_size: int,
    is_duplicate_variant: bool,
) -> str:
    original = norm(
        row["computability"]
    )

    confidence = safe_float(
        row["confidence"]
    )

    completeness = safe_float(
        row["completeness"]
    )

    # Duplicate kayıtlar kalite kaydı olarak korunuyor,
    # fakat primary specification olarak işaretlenmiyor.
    if is_duplicate_variant:
        return "DUPLICATE_VARIANT"

    # Gerçekten hazır olmak için:
    # - çekirdek alanların tamamına yakın olması
    # - yeterli confidence
    # - evidence bağlantısı
    # - distinct rules
    # şartlarını birlikte arıyoruz.
    if (
        critical_score >= 100.0
        and confidence >= 75.0
        and completeness >= 80.0
        and evidence_score >= 80.0
        and distinct_rule_score >= 70.0
        and original
        in {
            "computable_candidate",
            "semi_computable",
        }
    ):
        return "SPEC_READY"

    # Kaynak gerçekten yararlı ama eksikse PARTIAL.
    if (
        critical_score >= 66.7
        and evidence_score >= 45.0
        and (
            original
            in {
                "computable_candidate",
                "semi_computable",
            }
            or completeness >= 60.0
        )
    ):
        return "PARTIAL"

    return "REFERENCE_ONLY"


# ============================================================================
# DUPLICATE RANK
# ============================================================================


def duplicate_sort_key(
    row: sqlite3.Row,
) -> tuple[float, float, float, int]:
    evidence_score = compute_evidence_score(
        row
    )

    return (
        -safe_float(
            row["completeness"]
        ),
        -safe_float(
            row["confidence"]
        ),
        -evidence_score,
        int(
            row["method_id"]
        ),
    )


def choose_primary(
    group: list[sqlite3.Row],
) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    ordered = sorted(
        group,
        key=duplicate_sort_key,
    )

    return (
        ordered[0],
        ordered[1:],
    )


# ============================================================================
# BUILD RESULTS
# ============================================================================


def evaluate_group(
    group_key: str,
    group: list[sqlite3.Row],
) -> list[GateResult]:
    primary, variants = choose_primary(
        group
    )

    results: list[GateResult] = []

    ordered = [
        primary,
        *variants,
    ]

    for rank, row in enumerate(
        ordered,
        start=1,
    ):
        critical_score = compute_critical_score(
            row
        )

        evidence_score = compute_evidence_score(
            row
        )

        distinct_rule_score = compute_distinct_rule_score(
            row
        )

        blockers = make_blockers(
            row,
            critical_score,
            evidence_score,
        )

        warnings = make_warnings(
            row,
            critical_score,
            evidence_score,
            distinct_rule_score,
        )

        is_variant = (
            rank > 1
            and len(group) > 1
        )

        status = decide_gate_status(
            row,
            critical_score,
            evidence_score,
            distinct_rule_score,
            duplicate_group_size=len(group),
            is_duplicate_variant=is_variant,
        )

        result = GateResult(
            method_id=int(
                row["method_id"]
            ),
            method_name=clean_text(
                row["method_name"]
            ),
            canonical_key=clean_text(
                row["canonical_key"]
            ),
            original_computability=clean_text(
                row["computability"]
            ),
            gate_status=status,
            completeness=round(
                safe_float(
                    row["completeness"]
                ),
                1,
            ),
            confidence=round(
                safe_float(
                    row["confidence"]
                ),
                1,
            ),
            critical_score=critical_score,
            evidence_score=evidence_score,
            distinct_rule_score=distinct_rule_score,
            duplicate_group_key=group_key
            if len(group) > 1
            else None,
            duplicate_group_size=len(
                group
            ),
            duplicate_rank=rank,
            blockers=blockers,
            warnings=warnings,
            linked_knowledge_count=len(
                linked_knowledge_ids(row)
            ),
            linked_source_count=len(
                linked_source_ids(row)
            ),
            generated_at=now_iso(),
        )

        results.append(
            result
        )

    return results


# ============================================================================
# SAVE
# ============================================================================


def save_result(
    conn: sqlite3.Connection,
    result: GateResult,
) -> None:
    conn.execute(
        """
        INSERT INTO specification_quality_gate (
            method_id,
            method_name,
            canonical_key,

            original_computability,
            gate_status,

            completeness,
            confidence,

            critical_score,
            evidence_score,
            distinct_rule_score,

            duplicate_group_key,
            duplicate_group_size,
            duplicate_rank,

            blockers_json,
            warnings_json,

            linked_knowledge_count,
            linked_source_count,

            generated_at
        )
        VALUES (
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?
        )
        ON CONFLICT(method_id)
        DO UPDATE SET
            method_name = excluded.method_name,
            canonical_key = excluded.canonical_key,

            original_computability =
                excluded.original_computability,

            gate_status =
                excluded.gate_status,

            completeness =
                excluded.completeness,

            confidence =
                excluded.confidence,

            critical_score =
                excluded.critical_score,

            evidence_score =
                excluded.evidence_score,

            distinct_rule_score =
                excluded.distinct_rule_score,

            duplicate_group_key =
                excluded.duplicate_group_key,

            duplicate_group_size =
                excluded.duplicate_group_size,

            duplicate_rank =
                excluded.duplicate_rank,

            blockers_json =
                excluded.blockers_json,

            warnings_json =
                excluded.warnings_json,

            linked_knowledge_count =
                excluded.linked_knowledge_count,

            linked_source_count =
                excluded.linked_source_count,

            generated_at =
                excluded.generated_at
        """,
        (
            result.method_id,
            result.method_name,
            result.canonical_key,

            result.original_computability,
            result.gate_status,

            result.completeness,
            result.confidence,

            result.critical_score,
            result.evidence_score,
            result.distinct_rule_score,

            result.duplicate_group_key,
            result.duplicate_group_size,
            result.duplicate_rank,

            json.dumps(
                result.blockers,
                ensure_ascii=False,
            ),
            json.dumps(
                result.warnings,
                ensure_ascii=False,
            ),

            result.linked_knowledge_count,
            result.linked_source_count,

            result.generated_at,
        ),
    )


def save_json(
    payload: dict[str, Any],
) -> None:
    temp = OUTPUT_PATH.with_suffix(
        ".tmp"
    )

    temp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp.replace(
        OUTPUT_PATH
    )


# ============================================================================
# PAYLOAD
# ============================================================================


def make_payload(
    results: list[GateResult],
    source_count: int,
    duplicate_groups: dict[str, list[sqlite3.Row]],
) -> dict[str, Any]:
    status_counts = Counter(
        result.gate_status
        for result in results
    )

    original_counts = Counter(
        result.original_computability
        for result in results
    )

    avg_completeness = (
        statistics.mean(
            result.completeness
            for result in results
        )
        if results
        else 0.0
    )

    avg_confidence = (
        statistics.mean(
            result.confidence
            for result in results
        )
        if results
        else 0.0
    )

    avg_evidence = (
        statistics.mean(
            result.evidence_score
            for result in results
        )
        if results
        else 0.0
    )

    primary_results = [
        result
        for result in results
        if result.gate_status != "DUPLICATE_VARIANT"
    ]

    ready = [
        result
        for result in primary_results
        if result.gate_status
        == "SPEC_READY"
    ]

    partial = [
        result
        for result in primary_results
        if result.gate_status
        == "PARTIAL"
    ]

    ready.sort(
        key=lambda result: (
            -result.confidence,
            -result.completeness,
        )
    )

    partial.sort(
        key=lambda result: (
            -result.completeness,
            -result.confidence,
        )
    )

    duplicate_group_count = sum(
        1
        for group in duplicate_groups.values()
        if len(group) > 1
    )

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "generated_at": now_iso(),
        "database": str(DB_PATH),

        "source_specifications": source_count,
        "quality_gate_records": len(results),

        "original_computability": dict(
            original_counts
        ),

        "gate_status_counts": dict(
            status_counts
        ),

        "duplicate_groups": duplicate_group_count,
        "duplicate_variant_records": status_counts.get(
            "DUPLICATE_VARIANT",
            0,
        ),

        "primary_specifications": len(
            primary_results
        ),

        "spec_ready_count": len(
            ready
        ),

        "partial_count": len(
            partial
        ),

        "reference_only_count": status_counts.get(
            "REFERENCE_ONLY",
            0,
        ),

        "average_completeness": round(
            avg_completeness,
            1,
        ),

        "average_confidence": round(
            avg_confidence,
            1,
        ),

        "average_evidence_score": round(
            avg_evidence,
            1,
        ),

        "top_spec_ready": [
            result.to_dict()
            for result in ready[:25]
        ],

        "top_partial": [
            result.to_dict()
            for result in partial[:25]
        ],

        "results": [
            result.to_dict()
            for result in results
        ],
    }


# ============================================================================
# MAIN
# ============================================================================


def run() -> dict[str, Any]:
    conn = connect()

    try:
        ensure_schema(
            conn
        )

        rows = load_specifications(
            conn
        )

        duplicate_groups = build_duplicate_groups(
            rows
        )

        results: list[GateResult] = []

        for group_key, group in duplicate_groups.items():
            group_results = evaluate_group(
                group_key,
                group,
            )

            for result in group_results:
                save_result(
                    conn,
                    result,
                )

            results.extend(
                group_results
            )

        conn.commit()

        payload = make_payload(
            results,
            source_count=len(rows),
            duplicate_groups=duplicate_groups,
        )

        payload["status"] = "completed"

        save_json(
            payload
        )

        return payload

    finally:
        conn.close()


def print_summary(
    payload: dict[str, Any],
) -> None:
    print()
    print("=" * 78)
    print("FIN[SYS] SPECIFICATION QUALITY GATE V1")
    print("=" * 78)

    print(
        f"Database: {payload['database']}"
    )

    print(
        f"Source specifications: "
        f"{payload['source_specifications']}"
    )

    print(
        f"Quality gate records: "
        f"{payload['quality_gate_records']}"
    )

    print()

    print("ORIGINAL COMPUTABILITY")
    print("-" * 78)

    for key, value in sorted(
        payload["original_computability"].items()
    ):
        print(
            f"{key}: {value}"
        )

    print()

    print("QUALITY GATE")
    print("-" * 78)

    print(
        "SPEC_READY: "
        f"{payload['spec_ready_count']}"
    )

    print(
        "PARTIAL: "
        f"{payload['partial_count']}"
    )

    print(
        "REFERENCE_ONLY: "
        f"{payload['reference_only_count']}"
    )

    print(
        "DUPLICATE_VARIANT: "
        f"{payload['duplicate_variant_records']}"
    )

    print()

    print("DUPLICATES")
    print("-" * 78)

    print(
        f"Duplicate groups: "
        f"{payload['duplicate_groups']}"
    )

    print()

    print("QUALITY")
    print("-" * 78)

    print(
        "Average completeness: "
        f"{payload['average_completeness']}"
    )

    print(
        "Average confidence: "
        f"{payload['average_confidence']}"
    )

    print(
        "Average evidence score: "
        f"{payload['average_evidence_score']}"
    )

    print()

    print("TOP SPEC_READY")
    print("-" * 78)

    for index, item in enumerate(
        payload["top_spec_ready"][:20],
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{item['method_name'][:65]} | "
            f"C={item['completeness']:.1f} | "
            f"Conf={item['confidence']:.1f} | "
            f"Evidence={item['evidence_score']:.1f}"
        )

    print()

    print("TOP PARTIAL")
    print("-" * 78)

    for index, item in enumerate(
        payload["top_partial"][:20],
        start=1,
    ):
        blockers = ", ".join(
            item["blockers"][:3]
        )

        print(
            f"{index:02d}. "
            f"{item['method_name'][:58]} | "
            f"C={item['completeness']:.1f} | "
            f"Conf={item['confidence']:.1f} | "
            f"Blockers={blockers}"
        )

    print()

    print(
        f"JSON output: {OUTPUT_PATH}"
    )

    print(
        "✅ Specification Quality Gate V1 tamamlandı."
    )


def main() -> None:
    payload = run()
    print_summary(
        payload
    )


if __name__ == "__main__":
    main()
