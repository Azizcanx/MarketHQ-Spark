"""Postgres Repository Adapter — J15.

DB-agnostic repository pattern.
SQLite and PostgreSQL share the same business logic.
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgresql://")


class _PgTransaction:
    def __init__(self, repo: "PostgresRepository"):
        self.repo = repo
        self.conn = repo._get_conn()

    def execute(self, sql: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.commit()


class PostgresRepository:
    """Postgres-backed repository for AzizBusiness.

    Uses same schema as SQLite.
    Business logic is DB-agnostic.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or DATABASE_URL
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            import psycopg2
            self._conn = psycopg2.connect(self._database_url)
            self._conn.autocommit = False
        return self._conn

    def check_connection(self) -> dict[str, Any]:
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.execute("SELECT current_database()")
            db = cur.fetchone()[0]
            cur.execute("SELECT version()")
            version = cur.fetchone()[0][:80]
            return {"connected": True, "database": db, "version": version, "type": "postgres"}
        except Exception as e:
            return {"connected": False, "error": str(e), "type": "postgres"}

    def migrate(self) -> dict[str, Any]:
        """Idempotent migration — creates tables if not exists."""
        conn = self._get_conn()
        cur = conn.cursor()

        tables_created = []

        # agent_runs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                execution_id VARCHAR(100) PRIMARY KEY,
                agent_id VARCHAR(100),
                agent_version VARCHAR(50),
                symbol VARCHAR(50),
                timeframe VARCHAR(20),
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                observation_timestamp TIMESTAMP,
                data_cutoff_timestamp TIMESTAMP,
                status VARCHAR(50),
                error_type VARCHAR(50),
                error_message TEXT,
                result_json TEXT,
                trace_json TEXT
            )
        """)
        tables_created.append("agent_runs")

        # tasks
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(200),
                description TEXT,
                created_by VARCHAR(100),
                owner VARCHAR(100),
                assigned_agent VARCHAR(100),
                assigned_team VARCHAR(100),
                priority VARCHAR(20),
                status VARCHAR(30),
                task_type VARCHAR(30),
                symbol VARCHAR(50),
                timeframe VARCHAR(20),
                input_data JSONB,
                requirements JSONB,
                expected_output TEXT,
                dependencies JSONB,
                parent_task_id VARCHAR(100),
                child_task_ids JSONB,
                deadline TIMESTAMP,
                created_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                retry_count INT DEFAULT 0,
                max_retries INT DEFAULT 3,
                result_json TEXT,
                artifacts JSONB,
                evidence JSONB,
                error TEXT,
                ai_policy VARCHAR(50),
                workspace_id VARCHAR(100),
                audit_id VARCHAR(100),
                execution_id VARCHAR(100),
                attempt_id VARCHAR(100),
                assigned_at TIMESTAMP,
                heartbeats JSONB
            )
        """)
        tables_created.append("tasks")

        # workers
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                agent_id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(100),
                display_name VARCHAR(200),
                description TEXT,
                role VARCHAR(100),
                department VARCHAR(100),
                capabilities JSONB,
                skills JSONB,
                strategy_families JSONB,
                supported_symbols JSONB,
                supported_timeframes JSONB,
                status VARCHAR(30),
                health VARCHAR(20),
                reliability FLOAT,
                workload INT DEFAULT 0,
                max_concurrent_tasks INT DEFAULT 3,
                ai_policy VARCHAR(50),
                workspace_id VARCHAR(100),
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                version INT DEFAULT 1,
                last_heartbeat TIMESTAMP,
                failure_count INT DEFAULT 0
            )
        """)
        tables_created.append("workers")

        # teams
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(100),
                lead_agent VARCHAR(100),
                members JSONB,
                status VARCHAR(30),
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        tables_created.append("teams")

        # delegations
        cur.execute("""
            CREATE TABLE IF NOT EXISTS delegations (
                delegation_id VARCHAR(100) PRIMARY KEY,
                parent_task_id VARCHAR(100),
                child_task_id VARCHAR(100),
                delegating_agent VARCHAR(100),
                target_agent VARCHAR(100),
                reason TEXT,
                requirements JSONB,
                status VARCHAR(30),
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        tables_created.append("delegations")

        # worker_messages
        cur.execute("""
            CREATE TABLE IF NOT EXISTS worker_messages (
                message_id VARCHAR(100) PRIMARY KEY,
                task_id VARCHAR(100),
                agent_id VARCHAR(100),
                message_type VARCHAR(30),
                content TEXT,
                created_at TIMESTAMP
            )
        """)
        tables_created.append("worker_messages")

        # artifacts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id VARCHAR(100) PRIMARY KEY,
                task_id VARCHAR(100),
                agent_id VARCHAR(100),
                artifact_type VARCHAR(50),
                content TEXT,
                created_at TIMESTAMP
            )
        """)
        tables_created.append("artifacts")

        # approvals
        cur.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id VARCHAR(100) PRIMARY KEY,
                task_id VARCHAR(100),
                requested_by VARCHAR(100),
                reason TEXT,
                required_action VARCHAR(50),
                status VARCHAR(30),
                decided_by VARCHAR(100),
                decision TEXT,
                decision_reason TEXT,
                created_at TIMESTAMP,
                decided_at TIMESTAMP
            )
        """)
        tables_created.append("approvals")

        # audit_events
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id SERIAL PRIMARY KEY,
                event_type VARCHAR(50),
                task_id VARCHAR(100),
                execution_id VARCHAR(100),
                worker_id VARCHAR(100),
                details TEXT,
                created_at TIMESTAMP
            )
        """)
        tables_created.append("audit_events")

        # observations
        cur.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                observation_id VARCHAR(100) PRIMARY KEY,
                task_id VARCHAR(100),
                worker_id VARCHAR(100),
                observation_type VARCHAR(50),
                symbol VARCHAR(50),
                data JSONB,
                created_at TIMESTAMP
            )
        """)
        tables_created.append("observations")

        # research_memory
        cur.execute("""
            CREATE TABLE IF NOT EXISTS research_memory (
                memory_id SERIAL PRIMARY KEY,
                observation_id VARCHAR(100),
                symbol VARCHAR(50),
                data JSONB,
                created_at TIMESTAMP
            )
        """)
        tables_created.append("research_memory")

        # indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_symbol ON tasks USING GIN(input_data)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id)
        """)

        conn.commit()

        return {
            "migrated": True,
            "tables_created": tables_created,
            "table_count": len(tables_created),
            "type": "postgres",
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── Tasks ───

    def create_task(self, title: str, task_type: str = "research", symbol: str = "",
                    timeframe: str = "", **kwargs) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        import uuid
        task_id = f"T{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
        input_data = json.dumps({"symbol": symbol, "timeframe": timeframe, **kwargs})
        cur.execute(
            "INSERT INTO tasks (task_id, title, task_type, symbol, timeframe, status, created_at, input_data) "
            "VALUES (%s, %s, %s, %s, %s, 'CREATED', NOW(), %s)",
            (task_id, title, task_type, symbol, timeframe, input_data)
        )
        conn.commit()
        return {"task_id": task_id, "title": title, "task_type": task_type,
                "symbol": symbol, "timeframe": timeframe, "status": "CREATED"}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def list_tasks(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        if status:
            cur.execute("SELECT * FROM tasks WHERE status = %s ORDER BY created_at DESC LIMIT %s", (status, limit))
        else:
            cur.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]

    def update_task(self, task_id: str, **kwargs) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        updates = []
        values = []
        for k, v in kwargs.items():
            col = "result_json" if k == "result" else k
            updates.append(f"{col} = %s")
            values.append(json.dumps(v) if isinstance(v, dict) else v)
        if not updates:
            return None
        values.append(task_id)
        cur.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = %s",
            values
        )
        conn.commit()
        return self.get_task(task_id)

    # ─── Workers ───

    def create_worker(self, agent_id: str, name: str = "", capabilities: list | None = None, **kwargs) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        caps = json.dumps(capabilities if capabilities is not None else [])
        cur.execute(
            "INSERT INTO workers (agent_id, name, capabilities, status, health, created_at) "
            "VALUES (%s, %s, %s, 'AVAILABLE', 'healthy', NOW()) "
            "ON CONFLICT (agent_id) DO UPDATE SET name = %s, capabilities = %s, updated_at = NOW()",
            (agent_id, name, caps, name, caps)
        )
        conn.commit()
        return self.get_worker(agent_id)

    def get_worker(self, agent_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM workers WHERE agent_id = %s", (agent_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def list_workers(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        if status:
            cur.execute("SELECT * FROM workers WHERE status = %s", (status,))
        else:
            cur.execute("SELECT * FROM workers")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]

    # ─── Assignments ───

    def assign_task(self, task_id: str, agent_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET assigned_agent = %s, status = 'ASSIGNED', assigned_at = NOW() WHERE task_id = %s",
            (agent_id, task_id)
        )
        conn.commit()
        return self.get_task(task_id)

    # ─── Observations ───

    def create_observation(self, task_id: str, observation_type: str = "research_update",
                          content: dict | None = None, **kwargs) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        import uuid
        obs_id = f"OBS{uuid.uuid4().hex[:12].upper()}"
        cur.execute(
            "INSERT INTO observations (observation_id, task_id, worker_id, observation_type, symbol, data, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
            (obs_id, task_id, "", observation_type, "", json.dumps(content or {}))
        )
        conn.commit()
        return {"id": obs_id, "task_id": task_id, "type": observation_type}

    # ─── Memory ───

    def create_memory(self, key: str, value: dict | None = None, source: str = "", **kwargs) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        import uuid
        mem_id = f"M{uuid.uuid4().hex[:10].upper()}"
        cur.execute(
            "INSERT INTO research_memory (observation_id, symbol, data, created_at) "
            "VALUES (%s, %s, %s, NOW())",
            (mem_id, key, json.dumps(value or {}))
        )
        conn.commit()
        return {"id": mem_id, "key": key, "source": source}

    def get_observation(self, observation_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM observations WHERE observation_id = %s", (observation_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row)) if row else None

    def get_memory(self, key: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM research_memory WHERE symbol = %s", (key,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row)) if row else None

    # ─── Audit ───

    def create_audit_event(self, event_type: str, task_id: str = "", details: dict | None = None) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_events (event_type, task_id, worker_id, details, created_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (event_type, task_id, "", json.dumps(details or {}))
        )
        conn.commit()
        return {"id": cur.lastrowid, "event_type": event_type, "task_id": task_id}

    def get_audit_events(self, task_id: str = "") -> list[dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        if task_id:
            cur.execute("SELECT * FROM audit_events WHERE task_id = %s ORDER BY created_at", (task_id,))
        else:
            cur.execute("SELECT * FROM audit_events ORDER BY created_at")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]

    # ─── Helpers ───

    def transaction(self):
        return _PgTransaction(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()