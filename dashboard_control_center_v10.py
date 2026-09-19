import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "runtime_state.json"
STRATEGY_RESULT_FILE = BASE_DIR / "strategy_lab_result.json"
INTELLIGENCE_DB = BASE_DIR / "market_hq.db"
MAIN_FILE = BASE_DIR / "main.py"
STRATEGY_LAB_RUNNER = BASE_DIR / "strategy_lab_runner.py"
BRAIN_ORCHESTRATOR = BASE_DIR / "agents" / "brain_orchestrator_v1.py"
SELF_HEALING_ENGINE = BASE_DIR / "self_healing_engine_v1.py"
SELF_HEALING_REPORT = BASE_DIR / "self_healing" / "last_report.json"
AUTOMATION_CONTROLLER = BASE_DIR / "automation_controller_v2.py"
AUTOMATION_STATE_FILE = BASE_DIR / "automation_state.json"
LEARNING_FEEDBACK_STATE = BASE_DIR / "learning_feedback_state.json"

HOST = "127.0.0.1"
PORT = 8000

load_dotenv(BASE_DIR / ".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv(
    "MARKETHQ_AI_MODEL",
    os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
).strip()
OPENAI_RESPONSES_URL = os.getenv(
    "OPENAI_RESPONSES_URL",
    "https://api.openai.com/v1/responses",
).strip()


# =========================================================
# AGENT META
# =========================================================

AGENT_META = {
    "hq": {"icon": "🏢", "room": "HQ CONTROL"},
    "news": {"icon": "📰", "room": "NEWS ROOM"},
    "turkey_news": {"icon": "🇹🇷", "room": "TURKEY NEWS"},
    "turkey_market": {"icon": "📊", "room": "TURKEY DATA"},
    "company_updates": {"icon": "🏭", "room": "COMPANY DESK"},
    "market_data": {"icon": "📈", "room": "MARKET DATA"},
    "analyst": {"icon": "🧠", "room": "AI ANALYST"},
    "performance": {"icon": "📊", "room": "PERFORMANCE"},
    "strategy_lab": {"icon": "🧪", "room": "STRATEGY LAB"},
    "fin_sys": {"icon": "📚", "room": "FIN[SYS]"},
    "youtube": {"icon": "🎥", "room": "YOUTUBE"},
}

STATUS_ORDER = {"WORKING": 0, "ERROR": 1, "COMPLETED": 2, "IDLE": 3}


# =========================================================
# SAFE FILE / DB HELPERS
# =========================================================

