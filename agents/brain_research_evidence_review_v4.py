# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Evidence Review Engine V4
--------------------------------------------------
Canonical research-derived knowledge + original observation
        ↓
AI / deterministic evidence review
        ↓
SUPPORTIVE / PARTIALLY_SUPPORTIVE / CONTRADICTORY / INSUFFICIENT
        ↓
review memory

AMAÇ
----
Research Agent'ın ürettiği "research_derived" knowledge'ın, bağlandığı
brain_observation ile gerçekten uyumlu olup olmadığını ayrı bir denetim
katmanında saklamak.

Bu motor:
    - research knowledge'ı verified yapmaz.
    - observation'ı değiştirmez.
    - claim'i değiştirmez.
    - learned_rule'u değiştirmez.
    - validation'ı değiştirmez.
    - raw experiment/result kayıtlarını değiştirmez.

Ayrı tablo:
    brain_research_evidence_reviews

Her review:
    knowledge_item_id
    observation_id
    verdict
    score
    evidence_alignment
    contradiction_flag
    review_method
    review_text
    next_question
    metadata_json
    created_at

AI varsa:
    OpenAI Responses API ile review.

AI yoksa / çağrı başarısızsa:
    deterministic reviewer kullanılır.

ÖNEMLİ
------
Bu katman:
    research result -> "doğru"
demek yerine:
    research result -> observation ile ne kadar uyumlu?
sorusunu cevaplar.

Çalıştırma:
    python agents/brain_research_evidence_review_v1.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
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

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_EVIDENCE_REVIEW"
ENGINE_VERSION = "V4.1"

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "",
).strip()

REVIEW_MODEL = os.getenv(
    "MARKETHQ_REVIEW_MODEL",
    os.getenv(
        "MARKETHQ_RESEARCH_MODEL",
        os.getenv(
            "OPENAI_MODEL",
            "gpt-5.6-luna",
        ),
    ),
).strip()

