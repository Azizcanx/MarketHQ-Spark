import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_strategy_discovery import run_discovery


# ============================================================
# MARKET HQ
# RESEARCH INGESTION ENGINE V1
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

RESEARCH_DIR = PROJECT_ROOT / "research_sources"

INGESTION_RESULTS_DIR = (
    PROJECT_ROOT / "research_ingestion_results"
)

INGESTION_RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

SUPPORTED_EXTENSIONS = {
    ".txt": "article",
    ".md": "research",
    ".markdown": "research",
    ".csv": "research",
    ".json": "research",
}

MAX_SOURCE_CHARS = 30000


# ============================================================
# HELPERS
# ============================================================

def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""

    text = text.replace("\x00", " ")
    text = text.strip()

    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS]

    return text


def safe_filename(text: str) -> str:
    text = str(text).strip()

    if not text:
        text = "unknown"

    chars = []

    for char in text:
        if char.isalnum():
            chars.append(char)
        elif char in {
            " ",
            "-",
            "_",
        }:
            chars.append("_")

    result = "".join(chars)

    while "__" in result:
        result = result.replace(
            "__",
            "_",
        )

    result = result.strip("_")

    if not result:
        result = "unknown"

    return result[:100]


# ============================================================
# DIRECTORY
# ============================================================

def ensure_research_directory() -> None:
    RESEARCH_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# FILE DISCOVERY
# ============================================================

def discover_source_files() -> list[Path]:
    ensure_research_directory()

    files = []

    for path in RESEARCH_DIR.rglob("*"):

        if not path.is_file():
            continue

        if path.name.startswith("~$"):
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        files.append(path)

    files.sort(
        key=lambda item: str(item).lower()
    )

    return files


# ============================================================
# SOURCE TYPE
# ============================================================

def detect_source_type(
    file_path: Path,
) -> str:

    return SUPPORTED_EXTENSIONS.get(
        file_path.suffix.lower(),
        "unknown",
    )


# ============================================================
# TEXT READER
# ============================================================

def read_source_file(
    file_path: Path,
) -> str:

    suffix = file_path.suffix.lower()

    if suffix == ".json":

        raw_text = file_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        try:
            data = json.loads(raw_text)

            return clean_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        except json.JSONDecodeError:
            return clean_text(raw_text)

    return clean_text(
        file_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    )


# ============================================================
# SOURCE METADATA
# ============================================================

def build_source_metadata(
    file_path: Path,
) -> dict:

    try:
        stat = file_path.stat()

        size_bytes = stat.st_size

        modified_at = datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat()

    except OSError:

        size_bytes = 0
        modified_at = None

    return {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "extension": file_path.suffix.lower(),
        "source_type": detect_source_type(
            file_path
        ),
        "size_bytes": size_bytes,
        "modified_at": modified_at,
    }


# ============================================================
# RESULT SAVE
# ============================================================

