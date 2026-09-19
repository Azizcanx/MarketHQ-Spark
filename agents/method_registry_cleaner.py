from __future__ import annotations

import json
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "market_hq.db"

OUTPUT_FILE = (
    BASE_DIR
    / "method_registry_clean_v22.json"
)


# =========================================================
# CONFIG
# =========================================================

EXPECTED_REGISTRY_COUNT = 259

KNOWLEDGE_MATCH_MIN = 40

REAL_METHOD_SCORE = 68.0
POSSIBLE_METHOD_SCORE = 50.0

ALIAS_SIMILARITY_THRESHOLD = 0.88


# =========================================================
# TERMS
# =========================================================

WEBINAR_TERMS = {
    "webinar",
    "zoom",
    "sohbet",
    "online toplantı",
    "online toplantisi",
    "toplantı",
    "toplanti",
    "sunum",
    "chat",
}

EDUCATION_TERMS = {
    "eğitim",
    "egitim",
    "education",
    "ders",
    "kurs",
    "course",
    "eğitimi",
    "egitimi",
    "öğretim",
    "ogretim",
}

GENERAL_TERMS = {
    "başarı tablomuz",
    "basari tablomuz",
    "hakkımızda",
    "hakkimizda",
    "iletişim",
    "iletisim",
    "duyuru",
    "haberler",
    "haber",
    "about",
    "contact",
}

THEORY_TERMS = {
    "calculus",
    "matematik",
    "fizik",
    "kimya",
    "psikoloji",
    "davranışsal finans",
    "davranissal finans",
}

METHOD_TERMS = {
    "algoritma",
    "algorithm",
    "algoritmik",
    "metod",
    "method",
    "metodoloji",
    "yöntem",
    "yontem",
    "strateji",
    "strategy",
    "sistem",
    "system",
    "trend",
    "momentum",
    "tarama",
    "scan",
    "scanner",
    "indikatör",
    "indicator",
    "filtre",
    "filter",
    "bant",
    "band",
    "volatilite",
    "hacim",
    "volume",
    "sinyal",
    "signal",
    "formasyon",
    "pattern",
    "dip tepe",
    "dip-tepe",
    "çapraz",
    "cross",
    "regresyon",
    "regression",
    "frekans",
    "frequency",
    "makine öğrenmesi",
    "machine learning",
    "quant",
    "kantitatif",
}

CODE_TERMS = {
    "python",
    "pine",
    "pinescript",
    "kod",
    "code",
    "script",
    "scanner",
    "tarama kodu",
}

BUILDING_BLOCK_TERMS = {
    "bollinger",
    "bollinger band",
    "rsi",
    "macd",
    "ema",
    "sma",
    "wma",
    "hma",
    "atr",
    "adx",
    "stochastic",
    "cci",
    "obv",
    "vwap",
    "mfi",
    "roc",
    "ichimoku",
    "fibonacci",
    "heikin ashi",
    "hareketli ortalamalar",
    "hareketli ortalama",
    "destek ve direnç",
    "destek direnç",
}

SPECIAL_METHOD_TERMS = {
    "algoritma",
    "algorithm",
    "trend algoritması",
    "trend algoritma",
    "momentum algoritması",
    "momentum algoritma",
    "volatilite algoritması",
    "volatilite algoritma",
    "alış satış sistemi",
    "alis satis sistemi",
    "sistem",
    "system",
    "tarama uygulaması",
    "tarama uygulamasi",
    "tarama sistemi",
    "tarama algoritması",
    "tarama algoritmasi",
    "kantitatif tarama",
    "quantitative scan",
    "frekans analiz algoritması",
    "regresyon algoritması",
    "makine öğrenmesi",
    "machine learning",
    "çapraz fonksiyon tarama",
    "capraz fonksiyon tarama",
}

STRONG_METHOD_NAME_TERMS = {
    "algoritma",
    "algorithm",
    "sistem",
    "system",
    "tarama",
    "scanner",
    "scan",
    "momentum",
    "trend",
    "sinyal",
    "signal",
    "volatilite",
    "regresyon",
    "regression",
    "kantitatif",
    "quant",
    "çapraz fonksiyon",
    "capraz fonksiyon",
    "makine öğrenmesi",
    "machine learning",
    "tarama uygulaması",
    "tarama sistemi",
    "tarama kodu",
    "sinyal tarama",
}