BATCH_LIMIT = max(
    1,
    int(
        os.getenv(
            "BRAIN_RESEARCH_REVIEW_BATCH",
            "20",
        )
    ),
)


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


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_review_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_research_evidence_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            knowledge_item_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,

            verdict TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,

            evidence_alignment TEXT,
            contradiction_flag INTEGER NOT NULL DEFAULT 0,

            review_method TEXT NOT NULL,

            review_text TEXT NOT NULL,
            next_question TEXT,

            metadata_json TEXT,

            created_at TEXT NOT NULL,

            UNIQUE (
                knowledge_item_id,
                observation_id
            )
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_research_evidence_reviews_knowledge
        ON brain_research_evidence_reviews(
            knowledge_item_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_research_evidence_reviews_observation
        ON brain_research_evidence_reviews(
            observation_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_research_evidence_reviews_verdict
        ON brain_research_evidence_reviews(
            verdict
        )
        """
    )


def ensure_strategy_review_table(
    conn: sqlite3.Connection,
) -> None:
    """Create the dedicated strategy-level independent-evidence review table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_research_strategy_evidence_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_item_id INTEGER NOT NULL UNIQUE,
            strategy_id TEXT,
            strategy_name TEXT,
            verdict TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            evidence_alignment TEXT,
            contradiction_flag INTEGER NOT NULL DEFAULT 0,
            review_method TEXT NOT NULL,
            review_text TEXT NOT NULL,
            next_question TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_strategy_evidence_reviews_strategy
        ON brain_research_strategy_evidence_reviews(
            strategy_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_strategy_evidence_reviews_verdict
        ON brain_research_strategy_evidence_reviews(
            verdict
        )
        """
    )


# ---------------------------------------------------------------------------
# SCHEMA HELPERS
# ---------------------------------------------------------------------------

def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """Return live SQLite table columns; never assume optional fields exist."""
    if not table_exists(conn, table_name):
        return set()

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        norm(row["name"])
        for row in rows
    }


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_review_candidates(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """
    Load bridge candidates without assuming a fixed brain_observations schema.

    The first V1 implementation referenced optional observation columns
    directly (avg_return_1d, avg_return_5d, etc.). The live database may
    contain a smaller/different observation schema, so V2 builds the SELECT
    list from PRAGMA table_info and supplies NULL aliases for missing fields.

    This keeps the evidence-review layer schema-compatible without changing
    brain_observations.
    """
    obs_cols = table_columns(
        conn,
        "brain_observations",
    )

    required_base = {
        "id",
        "method_name",
        "symbol",
        "market",
        "timeframe",
    }

    missing_base = sorted(
        required_base - obs_cols
    )

    if missing_base:
        raise RuntimeError(
            "brain_observations eksik temel kolonlar: "
            + ", ".join(missing_base)
        )

    # These fields are used by the reviewer when available. Missing fields
    # are projected as NULL AS <alias>, so downstream packet construction
    # remains stable.
    optional_observation_fields = [
        "market_regime",
        "volume_state",
        "volatility_state",
        "sample_size",
        "positive_count",
        "negative_count",
        "neutral_count",
        "positive_rate",
        "avg_return_1d",
        "avg_return_5d",
        "avg_return_20d",
        "median_return_20d",
        "best_return_20d",
        "worst_return_20d",
        "avg_mfe",
        "avg_mae",
        "confidence",
        "status",
        "observation_text",
        "metadata_json",
    ]

    observation_select_parts = [
        (
            f"o.{column} AS {column}"
            if column in obs_cols
            else f"NULL AS {column}"
        )
        for column in optional_observation_fields
    ]

    # Keep the core observation fields explicit.
    observation_select = [
        "o.method_name AS method_name",
        "o.symbol AS symbol",
        "o.market AS market",
        "o.timeframe AS timeframe",
        *observation_select_parts,
    ]

    confidence_order = (
        "o.confidence DESC"
        if "confidence" in obs_cols
        else "0 DESC"
    )
    sample_order = (
        "o.sample_size DESC"
        if "sample_size" in obs_cols
        else "0 DESC"
    )

    sql = f"""
        SELECT
            l.id AS link_id,
            l.knowledge_item_id,
            l.observation_id,
            l.match_type,
            l.match_score,

            ki.title AS knowledge_title,
            ki.content AS knowledge_content,
            ki.summary AS knowledge_summary,
            ki.method AS knowledge_method,
            ki.confidence AS knowledge_confidence,
            ki.metadata_json AS knowledge_metadata,

            {", ".join(observation_select)}

        FROM brain_research_observation_links l

        JOIN knowledge_items ki
          ON ki.id=l.knowledge_item_id

        JOIN brain_observations o
          ON o.id=l.observation_id

        LEFT JOIN brain_research_evidence_reviews r
          ON r.knowledge_item_id=l.knowledge_item_id
         AND r.observation_id=l.observation_id

        WHERE
            r.id IS NULL
            AND l.verified=0

        ORDER BY
            l.match_score DESC,
            {confidence_order},
            {sample_order},
            l.id ASC

        LIMIT ?
    """

    try:
        return list(
            conn.execute(
                sql,
                (
                    BATCH_LIMIT,
                ),
            ).fetchall()
        )
    except sqlite3.OperationalError as exc:
        # A second defensive fallback for databases where an ordering column
        # is also absent. Re-run with a schema-safe ORDER BY.
        message = str(exc).lower()

        if (
            "no such column" not in message
            or (
                "confidence" not in message
                and "sample_size" not in message
            )
        ):
            raise

        order_parts = [
            "l.match_score DESC",
        ]

        if "confidence" in obs_cols:
            order_parts.append(
                "o.confidence DESC"
            )

        if "sample_size" in obs_cols:
            order_parts.append(
                "o.sample_size DESC"
            )

        order_parts.append(
            "l.id ASC"
        )

        sql_fallback = sql.replace(
            """
        ORDER BY
            l.match_score DESC,
            o.confidence DESC,
            o.sample_size DESC,
            l.id ASC
            """,
            "ORDER BY\n            "
            + ",\n            ".join(order_parts),
        )

        return list(
            conn.execute(
                sql_fallback,
                (
                    BATCH_LIMIT,
                ),
            ).fetchall()
        )


def load_independent_strategy_candidates(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """Find strategy-level independent evidence knowledge without using observations."""
    cols = table_columns(conn, "knowledge_items")
    source_cols = table_columns(conn, "knowledge_sources")

    required = {"id", "title", "content", "metadata_json"}
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(
            "knowledge_items eksik temel kolonlar: " + ", ".join(missing)
        )

    source_join = ""
    source_select = "NULL AS source_title"
    if "source_id" in cols and table_exists(conn, "knowledge_sources"):
        if "title" in source_cols:
            source_select = "ks.title AS source_title"
        source_join = "LEFT JOIN knowledge_sources ks ON ks.id=ki.source_id"

    existing_table = "brain_research_strategy_evidence_reviews"
    if not table_exists(conn, existing_table):
        raise RuntimeError("Strategy evidence review table oluşturulamadı.")

    tag_expr = ""
    if "tags_json" in cols:
        tag_expr = "OR lower(COALESCE(ki.tags_json, '')) LIKE '%independent_evidence%'"

    sql = f"""
        SELECT
            ki.id AS knowledge_item_id,
            ki.title AS knowledge_title,
            ki.content AS knowledge_content,
            ki.summary AS knowledge_summary,
            ki.method AS knowledge_method,
            ki.confidence AS knowledge_confidence,
            ki.metadata_json AS knowledge_metadata,
            {source_select}
        FROM knowledge_items ki
        {source_join}
        LEFT JOIN {existing_table} sr
          ON sr.knowledge_item_id=ki.id
        WHERE sr.id IS NULL
          AND (
                lower(COALESCE(ki.title, '')) LIKE '%independent%_evidence%'
                {tag_expr}
                OR lower(COALESCE({source_select.split(' AS ')[0]}, '')) LIKE '%independent strategy evidence%'
          )
        ORDER BY ki.id ASC
    """

    try:
        return list(conn.execute(sql).fetchall())
    except sqlite3.OperationalError:
        # Conservative fallback: inspect only text columns already known to exist.
        title_expr = "COALESCE(ki.title, '')" if "title" in cols else "''"
        meta_expr = "COALESCE(ki.metadata_json, '')" if "metadata_json" in cols else "''"
        content_expr = "COALESCE(ki.content, '')" if "content" in cols else "''"
        fallback_sql = f"""
            SELECT
                ki.id AS knowledge_item_id,
                {title_expr} AS knowledge_title,
                {content_expr} AS knowledge_content,
                {('ki.summary' if 'summary' in cols else "''")} AS knowledge_summary,
                {('ki.method' if 'method' in cols else "''")} AS knowledge_method,
                {('ki.confidence' if 'confidence' in cols else '0.0')} AS knowledge_confidence,
                {meta_expr} AS knowledge_metadata,
                NULL AS source_title
            FROM knowledge_items ki
            LEFT JOIN {existing_table} sr
              ON sr.knowledge_item_id=ki.id
            WHERE sr.id IS NULL
              AND (
                    lower({title_expr}) LIKE '%independent%'
                    OR lower({meta_expr}) LIKE '%independent_evidence%'
                    OR lower({content_expr}) LIKE '%independent strategy evidence%'
              )
            ORDER BY ki.id ASC
        """
        return list(conn.execute(fallback_sql).fetchall())


def strategy_evidence_packet(
    row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = parse_json(row["knowledge_metadata"])
    return {
        "knowledge_item_id": safe_int(row["knowledge_item_id"]),
        "title": norm(row["knowledge_title"]),
        "summary": norm(row["knowledge_summary"]),
        "content": norm(row["knowledge_content"])[:14000],
        "method": norm(row["knowledge_method"]),
        "confidence": safe_float(row["knowledge_confidence"]),
        "source_title": norm(row["source_title"]),
        "metadata": metadata,
    }


def extract_strategy_identity(packet: dict[str, Any]) -> tuple[str, str]:
    metadata = packet.get("metadata") or {}
    strategy_id = ""
    strategy_name = ""

    if isinstance(metadata, dict):
        strategy_id = norm(
            metadata.get("strategy_id")
            or metadata.get("paper_strategy_id")
        )
        strategy_name = norm(
            metadata.get("strategy_name")
            or metadata.get("paper_strategy_name")
        )

    text = " ".join(
        [
            norm(packet.get("title")),
            norm(packet.get("method")),
            norm(packet.get("source_title")),
            norm(packet.get("content"))[:4000],
        ]
    )

    if not strategy_id:
        match = re.search(
            r"\bSTR-[A-Z0-9]{6,20}\b",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            strategy_id = match.group(0).upper()

    if not strategy_name:
        title = norm(packet.get("title"))
        if title:
            strategy_name = title.replace(" | INDEPENDENT_EVIDENCE", "").strip()

    return strategy_id, strategy_name


def deterministic_strategy_evidence_review(
    packet: dict[str, Any],
) -> dict[str, Any]:
    """Conservative strategy-level reviewer; never turns independent evidence into proof."""
    content = norm(packet.get("content")).lower()
    metadata = packet.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    summary = metadata.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    positive_full = safe_int(
        summary.get("positive_full_runs")
        or metadata.get("positive_full_runs")
        or metadata.get("positive_runs")
    )
    negative_full = safe_int(
        summary.get("negative_full_runs")
        or metadata.get("negative_full_runs")
        or metadata.get("negative_runs")
    )
    cost_survivors = safe_int(
        summary.get("cost_survivors")
        or metadata.get("cost_survivors")
        or metadata.get("cost_survival_count")
    )
    holdout_positive = safe_int(
        summary.get("positive_holdout_folds")
        or metadata.get("positive_holdout_folds")
        or metadata.get("holdout_positive_folds")
    )
    holdout_total = safe_int(
        summary.get("total_holdout_folds")
        or metadata.get("total_holdout_folds")
        or metadata.get("holdout_folds")
    )

    full_total = positive_full + negative_full

    gap_words = (
        "insufficient",
        "evidence gap",
        "cannot establish",
        "not verified",
        "not proven",
    )
    explicit_gap = any(word in content for word in gap_words)

    if full_total >= 8:
        positive_ratio = positive_full / full_total
    else:
        positive_ratio = 0.0

    holdout_ratio = (
        holdout_positive / holdout_total
        if holdout_total > 0
        else 0.0
    )

    if (
        full_total >= 8
        and positive_ratio >= 0.70
        and holdout_ratio >= 0.60
        and cost_survivors >= 5
        and not explicit_gap
    ):
        verdict = "PARTIALLY_SUPPORTIVE"
        score = 0.70
        text = "Independent evidence is directionally supportive, but remains research evidence rather than proof."
    elif full_total >= 8:
        verdict = "INSUFFICIENT"
        score = 0.35
        text = "Independent evidence exists, but cross-symbol and/or holdout stability is not strong enough for a supportive verdict."
    else:
        verdict = "INSUFFICIENT"
        score = 0.20
        text = "Independent evidence record is incomplete for a strategy-level judgment."

    return {
        "verdict": verdict,
        "score": score,
        "evidence_alignment": (
            f"Independent strategy evidence: full_positive={positive_full}, "
            f"full_negative={negative_full}, cost_survivors={cost_survivors}, "
            f"holdout_positive={holdout_positive}/{holdout_total}."
        ),
        "contradiction_flag": 0,
        "review_method": "deterministic_strategy_v1",
        "review_text": text,
        "next_question": "Can the same strategy survive a further independent time/symbol slice without changing parameters?",
    }


def call_openai_strategy_review(
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not OPENAI_API_KEY:
        return None, "OPENAI_NOT_CONFIGURED"

    system_text = (
        "You are MarketHQ's strategy-level evidence review layer. "
        "Evaluate an independent historical backtest/WFO evidence record for a strategy. "
        "This is research only. Do not issue live trading instructions. "
        "Do not call the strategy verified or proven. Separate measured results from inference. "
        "Return strict JSON only."
    )

    user_text = (
        "Review the independent strategy evidence below. Assess whether it resolves the "
        "previous evidence gap at strategy level. Pay attention to cross-symbol consistency, "
        "cost survival, holdout stability, and whether the rules/periods appear unchanged. "
        "A mixed result should remain mixed; do not upgrade it merely because some symbols are positive.\n\n"
        "Allowed verdict values:\n"
        "SUPPORTIVE\n"
        "PARTIALLY_SUPPORTIVE\n"
        "CONTRADICTORY\n"
        "INSUFFICIENT\n\n"
        "Return JSON with exactly these keys:\n"
        "verdict, score, evidence_alignment, contradiction_flag, review_text, next_question\n\n"
        "score must be between 0.0 and 1.0.\n\n"
        "PACKET:\n"
        + json.dumps(packet, ensure_ascii=False)
    )

    payload = {
        "model": REVIEW_MODEL,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_text}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            },
        ],
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": "Bearer " + OPENAI_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None, "OPENAI_CALL_FAILED"

    raw = norm(data.get("output_text"))
    if not raw:
        parts: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = norm(content.get("text"))
                if text:
                    parts.append(text)
        raw = "\n".join(parts).strip()

    if not raw:
        return None, "OPENAI_EMPTY_RESPONSE"

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "OPENAI_INVALID_JSON"

    if not isinstance(parsed, dict):
        return None, "OPENAI_INVALID_OBJECT"

    verdict = norm(parsed.get("verdict")).upper()
    allowed = {
        "SUPPORTIVE",
        "PARTIALLY_SUPPORTIVE",
        "CONTRADICTORY",
        "INSUFFICIENT",
    }
    if verdict not in allowed:
        return None, "OPENAI_INVALID_VERDICT"

    score = max(0.0, min(1.0, safe_float(parsed.get("score"))))
    return (
        {
            "verdict": verdict,
            "score": round(score, 4),
            "evidence_alignment": norm(parsed.get("evidence_alignment"))[:3000] or "No detailed alignment statement returned.",
            "contradiction_flag": int(bool(parsed.get("contradiction_flag"))),
            "review_method": "openai_strategy_v1",
            "review_text": norm(parsed.get("review_text"))[:5000] or "AI returned a structured strategy evidence verdict.",
            "next_question": norm(parsed.get("next_question"))[:1500] or "Can the same strategy survive a further independent validation slice?",
        },
        "OPENAI_OK",
    )


def strategy_review_exists(
    conn: sqlite3.Connection,
    knowledge_item_id: int,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM brain_research_strategy_evidence_reviews
            WHERE knowledge_item_id=?
            LIMIT 1
            """,
            (knowledge_item_id,),
        ).fetchone()
        is not None
    )


def insert_strategy_review(
    conn: sqlite3.Connection,
    packet: dict[str, Any],
    result: dict[str, Any],
    provider_status: str,
) -> int:
    knowledge_id = safe_int(packet.get("knowledge_item_id"))
    strategy_id, strategy_name = extract_strategy_identity(packet)

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "provider_status": provider_status,
        "knowledge_item_id": knowledge_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "review_role": "strategy_level_independent_evidence",
        "verified": False,
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_strategy_evidence_reviews (
            knowledge_item_id,
            strategy_id,
            strategy_name,
            verdict,
            score,
            evidence_alignment,
            contradiction_flag,
            review_method,
            review_text,
            next_question,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            knowledge_id,
            strategy_id,
            strategy_name,
            norm(result["verdict"]),
            safe_float(result["score"]),
            norm(result["evidence_alignment"]),
            safe_int(result["contradiction_flag"]),
            norm(result["review_method"]),
            norm(result["review_text"]),
            norm(result["next_question"]),
            compact_json(metadata),
            utc_now(),
        ),
    )
    return safe_int(cur.lastrowid)

