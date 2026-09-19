
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONTROLLER = BASE_DIR / "automation_controller_v5.py"
STATE_FILE = BASE_DIR / "automation_service_state.json"
PID_FILE = BASE_DIR / "automation_service.pid"
LOG_FILE = BASE_DIR / "automation_service.log"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, fallback):
    try:
        if not path.exists():
            return fallback
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    tmp.replace(path)


def log(message):
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(line + "\n")


def set_state(**updates):
    state = read_json(STATE_FILE, {})
    state.update(updates)
    state["updated_at"] = now()
    write_json(STATE_FILE, state)


def pid_is_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (ValueError, OSError, ProcessLookupError, PermissionError):
        return False


def existing_service_alive():
    state = read_json(STATE_FILE, {})
    pid = state.get("pid")

    if pid and pid_is_alive(pid):
        return True, int(pid)

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if pid_is_alive(pid):
                return True, pid
        except Exception:
            pass

    return False, None


def taskkill(pid):
    if os.name != "nt":
        try:
            os.kill(int(pid), 15)
            return True
        except Exception:
            return False

    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    once = "--once" in sys.argv
    auto_heal = "--auto-heal" in sys.argv

    interval = 60
    cooldown = 900
    force_discovery = "--force-discovery" in sys.argv

    for arg in sys.argv:
        if arg.startswith("--interval="):
            try:
                interval = max(10, int(arg.split("=", 1)[1]))
            except ValueError:
                interval = 60

        if arg.startswith("--discovery-cooldown="):
            try:
                cooldown = max(60, int(arg.split("=", 1)[1]))
            except ValueError:
                cooldown = 900

    if not CONTROLLER.exists():
        print(f"Controller bulunamadı: {CONTROLLER}")
        return 2

    alive, old_pid = existing_service_alive()
    if alive:
        print(f"Automation Service zaten çalışıyor. PID={old_pid}")
        return 2

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    set_state(
        service="automation_service_v2",
        status="STARTING",
        pid=os.getpid(),
        controller_pid=None,
        controller=str(CONTROLLER),
        project_root=str(BASE_DIR),
        auto_heal_enabled=auto_heal,
        interval_seconds=interval,
        discovery_cooldown_seconds=cooldown,
        force_discovery=force_discovery,
        started_at=now(),
        stopped_at=None,
        return_code=None,
        error=None,
    )

    log("Automation Service V2 başlatıldı.")
    log(f"Project root: {BASE_DIR}")

    command = [
        sys.executable,
        "-u",
        str(CONTROLLER),
        f"--interval={interval}",
        f"--discovery-cooldown={cooldown}",
    ]

    if auto_heal:
        command.append("--auto-heal")
    if force_discovery:
        command.append("--force-discovery")
    if once:
        command.append("--once")

    process = None

    try:
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            if os.name == "nt"
            else 0
        )

        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )

        set_state(
            status="RUNNING",
            controller_pid=process.pid,
        )

        log(f"Controller V5 başlatıldı. PID={process.pid}")

        assert process.stdout is not None

        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if line:
                log(f"CONTROLLER | {line}")

        return_code = process.wait()

        set_state(
            status="STOPPED" if return_code == 0 else "ERROR",
            controller_pid=None,
            return_code=return_code,
            stopped_at=now(),
        )

        log(f"Controller sona erdi. return_code={return_code}")
        return return_code

    except KeyboardInterrupt:
        log("Service kullanıcı tarafından durduruluyor.")
        if process is not None and process.poll() is None:
            taskkill(process.pid)

        set_state(
            status="STOPPED",
            controller_pid=None,
            stopped_at=now(),
            return_code=0,
        )
        return 0

    except Exception as exc:
        log(f"Service hatası: {exc}")
        if process is not None and process.poll() is None:
            taskkill(process.pid)

        set_state(
            status="ERROR",
            controller_pid=None,
            error=str(exc),
            stopped_at=now(),
            return_code=1,
        )
        return 1

    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

