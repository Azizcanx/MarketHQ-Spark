import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# =========================================================
# PATH
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "market_hq.db"


# =========================================================
# TIME
# =========================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================
# CONNECTION
# =========================================================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db() -> None:

    conn = get_connection()

    try:

        conn.executescript(
            """

            -- =================================================
            -- NEWS
            -- =================================================

            CREATE TABLE IF NOT EXISTS news (
                article_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                published TEXT,
                source TEXT,
                link TEXT,
                description TEXT,
                created_at TEXT NOT NULL
            );


            -- =================================================
            -- AI ANALYSES
            -- =================================================

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                article_id TEXT NOT NULL,

                analysis_version TEXT NOT NULL,

                relevant INTEGER NOT NULL,

                summary TEXT,

                importance INTEGER,

                market_direction TEXT,

                reason TEXT,

                confidence REAL,

                raw_json TEXT,

                created_at TEXT NOT NULL,

                UNIQUE (
                    article_id,
                    analysis_version
                ),

                FOREIGN KEY (
                    article_id
                )
                REFERENCES news(article_id)
                ON DELETE CASCADE
            );


            -- =================================================
            -- ANALYSIS TARGETS
            -- =================================================

            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                analysis_id INTEGER NOT NULL,

                symbol TEXT NOT NULL,

                instrument_type TEXT,

                name TEXT,

                market TEXT,

                UNIQUE (
                    analysis_id,
                    symbol
                ),

                FOREIGN KEY (
                    analysis_id
                )
                REFERENCES analyses(id)
                ON DELETE CASCADE
            );


            -- =================================================
            -- FIN[SYS] SOURCES
            -- =================================================

            CREATE TABLE IF NOT EXISTS knowledge_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                source_type TEXT NOT NULL,

                title TEXT,

                url TEXT UNIQUE,

                published_at TEXT,

                author TEXT,

                access_note TEXT,

                metadata_json TEXT,

                created_at TEXT NOT NULL
            );


            -- =================================================
            -- FIN[SYS] KNOWLEDGE
            -- =================================================

            CREATE TABLE IF NOT EXISTS knowledge_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                source_id INTEGER,

                item_type TEXT NOT NULL,

                title TEXT,

                content TEXT NOT NULL,

                summary TEXT,

                method TEXT,

                symbols_json TEXT,

                tags_json TEXT,

                confidence REAL,

                metadata_json TEXT,

                created_at TEXT NOT NULL,

                UNIQUE (
                    source_id,
                    item_type,
                    title
                ),

                FOREIGN KEY (
                    source_id
                )
                REFERENCES knowledge_sources(id)
                ON DELETE SET NULL
            );


            -- =================================================
            -- VISUAL ASSETS
            -- =================================================

            CREATE TABLE IF NOT EXISTS visual_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                source_id INTEGER,

                asset_type TEXT NOT NULL,

                file_path TEXT NOT NULL,

                description TEXT,

                extracted_knowledge_id INTEGER,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    source_id
                )
                REFERENCES knowledge_sources(id)
                ON DELETE SET NULL,

                FOREIGN KEY (
                    extracted_knowledge_id
                )
                REFERENCES knowledge_items(id)
                ON DELETE SET NULL
            );


            -- =================================================
            -- LEARNING EXPERIMENTS
            -- =================================================

            CREATE TABLE IF NOT EXISTS learning_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                knowledge_id INTEGER,

                method_name TEXT NOT NULL,

                method_type TEXT,

                symbol TEXT NOT NULL,

                market TEXT,

                timeframe TEXT,

                signal_direction TEXT,

                start_date TEXT,

                end_date TEXT,

                status TEXT NOT NULL,

                parameters_json TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    knowledge_id
                )
                REFERENCES knowledge_items(id)
                ON DELETE SET NULL
            );


            -- =================================================
            -- EXPERIMENT RESULTS
            -- =================================================

            CREATE TABLE IF NOT EXISTS experiment_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                experiment_id INTEGER NOT NULL,

                observation_date TEXT,

                entry_price REAL,

                price_1d REAL,

                price_5d REAL,

                price_20d REAL,

                return_1d REAL,

                return_5d REAL,

                return_20d REAL,

                max_favorable_move REAL,

                max_adverse_move REAL,

                result_1d TEXT,

                result_5d TEXT,

                result_20d TEXT,

                market_regime TEXT,

                volume_state TEXT,

                volatility_state TEXT,

                metadata_json TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    experiment_id
                )
                REFERENCES learning_experiments(id)
                ON DELETE CASCADE
            );


            -- =================================================
            -- LEARNED RULES
            -- =================================================

            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                method_name TEXT NOT NULL,

                method_type TEXT,

                symbol TEXT,

                market TEXT,

                timeframe TEXT,

                condition_name TEXT NOT NULL,

                sample_size INTEGER NOT NULL,

                success_rate REAL,

                average_return REAL,

                average_return_5d REAL,

                average_return_20d REAL,

                best_return REAL,

                worst_return REAL,

                confidence REAL,

                observation TEXT,

                created_at TEXT NOT NULL,

                UNIQUE (
                    method_name,
                    symbol,
                    timeframe,
                    condition_name
                )
            );


            -- =================================================
            -- INDEXES
            -- =================================================

            CREATE INDEX IF NOT EXISTS idx_news_published
                ON news(published);


            CREATE INDEX IF NOT EXISTS idx_analyses_article
                ON analyses(article_id);


            CREATE INDEX IF NOT EXISTS idx_knowledge_type
                ON knowledge_items(item_type);


            CREATE INDEX IF NOT EXISTS idx_knowledge_title
                ON knowledge_items(title);


            CREATE INDEX IF NOT EXISTS idx_experiments_method
                ON learning_experiments(method_name);


            CREATE INDEX IF NOT EXISTS idx_experiment_symbol
                ON learning_experiments(symbol);


            CREATE INDEX IF NOT EXISTS idx_results_experiment
                ON experiment_results(experiment_id);


            CREATE INDEX IF NOT EXISTS idx_learned_rules_method
                ON learned_rules(method_name);

            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# NEWS
# =========================================================

def upsert_news(
    article: dict[str, Any]
) -> None:

    article_id = str(
        article.get("id")
        or article.get("link")
        or ""
    ).strip()

    if not article_id:
        return

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT INTO news (
                article_id,
                title,
                published,
                source,
                link,
                description,
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(article_id)

            DO UPDATE SET
                title = excluded.title,
                published = excluded.published,
                source = excluded.source,
                link = excluded.link,
                description = excluded.description
            """,
            (
                article_id,
                str(
                    article.get(
                        "title",
                        ""
                    )
                ).strip(),
                article.get(
                    "published"
                ),
                article.get(
                    "source"
                ),
                article.get(
                    "link"
                ),
                article.get(
                    "description"
                ),
                utc_now(),
            ),
        )

        conn.commit()

    finally:

        conn.close()


