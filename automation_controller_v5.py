
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ------------------------------------------------------------
# MarketHQ Autonomous Automation Controller V5
# - Finds project root robustly
# - Shows exactly which files are being used
# - Health -> Discovery -> Queue -> Brain -> Feedback -> Repeat
# ------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root():
    candidates = [
        SCRIPT_DIR,
        Path.cwd(),
        SCRIPT_DIR.parent,
        Path.cwd().parent,
    ]

    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "market_hq.db").exists() and (
            (candidate / "main.py").exists()
            or (candidate / "agents").exists()
        ):
            return candidate

    # Last resort: use the controller's directory.
    return SCRIPT_DIR


BASE_DIR = find_project_root()

DB_FILE = BASE_DIR / "market_hq.db"
STATE_FILE = BASE_DIR / "runtime_state.json"
AUTOMATION_STATE_FILE = BASE_DIR / "automation_state.json"

SELF_HEALING = BASE_DIR / "self_healing_engine_v1.py"
LEARNING_FEEDBACK = BASE_DIR / "learning_feedback_engine_v1.py"
BRAIN_ORCHESTRATOR = BASE_DIR / "agents" / "brain_orchestrator_v1.py"
MARKET_HQ_MAIN = BASE_DIR / "main.py"

LOCK_FILE = BASE_DIR / "automation_controller.lock"

DEFAULT_INTERVAL = 60
DEFAULT_DISCOVERY_COOLDOWN = 900


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    try:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def read_json(path, fallback):
    try:
        if not path.exists():
            return fallback
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except Exception:
        return fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    tmp.replace(path)


def acquire_lock():
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return True

    except FileExistsError:
        try:
            pid_text = LOCK_FILE.read_text(
                encoding="utf-8",
                errors="ignore",
            ).strip()
            pid = int(pid_text)
            os.kill(pid, 0)
            return False
        except Exception:
            try:
                LOCK_FILE.unlink(missing_ok=True)
            except OSError:
                return False
            return acquire_lock()

    except OSError:
        return False


def release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def runtime_snapshot():
    state = read_json(STATE_FILE, {})
    system = state.get("system")
    if not isinstance(system, dict):
        system = {}

    return {
        "status": str(system.get("status", "UNKNOWN")).upper(),
        "message": str(system.get("message", "")),
        "current_run_id": system.get("current_run_id"),
        "current_task": system.get("current_task"),
    }


def queue_snapshot():
    if not DB_FILE.exists():
        return {
            "exists": False,
            "queued": 0,
            "active": 0,
            "completed": 0,
        }

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)

        row = conn.execute(
            """
            SELECT
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(status, '')) IN
                        ('QUEUED','PENDING','OPEN','NEW')
                        THEN 1 ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(status, '')) NOT IN
                        ('COMPLETED','CANCELLED','DONE','CLOSED')
                        THEN 1 ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(status, '')) IN
                        ('COMPLETED','DONE','CLOSED')
                        THEN 1 ELSE 0
                    END
                )
            FROM brain_research_queue
            """
        ).fetchone()

        row = row or (0, 0, 0)

        return {
            "exists": True,
            "queued": int(row[0] or 0),
            "active": int(row[1] or 0),
            "completed": int(row[2] or 0),
        }

    except sqlite3.Error as exc:
        return {
            "exists": True,
            "queued": 0,
            "active": 0,
            "completed": 0,
            "error": str(exc),
        }

    finally:
        if conn is not None:
            conn.close()


def run_subprocess(script, args=None, timeout=180):
    if not script.exists():
        return {
            "ok": False,
            "return_code": None,
            "message": f"{script} bulunamadı.",
            "script": str(script),
        }

    command = [
        sys.executable,
        "-u",
        str(script),
        *(list(args or [])),
    ]

    try:
        result = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        return {
            "ok": result.returncode == 0,
            "return_code": result.returncode,
            "stdout_tail": (result.stdout or "")[-3000:],
            "stderr_tail": (result.stderr or "")[-2500:],
            "script": str(script),
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "timeout": True,
            "return_code": None,
            "message": f"{script.name} {timeout}s timeout.",
            "script": str(script),
        }

    except Exception as exc:
        return {
            "ok": False,
            "return_code": None,
            "message": str(exc),
            "script": str(script),
        }


def health_check(auto_heal=False):
    result = run_subprocess(
        SELF_HEALING,
        ["--auto"] if auto_heal else [],
        timeout=180,
    )

    report = read_json(
        BASE_DIR / "self_healing" / "last_report.json",
        {},
    )

    result["report"] = report
    result["syntax_errors"] = int(
        report.get("syntax_errors", 0) or 0
    )
    result["runtime_error_records"] = int(
        report.get("runtime_error_records", 0) or 0
    )

    return result


