from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# MARKET HQ
# FIN[SYS] METHOD SPECIFICATION CONSOLIDATOR V2
#
# Görev:
#   Eski V1/V2 + yeni V3 specification kayıtlarını tek bir registry yöntemi
#   altında toplamak.
#
# Hedef:
#   Registry = 259
#   Consolidated methods = ideal olarak 259
#
# Önemli:
#   - Eski specification kayıtları silinmez.
#   - method_registry değişmez.
#   - knowledge_items değişmez.
#   - Fuzzy similarity ile farklı yöntemler birleştirilmez.
#   - Öncelik: registry_id -> exact canonical key -> güvenli isim varyantı.
#   - Her canonical method için tek PRIMARY specification seçilir.
#   - Diğer specification kayıtları VARIANTS olarak korunur.
#
# Çıktılar:
#   market_hq.db
#       method_specification_consolidated
#
#   method_specification_consolidated_v1.json
#       Panel/raporlama için 259'luk temiz veri seti.
# ============================================================================


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "market_hq.db"
OUTPUT_PATH = BASE_DIR / "method_specification_consolidated_v3.json"

ENGINE_NAME = "FIN_SYS_METHOD_SPECIFICATION_CONSOLIDATOR_V3"
ENGINE_VERSION = "1.0"


# ============================================================================
# HELPERS
# ============================================================================


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def norm(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        clean_text(value),
    )
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


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


def as_dict(value: Any) -> dict[str, Any]:
    parsed = safe_json(value, {})

    if isinstance(parsed, dict):
        return parsed

    return {}


def unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []

    for value in values:
        item = clean_text(value)

        if item and item not in result:
            result.append(item)

    return result


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ============================================================================
# SAFE CANONICALIZATION
# ============================================================================


def safe_canonical_key(
    method_name: str,
    canonical_key: str | None = None,
) -> str:
    """
    Yalnızca sunum/format eklerini temizler.

    Burada:
      MIRACULUM 4S
      MIRACULUM Trend

    gibi farklı isimler kesinlikle aynı kabul edilmez.
    """

    text = norm(
        canonical_key
        or method_name
    )

    text = re.sub(
        r"^fin\s*\[sys\]\s*[-:|]?\s*",
        "",
        text,
    )

    # Eski/yeni dosya sunum ekleri.
    suffix_patterns = (
        r"\s+python\s+sinyal\s+tarama\s+kodu\b",
        r"\s+python\s+sinyal\s+kodu\b",
        r"\s+python\s+tarama\s+kodu\b",
        r"\s+python\s+kodu\b",
        r"\s+pine\s+script\b",
        r"\s+tradingview\b",
    )

    for pattern in suffix_patterns:
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
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def registry_alias_keys(
    registry_row: sqlite3.Row,
) -> set[str]:
    values = (
        clean_text(
            registry_row["registry_name"]
        ),
        clean_text(
            registry_row["canonical_name"]
        ),
    )

    result = set()

    for value in values:
        if value:
            result.add(
                safe_canonical_key(
                    value
                )
            )

    return {
        key
        for key in result
        if key
    }


def spec_alias_keys(
    row: sqlite3.Row,
) -> set[str]:
    values = (
        clean_text(
            row["method_name"]
        ),
        clean_text(
            row["canonical_key"]
        ),
    )

    result = set()

    for value in values:
        if value:
            result.add(
                safe_canonical_key(
                    value
                )
            )

    return {
        key
        for key in result
        if key
    }


# ============================================================================
# DB
# ============================================================================


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH
    )
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


def ensure_source_tables(
    conn: sqlite3.Connection,
) -> None:
    if not table_exists(
        conn,
        "method_registry",
    ):
        raise RuntimeError(
            "method_registry tablosu bulunamadı."
        )

    if not table_exists(
        conn,
        "method_specifications",
    ):
        raise RuntimeError(
            "method_specifications tablosu bulunamadı."
        )