def upsert_news_batch(
    articles: Iterable[dict[str, Any]]
) -> None:

    for article in articles:

        upsert_news(article)


# =========================================================
# ANALYSIS CACHE
# =========================================================

def get_unanalyzed_articles(
    articles: list[dict[str, Any]],
    analysis_version: str,
) -> list[dict[str, Any]]:

    if not articles:

        return []

    article_ids = [
        str(
            article.get("id")
            or article.get("link")
            or ""
        ).strip()

        for article in articles
    ]

    article_ids = [
        article_id
        for article_id in article_ids
        if article_id
    ]

    if not article_ids:

        return []

    placeholders = ",".join(
        "?"
        for _ in article_ids
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            f"""
            SELECT article_id
            FROM analyses

            WHERE analysis_version = ?

            AND article_id IN (
                {placeholders}
            )
            """,
            [
                analysis_version,
                *article_ids,
            ],
        ).fetchall()

    finally:

        conn.close()

    analyzed = {
        row["article_id"]
        for row in rows
    }

    return [
        article
        for article in articles
        if str(
            article.get("id")
            or article.get("link")
            or ""
        ).strip()
        not in analyzed
    ]


def get_cached_analysis(
    article_id: str,
    analysis_version: str,
) -> dict[str, Any] | None:

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT *
            FROM analyses

            WHERE article_id = ?
            AND analysis_version = ?

            ORDER BY id DESC

            LIMIT 1
            """,
            (
                article_id,
                analysis_version,
            ),
        ).fetchone()

        if row is None:

            return None

        result = dict(row)

        try:

            parsed = json.loads(
                result.get(
                    "raw_json"
                )
                or "{}"
            )

            if isinstance(
                parsed,
                dict
            ):

                return parsed

        except json.JSONDecodeError:

            pass

        return result

    finally:

        conn.close()


# =========================================================
# SAVE ANALYSIS
# =========================================================

def save_analysis(
    article_id: str,
    analysis: dict[str, Any],
    analysis_version: str,
) -> int:

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT INTO analyses (
                article_id,
                analysis_version,
                relevant,
                summary,
                importance,
                market_direction,
                reason,
                confidence,
                raw_json,
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(
                article_id,
                analysis_version
            )

            DO UPDATE SET

                relevant =
                    excluded.relevant,

                summary =
                    excluded.summary,

                importance =
                    excluded.importance,

                market_direction =
                    excluded.market_direction,

                reason =
                    excluded.reason,

                confidence =
                    excluded.confidence,

                raw_json =
                    excluded.raw_json,

                created_at =
                    excluded.created_at
            """,
            (
                article_id,
                analysis_version,

                1
                if analysis.get(
                    "relevant"
                )
                else 0,

                analysis.get(
                    "summary",
                    ""
                ),

                int(
                    analysis.get(
                        "importance"
                    )
                    or 0
                ),

                analysis.get(
                    "market_direction",
                    "Nötr",
                ),

                analysis.get(
                    "reason",
                    "",
                ),

                float(
                    analysis.get(
                        "confidence"
                    )
                    or 0
                ),

                json.dumps(
                    analysis,
                    ensure_ascii=False,
                ),

                utc_now(),
            ),
        )

        row = conn.execute(
            """
            SELECT id
            FROM analyses

            WHERE article_id = ?
            AND analysis_version = ?
            """,
            (
                article_id,
                analysis_version,
            ),
        ).fetchone()

        analysis_id = int(
            row["id"]
        )

        conn.execute(
            """
            DELETE FROM targets
            WHERE analysis_id = ?
            """,
            (
                analysis_id,
            ),
        )

        for target in (
            analysis.get(
                "target_instruments",
                []
            )
            or []
        ):

            if not isinstance(
                target,
                dict
            ):

                continue

            symbol = str(
                target.get(
                    "symbol"
                )
                or ""
            ).strip()

            if not symbol:

                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO targets (
                    analysis_id,
                    symbol,
                    instrument_type,
                    name,
                    market
                )

                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    symbol,
                    target.get(
                        "type"
                    ),
                    target.get(
                        "name"
                    ),
                    target.get(
                        "market"
                    ),
                ),
            )

        conn.commit()

        return analysis_id

    finally:

        conn.close()


