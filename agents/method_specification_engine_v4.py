from __future__ import annotations

import json
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# ============================================================================
# MARKET HQ
# FIN[SYS] METHOD SPECIFICATION ENGINE V3
#
# Amaç:
#   method_registry + knowledge_items verisini birlikte okuyup,
#   kanıtı uydurmadan yöntemleri yapılandırılmış specification'a dönüştürmek.
#
# Tasarım:
#   - Registry Cleaner'a bağımlı değildir.
#   - method_registry şemasını runtime'da keşfeder.
#   - knowledge_items içindeki gerçek metni esas alır.
#   - Eksik bilgiyi "unknown / missing" olarak bırakır.
#   - Fuzzy matching ile farklı yöntemleri birleştirmez.
#   - DB'ye sadece method_specifications tablosunu ekler/günceller.
#   - Eski method_registry ve knowledge_items kayıtlarına dokunmaz.
# ============================================================================


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "market_hq.db"

OUTPUT_PATH = BASE_DIR / "method_specifications_v4.json"

ENGINE_NAME = "FIN_SYS_METHOD_SPECIFICATION_ENGINE_V4"
ENGINE_VERSION = "4.0"

# Specification için zorunlu çekirdek alanlar.
REQUIRED_FIELDS = (
    "method_name",
    "category",
    "objective",
    "inputs",
    "parameters",
    "signal_rules",
    "entry_rules",
    "exit_rules",
    "filters",
    "timeframe",
    "market_scope",
    "risk_rules",
)

# Gerçek anlamda Python'a taşınabilirlik açısından kritik alanlar.
COMPUTABLE_FIELDS = (
    "inputs",
    "parameters",
    "signal_rules",
    "entry_rules",
    "exit_rules",
    "timeframe",
)

# ============================================================================
# DATAMODEL
# ============================================================================


@dataclass
class MethodSpec:
    method_id: int | None = None
    registry_id: int | None = None
    source_id: int | None = None
    method_name: str = ""
    canonical_key: str = ""
    category: str = "other"
    objective: str | None = None

    inputs: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    signal_rules: list[str] = field(default_factory=list)
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)

    timeframe: str | None = None
    market_scope: list[str] = field(default_factory=list)
    risk_rules: list[str] = field(default_factory=list)

    linked_knowledge_ids: list[int] = field(default_factory=list)
    linked_source_ids: list[int] = field(default_factory=list)

    evidence_state: str = "unknown"
    evidence_notes: list[str] = field(default_factory=list)

    extraction_method: str = ENGINE_NAME
    confidence: float = 0.0
    completeness: float = 0.0
    computability: str = "reference_only"

    missing_fields: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)

    source_text: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_db_payload(self) -> dict[str, Any]:
        payload = asdict(self)

        json_fields = (
            "inputs",
            "parameters",
            "signal_rules",
            "entry_rules",
            "exit_rules",
            "filters",
            "market_scope",
            "risk_rules",
            "linked_knowledge_ids",
            "linked_source_ids",
            "evidence_notes",
            "missing_fields",
            "ambiguities",
        )

        for field_name in json_fields:
            payload[field_name] = json.dumps(
                payload[field_name],
                ensure_ascii=False,
            )

        return payload


# ============================================================================
# TEXT HELPERS
# ============================================================================


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def norm(value: Any) -> str:
    text = clean_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    return text.lower()


def safe_json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default

    if isinstance(value, (dict, list, int, float, bool)):
        return value

    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def as_list(value: Any) -> list[Any]:
    parsed = safe_json_loads(value, value)

    if isinstance(parsed, list):
        return parsed

    if parsed in (None, ""):
        return []

    return [parsed]


def as_string_list(value: Any) -> list[str]:
    result: list[str] = []

    for item in as_list(value):
        text = clean_text(item)
        if text and text not in result:
            result.append(text)

    return result


def split_sentences(text: str) -> list[str]:
    text = str(text or "")
    chunks = re.split(
        r"(?<=[.!?])\s+|\n+|(?<=[;:])\s+",
        text,
    )

    result = []
    for chunk in chunks:
        item = clean_text(chunk)
        if item and item not in result:
            result.append(item)

    return result


def contains_any(text: str, words: Iterable[str]) -> bool:
    low = norm(text)
    return any(norm(word) in low for word in words)


def extract_lines(
    text: str,
    words: Iterable[str],
    limit: int = 20,
) -> list[str]:
    result: list[str] = []

    for sentence in split_sentences(text):
        if contains_any(sentence, words):
            if sentence not in result:
                result.append(sentence)

        if len(result) >= limit:
            break

    return result


def first_matching_sentence(
    text: str,
    words: Iterable[str],
) -> str | None:
    rows = extract_lines(text, words, limit=1)
    return rows[0] if rows else None


# ============================================================================
# DOMAIN VOCABULARY
# ============================================================================


INDICATOR_PATTERNS: dict[str, tuple[str, ...]] = {
    "EMA": (r"\bema\b", r"exponential moving average"),
    "SMA": (r"\bsma\b", r"simple moving average"),
    "WMA": (r"\bwma\b", r"weighted moving average"),
    "RSI": (r"\brsi\b", r"relative strength index"),
    "MACD": (r"\bmacd\b",),
    "ATR": (r"\batr\b", r"average true range"),
    "ADX": (r"\badx\b",),
    "STOCHASTIC": (r"\bstochastic\b", r"\bstoch\b"),
    "BOLLINGER": (r"\bbollinger\b", r"bollinger bands?"),
    "VWAP": (r"\bvwap\b",),
    "ROC": (r"\broc\b", r"rate of change"),
    "ZLSMA": (r"\bzlsma\b",),
    "FRAMA": (r"\bframa\b",),
    "OBV": (r"\bobv\b", r"on balance volume"),
    "MFI": (r"\bmfi\b", r"money flow index"),
    "CCI": (r"\bcci\b",),
    "ICHIMOKU": (r"\bichimoku\b",),
    "SUPPORT": (r"\bsupport\b", r"destek"),
    "RESISTANCE": (r"\bresistance\b", r"direnç"),
    "MOMENTUM": (r"\bmomentum\b",),
    "VOLATILITY": (r"\bvolatility\b", r"volatilite"),
    "REGRESSION": (
        r"\blinear regression\b",
        r"\blinreg\b",
        r"lineer regresyon",
        r"regresyon",
    ),
    "VOLUME": (r"\bvolume\b", r"hacim"),
    "PRICE": (
        r"\bopen\b",
        r"\bhigh\b",
        r"\blow\b",
        r"\bclose\b",
        r"fiyat",
    ),
}


