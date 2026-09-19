import re
import sys
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import (
    urljoin,
    urlparse,
)

import requests


# =========================================================
# MARKET HQ PROJECT ROOT
# =========================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


from database import (
    add_knowledge_item,
    add_knowledge_source,
    init_db,
)


# =========================================================
# CONFIG
# =========================================================

BASE_URL = "https://www.fin-sys.eu/"

DOMAIN = "www.fin-sys.eu"

MAX_PAGES = 120

REQUEST_TIMEOUT = 15

CRAWL_DELAY = 0.5

USER_AGENT = (
    "MarketHQ-FIN-SYS-PublicCrawler/1.0"
)


# =========================================================
# HTML PARSER
# =========================================================

class PublicPageParser(
    HTMLParser
):

    def __init__(self):

        super().__init__()

        self.links = []

        self.title_parts = []

        self.text_parts = []

        self.in_title = False

        self.skip_depth = 0

    def handle_starttag(
        self,
        tag,
        attrs,
    ):

        tag = tag.lower()

        if tag == "title":

            self.in_title = True

        if tag in {
            "script",
            "style",
            "noscript",
            "svg",
        }:

            self.skip_depth += 1

        if tag == "a":

            attrs_dict = dict(
                attrs
            )

            href = attrs_dict.get(
                "href"
            )

            if href:

                self.links.append(
                    href
                )

    def handle_endtag(
        self,
        tag,
    ):

        tag = tag.lower()

        if tag == "title":

            self.in_title = False

        if tag in {
            "script",
            "style",
            "noscript",
            "svg",
        }:

            if self.skip_depth > 0:

                self.skip_depth -= 1

    def handle_data(
        self,
        data,
    ):

        if self.skip_depth > 0:

            return

        text = data.strip()

        if not text:

            return

        if self.in_title:

            self.title_parts.append(
                text
            )

        self.text_parts.append(
            text
        )

    @property
    def title(self) -> str:

        return clean_text(
            " ".join(
                self.title_parts
            )
        )

    @property
    def text(self) -> str:

        return clean_text(
            " ".join(
                self.text_parts
            )
        )


# =========================================================
# TEXT CLEANER
# =========================================================

def clean_text(
    text: str,
) -> str:

    text = re.sub(
        r"\s+",
        " ",
        text or "",
    )

    return text.strip()


# =========================================================
# URL HELPERS
# =========================================================

def normalize_url(
    url: str,
) -> Optional[str]:

    if not url:

        return None

    url = url.strip()

    if url.startswith(
        (
            "mailto:",
            "javascript:",
            "tel:",
        )
    ):

        return None

    absolute = urljoin(
        BASE_URL,
        url,
    )

    parsed = urlparse(
        absolute
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:

        return None

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    if hostname not in {
        DOMAIN,
        "fin-sys.eu",
    }:

        return None

    clean = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )

    if parsed.query:

        clean += (
            "?"
            + parsed.query
        )

    return clean


# =========================================================
# PUBLIC PAGE DETECTION
# =========================================================

def is_probably_public_content_page(
    url: str,
    title: str,
    text: str,
) -> bool:

    lower_url = url.lower()

    lower_title = title.lower()

    lower_text = text.lower()

    interesting_terms = [
        "algorit",
        "indikat",
        "teknik",
        "python",
        "tradingview",
        "trend",
        "momentum",
        "hacim",
        "filtre",
        "tarama",
        "analiz",
        "borsa",
        "hisse",
        "regresyon",
    ]

    return any(
        term in (
            lower_url
            + " "
            + lower_title
            + " "
            + lower_text[:5000]
        )

        for term in interesting_terms
    )


# =========================================================
# PAGE FETCH
# =========================================================

def fetch_page(
    url: str,
) -> Optional[dict]:

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT
            },
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if "text/html" not in content_type:

            return None

        parser = PublicPageParser()

        parser.feed(
            response.text
        )

        return {
            "url": url,
            "title": parser.title,
            "text": parser.text,
            "links": parser.links,
        }

    except requests.RequestException as error:

        print(
            f"⚠️ Sayfa alınamadı: "
            f"{url}"
        )

        print(
            f"   {error}"
        )

        return None


# =========================================================
# TEXT LIMIT
# =========================================================

def prepare_content(
    text: str,
    max_chars: int = 18000,
) -> str:

    text = clean_text(
        text
    )

    if len(text) <= max_chars:

        return text

    return (
        text[:max_chars]
        + "\n\n"
        "[MarketHQ: public page truncated]"
    )


# =========================================================
# STORE PAGE
# =========================================================

