import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


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
    add_knowledge_item,
    get_connection,
    init_db,
)


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# CONFIG
# =========================================================

MODEL = "gpt-5.6-luna"

EXTRACTION_VERSION = "fin-sys-extractor-v1"

MAX_CONTENT_CHARS = 18000

MIN_CONTENT_CHARS = 150


# =========================================================
# PAGE LIST
# =========================================================

def get_public_pages() -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                title,
                url
            FROM knowledge_sources
            WHERE source_type = 'fin_sys_public_web'
            AND url IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# GET STORED PAGE CONTENT
# =========================================================

def get_page_content(
    source_id: int,
) -> str:

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT content
            FROM knowledge_items
            WHERE source_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                source_id,
            ),
        ).fetchone()

        if row is None:
            return ""

        return str(
            row["content"]
            or ""
        )

    finally:

        conn.close()


# =========================================================
# DUPLICATE CHECK
# =========================================================

def already_extracted(
    source_id: int,
) -> bool:

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT id
            FROM knowledge_items
            WHERE source_id = ?
            AND item_type = 'extracted_method'
            LIMIT 1
            """,
            (
                source_id,
            ),
        ).fetchone()

        return row is not None

    finally:

        conn.close()


# =========================================================
# CONTENT CLEANUP
# =========================================================

def prepare_content(
    text: str,
) -> str:

    text = " ".join(
        str(text or "")
        .split()
    ).strip()

    if len(text) <= MAX_CONTENT_CHARS:

        return text

    return (
        text[:MAX_CONTENT_CHARS]
        +
        "\n\n"
        "[MarketHQ: içerik uzunluğu nedeniyle "
        "burada kesildi.]"
    )


# =========================================================
# AI EXTRACTION
# =========================================================

def extract_methodology(
    title: str,
    url: str,
    content: str,
) -> dict[str, Any]:

    client = OpenAI()

    prompt = f"""
Sen MarketHQ'nun FIN[SYS] bilgi çıkarım uzmanısın.

Amaç:
FIN[SYS]'in KAMUYA AÇIK web sayfasındaki
bilgileri yapılandırılmış metodoloji bilgisine
dönüştürmek.

Bu çalışma yatırım tavsiyesi üretmeyecek.

--------------------------------------------------
KAYNAK
--------------------------------------------------

Başlık:
{title}

URL:
{url}

--------------------------------------------------
KAYNAK İÇERİĞİ
--------------------------------------------------

{content}

--------------------------------------------------
ÇIKTI
--------------------------------------------------

SADECE GEÇERLİ JSON DÖNDÜR.

Format:

{{
    "page_summary": "...",

    "content_type": "indicator",

    "methods": [

        {{
            "name": "...",

            "type": "indicator",

            "purpose": "...",

            "logic": "...",

            "inputs": [],

            "parameters": [],

            "conditions": [],

            "signals": [],

            "timeframes": [],

            "visual_elements": [],

            "filters": [],

            "risk_notes": [],

            "failure_modes": [],

            "explicit_claims": [],

            "inferences": []
        }}

    ],

    "mentioned_symbols": [],

    "mentioned_indicators": [],

    "mentioned_algorithms": [],

    "mentioned_tools": [],

    "tags": []
}}

--------------------------------------------------
TYPE DEĞERLERİ
--------------------------------------------------

indicator
filter
algorithm
tradingview_method
python_method
chart_method
trend_method
momentum_method
volume_method
scan_method
system
education
other

--------------------------------------------------
KURALLAR
--------------------------------------------------

1. Kaynakta olmayan bilgi uydurma.

2. Kaynakta olmayan formül uydurma.

3. Kaynakta olmayan parametre uydurma.

4. Kaynak bir yöntemin sadece adını veriyorsa,
   ayrıntılı çalışma mantığı icat etme.

5. Açıkça yazılan bilgiyi
   "explicit_claims" içine koy.

6. Metinden yapılan mantıksal çıkarımı
   "inferences" içine koy.

7. Belirsiz bilgileri kesinmiş gibi yazma.

8. Bir indikatör açıklanıyorsa mümkün olduğunca:
   - amacı
   - girdileri
   - çalışma mantığı
   - sinyal koşulları
   - zaman dilimi
   - görsel kullanım
   çıkar.

9. Bir grafik yöntemi anlatılıyorsa:
   - trend
   - destek
   - direnç
   - kanal
   - kırılım
   - regresyon
   - momentum
   gibi açıkça belirtilen unsurları çıkar.

10. Bir algoritma yalnızca isim olarak geçiyorsa
    algoritmayı uydurma.

11. Bir sistemin geçmiş performansı hakkında
    kaynak bir rakam veriyorsa bunu iddia olarak
    kaydet; doğrulanmış gerçek gibi sunma.

12. Hisse sembolü açıkça belirtilmiyorsa
    sembol tahmin etme.

13. Yatırım tavsiyesi verme.

14. JSON dışında hiçbir şey döndürme.
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt,
    )

    raw = (
        response.output_text
        or ""
    ).strip()

    try:

        result = json.loads(
            raw
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            "AI geçerli JSON döndürmedi.\n"
            f"{raw[:1500]}"
        ) from error

    if not isinstance(
        result,
        dict
    ):

        raise ValueError(
            "AI çıktısı JSON object değil."
        )

    return result


# =========================================================
# SAVE EXTRACTED METHODS
# =========================================================

