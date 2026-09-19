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

API_BASE = (
    "https://www.googleapis.com/youtube/v3"
)

# İlk testte sadece 10 video.
# Sistem sağlam çalıştıktan sonra artıracağız.
TEST_VIDEO_LIMIT = int(
    os.getenv(
        "YOUTUBE_TRANSCRIPT_TEST_LIMIT",
        "10"
    )
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
        CREATE TABLE IF NOT EXISTS youtube_caption_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL,

            caption_id TEXT,

            language TEXT,

            name TEXT,

            track_kind TEXT,

            is_draft INTEGER,

            is_auto_generated INTEGER,

            status TEXT,

            raw_metadata TEXT,

            discovered_at TEXT,
            updated_at TEXT,

            UNIQUE(video_id, caption_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL UNIQUE,

            transcript_status TEXT NOT NULL,

            transcript_text TEXT,

            language TEXT,

            source TEXT,

            error_message TEXT,

            checked_at TEXT,

            updated_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_youtube_transcript_status
        ON youtube_transcripts(transcript_status)
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

    return str(value).strip()


def parse_int(
    value: Any
) -> Optional[int]:

    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


# ============================================================
# YOUTUBE API
# ============================================================

def youtube_get(
    endpoint: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not YOUTUBE_API_KEY:

        raise RuntimeError(
            "YOUTUBE_API_KEY bulunamadı."
        )

    request_params = dict(
        params
    )

    request_params["key"] = (
        YOUTUBE_API_KEY
    )

    response = requests.get(
        f"{API_BASE}/{endpoint}",
        params=request_params,
        timeout=30
    )

    if response.status_code != 200:

        try:
            error = response.json()

        except Exception:
            error = response.text

        raise RuntimeError(
            f"YouTube API HTTP "
            f"{response.status_code}: "
            f"{error}"
        )

    return response.json()


# ============================================================
# LOAD QUEUE
# ============================================================

def load_test_videos(
    limit: int
) -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_processing_queue"
    ):
        conn.close()

        raise RuntimeError(
            "youtube_processing_queue bulunamadı.\n"
            "Önce youtube_queue.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT
            q.video_id,
            q.channel_id,
            q.priority,
            q.status,
            v.title,
            v.published_at,
            v.youtube_url,
            v.captions_available
        FROM youtube_processing_queue q
        JOIN youtube_videos v
            ON v.video_id = q.video_id
        WHERE q.status='queued'
        ORDER BY
            q.priority DESC,
            v.published_at DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


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
        (table_name,)
    ).fetchone()

    return row is not None


# ============================================================
# CAPTION METADATA
# ============================================================

def get_caption_tracks(
    video_id: str
) -> Dict[str, Any]:

    """
    Official YouTube Data API:
    captions.list

    Bu fonksiyon SADECE caption track metadata'sını
    almaya çalışır.

    Gerçek caption metnini indirmez.
    """

    data = youtube_get(
        "captions",
        {
            "part": "id,snippet",
            "videoId": video_id,
        }
    )

    return data


# ============================================================
# SAVE CAPTION TRACK
# ============================================================

def save_caption_track(
    video_id: str,
    item: Dict[str, Any]
) -> None:

    snippet = item.get(
        "snippet",
        {}
    )

    caption_id = normalize(
        item.get("id")
    )

    if not caption_id:
        return

    now = now_iso()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO youtube_caption_tracks (
            video_id,
            caption_id,
            language,
            name,
            track_kind,
            is_draft,
            is_auto_generated,
            status,
            raw_metadata,
            discovered_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )

        ON CONFLICT(
            video_id,
            caption_id
        )
        DO UPDATE SET
            language=excluded.language,
            name=excluded.name,
            track_kind=excluded.track_kind,
            is_draft=excluded.is_draft,
            is_auto_generated=excluded.is_auto_generated,
            status=excluded.status,
            raw_metadata=excluded.raw_metadata,
            updated_at=excluded.updated_at
        """,
        (
            video_id,
            caption_id,

            normalize(
                snippet.get(
                    "language"
                )
            ),

            normalize(
                snippet.get(
                    "name"
                )
            ),

            normalize(
                snippet.get(
                    "trackKind"
                )
            ),

            int(
                bool(
                    snippet.get(
                        "isDraft",
                        False
                    )
                )
            ),

            int(
                snippet.get(
                    "trackKind"
                )
                == "ASR"
            ),

            "metadata_available",

            str(
                item
            ),

            now,
            now,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# SAVE TRANSCRIPT STATUS
# ============================================================

def save_transcript_status(
    video_id: str,
    status: str,
    language: str = "",
    source: str = "youtube_api",
    error_message: str = "",
) -> None:

    now = now_iso()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO youtube_transcripts (
            video_id,
            transcript_status,
            transcript_text,
            language,
            source,
            error_message,
            checked_at,
            updated_at
        )
        VALUES (
            ?, ?, NULL, ?, ?, ?, ?, ?
        )

        ON CONFLICT(video_id)
        DO UPDATE SET
            transcript_status=excluded.transcript_status,
            language=excluded.language,
            source=excluded.source,
            error_message=excluded.error_message,
            checked_at=excluded.checked_at,
            updated_at=excluded.updated_at
        """,
        (
            video_id,
            status,
            language,
            source,
            error_message,
            now,
            now,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# PROCESS ONE VIDEO
# ============================================================

def process_video(
    video: Dict[str, Any]
) -> Dict[str, Any]:

    video_id = normalize(
        video["video_id"]
    )

    title = normalize(
        video["title"]
    )

    print()
    print(
        f"🎬 {title}"
    )

    print(
        f"   ID: {video_id}"
    )

    try:

        data = get_caption_tracks(
            video_id
        )

        items = data.get(
            "items",
            []
        )

        if not items:

            save_transcript_status(
                video_id,
                "no_caption_track",
                source="youtube_api"
            )

            return {
                "video_id": video_id,
                "title": title,
                "status": "no_caption_track",
                "tracks": 0,
            }

        languages = []

        for item in items:

            save_caption_track(
                video_id,
                item
            )

            snippet = item.get(
                "snippet",
                {}
            )

            language = normalize(
                snippet.get(
                    "language"
                )
            )

            if language:
                languages.append(
                    language
                )

        # ----------------------------------------------------
        # IMPORTANT:
        # captions.list does not return actual caption text.
        # We therefore do NOT fake a transcript here.
        # ----------------------------------------------------

        language = (
            languages[0]
            if languages
            else ""
        )

        save_transcript_status(
            video_id,
            "caption_metadata_found",
            language=language,
            source="youtube_api"
        )

        return {
            "video_id": video_id,
            "title": title,
            "status": "caption_metadata_found",
            "tracks": len(items),
            "languages": languages,
        }

    except Exception as exc:

        error = str(
            exc
        )

        # YouTube API returned an authorization problem.
        if (
            "403" in error
            or "forbidden" in error.lower()
        ):

            status = (
                "caption_access_denied"
            )

        elif (
            "404" in error
            or "notfound" in error.lower()
        ):

            status = (
                "video_or_caption_not_found"
            )

        else:

            status = (
                "caption_check_failed"
            )

        save_transcript_status(
            video_id,
            status,
            source="youtube_api",
            error_message=error
        )

        return {
            "video_id": video_id,
            "title": title,
            "status": status,
            "tracks": 0,
            "error": error,
        }


# ============================================================
# QUEUE UPDATE
# ============================================================

def update_queue_status_from_transcript(
    video_id: str,
    transcript_status: str
) -> None:

    conn = get_connection()

    if transcript_status == "caption_metadata_found":

        new_status = (
            "transcript_metadata_ready"
        )

    elif transcript_status == "no_caption_track":

        new_status = (
            "transcript_unavailable"
        )

    elif transcript_status == "caption_access_denied":

        new_status = (
            "transcript_access_denied"
        )

    else:

        new_status = (
            "transcript_check_failed"
        )

    conn.execute(
        """
        UPDATE youtube_processing_queue
        SET
            status=?,
            updated_at=?
        WHERE video_id=?
        """,
        (
            new_status,
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# REPORT
# ============================================================

def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    counts: Dict[str, int] = {}

    for result in results:

        status = result[
            "status"
        ]

        counts[
            status
        ] = counts.get(
            status,
            0
        ) + 1

    print()
    print(
        "========================================="
    )

    print(
        "📝 YOUTUBE TRANSCRIPT ENGINE"
    )

    print(
        "========================================="
    )

    print(
        f"Test edilen video: "
        f"{len(results)}"
    )

    for status, count in sorted(
        counts.items()
    ):

        print(
            f"{status}: {count}"
        )

    print(
        "========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print(
        "========================================="
    )

    print(
        "📝 MARKET HQ YOUTUBE TRANSCRIPT ENGINE"
    )

    print(
        "========================================="
    )

    print(
        f"Test limit: "
        f"{TEST_VIDEO_LIMIT}"
    )

    print(
        "API: YouTube Data API"
    )

    print()

    if not YOUTUBE_API_KEY:

        print(
            "❌ YOUTUBE_API_KEY bulunamadı."
        )

        return

    ensure_tables()

    try:

        videos = load_test_videos(
            TEST_VIDEO_LIMIT
        )

    except Exception as exc:

        print(
            f"❌ Video kuyruğu okunamadı: "
            f"{exc}"
        )

        return

    print(
        f"Kuyruktan alınan video: "
        f"{len(videos)}"
    )

    if not videos:

        print(
            "ℹ️ İşlenecek queued video yok."
        )

        return

    results = []

    for video in videos:

        result = process_video(
            video
        )

        update_queue_status_from_transcript(
            video["video_id"],
            result["status"]
        )

        results.append(
            result
        )

        print(
            f"   → {result['status']}"
        )

        if result.get(
            "tracks"
        ):

            print(
                f"   → Caption track: "
                f"{result['tracks']}"
            )

            if result.get(
                "languages"
            ):

                print(
                    f"   → Languages: "
                    f"{', '.join(result['languages'])}"
                )

    print_summary(
        results
    )

    print()
    print(
        "✅ Transcript Engine testi tamamlandı."
    )

    print()
    print(
        "NOT: Bu sürüm gerçek transcript metnini "
        "indirmiyor; yalnızca resmi API üzerinden "
        "caption erişilebilirliğini ve track metadata'sını "
        "kontrol ediyor."
    )


if __name__ == "__main__":
    main()
