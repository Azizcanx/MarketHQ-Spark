#!/usr/bin/env python3
"""
AgentSpace — Real Muratify-like Agent Execution Environment on MarketHQ VPS

Flow: Single task input → Hermes agent runs in real terminal → live log → 
      evidence/diff/test card generation

Features:
- Task execution with Hermes agent
- Live terminal output streaming
- Evidence capture (stdout, stderr, exit code, timestamps)
- Test card generation with output preview
- Diff generation between multiple runs
- Integration with MarketHQ brain orchestrator
- Support for research, analysis, and trading tasks
"""

import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTSPACE_DIR = PROJECT_ROOT / "agentspace"
EVIDENCE_DIR = AGENTSPACE_DIR / "evidence"
TEST_CARD_DIR = AGENTSPACE_DIR / "test-cards"
LOG_DIR = AGENTSPACE_DIR / "logs"

# Ensure research_setup_engine is importable from project root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure directories exist
for d in [EVIDENCE_DIR, TEST_CARD_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class AgentRun:
    """Represents a single AgentSpace run with all captured data."""
    
    def __init__(self, task: str, run_id: Optional[str] = None):
        self.task = task
        self.run_id = run_id or f"agentspace_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.timestamp = datetime.now().isoformat()
        self.exit_code: Optional[int] = None
        self.stdout_lines: List[str] = []
        self.stderr_lines: List[str] = []
        self.evidence_path: Optional[Path] = None
        self.test_card_path: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "exit_code": self.exit_code,
            "stdout": self.stdout_lines,
            "stderr": self.stderr_lines,
            "timestamp": self.timestamp,
        }
    
    def save_evidence(self) -> Path:
        """Save evidence JSON and return path."""
        self.evidence_path = EVIDENCE_DIR / f"evidence_{self.run_id}.json"
        self.evidence_path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return self.evidence_path
    
    def save_test_card(self, diff_data: Optional[Dict] = None) -> Path:
        """Save test card Markdown. Optionally include diff data from previous run."""
        lines = [
            f"# AgentSpace Test Card\n",
            f"**Run ID:** `{self.run_id}`\n",
            f"**Task:** {self.task}\n",
            f"**Timestamp:** {self.timestamp}\n",
            f"**Exit Code:** `{self.exit_code}`\n",
            "\n",
            "## Output Summary\n",
        ]
        
        # Stdout summary
        if self.stdout_lines:
            lines.append(f"**Stdout lines:** {len(self.stdout_lines)}")
            lines.append("\n**Output preview:**")
            # Show last 20 lines
            for line in self.stdout_lines[-20:]:
                lines.append(f"> {line}")
        else:
            lines.append("_No stdout captured_")
        
        # Stderr summary
        if self.stderr_lines:
            lines.append(f"\n**Stderr lines:** {len(self.stderr_lines)}")
            lines.append("\n**Errors:**")
            for line in self.stderr_lines:
                lines.append(f"> {line}")
        
        # Diff section if comparing runs
        if diff_data:
            lines.append("\n")
            lines.append("## Diff from Previous Run\n")
            lines.append(f"**Previous run:** `{diff_data.get('prev_run_id', '?')}`\n")
            lines.append(f"**Previous exit code:** `{diff_data.get('prev_exit_code', '?')}`\n")
            if diff_data.get('stdout_diff'):
                lines.append(f"\n**Stdout differences:** `{diff_data['stdout_diff'].get('added', []) and len(diff_data['stdout_diff']['added'])}` lines added, `{diff_data['stdout_diff'].get('removed', []) and len(diff_data['stdout_diff']['removed'])}` lines removed")
                for line in diff_data['stdout_diff'].get('added', [])[:15]:
                    lines.append(f"> {line}")
                for line in diff_data['stdout_diff'].get('removed', [])[:15]:
                    lines.append(f"> {line}")
            if diff_data.get('stderr_diff'):
                lines.append(f"\n**Stderr differences:** `{len(diff_data['stderr_diff'].get('added', []))}` lines added, `{len(diff_data['stderr_diff'].get('removed', []))}` lines removed")
                for line in diff_data['stderr_diff'].get('added', [])[:10]:
                    lines.append(f"> {line}")
                for line in diff_data['stderr_diff'].get('removed', [])[:10]:
                    lines.append(f"> {line}")
        
        lines.extend([
            "\n",
            "## Evidence\n",
            f"- Evidence JSON: `{self.evidence_path}`\n",
            f"- Test Card: `{self.test_card_path}`\n",
        ])
        
        self.test_card_path = TEST_CARD_DIR / f"test-card_{self.run_id}.md"
        self.test_card_path.write_text("\n".join(lines))
        return self.test_card_path


