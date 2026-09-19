import os
import sys
import sqlite3
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
# SOURCE TYPES
# ============================================================

SOURCE_TYPES = {
    "local_video",
    "authorized_video",
    "image_sequence",
    "single_image",
}


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def ensure_columns() -> None:

    conn = get_connection()

    if not table_exists(
        conn,
        "visual_analysis_queue"
    ):
        conn.close()

        raise RuntimeError(
            "visual_analysis_queue tablosu bulunamadı."
        )

    columns = {
        row["name"]
        for row in conn.execute(
            """
            PRAGMA table_info(
                visual_analysis_queue
            )
            """
        ).fetchall()
    }

    required = {
        "source_adapter_status":
            "TEXT DEFAULT 'pending'",

        "source_adapter_message":
            "TEXT",

        "normalized_source_type":
            "TEXT",

        "normalized_source_path":
            "TEXT",

        "normalized_source_uri":
            "TEXT",

        "resolved_at":
            "TEXT",
    }

    for name, definition in required.items():

        if name not in columns:

            conn.execute(
                f"""
                ALTER TABLE visual_analysis_queue
                ADD COLUMN {name}
                {definition}
                """
            )

    conn.commit()
    conn.close()


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


def is_file(
    path: str
) -> bool:

    return bool(
        path
        and os.path.isfile(
            path
        )
    )


def get_extension(
    path: str
) -> str:

    if not path:
        return ""

    return (
        os.path.splitext(
            path
        )[1]
        .lower()
    )


# ============================================================
# LOAD QUEUE
# ============================================================

def load_queue_items() -> List[Dict[str, Any]]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            video_id,
            channel_id,
            pilot_group,
            method_name,
            focus_type,

            status,
            priority,

            visual_source_status,
            visual_source_path,
            visual_source_type,

            source_adapter_status
        FROM visual_analysis_queue
        WHERE status IN (
            'queued',
            'waiting_for_visual_source',
            'ready_for_frame_scan'
        )
        ORDER BY
            priority DESC,
            queued_at ASC
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# SOURCE VALIDATION
# ============================================================

def validate_local_video(
    path: str
) -> Dict[str, Any]:

    if not path:

        return {
            "valid": False,
            "message": "Video path boş."
        }

    if not os.path.isfile(
        path
    ):

        return {
            "valid": False,
            "message": "Video dosyası bulunamadı."
        }

    supported_extensions = {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
    }

    extension = get_extension(
        path
    )

    if extension not in supported_extensions:

        return {
            "valid": False,
            "message": (
                f"Desteklenmeyen video formatı: "
                f"{extension}"
            )
        }

    try:

        file_size = os.path.getsize(
            path
        )

    except OSError:

        file_size = 0

    if file_size <= 0:

        return {
            "valid": False,
            "message": "Video dosyası boş."
        }

    return {
        "valid": True,
        "message": "Yerel video kaynağı hazır.",
        "source_type": "local_video",
        "path": os.path.abspath(
            path
        ),
        "size_bytes": file_size,
    }


def validate_image(
    path: str
) -> Dict[str, Any]:

    if not path:

        return {
            "valid": False,
            "message": "Görsel yolu boş."
        }

    if not os.path.isfile(
        path
    ):

        return {
            "valid": False,
            "message": "Görsel bulunamadı."
        }

    supported_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
    }

    extension = get_extension(
        path
    )

    if extension not in supported_extensions:

        return {
            "valid": False,
            "message": (
                f"Desteklenmeyen görsel formatı: "
                f"{extension}"
            )
        }

    return {
        "valid": True,
        "message": "Görsel kaynağı hazır.",
        "source_type": "single_image",
        "path": os.path.abspath(
            path
        ),
    }


# ============================================================
# RESOLVE SOURCE
# ============================================================

def resolve_item(
    item: Dict[str, Any]
) -> Dict[str, Any]:

    existing_path = normalize(
        item.get(
            "visual_source_path"
        )
    )

    existing_type = normalize(
        item.get(
            "visual_source_type"
        )
    )

    # --------------------------------------------------------
    # 1. Önceden atanmış kaynak
    # --------------------------------------------------------

    if existing_path:

        if existing_type == "local_video":

            result = validate_local_video(
                existing_path
            )

            if result["valid"]:
                return {
                    **result,
                    "message": (
                        "Mevcut visual source "
                        "başarıyla doğrulandı."
                    )
                }

        elif existing_type == "single_image":

            result = validate_image(
                existing_path
            )

            if result["valid"]:
                return result

    # --------------------------------------------------------
    # 2. Adapter'ın mevcut kaynak olarak kabul ettiği
    #    normalize edilmiş path
    # --------------------------------------------------------

    normalized_path = normalize(
        item.get(
            "normalized_source_path"
        )
    )

    normalized_type = normalize(
        item.get(
            "normalized_source_type"
        )
    )

    if normalized_path:

        if normalized_type == "local_video":

            result = validate_local_video(
                normalized_path
            )

            if result["valid"]:
                return result

    # --------------------------------------------------------
    # 3. Kaynak yok
    # --------------------------------------------------------

    return {
        "valid": False,

        "status": (
            "waiting_for_visual_source"
        ),

        "source_type": None,

        "path": None,

        "message": (
            "Görsel analiz için erişilebilir/"
            "yetkili video veya görsel kaynağı bulunamadı."
        ),
    }


