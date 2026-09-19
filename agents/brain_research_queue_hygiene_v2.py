# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Queue Hygiene Engine V2
-----------------------------------------------
Queue geçmişini silmeden aktif araştırma görevlerini temizler.

V1'deki temel sorun:
    Eski "Rule promotion review" task'larında learned_rule_id her zaman
    metadata içinde bulunmuyordu. Bazı görevlerde yalnızca claim_id /
    evaluation_id vardı. Bu nedenle V1 bu görevleri stale olarak
    kapatamıyordu.

V2 düzeltmeleri:
    1) Rule promotion task'larını question + metadata üzerinden tanır.
    2) claim_id -> brain_rule_promotion_events -> PROMOTED eşlemesi yapar.
    3) Böylece zaten promote edilmiş rule review task'larını completed yapar.
    4) Aynı learned_rule için weak/re-evaluation görevlerini tek aktif
       ailede tutar.
    5) Aynı context için variant comparison görevlerini tekleştirir.
    6) Hiçbir queue kaydını fiziksel olarak silmez.
    7) Yeni task üretmez.

Status:
    queued
    working
    completed
    deduplicated

Çalıştırma:
    python agents/brain_research_queue_hygiene_v2.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_QUEUE_HYGIENE"
ENGINE_VERSION = "V2"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def parse_metadata(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def queue_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return parse_metadata(row["metadata_json"])


def append_cleanup_metadata(
    old_raw: str,
    *,
    action: str,
    reason: str,
    keep_id: int | None = None,
) -> str:
    metadata = parse_metadata(old_raw)

    metadata["queue_hygiene"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": action,
        "reason": reason,
        "keep_id": keep_id,
        "updated_at": utc_now(),
    }

    return compact_json(metadata)


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_active_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                id,
                question,
                reason,
                priority,
                target_node_id,
                target_claim_id,
                status,
                created_at,
                updated_at,
                metadata_json
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# TASK IDENTIFICATION
# ---------------------------------------------------------------------------

def task_type(row: sqlite3.Row) -> str:
    metadata = queue_metadata(row)
    value = normalize(metadata.get("task_type")).upper()

    if value:
        return value

    question = normalize(row["question"]).lower()

    if question.startswith("rule promotion review:"):
        return "RULE_PROMOTION_REVIEW"

    if question.startswith("re-evaluate weak learned rule:"):
        return "WEAK_HOLDOUT_REVIEW"

    if question.startswith("why did the learned rule weaken"):
        return "WEAK_HOLDOUT_REVIEW"

    if question.startswith("recheck stability of validated candidate"):
        return "VALIDATED_RULE_RECHECK"

    if question.startswith("compare method variants"):
        return "METHOD_VARIANT_COMPARISON"

    if question.startswith("collect more evidence"):
        return "INSUFFICIENT_DATA_RESEARCH"

    return "GENERIC"


def metadata_claim_id(row: sqlite3.Row) -> int | None:
    metadata = queue_metadata(row)

    for key in (
        "target_claim_id",
        "claim_id",
    ):
        value = metadata.get(key)
        if value is not None:
            parsed = safe_int(value, 0)
            if parsed > 0:
                return parsed

    if row["target_claim_id"] is not None:
        parsed = safe_int(row["target_claim_id"], 0)
        if parsed > 0:
            return parsed

    return None


def metadata_rule_id(row: sqlite3.Row) -> int | None:
    metadata = queue_metadata(row)

    for key in (
        "learned_rule_id",
        "rule_id",
    ):
        value = metadata.get(key)
        if value is not None:
            parsed = safe_int(value, 0)
            if parsed > 0:
                return parsed

    return None


# ---------------------------------------------------------------------------
# PROMOTION RESOLUTION
# ---------------------------------------------------------------------------

def promoted_rule_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT learned_rule_id
        FROM brain_rule_promotion_events
        WHERE
            decision = 'PROMOTED'
            AND status = 'promoted'
            AND learned_rule_id IS NOT NULL
        """
    ).fetchall()

    return {
        int(row["learned_rule_id"])
        for row in rows
        if row["learned_rule_id"] is not None
    }


def promoted_rule_ids_by_claim(
    conn: sqlite3.Connection,
) -> dict[int, set[int]]:
    rows = conn.execute(
        """
        SELECT
            source_claim_id,
            learned_rule_id
        FROM brain_rule_promotion_events
        WHERE
            decision = 'PROMOTED'
            AND status = 'promoted'
            AND source_claim_id IS NOT NULL
            AND learned_rule_id IS NOT NULL
        """
    ).fetchall()

    mapping: dict[int, set[int]] = {}

    for row in rows:
        claim_id = safe_int(row["source_claim_id"], 0)
        rule_id = safe_int(row["learned_rule_id"], 0)

        if claim_id <= 0 or rule_id <= 0:
            continue

        mapping.setdefault(claim_id, set()).add(rule_id)

    return mapping


def resolved_rule_id(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    by_claim: dict[int, set[int]],
) -> int | None:
    direct = metadata_rule_id(row)

    if direct is not None:
        return direct

    claim_id = metadata_claim_id(row)

    if claim_id is not None:
        candidates = by_claim.get(claim_id, set())

        if len(candidates) == 1:
            return next(iter(candidates))

    return None


# ---------------------------------------------------------------------------
# STALE PROMOTION CLEANUP
# ---------------------------------------------------------------------------

def complete_stale_promotion_reviews(
    conn: sqlite3.Connection,
    tasks: list[sqlite3.Row],
    by_claim: dict[int, set[int]],
) -> int:
    updated = 0

    for row in tasks:
        if row["status"] not in ("queued", "working"):
            continue

        if task_type(row) != "RULE_PROMOTION_REVIEW":
            continue

        rule_id = resolved_rule_id(
            conn,
            row,
            by_claim,
        )

        if rule_id is None:
            continue

        metadata = append_cleanup_metadata(
            row["metadata_json"],
            action="completed",
            reason=(
                "legacy_rule_promotion_review_resolved: "
                "linked rule was already promoted"
            ),
        )

        conn.execute(
            """
            UPDATE brain_research_queue
            SET
                status = 'completed',
                updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                metadata,
                int(row["id"]),
            ),
        )

        updated += 1

    return updated


