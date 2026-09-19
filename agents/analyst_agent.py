import os
import json

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError("OPENAI_API_KEY bulunamadı.")

client = OpenAI(api_key=api_key)


# =========================================================
# MARKET HQ'NUN İZİN VERDİĞİ TAKİP ARAÇLARI
# =========================================================

INSTRUMENT_CATALOG = [
    {
        "symbol": "THYAO.IS",
        "name": "Türk Hava Yolları",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "ASELS.IS",
        "name": "ASELSAN",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "GARAN.IS",
        "name": "Garanti BBVA",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "AKBNK.IS",
        "name": "Akbank",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "EREGL.IS",
        "name": "Ereğli Demir Çelik",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "TUPRS.IS",
        "name": "Tüpraş",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "SISE.IS",
        "name": "Şişecam",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "BIMAS.IS",
        "name": "BİM",
        "type": "stock",
        "market": "BIST",
    },
    {
        "symbol": "AAPL",
        "name": "Apple",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "AMZN",
        "name": "Amazon",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "META",
        "name": "Meta Platforms",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "TSLA",
        "name": "Tesla",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "AVGO",
        "name": "Broadcom",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "BKNG",
        "name": "Booking Holdings",
        "type": "stock",
        "market": "US",
    },
    {
        "symbol": "^IXIC",
        "name": "NASDAQ Composite",
        "type": "index",
        "market": "US",
    },
    {
        "symbol": "^GSPC",
        "name": "S&P 500",
        "type": "index",
        "market": "US",
    },
    {
        "symbol": "^DJI",
        "name": "Dow Jones",
        "type": "index",
        "market": "US",
    },
    {
        "symbol": "XU030.IS",
        "name": "BIST 30",
        "type": "index",
        "market": "BIST",
    },
    {
        "symbol": "XU100.IS",
        "name": "BIST 100",
        "type": "index",
        "market": "BIST",
    },
    {
        "symbol": "^TNX",
        "name": "US 10Y Treasury Yield",
        "type": "yield",
        "market": "US",
    },
    {
        "symbol": "DX-Y.NYB",
        "name": "US Dollar Index",
        "type": "currency_index",
        "market": "US",
    },
]


def get_catalog_text():
    lines = []

    for item in INSTRUMENT_CATALOG:
        lines.append(
            f"- {item['symbol']} | "
            f"{item['name']} | "
            f"{item['type']} | "
            f"{item['market']}"
        )

    return "\n".join(lines)


def clean_analysis(analysis):

    if not isinstance(analysis, dict):
        analysis = {}

    result = {
        "relevant": False,
        "summary": "Analiz alınamadı.",
        "importance": 1,
        "market_direction": "Belirsiz",
        "affected_assets": [],
        "target_instruments": [],
        "reason": "Yeterli analiz verisi bulunamadı.",
        "confidence": "Düşük",
    }

    result.update(analysis)

    result["relevant"] = bool(
        result.get("relevant", False)
    )

    try:
        importance = int(
            result.get("importance", 1)
        )
    except (ValueError, TypeError):
        importance = 1

    result["importance"] = max(
        1,
        min(10, importance)
    )

    valid_confidence = [
        "Düşük",
        "Orta",
        "Yüksek",
    ]

    if result.get("confidence") not in valid_confidence:
        result["confidence"] = "Düşük"

    valid_directions = [
        "Pozitif",
        "Negatif",
        "Karışık",
        "Belirsiz",
    ]

    if result.get("market_direction") not in valid_directions:
        result["market_direction"] = "Belirsiz"

    if not isinstance(
        result.get("affected_assets"),
        list,
    ):
        result["affected_assets"] = []

    if not isinstance(
        result.get("target_instruments"),
        list,
    ):
        result["target_instruments"] = []

    valid_symbols = {
        item["symbol"]
        for item in INSTRUMENT_CATALOG
    }

    cleaned_targets = []

    for target in result["target_instruments"]:

        if not isinstance(target, dict):
            continue

        symbol = str(
            target.get("symbol", "")
        ).strip()

        if symbol not in valid_symbols:
            continue

        catalog_item = next(
            item
            for item in INSTRUMENT_CATALOG
            if item["symbol"] == symbol
        )

        cleaned_targets.append({
            "symbol": catalog_item["symbol"],
            "type": catalog_item["type"],
            "name": catalog_item["name"],
            "market": catalog_item["market"],
        })

    result["target_instruments"] = cleaned_targets

    # Düşük önem seviyesindeki haberleri
    # ana sinyal sistemine sokmuyoruz.
    if result["importance"] < 5:
        result["relevant"] = False
        result["market_direction"] = "Belirsiz"
        result["target_instruments"] = []

    if not result["relevant"]:
        result["affected_assets"] = []
        result["target_instruments"] = []

    return result