# =========================================================
# KNOWLEDGE SOURCES
# =========================================================

def add_knowledge_source(
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    published_at: str | None = None,
    author: str | None = None,
    access_note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:

    conn = get_connection()

    try:

        if url:

            conn.execute(
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

                ON CONFLICT(url)

                DO UPDATE SET
                    title = excluded.title,
                    published_at =
                        excluded.published_at,
                    author =
                        excluded.author,
                    access_note =
                        excluded.access_note,
                    metadata_json =
                        excluded.metadata_json
                """,
                (
                    source_type,
                    title,
                    url,
                    published_at,
                    author,
                    access_note,
                    json.dumps(
                        metadata or {},
                        ensure_ascii=False,
                    ),
                    utc_now(),
                ),
            )

            row = conn.execute(
                """
                SELECT id
                FROM knowledge_sources
                WHERE url = ?
                """,
                (
                    url,
                ),
            ).fetchone()

        else:

            conn.execute(
                """
                INSERT INTO knowledge_sources (
                    source_type,
                    title,
                    published_at,
                    author,
                    access_note,
                    metadata_json,
                    created_at
                )

                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_type,
                    title,
                    published_at,
                    author,
                    access_note,
                    json.dumps(
                        metadata or {},
                        ensure_ascii=False,
                    ),
                    utc_now(),
                ),
            )

            row = conn.execute(
                """
                SELECT id
                FROM knowledge_sources

                ORDER BY id DESC

                LIMIT 1
                """
            ).fetchone()

        conn.commit()

        return int(
            row["id"]
        )

    finally:

        conn.close()


