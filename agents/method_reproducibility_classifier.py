import os
import sys
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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
# CONFIG
# ============================================================

MIN_COMPUTABLE_REPRODUCIBILITY = 65
MIN_SEMI_REPRODUCIBILITY = 25

MIN_VERIFICATION_FOR_COMPUTABLE = 65
MIN_VERIFICATION_FOR_SEMI = 40

IMPORTANT_CATEGORIES = {
    "algorithm",
    "system",
    "indicator",
    "filter",
    "scan_method",
    "trend_method",
    "momentum_method",
    "volume_method",
    "python_method",
    "tradingview_method",
    "chart_method",
}


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
        CREATE TABLE IF NOT EXISTS method_reproducibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,
            category TEXT,

            classification TEXT NOT NULL,

            verification_score REAL,
            reproducibility_score REAL,

            source_supported INTEGER,
            logic_consistent INTEGER,
            parameters_supported INTEGER,

            technical_detail_score REAL,
            parameter_detail_score REAL,
            signal_detail_score REAL,
            input_detail_score REAL,

            implementation_readiness REAL,

            missing_information TEXT,
            reasoning TEXT,

            source_snapshot TEXT,

            classified_at TEXT,

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


def safe_int(
    value: Any,
    default: int = 0
) -> int:

    try:
        return int(value)
    except Exception:
        return default


def bool_value(value: Any) -> Optional[bool]:

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    text = normalize(value).lower()

    if text in {
        "true",
        "yes",
        "1",
        "supported"
    }:
        return True

    if text in {
        "false",
        "no",
        "0",
        "unsupported"
    }:
        return False

    return None


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


# ============================================================
# LOAD AI VALIDATION
# ============================================================

