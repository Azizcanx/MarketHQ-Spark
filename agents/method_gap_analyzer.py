import os
import sys
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


# ============================================================
# PATH
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
        CREATE TABLE IF NOT EXISTS method_gap_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,
            category TEXT,

            classification TEXT,

            verification_score REAL,
            reproducibility_score REAL,
            implementation_readiness REAL,

            indicators_found TEXT,
            parameters_found TEXT,
            signals_found TEXT,
            timeframes_found TEXT,

            has_indicator_detail INTEGER,
            has_parameter_detail INTEGER,
            has_signal_detail INTEGER,
            has_timeframe_detail INTEGER,
            has_formula_detail INTEGER,
            has_implementation_detail INTEGER,

            missing_indicator_detail INTEGER,
            missing_parameter_detail INTEGER,
            missing_signal_detail INTEGER,
            missing_timeframe_detail INTEGER,
            missing_formula_detail INTEGER,
            missing_implementation_detail INTEGER,

            gap_count INTEGER,
            gap_severity TEXT,

            missing_information TEXT,
            present_information TEXT,

            source_titles TEXT,
            source_urls TEXT,

            implementation_notes TEXT,

            analyzed_at TEXT,

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


def parse_json(
    value: Any
) -> Any:

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


def bool_to_int(
    value: bool
) -> int:

    return 1 if value else 0


# ============================================================
# LOAD SEMI-COMPUTABLE METHODS
# ============================================================

def load_semi_computable() -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "method_reproducibility"
    ):
        conn.close()

        raise RuntimeError(
            "method_reproducibility tablosu bulunamadı.\n"
            "Önce method_reproducibility_classifier.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM method_reproducibility
        WHERE classification = 'semi_computable'
        ORDER BY implementation_readiness DESC
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def extract_sources(
    row: Dict[str, Any]
) -> List[Dict[str, Any]]:

    parsed = parse_json(
        row.get("source_snapshot")
    )

    if not parsed:
        return []

    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list):
        return []

    sources = []

    for source in parsed:

        if not isinstance(source, dict):
            continue

        sources.append(
            {
                "title": normalize(
                    source.get("title")
                ),
                "url": normalize(
                    source.get("url")
                ),
                "source_type": normalize(
                    source.get("source_type")
                ),
                "text": normalize(
                    source.get("text")
                ),
            }
        )

    return sources


def combine_sources(
    sources: List[Dict[str, Any]]
) -> str:

    parts = []

    for source in sources:

        title = source.get(
            "title",
            ""
        )

        text = source.get(
            "text",
            ""
        )

        if title:
            parts.append(title)

        if text:
            parts.append(text)

    return "\n".join(parts)


# ============================================================
# TEXT ANALYSIS
# ============================================================

INDICATOR_TERMS = [
    "rsi",
    "macd",
    "ema",
    "sma",
    "wma",
    "hma",
    "bollinger",
    "bollinger bands",
    "stochastic",
    "atr",
    "adx",
    "cci",
    "obv",
    "mfi",
    "roc",
    "momentum",
    "zlsma",
    "fft",
    "regression",
    "fibonacci",
    "ichimoku",
    "moving average",
    "hareketli ortalama",
]


PARAMETER_TERMS = [
    "period",
    "periods",
    "length",
    "window",
    "lookback",
    "threshold",
    "factor",
    "multiplier",
    "sensitivity",
    "fast",
    "slow",
    "signal",
    "deviation",
    "band",
    "bands",
    "periyot",
    "periyod",
    "eşik",
    "katsayı",
    "çarpan",
    "pencere",
    "uzunluk",
]


SIGNAL_TERMS = [
    "buy",
    "sell",
    "long",
    "short",
    "entry",
    "exit",
    "signal",
    "cross",
    "crossover",
    "crossunder",
    "breakout",
    "breakdown",
    "alım",
    "satım",
    "alış",
    "satış",
    "sinyal",
    "giriş",
    "çıkış",
    "kesişim",
    "kırılım",
]


TIMEFRAME_TERMS = [
    "1 dakika",
    "3 dakika",
    "5 dakika",
    "15 dakika",
    "30 dakika",
    "1 saat",
    "2 saat",
    "4 saat",
    "günlük",
    "haftalık",
    "aylık",
    "daily",
    "weekly",
    "monthly",
    "intraday",
    "multi timeframe",
    "multi-timeframe",
    "çoklu zaman",
]