# Persistent session name — shared across all AgentSpace tasks.
# --continue keeps the session alive: system prompt, skills, tools, and memory
# are loaded once and cached. Subsequent tasks resume this session instead of
# starting a fresh process that reloads everything from scratch.
AGENTSPACE_SESSION_NAME = "agentspace"


AGENTSPACE_LOCK_FILE = Path("/tmp/agentspace.lock")


class HermesClient:
    """Client for running Hermes agent tasks with persistent session reuse.

    P0-1 optimization: uses `hermes chat --continue --create-if-missing` so that
    each task resumes the same session instead of spawning a fresh process.
    This avoids reloading system prompt, skills, tool schemas, and memory on
    every call — the primary source of token waste in the original design.
    """

    def __init__(self, timeout: int = 120, cwd: Optional[str] = None):
        self.timeout = timeout
        self.cwd = cwd or str(PROJECT_ROOT)

    def _load_context(self) -> str:
        """Load summary from the most recent evidence file for context continuity."""
        try:
            evidence_files = sorted(EVIDENCE_DIR.glob("evidence_agentspace_*.json"))
            if not evidence_files:
                return ""
            latest = evidence_files[-1]
            data = json.loads(latest.read_text())
            stdout = data.get("stdout", [])
            if not stdout:
                return ""
            # Extract last assistant response as context summary
            text = " ".join(str(s) for s in stdout[-5:])
            # Truncate to ~500 chars to keep token usage low
            return text[:500]
        except Exception:
            return ""

    @staticmethod
    def _acquire_lock() -> bool:
        """Acquire a file-based PID lock to prevent recursion.

        Returns True if lock acquired (not already running), False if recursion detected.
        """
        try:
            if AGENTSPACE_LOCK_FILE.exists():
                # Check if the previous process is still alive
                try:
                    pid = int(AGENTSPACE_LOCK_FILE.read_text().strip())
                    os.kill(pid, 0)  # signal 0 = check existence
                    # Process still running → recursion
                    return False
                except (ProcessLookupError, ValueError):
                    # Stale lock, remove it
                    AGENTSPACE_LOCK_FILE.unlink()
            # Acquire lock
            AGENTSPACE_LOCK_FILE.write_text(str(os.getpid()))
            return True
        except Exception:
            return True  # If lock fails, don't block execution

    @staticmethod
    def _release_lock():
        """Release the recursion lock."""
        try:
            if AGENTSPACE_LOCK_FILE.exists():
                AGENTSPACE_LOCK_FILE.unlink()
        except Exception:
            pass

    def run(self, task: str) -> subprocess.CompletedProcess:
        """Run Hermes agent with a FRESH session per task + context summary.

        No --continue: each task starts with minimal context,
        keeping token usage low (~5k per task vs ~200k with history).
        Context summary from previous runs is prepended to preserve continuity.
        Previous sessions remain accessible via /api/agentspace/sessions.
        --oneshot ensures a single query-response cycle without interactive mode.
        --no-restore-cwd prevents directory changes from leaking between tasks.
        """
        import os as _os
        hermes_bin = _os.path.expanduser("~/.local/bin")
        _os.environ["PATH"] = hermes_bin + ":" + _os.environ.get("PATH", "")
        _os.environ["HOME"] = _os.path.expanduser("~")
        _os.environ["USER"] = "markethq"

        # Recursion guard — file-based PID lock prevents agent_space → hermes → agent_space loops
        if not self._acquire_lock():
            return subprocess.CompletedProcess(["hermes", "chat"], 0, "Recursion guard: skip.", "")

        try:
            # Context summary — prepend previous run summary to preserve continuity
            _context = self._load_context()
            _full_task = f"[Context: {_context}] {task}" if _context else task

            # Fresh session per task — no --continue, minimal context
            # Use hermes-agent venv Python directly with the hermes CLI.
            # Running as executable (not via python3) ensures the shebang
            # interpreter is used, avoiding SSL/TLS issues from mismatched venvs.
            _hermes = "/opt/markethq/hermes-agent/venv/bin/python"
            _hermes_cli = "/opt/markethq/hermes-agent/hermes"
            cmd = [_hermes, _hermes_cli, "chat", "--create-if-missing", "--oneshot", "--no-restore-cwd", "-q", _full_task]
            try:
                _env = {**os.environ}
                _env["HOME"] = _os.path.expanduser("~")
                _env["USER"] = "markethq"
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=_env,
                )
                try:
                    stdout, stderr = proc.communicate(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(cmd, -1, "", "timeout")
        finally:
            self._release_lock()


def generate_run_diff(current_run: AgentRun, 
                      previous_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Generate diff data comparing current run to a previous run.
    
    Looks for the most recent previous run in the evidence directory.
    """
    # Find previous runs
    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_agentspace_*.json"))
    
    if len(evidence_files) < 2:
        return None
    
    # Determine which previous run to compare against
    if previous_run_id is None:
        # Use the second-most recent run
        prev_path = evidence_files[-2]  # second most recent
    else:
        prev_path = EVIDENCE_DIR / f"evidence_{previous_run_id}.json"
        if not prev_path.exists():
            return None
    
    try:
        with open(prev_path, 'r') as f:
            prev_data = json.load(f)
    except Exception:
        return None
    
    current_data = current_run.to_dict()
    
    diff = {
        "prev_run_id": prev_data.get("run_id", previous_run_id or "unknown"),
        "prev_exit_code": prev_data.get("exit_code", "?"),
        "current_run_id": current_data.get("run_id", current_run.run_id),
        "current_exit_code": current_data.get("exit_code", "?"),
    }
    
    # Compute stdout diff
    prev_stdout = prev_data.get("stdout", [])
    curr_stdout = current_data.get("stdout", [])
    
    if prev_stdout != curr_stdout:
        prev_set = set(prev_stdout)
        curr_set = set(curr_stdout)
        added = [l for l in curr_stdout if l not in prev_set]
        removed = [l for l in prev_stdout if l not in curr_set]
        common = [l for l in curr_stdout if l in prev_set]
        
        diff["stdout_diff"] = {
            "added": added[:15],
            "removed": removed[:15],
            "common_count": len(common),
        }
    else:
        diff["stdout_diff"] = None
    
    # Compute stderr diff
    prev_stderr = prev_data.get("stderr", [])
    curr_stderr = current_data.get("stderr", [])
    
    if prev_stderr != curr_stderr:
        prev_set = set(prev_stderr)
        curr_set = set(curr_stderr)
        added = [l for l in curr_stderr if l not in prev_set]
        removed = [l for l in prev_stderr if l not in curr_set]
        diff["stderr_diff"] = {
            "added": added[:10],
            "removed": removed[:10],
        }
    else:
        diff["stderr_diff"] = None
    
    return diff


def compare_runs(run_id_1: str, run_id_2: str) -> Dict[str, Any]:
    """
    Compare two specific runs and return detailed diff.
    """
    path1 = EVIDENCE_DIR / f"evidence_{run_id_1}.json"
    path2 = EVIDENCE_DIR / f"evidence_{run_id_2}.json"
    
    if not path1.exists() or not path2.exists():
        return {"error": "One or both run evidence files not found"}
    
    with open(path1) as f:
        data1 = json.load(f)
    with open(path2) as f:
        data2 = json.load(f)
    
    return {
        "run_1": {"run_id": data1.get("run_id"), "task": data1.get("task"), "exit_code": data1.get("exit_code")},
        "run_2": {"run_id": data2.get("run_id"), "task": data2.get("task"), "exit_code": data2.get("exit_code")},
        "stdout_comparison": {
            "run_1_lines": len(data1.get("stdout", [])),
            "run_2_lines": len(data2.get("stdout", [])),
            "identical": data1.get("stdout", []) == data2.get("stdout", []),
        },
        "stderr_comparison": {
            "run_1_lines": len(data1.get("stderr", [])),
            "run_2_lines": len(data2.get("stderr", [])),
            "identical": data1.get("stderr", []) == data2.get("stderr", []),
        },
    }


def run_agent_space_task(task: str, timeout: int = 120, 
                         generate_diff: bool = True) -> AgentRun:
    """
    Execute a task through the AgentSpace flow.
    
    Args:
        task: The task string to give to Hermes
        timeout: Maximum seconds to wait for Hermes response
        generate_diff: Whether to generate diff data comparing to previous run
    
    Returns:
        AgentRun object with all captured data
    """
    run = AgentRun(task)
    
    print(f"🛰 AgentSpace başlatılıyor...")
    print(f"📝 Görevi: {task}")
    print(f"⏱️ Timeout: {timeout}s")
    print("-" * 60)
    
    # Run via Hermes
    client = HermesClient(timeout=timeout)
    result = client.run(task)
    
    run.exit_code = result.returncode
    run.stdout_lines = result.stdout.split("\n") if result.stdout else []
    run.stderr_lines = result.stderr.split("\n") if result.stderr else []
    run.timestamp = datetime.now().isoformat()
    
    # Live output to terminal (what was captured)
    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""
    
    for line in stdout_text.split("\n"):
        print(line)
    for line in stderr_text.split("\n"):
        print(f"STDERR: {line}", file=sys.stderr)
    
    # Save evidence
    evidence_path = run.save_evidence()
    print(f"\n📋 Evidence kaydedildi: {evidence_path}")
    
    # Generate diff if enabled
    diff_data = None
    if generate_diff:
        diff_data = generate_run_diff(run)
    
    # Save test card (with diff if available)
    test_card_path = run.save_test_card(diff_data=diff_data)
    print(f"📄 Test kartı: {test_card_path}")
    
    print("-" * 60)
    print(f"✅ AgentSpace tamamlandı (exit code: {run.exit_code})")
    
    return run


def main():
    """Main entry point for AgentSpace."""
    if len(sys.argv) < 2:
        print("""\
🛰 AgentSpace — Muratify-like Agent Execution Environment

Usage:
    python3 agentspace/agent_space.py "your task here"

Examples:
    python3 agentspace/agent_space.py "Research GRPO papers and write summary"
    python3 agentspace/agent_space.py "Check MarketHQ system status"
    python3 agentspace/agent_space.py "Hello world"

The AgentSpace flow:
1. Takes a single task string from CLI arguments
2. Spawns Hermes agent to execute it
3. Captures live output to terminal
4. Saves evidence JSON with full run details
5. Generates markdown test card with output preview
6. Optionally diffs against previous run

Options:
    --compare RUN_ID_1 RUN_ID_2   Compare two existing runs
    --timeout SECONDS             Set Hermes timeout (default: 120)
    --no-diff                       Skip diff generation against previous run

Run 'python3 agentspace/agent_space.py' without arguments for this help.
""")
        sys.exit(1)
    
    # Handle --compare mode
    if sys.argv[1] == "--compare":
        if len(sys.argv) != 4:
            print("Usage: python3 agentspace/agent_space.py --compare RUN_ID_1 RUN_ID_2")
            sys.exit(1)
        run_id_1 = sys.argv[2]
        run_id_2 = sys.argv[3]
        result = compare_runs(run_id_1, run_id_2)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Handle research subcommand
    if sys.argv[1] == "research":
        if len(sys.argv) < 4:
            print("Usage: python3 agentspace/agent_space.py research SYMBOL TIMEFRAME")
            print("Example: python3 agentspace/agent_space.py research THYAO.IS 1h")
            sys.exit(1)
        symbol = sys.argv[2]
        timeframe = sys.argv[3]
        do_backtest = "--backtest" in sys.argv
        print(f"🛰 Research Setup Engine — {symbol} {timeframe}" + (" + backtest" if do_backtest else ""))
        print("-" * 60)

        import yfinance as yf
        import json as _json

        period_map = {"1m": "5d", "5m": "10d", "15m": "20d", "1h": "60d", "4h": "6mo", "1d": "2y"}
        period = period_map.get(timeframe, "60d")
        yf_sym = symbol.replace(".IS", ".IS")
        df = yf.download(yf_sym, period=period, interval=timeframe.replace("m", "m").replace("h", "h").replace("d", "1d"))

        if df is None or df.empty:
            print(f"❌ Veri alınamadı: {symbol} {timeframe}")
            sys.exit(1)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        from research_setup_engine import build_research_setup, format_why_panel, _verdict as _verdict_engine

        result = build_research_setup(df, symbol=symbol, timeframe=timeframe)
        model = result["model"]
        quality = model.quality

        print(f"\n📊 SETUP: {model.bias.direction} | Entry: {model.entry_zone.center:.4f}")
        print(f"   Type: {model.setup_type} | Regime: {model.regime.regime}")
        print(f"   Quality: {quality.overall:.0%} — {_verdict_engine(quality.overall)}")
        print(f"   R:R: {model.risk_reward.reward_risk_ratio}:1")
        print(f"   Structure: {model.structure.structure_type} | Liquidity: {model.liquidity.liquidity_side}")
        print(f"   Breakdown:")
        for dim, score in quality.breakdown.items():
            print(f"     {dim}: {score:.0%}")

        print(f"\n{format_why_panel(result)}")

        # Save evidence (model included)
        evidence_file = EVIDENCE_DIR / f"research_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        evidence_file.write_text(_json.dumps(result, indent=2, ensure_ascii=False, default=str))
        print(f"\n📋 Evidence: {evidence_file}")

        # Save test card
        tc_lines = [
            f"# Research Setup — {symbol} {timeframe}",
            f"**Direction:** {model.bias.direction} | **Quality:** {quality.overall:.0%} ({_verdict_engine(quality.overall)})",
            f"**Type:** {model.setup_type} | **Regime:** {model.regime.regime}",
            f"**Entry:** {model.entry_zone.center:.4f} | **Zone:** [{model.entry_zone.low:.4f}, {model.entry_zone.high:.4f}]",
            f"**Invalidation:** {model.invalidation.price} | **Target:** {model.targets.primary.price if model.targets.primary else '?'}",
            f"**Reward:Risk:** {model.risk_reward.reward_risk_ratio}:1",
            f"**Structure:** {model.structure.structure_type} | **Liquidity:** {model.liquidity.liquidity_side}",
            "",
            "### Quality Breakdown",
        ]
        for dim, score in quality.breakdown.items():
            tc_lines.append(f"- {dim}: {score:.0%}")

        tc_lines.extend([
            "",
            format_why_panel(result),
            "",
            "### Flags",
        ])
        for flag in quality.flags:
            tc_lines.append(f"- {flag}")

        tc_lines.append("")
        tc_lines.append("🛡️ RESEARCH ONLY — no live orders")

        tc_path = TEST_CARD_DIR / f"research_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        tc_path.write_text("\n".join(tc_lines))
        print(f"📄 Test card: {tc_path}")

        # Adaptive brain: record outcome + analyze
        try:
            from setup_outcome_tracker import record_outcome
            from setup_adaptive_brain import analyze_setup_performance, update_brain_research_queue
            from strategy_evolution import analyze_strategy_evolution, update_brain_with_evolution

            # Record this setup as "open" (no execution yet)
            sig = record_outcome(
                setup_type=model.setup_type,
                regime=model.regime.regime,
                direction=model.bias.direction,
                symbol=symbol,
                timeframe=timeframe,
                entry_price=model.entry_zone.center,
                invalidation_price=model.invalidation.price,
                target_price=model.targets.primary.price if model.targets.primary else None,
                quality_score=quality.overall,
                outcome="open",
                metadata={
                    "setup_id": model.setup_id,
                    "engine": model.engine,
                    "version": model.version,
                },
            )
            print(f"🧠 Outcome recorded: {sig}")

            # Analyze and update brain queue
            recs = analyze_setup_performance(symbol=symbol)
            if recs:
                top = recs[0]
                print(f"📊 Top learning: {top['setup_type']} + {top['regime']} + {top['direction']} → {top['action']} ({top['priority_score']:.0%})")
                print(f"   Soru: {top['next_research_question']}")

            brain_update = update_brain_research_queue(symbol=symbol, recommendations=recs)
            print(f"🔄 Brain queue: {brain_update['updated_count']} guncellendi")

            # Strategy evolution
            evolution = analyze_strategy_evolution(symbol=symbol)
            evo_summary = evolution.get("strategy_evolution", {})
            if evo_summary.get("keep_strategies") or evo_summary.get("remove_strategies"):
                print(f"\n📈 Strategy Evolution:")
                for k in evo_summary:
                    items = evo_summary[k]
                    if items:
                        print(f"  {k}: {len(items)}")
                        for item in items[:3]:
                            print(f"    - {item}")

            evo_update = update_brain_with_evolution(symbol=symbol, analysis=evolution)
            print(f"🔄 Evolution brain queue: {evo_update['questions_added']} soru eklendi")

        except Exception as e:
            print(f"🧠 Adaptive brain: {e}")

        # --- Backtest integration ---
        backtest_result = None
        if do_backtest:
            print("\n" + "=" * 60)
            print("📊 Phase G Backtest başlatılıyor...")
            print("=" * 60)
            try:
                from research_validation_pipeline import run_historical_backtest
                backtest_result = run_historical_backtest(
                    symbol=symbol,
                    timeframe=timeframe,
                )
                # Merge into evidence JSON
                evidence_data = json.loads(evidence_file.read_text())
                evidence_data["backtest"] = backtest_result
                evidence_file.write_text(json.dumps(evidence_data, indent=2, ensure_ascii=False, default=str))
                print(f"📋 Evidence (güncellendi): {evidence_file}")

                # Append backtest summary to test card
                tc_content = tc_path.read_text()
                metrics = backtest_result.get("metrics", {})
                wf = backtest_result.get("walk_forward", {})
                tc_lines.append("")
                tc_lines.append("### Backtest Sonuçları")
                tc_lines.append(f"- Setup: {backtest_result.get('setups_generated', 0)}")
                tc_lines.append(f"- Outcome: {len(backtest_result.get('outcomes', []))}")
                tc_lines.append(f"- T1 hit rate: {metrics.get('target_1_hit_rate', 'N/A')}")
                tc_lines.append(f"- T2 hit rate: {metrics.get('target_2_hit_rate', 'N/A')}")
                tc_lines.append(f"- T3 hit rate: {metrics.get('target_3_hit_rate', 'N/A')}")
                tc_lines.append(f"- Entry rate: {metrics.get('entry_rate', 'N/A')}")
                tc_lines.append(f"- Realized R: {metrics.get('realized_r_mean', 'N/A')}")
                tc_lines.append(f"- Walk-forward windows: {wf.get('windows', 0)}")
                tc_lines.append(f"- Claims validated: {len(backtest_result.get('claims', []))}")
                tc_lines.append(f"- Lookahead audit: {backtest_result.get('lookahead_audit', {}).get('lookahead_status', 'N/A')}")
                tc_content += "\n".join(tc_lines)
                tc_path.write_text(tc_content)
                print(f"📄 Test card (güncellendi): {tc_path}")
            except Exception as bt_e:
                print(f"❌ Backtest hatası: {bt_e}")

        sys.exit(0)
    
    # Parse flags: --timeout=N, --timeout N, --no-diff (any position)
    timeout = 120
    generate_diff = True
    filtered_args = []
    i = 0
    args = sys.argv[1:]
    while i < len(args):
        a = args[i]
        if a.startswith("--timeout="):
            try:
                timeout = int(a.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
            i += 1
        elif a == "--timeout":
            if i + 1 < len(args):
                try:
                    timeout = int(args[i + 1])
                except (ValueError, IndexError):
                    pass
                i += 2
            else:
                i += 1
        elif a == "--no-diff":
            generate_diff = False
            i += 1
        else:
            filtered_args.append(a)
            i += 1

    task = " ".join(filtered_args)
    
    # Execute
    run = run_agent_space_task(task=task, timeout=timeout, generate_diff=generate_diff)
    
    # Summary
    print(f"\n📊 AgentSpace Özeti:")
    print(f"  Run ID: {run.run_id}")
    print(f"  Görevi: {run.task}")
    print(f"  Çıktı kodu: {run.exit_code}")
    print(f"  Stdout satırları: {len(run.stdout_lines)}")
    print(f"  Stderr satırları: {len(run.stderr_lines)}")
    print(f"  Evidence: {run.evidence_path}")
    print(f"  Test kartı: {run.test_card_path}")


if __name__ == "__main__":
    main()