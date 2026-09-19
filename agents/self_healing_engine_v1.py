import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "self_healing"
REPORT_FILE = LOG_DIR / "last_report.json"
PROPOSAL_DIR = LOG_DIR / "proposals"
BACKUP_DIR = LOG_DIR / "backups"
STATE_FILE = BASE_DIR / "runtime_state.json"

load_dotenv(BASE_DIR / ".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("MARKETHQ_AI_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.6-luna")).strip()
OPENAI_RESPONSES_URL = os.getenv("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses").strip()

EXCLUDE_DIRS = {".venv", "venv", "__pycache__", ".git", "self_healing"}
MAX_FILE_BYTES = 220_000


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs():
    LOG_DIR.mkdir(exist_ok=True)
    PROPOSAL_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def discover_python_files():
    files = []
    for path in BASE_DIR.rglob("*.py"):
        rel = path.relative_to(BASE_DIR)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        try:
            if path.stat().st_size <= MAX_FILE_BYTES:
                files.append(path)
        except OSError:
            continue
    return sorted(files)


def syntax_scan():
    results = []
    for path in discover_python_files():
        item = {"file": str(path.relative_to(BASE_DIR)), "status": "OK", "error": None}
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            item["status"] = "ERROR"
            item["error"] = str(exc)
        except Exception as exc:
            item["status"] = "ERROR"
            item["error"] = repr(exc)
        results.append(item)
    return results


def runtime_error_context():
    state = read_json(STATE_FILE, {})
    errors = []
    if isinstance(state, dict):
        events = state.get("events") if isinstance(state.get("events"), list) else []
        tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
        for row in events[-60:]:
            if isinstance(row, dict) and str(row.get("type", row.get("status", ""))).upper() in {"ERROR", "FAILED", "FAIL"}:
                errors.append({"source": "event", "data": row})
        for row in tasks[-60:]:
            if isinstance(row, dict) and str(row.get("status", "")).upper() in {"ERROR", "FAILED", "FAIL"}:
                errors.append({"source": "task", "data": row})
    return errors[-20:]


def build_report():
    ensure_dirs()
    syntax = syntax_scan()
    runtime = runtime_error_context()
    syntax_errors = [x for x in syntax if x["status"] == "ERROR"]
    report = {
        "engine": "self_healing_engine_v1",
        "scanned_at": utc_now(),
        "project": str(BASE_DIR),
        "python_files_scanned": len(syntax),
        "syntax_errors": len(syntax_errors),
        "runtime_error_records": len(runtime),
        "status": "HEALTHY" if not syntax_errors and not runtime else "ATTENTION",
        "syntax": syntax,
        "runtime_errors": runtime,
    }
    write_json(REPORT_FILE, report)
    return report


def _extract_output_text(data):
    text = data.get("output_text")
    if text:
        return str(text).strip()
    chunks = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            value = content.get("text")
            if value:
                chunks.append(str(value))
    return "\n".join(chunks).strip()


def ask_repair(file_path, error_text):
    if not OPENAI_API_KEY:
        return None, "OPENAI_API_KEY yok. AI repair kapalı."
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, f"Dosya okunamadı: {exc}"

    prompt = f"""
MarketHQ içindeki bir Python dosyasında hata var.

Dosya: {file_path.relative_to(BASE_DIR)}
Hata:
{error_text}

Aşağıdaki dosyayı, yalnızca gerekli değişiklikleri yaparak düzeltilmiş TAM dosya olarak üret.
Davranışı gereksiz yere değiştirme. Harici bağımlılık ekleme. Placeholder bırakma.
Çıktı sadece şu iki işaret arasında olsun:
---BEGIN FILE---
...tam dosya...
---END FILE---

MEVCUT DOSYA:
{source}
"""
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": "You are a careful Python maintenance engineer. Preserve existing architecture and make the smallest correct repair."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            return None, str(data.get("error", {}).get("message", response.text))
        text = _extract_output_text(data)
        start = text.find("---BEGIN FILE---")
        end = text.find("---END FILE---")
        if start < 0 or end < 0 or end <= start:
            return None, "AI tam dosya formatında onarım döndürmedi."
        repaired = text[start + len("---BEGIN FILE---"):end].strip() + "\n"
        if not repaired or len(repaired) > MAX_FILE_BYTES * 2:
            return None, "Onarım çıktısı geçersiz boyutta."
        return repaired, None
    except Exception as exc:
        return None, f"AI repair hatası: {exc}"


def validate_source(source_text):
    with tempfile.TemporaryDirectory(prefix="markethq_heal_") as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(source_text, encoding="utf-8")
        try:
            py_compile.compile(str(path), doraise=True)
            return True, "Syntax test OK"
        except Exception as exc:
            return False, str(exc)


def repair_first_syntax_error(auto_apply=False):
    report = build_report()
    targets = [x for x in report["syntax"] if x["status"] == "ERROR"]
    if not targets:
        report["repair"] = {"status": "NOT_NEEDED", "message": "Syntax hatası bulunmadı."}
        write_json(REPORT_FILE, report)
        return report

    target = targets[0]
    file_path = BASE_DIR / target["file"]
    repaired, repair_error = ask_repair(file_path, target["error"])
    if repaired is None:
        report["repair"] = {"status": "FAILED", "file": target["file"], "error": repair_error}
        write_json(REPORT_FILE, report)
        return report

    valid, validation_message = validate_source(repaired)
    proposal = PROPOSAL_DIR / f"{file_path.stem}_{int(time.time())}.py"
    proposal.write_text(repaired, encoding="utf-8")

    repair_info = {
        "file": target["file"],
        "proposal": str(proposal.relative_to(BASE_DIR)),
        "validation": validation_message,
        "status": "PROPOSED" if valid else "REJECTED",
        "auto_apply_requested": bool(auto_apply),
    }

    if valid and auto_apply:
        backup = BACKUP_DIR / f"{file_path.name}.{int(time.time())}.bak"
        try:
            shutil.copy2(file_path, backup)
            file_path.write_text(repaired, encoding="utf-8")
            py_compile.compile(str(file_path), doraise=True)
            repair_info["status"] = "APPLIED"
            repair_info["backup"] = str(backup.relative_to(BASE_DIR))
        except Exception as exc:
            try:
                if backup.exists():
                    shutil.copy2(backup, file_path)
            except Exception:
                pass
            repair_info["status"] = "ROLLED_BACK"
            repair_info["error"] = str(exc)

    report["repair"] = repair_info
    write_json(REPORT_FILE, report)
    return report


def main():
    auto_apply = "--auto" in sys.argv
    report = repair_first_syntax_error(auto_apply=auto_apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
