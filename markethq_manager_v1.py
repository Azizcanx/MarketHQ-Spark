from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# MARKET HQ MANAGER V1.3
# =============================================================================
#
# Ana orkestrasyon / kontrol katmanı.
#
# Görev:
#   HEALTH
#      ↓
#   CORE
#      ↓
#   STRATEGY RESEARCH
#      ↓
#   BRAIN
#
# Bu sürüm özellikle subprocess gözlemlenebilirliğini güçlendirir:
#   - stdout canlı olarak gösterilir
#   - stderr canlı olarak gösterilir
#   - stage log dosyasına yazılır
#   - return code kaydedilir
#   - traceback kaybolmaz
#
# GÜVENLİK:
#   Research Only      : True
#   Execution Enabled  : False
#
# Gerçek emir / broker execution içermez.
# =============================================================================


# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

MAIN_SCRIPT = BASE_DIR / "main.py"

BRAIN_SCRIPT = (
    BASE_DIR
    / "agents"
    / "brain_orchestrator_v1.py"
)

RESEARCH_CANDIDATES = [
    BASE_DIR / "strategy_research_pipeline_v5.py",
    BASE_DIR / "strategy_research_pipeline.py",
]

STATE_FILE = BASE_DIR / "manager_state.json"
RUNTIME_STATE_FILE = BASE_DIR / "runtime_state.json"
LOCK_FILE = BASE_DIR / "markethq_manager.lock"

LOG_DIR = BASE_DIR / "manager_logs"


# =============================================================================
# SAFETY
# =============================================================================

RESEARCH_ONLY = True
EXECUTION_ENABLED = False


# =============================================================================
# TIMEOUTS
# =============================================================================

DEFAULT_TIMEOUT = 6 * 60 * 60

CORE_TIMEOUT = 30 * 60

RESEARCH_TIMEOUT = 6 * 60 * 60

BRAIN_TIMEOUT = 6 * 60 * 60


# =============================================================================
# STAGE DEFINITIONS
# =============================================================================

STAGES = [
    "HEALTH",
    "CORE",
    "STRATEGY_RESEARCH",
    "BRAIN",
]


# =============================================================================
# UTILS
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def safe_write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    temporary.replace(path)