# =========================================================
# KNOWLEDGE ITEMS
# =========================================================

def add_knowledge_item(
    content: str,
    item_type: str,
    title: str | None = None,
    summary: str | None = None,
    method: str | None = None,
    symbols: list[str] | None = None,
    tags: list[str] | None = None,
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
    source_id: int | None = None,
) -> int:

    clean_content = str(
        content or ""
    ).strip()

    if not clean_content:

        raise ValueError(
            "Knowledge content cannot be empty."
        )

    conn = get_connection()

    try:

        conn.execute(
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

            ON CONFLICT(
                source_id,
                item_type,
                title
            )

            DO UPDATE SET

                content =
                    excluded.content,

                summary =
                    excluded.summary,

                method =
                    excluded.method,

                symbols_json =
                    excluded.symbols_json,

                tags_json =
                    excluded.tags_json,

                confidence =
                    excluded.confidence,

                metadata_json =
                    excluded.metadata_json
            """,
            (
                source_id,

                item_type,

                title,

                clean_content,

                summary,

                method,

                json.dumps(
                    symbols or [],
                    ensure_ascii=False,
                ),

                json.dumps(
                    tags or [],
                    ensure_ascii=False,
                ),

                confidence,

                json.dumps(
                    metadata or {},
                    ensure_ascii=False,
                ),

                utc_now(),
            ),
        )

        row = conn.execute(
            """
            SELECT id
            FROM knowledge_items

            WHERE source_id IS ?
            AND item_type = ?
            AND title IS ?

            ORDER BY id DESC

            LIMIT 1
            """,
            (
                source_id,
                item_type,
                title,
            ),
        ).fetchone()

        conn.commit()

        return int(
            row["id"]
        )

    finally:

        conn.close()


# =========================================================
# VISUAL ASSETS
# =========================================================

def add_visual_asset(
    file_path: str,
    asset_type: str = "chart",
    source_id: int | None = None,
    description: str | None = None,
) -> int:

    conn = get_connection()

    try:

        cursor = conn.execute(
            """
            INSERT INTO visual_assets (
                source_id,
                asset_type,
                file_path,
                description,
                created_at
            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_id,
                asset_type,
                file_path,
                description,
                utc_now(),
            ),
        )

        conn.commit()

        return int(
            cursor.lastrowid
        )

    finally:

        conn.close()


# =========================================================
# KNOWLEDGE SEARCH
# =========================================================