def save_extracted_method(
    source_id: int,
    page_title: str,
    method: dict[str, Any],
    page_summary: str,
    mentioned_symbols: list,
    mentioned_indicators: list,
    mentioned_algorithms: list,
    mentioned_tools: list,
    tags: list,
) -> int:

    method_name = str(
        method.get(
            "name",
            page_title
        )
    ).strip()

    method_type = str(
        method.get(
            "type",
            "other"
        )
    ).strip()

    content = json.dumps(
        method,
        ensure_ascii=False,
        indent=2,
    )

    merged_tags = list(
        dict.fromkeys(
            [
                "FIN[SYS]",
                "AI_EXTRACTED",
                *(
                    tags or []
                ),
            ]
        )
    )

    metadata = {
        "extraction_version":
            EXTRACTION_VERSION,

        "source_page":
            page_title,

        "mentioned_symbols":
            mentioned_symbols,

        "mentioned_indicators":
            mentioned_indicators,

        "mentioned_algorithms":
            mentioned_algorithms,

        "mentioned_tools":
            mentioned_tools,
    }

    return add_knowledge_item(
        source_id=source_id,

        item_type="extracted_method",

        title=method_name,

        content=content,

        summary=page_summary,

        method=method.get(
            "logic",
            ""
        ),

        symbols=mentioned_symbols,

        tags=merged_tags,

        confidence=0.80,

        metadata=metadata,
    )


# =========================================================
# PROCESS ONE PAGE
# =========================================================

def process_page(
    page: dict[str, Any],
) -> dict[str, Any]:

    source_id = int(
        page["id"]
    )

    title = str(
        page.get(
            "title"
        )
        or "FIN[SYS] Page"
    )

    url = str(
        page.get(
            "url"
        )
        or ""
    )

    # -----------------------------------------------------
    # Duplicate protection
    # -----------------------------------------------------

    if already_extracted(
        source_id
    ):

        return {
            "status": "cached",
            "source_id": source_id,
            "title": title,
            "methods": 0,
        }

    content = get_page_content(
        source_id
    )

    content = prepare_content(
        content
    )

    if len(content) < MIN_CONTENT_CHARS:

        return {
            "status": "skipped",
            "source_id": source_id,
            "title": title,
            "methods": 0,
            "reason": "İçerik çok kısa.",
        }

    print()
    print(
        f"🧠 Analiz: {title}"
    )

    result = extract_methodology(
        title=title,
        url=url,
        content=content,
    )

    page_summary = str(
        result.get(
            "page_summary",
            ""
        )
    ).strip()

    methods = result.get(
        "methods",
        []
    )

    if not isinstance(
        methods,
        list
    ):

        methods = []

    mentioned_symbols = (
        result.get(
            "mentioned_symbols",
            []
        )
        or []
    )

    mentioned_indicators = (
        result.get(
            "mentioned_indicators",
            []
        )
        or []
    )

    mentioned_algorithms = (
        result.get(
            "mentioned_algorithms",
            []
        )
        or []
    )

    mentioned_tools = (
        result.get(
            "mentioned_tools",
            []
        )
        or []
    )

    tags = (
        result.get(
            "tags",
            []
        )
        or []
    )

    saved_methods = 0

    for method in methods:

        if not isinstance(
            method,
            dict
        ):
            continue

        save_extracted_method(
            source_id=source_id,

            page_title=title,

            method=method,

            page_summary=page_summary,

            mentioned_symbols=(
                mentioned_symbols
            ),

            mentioned_indicators=(
                mentioned_indicators
            ),

            mentioned_algorithms=(
                mentioned_algorithms
            ),

            mentioned_tools=(
                mentioned_tools
            ),

            tags=tags,
        )

        saved_methods += 1

    print(
        f"   ✅ {saved_methods} "
        f"metodoloji kaydı oluşturuldu."
    )

    return {
        "status": "processed",

        "source_id": source_id,

        "title": title,

        "methods": saved_methods,
    }


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    print(
        "=========================================="
    )

    print(
        "🧠 MARKET HQ FIN[SYS] "
        "KNOWLEDGE EXTRACTOR"
    )

    print(
        "=========================================="
    )

    pages = get_public_pages()

    print(
        f"Public sayfa sayısı: "
        f"{len(pages)}"
    )

    processed = 0

    cached = 0

    skipped = 0

    errors = 0

    methods = 0

    for index, page in enumerate(
        pages,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(pages)}]"
        )

        try:

            result = process_page(
                page
            )

            status = result.get(
                "status"
            )

            if status == "processed":

                processed += 1

                methods += int(
                    result.get(
                        "methods",
                        0
                    )
                )

            elif status == "cached":

                cached += 1

                print(
                    "   ℹ️ Zaten analiz edilmiş."
                )

            elif status == "skipped":

                skipped += 1

                print(
                    "   ⚠️ Atlandı: "
                    f"{result.get('reason', '')}"
                )

        except Exception as error:

            errors += 1

            print(
                "   ❌ Hata:"
            )

            print(
                f"      {error}"
            )

    print()
    print(
        "=========================================="
    )

    print(
        "📊 KNOWLEDGE EXTRACTION SONUCU"
    )

    print(
        "=========================================="
    )

    print(
        f"Toplam sayfa: {len(pages)}"
    )

    print(
        f"Yeni analiz edilen: {processed}"
    )

    print(
        f"Önceden analiz edilmiş: {cached}"
    )

    print(
        f"Atlanan: {skipped}"
    )

    print(
        f"Hatalı: {errors}"
    )

    print(
        f"Yeni metodoloji kaydı: {methods}"
    )

    print(
        "✅ FIN[SYS] Knowledge Extractor tamamlandı."
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
