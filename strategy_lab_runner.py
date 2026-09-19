import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(
    __file__
).resolve().parent

STRATEGY_LAB_FILE = (
    BASE_DIR
    / "agents"
    / "strategy_lab.py"
)

RESULT_FILE = (
    BASE_DIR
    / "strategy_lab_result.json"
)

TEMP_RESULT_FILE = (
    BASE_DIR
    / "strategy_lab_result.tmp"
)

LOCK_FILE = (
    BASE_DIR
    / "strategy_lab.lock"
)

RUNTIME_STATE_FILE = (
    BASE_DIR
    / "runtime_state.json"
)

RUNTIME_STATE_TEMP_FILE = (
    BASE_DIR
    / "runtime_state.strategy.tmp"
)


# =========================================================
# CONFIG
# =========================================================

TOTAL_SYMBOLS = 35

PROCESS_TIMEOUT = 60 * 60 * 2

RESULT_WRITE_RETRIES = 10

RESULT_WRITE_SLEEP = 0.5


# =========================================================
# SYMBOLS
# =========================================================

BIST_SYMBOLS = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "SISE.IS",
    "BIMAS.IS",
    "FROTO.IS",
    "KCHOL.IS",
    "SAHOL.IS",
    "TCELL.IS",
    "TAVHL.IS",
    "PGSUS.IS",
    "TOASO.IS",
    "ENKAI.IS",
    "EKGYO.IS",
    "MGROS.IS",
    "PETKM.IS",
    "SASA.IS",
]


US_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "AMD",
    "QCOM",
    "NFLX",
    "ORCL",
    "MU",
    "INTC",
    "COST",
]


ALL_SYMBOLS = (
    BIST_SYMBOLS
    + US_SYMBOLS
)


# =========================================================
# HELPERS
# =========================================================

def now_iso() -> str:

    return (
        datetime.now()
        .isoformat(
            timespec="seconds"
        )
    )


def safe_float(
    value: Any,
) -> float | None:

    if value is None:
        return None

    try:
        number = float(value)

        if number != number:
            return None

        return number

    except (
        TypeError,
        ValueError,
    ):
        return None


def parse_percent(
    value: str | None,
) -> float | None:

    if not value:
        return None

    cleaned = (
        value
        .replace("%", "")
        .replace(",", ".")
        .strip()
    )

    if cleaned.lower() in {
        "veri yok",
        "none",
        "nan",
    }:
        return None

    try:
        return float(cleaned)

    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_status(
    value: str | None,
) -> str:

    if not value:
        return "IDLE"

    value = (
        str(value)
        .strip()
        .upper()
    )

    allowed = {
        "RUNNING",
        "COMPLETED",
        "ERROR",
        "IDLE",
    }

    if value in allowed:
        return value

    return "IDLE"


def process_exists(
    pid: int | None,
) -> bool:

    if pid is None:
        return False

    if pid <= 0:
        return False

    try:

        if os.name == "nt":

            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {pid}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            return str(pid) in (
                result.stdout
            )

        os.kill(
            pid,
            0,
        )

        return True

    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ):

        return False


# =========================================================
# LOCK
# =========================================================

def read_lock() -> dict[str, Any] | None:

    if not LOCK_FILE.exists():
        return None

    try:

        with LOCK_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            return None

        return data

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):

        return None


def remove_lock() -> None:

    try:

        if LOCK_FILE.exists():
            LOCK_FILE.unlink()

    except OSError as error:

        print(
            f"⚠️ Lock silinemedi: {error}"
        )


def cleanup_stale_lock() -> None:

    lock = read_lock()

    if not lock:
        remove_lock()
        return

    pid = lock.get(
        "pid"
    )

    if process_exists(
        pid
    ):

        return

    print(
        "🧹 Eski Strategy Lab lock temizleniyor."
    )

    remove_lock()


