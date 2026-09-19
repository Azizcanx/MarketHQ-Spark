# -*- coding: utf-8 -*-
"""Persistence Layer — safe migration + agent run/result storage.

New tables (created by migrate()):
- agent_runs: execution lifecycle records
- agent_results: serialized AgentResult payloads
- evidence_items: structured evidence from agents
- agent_claims: structured claims for Brain validation
- feature_snapshots: cached feature data

Migration is SAFE + IDEMPOTENT — existing data preserved.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from agent_contract import AgentResult, Claim, Evidence, MarketContext

DB_PATH = "/opt/markethq/market_hq.db"


class PersistenceLayer:
    """Database persistence for Agent Runtime."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Migration ───────────────────────────────────────────────

    def migrate(self) -> dict[str, Any]:
        """Create new tables if they don't exist. Idempotent + safe."""
        conn = self._conn()
        cursor = conn.cursor()
        created = []

        # agent_runs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                execution_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                agent_version TEXT DEFAULT '1.0.0',
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                observation_timestamp TEXT,
                data_cutoff_timestamp TEXT,
                status TEXT NOT NULL DEFAULT 'CREATED',
                error_type TEXT,
                error_message TEXT,
                result_json TEXT,
                trace_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        created.append("agent_runs")

        # agent_results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                agent_version TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (execution_id) REFERENCES agent_runs(execution_id)
            )
        """)
        created.append("agent_results")

        # evidence_items
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                evidence_type TEXT,
                feature TEXT,
                value TEXT,
                direction TEXT,
                strength REAL,
                source TEXT,
                explanation TEXT,
                observation_timestamp TEXT,
                data_cutoff_timestamp TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (execution_id) REFERENCES agent_runs(execution_id)
            )
        """)
        created.append("evidence_items")

        # agent_claims
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                claim_key TEXT,
                statement TEXT NOT NULL,
                source_agent TEXT,
                source_agent_version TEXT,
                observation_timestamp TEXT,
                data_cutoff_timestamp TEXT,
                evidence_refs TEXT DEFAULT '[]',
                validation_status TEXT DEFAULT 'UNTESTED',
                feature TEXT,
                regime TEXT,
                timeframe TEXT,
                symbol TEXT,
                sample_size INTEGER,
                confidence REAL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (execution_id) REFERENCES agent_runs(execution_id)
            )
        """)
        created.append("agent_claims")

        # feature_snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                observation_timestamp TEXT,
                data_cutoff_timestamp TEXT NOT NULL,
                feature_values_json TEXT DEFAULT '{}',
                availability_json TEXT DEFAULT '{}',
                data_quality_score REAL DEFAULT 0.0,
                null_features_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(symbol, timeframe, data_cutoff_timestamp)
            )
        """)
        created.append("feature_snapshots")

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_id
            ON agent_runs(agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_symbol
            ON agent_runs(symbol)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_status
            ON agent_runs(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_cutoff
            ON agent_runs(data_cutoff_timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_evidence_exec
            ON evidence_items(execution_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_claims_exec
            ON agent_claims(execution_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feature_snap_key
            ON feature_snapshots(symbol, timeframe, data_cutoff_timestamp)
        """)

        # Record migration
        cursor.execute(
            "INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))",
            ("agent_runtime_v2",),
        )

        conn.commit()
        conn.close()

        return {"tables_created": created, "status": "ok"}

    # ─── Agent Runs ──────────────────────────────────────────────

    def persist_run(self, run: Any) -> None:
        """Persist an AgentRun to the database."""
        conn = self._conn()
        cursor = conn.cursor()

        # Handle both objects and dicts
        if isinstance(run, dict):
            def get(k, default=None):
                return run.get(k, default)
            execution_id = get("execution_id", "")
            agent_id = get("agent_id", "")
            agent_version = get("agent_version", "")
            symbol = get("symbol", "")
            timeframe = get("timeframe", "")
            started_at = get("started_at", "")
            completed_at = get("completed_at", "")
            observation_timestamp = get("observation_timestamp", "")
            data_cutoff_timestamp = get("data_cutoff_timestamp", "")
            status = get("status", "")
            error_type = get("error_type", "")
            error_message = get("error_message", "")
            result_json = json.dumps(get("result")) if get("result") else None
            trace_json = json.dumps(get("trace", []))
        else:
            execution_id = run.execution_id
            agent_id = run.agent_id
            agent_version = run.agent_version
            symbol = run.symbol
            timeframe = run.timeframe
            started_at = run.started_at
            completed_at = run.completed_at
            observation_timestamp = run.observation_timestamp
            data_cutoff_timestamp = run.data_cutoff_timestamp
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            error_type = run.error_type
            error_message = run.error_message
            result_json = json.dumps(run.result.to_dict()) if run.result else None
            trace_json = json.dumps(run.trace)
        cursor.execute(
            """INSERT OR REPLACE INTO agent_runs
            (execution_id, agent_id, agent_version, symbol, timeframe,
             started_at, completed_at, observation_timestamp,
             data_cutoff_timestamp, status, error_type, error_message,
             result_json, trace_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id, agent_id, agent_version, symbol, timeframe,
                started_at, completed_at, observation_timestamp,
                data_cutoff_timestamp, status, error_type, error_message,
                result_json, trace_json,
            ),
        )
        conn.commit()
        conn.close()

    def get_run(self, execution_id: str) -> dict[str, Any] | None:
        """Retrieve a run by execution_id."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM agent_runs WHERE execution_id = ?", (execution_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def list_runs(
        self,
        agent_id: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List runs with optional filters."""
        conn = self._conn()
        cursor = conn.cursor()
        query = "SELECT * FROM agent_runs WHERE 1=1"
        params: list[Any] = []
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ─── Agent Results ────────────────────────────────────────────

    def persist_result(self, execution_id: str, result: AgentResult) -> None:
        """Persist an AgentResult."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO agent_results (execution_id, agent_id, agent_version, result_json)
            VALUES (?, ?, ?, ?)""",
            (
                execution_id,
                result.agent_id,
                result.agent_version,
                json.dumps(result.to_dict()),
            ),
        )
        conn.commit()
        conn.close()

    def get_result(self, execution_id: str) -> dict[str, Any] | None:
        """Get result for an execution."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM agent_results WHERE execution_id = ? ORDER BY id DESC LIMIT 1",
            (execution_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    # ─── Evidence ─────────────────────────────────────────────────

    def persist_evidence(
        self, execution_id: str, evidence: Evidence
    ) -> None:
        """Persist evidence items."""
        conn = self._conn()
        cursor = conn.cursor()
        for item in evidence.items:
            cursor.execute(
                """INSERT INTO evidence_items
                (execution_id, evidence_type, feature, value, direction,
                 strength, source, explanation, observation_timestamp,
                 data_cutoff_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    item.type,
                    item.feature,
                    json.dumps(item.value) if item.value is not None else None,
                    item.direction,
                    item.strength,
                    item.source,
                    item.explanation,
                    item.timestamp,
                    item.data_cutoff_timestamp,
                ),
            )
        conn.commit()
        conn.close()

    def get_evidence(self, execution_id: str) -> list[dict[str, Any]]:
        """Get evidence items for an execution."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence_items WHERE execution_id = ? ORDER BY id",
            (execution_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ─── Claims ───────────────────────────────────────────────────

    def persist_claims(
        self, execution_id: str, claims: list[Claim]
    ) -> None:
        """Persist claims."""
        conn = self._conn()
        cursor = conn.cursor()
        for claim in claims:
            cursor.execute(
                """INSERT INTO agent_claims
                (execution_id, claim_key, statement, source_agent,
                 source_agent_version, observation_timestamp,
                 data_cutoff_timestamp, evidence_refs, validation_status,
                 feature, regime, timeframe, symbol, sample_size, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    claim.claim_id,
                    claim.statement,
                    claim.source_agent,
                    claim.source_agent_version,
                    claim.observation_timestamp,
                    claim.data_cutoff_timestamp,
                    json.dumps(claim.evidence_refs),
                    claim.validation_status.value,
                    claim.feature,
                    claim.regime,
                    claim.timeframe,
                    claim.symbol,
                    claim.sample_size,
                    claim.confidence,
                ),
            )
        conn.commit()
        conn.close()

    def get_claims(
        self, execution_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get claims, optionally filtered by execution."""
        conn = self._conn()
        cursor = conn.cursor()
        if execution_id:
            cursor.execute(
                "SELECT * FROM agent_claims WHERE execution_id = ? ORDER BY id",
                (execution_id,),
            )
        else:
            cursor.execute("SELECT * FROM agent_claims ORDER BY id")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ─── Feature Snapshots ────────────────────────────────────────

    def persist_feature_snapshot(
        self, ctx: MarketContext
    ) -> None:
        """Persist a feature snapshot."""
        fs = ctx.feature_snapshot
        conn = self._conn()
        cursor = conn.cursor()
        # Serialize feature values from FeatureSnapshot
        feature_values = {}
        for attr in dir(fs):
            if attr.startswith("_"):
                continue
            val = getattr(fs, attr)
            if not callable(val) and not isinstance(val, (dataclass, type(None), str, int, float, bool, list, dict)):
                feature_values[attr] = str(val)
            elif not callable(val) and not isinstance(val, (type(None), str, int, float, bool, list, dict)):
                feature_values[attr] = repr(val)

        cursor.execute(
            """INSERT OR REPLACE INTO feature_snapshots
            (symbol, timeframe, observation_timestamp, data_cutoff_timestamp,
             feature_values_json, availability_json, data_quality_score,
             null_features_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ctx.symbol,
                ctx.timeframe,
                ctx.observation_timestamp,
                ctx.data_cutoff_timestamp,
                json.dumps(feature_values),
                json.dumps(fs.available_features),
                fs.data_quality_score,
                json.dumps(fs.null_features),
            ),
        )
        conn.commit()
        conn.close()

    def get_feature_snapshot(
        self, symbol: str, timeframe: str, cutoff: str
    ) -> dict[str, Any] | None:
        """Get a feature snapshot from DB."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM feature_snapshots
            WHERE symbol = ? AND timeframe = ? AND data_cutoff_timestamp = ?""",
            (symbol, timeframe, cutoff),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    # ─── Stats ────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Get persistence statistics."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        run_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM agent_results")
        result_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM evidence_items")
        evidence_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM agent_claims")
        claim_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM feature_snapshots")
        snapshot_count = cursor.fetchone()[0]
        conn.close()
        return {
            "agent_runs": run_count,
            "agent_results": result_count,
            "evidence_items": evidence_count,
            "claims": claim_count,
            "feature_snapshots": snapshot_count,
        }