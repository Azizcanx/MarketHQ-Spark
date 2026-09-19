#!/usr/bin/env python3
"""AgentSpace Autonomous Engine v2 — API-based goal execution."""

import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTSPACE_DIR = PROJECT_ROOT / "agentspace"
EVOLUTION_DIR = AGENTSPACE_DIR / "evolution"
QUEUE_DIR = AGENTSPACE_DIR / "queue"
for d in [EVOLUTION_DIR, QUEUE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "http://localhost:3000/api/agentspace"
API_TOKEN = "markethq-agentspace-1789732782"


class EvolutionLog:
    def __init__(self):
        self.path = EVOLUTION_DIR / "evolution.jsonl"

    def record(self, goal, task, result, strategy, next_strategy):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "goal": goal, "task": task,
            "exit_code": result.get("exit_code"),
            "stdout_preview": (result.get("stdout") or [""])[0][:200] if result.get("stdout") else "",
            "strategy": strategy, "next_strategy": next_strategy,
            "improvement": next_strategy != strategy,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def get_last_n(self, n=20):
        try:
            lines = self.path.read_text(encoding="utf-8").strip().split("\n")
            return [json.loads(l) for l in lines[-n:] if l.strip()]
        except Exception:
            return []

    def suggest_strategy(self, goal):
        history = self.get_last_n(10)
        if not history:
            return "direct"
        recent_success = [h for h in history[-3:] if h.get("exit_code") == 0]
        if len(recent_success) >= 2:
            return recent_success[-1].get("strategy", "direct")
        tried = set(h.get("strategy") for h in history)
        for s in ["direct", "decompose", "step_by_step", "research_first", "verify_first"]:
            if s not in tried:
                return s
        return "direct"


class TaskQueue:
    def __init__(self):
        self.path = QUEUE_DIR / "queue.json"

    def add(self, goal, priority=0):
        queue = self.load()
        tid = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        queue.append({"id": tid, "goal": goal, "priority": priority,
                       "status": "queued", "created": datetime.now().isoformat(), "progress": []})
        self.save(queue)
        return tid

    def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save(self, queue):
        self.path.write_text(json.dumps(queue, ensure_ascii=False, indent=2))

    def get_next(self):
        queue = self.load()
        pending = [t for t in queue if t.get("status") == "queued"]
        if not pending:
            return None
        pending.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return pending[0]

    def update_status(self, task_id, status, progress=None):
        queue = self.load()
        for t in queue:
            if t.get("id") == task_id:
                t["status"] = status
                if progress is not None:
                    t["progress"] = progress
                break
        self.save(queue)


class AutonomousAgent:
    def __init__(self):
        self.evolution = EvolutionLog()
        self.queue = TaskQueue()

    def api(self, method, endpoint, data=None):
        url = f"{API_BASE}/{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {API_TOKEN}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"success": False, "error": f"HTTP {e.code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def decompose_goal(self, goal):
        gl = goal.lower()
        if any(w in gl for w in ["analiz et", "ara", "research", "investigate"]):
            return [f"research {goal.replace('analiz et','').replace('ara','').replace('research','').strip()}"]
        if ", " in goal or " ve " in gl:
            parts = goal.replace(" ve ", ", ").split(", ")
            return [p.strip() for p in parts if p.strip()][:5]
        return [goal]

    def run_task(self, task):
        """Submit task via API and poll for result."""
        result = self.api("POST", "run", {"task": task})
        if not result.get("success"):
            return {"exit_code": 1, "stdout": [], "stderr": [result.get("error", "Unknown")]}

        run_id = result.get("id", "")
        for _ in range(30):  # 60s max polling
            time.sleep(2)
            sresult = self.api("GET", f"run?id={run_id}")
            if sresult.get("success"):
                status = sresult.get("status", "")
                if status in ("done", "error"):
                    logs = sresult.get("logs", [])
                    exit_code = sresult.get("result", {}).get("exit_code", 0) if status == "done" else 1
                    return {"exit_code": exit_code, "stdout": logs if isinstance(logs, list) else [str(logs)], "stderr": []}
        return {"exit_code": 124, "stdout": [], "stderr": ["Polling timeout"]}

    def evaluate(self, result):
        if result.get("exit_code") == 0:
            stdout = "\n".join(result.get("stdout", []))
            # Only flag actual errors, not warnings
            error_words = ["hata:", "hatalı", "başarısız", "failed", "error:", "exception:", "traceback"]
            if any(w in stdout.lower() for w in error_words):
                return "partial"
            return "success"
        return "failed"

    def run_goal(self, goal, max_iterations=5):
        task_id = self.queue.add(goal, priority=1)
        self.queue.update_status(task_id, "running")

        strategy = self.evolution.suggest_strategy(goal)
        tasks = self.decompose_goal(goal)
        progress = []

        for i, task in enumerate(tasks):
            if i >= max_iterations:
                break
            result = self.run_task(task)
            evaluation = self.evaluate(result)
            next_strategy = self.evolution.suggest_strategy(goal)
            self.evolution.record(goal, task, result, strategy, next_strategy)
            progress.append({"task": task, "evaluation": evaluation,
                             "exit_code": result.get("exit_code"),
                             "strategy": strategy, "iteration": i + 1})
            strategy = next_strategy
            if evaluation == "failed":
                strategy = self.evolution.suggest_strategy(goal)

        status = "completed" if all(p["evaluation"] == "success" for p in progress) else "partial"
        self.queue.update_status(task_id, status, progress)
        return {"task_id": task_id, "goal": goal, "status": status,
                "progress": progress, "total_tasks": len(tasks),
                "successful": sum(1 for p in progress if p["evaluation"] == "success")}

    def run_loop(self, poll_interval=30):
        print(f"🤖 AgentSpace Autonomous Mode aktif (poll: {poll_interval}s)")
        while True:
            next_task = self.queue.get_next()
            if next_task:
                print(f"\n📋 Görev: {next_task['goal'][:80]}...")
                result = self.run_goal(next_task["goal"])
                print(f"   Sonuç: {result['status']} ({result['successful']}/{result['total_tasks']})")
            else:
                print(f"⏳ Bekleniyor... ({datetime.now().strftime('%H:%M:%S')})")
            time.sleep(poll_interval)


def main():
    if len(sys.argv) < 2:
        print("""🤖 AgentSpace Autonomous Mode

Kullanım:
  python3 autonomous.py goal "Hedef"    # Tek görev
  python3 autonomous.py queue            # Kuyruk listele
  python3 autonomous.py loop [sn]        # Otomatik döngü
  python3 autonomous.py evolve           # Evolisyon logu
        """)
        return

    cmd = sys.argv[1]
    if cmd == "goal" and len(sys.argv) >= 3:
        agent = AutonomousAgent()
        result = agent.run_goal(" ".join(sys.argv[2:]))
        print(json.dumps(result, ensure_ascii=False))
    elif cmd == "queue":
        for t in TaskQueue().load():
            print(f"  [{t['status']}] {t['id']}: {t['goal'][:60]}")
    elif cmd == "loop":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        AutonomousAgent().run_loop(poll_interval=interval)
    elif cmd == "evolve":
        for e in EvolutionLog().get_last_n(10):
            print(f"  {e['timestamp']} | {e['strategy']} -> {e['next_strategy']} | exit={e['exit_code']}")
    else:
        print(f"Bilinmeyen komut: {cmd}")


if __name__ == "__main__":
    main()