def acquire_lock(
    run_id: str,
) -> bool:

    cleanup_stale_lock()

    existing = read_lock()

    if existing:

        pid = existing.get(
            "pid"
        )

        if process_exists(
            pid
        ):

            print(
                "⚠️ Strategy Lab "
                "zaten çalışıyor."
            )

            print(
                f"   PID: {pid}"
            )

            print(
                f"   Run ID: "
                f"{existing.get('run_id', '-')}"
            )

            return False

        remove_lock()

    payload = {
        "pid": os.getpid(),
        "run_id": run_id,
        "created_at": now_iso(),
        "script": str(
            STRATEGY_LAB_FILE
        ),
    }

    try:

        with LOCK_FILE.open(
            "x",
            encoding="utf-8",
        ) as file:

            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return True

    except FileExistsError:

        cleanup_stale_lock()

        try:

            with LOCK_FILE.open(
                "x",
                encoding="utf-8",
            ) as file:

                json.dump(
                    payload,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            return True

        except FileExistsError:

            print(
                "❌ Strategy Lab lock alınamadı."
            )

            return False


# =========================================================
# RUNTIME STATE BRIDGE
# =========================================================

def read_runtime_state() -> dict[str, Any]:
    if not RUNTIME_STATE_FILE.exists():
        return {
            "version": 1,
            "system": {
                "status": "IDLE",
                "message": "MarketHQ hazır.",
                "run_count": 0,
                "current_run_id": None,
            },
            "agents": {},
            "events": [],
            "tasks": [],
        }

    try:
        with RUNTIME_STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            state = json.load(file)

        if not isinstance(state, dict):
            raise ValueError(
                "Geçersiz runtime state."
            )

        if not isinstance(
            state.get("agents"),
            dict,
        ):
            state["agents"] = {}

        if not isinstance(
            state.get("events"),
            list,
        ):
            state["events"] = []

        if not isinstance(
            state.get("tasks"),
            list,
        ):
            state["tasks"] = []

        if not isinstance(
            state.get("system"),
            dict,
        ):
            state["system"] = {
                "status": "IDLE",
                "message": "MarketHQ hazır.",
                "run_count": 0,
                "current_run_id": None,
            }

        return state

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:

        print(
            f"⚠️ Runtime state okunamadı: {error}"
        )

        return {
            "version": 1,
            "system": {
                "status": "IDLE",
                "message": "MarketHQ hazır.",
                "run_count": 0,
                "current_run_id": None,
            },
            "agents": {},
            "events": [],
            "tasks": [],
        }


def write_runtime_state(
    state: dict[str, Any],
) -> bool:

    payload = json.dumps(
        state,
        ensure_ascii=False,
        indent=2,
    )

    try:
        with RUNTIME_STATE_TEMP_FILE.open(
            "w",
            encoding="utf-8",
        ) as file:

            file.write(payload)
            file.flush()
            os.fsync(file.fileno())

    except OSError as error:

        print(
            "⚠️ Runtime state temp "
            f"yazılamadı: {error}"
        )

        return False

    for attempt in range(1, 6):

        try:

            os.replace(
                str(
                    RUNTIME_STATE_TEMP_FILE
                ),
                str(
                    RUNTIME_STATE_FILE
                ),
            )

            return True

        except PermissionError as error:

            if attempt == 5:
                print(
                    "⚠️ Runtime state "
                    f"kilitli: {error}"
                )

            time.sleep(
                0.15 * attempt
            )

        except OSError as error:

            if attempt == 5:
                print(
                    "⚠️ Runtime state "
                    f"yazma hatası: {error}"
                )

            time.sleep(
                0.15 * attempt
            )

    try:

        with RUNTIME_STATE_FILE.open(
            "w",
            encoding="utf-8",
        ) as file:

            file.write(payload)
            file.flush()
            os.fsync(file.fileno())

        return True

    except OSError as error:

        print(
            "❌ Runtime state fallback "
            f"başarısız: {error}"
        )

        return False


def update_strategy_runtime(
    status: str,
    run_id: str,
    completed_count: int,
    total_symbols: int,
    detail: str,
    current_symbol: str | None = None,
) -> bool:

    state = read_runtime_state()

    agents = state.setdefault(
        "agents",
        {},
    )

    progress = (
        completed_count
        / total_symbols
        * 100.0
        if total_symbols > 0
        else 0.0
    )

    progress = max(
        0.0,
        min(
            100.0,
            progress,
        ),
    )

    strategy_agent = {
        "name": "Strategy Lab",
        "status": normalize_status(
            status
        ),
        "progress": progress,
        "detail": detail,
        "updated_at": now_iso(),
        "run_id": run_id,
        "completed_count": completed_count,
        "total_symbols": total_symbols,
    }

    if current_symbol:
        strategy_agent[
            "current_symbol"
        ] = current_symbol

    agents["strategy_lab"] = strategy_agent

    events = state.setdefault(
        "events",
        [],
    )

    event_message = detail

    if current_symbol:
        event_message = (
            f"{detail} | "
            f"Sembol: {current_symbol}"
        )

    events.append(
        {
            "timestamp": now_iso(),
            "agent_id": "strategy_lab",
            "agent_name": "Strategy Lab",
            "event_type": (
                "status_update"
            ),
            "message": event_message,
            "run_id": run_id,
        }
    )

    # Feed'i sınırsız büyütme.
    if len(events) > 100:
        del events[:-100]

    return write_runtime_state(
        state
    )


def set_strategy_runtime(
    status: str,
    run_id: str,
    detail: str,
) -> bool:

    return update_strategy_runtime(
        status=status,
        run_id=run_id,
        completed_count=0,
        total_symbols=TOTAL_SYMBOLS,
        detail=detail,
    )


# =========================================================
# RESULT WRITE
# =========================================================

def write_result(
    data: dict[str, Any],
) -> bool:

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )

    # -----------------------------------------------------
    # TEMP WRITE
    # -----------------------------------------------------

    try:

        with TEMP_RESULT_FILE.open(
            "w",
            encoding="utf-8",
        ) as file:

            file.write(
                payload
            )

            file.flush()

            os.fsync(
                file.fileno()
            )

    except Exception as error:

        print(
            "❌ Strategy Lab geçici sonuç "
            f"dosyası yazılamadı: {error}"
        )

        return False

    # -----------------------------------------------------
    # ATOMIC REPLACE
    # -----------------------------------------------------

    for attempt in range(
        1,
        RESULT_WRITE_RETRIES + 1,
    ):

        try:

            os.replace(
                str(TEMP_RESULT_FILE),
                str(RESULT_FILE),
            )

            return True

        except PermissionError as error:

            print(
                "⚠️ Sonuç dosyası Windows "
                f"tarafından kilitli. "
                f"Deneme "
                f"{attempt}/"
                f"{RESULT_WRITE_RETRIES}"
            )

            if attempt == RESULT_WRITE_RETRIES:

                print(
                    f"   Son hata: {error}"
                )

            time.sleep(
                RESULT_WRITE_SLEEP
                * attempt
            )

        except OSError as error:

            print(
                "⚠️ Result replace hatası: "
                f"{error}"
            )

            time.sleep(
                RESULT_WRITE_SLEEP
                * attempt
            )

    # -----------------------------------------------------
    # FALLBACK
    # -----------------------------------------------------

    print(
        "⚠️ Atomik replace başarısız."
    )

    print(
        "   Direkt dosya yazma deneniyor..."
    )

    for attempt in range(
        1,
        4,
    ):

        try:

            with RESULT_FILE.open(
                "w",
                encoding="utf-8",
            ) as file:

                file.write(
                    payload
                )

                file.flush()

                os.fsync(
                    file.fileno()
                )

            try:

                if TEMP_RESULT_FILE.exists():
                    TEMP_RESULT_FILE.unlink()

            except OSError:
                pass

            print(
                "✅ Result fallback ile kaydedildi."
            )

            return True

        except PermissionError as error:

            print(
                "⚠️ Fallback yazma kilitli. "
                f"Deneme {attempt}/3"
            )

            if attempt == 3:

                print(
                    f"   Son hata: {error}"
                )

            time.sleep(
                1.0
            )

        except OSError as error:

            print(
                f"⚠️ Fallback OSError: {error}"
            )

            time.sleep(
                1.0
            )

    # -----------------------------------------------------
    # LAST CLEANUP
    # -----------------------------------------------------

    try:

        if TEMP_RESULT_FILE.exists():
            TEMP_RESULT_FILE.unlink()

    except OSError:
        pass

    return False


