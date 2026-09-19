# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Queue Hygiene Engine V1
-----------------------------------------------
Amaç:
    brain_research_queue içindeki eski V1 görevlerini silmeden
    semantik olarak tekilleştirmek ve artık geçerliliği kalmamış
    "rule promotion review" görevlerini kapatmak.

V1 yaptığı işler:
    1) Aktif görevleri tarar.
    2) Rule promotion review görevlerinden, ilgili learning event'in
       gerçekten PROMOTED olduğu tespit edilenleri "completed" yapar.
    3) Aynı learned_rule için:
         WEAK_HOLDOUT_REVIEW
         + eski/redundant re-evaluate benzeri görevleri
       tek aktif göreve indirir.
    4) Aynı METHOD_VARIANT_COMPARISON konusunu tek aktif göreve indirir.
    5) Hiçbir queue kaydını fiziksel olarak silmez.
    6) Kapanan kayıtların metadata_json alanına cleanup audit'i ekler.
    7) Yeni aktif task üretmez.

Bu bir araştırma motoru değildir.
Sadece queue hijyen / duplicate consolidation katmanıdır.

Status değerleri:
    queued
    working
    completed
    deduplicated

Çalıştırma:
    python agents/brain_research_queue_hygiene_v1.py
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
ENGINE_VERSION = "V1"


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


# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------

