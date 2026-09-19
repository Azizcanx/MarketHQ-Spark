import os
import sys
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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

MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
)

BATCH_SIZE = int(
    os.getenv(
        "METHOD_SPEC_BATCH_SIZE",
        "4"
    )
)

MAX_SOURCE_CHARS = int(
    os.getenv(
        "METHOD_SPEC_MAX_SOURCE_CHARS",
        "14000"
    )
)


# ============================================================
# OPENAI CLIENT
# ============================================================

client = None


def get_openai_client():
    global client

    if client is not None:
        return client

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(
        os.path.join(
            PROJECT_ROOT,
            ".env"
        )
    )

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY bulunamadı."
        )

    client = OpenAI(
        api_key=api_key
    )

    return client


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(
        DB_PATH
    )

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
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,)
    ).fetchone()

    return row is not None


def ensure_table() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_technical_specs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,
            category TEXT,

            spec_status TEXT,

            inputs TEXT,
            indicators TEXT,
            parameters TEXT,
            calculations TEXT,

            signal_rules TEXT,
            entry_rules TEXT,
            exit_rules TEXT,

            timeframe_rules TEXT,
            filters TEXT,
            confirmation_rules TEXT,
            risk_rules TEXT,

            visual_elements TEXT,
            scanning_rules TEXT,
            implementation_notes TEXT,

            supported_claims TEXT,
            inferred_claims TEXT,
            unknown_items TEXT,

            source_titles TEXT,
            source_urls TEXT,

            extraction_confidence REAL,

            raw_ai_response TEXT,

            model TEXT,
            extracted_at TEXT,

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

    return str(
        value
    ).strip()


def safe_float(
    value: Any,
    default: float = 0.0
) -> float:

    try:
        return float(
            value
        )

    except Exception:
        return default


def parse_json(
    value: Any
) -> Any:

    if value is None:
        return None

    if isinstance(
        value,
        (dict, list)
    ):
        return value

    text = normalize(
        value
    )

    if not text:
        return None

    try:
        return json.loads(
            text
        )

    except Exception:
        return None


def to_json(
    value: Any
) -> str:

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# LOAD SEMI-COMPUTABLE METHODS
# ============================================================

def load_methods() -> List[Dict[str, Any]]:

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
        row.get(
            "source_snapshot"
        )
    )

    if not parsed:
        return []

    if isinstance(
        parsed,
        dict
    ):
        parsed = [parsed]

    if not isinstance(
        parsed,
        list
    ):
        return []

    result = []

    for source in parsed:

        if not isinstance(
            source,
            dict
        ):
            continue

        result.append(
            {
                "title": normalize(
                    source.get(
                        "title"
                    )
                ),
                "url": normalize(
                    source.get(
                        "url"
                    )
                ),
                "source_type": normalize(
                    source.get(
                        "source_type"
                    )
                ),
                "text": normalize(
                    source.get(
                        "text"
                    )
                )[:MAX_SOURCE_CHARS],
            }
        )

    return result


def build_source_payload(
    method: Dict[str, Any]
) -> Dict[str, Any]:

    sources = extract_sources(
        method
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
        "verification_score": safe_float(
            method.get(
                "verification_score"
            )
        ),
        "reproducibility_score": safe_float(
            method.get(
                "reproducibility_score"
            )
        ),
        "implementation_readiness": safe_float(
            method.get(
                "implementation_readiness"
            )
        ),
        "sources": sources,
    }


# ============================================================
# PROMPT
# ============================================================

