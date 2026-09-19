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

VIDEO_DIR = os.path.join(
    PROJECT_ROOT,
    "videos"
)


# ============================================================
# CONFIG
# ============================================================

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".m4v",
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

    columns = [
        row["name"]
        for row in conn.execute(
            """
            PRAGMA table_info(
                visual_analysis_queue
            )
            """
        ).fetchall()
    ]

    required_columns = {
        "visual_source_status": (
            "TEXT DEFAULT 'unknown'"
        ),
        "visual_source_path": (
            "TEXT"
        ),
        "visual_source_type": (
            "TEXT"
        ),
        "visual_source_checked_at": (
            "TEXT"
        ),
    }

    for column_name, column_type in (
        required_columns.items()
    ):

        if column_name not in columns:

            conn.execute(
                f"""
                ALTER TABLE visual_analysis_queue
                ADD COLUMN {column_name}
                {column_type}
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


# ============================================================
# LOAD QUEUE
# ============================================================

def load_visual_queue() -> List[Dict[str, Any]]:

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
            frame_scan_status,
            vision_status,
            evidence_status,
            visual_source_status,
            visual_source_path,
            visual_source_type

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
# SEARCH LOCAL VIDEO
# ============================================================

def find_local_video(
    video_id: str
) -> Optional[str]:

    if not os.path.exists(
        VIDEO_DIR
    ):
        return None

    # Önce video ID'siyle birebir arama.
    for root, _, files in os.walk(
        VIDEO_DIR
    ):

        for filename in files:

            extension = (
                os.path.splitext(
                    filename
                )[1]
                .lower()
            )

            if extension not in (
                SUPPORTED_VIDEO_EXTENSIONS
            ):
                continue

            basename = os.path.splitext(
                filename
            )[0]

            if video_id.lower() in (
                basename.lower()
            ):

                return os.path.join(
                    root,
                    filename
                )

    return None


# ============================================================
# SEARCH BY METHOD NAME
# ============================================================

def find_video_by_method_name(
    method_name: str
) -> Optional[str]:

    if not os.path.exists(
        VIDEO_DIR
    ):
        return None

    normalized_method = normalize(
        method_name
    ).lower()

    if not normalized_method:
        return None

    # Aramayı daha toleranslı yapmak için
    # önemli kelimelere ayırıyoruz.
    words = [
        word
        for word in normalized_method
        .replace(
            "-",
            " "
        )
        .split()
        if len(word) >= 4
    ]

    if not words:
        return None

    best_path = None
    best_score = 0

    for root, _, files in os.walk(
        VIDEO_DIR
    ):

        for filename in files:

            extension = (
                os.path.splitext(
                    filename
                )[1]
                .lower()
            )

            if extension not in (
                SUPPORTED_VIDEO_EXTENSIONS
            ):
                continue

            filename_lower = (
                filename.lower()
            )

            score = sum(
                1
                for word in words
                if word.lower()
                in filename_lower
            )

            if score > best_score:

                best_score = score
                best_path = os.path.join(
                    root,
                    filename
                )

    # En az iki güçlü kelime eşleşmesi.
    if best_score >= 2:
        return best_path

    return None


# ============================================================
# RESOLVE ONE SOURCE
# ============================================================

def resolve_source(
    item: Dict[str, Any]
) -> Dict[str, Any]:

    video_id = normalize(
        item.get(
            "video_id"
        )
    )

    method_name = normalize(
        item.get(
            "method_name"
        )
    )

    # --------------------------------------------------------
    # 1. Daha önce atanmış kaynak
    # --------------------------------------------------------

    existing_path = normalize(
        item.get(
            "visual_source_path"
        )
    )

    if (
        existing_path
        and os.path.isfile(
            existing_path
        )
    ):

        return {
            "status": "ready_for_frame_scan",
            "source_type": "local_video",
            "source_path": existing_path,
            "reason": (
                "Daha önce atanmış ve mevcut "
                "video kaynağı bulundu."
            ),
        }

    # --------------------------------------------------------
    # 2. Video ID ile arama
    # --------------------------------------------------------

    local_path = find_local_video(
        video_id
    )

    if local_path:

        return {
            "status": "ready_for_frame_scan",
            "source_type": "local_video",
            "source_path": local_path,
            "reason": (
                "Video ID ile yerel video bulundu."
            ),
        }

    # --------------------------------------------------------
    # 3. Method adı ile arama
    # --------------------------------------------------------

    local_path = find_video_by_method_name(
        method_name
    )

    if local_path:

        return {
            "status": "ready_for_frame_scan",
            "source_type": "local_video",
            "source_path": local_path,
            "reason": (
                "Method adıyla eşleşen "
                "yerel video bulundu."
            ),
        }

    # --------------------------------------------------------
    # 4. Kaynak yok
    # --------------------------------------------------------

    return {
        "status": "waiting_for_visual_source",
        "source_type": None,
        "source_path": None,
        "reason": (
            "Frame analizi için erişilebilir/"
            "yetkili bir video girdisi bulunamadı."
        ),
    }


# ============================================================
# SAVE RESULT
# ============================================================

def save_resolution(
    queue_id: int,
    resolution: Dict[str, Any]
) -> None:

    conn = get_connection()

    conn.execute(
        """
        UPDATE visual_analysis_queue

        SET
            status=?,
            visual_source_status=?,
            visual_source_path=?,
            visual_source_type=?,
            visual_source_checked_at=?,
            updated_at=?,

            error_message=?

        WHERE id=?
        """,
        (
            resolution["status"],

            (
                "available"
                if resolution["source_path"]
                else "not_available"
            ),

            resolution["source_path"],

            resolution["source_type"],

            now_iso(),

            now_iso(),

            (
                None
                if resolution["source_path"]
                else resolution["reason"]
            ),

            queue_id,
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# REPORT
# ============================================================

def print_result(
    item: Dict[str, Any],
    resolution: Dict[str, Any]
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
        f"  Status: "
        f"{resolution['status']}"
    )

    if resolution["source_path"]:

        print(
            f"  Source: "
            f"{resolution['source_path']}"
        )

    else:

        print(
            f"  Source: "
            f"YOK"
        )

    print(
        f"  Reason: "
        f"{resolution['reason']}"
    )


def print_summary(
    results: List[Dict[str, Any]]
) -> None:

    ready = sum(
        1
        for result in results
        if result["status"]
        == "ready_for_frame_scan"
    )

    waiting = sum(
        1
        for result in results
        if result["status"]
        == "waiting_for_visual_source"
    )

    print()
    print(
        "========================================="
    )

    print(
        "🎬 VISUAL SOURCE RESOLVER SONUCU"
    )

    print(
        "========================================="
    )

    print(
        f"Kontrol edilen: "
        f"{len(results)}"
    )

    print(
        f"Frame scan'a hazır: "
        f"{ready}"
    )

    print(
        f"Kaynak bekleyen: "
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
        "🎬 MARKET HQ VISUAL SOURCE RESOLVER"
    )

    print(
        "========================================="
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_columns()

    items = load_visual_queue()

    print(
        f"Visual queue kontrol ediliyor: "
        f"{len(items)}"
    )

    if not items:

        print(
            "ℹ️ Kontrol edilecek visual queue yok."
        )

        return

    results = []

    for item in items:

        resolution = resolve_source(
            item
        )

        save_resolution(
            item["id"],
            resolution
        )

        result = {
            **resolution,
            "method_name": item[
                "method_name"
            ],
            "video_id": item[
                "video_id"
            ],
        }

        results.append(
            result
        )

        print_result(
            item,
            resolution
        )

    print_summary(
        results
    )

    print()
    print(
        "✅ Visual Source Resolver tamamlandı."
    )

    print()
    print(
        "Not: Kaynak bulunamadığında video "
        "silinmez; sadece waiting_for_visual_source "
        "durumunda tutulur."
    )

    print(
        "Kaynak daha sonra erişilebilir hale "
        "geldiğinde resolver tekrar çalıştırılabilir."
    )


if __name__ == "__main__":
    main()