def analyze_article(article):

    catalog_text = get_catalog_text()

    prompt = f"""
Sen Market HQ'nun finans piyasaları Analyst Agent'ısın.

Görevin verilen haberi analiz etmek ve yalnızca
izin verilen finansal araçlar arasından gerçekten
etkilenebilecek araçları seçmektir.

HABER

Başlık:
{article["title"]}

Tarih:
{article["published"]}

Kaynak:
{article["source"]}

RSS açıklaması:
{article.get("description", "Açıklama bulunamadı.")}

Kategoriler:
{", ".join(article.get("categories", [])) or "Belirlenemedi"}

News Agent varlıkları:
{", ".join(article.get("assets", [])) or "Belirlenemedi"}

========================
İZİNLİ TAKİP ARAÇLARI
========================

{catalog_text}

========================
KURALLAR
========================

1. Sadece yukarıdaki katalogda bulunan sembolleri kullan.

2. Katalogda olmayan hiçbir sembol uydurma.

3. Haberde açıkça desteklenmeyen bir aracı seçme.

4. Ancak haber bir şirketin markasından bahsediyorsa
   ve o marka katalogdaki halka açık şirketin markasıysa,
   o şirket hissesi hedef araç olabilir.

5. Örneğin:
   Booking.com → Booking Holdings → BKNG
   ancak yalnızca haber gerçekten Booking.com'u konu alıyorsa.

6. "Bond market", "Treasury", "10-year yield" gibi ifadelerde:
   haber ABD 10 yıllık tahvil getirileriyle açıkça ilişkilendirilebiliyorsa
   ^TNX seçilebilir.

7. Teknoloji hisselerini yalnızca haberin doğrudan veya güçlü
   makro etkisi varsa seç. Her teknoloji haberinde NASDAQ seçme.

8. Genel ve düşük etkili ekonomik haberlerde:
   relevant = false
   importance = 1-4

9. Ana sinyal olarak yalnızca importance >= 5 olan haberleri değerlendir.

10. Sadece başlıktan kesin fiyat tahmini yapma.

11. Kesin "yükselir" veya "düşer" deme.

12. Veri yetersizse target_instruments boş olabilir.

13. Yatırım tavsiyesi verme.

IMPORTANCE:

1-3 = çok düşük
4-5 = düşük
6-7 = orta/yüksek
8-9 = yüksek
10 = olağanüstü önemli

CONFIDENCE:

Düşük / Orta / Yüksek

MARKET_DIRECTION:

Pozitif / Negatif / Karışık / Belirsiz

SADECE geçerli JSON döndür.

FORMAT:

{{
    "relevant": true,
    "summary": "Kısa ve tarafsız özet.",
    "importance": 1,
    "market_direction": "Pozitif / Negatif / Karışık / Belirsiz",
    "affected_assets": [],
    "target_instruments": [
        {{
            "symbol": "BKNG",
            "type": "stock",
            "name": "Booking Holdings",
            "market": "US"
        }}
    ],
    "reason": "Piyasa açısından değerlendirme.",
    "confidence": "Düşük / Orta / Yüksek"
}}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    text = response.output_text.strip()

    try:
        analysis = json.loads(text)

    except json.JSONDecodeError:

        analysis = {
            "relevant": False,
            "summary": text,
            "importance": 1,
            "market_direction": "Belirsiz",
            "affected_assets": [],
            "target_instruments": [],
            "reason": "AI geçerli JSON döndürmedi.",
            "confidence": "Düşük",
        }

    return clean_analysis(analysis)


def analyze_news(news):

    analyzed_news = []

    for article in news:

        analysis = analyze_article(
            article
        )

        analyzed_news.append({
            **article,
            "analysis": analysis,
        })

    return analyzed_news
