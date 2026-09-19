# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Observation Bridge V3
---------------------------------------------
Canonical research-derived knowledge -> existing observations

V3 FIX
------
V1 yalnızca SQL tarafında:
    json_extract(metadata_json, '$.lifecycle_state')='canonical'
filtresine güveniyordu.

Repair Engine V1 çıktısında item 502/503 canonical görünmesine rağmen
Bridge V1 yalnızca 2 item gördüğü için canonical seçimi Python tarafında
yeniden doğrulanacak.

V3:
    1) V2'nin canonical seçim mantığını korur.
    2) Normal tek-sembol research knowledge için V2 context eşleşmesini korur.
    3) Paper evidence MULTI_SYMBOL kayıtlarında queue metadata içindeki gerçek sembol listesini geri çözer.
    4) Her sembol için yalnızca mevcut brain_observations kayıtlarını arar; yeni observation oluşturmaz.
    5) MULTI_SYMBOL bağlantıları ayrı bir match_type ile provenance olarak eklenir.
    6) Mevcut link varsa duplicate oluşturulmaz; eski linkler korunur.

DEĞİŞTİRİLMEYENLER
-----------------
- brain_observations
- experiment/result
- learned_rules
- brain_claims
- validations
- research episodes
- knowledge content

SADECE:
    brain_research_observation_links
tablosuna provenance bağlantısı eklenebilir.

Çalıştırma:
    python agents/brain_research_observation_bridge_v2.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_OBSERVATION_BRIDGE"
ENGINE_VERSION = "V3"