# ---------------------------------------------------------------------------
# SEMANTIC FAMILIES
# ---------------------------------------------------------------------------

def context_from_metadata(row: sqlite3.Row) -> tuple[str, str, str, str]:
    metadata = queue_metadata(row)

    return (
        normalize(metadata.get("symbol")).upper(),
        normalize(metadata.get("market")).upper(),
        normalize(metadata.get("timeframe")).lower(),
        normalize(metadata.get("condition_name")).lower(),
    )


def semantic_family(row: sqlite3.Row) -> tuple[Any, ...]:
    ttype = task_type(row)
    rule_id = metadata_rule_id(row)

    claim_id = metadata_claim_id(row)

    if ttype in {
        "WEAK_HOLDOUT_REVIEW",
        "VALIDATED_RULE_RECHECK",
        "INSUFFICIENT_DATA_RESEARCH",
    }:
        # Rule id varsa en sağlam anahtar.
        if rule_id is not None:
            return (
                "RULE_REVIEW",
                rule_id,
            )

        # Eski task'larda rule id yoksa claim id fallback.
        if claim_id is not None:
            return (
                "RULE_REVIEW_CLAIM",
                claim_id,
            )

        return (
            "RULE_REVIEW_TEXT",
            normalize(row["question"]).lower(),
        )

    if ttype == "METHOD_VARIANT_COMPARISON":
        return (
            "VARIANT_COMPARISON",
            context_from_metadata(row),
        )

    if ttype == "RULE_PROMOTION_REVIEW":
        if rule_id is not None:
            return (
                "PROMOTION_REVIEW",
                rule_id,
            )

        if claim_id is not None:
            return (
                "PROMOTION_REVIEW_CLAIM",
                claim_id,
            )

        return (
            "PROMOTION_REVIEW_TEXT",
            normalize(row["question"]).lower(),
        )

    return (
        "GENERIC",
        ttype,
        rule_id,
        claim_id,
        context_from_metadata(row),
    )


# ---------------------------------------------------------------------------
# KEEP WINNER
# ---------------------------------------------------------------------------

