import os
import sys
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


# ============================================================
# PATH / CONFIG
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(
    PROJECT_ROOT,
    "market_hq.db"
)

MAX_RELATED_SOURCES = 8
MAX_EVIDENCE_PER_GAP = 3

# Artık tek başına kelime eşleşmesi yeterli değil.
MIN_STRONG_SCORE = 75
MIN_MODERATE_SCORE = 55


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table_name: str
) -> bool:

    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name=?
        """,
        (table_name,)
    ).fetchone()

    return row is not None


def ensure_table() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_evidence_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,
            category TEXT,

            specification_id INTEGER,

            original_unknown_items TEXT,
            recovered_items TEXT,
            unresolved_items TEXT,

            evidence_map TEXT,
            related_sources TEXT,

            source_count INTEGER,
            recovered_count INTEGER,
            unresolved_count INTEGER,

            evidence_score REAL,

            audit_status TEXT,

            audit_notes TEXT,

            audited_at TEXT,

            UNIQUE(method_id, canonical_name)
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# HELPERS
# ============================================================

def normalize(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def safe_float(
    value: Any,
    default: float = 0.0
) -> float:

    try:
        return float(value)
    except Exception:
        return default


def parse_json(value: Any) -> Any:

    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    text = normalize(value)

    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        return None


def compact_text(
    text: str,
    max_chars: int = 1600
) -> str:

    text = re.sub(
        r"\s+",
        " ",
        normalize(text)
    )

    if len(text) <= max_chars:
        return text

    return text[:max_chars].rstrip() + "..."


def unique_list(
    values: List[Any]
) -> List[Any]:

    result = []
    seen = set()

    for value in values:

        key = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True
        ) if isinstance(
            value,
            (dict, list)
        ) else str(value)

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def tokenize(text: str) -> List[str]:

    return re.findall(
        r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_-]+",
        normalize(text).lower()
    )


# ============================================================
# LOAD SPECS
# ============================================================

def load_specs() -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "method_technical_specs"
    ):
        conn.close()

        raise RuntimeError(
            "method_technical_specs bulunamadı.\n"
            "Önce method_spec_extractor.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM method_technical_specs
        WHERE spec_status IN (
            'partial',
            'detailed'
        )
        ORDER BY extraction_confidence DESC
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# LOAD KNOWLEDGE
# ============================================================

def load_knowledge_items() -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "knowledge_items"
    ):
        conn.close()

        raise RuntimeError(
            "knowledge_items tablosu bulunamadı."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM knowledge_items
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# KNOWLEDGE NORMALIZATION
# ============================================================

def extract_title(
    row: Dict[str, Any]
) -> str:

    for field in [
        "title",
        "name",
        "source_title",
        "canonical_name"
    ]:

        value = normalize(
            row.get(field)
        )

        if value:
            return value

    return ""


def extract_url(
    row: Dict[str, Any]
) -> str:

    for field in [
        "url",
        "source_url",
        "page_url",
        "youtube_url"
    ]:

        value = normalize(
            row.get(field)
        )

        if value:
            return value

    return ""


def extract_source_type(
    row: Dict[str, Any]
) -> str:

    for field in [
        "source_type",
        "type",
        "content_type"
    ]:

        value = normalize(
            row.get(field)
        )

        if value:
            return value

    return ""


def extract_text(
    row: Dict[str, Any]
) -> str:

    fields = [
        "content",
        "text",
        "source_text",
        "body",
        "description",
        "summary",
        "title",
        "name",
    ]

    chunks = []

    for field in fields:

        value = normalize(
            row.get(field)
        )

        if value:
            chunks.append(value)

    if not chunks:

        for key, value in row.items():

            if value is None:
                continue

            text = normalize(value)

            if len(text) >= 80:
                chunks.append(
                    f"{key}: {text}"
                )

    return "\n".join(chunks)


def build_source_index(
    rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    index = []

    for row in rows:

        text = extract_text(
            row
        )

        if not text:
            continue

        index.append(
            {
                "row": row,
                "title": extract_title(row),
                "url": extract_url(row),
                "source_type": extract_source_type(row),
                "text": text,
            }
        )

    return index


# ============================================================
# METHOD NAME MATCHING
# ============================================================

def normalize_method_name(
    name: str
) -> str:

    name = normalize(
        name
    ).lower()

    name = name.replace(
        "algoritması",
        "algoritma"
    )

    name = name.replace(
        "sistemi",
        "sistem"
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name.strip()


def method_name_variants(
    method_name: str
) -> List[str]:

    original = normalize(
        method_name
    )

    normalized = normalize_method_name(
        original
    )

    variants = [
        original.lower(),
        normalized,
    ]

    # Parantezleri kaldır
    no_paren = re.sub(
        r"\([^)]*\)",
        "",
        normalized
    )

    variants.append(
        re.sub(
            r"\s+",
            " ",
            no_paren
        ).strip()
    )

    # Açıklama sonrasını atabilecek varyantlar
    separators = [
        " - ",
        " – ",
        " : ",
    ]

    for separator in separators:

        if separator in normalized:

            prefix = normalized.split(
                separator,
                1
            )[0].strip()

            if len(prefix) >= 5:
                variants.append(
                    prefix
                )

    # Özel adlar
    known_parts = [
        "sc-zlsma",
        "mat-r",
        "mgb-4s",
        "miraculum",
        "agilis",
        "bluesky",
        "impulsetracker",
        "bum",
        "hsd",
    ]

    for part in known_parts:

        if part in normalized:
            variants.append(
                part
            )

    return unique_list(
        [
            value
            for value in variants
            if len(value) >= 4
        ]
    )


def exact_method_match(
    method_name: str,
    source_title: str,
    source_text: str
) -> Tuple[bool, bool, List[str]]:

    variants = method_name_variants(
        method_name
    )

    title_lower = normalize(
        source_title
    ).lower()

    text_lower = normalize(
        source_text
    ).lower()

    title_match = False
    text_match = False
    matched = []

    for variant in variants:

        if variant in title_lower:

            title_match = True
            matched.append(
                f"title:{variant}"
            )

        if variant in text_lower:

            text_match = True
            matched.append(
                f"text:{variant}"
            )

    return (
        title_match,
        text_match,
        unique_list(matched)
    )


# ============================================================
# GAP TYPE
# ============================================================

def classify_gap(
    gap: str
) -> str:

    text = normalize(
        gap
    ).lower()

    if any(
        term in text
        for term in [
            "parametre",
            "parameter",
            "periyot",
            "period",
            "eşik",
            "threshold",
            "katsayı",
            "çarpan",
        ]
    ):
        return "parameters"

    if any(
        term in text
        for term in [
            "giriş",
            "entry",
            "çıkış",
            "exit",
            "sinyal",
            "signal",
        ]
    ):
        return "signals"

    if any(
        term in text
        for term in [
            "zaman",
            "timeframe",
            "dakika",
            "saat",
            "günlük",
            "haftalık",
            "aylık",
        ]
    ):
        return "timeframe"

    if any(
        term in text
        for term in [
            "formül",
            "formula",
            "hesap",
            "calculation",
            "matematik",
        ]
    ):
        return "formula"

    if any(
        term in text
        for term in [
            "indikatör",
            "indicator",
            "girdi",
            "input",
        ]
    ):
        return "inputs"

    if any(
        term in text
        for term in [
            "kod",
            "python",
            "pine",
            "uygulama",
            "implementation",
        ]
    ):
        return "implementation"

    return "other"


# ============================================================
# GAP TERMS
# ============================================================

def gap_terms(
    gap_type: str
) -> List[str]:

    mapping = {

        "parameters": [
            "parametre",
            "parameter",
            "periyot",
            "period",
            "length",
            "window",
            "lookback",
            "threshold",
            "eşik",
            "katsayı",
            "çarpan",
        ],

        "signals": [
            "sinyal",
            "signal",
            "alım",
            "satış",
            "alış",
            "entry",
            "exit",
            "buy",
            "sell",
            "kesişim",
            "cross",
            "kırılım",
            "breakout",
        ],

        "timeframe": [
            "zaman dilimi",
            "timeframe",
            "günlük",
            "haftalık",
            "aylık",
            "daily",
            "weekly",
            "monthly",
            "dakika",
            "saat",
        ],

        "formula": [
            "formül",
            "formula",
            "hesaplama",
            "calculation",
            "denklem",
            "equation",
            "regresyon",
            "ortalama",
            "standard deviation",
            "standart sapma",
        ],

        "inputs": [
            "indikatör",
            "indicator",
            "input",
            "girdi",
            "fiyat",
            "hacim",
            "volume",
        ],

        "implementation": [
            "python",
            "pine script",
            "pinescript",
            "kod",
            "code",
            "script",
            "scanner",
            "tarama",
        ],

        "other": [],
    }

    return mapping.get(
        gap_type,
        []
    )


# ============================================================
# TECHNICAL EVIDENCE
# ============================================================

def technical_patterns(
    gap_type: str
) -> List[str]:

    mapping = {

        "parameters": [
            r"\b(?:rsi|ema|sma|wma|hma|atr|adx|cci)\s*[=:]?\s*\d+\b",
            r"\b(?:length|period|window|lookback|threshold|factor|multiplier)\s*[=:]?\s*\d+\b",
            r"\b\d+\s*(?:günlük|haftalık|daily|weekly|period)\b",
        ],

        "signals": [
            r"\b(?:buy|sell|long|short|entry|exit)\b",
            r"\b(?:alım|satım|alış|satış|giriş|çıkış|sinyal)\b",
            r"\bcrossover\b",
            r"\bcrossunder\b",
            r"\bkesişim\b",
            r"\bkırılım\b",
        ],

        "timeframe": [
            r"\b\d+\s*(?:dakika|minute|saat|hour|gün|day|hafta|week)\b",
            r"\b(?:günlük|haftalık|aylık|daily|weekly|monthly)\b",
            r"\b(?:multi[- ]timeframe|çoklu zaman)\b",
        ],

        "formula": [
            r"=",
            r"\bformula\b",
            r"\bformül\b",
            r"\bcalculation\b",
            r"\bhesaplama\b",
            r"\bregresyon\b",
            r"\bregression\b",
        ],

        "inputs": [
            r"\brsi\b",
            r"\bmacd\b",
            r"\bema\b",
            r"\bsma\b",
            r"\batr\b",
            r"\badx\b",
            r"\bvolume\b",
            r"\bhacim\b",
            r"\bfiyat\b",
        ],

        "implementation": [
            r"\bpython\b",
            r"\bpine\s*script\b",
            r"\bpinescript\b",
            r"\bkod\b",
            r"\bcode\b",
            r"\bscanner\b",
            r"\btarama\b",
        ],

        "other": [],
    }

    return mapping.get(
        gap_type,
        []
    )


def count_pattern_matches(
    text: str,
    patterns: List[str]
) -> int:

    lower = normalize(
        text
    ).lower()

    count = 0

    for pattern in patterns:

        try:

            if re.search(
                pattern,
                lower,
                flags=re.IGNORECASE
            ):
                count += 1

        except re.error:
            continue

    return count


# ============================================================
# SOURCE SCORING
# ============================================================

def score_source(
    method: Dict[str, Any],
    source: Dict[str, Any],
    gap: str
) -> Dict[str, Any]:

    method_name = normalize(
        method.get(
            "canonical_name"
        )
    )

    title_match, text_match, name_matches = (
        exact_method_match(
            method_name,
            source["title"],
            source["text"]
        )
    )

    gap_type = classify_gap(
        gap
    )

    gap_terms_list = gap_terms(
        gap_type
    )

    source_text_lower = (
        source["text"]
        .lower()
    )

    matched_gap_terms = [
        term
        for term in gap_terms_list
        if term.lower()
        in source_text_lower
    ]

    technical_matches = count_pattern_matches(
        source["text"],
        technical_patterns(
            gap_type
        )
    )

    score = 0

    reasons = []

    # --------------------------------------------------------
    # Method relation is mandatory
    # --------------------------------------------------------

    if title_match:

        score += 65

        reasons.append(
            "exact/variant method name in title"
        )

    elif text_match:

        score += 40

        reasons.append(
            "exact/variant method name in source text"
        )

    else:

        # Source does not clearly identify the method.
        return {
            "score": 0,
            "usable": False,
            "title_match": False,
            "text_match": False,
            "matched_gap_terms": [],
            "technical_matches": 0,
            "reasons": [
                "method-specific relation not established"
            ],
            "snippet": "",
        }

    # --------------------------------------------------------
    # Gap-specific evidence
    # --------------------------------------------------------

    if matched_gap_terms:

        score += min(
            20,
            len(matched_gap_terms) * 5
        )

        reasons.append(
            "gap terms: "
            + ", ".join(
                matched_gap_terms[:8]
            )
        )

    # --------------------------------------------------------
    # Technical evidence
    # --------------------------------------------------------

    if technical_matches >= 1:

        score += min(
            25,
            technical_matches * 5
        )

        reasons.append(
            f"{technical_matches} technical pattern match(es)"
        )

    # --------------------------------------------------------
    # Source title is strong context
    # --------------------------------------------------------

    if title_match and len(
        source["title"]
    ) >= 5:

        score += 10

    # --------------------------------------------------------
    # Source length bonus is tiny
    # --------------------------------------------------------

    if len(source["text"]) >= 3000:

        score += 3

    score = min(
        score,
        100
    )

    usable = (
        title_match
        or (
            text_match
            and technical_matches >= 1
        )
    )

    snippet_terms = (
        gap_terms_list
        + method_name_variants(
            method_name
        )
    )

    snippet = find_snippet(
        source["text"],
        snippet_terms
    )

    return {
        "score": score,
        "usable": usable,
        "title_match": title_match,
        "text_match": text_match,
        "matched_gap_terms": matched_gap_terms,
        "technical_matches": technical_matches,
        "reasons": reasons,
        "matched_name_variants": name_matches,
        "snippet": snippet,
    }


# ============================================================
# SNIPPET
# ============================================================

def find_snippet(
    text: str,
    terms: List[str]
) -> str:

    if not text:
        return ""

    lower = text.lower()

    position = None

    for term in terms:

        term = normalize(
            term
        ).lower()

        if len(term) < 3:
            continue

        index = lower.find(
            term
        )

        if index >= 0:

            position = index
            break

    if position is None:

        return compact_text(
            text
        )

    start = max(
        0,
        position - 500
    )

    end = min(
        len(text),
        position + 1100
    )

    return compact_text(
        text[start:end]
    )


# ============================================================
# AUDIT METHOD
# ============================================================

def audit_method(
    method: Dict[str, Any],
    source_index: List[Dict[str, Any]]
) -> Dict[str, Any]:

    unknown_items = parse_json(
        method.get(
            "unknown_items"
        )
    )

    if not isinstance(
        unknown_items,
        list
    ):
        unknown_items = []

    unknown_items = [
        normalize(item)
        for item in unknown_items
        if normalize(item)
    ]

    related_sources = []

    # --------------------------------------------------------
    # First collect source/method relation
    # --------------------------------------------------------

    method_related_sources = []

    for source in source_index:

        title_match, text_match, name_matches = (
            exact_method_match(
                method.get(
                    "canonical_name",
                    ""
                ),
                source["title"],
                source["text"]
            )
        )

        if not (
            title_match
            or text_match
        ):
            continue

        method_related_sources.append(
            {
                "source": source,
                "title_match": title_match,
                "text_match": text_match,
                "name_matches": name_matches,
            }
        )

    # Remove duplicates by URL + title
    unique_related = []

    seen_sources = set()

    for item in method_related_sources:

        key = (
            item["source"]["url"],
            item["source"]["title"]
        )

        if key in seen_sources:
            continue

        seen_sources.add(
            key
        )

        unique_related.append(
            item
        )

    method_related_sources = (
        unique_related
    )

    # --------------------------------------------------------
    # Related source report
    # --------------------------------------------------------

    related_ranked = []

    for item in method_related_sources:

        source = item[
            "source"
        ]

        base_score = 0

        if item["title_match"]:
            base_score += 75

        elif item["text_match"]:
            base_score += 45

        if len(source["text"]) >= 3000:
            base_score += 5

        related_ranked.append(
            {
                "title": source["title"],
                "url": source["url"],
                "source_type": source["source_type"],
                "score": min(
                    base_score,
                    100
                ),
                "reasons": item[
                    "name_matches"
                ],
                "snippet": find_snippet(
                    source["text"],
                    method_name_variants(
                        method.get(
                            "canonical_name",
                            ""
                        )
                    )
                ),
            }
        )

    related_ranked.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    related_sources = related_ranked[
        :MAX_RELATED_SOURCES
    ]

    # --------------------------------------------------------
    # GAP AUDIT
    # --------------------------------------------------------

    recovered_items = []
    unresolved_items = []
    evidence_map = {}

    for gap in unknown_items:

        candidates = []

        for item in method_related_sources:

            source = item[
                "source"
            ]

            evidence = score_source(
                method,
                source,
                gap
            )

            if not evidence["usable"]:
                continue

            if evidence["score"] < MIN_MODERATE_SCORE:
                continue

            candidates.append(
                {
                    "title": source["title"],
                    "url": source["url"],
                    "source_type": source["source_type"],
                    "score": evidence["score"],
                    "reasons": evidence["reasons"],
                    "snippet": evidence["snippet"],
                    "matched_gap_terms": evidence[
                        "matched_gap_terms"
                    ],
                }
            )

        candidates.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        candidates = candidates[
            :MAX_EVIDENCE_PER_GAP
        ]

        # Strong evidence
        if candidates and candidates[0]["score"] >= MIN_STRONG_SCORE:

            recovered_items.append(
                {
                    "gap": gap,
                    "gap_type": classify_gap(
                        gap
                    ),
                    "recovery_strength": "strong",
                    "evidence": candidates,
                }
            )

            evidence_map[
                gap
            ] = candidates

        # Moderate evidence
        elif candidates and candidates[0]["score"] >= MIN_MODERATE_SCORE:

            recovered_items.append(
                {
                    "gap": gap,
                    "gap_type": classify_gap(
                        gap
                    ),
                    "recovery_strength": "moderate",
                    "evidence": candidates,
                }
            )

            evidence_map[
                gap
            ] = candidates

        # No reliable evidence
        else:

            unresolved_items.append(
                {
                    "gap": gap,
                    "gap_type": classify_gap(
                        gap
                    ),
                    "reason": (
                        "Mevcut public kaynaklarda metodun "
                        "bu eksik bilgisini doğrudan destekleyen "
                        "yeterli metod-spesifik kanıt bulunamadı."
                    ),
                }
            )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    total_gaps = len(
        unknown_items
    )

    strong_count = sum(
        1
        for item in recovered_items
        if item[
            "recovery_strength"
        ] == "strong"
    )

    moderate_count = sum(
        1
        for item in recovered_items
        if item[
            "recovery_strength"
        ] == "moderate"
    )

    if total_gaps == 0:

        evidence_score = 100.0

    else:

        evidence_score = (
            (
                strong_count * 1.0
                + moderate_count * 0.45
            )
            / total_gaps
            * 100
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if total_gaps == 0:

        audit_status = "complete"

    elif strong_count == total_gaps:

        audit_status = "strong_recovery"

    elif (
        strong_count > 0
        or moderate_count > 0
    ):

        audit_status = "partial_recovery"

    else:

        audit_status = "no_recovery"

    notes = []

    notes.append(
        f"{len(method_related_sources)} "
        "method-related public source found."
    )

    notes.append(
        "Evidence is accepted only when the source is "
        "method-specific; generic keyword matches are ignored."
    )

    if strong_count:

        notes.append(
            f"{strong_count} gap güçlü metod-spesifik kanıt aldı."
        )

    if moderate_count:

        notes.append(
            f"{moderate_count} gap orta güçte kanıt aldı."
        )

    if unresolved_items:

        notes.append(
            f"{len(unresolved_items)} gap hâlâ çözülmedi."
        )

    return {
        "method_id": method.get(
            "method_id"
        ),
        "canonical_name": normalize(
            method.get(
                "canonical_name"
            )
        ),
        "category": normalize(
            method.get(
                "category"
            )
        ),

        "specification_id": method.get(
            "id"
        ),

        "original_unknown_items": unknown_items,

        "recovered_items": recovered_items,

        "unresolved_items": unresolved_items,

        "evidence_map": evidence_map,

        "related_sources": related_sources,

        "source_count": len(
            method_related_sources
        ),

        "recovered_count": (
            strong_count
            + moderate_count
        ),

        "unresolved_count": len(
            unresolved_items
        ),

        "evidence_score": evidence_score,

        "audit_status": audit_status,

        "audit_notes": notes,
    }


# ============================================================
# SAVE
# ============================================================

def save_audit(
    result: Dict[str, Any]
) -> None:

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO method_evidence_audit (
            method_id,
            canonical_name,
            category,

            specification_id,

            original_unknown_items,
            recovered_items,
            unresolved_items,

            evidence_map,
            related_sources,

            source_count,
            recovered_count,
            unresolved_count,

            evidence_score,

            audit_status,

            audit_notes,

            audited_at
        )
        VALUES (
            ?, ?, ?,
            ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?,
            ?,
            ?,
            ?
        )

        ON CONFLICT(
            method_id,
            canonical_name
        )
        DO UPDATE SET

            category = excluded.category,

            specification_id =
                excluded.specification_id,

            original_unknown_items =
                excluded.original_unknown_items,

            recovered_items =
                excluded.recovered_items,

            unresolved_items =
                excluded.unresolved_items,

            evidence_map =
                excluded.evidence_map,

            related_sources =
                excluded.related_sources,

            source_count =
                excluded.source_count,

            recovered_count =
                excluded.recovered_count,

            unresolved_count =
                excluded.unresolved_count,

            evidence_score =
                excluded.evidence_score,

            audit_status =
                excluded.audit_status,

            audit_notes =
                excluded.audit_notes,

            audited_at =
                excluded.audited_at
        """,
        (
            result["method_id"],
            result["canonical_name"],
            result["category"],

            result["specification_id"],

            json.dumps(
                result["original_unknown_items"],
                ensure_ascii=False
            ),

            json.dumps(
                result["recovered_items"],
                ensure_ascii=False
            ),

            json.dumps(
                result["unresolved_items"],
                ensure_ascii=False
            ),

            json.dumps(
                result["evidence_map"],
                ensure_ascii=False
            ),

            json.dumps(
                result["related_sources"],
                ensure_ascii=False
            ),

            result["source_count"],
            result["recovered_count"],
            result["unresolved_count"],

            result["evidence_score"],

            result["audit_status"],

            json.dumps(
                result["audit_notes"],
                ensure_ascii=False
            ),

            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# REPORT
# ============================================================

def print_method_report(
    result: Dict[str, Any]
) -> None:

    print()
    print(
        f"• {result['canonical_name']}"
    )

    print(
        f"  Status: "
        f"{result['audit_status']}"
    )

    print(
        f"  Evidence score: "
        f"{result['evidence_score']:.1f}/100"
    )

    print(
        f"  Method-related sources: "
        f"{result['source_count']}"
    )

    print(
        f"  Recovered: "
        f"{result['recovered_count']}"
    )

    print(
        f"  Unresolved: "
        f"{result['unresolved_count']}"
    )

    if result["recovered_items"]:

        print(
            "  ✅ Kanıt bulunan eksikler:"
        )

        for item in result[
            "recovered_items"
        ]:

            print(
                f"    - {item['gap']} "
                f"[{item['recovery_strength']}]"
            )

            if item["evidence"]:

                top = item[
                    "evidence"
                ][0]

                print(
                    f"      Kaynak: "
                    f"{top['title'] or '(başlıksız)'}"
                )

                print(
                    f"      Score: "
                    f"{top['score']}"
                )

    if result["unresolved_items"]:

        print(
            "  ❌ Çözülmemiş eksikler:"
        )

        for item in result[
            "unresolved_items"
        ]:

            print(
                f"    - {item['gap']}"
            )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    counts = {
        "complete": 0,
        "strong_recovery": 0,
        "partial_recovery": 0,
        "no_recovery": 0,
    }

    scores = []

    recovered = 0
    unresolved = 0

    for result in results:

        status = result[
            "audit_status"
        ]

        if status in counts:

            counts[
                status
            ] += 1

        scores.append(
            result[
                "evidence_score"
            ]
        )

        recovered += result[
            "recovered_count"
        ]

        unresolved += result[
            "unresolved_count"
        ]

    print()
    print("=========================================")
    print("🔎 METHOD EVIDENCE AUDITOR V2 SONUCU")
    print("=========================================")

    print(
        f"Audited method: "
        f"{len(results)}"
    )

    print(
        f"Recovered gap: "
        f"{recovered}"
    )

    print(
        f"Unresolved gap: "
        f"{unresolved}"
    )

    if scores:

        print(
            f"Ortalama evidence score: "
            f"{sum(scores) / len(scores):.1f}/100"
        )

    print()
    print("AUDIT STATUS")
    print("-----------------------------------------")

    print(
        f"Complete:          "
        f"{counts['complete']}"
    )

    print(
        f"Strong recovery:   "
        f"{counts['strong_recovery']}"
    )

    print(
        f"Partial recovery:  "
        f"{counts['partial_recovery']}"
    )

    print(
        f"No recovery:       "
        f"{counts['no_recovery']}"
    )

    print()
    print(
        "========================================="
    )


# ============================================================
# PRIORITY
# ============================================================

def print_priority_order(
    results: List[Dict[str, Any]]
) -> None:

    ranked = sorted(
        results,
        key=lambda result: (
            -result["evidence_score"],
            result["unresolved_count"],
            result["canonical_name"]
        )
    )

    print()
    print("🎯 ARAŞTIRMA ÖNCELİĞİ")
    print("-----------------------------------------")

    for index, result in enumerate(
        ranked,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['canonical_name']} "
            f"| evidence="
            f"{result['evidence_score']:.1f} "
            f"| unresolved="
            f"{result['unresolved_count']} "
            f"| {result['audit_status']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("🔎 FIN[SYS] METHOD EVIDENCE AUDITOR V2")
    print("=========================================")

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_table()

    methods = load_specs()

    print(
        f"Technical spec: "
        f"{len(methods)}"
    )

    if not methods:

        print(
            "❌ Technical spec bulunamadı."
        )

        print(
            "Önce:"
        )

        print(
            "python agents/method_spec_extractor.py"
        )

        return

    knowledge_rows = (
        load_knowledge_items()
    )

    print(
        f"Knowledge item: "
        f"{len(knowledge_rows)}"
    )

    source_index = build_source_index(
        knowledge_rows
    )

    print(
        f"Searchable source: "
        f"{len(source_index)}"
    )

    print()

    results = []

    for method in methods:

        result = audit_method(
            method,
            source_index
        )

        save_audit(
            result
        )

        results.append(
            result
        )

        print_method_report(
            result
        )

    print_summary(
        results
    )

    print_priority_order(
        results
    )

    print()
    print(
        "✅ Method Evidence Auditor V2 tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Gerçekten kaynakla desteklenen teknik "
        "bilgiler ayrıştırılacak; desteklenmeyen "
        "kısımlar için yeni public kaynak araştırılacak."
    )


if __name__ == "__main__":
    main()