import os
import sys
import sqlite3
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


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


# ============================================================
# CONFIG
# ============================================================

# Her kategori için kullanılabilecek anahtar kelimeler.
# Bu sürüm tamamen deterministic çalışır.
CATEGORY_RULES = {
    "algorithm": [
        "algoritma",
        "algorithm",
        "sistem",
        "system",
        "alım satım algoritması",
        "alış satış sistemi",
        "al-sat",
        "sinyal",
        "signal",
        "python sinyal",
        "python tarama",
    ],

    "methodology": [
        "eğitimi",
        "eğitim",
        "giriş",
        "önbilgilendirme",
        "indikatör",
        "indikator",
        "teknik analiz",
        "strateji",
        "metodoloji",
    ],

    "stock_analysis": [
        "hisse analizi",
        "hisse senedi",
        "hisse yorumu",
        "borsa hisse",
        "aselsan",
        "asels",
        "enka",
        "en kai",
        "thyao",
        "tuprs",
        "tupras",
        "sise",
        "garanti",
        "akbank",
        "eregl",
        "froto",
        "bimas",
        "kchol",
        "sahol",
        "tcell",
        "pgsus",
        "toaso",
        "petkm",
        "sasa",
        "astor",
        "mavi",
        "migros",
    ],

    "market_analysis": [
        "bist 100",
        "bist100",
        "bist 30",
        "bist30",
        "endeks",
        "borsa yorum",
        "borsa değerlendirme",
        "piyasa değerlendirme",
        "piyasa yorum",
        "genel yatırım",
        "piyasa görünümü",
        "konjonktür",
    ],

    "tradingview": [
        "tradingview",
        "pine script",
        "pine",
        "alarm",
        "webhook",
    ],

    "python": [
        "python",
        "kodlama",
        "kod",
        "scanner",
        "tarama kodu",
        "python tarama",
        "python sinyal",
    ],

    "education": [
        "kur1",
        "kur 1",
        "kur2",
        "kur 2",
        "bölüm",
        "ders",
        "eğitim",
        "eğitimi",
        "öğren",
        "öğretici",
    ],

    "webinar": [
        "webinar",
        "web seminer",
        "seminer",
        "toplantı",
        "zoom",
    ],

    "general": [],
}


# Kategori önceliği.
# Bir video birden fazla kategoriye uyuyorsa
# üstteki kategori daha yüksek öncelikli kabul edilir.
CATEGORY_PRIORITY = [
    "algorithm",
    "python",
    "tradingview",
    "webinar",
    "methodology",
    "education",
    "stock_analysis",
    "market_analysis",
    "general",
]


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
        WHERE type='table'
        AND name=?
        """,
        (
            table_name,
        )
    ).fetchone()

    return row is not None


def ensure_columns() -> None:

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_videos"
    ):
        conn.close()

        raise RuntimeError(
            "youtube_videos tablosu bulunamadı.\n"
            "Önce youtube_discovery.py çalıştır."
        )

    columns = {
        row["name"]
        for row in conn.execute(
            """
            PRAGMA table_info(
                youtube_videos
            )
            """
        ).fetchall()
    }

    required_columns = {
        "video_category":
            "TEXT DEFAULT 'general'",

        "classification_score":
            "REAL DEFAULT 0",

        "classification_reason":
            "TEXT",

        "analysis_priority":
            "INTEGER DEFAULT 0",

        "classified_at":
            "TEXT",
    }

    for column_name, definition in (
        required_columns.items()
    ):

        if column_name not in columns:

            conn.execute(
                f"""
                ALTER TABLE youtube_videos
                ADD COLUMN {column_name}
                {definition}
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


def clean_text(
    text: str
) -> str:

    text = normalize(
        text
    )

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ============================================================
# SCORE CATEGORY
# ============================================================

def score_category(
    title: str,
    description: str,
    category: str
) -> Tuple[int, List[str]]:

    title_clean = clean_text(
        title
    )

    description_clean = clean_text(
        description
    )

    combined = (
        title_clean
        + " "
        + description_clean
    )

    rules = CATEGORY_RULES.get(
        category,
        []
    )

    score = 0
    reasons = []

    for keyword in rules:

        keyword_clean = clean_text(
            keyword
        )

        if not keyword_clean:
            continue

        # Başlıkta geçmesi açıklamaya göre
        # çok daha güçlü kanıt.
        if keyword_clean in title_clean:

            score += 15

            reasons.append(
                f"title:{keyword}"
            )

        elif keyword_clean in description_clean:

            score += 5

            reasons.append(
                f"description:{keyword}"
            )

        elif keyword_clean in combined:

            score += 2

    return score, reasons


# ============================================================
# CLASSIFY
# ============================================================