def observation_packet(
    row: sqlite3.Row,
) -> dict[str, Any]:
    return {
        "symbol": norm(row["symbol"]),
        "method_name": norm(row["method_name"]),
        "market": norm(row["market"]),
        "timeframe": norm(row["timeframe"]),
        "market_regime": norm(row["market_regime"]),
        "volume_state": norm(row["volume_state"]),
        "volatility_state": norm(row["volatility_state"]),
        "sample_size": safe_int(
            row["sample_size"]
        ),
        "positive_count": safe_int(
            row["positive_count"]
        ),
        "negative_count": safe_int(
            row["negative_count"]
        ),
        "neutral_count": safe_int(
            row["neutral_count"]
        ),
        "positive_rate": safe_float(
            row["positive_rate"]
        ),
        "avg_return_1d": safe_float(
            row["avg_return_1d"]
        ),
        "avg_return_5d": safe_float(
            row["avg_return_5d"]
        ),
        "avg_return_20d": safe_float(
            row["avg_return_20d"]
        ),
        "median_return_20d": safe_float(
            row["median_return_20d"]
        ),
        "best_return_20d": safe_float(
            row["best_return_20d"]
        ),
        "worst_return_20d": safe_float(
            row["worst_return_20d"]
        ),
        "avg_mfe": safe_float(
            row["avg_mfe"]
        ),
        "avg_mae": safe_float(
            row["avg_mae"]
        ),
        "confidence": safe_float(
            row["confidence"]
        ),
        "status": norm(
            row["status"]
        ),
        "observation_text": norm(
            row["observation_text"]
        ),
    }