def search_knowledge(
    query: str,
    limit: int = 8,
) -> list[dict[str, Any]]:

    query = str(
        query or ""
    ).strip()

    if not query:

        return []

    words = [
        word
        for word in query
        .replace(",", " ")
        .split()
        if word
    ]

    clauses = []

    params: list[Any] = []

    for word in words[:8]:

        like = f"%{word}%"

        clauses.append(
            """
            (
                title LIKE ?
                OR content LIKE ?
                OR summary LIKE ?
                OR method LIKE ?
                OR tags_json LIKE ?
                OR symbols_json LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
                like,
                like,
                like,
            ]
        )

    where = (
        " OR ".join(
            clauses
        )
        if clauses
        else "1=1"
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            f"""
            SELECT

                ki.*,

                ks.source_type,

                ks.title AS source_title,

                ks.url AS source_url,

                ks.author AS source_author

            FROM knowledge_items ki

            LEFT JOIN knowledge_sources ks

                ON ks.id = ki.source_id

            WHERE {where}

            ORDER BY ki.id DESC

            LIMIT ?
            """,
            [
                *params,
                limit,
            ],
        ).fetchall()

        results = []

        for row in rows:

            item = dict(row)

            for field in (
                "symbols_json",
                "tags_json",
                "metadata_json",
            ):

                try:

                    item[field] = json.loads(
                        item[field]
                        or "{}"
                        if field == "metadata_json"
                        else item[field]
                        or "[]"
                    )

                except (
                    json.JSONDecodeError,
                    TypeError,
                ):

                    item[field] = (
                        {}
                        if field == "metadata_json"
                        else []
                    )

            results.append(
                item
            )

        return results

    finally:

        conn.close()


# =========================================================
# LEARNING: EXPERIMENT
# =========================================================

def create_learning_experiment(
    method_name: str,
    symbol: str,
    method_type: str | None = None,
    market: str | None = None,
    timeframe: str | None = None,
    signal_direction: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    knowledge_id: int | None = None,
) -> int:

    conn = get_connection()

    try:

        cursor = conn.execute(
            """
            INSERT INTO learning_experiments (

                knowledge_id,

                method_name,

                method_type,

                symbol,

                market,

                timeframe,

                signal_direction,

                start_date,

                end_date,

                status,

                parameters_json,

                created_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                knowledge_id,

                method_name,

                method_type,

                symbol,

                market,

                timeframe,

                signal_direction,

                start_date,

                end_date,

                "created",

                json.dumps(
                    parameters or {},
                    ensure_ascii=False,
                ),

                utc_now(),
            ),
        )

        conn.commit()

        return int(
            cursor.lastrowid
        )

    finally:

        conn.close()


