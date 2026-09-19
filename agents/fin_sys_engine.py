import base64
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# MARKET HQ PROJE KLASÖRÜNÜ BUL
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# MARKET HQ DATABASE
# =========================================================

from database import (
    add_knowledge_item,
    add_knowledge_source,
    add_visual_asset,
    search_knowledge,
)


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# MODEL
# =========================================================

MODEL = "gpt-5.6-luna"

ANALYSIS_VERSION = "fin-sys-v1"


# =========================================================
# FIN[SYS] PUBLIC CATALOG
# =========================================================

PUBLIC_CATALOG = {
    "Teknik Analiz": [
        "Teknik Analiz Eğitimi - Sıfırdan İleri Düzeye",
    ],

    "İndikatörler": [
        "Yeni Nesil İndikatörler",
        "FIN",
        "Fin[Df]Dist",
        "Fin[Ft]",
        "Lin[Rs]",
        "Mtr-X",
        "RSI-Lin",
        "TSI",
        "DistMA",
        "NSM-OP",
        "Fin[CST]",
        "Trd[FL]",
        "MA-P",
        "QQE Signals",
        "QQE Classic",
        "RSHA",
        "Braid",
        "nQQE",
        "MACD",
        "ArzTalep",
        "RsiCross",
        "CRsi",
        "McLINEER",
        "MaTLRNS",
        "StochRsi",
        "TSD",
        "Hisse Değeri",
        "TopluEma",
        "ZeroLagEma",
        "Jigsaw",
        "Fisher",
        "DynamicLinReg",
        "LinReg[ax+b]",
        "LinReg[EXT]",
        "LinReg3CH",
        "Yatay DD",
        "LinReg3CH-P",
        "FIN[BnD]",
        "FIN[Rr]",
        "FIN[SrL]",
        "FIN[RmT]",
        "RSI-dF",
    ],

    "Teknik Filtreler": [
        "Teknik Filtreler - 1. Paket - Baz",
        "Teknik Filtreler - 2. Paket",
        "Teknik Filtreler - 3. Paket",
        "Teknik Filtreler - 4. Paket",
        "Teknik Filtreler - 5. Paket",
        "Trendliner",
        "Trendliner-Qnr",
        "KLC",
        "FIN[SrL]",
        "Teknik Filtreler - 7. Paket",
        "ImpulseTracker",
    ],

    "Algoritmalar": [
        "SKYLAR34D",
        "CALCULUS",
        "PAX",
        "ABAKUS-SW",
        "LINREGEXTREME-FIN[SS]",
        "ABAKUS-LW",
        "ImpulseTracker",
        "Agilis",
        "SC-Zlsma TF-MR-P",
        "RMA - Layered Engine",
        "FRAMA",
        "ALGODASHMASTER",
        "GaussZlma",
        "Algebra",
        "KHST",
        "ML-Supreme",
        "Dives",
        "LowPass",
        "Oracle",
        "POL-Gss",
        "Bluesky",
    ],

    "Python": [
        "Python İle Hisse Senedi Trend Tarama Çalışması",
        "Python İle Hisse Senedi Kısa Vadeli Dip-Tepe Oluşumları Tarama Çalışması",
        "Python İle Borsa İstanbul Hisse Senedi Günlük / Haftalık / Aylık / Yıllık Performans Tarama",
        "Python İle Hisse Senedi Trend ve Momentum Tarama Çalışması - ExpertMa",
        "TrendMultiCalc - Multi Time Frame Trend / Momentum / Hacim Tarama",
        "DPRS - Çoklu Çapraz Kantitatif Tarama",
    ],

    "Alış Satış Sistemleri": [
        "OPUS",
        "BRAT",
    ],

    "TradingView": [
        "TradingView Ekran Setupları",
        "TradingView Platformuna İndikatör ve Kod Yükleme",
    ],
}


# =========================================================
# PUBLIC CATALOG DATABASE'E EKLE
# =========================================================

def seed_public_catalog() -> int:

    source_id = add_knowledge_source(
        source_type="fin_sys_public_catalog",
        title="FIN[SYS] Public Content Catalog",
        url="https://www.fin-sys.eu/",
        author="FIN[SYS]",
        access_note="Public catalog metadata only.",
        metadata={
            "analysis_version": ANALYSIS_VERSION
        },
    )

    count = 0

    for category, items in PUBLIC_CATALOG.items():

        for item in items:

            add_knowledge_item(
                source_id=source_id,
                item_type="catalog",
                title=item,
                content=(
                    f"FIN[SYS] public catalog category: "
                    f"{category}. Item: {item}."
                ),
                summary=(
                    f"Publicly listed FIN[SYS] topic "
                    f"under {category}."
                ),
                method=category,
                tags=[
                    "FIN[SYS]",
                    category,
                ],
                metadata={
                    "catalog_item": item,
                    "category": category,
                },
            )

            count += 1

    return count


# =========================================================
# METİN / TRANSKRİPT ANALİZİ
# =========================================================