def build_prompt(
    batch: List[Dict[str, Any]]
) -> str:

    serialized = json.dumps(
        batch,
        ensure_ascii=False,
        indent=2
    )

    return f"""
Sen MarketHQ içindeki FIN[SYS] metodoloji teknik şartname
çıkarma ajanısın.

Aşağıdaki metodların KAMUYA AÇIK kaynak metinlerini incele.

AMAÇ:
Bir metodun kaynaklarda bulunan teknik yapısını, Python/backtest
uygulamasına geçmeden önce yapılandırılmış bir teknik şartnameye
dönüştürmek.

ÇOK ÖNEMLİ KURALLAR:

1. Kaynakta yazmayan hiçbir parametreyi UYDURMA.

2. Kaynakta olmayan bir formülü, eşik değerini veya sinyal koşulunu
   tahmin ederek tamamlama.

3. "Bilinmiyor", "kaynakta bulunmuyor" veya "UNKNOWN" gerekiyorsa
   bunu açıkça belirt.

4. Bir kaynak sadece metodun adını veya genel amacını söylüyorsa
   bunu teknik implementasyon detayı olarak kabul etme.

5. Kaynakta açıkça desteklenen bilgiler "supported_claims" içine
   alınmalı.

6. Kaynaktan mantıksal olarak çıkarılmış ama doğrudan yazılmamış
   bilgiler "inferred_claims" içine alınmalı.

7. Test edilebilmesi için bilinmesi gereken fakat kaynakta olmayan
   bilgiler "unknown_items" içine alınmalı.

8. FIN[SYS] metodunun başarılı olduğu varsayımını yapma.
   Bu adım yalnızca teknik şartname çıkarımıdır.

9. Yatırım tavsiyesi verme.

10. Özel/ücretli içeriklere erişim sağlamaya veya erişim kontrolünü
    aşmaya çalışma.

HER METHOD İÇİN ŞUNLARI ÇIKAR:

inputs:
  Metodun kullandığı fiyat, hacim, indikatör veya diğer girdiler.

indicators:
  Kullanılan indikatörler.

parameters:
  Açıkça belirtilmiş parametreleri yaz.
  Örneğin RSI=14 gibi.
  Parametre değeri yoksa:
  {{
    "name": "...",
    "value": "UNKNOWN",
    "supported": false
  }}

calculations:
  Kaynakta açıkça anlatılan hesaplamalar.

signal_rules:
  Sinyal üretim koşulları.
  Açık değilse UNKNOWN.

entry_rules:
  Giriş koşulları.
  Kaynakta yoksa UNKNOWN.

exit_rules:
  Çıkış koşulları.
  Kaynakta yoksa UNKNOWN.

timeframe_rules:
  Zaman dilimleri ve çoklu zaman koşulları.

filters:
  Filtreler.

confirmation_rules:
  Doğrulama / teyit kuralları.

risk_rules:
  Kaynakta bulunan risk yönetimi veya stop koşulları.

visual_elements:
  Grafik üzerinde görülen / tarif edilen çizgi,
  bant, kanal, renk, ok, işaret vb.

scanning_rules:
  Tarama/filtreleme mantığı.

implementation_notes:
  Python'da uygulanabilmesi için kaynakta açık olan teknik notlar.

supported_claims:
  Doğrudan kaynak tarafından desteklenen iddialar.

inferred_claims:
  Kaynaktan çıkarılabilecek ama doğrudan yazılmayan noktalar.

unknown_items:
  Uygulama için gerekli fakat kaynakta bulunmayan bilgiler.

extraction_confidence:
  0-100 arasında.
  Kaynak teknik olarak ne kadar açık?

spec_status:
  Şunlardan biri:
  - detailed
  - partial
  - descriptive_only

"descriptive_only" teknik ayrıntı çok azsa kullanılmalı.

SADECE GEÇERLİ JSON DÖNDÜR.

Format:

[
  {{
    "item_index": 1,
    "method_id": 123,
    "canonical_name": "...",
    "category": "algorithm",
    "spec_status": "partial",

    "inputs": [],
    "indicators": [],

    "parameters": [
      {{
        "name": "...",
        "value": "...",
        "unit": "...",
        "supported": true
      }}
    ],

    "calculations": [],
    "signal_rules": [],
    "entry_rules": [],
    "exit_rules": [],
    "timeframe_rules": [],
    "filters": [],
    "confirmation_rules": [],
    "risk_rules": [],
    "visual_elements": [],
    "scanning_rules": [],
    "implementation_notes": [],

    "supported_claims": [],
    "inferred_claims": [],
    "unknown_items": [],

    "extraction_confidence": 0
  }}
]

METHODS:

{serialized}
"""


# ============================================================
# AI CALL
# ============================================================

def strip_code_fences(
    text: str
) -> str:

    text = text.strip()

    if text.startswith(
        "```"
    ):

        lines = text.splitlines()

        if lines and lines[0].startswith(
            "```"
        ):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(
            lines
        )

        if text.startswith(
            "json"
        ):
            text = text[4:].lstrip()

    return text.strip()