def store_public_page(
    page: dict,
) -> bool:

    url = page["url"]

    title = (
        page["title"]
        or url
    )

    text = prepare_content(
        page["text"]
    )

    if len(text) < 150:

        return False

    if not is_probably_public_content_page(
        url,
        title,
        text,
    ):

        return False

    source_id = add_knowledge_source(
        source_type=(
            "fin_sys_public_web"
        ),

        title=title,

        url=url,

        author="FIN[SYS]",

        access_note=(
            "Public web page metadata/content "
            "collected from the publicly accessible "
            "FIN[SYS] website."
        ),

        metadata={
            "crawler": (
                "MarketHQ FIN[SYS] "
                "Public Crawler"
            ),
        },
    )

    item_type = classify_page(
        url,
        title,
        text,
    )

    add_knowledge_item(
        source_id=source_id,

        item_type=item_type,

        title=title,

        content=text,

        summary=(
            f"Public FIN[SYS] page: "
            f"{title}"
        ),

        method=(
            item_type
        ),

        tags=[
            "FIN[SYS]",
            "public_web",
            item_type,
        ],

        confidence=0.80,

        metadata={
            "url": url,
            "crawler_version": "v1",
        },
    )

    return True


# =========================================================
# CLASSIFICATION
# =========================================================

def classify_page(
    url: str,
    title: str,
    text: str,
) -> str:

    combined = (
        url
        + " "
        + title
        + " "
        + text[:5000]
    ).lower()

    if "tradingview" in combined:

        return "tradingview_method"

    if "python" in combined:

        return "python_method"

    if "algorit" in combined:

        return "algorithm"

    if (
        "indikat"
        in combined
    ):

        return "indicator"

    if "filtre" in combined:

        return "filter"

    if "momentum" in combined:

        return "momentum_method"

    if "regresyon" in combined:

        return "regression_method"

    if "trend" in combined:

        return "trend_method"

    return "fin_sys_public_methodology"


# =========================================================
# CRAWLER
# =========================================================

def crawl(
    start_url: str = BASE_URL,
) -> dict:

    start_url = normalize_url(
        start_url
    )

    if not start_url:

        raise ValueError(
            "Invalid start URL."
        )

    queue = deque()

    queue.append(
        start_url
    )

    visited = set()

    discovered = 0

    stored = 0

    failed = 0

    print(
        "======================================"
    )

    print(
        "🌐 FIN[SYS] PUBLIC CRAWLER"
    )

    print(
        "======================================"
    )

    print(
        f"Başlangıç: {start_url}"
    )

    print(
        f"Maksimum sayfa: {MAX_PAGES}"
    )

    while (
        queue
        and len(visited) < MAX_PAGES
    ):

        url = queue.popleft()

        if url in visited:

            continue

        visited.add(
            url
        )

        discovered += 1

        print()

        print(
            f"[{len(visited)}/{MAX_PAGES}] "
            f"{url}"
        )

        page = fetch_page(
            url
        )

        if page is None:

            failed += 1

            continue

        try:

            if store_public_page(
                page
            ):

                stored += 1

                print(
                    "   ✅ Public bilgi kaydedildi."
                )

            else:

                print(
                    "   ℹ️ Bilgi sayfası olarak "
                    "kaydedilmedi."
                )

        except Exception as error:

            print(
                f"   ❌ Database kayıt hatası: "
                f"{error}"
            )

        # -------------------------------------------------
        # Discover links
        # -------------------------------------------------

        for href in page.get(
            "links",
            []
        ):

            new_url = normalize_url(
                href
            )

            if not new_url:

                continue

            parsed = urlparse(
                new_url
            )

            # Avoid huge external/static files.
            path = (
                parsed.path
                or ""
            ).lower()

            if path.endswith(
                (
                    ".pdf",
                    ".zip",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".webp",
                    ".mp4",
                    ".mp3",
                    ".exe",
                )
            ):

                continue

            if new_url not in visited:

                queue.append(
                    new_url
                )

        time.sleep(
            CRAWL_DELAY
        )

    print()

    print(
        "======================================"
    )

    print(
        "📊 CRAWLER SONUCU"
    )

    print(
        "======================================"
    )

    print(
        f"Keşfedilen sayfa: "
        f"{discovered}"
    )

    print(
        f"Bilgi olarak kaydedilen: "
        f"{stored}"
    )

    print(
        f"Hata alınan: "
        f"{failed}"
    )

    print(
        f"Kuyrukta kalan: "
        f"{len(queue)}"
    )

    return {
        "discovered": discovered,
        "stored": stored,
        "failed": failed,
        "remaining": len(queue),
    }


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    init_db()

    result = crawl(
        BASE_URL
    )

    print()

    print(
        "✅ FIN[SYS] public crawl tamamlandı."
    )

    print(
        f"📚 {result['stored']} public "
        f"sayfa bilgi tabanına aktarıldı."
    )