def choose_keep(rows: list[sqlite3.Row]) -> sqlite3.Row:
    """
    Aynı semantic family'de:
        1) working task korunur
        2) sonra priority yüksek olan
        3) sonra daha eski task id
    """

    working = [
        row for row in rows
        if normalize(row["status"]) == "working"
    ]

    pool = working if working else rows

    return max(
        pool,
        key=lambda row: (
            safe_int(row["priority"]),
            -safe_int(row["id"]),
        ),
    )


def deduplicate_families(
    conn: sqlite3.Connection,
    tasks: list[sqlite3.Row],
) -> int:
    groups: dict[tuple[Any, ...], list[sqlite3.Row]] = {}

    for row in tasks:
        groups.setdefault(
            semantic_family(row),
            [],
        ).append(row)

    closed = 0

    for members in groups.values():
        if len(members) <= 1:
            continue

        keep = choose_keep(members)

        for row in members:
            if int(row["id"]) == int(keep["id"]):
                continue

            if normalize(row["status"]) not in (
                "queued",
                "working",
            ):
                continue

            metadata = append_cleanup_metadata(
                row["metadata_json"],
                action="deduplicated",
                reason="semantic_duplicate_of_active_research_task",
                keep_id=int(keep["id"]),
            )

            conn.execute(
                """
                UPDATE brain_research_queue
                SET
                    status = 'deduplicated',
                    updated_at = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    metadata,
                    int(row["id"]),
                ),
            )

            closed += 1

    return closed


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------

def count_statuses(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM brain_research_queue
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()

    return {
        normalize(row["status"]): safe_int(row["n"])
        for row in rows
    }


def active_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        """
    ).fetchone()

    return safe_int(row[0] if row else 0)


def print_active_queue(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT
            id,
            priority,
            status,
            question,
            reason
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        ORDER BY priority DESC, id ASC
        LIMIT 30
        """
    ).fetchall()

    print("ACTIVE QUEUE")
    print("-" * 76)

    if not rows:
        print("No active research tasks.")
        return

    for row in rows:
        print(
            f"[priority={safe_int(row['priority']):2d}] "
            f"{normalize(row['status'])} | "
            f"id={row['id']}"
        )
        print(f"  Q: {normalize(row['question'])}")
        print(f"  R: {normalize(row['reason'])}")
        print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        tasks_before = load_active_tasks(conn)
        active_before = len(tasks_before)

        by_claim = promoted_rule_ids_by_claim(conn)

        completed_promotions = complete_stale_promotion_reviews(
            conn,
            tasks_before,
            by_claim,
        )

        # Re-read after stale cleanup.
        tasks_after_promotion = load_active_tasks(conn)

        deduplicated = deduplicate_families(
            conn,
            tasks_after_promotion,
        )

        conn.commit()

        active_after = active_count(conn)
        statuses = count_statuses(conn)

        print("=" * 76)
        print("MARKETHQ BRAIN RESEARCH QUEUE HYGIENE ENGINE V2")
        print("=" * 76)
        print()
        print(f"Database : {DB_PATH}")
        print(f"Engine   : {ENGINE_NAME}")
        print(f"Version  : {ENGINE_VERSION}")
        print()
        print("QUEUE HYGIENE V2 RUN")
        print("-" * 76)
        print(f"active_before                         {active_before}")
        print(f"stale_promotion_tasks_completed       {completed_promotions}")
        print(f"semantic_duplicates_closed             {deduplicated}")
        print(f"active_after                          {active_after}")
        print()

        print("ALL QUEUE STATUSES")
        print("-" * 76)

        for status, count in statuses.items():
            print(f"{status:35s} {count}")

        print()

        print_active_queue(conn)

        print("IMPORTANT")
        print("-" * 76)
        print("- Hiçbir queue kaydı fiziksel olarak silinmedi.")
        print("- Eski görevlerin geçmişi korunuyor.")
        print("- Legacy promotion task'ları artık claim -> promoted rule")
        print("  bağlantısıyla çözümlenebiliyor.")
        print("- Aynı semantic araştırma işi aktif olarak tekilleştiriliyor.")
        print("- Bu motor yeni araştırma görevi üretmiyor.")
        print("- Sonraki aşama: Research Agent.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

