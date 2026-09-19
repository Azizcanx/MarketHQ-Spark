# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Agent Diagnostic V4
-------------------------------------------
Research Agent V3 pipeline'ının kalıcı veri değiştirmeden gerçek
çalışma adımlarını dry-run test eder.

V3 diagnostic'teki düzeltme:
    LEARNING_EVENT_INSERT_DRY_RUN için 7 placeholder'a 7 binding
    gönderilir. Önceki diagnostic'te yanlışlıkla fazladan bir
    "DIAGNOSTIC_V3" binding'i bulunuyordu.

HİÇBİR KALICI DEĞİŞİKLİK YAPMAZ:
    - INSERT/UPDATE denemeleri SAVEPOINT içinde yapılır.
    - Her işlem ROLLBACK edilir.
    - OpenAI çağrısı yapılmaz.
    - YouTube çağrısı yapılmaz.

Testler:
    1) Queue
    2) Context reconstruction
    3) Validation
    4) Learned rule
    5) Local knowledge_sources
    6) Local knowledge_items
    7) Brain claims
    8) Episode INSERT dry-run
    9) Learning event INSERT dry-run
    10) Queue UPDATE dry-run

Çalıştırma:
    python agents/brain_research_agent_diagnostic_v4.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def si(
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


def sf(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def cjson(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def pmeta(raw: Any) -> dict[str, Any]:
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


def db() -> sqlite3.Connection:
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
    name: str,
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
            (name,),
        ).fetchone()
        is not None
    )


def cols(
    conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        norm(row["name"])
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# QUEUE
# ---------------------------------------------------------------------------

def task_type(row: sqlite3.Row) -> str:
    metadata = pmeta(
        row["metadata_json"]
    )

    value = norm(
        metadata.get("task_type")
    ).upper()

    if value:
        return value

    q = norm(
        row["question"]
    ).lower()

    if q.startswith(
        "rule promotion review:"
    ):
        return "RULE_PROMOTION_REVIEW"

    if q.startswith(
        "re-evaluate weak learned rule:"
    ):
        return "WEAK_HOLDOUT_REVIEW"

    if q.startswith(
        "why did the learned rule weaken"
    ):
        return "WEAK_HOLDOUT_REVIEW"

    if q.startswith(
        "collect more evidence"
    ):
        return "INSUFFICIENT_DATA_RESEARCH"

    if q.startswith(
        "recheck stability"
    ):
        return "VALIDATED_RULE_RECHECK"

    if q.startswith(
        "compare method variants"
    ):
        return "METHOD_VARIANT_COMPARISON"

    return "GENERIC"


def queued_tasks(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT *
            FROM brain_research_queue
            WHERE status='queued'
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# ID RESOLUTION
# ---------------------------------------------------------------------------

def extract_id(
    text: str,
    pattern: str,
) -> int | None:
    match = re.search(
        pattern,
        norm(text),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    value = si(
        match.group(1),
        0,
    )

    return value if value > 0 else None


def resolve_claim_id(
    row: sqlite3.Row,
) -> int | None:
    metadata = pmeta(
        row["metadata_json"]
    )

    for key in (
        "target_claim_id",
        "claim_id",
    ):
        value = si(
            metadata.get(key),
            0,
        )

        if value > 0:
            return value

    value = si(
        row["target_claim_id"],
        0,
    )

    if value > 0:
        return value

    for text in (
        row["question"],
        row["reason"],
    ):
        value = extract_id(
            norm(text),
            r"claim_id\s*=\s*(\d+)",
        )

        if value:
            return value

    return None


def resolve_rule_id(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> int | None:
    metadata = pmeta(
        row["metadata_json"]
    )

    for key in (
        "learned_rule_id",
        "rule_id",
    ):
        value = si(
            metadata.get(key),
            0,
        )

        if value > 0:
            return value

    for text in (
        row["question"],
        row["reason"],
    ):
        value = extract_id(
            norm(text),
            r"rule_id\s*=\s*(\d+)",
        )

        if value:
            return value

    claim_id = resolve_claim_id(
        row
    )

    if (
        claim_id
        and table_exists(
            conn,
            "brain_rule_promotion_events",
        )
    ):
        result = conn.execute(
            """
            SELECT learned_rule_id
            FROM brain_rule_promotion_events
            WHERE
                source_claim_id=?
                AND decision='PROMOTED'
                AND status='promoted'
                AND learned_rule_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()

        if result:
            value = si(
                result["learned_rule_id"],
                0,
            )

            if value > 0:
                return value

    return None


def resolve_validation_id(
    row: sqlite3.Row,
) -> int | None:
    metadata = pmeta(
        row["metadata_json"]
    )

    value = si(
        metadata.get("validation_id"),
        0,
    )

    if value > 0:
        return value

    for text in (
        row["question"],
        row["reason"],
    ):
        value = extract_id(
            norm(text),
            r"validation_id\s*=\s*(\d+)",
        )

        if value:
            return value

    return None


# ---------------------------------------------------------------------------
# RULE / VALIDATION
# ---------------------------------------------------------------------------

def find_rule(
    conn: sqlite3.Connection,
    rule_id: int | None,
) -> sqlite3.Row | None:
    if not rule_id:
        return None

    return conn.execute(
        """
        SELECT *
        FROM learned_rules
        WHERE id=?
        LIMIT 1
        """,
        (rule_id,),
    ).fetchone()


def find_validation(
    conn: sqlite3.Connection,
    validation_id: int | None,
    rule_id: int | None,
) -> sqlite3.Row | None:
    if validation_id:
        row = conn.execute(
            """
            SELECT *
            FROM brain_rule_validations
            WHERE id=?
            LIMIT 1
            """,
            (validation_id,),
        ).fetchone()

        if row:
            return row

    if rule_id:
        return conn.execute(
            """
            SELECT *
            FROM brain_rule_validations
            WHERE learned_rule_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (rule_id,),
        ).fetchone()

    return None


def build_context(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = pmeta(
        row["metadata_json"]
    )

    claim_id = resolve_claim_id(
        row
    )

    rule_id = resolve_rule_id(
        conn,
        row,
    )

    validation_id = resolve_validation_id(
        row
    )

    rule = find_rule(
        conn,
        rule_id,
    )

    validation = find_validation(
        conn,
        validation_id,
        rule_id,
    )

    if (
        rule_id is None
        and validation is not None
    ):
        rule_id = si(
            validation["learned_rule_id"],
            0,
        ) or None

        rule = find_rule(
            conn,
            rule_id,
        )

    task = {
        "queue_id": si(row["id"]),
        "task_type": task_type(row),
        "question": norm(row["question"]),
        "reason": norm(row["reason"]),
        "claim_id": claim_id,
        "learned_rule_id": rule_id,
        "validation_id": (
            si(validation["id"])
            if validation is not None
            else validation_id
        ),
        "symbol": norm(
            metadata.get("symbol")
        ),
        "market": norm(
            metadata.get("market")
        ),
        "timeframe": norm(
            metadata.get("timeframe")
        ),
        "method_name": norm(
            metadata.get("method_name")
        ),
        "condition_name": norm(
            metadata.get("condition_name")
        ),
    }

    if rule is not None:
        task["symbol"] = norm(
            rule["symbol"]
        )
        task["market"] = norm(
            rule["market"]
        )
        task["timeframe"] = norm(
            rule["timeframe"]
        )
        task["method_name"] = norm(
            rule["method_name"]
        )
        task["condition_name"] = norm(
            rule["condition_name"]
        )

        for part in norm(
            rule["condition_name"]
        ).split("|"):
            if "=" not in part:
                continue

            key, value = part.split(
                "=",
                1,
            )

            key = norm(key).lower()
            value = norm(value)

            if key == "regime":
                task["market_regime"] = value
            elif key == "volume":
                task["volume_state"] = value
            elif key == "volatility":
                task["volatility_state"] = value

    return {
        "task": task,
        "rule": rule,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# LOCAL DISCOVERY
# ---------------------------------------------------------------------------

def test_knowledge_sources(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> int:
    if not table_exists(
        conn,
        "knowledge_sources",
    ):
        print(
            "  knowledge_sources: TABLE_MISSING"
        )
        return 0

    c = cols(
        conn,
        "knowledge_sources",
    )

    if "title" not in c:
        print(
            "  knowledge_sources: NO_TITLE_COLUMN"
        )
        return 0

    terms = [
        norm(task.get("symbol")),
        norm(task.get("method_name")),
        norm(task.get("condition_name")),
    ]

    terms = [
        x
        for x in terms
        if x
    ]

    if not terms:
        return 0

    clauses = []
    params = []

    for term in terms:
        clauses.append(
            "LOWER(COALESCE(title,'')) LIKE ?"
        )
        params.append(
            "%"
            + term.lower()[:120]
            + "%"
        )

    rows = conn.execute(
        f"""
        SELECT id
        FROM knowledge_sources
        WHERE {" OR ".join(clauses)}
        LIMIT 12
        """,
        tuple(params),
    ).fetchall()

    print(
        f"  knowledge_sources matched={len(rows)}"
    )

    return len(rows)


def test_knowledge_items(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> int:
    if not table_exists(
        conn,
        "knowledge_items",
    ):
        print(
            "  knowledge_items: TABLE_MISSING"
        )
        return 0

    c = cols(
        conn,
        "knowledge_items",
    )

    search_cols = [
        col
        for col in (
            "title",
            "summary",
            "content",
            "method",
        )
        if col in c
    ]

    if not search_cols:
        print(
            "  knowledge_items: NO_SEARCHABLE_COLUMNS"
        )
        return 0

    terms = [
        norm(task.get("symbol")),
        norm(task.get("method_name")),
        norm(task.get("condition_name")),
    ]

    terms = [
        x
        for x in terms
        if x
    ]

    if not terms:
        return 0

    term_clauses = []
    params = []

    for term in terms:
        parts = []

        for col in search_cols:
            parts.append(
                f"LOWER(COALESCE({col},'')) LIKE ?"
            )
            params.append(
                "%"
                + term.lower()[:120]
                + "%"
            )

        term_clauses.append(
            "("
            + " OR ".join(parts)
            + ")"
        )

    rows = conn.execute(
        f"""
        SELECT id
        FROM knowledge_items
        WHERE {" OR ".join(term_clauses)}
        LIMIT 20
        """,
        tuple(params),
    ).fetchall()

    print(
        f"  knowledge_items matched={len(rows)}"
    )

    return len(rows)


def test_claims(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> int:
    if not table_exists(
        conn,
        "brain_claims",
    ):
        print(
            "  brain_claims: TABLE_MISSING"
        )
        return 0

    claim_id = task.get(
        "claim_id"
    )

    if claim_id:
        rows = conn.execute(
            """
            SELECT id
            FROM brain_claims
            WHERE id=?
            LIMIT 10
            """,
            (claim_id,),
        ).fetchall()

        print(
            f"  brain_claims by id={len(rows)}"
        )

        return len(rows)

    symbol = norm(
        task.get("symbol")
    )

    if not symbol:
        print(
            "  brain_claims: NO_SYMBOL"
        )
        return 0

    rows = conn.execute(
        """
        SELECT id
        FROM brain_claims
        WHERE
            LOWER(COALESCE(claim_text,'')) LIKE ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (
            "%"
            + symbol.lower()
            + "%",
        ),
    ).fetchall()

    print(
        f"  brain_claims by symbol={len(rows)}"
    )

    return len(rows)


# ---------------------------------------------------------------------------
# DRY-RUN WRITES
# ---------------------------------------------------------------------------

def dry_run_episode_insert(
    conn: sqlite3.Connection,
    queue_id: int,
    task: dict[str, Any],
) -> int:
    content = (
        "DIAGNOSTIC DRY RUN\n"
        f"queue={queue_id}\n"
        f"symbol={task.get('symbol')}\n"
        f"method={task.get('method_name')}\n"
    )

    metadata = {
        "diagnostic": True,
        "queue_id": queue_id,
        "task_type": task.get(
            "task_type"
        ),
    }

    values = (
        "research_agent_result",
        "brain_research_queue",
        queue_id,
        f"diagnostic:queue:{queue_id}",
        "Diagnostic Episode",
        content,
        sha256(content),
        now(),
        now(),
        "",
        "DIAGNOSTIC_V4",
        cjson(metadata),
    )

    if len(values) != 12:
        raise RuntimeError(
            "Episode binding count expected 12, "
            f"got {len(values)}"
        )

    conn.execute(
        "SAVEPOINT diagnostic_episode"
    )

    try:
        cur = conn.execute(
            """
            INSERT INTO brain_episodes (
                episode_type,
                source_table,
                source_id,
                source_key,
                title,
                content,
                content_hash,
                observed_at,
                ingested_at,
                source_uri,
                author,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        inserted_id = si(
            cur.lastrowid
        )

        conn.execute(
            "ROLLBACK TO diagnostic_episode"
        )
        conn.execute(
            "RELEASE diagnostic_episode"
        )

        return inserted_id

    except Exception:
        conn.execute(
            "ROLLBACK TO diagnostic_episode"
        )
        conn.execute(
            "RELEASE diagnostic_episode"
        )
        raise


def dry_run_event_insert(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    episode_id: int,
) -> int:
    """
    brain_learning_events INSERT:
        11 columns listed,
        4 NULL constants,
        therefore 7 supplied placeholders:
            event_type
            learned_rule_id
            source_claim_id
            score
            decision
            created_at
            metadata_json
    """

    event_type = "RESEARCH_AGENT_RESULT"
    learned_rule_id = task.get(
        "learned_rule_id"
    )
    source_claim_id = task.get(
        "claim_id"
    )
    score = None
    decision = "RESEARCH_COMPLETED"
    created_at = now()

    metadata_json = cjson(
        {
            "diagnostic": True,
            "queue_id": task.get(
                "queue_id"
            ),
            "episode_id": episode_id,
        }
    )

    values = (
        event_type,
        learned_rule_id,
        source_claim_id,
        score,
        decision,
        created_at,
        metadata_json,
    )

    if len(values) != 7:
        raise RuntimeError(
            "Learning event binding count expected 7, "
            f"got {len(values)}"
        )

    conn.execute(
        "SAVEPOINT diagnostic_event"
    )

    try:
        cur = conn.execute(
            """
            INSERT INTO brain_learning_events (
                event_type,
                experiment_id,
                experiment_result_id,
                learned_rule_id,
                source_claim_id,
                created_node_id,
                created_edge_id,
                score,
                decision,
                created_at,
                metadata_json
            )
            VALUES (
                ?,
                NULL,
                NULL,
                ?,
                ?,
                NULL,
                NULL,
                ?,
                ?,
                ?,
                ?
            )
            """,
            values,
        )

        inserted_id = si(
            cur.lastrowid
        )

        conn.execute(
            "ROLLBACK TO diagnostic_event"
        )
        conn.execute(
            "RELEASE diagnostic_event"
        )

        return inserted_id

    except Exception:
        conn.execute(
            "ROLLBACK TO diagnostic_event"
        )
        conn.execute(
            "RELEASE diagnostic_event"
        )
        raise


def dry_run_queue_update(
    conn: sqlite3.Connection,
    queue_id: int,
) -> None:
    conn.execute(
        "SAVEPOINT diagnostic_queue"
    )

    try:
        conn.execute(
            """
            UPDATE brain_research_queue
            SET
                status='completed',
                updated_at=?
            WHERE id=?
            """,
            (
                now(),
                queue_id,
            ),
        )

        conn.execute(
            "ROLLBACK TO diagnostic_queue"
        )
        conn.execute(
            "RELEASE diagnostic_queue"
        )

    except Exception:
        conn.execute(
            "ROLLBACK TO diagnostic_queue"
        )
        conn.execute(
            "RELEASE diagnostic_queue"
        )
        raise


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    conn = db()

    try:
        print("=" * 78)
        print(
            "MARKETHQ BRAIN RESEARCH AGENT DIAGNOSTIC V4"
        )
        print("=" * 78)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            "MODE: DRY-RUN / ALL WRITES ROLLED BACK"
        )
        print(
            "OpenAI / YouTube calls: DISABLED"
        )
        print()

        rows = queued_tasks(
            conn
        )

        print(
            "queued_tasks_found                     "
            f"{len(rows)}"
        )
        print()

        for row in rows:
            print("#" * 78)
            print(
                f"QUEUE ID={row['id']} | "
                f"TYPE={task_type(row)}"
            )
            print(
                "Q: "
                + norm(row["question"])
            )
            print()

            try:
                print(
                    "CONTEXT_RECONSTRUCTION"
                )

                context = build_context(
                    conn,
                    row,
                )

                task = context["task"]
                validation = context[
                    "validation"
                ]

                print(
                    f"  symbol          = "
                    f"{task.get('symbol')!r}"
                )
                print(
                    f"  method          = "
                    f"{task.get('method_name')!r}"
                )
                print(
                    f"  market          = "
                    f"{task.get('market')!r}"
                )
                print(
                    f"  timeframe       = "
                    f"{task.get('timeframe')!r}"
                )
                print(
                    f"  condition       = "
                    f"{task.get('condition_name')!r}"
                )
                print(
                    f"  claim_id        = "
                    f"{task.get('claim_id')!r}"
                )
                print(
                    f"  learned_rule_id = "
                    f"{task.get('learned_rule_id')!r}"
                )
                print(
                    f"  validation_id   = "
                    f"{task.get('validation_id')!r}"
                )
                print(
                    "  STATUS = OK"
                )

                print()
                print("VALIDATION")

                if validation is None:
                    raise RuntimeError(
                        "validation row is None"
                    )

                print(
                    f"  verdict         = "
                    f"{validation['verdict']}"
                )
                print(
                    "  holdout_n       = "
                    f"{si(validation['holdout_sample_size'])}"
                )
                print(
                    "  holdout_pos     = "
                    f"{sf(validation['holdout_positive_rate']):.4f}"
                )
                print(
                    "  STATUS = OK"
                )

                print()
                print("LEARNED_RULE")

                rule = context["rule"]

                if rule is None:
                    raise RuntimeError(
                        "learned_rule is None"
                    )

                print(
                    "  rule_id         = "
                    f"{si(rule['id'])}"
                )
                print(
                    "  STATUS = OK"
                )

                print()
                print("LOCAL_DISCOVERY")

                test_knowledge_sources(
                    conn,
                    task,
                )

                test_knowledge_items(
                    conn,
                    task,
                )

                test_claims(
                    conn,
                    task,
                )

                print(
                    "  STATUS = OK"
                )

                print()
                print("EPISODE_INSERT_DRY_RUN")

                episode_id = (
                    dry_run_episode_insert(
                        conn,
                        si(row["id"]),
                        task,
                    )
                )

                print(
                    "  temporary_episode_id = "
                    f"{episode_id}"
                )
                print(
                    "  STATUS = OK / ROLLED_BACK"
                )

                print()
                print(
                    "LEARNING_EVENT_INSERT_DRY_RUN"
                )

                event_id = (
                    dry_run_event_insert(
                        conn,
                        task,
                        episode_id,
                    )
                )

                print(
                    "  temporary_event_id = "
                    f"{event_id}"
                )
                print(
                    "  STATUS = OK / ROLLED_BACK"
                )

                print()
                print(
                    "QUEUE_UPDATE_DRY_RUN"
                )

                dry_run_queue_update(
                    conn,
                    si(row["id"]),
                )

                print(
                    "  STATUS = OK / ROLLED_BACK"
                )

                print()
                print(
                    "TASK_RESULT = FULL_DRY_RUN_OK"
                )

            except Exception as exc:
                print()
                print(
                    "TASK_RESULT = ERROR"
                )
                print(
                    "ERROR_TYPE = "
                    f"{type(exc).__name__}"
                )
                print(
                    "ERROR_TEXT = "
                    f"{exc}"
                )
                print()
                traceback.print_exc()

        print()
        print("=" * 78)
        print("END")
        print("=" * 78)
        print(
            "No permanent INSERT/UPDATE/DELETE was performed."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()