FORMULA_TERMS = [
    "formula",
    "formül",
    "equation",
    "denklem",
    "calculate",
    "calculation",
    "hesapla",
    "hesaplama",
    "hesaplanır",
    "standard deviation",
    "standart sapma",
    "regression equation",
    "regresyon",
]


IMPLEMENTATION_TERMS = [
    "python",
    "pine script",
    "pinescript",
    "code",
    "kod",
    "script",
    "function",
    "fonksiyon",
    "api",
    "scanner",
    "scan",
    "tarama",
    "filter",
    "filtre",
    "backtest",
    "algoritma",
    "algorithm",
]


def find_terms(
    text: str,
    terms: List[str]
) -> List[str]:

    lower = text.lower()

    found = []

    for term in terms:

        if term.lower() in lower:
            found.append(term)

    return found


def extract_numeric_parameter_patterns(
    text: str
) -> List[str]:

    """
    Açık sayısal parametre ifadelerini yakalamaya çalışır.
    Örnek:
    EMA 20
    RSI 14
    50 günlük
    2.0 multiplier
    """

    import re

    patterns = [
        r"\b(?:rsi|ema|sma|wma|hma|atr|adx|cci)\s*[=:]?\s*\d+(?:\.\d+)?\b",

        r"\b\d+(?:\.\d+)?\s*(?:period|periods|gün|günlük|hafta|haftalık|bars?)\b",

        r"\b(?:length|period|window|lookback|threshold|factor|multiplier|sensitivity)\s*[=:]?\s*\d+(?:\.\d+)?\b",

        r"\b(?:periyot|eşik|katsayı|çarpan|pencere|uzunluk)\s*[=:]?\s*\d+(?:\.\d+)?\b",
    ]

    found = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for match in matches:

            value = (
                match
                if isinstance(match, str)
                else " ".join(match)
            )

            value = value.strip()

            if value and value not in found:
                found.append(value)

    return found[:30]


# ============================================================
# GAP CALCULATION
# ============================================================

