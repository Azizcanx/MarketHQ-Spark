# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Agent V4.1
--------------------------------
Production-ish repair of the Research Agent.

V4 fixes the main issues found during diagnostics:

1) Uses the verified DB schemas/columns from the diagnostic.
2) Reconstructs context from:
      queue -> validation -> learned_rule -> claim
3) Does NOT create a new "UNKNOWN" result when context is missing.
   It leaves the task queued instead.
4) Legacy RULE_PROMOTION_REVIEW tasks are never sent to research.
5) Existing UNKNOWN research episodes are preserved as history.
6) A successful re-run creates a NEW research episode instead of
   incorrectly reusing the old UNKNOWN episode.
7) The new episode records which older episode it supersedes.
8) Learning event INSERT uses the verified placeholder/binding count.
9) Each task reports its stage and traceback if anything fails.
10) OpenAI is used only for synthesis; local deterministic fallback remains.
11) YouTube is official Data API metadata discovery only.
12) No raw experiment/result / learned_rules / claims / validation rows
    are modified.

Recommended first run:
    RESEARCH_AGENT_BATCH_SIZE=2

Run:
    python agents/brain_research_agent_v4.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

load_dotenv(PROJECT_ROOT / ".env")

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_AGENT"
ENGINE_VERSION = "V4.2"

