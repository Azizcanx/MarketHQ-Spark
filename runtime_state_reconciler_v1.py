
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "runtime_state.json"
BACKUP_DIR = BASE_DIR / "runtime_state_backups"

STALE_MINUTES = 10


def now():
    return datetime.now(timezone.utc)


def read_state():
    if not STATE_FILE.exists():
        return {}
    return json.loads(
        STATE_FILE.read_text(
            encoding="utf-8"
        )
    )


def write_state(state):
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"runtime_state_{stamp}.json"
    backup.write_text(
        STATE_FILE.read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(STATE_FILE)
    return backup


def list_python_commandlines():
    """Windows'ta çalışan Python süreçlerinin command line bilgisini al."""
    if os.name != "nt":
        return []

    script = (
        "Get-CimInstance Win32_Process "
        "-Filter \"Name='python.exe'\" "
        "| Select-Object ProcessId,CommandLine "
        "| ConvertTo-Json -Compress"
    )

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )

        if result.returncode != 0:
            return []

        raw = (result.stdout or "").strip()
        if not raw:
            return []

        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        return data if isinstance(data, list) else []
    except Exception:
        return []


def process_is_active(processes, filename):
    needle = filename.lower()
    for item in processes:
        command = str(item.get("CommandLine") or "").lower()
        if needle in command:
            return True
    return False


def parse_time(value):
    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except Exception:
        return None


def main():
    state = read_state()
    system = state.get("system")
    if not isinstance(system, dict):
        print("runtime_state.json içinde system bölümü bulunamadı.")
        return 2

    status = str(system.get("status", "")).upper()
    current_run_id = system.get("current_run_id")
    current_task = system.get("current_task")
    updated_at = parse_time(system.get("updated_at"))

    print("RUNTIME STATE RECONCILER V1")
    print(f"Status       : {status}")
    print(f"Run ID       : {current_run_id}")
    print(f"Current task : {current_task}")
    print(f"Updated at   : {system.get('updated_at')}")

    if status != "WORKING":
        print("State zaten WORKING değil. Değişiklik yok.")
        return 0

    processes = list_python_commandlines()

    main_active = process_is_active(
        processes,
        "main.py",
    )
    brain_active = process_is_active(
        processes,
        "brain_orchestrator_v1.py",
    )
    controller_active = process_is_active(
        processes,
        "automation_controller",
    )
    service_active = process_is_active(
        processes,
        "automation_service",
    )

    print(
        "Aktif processler: "
        f"main={main_active}, "
        f"brain={brain_active}, "
        f"controller={controller_active}, "
        f"service={service_active}"
    )

    # A real main/brain task is active: never force IDLE.
    if main_active or brain_active:
        print("Gerçek aktif işlem bulundu. State değiştirilmedi.")
        return 0

    # When timestamps are available, only repair clearly stale states.
    stale = True
    if updated_at is not None:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(
                tzinfo=timezone.utc
            )
        stale = (
            now() - updated_at
        ) > timedelta(
            minutes=STALE_MINUTES
        )

    # Empty run/task + stale WORKING is the exact stale-state pattern
    # observed in the current MarketHQ runtime state.
    suspicious_stale_state = (
        stale
        and not current_run_id
        and not current_task
    )

    if not suspicious_stale_state:
        print(
            "WORKING state aktif işlem olmadan net biçimde stale "
            "olarak doğrulanamadı. Değişiklik yapılmadı."
        )
        return 0

    backup = write_state(
        {
            **state,
            "system": {
                **system,
                "status": "IDLE",
                "message": (
                    "Runtime state reconciler stale WORKING state'i "
                    "IDLE olarak düzeltti."
                ),
                "updated_at": now().isoformat(
                    timespec="seconds"
                ),
                "current_task": None,
                "current_run_id": None,
            },
        }
    )

    print(f"STALE WORKING -> IDLE düzeltildi.")
    print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

