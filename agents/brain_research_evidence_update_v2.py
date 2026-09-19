# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Evidence Update Engine V2
-------------------------------------------------
Evidence Review
    ↓
Brain update / provenance / research priority

AMAÇ
----
brain_research_evidence_reviews tablosundaki AI evidence review sonuçlarını
Brain'in mevcut katmanlarına kontrollü şekilde yansıtmak.

Bu motor:
    - observation değiştirmez
    - learned_rules değiştirmez
    - brain_claims değiştirmez
    - validations değiştirmez
    - raw experiment/result değiştirmez
    - research knowledge'ı verified yapmaz

Yalnızca ayrı bir update/audit tablosu ve gerekiyorsa
brain_research_queue kaydı oluşturur.

VERDICTS
--------
SUPPORTIVE
    -> research evidence alignment olumlu
    -> review sonucu brain audit'e yazılır
    -> sonraki recheck önceliği düşük/normal

PARTIALLY_SUPPORTIVE
    -> research ile observation kısmen uyumlu
    -> yeni "verified" statüsü verilmez
    -> ek bağımsız araştırma sorusu queue'ya alınır

CONTRADICTORY
    -> contradiction/review önceliği yükseltilir
    -> yeni research task oluşturulur

INSUFFICIENT
    -> evidence gap research task oluşturulur

Ayrı tablo:
    brain_research_brain_updates

Ayrıca research queue dedup kontrolü yapılır.

Çalıştırma:
    python agents/brain_research_evidence_update_v2.py
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

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_EVIDENCE_UPDATE"
ENGINE_VERSION = "V2.1"

PAPER_EVIDENCE_GAP_TASK_TYPE = "PAPER_EVIDENCE_GAP_RESEARCH"


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


def parse_json(raw: Any) -> dict[str, Any]:
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
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_update_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_research_brain_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            review_id INTEGER NOT NULL,
            knowledge_item_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,

            verdict TEXT NOT NULL,
            action TEXT NOT NULL,

            research_priority INTEGER NOT NULL DEFAULT 0,
            queue_task_id INTEGER,

            brain_effect TEXT NOT NULL,

            metadata_json TEXT,

            created_at TEXT NOT NULL,

            UNIQUE (review_id)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_review
        ON brain_research_brain_updates(review_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_observation
        ON brain_research_brain_updates(observation_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_research_updates_action
        ON brain_research_brain_updates(action)
        """
    )


# ---------------------------------------------------------------------------
# LOAD REVIEWS
# ---------------------------------------------------------------------------

def load_unprocessed_reviews(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                r.id,
                r.knowledge_item_id,
                r.observation_id,
                r.verdict,
                r.score,
                r.evidence_alignment,
                r.contradiction_flag,
                r.review_method,
                r.review_text,
                r.next_question,
                r.metadata_json,
                r.created_at,

                ki.title AS knowledge_title,
                ki.method AS knowledge_method,
                ki.metadata_json AS knowledge_metadata,

                o.symbol,
                o.method_name,
                o.market,
                o.timeframe,
                o.market_regime,
                o.volume_state,
                o.volatility_state,
                o.sample_size,
                o.confidence AS observation_confidence,
                o.status AS observation_status

            FROM brain_research_evidence_reviews r

            JOIN knowledge_items ki
              ON ki.id=r.knowledge_item_id

            JOIN brain_observations o
              ON o.id=r.observation_id

            LEFT JOIN brain_research_brain_updates u
              ON u.review_id=r.id

            WHERE u.id IS NULL

            ORDER BY
                CASE
                    WHEN r.verdict='CONTRADICTORY' THEN 1
                    WHEN r.verdict='INSUFFICIENT' THEN 2
                    WHEN r.verdict='PARTIALLY_SUPPORTIVE' THEN 3
                    WHEN r.verdict='SUPPORTIVE' THEN 4
                    ELSE 5
                END,
                r.score ASC,
                r.id ASC

            LIMIT 50
            """
        ).fetchall()
    )