def ingest_text(
    title: str,
    text: str,
    source_url: str | None = None,
    source_type: str = "fin_sys_text",
    published_at: str | None = None,
    author: str = "FIN[SYS]",
    tags: list[str] | None = None,
) -> dict[str, Any]:

    clean_text = str(text or "").strip()

    if not clean_text:
        raise ValueError(
            "Text/transcript is empty."
        )

    source_id = add_knowledge_source(
        source_type=source_type,
        title=title,
        url=source_url,
        published_at=published_at,
        author=author,
        access_note=(
            "Use only content the user is "
            "authorized to process."
        ),
        metadata={
            "analysis_version": ANALYSIS_VERSION
        },
    )

    prompt = f"""
Sen MarketHQ'nun FIN[SYS] bilgi çıkarım motorusun.

KAYNAK:
FIN[SYS]

BAŞLIK:
{title}

Görevin yatırım tavsiyesi üretmek değil.
Kaynakta anlatılan yöntemi yapılandırılmış
bilgi haline getirmek.

SADECE AŞAĞIDAKİ JSON FORMATINI DÖNDÜR:

{{
    "summary": "...",

    "methods": [
        {{
            "name": "...",
            "type": "indicator",
            "logic": "...",
            "inputs": [],
            "conditions": [],
            "signals": [],
            "timeframes": [],
            "failure_modes": []
        }}
    ],

    "symbols": [],

    "tags": []
}}

type şu değerlerden biri olmalı:

indicator
filter
algorithm
chart_method
risk_method
scan_method
tradingview_method
other

KURALLAR:

1. Kaynakta olmayan formül uydurma.

2. Kaynakta olmayan parametre uydurma.

3. Kaynakta olmayan hisse/sembol uydurma.

4. Açıkça belirtilen bilgi ile yorumunu ayır.

5. Yatırım tavsiyesi üretme.

6. İndikatör anlatılıyorsa:
   - amacı
   - girdileri
   - çalışma mantığı
   - koşulları
   - sinyalleri
   - zaman dilimi
   - sınırlamaları
   çıkar.

7. Grafik yöntemi anlatılıyorsa:
   - trend
   - destek
   - direnç
   - kanal
   - kırılım
   - momentum
   - hacim
   gibi açıkça anlatılan unsurları çıkar.

8. Algoritma anlatılıyorsa çalışma mantığını,
   kaynakta anlatıldığı ölçüde çıkar.

9. Kaynakta bilgi yoksa tahmin etme.

KAYNAK METNİ:

{clean_text}
"""

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=prompt,
    )

    raw = response.output_text.strip()

    try:
        structured = json.loads(raw)

    except json.JSONDecodeError as error:

        raise ValueError(
            "Model geçerli JSON döndürmedi:\n"
            f"{raw[:1000]}"
        ) from error

    summary = str(
        structured.get(
            "summary",
            ""
        )
    ).strip()

    methods = structured.get(
        "methods",
        []
    )

    symbols = structured.get(
        "symbols",
        []
    ) or []

    model_tags = structured.get(
        "tags",
        []
    ) or []

    if not methods:

        methods = [
            {
                "name": title,
                "type": "other",
                "logic": clean_text,
                "inputs": [],
                "conditions": [],
                "signals": [],
                "timeframes": [],
                "failure_modes": [],
            }
        ]

    created_ids = []

    for method in methods:

        if not isinstance(
            method,
            dict
        ):
            continue

        name = str(
            method.get(
                "name",
                title
            )
        ).strip()

        method_type = str(
            method.get(
                "type",
                "other"
            )
        )

        content = json.dumps(
            method,
            ensure_ascii=False,
            indent=2,
        )

        item_id = add_knowledge_item(
            source_id=source_id,
            item_type=method_type,
            title=name,
            content=content,
            summary=summary,
            method=method.get(
                "logic"
            ),
            symbols=symbols,
            tags=list(
                dict.fromkeys(
                    [
                        *(tags or []),
                        *model_tags,
                        "FIN[SYS]",
                    ]
                )
            ),
            confidence=0.75,
            metadata={
                "source_title": title,
                "analysis_version": ANALYSIS_VERSION,
            },
        )

        created_ids.append(
            item_id
        )

    return {
        "source_id": source_id,
        "knowledge_ids": created_ids,
        "summary": summary,
        "methods": methods,
        "symbols": symbols,
        "tags": model_tags,
    }


# =========================================================
# YOUTUBE METADATA
# =========================================================