BATCH_SIZE = max(
    1,
    int(os.getenv("RESEARCH_AGENT_BATCH_SIZE", "2")),
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

RESEARCH_MODEL = os.getenv(
    "MARKETHQ_RESEARCH_MODEL",
    os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
).strip()

YOUTUBE_API_KEY = os.getenv(
    "YOUTUBE_API_KEY",
    "").strip()

YOUTUBE_MAX_RESULTS = 5

LOCAL_SOURCE_LIMIT = 12
LOCAL_KNOWLEDGE_LIMIT = 20
LOCAL_CLAIM_LIMIT = 10
LOCAL_RULE_LIMIT = 10


REAL_RESEARCH_TYPES = {
    "WEAK_HOLDOUT_REVIEW",
    "INSUFFICIENT_DATA_RESEARCH",
    "VALIDATED_RULE_RECHECK",
    "METHOD_VARIANT_COMPARISON",

    # Paper evidence is a research input, not a live-trading action.
    "PAPER_EVIDENCE_WEAK_REVIEW",
    "PAPER_EVIDENCE_MIXED_REVIEW",
    "PAPER_EVIDENCE_INSUFFICIENT_DATA",
    "PAPER_EVIDENCE_PROMISING_VALIDATION",
    "PAPER_EVIDENCE_GAP_RESEARCH",
}


# ---------------------------------------------------------------------------
# GENERIC HELPERS
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


def safe_float(
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


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_metadata(
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


def text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


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
) -> set[str]:
    if not table_exists(
        conn,
        table_name,
    ):
        return set()

    return {
        norm(row["name"])
        for row in conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# QUEUE
# ---------------------------------------------------------------------------

def get_task_type(
    row: sqlite3.Row,
) -> str:
    metadata = parse_metadata(
        row["metadata_json"]
    )

    value = norm(
        metadata.get("task_type")
    ).upper()

    if value:
        return value

    question = norm(
        row["question"]
    ).lower()

    if question.startswith(
        "rule promotion review:"
    ):
        return "RULE_PROMOTION_REVIEW"

    if question.startswith(
        "re-evaluate weak learned rule:"
    ):
        return "WEAK_HOLDOUT_REVIEW"

    if question.startswith(
        "why did the learned rule weaken"
    ):
        return "WEAK_HOLDOUT_REVIEW"

    if question.startswith(
        "collect more evidence"
    ):
        return "INSUFFICIENT_DATA_RESEARCH"

    if question.startswith(
        "collect independent strategy-level evidence"
    ):
        return "PAPER_EVIDENCE_GAP_RESEARCH"

    if question.startswith(
        "recheck stability"
    ):
        return "VALIDATED_RULE_RECHECK"

    if question.startswith(
        "compare method variants"
    ):
        return "METHOD_VARIANT_COMPARISON"

    return "GENERIC"


def load_queued_tasks(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """Load queued research tasks with paper-gap tasks explicitly prioritized.

    The queue contains legacy tasks whose task type may be inferred from the
    question rather than metadata. Therefore prioritization is performed in
    Python after task-type resolution, not only through SQL text matching.
    """
    rows = conn.execute(
        """
        SELECT *
        FROM brain_research_queue
        WHERE status='queued'
        ORDER BY priority DESC, id ASC
        LIMIT ?
        """,
        (
            max(
                BATCH_SIZE * 25,
                100,
            ),
        ),
    ).fetchall()

    eligible: list[tuple[int, int, sqlite3.Row]] = []

    for row in rows:
        task_type = get_task_type(row)

        if task_type == "RULE_PROMOTION_REVIEW":
            continue

        if task_type not in REAL_RESEARCH_TYPES:
            continue

        # Priority 0 = strategy-level paper evidence gap.
        paper_priority = (
            0
            if task_type == "PAPER_EVIDENCE_GAP_RESEARCH"
            else 1
        )

        eligible.append(
            (
                paper_priority,
                -safe_int(row["priority"]),
                row,
            )
        )

    eligible.sort(
        key=lambda item: (
            item[0],
            item[1],
            safe_int(item[2]["id"]),
        )
    )

    return [
        item[2]
        for item in eligible[:BATCH_SIZE]
    ]


def queue_metadata(
    row: sqlite3.Row,
) -> dict[str, Any]:
    return parse_metadata(
        row["metadata_json"]
    )


def is_paper_evidence_task(
    task_type: str,
) -> bool:
    return norm(task_type).upper() in {
        "PAPER_EVIDENCE_WEAK_REVIEW",
        "PAPER_EVIDENCE_MIXED_REVIEW",
        "PAPER_EVIDENCE_INSUFFICIENT_DATA",
        "PAPER_EVIDENCE_PROMISING_VALIDATION",
        "PAPER_EVIDENCE_GAP_RESEARCH",
    }


def paper_evidence_context(
    metadata: dict[str, Any],
    task_type: str,
) -> dict[str, Any]:
    """Normalize aggregate paper evidence into Research Agent context."""
    nested = metadata.get("paper_evidence")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update(
            {
                key: value
                for key, value in metadata.items()
                if key != "paper_evidence"
                and value not in (None, "", [], {})
            }
        )
        metadata = merged

    symbols_raw = metadata.get("symbols", [])

    if isinstance(symbols_raw, str):
        symbols = [
            x.strip()
            for x in re.split(r"[,;|]", symbols_raw)
            if x.strip()
        ]
    elif isinstance(symbols_raw, list):
        symbols = [
            norm(x)
            for x in symbols_raw
            if norm(x)
        ]
    else:
        symbols = []

    strategy_id = norm(
        metadata.get("strategy_id")
    )
    strategy_name = norm(
        metadata.get("strategy_name")
    )
    classification = norm(
        metadata.get("classification")
    ).upper()

    period = norm(
        metadata.get("period")
        or metadata.get("paper_period")
        or metadata.get("timeframe")
        or metadata.get("interval")
    )
    interval = norm(
        metadata.get("interval")
    )

    market = norm(
        metadata.get("market")
    )
    if not market:
        if symbols and all(
            symbol.upper().endswith(".IS")
            for symbol in symbols
        ):
            market = "BIST"
        elif symbols:
            market = "MULTI_MARKET"
        else:
            market = "UNKNOWN"

    symbol_label = (
        symbols[0]
        if len(symbols) == 1
        else (
            "MULTI_SYMBOL"
            if symbols
            else "PAPER_EVIDENCE"
        )
    )

    timeframe = period or interval or "HISTORICAL"

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "classification": classification,
        "symbols": symbols,
        "symbol_count": safe_int(
            metadata.get("symbol_count"),
            len(symbols),
        ),
        "raw_runs": safe_int(
            metadata.get("raw_runs")
            or metadata.get("runs")
        ),
        "unique_runs": safe_int(
            metadata.get("unique_runs")
        ),
        "total_trades": safe_int(
            metadata.get("total_trades")
        ),
        "win_rate": safe_float(
            metadata.get("win_rate")
        ),
        "aggregate_net_pnl": safe_float(
            metadata.get("aggregate_net_pnl")
        ),
        "aggregate_return": safe_float(
            metadata.get("aggregate_return")
        ),
        "average_run_return": safe_float(
            metadata.get("avg_run_return")
            or metadata.get("average_run_return")
        ),
        "median_run_return": safe_float(
            metadata.get("median_run_return")
        ),
        "average_profit_factor": safe_float(
            metadata.get("average_profit_factor")
            or metadata.get("avg_profit_factor")
        ),
        "worst_profit_factor": safe_float(
            metadata.get("worst_profit_factor")
        ),
        "average_max_drawdown": safe_float(
            metadata.get("average_max_drawdown")
            or metadata.get("avg_max_drawdown")
        ),
        "worst_max_drawdown": safe_float(
            metadata.get("worst_max_drawdown")
        ),
        "reasons": (
            metadata.get("reasons")
            if isinstance(metadata.get("reasons"), list)
            else []
        ),
        "research_actions": (
            metadata.get("research_actions")
            if isinstance(
                metadata.get("research_actions"),
                list,
            )
            else []
        ),
        "evidence_source": norm(
            metadata.get("evidence_source")
            or metadata.get("source_file")
            or metadata.get("source")
        ),
        "period": period,
        "interval": interval,
        "context_symbol": symbol_label,
        "context_market": market,
        "context_timeframe": timeframe,
        "context_method": (
            strategy_name
            or strategy_id
            or "PAPER_EVIDENCE_REVIEW"
        ),
        "context_condition": (
            "paper_evidence="
            + (
                classification
                or norm(task_type)
            )
        ),
    }


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

    value = safe_int(
        match.group(1),
        0,
    )

    return (
        value
        if value > 0
        else None
    )


def resolve_claim_id(
    row: sqlite3.Row,
) -> int | None:
    metadata = queue_metadata(
        row
    )

    for key in (
        "target_claim_id",
        "claim_id",
    ):
        value = safe_int(
            metadata.get(key),
            0,
        )

        if value > 0:
            return value

    value = safe_int(
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
            text,
            r"claim_id\s*=\s*(\d+)",
        )

        if value:
            return value

    return None


def resolve_rule_id(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> int | None:
    metadata = queue_metadata(
        row
    )

    for key in (
        "learned_rule_id",
        "rule_id",
    ):
        value = safe_int(
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
            text,
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
            value = safe_int(
                result["learned_rule_id"],
                0,
            )

            if value > 0:
                return value

    return None


def resolve_validation_id(
    row: sqlite3.Row,
) -> int | None:
    metadata = queue_metadata(
        row
    )

    value = safe_int(
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
            text,
            r"validation_id\s*=\s*(\d+)",
        )

        if value:
            return value

    return None


# ---------------------------------------------------------------------------
# CORE CONTEXT
# ---------------------------------------------------------------------------

def load_rule(
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


def load_validation(
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


def reconstruct_context(
    conn: sqlite3.Connection,
    queue_row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = queue_metadata(
        queue_row
    )

    claim_id = resolve_claim_id(
        queue_row
    )

    rule_id = resolve_rule_id(
        conn,
        queue_row,
    )

    validation_id = resolve_validation_id(
        queue_row
    )

    rule = load_rule(
        conn,
        rule_id,
    )

    validation = load_validation(
        conn,
        validation_id,
        rule_id,
    )

    if (
        rule_id is None
        and validation is not None
    ):
        rule_id = safe_int(
            validation["learned_rule_id"],
            0,
        ) or None

        rule = load_rule(
            conn,
            rule_id,
        )

    task = {
        "queue_id": safe_int(
            queue_row["id"]
        ),
        "task_type": get_task_type(
            queue_row
        ),
        "question": norm(
            queue_row["question"]
        ),
        "reason": norm(
            queue_row["reason"]
        ),
        "claim_id": claim_id,
        "learned_rule_id": rule_id,
        "validation_id": (
            safe_int(
                validation["id"],
                0,
            )
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
        "market_regime": norm(
            metadata.get("market_regime")
        ),
        "volume_state": norm(
            metadata.get("volume_state")
        ),
        "volatility_state": norm(
            metadata.get("volatility_state")
        ),
    }

    if is_paper_evidence_task(
        task["task_type"]
    ):
        paper_context = paper_evidence_context(
            metadata,
            task["task_type"],
        )

        task["paper_evidence"] = paper_context
        task["strategy_id"] = paper_context[
            "strategy_id"
        ]
        task["strategy_name"] = paper_context[
            "strategy_name"
        ]
        task["paper_classification"] = paper_context[
            "classification"
        ]
        task["paper_symbols"] = paper_context[
            "symbols"
        ]

        if not task["symbol"]:
            task["symbol"] = paper_context[
                "context_symbol"
            ]
        if not task["market"]:
            task["market"] = paper_context[
                "context_market"
            ]
        if not task["timeframe"]:
            task["timeframe"] = paper_context[
                "context_timeframe"
            ]
        if not task["method_name"]:
            task["method_name"] = paper_context[
                "context_method"
            ]
        if not task["condition_name"]:
            task["condition_name"] = paper_context[
                "context_condition"
            ]

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

            key = norm(
                key
            ).lower()

            value = norm(
                value
            )

            if key == "regime":
                task["market_regime"] = value
            elif key == "volume":
                task["volume_state"] = value
            elif key == "volatility":
                task["volatility_state"] = value

    validation_summary = None

    if validation is not None:
        validation_summary = {
            "validation_id": safe_int(
                validation["id"]
            ),
            "verdict": norm(
                validation["verdict"]
            ),
            "reference_sample_size": safe_int(
                validation[
                    "reference_sample_size"
                ]
            ),
            "holdout_sample_size": safe_int(
                validation[
                    "holdout_sample_size"
                ]
            ),
            "reference_positive_rate": safe_float(
                validation[
                    "reference_positive_rate"
                ]
            ),
            "holdout_positive_rate": safe_float(
                validation[
                    "holdout_positive_rate"
                ]
            ),
            "reference_average_return_20d": safe_float(
                validation[
                    "reference_average_return_20d"
                ]
            ),
            "holdout_average_return_20d": safe_float(
                validation[
                    "holdout_average_return_20d"
                ]
            ),
            "positive_rate_delta": safe_float(
                validation[
                    "positive_rate_delta"
                ]
            ),
            "average_return_20d_ratio": validation[
                "average_return_20d_ratio"
            ],
            "split_date": norm(
                validation["split_date"]
            ),
            "rationale": norm(
                validation["rationale"]
            ),
        }

    task["validation_summary"] = (
        validation_summary
    )

    return {
        "task": task,
        "rule": rule,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# CONTEXT GUARD
# ---------------------------------------------------------------------------

def context_is_sufficient(
    task: dict[str, Any],
) -> bool:
    # Paper evidence is aggregate/multi-symbol evidence. It does not require
    # one canonical symbol or a single learned-rule/claim/validation row.
    if is_paper_evidence_task(
        task.get("task_type", "")
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        return bool(
            (
                paper.get("strategy_id")
                or paper.get("strategy_name")
            )
            and paper.get("symbols")
            and paper.get("classification")
        )

    return bool(
        task.get("symbol")
        and task.get(
            "method_name"
        )
        and task.get(
            "market"
        )
        and task.get(
            "timeframe"
        )
        and (
            task.get("learned_rule_id")
            or task.get("validation_id")
            or task.get("claim_id")
        )
    )


# ---------------------------------------------------------------------------
# LOCAL SOURCE DISCOVERY
# ---------------------------------------------------------------------------

def local_knowledge_sources(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    if not table_exists(
        conn,
        "knowledge_sources",
    ):
        return []

    columns = table_columns(
        conn,
        "knowledge_sources",
    )

    if "title" not in columns:
        return []

    terms = [
        norm(task.get("symbol")),
        norm(task.get("method_name")),
        norm(task.get("condition_name")),
    ]

    if is_paper_evidence_task(
        task.get("task_type", "")
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        terms.extend(
            [
                norm(paper.get("strategy_id")),
                norm(paper.get("strategy_name")),
                *[
                    norm(symbol)
                    for symbol in paper.get(
                        "symbols",
                        [],
                    )
                ],
            ]
        )

    terms = [
        x
        for x in terms
        if x
    ]

    if not terms:
        return []

    clauses = [
        "LOWER(COALESCE(title,'')) LIKE ?"
        for _ in terms
    ]

    params = [
        "%"
        + x.lower()[:150]
        + "%"
        for x in terms
    ]

    rows = conn.execute(
        f"""
        SELECT *
        FROM knowledge_sources
        WHERE {" OR ".join(clauses)}
        ORDER BY id DESC
        LIMIT ?
        """,
        tuple(
            params
            + [LOCAL_SOURCE_LIMIT]
        ),
    ).fetchall()

    uri_col = (
        "url"
        if "url" in columns
        else None
    )

    output = []

    for row in rows:
        output.append(
            {
                "id": safe_int(
                    row["id"]
                ),
                "title": norm(
                    row["title"]
                ),
                "uri": (
                    norm(row[uri_col])
                    if uri_col
                    else ""
                ),
            }
        )

    return output


def local_knowledge_items(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    if not table_exists(
        conn,
        "knowledge_items",
    ):
        return []

    columns = table_columns(
        conn,
        "knowledge_items",
    )

    # Actual schema observed in diagnostics:
    # id, source_id, item_type, title, content, summary,
    # method, symbols_json, tags_json, confidence, metadata_json, created_at

    searchable = [
        column
        for column in (
            "title",
            "summary",
            "content",
            "method",
        )
        if column in columns
    ]

    if not searchable:
        return []

    terms = [
        norm(task.get("symbol")),
        norm(task.get("method_name")),
        norm(task.get("condition_name")),
    ]

    if is_paper_evidence_task(
        task.get("task_type", "")
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        terms.extend(
            [
                norm(paper.get("strategy_id")),
                norm(paper.get("strategy_name")),
                *[
                    norm(symbol)
                    for symbol in paper.get(
                        "symbols",
                        [],
                    )
                ],
            ]
        )

    terms = [
        x
        for x in terms
        if x
    ]

    if not terms:
        return []

    term_clauses: list[str] = []
    params: list[Any] = []

    for term in terms:
        parts = []

        for column in searchable:
            parts.append(
                f"LOWER(COALESCE({column},'')) LIKE ?"
            )
            params.append(
                "%"
                + term.lower()[:150]
                + "%"
            )

        term_clauses.append(
            "("
            + " OR ".join(parts)
            + ")"
        )

    rows = conn.execute(
        f"""
        SELECT *
        FROM knowledge_items
        WHERE {" OR ".join(term_clauses)}
        ORDER BY id DESC
        LIMIT ?
        """,
        tuple(
            params
            + [LOCAL_KNOWLEDGE_LIMIT]
        ),
    ).fetchall()

    output = []

    for row in rows:
        output.append(
            {
                "id": safe_int(
                    row["id"]
                ),
                "title": norm(
                    row["title"]
                )
                if "title" in row.keys()
                else "",
                "summary": (
                    norm(
                        row["summary"]
                    )
                    if "summary" in row.keys()
                    else ""
                ),
                "content": (
                    norm(
                        row["content"]
                    )[:2500]
                    if "content" in row.keys()
                    else ""
                ),
                "method": (
                    norm(
                        row["method"]
                    )
                    if "method" in row.keys()
                    else ""
                ),
            }
        )

    return output


def local_claims(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    if not table_exists(
        conn,
        "brain_claims",
    ):
        return []

    claim_id = task.get(
        "claim_id"
    )

    if claim_id:
        rows = conn.execute(
            """
            SELECT
                id,
                claim_key,
                claim_text,
                claim_type,
                status,
                confidence
            FROM brain_claims
            WHERE id=?
            LIMIT ?
            """,
            (
                int(claim_id),
                LOCAL_CLAIM_LIMIT,
            ),
        ).fetchall()
    else:
        symbol = norm(
            task.get("symbol")
        )

        if not symbol:
            return []

        rows = conn.execute(
            """
            SELECT
                id,
                claim_key,
                claim_text,
                claim_type,
                status,
                confidence
            FROM brain_claims
            WHERE
                LOWER(COALESCE(claim_text,'')) LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                "%"
                + symbol.lower()
                + "%",
                LOCAL_CLAIM_LIMIT,
            ),
        ).fetchall()

    return [
        {
            "id": safe_int(
                row["id"]
            ),
            "claim_key": norm(
                row["claim_key"]
            ),
            "claim_text": norm(
                row["claim_text"]
            ),
            "claim_type": norm(
                row["claim_type"]
            ),
            "status": norm(
                row["status"]
            ),
            "confidence": safe_float(
                row["confidence"]
            ),
        }
        for row in rows
    ]


def local_rules(
    conn: sqlite3.Connection,
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    if not table_exists(
        conn,
        "learned_rules",
    ):
        return []

    symbol = norm(
        task.get("symbol")
    )

    method = norm(
        task.get("method_name")
    )

    clauses = []
    params: list[Any] = []

    if symbol:
        clauses.append(
            "symbol=?"
        )
        params.append(symbol)

    if method:
        clauses.append(
            "method_name=?"
        )
        params.append(method)

    if is_paper_evidence_task(
        task.get("task_type", "")
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        symbols = [
            norm(symbol)
            for symbol in paper.get(
                "symbols",
                [],
            )
            if norm(symbol)
        ]

        if not symbols:
            return []

        placeholders = ",".join(
            "?" for _ in symbols
        )

        rows = conn.execute(
            f"""
            SELECT
                id,
                method_name,
                symbol,
                market,
                timeframe,
                condition_name,
                sample_size,
                success_rate,
                average_return_20d,
                confidence,
                observation
            FROM learned_rules
            WHERE symbol IN ({placeholders})
            ORDER BY confidence DESC, sample_size DESC
            LIMIT ?
            """,
            tuple(
                symbols
                + [LOCAL_RULE_LIMIT]
            ),
        ).fetchall()

        return [
            {
                "id": safe_int(row["id"]),
                "method_name": norm(
                    row["method_name"]
                ),
                "symbol": norm(
                    row["symbol"]
                ),
                "market": norm(
                    row["market"]
                ),
                "timeframe": norm(
                    row["timeframe"]
                ),
                "condition_name": norm(
                    row["condition_name"]
                ),
                "sample_size": safe_int(
                    row["sample_size"]
                ),
                "success_rate": safe_float(
                    row["success_rate"]
                ),
                "average_return_20d": safe_float(
                    row["average_return_20d"]
                ),
                "confidence": safe_float(
                    row["confidence"]
                ),
                "observation": norm(
                    row["observation"]
                )[:1800],
            }
            for row in rows
        ]

    if not clauses:
        return []

    rows = conn.execute(
        f"""
        SELECT
            id,
            method_name,
            symbol,
            market,
            timeframe,
            condition_name,
            sample_size,
            success_rate,
            average_return_20d,
            confidence,
            observation
        FROM learned_rules
        WHERE {" AND ".join(clauses)}
        ORDER BY confidence DESC, sample_size DESC
        LIMIT ?
        """,
        tuple(
            params
            + [LOCAL_RULE_LIMIT]
        ),
    ).fetchall()

    return [
        {
            "id": safe_int(
                row["id"]
            ),
            "method_name": norm(
                row["method_name"]
            ),
            "symbol": norm(
                row["symbol"]
            ),
            "market": norm(
                row["market"]
            ),
            "timeframe": norm(
                row["timeframe"]
            ),
            "condition_name": norm(
                row["condition_name"]
            ),
            "sample_size": safe_int(
                row["sample_size"]
            ),
            "success_rate": safe_float(
                row["success_rate"]
            ),
            "average_return_20d": safe_float(
                row["average_return_20d"]
            ),
            "confidence": safe_float(
                row["confidence"]
            ),
            "observation": norm(
                row["observation"]
            )[:1800],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# YOUTUBE
# ---------------------------------------------------------------------------

def youtube_search(
    query: str,
) -> list[dict[str, Any]]:
    if not YOUTUBE_API_KEY:
        return []

    if not norm(query):
        return []

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "maxResults": YOUTUBE_MAX_RESULTS,
                "type": "video",
                "key": YOUTUBE_API_KEY,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (
        requests.RequestException,
        ValueError,
    ):
        return []

    results = []

    for item in data.get(
        "items",
        [],
    ):
        item_id = item.get(
            "id",
            {},
        )

        if not isinstance(
            item_id,
            dict,
        ):
            continue

        video_id = norm(
            item_id.get("videoId")
        )

        if not video_id:
            continue

        snippet = item.get(
            "snippet",
            {},
        )

        results.append(
            {
                "video_id": video_id,
                "title": norm(
                    snippet.get("title")
                ),
                "description": norm(
                    snippet.get("description")
                )[:1000],
                "published_at": norm(
                    snippet.get("publishedAt")
                ),
                "channel_title": norm(
                    snippet.get("channelTitle")
                ),
                "url": (
                    "https://www.youtube.com/watch?v="
                    + video_id
                ),
            }
        )

    return results


def discover_youtube(
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    query = " ".join(
        x
        for x in (
            "FIN[SYS]",
            norm(task.get("symbol")),
            norm(task.get("method_name")),
            norm(task.get("condition_name")),
            "research",
        )
        if x
    )

    return youtube_search(
        query[:400]
    )


# ---------------------------------------------------------------------------
# OPENAI SYNTHESIS
# ---------------------------------------------------------------------------

def call_openai(
    *,
    task: dict[str, Any],
    validation: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    items: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    youtube_results: list[dict[str, Any]],
) -> tuple[str, str]:
    if not OPENAI_API_KEY:
        return "", "OPENAI_NOT_CONFIGURED"

    packet = {
        "task": task,
        "validation": validation,
        "knowledge_sources": sources,
        "knowledge_items": items,
        "claims": claims,
        "rules": rules,
        "youtube_results": youtube_results,
    }

    system_text = (
        "You are MarketHQ's research synthesis layer. "
        "This is historical market research and decision support only. "
        "Do not provide live trading instructions or guarantees. "
        "Separate FACT, OBSERVATION, INFERENCE, HYPOTHESIS and UNKNOWN. "
        "Never invent missing evidence. "
        "Clearly state evidence gaps and contradictions."
    )

    user_text = (
        "Analyze this MarketHQ research task.\n\n"
        "Return a compact research brief with:\n"
        "1. Research question.\n"
        "2. Actual evidence found.\n"
        "3. Evidence vs inference.\n"
        "4. Why the rule weakened/remained stable, if relevant.\n"
        "5. Evidence gaps.\n"
        "6. One next research question.\n"
        "Do not call historical evidence a verified rule.\n\n"
        "EVIDENCE_PACKET:\n"
        + json.dumps(
            packet,
            ensure_ascii=False,
        )
    )

    payload = {
        "model": RESEARCH_MODEL,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_text,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_text,
                    }
                ],
            },
        ],
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": (
                    "Bearer "
                    + OPENAI_API_KEY
                ),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
    except (
        requests.RequestException,
        ValueError,
    ):
        return "", "OPENAI_CALL_FAILED"

    output_text = norm(
        data.get("output_text")
    )

    if not output_text:
        parts: list[str] = []

        for item in data.get(
            "output",
            [],
        ):
            for content in item.get(
                "content",
                [],
            ):
                text = norm(
                    content.get("text")
                )

                if text:
                    parts.append(text)

        output_text = "\n".join(
            parts
        ).strip()

    if not output_text:
        return "", "OPENAI_EMPTY_RESPONSE"

    return output_text, "OPENAI_OK"


# ---------------------------------------------------------------------------
# DETERMINISTIC FALLBACK
# ---------------------------------------------------------------------------

def local_brief(
    *,
    task: dict[str, Any],
    validation: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    items: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    youtube_results: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.append(
        "MARKETHQ LOCAL RESEARCH BRIEF"
    )
    lines.append("")
    lines.append(
        "Research question: "
        + norm(task.get("question"))
    )

    lines.append("")
    lines.append(
        "RECONSTRUCTED CONTEXT"
    )
    lines.append(
        f"symbol={norm(task.get('symbol'))}"
    )
    lines.append(
        f"method={norm(task.get('method_name'))}"
    )
    lines.append(
        f"market={norm(task.get('market'))}"
    )
    lines.append(
        f"timeframe={norm(task.get('timeframe'))}"
    )
    lines.append(
        "condition="
        + norm(task.get("condition_name"))
    )

    if is_paper_evidence_task(
        task.get("task_type", "")
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        lines.append("")
        lines.append("PAPER EVIDENCE")
        lines.append(
            "strategy_id="
            + norm(paper.get("strategy_id"))
        )
        lines.append(
            "strategy_name="
            + norm(paper.get("strategy_name"))
        )
        lines.append(
            "classification="
            + norm(paper.get("classification"))
        )
        lines.append(
            "symbols="
            + ", ".join(
                paper.get("symbols", [])
            )
        )
        lines.append(
            "runs="
            + str(
                safe_int(
                    paper.get("unique_runs")
                    or paper.get("raw_runs")
                )
            )
        )
        lines.append(
            "trades="
            + str(
                safe_int(
                    paper.get("total_trades")
                )
            )
        )
        lines.append(
            "win_rate="
            + f"{safe_float(paper.get('win_rate')):.4f}"
        )
        lines.append(
            "aggregate_return="
            + f"{safe_float(paper.get('aggregate_return')):.4f}"
        )
        lines.append(
            "average_profit_factor="
            + f"{safe_float(paper.get('average_profit_factor')):.4f}"
        )
        lines.append(
            "reasons="
            + "; ".join(
                norm(x)
                for x in paper.get(
                    "reasons",
                    [],
                )
                if norm(x)
            )
        )

    lines.append("")
    lines.append("EPISTEMIC STATE")
    lines.append(
        "- FACT/OBSERVATION: MarketHQ historical records."
    )
    lines.append(
        "- INFERENCE: interpretation of available records."
    )
    lines.append(
        "- UNKNOWN: independently unverified areas."
    )

    if validation:
        lines.append("")
        lines.append("VALIDATION")
        lines.append(
            f"verdict={validation.get('verdict')}"
        )
        lines.append(
            f"reference_n={validation.get('reference_sample_size')}"
        )
        lines.append(
            f"holdout_n={validation.get('holdout_sample_size')}"
        )
        lines.append(
            "reference_positive_rate="
            f"{safe_float(validation.get('reference_positive_rate')):.4f}"
        )
        lines.append(
            "holdout_positive_rate="
            f"{safe_float(validation.get('holdout_positive_rate')):.4f}"
        )
        lines.append(
            "reference_average_return_20d="
            f"{safe_float(validation.get('reference_average_return_20d')):.4f}"
        )
        lines.append(
            "holdout_average_return_20d="
            f"{safe_float(validation.get('holdout_average_return_20d')):.4f}"
        )
        lines.append(
            "positive_rate_delta="
            f"{safe_float(validation.get('positive_rate_delta')):+.4f}"
        )

    lines.append("")
    lines.append("LOCAL KNOWLEDGE")
    lines.append(
        f"sources_found={len(sources)}"
    )
    lines.append(
        f"items_found={len(items)}"
    )

    for item in items[:8]:
        lines.append(
            "- "
            + norm(item.get("title"))
            + ": "
            + norm(item.get("summary"))[:500]
        )

    lines.append("")
    lines.append("BRAIN CLAIMS")
    lines.append(
        f"claims_found={len(claims)}"
    )

    for claim in claims[:6]:
        lines.append(
            "- "
            + f"[{claim['status']}] "
            + f"confidence={claim['confidence']:.3f}: "
            + claim["claim_text"][:600]
        )

    lines.append("")
    lines.append("LEARNED RULES")
    lines.append(
        f"rules_found={len(rules)}"
    )

    for rule in rules[:6]:
        lines.append(
            "- "
            + f"{rule['symbol']} | "
            + f"n={rule['sample_size']} | "
            + f"pos={rule['success_rate']:.3f} | "
            + f"avg20={rule['average_return_20d']:.4f} | "
            + rule["condition_name"]
        )

    lines.append("")
    lines.append("YOUTUBE METADATA")
    lines.append(
        f"videos_found={len(youtube_results)}"
    )

    for video in youtube_results[:5]:
        lines.append(
            "- "
            + video["title"]
            + " | "
            + video["url"]
        )

    lines.append("")
    lines.append("EVIDENCE GAPS")
    lines.append(
        "- Historical local evidence does not establish "
        "fully independent forward validity."
    )

    if not items and not sources:
        lines.append(
            "- No matching local knowledge source was found."
        )

    if not youtube_results:
        lines.append(
            "- No YouTube metadata discovery result was available."
        )

    lines.append("")
    lines.append("NEXT RESEARCH QUESTION")
    lines.append(
        "Check whether the observed context remains stable "
        "in another independent historical slice or evidence source."
    )

    lines.append("")
    lines.append(
        "IMPORTANT: historical research brief; "
        "not a verified rule and not a live trading instruction."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BRAIN EPISODE
# ---------------------------------------------------------------------------

def ensure_episode_indexes(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_episodes_source
        ON brain_episodes(source_table, source_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_brain_episodes_hash
        ON brain_episodes(content_hash)
        """
    )


def previous_research_episode(
    conn: sqlite3.Connection,
    queue_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            id,
            content_hash,
            observed_at
        FROM brain_episodes
        WHERE
            episode_type='research_agent_result'
            AND source_table='brain_research_queue'
            AND source_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (queue_id,),
    ).fetchone()


def count_research_episodes(
    conn: sqlite3.Connection,
    queue_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_episodes
        WHERE
            episode_type='research_agent_result'
            AND source_table='brain_research_queue'
            AND source_id=?
        """,
        (queue_id,),
    ).fetchone()

    return safe_int(
        row[0] if row else 0
    )


def write_episode(
    conn: sqlite3.Connection,
    *,
    queue_id: int,
    task: dict[str, Any],
    research_text: str,
    provider_status: str,
    evidence_packet: dict[str, Any],
) -> int:
    previous = previous_research_episode(
        conn,
        queue_id,
    )

    sequence = (
        count_research_episodes(
            conn,
            queue_id,
        )
        + 1
    )

    symbol = (
        norm(task.get("symbol"))
        or "RESEARCH"
    )

    task_type = (
        norm(task.get("task_type"))
        or "RESEARCH"
    )

    title = (
        "Research Result | "
        f"{symbol} | {task_type} | run={sequence}"
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "queue_id": queue_id,
        "run_sequence": sequence,
        "task_type": task_type,
        "provider_status": provider_status,
        "claim_id": task.get("claim_id"),
        "learned_rule_id": task.get(
            "learned_rule_id"
        ),
        "validation_id": task.get(
            "validation_id"
        ),
        "reconstructed_context": {
            "symbol": task.get("symbol"),
            "method_name": task.get(
                "method_name"
            ),
            "market": task.get("market"),
            "timeframe": task.get(
                "timeframe"
            ),
            "condition_name": task.get(
                "condition_name"
            ),
            "market_regime": task.get(
                "market_regime"
            ),
            "volume_state": task.get(
                "volume_state"
            ),
            "volatility_state": task.get(
                "volatility_state"
            ),
        },
        "evidence_counts": {
            "knowledge_sources": len(
                evidence_packet[
                    "knowledge_sources"
                ]
            ),
            "knowledge_items": len(
                evidence_packet[
                    "knowledge_items"
                ]
            ),
            "claims": len(
                evidence_packet["claims"]
            ),
            "rules": len(
                evidence_packet["rules"]
            ),
            "youtube_results": len(
                evidence_packet[
                    "youtube_results"
                ]
            ),
        },
        "supersedes_episode_id": (
            safe_int(
                previous["id"],
                0,
            )
            if previous is not None
            else None
        ),
        "epistemic_note": (
            "Research result derived from MarketHQ "
            "historical evidence. Not a verified rule."
        ),
    }

    now = utc_now()

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
            ?
        )
        """,
        (
            "research_agent_result",
            "brain_research_queue",
            queue_id,
            f"queue:{queue_id}:run:{sequence}",
            title,
            research_text.strip(),
            text_hash(
                research_text
            ),
            now,
            now,
            "",
            ENGINE_NAME,
            compact_json(metadata),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# LEARNING EVENT
# ---------------------------------------------------------------------------

def write_research_event(
    conn: sqlite3.Connection,
    *,
    task: dict[str, Any],
    episode_id: int,
    provider_status: str,
) -> int:
    queue_id = safe_int(
        task.get("queue_id")
    )

    existing = conn.execute(
        """
        SELECT id
        FROM brain_learning_events
        WHERE
            event_type='RESEARCH_AGENT_RESULT'
            AND metadata_json LIKE ?
        LIMIT 1
        """,
        (
            f'%"episode_id":{episode_id}%',
        ),
    ).fetchone()

    if existing:
        return safe_int(
            existing["id"]
        )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "queue_id": queue_id,
        "episode_id": episode_id,
        "task_type": task.get(
            "task_type"
        ),
        "claim_id": task.get(
            "claim_id"
        ),
        "learned_rule_id": task.get(
            "learned_rule_id"
        ),
        "validation_id": task.get(
            "validation_id"
        ),
        "provider_status": provider_status,
        "event_role": "research_ingest",
        "context_reconstructed": True,
    }

    # Verified by Diagnostic V4:
    # 4 literal NULL values + 4 supplied values = 4 placeholders.
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
            'RESEARCH_AGENT_RESULT',
            NULL,
            NULL,
            ?,
            ?,
            NULL,
            NULL,
            NULL,
            'RESEARCH_COMPLETED',
            ?,
            ?
        )
        """,
        (
            task.get(
                "learned_rule_id"
            ),
            task.get(
                "claim_id"
            ),
            utc_now(),
            compact_json(metadata),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# QUEUE STATE
# ---------------------------------------------------------------------------

def mark_working(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> None:
    metadata = queue_metadata(
        row
    )

    metadata["research_agent"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "working",
        "started_at": utc_now(),
    }

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            status='working',
            updated_at=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            utc_now(),
            compact_json(metadata),
            safe_int(row["id"]),
        ),
    )

    conn.commit()


def mark_completed(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    episode_id: int,
) -> None:
    metadata = queue_metadata(
        row
    )

    metadata["research_agent"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "completed",
        "episode_id": episode_id,
        "completed_at": utc_now(),
    }

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            status='completed',
            updated_at=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            utc_now(),
            compact_json(metadata),
            safe_int(row["id"]),
        ),
    )


def mark_held(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    reason: str,
) -> None:
    metadata = queue_metadata(
        row
    )

    metadata["research_agent"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "held",
        "reason": reason,
        "updated_at": utc_now(),
    }

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            status='queued',
            updated_at=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            utc_now(),
            compact_json(metadata),
            safe_int(row["id"]),
        ),
    )

    conn.commit()


def mark_error(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    error_text: str,
) -> None:
    metadata = queue_metadata(
        row
    )

    metadata["research_agent"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "action": "error",
        "error": norm(error_text)[:2000],
        "updated_at": utc_now(),
    }

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            status='queued',
            updated_at=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            utc_now(),
            compact_json(metadata),
            safe_int(row["id"]),
        ),
    )

    conn.commit()


# ---------------------------------------------------------------------------
# TASK PROCESS
# ---------------------------------------------------------------------------

def process_task(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> tuple[str, int | None]:
    context = reconstruct_context(
        conn,
        row,
    )

    task = context["task"]

    if task["task_type"] == "RULE_PROMOTION_REVIEW":
        mark_held(
            conn,
            row,
            "promotion review is not a research task",
        )
        return (
            "HELD_PROMOTION_REVIEW",
            None,
        )

    if not context_is_sufficient(
        task
    ):
        mark_held(
            conn,
            row,
            (
                "reliable research context could not be reconstructed"
            ),
        )
        return (
            "HELD_NO_CONTEXT",
            None,
        )

    print(
        f"  CONTEXT | "
        f"{task['symbol']} | "
        f"{task['method_name']} | "
        f"{task['market']} | "
        f"{task['timeframe']}"
    )

    if is_paper_evidence_task(
        task["task_type"]
    ):
        paper = task.get(
            "paper_evidence",
            {},
        )
        print(
            "  PAPER   | "
            f"strategy={norm(paper.get('strategy_id'))} "
            f"classification={norm(paper.get('classification'))} "
            f"symbols={len(paper.get('symbols', []))} "
            f"trades={safe_int(paper.get('total_trades'))}"
        )

    mark_working(
        conn,
        row,
    )

    validation = context[
        "validation"
    ]

    sources = local_knowledge_sources(
        conn,
        task,
    )

    items = local_knowledge_items(
        conn,
        task,
    )

    claims = local_claims(
        conn,
        task,
    )

    rules = local_rules(
        conn,
        task,
    )

    youtube_results = discover_youtube(
        task,
    )

    print(
        f"  EVIDENCE | "
        f"sources={len(sources)} "
        f"items={len(items)} "
        f"claims={len(claims)} "
        f"rules={len(rules)} "
        f"youtube={len(youtube_results)}"
    )

    packet = {
        "task": task,
        "paper_evidence": task.get(
            "paper_evidence"
        ),
        "validation": (
            task.get("validation_summary")
        ),
        "knowledge_sources": sources,
        "knowledge_items": items,
        "claims": claims,
        "rules": rules,
        "youtube_results": youtube_results,
    }

    print(
        "  SYNTHESIS | OpenAI..."
    )

    research_text, provider_status = call_openai(
        task=task,
        validation=task.get(
            "validation_summary"
        ),
        sources=sources,
        items=items,
        claims=claims,
        rules=rules,
        youtube_results=youtube_results,
    )

    if not research_text:
        research_text = local_brief(
            task=task,
            validation=task.get(
                "validation_summary"
            ),
            sources=sources,
            items=items,
            claims=claims,
            rules=rules,
            youtube_results=youtube_results,
        )

        if provider_status != "OPENAI_OK":
            provider_status = (
                "LOCAL_DETERMINISTIC"
            )

    print(
        "  SYNTHESIS | "
        + provider_status
    )

    episode_id = write_episode(
        conn,
        queue_id=safe_int(
            row["id"]
        ),
        task=task,
        research_text=research_text,
        provider_status=provider_status,
        evidence_packet=packet,
    )

    print(
        f"  EPISODE   | id={episode_id}"
    )

    event_id = write_research_event(
        conn,
        task=task,
        episode_id=episode_id,
        provider_status=provider_status,
    )

    print(
        f"  EVENT     | id={event_id}"
    )

    mark_completed(
        conn,
        row,
        episode_id,
    )

    conn.commit()

    return (
        "RESEARCH_COMPLETED",
        episode_id,
    )


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------

def print_summary(
    conn: sqlite3.Connection,
    selected: int,
    completed: int,
    held: int,
    errors: int,
    statuses: dict[str, int],
) -> None:
    queue_rows = conn.execute(
        """
        SELECT
            status,
            COUNT(*) AS n
        FROM brain_research_queue
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()

    episode_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM brain_episodes
        WHERE episode_type='research_agent_result'
        """
    ).fetchone()[0]

    print()
    print("=" * 76)
    print(
        "MARKETHQ BRAIN RESEARCH AGENT V4"
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
    print("RESEARCH AGENT V4 RUN")
    print("-" * 76)
    print(
        f"tasks_selected                       {selected}"
    )
    print(
        f"research_completed                   {completed}"
    )
    print(
        f"held_tasks                           {held}"
    )
    print(
        f"errors                               {errors}"
    )
    print()
    print("TASK STATUSES")
    print("-" * 76)

    if statuses:
        for key, value in statuses.items():
            print(
                f"{key:35s} {value}"
            )
    else:
        print(
            "No task statuses."
        )

    print()
    print("QUEUE STATUS")
    print("-" * 76)

    for row in queue_rows:
        print(
            f"{norm(row['status']):35s} "
            f"{safe_int(row['n'])}"
        )

    print()
    print(
        "research_agent_episodes               "
        f"{safe_int(episode_count)}"
    )

    print()
    print("RECENT RESEARCH RESULTS")
    print("-" * 76)

    recent = conn.execute(
        """
        SELECT
            id,
            source_id,
            title,
            content_hash,
            metadata_json
        FROM brain_episodes
        WHERE episode_type='research_agent_result'
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()

    if not recent:
        print(
            "No research-agent episodes."
        )
    else:
        for row in recent:
            metadata = parse_metadata(
                row["metadata_json"]
            )

            context = metadata.get(
                "reconstructed_context",
                {},
            )

            print(
                f"episode_id={row['id']} | "
                f"queue_id={row['source_id']} | "
                f"{norm(row['title'])}"
            )

            if context:
                print(
                    "  context="
                    f"{norm(context.get('symbol'))} | "
                    f"{norm(context.get('method_name'))} | "
                    f"{norm(context.get('market'))} | "
                    f"{norm(context.get('timeframe'))} | "
                    f"{norm(context.get('condition_name'))}"
                )

    print()
    print("IMPORTANT")
    print("-" * 76)
    print("- Eski UNKNOWN episode'lar korunur; yenisi bunların üzerine yazmaz.")
    print("- Yeni araştırma sonucu ayrı episode olarak saklanır.")
    print("- Context çözülemezse UNKNOWN episode üretilmez.")
    print("- Legacy promotion review task'ları research'e gönderilmez.")
    print("- Paper evidence review task'ları mevcut Research Agent üzerinden işlenir.")
    print("- Ham experiment/result verileri değiştirilmez.")
    print("- learned_rules / claims / validations değiştirilmez.")
    print("- Research sonucu doğrulanmış kural veya canlı işlem sinyali değildir.")
    print("- Sonraki aşama: research result -> knowledge/observation ingest.")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        required = (
            "brain_research_queue",
            "brain_episodes",
            "brain_learning_events",
            "learned_rules",
            "brain_rule_validations",
        )

        for table in required:
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: "
                    + table
                )

        ensure_episode_indexes(
            conn
        )

        queue_rows = load_queued_tasks(
            conn
        )

        completed = 0
        held = 0
        errors = 0

        statuses: dict[str, int] = {}

        for row in queue_rows:
            print()
            print("-" * 76)
            print(
                f"TASK queue_id={row['id']} | "
                f"type={get_task_type(row)}"
            )
            print(
                "  Q: "
                + norm(row["question"])
            )

            try:
                status, _episode_id = process_task(
                    conn,
                    row,
                )

                statuses[status] = (
                    statuses.get(
                        status,
                        0,
                    )
                    + 1
                )

                if status == "RESEARCH_COMPLETED":
                    completed += 1
                elif status.startswith("HELD"):
                    held += 1

            except Exception as exc:
                errors += 1

                error_text = (
                    f"{type(exc).__name__}: {exc}"
                )

                statuses[
                    "ERROR"
                ] = statuses.get(
                    "ERROR",
                    0,
                ) + 1

                print(
                    "  TASK ERROR | "
                    + error_text
                )

                traceback.print_exc()

                try:
                    mark_error(
                        conn,
                        row,
                        error_text,
                    )
                except Exception:
                    traceback.print_exc()

        print_summary(
            conn=conn,
            selected=len(queue_rows),
            completed=completed,
            held=held,
            errors=errors,
            statuses=statuses,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    run()

