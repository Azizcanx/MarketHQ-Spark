# -*- coding: utf-8 -*-
"""
MarketHQ Research Observation Bridge Diagnostic V1
--------------------------------------------------
Bridge V1/V2 neden canonical item 502/503'ü görmüyor?

BU DOSYA SALT OKUNUR.
- INSERT yapmaz
- UPDATE yapmaz
- DELETE yapmaz
- queue değiştirmez
- observation değiştirmez
- knowledge değiştirmez
- API çağrısı yapmaz

Kontrol eder:
    1) knowledge_items içindeki tüm research_result kayıtları
    2) metadata_json parse sonucu
    3) lifecycle_state
    4) brain_episode_id
    5) task_type
    6) context
    7) item 500/501/502/503 özel kontrolü
    8) Bridge V1/V2 filtresine benzer sayımlar
    9) JSON1 destek / json_extract sonucu
    10) link tablosu mevcut bağlantıları

Çalıştırma:
    python agents/brain_research_observation_bridge_diagnostic_v1.py
"""

from __future__ import annotations

import json
import sqlite3
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def si(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sf(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_json(raw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(norm(raw) or "{}")
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database bulunamadı: {DB_PATH}"
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


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def main() -> None:
    conn = open_db()

    try:
        print("=" * 78)
        print(
            "MARKETHQ RESEARCH OBSERVATION BRIDGE DIAGNOSTIC V1"
        )
        print("=" * 78)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            "MODE     : READ ONLY"
        )
        print()

        for table in (
            "knowledge_items",
            "brain_observations",
        ):
            print(
                f"{table:35s} "
                + (
                    "EXISTS"
                    if table_exists(
                        conn,
                        table,
                    )
                    else "MISSING"
                )
            )

        print()
        print("RESEARCH RESULT ITEMS")
        print("-" * 78)

        rows = conn.execute(
            """
            SELECT
                id,
                source_id,
                title,
                method,
                confidence,
                metadata_json,
                tags_json
            FROM knowledge_items
            WHERE item_type='research_result'
            ORDER BY id ASC
            """
        ).fetchall()

        print(
            f"total research_result rows = {len(rows)}"
        )
        print()

        canonical_python = 0
        canonical_sql = 0
        state_counts: dict[str, int] = {}
        task_counts: dict[str, int] = {}

        for row in rows:
            metadata = parse_json(
                row["metadata_json"]
            )

            state = norm(
                metadata.get(
                    "lifecycle_state"
                )
            )

            state_lower = state.lower()

            task_type = norm(
                metadata.get(
                    "task_type"
                )
            )

            context = metadata.get(
                "context",
                {},
            )

            if not isinstance(
                context,
                dict,
            ):
                context = {}

            symbol = norm(
                context.get("symbol")
            )

            method_name = norm(
                context.get(
                    "method_name"
                )
            ) or norm(
                row["method"]
            )

            episode_id = si(
                metadata.get(
                    "brain_episode_id"
                )
            )

            if state_lower == "canonical":
                canonical_python += 1

            state_counts[state or "<EMPTY>"] = (
                state_counts.get(
                    state or "<EMPTY>",
                    0,
                )
                + 1
            )

            task_counts[task_type or "<EMPTY>"] = (
                task_counts.get(
                    task_type or "<EMPTY>",
                    0,
                )
                + 1
            )

            print(
                f"item={si(row['id']):4d} | "
                f"episode={episode_id:4d} | "
                f"state={state or '<EMPTY>':12s} | "
                f"task_type={task_type or '<EMPTY>':28s} | "
                f"symbol={symbol or '<EMPTY>':10s}"
            )
            print(
                "  title="
                + norm(row["title"])
            )
            print(
                "  method="
                + method_name
            )
            print(
                "  context="
                + json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        print()
        print("PYTHON-SIDE STATE COUNTS")
        print("-" * 78)

        for key, value in sorted(
            state_counts.items()
        ):
            print(
                f"{key:35s} {value}"
            )

        print()
        print("PYTHON-SIDE TASK TYPE COUNTS")
        print("-" * 78)

        for key, value in sorted(
            task_counts.items()
        ):
            print(
                f"{key:35s} {value}"
            )

        print()
        print(
            "canonical_by_python = "
            f"{canonical_python}"
        )

        print()
        print("SQL JSON1 TEST")
        print("-" * 78)

        try:
            sql_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS n
                FROM knowledge_items
                WHERE
                    item_type='research_result'
                    AND json_extract(
                        metadata_json,
                        '$.lifecycle_state'
                    )='canonical'
                """
            ).fetchone()

            canonical_sql = si(
                sql_row["n"]
            )

            print(
                "json_extract canonical count = "
                f"{canonical_sql}"
            )

        except Exception as exc:
            print(
                "json_extract ERROR = "
                f"{type(exc).__name__}: {exc}"
            )

        print()
        print("SPECIAL ITEMS 498-503")
        print("-" * 78)

        special = conn.execute(
            """
            SELECT
                id,
                source_id,
                title,
                method,
                confidence,
                metadata_json,
                tags_json
            FROM knowledge_items
            WHERE
                item_type='research_result'
                AND id BETWEEN 498 AND 503
            ORDER BY id
            """
        ).fetchall()

        if not special:
            print(
                "No items 498-503 found."
            )

        for row in special:
            metadata = parse_json(
                row["metadata_json"]
            )

            context = metadata.get(
                "context",
                {},
            )

            print()
            print(
                f"ITEM {si(row['id'])}"
            )
            print(
                f"source_id        = {si(row['source_id'])}"
            )
            print(
                f"title            = {norm(row['title'])}"
            )
            print(
                f"state            = "
                f"{metadata.get('lifecycle_state')!r}"
            )
            print(
                f"task_type        = "
                f"{metadata.get('task_type')!r}"
            )
            print(
                f"brain_episode_id = "
                f"{metadata.get('brain_episode_id')!r}"
            )
            print(
                f"queue_id         = "
                f"{metadata.get('queue_id')!r}"
            )
            print(
                f"claim_id         = "
                f"{metadata.get('claim_id')!r}"
            )
            print(
                f"rule_id          = "
                f"{metadata.get('learned_rule_id')!r}"
            )
            print(
                f"validation_id    = "
                f"{metadata.get('validation_id')!r}"
            )
            print(
                "context          = "
                + json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            print(
                "tags             = "
                + norm(row["tags_json"])
            )

        print()
        print("BRIDGE TABLE")
        print("-" * 78)

        if not table_exists(
            conn,
            "brain_research_observation_links",
        ):
            print(
                "brain_research_observation_links MISSING"
            )
        else:
            bridge_rows = conn.execute(
                """
                SELECT
                    id,
                    knowledge_item_id,
                    observation_id,
                    relation,
                    match_type,
                    match_score,
                    evidence_role,
                    verified
                FROM brain_research_observation_links
                ORDER BY id ASC
                """
            ).fetchall()

            print(
                "total bridge links = "
                f"{len(bridge_rows)}"
            )

            for row in bridge_rows:
                print(
                    f"link={si(row['id'])} | "
                    f"knowledge={si(row['knowledge_item_id'])} | "
                    f"observation={si(row['observation_id'])} | "
                    f"relation={norm(row['relation'])} | "
                    f"match={norm(row['match_type'])} | "
                    f"score={sf(row['match_score']):.2f} | "
                    f"verified={si(row['verified'])}"
                )

        print()
        print("BRIDGE-LIKE PYTHON FILTER TEST")
        print("-" * 78)

        python_canonical_rows = [
            row
            for row in rows
            if norm(
                parse_json(
                    row["metadata_json"]
                ).get(
                    "lifecycle_state"
                )
            ).lower()
            == "canonical"
        ]

        print(
            "python canonical rows = "
            f"{len(python_canonical_rows)}"
        )

        if python_canonical_rows:
            for row in python_canonical_rows:
                metadata = parse_json(
                    row["metadata_json"]
                )

                context = metadata.get(
                    "context",
                    {},
                )

                if not isinstance(
                    context,
                    dict,
                ):
                    context = {}

                print(
                    f"candidate item={si(row['id'])} | "
                    f"symbol={norm(context.get('symbol'))} | "
                    f"method={norm(context.get('method_name')) or norm(row['method'])} | "
                    f"task={norm(metadata.get('task_type'))}"
                )

        print()
        print("DIAGNOSTIC CONCLUSION")
        print("-" * 78)

        if canonical_python != canonical_sql:
            print(
                "JSON FILTER MISMATCH: "
                "Python ve SQLite canonical sayıları farklı."
            )
        else:
            print(
                "Python/SQLite canonical count aynı."
            )

        if canonical_python == 4:
            print(
                "Beklenen 4 canonical item bulundu."
            )
        elif canonical_python == 2:
            print(
                "Sadece 2 canonical item görülüyor; "
                "502/503 metadata/state incelenmeli."
            )
        else:
            print(
                "Canonical item sayısı beklenenden farklı."
            )

        print()
        print("=" * 78)
        print(
            "NO DATA WAS MODIFIED"
        )
        print("=" * 78)

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print(
            "FATAL | "
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc()