ENTRY_WORDS = (
    "entry",
    "giriş",
    "giris",
    "buy",
    "alım",
    "alim",
    "long",
    "pozisyon aç",
    "pozisyon ac",
    "signal",
    "sinyal",
)


EXIT_WORDS = (
    "exit",
    "çıkış",
    "cikis",
    "sell",
    "satış",
    "satis",
    "short",
    "stop",
    "take profit",
    "hedef",
    "kapat",
    "pozisyon kapat",
)


SIGNAL_WORDS = (
    "signal",
    "sinyal",
    "condition",
    "koşul",
    "kosul",
    "when",
    "if",
    "above",
    "below",
    "cross",
    "crosses",
    "üzerinde",
    "uzerinde",
    "altında",
    "altinda",
    "kesişim",
    "kesisim",
    "tetik",
)


FILTER_WORDS = (
    "filter",
    "filtre",
    "screen",
    "scanner",
    "scan",
    "tarama",
    "sadece",
    "only when",
    "exclude",
    "hariç",
    "haric",
)


RISK_WORDS = (
    "stop loss",
    "stop-loss",
    "risk",
    "position size",
    "pozisyon boyutu",
    "drawdown",
    "maksimum zarar",
    "max loss",
    "risk yönet",
    "risk yonet",
    "volatility",
    "volatilite",
)


TIMEFRAME_PATTERNS = (
    r"\b\d+\s*(?:m|min|minute|h|hour|saat|d|day|gün|gun|w|week|hafta|M|month|ay)\b",
    r"\bdaily\b",
    r"\bweekly\b",
    r"\bmonthly\b",
    r"\bintraday\b",
    r"\bgünlük\b",
    r"\bgunluk\b",
    r"\bhaftalık\b",
    r"\bhaftalik\b",
)


MARKET_PATTERNS = {
    "BIST": (
        r"\bbist\b",
        r"\bxu100\b",
        r"\btürkiye\b",
        r"\bturkiye\b",
        r"\bturkey\b",
        r"\bhisse\b",
    ),
    "US": (
        r"\bnasdaq\b",
        r"\bs&p\b",
        r"\bsp500\b",
        r"\bnyse\b",
        r"\busa\b",
        r"\bamerika\b",
    ),
    "CRYPTO": (
        r"\bcrypto\b",
        r"\bkripto\b",
        r"\bbitcoin\b",
        r"\bbtc\b",
        r"\beth\b",
    ),
    "FOREX": (
        r"\bforex\b",
        r"\bfx\b",
        r"\bcurrency\b",
        r"\bdöviz\b",
        r"\bdoviz\b",
    ),
}


CATEGORY_HINTS = {
    "algorithm": (
        "algoritma",
        "algorithm",
    ),
    "indicator": (
        "indicator",
        "indikatör",
        "indikator",
    ),
    "trend_method": (
        "trend",
    ),
    "momentum_method": (
        "momentum",
    ),
    "volume_method": (
        "volume",
        "hacim",
    ),
    "chart_method": (
        "chart",
        "grafik",
        "formasyon",
        "pattern",
    ),
    "scan_method": (
        "scan",
        "tarama",
        "screener",
        "scanner",
    ),
    "filter": (
        "filter",
        "filtre",
    ),
    "system": (
        "system",
        "sistem",
    ),
    "python_method": (
        "python",
    ),
    "tradingview_method": (
        "tradingview",
        "pine script",
        "pine",
    ),
}


NON_METHOD_TERMS = (
    "eğitim",
    "egitim",
    "kurs",
    "ders",
    "webinar",
    "zoom",
    "sohbet",
    "chat",
    "calculus",
    "matematik",
    "fizik",
    "kimya",
)


# ============================================================================
# DATABASE
# ============================================================================


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> list[str]:
    if not table_exists(conn, table_name):
        return []

    return [
        str(row["name"])
        for row in conn.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    ]