GENERIC_UNKNOWN_TERMS = {
    "makale",
    "makaleler",
    "blog",
    "blogu",
    "podcast",
    "podcasts",
    "kılavuz",
    "kilavuz",
    "rehber",
    "guide",
    "yatırım",
    "yatirim",
    "yatırımcı",
    "yatirimci",
    "portföy",
    "portfoy",
}


# =========================================================
# TEXT
# =========================================================

def normalize_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    text = str(value).strip().lower()

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
            new,
        )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    text = re.sub(
        r"[\[\]\(\)\{\}]",
        " ",
        text,
    )

    text = re.sub(
        r"[-_/|:+]+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def compact_text(
    value: Any,
) -> str:
    return normalize_text(
        value
    ).replace(
        " ",
        "",
    )


def text_tokens(
    value: Any,
) -> set[str]:
    return {
        token
        for token
        in normalize_text(value).split()
        if len(token) >= 2
    }


def contains_any(
    text: str,
    terms: set[str],
) -> bool:
    normalized = normalize_text(
        text
    )

    return any(
        term in normalized
        for term in terms
    )


def similarity(
    first: str,
    second: str,
) -> float:
    a = compact_text(first)
    b = compact_text(second)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    seq = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    a_tokens = text_tokens(first)
    b_tokens = text_tokens(second)

    token_score = 0.0

    if a_tokens and b_tokens:
        union = a_tokens | b_tokens
        intersection = (
            a_tokens & b_tokens
        )

        if union:
            token_score = (
                len(intersection)
                / len(union)
            )

    return min(
        1.0,
        seq * 0.65
        + token_score * 0.35,
    )


# =========================================================
# MARKERS
# =========================================================

def extract_package(
    text: str,
) -> str | None:
    normalized = normalize_text(
        text
    )

    match = re.search(
        r"\b([1-9][0-9]*)\s*paket\b",
        normalized,
    )

    if match:
        return (
            f"paket_{match.group(1)}"
        )

    return None


def extract_wave(
    text: str,
) -> str | None:
    normalized = normalize_text(
        text
    )

    if (
        re.search(
            r"\bsw\b",
            normalized,
        )
        or "kisa dalga"
        in normalized
    ):
        return "sw"

    if (
        re.search(
            r"\blw\b",
            normalized,
        )
        or "uzun dalga"
        in normalized
    ):
        return "lw"

    return None


def extract_directions(
    text: str,
) -> set[str]:
    normalized = normalize_text(
        text
    )

    markers = set()

    if "trend" in normalized:
        markers.add("trend")

    if "momentum" in normalized:
        markers.add("momentum")

    if "volatilite" in normalized:
        markers.add("volatilite")

    if (
        "regresyon"
        in normalized
        or "regression"
        in normalized
    ):
        markers.add("regression")

    return markers


def extract_markers(
    text: str,
) -> set[str]:
    markers = set()

    package = extract_package(
        text
    )

    if package:
        markers.add(package)

    wave = extract_wave(
        text
    )

    if wave:
        markers.add(
            f"wave_{wave}"
        )

    markers.update(
        extract_directions(
            text
        )
    )

    return markers


def strip_implementation_words(
    text: str,
) -> str:
    normalized = normalize_text(
        text
    )

    remove_terms = [
        "python sinyal tarama kodu",
        "python tarama kodu",
        "sinyalleri python tarama kodu",
        "python kodu",
        "tarama kodu",
        "python",
        "pine script",
        "pinescript",
        "uygulamasi",
        "uygulama",
        "script",
        "code",
        "kod",
        "agresif",
    ]

    for term in remove_terms:
        normalized = normalized.replace(
            normalize_text(term),
            " ",
        )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip()


# =========================================================
# MERGE SAFETY
# =========================================================