def get_youtube_metadata(
    youtube_url: str,
) -> dict[str, Any]:

    oembed_url = (
        "https://www.youtube.com/oembed"
        f"?url={quote(youtube_url, safe='')}"
        "&format=json"
    )

    response = requests.get(
        oembed_url,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# YOUTUBE İÇERİK EKLEME
# =========================================================

def ingest_youtube_url(
    youtube_url: str,
    transcript: str | None = None,
    extra_context: str = "",
) -> dict[str, Any]:

    metadata = get_youtube_metadata(
        youtube_url
    )

    title = (
        metadata.get(
            "title"
        )
        or "FIN[SYS] YouTube Video"
    )

    author = (
        metadata.get(
            "author_name"
        )
        or "FIN[SYS]"
    )

    source_id = add_knowledge_source(
        source_type="youtube",
        title=title,
        url=youtube_url,
        author=author,
        access_note=(
            "Public YouTube metadata. "
            "Transcript is processed only "
            "when supplied/authorized."
        ),
        metadata={
            "thumbnail_url": metadata.get(
                "thumbnail_url"
            ),
            "author_url": metadata.get(
                "author_url"
            ),
        },
    )

    if not transcript:

        add_knowledge_item(
            source_id=source_id,
            item_type="youtube_metadata",
            title=title,
            content=json.dumps(
                {
                    "title": title,
                    "author": author,
                    "url": youtube_url,
                    "note": (
                        "Transcript not supplied; "
                        "no claim is made about "
                        "unseen video content."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            summary="YouTube metadata only.",
            tags=[
                "FIN[SYS]",
                "YouTube",
            ],
            metadata=metadata,
        )

        return {
            "source_id": source_id,
            "title": title,
            "metadata_only": True,
        }

    combined_text = (
        f"{transcript}\n\n"
        f"ADDITIONAL CONTEXT:\n"
        f"{extra_context}"
    ).strip()

    result = ingest_text(
        title=title,
        text=combined_text,
        source_url=youtube_url,
        source_type="youtube_transcript",
        author=author,
        tags=[
            "FIN[SYS]",
            "YouTube",
        ],
    )

    return {
        "source_id": result["source_id"],
        "title": title,
        "metadata_only": False,
        "knowledge_ids": result[
            "knowledge_ids"
        ],
    }


# =========================================================
# GRAFİK / GÖRSEL ANALİZ
# =========================================================

def ingest_chart_image(
    image_path: str,
    source_title: str,
    source_url: str | None = None,
) -> dict[str, Any]:

    path = Path(
        image_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Görsel bulunamadı: {path}"
        )

    mime_type = (
        mimetypes.guess_type(
            path.name
        )[0]
        or "image/png"
    )

    image_bytes = path.read_bytes()

    encoded = base64.b64encode(
        image_bytes
    ).decode("ascii")

    image_data_url = (
        f"data:{mime_type};base64,"
        f"{encoded}"
    )

    source_id = add_knowledge_source(
        source_type="fin_sys_chart",
        title=source_title,
        url=source_url,
        author="FIN[SYS]",
        access_note=(
            "Only analyze visuals the user "
            "is authorized to process."
        ),
        metadata={
            "file_name": path.name
        },
    )

    visual_asset_id = add_visual_asset(
        file_path=str(
            path.resolve()
        ),
        asset_type="chart",
        source_id=source_id,
        description=(
            "FIN[SYS] chart screenshot "
            "for visual analysis."
        ),
    )

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
Bu FIN[SYS] grafik ekran görüntüsünü
bilgi çıkarımı amacıyla analiz et.

SADECE JSON DÖNDÜR:

{
    "summary": "...",
    "visible_instruments": [],
    "visible_timeframe": "...",
    "visible_indicators": [
        {
            "name": "...",
            "visible_role": "...",
            "visible_signal": "..."
        }
    ],
    "chart_structures": [],
    "explicit_levels": [],
    "cautions": []
}

Kurallar:

- Görselde görünmeyen değer uydurma.
- Görselde görünmeyen sembol uydurma.
- Görselde görünmeyen indikatör uydurma.
- Görselde görünmeyen zaman dilimi uydurma.
- Görülen bilgi ile yorumu ayır.
""",
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                    },
                ],
            }
        ],
    )

    raw = response.output_text.strip()

    try:
        structured = json.loads(raw)

    except json.JSONDecodeError as error:

        raise ValueError(
            "Grafik analizi geçerli JSON "
            "döndürmedi:\n"
            f"{raw[:1000]}"
        ) from error

    knowledge_id = add_knowledge_item(
        source_id=source_id,
        item_type="chart_analysis",
        title=source_title,
        content=json.dumps(
            structured,
            ensure_ascii=False,
            indent=2,
        ),
        summary=structured.get(
            "summary",
            "",
        ),
        symbols=structured.get(
            "visible_instruments",
            [],
        ) or [],
        tags=[
            "FIN[SYS]",
            "grafik",
            "TradingView",
        ],
        confidence=0.65,
        metadata={
            "visual_asset_id": visual_asset_id
        },
    )

    return {
        "source_id": source_id,
        "visual_asset_id": visual_asset_id,
        "knowledge_id": knowledge_id,
        "analysis": structured,
    }


# =========================================================
# FIN[SYS] BİLGİ ARAMA
# =========================================================

def retrieve_relevant_knowledge(
    query: str,
    limit: int = 8,
) -> list[dict[str, Any]]:

    return search_knowledge(
        query,
        limit=limit,
    )


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    print("=== FIN[SYS] ENGINE ===")

    try:

        count = seed_public_catalog()

        print(
            f"✅ FIN[SYS] public katalog "
            f"hazırlandı: {count} konu"
        )

    except Exception as error:

        print(
            f"❌ FIN[SYS] Engine hatası: {error}"
        )
