import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DB_FILE = BASE_DIR / "market_hq.db"

STATE_FILE = BASE_DIR / "runtime_state.json"

AUTOMATION_STATE_FILE = (
    BASE_DIR / "automation_state.json"
)

SELF_HEALING = (
    BASE_DIR / "self_healing_engine_v1.py"
)

BRAIN_ORCHESTRATOR = (
    BASE_DIR
    / "agents"
    / "brain_orchestrator_v1.py"
)

LOCK_FILE = (
    BASE_DIR / "automation_controller.lock"
)

DEFAULT_INTERVAL = 60


# =========================================================
# TIME
# =========================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


# =========================================================
# JSON HELPERS
# =========================================================

def read_json(path, fallback):
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            value,
            type(fallback)
        ):
            return value

        return fallback

    except Exception:
        return fallback


def write_json(path, value):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str
        ),
        encoding="utf-8"
    )

    tmp.replace(path)


# =========================================================
# LOCK
# =========================================================

def acquire_lock():

    try:

        fd = os.open(
            str(LOCK_FILE),
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as handle:

            handle.write(
                str(os.getpid())
            )

        return True

    except FileExistsError:

        existing = (
            LOCK_FILE
            .read_text(
                encoding="utf-8",
                errors="ignore"
            )
            .strip()
        )

        if existing:
            return False

        return _replace_stale_lock()

    except OSError:

        return False


def _replace_stale_lock():

    try:

        LOCK_FILE.unlink(
            missing_ok=True
        )

        fd = os.open(
            str(LOCK_FILE),
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as handle:

            handle.write(
                str(os.getpid())
            )

        return True

    except OSError:

        return False


def release_lock():

    try:

        LOCK_FILE.unlink(
            missing_ok=True
        )

    except OSError:

        pass


# =========================================================
# RUNTIME STATE
# =========================================================

def runtime_snapshot():

    state = read_json(
        STATE_FILE,
        {}
    )

    if not isinstance(
        state,
        dict
    ):
        state = {}

    system = state.get(
        "system"
    )

    if not isinstance(
        system,
        dict
    ):
        system = {}

    return {
        "status": str(
            system.get(
                "status",
                "IDLE"
            )
        ).upper(),

        "message": str(
            system.get(
                "message",
                ""
            )
        ),

        "current_run_id": (
            system.get(
                "current_run_id"
            )
        ),
    }


# =========================================================
# BRAIN QUEUE
# =========================================================

def queue_snapshot():

    if not DB_FILE.exists():

        return {
            "exists": False,
            "active": 0
        }

    conn = None

    try:

        conn = sqlite3.connect(
            DB_FILE,
            timeout=8
        )

        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_queue
            WHERE UPPER(
                COALESCE(status, '')
            )
            NOT IN (
                'COMPLETED',
                'CANCELLED',
                'DONE',
                'CLOSED'
            )
            """
        ).fetchone()

        return {
            "exists": True,
            "active": int(
                row[0]
                if row
                else 0
            )
        }

    except sqlite3.Error:

        return {
            "exists": True,
            "active": 0,
            "error": True
        }

    finally:

        if conn is not None:

            conn.close()


# =========================================================
# SELF HEALING / HEALTH
# =========================================================

def run_health(
    auto_heal=False
):

    if not SELF_HEALING.exists():

        return {
            "ok": False,
            "message": (
                "Self-Healing Engine "
                "bulunamadı."
            )
        }

    args = [
        sys.executable,
        "-u",
        str(SELF_HEALING)
    ]

    if auto_heal:

        args.append(
            "--auto"
        )

    try:

        result = subprocess.run(
            args,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180
        )

        report = read_json(
            BASE_DIR
            / "self_healing"
            / "last_report.json",
            {}
        )

        return {
            "ok": (
                result.returncode == 0
            ),

            "return_code": (
                result.returncode
            ),

            "report": report,

            "stdout_tail": (
                result.stdout[-1200:]
            ),

            "stderr_tail": (
                result.stderr[-1200:]
            ),
        }

    except Exception as exc:

        return {
            "ok": False,
            "message": str(exc)
        }


# =========================================================
# BRAIN ORCHESTRATOR
# =========================================================

def start_brain(
    brain_process
):

    if (
        brain_process is not None
        and brain_process.poll() is None
    ):

        return (
            brain_process,
            False,
            "Brain Orchestrator zaten çalışıyor."
        )

    if not BRAIN_ORCHESTRATOR.exists():

        return (
            None,
            False,
            "Brain Orchestrator bulunamadı."
        )

    try:

        kwargs = {
            "cwd": str(BASE_DIR)
        }

        if os.name == "nt":

            kwargs[
                "creationflags"
            ] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0
            )

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(BRAIN_ORCHESTRATOR)
            ],

            stdout=subprocess.DEVNULL,

            stderr=subprocess.DEVNULL,

            **kwargs
        )

        return (
            process,
            True,
            (
                "Brain Loop başlatıldı. "
                f"PID={process.pid}"
            )
        )

    except Exception as exc:

        return (
            None,
            False,
            (
                "Brain Loop "
                f"başlatılamadı: {exc}"
            )
        )


# =========================================================
# AUTOMATION CYCLE
# =========================================================

def automation_cycle(
    state,
    brain_process,
    auto_heal
):

    now = utc_now()

    runtime = runtime_snapshot()

    queue = queue_snapshot()

    action = "IDLE"

    action_detail = (
        "Yeni işlem gerekmiyor."
    )

    # -----------------------------------------------------
    # HEALTH CHECK
    # -----------------------------------------------------

    health = run_health(
        auto_heal=False
    )

    state[
        "last_health"
    ] = health

    report = (
        health.get("report")
        or {}
    )

    syntax_errors = int(
        report.get(
            "syntax_errors",
            0
        )
        or 0
    )

    runtime_errors = int(
        report.get(
            "runtime_error_records",
            0
        )
        or 0
    )

    # -----------------------------------------------------
    # AUTO HEAL
    # -----------------------------------------------------

    if (
        auto_heal
        and syntax_errors > 0
    ):

        heal = run_health(
            auto_heal=True
        )

        state[
            "last_auto_heal"
        ] = heal

        action = "AUTO_HEAL"

        action_detail = (
            "Syntax hatası için "
            "kontrollü onarım denendi."
        )

        health = heal

        report = (
            heal.get("report")
            or report
        )

        syntax_errors = int(
            report.get(
                "syntax_errors",
                0
            )
            or 0
        )

    # -----------------------------------------------------
    # BRAIN PROCESS CHECK
    # -----------------------------------------------------

    if (
        brain_process is not None
        and brain_process.poll()
        is not None
    ):

        state[
            "last_brain_exit_code"
        ] = brain_process.returncode

        state[
            "last_brain_finished_at"
        ] = now

        brain_process = None

        action = "BRAIN_COMPLETED"

        action_detail = (
            "Brain Orchestrator tamamlandı."
        )

        runtime = runtime_snapshot()

        queue = queue_snapshot()

    # -----------------------------------------------------
    # BRAIN START GATE
    # -----------------------------------------------------

    can_start_brain = (

        brain_process is None

        and queue.get(
            "active",
            0
        ) > 0

        and runtime.get(
            "status"
        ) != "WORKING"

        and syntax_errors == 0
    )

    if can_start_brain:

        (
            brain_process,
            started,
            message
        ) = start_brain(
            brain_process
        )

        if started:

            action = "BRAIN_STARTED"

            action_detail = message

            state[
                "last_brain_started_at"
            ] = now

            state[
                "last_brain_pid"
            ] = brain_process.pid

        else:

            action = (
                "BRAIN_START_BLOCKED"
            )

            action_detail = message

    # -----------------------------------------------------
    # STATE UPDATE
    # -----------------------------------------------------

    state.update(
        {
            "controller": (
                "automation_controller_v2"
            ),

            "updated_at": now,

            "controller_pid": (
                os.getpid()
            ),

            "controller_status": (
                "RUNNING"
            ),

            "interval_seconds": (
                state.get(
                    "interval_seconds",
                    DEFAULT_INTERVAL
                )
            ),

            "runtime": runtime,

            "queue": queue,

            "brain_running": (
                brain_process is not None
                and brain_process.poll()
                is None
            ),

            "action": action,

            "action_detail": (
                action_detail
            ),

            "safe_gate": {
                "syntax_errors": (
                    syntax_errors
                ),

                "runtime_errors_detected": (
                    runtime_errors
                ),

                "auto_heal_enabled": (
                    bool(auto_heal)
                ),

                "brain_requires_zero_syntax_errors": (
                    True
                ),
            },
        }
    )

    write_json(
        AUTOMATION_STATE_FILE,
        state
    )

    return (
        state,
        brain_process
    )


# =========================================================
# MAIN
# =========================================================

def main():

    once = (
        "--once"
        in sys.argv
    )

    auto_heal = (
        "--auto-heal"
        in sys.argv
    )

    interval = DEFAULT_INTERVAL

    # -----------------------------------------------------
    # INTERVAL
    # -----------------------------------------------------

    for arg in sys.argv:

        if arg.startswith(
            "--interval="
        ):

            try:

                interval = max(
                    10,
                    int(
                        arg.split(
                            "=",
                            1
                        )[1]
                    )
                )

            except ValueError:

                interval = (
                    DEFAULT_INTERVAL
                )

    # -----------------------------------------------------
    # LOCK
    # -----------------------------------------------------

    if not acquire_lock():

        print(
            "Automation Controller "
            "zaten çalışıyor."
        )

        return 2

    # -----------------------------------------------------
    # INITIAL STATE
    # -----------------------------------------------------

    state = {

        "controller": (
            "automation_controller_v2"
        ),

        "started_at": utc_now(),

        "controller_pid": (
            os.getpid()
        ),

        "controller_status": (
            "RUNNING"
        ),

        "interval_seconds": (
            interval
        ),

        "auto_heal_enabled": (
            auto_heal
        ),
    }

    brain_process = None

    # -----------------------------------------------------
    # CONTROLLER LOOP
    # -----------------------------------------------------

    try:

        print(
            "=" * 72
        )

        print(
            "MARKETHQ AUTOMATION "
            "CONTROLLER V2"
        )

        print(
            f"Interval: {interval}s | "
            f"Auto-Heal: "
            f"{'ON' if auto_heal else 'OFF'}"
        )

        print(
            "=" * 72
        )

        while True:

            (
                state,
                brain_process
            ) = automation_cycle(
                state,
                brain_process,
                auto_heal
            )

            print(
                json.dumps(
                    {
                        "time": (
                            state.get(
                                "updated_at"
                            )
                        ),

                        "action": (
                            state.get(
                                "action"
                            )
                        ),

                        "detail": (
                            state.get(
                                "action_detail"
                            )
                        ),

                        "queue": (
                            state
                            .get(
                                "queue",
                                {}
                            )
                            .get(
                                "active",
                                0
                            )
                        ),

                        "brain_running": (
                            state.get(
                                "brain_running"
                            )
                        ),

                        "syntax_errors": (
                            state
                            .get(
                                "safe_gate",
                                {}
                            )
                            .get(
                                "syntax_errors",
                                0
                            )
                        ),
                    },

                    ensure_ascii=False
                )
            )

            if once:

                break

            time.sleep(
                interval
            )

    except KeyboardInterrupt:

        state[
            "controller_status"
        ] = "STOPPED"

        state[
            "updated_at"
        ] = utc_now()

        state[
            "action"
        ] = "STOPPED_BY_USER"

        write_json(
            AUTOMATION_STATE_FILE,
            state
        )

        print(
            "Controller durduruldu."
        )

        return 0

    except Exception as exc:

        state[
            "controller_status"
        ] = "ERROR"

        state[
            "updated_at"
        ] = utc_now()

        state[
            "action"
        ] = "CONTROLLER_ERROR"

        state[
            "action_detail"
        ] = str(exc)

        write_json(
            AUTOMATION_STATE_FILE,
            state
        )

        print(
            f"Controller hatası: {exc}"
        )

        return 1

    finally:

        release_lock()

    return 0


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