def incompatible_markers(
    first: str,
    second: str,
) -> bool:
    first_markers = extract_markers(
        first
    )

    second_markers = extract_markers(
        second
    )

    first_packages = {
        marker
        for marker in first_markers
        if marker.startswith(
            "paket_"
        )
    }

    second_packages = {
        marker
        for marker in second_markers
        if marker.startswith(
            "paket_"
        )
    }

    if (
        first_packages
        and second_packages
        and first_packages
        != second_packages
    ):
        return True

    first_waves = {
        marker
        for marker in first_markers
        if marker.startswith(
            "wave_"
        )
    }

    second_waves = {
        marker
        for marker in second_markers
        if marker.startswith(
            "wave_"
        )
    }

    if (
        first_waves
        and second_waves
        and first_waves
        != second_waves
    ):
        return True

    first_direction = {
        marker
        for marker in first_markers
        if marker
        in {
            "trend",
            "momentum",
        }
    }

    second_direction = {
        marker
        for marker in second_markers
        if marker
        in {
            "trend",
            "momentum",
        }
    }

    if (
        first_direction
        and second_direction
        and first_direction
        != second_direction
    ):
        return True

    return False


def names_can_merge(
    first: str,
    second: str,
) -> tuple[bool, str]:
    first_normalized = (
        normalize_text(first)
    )

    second_normalized = (
        normalize_text(second)
    )

    if (
        first_normalized
        == second_normalized
    ):
        return (
            True,
            "exact_normalized",
        )

    if (
        compact_text(first)
        == compact_text(second)
    ):
        return (
            True,
            "exact_compact",
        )

    if incompatible_markers(
        first,
        second,
    ):
        return (
            False,
            "incompatible_markers",
        )

    first_base = (
        strip_implementation_words(
            first
        )
    )

    second_base = (
        strip_implementation_words(
            second
        )
    )

    if (
        first_base
        and second_base
        and first_base
        == second_base
    ):
        return (
            True,
            "same_base",
        )

    score = similarity(
        first_base,
        second_base,
    )

    if (
        score
        >= ALIAS_SIMILARITY_THRESHOLD
    ):
        return (
            True,
            "strong_alias",
        )

    return (
        False,
        "not_alias",
    )


# =========================================================
# SQLITE
# =========================================================

def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(DB_PATH)
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def discover_registry_table(
    connection: sqlite3.Connection,
) -> str | None:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name
        """
    ).fetchall()

    for row in rows:
        table_name = row["name"]
        lowered = table_name.lower()

        if (
            "method" in lowered
            and "registry" in lowered
        ):
            return table_name

    return None


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> list[str]:
    rows = connection.execute(
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()

    return [
        row["name"]
        for row in rows
    ]


def find_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    lookup = {
        column.lower(): column
        for column in columns
    }

    for candidate in candidates:
        if (
            candidate.lower()
            in lookup
        ):
            return lookup[
                candidate.lower()
            ]

    return None


# =========================================================
# REGISTRY LOAD
# =========================================================

def load_registry(
    connection: sqlite3.Connection,
) -> tuple[
    str,
    list[dict[str, Any]],
]:
    table_name = (
        discover_registry_table(
            connection
        )
    )

    if not table_name:
        raise RuntimeError(
            "method_registry tablosu bulunamadı."
        )

    columns = table_columns(
        connection,
        table_name,
    )

    id_column = find_column(
        columns,
        [
            "id",
            "method_id",
            "registry_id",
        ],
    )

    name_column = find_column(
        columns,
        [
            "canonical_name",
            "method_name",
            "name",
            "title",
            "method",
        ],
    )

    if not name_column:
        raise RuntimeError(
            "Registry isim sütunu bulunamadı."
        )

    rows = connection.execute(
        f'SELECT * FROM "{table_name}"'
    ).fetchall()

    registry = []

    for row in rows:
        raw = dict(row)

        registry.append(
            {
                "registry_id": (
                    raw.get(
                        id_column
                    )
                    if id_column
                    else None
                ),
                "name": str(
                    raw.get(
                        name_column
                    )
                    or ""
                ).strip(),
                "raw": raw,
            }
        )

    return (
        table_name,
        registry,
    )


# =========================================================
# KNOWLEDGE LOAD
# =========================================================

def load_knowledge_items(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            rowid AS _rowid,
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
        """
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# KNOWLEDGE MATCHING
# =========================================================

