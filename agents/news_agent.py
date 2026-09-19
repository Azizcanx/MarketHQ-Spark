import requests
import xml.etree.ElementTree as ET

URL = "https://feeds.bbci.co.uk/news/business/rss.xml"

KEYWORDS = [
    "stock",
    "stocks",
    "market",
    "nasdaq",
    "s&p",
    "fed",
    "federal reserve",
    "inflation",
    "interest rate",
    "wall street",
    "investor",
    "shares",
    "economy",
    "economic",
    "us economy",
    "bond",
    "bonds",
    "ipo",
    "dow",
    "recession",
    "economic downturn",
]


def get_news():
    print("📰 News Agent: Haberleri tarıyorum...\n")

    response = requests.get(URL, timeout=10)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    news = []

    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published = item.findtext("pubDate") or ""
        description = item.findtext("description") or ""

        article = {
            "id": link.strip(),
            "title": title.strip(),
            "published": published.strip(),
            "source": "BBC",
            "link": link.strip(),
            "description": description.strip(),
        }

        news.append(article)

    return news


def remove_duplicates(news):
    unique_news = []
    seen_ids = set()

    for article in news:
        article_id = article["id"]

        if article_id and article_id not in seen_ids:
            seen_ids.add(article_id)
            unique_news.append(article)

    return unique_news


def detect_categories(title):
    title_lower = title.lower()
    categories = []

    if any(word in title_lower for word in [
        "fed",
        "federal reserve",
        "central bank"
    ]):
        categories.append("Merkez Bankası / Fed")

    if any(word in title_lower for word in [
        "interest rate",
        "rate cut",
        "rate hike",
        "borrowing costs"
    ]):
        categories.append("Faiz")

    if any(word in title_lower for word in [
        "inflation",
        "prices",
        "cost of living"
    ]):
        categories.append("Enflasyon")

    if any(word in title_lower for word in [
        "stock",
        "stocks",
        "shares"
    ]):
        categories.append("Hisse Senetleri")

    if any(word in title_lower for word in [
        "nasdaq",
        "s&p",
        "dow",
        "wall street"
    ]):
        categories.append("Endeksler")

    if any(word in title_lower for word in [
        "bond",
        "bonds",
        "treasury",
        "yield"
    ]):
        categories.append("Tahviller")

    if any(word in title_lower for word in [
        "economy",
        "economic",
        "recession",
        "economic downturn",
        "growth"
    ]):
        categories.append("Ekonomi")

    if any(word in title_lower for word in [
        "ipo",
        "company",
        "shares debut",
        "stock market debut"
    ]):
        categories.append("Şirket Haberleri")

    if any(word in title_lower for word in [
        "ai",
        "artificial intelligence",
        "technology",
        "tech"
    ]):
        categories.append("Teknoloji / AI")

    if any(word in title_lower for word in [
        "bitcoin",
        "crypto",
        "cryptocurrency"
    ]):
        categories.append("Kripto")

    if any(word in title_lower for word in [
        "war",
        "sanctions",
        "geopolitical",
        "geopolitics"
    ]):
        categories.append("Jeopolitik")

    if not categories:
        categories.append("Diğer")

    return categories


def detect_assets(title):
    title_lower = title.lower()
    assets = []

    if any(word in title_lower for word in [
        "nasdaq",
        "technology",
        "tech",
        "ai"
    ]):
        assets.append("NASDAQ")

    if any(word in title_lower for word in [
        "s&p",
        "wall street",
        "stocks",
        "shares"
    ]):
        assets.append("S&P 500")

    if any(word in title_lower for word in [
        "fed",
        "federal reserve",
        "interest rate",
        "inflation"
    ]):
        assets.append("USD")

    if any(word in title_lower for word in [
        "bond",
        "bonds",
        "treasury",
        "yield",
        "borrowing costs"
    ]):
        assets.append("ABD Tahvilleri")

    if any(word in title_lower for word in [
        "bitcoin",
        "crypto",
        "cryptocurrency"
    ]):
        assets.append("Bitcoin")

    return assets


def enrich_news(news):
    enriched_news = []

    for article in news:
        article["categories"] = detect_categories(article["title"])
        article["assets"] = detect_assets(article["title"])

        enriched_news.append(article)

    return enriched_news


def filter_news(news):
    filtered = []

    for article in news:
        title_lower = article["title"].lower()

        if any(keyword in title_lower for keyword in KEYWORDS):
            filtered.append(article)

    return filtered


def prepare_news():
    all_news = get_news()

    unique_news = remove_duplicates(all_news)

    filtered_news = filter_news(unique_news)

    enriched_news = enrich_news(filtered_news)

    return enriched_news
