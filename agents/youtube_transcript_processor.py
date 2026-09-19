import os
import sys
import json
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

TRANSCRIPT_DIR = os.path.join(
    PROJECT_ROOT,
    "transcripts"
)


# ============================================================
# PILOT
# ============================================================

PILOT_VIDEO_ID = "siUhYKVwL-Q"

PILOT_METHOD = "BUM"


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    return conn


def ensure_columns():

    conn = get_connection()

    columns = {
        row["name"]
        for row in conn.execute(
            """
            PRAGMA table_info(
                youtube_transcripts
            )
            """
        ).fetchall()
    }

    required = {
        "segment_count":
            "INTEGER DEFAULT 0",

        "timestamped":
            "INTEGER DEFAULT 0",

        "processed_at":
            "TEXT",
    }

    for name, definition in required.items():

        if name not in columns:

            conn.execute(
                f"""
                ALTER TABLE youtube_transcripts
                ADD COLUMN {name}
                {definition}
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


def normalize(
    value: Any
) -> str:

    if value is None:
        return ""

    return str(
        value
    ).strip()


# ============================================================
# TRANSCRIPT FILE
# ============================================================

def ensure_directory():

    os.makedirs(
        TRANSCRIPT_DIR,
        exist_ok=True
    )


def get_transcript_path(
    video_id: str
) -> str:

    return os.path.join(
        TRANSCRIPT_DIR,
        f"{video_id}.txt"
    )


def read_transcript_file(
    video_id: str
) -> str:

    path = get_transcript_path(
        video_id
    )

    if not os.path.isfile(
        path
    ):
        return ""

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read().strip()


# ============================================================
# TRANSCRIPT PARSER
# ============================================================

def parse_timestamp(
    line: str
) -> str:

    text = normalize(
        line
    )

    if not text:
        return ""

    # Örnek:
    # [00:12]
    # [00:01:23]
    # 00:12
    # 01:23:45

    import re

    match = re.search(
        r"\[?(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\]?",
        text
    )

    if not match:
        return ""

    return match.group(1)


def parse_timestamp_to_seconds(
    timestamp: str
) -> float:

    if not timestamp:
        return 0.0

    parts = timestamp.split(
        ":"
    )

    try:

        if len(parts) == 2:

            minutes = float(
                parts[0]
            )

            seconds = float(
                parts[1]
            )

            return (
                minutes * 60
                + seconds
            )

        if len(parts) == 3:

            hours = float(
                parts[0]
            )

            minutes = float(
                parts[1]
            )

            seconds = float(
                parts[2]
            )

            return (
                hours * 3600
                + minutes * 60
                + seconds
            )

    except ValueError:

        return 0.0

    return 0.0


def clean_transcript_text(
    line: str
) -> str:

    text = normalize(
        line
    )

    if not text:
        return ""

    import re

    text = re.sub(
        r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?\]?\s*",
        "",
        text
    )

    return text.strip()


def parse_transcript(
    transcript_text: str
) -> List[Dict[str, Any]]:

    lines = transcript_text.splitlines()

    segments = []

    current_timestamp = ""
    current_text_parts = []

    def flush():

        nonlocal current_timestamp
        nonlocal current_text_parts

        if not current_text_parts:
            return

        text = " ".join(
            current_text_parts
        ).strip()

        if not text:
            current_text_parts = []
            return

        seconds = (
            parse_timestamp_to_seconds(
                current_timestamp
            )
        )

        segments.append(
            {
                "timestamp": current_timestamp,
                "timestamp_seconds": seconds,
                "text": text,
            }
        )

        current_text_parts = []

    for raw_line in lines:

        line = normalize(
            raw_line
        )

        if not line:
            continue

        timestamp = parse_timestamp(
            line
        )

        if timestamp:

            flush()

            current_timestamp = (
                timestamp
            )

            cleaned = clean_transcript_text(
                line
            )

            if cleaned:

                current_text_parts.append(
                    cleaned
                )

        else:

            current_text_parts.append(
                line
            )

    flush()

    # Timestamp yoksa tüm metni tek segment yap.
    if not segments and transcript_text.strip():

        segments.append(
            {
                "timestamp": "",
                "timestamp_seconds": 0.0,
                "text": normalize(
                    transcript_text
                ),
            }
        )

    return segments


# ============================================================
# TECHNICAL KEYWORD INDEX
# ============================================================

KEYWORD_GROUPS = {

    "indicators": [
        "rsi",
        "macd",
        "ema",
        "sma",
        "wma",
        "hma",
        "atr",
        "adx",
        "cci",
        "stochastic",
        "bollinger",
        "zlsma",
        "supertrend",
        "kaufman",
        "momentum",
        "hacim",
        "volume",
    ],

    "signals": [
        "al",
        "sat",
        "alış",
        "satış",
        "alım",
        "satım",
        "sinyal",
        "buy",
        "sell",
        "long",
        "short",
        "giriş",
        "çıkış",
        "kesişim",
        "kırılım",
        "breakout",
    ],

    "trend": [
        "trend",
        "yükseliş",
        "düşüş",
        "yukarı",
        "aşağı",
        "momentum",
        "volatilite",
    ],

    "chart": [
        "grafik",
        "mum",
        "destek",
        "direnç",
        "kanal",
        "bant",
        "çizgi",
        "formasyon",
        "pivot",
    ],

    "parameters": [
        "periyot",
        "parametre",
        "eşik",
        "katsayı",
        "çarpan",
        "length",
        "period",
        "threshold",
        "window",
        "lookback",
    ],

    "timeframe": [
        "dakika",
        "saat",
        "günlük",
        "haftalık",
        "aylık",
        "daily",
        "weekly",
        "monthly",
        "timeframe",
        "zaman dilimi",
    ],
}


def find_keywords(
    text: str
) -> Dict[str, List[str]]:

    lower = text.lower()

    result = {}

    for group, keywords in (
        KEYWORD_GROUPS.items()
    ):

        found = []

        for keyword in keywords:

            if keyword.lower() in lower:

                found.append(
                    keyword
                )

        result[group] = found

    return result


# ============================================================
# DATABASE SAVE
# ============================================================

def save_transcript(
    video_id: str,
    text: str,
    segments: List[Dict[str, Any]]
):

    timestamped = any(
        bool(
            segment.get(
                "timestamp"
            )
        )
        for segment in segments
    )

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
            updated_at,
            segment_count,
            timestamped,
            processed_at
        )
        VALUES (
            ?,
            'processed',
            ?,
            'tr',
            'external_or_authorized_input',
            NULL,
            ?,
            ?,
            ?,
            ?,
            ?
        )

        ON CONFLICT(video_id)
        DO UPDATE SET
            transcript_status='processed',
            transcript_text=excluded.transcript_text,
            language=excluded.language,
            source=excluded.source,
            error_message=NULL,
            checked_at=excluded.checked_at,
            updated_at=excluded.updated_at,
            segment_count=excluded.segment_count,
            timestamped=excluded.timestamped,
            processed_at=excluded.processed_at
        """,
        (
            video_id,
            text,
            now_iso(),
            now_iso(),
            len(segments),
            int(
                timestamped
            ),
            now_iso(),
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# SAVE SEGMENT ANALYSIS
# ============================================================

def ensure_segment_table():

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS youtube_transcript_segments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id TEXT NOT NULL,

            segment_index INTEGER,

            timestamp TEXT,

            timestamp_seconds REAL,

            text TEXT,

            technical_keywords TEXT,

            created_at TEXT,

            UNIQUE(
                video_id,
                segment_index
            )
        )
        """
    )

    conn.commit()
    conn.close()


def save_segments(
    video_id: str,
    segments: List[Dict[str, Any]]
):

    conn = get_connection()

    for index, segment in enumerate(
        segments,
        start=1
    ):

        keywords = find_keywords(
            segment["text"]
        )

        conn.execute(
            """
            INSERT INTO youtube_transcript_segments (
                video_id,
                segment_index,
                timestamp,
                timestamp_seconds,
                text,
                technical_keywords,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(
                video_id,
                segment_index
            )
            DO UPDATE SET
                timestamp=excluded.timestamp,
                timestamp_seconds=excluded.timestamp_seconds,
                text=excluded.text,
                technical_keywords=excluded.technical_keywords,
                created_at=excluded.created_at
            """,
            (
                video_id,
                index,

                segment.get(
                    "timestamp",
                    ""
                ),

                segment.get(
                    "timestamp_seconds",
                    0.0
                ),

                segment.get(
                    "text",
                    ""
                ),

                json.dumps(
                    keywords,
                    ensure_ascii=False
                ),

                now_iso(),
            )
        )

    conn.commit()
    conn.close()


# ============================================================
# TECHNICAL SUMMARY
# ============================================================

def build_summary(
    segments: List[Dict[str, Any]]
) -> Dict[str, Any]:

    full_text = " ".join(
        segment["text"]
        for segment in segments
    )

    keyword_index = find_keywords(
        full_text
    )

    technical_segments = []

    for index, segment in enumerate(
        segments,
        start=1
    ):

        keywords = find_keywords(
            segment["text"]
        )

        total_matches = sum(
            len(values)
            for values in keywords.values()
        )

        if total_matches >= 1:

            technical_segments.append(
                {
                    "segment_index": index,
                    "timestamp": segment[
                        "timestamp"
                    ],
                    "timestamp_seconds": segment[
                        "timestamp_seconds"
                    ],
                    "text": segment[
                        "text"
                    ],
                    "keywords": keywords,
                    "match_count": total_matches,
                }
            )

    return {
        "segment_count": len(
            segments
        ),

        "timestamped": any(
            bool(
                segment["timestamp"]
            )
            for segment in segments
        ),

        "keyword_index": keyword_index,

        "technical_segment_count": len(
            technical_segments
        ),

        "technical_segments": (
            technical_segments[:100]
        ),
    }


# ============================================================
# SAVE TECHNICAL SUMMARY
# ============================================================

def save_summary(
    video_id: str,
    summary: Dict[str, Any]
):

    summary_dir = os.path.join(
        PROJECT_ROOT,
        "youtube_analysis"
    )

    os.makedirs(
        summary_dir,
        exist_ok=True
    )

    path = os.path.join(
        summary_dir,
        f"{video_id}__transcript_analysis.json"
    )

    payload = {
        "video_id": video_id,
        "method": PILOT_METHOD,
        "created_at": now_iso(),
        "summary": summary,
    }

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2
        )

    return path


# ============================================================
# REPORT
# ============================================================

def print_report(
    segments: List[Dict[str, Any]],
    summary: Dict[str, Any],
    summary_path: str
):

    print()
    print(
        "========================================="
    )

    print(
        "📝 BUM TRANSCRIPT PROCESSOR"
    )

    print(
        "========================================="
    )

    print(
        f"Video ID: "
        f"{PILOT_VIDEO_ID}"
    )

    print(
        f"Segment: "
        f"{summary['segment_count']}"
    )

    print(
        f"Timestamped: "
        f"{'YES' if summary['timestamped'] else 'NO'}"
    )

    print(
        f"Technical segment: "
        f"{summary['technical_segment_count']}"
    )

    print()
    print(
        "KEYWORD INDEX"
    )

    print(
        "-----------------------------------------"
    )

    for group, values in summary[
        "keyword_index"
    ].items():

        print(
            f"{group}: "
            f"{', '.join(values) if values else 'none'}"
        )

    print()
    print(
        "ÖNEMLİ SEGMENTLER"
    )

    print(
        "-----------------------------------------"
    )

    for segment in summary[
        "technical_segments"
    ][:20]:

        timestamp = (
            segment["timestamp"]
            or "NO_TIMESTAMP"
        )

        print(
            f"{timestamp} | "
            f"{segment['text'][:240]}"
        )

    print()
    print(
        f"Analysis file: "
        f"{summary_path}"
    )

    print(
        "========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================="
    )

    print(
        "📝 MARKET HQ YOUTUBE TRANSCRIPT PROCESSOR"
    )

    print(
        "========================================="
    )

    print(
        f"Pilot: "
        f"{PILOT_METHOD}"
    )

    print(
        f"Video ID: "
        f"{PILOT_VIDEO_ID}"
    )

    print(
        "API kullanımı: 0"
    )

    print()

    ensure_columns()
    ensure_segment_table()
    ensure_directory()

    transcript = read_transcript_file(
        PILOT_VIDEO_ID
    )

    if not transcript:

        print(
            "❌ Transcript dosyası bulunamadı."
        )

        print()
        print(
            "Beklenen dosya:"
        )

        print(
            get_transcript_path(
                PILOT_VIDEO_ID
            )
        )

        print()
        print(
            "Bu dosya yalnızca erişimin olan/"
            "yetkili transcript metnini işlemek için kullanılır."
        )

        print(
            "Henüz video indirilmiyor veya "
            "erişim kısıtları aşılmıyor."
        )

        return

    print(
        f"Transcript karakter: "
        f"{len(transcript)}"
    )

    segments = parse_transcript(
        transcript
    )

    save_transcript(
        PILOT_VIDEO_ID,
        transcript,
        segments
    )

    save_segments(
        PILOT_VIDEO_ID,
        segments
    )

    summary = build_summary(
        segments
    )

    summary_path = save_summary(
        PILOT_VIDEO_ID,
        summary
    )

    print_report(
        segments,
        summary,
        summary_path
    )

    print()
    print(
        "✅ BUM transcript processing tamamlandı."
    )

    print()
    print(
        "Sonraki aşama:"
    )

    print(
        "Transcript'teki teknik segmentleri "
        "grafik/frame kanıtlarıyla eşleştirmek."
    )


if __name__ == "__main__":
    main()