def load_ai_validations() -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "method_ai_validation"
    ):
        conn.close()

        raise RuntimeError(
            "method_ai_validation tablosu bulunamadı.\n"
            "Önce method_ai_verifier.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM method_ai_validation
        ORDER BY canonical_name
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# SOURCE ANALYSIS
# ============================================================

def extract_source_snapshot(
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

    result = []

    for source in parsed:

        if not isinstance(source, dict):
            continue

        result.append(
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

    return result


def combine_source_text(
    sources: List[Dict[str, Any]]
) -> str:

    chunks = []

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
            chunks.append(title)

        if text:
            chunks.append(text)

    return "\n".join(chunks)


# ============================================================
# TECHNICAL SIGNAL DETECTION
# ============================================================

def contains_any(
    text: str,
    terms: List[str]
) -> bool:

    text = text.lower()

    return any(
        term.lower() in text
        for term in terms
    )


def count_matches(
    text: str,
    terms: List[str]
) -> int:

    text = text.lower()

    return sum(
        1
        for term in terms
        if term.lower() in text
    )


def detect_indicators(
    text: str
) -> List[str]:

    indicators = [
        "rsi",
        "macd",
        "ema",
        "sma",
        "wma",
        "hma",
        "bollinger",
        "stochastic",
        "atr",
        "adx",
        "cci",
        "obv",
        "mfi",
        "roc",
        "momentum",
        "volume",
        "moving average",
        "zlsma",
        "fft",
        "regression",
        "fibonacci",
        "ichimoku",
    ]

    return [
        indicator
        for indicator in indicators
        if indicator in text.lower()
    ]


def detect_parameter_patterns(
    text: str
) -> int:

    patterns = [
        "length",
        "period",
        "window",
        "lookback",
        "threshold",
        "factor",
        "multiplier",
        "sensitivity",
        "fast",
        "slow",
        "signal",
        "timeframe",
        "periyot",
        "periyod",
        "eşik",
        "katsayı",
        "çarpan",
        "pencere",
        "uzunluk",
    ]

    return count_matches(
        text,
        patterns
    )


def detect_signal_language(
    text: str
) -> int:

    signal_terms = [
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
        "alım",
        "satım",
        "alış",
        "satış",
        "sinyal",
        "giriş",
        "çıkış",
        "yukarı",
        "aşağı",
    ]

    return count_matches(
        text,
        signal_terms
    )


def detect_formula_language(
    text: str
) -> int:

    terms = [
        "=",
        "formula",
        "calculation",
        "calculate",
        "equation",
        "formül",
        "hesaplama",
        "hesaplanır",
        "matematiksel",
        "ortalama",
        "standard deviation",
        "standart sapma",
        "%",
        "*",
        "/",
    ]

    return count_matches(
        text,
        terms
    )


def detect_implementation_language(
    text: str
) -> int:

    terms = [
        "python",
        "pine script",
        "pinescript",
        "code",
        "kod",
        "script",
        "function",
        "fonksiyon",
        "algorithm",
        "algoritma",
        "api",
        "scanner",
        "tarama",
        "filter",
        "filtre",
        "backtest",
        "backtest",
    ]

    return count_matches(
        text,
        terms
    )


def detect_timeframe_detail(
    text: str
) -> int:

    terms = [
        "1 dakika",
        "5 dakika",
        "15 dakika",
        "30 dakika",
        "1 saat",
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
    ]

    return count_matches(
        text,
        terms
    )


# ============================================================
# CLASSIFIER
# ============================================================

def classify_method(
    row: Dict[str, Any]
) -> Dict[str, Any]:

    name = normalize(
        row.get("canonical_name")
    )

    category = normalize(
        row.get("category")
    ).lower()

    verification_score = safe_float(
        row.get("verification_score")
    )

    reproducibility_score = safe_float(
        row.get("reproducibility_score")
    )

    source_supported = bool_value(
        row.get("source_supported")
    )

    logic_consistent = bool_value(
        row.get("logic_consistent")
    )

    parameters_supported = bool_value(
        row.get("parameters_supported")
    )

    sources = extract_source_snapshot(
        row
    )

    source_text = combine_source_text(
        sources
    )

    text_lower = source_text.lower()

    # --------------------------------------------------------
    # RAW TECHNICAL FEATURES
    # --------------------------------------------------------

    indicators = detect_indicators(
        text_lower
    )

    parameter_hits = detect_parameter_patterns(
        text_lower
    )

    signal_hits = detect_signal_language(
        text_lower
    )

    formula_hits = detect_formula_language(
        source_text
    )

    implementation_hits = detect_implementation_language(
        text_lower
    )

    timeframe_hits = detect_timeframe_detail(
        text_lower
    )

    technical_hits = (
        len(indicators)
        + formula_hits
        + implementation_hits
        + timeframe_hits
    )

    # --------------------------------------------------------
    # DETAIL SCORES
    # --------------------------------------------------------

    technical_detail_score = min(
        100.0,
        technical_hits * 8.0
    )

    parameter_detail_score = min(
        100.0,
        parameter_hits * 12.5
    )

    signal_detail_score = min(
        100.0,
        signal_hits * 10.0
    )

    input_detail_score = min(
        100.0,
        (
            len(indicators) * 15.0
            + implementation_hits * 2.0
        )
    )

    # --------------------------------------------------------
    # IMPLEMENTATION READINESS
    # --------------------------------------------------------

    readiness_components = [
        reproducibility_score,
        verification_score,
        technical_detail_score,
        parameter_detail_score,
        signal_detail_score,
        input_detail_score,
    ]

    implementation_readiness = (
        sum(readiness_components)
        / len(readiness_components)
    )

    # --------------------------------------------------------
    # NEGATIVE EVIDENCE
    # --------------------------------------------------------

    vague_terms = [
        "genel olarak",
        "amaçlar",
        "hedefler",
        "özet",
        "tanıtım",
        "strateji sunar",
        "fırsat sunar",
        "başarılı sonuçlar",
        "yüksek başarı",
        "avantaj sağlar",
        "güçlü sonuçlar",
    ]

    vague_hits = count_matches(
        text_lower,
        vague_terms
    )

    promotional_language = [
        "kesin",
        "garanti",
        "garantili",
        "mükemmel",
        "yüksek kazanç",
        "kazandırır",
        "risksiz",
    ]

    promotional_hits = count_matches(
        text_lower,
        promotional_language
    )

    missing_information = []

    if not indicators:
        missing_information.append(
            "Açık teknik indikatör/girdi tanımı"
        )

    if parameter_hits == 0:
        missing_information.append(
            "Parametre veya pencere bilgisi"
        )

    if signal_hits == 0:
        missing_information.append(
            "Açık giriş/çıkış sinyal koşulu"
        )

    if formula_hits == 0:
        missing_information.append(
            "Açık hesaplama/formül mantığı"
        )

    if timeframe_hits == 0:
        missing_information.append(
            "Net zaman dilimi"
        )

    if implementation_hits == 0:
        missing_information.append(
            "Uygulama/kodlama detayı"
        )

    if logic_consistent is False:
        missing_information.append(
            "Kaynak ile tutarlı açık mantık"
        )

    if parameters_supported is False:
        missing_information.append(
            "Kaynak tarafından desteklenen parametreler"
        )

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    classification = "reference_only"

    reasons = []

    # HARD BLOCK:
    # Kaynak metodun varlığını bile yeterince doğrulamıyorsa
    if source_supported is False:

        classification = "reference_only"

        reasons.append(
            "Kaynak metodun varlığını yeterince desteklemiyor."
        )

    else:

        # COMPUTABLE
        if (
            verification_score >= MIN_VERIFICATION_FOR_COMPUTABLE
            and reproducibility_score >= MIN_COMPUTABLE_REPRODUCIBILITY
            and logic_consistent is not False
            and parameters_supported is not False
            and parameter_hits >= 2
            and signal_hits >= 2
            and len(missing_information) <= 2
        ):

            classification = "computable"

            reasons.append(
                "Teknik detaylar Python/backtest uygulamasına "
                "yetecek seviyeye yakın."
            )

        # SEMI-COMPUTABLE
        elif (
            verification_score >= MIN_VERIFICATION_FOR_SEMI
            and reproducibility_score >= MIN_SEMI_REPRODUCIBILITY
            and (
                technical_hits >= 2
                or parameter_hits >= 1
                or signal_hits >= 1
            )
        ):

            classification = "semi_computable"

            reasons.append(
                "Metodun teknik çekirdeğinin bir kısmı "
                "kaynaklardan çıkarılabiliyor ancak "
                "uygulama için eksik bilgiler var."
            )

        # REFERENCE ONLY
        else:

            classification = "reference_only"

            reasons.append(
                "Kaynaklarda yöntem hakkında tanıtım/özet "
                "seviyesi bilgi var; güvenilir yeniden üretim "
                "için yeterli teknik detay yok."
            )

    # --------------------------------------------------------
    # ADD CONTEXTUAL REASONS
    # --------------------------------------------------------

    if vague_hits >= 2:
        reasons.append(
            "Kaynakta yüksek oranda genel/tanıtımsal dil bulunuyor."
        )

    if promotional_hits >= 2:
        reasons.append(
            "Kaynakta promosyonel/iddialı dil bulundu."
        )

    if parameter_hits >= 2:
        reasons.append(
            f"Parametre göstergeleri bulundu: {parameter_hits}"
        )

    if signal_hits >= 2:
        reasons.append(
            f"Sinyal dili bulundu: {signal_hits}"
        )

    if len(indicators) >= 2:
        reasons.append(
            "Birden fazla teknik gösterge/girdi bulundu: "
            + ", ".join(indicators[:8])
        )

    if implementation_hits >= 2:
        reasons.append(
            "Uygulama/kodlama ile ilişkili teknik ifadeler bulundu."
        )

    # Category sanity check
    if category in IMPORTANT_CATEGORIES:
        reasons.append(
            f"Kategori: {category}"
        )

    return {
        "method_id": row.get("method_id"),
        "canonical_name": name,
        "category": category,

        "classification": classification,

        "verification_score": verification_score,
        "reproducibility_score": reproducibility_score,

        "source_supported": source_supported,
        "logic_consistent": logic_consistent,
        "parameters_supported": parameters_supported,

        "technical_detail_score": technical_detail_score,
        "parameter_detail_score": parameter_detail_score,
        "signal_detail_score": signal_detail_score,
        "input_detail_score": input_detail_score,

        "implementation_readiness": implementation_readiness,

        "missing_information": missing_information,
        "reasoning": reasons,

        "source_snapshot": sources,
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
        INSERT INTO method_reproducibility (
            method_id,
            canonical_name,
            category,
            classification,
            verification_score,
            reproducibility_score,
            source_supported,
            logic_consistent,
            parameters_supported,
            technical_detail_score,
            parameter_detail_score,
            signal_detail_score,
            input_detail_score,
            implementation_readiness,
            missing_information,
            reasoning,
            source_snapshot,
            classified_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(method_id, canonical_name)
        DO UPDATE SET
            category = excluded.category,
            classification = excluded.classification,
            verification_score = excluded.verification_score,
            reproducibility_score = excluded.reproducibility_score,
            source_supported = excluded.source_supported,
            logic_consistent = excluded.logic_consistent,
            parameters_supported = excluded.parameters_supported,
            technical_detail_score = excluded.technical_detail_score,
            parameter_detail_score = excluded.parameter_detail_score,
            signal_detail_score = excluded.signal_detail_score,
            input_detail_score = excluded.input_detail_score,
            implementation_readiness = excluded.implementation_readiness,
            missing_information = excluded.missing_information,
            reasoning = excluded.reasoning,
            source_snapshot = excluded.source_snapshot,
            classified_at = excluded.classified_at
        """,
        (
            result["method_id"],
            result["canonical_name"],
            result["category"],
            result["classification"],
            result["verification_score"],
            result["reproducibility_score"],
            (
                None
                if result["source_supported"] is None
                else int(result["source_supported"])
            ),
            (
                None
                if result["logic_consistent"] is None
                else int(result["logic_consistent"])
            ),
            (
                None
                if result["parameters_supported"] is None
                else int(result["parameters_supported"])
            ),
            result["technical_detail_score"],
            result["parameter_detail_score"],
            result["signal_detail_score"],
            result["input_detail_score"],
            result["implementation_readiness"],
            json.dumps(
                result["missing_information"],
                ensure_ascii=False
            ),
            json.dumps(
                result["reasoning"],
                ensure_ascii=False
            ),
            json.dumps(
                result["source_snapshot"],
                ensure_ascii=False
            ),
            datetime.now(
                timezone.utc
            ).isoformat(),
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

    print(
        f"  • {result['canonical_name']}"
    )

    print(
        f"    [{result['category']}] "
        f"→ {result['classification']}"
    )

    print(
        f"    Verification: "
        f"{result['verification_score']:.1f}/100 | "
        f"Reproducibility: "
        f"{result['reproducibility_score']:.1f}/100 | "
        f"Readiness: "
        f"{result['implementation_readiness']:.1f}/100"
    )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    counts = {
        "computable": 0,
        "semi_computable": 0,
        "reference_only": 0,
    }

    for result in results:

        classification = result[
            "classification"
        ]

        if classification in counts:
            counts[classification] += 1

    print()
    print("=========================================")
    print("🧪 REPRODUCIBILITY CLASSIFIER SONUCU")
    print("=========================================")
    print(
        f"Toplam AI doğrulanmış method: "
        f"{len(results)}"
    )

    print()
    print("SINIFLAR")
    print("-----------------------------------------")

    print(
        f"Computable:       "
        f"{counts['computable']}"
    )

    print(
        f"Semi-computable:  "
        f"{counts['semi_computable']}"
    )

    print(
        f"Reference-only:   "
        f"{counts['reference_only']}"
    )

    readiness_values = [
        result["implementation_readiness"]
        for result in results
    ]

    if readiness_values:

        average = (
            sum(readiness_values)
            / len(readiness_values)
        )

        print()
        print(
            f"Ortalama implementation readiness: "
            f"{average:.1f}/100"
        )

    print()
    print("=========================================")


# ============================================================
# IMPORTANT METHOD REPORT
# ============================================================

def print_computable_methods(
    results: List[Dict[str, Any]]
) -> None:

    computable = [
        result
        for result in results
        if result["classification"]
        == "computable"
    ]

    semi = [
        result
        for result in results
        if result["classification"]
        == "semi_computable"
    ]

    print()
    print("🟢 COMPUTABLE")
    print("-----------------------------------------")

    if not computable:
        print("Henüz computable method yok.")
    else:
        for result in computable:
            print(
                f"  • {result['canonical_name']} "
                f"({result['implementation_readiness']:.1f}/100)"
            )

    print()
    print("🟡 SEMI-COMPUTABLE")
    print("-----------------------------------------")

    if not semi:
        print("Henüz semi-computable method yok.")
    else:
        for result in semi:
            print(
                f"  • {result['canonical_name']} "
                f"({result['implementation_readiness']:.1f}/100)"
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("🧪 FIN[SYS] REPRODUCIBILITY CLASSIFIER")
    print("=========================================")
    print(
        "API kullanımı: 0"
    )
    print()

    ensure_table()

    validations = load_ai_validations()

    print(
        f"AI doğrulama kaydı: "
        f"{len(validations)}"
    )

    if not validations:

        print(
            "❌ AI doğrulama kaydı bulunamadı."
        )

        print(
            "Önce:"
        )

        print(
            "python agents/method_ai_verifier.py"
        )

        return

    results = []

    for row in validations:

        result = classify_method(
            row
        )

        save_result(
            result
        )

        results.append(
            result
        )

    # Sonuçları hazırla
    results.sort(
        key=lambda x: (
            {
                "computable": 3,
                "semi_computable": 2,
                "reference_only": 1,
            }.get(
                x["classification"],
                0
            ),
            x["implementation_readiness"],
        ),
        reverse=True
    )

    print()

    for result in results:

        print_method(
            result
        )

    print_summary(
        results
    )

    print_computable_methods(
        results
    )

    print()
    print(
        "✅ Reproducibility Classifier tamamlandı."
    )

    print(
        "Sonraki aşama:"
    )

    print(
        "Computable methodlar için "
        "Strategy Lab adaptörü oluşturulacak."
    )


if __name__ == "__main__":
    main()