def call_ai(
    batch: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    ai = get_openai_client()

    prompt = build_prompt(
        batch
    )

    response = ai.responses.create(
        model=MODEL,
        input=prompt
    )

    raw = response.output_text.strip()

    cleaned = strip_code_fences(
        raw
    )

    try:
        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            "AI JSON cevabı parse edilemedi.\n"
            f"Hata: {exc}\n"
            f"Çıktı:\n{raw[:6000]}"
        )

    if isinstance(
        parsed,
        dict
    ):

        if "results" in parsed:
            parsed = parsed[
                "results"
            ]

        else:
            parsed = [parsed]

    if not isinstance(
        parsed,
        list
    ):

        raise RuntimeError(
            "AI cevabı liste formatında değil."
        )

    return parsed


# ============================================================
# VALIDATION / NORMALIZATION
# ============================================================

def ensure_list(
    value: Any
) -> List[Any]:

    if value is None:
        return []

    if isinstance(
        value,
        list
    ):
        return value

    return [value]


def normalize_parameter_list(
    parameters: Any
) -> List[Dict[str, Any]]:

    parameters = ensure_list(
        parameters
    )

    result = []

    for parameter in parameters:

        if isinstance(
            parameter,
            dict
        ):

            result.append(
                {
                    "name": normalize(
                        parameter.get(
                            "name"
                        )
                    ),
                    "value": normalize(
                        parameter.get(
                            "value"
                        )
                    ),
                    "unit": normalize(
                        parameter.get(
                            "unit"
                        )
                    ),
                    "supported": bool(
                        parameter.get(
                            "supported",
                            False
                        )
                    )
                }
            )

        else:

            result.append(
                {
                    "name": normalize(
                        parameter
                    ),
                    "value": "UNKNOWN",
                    "unit": "",
                    "supported": False
                }
            )

    return result


def normalize_result(
    result: Dict[str, Any],
    method: Dict[str, Any]
) -> Dict[str, Any]:

    fields = [
        "inputs",
        "indicators",
        "calculations",
        "signal_rules",
        "entry_rules",
        "exit_rules",
        "timeframe_rules",
        "filters",
        "confirmation_rules",
        "risk_rules",
        "visual_elements",
        "scanning_rules",
        "implementation_notes",
        "supported_claims",
        "inferred_claims",
        "unknown_items",
    ]

    normalized = {}

    for field in fields:

        normalized[field] = ensure_list(
            result.get(
                field,
                []
            )
        )

    normalized["parameters"] = (
        normalize_parameter_list(
            result.get(
                "parameters",
                []
            )
        )
    )

    spec_status = normalize(
        result.get(
            "spec_status",
            "partial"
        )
    ).lower()

    allowed_statuses = {
        "detailed",
        "partial",
        "descriptive_only"
    }

    if spec_status not in allowed_statuses:
        spec_status = "partial"

    confidence = max(
        0.0,
        min(
            100.0,
            safe_float(
                result.get(
                    "extraction_confidence",
                    0
                )
            )
        )
    )

    canonical_name = normalize(
        result.get(
            "canonical_name"
        )
    )

    if not canonical_name:
        canonical_name = normalize(
            method.get(
                "canonical_name"
            )
        )

    normalized.update(
        {
            "method_id": (
                result.get(
                    "method_id"
                )
                if result.get(
                    "method_id"
                ) is not None
                else method.get(
                    "method_id"
                )
            ),
            "canonical_name": canonical_name,
            "category": normalize(
                result.get(
                    "category"
                )
                or method.get(
                    "category"
                )
            ),
            "spec_status": spec_status,
            "extraction_confidence": confidence,
        }
    )

    return normalized


# ============================================================
# SAVE
# ============================================================

