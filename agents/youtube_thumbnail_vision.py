import os
import sys
import json
import base64
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

import requests


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

THUMBNAIL_DIR = os.path.join(
    PROJECT_ROOT,
    "youtube_analysis",
    "thumbnails"
)


# ============================================================
# ENV
# ============================================================

from dotenv import load_dotenv

load_dotenv(
    os.path.join(
        PROJECT_ROOT,
        ".env"
    )
)

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
)


# ============================================================
# PILOT VIDEOS
# ============================================================

PILOT_VIDEOS = {
    "siUhYKVwL-Q": {
        "method_name": "BUM",
        "priority": 100,
    },

    "OlHPgcgUTk8": {
        "method_name": "Bluesky",
        "priority": 95,
    },

    "zj1Brlqb5dE": {
        "method_name": "TrendMultiCalc",
        "priority": 90,
    },
}


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def ensure_table() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_visual_observations (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL,

            method_name TEXT,

            image_type TEXT NOT NULL,

            image_path TEXT,

            image_url TEXT,

            instrument TEXT,
            timeframe TEXT,

            chart_visible INTEGER,

            chart_type TEXT,

            indicators TEXT,
            support_levels TEXT,
            resistance_levels TEXT,

            trend_lines TEXT,
            channels TEXT,
            bands TEXT,
            formations TEXT,

            signal_markers TEXT,
            visible_numeric_levels TEXT,

            annotations TEXT,
            visual_summary TEXT,

            confidence REAL,

            raw_ai_response TEXT,

            model TEXT,

            analyzed_at TEXT,

            UNIQUE(
                video_id,
                image_type
            )
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize(
    value: Any
) -> str:

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


def normalize_confidence(
    value: Any
) -> float:
    """
    AI bazen 0.9, bazen 90, bazen 0-1 aralığında
    güven skoru döndürebilir.

    Biz DB içinde daima 0-100 tutuyoruz.

    0.0 - 1.0 -> x100
    1.0        -> 100
    90         -> 90
    100        -> 100
    """

    confidence = safe_float(
        value,
        0.0
    )

    if confidence < 0:
        confidence = 0.0

    if confidence <= 1.0:
        confidence *= 100.0

    confidence = max(
        0.0,
        min(
            100.0,
            confidence
        )
    )

    return confidence


def ensure_list(
    value: Any
):

    if value is None:
        return []

    if isinstance(
        value,
        list
    ):
        return value

    return [value]


# ============================================================
# THUMBNAIL URL
# ============================================================

def get_thumbnail_urls(
    video_id: str
):

    return [
        (
            "maxres",
            f"https://i.ytimg.com/vi/"
            f"{video_id}/maxresdefault.jpg"
        ),

        (
            "standard",
            f"https://i.ytimg.com/vi/"
            f"{video_id}/sddefault.jpg"
        ),

        (
            "high",
            f"https://i.ytimg.com/vi/"
            f"{video_id}/hqdefault.jpg"
        ),
    ]


# ============================================================
# DOWNLOAD THUMBNAIL
# ============================================================

def download_thumbnail(
    video_id: str
) -> Dict[str, Any]:

    os.makedirs(
        THUMBNAIL_DIR,
        exist_ok=True
    )

    for image_type, url in get_thumbnail_urls(
        video_id
    ):

        try:

            response = requests.get(
                url,
                timeout=20
            )

        except requests.RequestException:

            continue

        if response.status_code != 200:
            continue

        content = response.content

        if len(content) < 10_000:
            continue

        filename = (
            f"{video_id}__"
            f"{image_type}.jpg"
        )

        path = os.path.join(
            THUMBNAIL_DIR,
            filename
        )

        with open(
            path,
            "wb"
        ) as file:

            file.write(
                content
            )

        return {
            "image_type": image_type,
            "url": url,
            "path": path,
        }

    raise RuntimeError(
        f"Thumbnail alınamadı: "
        f"{video_id}"
    )


# ============================================================
# IMAGE DATA URL
# ============================================================

def image_to_data_url(
    image_path: str
) -> str:

    with open(
        image_path,
        "rb"
    ) as file:

        encoded = base64.b64encode(
            file.read()
        ).decode(
            "utf-8"
        )

    return (
        "data:image/jpeg;base64,"
        + encoded
    )


# ============================================================
# OPENAI
# ============================================================

def get_openai_client():

    if not OPENAI_API_KEY:

        raise RuntimeError(
            "OPENAI_API_KEY bulunamadı."
        )

    from openai import OpenAI

    return OpenAI(
        api_key=OPENAI_API_KEY
    )


def build_prompt(
    method_name: str,
    video_id: str
) -> str:

    return f"""
Sen MarketHQ'nun görsel piyasa grafiği analiz ajanısın.

Video ID:
{video_id}

Method:
{method_name}

Bu görüntü bir YouTube thumbnail'ıdır.

GÖREV:
Görüntüde gerçekten görülen grafik bilgilerini tespit et.

ÇOK ÖNEMLİ KURALLAR:

1. Sadece görüntüde açıkça görülen bilgileri raporla.

2. Görünmeyen indikatörleri tahmin etme.

3. Okunamayan sayıları uydurma.

4. Thumbnail'daki genel tasarımdan bir yöntemin
   bütün teknik yapısını çıkarma.

5. Bir grafik varsa:
   - enstrüman
   - zaman dilimi
   - grafik tipi
   - görünür indikatörler
   - görünür destek
   - görünür direnç
   - görünür trend çizgileri
   - görünür kanallar
   - görünür bantlar
   - formasyonlar
   - AL/SAT işaretleri
   - görünür fiyat/seviye değerleri
   tespit edilmeye çalışılmalı.

6. Yazı yeterince okunmuyorsa UNKNOWN yaz.

7. Görselde bir alanın gerçekten mevcut olup olmadığı
   belirsizse boş liste veya UNKNOWN kullan.

8. Bu görüntü videonun tamamını temsil etmez.

9. Thumbnail'da görülen bir indikatör, videonun bütününde
   kesin olarak kullanılıyor anlamına gelmez.

10. Yatırım tavsiyesi verme.

11. FIN[SYS] metodunun başarılı, başarısız veya kârlı
    olduğu sonucuna varma.

GÜVEN SKORU:

0-100 arası bir sayı ver.

100:
Görüntü çok net, tespitler açık.

80-99:
Görüntü genel olarak net.

60-79:
Bazı bilgiler net, bazıları belirsiz.

40-59:
Sınırlı görsel bilgi var.

0-39:
Görüntü teknik analiz için çok belirsiz.

SADECE JSON döndür.

Format:

{{
    "method_name": "{method_name}",
    "video_id": "{video_id}",
    "image_type": "thumbnail",

    "chart_visible": true,

    "chart_type": "candlestick",

    "instrument": "UNKNOWN",

    "timeframe": "UNKNOWN",

    "indicators": [],

    "support_levels": [],

    "resistance_levels": [],

    "trend_lines": [],

    "channels": [],

    "bands": [],

    "formations": [],

    "signal_markers": [],

    "visible_numeric_levels": [],

    "annotations": [],

    "visual_summary": "",

    "confidence": 0
}}
"""


def analyze_image(
    method_name: str,
    video_id: str,
    image_path: str
) -> Dict[str, Any]:

    client = get_openai_client()

    image_data_url = image_to_data_url(
        image_path
    )

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_prompt(
                            method_name,
                            video_id
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "high",
                    },
                ],
            }
        ],
    )

    raw = response.output_text.strip()

    if raw.startswith(
        "```"
    ):

        lines = raw.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip()
            == "```"
        ):
            lines = lines[:-1]

        raw = "\n".join(
            lines
        )

        if raw.startswith(
            "json"
        ):
            raw = raw[4:].lstrip()

    try:

        result = json.loads(
            raw
        )

    except json.JSONDecodeError:

        raise RuntimeError(
            "Vision JSON parse edilemedi.\n"
            f"AI çıktısı:\n{raw[:6000]}"
        )

    if not isinstance(
        result,
        dict
    ):

        raise RuntimeError(
            "Vision sonucu JSON object değil."
        )

    # Confidence'ı DB için 0-100 standardına çek.
    result["confidence"] = normalize_confidence(
        result.get(
            "confidence"
        )
    )

    return result


