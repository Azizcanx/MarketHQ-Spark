import os
import sys
import sqlite3
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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
# ENV
# ============================================================

from dotenv import load_dotenv

load_dotenv(
    os.path.join(
        PROJECT_ROOT,
        ".env"
    )
)

YOUTUBE_API_KEY = os.getenv(
    "YOUTUBE_API_KEY"
)

FIN_SYS_CHANNEL_ID = os.getenv(
    "FIN_SYS_CHANNEL_ID",
    "UCy8Z7BlLYfdqOvpxqGKNQFA"
)

API_BASE = (
    "https://www.googleapis.com/youtube/v3"
)


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def ensure_tables() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            channel_id TEXT NOT NULL UNIQUE,

            channel_name TEXT,

            uploads_playlist_id TEXT,

            enabled INTEGER DEFAULT 1,

            last_checked_at TEXT,

            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL UNIQUE,

            channel_id TEXT NOT NULL,

            title TEXT,

            description TEXT,

            published_at TEXT,

            thumbnail_url TEXT,

            youtube_url TEXT,

            duration TEXT,

            view_count INTEGER,

            like_count INTEGER,

            comment_count INTEGER,

            captions_available INTEGER,

            status TEXT DEFAULT 'discovered',

            first_seen_at TEXT,

            last_seen_at TEXT,

            created_at TEXT,

            updated_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# YOUTUBE API
# ============================================================

