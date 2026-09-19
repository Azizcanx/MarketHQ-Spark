"""
MarketHQ Multi-Symbol Paper Research Runner V1
-----------------------------------------------
Birleştirilmiş research/paper zincirinin orkestrasyon katmanıdır.

Pipeline:
    Strategy Selection V2
            ↓
    Parameter Resolver
            ↓
    Multi-Symbol Paper Replay
            ↓
    Paper Evidence Aggregator
            ↓
    Evidence Report

Bu sürüm:
- Seçim dosyasındaki PAPER_RESEARCH adaylarını otomatik bulur.
- Selection V2 kaydında parametreler taşınmamışsa V6 kaynak JSON'larından
  orijinal strategy record'u çözerek Paper Trading Engine'e aktarır.
- BIST sembollerini sırayla paper-replay'e gönderir.
- Aynı strategy + symbol + period + interval + veri başlangıç/bitiş kombinasyonu
  daha önce çalıştırılmışsa varsayılan olarak tekrar çalıştırmaz.
- Her paper sonucu ayrı JSON olarak mevcut paper_trading_engine_v1.py tarafından
  kaydedilir.
- Tüm sonuçları mevcut paper_evidence_aggregator_v1.py ile toplar.
- Gerçek emir/broker/execution içermez.

Güvenlik:
    RESEARCH_ONLY = True
    EXECUTION_ENABLED = False

Kullanım:
    .\\.venv\\Scripts\\python.exe multi_symbol_paper_research_runner_v1.py

Belirli strateji:
    .\\.venv\\Scripts\\python.exe multi_symbol_paper_research_runner_v1.py ^
        --strategy-id STR-43839FA9C6

Belirli semboller:
    .\\.venv\\Scripts\\python.exe multi_symbol_paper_research_runner_v1.py ^
        --strategy-id STR-43839FA9C6 ^
        --symbols THYAO.IS ASELS.IS EREGL.IS TUPRS.IS AKBNK.IS GARAN.IS SISE.IS BIMAS.IS

Tekrar çalıştırmaya zorla:
    .\\.venv\\Scripts\\python.exe multi_symbol_paper_research_runner_v1.py ^
        --strategy-id STR-43839FA9C6 ^
        --force

Not:
    Bu modül yalnızca historical paper/research simülasyonu yapar.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# PATHS / SAFETY
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

SELECTION_DIR = PROJECT_ROOT / "strategy_selection_results"
PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
PAPER_RESULTS_DIR = PROJECT_ROOT / "paper_trading_results"
PAPER_ENGINE = PROJECT_ROOT / "paper_trading_engine_v1.py"
AGGREGATOR = PROJECT_ROOT / "paper_evidence_aggregator_v1.py"

OUTPUT_DIR = PROJECT_ROOT / "multi_symbol_paper_results"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"

# İlk birleşik test için mevcut validation evrenindeki 8 BIST sembolü.
DEFAULT_BIST_SYMBOLS = [
    "THYAO.IS",
    "ASELS.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "AKBNK.IS",
    "GARAN.IS",
    "SISE.IS",
    "BIMAS.IS",
]

STRATEGY_ID_PATTERN = re.compile(
    r"\bSTR-[A-Z0-9]{6,20}\b",
    re.IGNORECASE,
)


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    text = str(value).strip()

    return text if text else default


def load_json(
    path: Path,
) -> Any:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


def save_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )


def extract_strategy_id(
    data: Any,
    fallback_text: str = "",
) -> str:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in {
                "strategy_id",
                "strategyid",
            }:
                match = STRATEGY_ID_PATTERN.search(
                    str(value)
                )

                if match:
                    return match.group(0).upper()

        for value in data.values():
            found = extract_strategy_id(value)

            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = extract_strategy_id(item)

            if found:
                return found

    if fallback_text:
        match = STRATEGY_ID_PATTERN.search(
            fallback_text
        )

        if match:
            return match.group(0).upper()

    return ""


def extract_strategy_name(
    data: Any,
) -> str:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in {
                "strategy_name",
                "strategyname",
            }:
                text = safe_text(value)

                if text:
                    return text

        for value in data.values():
            found = extract_strategy_name(value)

            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = extract_strategy_name(item)

            if found:
                return found

    return "UNKNOWN_STRATEGY"


def recursively_find_strategy_record(
    data: Any,
    strategy_id: str,
) -> dict[str, Any] | None:
    """
    V6 çıktılarında strategy_id taşıyan en anlamlı dict'i bulur.

    Öncelik:
    - dict'in doğrudan strategy_id taşıması
    - strategy_id'nin tam eşleşmesi
    """
    wanted = strategy_id.upper()

    if isinstance(data, dict):
        direct_id = ""

        for key in (
            "strategy_id",
            "strategyid",
        ):
            if key in data:
                direct_id = safe_text(
                    data[key]
                ).upper()
                break

        if direct_id == wanted:
            return data

        # Bazı yapılarda id nested strategy dict içindedir.
        for key, value in data.items():
            if str(key).lower() in {
                "strategy",
                "strategy_record",
                "candidate",
                "record",
            } and isinstance(value, dict):
                nested_id = extract_strategy_id(
                    value
                ).upper()

                if nested_id == wanted:
                    return value

        for value in data.values():
            found = recursively_find_strategy_record(
                value,
                strategy_id,
            )

            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = recursively_find_strategy_record(
                item,
                strategy_id,
            )

            if found is not None:
                return found

    return None


# ============================================================================
# SELECTION
# ============================================================================

def discover_selection_files() -> list[Path]:
    if not SELECTION_DIR.exists():
        return []

    return sorted(
        SELECTION_DIR.glob(
            "strategy_selection_*.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def load_selection_file(
    explicit_path: Path | None,
) -> tuple[dict[str, Any], Path]:
    if explicit_path is not None:
        payload = load_json(
            explicit_path
        )

        if not isinstance(payload, dict):
            raise ValueError(
                f"Selection JSON okunamadı: {explicit_path}"
            )

        return payload, explicit_path

    paths = discover_selection_files()

    if not paths:
        raise FileNotFoundError(
            "strategy_selection_results klasöründe selection JSON bulunamadı."
        )

    for path in paths:
        payload = load_json(path)

        if isinstance(payload, dict):
            return payload, path

    raise ValueError(
        "Geçerli bir selection JSON bulunamadı."
    )


def extract_paper_candidates(
    selection: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = selection.get(
        "paper_candidates"
    )

    if isinstance(candidates, list):
        return [
            item
            for item in candidates
            if isinstance(item, dict)
        ]

    # Fallback: shortlist içinden paper_candidate=True.
    shortlist = selection.get(
        "shortlist"
    )

    if isinstance(shortlist, list):
        return [
            item
            for item in shortlist
            if (
                isinstance(item, dict)
                and bool(
                    item.get(
                        "paper_candidate",
                        False,
                    )
                )
            )
        ]

    return []


def choose_candidate(
    candidates: list[dict[str, Any]],
    strategy_id: str | None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError(
            "Selection dosyasında PAPER_RESEARCH adayı bulunamadı."
        )

    if strategy_id:
        wanted = strategy_id.upper()

        for item in candidates:
            found = extract_strategy_id(
                item
            ).upper()

            if found == wanted:
                return item

        raise ValueError(
            f"Selection içinde {wanted} bulunamadı."
        )

    # Selection Engine zaten sıralı shortlist üretir.
    return candidates[0]


# ============================================================================
# V6 PARAMETER RESOLUTION
# ============================================================================

def discover_pipeline_files() -> list[Path]:
    if not PIPELINE_DIR.exists():
        return []

    return sorted(
        PIPELINE_DIR.glob(
            "*.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def resolve_original_strategy_record(
    strategy_id: str,
    selection_path: Path,
) -> dict[str, Any] | None:
    """
    Selection V2 kaydı yalnızca score/quality tutuyorsa,
    parametreleri V6 source_pipeline çıktısından çöz.

    Önce selection dosyasının source_files alanına,
    sonra strategy_pipeline_results klasörüne bakar.
    """
    selection_payload = load_json(
        selection_path
    )

    candidate_paths: list[Path] = []

    if isinstance(selection_payload, dict):
        source_files = selection_payload.get(
            "source_files",
            [],
        )

        if isinstance(source_files, list):
            for raw_path in source_files:
                try:
                    path = Path(
                        safe_text(raw_path)
                    )

                    if path.exists():
                        candidate_paths.append(
                            path
                        )
                except Exception:
                    continue

    # En güncel V6 dosyalarını da tara.
    for path in discover_pipeline_files():
        if path not in candidate_paths:
            candidate_paths.append(
                path
            )

    for path in candidate_paths:
        payload = load_json(
            path
        )

        if payload is None:
            continue

        found = recursively_find_strategy_record(
            payload,
            strategy_id,
        )

        if found is not None:
            return found

    return None


def build_parameter_bridge_selection(
    selection: dict[str, Any],
    selected_candidate: dict[str, Any],
    original_record: dict[str, Any] | None,
    strategy_id: str,
    strategy_name: str,
) -> dict[str, Any]:
    """
    Paper Trading Engine V1.3 selection dosyasını beslemek için
    original strategy record'u selected candidate içine ekler.

    Böylece V2 selection çıktısında parametreler taşınmamış olsa bile
    Paper Engine gerçek V6 candidate parametrelerini görebilir.
    """
    candidate = dict(
        selected_candidate
    )

    if original_record is not None:
        candidate["strategy_record"] = (
            original_record
        )
        candidate["original_v6_record"] = (
            original_record
        )

    candidate["strategy_id"] = strategy_id
    candidate["strategy_name"] = strategy_name
    candidate["research_only"] = True
    candidate["execution_enabled"] = False
    candidate["paper_candidate"] = True

    bridge = {
        "selection_version": selection.get(
            "selection_version"
        ),
        "source_pipeline": selection.get(
            "source_pipeline"
        ),
        "created_at": utc_now(),
        "research_only": True,
        "execution_enabled": False,
        "input_strategy_count": 1,
        "shortlist": [
            candidate
        ],
        "paper_candidates": [
            candidate
        ],
        "rejected_count": 0,
        "bridge_metadata": {
            "engine": (
                "MARKETHQ_MULTI_SYMBOL_PAPER_RESEARCH_RUNNER"
            ),
            "engine_version": "V1.0",
            "original_selection_file": str(
                selection_path_for_metadata
            ),
            "parameter_record_resolved": (
                original_record is not None
            ),
        },
    }

    return bridge


# Global only for metadata assignment inside bridge helper.
selection_path_for_metadata = Path("UNKNOWN")


# ============================================================================
# EXISTING RESULT DEDUPLICATION
# ============================================================================

def paper_result_key(
    payload: dict[str, Any],
) -> tuple[str, str, str, str, str, str]:
    strategy_id = extract_strategy_id(
        payload
    ).upper()

    market = payload.get(
        "market",
        {},
    )

    if not isinstance(market, dict):
        market = {}

    symbol = safe_text(
        market.get("symbol")
        or payload.get("symbol"),
        "UNKNOWN",
    ).upper()

    period = safe_text(
        market.get("period")
        or payload.get("period"),
        "UNKNOWN",
    )

    interval = safe_text(
        market.get("interval")
        or payload.get("interval"),
        "UNKNOWN",
    )

    start = safe_text(
        market.get("start")
    )

    end = safe_text(
        market.get("end")
    )

    return (
        strategy_id,
        symbol,
        period,
        interval,
        start,
        end,
    )


def discover_existing_paper_keys() -> set[
    tuple[str, str, str, str, str, str]
]:
    keys: set[
        tuple[str, str, str, str, str, str]
    ] = set()

    if not PAPER_RESULTS_DIR.exists():
        return keys

    for path in PAPER_RESULTS_DIR.glob(
        "*.json"
    ):
        payload = load_json(
            path
        )

        if not isinstance(payload, dict):
            continue

        key = paper_result_key(
            payload
        )

        if key[0] and key[1] != "UNKNOWN":
            keys.add(
                key
            )

    return keys


# ============================================================================
# SUBPROCESS EXECUTION
# ============================================================================

def run_paper_engine(
    strategy_id: str,
    symbol: str,
    period: str,
    interval: str,
    bridge_selection: Path,
) -> tuple[
    bool,
    str,
]:
    if not PAPER_ENGINE.exists():
        return (
            False,
            f"Paper engine bulunamadı: {PAPER_ENGINE}",
        )

    command = [
        sys.executable,
        "-u",
        str(PAPER_ENGINE),
        "--symbol",
        symbol,
        "--period",
        period,
        "--interval",
        interval,
        "--strategy-id",
        strategy_id,
        "--selection-file",
        str(bridge_selection),
    ]

    print()
    print(
        "-" * 82
    )
    print(
        f"🧪 PAPER REPLAY: {symbol}"
    )
    print(
        "-" * 82
    )

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            text=True,
            check=False,
        )
    except OSError as exc:
        return (
            False,
            f"Process başlatılamadı: {exc}",
        )

    if completed.returncode != 0:
        return (
            False,
            f"Paper engine exit code={completed.returncode}",
        )

    return (
        True,
        "Paper replay tamamlandı.",
    )


# ============================================================================
# AGGREGATOR
# ============================================================================

def run_aggregator(
    strategy_id: str,
    min_trades: int,
) -> tuple[
    bool,
    str,
]:
    if not AGGREGATOR.exists():
        return (
            False,
            f"Aggregator bulunamadı: {AGGREGATOR}",
        )

    command = [
        sys.executable,
        "-u",
        str(AGGREGATOR),
        "--strategy-id",
        strategy_id,
        "--min-trades",
        str(min_trades),
    ]

    print()
    print(
        "=" * 82
    )
    print(
        "🧠 PAPER EVIDENCE AGGREGATION"
    )
    print(
        "=" * 82
    )

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            text=True,
            check=False,
        )
    except OSError as exc:
        return (
            False,
            f"Aggregator başlatılamadı: {exc}",
        )

    if completed.returncode != 0:
        return (
            False,
            f"Aggregator exit code={completed.returncode}",
        )

    return (
        True,
        "Evidence aggregation tamamlandı.",
    )


# ============================================================================
# REPORT
# ============================================================================

def save_runner_report(
    report: dict[str, Any],
) -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    strategy_id = safe_text(
        report.get(
            "strategy_id"
        ),
        "UNKNOWN",
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        OUTPUT_DIR
        / (
            f"multi_symbol_paper_"
            f"{strategy_id}_"
            f"{timestamp}.json"
        )
    )

    save_json(
        path,
        report,
    )

    return path


def print_summary(
    report: dict[str, Any],
) -> None:
    print()
    print(
        "=" * 82
    )
    print(
        "🚀 MARKET HQ MULTI-SYMBOL PAPER RESEARCH RUNNER V1.0"
    )
    print(
        "=" * 82
    )
    print()
    print(
        f"Research Only       : {RESEARCH_ONLY}"
    )
    print(
        f"Execution Enabled   : {EXECUTION_ENABLED}"
    )
    print()
    print(
        f"Selection File      : {report['selection_file']}"
    )
    print(
        f"Strategy ID         : {report['strategy_id']}"
    )
    print(
        f"Strategy            : {report['strategy_name']}"
    )
    print()
    print(
        "-" * 82
    )
    print(
        "MULTI-SYMBOL RUN"
    )
    print(
        "-" * 82
    )
    print(
        f"Requested Symbols   : {len(report['requested_symbols'])}"
    )
    print(
        f"Completed           : {report['completed_count']}"
    )
    print(
        f"Skipped Existing    : {report['skipped_existing_count']}"
    )
    print(
        f"Failed              : {report['failed_count']}"
    )
    print(
        f"Parameter Resolved  : {report['parameter_record_resolved']}"
    )
    print()

    for item in report["runs"]:
        print(
            f"{item['symbol']:12} | "
            f"{item['status']:>10} | "
            f"{item['message']}"
        )

    print()
    print(
        "-" * 82
    )
    print(
        "CHAIN STATUS"
    )
    print(
        "-" * 82
    )
    print(
        f"Paper Engine        : {report['paper_engine_status']}"
    )
    print(
        f"Aggregator          : {report['aggregator_status']}"
    )
    print(
        f"Runner Report       : {report['output_file']}"
    )
    print()
    print(
        "=" * 82
    )
    print(
        "SAFETY"
    )
    print(
        "=" * 82
    )
    print(
        "• Historical paper/research replay only."
    )
    print(
        "• Broker bağlantısı yok."
    )
    print(
        "• Gerçek emir yok."
    )
    print(
        "• Execution Enabled = False."
    )
    print(
        "=" * 82
    )


# ============================================================================
# MAIN
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ Multi-Symbol Paper Research Runner V1.0"
        )
    )

    parser.add_argument(
        "--selection-file",
        default=None,
        help=(
            "Belirli strategy_selection JSON dosyası."
        ),
    )

    parser.add_argument(
        "--strategy-id",
        default=None,
        help=(
            "Paper yapılacak strategy_id."
        ),
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_BIST_SYMBOLS,
        help=(
            "Paper sembolleri. "
            "Varsayılan 8 BIST sembolüdür."
        ),
    )

    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=(
            f"Tarih periyodu. Varsayılan: {DEFAULT_PERIOD}"
        ),
    )

    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL,
        help=(
            f"Bar aralığı. Varsayılan: {DEFAULT_INTERVAL}"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Mevcut aynı market/replay sonucu olsa bile yeniden çalıştır."
        ),
    )

    parser.add_argument(
        "--min-trades",
        type=int,
        default=8,
        help=(
            "Aggregator minimum trade eşiği."
        ),
    )

    return parser


def run(
    selection_file: str | None = None,
    strategy_id: str | None = None,
    symbols: list[str] | None = None,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    force: bool = False,
    min_trades: int = 8,
) -> Path:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False."
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True."
        )

    if min_trades < 1:
        raise ValueError(
            "--min-trades en az 1 olmalıdır."
        )

    selected_symbols = [
        safe_text(symbol).upper()
        for symbol in (
            symbols
            or DEFAULT_BIST_SYMBOLS
        )
        if safe_text(symbol)
    ]

    if not selected_symbols:
        raise ValueError(
            "En az bir sembol verilmelidir."
        )

    explicit_selection = (
        Path(selection_file)
        if selection_file
        else None
    )

    selection, actual_selection_path = (
        load_selection_file(
            explicit_selection
        )
    )

    candidates = extract_paper_candidates(
        selection
    )

    selected_candidate = choose_candidate(
        candidates,
        strategy_id,
    )

    resolved_strategy_id = extract_strategy_id(
        selected_candidate
    )

    if not resolved_strategy_id:
        raise ValueError(
            "Selected paper candidate içinde strategy_id bulunamadı."
        )

    resolved_strategy_name = extract_strategy_name(
        selected_candidate
    )

    original_record = (
        resolve_original_strategy_record(
            resolved_strategy_id,
            actual_selection_path,
        )
    )

    # Metadata helper'ın gerçek selection path'i görmesi için.
    global selection_path_for_metadata
    selection_path_for_metadata = (
        actual_selection_path
    )

    bridge_selection = (
        build_parameter_bridge_selection(
            selection=selection,
            selected_candidate=selected_candidate,
            original_record=original_record,
            strategy_id=resolved_strategy_id,
            strategy_name=resolved_strategy_name,
        )
    )

    bridge_dir = (
        OUTPUT_DIR
        / "bridge_selections"
    )

    bridge_path = (
        bridge_dir
        / (
            f"selection_bridge_"
            f"{resolved_strategy_id}.json"
        )
    )

    save_json(
        bridge_path,
        bridge_selection,
    )

    existing_keys = (
        discover_existing_paper_keys()
    )

    runs: list[dict[str, Any]] = []

    completed_count = 0
    skipped_count = 0
    failed_count = 0

    paper_engine_status = "NOT_RUN"

    for symbol in selected_symbols:
        status = "PENDING"
        message = ""

        existing_match = False

        if not force:
            for key in existing_keys:
                if (
                    key[0]
                    == resolved_strategy_id
                    and key[1]
                    == symbol
                    and key[2]
                    == period
                    and key[3]
                    == interval
                ):
                    existing_match = True
                    break

        if existing_match:
            status = "SKIPPED"
            message = (
                "Aynı strategy/symbol/period/interval "
                "için mevcut paper sonucu var."
            )

            skipped_count += 1

            runs.append(
                {
                    "symbol": symbol,
                    "status": status,
                    "message": message,
                }
            )

            continue

        success, message = run_paper_engine(
            strategy_id=resolved_strategy_id,
            symbol=symbol,
            period=period,
            interval=interval,
            bridge_selection=bridge_path,
        )

        if success:
            status = "COMPLETED"
            completed_count += 1
            paper_engine_status = "OK"
        else:
            status = "FAILED"
            failed_count += 1
            paper_engine_status = "ERROR"

        runs.append(
            {
                "symbol": symbol,
                "status": status,
                "message": message,
            }
        )

    # En az bir yeni run tamamlandıysa veya mevcut sonuçlar varsa
    # aggregator yine çalıştırılır.
    aggregator_status = "NOT_RUN"

    if completed_count > 0 or skipped_count > 0:
        aggregate_ok, aggregate_message = (
            run_aggregator(
                strategy_id=resolved_strategy_id,
                min_trades=min_trades,
            )
        )

        if aggregate_ok:
            aggregator_status = "OK"
        else:
            aggregator_status = (
                f"ERROR: {aggregate_message}"
            )
    else:
        aggregator_status = (
            "SKIPPED: paper sonucu oluşmadı."
        )

    report = {
        "engine": (
            "MARKETHQ_MULTI_SYMBOL_PAPER_RESEARCH_RUNNER"
        ),
        "engine_version": "V1.0",
        "created_at": utc_now(),
        "research_only": True,
        "execution_enabled": False,
        "selection_file": str(
            actual_selection_path
        ),
        "strategy_id": resolved_strategy_id,
        "strategy_name": resolved_strategy_name,
        "period": period,
        "interval": interval,
        "requested_symbols": selected_symbols,
        "completed_count": completed_count,
        "skipped_existing_count": skipped_count,
        "failed_count": failed_count,
        "parameter_record_resolved": (
            original_record is not None
        ),
        "bridge_selection": str(
            bridge_path
        ),
        "paper_engine": str(
            PAPER_ENGINE
        ),
        "aggregator": str(
            AGGREGATOR
        ),
        "paper_engine_status": paper_engine_status,
        "aggregator_status": aggregator_status,
        "runs": runs,
        "output_file": "",
    }

    output_path = save_runner_report(
        report
    )

    report["output_file"] = str(
        output_path
    )

    save_json(
        output_path,
        report,
    )

    print_summary(
        report
    )

    return output_path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        run(
            selection_file=args.selection_file,
            strategy_id=args.strategy_id,
            symbols=args.symbols,
            period=args.period,
            interval=args.interval,
            force=args.force,
            min_trades=args.min_trades,
        )

    except KeyboardInterrupt:
        print()
        print(
            "İşlem kullanıcı tarafından durduruldu."
        )
        raise SystemExit(1)

    except Exception as exc:
        print()
        print(
            "=" * 82
        )
        print(
            "❌ MULTI-SYMBOL PAPER RUNNER HATASI"
        )
        print(
            "=" * 82
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print(
            "=" * 82
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()

