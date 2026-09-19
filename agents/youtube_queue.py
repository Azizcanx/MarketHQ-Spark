import os
import sys
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


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

# Tek çalıştırmada kuyruğa alınabilecek maksimum yeni video.
# Bunu sınırlı tutuyoruz.
QUEUE_LIMIT = int(
    os.getenv(
        "YOUTUBE_QUEUE_LIMIT",
        "100"
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


def ensure_queue_table() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_processing_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL UNIQUE,

            channel_id TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'queued',

            priority INTEGER DEFAULT 0,

            attempt_count INTEGER DEFAULT 0,

            error_message TEXT,

            discovered_at TEXT,

            queued_at TEXT,

            started_at TEXT,

            completed_at TEXT,

            updated_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_youtube_queue_status
        ON youtube_processing_queue(status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_youtube_queue_priority
        ON youtube_processing_queue(
            priority DESC,
            queued_at ASC
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

    return str(value).strip()


# ============================================================
# QUEUE BUILD
# ============================================================

def queue_new_videos() -> Dict[str, int]:

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

    videos = conn.execute(
        """
        SELECT
            video_id,
            channel_id,
            status,
            published_at,
            first_seen_at
        FROM youtube_videos
        ORDER BY
            published_at DESC,
            first_seen_at DESC
        """
    ).fetchall()

    queued = 0
    existing = 0
    skipped = 0

    current_time = now_iso()

    for video in videos:

        video_id = normalize(
            video["video_id"]
        )

        channel_id = normalize(
            video["channel_id"]
        )

        if not video_id or not channel_id:
            skipped += 1
            continue

        queue_row = conn.execute(
            """
            SELECT
                status
            FROM youtube_processing_queue
            WHERE video_id=?
            """,
            (video_id,)
        ).fetchone()

        if queue_row:

            existing += 1
            continue

        # ----------------------------------------------------
        # Priority
        # ----------------------------------------------------

        priority = 0

        # Yeni videolara öncelik
        priority += 10

        # Son yayınlanan videoları biraz öne al
        if video["published_at"]:
            priority += 5

        # Caption olması transcript aşamasında avantaj sağlayabilir
        # Bu bilgiyi youtube_videos içinden ayrıca okuyabiliriz.
        caption_row = conn.execute(
            """
            SELECT captions_available
            FROM youtube_videos
            WHERE video_id=?
            """,
            (video_id,)
        ).fetchone()

        if (
            caption_row
            and caption_row["captions_available"] == 1
        ):
            priority += 10

        # ----------------------------------------------------
        # Insert queue
        # ----------------------------------------------------

        try:

            conn.execute(
                """
                INSERT INTO youtube_processing_queue (
                    video_id,
                    channel_id,
                    status,
                    priority,
                    attempt_count,
                    discovered_at,
                    queued_at,
                    updated_at
                )
                VALUES (
                    ?, ?, 'queued', ?, 0,
                    ?, ?, ?
                )
                """,
                (
                    video_id,
                    channel_id,
                    priority,
                    video["first_seen_at"]
                    or current_time,
                    current_time,
                    current_time,
                )
            )

            queued += 1

        except sqlite3.IntegrityError:

            existing += 1

    conn.commit()
    conn.close()

    return {
        "total_videos": len(videos),
        "queued": queued,
        "existing": existing,
        "skipped": skipped,
    }


# ============================================================
# LIMIT QUEUE
# ============================================================

def cap_queue(
    limit: int
) -> int:

    conn = get_connection()

    # Queue'da daha önce oluşturulmuş tüm kayıtlar kalır.
    # Sadece aktif "queued" kayıtların içinden işlem sırası
    # belirlenir.
    rows = conn.execute(
        """
        SELECT id
        FROM youtube_processing_queue
        WHERE status='queued'
        ORDER BY
            priority DESC,
            queued_at ASC
        """
    ).fetchall()

    if len(rows) <= limit:

        conn.close()
        return 0

    # Fazla kayıtları silmiyoruz.
    # Çünkü bunlar sonraki çalıştırmalarda işlenecek.
    # Burada sadece kaç tanesinin hemen işlem için seçileceğini
    # raporluyoruz.
    selected = min(
        len(rows),
        limit
    )

    conn.close()

    return selected


# ============================================================
# FETCH NEXT QUEUE ITEMS
# ============================================================

def get_next_items(
    limit: int
) -> List[Dict[str, Any]]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            q.id,
            q.video_id,
            q.channel_id,
            q.status,
            q.priority,
            q.attempt_count,
            v.title,
            v.description,
            v.published_at,
            v.youtube_url,
            v.duration,
            v.captions_available
        FROM youtube_processing_queue q
        JOIN youtube_videos v
            ON v.video_id = q.video_id
        WHERE q.status='queued'
        ORDER BY
            q.priority DESC,
            v.published_at DESC,
            q.queued_at ASC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# QUEUE STATUS
# ============================================================

def get_queue_statistics() -> Dict[str, int]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            status,
            COUNT(*) AS count
        FROM youtube_processing_queue
        GROUP BY status
        """
    ).fetchall()

    conn.close()

    stats = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    }

    for row in rows:

        status = normalize(
            row["status"]
        )

        if status in stats:

            stats[
                status
            ] = int(
                row["count"]
            )

    return stats


# ============================================================
# UPDATE VIDEO STATUS
# ============================================================

def sync_video_status_from_queue() -> int:

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_videos"
    ):
        conn.close()
        return 0

    mappings = [
        (
            "queued",
            "queued"
        ),
        (
            "processing",
            "processing"
        ),
        (
            "completed",
            "completed"
        ),
        (
            "failed",
            "failed"
        ),
        (
            "skipped",
            "skipped"
        ),
    ]

    updated = 0

    for queue_status, video_status in mappings:

        cursor = conn.execute(
            """
            UPDATE youtube_videos
            SET
                status=?,
                updated_at=?
            WHERE video_id IN (
                SELECT video_id
                FROM youtube_processing_queue
                WHERE status=?
            )
            """,
            (
                video_status,
                now_iso(),
                queue_status,
            )
        )

        updated += cursor.rowcount

    conn.commit()
    conn.close()

    return updated


# ============================================================
# MARK PROCESSING
# ============================================================

def mark_processing(
    video_id: str
) -> bool:

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            id,
            status,
            attempt_count
        FROM youtube_processing_queue
        WHERE video_id=?
        """,
        (video_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False

    current_attempt = int(
        row["attempt_count"]
        or 0
    )

    conn.execute(
        """
        UPDATE youtube_processing_queue
        SET
            status='processing',
            attempt_count=?,
            started_at=?,
            updated_at=?
        WHERE video_id=?
        """,
        (
            current_attempt + 1,
            now_iso(),
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return True


# ============================================================
# MARK COMPLETED
# ============================================================

def mark_completed(
    video_id: str
) -> bool:

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE youtube_processing_queue
        SET
            status='completed',
            completed_at=?,
            updated_at=?,
            error_message=NULL
        WHERE video_id=?
        """,
        (
            now_iso(),
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# MARK FAILED
# ============================================================

def mark_failed(
    video_id: str,
    error_message: str
) -> bool:

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE youtube_processing_queue
        SET
            status='failed',
            error_message=?,
            updated_at=?
        WHERE video_id=?
        """,
        (
            normalize(
                error_message
            )[:4000],
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# RESET FAILED
# ============================================================

def reset_failed(
    max_attempts: int = 3
) -> int:

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE youtube_processing_queue
        SET
            status='queued',
            error_message=NULL,
            updated_at=?
        WHERE status='failed'
        AND attempt_count < ?
        """,
        (
            now_iso(),
            max_attempts,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount


# ============================================================
# REPORT
# ============================================================

def print_queue_report() -> None:

    stats = get_queue_statistics()

    print()
    print(
        "========================================="
    )

    print(
        "📋 YOUTUBE PROCESSING QUEUE"
    )

    print(
        "========================================="
    )

    print(
        f"Queued:      {stats['queued']}"
    )

    print(
        f"Processing:  {stats['processing']}"
    )

    print(
        f"Completed:   {stats['completed']}"
    )

    print(
        f"Failed:      {stats['failed']}"
    )

    print(
        f"Skipped:     {stats['skipped']}"
    )

    print(
        "========================================="
    )


def print_next_items(
    limit: int = 20
) -> None:

    items = get_next_items(
        limit
    )

    print()
    print(
        "SONRAKİ İŞLENECEK VİDEOLAR"
    )

    print(
        "-----------------------------------------"
    )

    if not items:

        print(
            "Kuyruk boş."
        )

        return

    for index, item in enumerate(
        items,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{item['title']}"
        )

        print(
            f"    ID: "
            f"{item['video_id']}"
        )

        print(
            f"    Priority: "
            f"{item['priority']}"
        )

        print(
            f"    Captions: "
            f"{'YES' if item['captions_available'] else 'NO'}"
        )

        print(
            f"    Status: "
            f"{item['status']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print(
        "========================================="
    )

    print(
        "📋 MARKET HQ YOUTUBE QUEUE"
    )

    print(
        "========================================="
    )

    print(
        f"Queue limit: {QUEUE_LIMIT}"
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_queue_table()

    try:

        stats = queue_new_videos()

    except Exception as exc:

        print(
            f"❌ Queue oluşturulamadı: {exc}"
        )

        return

    synced = sync_video_status_from_queue()

    print(
        "QUEUE BUILD"
    )

    print(
        "-----------------------------------------"
    )

    print(
        f"Toplam video: "
        f"{stats['total_videos']}"
    )

    print(
        f"Yeni kuyruğa alınan: "
        f"{stats['queued']}"
    )

    print(
        f"Zaten kuyrukta: "
        f"{stats['existing']}"
    )

    print(
        f"Atlanan: "
        f"{stats['skipped']}"
    )

    print(
        f"Video status senkronizasyonu: "
        f"{synced}"
    )

    selected_count = cap_queue(
        QUEUE_LIMIT
    )

    print()
    print(
        f"Bu çalıştırmada öncelikli "
        f"işlem adayı: "
        f"{selected_count}"
    )

    print_queue_report()

    print_next_items(
        min(
            QUEUE_LIMIT,
            20
        )
    )

    print()
    print(
        "✅ YouTube Queue tamamlandı."
    )

    print()
    print(
        "Henüz transcript veya grafik analizi yapılmadı."
    )

    print(
        "Kuyruk sistemi yalnızca hangi videoların "
        "sonraki aşamaya gireceğini yönetiyor."
    )


if __name__ == "__main__":
    main()