def save_ingestion_result(
    result: dict,
    source_name: str,
) -> Path:

    filename = safe_filename(
        source_name
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        INGESTION_RESULTS_DIR
        / f"{filename}_{timestamp}.json"
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output_path


# ============================================================
# SINGLE SOURCE PROCESSING
# ============================================================

def process_source(
    file_path: Path,
) -> dict:

    print()
    print("-" * 70)
    print(
        f"📄 Kaynak: {file_path.name}"
    )

    metadata = build_source_metadata(
        file_path
    )

    source_type = metadata[
        "source_type"
    ]

    try:

        source_text = read_source_file(
            file_path
        )

        if not source_text:

            return {
                "status": "SKIPPED",
                "reason": "Kaynak dosyası boş.",
                "source": metadata,
                "timestamp": utc_timestamp(),
            }

        print(
            f"   Tür          : {source_type}"
        )

        print(
            f"   Boyut        : "
            f"{metadata['size_bytes']} bytes"
        )

        print(
            f"   Metin        : "
            f"{len(source_text)} karakter"
        )

        print()
        print(
            "   🧠 Strategy Discovery başlıyor..."
        )

        discovery_result = run_discovery(
            source_text=source_text,
            source_title=file_path.stem,
            source_type=source_type,
            save_to_kb=True,
        )

        strategy_count = int(
            discovery_result.get(
                "strategy_count",
                0,
            )
        )

        result = {
            "status": "SUCCESS",
            "timestamp": utc_timestamp(),
            "source": metadata,
            "strategy_count": strategy_count,
            "discovery": discovery_result,
            "safety": {
                "research_only": True,
                "execution_enabled": False,
            },
        }

        print()
        print(
            f"   ✅ Kaynak tamamlandı"
        )

        print(
            f"   Strateji adayı: "
            f"{strategy_count}"
        )

        return result

    except Exception as exc:

        print()
        print(
            f"   ❌ Kaynak işlenemedi:"
        )

        print(
            f"   {exc}"
        )

        return {
            "status": "ERROR",
            "timestamp": utc_timestamp(),
            "source": metadata,
            "strategy_count": 0,
            "error": str(exc),
            "safety": {
                "research_only": True,
                "execution_enabled": False,
            },
        }


# ============================================================
# BATCH INGESTION
# ============================================================

def run_ingestion() -> dict:

    print()
    print("=" * 70)
    print(
        "📚 MARKET HQ RESEARCH INGESTION ENGINE V1"
    )
    print("=" * 70)

    print()
    print(
        f"Research Directory:"
    )

    print(
        RESEARCH_DIR
    )

    ensure_research_directory()

    source_files = (
        discover_source_files()
    )

    print()
    print(
        f"🔎 Bulunan kaynak sayısı: "
        f"{len(source_files)}"
    )

    if not source_files:

        print()
        print(
            "⚠️ research_sources klasöründe "
            "desteklenen kaynak bulunamadı."
        )

        print()
        print(
            "Desteklenen formatlar:"
        )

        for extension in sorted(
            SUPPORTED_EXTENSIONS
        ):
            print(
                f"  - {extension}"
            )

        print()
        print(
            "Örnek:"
        )

        print(
            RESEARCH_DIR
            / "ornek_strateji.md"
        )

        result = {
            "engine": (
                "MarketHQ Research "
                "Ingestion Engine V1"
            ),
            "timestamp": utc_timestamp(),
            "status": "NO_SOURCES",
            "source_count": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "total_strategies": 0,
            "sources": [],
            "safety": {
                "research_only": True,
                "execution_enabled": False,
            },
        }

        return result

    results = []

    success_count = 0
    error_count = 0
    skipped_count = 0
    total_strategies = 0

    for index, file_path in enumerate(
        source_files,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(source_files)}]"
        )

        result = process_source(
            file_path
        )

        results.append(result)

        status = result.get(
            "status"
        )

        if status == "SUCCESS":
            success_count += 1

        elif status == "ERROR":
            error_count += 1

        elif status == "SKIPPED":
            skipped_count += 1

        total_strategies += int(
            result.get(
                "strategy_count",
                0,
            )
        )

    batch_result = {
        "engine": (
            "MarketHQ Research "
            "Ingestion Engine V1"
        ),
        "timestamp": utc_timestamp(),
        "status": (
            "SUCCESS"
            if error_count == 0
            else "PARTIAL"
        ),
        "source_count": len(
            source_files
        ),
        "success_count": success_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "total_strategies": total_strategies,
        "sources": results,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
        },
    }

    return batch_result


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(
    result: dict,
) -> None:

    print()
    print("=" * 70)
    print(
        "📊 INGESTION SUMMARY"
    )
    print("=" * 70)

    print(
        f"Status             : "
        f"{result.get('status')}"
    )

    print(
        f"Sources            : "
        f"{result.get('source_count', 0)}"
    )

    print(
        f"Successful         : "
        f"{result.get('success_count', 0)}"
    )

    print(
        f"Errors             : "
        f"{result.get('error_count', 0)}"
    )

    print(
        f"Skipped            : "
        f"{result.get('skipped_count', 0)}"
    )

    print(
        f"Strategy Candidates: "
        f"{result.get('total_strategies', 0)}"
    )

    print()
    print(
        "SAFETY"
    )

    print(
        "Research Only      : True"
    )

    print(
        "Execution Enabled  : False"
    )

    print("=" * 70)


# ============================================================
# SAVE BATCH RESULT
# ============================================================

def save_batch_result(
    result: dict,
) -> Path:

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        INGESTION_RESULTS_DIR
        / f"batch_{timestamp}.json"
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output_path


# ============================================================
# DEMO SOURCE CREATOR
# ============================================================

def create_demo_source() -> Path:

    ensure_research_directory()

    demo_path = (
        RESEARCH_DIR
        / "demo_strategy_source.md"
    )

    demo_text = """
# MarketHQ Strategy Research Demo

Bu metin MarketHQ Research Ingestion Engine testidir.

Örnek strateji:

Kısa vadeli hareketli ortalamanın uzun vadeli hareketli
ortalamayı yukarı kesmesi trend başlangıcı olarak kabul edilir.

RSI göstergesinin 50 seviyesinin üzerinde olması ek onay
olarak kullanılabilir.

Pozisyon, trendin tersine dönmesi durumunda kapatılabilir.

ATR tabanlı risk yönetimi kullanılabilir.

Kaynak, kesin pozisyon büyüklüğü veya kesin ATR katsayısı
belirtmemektedir.

Bu metin yalnızca araştırma ve yazılım testi amacıyla
kullanılmaktadır.
"""

    demo_path.write_text(
        demo_text.strip(),
        encoding="utf-8",
    )

    return demo_path


# ============================================================
# CLI
# ============================================================

def print_usage() -> None:

    print()
    print("=" * 70)
    print(
        "MARKET HQ RESEARCH INGESTION ENGINE"
    )
    print("=" * 70)

    print()
    print("Kullanım:")
    print()

    print(
        r".\.venv\Scripts\python.exe "
        r"research_ingestion_engine.py"
    )

    print()
    print(
        "Bu komut research_sources klasörünü tarar."
    )

    print()
    print("Demo kaynak oluştur:")
    print()

    print(
        r".\.venv\Scripts\python.exe "
        r"research_ingestion_engine.py --demo"
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    args = sys.argv[1:]

    if args:

        if args[0] in {
            "-h",
            "--help",
            "help",
        }:

            print_usage()
            return

        if args[0] == "--demo":

            demo_path = (
                create_demo_source()
            )

            print()
            print(
                "✅ Demo kaynak oluşturuldu:"
            )

            print(
                demo_path
            )

            print()
            print(
                "Şimdi ingestion çalıştırılıyor..."
            )

    result = run_ingestion()

    print_summary(
        result
    )

    output_path = save_batch_result(
        result
    )

    print()
    print(
        "💾 Batch sonucu kaydedildi:"
    )

    print(
        output_path
    )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