def save_spec(
    spec: Dict[str, Any],
    method: Dict[str, Any],
    raw_response: Dict[str, Any]
) -> None:

    sources = extract_sources(
        method
    )

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

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO method_technical_specs (
            method_id,
            canonical_name,
            category,
            spec_status,

            inputs,
            indicators,
            parameters,
            calculations,

            signal_rules,
            entry_rules,
            exit_rules,

            timeframe_rules,
            filters,
            confirmation_rules,
            risk_rules,

            visual_elements,
            scanning_rules,
            implementation_notes,

            supported_claims,
            inferred_claims,
            unknown_items,

            source_titles,
            source_urls,

            extraction_confidence,

            raw_ai_response,

            model,
            extracted_at
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?,
            ?,
            ?, ?
        )

        ON CONFLICT(
            method_id,
            canonical_name
        )
        DO UPDATE SET

            category = excluded.category,
            spec_status = excluded.spec_status,

            inputs = excluded.inputs,
            indicators = excluded.indicators,
            parameters = excluded.parameters,
            calculations = excluded.calculations,

            signal_rules = excluded.signal_rules,
            entry_rules = excluded.entry_rules,
            exit_rules = excluded.exit_rules,

            timeframe_rules = excluded.timeframe_rules,
            filters = excluded.filters,
            confirmation_rules = excluded.confirmation_rules,
            risk_rules = excluded.risk_rules,

            visual_elements = excluded.visual_elements,
            scanning_rules = excluded.scanning_rules,
            implementation_notes = excluded.implementation_notes,

            supported_claims = excluded.supported_claims,
            inferred_claims = excluded.inferred_claims,
            unknown_items = excluded.unknown_items,

            source_titles = excluded.source_titles,
            source_urls = excluded.source_urls,

            extraction_confidence = excluded.extraction_confidence,

            raw_ai_response = excluded.raw_ai_response,

            model = excluded.model,
            extracted_at = excluded.extracted_at
        """,
        (
            spec["method_id"],
            spec["canonical_name"],
            spec["category"],
            spec["spec_status"],

            to_json(
                spec["inputs"]
            ),

            to_json(
                spec["indicators"]
            ),

            to_json(
                spec["parameters"]
            ),

            to_json(
                spec["calculations"]
            ),

            to_json(
                spec["signal_rules"]
            ),

            to_json(
                spec["entry_rules"]
            ),

            to_json(
                spec["exit_rules"]
            ),

            to_json(
                spec["timeframe_rules"]
            ),

            to_json(
                spec["filters"]
            ),

            to_json(
                spec["confirmation_rules"]
            ),

            to_json(
                spec["risk_rules"]
            ),

            to_json(
                spec["visual_elements"]
            ),

            to_json(
                spec["scanning_rules"]
            ),

            to_json(
                spec["implementation_notes"]
            ),

            to_json(
                spec["supported_claims"]
            ),

            to_json(
                spec["inferred_claims"]
            ),

            to_json(
                spec["unknown_items"]
            ),

            to_json(
                source_titles
            ),

            to_json(
                source_urls
            ),

            spec["extraction_confidence"],

            to_json(
                raw_response
            ),

            MODEL,

            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# DISPLAY
# ============================================================

def print_spec(
    spec: Dict[str, Any]
) -> None:

    print()
    print(
        f"• {spec['canonical_name']}"
    )

    print(
        f"  Status: {spec['spec_status']}"
    )

    print(
        f"  Confidence: "
        f"{spec['extraction_confidence']:.1f}/100"
    )

    print(
        f"  Inputs: "
        f"{len(spec['inputs'])}"
    )

    print(
        f"  Indicators: "
        f"{len(spec['indicators'])}"
    )

    known_parameters = [
        parameter
        for parameter in spec["parameters"]
        if parameter.get(
            "supported"
        )
        and parameter.get(
            "value"
        )
        and parameter.get(
            "value"
        ).upper() != "UNKNOWN"
    ]

    unknown_parameters = [
        parameter
        for parameter in spec["parameters"]
        if (
            not parameter.get(
                "supported"
            )
            or parameter.get(
                "value",
                ""
            ).upper()
            == "UNKNOWN"
        )
    ]

    print(
        f"  Known parameters: "
        f"{len(known_parameters)}"
    )

    print(
        f"  Unknown parameters: "
        f"{len(unknown_parameters)}"
    )

    print(
        f"  Signal rules: "
        f"{len(spec['signal_rules'])}"
    )

    print(
        f"  Entry rules: "
        f"{len(spec['entry_rules'])}"
    )

    print(
        f"  Exit rules: "
        f"{len(spec['exit_rules'])}"
    )

    print(
        f"  Timeframe rules: "
        f"{len(spec['timeframe_rules'])}"
    )

    print(
        f"  Filters: "
        f"{len(spec['filters'])}"
    )

    print(
        f"  Unknown items: "
        f"{len(spec['unknown_items'])}"
    )

    if spec["unknown_items"]:

        print(
            "  Eksik/UNKNOWN:"
        )

        for item in spec[
            "unknown_items"
        ][:8]:

            print(
                f"    - {item}"
            )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    status_counts = {
        "detailed": 0,
        "partial": 0,
        "descriptive_only": 0,
    }

    confidence_values = []

    unknown_counts = []

    for result in results:

        status = result[
            "spec_status"
        ]

        if status in status_counts:
            status_counts[
                status
            ] += 1

        confidence_values.append(
            result[
                "extraction_confidence"
            ]
        )

        unknown_counts.append(
            len(
                result[
                    "unknown_items"
                ]
            )
        )

    print()
    print("=========================================")
    print("📐 METHOD TECHNICAL SPEC EXTRACTOR")
    print("=========================================")

    print(
        f"Toplam method: "
        f"{len(results)}"
    )

    print()
    print("SPEC STATUS")
    print("-----------------------------------------")

    print(
        f"Detailed:         "
        f"{status_counts['detailed']}"
    )

    print(
        f"Partial:          "
        f"{status_counts['partial']}"
    )

    print(
        f"Descriptive only: "
        f"{status_counts['descriptive_only']}"
    )

    if confidence_values:

        print()
        print(
            "Ortalama extraction confidence: "
            f"{sum(confidence_values) / len(confidence_values):.1f}/100"
        )

    if unknown_counts:

        print(
            "Ortalama unknown item: "
            f"{sum(unknown_counts) / len(unknown_counts):.1f}"
        )

    print()
    print(
        "========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("📐 FIN[SYS] METHOD SPEC EXTRACTOR")
    print("=========================================")
    print(
        f"Model: {MODEL}"
    )
    print(
        f"Batch size: {BATCH_SIZE}"
    )
    print()

    ensure_table()

    methods = load_methods()

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
            "Önce:"
        )

        print(
            "python agents/method_reproducibility_classifier.py"
        )

        return

    payloads = []

    for method in methods:

        payloads.append(
            build_source_payload(
                method
            )
        )

    all_results = []

    total_batches = (
        len(payloads)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    for start in range(
        0,
        len(payloads),
        BATCH_SIZE
    ):

        batch = payloads[
            start:
            start + BATCH_SIZE
        ]

        batch_number = (
            start // BATCH_SIZE
        ) + 1

        print()
        print(
            f"🔎 Batch "
            f"{batch_number}/"
            f"{total_batches} "
            f"({len(batch)} method)"
        )

        try:

            ai_results = call_ai(
                batch
            )

        except Exception as exc:

            print(
                f"❌ Batch başarısız: "
                f"{exc}"
            )

            continue

        saved_count = 0

        for ai_result in ai_results:

            method_id = ai_result.get(
                "method_id"
            )

            canonical_name = normalize(
                ai_result.get(
                    "canonical_name"
                )
            )

            matched_method = None

            # Önce method ID
            if method_id is not None:

                for method in methods:

                    if normalize(
                        method.get(
                            "method_id"
                        )
                    ) == normalize(
                        method_id
                    ):

                        matched_method = method
                        break

            # Sonra isim
            if (
                matched_method is None
                and canonical_name
            ):

                for method in methods:

                    if (
                        normalize(
                            method.get(
                                "canonical_name"
                            )
                        ).lower()
                        ==
                        canonical_name.lower()
                    ):

                        matched_method = method
                        break

            if matched_method is None:

                print(
                    "⚠️ AI sonucu method "
                    "ile eşleştirilemedi:"
                    f" {canonical_name}"
                )

                continue

            spec = normalize_result(
                ai_result,
                matched_method
            )

            save_spec(
                spec,
                matched_method,
                ai_result
            )

            all_results.append(
                spec
            )

            saved_count += 1

            print_spec(
                spec
            )

        print(
            f"✅ Batch tamamlandı: "
            f"{saved_count}/{len(batch)}"
        )

    print_summary(
        all_results
    )

    print()
    print(
        "✅ Method Spec Extractor tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Teknik şartnameler arasından gerçekten "
        "uygulanabilir kuralları seçip Method Lab'e "
        "aktaracağız."
    )


if __name__ == "__main__":
    main()
