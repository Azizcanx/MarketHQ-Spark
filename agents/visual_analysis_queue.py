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

VISUAL_QUEUE_LIMIT = int(
    os.getenv(
        "VISUAL_QUEUE_LIMIT",
        "3"
    )
)


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
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


def ensure_table() -> None:

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS visual_analysis_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL UNIQUE,
            channel_id TEXT,

            pilot_group TEXT,
            method_name TEXT,
            focus_type TEXT,

            status TEXT NOT NULL DEFAULT 'queued',

            priority INTEGER DEFAULT 0,

            frame_scan_status TEXT DEFAULT 'pending',
            vision_status TEXT DEFAULT 'pending',
            evidence_status TEXT DEFAULT 'pending',

            attempt_count INTEGER DEFAULT 0,

            error_message TEXT,

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
        idx_visual_queue_status
        ON visual_analysis_queue(status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_visual_queue_priority
        ON visual_analysis_queue(
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


def normalize(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# LOAD PILOTS
# ============================================================

def load_pilots() -> List[Dict[str, Any]]:

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_pilots"
    ):
        conn.close()

        raise RuntimeError(
            "youtube_pilots tablosu bulunamadı.\n"
            "Önce youtube_pilot_manager.py çalıştır."
        )

    rows = conn.execute(
        """
        SELECT
            p.video_id,
            p.method_name,
            p.focus_type,
            p.priority,
            p.pilot_group,

            v.channel_id,
            v.title,
            v.published_at,
            v.youtube_url,
            v.duration

        FROM youtube_pilots p

        LEFT JOIN youtube_videos v
            ON v.video_id = p.video_id

        ORDER BY
            p.priority DESC

        LIMIT ?
        """,
        (
            VISUAL_QUEUE_LIMIT,
        )
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# QUEUE PILOTS
# ============================================================

def queue_pilots(
    pilots: List[Dict[str, Any]]
) -> Dict[str, int]:

    conn = get_connection()

    inserted = 0
    existing = 0

    timestamp = now_iso()

    for pilot in pilots:

        video_id = normalize(
            pilot.get(
                "video_id"
            )
        )

        if not video_id:
            continue

        existing_row = conn.execute(
            """
            SELECT
                id,
                status
            FROM visual_analysis_queue
            WHERE video_id=?
            """,
            (
                video_id,
            )
        ).fetchone()

        if existing_row:

            existing += 1

            # Kuyrukta zaten varsa metadata'yı güncelle.
            conn.execute(
                """
                UPDATE visual_analysis_queue
                SET
                    channel_id=?,
                    pilot_group=?,
                    method_name=?,
                    focus_type=?,
                    priority=?,
                    updated_at=?
                WHERE video_id=?
                """,
                (
                    pilot.get(
                        "channel_id"
                    ),

                    pilot.get(
                        "pilot_group"
                    ),

                    pilot.get(
                        "method_name"
                    ),

                    pilot.get(
                        "focus_type"
                    ),

                    pilot.get(
                        "priority",
                        0
                    ),

                    timestamp,

                    video_id,
                )
            )

            continue

        conn.execute(
            """
            INSERT INTO visual_analysis_queue (
                video_id,
                channel_id,

                pilot_group,
                method_name,
                focus_type,

                status,
                priority,

                frame_scan_status,
                vision_status,
                evidence_status,

                attempt_count,

                error_message,

                queued_at,
                updated_at
            )
            VALUES (
                ?, ?,
                ?, ?, ?,
                'queued', ?,
                'pending',
                'pending',
                'pending',
                0,
                NULL,
                ?, ?
            )
            """,
            (
                video_id,

                pilot.get(
                    "channel_id"
                ),

                pilot.get(
                    "pilot_group"
                ),

                pilot.get(
                    "method_name"
                ),

                pilot.get(
                    "focus_type"
                ),

                pilot.get(
                    "priority",
                    0
                ),

                timestamp,
                timestamp,
            )
        )

        inserted += 1

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "existing": existing,
    }


# ============================================================
# QUEUE STATISTICS
# ============================================================

def get_statistics() -> Dict[str, int]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            status,
            COUNT(*) AS count
        FROM visual_analysis_queue
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
# NEXT VISUAL ITEMS
# ============================================================

def get_next_visual_items(
    limit: int = 10
) -> List[Dict[str, Any]]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            q.id,
            q.video_id,
            q.channel_id,

            q.pilot_group,
            q.method_name,
            q.focus_type,

            q.status,
            q.priority,

            q.frame_scan_status,
            q.vision_status,
            q.evidence_status,

            v.title,
            v.youtube_url,
            v.duration,
            v.published_at

        FROM visual_analysis_queue q

        LEFT JOIN youtube_videos v
            ON v.video_id = q.video_id

        WHERE q.status='queued'

        ORDER BY
            q.priority DESC,
            v.published_at DESC

        LIMIT ?
        """,
        (
            limit,
        )
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


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
            attempt_count,
            status
        FROM visual_analysis_queue
        WHERE video_id=?
        """,
        (
            video_id,
        )
    ).fetchone()

    if not row:

        conn.close()
        return False

    attempt_count = int(
        row["attempt_count"]
        or 0
    )

    now = now_iso()

    cursor = conn.execute(
        """
        UPDATE visual_analysis_queue
        SET
            status='processing',
            attempt_count=?,
            started_at=?,
            updated_at=?,
            error_message=NULL
        WHERE video_id=?
        """,
        (
            attempt_count + 1,
            now,
            now,
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# MARK FRAME SCAN
# ============================================================

def mark_frame_scan(
    video_id: str,
    status: str
) -> bool:

    allowed = {
        "pending",
        "processing",
        "completed",
        "failed",
    }

    if status not in allowed:
        status = "failed"

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE visual_analysis_queue
        SET
            frame_scan_status=?,
            updated_at=?
        WHERE video_id=?
        """,
        (
            status,
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# MARK VISION
# ============================================================

def mark_vision(
    video_id: str,
    status: str
) -> bool:

    allowed = {
        "pending",
        "processing",
        "completed",
        "failed",
    }

    if status not in allowed:
        status = "failed"

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE visual_analysis_queue
        SET
            vision_status=?,
            updated_at=?
        WHERE video_id=?
        """,
        (
            status,
            now_iso(),
            video_id,
        )
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


# ============================================================
# MARK COMPLETE
# ============================================================

def mark_completed(
    video_id: str
) -> bool:

    now = now_iso()

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE visual_analysis_queue
        SET
            status='completed',
            completed_at=?,
            updated_at=?,
            error_message=NULL
        WHERE video_id=?
        """,
        (
            now,
            now,
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
        UPDATE visual_analysis_queue
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
        UPDATE visual_analysis_queue
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

    stats = get_statistics()

    print()
    print(
        "========================================="
    )

    print(
        "🎨 VISUAL ANALYSIS QUEUE"
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
    limit: int = 10
) -> None:

    items = get_next_visual_items(
        limit
    )

    print()
    print(
        "GÖRSEL ANALİZE GİRECEK VİDEOLAR"
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
            f"{item['method_name']}"
        )

        print(
            f"    Video: "
            f"{item['title'] or 'Unknown'}"
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
            f"    Frame scan: "
            f"{item['frame_scan_status']}"
        )

        print(
            f"    Vision: "
            f"{item['vision_status']}"
        )

        print(
            f"    Evidence: "
            f"{item['evidence_status']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print(
        "========================================="
    )

    print(
        "🎨 MARKET HQ VISUAL ANALYSIS QUEUE"
    )

    print(
        "========================================="
    )

    print(
        f"Pilot limit: "
        f"{VISUAL_QUEUE_LIMIT}"
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_table()

    try:

        pilots = load_pilots()

    except Exception as exc:

        print(
            f"❌ Pilotlar okunamadı: "
            f"{exc}"
        )

        return

    print(
        f"Pilot video: "
        f"{len(pilots)}"
    )

    if not pilots:

        print(
            "❌ Pilot video bulunamadı."
        )

        print(
            "Önce:"
        )

        print(
            "python agents/youtube_pilot_manager.py"
        )

        return

    result = queue_pilots(
        pilots
    )

    print()
    print(
        "QUEUE BUILD"
    )

    print(
        "-----------------------------------------"
    )

    print(
        f"Yeni visual queue: "
        f"{result['inserted']}"
    )

    print(
        f"Zaten mevcut: "
        f"{result['existing']}"
    )

    print_queue_report()

    print_next_items(
        VISUAL_QUEUE_LIMIT
    )

    print()
    print(
        "✅ Visual Analysis Queue tamamlandı."
    )

    print()
    print(
        "Henüz hiçbir frame veya grafik "
        "Vision ile analiz edilmedi."
    )


if __name__ == "__main__":
    main()