# =========================================================
# INITIAL RESULT
# =========================================================

def build_initial_result(
    run_id: str,
) -> dict[str, Any]:

    return {
        "exists": True,

        "status": "running",

        "engine": (
            "FIN[SYS] V4.4"
        ),

        "run_id": run_id,

        "started_at": now_iso(),

        "completed_at": None,

        "progress": 0.0,

        "completed_count": 0,

        "total_symbols": TOTAL_SYMBOLS,

        "result_rows": 0,

        "symbols": [],

        "bist": {},

        "us": {},

        "global": {},

        "warnings": [],

        "errors": [],
    }


# =========================================================
# RESULT PARSING
# =========================================================

def parse_symbol_line(
    line: str,
) -> dict[str, Any] | None:

    pattern = re.compile(
        r"^"
        r"(?P<symbol>\S+)"
        r"\s*\|\s*"
        r"(?P<market>BIST|US)"
        r"\s*\|\s*"
        r"Test\s+(?P<trades>\d+)"
        r"\s*\|\s*"
        r"20G\s+(?P<return>[^|]+)"
        r"\s*\|\s*"
        r"Win\s+(?P<win>[^|]+)"
        r"\s*\|\s*"
        r"PF\s+(?P<pf>[^|]+)"
        r"\s*\|\s*"
        r"Sharpe\s+(?P<sharpe>[^|]+)"
        r"\s*\|\s*"
        r"MaxDD\s+(?P<maxdd>[^|]+)"
        r"\s*\|\s*"
        r"Bench\s+(?P<bench>[^|]+)"
        r"\s*\|\s*"
        r"Rel\s+(?P<rel>[^|]+)"
        r"(?:\s*\|\s*"
        r"Verdict\s+(?P<verdict>[^⚠️\r\n]+))?"
        r"(?P<warning>\s*⚠️.*)?"
        r"$"
    )

    match = pattern.search(
        line.strip()
    )

    if not match:
        return None

    return {
        "symbol": match.group(
            "symbol"
        ).strip(),

        "market": match.group(
            "market"
        ).strip(),

        "test_trades": int(
            match.group(
                "trades"
            )
        ),

        "test_return_20d": (
            parse_percent(
                match.group(
                    "return"
                )
            )
        ),

        "win_rate": (
            parse_percent(
                match.group(
                    "win"
                )
            )
        ),

        "profit_factor": safe_float(
            match.group(
                "pf"
            ).strip()
        ),

        "sharpe": safe_float(
            match.group(
                "sharpe"
            ).strip()
        ),

        "max_drawdown": (
            parse_percent(
                match.group(
                    "maxdd"
                )
            )
        ),

        "benchmark": (
            parse_percent(
                match.group(
                    "bench"
                )
            )
        ),

        "relative": (
            parse_percent(
                match.group(
                    "rel"
                )
            )
        ),

        "research_verdict": (
            (
                match.group(
                    "verdict"
                ).strip()
                if match.group(
                    "verdict"
                )
                else "INCONCLUSIVE"
            )
        ),

        "small_sample_warning": (
            bool(
                match.group(
                    "warning"
                )
            )
        ),

        "raw": line.strip(),
    }


