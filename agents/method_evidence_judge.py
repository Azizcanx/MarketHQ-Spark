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
        "METHOD_EVIDENCE_JUDGE_BATCH_SIZE",
        "4"
    )
)

MAX_EVIDENCE_PER_GAP = 3


# ============================================================
# OPENAI
# ============================================================

client = None


def get_client():

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

def get_connection():

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def table_exists(
    conn,
    table_name
):

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


def ensure_table():

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS method_evidence_judgments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            method_id INTEGER,
            canonical_name TEXT NOT NULL,

            gap TEXT NOT NULL,
            gap_type TEXT,

            judgment TEXT NOT NULL,

            support_score REAL,

            explanation TEXT,

            supported_fact TEXT,
            unsupported_reason TEXT,

            evidence_used TEXT,

            source_urls TEXT,

            model TEXT,

            judged_at TEXT,

            UNIQUE(
                method_id,
                canonical_name,
                gap
            )
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


def compact(
    value: Any,
    limit: int = 1800
) -> str:

    text = normalize(
        value
    )

    text = " ".join(
        text.split()
    )

    if len(text) <= limit:
        return text

    return (
        text[:limit].rstrip()
        + "..."
    )


# ============================================================
# LOAD AUDITS
# ============================================================

def load_audits():

    conn = get_connection()

    if not table_exists(
        conn,
        "method_evidence_audit"
    ):
        conn.close()

        raise RuntimeError(
            "method_evidence_audit bulunamadı.\n"
            "Önce method_evidence_auditor.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM method_evidence_audit
        WHERE unresolved_count = 0
        ORDER BY canonical_name
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# BUILD JUDGMENT INPUT
# ============================================================

def build_judgment_items(
    audits: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    items = []

    for audit in audits:

        recovered = parse_json(
            audit.get(
                "recovered_items"
            )
        )

        if not isinstance(
            recovered,
            list
        ):
            continue

        for recovered_item in recovered:

            if not isinstance(
                recovered_item,
                dict
            ):
                continue

            gap = normalize(
                recovered_item.get(
                    "gap"
                )
            )

            if not gap:
                continue

            evidence = recovered_item.get(
                "evidence",
                []
            )

            if not isinstance(
                evidence,
                list
            ):
                evidence = []

            evidence = evidence[
                :MAX_EVIDENCE_PER_GAP
            ]

            clean_evidence = []

            for source in evidence:

                if not isinstance(
                    source,
                    dict
                ):
                    continue

                clean_evidence.append(
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
                        "score": safe_float(
                            source.get(
                                "score"
                            )
                        ),
                        "matched_gap_terms": (
                            source.get(
                                "matched_gap_terms",
                                []
                            )
                        ),
                        "reasons": source.get(
                            "reasons",
                            []
                        ),
                        "snippet": compact(
                            source.get(
                                "snippet"
                            ),
                            2200
                        ),
                    }
                )

            items.append(
                {
                    "method_id": audit.get(
                        "method_id"
                    ),
                    "canonical_name": normalize(
                        audit.get(
                            "canonical_name"
                        )
                    ),
                    "category": normalize(
                        audit.get(
                            "category"
                        )
                    ),
                    "gap": gap,
                    "gap_type": normalize(
                        recovered_item.get(
                            "gap_type"
                        )
                    ),
                    "recovery_strength": normalize(
                        recovered_item.get(
                            "recovery_strength"
                        )
                    ),
                    "evidence": clean_evidence,
                }
            )

    return items


# ============================================================
# PROMPT
# ============================================================

def build_prompt(
    batch: List[Dict[str, Any]]
) -> str:

    payload = json.dumps(
        batch,
        ensure_ascii=False,
        indent=2
    )

    return f"""
Sen MarketHQ içindeki FIN[SYS] kaynak kanıtı değerlendirme ajanısın.

Görevin aşağıdaki her GAP için, verilen kaynak snippet'lerinin
o GAP'i gerçekten destekleyip desteklemediğini belirlemek.

ÇOK ÖNEMLİ:

1. Sadece verilen kaynak snippet'lerini kullan.

2. Metodun adı ile aynı sayfada bulunmak TEK BAŞINA yeterli değildir.

3. "Trend", "momentum", "volatilite", "algoritma", "sinyal"
   gibi genel kelimeler teknik parametreyi kanıtlamaz.

4. Örneğin GAP:
   "EMA periyodu"

   Kaynak:
   "Sistem trend analizi yapar."

   ise sonuç NOT_SUPPORTED olmalı.

5. GAP:
   "Haftalık zaman dilimi"

   Kaynak:
   "Bluesky haftalık grafiklerde kullanılır."

   ise SUPPORTED olabilir.

6. GAP:
   "RSI 14 kullanır"

   Kaynak:
   sadece "RSI kullanılır"

   ise PARTIALLY_SUPPORTED olmalı.
   Çünkü RSI destekleniyor ama 14 değeri desteklenmiyor.

7. Kaynakta bulunmayan sayısal değerleri tahmin etme.

8. Kaynağın tanıtım dili teknik şartname olarak kabul edilmemeli.

9. Kaynak metodun kendi tekniğini anlatmıyorsa onu kanıt olarak
   kullanma.

10. Bir bilgi mantıksal olarak mümkün görünse bile kaynak açıkça
    desteklemiyorsa SUPPORTED verme.

11. Yatırım tavsiyesi verme.

12. Private/paid içeriğe erişim veya erişim kontrolü aşma girişimi yapma.

JUDGMENT seçenekleri:

SUPPORTED
    Kaynak GAP'i açıkça destekliyor.

PARTIALLY_SUPPORTED
    Kaynağın bir kısmı destekleniyor ama önemli bir ayrıntı eksik.

NOT_SUPPORTED
    Kaynak GAP'i desteklemiyor.

Her item için:

- item_index
- method_id
- canonical_name
- gap
- judgment
- support_score: 0-100
- explanation
- supported_fact
- unsupported_reason
- evidence_used

döndür.

SADECE JSON ARRAY döndür.

Format:

[
  {{
    "item_index": 1,
    "method_id": 123,
    "canonical_name": "Example",
    "gap": "EMA periyodu",
    "judgment": "PARTIALLY_SUPPORTED",
    "support_score": 55,
    "explanation": "...",
    "supported_fact": "EMA kullanımı kaynakta belirtiliyor.",
    "unsupported_reason": "EMA periyodu belirtilmiyor.",
    "evidence_used": [
      {{
        "title": "...",
        "url": "..."
      }}
    ]
  }}
]

ITEMS:

{payload}
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

        if lines and lines[
            0
        ].startswith("```"):

            lines = lines[1:]

        if lines and lines[
            -1
        ].strip() == "```":

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
    batch
):

    ai = get_client()

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
            "AI JSON parse hatası: "
            f"{exc}\n"
            f"{raw[:6000]}"
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
            "AI cevabı liste değil."
        )

    return parsed


# ============================================================
# RESULT NORMALIZATION
# ============================================================

ALLOWED_JUDGMENTS = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "NOT_SUPPORTED"
}


def normalize_judgment(
    value: Any
) -> str:

    value = normalize(
        value
    ).upper()

    if value in ALLOWED_JUDGMENTS:
        return value

    if "PART" in value:
        return "PARTIALLY_SUPPORTED"

    if "NOT" in value:
        return "NOT_SUPPORTED"

    if "SUPPORT" in value:
        return "SUPPORTED"

    return "NOT_SUPPORTED"


def normalize_result(
    result: Dict[str, Any]
) -> Dict[str, Any]:

    return {
        "item_index": result.get(
            "item_index"
        ),

        "method_id": result.get(
            "method_id"
        ),

        "canonical_name": normalize(
            result.get(
                "canonical_name"
            )
        ),

        "gap": normalize(
            result.get(
                "gap"
            )
        ),

        "judgment": normalize_judgment(
            result.get(
                "judgment"
            )
        ),

        "support_score": max(
            0.0,
            min(
                100.0,
                safe_float(
                    result.get(
                        "support_score"
                    )
                )
            )
        ),

        "explanation": normalize(
            result.get(
                "explanation"
            )
        ),

        "supported_fact": normalize(
            result.get(
                "supported_fact"
            )
        ),

        "unsupported_reason": normalize(
            result.get(
                "unsupported_reason"
            )
        ),

        "evidence_used": ensure_list(
            result.get(
                "evidence_used",
                []
            )
        ),
    }


# ============================================================
# SAVE
# ============================================================

def save_judgment(
    judgment: Dict[str, Any],
    method_item: Dict[str, Any]
) -> None:

    evidence_urls = []

    for evidence in judgment[
        "evidence_used"
    ]:

        if not isinstance(
            evidence,
            dict
        ):
            continue

        url = normalize(
            evidence.get(
                "url"
            )
        )

        if url and url not in evidence_urls:
            evidence_urls.append(
                url
            )

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO method_evidence_judgments (
            method_id,
            canonical_name,
            gap,
            gap_type,

            judgment,
            support_score,

            explanation,
            supported_fact,
            unsupported_reason,

            evidence_used,
            source_urls,

            model,
            judged_at
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?
        )

        ON CONFLICT(
            method_id,
            canonical_name,
            gap
        )
        DO UPDATE SET

            gap_type = excluded.gap_type,

            judgment = excluded.judgment,
            support_score = excluded.support_score,

            explanation = excluded.explanation,
            supported_fact = excluded.supported_fact,
            unsupported_reason = excluded.unsupported_reason,

            evidence_used = excluded.evidence_used,
            source_urls = excluded.source_urls,

            model = excluded.model,
            judged_at = excluded.judged_at
        """,
        (
            judgment.get(
                "method_id"
            )
            if judgment.get(
                "method_id"
            ) is not None
            else method_item.get(
                "method_id"
            ),

            (
                judgment.get(
                    "canonical_name"
                )
                or method_item.get(
                    "canonical_name"
                )
            ),

            (
                judgment.get(
                    "gap"
                )
                or method_item.get(
                    "gap"
                )
            ),

            method_item.get(
                "gap_type"
            ),

            judgment[
                "judgment"
            ],

            judgment[
                "support_score"
            ],

            judgment[
                "explanation"
            ],

            judgment[
                "supported_fact"
            ],

            judgment[
                "unsupported_reason"
            ],

            json.dumps(
                judgment[
                    "evidence_used"
                ],
                ensure_ascii=False
            ),

            json.dumps(
                evidence_urls,
                ensure_ascii=False
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
# MATCH RESULT TO ITEM
# ============================================================

def match_result(
    result: Dict[str, Any],
    batch: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:

    method_id = result.get(
        "method_id"
    )

    gap = normalize(
        result.get(
            "gap"
        )
    )

    canonical_name = normalize(
        result.get(
            "canonical_name"
        )
    ).lower()

    # 1. ID + gap
    for item in batch:

        if method_id is not None:

            if normalize(
                item.get(
                    "method_id"
                )
            ) != normalize(
                method_id
            ):
                continue

        if gap:

            if normalize(
                item.get(
                    "gap"
                )
            ).lower() != gap.lower():

                continue

        return item

    # 2. Name + gap
    for item in batch:

        if (
            canonical_name
            and normalize(
                item.get(
                    "canonical_name"
                )
            ).lower()
            != canonical_name
        ):
            continue

        if gap:

            if normalize(
                item.get(
                    "gap"
                )
            ).lower() != gap.lower():

                continue

        return item

    # 3. item index
    index = result.get(
        "item_index"
    )

    if index is not None:

        try:

            index = int(
                index
            )

            if (
                index >= 1
                and index <= len(batch)
            ):
                return batch[
                    index - 1
                ]

        except Exception:
            pass

    return None


# ============================================================
# REPORT
# ============================================================

def print_summary(
    judgments: List[Dict[str, Any]]
):

    counts = {
        "SUPPORTED": 0,
        "PARTIALLY_SUPPORTED": 0,
        "NOT_SUPPORTED": 0,
    }

    scores = []

    for judgment in judgments:

        value = judgment[
            "judgment"
        ]

        if value in counts:
            counts[
                value
            ] += 1

        scores.append(
            judgment[
                "support_score"
            ]
        )

    print()
    print("=========================================")
    print("⚖️ METHOD EVIDENCE JUDGE SONUCU")
    print("=========================================")

    print(
        f"Yargılanan gap: "
        f"{len(judgments)}"
    )

    print()
    print("JUDGMENTS")
    print("-----------------------------------------")

    print(
        f"SUPPORTED:             "
        f"{counts['SUPPORTED']}"
    )

    print(
        f"PARTIALLY_SUPPORTED:   "
        f"{counts['PARTIALLY_SUPPORTED']}"
    )

    print(
        f"NOT_SUPPORTED:         "
        f"{counts['NOT_SUPPORTED']}"
    )

    if scores:

        print()
        print(
            f"Ortalama support score: "
            f"{sum(scores) / len(scores):.1f}/100"
        )

    print()
    print(
        "========================================="
    )


def print_interesting_cases(
    judgments: List[Dict[str, Any]]
):

    not_supported = [
        judgment
        for judgment in judgments
        if judgment[
            "judgment"
        ] == "NOT_SUPPORTED"
    ]

    partially = [
        judgment
        for judgment in judgments
        if judgment[
            "judgment"
        ] == "PARTIALLY_SUPPORTED"
    ]

    print()
    print("❌ NOT SUPPORTED")
    print("-----------------------------------------")

    if not not_supported:

        print(
            "Yok."
        )

    else:

        for judgment in not_supported[
            :20
        ]:

            print(
                f"• {judgment['canonical_name']}"
            )

            print(
                f"  GAP: {judgment['gap']}"
            )

            print(
                f"  Score: "
                f"{judgment['support_score']:.1f}"
            )

    print()
    print("🟡 PARTIALLY SUPPORTED")
    print("-----------------------------------------")

    if not partially:

        print(
            "Yok."
        )

    else:

        for judgment in partially[
            :20
        ]:

            print(
                f"• {judgment['canonical_name']}"
            )

            print(
                f"  GAP: {judgment['gap']}"
            )

            print(
                f"  Score: "
                f"{judgment['support_score']:.1f}"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=========================================")
    print("⚖️ FIN[SYS] METHOD EVIDENCE JUDGE")
    print("=========================================")

    print(
        f"Model: {MODEL}"
    )

    print(
        f"Batch size: {BATCH_SIZE}"
    )

    print()

    ensure_table()

    audits = load_audits()

    print(
        f"Audit record: "
        f"{len(audits)}"
    )

    if not audits:

        print(
            "❌ Evidence audit kaydı bulunamadı."
        )

        print(
            "Önce method_evidence_auditor.py çalıştır."
        )

        return

    items = build_judgment_items(
        audits
    )

    print(
        f"Yargılanacak gap: "
        f"{len(items)}"
    )

    if not items:

        print(
            "❌ Yargılanacak evidence bulunamadı."
        )

        return

    all_judgments = []

    total_batches = (
        len(items)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    for start in range(
        0,
        len(items),
        BATCH_SIZE
    ):

        batch = items[
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
            f"({len(batch)} gap)"
        )

        try:

            results = call_ai(
                batch
            )

        except Exception as exc:

            print(
                f"❌ Batch başarısız: "
                f"{exc}"
            )

            continue

        saved = 0

        for raw_result in results:

            if not isinstance(
                raw_result,
                dict
            ):
                continue

            judgment = normalize_result(
                raw_result
            )

            matched_item = match_result(
                judgment,
                batch
            )

            if matched_item is None:

                print(
                    "⚠️ AI sonucu item "
                    "ile eşleştirilemedi:"
                )

                print(
                    f"   {judgment['canonical_name']} "
                    f"/ {judgment['gap']}"
                )

                continue

            save_judgment(
                judgment,
                matched_item
            )

            all_judgments.append(
                judgment
            )

            saved += 1

            print(
                f"  • "
                f"{judgment['canonical_name']} "
                f"/ {judgment['gap']}"
            )

            print(
                f"    → "
                f"{judgment['judgment']} "
                f"({judgment['support_score']:.1f}/100)"
            )

        print(
            f"✅ Batch tamamlandı: "
            f"{saved}/{len(batch)}"
        )

    print_summary(
        all_judgments
    )

    print_interesting_cases(
        all_judgments
    )

    print()
    print(
        "✅ Method Evidence Judge tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Gerçekten desteklenen teknik parçalar "
        "Technical Spec ile birleştirilecek; "
        "desteklenmeyenler Strategy Lab'e aktarılmayacak."
    )


if __name__ == "__main__":
    main()