PAPER_EVIDENCE_TASK_TYPES = {
    "PAPER_EVIDENCE_WEAK_REVIEW",
    "PAPER_EVIDENCE_MIXED_REVIEW",
    "PAPER_EVIDENCE_INSUFFICIENT_DATA",
    "PAPER_EVIDENCE_PROMISING_VALIDATION",
}


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
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


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    if not table_exists(
        conn,
        table,
    ):
        return set()

    return {
        norm(row["name"])
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# LINK TABLE
# ---------------------------------------------------------------------------

def ensure_link_table(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_research_observation_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            knowledge_item_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,

            relation TEXT NOT NULL,
            match_type TEXT NOT NULL,

            match_score REAL NOT NULL DEFAULT 0.0,

            evidence_role TEXT NOT NULL
                DEFAULT 'research_context',

            verified INTEGER NOT NULL DEFAULT 0,

            metadata_json TEXT,

            created_at TEXT NOT NULL,

            UNIQUE (
                knowledge_item_id,
                observation_id,
                relation
            )
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_research_observation_links_knowledge
        ON brain_research_observation_links(
            knowledge_item_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_research_observation_links_observation
        ON brain_research_observation_links(
            observation_id
        )
        """
    )


# ---------------------------------------------------------------------------
# RESEARCH KNOWLEDGE
# ---------------------------------------------------------------------------

def load_all_research_items(
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
                content,
                summary,
                method,
                symbols_json,
                tags_json,
                confidence,
                metadata_json,
                created_at
            FROM knowledge_items
            WHERE item_type='research_result'
            ORDER BY id
            """
        ).fetchall()
    )


def canonical_research_items(
    conn: sqlite3.Connection,
) -> tuple[list[sqlite3.Row], int]:
    all_items = load_all_research_items(conn)

    canonical: list[sqlite3.Row] = []
    malformed_or_noncanonical = 0

    for row in all_items:
        metadata = parse_json(
            row["metadata_json"]
        )

        state = norm(
            metadata.get(
                "lifecycle_state"
            )
        ).lower()

        # V2: Python-side authoritative selection.
        if state == "canonical":
            canonical.append(row)
        else:
            malformed_or_noncanonical += 1

    return (
        canonical,
        malformed_or_noncanonical,
    )


def item_context(
    row: sqlite3.Row,
) -> dict[str, Any]:
    metadata = parse_json(
        row["metadata_json"]
    )

    raw_context = metadata.get(
        "context",
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

    return {
        "symbol": norm(
            context.get("symbol")
        ),
        "method_name": (
            norm(
                context.get(
                    "method_name"
                )
            )
            or norm(
                row["method"]
            )
        ),
        "market": norm(
            context.get("market")
        ),
        "timeframe": norm(
            context.get("timeframe")
        ),
        "condition_name": norm(
            context.get(
                "condition_name"
            )
        ),
        "market_regime": norm(
            context.get(
                "market_regime"
            )
        ),
        "volume_state": norm(
            context.get(
                "volume_state"
            )
        ),
        "volatility_state": norm(
            context.get(
                "volatility_state"
            )
        ),
        "task_type": (
            norm(
                metadata.get(
                    "task_type"
                )
            )
            or norm(
                context.get(
                    "task_type"
                )
            )
        ),
        "brain_episode_id": safe_int(
            metadata.get(
                "brain_episode_id"
            )
        ),
        "learned_rule_id": safe_int(
            metadata.get(
                "learned_rule_id"
            )
        ),
        "validation_id": safe_int(
            metadata.get(
                "validation_id"
            )
        ),
        "provider_status": norm(
            metadata.get(
                "provider_status"
            )
        ),
        "lifecycle_state": norm(
            metadata.get(
                "lifecycle_state"
            )
        ),
    }


# ---------------------------------------------------------------------------
# MULTI-SYMBOL PAPER EVIDENCE
# ---------------------------------------------------------------------------

def is_paper_evidence_task(task_type: Any) -> bool:
    return norm(task_type).upper() in PAPER_EVIDENCE_TASK_TYPES


def load_queue_metadata_for_episode(
    conn: sqlite3.Connection,
    episode_id: int,
) -> dict[str, Any]:
    """Recover the original paper-evidence queue metadata for a research episode."""
    if episode_id <= 0 or not table_exists(conn, "brain_episodes"):
        return {}

    episode = conn.execute(
        """
        SELECT source_table, source_id
        FROM brain_episodes
        WHERE id=?
        LIMIT 1
        """,
        (episode_id,),
    ).fetchone()

    if episode is None:
        return {}

    if norm(episode["source_table"]) != "brain_research_queue":
        return {}

    queue_id = safe_int(episode["source_id"])
    if queue_id <= 0 or not table_exists(conn, "brain_research_queue"):
        return {}

    queue = conn.execute(
        """
        SELECT metadata_json
        FROM brain_research_queue
        WHERE id=?
        LIMIT 1
        """,
        (queue_id,),
    ).fetchone()

    if queue is None:
        return {}

    return parse_json(queue["metadata_json"])


def paper_symbols_for_item(
    conn: sqlite3.Connection,
    item: sqlite3.Row,
    context: dict[str, Any],
) -> list[str]:
    """Return the real symbol list for a MULTI_SYMBOL paper-evidence item."""
    task_type = norm(context.get("task_type")).upper()
    if not is_paper_evidence_task(task_type):
        return []

    symbols: list[str] = []

    # First preference: explicit symbols carried by the knowledge item.
    raw_symbols = parse_json(item["symbols_json"]) if "symbols_json" in item.keys() else []
    if isinstance(raw_symbols, list):
        symbols.extend(norm(x) for x in raw_symbols if norm(x))

    # The V3 ingest can only see MULTI_SYMBOL at item level. Recover the
    # authoritative per-symbol list from the originating queue metadata.
    episode_id = safe_int(context.get("brain_episode_id"))
    queue_metadata = load_queue_metadata_for_episode(
        conn,
        episode_id,
    )

    queue_symbols = queue_metadata.get("symbols", [])
    if isinstance(queue_symbols, str):
        queue_symbols = re.split(r"[,;|]", queue_symbols)

    if isinstance(queue_symbols, list):
        symbols.extend(
            norm(x)
            for x in queue_symbols
            if norm(x)
        )

    # A future writer may already preserve paper_evidence directly.
    paper = queue_metadata.get("paper_evidence", {})
    if isinstance(paper, dict):
        nested = paper.get("symbols", [])
        if isinstance(nested, str):
            nested = re.split(r"[,;|]", nested)
        if isinstance(nested, list):
            symbols.extend(
                norm(x)
                for x in nested
                if norm(x)
            )

    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        key = symbol.upper()
        if key in {"MULTI_SYMBOL", "PAPER_EVIDENCE", "UNKNOWN"}:
            continue
        if key not in seen:
            seen.add(key)
            deduped.append(symbol)

    return deduped


def load_observations_for_symbol(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    market: str,
    timeframe: str,
) -> list[sqlite3.Row]:
    """Load only existing observations for one paper-evidence symbol."""
    columns = table_columns(conn, "brain_observations")
    required = {
        "id",
        "method_name",
        "symbol",
        "market",
        "timeframe",
    }
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            "brain_observations eksik kolonlar: "
            + ", ".join(missing)
        )

    symbol = norm(symbol)
    market = norm(market)
    timeframe = norm(timeframe)
    if not symbol or not market:
        return []

    # HISTORICAL is an aggregate research label, not an observation timeframe.
    # Therefore it is intentionally treated as a wildcard here.
    if timeframe and timeframe.upper() != "HISTORICAL":
        return list(
            conn.execute(
                """
                SELECT *
                FROM brain_observations
                WHERE symbol=? AND market=? AND timeframe=?
                ORDER BY confidence DESC, sample_size DESC, id ASC
                LIMIT 100
                """,
                (symbol, market, timeframe),
            ).fetchall()
        )

    return list(
        conn.execute(
            """
            SELECT *
            FROM brain_observations
            WHERE symbol=? AND market=?
            ORDER BY confidence DESC, sample_size DESC, id ASC
            LIMIT 100
            """,
            (symbol, market),
        ).fetchall()
    )


def multi_symbol_matches(
    conn: sqlite3.Connection,
    item: sqlite3.Row,
    context: dict[str, Any],
) -> list[tuple[float, str, sqlite3.Row, str]]:
    """Build safe provenance matches from aggregate paper evidence to existing observations."""
    symbols = paper_symbols_for_item(
        conn,
        item,
        context,
    )
    if not symbols:
        return []

    market = norm(context.get("market"))
    timeframe = norm(context.get("timeframe"))
    results: list[tuple[float, str, sqlite3.Row, str]] = []

    for symbol in symbols:
        observations = load_observations_for_symbol(
            conn,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
        )
        for observation in observations:
            obs_context = observation_context(observation)
            obs_timeframe = norm(obs_context.get("timeframe"))

            if timeframe and timeframe.upper() != "HISTORICAL" and obs_timeframe != timeframe:
                continue

            # For aggregate paper evidence, symbol+market is the reliable
            # provenance boundary. Method/timeframe may describe a different
            # research layer and must not be fabricated or forced.
            if norm(obs_context.get("symbol")).upper() != symbol.upper():
                continue
            if norm(obs_context.get("market")).upper() != market.upper():
                continue

            score = 0.95 if timeframe and timeframe.upper() != "HISTORICAL" else 0.90
            results.append(
                (
                    score,
                    "MULTI_SYMBOL_CONTEXT",
                    observation,
                    symbol,
                )
            )

    return results


# ---------------------------------------------------------------------------
# OBSERVATIONS
# ---------------------------------------------------------------------------

def load_observations_for_context(
    conn: sqlite3.Connection,
    context: dict[str, Any],
) -> list[sqlite3.Row]:
    columns = table_columns(
        conn,
        "brain_observations",
    )

    required = {
        "id",
        "method_name",
        "symbol",
        "market",
        "timeframe",
    }

    missing = sorted(
        required - columns
    )

    if missing:
        raise RuntimeError(
            "brain_observations eksik kolonlar: "
            + ", ".join(missing)
        )

    symbol = norm(
        context.get("symbol")
    )
    method_name = norm(
        context.get("method_name")
    )
    market = norm(
        context.get("market")
    )
    timeframe = norm(
        context.get("timeframe")
    )

    if not (
        symbol
        and method_name
        and market
        and timeframe
    ):
        return []

    return list(
        conn.execute(
            """
            SELECT *
            FROM brain_observations
            WHERE
                symbol=?
                AND method_name=?
                AND market=?
                AND timeframe=?
            ORDER BY
                confidence DESC,
                sample_size DESC,
                id ASC
            LIMIT 100
            """,
            (
                symbol,
                method_name,
                market,
                timeframe,
            ),
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# MATCH
# ---------------------------------------------------------------------------

def observation_context(
    row: sqlite3.Row,
) -> dict[str, str]:
    return {
        "symbol": norm(
            row["symbol"]
        ),
        "method_name": norm(
            row["method_name"]
        ),
        "market": norm(
            row["market"]
        ),
        "timeframe": norm(
            row["timeframe"]
        ),
        "market_regime": norm(
            row["market_regime"]
        ),
        "volume_state": norm(
            row["volume_state"]
        ),
        "volatility_state": norm(
            row["volatility_state"]
        ),
    }


def score_match(
    research: dict[str, Any],
    observation: sqlite3.Row,
) -> tuple[float, str]:
    obs = observation_context(
        observation
    )

    base_fields = (
        "symbol",
        "method_name",
        "market",
        "timeframe",
    )

    if not all(
        norm(
            research.get(field)
        )
        == norm(
            obs.get(field)
        )
        for field in base_fields
    ):
        return (
            0.0,
            "NO_BASE_MATCH",
        )

    contextual_fields = (
        "market_regime",
        "volume_state",
        "volatility_state",
    )

    provided = [
        field
        for field in contextual_fields
        if norm(
            research.get(field)
        )
    ]

    if not provided:
        return (
            0.80,
            "BASE_CONTEXT",
        )

    matched = sum(
        1
        for field in provided
        if norm(
            research.get(field)
        )
        == norm(
            obs.get(field)
        )
    )

    if matched == len(provided):
        return (
            1.00,
            "EXACT_CONTEXT",
        )

    if matched > 0:
        return (
            0.90,
            "PARTIAL_CONTEXT",
        )

    return (
        0.82,
        "BASE_CONTEXT",
    )


# ---------------------------------------------------------------------------
# LINK
# ---------------------------------------------------------------------------

def link_exists(
    conn: sqlite3.Connection,
    knowledge_id: int,
    observation_id: int,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM brain_research_observation_links
            WHERE
                knowledge_item_id=?
                AND observation_id=?
                AND relation='contextualizes'
            LIMIT 1
            """,
            (
                knowledge_id,
                observation_id,
            ),
        ).fetchone()
        is not None
    )


def create_link(
    conn: sqlite3.Connection,
    item: sqlite3.Row,
    observation: sqlite3.Row,
    score: float,
    match_type: str,
) -> str:
    knowledge_id = safe_int(
        item["id"]
    )

    observation_id = safe_int(
        observation["id"]
    )

    if link_exists(
        conn,
        knowledge_id,
        observation_id,
    ):
        return "existing"

    context = item_context(
        item
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "knowledge_item_id": knowledge_id,
        "observation_id": observation_id,
        "brain_episode_id": context.get(
            "brain_episode_id"
        ),
        "task_type": context.get(
            "task_type"
        ),
        "learned_rule_id": context.get(
            "learned_rule_id"
        ),
        "validation_id": context.get(
            "validation_id"
        ),
        "provider_status": context.get(
            "provider_status"
        ),
        "match_type": match_type,
        "match_score": score,
        "relation_role": "research_context",
        "verified": False,
    }

    conn.execute(
        """
        INSERT INTO brain_research_observation_links (
            knowledge_item_id,
            observation_id,
            relation,
            match_type,
            match_score,
            evidence_role,
            verified,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            knowledge_id,
            observation_id,
            "contextualizes",
            match_type,
            score,
            "research_context",
            0,
            compact_json(
                metadata
            ),
            utc_now(),
        ),
    )

    return "created"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        for table in (
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

        ensure_link_table(
            conn
        )

        all_items = load_all_research_items(
            conn
        )

        (
            canonical_items,
            noncanonical_count,
        ) = canonical_research_items(
            conn
        )

        eligible = 0
        matched_items = 0
        unmatched_items = 0

        links_created = 0
        links_existing = 0

        exact_matches = 0
        partial_matches = 0

        errors = 0

        for item in canonical_items:
            try:
                context = item_context(
                    item
                )

                paper_task = is_paper_evidence_task(
                    context.get("task_type", "")
                )

                if paper_task and norm(context.get("symbol")).upper() == "MULTI_SYMBOL":
                    eligible += 1

                    multi_matches = multi_symbol_matches(
                        conn,
                        item,
                        context,
                    )

                    matches = [
                        (score, match_type, observation)
                        for score, match_type, observation, _symbol in multi_matches
                        if score >= 0.90
                    ]

                else:
                    if not (
                        norm(context.get("symbol"))
                        and norm(context.get("method_name"))
                        and norm(context.get("market"))
                        and norm(context.get("timeframe"))
                    ):
                        unmatched_items += 1
                        print(
                            f"NO_CONTEXT | "
                            f"item={safe_int(item['id'])}"
                        )
                        continue

                    eligible += 1

                    observations = (
                        load_observations_for_context(
                            conn,
                            context,
                        )
                    )

                    matches = []

                    for observation in observations:
                        score, match_type = score_match(
                            context,
                            observation,
                        )

                        if score >= 0.90:
                            matches.append(
                                (
                                    score,
                                    match_type,
                                    observation,
                                )
                            )

                if not matches:
                    unmatched_items += 1

                    print(
                        f"NO_MATCH | "
                        f"item={safe_int(item['id'])} | "
                        f"{norm(context.get('symbol'))} | "
                        f"{norm(context.get('task_type'))}"
                    )

                    continue

                matched_items += 1

                exact_present = any(
                    match_type == "EXACT_CONTEXT"
                    for (
                        _score,
                        match_type,
                        _observation,
                    ) in matches
                )

                # Only the legacy single-symbol path applies exact-context
                # preference. Multi-symbol paper evidence intentionally keeps
                # all safe symbol-level matches.
                if exact_present and not paper_task:
                    matches = [
                        match
                        for match in matches
                        if match[1] == "EXACT_CONTEXT"
                    ]

                for (
                    score,
                    match_type,
                    observation,
                ) in matches:
                    action = create_link(
                        conn,
                        item,
                        observation,
                        score,
                        match_type,
                    )

                    if action == "created":
                        links_created += 1
                    else:
                        links_existing += 1

                    if match_type == "EXACT_CONTEXT":
                        exact_matches += 1
                    else:
                        partial_matches += 1

                    print(
                        f"LINKED | "
                        f"item={safe_int(item['id'])} | "
                        f"obs={safe_int(observation['id'])} | "
                        f"score={score:.2f} | "
                        f"{match_type} | "
                        f"{norm(context.get('symbol'))} | "
                        f"{norm(context.get('task_type'))}"
                    )

                conn.commit()

            except Exception as exc:
                errors += 1
                conn.rollback()

                print(
                    f"ERROR | "
                    f"item={safe_int(item['id'])} | "
                    f"{type(exc).__name__}: {exc}"
                )

        total_links = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_observation_links
            """
        ).fetchone()[0]

        unique_knowledge = conn.execute(
            """
            SELECT COUNT(DISTINCT knowledge_item_id)
            FROM brain_research_observation_links
            """
        ).fetchone()[0]

        unique_observations = conn.execute(
            """
            SELECT COUNT(DISTINCT observation_id)
            FROM brain_research_observation_links
            """
        ).fetchone()[0]

        print()
        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH OBSERVATION BRIDGE V3"
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
        print("BRIDGE V2 RUN")
        print("-" * 76)
        print(
            "research_result_items_seen              "
            f"{len(all_items)}"
        )
        print(
            "canonical_items_seen                    "
            f"{len(canonical_items)}"
        )
        print(
            "noncanonical_or_invalid_skipped         "
            f"{noncanonical_count}"
        )
        print(
            "eligible_items                           "
            f"{eligible}"
        )
        print(
            "items_with_observation_match             "
            f"{matched_items}"
        )
        print(
            "items_without_match                      "
            f"{unmatched_items}"
        )
        print(
            "links_created                            "
            f"{links_created}"
        )
        print(
            "links_already_present                    "
            f"{links_existing}"
        )
        print(
            "exact_context_matches                    "
            f"{exact_matches}"
        )
        print(
            "partial_context_matches                  "
            f"{partial_matches}"
        )
        print(
            "errors                                  "
            f"{errors}"
        )
        print()
        print(
            "total_bridge_links                      "
            f"{safe_int(total_links)}"
        )
        print(
            "unique_knowledge_items_linked            "
            f"{safe_int(unique_knowledge)}"
        )
        print(
            "unique_observations_linked               "
            f"{safe_int(unique_observations)}"
        )

        print()
        print("RECENT BRIDGE LINKS")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                l.id,
                l.knowledge_item_id,
                l.observation_id,
                l.match_type,
                l.match_score,
                ki.title AS knowledge_title,
                o.symbol,
                o.method_name
            FROM brain_research_observation_links l
            JOIN knowledge_items ki
              ON ki.id=l.knowledge_item_id
            JOIN brain_observations o
              ON o.id=l.observation_id
            ORDER BY l.id DESC
            LIMIT 20
            """
        ).fetchall()

        if not recent:
            print(
                "No bridge links."
            )
        else:
            for row in recent:
                print(
                    f"link_id={row['id']} | "
                    f"knowledge={row['knowledge_item_id']} | "
                    f"observation={row['observation_id']} | "
                    f"score={safe_float(row['match_score']):.2f} | "
                    f"{norm(row['match_type'])}"
                )
                print(
                    "  "
                    f"{norm(row['symbol'])} | "
                    f"{norm(row['method_name'])}"
                )
                print(
                    f"  {norm(row['knowledge_title'])}"
                )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Canonical seçimi Python tarafında yapılır.")
        print("- Yeni observation oluşturulmaz.")
        print("- Mevcut observation değiştirilmez.")
        print("- Research knowledge verified yapılmaz.")
        print("- Mevcut linkler duplicate olmadan korunur.")
        print("- Eşleşmeyen knowledge kaybedilmez.")
        print("- MULTI_SYMBOL paper evidence yalnızca mevcut sembol bazlı observation")
        print("  kayıtlarına provenance link olarak bağlanır.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