def classify_video(
    title: str,
    description: str
) -> Dict[str, Any]:

    category_scores = {}

    for category in CATEGORY_RULES:

        score, reasons = score_category(
            title,
            description,
            category
        )

        category_scores[
            category
        ] = {
            "score": score,
            "reasons": reasons,
        }

    ranked_categories = sorted(
        category_scores.items(),
        key=lambda item: (
            item[1]["score"],
            -CATEGORY_PRIORITY.index(
                item[0]
            )
            if item[0]
            in CATEGORY_PRIORITY
            else 0,
        ),
        reverse=True
    )

    best_category = "general"
    best_score = 0
    best_reasons = []

    for category, data in ranked_categories:

        if data["score"] <= 0:
            continue

        best_category = category

        best_score = data["score"]

        best_reasons = data[
            "reasons"
        ]

        break

    # --------------------------------------------------------
    # Special handling:
    # Method/algorithm videos should get more priority.
    # --------------------------------------------------------

    priority_map = {
        "algorithm": 100,
        "python": 92,
        "tradingview": 90,
        "methodology": 88,
        "webinar": 75,
        "education": 70,
        "market_analysis": 60,
        "stock_analysis": 50,
        "general": 20,
    }

    priority = priority_map.get(
        best_category,
        20
    )

    # Stronger evidence increases priority.
    priority += min(
        20,
        best_score // 5
    )

    priority = min(
        120,
        priority
    )

    return {
        "category": best_category,

        "score": best_score,

        "reasons": best_reasons,

        "priority": priority,

        "all_scores": category_scores,
    }


# ============================================================
# LOAD VIDEOS
# ============================================================

def load_videos() -> List[Dict[str, Any]]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            video_id,
            channel_id,
            title,
            description,
            published_at,
            status
        FROM youtube_videos
        ORDER BY
            published_at DESC
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# SAVE CLASSIFICATION
# ============================================================

def save_classification(
    video: Dict[str, Any],
    result: Dict[str, Any]
) -> None:

    conn = get_connection()

    reason_text = "; ".join(
        result["reasons"][:20]
    )

    conn.execute(
        """
        UPDATE youtube_videos
        SET
            video_category=?,
            classification_score=?,
            classification_reason=?,
            analysis_priority=?,
            classified_at=?
        WHERE video_id=?
        """,
        (
            result["category"],
            result["score"],
            reason_text,
            result["priority"],
            now_iso(),
            video["video_id"],
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# CATEGORY SUMMARY
# ============================================================

def print_category_summary(
    classifications: List[Dict[str, Any]]
) -> None:

    counts: Dict[str, int] = {}
    priorities: Dict[str, List[int]] = {}

    for item in classifications:

        category = item[
            "category"
        ]

        counts[
            category
        ] = counts.get(
            category,
            0
        ) + 1

        priorities.setdefault(
            category,
            []
        ).append(
            item["priority"]
        )

    print()
    print(
        "========================================="
    )

    print(
        "📊 VIDEO CATEGORY SUMMARY"
    )

    print(
        "========================================="
    )

    for category in CATEGORY_PRIORITY:

        count = counts.get(
            category,
            0
        )

        if count <= 0:
            continue

        avg_priority = (
            sum(
                priorities[category]
            )
            / len(
                priorities[category]
            )
        )

        print(
            f"{category:18s} "
            f"{count:4d} video "
            f"| avg priority "
            f"{avg_priority:.1f}"
        )

    print(
        "========================================="
    )


# ============================================================
# PRINT HIGH PRIORITY
# ============================================================

def print_high_priority(
    classifications: List[Dict[str, Any]],
    limit: int = 30
) -> None:

    ranked = sorted(
        classifications,
        key=lambda item: (
            item["priority"],
            item["published_at"],
        ),
        reverse=True
    )

    print()
    print(
        "🔥 YÜKSEK ÖNCELİKLİ VİDEOLAR"
    )

    print(
        "-----------------------------------------"
    )

    for index, item in enumerate(
        ranked[:limit],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{item['title']}"
        )

        print(
            f"    Category: "
            f"{item['category']}"
        )

        print(
            f"    Priority: "
            f"{item['priority']}"
        )

        print(
            f"    Score: "
            f"{item['score']}"
        )

        if item["reasons"]:

            print(
                f"    Reason: "
                f"{'; '.join(item['reasons'][:5])}"
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print(
        "========================================="
    )

    print(
        "🏷️ MARKET HQ YOUTUBE VIDEO CLASSIFIER"
    )

    print(
        "========================================="
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_columns()

    videos = load_videos()

    print(
        f"Sınıflandırılacak video: "
        f"{len(videos)}"
    )

    if not videos:

        print(
            "❌ YouTube videosu bulunamadı."
        )

        print(
            "Önce youtube_discovery.py çalıştır."
        )

        return

    classifications = []

    for video in videos:

        result = classify_video(
            video.get(
                "title",
                ""
            ),
            video.get(
                "description",
                ""
            )
        )

        save_classification(
            video,
            result
        )

        classifications.append(
            {
                **result,

                "video_id": video[
                    "video_id"
                ],

                "title": normalize(
                    video.get(
                        "title"
                    )
                ),

                "published_at": normalize(
                    video.get(
                        "published_at"
                    )
                ),
            }
        )

    print_category_summary(
        classifications
    )

    print_high_priority(
        classifications
    )

    print()
    print(
        "✅ YouTube Video Classifier tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Yüksek öncelikli method/algorithm "
        "videolarını transcript + görsel analiz "
        "pipeline'ına yönlendirmek."
    )


if __name__ == "__main__":
    main()