def load_paper_gap_reviews(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """Load previously reviewed paper-evidence gaps for strategy-level regrouping."""
    rows = conn.execute(
        """
        SELECT
            r.id, r.knowledge_item_id, r.observation_id, r.verdict, r.score,
            r.evidence_alignment, r.contradiction_flag, r.review_method,
            r.review_text, r.next_question, r.metadata_json, r.created_at,
            ki.title AS knowledge_title,
            ki.method AS knowledge_method,
            ki.metadata_json AS knowledge_metadata,
            o.symbol, o.method_name, o.market, o.timeframe,
            o.market_regime, o.volume_state, o.volatility_state,
            o.sample_size, o.confidence AS observation_confidence,
            o.status AS observation_status
        FROM brain_research_evidence_reviews r
        JOIN knowledge_items ki ON ki.id=r.knowledge_item_id
        JOIN brain_observations o ON o.id=r.observation_id
        WHERE UPPER(TRIM(COALESCE(r.verdict, '')))='INSUFFICIENT'
          AND (
                LOWER(COALESCE(r.metadata_json, '')) LIKE '%paper_evidence%'
             OR LOWER(COALESCE(r.metadata_json, '')) LIKE '%strategy_id%'
             OR LOWER(COALESCE(ki.metadata_json, '')) LIKE '%paper_evidence%'
             OR LOWER(COALESCE(ki.metadata_json, '')) LIKE '%strategy_id%'
          )
        ORDER BY r.knowledge_item_id ASC, r.id ASC
        """
    ).fetchall()

    paper_markers = {
        'PAPER_EVIDENCE_WEAK_REVIEW',
        'PAPER_EVIDENCE_MIXED_REVIEW',
        'PAPER_EVIDENCE_INSUFFICIENT_DATA',
        'PAPER_EVIDENCE_PROMISING_VALIDATION',
        'PAPER_EVIDENCE_GAP_RESEARCH',
    }

    selected: list[sqlite3.Row] = []
    for row in rows:
        dictionaries = [
            *recursive_dicts(parse_json_dict(row['metadata_json'])),
            *recursive_dicts(parse_json_dict(row['knowledge_metadata'])),
        ]
        task_types = {
            norm(data.get('task_type')).upper()
            for data in dictionaries
            if norm(data.get('task_type'))
        }
        has_marker = bool(task_types & paper_markers)
        has_paper_block = any(
            'paper_evidence' in data
            or 'paper_classification' in data
            or 'paper_strategy_id' in data
            for data in dictionaries
        )
        if has_marker or has_paper_block:
            selected.append(row)

    return selected


# ---------------------------------------------------------------------------
# ACTION POLICY
# ---------------------------------------------------------------------------

def action_for_verdict(
    verdict: str,
) -> tuple[str, int, str]:
    verdict = norm(
        verdict
    ).upper()

    if verdict == "SUPPORTIVE":
        return (
            "RECORD_SUPPORT",
            3,
            (
                "Research knowledge is aligned with the linked "
                "historical observation, but verification state "
                "remains unchanged."
            ),
        )

    if verdict == "PARTIALLY_SUPPORTIVE":
        return (
            "QUEUE_INDEPENDENT_RECHECK",
            6,
            (
                "Research and observation are partially aligned; "
                "additional independent evidence is needed."
            ),
        )

    if verdict == "CONTRADICTORY":
        return (
            "QUEUE_CONTRADICTION_RESEARCH",
            9,
            (
                "Research evidence indicates a contradiction or "
                "conflict requiring focused research."
            ),
        )

    if verdict == "INSUFFICIENT":
        return (
            "QUEUE_EVIDENCE_GAP_RESEARCH",
            8,
            (
                "Available evidence is insufficient for a strong "
                "judgment; additional evidence is required."
            ),
        )

    return (
        "QUEUE_REVIEW",
        5,
        "Unknown verdict requires manual research review.",
    )


# ---------------------------------------------------------------------------
# QUEUE DEDUP
# ---------------------------------------------------------------------------

def queue_exists_for_review(
    conn: sqlite3.Connection,
    review_id: int,
) -> int | None:
    marker = (
        f'"review_id":{review_id}'
    )

    row = conn.execute(
        """
        SELECT id
        FROM brain_research_queue
        WHERE metadata_json LIKE ?
          AND status IN ('queued', 'working')
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            f"%{marker}%",
        ),
    ).fetchone()

    if row:
        return safe_int(
            row["id"]
        )

    return None



# ---------------------------------------------------------------------------
# PAPER EVIDENCE CONTEXT
# ---------------------------------------------------------------------------

def parse_json_dict(value: Any) -> dict[str, Any]:
    try:
        obj = json.loads(norm(value) or "{}")
        return obj if isinstance(obj, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def recursive_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(recursive_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(recursive_dicts(child))

    return found


def first_value(
    dictionaries: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> Any:
    for data in dictionaries:
        for key in keys:
            if key in data and data[key] not in (None, "", [], {}):
                return data[key]
    return None


def normalize_symbols(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[,;|]", value)
    elif isinstance(value, list):
        parts = value
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()

    for part in parts:
        symbol = norm(part)
        if not symbol:
            continue
        key = symbol.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(symbol)

    return result


def extract_paper_evidence(
    reviews: list[sqlite3.Row],
) -> dict[str, Any] | None:
    """
    Aggregate the evidence context for one knowledge item.

    Priority:
      1) review/knowledge metadata carrying explicit paper evidence
      2) review rows for authoritative symbol coverage
      3) knowledge title/method as strategy-name fallback

    This function never invents performance metrics.
    Missing metrics remain zero/empty and are marked as unavailable.
    """
    if not reviews:
        return None

    dictionaries: list[dict[str, Any]] = []
    titles: list[str] = []
    methods: list[str] = []

    for review in reviews:
        review_meta = parse_json_dict(review["metadata_json"])
        knowledge_meta = parse_json_dict(review["knowledge_metadata"])

        dictionaries.extend(recursive_dicts(review_meta))
        dictionaries.extend(recursive_dicts(knowledge_meta))

        title = norm(review["knowledge_title"])
        method = norm(review["knowledge_method"])

        if title:
            titles.append(title)
        if method:
            methods.append(method)

    task_types = {
        norm(d.get("task_type")).upper()
        for d in dictionaries
        if norm(d.get("task_type"))
    }

    # The research result/ingest path identifies paper evidence with these
    # task types. Do not convert arbitrary observations into paper evidence.
    paper_markers = {
        "PAPER_EVIDENCE_WEAK_REVIEW",
        "PAPER_EVIDENCE_MIXED_REVIEW",
        "PAPER_EVIDENCE_INSUFFICIENT_DATA",
        "PAPER_EVIDENCE_PROMISING_VALIDATION",
        "PAPER_EVIDENCE_GAP_RESEARCH",
    }

    has_paper_marker = bool(task_types & paper_markers)

    explicit_symbols = normalize_symbols(
        first_value(
            dictionaries,
            ("symbols", "paper_symbols"),
        )
    )

    review_symbols = normalize_symbols(
        [norm(row["symbol"]) for row in reviews]
    )

    symbols = explicit_symbols or review_symbols

    strategy_id = norm(
        first_value(
            dictionaries,
            ("strategy_id", "paper_strategy_id"),
        )
    )

    strategy_name = norm(
        first_value(
            dictionaries,
            ("strategy_name", "paper_strategy_name"),
        )
    )

    if not strategy_id:
        joined = " ".join(
            [
                *titles,
                *methods,
                *[
                    norm(row["review_text"])
                    for row in reviews
                ],
                *[
                    norm(row["next_question"])
                    for row in reviews
                ],
            ]
        )
        match = re.search(
            r"\bSTR-[A-Z0-9]{6,}\b",
            joined,
            flags=re.IGNORECASE,
        )
        if match:
            strategy_id = match.group(0).upper()

    if not strategy_name:
        strategy_name = (
            titles[0]
            if titles
            else (
                methods[0]
                if methods
                else ""
            )
        )

    classification = norm(
        first_value(
            dictionaries,
            ("classification", "paper_classification"),
        )
    ).upper()

    if not classification:
        # Evidence reviews themselves may not carry the aggregate
        # classification. Keep this as a neutral label rather than inventing
        # a stronger conclusion.
        classification = "INSUFFICIENT_PAPER_EVIDENCE"

    def number(keys: tuple[str, ...]) -> float:
        value = first_value(dictionaries, keys)
        return safe_float(value)

    def integer(keys: tuple[str, ...]) -> int:
        value = first_value(dictionaries, keys)
        return safe_int(value)

    raw_runs = integer(("raw_runs", "runs"))
    unique_runs = integer(("unique_runs",))
    total_trades = integer(("total_trades",))
    win_rate = number(("win_rate",))
    aggregate_net_pnl = number(("aggregate_net_pnl",))
    aggregate_return = number(("aggregate_return",))
    average_run_return = number(
        ("average_run_return", "avg_run_return")
    )
    median_run_return = number(("median_run_return",))
    average_profit_factor = number(
        ("average_profit_factor", "avg_profit_factor")
    )
    worst_profit_factor = number(("worst_profit_factor",))
    average_max_drawdown = number(("average_max_drawdown",))
    worst_max_drawdown = number(("worst_max_drawdown",))

    reasons_value = first_value(
        dictionaries,
        ("reasons", "reason_list"),
    )
    if isinstance(reasons_value, list):
        reasons = [
            norm(x)
            for x in reasons_value
            if norm(x)
        ]
    elif isinstance(reasons_value, str):
        reasons = [
            x.strip()
            for x in re.split(r"[;\n|]", reasons_value)
            if x.strip()
        ]
    else:
        reasons = []

    period = norm(
        first_value(
            dictionaries,
            ("period", "paper_period"),
        )
    )
    interval = norm(
        first_value(
            dictionaries,
            ("interval",),
        )
    )

    market = norm(
        first_value(
            dictionaries,
            ("market",),
        )
    )

    if not market:
        if symbols and all(
            symbol.upper().endswith(".IS")
            for symbol in symbols
        ):
            market = "BIST"
        elif symbols:
            market = "MULTI_MARKET"

    # Only treat the record as paper evidence if the provenance actually
    # identifies it as such. This avoids converting ordinary reviews.
    if not has_paper_marker and not strategy_id:
        return None

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "classification": classification,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "raw_runs": raw_runs,
        "unique_runs": unique_runs,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "aggregate_net_pnl": aggregate_net_pnl,
        "aggregate_return": aggregate_return,
        "average_run_return": average_run_return,
        "median_run_return": median_run_return,
        "average_profit_factor": average_profit_factor,
        "worst_profit_factor": worst_profit_factor,
        "average_max_drawdown": average_max_drawdown,
        "worst_max_drawdown": worst_max_drawdown,
        "period": period,
        "interval": interval,
        "market": market,
        "reasons": reasons,
        "source_review_ids": [
            safe_int(row["id"])
            for row in reviews
        ],
        "source_observation_ids": [
            safe_int(row["observation_id"])
            for row in reviews
        ],
    }


def active_paper_gap_queue(
    conn: sqlite3.Connection,
    strategy_id: str,
    knowledge_item_id: int,
) -> int | None:
    if not strategy_id:
        return None

    rows = conn.execute(
        """
        SELECT id, metadata_json
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
          AND metadata_json LIKE ?
        ORDER BY id DESC
        """,
        (f'%{strategy_id}%',),
    ).fetchall()

    for row in rows:
        metadata = parse_json_dict(row["metadata_json"])
        task_type = norm(metadata.get("task_type")).upper()

        if task_type != PAPER_EVIDENCE_GAP_TASK_TYPE:
            continue

        if (
            safe_int(metadata.get("knowledge_item_id"))
            == knowledge_item_id
        ):
            return safe_int(row["id"])

    return None


def create_grouped_paper_gap_task(
    conn: sqlite3.Connection,
    reviews: list[sqlite3.Row],
) -> tuple[int | None, bool]:
    """
    Create one strategy-level paper evidence gap task for a group of
    insufficient reviews.

    Returns:
        (queue_id, created)
    """
    paper = extract_paper_evidence(reviews)

    if not paper:
        return None, False

    knowledge_item_id = safe_int(
        reviews[0]["knowledge_item_id"]
    )
    strategy_id = norm(paper.get("strategy_id"))
    strategy_name = norm(paper.get("strategy_name"))

    existing = active_paper_gap_queue(
        conn,
        strategy_id,
        knowledge_item_id,
    )

    if existing:
        return existing, False

    symbols = paper.get("symbols", [])

    scope = (
        ", ".join(symbols)
        if symbols
        else "MULTI_SYMBOL"
    )

    question = (
        "Collect independent strategy-level evidence for "
        f"{strategy_name or 'the paper-tested strategy'}"
        + (
            f" ({strategy_id})"
            if strategy_id
            else ""
        )
        + ". "
        "Re-run or identify an independent historical backtest/WFO "
        "with the same symbols, periods, entry/exit rules and cost "
        "assumptions, and separate the results by symbol and market "
        "regime. Determine whether the evidence gap can be resolved."
    )

    reason = (
        "Generated by grouped evidence-gap Brain Update V2. "
        f"knowledge_item_id={knowledge_item_id}; "
        f"insufficient_reviews={len(reviews)}; "
        f"symbols={scope}. "
        "This is a research task, not a live trading instruction."
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "task_role": "strategy_level_research_followup",
        "task_type": PAPER_EVIDENCE_GAP_TASK_TYPE,
        "research_scope": "STRATEGY_PAPER_EVIDENCE_GAP",
        "generated_from_evidence_reviews": True,
        "knowledge_item_id": knowledge_item_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "classification": norm(
            paper.get("classification")
        ),
        "symbols": symbols,
        "symbol_count": safe_int(
            paper.get("symbol_count"),
            len(symbols),
        ),
        "raw_runs": safe_int(paper.get("raw_runs")),
        "unique_runs": safe_int(paper.get("unique_runs")),
        "total_trades": safe_int(paper.get("total_trades")),
        "win_rate": safe_float(paper.get("win_rate")),
        "aggregate_net_pnl": safe_float(
            paper.get("aggregate_net_pnl")
        ),
        "aggregate_return": safe_float(
            paper.get("aggregate_return")
        ),
        "average_run_return": safe_float(
            paper.get("average_run_return")
        ),
        "median_run_return": safe_float(
            paper.get("median_run_return")
        ),
        "average_profit_factor": safe_float(
            paper.get("average_profit_factor")
        ),
        "worst_profit_factor": safe_float(
            paper.get("worst_profit_factor")
        ),
        "average_max_drawdown": safe_float(
            paper.get("average_max_drawdown")
        ),
        "worst_max_drawdown": safe_float(
            paper.get("worst_max_drawdown")
        ),
        "period": norm(paper.get("period")),
        "interval": norm(paper.get("interval")),
        "market": norm(paper.get("market")),
        "reasons": paper.get("reasons", []),
        "source_review_ids": paper.get("source_review_ids", []),
        "source_observation_ids": paper.get(
            "source_observation_ids",
            [],
        ),
        "paper_evidence": paper,
        "verification_changed": False,
        "execution_enabled": False,
        "research_only": True,
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_queue (
            question,
            reason,
            priority,
            target_node_id,
            target_claim_id,
            status,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, 8, NULL, NULL, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            utc_now(),
            utc_now(),
            compact_json(metadata),
        ),
    )

    # Persist this strategy-level task immediately. A run may have no later
    # review-level writes/commits, so relying on the end-of-run transaction
    # would roll the queue insert back when the process exits.
    conn.commit()

    return safe_int(cur.lastrowid), True


# ---------------------------------------------------------------------------
# CREATE RESEARCH TASK
# ---------------------------------------------------------------------------

def create_research_task(
    conn: sqlite3.Connection,
    review: sqlite3.Row,
    action: str,
    priority: int,
) -> int | None:
    """
    PARTIAL / CONTRADICTORY / INSUFFICIENT durumlarında
    kontrollü bir research task üretir.
    SUPPORTIVE için yeni queue açılmaz.
    """

    if action == "RECORD_SUPPORT":
        return None

    existing = queue_exists_for_review(
        conn,
        safe_int(review["id"]),
    )

    if existing:
        return existing

    verdict = norm(
        review["verdict"]
    )

    symbol = norm(
        review["symbol"]
    )

    method = norm(
        review["method_name"]
    )

    market = norm(
        review["market"]
    )

    timeframe = norm(
        review["timeframe"]
    )

    next_question = norm(
        review["next_question"]
    )

    if action == "QUEUE_CONTRADICTION_RESEARCH":
        question = (
            "Investigate contradiction: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    elif action == "QUEUE_EVIDENCE_GAP_RESEARCH":
        question = (
            "Collect additional evidence: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    else:
        question = (
            "Recheck research finding independently: "
            f"{symbol} | {method} | "
            f"{market} | {timeframe}"
        )

    if next_question:
        question = (
            question
            + " | "
            + next_question[:700]
        )

    reason = (
        "Generated from brain evidence review. "
        f"review_id={safe_int(review['id'])}; "
        f"verdict={verdict}; "
        f"score={safe_float(review['score']):.4f}; "
        f"observation_id={safe_int(review['observation_id'])}; "
        f"knowledge_item_id={safe_int(review['knowledge_item_id'])}. "
        "This is a research task, not a live trading instruction."
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "task_role": "research_followup",
        "review_id": safe_int(
            review["id"]
        ),
        "knowledge_item_id": safe_int(
            review["knowledge_item_id"]
        ),
        "observation_id": safe_int(
            review["observation_id"]
        ),
        "verdict": verdict,
        "score": safe_float(
            review["score"]
        ),
        "task_type": (
            "CONTRADICTION_RESEARCH"
            if action
            == "QUEUE_CONTRADICTION_RESEARCH"
            else (
                "INSUFFICIENT_DATA_RESEARCH"
                if action
                == "QUEUE_EVIDENCE_GAP_RESEARCH"
                else "VALIDATED_RULE_RECHECK"
            )
        ),
        "symbol": symbol,
        "method_name": method,
        "market": market,
        "timeframe": timeframe,
        "generated_from_evidence_review": True,
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_queue (
            question,
            reason,
            priority,
            target_node_id,
            target_claim_id,
            status,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            priority,
            utc_now(),
            utc_now(),
            compact_json(
                metadata
            ),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# WRITE UPDATE
# ---------------------------------------------------------------------------

def update_exists(
    conn: sqlite3.Connection,
    review_id: int,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM brain_research_brain_updates
            WHERE review_id=?
            LIMIT 1
            """,
            (review_id,),
        ).fetchone()
        is not None
    )