def analyze_gaps(
    row: Dict[str, Any]
) -> Dict[str, Any]:

    sources = extract_sources(
        row
    )

    source_text = combine_sources(
        sources
    )

    indicators = find_terms(
        source_text,
        INDICATOR_TERMS
    )

    parameters = find_terms(
        source_text,
        PARAMETER_TERMS
    )

    numeric_parameters = (
        extract_numeric_parameter_patterns(
            source_text
        )
    )

    signals = find_terms(
        source_text,
        SIGNAL_TERMS
    )

    timeframes = find_terms(
        source_text,
        TIMEFRAME_TERMS
    )

    formulas = find_terms(
        source_text,
        FORMULA_TERMS
    )

    implementations = find_terms(
        source_text,
        IMPLEMENTATION_TERMS
    )

    # --------------------------------------------------------
    # DETAIL TESTS
    # --------------------------------------------------------

    has_indicator_detail = (
        len(indicators) >= 1
    )

    has_parameter_detail = (
        len(parameters) >= 1
        or len(numeric_parameters) >= 1
    )

    has_signal_detail = (
        len(signals) >= 1
    )

    has_timeframe_detail = (
        len(timeframes) >= 1
    )

    has_formula_detail = (
        len(formulas) >= 1
    )

    has_implementation_detail = (
        len(implementations) >= 1
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # A keyword appearing in source does NOT mean the
    # method is fully reproducible.
    #
    # We therefore mark gaps conservatively.
    # --------------------------------------------------------

    missing_information = []
    present_information = []

    if has_indicator_detail:
        present_information.append(
            "En az bir teknik indikatör/girdi adı mevcut."
        )
    else:
        missing_information.append(
            "Kullanılan indikatör veya temel teknik girdiler"
        )

    if has_parameter_detail:
        present_information.append(
            "Parametre/periyot ile ilgili ifadeler mevcut."
        )
    else:
        missing_information.append(
            "Net parametre değerleri veya hesaplama pencereleri"
        )

    if has_signal_detail:
        present_information.append(
            "Sinyal/giriş/çıkış dili mevcut."
        )
    else:
        missing_information.append(
            "Açık giriş/çıkış koşulları"
        )

    if has_timeframe_detail:
        present_information.append(
            "En az bir zaman dilimi ifadesi mevcut."
        )
    else:
        missing_information.append(
            "Net zaman dilimi veya çoklu zaman kullanımı"
        )

    if has_formula_detail:
        present_information.append(
            "Formül/hesaplama ile ilgili ifade mevcut."
        )
    else:
        missing_information.append(
            "Matematiksel/hesaplama formülü"
        )

    if has_implementation_detail:
        present_information.append(
            "Kodlama/uygulama ile ilgili ifade mevcut."
        )
    else:
        missing_information.append(
            "Kodlama veya uygulama prosedürü"
        )

    # --------------------------------------------------------
    # IMPORTANT EXTRA GAP:
    # Parameter names without numerical values are not enough.
    # --------------------------------------------------------

    if parameters and not numeric_parameters:

        missing_information.append(
            "Parametre isimleri var ancak açık sayısal değerleri yok."
        )

    # --------------------------------------------------------
    # GAP SEVERITY
    # --------------------------------------------------------

    gap_count = len(
        missing_information
    )

    if gap_count <= 1:
        gap_severity = "low"

    elif gap_count <= 3:
        gap_severity = "medium"

    elif gap_count <= 5:
        gap_severity = "high"

    else:
        gap_severity = "critical"

    # --------------------------------------------------------
    # IMPLEMENTATION NOTES
    # --------------------------------------------------------

    notes = []

    if not has_indicator_detail:
        notes.append(
            "Önce giriş/indikatör yapısı netleştirilmeli."
        )

    if not has_parameter_detail:
        notes.append(
            "Parametreler kaynaklardan doğrulanmadan "
            "varsayılan değer kullanılmamalı."
        )

    if not has_signal_detail:
        notes.append(
            "Sinyal kuralı tahmin edilerek oluşturulmamalı."
        )

    if not has_timeframe_detail:
        notes.append(
            "Test zaman dilimi belirlenmeden backtest yapılmamalı."
        )

    if not has_formula_detail:
        notes.append(
            "Formül bilinmiyorsa gösterge yeniden yazılmamalı."
        )

    if not has_implementation_detail:
        notes.append(
            "Kaynağın anlatımı uygulama detayı içermiyor."
        )

    if (
        row.get("reproducibility_score", 0)
        and safe_float(
            row.get("reproducibility_score")
        ) < 30
    ):
        notes.append(
            "AI reproducibility skoru düşük; "
            "metodun önce kaynak açısından detaylandırılması gerekiyor."
        )

    # --------------------------------------------------------
    # SOURCE META
    # --------------------------------------------------------

    source_titles = [
        source["title"]
        for source in sources
        if source["title"]
    ]

    source_urls = [
        source["url"]
        for source in sources
        if source["url"]
    ]

    return {
        "method_id": row.get("method_id"),
        "canonical_name": normalize(
            row.get("canonical_name")
        ),
        "category": normalize(
            row.get("category")
        ),

        "classification": normalize(
            row.get("classification")
        ),

        "verification_score": safe_float(
            row.get("verification_score")
        ),

        "reproducibility_score": safe_float(
            row.get("reproducibility_score")
        ),

        "implementation_readiness": safe_float(
            row.get("implementation_readiness")
        ),

        "indicators_found": indicators,
        "parameters_found": parameters,
        "numeric_parameters_found": numeric_parameters,
        "signals_found": signals,
        "timeframes_found": timeframes,
        "formulas_found": formulas,
        "implementations_found": implementations,

        "has_indicator_detail": has_indicator_detail,
        "has_parameter_detail": has_parameter_detail,
        "has_signal_detail": has_signal_detail,
        "has_timeframe_detail": has_timeframe_detail,
        "has_formula_detail": has_formula_detail,
        "has_implementation_detail": has_implementation_detail,

        "gap_count": gap_count,
        "gap_severity": gap_severity,

        "missing_information": missing_information,
        "present_information": present_information,

        "source_titles": source_titles,
        "source_urls": source_urls,

        "implementation_notes": notes,
    }


# ============================================================
# SAVE
# ============================================================

def save_result(
    result: Dict[str, Any]
) -> None:

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO method_gap_analysis (
            method_id,
            canonical_name,
            category,
            classification,

            verification_score,
            reproducibility_score,
            implementation_readiness,

            indicators_found,
            parameters_found,
            signals_found,
            timeframes_found,

            has_indicator_detail,
            has_parameter_detail,
            has_signal_detail,
            has_timeframe_detail,
            has_formula_detail,
            has_implementation_detail,

            missing_indicator_detail,
            missing_parameter_detail,
            missing_signal_detail,
            missing_timeframe_detail,
            missing_formula_detail,
            missing_implementation_detail,

            gap_count,
            gap_severity,

            missing_information,
            present_information,

            source_titles,
            source_urls,

            implementation_notes,

            analyzed_at
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?,
            ?
        )

        ON CONFLICT(method_id, canonical_name)
        DO UPDATE SET
            category = excluded.category,
            classification = excluded.classification,

            verification_score = excluded.verification_score,
            reproducibility_score = excluded.reproducibility_score,
            implementation_readiness = excluded.implementation_readiness,

            indicators_found = excluded.indicators_found,
            parameters_found = excluded.parameters_found,
            signals_found = excluded.signals_found,
            timeframes_found = excluded.timeframes_found,

            has_indicator_detail = excluded.has_indicator_detail,
            has_parameter_detail = excluded.has_parameter_detail,
            has_signal_detail = excluded.has_signal_detail,
            has_timeframe_detail = excluded.has_timeframe_detail,
            has_formula_detail = excluded.has_formula_detail,
            has_implementation_detail = excluded.has_implementation_detail,

            missing_indicator_detail = excluded.missing_indicator_detail,
            missing_parameter_detail = excluded.missing_parameter_detail,
            missing_signal_detail = excluded.missing_signal_detail,
            missing_timeframe_detail = excluded.missing_timeframe_detail,
            missing_formula_detail = excluded.missing_formula_detail,
            missing_implementation_detail = excluded.missing_implementation_detail,

            gap_count = excluded.gap_count,
            gap_severity = excluded.gap_severity,

            missing_information = excluded.missing_information,
            present_information = excluded.present_information,

            source_titles = excluded.source_titles,
            source_urls = excluded.source_urls,

            implementation_notes = excluded.implementation_notes,

            analyzed_at = excluded.analyzed_at
        """,
        (
            result["method_id"],
            result["canonical_name"],
            result["category"],
            result["classification"],

            result["verification_score"],
            result["reproducibility_score"],
            result["implementation_readiness"],

            json.dumps(
                result["indicators_found"],
                ensure_ascii=False
            ),

            json.dumps(
                (
                    result["parameters_found"]
                    + [
                        f"NUMERIC:{value}"
                        for value in result["numeric_parameters_found"]
                    ]
                ),
                ensure_ascii=False
            ),

            json.dumps(
                result["signals_found"],
                ensure_ascii=False
            ),

            json.dumps(
                result["timeframes_found"],
                ensure_ascii=False
            ),

            bool_to_int(
                result["has_indicator_detail"]
            ),

            bool_to_int(
                result["has_parameter_detail"]
            ),

            bool_to_int(
                result["has_signal_detail"]
            ),

            bool_to_int(
                result["has_timeframe_detail"]
            ),

            bool_to_int(
                result["has_formula_detail"]
            ),

            bool_to_int(
                result["has_implementation_detail"]
            ),

            bool_to_int(
                not result["has_indicator_detail"]
            ),

            bool_to_int(
                not result["has_parameter_detail"]
            ),

            bool_to_int(
                not result["has_signal_detail"]
            ),

            bool_to_int(
                not result["has_timeframe_detail"]
            ),

            bool_to_int(
                not result["has_formula_detail"]
            ),

            bool_to_int(
                not result["has_implementation_detail"]
            ),

            result["gap_count"],
            result["gap_severity"],

            json.dumps(
                result["missing_information"],
                ensure_ascii=False
            ),

            json.dumps(
                result["present_information"],
                ensure_ascii=False
            ),

            json.dumps(
                result["source_titles"],
                ensure_ascii=False
            ),

            json.dumps(
                result["source_urls"],
                ensure_ascii=False
            ),

            json.dumps(
                result["implementation_notes"],
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

def print_method(
    result: Dict[str, Any]
) -> None:

    print()
    print(
        f"• {result['canonical_name']}"
    )

    print(
        f"  Kategori: {result['category']}"
    )

    print(
        f"  Verification: "
        f"{result['verification_score']:.1f}/100"
    )

    print(
        f"  Reproducibility: "
        f"{result['reproducibility_score']:.1f}/100"
    )

    print(
        f"  Readiness: "
        f"{result['implementation_readiness']:.1f}/100"
    )

    print(
        f"  Gap: "
        f"{result['gap_count']} "
        f"({result['gap_severity']})"
    )

    print(
        f"  İndikatörler: "
        f"{', '.join(result['indicators_found']) or 'YOK'}"
    )

    numeric = result[
        "numeric_parameters_found"
    ]

    print(
        f"  Parametreler: "
        f"{', '.join(numeric) or 'NET DEĞER YOK'}"
    )

    print(
        f"  Sinyaller: "
        f"{', '.join(result['signals_found']) or 'YOK'}"
    )

    print(
        f"  Zaman dilimleri: "
        f"{', '.join(result['timeframes_found']) or 'YOK'}"
    )

    if result["missing_information"]:

        print(
            "  Eksikler:"
        )

        for item in result[
            "missing_information"
        ]:
            print(
                f"    - {item}"
            )

    else:

        print(
            "  Eksikler: önemli bir boşluk tespit edilmedi."
        )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    severity_counts = {
        "low": 0,
        "medium": 0,
        "high": 0,
        "critical": 0,
    }

    total_gaps = 0

    for result in results:

        severity = result[
            "gap_severity"
        ]

        if severity in severity_counts:
            severity_counts[severity] += 1

        total_gaps += result[
            "gap_count"
        ]

    average_gap = (
        total_gaps / len(results)
        if results
        else 0
    )

    print()
    print("=========================================")
    print("🧩 METHOD GAP ANALYZER SONUCU")
    print("=========================================")

    print(
        f"Analiz edilen semi-computable method: "
        f"{len(results)}"
    )

    print(
        f"Ortalama bilgi boşluğu: "
        f"{average_gap:.1f}"
    )

    print()
    print("GAP SEVERITY")
    print("-----------------------------------------")

    print(
        f"Low:       {severity_counts['low']}"
    )

    print(
        f"Medium:    {severity_counts['medium']}"
    )

    print(
        f"High:      {severity_counts['high']}"
    )

    print(
        f"Critical:  {severity_counts['critical']}"
    )

    print()
    print("=========================================")


# ============================================================
# PRIORITY REPORT
# ============================================================

def print_priority_list(
    results: List[Dict[str, Any]]
) -> None:

    """
    Bir sonraki aşamada hangi methodların önce
    detaylandırılması gerektiğini belirler.
    """

    # Daha yüksek readiness + daha az gap
    # öncelikli kabul edilir.

    ranked = sorted(
        results,
        key=lambda result: (
            -result["implementation_readiness"],
            result["gap_count"],
        )
    )

    print()
    print("🎯 GELİŞTİRME ÖNCELİĞİ")
    print("-----------------------------------------")

    for index, result in enumerate(
        ranked,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['canonical_name']} "
            f"| readiness="
            f"{result['implementation_readiness']:.1f} "
            f"| gap="
            f"{result['gap_count']} "
            f"| {result['gap_severity']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("🧩 FIN[SYS] METHOD GAP ANALYZER")
    print("=========================================")
    print(
        "API kullanımı: 0"
    )
    print()

    ensure_table()

    methods = load_semi_computable()

    print(
        f"Semi-computable method: "
        f"{len(methods)}"
    )

    if not methods:

        print(
            "❌ Semi-computable method bulunamadı."
        )

        print()
        print(
            "Önce şu dosyayı çalıştır:"
        )

        print(
            "python agents/method_reproducibility_classifier.py"
        )

        return

    results = []

    for row in methods:

        result = analyze_gaps(
            row
        )

        save_result(
            result
        )

        results.append(
            result
        )

        print_method(
            result
        )

    print_summary(
        results
    )

    print_priority_list(
        results
    )

    print()
    print(
        "✅ Method Gap Analyzer tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "En az bilgi boşluğuna sahip methodlar "
        "kaynak-temelli teknik ayrıştırmaya alınacak."
    )


if __name__ == "__main__":
    main()