def parse_metadata(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


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
# ACTIVE QUEUE
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
# TASK TYPE
# ---------------------------------------------------------------------------

def task_type(row: sqlite3.Row) -> str:
    metadata = parse_metadata(row["metadata_json"])
    return normalize(metadata.get("task_type")).upper()


def learned_rule_id(row: sqlite3.Row) -> int | None:
    metadata = parse_metadata(row["metadata_json"])
    value = metadata.get("learned_rule_id")

    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    # Eski task'lar metadata'sız olabilir.
    return None


def symbol_context(row: sqlite3.Row) -> tuple[str, str, str, str]:
    metadata = parse_metadata(row["metadata_json"])

    return (
        normalize(metadata.get("symbol")).upper(),
        normalize(metadata.get("market")).upper(),
        normalize(metadata.get("timeframe")).lower(),
        normalize(metadata.get("condition_name")).lower(),
    )


# ---------------------------------------------------------------------------
# PROMOTION COMPLETION
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


def complete_stale_promotion_reviews(
    conn: sqlite3.Connection,
    tasks: list[sqlite3.Row],
) -> int:
    promoted_ids = promoted_rule_ids(conn)

    updated = 0

    for row in tasks:
        if row["status"] not in ("queued", "working"):
            continue

        q = normalize(row["question"]).lower()

        if not q.startswith("rule promotion review:"):
            continue

        rule_id = learned_rule_id(row)

        # Eski V1 promotion task'ı metadata'da rule id taşımıyorsa
        # question'dan kesin bir rule eşlemesi yapmak güvenli değildir.
        # Bu nedenle sadece doğrulanabilir rule_id varsa kapatılır.
        if rule_id is None or rule_id not in promoted_ids:
            continue

        metadata = append_cleanup_metadata(
            row["metadata_json"],
            action="completed",
            reason="rule_already_promoted_and_audit_confirmed",
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
# SEMANTIC GROUPING
# ---------------------------------------------------------------------------

def semantic_family(row: sqlite3.Row) -> tuple[Any, ...]:
    """
    Aynı araştırma işi için daha geniş bir aile anahtarı.

    WEAK_HOLDOUT_REVIEW:
        learned_rule_id bazlı.

    METHOD_VARIANT_COMPARISON:
        symbol + market + timeframe + condition bazlı.

    Diğerleri:
        task type + target claim + rule + context.
    """

    ttype = task_type(row)
    rule_id = learned_rule_id(row)
    claim_id = (
        safe_int(row["target_claim_id"])
        if row["target_claim_id"] is not None
        else None
    )

    ctx = symbol_context(row)

    if ttype in {
        "WEAK_HOLDOUT_REVIEW",
        "INSUFFICIENT_DATA_RESEARCH",
        "VALIDATED_RULE_RECHECK",
    }:
        return (
            "RULE_REVIEW",
            rule_id,
            ctx,
        )

    if ttype == "METHOD_VARIANT_COMPARISON":
        return (
            "VARIANT_COMPARISON",
            ctx,
        )

    # Eski V1 rule promotion review'leri için claim/rule ailesi.
    if normalize(row["question"]).lower().startswith(
        "rule promotion review:"
    ):
        return (
            "PROMOTION_REVIEW",
            rule_id,
            claim_id,
            ctx,
        )

    return (
        "GENERIC",
        ttype,
        rule_id,
        claim_id,
        ctx,
    )


# ---------------------------------------------------------------------------
# KEEP WINNER
# ---------------------------------------------------------------------------

def choose_keep(rows: list[sqlite3.Row]) -> sqlite3.Row:
    """
    Aynı semantic family içinde:
      1) queued, working'e göre öncelikli
      2) yüksek priority
      3) daha eski id
    """

    def key(row: sqlite3.Row) -> tuple[int, int, int]:
        status_score = (
            2 if normalize(row["status"]) == "working"
            else 1
        )

        return (
            status_score,
            safe_int(row["priority"]),
            -safe_int(row["id"]),
        )

    # working task'ı kaybetmek istemiyoruz; priority sonra geliyor.
    working = [
        row for row in rows
        if normalize(row["status"]) == "working"
    ]

    if working:
        return max(
            working,
            key=lambda r: (
                safe_int(r["priority"]),
                -safe_int(r["id"]),
            ),
        )

    return max(
        rows,
        key=lambda r: (
            safe_int(r["priority"]),
            -safe_int(r["id"]),
        ),
    )


def deduplicate_family(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> int:
    if len(rows) <= 1:
        return 0

    keep = choose_keep(rows)
    changed = 0

    for row in rows:
        if int(row["id"]) == int(keep["id"]):
            continue

        if normalize(row["status"]) not in ("queued", "working"):
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

        changed += 1

    return changed


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------

def active_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        """
    ).fetchone()

    return safe_int(row[0] if row else 0)


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
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


def print_queue(conn: sqlite3.Connection) -> None:
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
        before = active_count(conn)
        tasks = load_active_tasks(conn)

        completed_promotion = complete_stale_promotion_reviews(
            conn,
            tasks,
        )

        # Re-load after promotion cleanup.
        tasks = load_active_tasks(conn)

        groups: dict[tuple[Any, ...], list[sqlite3.Row]] = {}

        for row in tasks:
            groups.setdefault(
                semantic_family(row),
                [],
            ).append(row)

        duplicate_removed = 0

        for members in groups.values():
            duplicate_removed += deduplicate_family(
                conn,
                members,
            )

        conn.commit()

        after = active_count(conn)
        statuses = status_counts(conn)

        print("=" * 76)
        print("MARKETHQ BRAIN RESEARCH QUEUE HYGIENE ENGINE V1")
        print("=" * 76)
        print()
        print(f"Database : {DB_PATH}")
        print(f"Engine   : {ENGINE_NAME}")
        print(f"Version  : {ENGINE_VERSION}")
        print()
        print("QUEUE HYGIENE RUN")
        print("-" * 76)
        print(f"active_before                         {before}")
        print(f"stale_promotion_tasks_completed       {completed_promotion}")
        print(f"semantic_duplicates_closed             {duplicate_removed}")
        print(f"active_after                          {after}")
        print()
        print("ALL QUEUE STATUSES")
        print("-" * 76)

        for status, count in statuses.items():
            print(f"{status:35s} {count}")

        print()

        print_queue(conn)

        print("IMPORTANT")
        print("-" * 76)
        print("- Hiçbir queue kaydı fiziksel olarak silinmedi.")
        print("- Eski görevlerin geçmişi korunuyor.")
        print("- Sadece aktif stale/duplicate görevler kapatıldı.")
        print("- 'completed' = artık o araştırma görevine ihtiyaç kalmadı.")
        print("- 'deduplicated' = aynı iş için başka aktif görev korunuyor.")
        print("- Research Agent artık daha temiz bir queue görebilir.")
        print("- Sonraki aşama: Research Agent -> source discovery -> knowledge ingest.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

