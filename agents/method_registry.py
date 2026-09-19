import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# =========================================================
# PROJECT ROOT
# =========================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


# =========================================================
# DATABASE
# =========================================================

from database import (
    get_connection,
    init_db,
)


# =========================================================
# CONFIG
# =========================================================

REGISTRY_VERSION = "method-registry-v3"

SIMILARITY_THRESHOLD = 0.94


# =========================================================
# VALID CATEGORIES
# =========================================================

VALID_CATEGORIES = {
    "indicator",
    "filter",
    "algorithm",
    "tradingview_method",
    "python_method",
    "chart_method",
    "trend_method",
    "momentum_method",
    "volume_method",
    "scan_method",
    "system",
    "education",
    "other",
}


# =========================================================
# TIME
# =========================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# REGISTRY TABLES
# =========================================================

def init_registry_tables() -> None:

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS method_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                canonical_name TEXT NOT NULL,

                category TEXT NOT NULL,

                description TEXT,

                source_count INTEGER NOT NULL DEFAULT 0,

                confidence REAL NOT NULL DEFAULT 0.50,

                status TEXT NOT NULL DEFAULT 'candidate',

                registry_version TEXT NOT NULL,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                UNIQUE(
                    canonical_name,
                    category
                )
            );


            CREATE TABLE IF NOT EXISTS method_registry_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                method_id INTEGER NOT NULL,

                knowledge_id INTEGER NOT NULL,

                relation TEXT NOT NULL DEFAULT 'member',

                similarity REAL,

                created_at TEXT NOT NULL,

                UNIQUE(
                    method_id,
                    knowledge_id
                ),

                FOREIGN KEY(
                    method_id
                )
                REFERENCES method_registry(id)
                ON DELETE CASCADE
            );


            CREATE TABLE IF NOT EXISTS method_similarity_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                method_id_a INTEGER NOT NULL,

                method_id_b INTEGER NOT NULL,

                similarity REAL NOT NULL,

                status TEXT NOT NULL DEFAULT 'review',

                created_at TEXT NOT NULL,

                UNIQUE(
                    method_id_a,
                    method_id_b
                ),

                FOREIGN KEY(
                    method_id_a
                )
                REFERENCES method_registry(id)
                ON DELETE CASCADE,

                FOREIGN KEY(
                    method_id_b
                )
                REFERENCES method_registry(id)
                ON DELETE CASCADE
            );


            CREATE INDEX IF NOT EXISTS idx_registry_category
                ON method_registry(category);

            CREATE INDEX IF NOT EXISTS idx_registry_status
                ON method_registry(status);

            CREATE INDEX IF NOT EXISTS idx_registry_item_method
                ON method_registry_items(method_id);

            CREATE INDEX IF NOT EXISTS idx_registry_item_knowledge
                ON method_registry_items(knowledge_id);

            CREATE INDEX IF NOT EXISTS idx_similarity_a
                ON method_similarity_candidates(method_id_a);

            CREATE INDEX IF NOT EXISTS idx_similarity_b
                ON method_similarity_candidates(method_id_b);
            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# RESET OLD REGISTRY
# =========================================================