def load_json(
    path: Path,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if default is None:
        default = {}

    if not path.exists():
        return default

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return default


def print_separator(char: str = "=", length: int = 80) -> None:
    print(char * length)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"

    minutes = int(seconds // 60)
    remaining = seconds % 60

    if minutes < 60:
        return f"{minutes}m {remaining:.1f}s"

    hours = int(minutes // 60)
    remaining_minutes = minutes % 60

    return (
        f"{hours}h "
        f"{remaining_minutes}m "
        f"{remaining:.1f}s"
    )


# =============================================================================
# MANAGER
# =============================================================================

class MarketHQManager:
    def __init__(
        self,
        research_only: bool = True,
    ) -> None:
        self.run_id = create_run_id()

        self.research_only = research_only
        self.execution_enabled = False

        self.started_at = utc_now()

        self.state: dict[str, Any] = {
            "manager_version": "1.3",
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": None,
            "status": "STARTING",
            "current_stage": None,
            "research_only": self.research_only,
            "execution_enabled": self.execution_enabled,
            "role": "orchestration_control_plane",
            "architecture": {
                "core": "main.py",
                "research": "strategy_research_pipeline_v5.py",
                "brain": "agents/brain_orchestrator_v1.py",
                "automation_controller": "automation_controller_v5.py",
            },
            "stages": {},
        }

        self.log_dir = LOG_DIR / self.run_id
        self.log_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # -------------------------------------------------------------------------
    # STATE
    # -------------------------------------------------------------------------

    def save_state(self) -> None:
        safe_write_json(
            STATE_FILE,
            self.state,
        )

        runtime_state = {
            "manager_version": "1.3",
            "run_id": self.run_id,
            "status": self.state.get("status"),
            "current_stage": self.state.get(
                "current_stage"
            ),
            "research_only": self.research_only,
            "execution_enabled": self.execution_enabled,
            "updated_at": utc_now(),
        }

        safe_write_json(
            RUNTIME_STATE_FILE,
            runtime_state,
        )

    # -------------------------------------------------------------------------
    # LOCK
    # -------------------------------------------------------------------------

    def acquire_lock(self) -> bool:
        if LOCK_FILE.exists():
            try:
                existing = LOCK_FILE.read_text(
                    encoding="utf-8"
                )

                print(
                    "⚠️ Manager lock dosyası mevcut."
                )

                if existing.strip():
                    print(
                        f"   Mevcut lock: "
                        f"{existing.strip()}"
                    )

                return False

            except Exception:
                return False

        try:
            LOCK_FILE.write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "created_at": utc_now(),
                        "pid": os.getpid(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            return True

        except Exception as exc:
            print(
                f"❌ Lock oluşturulamadı: {exc}"
            )
            return False

    def release_lock(self) -> None:
        try:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except Exception as exc:
            print(
                f"⚠️ Lock silinemedi: {exc}"
            )

    # -------------------------------------------------------------------------
    # FILE DISCOVERY
    # -------------------------------------------------------------------------

    def find_research_script(self) -> Path | None:
        for candidate in RESEARCH_CANDIDATES:
            if candidate.exists():
                return candidate

        return None

    # -------------------------------------------------------------------------
    # HEALTH
    # -------------------------------------------------------------------------

    def health_check(self) -> bool:
        self.state["current_stage"] = "HEALTH"
        self.state["status"] = "HEALTH_CHECK"
        self.save_state()

        print()
        print_separator()

        print("🛡️ MANAGER HEALTH CHECK")

        print_separator()

        checks: dict[str, bool] = {}

        checks["main"] = MAIN_SCRIPT.exists()

        checks["brain"] = BRAIN_SCRIPT.exists()

        research_script = self.find_research_script()
        checks["research"] = research_script is not None

        checks["python"] = sys.executable is not None

        checks["research_safety"] = (
            self.research_only is True
            and self.execution_enabled is False
        )

        for name, result in checks.items():
            if result:
                print(f"✅ {name}")
            else:
                print(f"❌ {name}")

        print()

        print(
            f"Research Only     : "
            f"{self.research_only}"
        )

        print(
            f"Execution Enabled : "
            f"{self.execution_enabled}"
        )

        healthy = all(checks.values())

        if healthy:
            print("✅ Health Check OK")
        else:
            print("❌ Health Check FAILED")

        self.state["health"] = {
            "checks": checks,
            "research_script": (
                str(research_script)
                if research_script
                else None
            ),
            "passed": healthy,
            "checked_at": utc_now(),
        }

        self.save_state()

        return healthy

    # -------------------------------------------------------------------------
    # COMMAND BUILDER
    # -------------------------------------------------------------------------

    def build_command(
        self,
        script: Path,
    ) -> list[str]:
        return [
            sys.executable,
            "-X",
            "utf8",
            "-u",
            str(script),
        ]

    # -------------------------------------------------------------------------
    # STAGE LOGGING
    # -------------------------------------------------------------------------

    def create_stage_log(
        self,
        stage: str,
    ) -> Path:
        filename = (
            f"{stage.lower()}_"
            f"{self.run_id}.log"
        )

        return self.log_dir / filename

    # -------------------------------------------------------------------------
    # PROCESS RUNNER
    # -------------------------------------------------------------------------

    def run_process(
        self,
        stage: str,
        script: Path,
        timeout: int,
    ) -> bool:
        print()
        print_separator()

        print(
            f"▶️ MANAGER STAGE: {stage}"
        )

        print_separator()

        print(
            f"Script : {script.name}"
        )

        print(
            f"Timeout: {timeout}s"
        )

        print(
            f"Python : {sys.executable}"
        )

        print(
            f"Working directory: {BASE_DIR}"
        )

        print_separator(
            "-",
            70,
        )

        command = self.build_command(
            script
        )

        stage_log = self.create_stage_log(
            stage
        )

        started = time.perf_counter()

        stage_state: dict[str, Any] = {
            "stage": stage,
            "script": str(script),
            "command": command,
            "started_at": utc_now(),
            "finished_at": None,
            "duration_seconds": None,
            "return_code": None,
            "status": "RUNNING",
            "log_file": str(stage_log),
        }

        self.state["stages"][stage] = stage_state
        self.save_state()

        process: subprocess.Popen[str] | None = None

        try:
            with stage_log.open(
                "w",
                encoding="utf-8",
                buffering=1,
            ) as log_handle:

                log_handle.write(
                    "=" * 80
                    + "\n"
                )

                log_handle.write(
                    f"MARKET HQ MANAGER V1.3\n"
                )

                log_handle.write(
                    f"Stage      : {stage}\n"
                )

                log_handle.write(
                    f"Run ID     : {self.run_id}\n"
                )

                log_handle.write(
                    f"Started    : {utc_now()}\n"
                )

                log_handle.write(
                    f"Python     : {sys.executable}\n"
                )

                log_handle.write(
                    f"Working dir: {BASE_DIR}\n"
                )

                log_handle.write(
                    "=" * 80
                    + "\n\n"
                )

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

                print(
                    f"PID    : {process.pid}"
                )

                print(
                    "Output : LIVE"
                )

                print()

                log_handle.write(
                    f"PID: {process.pid}\n\n"
                )

                # -------------------------------------------------------------
                # LIVE OUTPUT
                # -------------------------------------------------------------

                if process.stdout is not None:
                    for line in iter(
                        process.stdout.readline,
                        "",
                    ):
                        if not line:
                            break

                        text = line.rstrip(
                            "\r\n"
                        )

                        print(text)

                        log_handle.write(
                            text + "\n"
                        )

                        log_handle.flush()

                # -------------------------------------------------------------
                # PROCESS WAIT
                # -------------------------------------------------------------

                try:
                    return_code = process.wait(
                        timeout=timeout
                    )

                except subprocess.TimeoutExpired:
                    print()
                    print(
                        f"❌ {stage} TIMEOUT"
                    )

                    log_handle.write(
                        "\n"
                        + "=" * 80
                        + "\n"
                    )

                    log_handle.write(
                        "TIMEOUT\n"
                    )

                    log_handle.write(
                        f"Timeout: {timeout}s\n"
                    )

                    log_handle.write(
                        "=" * 80
                        + "\n"
                    )

                    try:
                        process.kill()
                    except Exception:
                        pass

                    try:
                        process.wait(
                            timeout=10
                        )
                    except Exception:
                        pass

                    duration = (
                        time.perf_counter()
                        - started
                    )

                    stage_state.update(
                        {
                            "finished_at": utc_now(),
                            "duration_seconds": duration,
                            "return_code": None,
                            "status": "TIMEOUT",
                        }
                    )

                    self.save_state()

                    return False

                duration = (
                    time.perf_counter()
                    - started
                )

                stage_state.update(
                    {
                        "finished_at": utc_now(),
                        "duration_seconds": duration,
                        "return_code": return_code,
                        "status": (
                            "SUCCESS"
                            if return_code == 0
                            else "ERROR"
                        ),
                    }
                )

                self.save_state()

                print()
                print_separator(
                    "-",
                    70,
                )

                print(
                    f"Return code: "
                    f"{return_code}"
                )

                print(
                    f"Duration   : "
                    f"{format_duration(duration)}"
                )

                print(
                    f"Log file   : "
                    f"{stage_log}"
                )

                if return_code == 0:
                    print(
                        "Status     : SUCCESS"
                    )
                    return True

                print(
                    "Status     : ERROR"
                )

                print()
                print(
                    "❌ Alt process hata ile "
                    "sonlandı."
                )

                print(
                    "📄 Tam çıktı log dosyasına "
                    "kaydedildi."
                )

                return False

        except Exception as exc:
            duration = (
                time.perf_counter()
                - started
            )

            error_text = (
                f"{type(exc).__name__}: "
                f"{exc}\n\n"
                f"{traceback.format_exc()}"
            )

            print()
            print(
                "❌ MANAGER PROCESS ERROR"
            )

            print(error_text)

            try:
                with stage_log.open(
                    "a",
                    encoding="utf-8",
                ) as log_handle:
                    log_handle.write(
                        "\n"
                        + "=" * 80
                        + "\n"
                    )

                    log_handle.write(
                        "MANAGER EXCEPTION\n"
                    )

                    log_handle.write(
                        error_text
                    )

                    log_handle.write(
                        "\n"
                        + "=" * 80
                        + "\n"
                    )
            except Exception:
                pass

            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()
                except Exception:
                    pass

            stage_state.update(
                {
                    "finished_at": utc_now(),
                    "duration_seconds": duration,
                    "return_code": None,
                    "status": "MANAGER_ERROR",
                    "error": error_text,
                }
            )

            self.save_state()

            return False

    # -------------------------------------------------------------------------
    # CORE
    # -------------------------------------------------------------------------

    def run_core(self) -> bool:
        if not MAIN_SCRIPT.exists():
            print(
                "❌ main.py bulunamadı."
            )
            return False

        if self.runtime_is_busy():
            print(
                "⚠️ runtime_state.json WORKING durumda; "
                "CORE yeni process olarak başlatılmayacak."
            )
            return False

        return self.run_process(
            stage="CORE",
            script=MAIN_SCRIPT,
            timeout=CORE_TIMEOUT,
        )

    # -------------------------------------------------------------------------
    # STRATEGY RESEARCH
    # -------------------------------------------------------------------------

    def run_strategy_research(self) -> bool:
        script = self.find_research_script()

        if script is None:
            print(
                "❌ Strategy Research script "
                "bulunamadı."
            )

            return False

        return self.run_process(
            stage="STRATEGY_RESEARCH",
            script=script,
            timeout=RESEARCH_TIMEOUT,
        )

    # -------------------------------------------------------------------------
    # BRAIN
    # -------------------------------------------------------------------------

    def run_brain(self) -> bool:
        if not BRAIN_SCRIPT.exists():
            print(
                "❌ Brain Orchestrator "
                "bulunamadı."
            )

            return False

        return self.run_process(
            stage="BRAIN",
            script=BRAIN_SCRIPT,
            timeout=BRAIN_TIMEOUT,
        )

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    def summary(
        self,
        final_status: str,
    ) -> None:
        self.state["status"] = final_status
        self.state["finished_at"] = utc_now()
        self.state["current_stage"] = None

        self.save_state()

        print()
        print_separator()

        print(
            "📊 MARKET HQ MANAGER SUMMARY"
        )

        print_separator()

        print(
            f"Run ID             : "
            f"{self.run_id}"
        )

        print(
            f"Status             : "
            f"{final_status}"
        )

        print(
            f"Research Only      : "
            f"{self.research_only}"
        )

        print(
            f"Execution Enabled  : "
            f"{self.execution_enabled}"
        )

        print()

        for stage in STAGES:
            stage_data = self.state[
                "stages"
            ].get(stage)

            if stage == "HEALTH":
                health = self.state.get(
                    "health"
                )

                if health:
                    status = (
                        "SUCCESS"
                        if health.get(
                            "passed"
                        )
                        else "ERROR"
                    )

                    print(
                        f"{stage:<24}: "
                        f"{status}"
                    )

                continue

            if not stage_data:
                continue

            print(
                f"{stage:<24}: "
                f"{stage_data.get('status')}"
            )

        print()

        print(
            f"State file         : "
            f"{STATE_FILE}"
        )

        print(
            f"Runtime state      : "
            f"{RUNTIME_STATE_FILE}"
        )

        print(
            f"Run logs           : "
            f"{self.log_dir}"
        )

    # -------------------------------------------------------------------------
    # RUNTIME CONFLICT GUARD
    # -------------------------------------------------------------------------

    def runtime_is_busy(self) -> bool:
        """Mevcut MarketHQ runtime'ı çalışıyorsa yeni CORE başlatmayı engeller."""
        runtime = load_json(RUNTIME_STATE_FILE, {})
        status = str(runtime.get("status", "IDLE")).upper()
        return status == "WORKING"

    # -------------------------------------------------------------------------
    # RUN
    # -------------------------------------------------------------------------

    def run(
        self,
        skip_core: bool = False,
        skip_research: bool = False,
        skip_brain: bool = False,
        skip_health: bool = False,
    ) -> bool:

        print()
        print_separator()

        print(
            "🏢 MARKET HQ MANAGER V1.3"
        )

        print_separator()

        print(
            f"Run ID            : "
            f"{self.run_id}"
        )

        print(
            f"Research Only     : "
            f"{self.research_only}"
        )

        print(
            f"Execution Enabled : "
            f"{self.execution_enabled}"
        )

        print()

        if self.research_only is not True:
            print(
                "❌ Research Only güvenlik "
                "kontrolü başarısız."
            )

            self.summary("ERROR")
            return False

        if self.execution_enabled is not False:
            print(
                "❌ Execution Enabled güvenlik "
                "kontrolü başarısız."
            )

            self.summary("ERROR")
            return False

        if not self.acquire_lock():
            self.state["status"] = "LOCKED"
            self.save_state()
            return False

        try:
            # ================================================================
            # HEALTH
            # ================================================================

            if not skip_health:
                if not self.health_check():
                    print()
                    print(
                        "🛑 Health Check başarısız."
                    )

                    self.summary("ERROR")
                    return False

            # ================================================================
            # CORE
            # ================================================================

            if not skip_core:
                self.state[
                    "current_stage"
                ] = "CORE"

                self.save_state()

                if not self.run_core():
                    print()
                    print(
                        "🛑 CORE kontrollü şekilde "
                        "durduruldu."
                    )

                    self.summary("ERROR")
                    return False

            # ================================================================
            # STRATEGY RESEARCH
            # ================================================================

            if not skip_research:
                self.state[
                    "current_stage"
                ] = "STRATEGY_RESEARCH"

                self.save_state()

                if not self.run_strategy_research():
                    print()
                    print(
                        "🛑 Strategy Research "
                        "kontrollü şekilde "
                        "durduruldu."
                    )

                    self.summary("ERROR")
                    return False

            # ================================================================
            # BRAIN
            # ================================================================

            if not skip_brain:
                self.state[
                    "current_stage"
                ] = "BRAIN"

                self.save_state()

                if not self.run_brain():
                    print()
                    print(
                        "🛑 Brain kontrollü şekilde "
                        "durduruldu."
                    )

                    self.summary("ERROR")
                    return False

            # ================================================================
            # COMPLETED
            # ================================================================

            self.summary("COMPLETED")

            return True

        except KeyboardInterrupt:
            print()
            print(
                "⚠️ Manager kullanıcı tarafından "
                "durduruldu."
            )

            self.summary("INTERRUPTED")

            return False

        except Exception:
            print()
            print(
                "❌ MANAGER UNHANDLED ERROR"
            )

            traceback.print_exc()

            self.summary("ERROR")

            return False

        finally:
            self.release_lock()


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ Manager V1.3 - "
            "Research orchestration layer"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Manager'ı tek sefer çalıştır."
        ),
    )

    parser.add_argument(
        "--skip-health",
        action="store_true",
        help=(
            "Health Check aşamasını atla."
        ),
    )

    parser.add_argument(
        "--skip-core",
        action="store_true",
        help=(
            "CORE / main.py aşamasını atla."
        ),
    )

    parser.add_argument(
        "--skip-research",
        action="store_true",
        help=(
            "Strategy Research aşamasını atla."
        ),
    )

    parser.add_argument(
        "--skip-brain",
        action="store_true",
        help=(
            "Brain aşamasını atla."
        ),
    )

    parser.add_argument(
        "--research-only",
        action="store_true",
        default=True,
        help=(
            "Research Only modunu zorunlu tut."
        ),
    )

    return parser.parse_args()


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    args = parse_args()

    manager = MarketHQManager(
        research_only=True
    )

    success = manager.run(
        skip_core=args.skip_core,
        skip_research=args.skip_research,
        skip_brain=args.skip_brain,
        skip_health=args.skip_health,
    )

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