def update_experiment_status(
    experiment_id: int,
    status: str,
) -> None:

    conn = get_connection()

    try:

        conn.execute(
            """
            UPDATE learning_experiments

            SET status = ?

            WHERE id = ?
            """,
            (
                status,
                experiment_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# LEARNING: RESULTS
# =========================================================

def add_experiment_result(
    experiment_id: int,
    observation_date: str | None = None,
    entry_price: float | None = None,
    price_1d: float | None = None,
    price_5d: float | None = None,
    price_20d: float | None = None,
    return_1d: float | None = None,
    return_5d: float | None = None,
    return_20d: float | None = None,
    max_favorable_move: float | None = None,
    max_adverse_move: float | None = None,
    result_1d: str | None = None,
    result_5d: str | None = None,
    result_20d: str | None = None,
    market_regime: str | None = None,
    volume_state: str | None = None,
    volatility_state: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:

    conn = get_connection()

    try:

        cursor = conn.execute(
            """
            INSERT INTO experiment_results (

                experiment_id,

                observation_date,

                entry_price,

                price_1d,

                price_5d,

                price_20d,

                return_1d,

                return_5d,

                return_20d,

                max_favorable_move,

                max_adverse_move,

                result_1d,

                result_5d,

                result_20d,

                market_regime,

                volume_state,

                volatility_state,

                metadata_json,

                created_at

            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                experiment_id,

                observation_date,

                entry_price,

                price_1d,

                price_5d,

                price_20d,

                return_1d,

                return_5d,

                return_20d,

                max_favorable_move,

                max_adverse_move,

                result_1d,

                result_5d,

                result_20d,

                market_regime,

                volume_state,

                volatility_state,

                json.dumps(
                    metadata or {},
                    ensure_ascii=False,
                ),

                utc_now(),
            ),
        )

        conn.commit()

        return int(
            cursor.lastrowid
        )

    finally:

        conn.close()


# =========================================================
# LEARNING: STATISTICS
# =========================================================

def get_experiment_statistics(
    experiment_id: int,
) -> dict[str, Any]:

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT

                COUNT(*) AS sample_size,

                AVG(return_1d)
                    AS avg_return_1d,

                AVG(return_5d)
                    AS avg_return_5d,

                AVG(return_20d)
                    AS avg_return_20d

            FROM experiment_results

            WHERE experiment_id = ?
            """,
            (
                experiment_id,
            ),
        ).fetchone()

        return dict(row)

    finally:

        conn.close()


# =========================================================
# LEARNING: SAVE RULE
# =========================================================

def save_learned_rule(
    method_name: str,
    condition_name: str,
    sample_size: int,
    method_type: str | None = None,
    symbol: str | None = None,
    market: str | None = None,
    timeframe: str | None = None,
    success_rate: float | None = None,
    average_return: float | None = None,
    average_return_5d: float | None = None,
    average_return_20d: float | None = None,
    best_return: float | None = None,
    worst_return: float | None = None,
    confidence: float | None = None,
    observation: str | None = None,
) -> int:

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT INTO learned_rules (

                method_name,

                method_type,

                symbol,

                market,

                timeframe,

                condition_name,

                sample_size,

                success_rate,

                average_return,

                average_return_5d,

                average_return_20d,

                best_return,

                worst_return,

                confidence,

                observation,

                created_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(
                method_name,
                symbol,
                timeframe,
                condition_name
            )

            DO UPDATE SET

                method_type =
                    excluded.method_type,

                market =
                    excluded.market,

                sample_size =
                    excluded.sample_size,

                success_rate =
                    excluded.success_rate,

                average_return =
                    excluded.average_return,

                average_return_5d =
                    excluded.average_return_5d,

                average_return_20d =
                    excluded.average_return_20d,

                best_return =
                    excluded.best_return,

                worst_return =
                    excluded.worst_return,

                confidence =
                    excluded.confidence,

                observation =
                    excluded.observation,

                created_at =
                    excluded.created_at
            """,
            (
                method_name,

                method_type,

                symbol,

                market,

                timeframe,

                condition_name,

                sample_size,

                success_rate,

                average_return,

                average_return_5d,

                average_return_20d,

                best_return,

                worst_return,

                confidence,

                observation,

                utc_now(),
            ),
        )

        row = conn.execute(
            """
            SELECT id

            FROM learned_rules

            WHERE method_name = ?

            AND symbol IS ?

            AND timeframe IS ?

            AND condition_name = ?

            """,
            (
                method_name,
                symbol,
                timeframe,
                condition_name,
            ),
        ).fetchone()

        conn.commit()

        return int(
            row["id"]
        )

    finally:

        conn.close()


# =========================================================
# LEARNING: GET RULES
# =========================================================

def get_learned_rules(
    method_name: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        query = """
            SELECT *
            FROM learned_rules
            WHERE 1 = 1
        """

        params: list[Any] = []

        if method_name:

            query += """
                AND method_name = ?
            """

            params.append(
                method_name
            )

        if symbol:

            query += """
                AND symbol = ?
            """

            params.append(
                symbol
            )

        query += """
            ORDER BY confidence DESC,
                     sample_size DESC
        """

        rows = conn.execute(
            query,
            params,
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":

    init_db()

    print(
        "✅ MarketHQ SQLite database hazır."
    )

    print(
        f"📁 {DB_PATH}"
    )

    print(
        "🧠 Learning tables hazır:"
    )

    print(
        "   - learning_experiments"
    )

    print(
        "   - experiment_results"
    )

    print(
        "   - learned_rules"
    )