def reset_registry() -> None:

    conn = get_connection()

    try:

        # Foreign key cascade handles children.
        conn.execute(
            "DELETE FROM method_similarity_candidates"
        )

        conn.execute(
            "DELETE FROM method_registry_items"
        )

        conn.execute(
            "DELETE FROM method_registry"
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# NORMALIZE TEXT
# =========================================================

def normalize_text(
    value: str | None,
) -> str:

    if not value:

        return ""

    text = str(
        value
    ).lower().strip()

    replacements = {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    text = re.sub(
        r"[\[\]\(\)\{\}:,_./\\\-]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# =========================================================
# SIMILARITY
# =========================================================

def similarity(
    a: str,
    b: str,
) -> float:

    a = normalize_text(
        a
    )

    b = normalize_text(
        b
    )

    if not a or not b:

        return 0.0

    if a == b:

        return 1.0

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


# =========================================================
# LOAD CONTENT JSON
# =========================================================

def parse_method_content(
    raw_content: Any,
) -> dict[str, Any]:

    if isinstance(
        raw_content,
        dict,
    ):

        return raw_content

    try:

        parsed = json.loads(
            str(
                raw_content
                or ""
            )
        )

        if isinstance(
            parsed,
            dict,
        ):

            return parsed

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):

        pass

    return {}


# =========================================================
# EXTRACT METHOD TYPE
# =========================================================

def detect_category(
    item: dict[str, Any],
) -> str:

    # -----------------------------------------------------
    # 1. Content JSON
    # -----------------------------------------------------

    structured = parse_method_content(
        item.get("content")
    )

    candidates = [
        structured.get("type"),
        structured.get("method_type"),
        item.get("item_type"),
    ]

    # -----------------------------------------------------
    # 2. Metadata JSON
    # -----------------------------------------------------

    metadata = parse_method_content(
        item.get("metadata_json")
    )

    candidates.extend(
        [
            metadata.get(
                "type"
            ),
            metadata.get(
                "method_type"
            ),
        ]
    )

    # -----------------------------------------------------
    # 3. Candidate evaluation
    # -----------------------------------------------------

    for candidate in candidates:

        category = str(
            candidate
            or ""
        ).strip().lower()

        if category in VALID_CATEGORIES:

            return category

    return infer_category_from_text(
        item
    )


# =========================================================
# TEXT-BASED FALLBACK CATEGORY
# =========================================================

def infer_category_from_text(
    item: dict[str, Any],
) -> str:

    title = str(
        item.get(
            "title"
        )
        or ""
    ).lower()

    content = str(
        item.get(
            "content"
        )
        or ""
    ).lower()

    combined = (
        title
        + " "
        + content[:4000]
    )

    if "tradingview" in combined:

        return "tradingview_method"

    if "python" in combined:

        return "python_method"

    if "algorit" in combined:

        return "algorithm"

    if "indikat" in combined:

        return "indicator"

    if "filtre" in combined:

        return "filter"

    if "momentum" in combined:

        return "momentum_method"

    if "regresyon" in combined:

        return "chart_method"

    if "hacim" in combined:

        return "volume_method"

    if "trend" in combined:

        return "trend_method"

    if "tarama" in combined:

        return "scan_method"

    return "other"


# =========================================================
# GET EXTRACTED METHODS
# =========================================================

def get_extracted_items() -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.summary,
                ki.method,
                ki.symbols_json,
                ki.tags_json,
                ki.confidence,
                ki.metadata_json,
                ki.item_type,

                ks.title AS source_title,
                ks.url AS source_url

            FROM knowledge_items ki

            LEFT JOIN knowledge_sources ks
                ON ks.id = ki.source_id

            WHERE ki.item_type =
                'extracted_method'

            ORDER BY ki.id
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# CREATE METHOD
# =========================================================

def create_method(
    canonical_name: str,
    category: str,
    description: str = "",
) -> int:

    now = utc_now()

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT OR IGNORE INTO method_registry (

                canonical_name,

                category,

                description,

                source_count,

                confidence,

                status,

                registry_version,

                created_at,

                updated_at

            )

            VALUES (
                ?, ?, ?, 0, 0.50,
                'candidate', ?, ?, ?
            )
            """,
            (
                canonical_name,
                category,
                description,
                REGISTRY_VERSION,
                now,
                now,
            ),
        )

        row = conn.execute(
            """
            SELECT id
            FROM method_registry

            WHERE canonical_name = ?
            AND category = ?
            """,
            (
                canonical_name,
                category,
            ),
        ).fetchone()

        conn.commit()

        return int(
            row["id"]
        )

    finally:

        conn.close()


# =========================================================
# ATTACH
# =========================================================

def attach_knowledge(
    method_id: int,
    knowledge_id: int,
    similarity_score: float,
) -> None:

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT OR IGNORE INTO method_registry_items (

                method_id,

                knowledge_id,

                relation,

                similarity,

                created_at

            )

            VALUES (?, ?, 'member', ?, ?)
            """,
            (
                method_id,
                knowledge_id,
                similarity_score,
                utc_now(),
            ),
        )

        conn.execute(
            """
            UPDATE method_registry

            SET source_count = (

                SELECT COUNT(*)

                FROM method_registry_items

                WHERE method_id = ?

            ),

            updated_at = ?

            WHERE id = ?
            """,
            (
                method_id,
                utc_now(),
                method_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# BUILD REGISTRY
# =========================================================

def build_registry() -> dict[str, int]:

    items = get_extracted_items()

    if not items:

        return {
            "source_items": 0,
            "exact_groups": 0,
            "methods_created": 0,
            "items_attached": 0,
            "similarity_candidates": 0,
        }

    # -----------------------------------------------------
    # Exact title + category groups
    # -----------------------------------------------------

    groups = defaultdict(list)

    for item in items:

        title = str(
            item.get(
                "title"
            )
            or ""
        ).strip()

        if not title:

            title = (
                "Unnamed FIN[SYS] Method"
            )

        category = detect_category(
            item
        )

        normalized_name = normalize_text(
            title
        )

        groups[
            (
                normalized_name,
                category,
            )
        ].append(
            item
        )

    methods_created = 0

    items_attached = 0

    # -----------------------------------------------------
    # Create exact canonical methods
    # -----------------------------------------------------

    for (
        group_key,
        group_items,
    ) in groups.items():

        first = group_items[0]

        canonical_name = str(
            first.get(
                "title"
            )
            or "Unnamed FIN[SYS] Method"
        ).strip()

        category = group_key[1]

        description = str(
            first.get(
                "summary"
            )
            or ""
        ).strip()

        method_id = create_method(
            canonical_name=canonical_name,
            category=category,
            description=description,
        )

        methods_created += 1

        for item in group_items:

            knowledge_id = int(
                item["id"]
            )

            score = similarity(
                canonical_name,
                str(
                    item.get(
                        "title"
                    )
                    or ""
                ),
            )

            attach_knowledge(
                method_id=method_id,

                knowledge_id=knowledge_id,

                similarity_score=score,
            )

            items_attached += 1

    # -----------------------------------------------------
    # Similarity review candidates.
    #
    # IMPORTANT:
    # We do NOT merge them automatically.
    # -----------------------------------------------------

    candidate_count = (
        create_similarity_candidates()
    )

    return {
        "source_items": len(
            items
        ),

        "exact_groups": len(
            groups
        ),

        "methods_created":
            methods_created,

        "items_attached":
            items_attached,

        "similarity_candidates":
            candidate_count,
    }


# =========================================================
# SIMILARITY CANDIDATES
# =========================================================

def create_similarity_candidates() -> int:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                canonical_name,
                category
            FROM method_registry
            ORDER BY id
            """
        ).fetchall()

        candidates = 0

        for i in range(
            len(rows)
        ):

            a = rows[i]

            for j in range(
                i + 1,
                len(rows)
            ):

                b = rows[j]

                # Different categories are not automatically
                # considered duplicates.
                if (
                    a["category"]
                    !=
                    b["category"]
                ):

                    continue

                score = similarity(
                    a["canonical_name"],
                    b["canonical_name"],
                )

                if score < SIMILARITY_THRESHOLD:

                    continue

                conn.execute(
                    """
                    INSERT OR IGNORE INTO
                    method_similarity_candidates (

                        method_id_a,

                        method_id_b,

                        similarity,

                        status,

                        created_at

                    )

                    VALUES (
                        ?, ?, ?, 'review', ?
                    )
                    """,
                    (
                        int(
                            a["id"]
                        ),

                        int(
                            b["id"]
                        ),

                        score,

                        utc_now(),
                    ),
                )

                candidates += 1

        conn.commit()

        return candidates

    finally:

        conn.close()


# =========================================================
# REPORT
# =========================================================

def get_registry_report() -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                canonical_name,
                category,
                source_count,
                confidence,
                status,
                registry_version,
                created_at,
                updated_at

            FROM method_registry

            ORDER BY
                category,
                canonical_name
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# CATEGORY REPORT
# =========================================================

def get_category_counts(
    report: list[dict[str, Any]],
) -> dict[str, int]:

    counts = defaultdict(int)

    for method in report:

        counts[
            method["category"]
        ] += 1

    return dict(
        sorted(
            counts.items()
        )
    )


# =========================================================
# PRINT REPORT
# =========================================================

def print_report(
    results: dict[str, int],
) -> None:

    report = (
        get_registry_report()
    )

    candidates = (
        get_similarity_candidates()
    )

    print()

    print(
        "=========================================="
    )

    print(
        "🧠 FIN[SYS] METHOD REGISTRY V3"
    )

    print(
        "=========================================="
    )

    print(
        f"Kaynak metodoloji kaydı: "
        f"{results['source_items']}"
    )

    print(
        f"Exact grup: "
        f"{results['exact_groups']}"
    )

    print(
        f"Canonical method: "
        f"{len(report)}"
    )

    print(
        f"Knowledge bağlantısı: "
        f"{results['items_attached']}"
    )

    print(
        f"Benzerlik inceleme adayı: "
        f"{results['similarity_candidates']}"
    )

    # -----------------------------------------------------
    # Categories
    # -----------------------------------------------------

    print()

    print(
        "KATEGORİLER"
    )

    print(
        "------------------------------------------"
    )

    category_counts = (
        get_category_counts(
            report
        )
    )

    for category, count in (
        category_counts.items()
    ):

        print(
            f"{category:<25} {count}"
        )

    # -----------------------------------------------------
    # Methods
    # -----------------------------------------------------

    print()

    print(
        "ÖRNEK METHODLAR"
    )

    print(
        "------------------------------------------"
    )

    for method in report[:50]:

        print(
            f"[{method['category']}] "
            f"{method['canonical_name']} "
            f"→ {method['source_count']} kaynak"
        )

    # -----------------------------------------------------
    # Similarity candidates
    # -----------------------------------------------------

    if candidates:

        print()

        print(
            "BENZERLİK İNCELEME ADAYLARI"
        )

        print(
            "------------------------------------------"
        )

        for candidate in candidates[:25]:

            print(
                f"{candidate['similarity']:.3f} | "
                f"[{candidate['category']}] "
                f"{candidate['method_a']} "
                f"<-> "
                f"{candidate['method_b']}"
            )


# =========================================================
# GET SIMILARITY CANDIDATES
# =========================================================

def get_similarity_candidates() -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                c.id,

                a.canonical_name
                    AS method_a,

                b.canonical_name
                    AS method_b,

                a.category,

                c.similarity,

                c.status

            FROM method_similarity_candidates c

            INNER JOIN method_registry a
                ON a.id = c.method_id_a

            INNER JOIN method_registry b
                ON b.id = c.method_id_b

            ORDER BY
                c.similarity DESC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=========================================="
    )

    print(
        "🧠 MARKET HQ METHOD REGISTRY V3"
    )

    print(
        "=========================================="
    )

    init_db()

    init_registry_tables()

    print(
        "✅ Registry tabloları hazır."
    )

    # -----------------------------------------------------
    # Old broken registry is removed.
    # Knowledge itself is NOT touched.
    # -----------------------------------------------------

    print(
        "♻️ Eski Registry temizleniyor..."
    )

    reset_registry()

    print(
        "✅ Eski Registry temizlendi."
    )

    print(
        "🧠 290 mevcut AI knowledge kaydı "
        "yeniden sınıflandırılıyor..."
    )

    results = build_registry()

    print_report(
        results
    )

    print()

    print(
        "✅ FIN[SYS] Method Registry V3 tamamlandı."
    )

    print(
        "API çağrısı yapılmadı."
    )

    print(
        "Bir sonraki aşama:"
    )

    print(
        "Canonical Method → "
        "AI doğrulama → "
        "Method Lab"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
