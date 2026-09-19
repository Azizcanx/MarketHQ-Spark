import os
import sys
import sqlite3
from datetime import datetime, timezone


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
# PILOT VIDEOS
# ============================================================

PILOT_VIDEOS = {
    "siUhYKVwL-Q": {
        "method": "BUM",
        "focus": "algorithm",
        "priority": 100,
    },

    "OlHPgcgUTk8": {
        "method": "Bluesky",
        "focus": "algorithm",
        "priority": 95,
    },

    "zj1Brlqb5dE": {
        "method": "TrendMultiCalc",
        "focus": "trend_method",
        "priority": 90,
    },
}


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def ensure_table():

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_pilots (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL UNIQUE,

            pilot_group TEXT NOT NULL,

            method_name TEXT,

            focus_type TEXT,

            priority INTEGER DEFAULT 0,

            transcript_status TEXT,

            visual_status TEXT,

            evidence_status TEXT,

            notes TEXT,

            created_at TEXT,

            updated_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ============================================================
# HELPERS
# ============================================================

def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# REGISTER PILOT
# ============================================================

def register_pilots():

    conn = get_connection()

    inserted = 0
    existing = 0

    for video_id, data in PILOT_VIDEOS.items():

        row = conn.execute(
            """
            SELECT id
            FROM youtube_pilots
            WHERE video_id=?
            """,
            (
                video_id,
            )
        ).fetchone()

        if row:

            existing += 1

            conn.execute(
                """
                UPDATE youtube_pilots
                SET
                    pilot_group='FIN_SYS_CORE',
                    method_name=?,
                    focus_type=?,
                    priority=?,
                    updated_at=?
                WHERE video_id=?
                """,
                (
                    data["method"],
                    data["focus"],
                    data["priority"],
                    now_iso(),
                    video_id,
                )
            )

        else:

            inserted += 1

            conn.execute(
                """
                INSERT INTO youtube_pilots (
                    video_id,
                    pilot_group,
                    method_name,
                    focus_type,
                    priority,
                    transcript_status,
                    visual_status,
                    evidence_status,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?,
                    'FIN_SYS_CORE',
                    ?,
                    ?,
                    ?,
                    'pending',
                    'pending',
                    'pending',
                    '',
                    ?,
                    ?
                )
                """,
                (
                    video_id,
                    data["method"],
                    data["focus"],
                    data["priority"],
                    now_iso(),
                    now_iso(),
                )
            )

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "existing": existing,
    }


# ============================================================
# SYNC TRANSCRIPT STATUS
# ============================================================

def sync_transcript_status():

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_transcripts"
    ):
        conn.close()

        return 0

    rows = conn.execute(
        """
        SELECT
            video_id,
            transcript_status
        FROM youtube_transcripts
        WHERE video_id IN (
            SELECT video_id
            FROM youtube_pilots
        )
        """
    ).fetchall()

    updated = 0

    for row in rows:

        status = row[
            "transcript_status"
        ]

        conn.execute(
            """
            UPDATE youtube_pilots
            SET
                transcript_status=?,
                updated_at=?
            WHERE video_id=?
            """,
            (
                status,
                now_iso(),
                row["video_id"],
            )
        )

        updated += 1

    conn.commit()
    conn.close()

    return updated


# ============================================================
# SYNC QUEUE STATUS
# ============================================================

def sync_visual_queue_status():

    conn = get_connection()

    if not table_exists(
        conn,
        "youtube_processing_queue"
    ):
        conn.close()

        return 0

    rows = conn.execute(
        """
        SELECT
            video_id,
            status
        FROM youtube_processing_queue
        WHERE video_id IN (
            SELECT video_id
            FROM youtube_pilots
        )
        """
    ).fetchall()

    updated = 0

    for row in rows:

        queue_status = row[
            "status"
        ]

        if queue_status in {
            "completed",
            "visual_completed"
        }:

            visual_status = "completed"

        elif queue_status in {
            "processing",
            "visual_processing"
        }:

            visual_status = "processing"

        elif queue_status in {
            "failed"
        }:

            visual_status = "failed"

        else:

            visual_status = "pending"

        conn.execute(
            """
            UPDATE youtube_pilots
            SET
                visual_status=?,
                updated_at=?
            WHERE video_id=?
            """,
            (
                visual_status,
                now_iso(),
                row["video_id"],
            )
        )

        updated += 1

    conn.commit()
    conn.close()

    return updated


# ============================================================
# PILOT REPORT
# ============================================================

def print_report():

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            p.video_id,
            p.method_name,
            p.focus_type,
            p.priority,
            p.transcript_status,
            p.visual_status,
            p.evidence_status,
            v.title,
            v.published_at,
            v.youtube_url
        FROM youtube_pilots p
        LEFT JOIN youtube_videos v
            ON v.video_id=p.video_id
        ORDER BY
            p.priority DESC
        """
    ).fetchall()

    conn.close()

    print()
    print(
        "========================================="
    )

    print(
        "🧪 FIN[SYS] YOUTUBE PILOT"
    )

    print(
        "========================================="
    )

    if not rows:

        print(
            "Pilot video yok."
        )

        return

    for index, row in enumerate(
        rows,
        start=1
    ):

        print()
        print(
            f"{index}. "
            f"{row['method_name']}"
        )

        print(
            f"   Video: "
            f"{row['title'] or 'Unknown'}"
        )

        print(
            f"   ID: "
            f"{row['video_id']}"
        )

        print(
            f"   Priority: "
            f"{row['priority']}"
        )

        print(
            f"   Transcript: "
            f"{row['transcript_status'] or 'pending'}"
        )

        print(
            f"   Visual: "
            f"{row['visual_status'] or 'pending'}"
        )

        print(
            f"   Evidence: "
            f"{row['evidence_status'] or 'pending'}"
        )

        print(
            f"   URL: "
            f"{row['youtube_url'] or 'unknown'}"
        )

    print()
    print(
        "========================================="
    )


# ============================================================
# TABLE CHECK
# ============================================================

def table_exists(
    conn,
    table_name
):

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


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================="
    )

    print(
        "🧪 MARKET HQ YOUTUBE PILOT MANAGER"
    )

    print(
        "========================================="
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_table()

    result = register_pilots()

    print(
        f"Pilot yeni kayıt: "
        f"{result['inserted']}"
    )

    print(
        f"Pilot zaten kayıtlı: "
        f"{result['existing']}"
    )

    transcript_updates = (
        sync_transcript_status()
    )

    visual_updates = (
        sync_visual_queue_status()
    )

    print(
        f"Transcript status sync: "
        f"{transcript_updates}"
    )

    print(
        f"Visual status sync: "
        f"{visual_updates}"
    )

    print_report()

    print()
    print(
        "✅ YouTube Pilot Manager tamamlandı."
    )

    print()
    print(
        "Pilot kapsamı:"
    )

    print(
        "BUM + Bluesky + TrendMultiCalc"
    )

    print()
    print(
        "Bir sonraki aşamada bu üç videonun "
        "yetkili/erişilebilir içeriklerinden "
        "teknik kanıt ve görsel analiz pipeline'ı kurulacak."
    )


if __name__ == "__main__":
    main()