# ============================================================
# SAVE
# ============================================================

def save_resolution(
    queue_id: int,
    result: Dict[str, Any]
) -> None:

    timestamp = now_iso()

    if result.get(
        "valid"
    ):

        status = "ready_for_frame_scan"

        source_status = "resolved"

        error_message = None

        source_type = result.get(
            "source_type"
        )

        source_path = result.get(
            "path"
        )

        source_uri = None

        adapter_status = "ready"

    else:

        status = "waiting_for_visual_source"

        source_status = "not_available"

        error_message = result.get(
            "message"
        )

        source_type = None

        source_path = None

        source_uri = None

        adapter_status = "waiting"

    conn = get_connection()

    conn.execute(
        """
        UPDATE visual_analysis_queue

        SET
            status=?,

            visual_source_status=?,
            visual_source_path=?,
            visual_source_type=?,

            source_adapter_status=?,
            source_adapter_message=?,

            normalized_source_type=?,
            normalized_source_path=?,
            normalized_source_uri=?,

            resolved_at=?,
            updated_at=?,

            error_message=?

        WHERE id=?
        """,
        (
            status,

            source_status,
            source_path,
            source_type,

            adapter_status,
            result.get(
                "message"
            ),

            source_type,
            source_path,
            source_uri,

            timestamp,
            timestamp,

            error_message,

            queue_id,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# SOURCE STATUS COUNTS
# ============================================================

def get_statistics() -> Dict[str, int]:

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            source_adapter_status,
            COUNT(*) AS count
        FROM visual_analysis_queue
        GROUP BY source_adapter_status
        """
    ).fetchall()

    conn.close()

    stats = {
        "ready": 0,
        "waiting": 0,
        "error": 0,
        "pending": 0,
    }

    for row in rows:

        status = normalize(
            row[
                "source_adapter_status"
            ]
        )

        if status in stats:

            stats[
                status
            ] = int(
                row["count"]
            )

    return stats


# ============================================================
# REPORT
# ============================================================

def print_item(
    item: Dict[str, Any],
    result: Dict[str, Any]
) -> None:

    print()
    print(
        f"• {item['method_name']}"
    )

    print(
        f"  Video ID: "
        f"{item['video_id']}"
    )

    print(
        f"  Adapter status: "
        f"{'ready' if result.get('valid') else 'waiting'}"
    )

    print(
        f"  Source type: "
        f"{result.get('source_type') or 'YOK'}"
    )

    print(
        f"  Source path: "
        f"{result.get('path') or 'YOK'}"
    )

    print(
        f"  Message: "
        f"{result.get('message', '')}"
    )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    ready = sum(
        1
        for result in results
        if result.get(
            "valid"
        )
    )

    waiting = len(
        results
    ) - ready

    print()
    print(
        "========================================="
    )

    print(
        "🔌 VISUAL SOURCE ADAPTER SONUCU"
    )

    print(
        "========================================="
    )

    print(
        f"Kontrol edilen: "
        f"{len(results)}"
    )

    print(
        f"Ready for frame scan: "
        f"{ready}"
    )

    print(
        f"Waiting for source: "
        f"{waiting}"
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
        "🔌 MARKET HQ VISUAL SOURCE ADAPTER"
    )

    print(
        "========================================="
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_columns()

    items = load_queue_items()

    print(
        f"Visual queue: "
        f"{len(items)}"
    )

    if not items:

        print(
            "ℹ️ Visual queue boş."
        )

        return

    results = []

    for item in items:

        result = resolve_item(
            item
        )

        save_resolution(
            item["id"],
            result
        )

        print_item(
            item,
            result
        )

        results.append(
            result
        )

    print_summary(
        results
    )

    print()
    print(
        "✅ Visual Source Adapter tamamlandı."
    )

    print()
    print(
        "Not: Bu adapter üçüncü taraf YouTube "
        "videolarını indirmez veya erişim "
        "kısıtlarını aşmaz."
    )

    print(
        "Sadece mevcut/yetkili video veya "
        "görsel kaynakları standartlaştırır."
    )


if __name__ == "__main__":
    main()