# =========================================================
# AGGREGATE PARSER
# =========================================================

def parse_aggregate(
    lines: list[str],
) -> dict[str, Any]:

    output = {
        "bist": {},
        "us": {},
        "global": {},
    }

    current_market = None
    current_section = None

    for raw_line in lines:

        line = raw_line.strip()

        if line == "🌍 BIST":

            current_market = "bist"
            current_section = "market"
            continue

        if line == "🌍 US":

            current_market = "us"
            current_section = "market"
            continue

        if (
            "GLOBAL MARKET HQ PORTFOLIO"
            in line
        ):

            current_market = "global"
            current_section = "global"
            continue

        if not line:
            continue

        if (
            current_market in {
                "bist",
                "us",
            }
            and current_section == "market"
        ):

            target = output[
                current_market
            ]

            if line.startswith(
                "Sembol sayısı:"
            ):

                match = re.search(
                    r"(\d+)",
                    line,
                )

                if match:
                    target[
                        "symbol_count"
                    ] = int(
                        match.group(1)
                    )

                continue

            if (
                "Portföy toplam test getirisi:"
                in line
            ):

                target[
                    "total_return"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Portföy Sharpe:"
                in line
            ):

                target[
                    "sharpe"
                ] = safe_float(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Portföy MaxDD:"
                in line
            ):

                target[
                    "max_dd"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Benchmark:"
                in line
                and
                "farkı"
                not in line
            ):

                target[
                    "benchmark"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Benchmark farkı:"
                in line
            ):

                target[
                    "benchmark_diff"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Pooled test işlem:"
                in line
            ):

                match = re.search(
                    r"(\d+)",
                    line,
                )

                if match:
                    target[
                        "trade_count"
                    ] = int(
                        match.group(1)
                    )

                continue

            if (
                "Pooled Win Rate:"
                in line
            ):

                target[
                    "win_rate"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if (
                "Pooled Profit Factor:"
                in line
            ):

                target[
                    "profit_factor"
                ] = safe_float(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

        if (
            current_market == "global"
            and current_section == "global"
        ):

            target = output[
                "global"
            ]

            if (
                "Toplam portföy test getirisi:"
                in line
            ):

                target[
                    "total_return"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if "Global Sharpe:" in line:

                target[
                    "sharpe"
                ] = safe_float(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if "Global MaxDD:" in line:

                target[
                    "max_dd"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if "Pooled test işlem:" in line:

                match = re.search(
                    r"(\d+)",
                    line,
                )

                if match:
                    target[
                        "trade_count"
                    ] = int(
                        match.group(1)
                    )

                continue

            if "Pooled Win Rate:" in line:

                target[
                    "win_rate"
                ] = parse_percent(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

            if "Pooled Profit Factor:" in line:

                target[
                    "profit_factor"
                ] = safe_float(
                    line.split(
                        ":",
                        1
                    )[1].strip()
                )

                continue

    return output


# =========================================================
# PARSE OUTPUT
# =========================================================

def parse_output(
    lines: list[str],
) -> dict[str, Any]:

    result = {
        "symbols": [],
        "warnings": [],
        "errors": [],
    }

    seen_symbols = set()

    for line in lines:

        parsed = parse_symbol_line(
            line
        )

        if parsed is not None:

            symbol = parsed[
                "symbol"
            ]

            if symbol not in seen_symbols:

                result[
                    "symbols"
                ].append(
                    parsed
                )

                seen_symbols.add(
                    symbol
                )

            continue

        stripped = line.strip()

        if stripped.startswith(
            "⚠️"
        ):

            result[
                "warnings"
            ].append(
                stripped
            )

        if stripped.startswith(
            "❌"
        ):

            result[
                "errors"
            ].append(
                stripped
            )

    aggregates = parse_aggregate(
        lines
    )

    result.update(
        aggregates
    )

    return result


# =========================================================
# PROGRESS
# =========================================================

def count_completed_symbols(
    lines: list[str],
) -> int:

    completed = set()

    for line in lines:

        match = re.search(
            r"✅\s+(\S+)\s+tamamlandı",
            line,
        )

        if match:

            completed.add(
                match.group(1).strip()
            )

    return len(
        completed
    )


# =========================================================
# STREAM PROCESS
# =========================================================

def run_subprocess(
    run_id: str,
) -> tuple[
    int,
    list[str],
    str | None,
]:

    if not STRATEGY_LAB_FILE.exists():

        return (
            1,
            [],
            "strategy_lab.py bulunamadı.",
        )

    command = [
        sys.executable,
        "-u",
        str(
            STRATEGY_LAB_FILE
        ),
    ]

    print()
    print(
        "============================================================"
    )
    print(
        "🧪 STRATEGY LAB RUNNER"
    )
    print(
        "============================================================"
    )

    print(
        f"Run ID: {run_id}"
    )

    print(
        f"Engine: {STRATEGY_LAB_FILE}"
    )

    print()

    try:

        # Windows console encoding (cp1254) can crash strategy_lab.py
        # when it prints emoji/unicode. Force the child Python process
        # to use UTF-8 for stdout/stderr.
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"

        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    except Exception as error:

        return (
            1,
            [],
            (
                "Strategy Lab process "
                f"başlatılamadı: {error}"
            ),
        )

    lines = []

    started = time.monotonic()

    try:

        if process.stdout is not None:

            for line in iter(
                process.stdout.readline,
                "",
            ):

                if not line:

                    if (
                        process.poll()
                        is not None
                    ):
                        break

                    continue

                line = line.rstrip(
                    "\r\n"
                )

                lines.append(
                    line
                )

                print(
                    line,
                    flush=True,
                )

                # ---------------------------------------------
                # AGENTSPACE LIVE STATUS
                # ---------------------------------------------

                completed_count = (
                    count_completed_symbols(
                        lines
                    )
                )

                current_symbol_match = re.search(
                    r"🔬\s*Deney başlıyor:\s*(\S+)",
                    line,
                )

                completed_symbol_match = re.search(
                    r"✅\s*(\S+)\s*tamamlandı",
                    line,
                )

                current_symbol = (
                    current_symbol_match.group(1)
                    if current_symbol_match
                    else None
                )

                if completed_symbol_match:
                    current_symbol = (
                        completed_symbol_match.group(1)
                    )

                detail = (
                    f"Çalışıyor — "
                    f"{completed_count}/"
                    f"{TOTAL_SYMBOLS} sembol tamamlandı."
                )

                if completed_symbol_match:
                    detail = (
                        f"{completed_symbol_match.group(1)} "
                        "tamamlandı — "
                        f"{completed_count}/"
                        f"{TOTAL_SYMBOLS}."
                    )

                elif current_symbol_match:
                    detail = (
                        f"{current_symbol_match.group(1)} "
                        "üzerinde çalışıyor — "
                        f"{completed_count}/"
                        f"{TOTAL_SYMBOLS}."
                    )

                update_strategy_runtime(
                    status="WORKING",
                    run_id=run_id,
                    completed_count=completed_count,
                    total_symbols=TOTAL_SYMBOLS,
                    detail=detail,
                    current_symbol=current_symbol,
                )

                elapsed = (
                    time.monotonic()
                    - started
                )

                if elapsed > PROCESS_TIMEOUT:

                    print(
                        "❌ Strategy Lab timeout."
                    )

                    try:

                        process.kill()

                    except OSError:
                        pass

                    return (
                        1,
                        lines,
                        "Strategy Lab timeout.",
                    )

        return_code = process.wait(
            timeout=30
        )

        return (
            return_code,
            lines,
            None,
        )

    except subprocess.TimeoutExpired:

        try:
            process.kill()
        except OSError:
            pass

        return (
            1,
            lines,
            "Process wait timeout.",
        )

    except Exception as error:

        try:
            process.kill()
        except OSError:
            pass

        return (
            1,
            lines,
            str(error),
        )


# =========================================================
# ERROR RESULT
# =========================================================

def build_error_result(
    run_id: str,
    started_at: str,
    message: str,
    lines: list[str],
) -> dict[str, Any]:

    parsed = parse_output(
        lines
    )

    completed_count = (
        count_completed_symbols(
            lines
        )
    )

    errors = list(
        parsed.get(
            "errors",
            []
        )
    )

    if message:

        errors.append(
            message
        )

    return {
        "exists": True,

        "status": "error",

        "engine": (
            "FIN[SYS] V4.4"
        ),

        "run_id": run_id,

        "started_at": started_at,

        "completed_at": now_iso(),

        "progress": (
            completed_count
            / TOTAL_SYMBOLS
            * 100.0
            if TOTAL_SYMBOLS
            else 0.0
        ),

        "completed_count": (
            completed_count
        ),

        "total_symbols": (
            TOTAL_SYMBOLS
        ),

        "result_rows": len(
            parsed.get(
                "symbols",
                []
            )
        ),

        "symbols": parsed.get(
            "symbols",
            []
        ),

        "bist": parsed.get(
            "bist",
            {}
        ),

        "us": parsed.get(
            "us",
            {}
        ),

        "global": parsed.get(
            "global",
            {}
        ),

        "warnings": parsed.get(
            "warnings",
            []
        ),

        "errors": errors,

        "return_code": None,
    }


# =========================================================
# MAIN RUNNER
# =========================================================

def run_strategy_lab():

    run_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
        +
        "_"
        +
        str(
            os.getpid()
        )
    )

    started_at = now_iso()

    # -----------------------------------------------------
    # LOCK
    # -----------------------------------------------------

    if not acquire_lock(
        run_id
    ):

        return

    # -----------------------------------------------------
    # AGENTSPACE -> WORKING
    # -----------------------------------------------------

    update_strategy_runtime(
        status="WORKING",
        run_id=run_id,
        completed_count=0,
        total_symbols=TOTAL_SYMBOLS,
        detail=(
            "Strategy Lab başlatıldı — "
            "veriler hazırlanıyor."
        ),
    )

    # -----------------------------------------------------
    # INITIAL RESULT
    # -----------------------------------------------------

    initial_result = (
        build_initial_result(
            run_id
        )
    )

    if not write_result(
        initial_result
    ):

        print(
            "⚠️ Initial result dosyası "
            "yazılamadı."
        )

    all_lines = []

    try:

        # -------------------------------------------------
        # RUN
        # -------------------------------------------------

        return_code, lines, process_error = (
            run_subprocess(
                run_id
            )
        )

        all_lines = lines

        # -------------------------------------------------
        # PARSE
        # -------------------------------------------------

        parsed = parse_output(
            lines
        )

        completed_count = (
            count_completed_symbols(
                lines
            )
        )

        symbols = parsed.get(
            "symbols",
            []
        )

        errors = parsed.get(
            "errors",
            []
        )

        warnings = parsed.get(
            "warnings",
            []
        )

        if process_error:

            errors.append(
                process_error
            )

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        if (
            return_code == 0
            and not process_error
        ):

            status = "completed"

        else:

            status = "error"

        # -------------------------------------------------
        # AGENTSPACE -> FINAL STATUS
        # -------------------------------------------------

        if status == "completed":

            update_strategy_runtime(
                status="COMPLETED",
                run_id=run_id,
                completed_count=completed_count,
                total_symbols=TOTAL_SYMBOLS,
                detail=(
                    "Strategy Lab tamamlandı — "
                    f"{completed_count}/"
                    f"{TOTAL_SYMBOLS} sembol işlendi."
                ),
            )

        else:

            update_strategy_runtime(
                status="ERROR",
                run_id=run_id,
                completed_count=completed_count,
                total_symbols=TOTAL_SYMBOLS,
                detail=(
                    "Strategy Lab hata ile sonlandı."
                ),
            )

        # -------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------

        final_result = {
            "exists": True,

            "status": status,

            "engine": (
                "FIN[SYS] V4.4"
            ),

            "run_id": run_id,

            "started_at": (
                started_at
            ),

            "completed_at": (
                now_iso()
            ),

            "progress": (
                completed_count
                / TOTAL_SYMBOLS
                * 100.0
                if TOTAL_SYMBOLS
                else 0.0
            ),

            "completed_count": (
                completed_count
            ),

            "total_symbols": (
                TOTAL_SYMBOLS
            ),

            "result_rows": len(
                symbols
            ),

            "symbols": symbols,

            "bist": parsed.get(
                "bist",
                {}
            ),

            "us": parsed.get(
                "us",
                {}
            ),

            "global": parsed.get(
                "global",
                {}
            ),

            "warnings": warnings,

            "errors": errors,

            "return_code": (
                return_code
            ),

            "research_version": (
                "V4.4"
            ),

            "process_pid": (
                os.getpid()
            ),
        }

        print()
        print(
            "============================================================"
        )

        print(
            "📋 STRATEGY LAB SONUÇ ÖZETİ"
        )

        print(
            "============================================================"
        )

        print(
            f"Status: {status}"
        )

        print(
            f"Tamamlanan sembol: "
            f"{completed_count}/"
            f"{TOTAL_SYMBOLS}"
        )

        print(
            f"Parsed result: "
            f"{len(symbols)}"
        )

        print(
            f"Return code: "
            f"{return_code}"
        )

        print()

        # -------------------------------------------------
        # FINAL WRITE
        # -------------------------------------------------

        saved = write_result(
            final_result
        )

        if saved:

            print(
                "✅ Strategy Lab sonucu "
                "dashboard dosyasına kaydedildi."
            )

        else:

            print(
                "❌ Strategy Lab sonucu "
                "dosyaya kaydedilemedi."
            )

    except Exception as error:

        print()
        print(
            "❌ RUNNER KRİTİK HATA:"
        )

        print(
            f"   {error}"
        )

        completed_count = (
            count_completed_symbols(
                all_lines
            )
        )

        update_strategy_runtime(
            status="ERROR",
            run_id=run_id,
            completed_count=completed_count,
            total_symbols=TOTAL_SYMBOLS,
            detail=(
                "Strategy Lab kritik hata: "
                f"{error}"
            ),
        )

        error_result = (
            build_error_result(
                run_id=run_id,
                started_at=started_at,
                message=str(error),
                lines=all_lines,
            )
        )

        try:

            write_result(
                error_result
            )

        except Exception as write_error:

            print(
                "❌ Hata sonucu bile "
                "yazılamadı:"
            )

            print(
                f"   {write_error}"
            )

    finally:

        # -------------------------------------------------
        # LOCK RELEASE
        # -------------------------------------------------

        current_lock = read_lock()

        if current_lock:

            current_pid = (
                current_lock.get(
                    "pid"
                )
            )

            current_run_id = (
                current_lock.get(
                    "run_id"
                )
            )

            if (
                current_pid
                == os.getpid()
                and current_run_id
                == run_id
            ):

                remove_lock()

        print()
        print(
            "🏁 Strategy Lab Runner kapatıldı."
        )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    run_strategy_lab()