def choose_column(
    columns: Iterable[str],
    candidates: Iterable[str],
) -> str | None:
    column_set = {str(x) for x in columns}

    for candidate in candidates:
        if candidate in column_set:
            return candidate

    lower_map = {
        str(x).lower(): str(x)
        for x in columns
    }

    for candidate in candidates:
        matched = lower_map.get(candidate.lower())
        if matched:
            return matched

    return None


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    V1/V2 döneminden kalmış method_specifications tablosunu güvenli biçimde
    V3 şemasına taşır.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_specifications (
            method_id INTEGER PRIMARY KEY,
            registry_id INTEGER,
            source_id INTEGER,
            method_name TEXT NOT NULL,
            canonical_key TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'other',
            objective TEXT,
            inputs_json TEXT NOT NULL DEFAULT '[]',
            parameters_json TEXT NOT NULL DEFAULT '{}',
            signal_rules_json TEXT NOT NULL DEFAULT '[]',
            entry_rules_json TEXT NOT NULL DEFAULT '[]',
            exit_rules_json TEXT NOT NULL DEFAULT '[]',
            filters_json TEXT NOT NULL DEFAULT '[]',
            timeframe TEXT,
            market_scope_json TEXT NOT NULL DEFAULT '[]',
            risk_rules_json TEXT NOT NULL DEFAULT '[]',
            linked_knowledge_ids_json TEXT NOT NULL DEFAULT '[]',
            linked_source_ids_json TEXT NOT NULL DEFAULT '[]',
            evidence_state TEXT NOT NULL DEFAULT 'unknown',
            evidence_notes_json TEXT NOT NULL DEFAULT '[]',
            source_text TEXT NOT NULL DEFAULT '',
            extraction_method TEXT NOT NULL DEFAULT 'unknown',
            confidence REAL NOT NULL DEFAULT 0,
            completeness REAL NOT NULL DEFAULT 0,
            computability TEXT NOT NULL DEFAULT 'reference_only',
            missing_fields_json TEXT NOT NULL DEFAULT '[]',
            ambiguities_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )

    existing_columns = set(
        table_columns(
            conn,
            "method_specifications",
        )
    )

    required_v3_columns = {
        "method_id",
        "method_name",
        "category",
        "computability",
        "confidence",
        "completeness",
    }

    missing_base = required_v3_columns - existing_columns

    if missing_base:
        raise RuntimeError(
            "Mevcut method_specifications tablosu beklenmeyen bir "
            "şemaya sahip. Eksik temel kolonlar: "
            + ", ".join(sorted(missing_base))
            + ". Eski tabloyu silmek yerine yedek alıp "
              "engine migration ile yeniden çalıştırılmalıdır."
        )

    migrations = {
        "registry_id": "INTEGER",
        "canonical_key": "TEXT NOT NULL DEFAULT ''",
        "linked_knowledge_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "linked_source_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "evidence_notes_json": "TEXT NOT NULL DEFAULT '[]'",
    }

    for column_name, column_definition in migrations.items():
        if column_name not in existing_columns:
            sql = (
                'ALTER TABLE method_specifications '
                f'ADD COLUMN "{column_name}" {column_definition}'
            )
            conn.execute(sql)

    conn.execute(
        """
        UPDATE method_specifications
        SET canonical_key = method_name
        WHERE canonical_key IS NULL
           OR TRIM(canonical_key) = ''
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_method_spec_v3_computability
        ON method_specifications(computability)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_method_spec_v3_confidence
        ON method_specifications(confidence DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_method_spec_v3_completeness
        ON method_specifications(completeness DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_method_spec_v3_canonical
        ON method_specifications(canonical_key)
        """
    )

    conn.commit()


# ============================================================================
# REGISTRY DISCOVERY
# ============================================================================