def knowledge_score(
    registry_name: str,
    item: dict[str, Any],
) -> float:
    title = (
        item.get("title")
        or ""
    )

    method = (
        item.get("method")
        or ""
    )

    summary = (
        item.get("summary")
        or ""
    )

    content = (
        item.get("content")
        or ""
    )

    title_score = similarity(
        registry_name,
        title,
    )

    method_score = (
        similarity(
            registry_name,
            method,
        )
        if method
        else 0.0
    )

    summary_score = (
        similarity(
            registry_name,
            summary,
        )
        if summary
        else 0.0
    )

    score = (
        title_score * 55.0
        + method_score * 25.0
        + summary_score * 10.0
    )

    blob = " ".join(
        [
            str(title),
            str(method),
            str(summary),
            str(content),
        ]
    )

    if contains_any(
        blob,
        METHOD_TERMS,
    ):
        score += 5.0

    if contains_any(
        blob,
        CODE_TERMS,
    ):
        score += 5.0

    return min(
        100.0,
        score,
    )


def best_matches(
    registry_name: str,
    knowledge_items: list[
        dict[str, Any]
    ],
    limit: int = 5,
) -> list[dict[str, Any]]:
    matches = []

    for item in knowledge_items:
        score = knowledge_score(
            registry_name,
            item,
        )

        if score < KNOWLEDGE_MATCH_MIN:
            continue

        matches.append(
            {
                "score": round(
                    score,
                    2,
                ),
                "knowledge": item,
            }
        )

    matches.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True,
    )

    return matches[:limit]


# =========================================================
# CLASSIFICATION
# =========================================================

def classify_title(
    name: str,
) -> str:
    normalized = normalize_text(
        name
    )

    if not normalized:
        return "unknown"

    if contains_any(
        normalized,
        WEBINAR_TERMS,
    ):
        return "webinar"

    if contains_any(
        normalized,
        EDUCATION_TERMS,
    ):
        return "education"

    if contains_any(
        normalized,
        GENERAL_TERMS,
    ):
        return "general"

    if contains_any(
        normalized,
        THEORY_TERMS,
    ):
        return "theory"

    return "unknown"


def is_building_block(
    name: str,
) -> bool:
    normalized = normalize_text(
        name
    )

    if contains_any(
        normalized,
        SPECIAL_METHOD_TERMS,
    ):
        return False

    if normalized in {
        "bollinger bantlari",
        "rsi",
        "macd",
        "ema",
        "sma",
        "wma",
        "atr",
        "adx",
        "ichimoku",
        "heikin ashi",
        "fibonacci duzeltme seviyeleri",
        "hareketli ortalamalar",
        "hareketli ortalama",
        "destek ve direnc",
        "destek ve direnc analizi",
    }:
        return True

    building_score = 0

    for term in BUILDING_BLOCK_TERMS:
        if term in normalized:
            building_score += 1

    method_score = 0

    for term in SPECIAL_METHOD_TERMS:
        if term in normalized:
            method_score += 1

    return (
        building_score >= 1
        and method_score == 0
    )


def method_name_strength(
    name: str,
) -> float:
    normalized = normalize_text(
        name
    )

    score = 0.0

    strong_hits = sum(
        1
        for term
        in STRONG_METHOD_NAME_TERMS
        if term in normalized
    )

    method_hits = sum(
        1
        for term
        in METHOD_TERMS
        if term in normalized
    )

    code_hits = sum(
        1
        for term
        in CODE_TERMS
        if term in normalized
    )

    score += min(
        60.0,
        strong_hits * 15.0,
    )

    score += min(
        20.0,
        method_hits * 4.0,
    )

    score += min(
        10.0,
        code_hits * 5.0,
    )

    if (
        len(normalized.split())
        <= 3
        and normalized
    ):
        # Özel isim ihtimali
        score += 5.0

    if contains_any(
        normalized,
        GENERIC_UNKNOWN_TERMS,
    ):
        score -= 10.0

    if is_building_block(
        name
    ):
        score -= 25.0

    return max(
        0.0,
        min(
            100.0,
            score,
        ),
    )


