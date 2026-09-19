# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Knowledge Canonical Repair Engine V2
-------------------------------------------------------------
Research-derived knowledge_items canonical state repair.

V2 NEDEN GEREKLİ?
-----------------
Diagnostic sonucu:
    total research_result rows = 6
    canonical                  = 2
    superseded                 = 2
    lifecycle_state EMPTY      = 2

Bu iki EMPTY kayıt yeni Research Agent episode'larıdır:
    episode 502 -> TOASO
    episode 503 -> ASELS

Ama lifecycle_state metadata'ları yazılmamış/eksik kalmış.

V2:
    - Tüm research_result kayıtlarını okur.
    - episode_id'yi metadata veya title'dan çözer.
    - Aynı episode içindeki kayıtları gruplar.
    - Halihazırda superseded olanı canonical yapmaz.
    - Canonical adayını şu sırayla seçer:
        1) mevcut canonical
        2) spesifik task_type
        3) en büyük item id
    - EMPTY kayıtları canonical metadata ile tamamlar.
    - Canonical kayıtları da metadata açısından normalize eder.
    - Hiçbir item silinmez.
    - Superseded kayıtlar korunur.
    - Ham experiment/result, learned_rules, claims,
      validations ve observations değiştirilmez.

Çalıştırma:
    python agents/brain_research_knowledge_repair_v2.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_KNOWLEDGE_REPAIR"
ENGINE_VERSION = "V2"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_json(
    raw: Any,
) -> dict[str, Any]:
    try:
        obj = json.loads(
            norm(raw) or "{}"
        )
        return (
            obj
            if isinstance(obj, dict)
            else {}
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ):
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


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_items(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                id,
                source_id,
                item_type,
                title,
                method,
                tags_json,
                metadata_json,
                created_at
            FROM knowledge_items
            WHERE item_type='research_result'
            ORDER BY id ASC
            """
        ).fetchall()
    )


def metadata(
    row: sqlite3.Row,
) -> dict[str, Any]:
    return parse_json(
        row["metadata_json"]
    )


def lifecycle_state(
    row: sqlite3.Row,
) -> str:
    return norm(
        metadata(row).get(
            "lifecycle_state"
        )
    ).lower()


def task_type(
    row: sqlite3.Row,
) -> str:
    meta = metadata(
        row
    )

    direct = norm(
        meta.get("task_type")
    ).upper()

    if direct:
        return direct

    context = meta.get(
        "context",
        {},
    )

    if isinstance(
        context,
        dict,
    ):
        nested = norm(
            context.get("task_type")
        ).upper()

        if nested:
            return nested

    title = norm(
        row["title"]
    ).upper()

    for value in (
        "WEAK_HOLDOUT_REVIEW",
        "VALIDATED_RULE_RECHECK",
        "INSUFFICIENT_DATA_RESEARCH",
        "METHOD_VARIANT_COMPARISON",
    ):
        if value in title:
            return value

    return "RESEARCH"


def episode_id(
    row: sqlite3.Row,
) -> int | None:
    meta = metadata(
        row
    )

    for key in (
        "brain_episode_id",
        "episode_id",
    ):
        value = safe_int(
            meta.get(key),
            0,
        )
        if value > 0:
            return value

    title = norm(
        row["title"]
    )

    match = re.search(
        r"episode\s*=\s*(\d+)",
        title,
        flags=re.IGNORECASE,
    )

    if match:
        value = safe_int(
            match.group(1),
            0,
        )
        if value > 0:
            return value

    return None


def context(
    row: sqlite3.Row,
) -> dict[str, Any]:
    meta = metadata(
        row
    )

    raw = meta.get(
        "context",
        {},
    )

    if isinstance(
        raw,
        dict,
    ):
        return raw

    return {}


def has_specific_task(
    row: sqlite3.Row,
) -> bool:
    return task_type(
        row
    ) not in {
        "",
        "RESEARCH",
        "UNKNOWN",
        "NONE",
    }


# ---------------------------------------------------------------------------
# TAGS
# ---------------------------------------------------------------------------

def parse_tags(
    raw: Any,
) -> set[str]:
    try:
        values = json.loads(
            norm(raw) or "[]"
        )

        if not isinstance(
            values,
            list,
        ):
            return set()

        return {
            norm(value)
            for value in values
            if norm(value)
        }

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return set()


# ---------------------------------------------------------------------------
# CANONICAL CHOICE
# ---------------------------------------------------------------------------

def choose_canonical(
    members: list[sqlite3.Row],
) -> sqlite3.Row:
    """
    Priority:
        1) already canonical
        2) specific task type
        3) latest item id
    """

    canonical_members = [
        row
        for row in members
        if lifecycle_state(row)
        == "canonical"
    ]

    if canonical_members:
        return max(
            canonical_members,
            key=lambda row: safe_int(
                row["id"]
            ),
        )

    return max(
        members,
        key=lambda row: (
            1
            if has_specific_task(row)
            else 0,
            safe_int(
                row["id"]
            ),
        ),
    )


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------

def normalize_canonical(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    previous_ids: list[int],
) -> None:
    meta = metadata(
        row
    )

    meta["lifecycle_state"] = "canonical"

    existing_history = meta.get(
        "duplicate_history",
        {},
    )

    if not isinstance(
        existing_history,
        dict,
    ):
        existing_history = {}

    existing_history.update(
        {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "action": "canonical_normalized",
            "reviewed": True,
            "reviewed_at": utc_now(),
            "previous_item_ids": sorted(
                previous_ids
            ),
            "reason": (
                "canonical research_result selected "
                "by episode-level provenance repair"
            ),
        }
    )

    meta["duplicate_history"] = (
        existing_history
    )

    tags = parse_tags(
        row["tags_json"]
    )

    tags.discard(
        "superseded"
    )
    tags.discard(
        "historical_duplicate"
    )

    tags.add(
        "research_agent"
    )
    tags.add(
        "research_derived"
    )
    tags.add(
        "not_verified"
    )

    resolved_task_type = task_type(
        row
    )

    if resolved_task_type:
        tags.add(
            resolved_task_type
        )

    conn.execute(
        """
        UPDATE knowledge_items
        SET
            tags_json=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            compact_json(
                sorted(tags)
            ),
            compact_json(
                meta
            ),
            safe_int(
                row["id"]
            ),
        ),
    )


