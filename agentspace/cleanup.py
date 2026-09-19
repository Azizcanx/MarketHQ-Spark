#!/usr/bin/env python3
"""Evidence retention cleanup — removes evidence/test-card files older than retention days."""

import json
import time
from pathlib import Path

AGENTSPACE = Path("/opt/markethq/agentspace")
EVIDENCE_DIR = AGENTSPACE / "evidence"
TEST_CARD_DIR = AGENTSPACE / "test-cards"
LOGS_DIR = AGENTSPACE / "logs"
RETENTION_DAYS = 7
DRY_RUN = True  # set False to actually delete


def cleanup_dir(directory: Path, prefixes: list):
    """Returns (removed, kept). Matches files starting with any prefix."""
    now = time.time()
    cutoff = now - (RETENTION_DAYS * 86400)
    removed = 0
    kept = 0
    for f in sorted(directory.iterdir()):
        if not f.is_file():
            continue
        if not any(f.name.startswith(p) for p in prefixes):
            continue
        if f.stat().st_mtime < cutoff:
            size = f.stat().st_size
            if not DRY_RUN:
                f.unlink()
            removed += 1
            print(f"{'[DRY]' if DRY_RUN else '[DEL]'} {f.name} ({size}b, {time.strftime('%Y-%m-%d', time.localtime(f.stat().st_mtime))})")
        else:
            kept += 1
    return removed, kept


def _parse_date(s: str) -> float:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    return 0.0

def cleanup_queue() -> int:
    """Remove queue entries older than retention days. Returns count removed."""
    queue_file = LOGS_DIR / "agentspace_queue.json"
    if not queue_file.exists():
        return 0
    try:
        q = json.loads(queue_file.read_text())
    except Exception:
        return 0
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    old_len = len(q)
    q = [e for e in q if _parse_date(e.get("createdAt", "1970-01-01")) > cutoff]
    new_len = len(q)
    if not DRY_RUN and new_len < old_len:
        queue_file.write_text(json.dumps(q, indent=2))
    return old_len - new_len


def cleanup_sessions() -> int:
    """Prune old hermes sessions via hermes sessions prune. Returns count."""
    import subprocess
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "/opt/markethq/hermes-run", "sessions", "prune", "--older-than", "7d"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "HERMES_HOME": "/opt/markethq/hermes-agent"},
        )
        if result.returncode == 0:
            print(f"[SESSION] prune output: {result.stdout.strip()[:200]}")
            return 1
        print(f"[SESSION] prune failed: {result.stderr.strip()[:200]}")
        return 0
    except Exception as e:
        print(f"[SESSION] prune error: {e}")
        return 0


def main():
    print(f"Evidence cleanup — retention: {RETENTION_DAYS} days, dry_run: {DRY_RUN}")
    print("=" * 50)

    e_removed, e_kept = cleanup_dir(EVIDENCE_DIR, ["evidence_", "research_", "adaptive_brain_"])
    t_removed, t_kept = cleanup_dir(TEST_CARD_DIR, ["test-card_", "research_"])
    q_removed = cleanup_queue()
    s_removed = cleanup_sessions()

    print("=" * 50)
    print(f"Evidence: removed={e_removed} kept={e_kept}")
    print(f"Test cards: removed={t_removed} kept={t_kept}")
    print(f"Queue entries: removed={q_removed}")
    print(f"Sessions pruned: {s_removed}")
    total = e_removed + t_removed + q_removed + s_removed
    print(f"Total: {total} items {'would be deleted' if DRY_RUN else 'deleted'}")


if __name__ == "__main__":
    main()