def analyze_entry(
    entry: dict[str, Any],
    knowledge_items: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    name = entry[
        "name"
    ]

    title_class = classify_title(
        name
    )

    matches = best_matches(
        name,
        knowledge_items,
    )

    support = (
        matches[0]["score"]
        if matches
        else 0.0
    )

    name_strength = (
        method_name_strength(
            name
        )
    )

    method_evidence = False
    strong_method_evidence = False

    for match in matches:
        item = match[
            "knowledge"
        ]

        blob = " ".join(
            [
                str(
                    item.get("title")
                    or ""
                ),
                str(
                    item.get("method")
                    or ""
                ),
                str(
                    item.get("summary")
                    or ""
                ),
                str(
                    item.get("content")
                    or ""
                ),
            ]
        )

        if contains_any(
            blob,
            METHOD_TERMS,
        ):
            method_evidence = True

        if (
            match["score"]
            >= 65.0
            and contains_any(
                blob,
                METHOD_TERMS,
            )
        ):
            strong_method_evidence = True

    final_score = (
        support * 0.45
        + name_strength * 0.55
    )

    # ---------------------------------------------
    # Hard classes
    # ---------------------------------------------

    if title_class in {
        "education",
        "webinar",
        "theory",
        "general",
    }:
        classification = (
            title_class
        )

    elif is_building_block(
        name
    ):
        classification = (
            "building_block"
        )

    # ---------------------------------------------
    # Real method
    # ---------------------------------------------

    elif (
        (
            final_score
            >= REAL_METHOD_SCORE
        )
        and (
            strong_method_evidence
            or name_strength >= 75.0
        )
        and support >= 45.0
    ):
        classification = (
            "real_method"
        )

    # ---------------------------------------------
    # Possible method
    # ---------------------------------------------

    elif (
        (
            final_score
            >= POSSIBLE_METHOD_SCORE
        )
        and (
            method_evidence
            or name_strength >= 45.0
        )
    ):
        classification = (
            "possible_method"
        )

    # ---------------------------------------------
    # Strong-name rescue
    #
    # Knowledge eşleşmesi kötü olsa bile
    # açıkça method kimliği taşıyan kayıtları
    # unknown'a atma.
    # ---------------------------------------------

    elif (
        name_strength >= 55.0
        and contains_any(
            name,
            STRONG_METHOD_NAME_TERMS,
        )
    ):
        classification = (
            "possible_method"
        )

    else:
        classification = (
            "unknown"
        )

    confidence = min(
        100.0,
        (
            support * 0.45
            + name_strength * 0.35
            + (
                20.0
                if method_evidence
                else 0.0
            )
        ),
    )

    return {
        "registry_id": entry[
            "registry_id"
        ],
        "name": name,
        "classification": classification,
        "confidence": round(
            confidence,
            2,
        ),
        "knowledge_support": round(
            support,
            2,
        ),
        "method_name_strength": round(
            name_strength,
            2,
        ),
        "knowledge_matches": [
            {
                "score": match[
                    "score"
                ],
                "title": match[
                    "knowledge"
                ].get(
                    "title"
                ),
                "item_type": match[
                    "knowledge"
                ].get(
                    "item_type"
                ),
                "source_id": match[
                    "knowledge"
                ].get(
                    "source_id"
                ),
            }
            for match in matches
        ],
    }


# =========================================================
# CLUSTER
# =========================================================

class UnionFind:
    def __init__(
        self,
        size: int,
    ):
        self.parent = list(
            range(size)
        )

    def find(
        self,
        index: int,
    ) -> int:
        while (
            self.parent[index]
            != index
        ):
            self.parent[index] = (
                self.parent[
                    self.parent[index]
                ]
            )

            index = self.parent[
                index
            ]

        return index

    def union(
        self,
        first: int,
        second: int,
    ) -> None:
        root_a = self.find(
            first
        )

        root_b = self.find(
            second
        )

        if root_a == root_b:
            return

        self.parent[
            root_b
        ] = root_a


def build_clusters(
    analyzed: list[
        dict[str, Any]
    ],
) -> list[
    list[dict[str, Any]]
]:
    candidates = [
        item
        for item in analyzed
        if item[
            "classification"
        ]
        in {
            "real_method",
            "possible_method",
        }
    ]

    if not candidates:
        return []

    union_find = UnionFind(
        len(candidates)
    )

    for i in range(
        len(candidates)
    ):
        for j in range(
            i + 1,
            len(candidates),
        ):
            can_merge, _ = (
                names_can_merge(
                    candidates[i][
                        "name"
                    ],
                    candidates[j][
                        "name"
                    ],
                )
            )

            if can_merge:
                union_find.union(
                    i,
                    j,
                )

    groups = {}

    for index, item in enumerate(
        candidates
    ):
        root = union_find.find(
            index
        )

        groups.setdefault(
            root,
            [],
        ).append(
            item
        )

    return list(
        groups.values()
    )


# =========================================================
# CANONICAL
# =========================================================

def choose_canonical_name(
    group: list[
        dict[str, Any]
    ],
) -> str:
    def rank(
        item: dict[str, Any],
    ) -> tuple:
        name = item[
            "name"
        ]

        normalized = normalize_text(
            name
        )

        implementation_penalty = sum(
            1
            for term
            in {
                "python",
                "python kodu",
                "tarama kodu",
                "kod",
                "code",
                "script",
            }
            if term in normalized
        )

        return (
            item[
                "knowledge_support"
            ],
            item[
                "method_name_strength"
            ],
            item[
                "confidence"
            ],
            -implementation_penalty,
            -len(name),
        )

    return max(
        group,
        key=rank,
    )["name"]


def build_canonical_methods(
    groups: list[
        list[dict[str, Any]]
    ],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    methods = []
    duplicates = []

    for group in groups:
        canonical_name = (
            choose_canonical_name(
                group
            )
        )

        variants = list(
            dict.fromkeys(
                item["name"]
                for item in group
            )
        )

        registry_ids = [
            item["registry_id"]
            for item in group
        ]

        classification = (
            "real_method"
            if any(
                item[
                    "classification"
                ]
                == "real_method"
                for item in group
            )
            else "possible_method"
        )

        confidence = max(
            item["confidence"]
            for item in group
        )

        support = max(
            item[
                "knowledge_support"
            ]
            for item in group
        )

        knowledge_links = []

        for item in group:
            for match in item[
                "knowledge_matches"
            ]:
                knowledge_links.append(
                    {
                        "source_id": match[
                            "source_id"
                        ],
                        "title": match[
                            "title"
                        ],
                        "score": match[
                            "score"
                        ],
                    }
                )

        seen = set()
        unique_links = []

        for link in knowledge_links:
            key = (
                link["source_id"],
                link["title"],
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            unique_links.append(
                link
            )

        canonical_id = (
            "METHOD-"
            + compact_text(
                canonical_name
            )[:72]
        )

        methods.append(
            {
                "canonical_id": canonical_id,
                "canonical_name": canonical_name,
                "classification": classification,
                "confidence": round(
                    confidence,
                    2,
                ),
                "knowledge_support": round(
                    support,
                    2,
                ),
                "registry_variants": variants,
                "registry_count": len(
                    variants
                ),
                "registry_ids": registry_ids,
                "knowledge_links": unique_links,
            }
        )

        if len(variants) > 1:
            duplicates.append(
                {
                    "canonical_name": canonical_name,
                    "count": len(
                        variants
                    ),
                    "variants": variants,
                }
            )

    methods.sort(
        key=lambda item: (
            -item["confidence"],
            -item[
                "knowledge_support"
            ],
            item[
                "canonical_name"
            ].lower(),
        )
    )

    duplicates.sort(
        key=lambda item: (
            -item["count"],
            item[
                "canonical_name"
            ].lower(),
        )
    )

    return (
        methods,
        duplicates,
    )


# =========================================================
# SUMMARY
# =========================================================

def mean_or_zero(
    values: list[float],
) -> float:
    if not values:
        return 0.0

    return float(
        statistics.mean(
            values
        )
    )


def build_summary(
    registry: list[
        dict[str, Any]
    ],
    analyzed: list[
        dict[str, Any]
    ],
    methods: list[
        dict[str, Any]
    ],
    duplicates: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    counts = Counter(
        item["classification"]
        for item in analyzed
    )

    method_items = [
        item
        for item in analyzed
        if item[
            "classification"
        ]
        in {
            "real_method",
            "possible_method",
        }
    ]

    return {
        "raw_registry": len(
            registry
        ),
        "canonical_methods": len(
            methods
        ),
        "real_methods": counts.get(
            "real_method",
            0,
        ),
        "possible_methods": counts.get(
            "possible_method",
            0,
        ),
        "building_blocks": counts.get(
            "building_block",
            0,
        ),
        "education": counts.get(
            "education",
            0,
        ),
        "webinar": counts.get(
            "webinar",
            0,
        ),
        "theory": counts.get(
            "theory",
            0,
        ),
        "general": counts.get(
            "general",
            0,
        ),
        "unknown": counts.get(
            "unknown",
            0,
        ),
        "duplicate_groups": len(
            duplicates
        ),
        "average_confidence": round(
            mean_or_zero(
                [
                    item[
                        "confidence"
                    ]
                    for item
                    in method_items
                ]
            ),
            2,
        ),
        "average_knowledge_support": round(
            mean_or_zero(
                [
                    item[
                        "knowledge_support"
                    ]
                    for item
                    in method_items
                ]
            ),
            2,
        ),
    }


# =========================================================
# SANITY
# =========================================================

def sanity_check(
    methods: list[
        dict[str, Any]
    ],
) -> list[str]:
    warnings = []

    for method in methods:
        variants = method[
            "registry_variants"
        ]

        for i in range(
            len(variants)
        ):
            for j in range(
                i + 1,
                len(variants),
            ):
                first = variants[i]
                second = variants[j]

                if incompatible_markers(
                    first,
                    second,
                ):
                    warnings.append(
                        (
                            "Incompatible "
                            "variants merged: "
                            f"{first} <> "
                            f"{second}"
                        )
                    )

    return list(
        dict.fromkeys(
            warnings
        )
    )


# =========================================================
# OUTPUT
# =========================================================

def write_output(
    payload: dict[str, Any],
) -> None:
    temp_file = (
        OUTPUT_FILE.with_suffix(
            ".tmp"
        )
    )

    with temp_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temp_file.replace(
        OUTPUT_FILE
    )


# =========================================================
# DISPLAY
# =========================================================

def print_header(
    title: str,
) -> None:
    print()
    print(
        "=" * 76
    )
    print(title)
    print(
        "=" * 76
    )


def print_top_methods(
    methods: list[
        dict[str, Any]
    ],
    limit: int = 30,
) -> None:
    print_header(
        "🔬 TOP CANONICAL METHODS V2.2"
    )

    for index, method in enumerate(
        methods[:limit],
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{method['canonical_name']}"
        )

        print(
            "    "
            f"{method['classification']} | "
            f"Conf={method['confidence']:.1f} | "
            f"Support={method['knowledge_support']:.1f} | "
            f"Variants={method['registry_count']}"
        )


def print_duplicates(
    duplicates: list[
        dict[str, Any]
    ],
    limit: int = 40,
) -> None:
    print_header(
        "🧬 DUPLICATE / ALIAS GROUPS V2.2"
    )

    if not duplicates:
        print(
            "Duplicate grupu yok."
        )
        return

    for group in duplicates[
        :limit
    ]:
        print(
            f"- "
            f"{group['canonical_name']} "
            f"({group['count']} kayıt)"
        )

        for variant in group[
            "variants"
        ]:
            print(
                f"    • {variant}"
            )


def print_excluded(
    analyzed: list[
        dict[str, Any]
    ],
    limit: int = 120,
) -> None:
    excluded = [
        item
        for item in analyzed
        if item[
            "classification"
        ]
        not in {
            "real_method",
            "possible_method",
        }
    ]

    excluded.sort(
        key=lambda item: (
            item[
                "classification"
            ],
            item[
                "name"
            ].lower(),
        )
    )

    print_header(
        "🚫 METHOD HAVUZUNDAN AYRILANLAR"
    )

    for item in excluded[
        :limit
    ]:
        print(
            f"- "
            f"{item['registry_id']} | "
            f"{item['name']} | "
            f"{item['classification']}"
        )


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    print(
        "=" * 76
    )

    print(
        "🔬 FIN[SYS] METHOD REGISTRY CLEANER V2.2"
    )

    print(
        "=" * 76
    )

    print(
        f"Database: {DB_PATH}"
    )

    print(
        "Mode: non-destructive registry analysis"
    )

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database bulunamadı: "
            f"{DB_PATH}"
        )

    connection = connect_db()

    try:
        # -------------------------------------------------
        # REGISTRY
        # -------------------------------------------------

        print()
        print(
            "📥 Registry okunuyor..."
        )

        (
            registry_table,
            registry,
        ) = load_registry(
            connection
        )

        print(
            f"Registry table: "
            f"{registry_table}"
        )

        print(
            f"Raw registry: "
            f"{len(registry)}"
        )

        print(
            f"Expected registry: "
            f"{EXPECTED_REGISTRY_COUNT}"
        )

        # -------------------------------------------------
        # KNOWLEDGE
        # -------------------------------------------------

        print()
        print(
            "📥 Knowledge items okunuyor..."
        )

        knowledge_items = (
            load_knowledge_items(
                connection
            )
        )

        print(
            f"Knowledge items: "
            f"{len(knowledge_items)}"
        )

        # -------------------------------------------------
        # ANALYZE
        # -------------------------------------------------

        print()
        print(
            "🔎 Registry kayıtları "
            "sınıflandırılıyor..."
        )

        analyzed = []

        for entry in registry:
            analyzed.append(
                analyze_entry(
                    entry,
                    knowledge_items,
                )
            )

        # -------------------------------------------------
        # CLUSTER
        # -------------------------------------------------

        print(
            "🧬 Güvenli canonical / "
            "alias grupları oluşturuluyor..."
        )

        groups = build_clusters(
            analyzed
        )

        (
            methods,
            duplicates,
        ) = build_canonical_methods(
            groups
        )

        # -------------------------------------------------
        # SUMMARY
        # -------------------------------------------------

        summary = build_summary(
            registry,
            analyzed,
            methods,
            duplicates,
        )

        # -------------------------------------------------
        # SANITY
        # -------------------------------------------------

        warnings = sanity_check(
            methods
        )

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        payload = {
            "engine": {
                "name": (
                    "FIN[SYS] METHOD REGISTRY "
                    "CLEANER"
                ),
                "version": "2.2",
                "mode": (
                    "non-destructive"
                ),
            },
            "database": str(
                DB_PATH
            ),
            "registry_table": (
                registry_table
            ),
            "summary": summary,
            "sanity_warnings": warnings,
            "clean_registry": methods,
            "duplicate_groups": duplicates,
            "registry_analysis": analyzed,
        }

        write_output(
            payload
        )

        # -------------------------------------------------
        # SUMMARY
        # -------------------------------------------------

        print_header(
            "📊 REGISTRY CLEANING SUMMARY V2.2"
        )

        print(
            f"Raw registry: "
            f"{summary['raw_registry']}"
        )

        print(
            f"Canonical methods: "
            f"{summary['canonical_methods']}"
        )

        print(
            f"Real methods: "
            f"{summary['real_methods']}"
        )

        print(
            f"Possible methods: "
            f"{summary['possible_methods']}"
        )

        print(
            f"Building blocks: "
            f"{summary['building_blocks']}"
        )

        print(
            f"Education: "
            f"{summary['education']}"
        )

        print(
            f"Webinar: "
            f"{summary['webinar']}"
        )

        print(
            f"Theory: "
            f"{summary['theory']}"
        )

        print(
            f"General: "
            f"{summary['general']}"
        )

        print(
            f"Unknown: "
            f"{summary['unknown']}"
        )

        print(
            f"Duplicate groups: "
            f"{summary['duplicate_groups']}"
        )

        print(
            f"Average confidence: "
            f"{summary['average_confidence']:.1f}"
        )

        print(
            f"Average knowledge support: "
            f"{summary['average_knowledge_support']:.1f}"
        )

        # -------------------------------------------------
        # TOP
        # -------------------------------------------------

        print_top_methods(
            methods
        )

        # -------------------------------------------------
        # DUPLICATES
        # -------------------------------------------------

        print_duplicates(
            duplicates
        )

        # -------------------------------------------------
        # EXCLUDED
        # -------------------------------------------------

        print_excluded(
            analyzed
        )

        # -------------------------------------------------
        # SANITY
        # -------------------------------------------------

        if warnings:
            print_header(
                "⚠️ SANITY WARNINGS"
            )

            for warning in warnings:
                print(
                    f"- {warning}"
                )

        else:
            print()
            print(
                "✅ Canonical cluster sanity "
                "check temiz."
            )

        # -------------------------------------------------
        # DONE
        # -------------------------------------------------

        print()
        print(
            "=" * 76
        )

        print(
            "✅ METHOD REGISTRY CLEANER V2.2 TAMAMLANDI"
        )

        print(
            f"📄 Output: {OUTPUT_FILE}"
        )

        print(
            "ℹ️ DB registry değiştirilmedi."
        )

        print(
            "=" * 76
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
