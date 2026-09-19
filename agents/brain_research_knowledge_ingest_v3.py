# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Knowledge Ingest Engine V3
--------------------------------------------------
Research Agent episode -> Knowledge layer

V3 FIX:
    V2'de source title task_type eklenince aynı episode için yeni
    knowledge_source oluşturulmaya çalışıldı. URL unique olduğu için:

        UNIQUE constraint failed: knowledge_sources.url

    hatası oluştu.

V3:
    1) Önce source URL ile mevcut kaydı bulur.
    2) Bulursa mevcut source'u REUSE + METADATA UPGRADE eder.
    3) URL mevcut başka bir source'ta olsa bile duplicate INSERT yapmaz.
    4) Sonra knowledge_item'i aynı source üzerinde CREATE / UPGRADE eder.
    5) task_type artık metadata/context içine doğru şekilde yazılır.
    6) Eski UNKNOWN research episode'ları ingest edilmez.
    7) Aynı episode tekrar çalıştırıldığında duplicate üretmez.
    8) Research-derived knowledge:
          epistemic_state = research_derived
          verified = false
          verification_required = true
       olarak korunur.

DEĞİŞTİRİLMEYENLER:
    - experiment/result
    - learned_rules
    - brain_claims
    - brain_rule_validations
    - research episodes

AKIŞ:

    brain_episodes
          |
          v
    research_agent_result
          |
          v
    knowledge_sources
          |
          v
    knowledge_items
          |
          v
    Observation / Claim katmanı

Çalıştırma:
    python agents/brain_research_knowledge_ingest_v3.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_KNOWLEDGE_INGEST"
ENGINE_VERSION = "V3"


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


def parse_metadata(raw: Any) -> dict[str, Any]:
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


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    if not table_exists(
        conn,
        table_name,
    ):
        return set()

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        norm(row["name"])
        for row in rows
    }


# ---------------------------------------------------------------------------
# EPISODES
# ---------------------------------------------------------------------------

def load_research_episodes(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                id,
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
            FROM brain_episodes
            WHERE episode_type='research_agent_result'
            ORDER BY id
            """
        ).fetchall()
    )


def episode_metadata(
    row: sqlite3.Row,
) -> dict[str, Any]:
    return parse_metadata(
        row["metadata_json"]
    )


def normalized_episode_context(
    row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = episode_metadata(
        row
    )

    raw_context = metadata.get(
        "reconstructed_context",
        {},
    )

    context = (
        raw_context
        if isinstance(
            raw_context,
            dict,
        )
        else {}
    )

    task_type = (
        norm(
            context.get(
                "task_type"
            )
        )
        or norm(
            metadata.get(
                "task_type"
            )
        )
        or infer_task_type(
            row
        )
    )

    return {
        "task_type": task_type,
        "symbol": norm(
            context.get("symbol")
        ),
        "method_name": norm(
            context.get("method_name")
        ),
        "market": norm(
            context.get("market")
        ),
        "timeframe": norm(
            context.get("timeframe")
        ),
        "condition_name": norm(
            context.get("condition_name")
        ),
        "market_regime": norm(
            context.get("market_regime")
        ),
        "volume_state": norm(
            context.get("volume_state")
        ),
        "volatility_state": norm(
            context.get("volatility_state")
        ),
        "claim_id": metadata.get(
            "claim_id"
        ),
        "learned_rule_id": metadata.get(
            "learned_rule_id"
        ),
        "validation_id": metadata.get(
            "validation_id"
        ),
        "provider_status": norm(
            metadata.get(
                "provider_status"
            )
        ),
    }


def infer_task_type(
    row: sqlite3.Row,
) -> str:
    text = (
        norm(row["title"])
        + " "
        + norm(row["content"])
    ).lower()

    if "rule_promotion_review" in text:
        return "RULE_PROMOTION_REVIEW"

    if "weak_holdout_review" in text:
        return "WEAK_HOLDOUT_REVIEW"

    if "insufficient_data_research" in text:
        return "INSUFFICIENT_DATA_RESEARCH"

    if "validated_rule_recheck" in text:
        return "VALIDATED_RULE_RECHECK"

    if "method_variant_comparison" in text:
        return "METHOD_VARIANT_COMPARISON"

    return "RESEARCH"


def is_invalid_unknown_episode(
    row: sqlite3.Row,
) -> bool:
    metadata = episode_metadata(
        row
    )

    title = norm(
        row["title"]
    ).upper()

    content = norm(
        row["content"]
    ).upper()[:1800]

    provider = norm(
        metadata.get(
            "provider_status"
        )
    ).upper()

    if "UNKNOWN" in title:
        return True

    if (
        "UNKNOWN" in content
        and provider not in {
            "OPENAI_OK",
            "LOCAL_DETERMINISTIC",
        }
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# SOURCE
# ---------------------------------------------------------------------------

def source_url(
    episode: sqlite3.Row,
) -> str:
    return (
        "brain://research-agent/episode/"
        + str(
            safe_int(
                episode["id"]
            )
        )
    )


def source_title(
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> str:
    parts = [
        "MarketHQ Research Agent",
        norm(
            context.get("symbol")
        ) or "RESEARCH",
    ]

    method = norm(
        context.get(
            "method_name"
        )
    )

    task_type = norm(
        context.get(
            "task_type"
        )
    )

    if method:
        parts.append(
            method
        )

    if task_type:
        parts.append(
            task_type
        )

    parts.append(
        "episode="
        + str(
            safe_int(
                episode["id"]
            )
        )
    )

    return " | ".join(
        parts
    )


def source_metadata(
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> str:
    return compact_json(
        {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "source_role": "research_derived",
            "epistemic_state": "research_derived",
            "verified": False,
            "verification_required": True,
            "episode_id": safe_int(
                episode["id"]
            ),
            "queue_id": safe_int(
                episode["source_id"]
            ),
            "task_type": context.get(
                "task_type"
            ),
            "provider_status": context.get(
                "provider_status"
            ),
            "claim_id": context.get(
                "claim_id"
            ),
            "learned_rule_id": context.get(
                "learned_rule_id"
            ),
            "validation_id": context.get(
                "validation_id"
            ),
            "context": context,
        }
    )


def find_source_by_url(
    conn: sqlite3.Connection,
    url: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM knowledge_sources
        WHERE url=?
        LIMIT 1
        """,
        (url,),
    ).fetchone()


