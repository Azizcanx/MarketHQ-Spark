import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from agents.market_data_agent import get_bist_data


# =========================================================
# TÜRKİYE HABERLERİ
# =========================================================

def prepare_turkey_news():
    """
    Türkiye / BIST odaklı haberleri Google News RSS üzerinden toplar.

    Analyst Agent'in beklediği alanlar:
    - title
    - url
    - source
    - published
    - published_at
    - market
    - country
    - type
    """

    queries = [
        "Borsa İstanbul BIST",
        "BIST 30",
        "Borsa İstanbul şirket haberleri",
    ]

    results = []

    for query in queries:

        try:
            params = urllib.parse.urlencode(
                {
                    "q": query,
                    "hl": "tr",
                    "gl": "TR",
                    "ceid": "TR:tr",
                }
            )

            url = (
                "https://news.google.com/rss/search?"
                + params
            )

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MarketHQ/1.0"
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=15,
            ) as response:

                xml_data = response.read()

            root = ET.fromstring(xml_data)

            for item in root.findall(".//item"):

                title_element = item.find("title")
                link_element = item.find("link")
                source_element = item.find("source")
                date_element = item.find("pubDate")

                title = (
                    title_element.text
                    if title_element is not None
                    else ""
                )

                link = (
                    link_element.text
                    if link_element is not None
                    else ""
                )

                source = (
                    source_element.text
                    if source_element is not None
                    else "Google News"
                )

                pub_date = (
                    date_element.text
                    if date_element is not None
                    else None
                )

                if not title or not link:
                    continue

                results.append(
                    {
                        "title": title.strip(),

                        "url": link.strip(),

                        "source": (
                            source.strip()
                            if source
                            else "Google News"
                        ),

                        # Analyst Agent'in beklediği alan
                        "published": (
                            pub_date.strip()
                            if pub_date
                            else None
                        ),

                        # Diğer sistemler için standart alan
                        "published_at": (
                            pub_date.strip()
                            if pub_date
                            else None
                        ),

                        "market": "BIST",

                        "country": "Türkiye",

                        "type": "news",
                    }
                )

        except Exception as exc:

            print(
                f"⚠️ Türkiye haber kaynağı "
                f"alınamadı ({query}): {exc}"
            )

    # =====================================================
    # DUPLICATE TEMİZLEME
    # =====================================================

    unique = {}

    for item in results:

        item_url = item.get("url")

        if not item_url:
            continue

        if item_url not in unique:
            unique[item_url] = item

    return list(unique.values())[:30]


# =========================================================
# TÜRKİYE PİYASA VERİSİ
# =========================================================

def get_turkey_market_data():
    """
    BIST piyasa verilerini mevcut Market Data Agent
    üzerinden alır.
    """

    try:

        return get_bist_data()

    except Exception as exc:

        print(
            f"❌ Türkiye piyasa verisi alınamadı: {exc}"
        )

        return []


# =========================================================
# ŞİRKET BİLDİRİMLERİ
# =========================================================

def get_company_updates():
    """
    KAP şirket bildirimleri için hazırlık katmanı.

    KAP tarafında yetkili API bağlantısı kurulana kadar
    boş liste döndürür.
    """

    return []
