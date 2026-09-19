import os
import sys
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# PATH / ENV
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DB_PATH = os.path.join(PROJECT_ROOT, "market_hq.db")

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

# API maliyetini kontrol etmek için sınırlar
MAX_METHODS = int(os.getenv("AI_VERIFIER_MAX_METHODS", "40"))
BATCH_SIZE = int(os.getenv("AI_VERIFIER_BATCH_SIZE", "8"))

# Kaynak başına maksimum karakter
MAX_SOURCE_CHARS = int(os.getenv("AI_VERIFIER_MAX_SOURCE_CHARS", "12000"))

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

client: Optional[OpenAI] = None


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def get_table_columns(
    conn: sqlite3.Connection,
    table_name: str
) -> List[str]:
    if not table_exists(conn, table_name):
        return []

    rows = conn.execute(
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()

    return [row["name"] for row in rows]


def pick_column(
    columns: List[str],
    candidates: List[str]
) -> Optional[str]:
    lowered = {col.lower(): col for col in columns}

    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    return None


def ensure_validation_table() -> None:
    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_ai_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,
            category TEXT,

            verification_status TEXT,
            verification_score REAL,

            source_supported INTEGER,
            logic_consistent INTEGER,
            parameters_supported INTEGER,
            reproducibility_score REAL,

            claim_risk TEXT,

            reasoning TEXT,
            missing_information TEXT,
            supported_claims TEXT,
            unsupported_claims TEXT,

            source_snapshot TEXT,
            raw_response TEXT,

            model TEXT,
            validated_at TEXT,

            UNIQUE(method_id, canonical_name)
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# GENERIC DB READING
# ============================================================

def get_all_rows(
    conn: sqlite3.Connection,
    table_name: str
) -> List[sqlite3.Row]:
    if not table_exists(conn, table_name):
        return []

    return conn.execute(
        f'SELECT * FROM "{table_name}"'
    ).fetchall()


def normalize(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def parse_json(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    text = str(value).strip()

    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        return None


# ============================================================
# METHOD REGISTRY
# ============================================================

def load_methods() -> List[Dict[str, Any]]:
    conn = get_connection()

    if not table_exists(conn, "method_registry"):
        conn.close()
        raise RuntimeError(
            "method_registry tablosu bulunamadı. "
            "Önce method_registry.py çalıştır."
        )

    columns = get_table_columns(conn, "method_registry")
    rows = get_all_rows(conn, "method_registry")

    id_col = pick_column(
        columns,
        ["method_id", "id", "registry_id"]
    )

    name_col = pick_column(
        columns,
        [
            "canonical_name",
            "method_name",
            "name",
            "title"
        ]
    )

    category_col = pick_column(
        columns,
        [
            "category",
            "method_type",
            "type"
        ]
    )

    score_col = pick_column(
        columns,
        [
            "score",
            "validator_score",
            "validation_score"
        ]
    )

    source_count_col = pick_column(
        columns,
        [
            "source_count",
            "sources",
            "source_total"
        ]
    )

    methods = []

    for row in rows:
        name = normalize(row[name_col]) if name_col else ""
        if not name:
            continue

        method_id = row[id_col] if id_col else None

        category = (
            normalize(row[category_col])
            if category_col
            else "other"
        )

        score = 0.0

        if score_col:
            try:
                score = float(row[score_col] or 0)
            except Exception:
                score = 0.0

        source_count = 0

        if source_count_col:
            try:
                source_count = int(row[source_count_col] or 0)
            except Exception:
                source_count = 0

        methods.append(
            {
                "method_id": method_id,
                "canonical_name": name,
                "category": category,
                "validator_score": score,
                "source_count": source_count,
                "raw": dict(row),
            }
        )

    conn.close()

    return methods


# ============================================================
# METHOD VALIDATOR RESULT DISCOVERY
# ============================================================

def find_validation_table(
    conn: sqlite3.Connection
) -> Optional[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name
        """
    ).fetchall()

    candidates = []

    for row in rows:
        name = row["name"].lower()

        if "valid" in name:
            candidates.append(row["name"])

    # Öncelik sırası
    preferred = [
        "method_validation",
        "method_validator",
        "validator_results",
        "method_ai_validation",
    ]

    for table in preferred:
        if table_exists(conn, table):
            return table

    for table in candidates:
        if table == "method_ai_validation":
            continue

        return table

    return None


def load_validator_priority() -> Dict[str, Dict[str, Any]]:
    """
    Method Validator V2 bir tablo oluşturduysa onu kullanır.
    Yoksa boş döner ve registry bilgileri kullanılır.
    """

    conn = get_connection()

    table_name = find_validation_table(conn)

    if not table_name:
        conn.close()
        return {}

    columns = get_table_columns(conn, table_name)

    name_col = pick_column(
        columns,
        [
            "canonical_name",
            "method_name",
            "name",
            "title"
        ]
    )

    status_col = pick_column(
        columns,
        [
            "status",
            "validation_status",
            "result"
        ]
    )

    score_col = pick_column(
        columns,
        [
            "score",
            "validator_score",
            "validation_score"
        ]
    )

    risk_col = pick_column(
        columns,
        [
            "risk",
            "hallucination_risk",
            "risk_score"
        ]
    )

    if not name_col:
        conn.close()
        return {}

    rows = get_all_rows(conn, table_name)

    result = {}

    for row in rows:
        name = normalize(row[name_col])

        if not name:
            continue

        status = (
            normalize(row[status_col])
            if status_col
            else ""
        )

        score = 0.0

        if score_col:
            try:
                score = float(row[score_col] or 0)
            except Exception:
                pass

        risk = 0.0

        if risk_col:
            try:
                risk = float(row[risk_col] or 0)
            except Exception:
                pass

        result[name.lower()] = {
            "status": status.lower(),
            "score": score,
            "risk": risk,
        }

    conn.close()

    return result


# ============================================================
# SOURCE KNOWLEDGE
# ============================================================

def find_source_link_table(
    conn: sqlite3.Connection
) -> Optional[str]:
    possible = [
        "method_registry_items",
        "method_registry_sources",
        "method_sources",
    ]

    for table in possible:
        if table_exists(conn, table):
            return table

    return None


def load_knowledge_rows(
    conn: sqlite3.Connection
) -> List[sqlite3.Row]:
    if not table_exists(conn, "knowledge_items"):
        return []

    return get_all_rows(conn, "knowledge_items")


def extract_source_text(row: sqlite3.Row) -> str:
    data = dict(row)

    preferred = [
        "content",
        "text",
        "source_text",
        "body",
        "description",
        "summary",
    ]

    chunks = []

    for key in preferred:
        if key in data and data[key] is not None:
            value = normalize(data[key])

            if value:
                chunks.append(value)

    if not chunks:
        for key, value in data.items():
            if value is None:
                continue

            text = normalize(value)

            if len(text) > 80:
                chunks.append(f"{key}: {text}")

    combined = "\n\n".join(chunks)

    return combined[:MAX_SOURCE_CHARS]


def extract_source_metadata(
    row: sqlite3.Row
) -> Dict[str, Any]:
    data = dict(row)

    title = ""

    for key in [
        "title",
        "name",
        "source_title",
        "canonical_name",
    ]:
        if key in data and data[key]:
            title = normalize(data[key])
            break

    url = ""

    for key in [
        "url",
        "source_url",
        "page_url",
        "youtube_url",
    ]:
        if key in data and data[key]:
            url = normalize(data[key])
            break

    source_type = ""

    for key in [
        "source_type",
        "type",
        "content_type",
    ]:
        if key in data and data[key]:
            source_type = normalize(data[key])
            break

    return {
        "title": title,
        "url": url,
        "source_type": source_type,
    }


def find_links_for_method(
    method: Dict[str, Any],
    link_rows: List[sqlite3.Row],
    knowledge_rows: List[sqlite3.Row],
) -> List[sqlite3.Row]:

    method_id = method["method_id"]
    method_name = method["canonical_name"].strip().lower()

    if not link_rows:
        return []

    # Link tablosu kolonlarını keşfet
    sample = dict(link_rows[0])
    columns = list(sample.keys())

    method_id_col = pick_column(
        columns,
        [
            "method_id",
            "registry_id",
            "method_registry_id",
        ]
    )

    knowledge_id_col = pick_column(
        columns,
        [
            "knowledge_id",
            "knowledge_item_id",
            "item_id",
        ]
    )

    if not method_id_col or not knowledge_id_col:
        return []

    knowledge_by_id = {}

    # knowledge_items ID kolonunu bul
    if knowledge_rows:
        knowledge_columns = list(dict(knowledge_rows[0]).keys())

        knowledge_id_field = pick_column(
            knowledge_columns,
            [
                "knowledge_id",
                "id",
                "item_id",
            ]
        )

        if knowledge_id_field:
            for row in knowledge_rows:
                knowledge_by_id[
                    str(row[knowledge_id_field])
                ] = row

    result = []

    for link in link_rows:
        link_method_id = normalize(link[method_id_col])

        if method_id is not None:
            if link_method_id != normalize(method_id):
                continue
        else:
            continue

        knowledge_id = normalize(
            link[knowledge_id_col]
        )

        if knowledge_id in knowledge_by_id:
            result.append(
                knowledge_by_id[knowledge_id]
            )

    return result


def fallback_find_sources(
    method: Dict[str, Any],
    knowledge_rows: List[sqlite3.Row]
) -> List[sqlite3.Row]:
    """
    Registry-link tablosu yoksa metod adı üzerinden
    güvenli bir fallback araması.
    """

    target = method["canonical_name"].strip().lower()

    if not target:
        return []

    results = []

    for row in knowledge_rows:
        metadata = extract_source_metadata(row)

        title = metadata["title"].lower()

        source_text = extract_source_text(row).lower()

        if target in title or target in source_text:
            results.append(row)

    return results[:5]


def collect_sources_for_methods(
    methods: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:

    conn = get_connection()

    knowledge_rows = load_knowledge_rows(conn)

    link_table = find_source_link_table(conn)

    link_rows = (
        get_all_rows(conn, link_table)
        if link_table
        else []
    )

    result = {}

    for method in methods:
        sources = find_links_for_method(
            method,
            link_rows,
            knowledge_rows,
        )

        if not sources:
            sources = fallback_find_sources(
                method,
                knowledge_rows,
            )

        source_payload = []

        for source in sources:
            metadata = extract_source_metadata(source)
            text = extract_source_text(source)

            source_payload.append(
                {
                    "title": metadata["title"],
                    "url": metadata["url"],
                    "source_type": metadata["source_type"],
                    "text": text,
                }
            )

        result[method["canonical_name"]] = source_payload

    conn.close()

    return result


# ============================================================
# PRIORITY
# ============================================================

def calculate_priority(
    method: Dict[str, Any],
    validator_data: Dict[str, Dict[str, Any]]
) -> Tuple[int, List[str]]:

    name = method["canonical_name"]
    key = name.lower()

    category = method["category"].lower()
    score = method["validator_score"]
    source_count = method["source_count"]

    validation = validator_data.get(
        key,
        {}
    )

    validator_status = validation.get(
        "status",
        ""
    )

    validator_score = validation.get(
        "score",
        score
    )

    reasons = []
    priority = 0

    # 1. Verified candidate
    if (
        "verified" in validator_status
        or "candidate" in validator_status
    ):
        priority += 100
        reasons.append(
            "Validator V2: verified candidate"
        )

    # 2. Important methodology
    if category in IMPORTANT_CATEGORIES:
        priority += 45
        reasons.append(
            f"important category: {category}"
        )

    # 3. Strong validator score
    if validator_score >= 85:
        priority += 30
        reasons.append(
            f"yüksek validator skoru: {validator_score:.1f}"
        )
    elif validator_score >= 80:
        priority += 20

    # 4. Multiple sources
    if source_count >= 3:
        priority += 25
        reasons.append(
            f"{source_count} kaynak"
        )
    elif source_count >= 2:
        priority += 15

    # 5. Slight priority for algorithms/systems
    if category in {"algorithm", "system"}:
        priority += 20

    # 6. Riskli kayıtları ikinci doğrulamaya almak için ek puan
    risk = validation.get("risk", 0)

    if risk >= 20:
        priority += 15
        reasons.append(
            f"yüksek validator risk sinyali: {risk}"
        )
    elif risk >= 10:
        priority += 7

    # 7. Kaynağı olmayan method daha düşük
    if source_count == 0:
        priority -= 20

    return priority, reasons


def select_methods_for_verification(
    methods: List[Dict[str, Any]],
    validator_data: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:

    scored = []

    for method in methods:
        priority, reasons = calculate_priority(
            method,
            validator_data
        )

        item = dict(method)
        item["priority"] = priority
        item["priority_reasons"] = reasons

        scored.append(item)

    scored.sort(
        key=lambda item: (
            item["priority"],
            item["validator_score"],
            item["source_count"],
        ),
        reverse=True
    )

    return scored[:MAX_METHODS]


# ============================================================
# OPENAI
# ============================================================

def get_client() -> OpenAI:
    global client

    if client is not None:
        return client

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY bulunamadı. .env dosyasını kontrol et."
        )

    client = OpenAI(api_key=api_key)

    return client


def build_prompt(
    batch: List[Dict[str, Any]],
    source_map: Dict[str, List[Dict[str, Any]]],
) -> str:

    payload = []

    for index, method in enumerate(batch, start=1):

        source_data = source_map.get(
            method["canonical_name"],
            []
        )

        source_texts = []

        for source_index, source in enumerate(
            source_data,
            start=1
        ):
            source_texts.append(
                {
                    "source_index": source_index,
                    "title": source["title"],
                    "url": source["url"],
                    "source_type": source["source_type"],
                    "text": source["text"],
                }
            )

        payload.append(
            {
                "item_index": index,
                "method_id": method["method_id"],
                "canonical_name": method["canonical_name"],
                "category": method["category"],
                "validator_priority": method["priority"],
                "validator_reasons": method["priority_reasons"],
                "sources": source_texts,
            }
        )

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2
    )

    return f"""
Sen MarketHQ içindeki FIN[SYS] metodoloji doğrulama ajanısın.

Görevin, aşağıdaki metodların veritabanında saklanan KAMUYA AÇIK
kaynak metinleri ile ne kadar tutarlı olduğunu değerlendirmek.

ÖNEMLİ:
- Kaynakta olmayan bir bilgiyi varmış gibi kabul etme.
- Kaynak açıkça söylüyorsa "supported" say.
- Kaynaktan mantıksal olarak çıkarılabiliyorsa "inferred" say.
- Kaynakta bulunmuyorsa "unsupported" say.
- Bir metodun adının bulunması tek başına onun mantığının doğrulandığı
  anlamına gelmez.
- FIN[SYS] kaynağının iddialarını otomatik olarak bilimsel gerçek kabul etme.
- İddia ile kaynak desteğini birbirinden ayır.
- Özel/ücretli/içerik erişimlerini aşmaya çalışma.
- Sadece verilen kaynakları kullan.
- Yatırım tavsiyesi üretme.
- "Bu kesin çalışır" gibi sonuçlara varma.

Her metod için değerlendir:

1. source_supported
   Kaynak metodun varlığını gerçekten destekliyor mu?

2. logic_consistent
   Metodun anlatılan mantığı kaynak ile tutarlı mı?

3. parameters_supported
   Parametreler / indikatörler / koşullar kaynakta gerçekten destekleniyor mu?

4. reproducibility_score
   Kaynak sadece tanıtım mı yapıyor, yoksa metodun uygulanmasına yetecek
   kadar teknik detay veriyor mu?
   0-100.

5. claim_risk
   "low", "medium", "high".

6. verification_score
   Genel kaynak doğrulama skoru 0-100.

7. status
   Şunlardan biri:
   - verified
   - partially_verified
   - needs_review
   - unsupported

8. supported_claims
   Kaynak tarafından açıkça desteklenen önemli iddialar.

9. unsupported_claims
   Kaynağın desteklemediği veya doğrulanamayan iddialar.

10. missing_information
    Uygulanabilirlik için eksik kalan bilgiler.

11. reasoning
    Kısa fakat teknik gerekçe.

SADECE geçerli JSON döndür.

Format:

[
  {{
    "item_index": 1,
    "method_id": 123,
    "canonical_name": "Example",
    "source_supported": true,
    "logic_consistent": true,
    "parameters_supported": false,
    "reproducibility_score": 62,
    "claim_risk": "medium",
    "verification_score": 78,
    "status": "partially_verified",
    "supported_claims": [],
    "unsupported_claims": [],
    "missing_information": [],
    "reasoning": "..."
  }}
]

Metodlar:

{serialized}
"""


def strip_code_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines)

        if text.startswith("json"):
            text = text[4:].lstrip()

    return text.strip()


def call_ai(
    batch: List[Dict[str, Any]],
    source_map: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:

    prompt = build_prompt(
        batch,
        source_map
    )

    ai = get_client()

    response = ai.responses.create(
        model=MODEL,
        input=prompt,
    )

    raw = response.output_text.strip()
    cleaned = strip_code_fences(raw)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "AI JSON cevabı parse edilemedi.\n"
            f"Hata: {exc}\n"
            f"AI çıktısı:\n{raw[:5000]}"
        )

    if isinstance(parsed, dict):
        if "results" in parsed:
            parsed = parsed["results"]
        else:
            parsed = [parsed]

    if not isinstance(parsed, list):
        raise RuntimeError(
            "AI cevabı liste formatında değil."
        )

    return parsed


# ============================================================
# VALIDATION SAVE
# ============================================================

def bool_to_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, bool):
        return 1 if value else 0

    text = str(value).strip().lower()

    if text in {
        "true",
        "yes",
        "1",
        "supported",
    }:
        return 1

    if text in {
        "false",
        "no",
        "0",
        "unsupported",
    }:
        return 0

    return None


def save_validation_result(
    result: Dict[str, Any],
    method: Dict[str, Any],
    source_map: Dict[str, List[Dict[str, Any]]],
    raw_response: Dict[str, Any],
) -> None:

    conn = get_connection()

    method_name = (
        result.get("canonical_name")
        or method["canonical_name"]
    )

    method_id = (
        result.get("method_id")
        if result.get("method_id") is not None
        else method["method_id"]
    )

    sources = source_map.get(
        method["canonical_name"],
        []
    )

    source_snapshot = json.dumps(
        sources,
        ensure_ascii=False
    )

    supported_claims = json.dumps(
        result.get("supported_claims", []),
        ensure_ascii=False
    )

    unsupported_claims = json.dumps(
        result.get("unsupported_claims", []),
        ensure_ascii=False
    )

    missing_information = json.dumps(
        result.get("missing_information", []),
        ensure_ascii=False
    )

    raw_json = json.dumps(
        raw_response,
        ensure_ascii=False
    )

    validated_at = datetime.now(
        timezone.utc
    ).isoformat()

    conn.execute(
        """
        INSERT INTO method_ai_validation (
            method_id,
            canonical_name,
            category,
            verification_status,
            verification_score,
            source_supported,
            logic_consistent,
            parameters_supported,
            reproducibility_score,
            claim_risk,
            reasoning,
            missing_information,
            supported_claims,
            unsupported_claims,
            source_snapshot,
            raw_response,
            model,
            validated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(method_id, canonical_name)
        DO UPDATE SET
            category = excluded.category,
            verification_status = excluded.verification_status,
            verification_score = excluded.verification_score,
            source_supported = excluded.source_supported,
            logic_consistent = excluded.logic_consistent,
            parameters_supported = excluded.parameters_supported,
            reproducibility_score = excluded.reproducibility_score,
            claim_risk = excluded.claim_risk,
            reasoning = excluded.reasoning,
            missing_information = excluded.missing_information,
            supported_claims = excluded.supported_claims,
            unsupported_claims = excluded.unsupported_claims,
            source_snapshot = excluded.source_snapshot,
            raw_response = excluded.raw_response,
            model = excluded.model,
            validated_at = excluded.validated_at
        """,
        (
            method_id,
            method_name,
            method["category"],
            result.get(
                "status",
                "needs_review"
            ),
            result.get(
                "verification_score"
            ),
            bool_to_int(
                result.get("source_supported")
            ),
            bool_to_int(
                result.get("logic_consistent")
            ),
            bool_to_int(
                result.get("parameters_supported")
            ),
            result.get(
                "reproducibility_score"
            ),
            result.get(
                "claim_risk",
                "medium"
            ),
            result.get(
                "reasoning",
                ""
            ),
            missing_information,
            supported_claims,
            unsupported_claims,
            source_snapshot,
            raw_json,
            MODEL,
            validated_at,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# REPORT
# ============================================================

def print_result(
    result: Dict[str, Any]
) -> None:

    name = result.get(
        "canonical_name",
        "Unknown"
    )

    status = result.get(
        "status",
        "needs_review"
    )

    score = result.get(
        "verification_score",
        0
    )

    reproducibility = result.get(
        "reproducibility_score",
        0
    )

    risk = result.get(
        "claim_risk",
        "medium"
    )

    print(
        f"  • {name}\n"
        f"    Status: {status}\n"
        f"    Score: {score}/100 | "
        f"Reproducibility: {reproducibility}/100 | "
        f"Claim risk: {risk}"
    )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    if not results:
        return

    statuses: Dict[str, int] = {}

    scores = []
    reproducibility_scores = []

    for result in results:
        status = result.get(
            "status",
            "needs_review"
        )

        statuses[status] = (
            statuses.get(status, 0) + 1
        )

        try:
            scores.append(
                float(
                    result.get(
                        "verification_score",
                        0
                    )
                )
            )
        except Exception:
            pass

        try:
            reproducibility_scores.append(
                float(
                    result.get(
                        "reproducibility_score",
                        0
                    )
                )
            )
        except Exception:
            pass

    print()
    print("=========================================")
    print("🤖 AI METHOD VERIFIER SONUCU")
    print("=========================================")
    print(f"Doğrulanan method: {len(results)}")

    if scores:
        print(
            f"Ortalama verification score: "
            f"{sum(scores) / len(scores):.1f}/100"
        )

    if reproducibility_scores:
        print(
            f"Ortalama reproducibility: "
            f"{sum(reproducibility_scores) / len(reproducibility_scores):.1f}/100"
        )

    print()
    print("STATUS")
    print("-----------------------------------------")

    for status, count in sorted(
        statuses.items(),
        key=lambda x: (-x[1], x[0])
    ):
        print(
            f"{status}: {count}"
        )

    print()
    print("=========================================")


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("🤖 FIN[SYS] METHOD AI VERIFIER")
    print("=========================================")
    print(f"Model: {MODEL}")
    print(f"Max method: {MAX_METHODS}")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    ensure_validation_table()

    methods = load_methods()

    print(
        f"Registry toplam method: {len(methods)}"
    )

    if not methods:
        print(
            "❌ Doğrulanacak method bulunamadı."
        )
        return

    validator_data = load_validator_priority()

    if validator_data:
        print(
            f"Validator öncelik verisi: "
            f"{len(validator_data)} kayıt"
        )
    else:
        print(
            "ℹ️ Validator sonuç tablosu bulunamadı; "
            "registry bilgileri ile önceliklendirme yapılacak."
        )

    selected = select_methods_for_verification(
        methods,
        validator_data
    )

    print(
        f"AI doğrulama adayı: {len(selected)}"
    )

    print()
    print("ÖNCELİKLİ METHODLAR")
    print("-----------------------------------------")

    for index, method in enumerate(
        selected,
        start=1
    ):
        print(
            f"{index:02d}. "
            f"{method['canonical_name']} "
            f"[{method['category']}] "
            f"priority={method['priority']}"
        )

    print()

    source_map = collect_sources_for_methods(
        selected
    )

    with_source = sum(
        1
        for method in selected
        if source_map.get(
            method["canonical_name"]
        )
    )

    print(
        f"Kaynağı bulunan aday: "
        f"{with_source}/{len(selected)}"
    )

    # Kaynak bulunmayan methodları yine de AI'a göndermek
    # gereksiz olduğundan çıkartıyoruz.
    selected = [
        method
        for method in selected
        if source_map.get(
            method["canonical_name"]
        )
    ]

    if not selected:
        print(
            "❌ Kaynak metni bulunan method yok."
        )
        return

    print()
    print(
        f"Kaynaklı method sayısı: {len(selected)}"
    )

    all_results = []

    for start in range(
        0,
        len(selected),
        BATCH_SIZE
    ):
        batch = selected[
            start:start + BATCH_SIZE
        ]

        batch_number = (
            start // BATCH_SIZE
        ) + 1

        total_batches = (
            (len(selected) + BATCH_SIZE - 1)
            // BATCH_SIZE
        )

        print()
        print(
            f"🔎 Batch {batch_number}/{total_batches} "
            f"({len(batch)} method)"
        )

        try:
            results = call_ai(
                batch,
                source_map
            )

        except Exception as exc:
            print(
                f"❌ Batch başarısız: {exc}"
            )
            continue

        valid_batch_results = 0

        for result in results:
            method_id = result.get(
                "method_id"
            )

            canonical_name = normalize(
                result.get(
                    "canonical_name"
                )
            )

            matched_method = None

            if method_id is not None:
                for method in batch:
                    if normalize(
                        method["method_id"]
                    ) == normalize(method_id):
                        matched_method = method
                        break

            if matched_method is None and canonical_name:
                for method in batch:
                    if (
                        method["canonical_name"].lower()
                        == canonical_name.lower()
                    ):
                        matched_method = method
                        break

            if matched_method is None:
                print(
                    "⚠️ AI sonucu registry'deki "
                    "method ile eşleştirilemedi."
                )
                continue

            try:
                save_validation_result(
                    result,
                    matched_method,
                    source_map,
                    result,
                )

                all_results.append(result)
                valid_batch_results += 1

                print_result(result)

            except Exception as exc:
                print(
                    f"⚠️ Sonuç kaydedilemedi: {exc}"
                )

        print(
            f"✅ Batch tamamlandı: "
            f"{valid_batch_results}/{len(batch)}"
        )

    print_summary(all_results)

    print()
    print("✅ Method AI Verifier tamamlandı.")
    print(
        "Sonraki aşama: "
        "AI doğrulaması yüksek olan ve "
        "teknik olarak yeniden üretilebilir "
        "methodları Strategy Lab'e bağlamak."
    )


if __name__ == "__main__":
    main()