def find_source_by_title(
    conn: sqlite3.Connection,
    title: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM knowledge_sources
        WHERE source_type='research_agent'
          AND title=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (title,),
    ).fetchone()


def update_existing_source(
    conn: sqlite3.Connection,
    source_id: int,
    title: str,
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> None:
    columns = table_columns(
        conn,
        "knowledge_sources",
    )

    metadata_json = source_metadata(
        episode,
        context,
    )

    updates = []
    values: list[Any] = []

    if "title" in columns:
        updates.append(
            "title=?"
        )
        values.append(title)

    if "author" in columns:
        updates.append(
            "author=?"
        )
        values.append(ENGINE_NAME)

    if "access_note" in columns:
        updates.append(
            "access_note=?"
        )
        values.append(
            "Generated by MarketHQ Research Agent "
            "from historical research context. "
            "Not independently verified."
        )

    if "metadata_json" in columns:
        updates.append(
            "metadata_json=?"
        )
        values.append(
            metadata_json
        )

    if not updates:
        return

    values.append(
        source_id
    )

    conn.execute(
        f"""
        UPDATE knowledge_sources
        SET {", ".join(updates)}
        WHERE id=?
        """,
        tuple(values),
    )


def find_or_create_source(
    conn: sqlite3.Connection,
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> tuple[int, str]:
    columns = table_columns(
        conn,
        "knowledge_sources",
    )

    required = {
        "source_type",
        "title",
        "url",
        "published_at",
        "author",
        "access_note",
        "metadata_json",
        "created_at",
    }

    missing = sorted(
        required - columns
    )

    if missing:
        raise RuntimeError(
            "knowledge_sources eksik kolonlar: "
            + ", ".join(missing)
        )

    url = source_url(
        episode
    )

    title = source_title(
        episode,
        context,
    )

    # 1) GLOBAL UNIQUE URL kontrolü
    existing = find_source_by_url(
        conn,
        url,
    )

    if existing:
        update_existing_source(
            conn,
            safe_int(
                existing["id"]
            ),
            title,
            episode,
            context,
        )

        return (
            safe_int(
                existing["id"]
            ),
            "reused_by_url",
        )

    # 2) Title fallback
    existing = find_source_by_title(
        conn,
        title,
    )

    if existing:
        # Mevcut title source'unun URL'si farklı olabilir.
        # Unique URL riskine girmeden metadata/title upgrade.
        update_existing_source(
            conn,
            safe_int(
                existing["id"]
            ),
            title,
            episode,
            context,
        )

        return (
            safe_int(
                existing["id"]
            ),
            "reused_by_title",
        )

    # 3) Yeni source
    cur = conn.execute(
        """
        INSERT INTO knowledge_sources (
            source_type,
            title,
            url,
            published_at,
            author,
            access_note,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "research_agent",
            title,
            url,
            episode["observed_at"],
            ENGINE_NAME,
            (
                "Generated by MarketHQ Research Agent "
                "from historical research context. "
                "Not independently verified."
            ),
            source_metadata(
                episode,
                context,
            ),
            utc_now(),
        ),
    )

    return (
        safe_int(
            cur.lastrowid
        ),
        "created",
    )


# ---------------------------------------------------------------------------
# KNOWLEDGE ITEM
# ---------------------------------------------------------------------------

def item_title(
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> str:
    symbol = (
        norm(
            context.get("symbol")
        )
        or "RESEARCH"
    )

    task_type = (
        norm(
            context.get("task_type")
        )
        or "RESEARCH"
    )

    return (
        "Research Finding | "
        f"{symbol} | "
        f"{task_type} | "
        f"episode={safe_int(episode['id'])}"
    )


def item_tags(
    context: dict[str, Any],
) -> list[str]:
    tags = {
        "research_agent",
        "research_derived",
        "brain_episode",
        "not_verified",
    }

    for key in (
        "market",
        "timeframe",
        "market_regime",
        "volume_state",
        "volatility_state",
        "task_type",
    ):
        value = norm(
            context.get(
                key
            )
        )

        if value:
            tags.add(
                value
            )

    return sorted(
        tags
    )


def item_metadata(
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> str:
    return compact_json(
        {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "source_role": "research_derived",
            "epistemic_state": "research_derived",
            "verified": False,
            "verification_required": True,
            "brain_episode_id": safe_int(
                episode["id"]
            ),
            "queue_id": safe_int(
                episode["source_id"]
            ),
            "content_hash": norm(
                episode["content_hash"]
            ),
            "task_type": context.get(
                "task_type"
            ),
            "provider_status": context.get(
                "provider_status"
            ),
            "claim_id": context.get(
                "claim_id"
            ),
            "learned_rule_id": context.get(
                "learned_rule_id"
            ),
            "validation_id": context.get(
                "validation_id"
            ),
            "context": context,
            "episode_metadata": episode_metadata(
                episode
            ),
        }
    )


def find_item(
    conn: sqlite3.Connection,
    source_id: int,
    title: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id
        FROM knowledge_items
        WHERE
            source_id=?
            AND item_type='research_result'
            AND title=?
        LIMIT 1
        """,
        (
            source_id,
            title,
        ),
    ).fetchone()


def create_or_upgrade_item(
    conn: sqlite3.Connection,
    source_id: int,
    episode: sqlite3.Row,
    context: dict[str, Any],
) -> tuple[int, str]:
    columns = table_columns(
        conn,
        "knowledge_items",
    )

    required = {
        "source_id",
        "item_type",
        "title",
        "content",
        "summary",
        "method",
        "symbols_json",
        "tags_json",
        "confidence",
        "metadata_json",
        "created_at",
    }

    missing = sorted(
        required - columns
    )

    if missing:
        raise RuntimeError(
            "knowledge_items eksik kolonlar: "
            + ", ".join(missing)
        )

    title = item_title(
        episode,
        context,
    )

    existing = find_item(
        conn,
        source_id,
        title,
    )

    metadata_json = item_metadata(
        episode,
        context,
    )

    summary = (
        "Research Agent tarafından üretilen "
        "tarihsel araştırma özeti. "
        "Bağımsız olarak doğrulanmış kural değildir."
    )

    method = norm(
        context.get(
            "method_name"
        )
    )

    symbol = norm(
        context.get(
            "symbol"
        )
    )

    tags_json = compact_json(
        item_tags(
            context
        )
    )

    symbols_json = compact_json(
        [symbol]
        if symbol
        else []
    )

    episode_meta = episode_metadata(
        episode
    )

    confidence = safe_float(
        episode_meta.get(
            "confidence"
        ),
        0.50,
    )

    confidence = max(
        0.0,
        min(
            1.0,
            confidence,
        ),
    )

    if existing:
        conn.execute(
            """
            UPDATE knowledge_items
            SET
                content=?,
                summary=?,
                method=?,
                symbols_json=?,
                tags_json=?,
                confidence=?,
                metadata_json=?
            WHERE id=?
            """,
            (
                norm(
                    episode["content"]
                ),
                summary,
                method,
                symbols_json,
                tags_json,
                confidence,
                metadata_json,
                safe_int(
                    existing["id"]
                ),
            ),
        )

        return (
            safe_int(
                existing["id"]
            ),
            "upgraded",
        )

    cur = conn.execute(
        """
        INSERT INTO knowledge_items (
            source_id,
            item_type,
            title,
            content,
            summary,
            method,
            symbols_json,
            tags_json,
            confidence,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            "research_result",
            title,
            norm(
                episode["content"]
            ),
            summary,
            method,
            symbols_json,
            tags_json,
            confidence,
            metadata_json,
            utc_now(),
        ),
    )

    return (
        safe_int(
            cur.lastrowid
        ),
        "created",
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        for table in (
            "brain_episodes",
            "knowledge_sources",
            "knowledge_items",
        ):
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: "
                    + table
                )

        episodes = load_research_episodes(
            conn
        )

        eligible = 0
        skipped_unknown = 0

        sources_created = 0
        sources_reused = 0

        items_created = 0
        items_upgraded = 0
        items_already_present = 0

        errors = 0

        for episode in episodes:
            try:
                if is_invalid_unknown_episode(
                    episode
                ):
                    skipped_unknown += 1
                    continue

                context = normalized_episode_context(
                    episode
                )

                symbol = norm(
                    context.get(
                        "symbol"
                    )
                )

                if not symbol:
                    skipped_unknown += 1
                    continue

                eligible += 1

                source_id, source_action = (
                    find_or_create_source(
                        conn,
                        episode,
                        context,
                    )
                )

                if source_action == "created":
                    sources_created += 1
                else:
                    sources_reused += 1

                (
                    item_id,
                    item_action,
                ) = create_or_upgrade_item(
                    conn,
                    source_id,
                    episode,
                    context,
                )

                if item_action == "created":
                    items_created += 1
                elif item_action == "upgraded":
                    items_upgraded += 1
                else:
                    items_already_present += 1

                conn.commit()

                print(
                    f"INGESTED | "
                    f"episode={safe_int(episode['id'])} | "
                    f"source={source_id} "
                    f"({source_action}) | "
                    f"item={item_id} "
                    f"({item_action}) | "
                    f"{symbol} | "
                    f"{norm(context.get('task_type')) or 'RESEARCH'}"
                )

            except Exception as exc:
                errors += 1
                conn.rollback()

                print(
                    f"ERROR | "
                    f"episode={safe_int(episode['id'])} | "
                    f"{type(exc).__name__}: {exc}"
                )

        total_research_items = conn.execute(
            """
            SELECT COUNT(*)
            FROM knowledge_items
            WHERE item_type='research_result'
            """
        ).fetchone()[0]

        print()
        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH KNOWLEDGE INGEST ENGINE V3"
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
        print("INGEST V3 RUN")
        print("-" * 76)
        print(
            "research_episodes_seen                "
            f"{len(episodes)}"
        )
        print(
            "eligible_episodes                     "
            f"{eligible}"
        )
        print(
            "unknown_or_invalid_skipped             "
            f"{skipped_unknown}"
        )
        print(
            "sources_created                       "
            f"{sources_created}"
        )
        print(
            "sources_reused                        "
            f"{sources_reused}"
        )
        print(
            "items_created                         "
            f"{items_created}"
        )
        print(
            "items_upgraded                        "
            f"{items_upgraded}"
        )
        print(
            "items_already_present                  "
            f"{items_already_present}"
        )
        print(
            "errors                               "
            f"{errors}"
        )
        print()
        print(
            "total_research_result_items            "
            f"{safe_int(total_research_items)}"
        )

        print()
        print("RECENT RESEARCH KNOWLEDGE")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                ki.id,
                ki.source_id,
                ki.title,
                ki.method,
                ki.confidence,
                ki.metadata_json
            FROM knowledge_items ki
            WHERE ki.item_type='research_result'
            ORDER BY ki.id DESC
            LIMIT 10
            """
        ).fetchall()

        if not recent:
            print(
                "No research_result knowledge items."
            )
        else:
            for item in recent:
                metadata = parse_metadata(
                    item["metadata_json"]
                )

                context = metadata.get(
                    "context",
                    {},
                )

                print(
                    f"item_id={item['id']} | "
                    f"source_id={item['source_id']} | "
                    f"confidence={safe_float(item['confidence']):.3f}"
                )

                print(
                    "  "
                    f"{norm(context.get('symbol'))} | "
                    f"{norm(item['method'])} | "
                    f"{norm(context.get('market'))} | "
                    f"{norm(context.get('timeframe'))} | "
                    f"{norm(metadata.get('task_type')) or 'RESEARCH'}"
                )

                print(
                    f"  {norm(item['title'])}"
                )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- V3 source URL duplicate problemini çözer.")
        print("- Mevcut source URL varsa yeni source açılmaz.")
        print("- Research-derived knowledge verified değildir.")
        print("- Eski UNKNOWN episode'lar ingest edilmez.")
        print("- Aynı episode tekrar çalıştırıldığında duplicate oluşmaz.")
        print("- Ham experiment/result, learned_rules, claims ve validations")
        print("  değiştirilmez.")
        print("- Sonraki aşama: research-derived knowledge -> observation.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