def learning_feedback():
    result = run_subprocess(
        LEARNING_FEEDBACK,
        timeout=180,
    )

    result["report"] = read_json(
        BASE_DIR / "learning_feedback_state.json",
        {},
    )

    return result


def is_brain_running(process):
    return process is not None and process.poll() is None


def start_brain(process):
    if is_brain_running(process):
        return process, False, "Brain Orchestrator zaten çalışıyor."

    if not BRAIN_ORCHESTRATOR.exists():
        return None, False, (
            f"Brain Orchestrator bulunamadı: "
            f"{BRAIN_ORCHESTRATOR}"
        )

    try:
        kwargs = {
            "cwd": str(BASE_DIR),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(BRAIN_ORCHESTRATOR),
            ],
            **kwargs,
        )

        return (
            process,
            True,
            f"Brain Loop başlatıldı. PID={process.pid}",
        )

    except Exception as exc:
        return None, False, (
            f"Brain Loop başlatılamadı: {exc}"
        )


def discovery_gate(
    state,
    runtime,
    queue,
    cooldown_seconds,
    force=False,
):
    if not MARKET_HQ_MAIN.exists():
        return False, f"main.py bulunamadı: {MARKET_HQ_MAIN}"

    if runtime["status"] == "WORKING":
        return False, (
            "Runtime WORKING; mevcut MarketHQ işlemi "
            "bitene kadar bekleniyor."
        )

    if queue["active"] > 0:
        return False, (
            f"Araştırma kuyruğunda {queue['active']} "
            f"aktif görev var."
        )

    if force:
        return True, "Force discovery aktif."

    last_run = parse_iso(
        state.get("last_discovery_finished_at")
    )

    if last_run is not None:
        elapsed = (
            datetime.now(timezone.utc) - last_run
        ).total_seconds()

        if elapsed < cooldown_seconds:
            remaining = int(
                cooldown_seconds - elapsed
            )
            return False, (
                "Discovery cooldown aktif; "
                f"{remaining} saniye kaldı."
            )

    return True, "Discovery çalıştırılabilir."


def run_discovery():
    result = run_subprocess(
        MARKET_HQ_MAIN,
        timeout=1200,
    )

    automation_dir = BASE_DIR / "automation"
    automation_dir.mkdir(exist_ok=True)

    (
        automation_dir / "last_discovery_stdout.txt"
    ).write_text(
        result.get("stdout_tail", ""),
        encoding="utf-8",
    )

    (
        automation_dir / "last_discovery_stderr.txt"
    ).write_text(
        result.get("stderr_tail", ""),
        encoding="utf-8",
    )

    return result