def youtube_get(
    endpoint: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not YOUTUBE_API_KEY:

        raise RuntimeError(
            "YOUTUBE_API_KEY bulunamadı.\n"
            ".env dosyasını kontrol et."
        )

    request_params = dict(
        params
    )

    request_params["key"] = (
        YOUTUBE_API_KEY
    )

    url = (
        f"{API_BASE}/{endpoint}"
    )

    response = requests.get(
        url,
        params=request_params,
        timeout=30
    )

    if response.status_code != 200:

        try:
            error_data = response.json()

        except Exception:
            error_data = response.text

        raise RuntimeError(
            "YouTube API hatası:\n"
            f"HTTP {response.status_code}\n"
            f"{error_data}"
        )

    return response.json()


# ============================================================
# CHANNEL
# ============================================================

def get_channel_info(
    channel_id: str
) -> Dict[str, Any]:

    data = youtube_get(
        "channels",
        {
            "part": "snippet,contentDetails",
            "id": channel_id,
        }
    )

    items = data.get(
        "items",
        []
    )

    if not items:

        raise RuntimeError(
            f"Kanal bulunamadı: "
            f"{channel_id}"
        )

    channel = items[0]

    snippet = channel.get(
        "snippet",
        {}
    )

    content_details = channel.get(
        "contentDetails",
        {}
    )

    related_playlists = (
        content_details.get(
            "relatedPlaylists",
            {}
        )
    )

    uploads_playlist_id = (
        related_playlists.get(
            "uploads"
        )
    )

    return {
        "channel_id": channel.get(
            "id",
            channel_id
        ),

        "channel_name": snippet.get(
            "title",
            ""
        ),

        "description": snippet.get(
            "description",
            ""
        ),

        "published_at": snippet.get(
            "publishedAt",
            ""
        ),

        "thumbnail_url": (
            snippet
            .get(
                "thumbnails",
                {}
            )
            .get(
                "high",
                {}
            )
            .get(
                "url",
                ""
            )
        ),

        "uploads_playlist_id": (
            uploads_playlist_id
        ),
    }


# ============================================================
# SAVE CHANNEL
# ============================================================

def save_channel(
    channel: Dict[str, Any]
) -> None:

    now = datetime.now(
        timezone.utc
    ).isoformat()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO youtube_channels (
            channel_id,
            channel_name,
            uploads_playlist_id,
            enabled,
            last_checked_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 1, ?, ?, ?)

        ON CONFLICT(channel_id)
        DO UPDATE SET
            channel_name =
                excluded.channel_name,

            uploads_playlist_id =
                excluded.uploads_playlist_id,

            updated_at =
                excluded.updated_at
        """,
        (
            channel["channel_id"],
            channel["channel_name"],
            channel["uploads_playlist_id"],
            now,
            now,
            now,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# PLAYLIST
# ============================================================

def get_uploads(
    playlist_id: str
) -> List[Dict[str, Any]]:

    videos = []

    next_page_token = None

    while True:

        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }

        if next_page_token:
            params[
                "pageToken"
            ] = next_page_token

        data = youtube_get(
            "playlistItems",
            params
        )

        items = data.get(
            "items",
            []
        )

        for item in items:

            snippet = item.get(
                "snippet",
                {}
            )

            content_details = item.get(
                "contentDetails",
                {}
            )

            resource = snippet.get(
                "resourceId",
                {}
            )

            video_id = resource.get(
                "videoId"
            )

            if not video_id:
                continue

            thumbnails = snippet.get(
                "thumbnails",
                {}
            )

            thumbnail_url = (
                thumbnails
                .get(
                    "high",
                    thumbnails.get(
                        "medium",
                        thumbnails.get(
                            "default",
                            {}
                        )
                    )
                )
                .get(
                    "url",
                    ""
                )
            )

            videos.append(
                {
                    "video_id": video_id,

                    "title": snippet.get(
                        "title",
                        ""
                    ),

                    "description": snippet.get(
                        "description",
                        ""
                    ),

                    "published_at": snippet.get(
                        "publishedAt",
                        ""
                    ),

                    "thumbnail_url": (
                        thumbnail_url
                    ),

                    "youtube_url": (
                        f"https://www.youtube.com/"
                        f"watch?v={video_id}"
                    ),

                    "position": snippet.get(
                        "position"
                    ),

                    "playlist_published_at": (
                        content_details.get(
                            "videoPublishedAt",
                            ""
                        )
                    ),
                }
            )

        next_page_token = data.get(
            "nextPageToken"
        )

        if not next_page_token:
            break

    return videos


# ============================================================
# VIDEO DETAILS
# ============================================================

def get_video_details(
    video_ids: List[str]
) -> Dict[str, Dict[str, Any]]:

    if not video_ids:
        return {}

    result = {}

    # YouTube API allows comma-separated video IDs.
    for start in range(
        0,
        len(video_ids),
        50
    ):

        batch = video_ids[
            start:start + 50
        ]

        data = youtube_get(
            "videos",
            {
                "part": (
                    "snippet,"
                    "contentDetails,"
                    "statistics,"
                    "status"
                ),

                "id": ",".join(
                    batch
                )
            }
        )

        for video in data.get(
            "items",
            []
        ):

            video_id = video.get(
                "id"
            )

            if not video_id:
                continue

            snippet = video.get(
                "snippet",
                {}
            )

            content_details = video.get(
                "contentDetails",
                {}
            )

            statistics = video.get(
                "statistics",
                {}
            )

            result[
                video_id
            ] = {
                "duration": content_details.get(
                    "duration",
                    ""
                ),

                "view_count": parse_int(
                    statistics.get(
                        "viewCount"
                    )
                ),

                "like_count": parse_int(
                    statistics.get(
                        "likeCount"
                    )
                ),

                "comment_count": parse_int(
                    statistics.get(
                        "commentCount"
                    )
                ),

                "captions_available": (
                    content_details.get(
                        "caption"
                    ) == "true"
                ),

                "channel_id": snippet.get(
                    "channelId"
                ),

                "category_id": snippet.get(
                    "categoryId"
                ),
            }

    return result


# ============================================================
# INTEGER
# ============================================================

def parse_int(
    value: Any
) -> Optional[int]:

    if value is None:
        return None

    try:
        return int(
            value
        )

    except Exception:
        return None


# ============================================================
# SAVE VIDEOS
# ============================================================

def save_videos(
    channel_id: str,
    videos: List[Dict[str, Any]],
    details: Dict[str, Dict[str, Any]]
) -> Dict[str, int]:

    now = datetime.now(
        timezone.utc
    ).isoformat()

    inserted = 0
    existing = 0

    conn = get_connection()

    for video in videos:

        video_id = video[
            "video_id"
        ]

        detail = details.get(
            video_id,
            {}
        )

        existing_row = conn.execute(
            """
            SELECT id
            FROM youtube_videos
            WHERE video_id=?
            """,
            (
                video_id,
            )
        ).fetchone()

        if existing_row:

            existing += 1

            conn.execute(
                """
                UPDATE youtube_videos
                SET
                    title=?,
                    description=?,
                    published_at=?,
                    thumbnail_url=?,
                    youtube_url=?,
                    duration=?,
                    view_count=?,
                    like_count=?,
                    comment_count=?,
                    captions_available=?,
                    last_seen_at=?,
                    updated_at=?
                WHERE video_id=?
                """,
                (
                    video["title"],
                    video["description"],
                    video["published_at"],
                    video["thumbnail_url"],
                    video["youtube_url"],
                    detail.get(
                        "duration"
                    ),
                    detail.get(
                        "view_count"
                    ),
                    detail.get(
                        "like_count"
                    ),
                    detail.get(
                        "comment_count"
                    ),
                    int(
                        bool(
                            detail.get(
                                "captions_available",
                                False
                            )
                        )
                    ),
                    now,
                    now,
                    video_id,
                )
            )

        else:

            inserted += 1

            conn.execute(
                """
                INSERT INTO youtube_videos (
                    video_id,
                    channel_id,
                    title,
                    description,
                    published_at,
                    thumbnail_url,
                    youtube_url,
                    duration,
                    view_count,
                    like_count,
                    comment_count,
                    captions_available,
                    status,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, 'discovered',
                    ?, ?, ?, ?
                )
                """,
                (
                    video_id,
                    channel_id,
                    video["title"],
                    video["description"],
                    video["published_at"],
                    video["thumbnail_url"],
                    video["youtube_url"],
                    detail.get(
                        "duration"
                    ),
                    detail.get(
                        "view_count"
                    ),
                    detail.get(
                        "like_count"
                    ),
                    detail.get(
                        "comment_count"
                    ),
                    int(
                        bool(
                            detail.get(
                                "captions_available",
                                False
                            )
                        )
                    ),
                    now,
                    now,
                    now,
                    now,
                )
            )

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "existing": existing,
    }


# ============================================================
# FETCH CHANNEL
# ============================================================

def discover_channel(
    channel_id: str
) -> Dict[str, Any]:

    print(
        f"Kanal kontrol ediliyor: "
        f"{channel_id}"
    )

    channel = get_channel_info(
        channel_id
    )

    print(
        f"Kanal: "
        f"{channel['channel_name']}"
    )

    print(
        f"Uploads playlist: "
        f"{channel['uploads_playlist_id']}"
    )

    if not channel[
        "uploads_playlist_id"
    ]:

        raise RuntimeError(
            "Kanalın uploads playlist'i alınamadı."
        )

    save_channel(
        channel
    )

    videos = get_uploads(
        channel[
            "uploads_playlist_id"
        ]
    )

    print(
        f"Bulunan video: "
        f"{len(videos)}"
    )

    if not videos:

        return {
            "channel": channel,
            "videos": [],
            "stats": {
                "inserted": 0,
                "existing": 0,
            }
        }

    video_ids = [
        video[
            "video_id"
        ]
        for video in videos
    ]

    details = get_video_details(
        video_ids
    )

    stats = save_videos(
        channel[
            "channel_id"
        ],
        videos,
        details
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    conn = get_connection()

    conn.execute(
        """
        UPDATE youtube_channels
        SET last_checked_at=?,
            updated_at=?
        WHERE channel_id=?
        """,
        (
            now,
            now,
            channel[
                "channel_id"
            ],
        )
    )

    conn.commit()
    conn.close()

    return {
        "channel": channel,
        "videos": videos,
        "details": details,
        "stats": stats,
    }


# ============================================================
# RECENT REPORT
# ============================================================

def print_recent_videos(
    channel_id: str,
    limit: int = 15
) -> None:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            video_id,
            title,
            published_at,
            duration,
            captions_available,
            status
        FROM youtube_videos
        WHERE channel_id=?
        ORDER BY published_at DESC
        LIMIT ?
        """,
        (
            channel_id,
            limit
        )
    ).fetchall()

    conn.close()

    print()

    print(
        "SON VİDEOLAR"
    )

    print(
        "-----------------------------------------"
    )

    for index, row in enumerate(
        rows,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{row['title']}"
        )

        print(
            f"    ID: {row['video_id']}"
        )

        print(
            f"    Published: "
            f"{row['published_at']}"
        )

        print(
            f"    Duration: "
            f"{row['duration'] or 'unknown'}"
        )

        print(
            f"    Captions: "
            f"{'YES' if row['captions_available'] else 'NO'}"
        )

        print(
            f"    Status: "
            f"{row['status']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=========================================")
    print("📺 MARKET HQ YOUTUBE DISCOVERY")
    print("=========================================")

    print(
        f"FIN[SYS] channel: "
        f"{FIN_SYS_CHANNEL_ID}"
    )

    print()

    if not YOUTUBE_API_KEY:

        print(
            "❌ YOUTUBE_API_KEY bulunamadı."
        )

        print(
            ".env dosyasında:"
        )

        print(
            "YOUTUBE_API_KEY=..."
        )

        return

    ensure_tables()

    try:

        result = discover_channel(
            FIN_SYS_CHANNEL_ID
        )

    except Exception as exc:

        print()
        print(
            "❌ Discovery başarısız:"
        )

        print(
            exc
        )

        return

    stats = result[
        "stats"
    ]

    print()
    print(
        "========================================="
    )

    print(
        "DISCOVERY SONUCU"
    )

    print(
        "-----------------------------------------"
    )

    print(
        f"Kanal: "
        f"{result['channel']['channel_name']}"
    )

    print(
        f"Toplam çekilen kayıt: "
        f"{len(result['videos'])}"
    )

    print(
        f"Yeni video: "
        f"{stats['inserted']}"
    )

    print(
        f"Daha önce bulunan: "
        f"{stats['existing']}"
    )

    print(
        "========================================="
    )

    print_recent_videos(
        FIN_SYS_CHANNEL_ID
    )

    print()
    print(
        "✅ YouTube Discovery tamamlandı."
    )

    print()
    print(
        "Henüz transcript veya grafik analizi yapılmadı."
    )

    print(
        "Bu aşama yalnızca video keşfi ve metadata toplama aşamasıdır."
    )


if __name__ == "__main__":
    main()