def ensure_consolidated_schema(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_specification_consolidated (
            registry_id INTEGER PRIMARY KEY,

            method_name TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            category TEXT NOT NULL,

            objective TEXT,

            inputs_json TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            signal_rules_json TEXT NOT NULL,
            entry_rules_json TEXT NOT NULL,
            exit_rules_json TEXT NOT NULL,
            filters_json TEXT NOT NULL,

            timeframe TEXT,
            market_scope_json TEXT NOT NULL,
            risk_rules_json TEXT NOT NULL,

            confidence REAL NOT NULL,
            completeness REAL NOT NULL,
            computability TEXT NOT NULL,

            evidence_state TEXT NOT NULL,
            evidence_notes_json TEXT NOT NULL,

            gate_status TEXT NOT NULL DEFAULT 'UNASSESSED',

            linked_knowledge_ids_json TEXT NOT NULL,
            linked_source_ids_json TEXT NOT NULL,

            primary_specification_id INTEGER,

            variant_specification_ids_json TEXT NOT NULL,

            consolidation_method TEXT NOT NULL,
            consolidation_notes_json TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_msc_computability
        ON method_specification_consolidated(computability)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_msc_gate_status
        ON method_specification_consolidated(gate_status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_msc_confidence
        ON method_specification_consolidated(confidence DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_msc_completeness
        ON method_specification_consolidated(completeness DESC)
        """
    )

    conn.commit()


# ============================================================================
# REGISTRY LOADING
# ============================================================================


def discover_registry_columns(
    conn: sqlite3.Connection,
) -> dict[str, str | None]:
    columns = table_columns(
        conn,
        "method_registry",
    )

    def choose(
        candidates: tuple[str, ...],
    ) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate

        lower_map = {
            column.lower(): column
            for column in columns
        }

        for candidate in candidates:
            found = lower_map.get(
                candidate.lower()
            )

            if found:
                return found

        return None

    return {
        "id": choose(
            (
                "id",
                "method_id",
                "registry_id",
            )
        ),
        "name": choose(
            (
                "method_name",
                "canonical_name",
                "name",
                "title",
            )
        ),
        "canonical_name": choose(
            (
                "canonical_name",
                "method_name",
                "name",
                "title",
            )
        ),
        "category": choose(
            (
                "category",
                "method_type",
                "type",
            )
        ),
        "confidence": choose(
            (
                "confidence",
                "registry_confidence",
                "score",
            )
        ),
    }


def load_registry(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    layout = discover_registry_columns(
        conn
    )

    id_col = layout["id"]
    name_col = layout["name"]
    canonical_col = layout["canonical_name"]
    category_col = layout["category"]
    confidence_col = layout["confidence"]

    if not id_col:
        raise RuntimeError(
            "method_registry içinde ID kolonu bulunamadı."
        )

    if not name_col:
        raise RuntimeError(
            "method_registry içinde isim kolonu bulunamadı."
        )

    select_parts = [
        f'"{id_col}" AS registry_id',
        f'"{name_col}" AS registry_name',
    ]

    if canonical_col:
        select_parts.append(
            f'"{canonical_col}" AS canonical_name'
        )
    else:
        select_parts.append(
            "NULL AS canonical_name"
        )

    if category_col:
        select_parts.append(
            f'"{category_col}" AS registry_category'
        )
    else:
        select_parts.append(
            "NULL AS registry_category"
        )

    if confidence_col:
        select_parts.append(
            f'"{confidence_col}" AS registry_confidence'
        )
    else:
        select_parts.append(
            "NULL AS registry_confidence"
        )

    query = (
        "SELECT "
        + ", ".join(select_parts)
        + ' FROM "method_registry"'
        + " ORDER BY "
        + f'"{id_col}" ASC'
    )

    return conn.execute(
        query
    ).fetchall()


# ============================================================================
# SPECIFICATION LOADING
# ============================================================================


def load_specifications(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    columns = table_columns(
        conn,
        "method_specifications",
    )

    required = {
        "method_id",
        "source_id",
        "method_name",
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
        "confidence",
        "completeness",
        "computability",
        "missing_fields_json",
        "ambiguities_json",
        "evidence_state",
    }

    missing = required - columns

    if missing:
        raise RuntimeError(
            "method_specifications eksik kolonlar: "
            + ", ".join(
                sorted(missing)
            )
        )

    optional_registry_id = (
        "registry_id"
        if "registry_id" in columns
        else "NULL"
    )

    optional_canonical_key = (
        "canonical_key"
        if "canonical_key" in columns
        else "method_name"
    )

    optional_knowledge = (
        "linked_knowledge_ids_json"
        if "linked_knowledge_ids_json" in columns
        else "'[]'"
    )

    optional_sources = (
        "linked_source_ids_json"
        if "linked_source_ids_json" in columns
        else "'[]'"
    )

    optional_evidence_notes = (
        "evidence_notes_json"
        if "evidence_notes_json" in columns
        else "'[]'"
    )

    query = f"""
        SELECT
            method_id,
            {optional_registry_id} AS registry_id,
            source_id,

            method_name,
            {optional_canonical_key} AS canonical_key,
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

            confidence,
            completeness,
            computability,

            missing_fields_json,
            ambiguities_json,

            evidence_state,

            {optional_knowledge} AS linked_knowledge_ids_json,
            {optional_sources} AS linked_source_ids_json,
            {optional_evidence_notes} AS evidence_notes_json
        FROM method_specifications
        ORDER BY method_id ASC
    """

    return conn.execute(
        query
    ).fetchall()


# ============================================================================
# QUALITY / PRIMARY SELECTION
# ============================================================================


def spec_linked_knowledge_count(
    row: sqlite3.Row,
) -> int:
    return len(
        as_list(
            row["linked_knowledge_ids_json"]
        )
    )


def spec_linked_source_count(
    row: sqlite3.Row,
) -> int:
    return len(
        as_list(
            row["linked_source_ids_json"]
        )
    )


def original_status_rank(
    computability: str,
) -> int:
    status = norm(
        computability
    )

    if status == "computable_candidate":
        return 3

    if status == "semi_computable":
        return 2

    return 1


def evidence_rank(
    evidence_state: str,
) -> int:
    value = norm(
        evidence_state
    )

    if value == "linked_source":
        return 3

    if value == "knowledge_only":
        return 2

    return 1


def primary_sort_key(
    row: sqlite3.Row,
) -> tuple[Any, ...]:
    # Higher is better; Python sorted ascending so values are negated.
    return (
        -original_status_rank(
            clean_text(
                row["computability"]
            )
        ),
        -safe_float(
            row["completeness"]
        ),
        -safe_float(
            row["confidence"]
        ),
        -evidence_rank(
            clean_text(
                row["evidence_state"]
            )
        ),
        -spec_linked_knowledge_count(
            row
        ),
        -spec_linked_source_count(
            row
        ),
        int(
            row["method_id"]
        ),
    )


def merge_json_lists(
    rows: list[sqlite3.Row],
    column: str,
) -> list[str]:
    values: list[Any] = []

    for row in rows:
        values.extend(
            as_list(
                row[column]
            )
        )

    return unique_strings(
        values
    )


def merge_parameters(
    rows: list[sqlite3.Row],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    # Primary first.
    ordered = sorted(
        rows,
        key=primary_sort_key,
    )

    for row in ordered:
        data = as_dict(
            row["parameters_json"]
        )

        for key, value in data.items():
            if key not in merged:
                merged[key] = value

    return merged


def merge_scalar(
    rows: list[sqlite3.Row],
    column: str,
) -> Any:
    ordered = sorted(
        rows,
        key=primary_sort_key,
    )

    for row in ordered:
        value = row[column]

        if value not in (None, ""):
            return value

    return None


def derive_gate_status(
    row: sqlite3.Row,
) -> str:
    """
    Consolidator, Quality Gate'e zorunlu bağlı değil.
    Ancak mevcut quality gate tablosu varsa status'u okuyabiliriz.
    """

    return "UNASSESSED"


def load_gate_statuses(
    conn: sqlite3.Connection,
) -> dict[int, str]:
    if not table_exists(
        conn,
        "specification_quality_gate",
    ):
        return {}

    columns = table_columns(
        conn,
        "specification_quality_gate",
    )

    if not {
        "method_id",
        "gate_status",
    }.issubset(columns):
        return {}

    rows = conn.execute(
        """
        SELECT method_id, gate_status
        FROM specification_quality_gate
        """
    ).fetchall()

    return {
        int(row["method_id"]):
            clean_text(row["gate_status"])
        for row in rows
    }


# ============================================================================
# MATCHING
# ============================================================================


def index_specs_by_registry_id(
    specs: list[sqlite3.Row],
) -> dict[int, list[sqlite3.Row]]:
    result: dict[int, list[sqlite3.Row]] = defaultdict(list)

    for row in specs:
        value = row["registry_id"]

        if value in (None, ""):
            continue

        try:
            registry_id = int(value)
        except (TypeError, ValueError):
            continue

        result[registry_id].append(
            row
        )

    return result


def index_specs_by_alias(
    specs: list[sqlite3.Row],
) -> dict[str, list[sqlite3.Row]]:
    result: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in specs:
        for key in spec_alias_keys(
            row
        ):
            result[key].append(
                row
            )

    return result


def unique_rows(
    rows: list[sqlite3.Row],
) -> list[sqlite3.Row]:
    result: list[sqlite3.Row] = []
    seen: set[int] = set()

    for row in rows:
        row_id = int(
            row["method_id"]
        )

        if row_id in seen:
            continue

        seen.add(
            row_id
        )

        result.append(
            row
        )

    return result


def build_registry_groups(
    registry_rows: list[sqlite3.Row],
) -> dict[str, list[sqlite3.Row]]:
    """
    Güvenli canonical grouping.

    Aynı isim ancak format farklarıyla tekrar ediyorsa birleştirilir.
    Örnek:
        HSD Trend Algoritması
        hsd trend algoritması
        HSD Trend Algoritması (Python)

    Birleştirilmez:
        HSD Trend Algoritması
        HSD Momentum Algoritması

    Böylece farklı yöntemleri fuzzy similarity ile yanlışlıkla birleştirmeyiz.
    """
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in registry_rows:
        name = (
            clean_text(row["canonical_name"])
            or clean_text(row["registry_name"])
            or f"Registry Method #{row['registry_id']}"
        )

        key = safe_canonical_key(name)

        if not key:
            key = f"registry:{int(row['registry_id'])}"

        groups[key].append(row)

    return groups


def representative_registry_row(
    group: list[sqlite3.Row],
) -> sqlite3.Row:
    """
    Canonical grubun görünen adını seçmek için en dolu/temiz kaydı seç.
    Registry ID korunur.
    """
    ordered = sorted(
        group,
        key=lambda row: (
            -len(
                clean_text(
                    row["canonical_name"]
                )
            ),
            -len(
                clean_text(
                    row["registry_name"]
                )
            ),
            int(
                row["registry_id"]
            ),
        ),
    )

    return ordered[0]


def match_registry(
    registry_row: sqlite3.Row,
    by_registry_id: dict[int, list[sqlite3.Row]],
    by_alias: dict[str, list[sqlite3.Row]],
) -> tuple[list[sqlite3.Row], str]:
    registry_id = int(
        registry_row["registry_id"]
    )

    # 1. Exact registry_id: en güvenli eşleşme.
    direct = unique_rows(
        by_registry_id.get(
            registry_id,
            [],
        )
    )

    if direct:
        return direct, "registry_id"

    # 2. Safe canonical name match.
    candidates: list[sqlite3.Row] = []

    for key in registry_alias_keys(
        registry_row
    ):
        candidates.extend(
            by_alias.get(
                key,
                [],
            )
        )

    candidates = unique_rows(
        candidates
    )

    if candidates:
        return candidates, "safe_canonical_key"

    # 3. Bilinçli olarak fuzzy match yapılmıyor.
    return [], "unmatched"


# ============================================================================
# CONSOLIDATED RECORD
# ============================================================================


@dataclass
class ConsolidatedMethod:
    registry_id: int
    registry_ids: list[int]

    method_name: str
    canonical_key: str
    category: str

    objective: str | None

    inputs: list[str]
    parameters: dict[str, Any]

    signal_rules: list[str]
    entry_rules: list[str]
    exit_rules: list[str]
    filters: list[str]

    timeframe: str | None
    market_scope: list[str]
    risk_rules: list[str]

    confidence: float
    completeness: float
    computability: str

    evidence_state: str
    evidence_notes: list[str]

    gate_status: str

    linked_knowledge_ids: list[str]
    linked_source_ids: list[str]

    primary_specification_id: int | None
    variant_specification_ids: list[int]

    consolidation_method: str
    consolidation_notes: list[str]

    updated_at: str


def build_consolidated_method(
    registry_row: sqlite3.Row,
    registry_group: list[sqlite3.Row],
    matched_specs: list[sqlite3.Row],
    match_method: str,
    gate_statuses: dict[int, str],
) -> ConsolidatedMethod:
    registry_id = min(
        int(row["registry_id"])
        for row in registry_group
    )

    registry_ids = sorted(
        {
            int(row["registry_id"])
            for row in registry_group
        }
    )

    if not matched_specs:
        method_name = (
            clean_text(
                registry_row["canonical_name"]
            )
            or clean_text(
                registry_row["registry_name"]
            )
            or f"Registry Method #{registry_id}"
        )

        category = (
            clean_text(
                registry_row["registry_category"]
            )
            or "other"
        )

        return ConsolidatedMethod(
            registry_id=registry_id,
            registry_ids=registry_ids,
            method_name=method_name,
            canonical_key=safe_canonical_key(
                method_name
            ),
            category=category,
            objective=None,
            inputs=[],
            parameters={},
            signal_rules=[],
            entry_rules=[],
            exit_rules=[],
            filters=[],
            timeframe=None,
            market_scope=[],
            risk_rules=[],
            confidence=0.0,
            completeness=0.0,
            computability="reference_only",
            evidence_state="registry_only",
            evidence_notes=[
                "Registry kaydı için specification eşleşmesi bulunamadı.",
            ],
            gate_status="REFERENCE_ONLY",
            linked_knowledge_ids=[],
            linked_source_ids=[],
            primary_specification_id=None,
            variant_specification_ids=[],
            consolidation_method=match_method,
            consolidation_notes=[
                "Fuzzy matching kullanılmadı.",
                "Yeni kanıt varsayılmadı.",
            ],
            updated_at=now_iso(),
        )

    ordered = sorted(
        matched_specs,
        key=primary_sort_key,
    )

    primary = ordered[0]
    variants = ordered[1:]

    all_knowledge = merge_json_lists(
        ordered,
        "linked_knowledge_ids_json",
    )

    all_sources = merge_json_lists(
        ordered,
        "linked_source_ids_json",
    )

    gate_status = (
        gate_statuses.get(
            int(
                primary["method_id"]
            ),
            "UNASSESSED",
        )
    )

    # Quality Gate V1'in eski method_id'leri specification id'si,
    # V3'ün method_id'si ise registry_id idi. Bu yüzden status bulunmazsa
    # canonical yöntem adına göre başka bir doğrudan eşleme yapılmaz.
    if gate_status == "DUPLICATE_VARIANT":
        gate_status = "PARTIAL"

    evidence_states = [
        clean_text(
            row["evidence_state"]
        )
        for row in ordered
        if clean_text(
            row["evidence_state"]
        )
    ]

    if "linked_source" in evidence_states:
        evidence_state = "linked_source"
    elif "knowledge_only" in evidence_states:
        evidence_state = "knowledge_only"
    elif evidence_states:
        evidence_state = evidence_states[0]
    else:
        evidence_state = "unknown"

    evidence_notes = merge_json_lists(
        ordered,
        "evidence_notes_json",
    )

    consolidation_notes = [
        f"{len(matched_specs)} specification kaydı tek registry yönteminde toplandı.",
        f"Primary specification: {int(primary['method_id'])}.",
        f"Variant specification count: {len(variants)}.",
        f"Eşleşme yöntemi: {match_method}.",
        "Fuzzy similarity ile farklı yöntem birleştirilmedi.",
    ]

    return ConsolidatedMethod(
        registry_id=registry_id,
        registry_ids=registry_ids,

        method_name=(
            clean_text(
                registry_row["canonical_name"]
            )
            or clean_text(
                registry_row["registry_name"]
            )
            or clean_text(
                primary["method_name"]
            )
        ),

        canonical_key=safe_canonical_key(
            (
                clean_text(
                    registry_row["canonical_name"]
                )
                or clean_text(
                    registry_row["registry_name"]
                )
            ),
            clean_text(
                primary["canonical_key"]
            ),
        ),

        category=(
            clean_text(
                registry_row["registry_category"]
            )
            or clean_text(
                primary["category"]
            )
            or "other"
        ),

        objective=clean_text(
            merge_scalar(
                ordered,
                "objective",
            )
        ) or None,

        inputs=unique_strings(
            merge_json_lists(
                ordered,
                "inputs_json",
            )
        ),

        parameters=merge_parameters(
            ordered
        ),

        signal_rules=unique_strings(
            merge_json_lists(
                ordered,
                "signal_rules_json",
            )
        ),

        entry_rules=unique_strings(
            merge_json_lists(
                ordered,
                "entry_rules_json",
            )
        ),

        exit_rules=unique_strings(
            merge_json_lists(
                ordered,
                "exit_rules_json",
            )
        ),

        filters=unique_strings(
            merge_json_lists(
                ordered,
                "filters_json",
            )
        ),

        timeframe=(
            clean_text(
                merge_scalar(
                    ordered,
                    "timeframe",
                )
            )
            or None
        ),

        market_scope=unique_strings(
            merge_json_lists(
                ordered,
                "market_scope_json",
            )
        ),

        risk_rules=unique_strings(
            merge_json_lists(
                ordered,
                "risk_rules_json",
            )
        ),

        confidence=round(
            max(
                safe_float(
                    primary["confidence"]
                ),
                min(
                    100.0,
                    max(
                        (
                            safe_float(
                                row["confidence"]
                            )
                            for row in ordered
                        ),
                        default=0.0,
                    ),
                ),
            ),
            1,
        ),

        completeness=round(
            max(
                (
                    safe_float(
                        row["completeness"]
                    )
                    for row in ordered
                ),
                default=0.0,
            ),
            1,
        ),

        computability=clean_text(
            primary["computability"]
        ) or "reference_only",

        evidence_state=evidence_state,
        evidence_notes=evidence_notes,

        gate_status=gate_status,

        linked_knowledge_ids=all_knowledge,
        linked_source_ids=all_sources,

        primary_specification_id=int(
            primary["method_id"]
        ),

        variant_specification_ids=[
            int(
                row["method_id"]
            )
            for row in variants
        ],

        consolidation_method=match_method,
        consolidation_notes=consolidation_notes,

        updated_at=now_iso(),
    )


# ============================================================================
# SAVE
# ============================================================================


def save_consolidated(
    conn: sqlite3.Connection,
    item: ConsolidatedMethod,
) -> None:
    payload = asdict(
        item
    )

    conn.execute(
        """
        INSERT INTO method_specification_consolidated (
            registry_id,

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

            confidence,
            completeness,
            computability,

            evidence_state,
            evidence_notes_json,

            gate_status,

            linked_knowledge_ids_json,
            linked_source_ids_json,

            primary_specification_id,

            variant_specification_ids_json,

            consolidation_method,
            consolidation_notes_json,

            updated_at
        )
        VALUES (
            ?,
            ?, ?, ?,
            ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        ON CONFLICT(registry_id)
        DO UPDATE SET
            method_name = excluded.method_name,
            canonical_key = excluded.canonical_key,
            category = excluded.category,

            objective = excluded.objective,

            inputs_json = excluded.inputs_json,
            parameters_json = excluded.parameters_json,
            signal_rules_json = excluded.signal_rules_json,
            entry_rules_json = excluded.entry_rules_json,
            exit_rules_json = excluded.exit_rules_json,
            filters_json = excluded.filters_json,

            timeframe = excluded.timeframe,
            market_scope_json = excluded.market_scope_json,
            risk_rules_json = excluded.risk_rules_json,

            confidence = excluded.confidence,
            completeness = excluded.completeness,
            computability = excluded.computability,

            evidence_state = excluded.evidence_state,
            evidence_notes_json = excluded.evidence_notes_json,

            gate_status = excluded.gate_status,

            linked_knowledge_ids_json =
                excluded.linked_knowledge_ids_json,

            linked_source_ids_json =
                excluded.linked_source_ids_json,

            primary_specification_id =
                excluded.primary_specification_id,

            variant_specification_ids_json =
                excluded.variant_specification_ids_json,

            consolidation_method =
                excluded.consolidation_method,

            consolidation_notes_json =
                excluded.consolidation_notes_json,

            updated_at =
                excluded.updated_at
        """,
        (
            payload["registry_id"],

            payload["method_name"],
            payload["canonical_key"],
            payload["category"],

            payload["objective"],

            json.dumps(
                payload["inputs"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["parameters"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["signal_rules"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["entry_rules"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["exit_rules"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["filters"],
                ensure_ascii=False,
            ),

            payload["timeframe"],

            json.dumps(
                payload["market_scope"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["risk_rules"],
                ensure_ascii=False,
            ),

            payload["confidence"],
            payload["completeness"],
            payload["computability"],

            payload["evidence_state"],

            json.dumps(
                payload["evidence_notes"],
                ensure_ascii=False,
            ),

            payload["gate_status"],

            json.dumps(
                payload["linked_knowledge_ids"],
                ensure_ascii=False,
            ),

            json.dumps(
                payload["linked_source_ids"],
                ensure_ascii=False,
            ),

            payload["primary_specification_id"],

            json.dumps(
                payload["variant_specification_ids"],
                ensure_ascii=False,
            ),

            payload["consolidation_method"],

            json.dumps(
                payload["consolidation_notes"],
                ensure_ascii=False,
            ),

            payload["updated_at"],
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
# REPORT
# ============================================================================


def make_payload(
    items: list[ConsolidatedMethod],
    registry_count: int,
    specification_count: int,
    unmatched_registry_ids: list[int],
    match_method_counts: Counter[str],
) -> dict[str, Any]:
    computability = Counter(
        item.computability
        for item in items
    )

    gate_status = Counter(
        item.gate_status
        for item in items
    )

    evidence = Counter(
        item.evidence_state
        for item in items
    )

    category = Counter(
        item.category
        for item in items
    )

    variant_counts = [
        len(
            item.variant_specification_ids
        )
        for item in items
    ]

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "generated_at": now_iso(),

        "database": str(
            DB_PATH
        ),

        "registry_count": registry_count,
        "source_specification_count": specification_count,
        "consolidated_method_count": len(
            items
        ),

        "expected_consolidated_count": registry_count,
        "canonical_registry_group_count": len(items),

        "coverage": round(
            (
                len(items)
                / registry_count
                * 100.0
            )
            if registry_count
            else 0.0,
            1,
        ),

        "unmatched_registry_count": len(
            unmatched_registry_ids
        ),

        "unmatched_registry_ids":
            unmatched_registry_ids,

        "match_methods":
            dict(match_method_counts),

        "computability":
            dict(computability),

        "gate_status":
            dict(gate_status),

        "evidence_state":
            dict(evidence),

        "categories":
            dict(category),

        "duplicate_variant_records":
            sum(
                count
                for count in variant_counts
            ),

        "methods_with_variants":
            sum(
                1
                for count in variant_counts
                if count > 0
            ),

        "average_variant_count":
            round(
                sum(variant_counts)
                / len(variant_counts),
                2,
            )
            if variant_counts
            else 0.0,

        "average_confidence":
            round(
                sum(
                    item.confidence
                    for item in items
                )
                / len(items),
                1,
            )
            if items
            else 0.0,

        "average_completeness":
            round(
                sum(
                    item.completeness
                    for item in items
                )
                / len(items),
                1,
            )
            if items
            else 0.0,

        "methods": [
            asdict(item)
            for item in items
        ],
    }


# ============================================================================
# MAIN
# ============================================================================


def run() -> dict[str, Any]:
    conn = connect()

    try:
        ensure_source_tables(
            conn
        )

        ensure_consolidated_schema(
            conn
        )

        registry_rows = load_registry(
            conn
        )

        specification_rows = load_specifications(
            conn
        )

        gate_statuses = load_gate_statuses(
            conn
        )

        by_registry_id = index_specs_by_registry_id(
            specification_rows
        )

        by_alias = index_specs_by_alias(
            specification_rows
        )

        # Önce registry'yi güvenli canonical gruplara ayır.
        registry_groups = build_registry_groups(
            registry_rows
        )

        consolidated: list[ConsolidatedMethod] = []
        unmatched: list[int] = []

        match_method_counts = Counter()

        for group_key, registry_group in registry_groups.items():
            # Grup içindeki tüm registry ID'lerinin specification kayıtlarını
            # topla. Böylece aynı yöntemin farklı registry kayıtları tek
            # canonical method altında birleşir.
            matched: list[sqlite3.Row] = []

            group_match_methods: set[str] = set()

            for registry_row in registry_group:
                row_matches, method = match_registry(
                    registry_row,
                    by_registry_id,
                    by_alias,
                )

                matched.extend(
                    row_matches
                )
                group_match_methods.add(
                    method
                )

                if method == "unmatched":
                    unmatched.append(
                        int(
                            registry_row["registry_id"]
                        )
                    )

            matched = unique_rows(
                matched
            )

            if (
                "registry_id"
                in group_match_methods
            ):
                match_method = "registry_id"
            elif (
                "safe_canonical_key"
                in group_match_methods
            ):
                match_method = "safe_canonical_key"
            else:
                match_method = "unmatched"

            match_method_counts[
                match_method
            ] += 1

            representative = representative_registry_row(
                registry_group
            )

            item = build_consolidated_method(
                representative,
                registry_group,
                matched,
                match_method,
                gate_statuses,
            )

            save_consolidated(
                conn,
                item,
            )

            consolidated.append(
                item
            )

        conn.commit()

        # UNIQUE registry_id nedeniyle önceki V2 kayıtlarından kalan,
        # artık canonical primary olmayan satırları temizlemeden bırakmak
        # yerine sadece V3'ün canonical setini ayrı bir tabloya yazıyoruz.
        payload = make_payload(
            consolidated,
            registry_count=len(
                registry_rows
            ),
            specification_count=len(
                specification_rows
            ),
            unmatched_registry_ids=sorted(
                set(unmatched)
            ),
            match_method_counts=match_method_counts,
        )

        payload["registry_canonical_group_count"] = len(
            registry_groups
        )

        payload["registry_records_collapsed"] = (
            len(registry_rows)
            - len(registry_groups)
        )

        payload["status"] = (
            "completed"
            if not unmatched
            else "completed_with_unmatched"
        )

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
    print("=" * 82)
    print(
        "FIN[SYS] METHOD SPECIFICATION CONSOLIDATOR V2"
    )
    print("=" * 82)

    print(
        f"Registry: {payload['registry_count']}"
    )

    print(
        f"Source specifications: "
        f"{payload['source_specification_count']}"
    )

    print(
        f"Consolidated canonical methods: "
        f"{payload['consolidated_method_count']}"
    )

    print(
        f"Registry records collapsed: "
        f"{payload.get('registry_records_collapsed', 0)}"
    )

    print(
        f"Coverage: "
        f"{payload['coverage']}%"
    )

    print()

    print("MATCHING")
    print("-" * 82)

    for key, value in sorted(
        payload["match_methods"].items()
    ):
        print(
            f"{key}: {value}"
        )

    print(
        f"Unmatched registry: "
        f"{payload['unmatched_registry_count']}"
    )

    print()

    print("COMPUTABILITY")
    print("-" * 82)

    for key, value in sorted(
        payload["computability"].items()
    ):
        print(
            f"{key}: {value}"
        )

    print()

    print("QUALITY GATE")
    print("-" * 82)

    for key, value in sorted(
        payload["gate_status"].items()
    ):
        print(
            f"{key}: {value}"
        )

    print()

    print("DUPLICATES / VARIANTS")
    print("-" * 82)

    print(
        "Methods with variants: "
        f"{payload['methods_with_variants']}"
    )

    print(
        "Variant records: "
        f"{payload['duplicate_variant_records']}"
    )

    print(
        "Average variants per method: "
        f"{payload['average_variant_count']}"
    )

    print()

    print("AVERAGES")
    print("-" * 82)

    print(
        "Average confidence: "
        f"{payload['average_confidence']}"
    )

    print(
        "Average completeness: "
        f"{payload['average_completeness']}"
    )

    print()

    print("TOP METHODS FOR PANEL")
    print("-" * 82)

    ranked = sorted(
        payload["methods"],
        key=lambda item: (
            -item["completeness"],
            -item["confidence"],
        ),
    )

    for index, item in enumerate(
        ranked[:25],
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{item['method_name'][:62]} | "
            f"{item['computability']} | "
            f"C={item['completeness']:.1f} | "
            f"Conf={item['confidence']:.1f} | "
            f"Variants={len(item['variant_specification_ids'])}"
        )

    print()

    if payload[
        "unmatched_registry_count"
    ]:
        print("UNMATCHED IDS")
        print("-" * 82)

        print(
            ", ".join(
                str(value)
                for value in payload[
                    "unmatched_registry_ids"
                ][:100]
            )
        )

        print()

    print(
        f"JSON output: {OUTPUT_PATH}"
    )

    print(
        "✅ Method Specification Consolidator V1 tamamlandı."
    )


def main() -> None:
    payload = run()
    print_summary(
        payload
    )


if __name__ == "__main__":
    main()