def run_cycle(
    state,
    brain_process,
    *,
    auto_heal,
    discovery_enabled,
    cooldown_seconds,
    force_discovery,
):
    now = utc_now()
    state["last_cycle_started_at"] = now

    action = "WAITING"
    reason = "Yeni işlem gerekmiyor."

    # 1. HEALTH
    health = health_check(auto_heal=False)
    state["last_health"] = health

    syntax_errors = health["syntax_errors"]
    runtime_error_records = health[
        "runtime_error_records"
    ]

    if syntax_errors > 0:
        if auto_heal:
            healed = health_check(auto_heal=True)
            state["last_auto_heal"] = healed
            state["last_health"] = healed

            health = healed
            syntax_errors = healed["syntax_errors"]

            action = "AUTO_HEAL_ATTEMPT"
            reason = (
                "Syntax hataları için kontrollü onarım "
                f"denendi; kalan={syntax_errors}."
            )
        else:
            state.update(
                {
                    "action": "BLOCKED_SYNTAX",
                    "action_detail": (
                        f"{syntax_errors} syntax hatası bulundu; "
                        "Brain başlatılmadı."
                    ),
                    "safe_gate": {
                        "syntax_errors": syntax_errors,
                        "runtime_error_records": (
                            runtime_error_records
                        ),
                        "brain_blocked": True,
                    },
                    "updated_at": utc_now(),
                }
            )
            write_json(
                AUTOMATION_STATE_FILE,
                state,
            )
            return state, brain_process

    # 2. BRAIN TAMAMLANDI -> FEEDBACK
    if (
        brain_process is not None
        and brain_process.poll() is not None
    ):
        exit_code = brain_process.returncode
        brain_process = None

        state["last_brain_exit_code"] = exit_code
        state["last_brain_finished_at"] = now

        feedback = learning_feedback()
        state["last_learning_feedback"] = feedback

        created = int(
            (feedback.get("report") or {}).get(
                "queue_created",
                0,
            )
            or 0
        )

        action = "BRAIN_COMPLETED"
        reason = (
            f"Brain tamamlandı. Exit={exit_code}."
        )

        if feedback.get("ok") and created > 0:
            action = "FEEDBACK_CREATED_TASKS"
            reason += (
                f" Feedback {created} yeni araştırma "
                "görevi üretti."
            )

    runtime = runtime_snapshot()
    queue = queue_snapshot()

    state["runtime"] = runtime
    state["queue"] = queue

    # 3. DISCOVERY
    if (
        discovery_enabled
        and brain_process is None
        and syntax_errors == 0
    ):
        allowed, gate_reason = discovery_gate(
            state,
            runtime,
            queue,
            cooldown_seconds,
            force=force_discovery,
        )

        if allowed:
            state["last_discovery_started_at"] = now

            result = run_discovery()

            state["last_discovery_result"] = result
            state["last_discovery_finished_at"] = utc_now()

            runtime = runtime_snapshot()
            queue = queue_snapshot()

            state["runtime"] = runtime
            state["queue"] = queue

            if result.get("ok"):
                action = "DISCOVERY_COMPLETED"
                reason = (
                    "main.py tamamlandı; yeni araştırma "
                    "kuyruğu kontrol ediliyor."
                )
            else:
                action = "DISCOVERY_ERROR"
                reason = result.get(
                    "message",
                    (
                        "main.py başarısız oldu; "
                        f"exit={result.get('return_code')}"
                    ),
                )
        else:
            action = "WAITING"
            reason = gate_reason

    # 4. FEEDBACK
    if (
        brain_process is None
        and syntax_errors == 0
        and queue["active"] > 0
    ):
        feedback = learning_feedback()
        state["last_learning_feedback"] = feedback

        queue = queue_snapshot()
        state["queue"] = queue

        if feedback.get("ok"):
            action = "FEEDBACK_CHECKED"
            reason = (
                "Araştırma kuyruğu için learning feedback "
                "kontrol edildi."
            )

    # 5. BRAIN START
    if (
        brain_process is None
        and queue["active"] > 0
        and runtime["status"] != "WORKING"
        and syntax_errors == 0
    ):
        (
            brain_process,
            started,
            message,
        ) = start_brain(brain_process)

        if started:
            action = "BRAIN_STARTED"
            reason = message

            state["last_brain_started_at"] = now
            state["last_brain_pid"] = (
                brain_process.pid
            )

        else:
            action = "BRAIN_BLOCKED"
            reason = message

    # 6. EXPLICIT WAIT REASON
    if action in {"WAITING", "FEEDBACK_CHECKED"}:
        if runtime["status"] == "WORKING":
            action = "WAITING_RUNTIME"
            reason = (
                "Runtime WORKING; mevcut işlem "
                "bitmesi bekleniyor."
            )
        elif queue["active"] > 0:
            action = "WAITING_QUEUE"
            reason = (
                f"{queue['active']} aktif araştırma "
                "görevi bekliyor."
            )
        elif discovery_enabled:
            action = "WAITING_DISCOVERY"
            reason = (
                "Queue boş. Discovery zamanı gelince "
                "main.py otomatik çalışacak."
            )
        else:
            action = "IDLE"
            reason = (
                "Discovery kapalı ve aktif araştırma işi yok."
            )

    state.update(
        {
            "controller": "automation_controller_v5",
            "updated_at": utc_now(),
            "controller_pid": os.getpid(),
            "controller_status": "RUNNING",
            "action": action,
            "action_detail": reason,
            "brain_running": is_brain_running(
                brain_process
            ),
            "auto_heal_enabled": bool(auto_heal),
            "discovery_enabled": bool(
                discovery_enabled
            ),
            "discovery_cooldown_seconds": int(
                cooldown_seconds
            ),
            "force_discovery": bool(
                force_discovery
            ),
            "project_root": str(BASE_DIR),
            "resolved_paths": {
                "controller": str(
                    Path(__file__).resolve()
                ),
                "main": str(MARKET_HQ_MAIN),
                "brain_orchestrator": str(
                    BRAIN_ORCHESTRATOR
                ),
                "learning_feedback": str(
                    LEARNING_FEEDBACK
                ),
                "self_healing": str(SELF_HEALING),
                "database": str(DB_FILE),
            },
            "safe_gate": {
                "syntax_errors": syntax_errors,
                "runtime_error_records": (
                    runtime_error_records
                ),
                "brain_blocked_by_syntax": (
                    syntax_errors > 0
                ),
                "runtime_status": runtime["status"],
                "queue_active": queue["active"],
            },
            "last_cycle_finished_at": utc_now(),
        }
    )

    write_json(
        AUTOMATION_STATE_FILE,
        state,
    )

    return state, brain_process