# ============================================================
# SAVE
# ============================================================

def save_observation(
    video_id: str,
    method_name: str,
    source: Dict[str, Any],
    result: Dict[str, Any]
) -> None:

    confidence = normalize_confidence(
        result.get(
            "confidence"
        )
    )

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO youtube_visual_observations (

            video_id,
            method_name,

            image_type,
            image_path,
            image_url,

            instrument,
            timeframe,

            chart_visible,
            chart_type,

            indicators,
            support_levels,
            resistance_levels,

            trend_lines,
            channels,
            bands,
            formations,

            signal_markers,
            visible_numeric_levels,

            annotations,
            visual_summary,

            confidence,

            raw_ai_response,
            model,
            analyzed_at
        )
        VALUES (
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?,
            ?, ?, ?
        )

        ON CONFLICT(
            video_id,
            image_type
        )
        DO UPDATE SET

            method_name=excluded.method_name,

            image_path=excluded.image_path,
            image_url=excluded.image_url,

            instrument=excluded.instrument,
            timeframe=excluded.timeframe,

            chart_visible=excluded.chart_visible,
            chart_type=excluded.chart_type,

            indicators=excluded.indicators,
            support_levels=excluded.support_levels,
            resistance_levels=excluded.resistance_levels,

            trend_lines=excluded.trend_lines,
            channels=excluded.channels,
            bands=excluded.bands,
            formations=excluded.formations,

            signal_markers=excluded.signal_markers,
            visible_numeric_levels=excluded.visible_numeric_levels,

            annotations=excluded.annotations,
            visual_summary=excluded.visual_summary,

            confidence=excluded.confidence,

            raw_ai_response=excluded.raw_ai_response,

            model=excluded.model,
            analyzed_at=excluded.analyzed_at
        """,
        (
            video_id,
            method_name,

            source["image_type"],
            source["path"],
            source["url"],

            normalize(
                result.get(
                    "instrument"
                )
            ),

            normalize(
                result.get(
                    "timeframe"
                )
            ),

            int(
                bool(
                    result.get(
                        "chart_visible",
                        False
                    )
                )
            ),

            normalize(
                result.get(
                    "chart_type"
                )
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "indicators"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "support_levels"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "resistance_levels"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "trend_lines"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "channels"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "bands"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "formations"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "signal_markers"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "visible_numeric_levels"
                    )
                ),
                ensure_ascii=False
            ),

            json.dumps(
                ensure_list(
                    result.get(
                        "annotations"
                    )
                ),
                ensure_ascii=False
            ),

            normalize(
                result.get(
                    "visual_summary"
                )
            ),

            confidence,

            json.dumps(
                result,
                ensure_ascii=False
            ),

            MODEL,

            now_iso(),
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# REPORT
# ============================================================

def print_result(
    method_name: str,
    source: Dict[str, Any],
    result: Dict[str, Any]
) -> None:

    print()
    print(
        f"• {method_name}"
    )

    print(
        f"  Thumbnail: "
        f"{source['image_type']}"
    )

    print(
        f"  Chart visible: "
        f"{'YES' if result.get('chart_visible') else 'NO'}"
    )

    print(
        f"  Instrument: "
        f"{result.get('instrument', 'UNKNOWN')}"
    )

    print(
        f"  Timeframe: "
        f"{result.get('timeframe', 'UNKNOWN')}"
    )

    indicators = ensure_list(
        result.get(
            "indicators"
        )
    )

    print(
        f"  Indicators: "
        f"{', '.join(
            str(x) for x in indicators
        ) if indicators else 'none'}"
    )

    support = ensure_list(
        result.get(
            "support_levels"
        )
    )

    print(
        f"  Support: "
        f"{', '.join(
            str(x) for x in support
        ) if support else 'none'}"
    )

    resistance = ensure_list(
        result.get(
            "resistance_levels"
        )
    )

    print(
        f"  Resistance: "
        f"{', '.join(
            str(x) for x in resistance
        ) if resistance else 'none'}"
    )

    markers = ensure_list(
        result.get(
            "signal_markers"
        )
    )

    print(
        f"  Signal markers: "
        f"{', '.join(
            str(x) for x in markers
        ) if markers else 'none'}"
    )

    print(
        f"  Confidence: "
        f"{normalize_confidence(
            result.get(
                'confidence'
            )
        ):.1f}/100"
    )

    print(
        f"  Summary: "
        f"{normalize(
            result.get(
                'visual_summary'
            )
        )[:500]}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================="
    )

    print(
        "👁️ MARKET HQ YOUTUBE THUMBNAIL VISION"
    )

    print(
        "========================================="
    )

    print(
        f"Model: "
        f"{MODEL}"
    )

    print(
        "Pilot video: 3"
    )

    print()

    if not OPENAI_API_KEY:

        print(
            "❌ OPENAI_API_KEY bulunamadı."
        )

        return

    os.makedirs(
        THUMBNAIL_DIR,
        exist_ok=True
    )

    ensure_table()

    results = []

    for video_id, data in (
        PILOT_VIDEOS.items()
    ):

        method_name = data[
            "method_name"
        ]

        print()
        print(
            "-----------------------------------------"
        )

        print(
            f"🎬 {method_name}"
        )

        print(
            f"   Video ID: "
            f"{video_id}"
        )

        try:

            source = download_thumbnail(
                video_id
            )

            print(
                f"   Thumbnail: "
                f"{source['image_type']}"
            )

            result = analyze_image(
                method_name,
                video_id,
                source["path"]
            )

            save_observation(
                video_id,
                method_name,
                source,
                result
            )

            print_result(
                method_name,
                source,
                result
            )

            results.append(
                {
                    "method_name": method_name,
                    "status": "success",
                    "result": result,
                }
            )

        except Exception as exc:

            print(
                f"   ❌ Hata: "
                f"{exc}"
            )

            results.append(
                {
                    "method_name": method_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    print()
    print(
        "========================================="
    )

    print(
        "🎯 VISION PILOT SONUCU"
    )

    print(
        "========================================="
    )

    success = sum(
        1
        for item in results
        if item["status"]
        == "success"
    )

    failed = (
        len(results)
        - success
    )

    print(
        f"Başarılı: "
        f"{success}"
    )

    print(
        f"Başarısız: "
        f"{failed}"
    )

    print()
    print(
        f"Thumbnail klasörü:"
    )

    print(
        THUMBNAIL_DIR
    )

    print()
    print(
        "✅ YouTube Thumbnail Vision tamamlandı."
    )

    print()
    print(
        "NOT: Bunlar yalnızca thumbnail analizleridir."
    )

    print(
        "Video içindeki tüm grafik karelerini temsil etmez."
    )


if __name__ == "__main__":
    main()