def normalize_superseded(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    canonical_id: int,
) -> None:
    meta = metadata(
        row
    )

    meta["lifecycle_state"] = "superseded"

    meta["duplicate_history"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "superseded",
        "reviewed": True,
        "reviewed_at": utc_now(),
        "superseded_by_item_id": canonical_id,
        "reason": (
            "another research_result for the same episode "
            "is the canonical item"
        ),
    }

    tags = parse_tags(
        row["tags_json"]
    )

    tags.add(
        "superseded"
    )
    tags.add(
        "historical_duplicate"
    )

    conn.execute(
        """
        UPDATE knowledge_items
        SET
            tags_json=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            compact_json(
                sorted(tags)
            ),
            compact_json(
                meta
            ),
            safe_int(
                row["id"]
            ),
        ),
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        if not table_exists(
            conn,
            "knowledge_items",
        ):
            raise RuntimeError(
                "knowledge_items tablosu bulunamadı."
            )

        rows = load_items(
            conn
        )

        groups: dict[int, list[sqlite3.Row]] = {}
        ungrouped = 0

        for row in rows:
            ep = episode_id(
                row
            )

            if ep is None:
                ungrouped += 1
                continue

            groups.setdefault(
                ep,
                [],
            ).append(row)

        groups_seen = len(
            groups
        )

        canonicalized = 0
        already_canonical = 0
        superseded = 0
        empty_state_fixed = 0
        duplicate_groups = 0
        errors = 0

        for ep, members in sorted(
            groups.items()
        ):
            try:
                canonical = choose_canonical(
                    members
                )

                canonical_id = safe_int(
                    canonical["id"]
                )

                previous_ids = [
                    safe_int(row["id"])
                    for row in members
                    if safe_int(row["id"])
                    != canonical_id
                ]

                old_state = lifecycle_state(
                    canonical
                )

                normalize_canonical(
                    conn,
                    canonical,
                    previous_ids,
                )

                canonicalized += 1

                if old_state == "canonical":
                    already_canonical += 1

                if old_state in {
                    "",
                    "unknown",
                    "none",
                }:
                    empty_state_fixed += 1

                if len(members) > 1:
                    duplicate_groups += 1

                    for member in members:
                        member_id = safe_int(
                            member["id"]
                        )

                        if member_id == canonical_id:
                            continue

                        # Zaten superseded olan kayıtları da metadata
                        # açısından canonical hedefe bağla.
                        normalize_superseded(
                            conn,
                            member,
                            canonical_id,
                        )

                        superseded += 1

                print(
                    f"REPAIRED | "
                    f"episode={ep} | "
                    f"canonical={canonical_id} | "
                    f"task={task_type(canonical)} | "
                    f"previous={previous_ids}"
                )

                conn.commit()

            except Exception as exc:
                errors += 1
                conn.rollback()

                print(
                    f"ERROR | "
                    f"episode={ep} | "
                    f"{type(exc).__name__}: {exc}"
                )

        # Final deterministic state profile.
        state_rows = conn.execute(
            """
            SELECT
                metadata_json
            FROM knowledge_items
            WHERE item_type='research_result'
            """
        ).fetchall()

        final_states: dict[str, int] = {}

        for row in state_rows:
            state = norm(
                parse_json(
                    row["metadata_json"]
                ).get(
                    "lifecycle_state"
                )
            ) or "<EMPTY>"

            final_states[state] = (
                final_states.get(
                    state,
                    0,
                )
                + 1
            )

        print()
        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH KNOWLEDGE REPAIR ENGINE V2"
        )
        print("=" * 76)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            f"Engine   : {ENGINE_NAME}"
        )
        print(
            f"Version  : {ENGINE_VERSION}"
        )
        print()
        print("REPAIR V2 RUN")
        print("-" * 76)
        print(
            f"research_result_items_seen             {len(rows)}"
        )
        print(
            f"episode_groups_seen                     {groups_seen}"
        )
        print(
            f"duplicate_episode_groups                {duplicate_groups}"
        )
        print(
            f"canonicalized                           {canonicalized}"
        )
        print(
            f"already_canonical                       {already_canonical}"
        )
        print(
            f"empty_state_fixed                       {empty_state_fixed}"
        )
        print(
            f"superseded_normalized                   {superseded}"
        )
        print(
            f"ungrouped_items                         {ungrouped}"
        )
        print(
            f"errors                                  {errors}"
        )

        print()
        print("FINAL LIFECYCLE STATES")
        print("-" * 76)

        for state, count in sorted(
            final_states.items()
        ):
            print(
                f"{state:35s} {count}"
            )

        print()
        print("SPECIAL ITEMS 500-503")
        print("-" * 76)

        special = conn.execute(
            """
            SELECT
                id,
                title,
                metadata_json
            FROM knowledge_items
            WHERE
                item_type='research_result'
                AND id BETWEEN 500 AND 503
            ORDER BY id
            """
        ).fetchall()

        for row in special:
            meta = parse_json(
                row["metadata_json"]
            )

            context_data = meta.get(
                "context",
                {},
            )

            if not isinstance(
                context_data,
                dict,
            ):
                context_data = {}

            print(
                f"item={safe_int(row['id'])} | "
                f"episode={meta.get('brain_episode_id')} | "
                f"state={meta.get('lifecycle_state')} | "
                f"task={meta.get('task_type')}"
            )
            print(
                "  "
                f"{norm(context_data.get('symbol'))} | "
                f"{norm(context_data.get('method_name'))}"
            )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Hiçbir knowledge item silinmedi.")
        print("- Superseded geçmiş kayıtları korunuyor.")
        print("- EMPTY lifecycle state kayıtları episode bazında normalize edildi.")
        print("- Canonical research item downstream Brain için esas kayıttır.")
        print("- Research-derived bilgi verified değildir.")
        print("- Ham experiment/result, learned_rules, claims, validations")
        print("  ve observations değiştirilmedi.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