def discover_registry_layout(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    columns = table_columns(
        conn,
        "method_registry",
    )

    if not columns:
        raise RuntimeError(
            "method_registry tablosu bulunamadı."
        )

    return {
        "columns": columns,
        "id": choose_column(
            columns,
            ("id", "method_id", "registry_id"),
        ),
        "name": choose_column(
            columns,
            (
                "method_name",
                "canonical_name",
                "name",
                "title",
            ),
        ),
        "canonical_name": choose_column(
            columns,
            (
                "canonical_name",
                "method_name",
                "name",
                "title",
            ),
        ),
        "category": choose_column(
            columns,
            (
                "category",
                "method_type",
                "type",
            ),
        ),
        "confidence": choose_column(
            columns,
            (
                "confidence",
                "registry_confidence",
                "score",
            ),
        ),
    }


def discover_knowledge_layout(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    columns = table_columns(
        conn,
        "knowledge_items",
    )

    if not columns:
        raise RuntimeError(
            "knowledge_items tablosu bulunamadı."
        )

    required = (
        "id",
        "source_id",
        "item_type",
        "title",
        "content",
        "summary",
        "method",
        "tags_json",
    )

    missing = [
        column
        for column in required
        if column not in columns
    ]

    if missing:
        raise RuntimeError(
            "knowledge_items eksik kolonlar: "
            + ", ".join(missing)
        )

    return {
        "columns": columns,
        "id": "id",
        "source_id": "source_id",
        "item_type": "item_type",
        "title": "title",
        "content": "content",
        "summary": "summary",
        "method": "method",
        "tags_json": "tags_json",
        "confidence": choose_column(
            columns,
            ("confidence",),
        ),
        "metadata_json": choose_column(
            columns,
            ("metadata_json",),
        ),
    }


def load_registry_rows(
    conn: sqlite3.Connection,
    layout: dict[str, Any],
) -> list[sqlite3.Row]:
    id_col = layout["id"]
    name_col = layout["name"]
    canonical_col = layout["canonical_name"]
    category_col = layout["category"]
    confidence_col = layout["confidence"]

    select_parts = []

    if id_col:
        select_parts.append(
            f'"{id_col}" AS registry_id'
        )
    else:
        select_parts.append(
            "rowid AS registry_id"
        )

    if name_col:
        select_parts.append(
            f'"{name_col}" AS registry_name'
        )
    else:
        select_parts.append(
            "NULL AS registry_name"
        )

    if canonical_col:
        select_parts.append(
            f'"{canonical_col}" AS canonical_name'
        )
    else:
        select_parts.append(
            "NULL AS canonical_name"
        )

    if category_col:
        select_parts.append(
            f'"{category_col}" AS registry_category'
        )
    else:
        select_parts.append(
            "NULL AS registry_category"
        )

    if confidence_col:
        select_parts.append(
            f'"{confidence_col}" AS registry_confidence'
        )
    else:
        select_parts.append(
            "NULL AS registry_confidence"
        )

    query = (
        "SELECT "
        + ", ".join(select_parts)
        + ' FROM "method_registry"'
    )

    return conn.execute(query).fetchall()


def load_knowledge_rows(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    columns = discover_knowledge_layout(conn)

    confidence_sql = (
        f'"{columns["confidence"]}" AS item_confidence'
        if columns["confidence"]
        else "NULL AS item_confidence"
    )

    metadata_sql = (
        f'"{columns["metadata_json"]}" AS metadata_json'
        if columns["metadata_json"]
        else "NULL AS metadata_json"
    )

    query = f"""
        SELECT
            "{columns["id"]}" AS knowledge_id,
            "{columns["source_id"]}" AS source_id,
            "{columns["item_type"]}" AS item_type,
            "{columns["title"]}" AS title,
            "{columns["content"]}" AS content,
            "{columns["summary"]}" AS summary,
            "{columns["method"]}" AS method,
            "{columns["tags_json"]}" AS tags_json,
            {confidence_sql},
            {metadata_sql}
        FROM "knowledge_items"
        ORDER BY "{columns["id"]}" ASC
    """

    return conn.execute(query).fetchall()


# ============================================================================
# METHOD IDENTIFICATION
# ============================================================================


def canonical_key(value: Any) -> str:
    text = norm(value)

    text = re.sub(
        r"^fin\[sys\]\s*[-:|]?\s*",
        "",
        text,
    )

    # Sadece sunum/format eklerini temizle.
    # Farklı yöntem isimlerini birleştiren agresif fuzzy kurallar YOK.
    text = re.sub(
        r"\b(python|pine script|tradingview)\s+(sinyal|tarama|kodu|code)\b",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = re.sub(
        r"[^\w\s\-+/.]",
        "",
        text,
    )

    return text.strip()


def is_non_method_text(
    title: str,
    method: str,
    item_type: str,
) -> bool:
    text = " ".join(
        [
            norm(title),
            norm(method),
            norm(item_type),
        ]
    )

    # Sadece başlıkta eğitim terimi bulunması yeterli değil;
    # item_type de education/webinar/theory ise güçlü biçimde dışla.
    educational_types = {
        "education",
        "webinar",
        "theory",
    }

    if norm(item_type) in educational_types:
        return True

    # Başlık açıkça eğitim materyali gibi görünüyorsa dışla.
    title_norm = norm(title)

    for term in NON_METHOD_TERMS:
        if re.search(
            rf"\b{re.escape(norm(term))}\b",
            title_norm,
        ):
            return True

    return False


def method_strength(
    title: str,
    method: str,
    content: str,
    item_type: str,
) -> float:
    text = " ".join(
        [
            norm(title),
            norm(method),
            norm(content),
            norm(item_type),
        ]
    )

    score = 0.0

    if norm(method):
        score += 25.0

    if any(
        term in norm(title)
        for term in (
            "algoritma",
            "sistem",
            "strategy",
            "strateji",
            "metod",
            "method",
            "scanner",
            "scanner",
            "tarama",
        )
    ):
        score += 20.0

    signal_terms = (
        "sinyal",
        "entry",
        "exit",
        "alım",
        "alim",
        "satış",
        "satis",
        "long",
        "short",
        "trend",
        "momentum",
        "volatilite",
        "hacim",
        "filter",
        "filtre",
    )

    score += min(
        25.0,
        sum(
            5.0
            for term in signal_terms
            if term in text
        ),
    )

    if item_type in {
        "algorithm",
        "chart_method",
        "filter",
        "indicator",
        "momentum_method",
        "python_method",
        "scan_method",
        "system",
        "tradingview_method",
        "trend_method",
        "volume_method",
    }:
        score += 20.0

    if norm(content):
        score += 10.0

    return min(
        100.0,
        score,
    )


# ============================================================================
# SPEC EXTRACTION
# ============================================================================


def extract_indicators(text: str) -> list[str]:
    low = norm(text)
    found: list[str] = []

    for indicator, patterns in INDICATOR_PATTERNS.items():
        for pattern in patterns:
            if re.search(
                pattern,
                low,
                flags=re.IGNORECASE,
            ):
                found.append(indicator)
                break

    return sorted(set(found))


def extract_parameters(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}

    patterns = (
        # RSI length 14 / period=20 / window: 50
        re.compile(
            r"\b([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-z0-9ÇĞİÖŞÜçğıöşü _-]{1,40})"
            r"\s*(?:=|:|is|are)\s*"
            r"(\d+(?:\.\d+)?)\b",
            flags=re.IGNORECASE,
        ),
        # 20-period EMA / 14 period RSI
        re.compile(
            r"\b(\d+)\s*[- ]?(?:period|periyot|length|bar|bars)\b"
            r"(?:\s+([A-Za-zÇĞİÖŞÜçğıöşüA-Za-z0-9_-]{2,30}))?",
            flags=re.IGNORECASE,
        ),
    )

    for pattern in patterns:
        for match in pattern.finditer(text):
            groups = match.groups()

            if len(groups) == 2 and groups[1] is not None:
                first = clean_text(groups[0])
                second = clean_text(groups[1])

                # Pattern 2: first=number, second=name
                key = norm(second).replace(" ", "_")
                raw_value = first
            elif len(groups) == 2:
                key = norm(groups[0]).replace(" ", "_")
                raw_value = groups[1]
            else:
                continue

            if not key or not raw_value:
                continue

            try:
                number = float(raw_value)
                if number.is_integer():
                    number = int(number)
            except (TypeError, ValueError):
                continue

            params.setdefault(
                key,
                number,
            )

    # Yaygın çıplak periyotlar; sadece sayı görmek parametre kabul edilmez.
    explicit_periods = re.findall(
        r"\b(\d+)\s*(?:period|periyot|bar|bars|günlük|gunluk)\b",
        norm(text),
        flags=re.IGNORECASE,
    )

    for index, value in enumerate(explicit_periods, start=1):
        key = (
            "period"
            if index == 1
            else f"period_{index}"
        )

        try:
            params.setdefault(
                key,
                int(value),
            )
        except ValueError:
            pass

    return params


def extract_timeframe(
    text: str,
) -> str | None:
    for pattern in TIMEFRAME_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return clean_text(
                match.group(0)
            )

    return None


def extract_market_scope(
    text: str,
) -> list[str]:
    low = norm(text)
    result: list[str] = []

    for market, patterns in MARKET_PATTERNS.items():
        if any(
            re.search(
                pattern,
                low,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            result.append(market)

    return result


def infer_category(
    title: str,
    method: str,
    tags: list[str],
    registry_category: str | None,
) -> str:
    # Registry kategorisi varsa, önce onu koru.
    if registry_category:
        category = norm(registry_category).replace(" ", "_")

        allowed = {
            "algorithm",
            "chart_method",
            "education",
            "filter",
            "indicator",
            "momentum_method",
            "other",
            "python_method",
            "scan_method",
            "system",
            "tradingview_method",
            "trend_method",
            "volume_method",
        }

        if category in allowed:
            return category

    blob = " ".join(
        [
            title,
            method,
            *tags,
        ]
    )

    low = norm(blob)

    # Daha spesifik kategoriler önce.
    ordered = (
        "python_method",
        "tradingview_method",
        "scan_method",
        "filter",
        "algorithm",
        "trend_method",
        "momentum_method",
        "volume_method",
        "chart_method",
        "indicator",
        "system",
    )

    for category in ordered:
        hints = CATEGORY_HINTS.get(
            category,
            (),
        )

        if any(
            norm(hint) in low
            for hint in hints
        ):
            return category

    return "other"


def infer_objective(
    title: str,
    method: str,
    summary: str,
) -> str | None:
    # Summary varsa doğrudan kaynak bilgisi olarak kullan.
    if summary:
        return summary[:1200]

    # Summary yoksa başlıktan iddia üretme.
    # Yalnızca isim mevcut olduğunu belirt.
    if title:
        return (
            f"Kaynakta yöntem adı: {title}"
        )

    if method:
        return (
            f"Kaynakta yöntem adı: {method}"
        )

    return None


def build_source_text(
    title: str,
    method: str,
    summary: str,
    content: str,
) -> str:
    pieces = [
        clean_text(title),
        clean_text(method),
        clean_text(summary),
        clean_text(content),
    ]

    return "\n".join(
        piece
        for piece in pieces
        if piece
    )


def extract_evidence_state(
    source_id: int | None,
    linked_knowledge_ids: list[int],
    content_length: int,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    if source_id is not None:
        notes.append(
            "Knowledge item bir knowledge_source kaydına bağlı."
        )
        base = "linked_source"
    else:
        base = "knowledge_only"

    if linked_knowledge_ids:
        notes.append(
            f"{len(linked_knowledge_ids)} knowledge item kaydıyla destekleniyor."
        )

    if content_length >= 1000:
        notes.append(
            "Kaynak metni extraction için yeterli uzunlukta."
        )
    elif content_length > 0:
        notes.append(
            "Kaynak metni kısa; specification eksik kalabilir."
        )
    else:
        notes.append(
            "Kaynak metni bulunamadı."
        )

    return base, notes


# ============================================================================
# COMPUTABILITY / QUALITY
# ============================================================================


def finalize_spec(
    spec: MethodSpec,
) -> None:
    missing: list[str] = []

    if not spec.method_name:
        missing.append("method_name")

    if not spec.category:
        missing.append("category")

    if not spec.objective:
        missing.append("objective")

    if not spec.inputs:
        missing.append("inputs")

    if not spec.parameters:
        missing.append("parameters")

    if not spec.signal_rules:
        missing.append("signal_rules")

    if not spec.entry_rules:
        missing.append("entry_rules")

    if not spec.exit_rules:
        missing.append("exit_rules")

    if not spec.filters:
        missing.append("filters")

    if not spec.timeframe:
        missing.append("timeframe")

    if not spec.market_scope:
        missing.append("market_scope")

    if not spec.risk_rules:
        missing.append("risk_rules")

    spec.missing_fields = missing

    known = sum(
        bool(getattr(spec, field_name))
        for field_name in REQUIRED_FIELDS
    )

    spec.completeness = round(
        known / len(REQUIRED_FIELDS) * 100.0,
        1,
    )

    computable_known = sum(
        bool(getattr(spec, field_name))
        for field_name in COMPUTABLE_FIELDS
    )

    # Aşırı iyimser "computable" üretmiyoruz.
    # Entry/exit/signal/timeframe kesin yoksa gerçek computable sayılmaz.
    critical = (
        bool(spec.signal_rules)
        and bool(spec.entry_rules)
        and bool(spec.exit_rules)
        and bool(spec.timeframe)
    )

    parameter_quality = bool(
        spec.parameters
        or not re.search(
            r"\b(?:parameter|parametre|length|period|periyot|window)\b",
            spec.source_text,
            flags=re.IGNORECASE,
        )
    )

    if (
        computable_known == len(COMPUTABLE_FIELDS)
        and critical
        and parameter_quality
        and spec.completeness >= 70.0
    ):
        spec.computability = "computable_candidate"

    elif (
        computable_known >= 4
        or (
            computable_known >= 3
            and spec.completeness >= 50.0
        )
    ):
        spec.computability = "semi_computable"

    else:
        spec.computability = "reference_only"

    ambiguities: list[str] = []

    if not spec.signal_rules:
        ambiguities.append(
            "signal_logic_not_explicit"
        )

    if not spec.entry_rules:
        ambiguities.append(
            "entry_logic_not_explicit"
        )

    if not spec.exit_rules:
        ambiguities.append(
            "exit_logic_not_explicit"
        )

    if not spec.timeframe:
        ambiguities.append(
            "timeframe_not_explicit"
        )

    if not spec.parameters:
        ambiguities.append(
            "parameters_not_explicit"
        )

    if not spec.market_scope:
        ambiguities.append(
            "market_scope_not_explicit"
        )

    if len(spec.entry_rules) > 5:
        ambiguities.append(
            "multiple_entry_phrasings"
        )

    if len(spec.exit_rules) > 5:
        ambiguities.append(
            "multiple_exit_phrasings"
        )

    spec.ambiguities = ambiguities

    # Confidence: completeness + explicit evidence,
    # ancak eksik bilgiyi doldurmaya çalışarak puan şişirmiyoruz.
    confidence = 20.0

    if spec.method_name:
        confidence += 10.0

    if spec.objective:
        confidence += 8.0

    confidence += min(
        16.0,
        len(spec.inputs) * 4.0,
    )

    confidence += min(
        16.0,
        len(spec.signal_rules) * 4.0,
    )

    confidence += min(
        10.0,
        len(spec.entry_rules) * 2.0,
    )

    confidence += min(
        10.0,
        len(spec.exit_rules) * 2.0,
    )

    if spec.timeframe:
        confidence += 5.0

    if spec.parameters:
        confidence += 5.0

    if spec.source_id is not None:
        confidence += 3.0

    confidence -= min(
        20.0,
        len(spec.missing_fields) * 1.75,
    )

    spec.confidence = round(
        max(
            0.0,
            min(
                100.0,
                confidence,
            ),
        ),
        1,
    )


# ============================================================================
# REGISTRY + KNOWLEDGE LINKING
# ============================================================================


def registry_aliases(
    registry_row: sqlite3.Row,
) -> list[str]:
    aliases: list[str] = []

    for key in (
        "registry_name",
        "canonical_name",
    ):
        value = clean_text(
            registry_row[key]
        )

        if value:
            aliases.append(value)

    return list(
        dict.fromkeys(
            aliases
        )
    )


def build_knowledge_index(
    knowledge_rows: list[sqlite3.Row],
) -> dict[str, list[sqlite3.Row]]:
    index: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in knowledge_rows:
        title = clean_text(
            row["title"]
        )
        method = clean_text(
            row["method"]
        )

        keys = {
            canonical_key(title),
            canonical_key(method),
        }

        # Yalnızca gerçekten anlamlı anahtarları ekle.
        for key in keys:
            if key:
                index[key].append(row)

    return index


def score_knowledge_link(
    registry_name: str,
    registry_category: str | None,
    row: sqlite3.Row,
) -> float:
    title = clean_text(
        row["title"]
    )
    method = clean_text(
        row["method"]
    )
    content = clean_text(
        row["content"]
    )
    item_type = norm(
        row["item_type"]
    )

    reg_key = canonical_key(
        registry_name
    )
    title_key = canonical_key(
        title
    )
    method_key = canonical_key(
        method
    )

    score = 0.0

    if reg_key and reg_key == title_key:
        score += 70.0

    if reg_key and reg_key == method_key:
        score += 85.0

    # Sadece yöntemin adı içerikte açıkça geçiyorsa zayıf destek.
    reg_norm = norm(
        registry_name
    )

    if (
        reg_norm
        and len(reg_norm) >= 5
        and reg_norm in norm(content)[:5000]
    ):
        score += 15.0

    if registry_category:
        if norm(registry_category) == item_type:
            score += 5.0

    strength = method_strength(
        title,
        method,
        content,
        item_type,
    )

    score += min(
        10.0,
        strength / 10.0,
    )

    return min(
        100.0,
        score,
    )


def link_registry_to_knowledge(
    registry_row: sqlite3.Row,
    all_knowledge: list[sqlite3.Row],
    knowledge_index: dict[str, list[sqlite3.Row]],
) -> list[tuple[sqlite3.Row, float]]:
    names = registry_aliases(
        registry_row
    )

    candidate_rows: dict[int, sqlite3.Row] = {}

    for name in names:
        key = canonical_key(
            name
        )

        if not key:
            continue

        for row in knowledge_index.get(
            key,
            [],
        ):
            candidate_rows[
                int(row["knowledge_id"])
            ] = row

    # Fallback:
    # registry ile aynı method/title anahtarını yakalayamadıysa
    # yalnızca method alanında exact normalized eşleşme ara.
    if not candidate_rows:
        wanted = {
            canonical_key(name)
            for name in names
            if canonical_key(name)
        }

        for row in all_knowledge:
            row_keys = {
                canonical_key(row["title"]),
                canonical_key(row["method"]),
            }

            if wanted.intersection(
                row_keys
            ):
                candidate_rows[
                    int(row["knowledge_id"])
                ] = row

    scored: list[tuple[sqlite3.Row, float]] = []

    registry_category = clean_text(
        registry_row["registry_category"]
    )

    registry_name = (
        clean_text(
            registry_row["canonical_name"]
        )
        or clean_text(
            registry_row["registry_name"]
        )
    )

    for row in candidate_rows.values():
        score = score_knowledge_link(
            registry_name,
            registry_category,
            row,
        )

        # 60 altındaki zayıf bağlantıları spesifikasyona
        # "kanıt" olarak sokma.
        if score >= 60.0:
            scored.append(
                (row, score)
            )

    scored.sort(
        key=lambda item: (
            -item[1],
            -len(
                clean_text(
                    item[0]["content"]
                )
            ),
            int(
                item[0]["knowledge_id"]
            ),
        )
    )

    return scored


# ============================================================================
# SPEC BUILD
# ============================================================================


def build_spec_from_registry(
    registry_row: sqlite3.Row,
    linked_rows: list[tuple[sqlite3.Row, float]],
) -> MethodSpec:
    registry_id = registry_row["registry_id"]

    method_name = (
        clean_text(
            registry_row["canonical_name"]
        )
        or clean_text(
            registry_row["registry_name"]
        )
        or f"Registry Method #{registry_id}"
    )

    registry_category = clean_text(
        registry_row["registry_category"]
    )

    best_row: sqlite3.Row | None = (
        linked_rows[0][0]
        if linked_rows
        else None
    )

    all_text_parts: list[str] = []

    linked_knowledge_ids = []
    linked_source_ids = []

    # En fazla en güçlü birkaç kayıt; aşırı tekrarın
    # extraction'ı şişirmesini önler.
    for row, _score in linked_rows[:8]:
        linked_knowledge_ids.append(
            int(row["knowledge_id"])
        )

        if row["source_id"] is not None:
            linked_source_ids.append(
                int(row["source_id"])
            )

        all_text_parts.extend(
            [
                clean_text(row["title"]),
                clean_text(row["method"]),
                clean_text(row["summary"]),
                clean_text(row["content"]),
            ]
        )

    # Registry adı da kaynak metnine girsin,
    # fakat registry adı tek başına kural olarak sayılmasın.
    all_text_parts.insert(
        0,
        method_name,
    )

    source_text = "\n".join(
        part
        for part in all_text_parts
        if part
    )

    tags: list[str] = []
    if best_row is not None:
        tags = as_string_list(
            best_row["tags_json"]
        )

    inputs = extract_indicators(
        source_text
    )

    signal_rules = extract_lines(
        source_text,
        SIGNAL_WORDS,
        limit=20,
    )

    entry_rules = extract_lines(
        source_text,
        ENTRY_WORDS,
        limit=20,
    )

    exit_rules = extract_lines(
        source_text,
        EXIT_WORDS,
        limit=20,
    )

    filters = extract_lines(
        source_text,
        FILTER_WORDS,
        limit=20,
    )

    risk_rules = extract_lines(
        source_text,
        RISK_WORDS,
        limit=20,
    )

    timeframe = extract_timeframe(
        source_text
    )

    market_scope = extract_market_scope(
        source_text
    )

    parameters = extract_parameters(
        source_text
    )

    category = infer_category(
        method_name,
        (
            clean_text(
                best_row["method"]
            )
            if best_row is not None
            else ""
        ),
        tags,
        registry_category,
    )

    summary = (
        clean_text(
            best_row["summary"]
        )
        if best_row is not None
        else ""
    )

    objective = infer_objective(
        method_name,
        (
            clean_text(
                best_row["method"]
            )
            if best_row is not None
            else ""
        ),
        summary,
    )

    source_id = None
    if best_row is not None:
        if best_row["source_id"] is not None:
            source_id = int(
                best_row["source_id"]
            )

    content_length = sum(
        len(
            clean_text(row["content"])
        )
        for row, _score in linked_rows[:8]
    )

    evidence_state, evidence_notes = (
        extract_evidence_state(
            source_id,
            linked_knowledge_ids,
            content_length,
        )
    )

    if not linked_rows:
        evidence_state = "registry_only"
        evidence_notes = [
            "Registry kaydı var fakat eşleşen knowledge item bulunamadı.",
            "Specification alanları varsayımla doldurulmadı.",
        ]

    spec = MethodSpec(
        method_id=registry_id,
        registry_id=registry_id,
        source_id=source_id,
        method_name=method_name,
        canonical_key=canonical_key(
            method_name
        ),
        category=category,
        objective=objective,
        inputs=inputs,
        parameters=parameters,
        signal_rules=signal_rules,
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        filters=filters,
        timeframe=timeframe,
        market_scope=market_scope,
        risk_rules=risk_rules,
        linked_knowledge_ids=sorted(
            set(linked_knowledge_ids)
        ),
        linked_source_ids=sorted(
            set(linked_source_ids)
        ),
        evidence_state=evidence_state,
        evidence_notes=evidence_notes,
        source_text=source_text[:20000],
        extraction_method=ENGINE_NAME,
        created_at=now_iso(),
        updated_at=now_iso(),
    )

    finalize_spec(
        spec
    )

    return spec


# ============================================================================
# SAVE
# ============================================================================


def save_spec(
    conn: sqlite3.Connection,
    spec: MethodSpec,
) -> None:
    payload = spec.to_db_payload()

    conn.execute(
        """
        INSERT INTO method_specifications (
            method_id,
            registry_id,
            source_id,
            method_name,
            canonical_key,
            category,
            objective,

            inputs_json,
            parameters_json,
            signal_rules_json,
            entry_rules_json,
            exit_rules_json,
            filters_json,

            timeframe,
            market_scope_json,
            risk_rules_json,

            linked_knowledge_ids_json,
            linked_source_ids_json,

            evidence_state,
            evidence_notes_json,

            source_text,
            extraction_method,

            confidence,
            completeness,
            computability,

            missing_fields_json,
            ambiguities_json,

            created_at,
            updated_at
        )
        VALUES (
            :method_id,
            :registry_id,
            :source_id,
            :method_name,
            :canonical_key,
            :category,
            :objective,

            :inputs,
            :parameters,
            :signal_rules,
            :entry_rules,
            :exit_rules,
            :filters,

            :timeframe,
            :market_scope,
            :risk_rules,

            :linked_knowledge_ids,
            :linked_source_ids,

            :evidence_state,
            :evidence_notes,

            :source_text,
            :extraction_method,

            :confidence,
            :completeness,
            :computability,

            :missing_fields,
            :ambiguities,

            :created_at,
            :updated_at
        )
        ON CONFLICT(method_id)
        DO UPDATE SET
            registry_id = excluded.registry_id,
            source_id = excluded.source_id,
            method_name = excluded.method_name,
            canonical_key = excluded.canonical_key,
            category = excluded.category,
            objective = excluded.objective,

            inputs_json = excluded.inputs_json,
            parameters_json = excluded.parameters_json,
            signal_rules_json = excluded.signal_rules_json,
            entry_rules_json = excluded.entry_rules_json,
            exit_rules_json = excluded.exit_rules_json,
            filters_json = excluded.filters_json,

            timeframe = excluded.timeframe,
            market_scope_json = excluded.market_scope_json,
            risk_rules_json = excluded.risk_rules_json,

            linked_knowledge_ids_json =
                excluded.linked_knowledge_ids_json,

            linked_source_ids_json =
                excluded.linked_source_ids_json,

            evidence_state = excluded.evidence_state,
            evidence_notes_json = excluded.evidence_notes_json,

            source_text = excluded.source_text,
            extraction_method = excluded.extraction_method,

            confidence = excluded.confidence,
            completeness = excluded.completeness,
            computability = excluded.computability,

            missing_fields_json =
                excluded.missing_fields_json,

            ambiguities_json =
                excluded.ambiguities_json,

            updated_at = excluded.updated_at
        """,
        payload,
    )


def save_json_output(
    payload: dict[str, Any],
) -> None:
    temp_path = OUTPUT_PATH.with_suffix(
        OUTPUT_PATH.suffix + ".tmp"
    )

    temp_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_path.replace(
        OUTPUT_PATH
    )


# ============================================================================
# REPORTING
# ============================================================================


def percentile(
    values: list[float],
    p: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    index = (
        (len(ordered) - 1)
        * p
    )

    lower = int(index)
    upper = min(
        lower + 1,
        len(ordered) - 1,
    )

    weight = index - lower

    return (
        ordered[lower]
        * (1.0 - weight)
        + ordered[upper]
        * weight
    )


def make_payload(
    specs: list[MethodSpec],
    registry_count: int,
    knowledge_count: int,
    unmatched_registry_ids: list[int],
) -> dict[str, Any]:
    counts = Counter(
        spec.computability
        for spec in specs
    )

    evidence_counts = Counter(
        spec.evidence_state
        for spec in specs
    )

    categories = Counter(
        spec.category
        for spec in specs
    )

    confidences = [
        spec.confidence
        for spec in specs
    ]

    completeness = [
        spec.completeness
        for spec in specs
    ]

    return {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "generated_at": now_iso(),

        "database": str(DB_PATH),

        "registry_count": registry_count,
        "knowledge_item_count": knowledge_count,
        "specification_count": len(specs),

        "unmatched_registry_count": len(
            unmatched_registry_ids
        ),
        "unmatched_registry_ids": unmatched_registry_ids,

        "computable_candidates": counts.get(
            "computable_candidate",
            0,
        ),
        "semi_computable": counts.get(
            "semi_computable",
            0,
        ),
        "reference_only": counts.get(
            "reference_only",
            0,
        ),

        "evidence_states": dict(
            evidence_counts
        ),
        "categories": dict(
            categories
        ),

        "average_confidence": round(
            statistics.mean(confidences)
            if confidences
            else 0.0,
            1,
        ),

        "median_confidence": round(
            statistics.median(confidences)
            if confidences
            else 0.0,
            1,
        ),

        "average_completeness": round(
            statistics.mean(completeness)
            if completeness
            else 0.0,
            1,
        ),

        "median_completeness": round(
            statistics.median(completeness)
            if completeness
            else 0.0,
            1,
        ),

        "p90_completeness": round(
            percentile(
                completeness,
                0.90,
            ),
            1,
        ),

        "methods": [
            asdict(spec)
            for spec in specs
        ],
    }


# ============================================================================
# MAIN ENGINE
# ============================================================================


def run() -> dict[str, Any]:
    conn = connect()

    try:
        if not table_exists(
            conn,
            "method_registry",
        ):
            raise RuntimeError(
                "method_registry tablosu bulunamadı."
            )

        if not table_exists(
            conn,
            "knowledge_items",
        ):
            raise RuntimeError(
                "knowledge_items tablosu bulunamadı."
            )

        ensure_schema(
            conn
        )

        registry_layout = discover_registry_layout(
            conn
        )

        registry_rows = load_registry_rows(
            conn,
            registry_layout,
        )

        knowledge_rows = load_knowledge_rows(
            conn
        )

        knowledge_index = build_knowledge_index(
            knowledge_rows
        )

        specs: list[MethodSpec] = []

        unmatched_registry_ids: list[int] = []

        errors: list[dict[str, Any]] = []

        for registry_row in registry_rows:
            registry_id = int(
                registry_row["registry_id"]
            )

            try:
                # Bilinçli olarak fuzzy merge YOK.
                linked_rows = link_registry_to_knowledge(
                    registry_row,
                    knowledge_rows,
                    knowledge_index,
                )

                if not linked_rows:
                    unmatched_registry_ids.append(
                        registry_id
                    )

                spec = build_spec_from_registry(
                    registry_row,
                    linked_rows,
                )

                save_spec(
                    conn,
                    spec,
                )

                specs.append(
                    spec
                )

            except Exception as exc:
                errors.append(
                    {
                        "registry_id": registry_id,
                        "error": str(exc),
                    }
                )

        conn.commit()

        payload = make_payload(
            specs,
            registry_count=len(
                registry_rows
            ),
            knowledge_count=len(
                knowledge_rows
            ),
            unmatched_registry_ids=unmatched_registry_ids,
        )

        payload["errors"] = errors
        payload["registry_layout"] = registry_layout
        payload["status"] = (
            "completed"
            if not errors
            else "completed_with_errors"
        )

        save_json_output(
            payload
        )

        return payload

    finally:
        conn.close()


def print_summary(
    payload: dict[str, Any],
) -> None:
    print()
    print("=" * 78)
    print("FIN[SYS] METHOD SPECIFICATION ENGINE V3")
    print("=" * 78)

    print(
        f"Database: {payload['database']}"
    )

    print(
        f"Registry: {payload['registry_count']}"
    )

    print(
        f"Knowledge items: {payload['knowledge_item_count']}"
    )

    print(
        f"Specifications: {payload['specification_count']}"
    )

    print()

    print("COMPUTABILITY")
    print("-" * 78)

    print(
        "Computable candidates: "
        f"{payload['computable_candidates']}"
    )

    print(
        "Semi-computable: "
        f"{payload['semi_computable']}"
    )

    print(
        "Reference-only: "
        f"{payload['reference_only']}"
    )

    print()

    print("QUALITY")
    print("-" * 78)

    print(
        "Average confidence: "
        f"{payload['average_confidence']}"
    )

    print(
        "Median confidence: "
        f"{payload['median_confidence']}"
    )

    print(
        "Average completeness: "
        f"{payload['average_completeness']}"
    )

    print(
        "Median completeness: "
        f"{payload['median_completeness']}"
    )

    print(
        "P90 completeness: "
        f"{payload['p90_completeness']}"
    )

    print()

    print("EVIDENCE")
    print("-" * 78)

    for key, value in sorted(
        payload["evidence_states"].items()
    ):
        print(
            f"{key}: {value}"
        )

    print()

    print("UNMATCHED REGISTRY")
    print("-" * 78)

    print(
        payload["unmatched_registry_count"]
    )

    print()

    print("TOP COMPUTABLE / SEMI-COMPUTABLE")
    print("-" * 78)

    ranked = [
        item
        for item in payload["methods"]
        if item["computability"]
        in {
            "computable_candidate",
            "semi_computable",
        }
    ]

    ranked.sort(
        key=lambda item: (
            0
            if item["computability"]
            == "computable_candidate"
            else 1,
            -float(
                item["completeness"]
            ),
            -float(
                item["confidence"]
            ),
        )
    )

    for index, item in enumerate(
        ranked[:20],
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{item['method_name'][:68]} | "
            f"{item['computability']} | "
            f"C={item['completeness']:.1f} | "
            f"Conf={item['confidence']:.1f} | "
            f"Knowledge={len(item['linked_knowledge_ids'])}"
        )

    print()

    if payload["errors"]:
        print("ERRORS")
        print("-" * 78)

        for error in payload["errors"][:20]:
            print(
                f"- registry_id="
                f"{error['registry_id']}: "
                f"{error['error']}"
            )

        print()

    print(
        f"JSON output: {OUTPUT_PATH}"
    )

    print(
        "Method Specification Engine V3 tamamlandı."
    )


def main() -> None:
    try:
        payload = run()
        print_summary(
            payload
        )

    except Exception as exc:
        print()
        print(
            "METHOD SPECIFICATION ENGINE V3 HATASI"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        raise


if __name__ == "__main__":
    main()