def read_json_file(path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return fallback


def read_state():
    fallback = {
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
    state = read_json_file(STATE_FILE, fallback)
    if not isinstance(state, dict):
        return fallback
    state.setdefault("system", {})
    state.setdefault("agents", {})
    state.setdefault("events", [])
    state.setdefault("tasks", [])
    return state


def read_strategy_result():
    fallback = {"exists": False}
    result = read_json_file(STRATEGY_RESULT_FILE, fallback)
    if not result:
        return fallback
    if isinstance(result, dict):
        result["exists"] = True
        return result
    return fallback


def read_self_healing_report():
    fallback = {"status": "UNKNOWN", "scanned_at": None, "syntax_errors": 0, "runtime_error_records": 0, "python_files_scanned": 0, "repair": None}
    report = read_json_file(SELF_HEALING_REPORT, fallback)
    if not isinstance(report, dict):
        return fallback
    return report


def read_learning_feedback_state():
    fallback = {
        "status": "UNKNOWN",
        "updated_at": None,
        "queue_created": 0,
        "queue_existing": 0,
        "reviews_seen": 0,
        "actions": {},
        "last_actions": [],
    }
    value = read_json_file(LEARNING_FEEDBACK_STATE, fallback)
    return value if isinstance(value, dict) else fallback


def read_automation_state():
    fallback = {
        "controller_status": "STOPPED",
        "auto_heal_enabled": False,
        "brain_running": False,
        "queue": {"active": 0},
        "safe_gate": {"syntax_errors": 0, "runtime_errors_detected": 0},
    }
    value = read_json_file(AUTOMATION_STATE_FILE, fallback)
    return value if isinstance(value, dict) else fallback


def automation_pid_running():
    state = read_automation_state()
    pid = state.get("controller_pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ValueError, OSError, ProcessLookupError, PermissionError):
        return False


def connect_db():
    if not INTELLIGENCE_DB.exists():
        return None
    conn = sqlite3.connect(INTELLIGENCE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, name):
    if conn is None:
        return False
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def table_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return []
    try:
        return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table_name}")')]
    except sqlite3.Error:
        return []


def table_count(conn, table_name):
    if not table_exists(conn, table_name):
        return 0
    try:
        row = conn.execute(f'SELECT COUNT(*) AS n FROM "{table_name}"').fetchone()
        return int(row["n"] or 0)
    except sqlite3.Error:
        return 0


def recent_rows(conn, table_name, wanted_columns, limit=8):
    if not table_exists(conn, table_name):
        return []
    existing = table_columns(conn, table_name)
    selected = [column for column in wanted_columns if column in existing]
    if not selected:
        return []
    order_col = next(
        (candidate for candidate in ("updated_at", "created_at", "finished_at", "id") if candidate in existing),
        None,
    )
    order_sql = f' ORDER BY "{order_col}" DESC' if order_col else ""
    try:
        rows = conn.execute(
            f'SELECT {", ".join(f"\"{column}\"" for column in selected)} FROM "{table_name}"{order_sql} LIMIT ?',
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def first_value(row, *names, default=""):
    if not isinstance(row, dict):
        return default
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


# =========================================================
# INTELLIGENCE SNAPSHOT
# =========================================================

def read_intelligence():
    payload = {
        "status": "ok",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "knowledge": {
            "items": 0,
            "sources": 0,
            "recent_items": [],
            "recent_sources": [],
        },
        "learning": {
            "experiments": 0,
            "experiment_results": 0,
            "learned_rules": 0,
            "total_records": 0,
            "recent_experiments": [],
            "recent_rules": [],
        },
        "specifications": {
            "registry": 0,
            "canonical_methods": 0,
            "spec_ready": 0,
            "partial": 0,
            "reference_only": 0,
        },
        "research": {
            "strategy_symbols": 0,
            "strategy_status": "NONE",
        },
        "brain": {
            "nodes": 0,
            "edges": 0,
            "observations": 0,
            "claims": 0,
            "learning_events": 0,
            "evidence_reviews": 0,
            "research_queue_active": 0,
            "research_episodes": 0,
            "research_updates": 0,
            "contradictions_open": 0,
            "orphan_nodes": 0,
            "validated_candidates": 0,
            "canonical_research_items": 0,
            "recent_updates": [],
            "recent_reviews": [],
            "recent_queue": [],
        },
        "database": {"available": INTELLIGENCE_DB.exists()},
        "self_healing": read_self_healing_report(),
        "automation": read_automation_state(),
        "learning_feedback": read_learning_feedback_state(),
    }

    conn = None
    try:
        conn = connect_db()
        if conn is None:
            payload["status"] = "degraded"
            payload["database"]["available"] = False
            return payload

        payload["knowledge"]["items"] = table_count(conn, "knowledge_items")
        payload["knowledge"]["sources"] = table_count(conn, "knowledge_sources")
        payload["learning"]["experiments"] = table_count(conn, "learning_experiments")
        payload["learning"]["experiment_results"] = table_count(conn, "experiment_results")
        payload["learning"]["learned_rules"] = table_count(conn, "learned_rules")
        payload["learning"]["total_records"] = (
            payload["learning"]["experiments"]
            + payload["learning"]["learned_rules"]
        )

        payload["knowledge"]["recent_items"] = recent_rows(
            conn,
            "knowledge_items",
            [
                "title",
                "summary",
                "method_name",
                "confidence",
                "item_type",
                "created_at",
                "updated_at",
            ],
            8,
        )
        payload["knowledge"]["recent_sources"] = recent_rows(
            conn,
            "knowledge_sources",
            ["title", "name", "url", "source_type", "status", "created_at", "updated_at"],
            6,
        )
        payload["learning"]["recent_rules"] = recent_rows(
            conn,
            "learned_rules",
            [
                "method_name",
                "symbol",
                "timeframe",
                "condition_name",
                "sample_size",
                "success_rate",
                "average_return",
                "confidence",
                "observation",
                "created_at",
                "updated_at",
            ],
            8,
        )
        payload["learning"]["recent_experiments"] = recent_rows(
            conn,
            "learning_experiments",
            [
                "method_name",
                "symbol",
                "market",
                "timeframe",
                "signal_direction",
                "status",
                "created_at",
                "updated_at",
            ],
            8,
        )

        payload["specifications"]["registry"] = table_count(conn, "method_registry")
        if table_exists(conn, "method_specification_consolidated"):
            payload["specifications"]["canonical_methods"] = table_count(
                conn, "method_specification_consolidated"
            )
            for status, key in (
                ("SPEC_READY", "spec_ready"),
                ("PARTIAL", "partial"),
                ("REFERENCE_ONLY", "reference_only"),
            ):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM method_specification_consolidated WHERE gate_status=?",
                    (status,),
                ).fetchone()
                payload["specifications"][key] = int(row["n"] or 0)
        elif table_exists(conn, "method_specifications"):
            payload["specifications"]["canonical_methods"] = table_count(
                conn, "method_specifications"
            )

        # Brain snapshot
        brain = payload["brain"]
        brain["nodes"] = table_count(conn, "brain_nodes")
        brain["edges"] = table_count(conn, "brain_edges")
        brain["observations"] = table_count(conn, "brain_observations")
        brain["claims"] = table_count(conn, "brain_claims")
        brain["learning_events"] = table_count(conn, "brain_learning_events")
        brain["evidence_reviews"] = table_count(conn, "brain_research_evidence_reviews")
        brain["research_episodes"] = table_count(conn, "brain_episodes")
        brain["research_updates"] = table_count(conn, "brain_research_brain_updates")

        if table_exists(conn, "brain_research_queue"):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM brain_research_queue WHERE status IN ('queued','working')"
            ).fetchone()
            brain["research_queue_active"] = int(row["n"] or 0)

        if table_exists(conn, "brain_contradictions"):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM brain_contradictions WHERE status IN ('open','OPEN')"
            ).fetchone()
            brain["contradictions_open"] = int(row["n"] or 0)

        if table_exists(conn, "brain_nodes") and table_exists(conn, "brain_edges"):
            evidence_clause = ""
            if table_exists(conn, "brain_node_evidence"):
                evidence_clause = "AND NOT EXISTS (SELECT 1 FROM brain_node_evidence ne WHERE ne.node_id=n.id)"

            row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM brain_nodes n
                WHERE NOT EXISTS (
                    SELECT 1 FROM brain_edges e
                    WHERE e.source_node_id=n.id OR e.target_node_id=n.id
                )
                {evidence_clause}
                """
            ).fetchone()
            brain["orphan_nodes"] = int(row["n"] or 0)

        if table_exists(conn, "brain_nodes"):
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM brain_nodes
                WHERE node_type='learned_rule'
                  AND status='validated_candidate'
                """
            ).fetchone()
            brain["validated_candidates"] = int(row["n"] or 0)

        if table_exists(conn, "knowledge_items"):
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM knowledge_items
                WHERE item_type='research_result'
                  AND LOWER(COALESCE(metadata_json,'')) LIKE '%"lifecycle_state":"canonical"%'
                """
            ).fetchone()
            # JSON text count is only a display metric; lifecycle repair remains authoritative in its own engine.
            brain["canonical_research_items"] = int(row["n"] or 0)

        brain["recent_updates"] = recent_rows(
            conn,
            "brain_research_brain_updates",
            [
                "review_id",
                "knowledge_item_id",
                "observation_id",
                "verdict",
                "action",
                "research_priority",
                "queue_task_id",
                "created_at",
            ],
            8,
        )
        brain["recent_reviews"] = recent_rows(
            conn,
            "brain_research_evidence_reviews",
            [
                "id",
                "knowledge_item_id",
                "observation_id",
                "verdict",
                "score",
                "contradiction_flag",
                "review_method",
                "created_at",
            ],
            8,
        )
        brain["recent_queue"] = recent_rows(
            conn,
            "brain_research_queue",
            [
                "id",
                "question",
                "priority",
                "status",
                "created_at",
                "updated_at",
                "metadata_json",
            ],
            8,
        )
        brain["orchestrator_running"] = brain_orchestrator_running()
        payload["self_healing"]["running"] = self_healing_running()
        payload["automation"]["running"] = automation_pid_running()

        result = read_strategy_result()
        payload["research"]["strategy_status"] = str(
            result.get("status", "NONE") if result.get("exists") else "NONE"
        )
        symbols = result.get("symbols", []) if isinstance(result, dict) else []
        if isinstance(symbols, list):
            payload["research"]["strategy_symbols"] = len(symbols)

        return payload
    except Exception as exc:
        return {"status": "error", "error": str(exc), **payload}
    finally:
        if conn is not None:
            conn.close()


# =========================================================
# QUERY CONTEXT / AI
# =========================================================

def _safe_db_count(conn, table_name):
    return table_count(conn, table_name)


def _collect_query_context(question, selected_agent=None):
    state = read_state()
    intelligence = read_intelligence()
    strategy = read_strategy_result()
    agents = state.get("agents") or {}

    snapshot = []
    for name, info in agents.items():
        if not isinstance(info, dict):
            continue
        snapshot.append(
            {
                "agent": name,
                "room": AGENT_META.get(name, {}).get("room", name.upper()),
                "status": info.get("status", "IDLE"),
                "message": info.get("message", info.get("text", info.get("detail", ""))),
                "task": info.get("task", ""),
                "updated_at": info.get("updated_at", info.get("timestamp", "")),
            }
        )

    context = {
        "question": question,
        "focus_agent": selected_agent or "ALL",
        "system": state.get("system", {}),
        "agents": snapshot,
        "tasks": state.get("tasks", [])[-15:] if isinstance(state.get("tasks"), list) else [],
        "recent_events": state.get("events", [])[-15:] if isinstance(state.get("events"), list) else [],
        "intelligence": intelligence,
        "strategy_lab": strategy,
    }

    conn = None
    try:
        conn = connect_db()
        if conn is not None:
            context["database"] = {
                "counts": {
                    "knowledge_items": _safe_db_count(conn, "knowledge_items"),
                    "knowledge_sources": _safe_db_count(conn, "knowledge_sources"),
                    "learning_experiments": _safe_db_count(conn, "learning_experiments"),
                    "experiment_results": _safe_db_count(conn, "experiment_results"),
                    "learned_rules": _safe_db_count(conn, "learned_rules"),
                },
                "recent_knowledge": recent_rows(
                    conn,
                    "knowledge_items",
                    ["title", "summary", "method_name", "confidence", "item_type"],
                    8,
                ),
                "recent_learned_rules": recent_rows(
                    conn,
                    "learned_rules",
                    [
                        "method_name",
                        "symbol",
                        "timeframe",
                        "condition_name",
                        "sample_size",
                        "success_rate",
                        "average_return",
                        "confidence",
                        "observation",
                    ],
                    8,
                ),
                "recent_experiments": recent_rows(
                    conn,
                    "learning_experiments",
                    ["method_name", "symbol", "market", "timeframe", "signal_direction", "status"],
                    8,
                ),
            }
        else:
            context["database_error"] = "market_hq.db bulunamadı."
    except Exception as exc:
        context["database_error"] = str(exc)
    finally:
        if conn is not None:
            conn.close()

    return context


def _extract_output_text(data):
    answer = data.get("output_text")
    if answer:
        return str(answer).strip()
    chunks = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks).strip()


def ask_hq(question, selected_agent=None):
    question = str(question or "").strip()
    selected_agent = str(selected_agent or "").strip() or None
    if not question:
        return False, "Soru boş bırakılamaz.", None
    if len(question) > 3000:
        return False, "Soru 3000 karakteri geçemez.", None
    if not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY bulunamadı. .env dosyanı kontrol et.", None

    context = _collect_query_context(question, selected_agent)
    system_prompt = (
        "Sen MarketHQ'nun yönetici seviyesinde Research Intelligence Lead'isin. "
        "Yalnızca sana verilen MarketHQ bağlamını kullan. "
        "Veri, ajan durumu, bilgi kaydı, deney sonucu ve öğrenilmiş kuralı birbirinden ayır. "
        "Kanıt olmayan şeyi olmuş gibi anlatma. Eksik veri varsa açıkça söyle. "
        "Kullanıcıya teknik kayıt dökmek yerine yönetsel bir sentez sun. "
        "Gerektiğinde 'Durum', 'Bulgu', 'Risk/Açık', 'Önerilen sonraki adım' başlıklarını kullan. "
        "Yanıt Türkçe olsun. Araştırma/karar destek sistemi olduğunu unutma; canlı al-sat talimatı veya garanti verme."
    )

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, indent=2, default=str),
            },
        ],
    }

    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code >= 400:
            message = data.get("error", {}).get("message", response.text)
            return False, f"AI servisi hata verdi: {message}", None

        answer = _extract_output_text(data)
        if not answer:
            return False, "AI yanıt üretemedi.", None
        return True, answer, OPENAI_MODEL
    except requests.RequestException as exc:
        return False, f"AI bağlantı hatası: {exc}", None
    except Exception as exc:
        return False, f"Sorgu hatası: {exc}", None


# =========================================================
# PROCESS CONTROLS
# =========================================================

def start_process(script_file, process_name):
    if not script_file.exists():
        return False, f"{process_name} dosyası bulunamadı."
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, str(script_file)],
            cwd=str(BASE_DIR),
            creationflags=creationflags,
        )
        return True, f"{process_name} başlatıldı."
    except Exception as exc:
        return False, f"{process_name} başlatılamadı: {exc}"


def run_market_hq():
    state = read_state()
    if str(state.get("system", {}).get("status", "IDLE")).upper() == "WORKING":
        return False, "MarketHQ zaten çalışıyor."
    return start_process(MAIN_FILE, "MarketHQ")


def run_strategy_lab():
    return start_process(STRATEGY_LAB_RUNNER, "Strategy Lab")


# =========================================================
# SELF-HEALING PROCESS
# =========================================================

SELF_HEALING_PROCESS = None

def self_healing_running():
    global SELF_HEALING_PROCESS
    if SELF_HEALING_PROCESS is None:
        return False
    try:
        running = SELF_HEALING_PROCESS.poll() is None
    except Exception:
        running = False
    if not running:
        SELF_HEALING_PROCESS = None
    return running


def run_self_healing(auto_apply=False):
    global SELF_HEALING_PROCESS
    if self_healing_running():
        return False, "Self-Healing taraması zaten çalışıyor."
    if not SELF_HEALING_ENGINE.exists():
        return False, f"Self-Healing Engine bulunamadı: {SELF_HEALING_ENGINE}"
    try:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        args = [sys.executable, "-u", str(SELF_HEALING_ENGINE)]
        if auto_apply:
            args.append("--auto")
        SELF_HEALING_PROCESS = subprocess.Popen(
            args, cwd=str(BASE_DIR), creationflags=creationflags
        )
        return True, "Self-Healing Engine başlatıldı." if not auto_apply else "Self-Healing otomatik onarım başlatıldı."
    except Exception as exc:
        SELF_HEALING_PROCESS = None
        return False, f"Self-Healing başlatılamadı: {exc}"


# =========================================================
# AUTOMATION CONTROLLER PROCESS
# =========================================================

AUTOMATION_PROCESS = None

def automation_running():
    global AUTOMATION_PROCESS
    if AUTOMATION_PROCESS is not None:
        try:
            if AUTOMATION_PROCESS.poll() is None:
                return True
        except Exception:
            pass
        AUTOMATION_PROCESS = None
    return automation_pid_running()


def run_automation(enable_auto_heal=False, interval=60):
    global AUTOMATION_PROCESS
    if automation_running():
        return False, "Automation Controller zaten çalışıyor."
    if not AUTOMATION_CONTROLLER.exists():
        return False, f"Automation Controller bulunamadı: {AUTOMATION_CONTROLLER}"
    try:
        args = [sys.executable, "-u", str(AUTOMATION_CONTROLLER), f"--interval={max(10, int(interval))}"]
        if enable_auto_heal:
            args.append("--auto-heal")
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        AUTOMATION_PROCESS = subprocess.Popen(args, cwd=str(BASE_DIR), creationflags=creationflags)
        return True, "Otomasyon başlatıldı."
    except Exception as exc:
        AUTOMATION_PROCESS = None
        return False, f"Otomasyon başlatılamadı: {exc}"


def stop_automation():
    global AUTOMATION_PROCESS
    if AUTOMATION_PROCESS is not None and AUTOMATION_PROCESS.poll() is None:
        try:
            AUTOMATION_PROCESS.terminate()
            AUTOMATION_PROCESS.wait(timeout=5)
        except Exception:
            try:
                AUTOMATION_PROCESS.kill()
            except Exception:
                pass
        AUTOMATION_PROCESS = None
        return True, "Otomasyon durduruldu."
    state = read_automation_state()
    pid = state.get("controller_pid")
    if pid:
        try:
            os.kill(int(pid), 15)
            return True, "Otomasyon durdurma sinyali gönderildi."
        except Exception as exc:
            return False, f"Otomasyon durdurulamadı: {exc}"
    return False, "Çalışan otomasyon bulunamadı."


# =========================================================
# BRAIN ORCHESTRATOR PROCESS
# =========================================================

BRAIN_PROCESS = None


def brain_orchestrator_running():
    global BRAIN_PROCESS
    if BRAIN_PROCESS is None:
        return False
    try:
        running = BRAIN_PROCESS.poll() is None
    except Exception:
        running = False
    if not running:
        BRAIN_PROCESS = None
    return running


def run_brain_orchestrator():
    global BRAIN_PROCESS
    if brain_orchestrator_running():
        return False, "Brain Orchestrator zaten çalışıyor."
    if not BRAIN_ORCHESTRATOR.exists():
        return False, f"Brain Orchestrator bulunamadı: {BRAIN_ORCHESTRATOR}"
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        BRAIN_PROCESS = subprocess.Popen(
            [sys.executable, "-u", str(BRAIN_ORCHESTRATOR)],
            cwd=str(BASE_DIR),
            creationflags=creationflags,
        )
        return True, "Brain Orchestrator başlatıldı."
    except Exception as exc:
        BRAIN_PROCESS = None
        return False, f"Brain Orchestrator başlatılamadı: {exc}"



# =========================================================
# HTML
# =========================================================

HTML = '\n<!DOCTYPE html>\n<html lang="tr">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>MarketHQ — Control Center</title>\n<style>\n:root{\n  --bg:#f4f6f8;--card:#fff;--soft:#fafbfc;--line:#dfe5eb;--text:#111;\n  --muted:#252a30;--purple:#6547e8;--purple-soft:#f0edff;--green:#148a5d;\n  --green-soft:#eaf8f1;--amber:#9a6a07;--amber-soft:#fff6dc;--red:#b6314d;\n  --red-soft:#fff0f3;--blue:#2d68bc;--blue-soft:#edf4ff;--shadow:0 7px 24px rgba(24,34,44,.055)\n}\n*{box-sizing:border-box}\nhtml{scroll-behavior:smooth}\nbody{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;line-height:1.45}\nbutton,input,textarea,select{font:inherit;color:#111}\nbutton{cursor:pointer}\nbutton:disabled{cursor:wait;opacity:.48}\na{color:#111;text-decoration:underline}\n.topbar{position:sticky;top:0;z-index:50;height:60px;background:rgba(255,255,255,.97);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:9px;padding:0 24px}\n.logo{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:900;letter-spacing:-.4px}\n.logo-mark{width:21px;height:21px;border-radius:6px;background:linear-gradient(135deg,#967aff,#5d3ddd)}\n.brand-sub{font-size:9px;color:#111;font-weight:900;letter-spacing:1px}\n.flex1{flex:1}\n.statusbar{display:flex;align-items:center;gap:7px;font-size:10px;font-weight:800;color:#111}\n.status-dot{width:8px;height:8px;border-radius:50%;background:var(--blue)}\n.btn{border:1px solid #cfd6de;background:#fff;color:#111;border-radius:8px;padding:8px 12px;font-size:10px;font-weight:900}\n.btn:hover{border-color:#aeb8c2;background:#fbfcfe}\n.btn.brain{background:var(--purple-soft);border-color:#d4ccff}\n.btn.primary{background:#111;border-color:#111;color:#fff}\n.shell{max-width:1560px;margin:0 auto;padding:22px 24px 42px}\n.hero{display:flex;gap:24px;align-items:flex-start;margin-bottom:18px}\n.hero-main{flex:1}\n.eyebrow{font-size:9px;letter-spacing:1.3px;font-weight:900;color:#111}\nh1{font-size:31px;line-height:1.08;letter-spacing:-1.1px;margin:5px 0 8px;color:#111}\n.hero p{margin:0;max-width:820px;color:#202328;font-size:12px}\n.hero-actions{display:flex;gap:7px;flex-wrap:wrap;max-width:470px;justify-content:flex-end}\n.quick{border:1px solid #cfd6de;background:#fff;color:#111;border-radius:8px;padding:8px 10px;font-size:10px;font-weight:900}\n.quick:hover{background:#fbfcfd}\n.nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}\n.nav a{text-decoration:none;color:#111;background:#fff;border:1px solid var(--line);padding:6px 10px;border-radius:999px;font-size:9px;font-weight:900}\n.kpis{display:grid;grid-template-columns:repeat(8,1fr);gap:9px;margin-bottom:16px}\n.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);padding:12px;min-height:86px}\n.kpi .label{font-size:8px;color:#111;font-weight:900;text-transform:uppercase;letter-spacing:.8px}\n.kpi .value{font-size:23px;font-weight:900;margin-top:7px;color:#111}\n.kpi .meta{font-size:8px;color:#333;margin-top:2px}\n.kpi.p .value{color:var(--purple)}.kpi.g .value{color:var(--green)}.kpi.a .value{color:var(--amber)}.kpi.r .value{color:var(--red)}\n.grid2{display:grid;grid-template-columns:1.45fr 1fr;gap:16px}\n.card{background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);overflow:hidden}\n.head{display:flex;align-items:center;gap:8px;padding:13px 15px;border-bottom:1px solid var(--line)}\n.head h2{margin:0;font-size:12px;color:#111}.head .muted{color:#333;font-size:9px}\n.body{padding:14px}\n.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}\n.box{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:12px}\n.box .cap{font-size:8px;text-transform:uppercase;letter-spacing:.8px;color:#111;font-weight:900}\n.box .main{font-size:16px;font-weight:900;margin-top:4px;color:#111}.box p{margin:4px 0 0;color:#333;font-size:9px}\n.mini-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:10px}\n.mini{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:9px}\n.mini .cap{font-size:8px;color:#111;font-weight:900}.mini .num{font-size:16px;font-weight:900;margin-top:4px;color:#111}\n.two{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}\n.list{display:grid;gap:7px}.row{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:9px}\n.rowtop{display:flex;align-items:center;gap:6px}.rowtop strong{font-size:9px;color:#111}.rowtop .right{margin-left:auto;color:#222;font-size:8px}\n.desc{margin-top:4px;color:#2e353c;font-size:8px;line-height:1.45}\n.tag{display:inline-flex;border-radius:999px;padding:3px 6px;font-size:7px;font-weight:900;background:#eceff2;color:#111}\n.tag.p{background:var(--purple-soft)}.tag.g{background:var(--green-soft)}.tag.a{background:var(--amber-soft)}.tag.r{background:var(--red-soft)}.tag.b{background:var(--blue-soft)}\n.ask{display:grid;grid-template-columns:1fr 105px;gap:8px}\ntextarea{width:100%;min-height:82px;resize:vertical;background:#fff;border:1px solid #cfd6de;border-radius:9px;padding:10px;outline:none;font-size:10px;color:#111}\ntextarea:focus{border-color:#a99af8;box-shadow:0 0 0 3px rgba(101,71,232,.08)}\n.ask-btn{border:1px solid #111;background:#111;color:#fff;border-radius:9px;font-weight:900;font-size:9px}\n.answer{margin-top:10px;border:1px solid var(--line);background:var(--soft);border-radius:9px;padding:12px;min-height:128px;white-space:pre-wrap;color:#111;font-size:9px;line-height:1.65}\n.answer-meta{display:flex;justify-content:space-between;margin-top:6px;color:#333;font-size:7px}\n.full{margin-top:16px}.agent-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}\n.agent{border:1px solid var(--line);background:var(--soft);border-radius:9px;padding:10px}\n.agent:hover{background:#fff;border-color:#c6cfd8}\n.agent-top{display:flex;gap:8px;align-items:center}.agent-icon{font-size:17px}\n.agent-name{font-size:10px;font-weight:900;color:#111}.agent-room{font-size:8px;color:#333}\n.agent-state{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:8px;color:#111}\n.state-dot{width:7px;height:7px;border-radius:50%;background:#9da6b0}.state-dot.w{background:var(--green)}.state-dot.e{background:var(--red)}.state-dot.d{background:var(--purple)}\n.task-cols{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.col-title{font-size:8px;color:#111;font-weight:900;text-transform:uppercase;letter-spacing:.8px;margin-bottom:7px}\n.task{border:1px solid var(--line);background:var(--soft);border-radius:8px;padding:9px;margin-bottom:7px}.task strong{font-size:9px;display:block;color:#111;line-height:1.4}.task p{margin:4px 0 0;color:#333;font-size:8px}\n.section-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}\n.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:650px}th,td{padding:9px 10px;border-bottom:1px solid var(--line);font-size:8px;text-align:left;vertical-align:top;color:#111}th{font-size:7px;color:#222;letter-spacing:.7px;text-transform:uppercase;background:var(--soft)}\n.activity{display:grid;gap:6px}\n.info-banner{border:1px solid #cfd6de;background:#f7f8fa;border-radius:9px;padding:10px;font-size:9px;color:#111;margin-bottom:10px}\n.info-banner strong{font-weight:900}\n.badge-line{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-top:6px}\n.live-dot{width:7px;height:7px;border-radius:50%;display:inline-block;background:#9da6b0}.live-dot.on{background:var(--green)}.live-dot.warn{background:var(--amber)}.live-dot.bad{background:var(--red)}\n.small-note{font-size:8px;color:#222}\n@media(max-width:1250px){.kpis{grid-template-columns:repeat(4,1fr)}.grid2{grid-template-columns:1fr}.agent-grid{grid-template-columns:repeat(3,1fr)}}\n@media(max-width:820px){.topbar{padding:0 14px}.shell{padding:16px 14px 28px}.hero{flex-direction:column}.hero-actions{justify-content:flex-start}.kpis{grid-template-columns:repeat(2,1fr)}.status-grid,.two,.section-grid{grid-template-columns:1fr}.mini-grid{grid-template-columns:repeat(2,1fr)}.task-cols{grid-template-columns:1fr}.agent-grid{grid-template-columns:repeat(2,1fr)}}\n</style>\n</head>\n<body>\n<header class="topbar">\n  <div class="logo"><span class="logo-mark"></span><span>MarketHQ</span><span class="brand-sub">CONTROL CENTER</span></div>\n  <div class="flex1"></div>\n  <div class="statusbar"><span id="topDot" class="status-dot"></span><span id="topStatus">Hazır</span></div>\n  <button class="btn" id="refreshBtn">Yenile</button>\n  <button class="btn" id="runHqBtn">Run HQ</button>\n  <button class="btn brain" id="runBrainBtn">Brain Loop</button>\n</header>\n\n<main class="shell">\n  <section class="hero">\n    <div class="hero-main">\n      <div class="eyebrow">MARKET RESEARCH OS</div>\n      <h1>MarketHQ\'nun tamamı tek ekranda.</h1>\n      <p>Brain, research loop, ajanlar, knowledge, learning, kaynaklar ve Strategy Lab. Sade, ferah ve doğrudan kullanılabilir.</p>\n    </div>\n    <div class="hero-actions">\n      <button class="quick" data-q="Sistemin şu an en önemli üç açığı ne?">3 açık</button>\n      <button class="quick" data-q="Şu ana kadar gerçekten ne öğrendik?">Ne öğrendik?</button>\n      <button class="quick" data-q="Brain research loop şu an hangi durumda?">Brain durumu</button>\n      <button class="quick" data-q="Bir sonraki en değerli geliştirme adımı ne olmalı?">Next step</button>\n    </div>\n  </section>\n\n  <nav class="nav">\n    <a href="#overview">Özet</a><a href="#live">Live Pipeline</a><a href="#brain">Brain</a><a href="#agents">Ajanlar</a><a href="#tasks">Görevler</a>\n    <a href="#knowledge">Knowledge</a><a href="#learning">Learning</a><a href="#sources">Kaynaklar</a><a href="#strategy">Strategy Lab</a><a href="#selfhealing">Self-Healing</a><a href="#ask">AI</a><a href="#activity">Activity</a>\n  </nav>\n\n  <section id="overview">\n    <div class="kpis">\n      <div class="kpi p"><div class="label">Brain Nodes</div><div id="kNodes" class="value">—</div><div class="meta">Graph</div></div>\n      <div class="kpi p"><div class="label">Brain Edges</div><div id="kEdges" class="value">—</div><div class="meta">Relations</div></div>\n      <div class="kpi"><div class="label">Observations</div><div id="kObs" class="value">—</div><div class="meta">Memory</div></div>\n      <div class="kpi"><div class="label">Claims</div><div id="kClaims" class="value">—</div><div class="meta">Brain claims</div></div>\n      <div class="kpi g"><div class="label">Learning Events</div><div id="kLearn" class="value">—</div><div class="meta">Feedback</div></div>\n      <div class="kpi"><div class="label">Evidence Reviews</div><div id="kReviews" class="value">—</div><div class="meta">AI review</div></div>\n      <div class="kpi a"><div class="label">Active Queue</div><div id="kQueue" class="value">—</div><div class="meta">Research</div></div>\n      <div class="kpi r"><div class="label">Orphan Nodes</div><div id="kOrphans" class="value">—</div><div class="meta">Review candidate</div></div>\n    </div>\n  </section>\n\n  <section id="live" class="full card">\n    <div class="head"><h2>Live MarketHQ Pipeline</h2><span class="tag g">GERÇEK RUNTIME VERİSİ</span><span id="liveMeta" class="muted">—</span></div>\n    <div class="body">\n      <div class="mini-grid">\n        <div class="mini"><div class="cap">Genel Haber</div><div id="liveNews" class="num">—</div></div>\n        <div class="mini"><div class="cap">Türkiye Haber</div><div id="liveTurkeyNews" class="num">—</div></div>\n        <div class="mini"><div class="cap">BIST Veri</div><div id="liveTurkeyMarket" class="num">—</div></div>\n        <div class="mini"><div class="cap">AI Analiz</div><div id="liveAnalyst" class="num">—</div></div>\n        <div class="mini"><div class="cap">Şirket Bildirimi</div><div id="liveCompany" class="num">—</div></div>\n      </div>\n      <div class="info-banner" style="margin-top:10px"><strong>Pipeline:</strong> Haber → Türkiye Haber → BIST Veri → AI Analyst → Performance. Bu alan runtime_state içindeki son agent durumlarından beslenir.</div>\n    </div>\n  </section>\n\n  <section class="grid2">\n    <div id="brain" class="card">\n      <div class="head"><h2>Brain / Research Loop</h2><span id="brainState" class="muted">Hazır</span><div class="flex1"></div><button class="btn brain" id="brainBtn2">Brain Loop</button></div>\n      <div class="body">\n        <div id="brainBanner" class="info-banner"><strong>Durum:</strong> Brain Loop hazır. Tek tıkla research pipeline\'ı başlatabilirsin.</div>\n        <div class="status-grid">\n          <div class="box"><div class="cap">System</div><div id="systemStatus" class="main">—</div><p id="systemMessage">—</p></div>\n          <div class="box"><div class="cap">Pipeline</div><div id="pipelineState" class="main">—</div><p id="pipelineInfo">Queue → Research → Knowledge → Review → Brain</p></div>\n        </div>\n        <div class="mini-grid">\n          <div class="mini"><div class="cap">Validated</div><div id="bValidated" class="num">—</div></div>\n          <div class="mini"><div class="cap">Canonical</div><div id="bCanonical" class="num">—</div></div>\n          <div class="mini"><div class="cap">Open contradiction</div><div id="bContradictions" class="num">—</div></div>\n          <div class="mini"><div class="cap">Episodes</div><div id="bEpisodes" class="num">—</div></div>\n          <div class="mini"><div class="cap">Updates</div><div id="bUpdates" class="num">—</div></div>\n        </div>\n        <div class="two">\n          <div><div class="head" style="padding:0 0 8px;border:0"><h2>Son Brain Updates</h2></div><div id="brainUpdates" class="list"></div></div>\n          <div><div class="head" style="padding:0 0 8px;border:0"><h2>Son Evidence Reviews</h2></div><div id="brainReviews" class="list"></div></div>\n        </div>\n      </div>\n    </div>\n\n    <div id="ask" class="card">\n      <div class="head"><h2>AI Terminal</h2><span class="muted">MarketHQ verisiyle</span></div>\n      <div class="body">\n        <div class="ask"><textarea id="queryInput" placeholder="Örn: Brain\'in şu an en kritik problemi ne?"></textarea><button id="askBtn" class="ask-btn">SORGULA</button></div>\n        <div id="answerCard" class="answer">Hazır. Soru yaz ve SORGULA\'ya bas.</div>\n        <div class="answer-meta"><span id="answerModel">—</span><span id="answerTime">—</span></div>\n      </div>\n    </div>\n  </section>\n\n  <section id="selfhealing" class="full card">\n    <div class="head"><h2>Automation / Self-Healing</h2><span class="tag a">OTOMASYON MERKEZİ</span><span id="automationMeta" class="muted">—</span><div class="flex1"></div>\n      <button class="btn" id="autoScanBtn">Sistemi Tara</button>\n      <button class="btn primary" id="autoStartBtn">Otomasyonu Başlat</button>\n      <button class="btn" id="autoStartHealBtn">Auto-Heal ile Başlat</button>\n      <button class="btn" id="autoStopBtn">Durdur</button>\n    </div>\n    <div class="body">\n      <div class="status-grid">\n        <div class="box"><div class="cap">Automation</div><div id="automationState" class="main">—</div><p id="automationDetail">—</p></div>\n        <div class="box"><div class="cap">Self-Healing</div><div id="healingState" class="main">—</div><p id="healingDetail">—</p></div>\n      </div>\n      <div class="mini-grid">\n        <div class="mini"><div class="cap">Queue</div><div id="aQueue" class="num">—</div></div>\n        <div class="mini"><div class="cap">Syntax Error</div><div id="aSyntax" class="num">—</div></div>\n        <div class="mini"><div class="cap">Runtime Error</div><div id="aRuntime" class="num">—</div></div>\n        <div class="mini"><div class="cap">Auto-Heal</div><div id="aAutoHeal" class="num">—</div></div>\n        <div class="mini"><div class="cap">Last Action</div><div id="aAction" class="num" style="font-size:11px">—</div></div>\n      </div>\n      <div id="automationBanner" class="info-banner" style="margin-top:10px"><strong>Durum:</strong> Otomasyon henüz başlatılmadı.</div>\n      <div class="two">\n        <div>\n          <div class="head" style="padding:0 0 8px;border:0"><h2>Learning Feedback</h2><span id="feedbackMeta" class="muted">—</span></div>\n          <div id="feedbackBox" class="list"></div>\n        </div>\n        <div>\n          <div class="head" style="padding:0 0 8px;border:0"><h2>Otomasyon Döngüsü</h2><span id="cycleMeta" class="muted">—</span></div>\n          <div id="cycleBox" class="list"></div>\n        </div>\n      </div>\n    </div>\n  </section>\n\n  <section id="agents" class="full card">\n    <div class="head"><h2>Ajanlar</h2><span class="muted">Runtime durumu</span><div class="flex1"></div><button class="btn" id="agentRefresh">Yenile</button></div>\n    <div class="body"><div id="agentGrid" class="agent-grid"></div></div>\n  </section>\n\n  <section id="tasks" class="full card">\n    <div class="head"><h2>Görevler</h2><span id="taskSummary" class="muted">—</span></div>\n    <div class="body"><div class="task-cols">\n      <div><div class="col-title">Bekleyen <span id="todoCount">0</span></div><div id="todoCol"></div></div>\n      <div><div class="col-title">Çalışıyor <span id="workCount">0</span></div><div id="workCol"></div></div>\n      <div><div class="col-title">Tamamlandı / Hata <span id="doneCount">0</span></div><div id="doneCol"></div></div>\n    </div></div>\n  </section>\n\n  <div class="section-grid">\n    <section id="knowledge" class="card">\n      <div class="head"><h2>Knowledge</h2><span id="knowledgeMeta" class="muted">—</span></div>\n      <div class="body"><div id="knowledgeList" class="list"></div></div>\n    </section>\n\n    <section id="learning" class="card">\n      <div class="head"><h2>Learning</h2><span id="learningMeta" class="muted">—</span></div>\n      <div class="body"><div class="tablewrap"><table><thead><tr><th>Method</th><th>Symbol</th><th>Condition</th><th>Sample</th><th>Success</th><th>Confidence</th></tr></thead><tbody id="rulesTable"></tbody></table></div></div>\n    </section>\n  </div>\n\n  <section id="sources" class="full card">\n    <div class="head"><h2>Kaynaklar</h2><span id="sourceMeta" class="muted">—</span></div>\n    <div class="body"><div class="tablewrap"><table><thead><tr><th>Başlık</th><th>Tip</th><th>URL</th><th>Durum</th></tr></thead><tbody id="sourcesTable"></tbody></table></div></div>\n  </section>\n\n  <section id="strategy" class="full card">\n    <div class="head"><h2>Strategy Lab</h2><span id="strategyMeta" class="muted">—</span><div class="flex1"></div><button class="btn" id="runLabBtn">Lab\'ı çalıştır</button></div>\n    <div class="body">\n      <div class="status-grid">\n        <div class="box"><div class="cap">Status</div><div id="strategyStatus" class="main">—</div><p id="strategyDetail">—</p></div>\n        <div class="box"><div class="cap">Symbols</div><div id="strategySymbols" class="main">—</div><p>Son Strategy Lab sonucu</p></div>\n      </div>\n    </div>\n  </section>\n\n  <section id="activity" class="full card">\n    <div class="head"><h2>Recent Activity</h2><span class="muted">Runtime event geçmişi</span></div>\n    <div class="body"><div id="activityList" class="activity"></div></div>\n  </section>\n</main>\n\n<div id="toast" style="display:none;position:fixed;right:20px;bottom:20px;background:#111;color:#fff;padding:10px 13px;border-radius:9px;font-size:9px;box-shadow:0 14px 40px rgba(0,0,0,.18);z-index:100"></div>\n\n<script>\nconst META={"hq": {"icon": "🏢", "room": "HQ CONTROL"}, "news": {"icon": "📰", "room": "NEWS ROOM"}, "turkey_news": {"icon": "🇹🇷", "room": "TURKEY NEWS"}, "turkey_market": {"icon": "📊", "room": "TURKEY DATA"}, "company_updates": {"icon": "🏭", "room": "COMPANY DESK"}, "market_data": {"icon": "📈", "room": "MARKET DATA"}, "analyst": {"icon": "🧠", "room": "AI ANALYST"}, "performance": {"icon": "📊", "room": "PERFORMANCE"}, "strategy_lab": {"icon": "🧪", "room": "STRATEGY LAB"}, "fin_sys": {"icon": "📚", "room": "FIN[SYS]"}, "youtube": {"icon": "🎥", "room": "YOUTUBE"}};\nwindow.S={runtime:null,intel:null,strategy:null};\n\nfunction $(id){return document.getElementById(id)}\nfunction esc(v){return String(v??"").replace(/[&<>"\']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","\'":"&#39;"}[s]))}\nfunction fmt(v){return Number(v??0).toLocaleString("tr-TR")}\nfunction time(v){if(!v)return "—";try{return new Date(v).toLocaleString("tr-TR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"})}catch{return String(v)}}\nfunction short(v,n=110){const s=String(v??"");return s.length>n?s.slice(0,n-1)+"…":s}\nfunction status(v){return String(v||"IDLE").toUpperCase()}\nfunction toast(msg,bad=false){const el=$("toast");el.textContent=msg;el.style.display="block";el.style.background=bad?"#8b2f42":"#111";clearTimeout(window._toast);window._toast=setTimeout(()=>el.style.display="none",2800)}\nasync function getJson(url){const r=await fetch(url,{cache:"no-store"});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.error||"İstek başarısız");return d}\nasync function postJson(url,p={}){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.error||d.answer||"İstek başarısız");return d}\nfunction tag(t,c=""){return `<span class="tag ${c}">${esc(t)}</span>`}\n\nfunction agentInfo(name){\n  const a=window.S.runtime?.agents?.[name];\n  return a&&typeof a==="object"?a:{};\n}\nfunction extractCount(info){\n  const direct=[info.count,info.items,info.total,info.records,info.analysis_count];\n  for(const v of direct){\n    if(v!==undefined&&v!==null&&v!==""&&!Number.isNaN(Number(v))) return Number(v);\n  }\n  const text=String(info.detail||info.message||info.text||"");\n  const m=text.match(/(?:^|\\D)(\\d+)(?:\\s*(?:haber|analiz|kayıt|bildirim|item|record))/i);\n  return m?Number(m[1]):0;\n}\nfunction renderLivePipeline(){\n  const names={news:"liveNews",turkey_news:"liveTurkeyNews",turkey_market:"liveTurkeyMarket",analyst:"liveAnalyst",company_updates:"liveCompany"};\n  for(const [agent,id] of Object.entries(names)) $(id).textContent=fmt(extractCount(agentInfo(agent)));\n  const now=new Date();\n  $("liveMeta").textContent="Son yenileme: "+now.toLocaleTimeString("tr-TR");\n}\nfunction renderOverview(){\n  const i=window.S.intel||{},b=i.brain||{},sys=window.S.runtime?.system||{};\n  $("kNodes").textContent=fmt(b.nodes);$("kEdges").textContent=fmt(b.edges);$("kObs").textContent=fmt(b.observations);$("kClaims").textContent=fmt(b.claims);\n  $("kLearn").textContent=fmt(b.learning_events);$("kReviews").textContent=fmt(b.evidence_reviews);$("kQueue").textContent=fmt(b.research_queue_active);$("kOrphans").textContent=fmt(b.orphan_nodes);\n  $("systemStatus").textContent=status(sys.status);$("systemMessage").textContent=sys.message||"MarketHQ hazır.";\n  const running=Boolean(b.orchestrator_running);\n  $("brainState").textContent=running?"Çalışıyor":"Hazır";$("pipelineState").textContent=running?"RUNNING":"IDLE";\n  $("pipelineInfo").textContent=running?"Queue → Research → Knowledge → Review → Brain (aktif)":"Tek tur Brain Orchestrator hazır.";\n  $("brainBanner").innerHTML=running?"<strong>Durum:</strong> Brain Loop şu anda çalışıyor. Panel 5 saniyede bir yenileniyor.":"<strong>Durum:</strong> Brain Loop hazır. Tek tıkla research pipeline\'ı başlatabilirsin.";\n  $("bValidated").textContent=fmt(b.validated_candidates);$("bCanonical").textContent=fmt(b.canonical_research_items);$("bContradictions").textContent=fmt(b.contradictions_open);$("bEpisodes").textContent=fmt(b.research_episodes);$("bUpdates").textContent=fmt(b.research_updates);\n  $("topDot").style.background=status(sys.status)==="ERROR"?"#b6314d":running?"#148a5d":"#2d68bc";\n  $("topStatus").textContent=sys.message||status(sys.status);\n  $("runBrainBtn").disabled=running;$("brainBtn2").disabled=running;\n  $("runHqBtn").disabled=status(sys.status)==="WORKING";\n}\nfunction renderBrain(){\n  const b=window.S.intel?.brain||{},u=b.recent_updates||[],r=b.recent_reviews||[];\n  $("brainUpdates").innerHTML=u.length?u.slice(0,7).map(x=>`<div class="row"><div class="rowtop">${tag(x.verdict||"UPDATE","p")}<strong>review #${esc(x.review_id??"—")}</strong><span class="right">${time(x.created_at)}</span></div><div class="desc">${esc(short(x.action||"",120))} · queue=${esc(x.queue_task_id??"—")}</div></div>`).join(""):\'<div class="row"><div class="desc">Brain update yok.</div></div>\';\n  $("brainReviews").innerHTML=r.length?r.slice(0,7).map(x=>`<div class="row"><div class="rowtop">${tag(x.verdict||"REVIEW",x.verdict==="CONTRADICTORY"?"r":x.verdict==="PARTIALLY_SUPPORTIVE"?"a":"g")}<strong>knowledge #${esc(x.knowledge_item_id??"—")}</strong><span class="right">score ${esc(Number(x.score||0).toFixed(3))}</span></div><div class="desc">observation=${esc(x.observation_id??"—")} · ${esc(x.review_method||"—")}</div></div>`).join(""):\'<div class="row"><div class="desc">Evidence review yok.</div></div>\';\n}\nfunction renderSelfHealing(){\n  const i=window.S.intel||{},a=i.automation||{},h=i.self_healing||{},fb=i.learning_feedback||{};\n  const running=Boolean(a.running);\n  const statusText=String(a.controller_status||"STOPPED").toUpperCase();\n  const syntax=Number((a.safe_gate||{}).syntax_errors||0);\n  const runtime=Number((a.safe_gate||{}).runtime_errors_detected||0);\n  const queue=Number((a.queue||{}).active||0);\n  const report=(a.last_learning_feedback||{}).report||{};\n  const feedbackCreated=Number(fb.queue_created||report.queue_created||0);\n  const feedbackSeen=Number(fb.reviews_seen||report.reviews_seen||0);\n  $("automationMeta").textContent=running?"AKTİF":statusText;\n  $("automationState").textContent=running?"AKTİF":"DURDU";\n  $("automationDetail").textContent=running\n    ? `Controller V2 · ${a.interval_seconds||60}s · ${a.auto_heal_enabled?"Auto-Heal açık":"Auto-Heal kapalı"}`\n    : (a.action_detail||"Controller çalışmıyor.");\n  $("healingState").textContent=h.running?"ÇALIŞIYOR":String(h.status||"UNKNOWN");\n  $("healingDetail").textContent=`${Number(h.syntax_errors||0)} syntax · ${Number(h.runtime_error_records||0)} runtime kayıt`;\n  $("aQueue").textContent=fmt(queue);\n  $("aSyntax").textContent=fmt(syntax);\n  $("aRuntime").textContent=fmt(runtime);\n  $("aAutoHeal").textContent=a.auto_heal_enabled?"ON":"OFF";\n  $("aAction").textContent=short(a.action||"IDLE",30);\n  $("automationBanner").innerHTML=`<strong>Son hareket:</strong> ${esc(a.action_detail||"Yeni işlem yok.")} · ${esc(a.updated_at||"—")}`;\n  $("autoStartBtn").disabled=running;\n  $("autoStartHealBtn").disabled=running;\n  $("autoStopBtn").disabled=!running;\n\n  const fbStatus=String(fb.status||report.status||"UNKNOWN");\n  const actions=fb.actions&&typeof fb.actions==="object"?fb.actions:{};\n  const actionText=Object.entries(actions).map(([k,v])=>`${k}: ${v}`).join(" · ");\n  $("feedbackMeta").textContent=fb.updated_at?time(fb.updated_at):"—";\n  $("feedbackBox").innerHTML=`<div class="row"><div class="rowtop"><span class="tag ${fbStatus==="COMPLETED"?"g":fbStatus==="ERROR"?"r":"b"}">${esc(fbStatus)}</span><strong>${fmt(feedbackCreated)} yeni görev</strong><span class="right">${fmt(feedbackSeen)} review</span></div><div class="desc">${esc(actionText||"Feedback henüz çalışmadı.")} ${a.last_brain_finished_at?`· Son Brain bitişi: ${esc(time(a.last_brain_finished_at))}`:""}</div></div>`;\n\n  const steps=[\n    ["Health Check", syntax===0 && runtime===0 ? "OK" : "DİKKAT"],\n    ["Research Queue", queue>0 ? `${queue} aktif` : "Boş"],\n    ["Brain", a.brain_running ? "ÇALIŞIYOR" : (a.last_brain_exit_code!=null ? `BİTTİ · exit ${a.last_brain_exit_code}` : "BEKLEMEDE")],\n    ["Learning Feedback", feedbackCreated>0 ? `${feedbackCreated} görev üretildi` : "Kontrol edildi"],\n  ];\n  $("cycleMeta").textContent=a.last_brain_started_at?`son başlangıç ${time(a.last_brain_started_at)}`:"henüz başlatılmadı";\n  $("cycleBox").innerHTML=steps.map(([name,state])=>`<div class="row"><div class="rowtop"><span class="live-dot ${state==="OK"||state.includes("üretildi")?"on":state==="DİKKAT"?"bad":""}"></span><strong>${esc(name)}</strong><span class="right">${esc(state)}</span></div></div>`).join("");\n}\n\nfunction renderAgents(){\n  const agents=window.S.runtime?.agents||{},entries=Object.entries(agents);\n  $("agentGrid").innerHTML=entries.length?entries.map(([name,a])=>{const m=META[name]||{},st=status(a?.status),cls=st==="WORKING"?"w":st==="ERROR"?"e":st==="COMPLETED"?"d":"";return `<div class="agent"><div class="agent-top"><span class="agent-icon">${esc(m.icon||"◉")}</span><div><div class="agent-name">${esc(name.replaceAll("_"," "))}</div><div class="agent-room">${esc(m.room||"Agent")}</div></div></div><div class="agent-state"><span class="state-dot ${cls}"></span>${esc(st)}</div></div>`}).join(""):\'<div class="row"><div class="desc">Runtime agent kaydı yok.</div></div>\';\n}\nfunction taskClass(t){const s=status(t?.status);return s==="WORKING"?"work":s==="COMPLETED"||s==="ERROR"?"done":"todo"}\nfunction renderTasks(){\n  const tasks=Array.isArray(window.S.runtime?.tasks)?window.S.runtime.tasks.slice(-60).reverse():[],c={todo:[],work:[],done:[]};\n  tasks.forEach(t=>c[taskClass(t)].push(t));$("todoCount").textContent=c.todo.length;$("workCount").textContent=c.work.length;$("doneCount").textContent=c.done.length;$("taskSummary").textContent=tasks.length+" son görev";\n  function draw(xs){return xs.slice(0,14).map(t=>`<div class="task"><strong>${esc(short(t?.name||t?.task||t?.title||"Görev",120))}</strong><p>${esc(t?.agent||t?.room||"—")} · ${esc(status(t?.status))} · #${esc(t?.id??t?.task_id??"—")}</p></div>`).join("")||\'<div class="row"><div class="desc">—</div></div>\'}\n  $("todoCol").innerHTML=draw(c.todo);$("workCol").innerHTML=draw(c.work);$("doneCol").innerHTML=draw(c.done);\n}\nfunction renderKnowledge(){\n  const k=window.S.intel?.knowledge||{},rows=k.recent_items||[];$("knowledgeMeta").textContent=fmt(k.items)+" kayıt";\n  $("knowledgeList").innerHTML=rows.length?rows.slice(0,10).map(x=>`<div class="row"><div class="rowtop"><strong>${esc(short(x.title||x.method_name||"Knowledge",84))}</strong><span class="right">${x.confidence!=null?"conf "+Number(x.confidence).toFixed(2):""}</span></div><div class="desc">${esc(short(x.summary||x.item_type||"—",180))}</div></div>`).join(""):\'<div class="row"><div class="desc">Knowledge yok.</div></div>\';\n}\nfunction renderLearning(){\n  const l=window.S.intel?.learning||{},rows=l.recent_rules||[];$("learningMeta").textContent=fmt(l.learned_rules)+" learned rule";\n  $("rulesTable").innerHTML=rows.length?rows.slice(0,14).map(x=>`<tr><td>${esc(short(x.method_name||"—",42))}</td><td>${esc(x.symbol||"—")}</td><td>${esc(short(x.condition_name||"—",54))}</td><td>${esc(x.sample_size??"—")}</td><td>${x.success_rate!=null?esc((Number(x.success_rate)*100).toFixed(1)+"%"):"—"}</td><td>${x.confidence!=null?esc(Number(x.confidence).toFixed(3)):"—"}</td></tr>`).join(""):\'<tr><td colspan="6">Learning kaydı yok.</td></tr>\';\n}\nfunction renderSources(){\n  const rows=window.S.intel?.knowledge?.recent_sources||[];$("sourceMeta").textContent=fmt(window.S.intel?.knowledge?.sources)+" source";\n  $("sourcesTable").innerHTML=rows.length?rows.map(x=>`<tr><td>${esc(short(x.title||x.name||"—",90))}</td><td>${esc(x.source_type||"—")}</td><td>${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(short(x.url,100))}</a>`:"—"}</td><td>${esc(x.status||"—")}</td></tr>`).join(""):\'<tr><td colspan="4">Source yok.</td></tr>\';\n}\nfunction renderStrategy(){\n  const s=window.S.strategy||{},r=window.S.intel?.research||{},exists=Boolean(s.exists);\n  $("strategyStatus").textContent=exists?String(s.status||"UNKNOWN"):"NONE";$("strategySymbols").textContent=fmt(r.strategy_symbols||0);\n  $("strategyMeta").textContent=exists?"son sonuç mevcut":"henüz koşulmadı";$("strategyDetail").textContent=exists?"Strategy Lab result kaydı mevcut.":"Strategy Lab sonucu bulunamadı.";\n}\nfunction renderActivity(){\n  const ev=Array.isArray(window.S.runtime?.events)?window.S.runtime.events.slice(-16).reverse():[];$("activityList").innerHTML=ev.length?ev.map(x=>`<div class="row"><div class="rowtop">${tag(x.type||x.event||"EVENT","b")}<strong>${esc(short(x.message||x.detail||x.task||"Runtime event",100))}</strong><span class="right">${time(x.timestamp||x.created_at)}</span></div></div>`).join(""):\'<div class="row"><div class="desc">Activity yok.</div></div>\';\n}\nasync function ask(){\n  const q=$("queryInput").value.trim();if(!q){toast("Önce soru yaz.",true);return}\n  $("askBtn").disabled=true;$("answerCard").textContent="MarketHQ bağlamı hazırlanıyor…";$("answerModel").textContent="AI";\n  try{const d=await postJson("/api/ask",{question:q});$("answerCard").textContent=d.answer||"Yanıt yok.";$("answerModel").textContent=d.model||"AI";$("answerTime").textContent=time(d.created_at)}\n  catch(e){$("answerCard").textContent="Sorgu başarısız: "+e.message;$("answerModel").textContent="ERROR";toast(e.message,true)}\n  finally{$("askBtn").disabled=false}\n}\nasync function run(path,button,label){\n  if(button)button.disabled=true;\n  try{const d=await postJson(path);toast(d.message||label+" başlatıldı.");await refresh()}\n  catch(e){toast(e.message,true)}\n  finally{await refresh().catch(()=>{})}\n}\nfunction question(q){$("queryInput").value=q;location.hash="#ask";$("queryInput").focus()}\nasync function refresh(){\n  const [runtime,intel,strategy]=await Promise.all([getJson("/api/state"),getJson("/api/intelligence"),getJson("/api/strategy-result")]);\n  window.S={runtime:runtime,intel:intel,strategy:strategy};\n  renderOverview();renderLivePipeline();renderBrain();renderSelfHealing();renderAgents();renderTasks();renderKnowledge();renderLearning();renderSources();renderStrategy();renderActivity();\n}\ndocument.querySelectorAll(".quick").forEach(b=>b.onclick=()=>question(b.dataset.q));\n$("askBtn").onclick=ask;\n$("queryInput").addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter")ask()});\n$("refreshBtn").onclick=()=>refresh().then(()=>toast("Panel yenilendi.")).catch(e=>toast(e.message,true));\n$("agentRefresh").onclick=()=>refresh().then(()=>toast("Ajanlar yenilendi.")).catch(e=>toast(e.message,true));\n$("runHqBtn").onclick=()=>run("/api/run",$("runHqBtn"),"Run HQ");\n$("runBrainBtn").onclick=()=>run("/api/run-brain",$("runBrainBtn"),"Brain Loop");\n$("brainBtn2").onclick=()=>run("/api/run-brain",$("brainBtn2"),"Brain Loop");\n$("runLabBtn").onclick=()=>run("/api/run-strategy",$("runLabBtn"),"Strategy Lab");\nasync function startAutomation(autoHeal=false){\n  const buttons=[$("autoStartBtn"),$("autoStartHealBtn")].filter(Boolean);\n  buttons.forEach(b=>b.disabled=true);\n  try{\n    const d=await postJson("/api/automation/start",{auto_heal:autoHeal,interval:60});\n    toast(d.message||"Otomasyon başlatıldı.");\n    await refresh();\n  }catch(e){toast(e.message,true)}\n  finally{await refresh().catch(()=>{})}\n}\nasync function stopAutomation(){\n  const btn=$("autoStopBtn");\n  btn.disabled=true;\n  try{\n    const d=await postJson("/api/automation/stop");\n    toast(d.message||"Otomasyon durduruldu.");\n    await refresh();\n  }catch(e){toast(e.message,true)}\n  finally{await refresh().catch(()=>{})}\n}\n$("autoScanBtn").onclick=()=>run("/api/self-healing/scan",$("autoScanBtn"),"Self-Healing taraması");\n$("autoStartBtn").onclick=()=>startAutomation(false);\n$("autoStartHealBtn").onclick=()=>startAutomation(true);\n$("autoStopBtn").onclick=stopAutomation;\nrefresh();\nsetInterval(()=>refresh().catch(()=>{}),5000);\n</script>\n</body>\n</html>\n'
# =========================================================
# HTTP HANDLER
# =========================================================

class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_html(self):
        payload = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_html()
            return
        if path == "/api/state":
            self.send_json(read_state())
            return
        if path == "/api/intelligence":
            self.send_json(read_intelligence())
            return
        if path == "/api/strategy-result":
            self.send_json(read_strategy_result())
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/ask":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(max(0, min(length, 20000)))
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                self.send_json({"success": False, "error": "Geçersiz istek gövdesi."}, 400)
                return
            success, answer, model = ask_hq(
                body.get("question", ""),
                body.get("selected_agent", ""),
            )
            self.send_json(
                {
                    "success": success,
                    "answer": answer,
                    "model": model,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
                200 if success else 400,
            )
            return

        if path == "/api/run":
            success, message = run_market_hq()
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/run-strategy":
            success, message = run_strategy_lab()
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/run-brain":
            success, message = run_brain_orchestrator()
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/self-healing/scan":
            success, message = run_self_healing(auto_apply=False)
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/self-healing/auto":
            success, message = run_self_healing(auto_apply=True)
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/automation/start":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(max(0, min(length, 5000)))
                body = json.loads(raw.decode("utf-8") or "{}") if raw else {}
            except Exception:
                body = {}
            try:
                interval = max(10, int(body.get("interval", 60)))
            except (TypeError, ValueError):
                interval = 60
            success, message = run_automation(bool(body.get("auto_heal", False)), interval)
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        if path == "/api/automation/stop":
            success, message = stop_automation()
            self.send_json({"success": success, "message": message}, 200 if success else 409)
            return

        self.send_json({"error": "Not found"}, 404)

    def log_message(self, format_string, *args):
        return


# =========================================================
# SERVER
# =========================================================

def main():
    print()
    print("=" * 72)
    print("🏢 MARKET HQ — EXECUTIVE INTELLIGENCE CENTER")
    print("=" * 72)
    print()
    print(f"🌐 http://{HOST}:{PORT}")
    print("Dashboard çalışıyor. CTRL+C ile durdur.")
    print()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Dashboard kapatıldı.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