def research_packet(
    row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = parse_json(
        row["knowledge_metadata"]
    )

    return {
        "title": norm(
            row["knowledge_title"]
        ),
        "summary": norm(
            row["knowledge_summary"]
        ),
        "content": norm(
            row["knowledge_content"]
        )[:7000],
        "method": norm(
            row["knowledge_method"]
        ),
        "confidence": safe_float(
            row["knowledge_confidence"]
        ),
        "metadata": metadata,
        "match_type": norm(
            row["match_type"]
        ),
        "match_score": safe_float(
            row["match_score"]
        ),
    }


# ---------------------------------------------------------------------------
# DETERMINISTIC REVIEW
# ---------------------------------------------------------------------------

def deterministic_review(
    research: dict[str, Any],
    observation: dict[str, Any],
) -> dict[str, Any]:
    """
    Conservative deterministic baseline.

    This reviewer does NOT claim semantic understanding of long research
    prose. It checks:
        - context match
        - whether the research says "contradiction" / "gap"
        - whether observation has sufficient sample
        - whether research task context matches observation
    """

    context_score = safe_float(
        research.get(
            "match_score"
        )
    )

    sample = safe_int(
        observation.get(
            "sample_size"
        )
    )

    obs_conf = safe_float(
        observation.get(
            "confidence"
        )
    )

    content = (
        norm(
            research.get(
                "content"
            )
        ).lower()
    )

    contradiction_words = (
        "contradict",
        "contradiction",
        "çelişki",
        "çelişk",
        "conflict",
    )

    gap_words = (
        "evidence gap",
        "evidence gaps",
        "evidence missing",
        "insufficient",
        "kanıt eksik",
        "yeterli değil",
    )

    contradiction = any(
        word in content
        for word in contradiction_words
    )

    gap = any(
        word in content
        for word in gap_words
    )

    if contradiction:
        verdict = "CONTRADICTORY"
        score = min(
            0.95,
            max(
                0.65,
                context_score,
            ),
        )

    elif sample < 20:
        verdict = "INSUFFICIENT"
        score = min(
            0.60,
            max(
                0.30,
                context_score,
            ),
        )

    elif gap:
        verdict = "PARTIALLY_SUPPORTIVE"
        score = min(
            0.80,
            max(
                0.50,
                context_score,
            ),
        )

    elif (
        context_score >= 0.95
        and obs_conf >= 0.60
        and sample >= 50
    ):
        verdict = "SUPPORTIVE"
        score = min(
            0.90,
            max(
                0.70,
                context_score,
            ),
        )

    else:
        verdict = "PARTIALLY_SUPPORTIVE"
        score = min(
            0.80,
            max(
                0.50,
                context_score,
            ),
        )

    if verdict == "SUPPORTIVE":
        alignment = (
            "Research knowledge context matches the observation "
            "and the observation has sufficient historical sample."
        )

    elif verdict == "PARTIALLY_SUPPORTIVE":
        alignment = (
            "Research context is compatible with the observation, "
            "but evidence is not sufficient for a full confirmation."
        )

    elif verdict == "CONTRADICTORY":
        alignment = (
            "Research text indicates a contradiction or conflict "
            "that requires additional review."
        )

    else:
        alignment = (
            "Observation does not provide enough historical evidence "
            "for a strong evidence judgment."
        )

    next_question = (
        "Can this research finding be reproduced on a separate "
        "historical slice without changing the rule definition?"
    )

    return {
        "verdict": verdict,
        "score": round(
            score,
            4,
        ),
        "evidence_alignment": alignment,
        "contradiction_flag": int(
            verdict == "CONTRADICTORY"
        ),
        "review_method": "deterministic_v1",
        "review_text": (
            f"Context match={context_score:.3f}. "
            f"Observation sample={sample}. "
            f"Observation confidence={obs_conf:.3f}. "
            f"Assessment={verdict}."
        ),
        "next_question": next_question,
    }


# ---------------------------------------------------------------------------
# OPENAI REVIEW
# ---------------------------------------------------------------------------

def call_openai_review(
    research: dict[str, Any],
    observation: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not OPENAI_API_KEY:
        return (
            None,
            "OPENAI_NOT_CONFIGURED",
        )

    packet = {
        "research": research,
        "observation": observation,
    }

    system_text = (
        "You are MarketHQ's evidence review layer. "
        "Review whether a research-derived knowledge item is "
        "supported by its linked historical observation. "
        "This is historical research and decision support. "
        "Do not issue live trading instructions. "
        "Do not convert compatibility into proof. "
        "Separate observation from inference. "
        "Return strict JSON only."
    )

    user_text = (
        "Evaluate the evidence alignment between the research "
        "knowledge and the original observation.\n\n"
        "Allowed verdict values:\n"
        "SUPPORTIVE\n"
        "PARTIALLY_SUPPORTIVE\n"
        "CONTRADICTORY\n"
        "INSUFFICIENT\n\n"
        "Return JSON with exactly these keys:\n"
        "verdict, score, evidence_alignment, "
        "contradiction_flag, review_text, next_question\n\n"
        "Rules:\n"
        "- score must be 0.0 to 1.0\n"
        "- contradiction_flag must be true or false\n"
        "- Do not say verified or proven unless the provided evidence truly "
        "supports that language.\n"
        "- A large sample is evidence strength, not automatic proof.\n\n"
        "PACKET:\n"
        + json.dumps(
            packet,
            ensure_ascii=False,
        )
    )

    payload = {
        "model": REVIEW_MODEL,
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
        return (
            None,
            "OPENAI_CALL_FAILED",
        )

    raw = norm(
        data.get(
            "output_text"
        )
    )

    if not raw:
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
                    content.get(
                        "text"
                    )
                )
                if text:
                    parts.append(
                        text
                    )

        raw = "\n".join(
            parts
        ).strip()

    if not raw:
        return (
            None,
            "OPENAI_EMPTY_RESPONSE",
        )

    try:
        parsed = json.loads(
            raw
        )
    except (
        json.JSONDecodeError,
    ):
        return (
            None,
            "OPENAI_INVALID_JSON",
        )

    if not isinstance(
        parsed,
        dict,
    ):
        return (
            None,
            "OPENAI_INVALID_OBJECT",
        )

    verdict = norm(
        parsed.get(
            "verdict"
        )
    ).upper()

    allowed = {
        "SUPPORTIVE",
        "PARTIALLY_SUPPORTIVE",
        "CONTRADICTORY",
        "INSUFFICIENT",
    }

    if verdict not in allowed:
        return (
            None,
            "OPENAI_INVALID_VERDICT",
        )

    score = max(
        0.0,
        min(
            1.0,
            safe_float(
                parsed.get(
                    "score"
                )
            ),
        ),
    )

    result = {
        "verdict": verdict,
        "score": round(
            score,
            4,
        ),
        "evidence_alignment": norm(
            parsed.get(
                "evidence_alignment"
            )
        )[:3000],
        "contradiction_flag": int(
            bool(
                parsed.get(
                    "contradiction_flag"
                )
            )
        ),
        "review_method": "openai_v1",
        "review_text": norm(
            parsed.get(
                "review_text"
            )
        )[:5000],
        "next_question": norm(
            parsed.get(
                "next_question"
            )
        )[:1500],
    }

    if not result["evidence_alignment"]:
        result["evidence_alignment"] = (
            "No detailed alignment statement returned."
        )

    if not result["review_text"]:
        result["review_text"] = (
            "AI returned a structured evidence verdict."
        )

    return (
        result,
        "OPENAI_OK",
    )


# ---------------------------------------------------------------------------
# WRITE REVIEW
# ---------------------------------------------------------------------------

def review_exists(
    conn: sqlite3.Connection,
    knowledge_item_id: int,
    observation_id: int,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM brain_research_evidence_reviews
            WHERE
                knowledge_item_id=?
                AND observation_id=?
            LIMIT 1
            """,
            (
                knowledge_item_id,
                observation_id,
            ),
        ).fetchone()
        is not None
    )


def insert_review(
    conn: sqlite3.Connection,
    candidate: sqlite3.Row,
    result: dict[str, Any],
    provider_status: str,
) -> int:
    knowledge_id = safe_int(
        candidate["knowledge_item_id"]
    )

    observation_id = safe_int(
        candidate["observation_id"]
    )

    if review_exists(
        conn,
        knowledge_id,
        observation_id,
    ):
        row = conn.execute(
            """
            SELECT id
            FROM brain_research_evidence_reviews
            WHERE
                knowledge_item_id=?
                AND observation_id=?
            LIMIT 1
            """,
            (
                knowledge_id,
                observation_id,
            ),
        ).fetchone()

        return safe_int(
            row["id"]
        )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "provider_status": provider_status,
        "link_id": safe_int(
            candidate["link_id"]
        ),
        "knowledge_item_id": knowledge_id,
        "observation_id": observation_id,
        "match_type": norm(
            candidate["match_type"]
        ),
        "match_score": safe_float(
            candidate["match_score"]
        ),
        "knowledge_confidence": safe_float(
            candidate["knowledge_confidence"]
        ),
        "observation_confidence": safe_float(
            candidate["confidence"]
        ),
        "observation_sample_size": safe_int(
            candidate["sample_size"]
        ),
        "verified": False,
        "review_role": "evidence_alignment",
    }

    cur = conn.execute(
        """
        INSERT INTO brain_research_evidence_reviews (
            knowledge_item_id,
            observation_id,
            verdict,
            score,
            evidence_alignment,
            contradiction_flag,
            review_method,
            review_text,
            next_question,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            knowledge_id,
            observation_id,
            norm(
                result["verdict"]
            ),
            safe_float(
                result["score"]
            ),
            norm(
                result["evidence_alignment"]
            ),
            safe_int(
                result["contradiction_flag"]
            ),
            norm(
                result["review_method"]
            ),
            norm(
                result["review_text"]
            ),
            norm(
                result["next_question"]
            ),
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
        for table in (
            "brain_research_observation_links",
            "knowledge_items",
            "brain_observations",
        ):
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: "
                    + table
                )

        ensure_review_table(
            conn
        )
        ensure_strategy_review_table(
            conn
        )

        strategy_candidates = load_independent_strategy_candidates(
            conn
        )

        candidates = load_review_candidates(
            conn
        )

        reviews_created = 0
        already_present = 0
        openai_ok = 0
        deterministic_used = 0
        errors = 0

        verdict_counts: dict[str, int] = {}

        strategy_reviews_created = 0
        strategy_already_present = 0
        strategy_openai_ok = 0
        strategy_deterministic_used = 0
        strategy_errors = 0
        strategy_verdict_counts: dict[str, int] = {}

        for strategy_candidate in strategy_candidates:
            knowledge_id = safe_int(strategy_candidate["knowledge_item_id"])
            try:
                packet = strategy_evidence_packet(strategy_candidate)
                print(
                    f"STRATEGY REVIEW | knowledge={knowledge_id} | "
                    f"{norm(strategy_candidate['knowledge_title'])}"
                )

                ai_result, provider_status = call_openai_strategy_review(packet)
                if ai_result is not None:
                    result = ai_result
                    strategy_openai_ok += 1
                else:
                    result = deterministic_strategy_evidence_review(packet)
                    strategy_deterministic_used += 1

                if strategy_review_exists(conn, knowledge_id):
                    strategy_already_present += 1
                    continue

                review_id = insert_strategy_review(
                    conn,
                    packet,
                    result,
                    provider_status,
                )
                conn.commit()
                strategy_reviews_created += 1

                verdict = norm(result["verdict"])
                strategy_verdict_counts[verdict] = strategy_verdict_counts.get(verdict, 0) + 1

                print(
                    f"  strategy={extract_strategy_identity(packet)[0]} | "
                    f"verdict={verdict} | "
                    f"score={safe_float(result['score']):.3f} | "
                    f"method={result['review_method']} | "
                    f"review_id={review_id}"
                )
            except Exception as exc:
                strategy_errors += 1
                conn.rollback()
                print(
                    f"STRATEGY ERROR | knowledge={knowledge_id} | "
                    f"{type(exc).__name__}: {exc}"
                )

        for candidate in candidates:
            knowledge_id = safe_int(
                candidate["knowledge_item_id"]
            )

            observation_id = safe_int(
                candidate["observation_id"]
            )

            try:
                research = research_packet(
                    candidate
                )

                observation = observation_packet(
                    candidate
                )

                print(
                    f"REVIEW | "
                    f"knowledge={knowledge_id} | "
                    f"observation={observation_id} | "
                    f"{norm(candidate['symbol'])}"
                )

                ai_result, provider_status = (
                    call_openai_review(
                        research,
                        observation,
                    )
                )

                if ai_result is not None:
                    result = ai_result
                    openai_ok += 1
                else:
                    result = deterministic_review(
                        research,
                        observation,
                    )
                    deterministic_used += 1

                review_id = insert_review(
                    conn,
                    candidate,
                    result,
                    provider_status,
                )

                conn.commit()

                reviews_created += 1

                verdict = norm(
                    result["verdict"]
                )

                verdict_counts[verdict] = (
                    verdict_counts.get(
                        verdict,
                        0,
                    )
                    + 1
                )

                print(
                    f"  verdict={verdict} | "
                    f"score={safe_float(result['score']):.3f} | "
                    f"method={result['review_method']} | "
                    f"review_id={review_id}"
                )

            except Exception as exc:
                errors += 1
                conn.rollback()

                print(
                    f"ERROR | "
                    f"knowledge={knowledge_id} | "
                    f"observation={observation_id} | "
                    f"{type(exc).__name__}: {exc}"
                )

        total_reviews = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_evidence_reviews
            """
        ).fetchone()[0]

        print()
        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH EVIDENCE REVIEW ENGINE V4"
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
        print("STRATEGY INDEPENDENT EVIDENCE REVIEW")
        print("-" * 76)
        print(
            "strategy_candidates_seen                 "
            f"{len(strategy_candidates)}"
        )
        print(
            "strategy_reviews_created                 "
            f"{strategy_reviews_created}"
        )
        print(
            "strategy_already_present                  "
            f"{strategy_already_present}"
        )
        print(
            "strategy_openai_reviews                  "
            f"{strategy_openai_ok}"
        )
        print(
            "strategy_deterministic_reviews           "
            f"{strategy_deterministic_used}"
        )
        print(
            "strategy_errors                          "
            f"{strategy_errors}"
        )
        if strategy_verdict_counts:
            for verdict, count in sorted(strategy_verdict_counts.items()):
                print(f"  {verdict:35s} {count}")
        else:
            print("  No new strategy-level verdicts.")
        print()
        print("EVIDENCE REVIEW RUN")
        print("-" * 76)
        print(
            "review_candidates_seen                  "
            f"{len(candidates)}"
        )
        print(
            "reviews_created                        "
            f"{reviews_created}"
        )
        print(
            "already_present                         "
            f"{already_present}"
        )
        print(
            "openai_reviews                          "
            f"{openai_ok}"
        )
        print(
            "deterministic_reviews                   "
            f"{deterministic_used}"
        )
        print(
            "errors                               "
            f"{errors}"
        )
        print()
        print(
            "total_evidence_reviews                  "
            f"{safe_int(total_reviews)}"
        )

        print()
        print("VERDICT DISTRIBUTION")
        print("-" * 76)

        if verdict_counts:
            for verdict, count in sorted(
                verdict_counts.items()
            ):
                print(
                    f"{verdict:35s} {count}"
                )
        else:
            print(
                "No new verdicts."
            )

        print()
        print("RECENT STRATEGY REVIEWS")
        print("-" * 76)
        recent_strategy = conn.execute(
            """
            SELECT
                id, knowledge_item_id, strategy_id, strategy_name,
                verdict, score, review_method
            FROM brain_research_strategy_evidence_reviews
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        if not recent_strategy:
            print("No strategy-level evidence reviews.")
        else:
            for row in recent_strategy:
                print(
                    f"review_id={row['id']} | "
                    f"knowledge={row['knowledge_item_id']} | "
                    f"strategy={norm(row['strategy_id'])} | "
                    f"{norm(row['verdict'])} | "
                    f"score={safe_float(row['score']):.3f} | "
                    f"{norm(row['review_method'])}"
                )
                print(
                    "  " + norm(row['strategy_name'])
                )

        print()
        print("RECENT EVIDENCE REVIEWS")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                r.id,
                r.knowledge_item_id,
                r.observation_id,
                r.verdict,
                r.score,
                r.review_method,
                r.contradiction_flag,
                o.symbol,
                o.method_name
            FROM brain_research_evidence_reviews r
            JOIN brain_observations o
              ON o.id=r.observation_id
            ORDER BY r.id DESC
            LIMIT 10
            """
        ).fetchall()

        if not recent:
            print(
                "No evidence reviews."
            )
        else:
            for row in recent:
                print(
                    f"review_id={row['id']} | "
                    f"knowledge={row['knowledge_item_id']} | "
                    f"observation={row['observation_id']} | "
                    f"{norm(row['verdict'])} | "
                    f"score={safe_float(row['score']):.3f} | "
                    f"{norm(row['review_method'])}"
                )
                print(
                    "  "
                    f"{norm(row['symbol'])} | "
                    f"{norm(row['method_name'])} | "
                    f"contradiction={safe_int(row['contradiction_flag'])}"
                )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Bu katman research knowledge'ı verified yapmaz.")
        print("- Observation kayıtları değiştirilmez.")
        print("- Claim/rule/validation kayıtları değiştirilmez.")
        print("- Review ayrı bir provenance/evaluation hafızasıdır.")
        print("- AI ve deterministic review ayrı işaretlenir.")
        print("- SUPPORTIVE bile tek başına doğrulanmış kural anlamına gelmez.")
        print("- Strategy-level independent evidence ayrı provenance katmanında değerlendirilir.")
        print("- Sonraki aşama: review sonucu -> final research decision / ranking.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

