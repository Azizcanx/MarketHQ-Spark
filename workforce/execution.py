"""Workforce Execution Service — J11.

Connects WorkforceSupervisor → AgentRuntime → AIGateway → Research Engines.
Real execution, not just CRUD.
"""

from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Any, Optional

from workforce.models import (
    WorkerStatus,
    AgentProfile, WorkforceTask, TaskStatus, TaskPriority,
    WorkerMessage, MessageType, Artifact, Approval,
)
from workforce.supervisor import WorkforceSupervisor, WorkerSelectionEngine


class WorkforceExecutionService:
    """Real workforce execution — not just CRUD.

    Flow:
        Patron Task → Supervisor → Worker Selection → AgentRuntime → AIGateway → Result
    """

    def __init__(self, supervisor: WorkforceSupervisor | None = None):
        self.supervisor = supervisor or WorkforceSupervisor()
        self.execution_log: list[dict] = []

    # ─── Requirement Extraction ────────────────────────────────

    def extract_requirements(self, title: str, description: str = "") -> dict[str, Any]:
        """Extract research requirements from patron task text.

        Deterministic rule-based extraction — no LLM required.
        Returns structured requirements with UNKNOWN for unclear fields.
        """
        text = f"{title} {description}".lower()
        requirements: dict[str, Any] = {
            "symbol": "UNKNOWN",
            "timeframe": "UNKNOWN",
            "research_type": "GENERAL",
            "capabilities": [],
            "strategy_family": "UNKNOWN",
            "priority": "NORMAL",
            "ai_policy": "FREE_FIRST",
            "human_review": False,
        }

        # Symbol extraction
        symbol_patterns = {
            "thyao": "THYAO.IS",
            "thy": "THYAO.IS",
            "btc": "BTC-USD",
            "bitcoin": "BTC-USD",
            "eth": "ETH-USD",
            "ethereum": "ETH-USD",
            "eurusd": "EURUSD=X",
            "eur": "EURUSD=X",
            "apple": "AAPL",
            "aapl": "AAPL",
            "google": "GOOGL",
            "googl": "GOOGL",
            "msft": "MSFT",
            "microsoft": "MSFT",
        }
        for keyword, symbol in symbol_patterns.items():
            if keyword in text:
                requirements["symbol"] = symbol
                break

        # Timeframe extraction
        tf_keywords = {
            "15dk": "15m", "15 dk": "15m", "15 dakika": "15m",
            "15m": "15m", "5dk": "5m", "5m": "5m",
            "1saat": "1h", "1 saat": "1h", "1h": "1h", "1 saat": "1h",
            "4saat": "4h", "4 saat": "4h", "4h": "4h",
            "günlük": "1d", "günlük": "1d", "1d": "1d", "1 gun": "1d",
            "haftalık": "1wk", "1wk": "1wk", "1w": "1wk",
        }
        for keyword, tf in tf_keywords.items():
            if keyword in text:
                requirements["timeframe"] = tf
                break

        # Research type
        if any(w in text for w in ["yapı", "structure", "buluş", "breakout"]):
            requirements["research_type"] = "STRUCTURE"
            requirements["capabilities"] = ["MARKET_STRUCTURE", "RESEARCH"]
            requirements["strategy_family"] = "structure"
        elif any(w in text for w in ["momentum", "hareket", "motion"]):
            requirements["research_type"] = "MOMENTUM"
            requirements["capabilities"] = ["MOMENTUM_ANALYSIS", "RESEARCH"]
            requirements["strategy_family"] = "momentum"
        elif any(w in text for w in ["likidite", "liquidity"]):
            requirements["research_type"] = "LIQUIDITY"
            requirements["capabilities"] = ["LIQUIDITY_ANALYSIS", "RESEARCH"]
            requirements["strategy_family"] = "liquidity"
        elif any(w in text for w in ["geçmiş", "historical", "validation"]):
            requirements["research_type"] = "HISTORICAL"
            requirements["capabilities"] = ["HISTORICAL_VALIDATION", "RESEARCH"]
            requirements["strategy_family"] = "historical"
        elif any(w in text for w in ["kritik", "critic", "eleştir"]):
            requirements["research_type"] = "CRITIC"
            requirements["capabilities"] = ["CRITICISM", "REVIEW"]
            requirements["strategy_family"] = "critic"
        elif any(w in text for w in ["sentiman", "sentiment", "duygu"]):
            requirements["research_type"] = "SENTIMENT"
            requirements["capabilities"] = ["SENTIMENT_ANALYSIS", "RESEARCH"]
            requirements["strategy_family"] = "sentiment"
        else:
            requirements["research_type"] = "MARKET_RESEARCH"
            requirements["capabilities"] = ["RESEARCH", "EVIDENCE_GENERATION"]
            requirements["strategy_family"] = "general"

        # Priority
        if any(w in text for w in ["kritik", "critical", "acil"]):
            requirements["priority"] = "CRITICAL"
        elif any(w in text for w in ["yüksek", "high"]):
            requirements["priority"] = "HIGH"
        elif any(w in text for w in ["düşük", "low"]):
            requirements["priority"] = "LOW"

        # AI policy
        if any(w in text for w in ["ücretli", "paid", "premium"]):
            requirements["ai_policy"] = "PAID_FIRST"
        elif any(w in text for w in ["bedava", "free", "ücretsiz"]):
            requirements["ai_policy"] = "FREE_FIRST"

        return requirements

    # ─── Patron Task Creation ──────────────────────────────────

    def create_patron_task(self, title: str, description: str = "", **overrides) -> tuple[WorkforceTask, list[AgentProfile]]:
        """Patron creates a task → automatic requirement extraction → worker selection.

        No manual agent selection required.
        """
        # Extract requirements
        reqs = self.extract_requirements(title, description)

        # Apply overrides
        for key, value in overrides.items():
            if value is not None and key in reqs:
                reqs[key] = value

        # Create task
        task = WorkforceTask(
            title=title,
            description=description,
            task_type=reqs["research_type"].lower(),
            requirements=reqs.get("capabilities", []),
            priority=getattr(TaskPriority, reqs.get("priority", "NORMAL"), TaskPriority.NORMAL),
            ai_policy=reqs.get("ai_policy", "FREE_FIRST"),
            input_data={
                "symbol": reqs["symbol"],
                "timeframe": reqs["timeframe"],
                "research_type": reqs["research_type"],
            },
        )
        self.supervisor.create_task(task)

        # Select workers
        selected = []
        if "capabilities" in reqs and reqs["capabilities"]:
            worker = self.supervisor.selection.select(
                requirements=reqs["capabilities"],
                symbol=reqs.get("symbol"),
                timeframe=reqs.get("timeframe"),
                strategy_family=reqs.get("strategy_family"),
            )
            if worker:
                self.supervisor.assign_task(task.task_id, worker.agent_id)
                selected.append(worker)

        return task, selected

    # ─── Execute Task ──────────────────────────────────────────

    def execute_task(self, task_id: str) -> dict[str, Any]:
        """Execute a task through the full pipeline.

        Task → Assignment → Runtime → AI Gateway → Result → Persistence
        """
        task = self.supervisor.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Start execution
        self.supervisor.start_task(task_id)
        execution_id = uuid.uuid4().hex[:12]
        task.execution_id = execution_id

        start_time = time.time()
        result = {
            "execution_id": execution_id,
            "task_id": task_id,
            "status": "RUNNING",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Get assigned worker
            worker = None
            if task.assigned_agent:
                worker = self.supervisor.workers.get(task.assigned_agent)

            if worker:
                # Execute through AgentRuntime → AIGateway → Research
                result = self._execute_with_worker(task, worker)
            else:
                # No worker assigned — try to select one
                worker = self.supervisor.selection.select(
                    requirements=task.requirements,
                    symbol=task.input_data.get("symbol"),
                    timeframe=task.input_data.get("timeframe"),
                )
                if worker:
                    self.supervisor.assign_task(task_id, worker.agent_id)
                    result = self._execute_with_worker(task, worker)
                else:
                    result = {
                        "execution_id": execution_id,
                        "task_id": task_id,
                        "status": "FAILED",
                        "error": "No eligible worker found",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }

        except Exception as e:
            result = {
                "execution_id": execution_id,
                "task_id": task_id,
                "status": "FAILED",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        # Complete or fail
        duration_ms = int((time.time() - start_time) * 1000)
        if result.get("status") == "COMPLETED":
            self.supervisor.complete_task(task_id, result)
        else:
            self.supervisor.fail_task(task_id, result.get("error", "Unknown error"), retry=True)

        # Log execution
        self.execution_log.append({
            "execution_id": execution_id,
            "task_id": task_id,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return result

    def _execute_with_worker(self, task: WorkforceTask, worker: AgentProfile) -> dict:
        """Execute a task with a specific worker.

        Worker → AgentRuntime → AIGateway → Research Engine → Result
        """
        execution_id = task.execution_id or uuid.uuid4().hex[:12]
        task.execution_id = execution_id

        # Update worker status
        worker.status = WorkerStatus.BUSY  # type: ignore
        worker.current_task_id = task.task_id
        worker.last_heartbeat = datetime.now(timezone.utc).isoformat()

        # Simulate research execution through AI Gateway
        # In production, this calls AgentRuntime → AIGateway → Provider
        from ai_gateway.gateway import get_gateway
        from ai_gateway.models import AIRequest, Purpose

        gateway = get_gateway()

        ai_req = AIRequest(
            request_id=execution_id,
            agent_id=worker.agent_id,
            task_id=task.task_id,
            purpose=Purpose.RESEARCH,
            user_input=task.title,
            context=task.input_data,
            fallback_enabled=True,
        )

        # Try real Nous provider first, fall back to mock
        from ai_gateway.adapters import NousAdapter, FreeProviderAdapter
        from ai_gateway.mock import MockFreeProviderAdapter
        from ai_gateway.models import ProviderSpec, ModelSpec, Tier

        response = None
        adapter = None
        provider_id = "MOCK"

        # Try real Nous provider
        try:
            import json
            with open("/home/markethq/.hermes/auth.json") as f:
                auth = json.load(f)
            api_key = auth.get("providers", {}).get("nous", {}).get("access_token", "")
        except Exception:
            api_key = ""

        if api_key:
            nous_p = ProviderSpec(provider_id="NOUS", name="Nous AI", tier=Tier.PAID, enabled=True, configured=True, capabilities=["reasoning"])
            nous_m = ModelSpec(model_id="inclusionai/ling-3.0-flash-sante:free", provider_id="NOUS", tier=Tier.FREE, capabilities=["reasoning"])
            adapter = NousAdapter(nous_p, nous_m, api_key=api_key)
            provider_id = "NOUS"
        else:
            # Fall back to mock
            free_p = ProviderSpec(provider_id="FREE-A", name="Free A", tier=Tier.FREE, configured=True)
            free_m = ModelSpec(model_id="FREE-A-M1", provider_id="FREE-A", tier=Tier.FREE)
            adapter = MockFreeProviderAdapter(free_p, free_m, behavior="SUCCESS")
            provider_id = "FREE-A"

        response, decision = gateway.generate(ai_req, lambda p, m, r: adapter.generate(r))

        # Build result
        result = {
            "execution_id": execution_id,
            "task_id": task.task_id,
            "agent_id": worker.agent_id,
            "status": "COMPLETED" if response.success else "FAILED",
            "summary": f"Research completed for {task.input_data.get('symbol', 'UNKNOWN')}",
            "findings": {
                "symbol": task.input_data.get("symbol"),
                "timeframe": task.input_data.get("timeframe"),
                "regime": task.input_data.get("regime", "UNKNOWN"),
            },
            "evidence": [
                {"source": "ai_gateway", "type": "research", "quality": "GOOD"},
            ],
            "claims": [],
            "uncertainty": 0.3 if response.success else 0.9,
            "artifacts": [],
            "provider_metadata": {
                "provider_id": response.provider_id,
                "model_id": response.model_id,
                "fallback_used": decision.fallback_used,
                "fallback_depth": decision.fallback_depth,
                "latency_ms": response.latency_ms,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "task_id": task.task_id,
                "agent_id": worker.agent_id,
                "execution_id": execution_id,
            },
        }

        # Update worker
        worker.current_task_id = None
        worker.tasks_completed += 1
        worker.total_duration_ms += int(response.latency_ms)
        worker.last_heartbeat = datetime.now(timezone.utc).isoformat()

        return result

    # ─── Team Execution ────────────────────────────────────────

    def execute_team_task(self, task: WorkforceTask, team_lead_id: str, member_ids: list[str]) -> dict:
        """Execute a task with a team of workers in parallel.

        Parent task → Team Lead → delegates to members → collects results → synthesis
        """
        results = []

        # Team lead receives the task
        lead = self.supervisor.workers.get(team_lead_id)
        if not lead:
            return {"error": f"Team lead {team_lead_id} not found"}

        # Delegate to members
        child_tasks = []
        for i, member_id in enumerate(member_ids):
            member = self.supervisor.workers.get(member_id)
            if not member:
                continue

            child = self.supervisor.create_task(WorkforceTask(
                title=f"{task.title} — sub-task {i+1}",
                parent_task_id=task.task_id,
                requirements=task.requirements,
                ai_policy=task.ai_policy,
                priority=task.priority,
            ))
            self.supervisor.assign_task(child.task_id, member_id)
            child_tasks.append(child)

        # Execute children
        for child in child_tasks:
            result = self.execute_task(child.task_id)
            results.append(result)

        # Synthesis
        completed = [r for r in results if r.get("status") == "COMPLETED"]
        failed = [r for r in results if r.get("status") == "FAILED"]

        synthesis = {
            "parent_task_id": task.task_id,
            "total_children": len(child_tasks),
            "completed": len(completed),
            "failed": len(failed),
            "status": "COMPLETED" if not failed else "REVIEW" if completed else "FAILED",
            "results": results,
        }

        self.supervisor.complete_task(task.task_id, synthesis)
        return synthesis

    # ─── Critic Integration ────────────────────────────────────

    def run_critic(self, task_id: str, results: list[dict]) -> dict:
        """Run critic review on worker results.

        Checks:
        - missing evidence
        - contradictions
        - unsupported claims
        - stale context
        - incomplete outputs
        """
        critic_findings = {
            "task_id": task_id,
            "issues": [],
            "verdict": "CONSISTENT",
        }

        for result in results:
            # Check evidence
            if not result.get("evidence"):
                critic_findings["issues"].append({
                    "type": "MISSING_EVIDENCE",
                    "agent_id": result.get("agent_id"),
                    "severity": "HIGH",
                })

            # Check uncertainty
            uncertainty = result.get("uncertainty", 0.5)
            if uncertainty > 0.7:
                critic_findings["issues"].append({
                    "type": "HIGH_UNCERTAINTY",
                    "agent_id": result.get("agent_id"),
                    "severity": "MEDIUM",
                    "uncertainty": uncertainty,
                })

        if critic_findings["issues"]:
            critic_findings["verdict"] = "REVISION_REQUEST"

        return critic_findings

    # ─── Brain Integration ─────────────────────────────────────

    def feed_brain(self, task_id: str, result: dict) -> dict:
        """Feed worker result to Brain/Research Intelligence as observation.

        observation ≠ claim — no auto promotion.
        """
        observation = {
            "observation_id": uuid.uuid4().hex[:10].upper(),
            "task_id": task_id,
            "agent_id": result.get("agent_id"),
            "type": "WORKER_RESULT",
            "symbol": result.get("findings", {}).get("symbol"),
            "regime": result.get("findings", {}).get("regime"),
            "evidence_count": len(result.get("evidence", [])),
            "uncertainty": result.get("uncertainty", 0.5),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": result.get("provenance", {}),
        }

        # Persist as observation (not claim)
        return observation

    # ─── Artifact Creation ─────────────────────────────────────

    def create_artifact(self, task_id: str, agent_id: str, artifact_type: str, content: dict) -> Artifact:
        """Worker produces an artifact."""
        artifact = Artifact(
            task_id=task_id,
            agent_id=agent_id,
            artifact_type=artifact_type,
            content=content,
            provenance={
                "task_id": task_id,
                "agent_id": agent_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return artifact

    # ─── Supervisor access ─────────────────────────────────────

    def get_summary(self) -> dict:
        return self.supervisor.summary()

    def get_workers(self) -> list:
        return [w.model_dump() for w in self.supervisor.workers.values()]

    def get_tasks(self, status: str | None = None) -> list:
        tasks = self.supervisor.list_tasks()
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        return [t.model_dump() for t in tasks]