def main():
    once = "--once" in sys.argv
    auto_heal = "--auto-heal" in sys.argv
    discovery_enabled = (
        "--no-discovery" not in sys.argv
    )
    force_discovery = (
        "--force-discovery" in sys.argv
    )

    interval = DEFAULT_INTERVAL
    cooldown = DEFAULT_DISCOVERY_COOLDOWN

    for arg in sys.argv:
        if arg.startswith("--interval="):
            try:
                interval = max(
                    10,
                    int(arg.split("=", 1)[1]),
                )
            except ValueError:
                interval = DEFAULT_INTERVAL

        elif arg.startswith("--discovery-cooldown="):
            try:
                cooldown = max(
                    60,
                    int(arg.split("=", 1)[1]),
                )
            except ValueError:
                cooldown = (
                    DEFAULT_DISCOVERY_COOLDOWN
                )

    if not acquire_lock():
        print(
            "Automation Controller zaten çalışıyor."
        )
        return 2

    state = read_json(
        AUTOMATION_STATE_FILE,
        {},
    )

    state.update(
        {
            "controller": "automation_controller_v5",
            "started_at": utc_now(),
            "controller_pid": os.getpid(),
            "controller_status": "RUNNING",
            "interval_seconds": interval,
            "auto_heal_enabled": auto_heal,
            "discovery_enabled": discovery_enabled,
            "discovery_cooldown_seconds": cooldown,
            "force_discovery": force_discovery,
            "project_root": str(BASE_DIR),
            "resolved_paths": {
                "controller": str(
                    Path(__file__).resolve()
                ),
                "main": str(MARKET_HQ_MAIN),
                "brain_orchestrator": str(
                    BRAIN_ORCHESTRATOR
                ),
                "learning_feedback": str(
                    LEARNING_FEEDBACK
                ),
                "self_healing": str(SELF_HEALING),
                "database": str(DB_FILE),
            },
        }
    )

    write_json(
        AUTOMATION_STATE_FILE,
        state,
    )

    brain_process = None

    print("=" * 78)
    print(
        "MARKETHQ AUTONOMOUS AUTOMATION CONTROLLER V5"
    )
    print(
        f"Project Root : {BASE_DIR}"
    )
    print(
        f"main.py      : {MARKET_HQ_MAIN} "
        f"[{'OK' if MARKET_HQ_MAIN.exists() else 'MISSING'}]"
    )
    print(
        f"Brain        : {BRAIN_ORCHESTRATOR} "
        f"[{'OK' if BRAIN_ORCHESTRATOR.exists() else 'MISSING'}]"
    )
    print(
        f"Database     : {DB_FILE} "
        f"[{'OK' if DB_FILE.exists() else 'MISSING'}]"
    )
    print(
        f"Interval={interval}s | "
        f"Auto-Heal={'ON' if auto_heal else 'OFF'} | "
        f"Discovery={'ON' if discovery_enabled else 'OFF'} | "
        f"Force={'ON' if force_discovery else 'OFF'} | "
        f"Cooldown={cooldown}s"
    )
    print(
        "Flow: Health -> Discovery -> Queue -> "
        "Brain -> Feedback -> Repeat"
    )
    print("=" * 78)

    try:
        while True:
            state, brain_process = run_cycle(
                state,
                brain_process,
                auto_heal=auto_heal,
                discovery_enabled=discovery_enabled,
                cooldown_seconds=cooldown,
                force_discovery=force_discovery,
            )

            summary = {
                "time": state.get("updated_at"),
                "action": state.get("action"),
                "reason": state.get(
                    "action_detail"
                ),
                "runtime": (
                    state.get("runtime") or {}
                ).get("status"),
                "queue_active": (
                    state.get("queue") or {}
                ).get("active", 0),
                "brain_running": state.get(
                    "brain_running"
                ),
                "syntax_errors": (
                    state.get("safe_gate") or {}
                ).get("syntax_errors", 0),
                "project_root": state.get(
                    "project_root"
                ),
                "main_exists": MARKET_HQ_MAIN.exists(),
            }

            print(
                json.dumps(
                    summary,
                    ensure_ascii=False,
                )
            )

            if once:
                break

            sleep_for = (
                10
                if is_brain_running(brain_process)
                else interval
            )
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        state["controller_status"] = "STOPPED"
        state["action"] = "STOPPED_BY_USER"
        state["action_detail"] = (
            "Kullanıcı tarafından durduruldu."
        )
        state["updated_at"] = utc_now()

        write_json(
            AUTOMATION_STATE_FILE,
            state,
        )

        print("Controller durduruldu.")
        return 0

    except Exception as exc:
        state["controller_status"] = "ERROR"
        state["action"] = "CONTROLLER_ERROR"
        state["action_detail"] = str(exc)
        state["updated_at"] = utc_now()

        write_json(
            AUTOMATION_STATE_FILE,
            state,
        )

        print(
            f"Controller hatası: {exc}"
        )
        return 1

    finally:
        release_lock()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