def write_update(
    conn: sqlite3.Connection,
    review: sqlite3.Row,
    action: str,
    priority: int,
    brain_effect: str,
    queue_task_id: int | None,
) -> int:
    review_id = safe_int(
        review["id"]
    )

    if update_exists(
        conn,
        review_id,
    ):
        existing = conn.execute(
            """
            SELECT id
            FROM brain_research_brain_updates
            WHERE review_id=?
            LIMIT 1
            """,
            (review_id,),
        ).fetchone()

        return safe_int(
            existing["id"]
        )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "review_method": norm(
            review["review_method"]
        ),
        "review_score": safe_float(
            review["score"]
        ),
        "contradiction_flag": safe_int(
            review["contradiction_flag"]
        ),
        "knowledge_item_id": safe_int(
            review["knowledge_item_id"]
        ),
        "observation_id": safe_int(
            review["observation_id"]
        ),
        "queue_task_id": queue_task_id,
        "verification_changed": False,
        "brain_effect": brain_effect,
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_brain_updates (
            review_id,
            knowledge_item_id,
            observation_id,
            verdict,
            action,
            research_priority,
            queue_task_id,
            brain_effect,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            safe_int(
                review["knowledge_item_id"]
            ),
            safe_int(
                review["observation_id"]
            ),
            norm(
                review["verdict"]
            ),
            action,
            priority,
            queue_task_id,
            brain_effect,
            compact_json(
                metadata
            ),
            utc_now(),
        ),
    )

    return safe_int(
        cur.lastrowid
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        required = (
            "brain_research_evidence_reviews",
            "brain_research_observation_links",
            "brain_research_queue",
            "knowledge_items",
            "brain_observations",
        )

        for table in required:
            if not table_exists(conn, table):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: " + table
                )

        ensure_update_table(conn)

        reviews = load_unprocessed_reviews(conn)

        # Migration-safe scan: V1 already processed the 20 paper reviews,
        # so they are absent from load_unprocessed_reviews(). V2 scans all
        # INSUFFICIENT paper-provenance reviews and consolidates them.
        paper_gap_reviews = load_paper_gap_reviews(conn)

        paper_groups: dict[int, list[sqlite3.Row]] = {}
        for review in paper_gap_reviews:
            key = safe_int(review["knowledge_item_id"])
            paper_groups.setdefault(key, []).append(review)

        grouped_queue_ids: dict[int, int | None] = {}

        for knowledge_item_id, group in paper_groups.items():
            queue_id, created = create_grouped_paper_gap_task(conn, group)
            grouped_queue_ids[knowledge_item_id] = queue_id

            if queue_id is not None:
                print(
                    f"GROUPED_PAPER_GAP | knowledge={knowledge_item_id} | "
                    f"reviews={len(group)} | queue={queue_id} | created={created}"
                )

        paper_gap_review_ids = {
            safe_int(row["id"]) for row in paper_gap_reviews
        }

        processed = 0
        supportive = 0
        partial = 0
        contradictory = 0
        insufficient = 0
        queue_created = 0
        queue_existing = 0
        errors = 0

        for review in reviews:
            review_id = safe_int(review["id"])

            try:
                verdict = norm(review["verdict"]).upper()
                action, priority, brain_effect = action_for_verdict(verdict)

                if (
                    action != "RECORD_SUPPORT"
                    and review_id in paper_gap_review_ids
                ):
                    queue_task_id = grouped_queue_ids.get(
                        safe_int(review["knowledge_item_id"])
                    )
                else:
                    queue_task_id = create_research_task(
                        conn,
                        review,
                        action,
                        priority,
                    )

                if (
                    action != "RECORD_SUPPORT"
                    and queue_task_id is not None
                    and review_id not in paper_gap_review_ids
                ):
                    existing_marker = queue_exists_for_review(
                        conn,
                        review_id,
                    )
                    if (
                        existing_marker is not None
                        and existing_marker != queue_task_id
                    ):
                        queue_existing += 1
                    else:
                        queue_created += 1

                update_id = write_update(
                    conn,
                    review,
                    action,
                    priority,
                    brain_effect,
                    queue_task_id,
                )

                conn.commit()
                processed += 1

                if verdict == "SUPPORTIVE":
                    supportive += 1
                elif verdict == "PARTIALLY_SUPPORTIVE":
                    partial += 1
                elif verdict == "CONTRADICTORY":
                    contradictory += 1
                elif verdict == "INSUFFICIENT":
                    insufficient += 1

                print(
                    f"UPDATED | review={review_id} | "
                    f"{norm(review['symbol'])} | {verdict} | "
                    f"action={action} | priority={priority} | "
                    f"queue={queue_task_id} | update={update_id}"
                )

            except Exception as exc:
                errors += 1
                conn.rollback()
                print(
                    f"ERROR | review={review_id} | "
                    f"{type(exc).__name__}: {exc}"
                )

        total_updates = conn.execute(
            "SELECT COUNT(*) FROM brain_research_brain_updates"
        ).fetchone()[0]

        active_research_queue = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_queue
            WHERE status IN ('queued', 'working')
            """
        ).fetchone()[0]

        print()
        print("=" * 76)
        print("MARKETHQ BRAIN RESEARCH EVIDENCE UPDATE ENGINE V2")
        print("=" * 76)
        print()
        print(f"Database : {DB_PATH}")
        print(f"Engine   : {ENGINE_NAME}")
        print(f"Version  : {ENGINE_VERSION}")
        print()
        print("BRAIN UPDATE RUN")
        print("-" * 76)
        print(f"reviews_seen                           {len(reviews)}")
        print(f"paper_gap_reviews_seen                  {len(paper_gap_reviews)}")
        print(f"paper_gap_groups                        {len(paper_groups)}")
        print(f"reviews_processed                      {processed}")
        print(f"supportive                             {supportive}")
        print(f"partially_supportive                   {partial}")
        print(f"contradictory                          {contradictory}")
        print(f"insufficient                           {insufficient}")
        print(f"queue_tasks_created                    {queue_created}")
        print(f"queue_tasks_existing                   {queue_existing}")
        print(f"errors                               {errors}")
        print()
        print(
            f"total_brain_research_updates           "
            f"{safe_int(total_updates)}"
        )
        print(
            f"active_research_queue                  "
            f"{safe_int(active_research_queue)}"
        )

        print()
        print("RECENT BRAIN UPDATES")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                u.id,
                u.review_id,
                u.knowledge_item_id,
                u.observation_id,
                u.verdict,
                u.action,
                u.research_priority,
                u.queue_task_id,
                o.symbol,
                o.method_name
            FROM brain_research_brain_updates u
            JOIN brain_observations o ON o.id=u.observation_id
            ORDER BY u.id DESC
            LIMIT 10
            """
        ).fetchall()

        if not recent:
            print("No brain updates.")
        else:
            for row in recent:
                print(
                    f"update_id={safe_int(row['id'])} | "
                    f"review={safe_int(row['review_id'])} | "
                    f"{norm(row['symbol'])} | "
                    f"{norm(row['verdict'])} | "
                    f"{norm(row['action'])} | "
                    f"priority={safe_int(row['research_priority'])} | "
                    f"queue={safe_int(row['queue_task_id'])}"
                )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- V1'in eski observation-level queue kayıtları silinmez.")
        print("- V2 aynı paper evidence için tek strategy-level gap task üretir.")
        print("- Review/update audit kayıtları değiştirilmez.")
        print("- learned_rules / claims / validations değiştirilmez.")
        print("- Verification state değiştirilmez.")
        print("- Research-only; canlı işlem veya broker execution yoktur.")

    finally:
        conn.close()


if __name__ == "__main__":
    run()

