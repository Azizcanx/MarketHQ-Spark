# -*- coding: utf-8 -*-
"""Phase J7 — Repository / Storage Abstraction.

Abstraction over persistence layer supporting:
- SQLite (development)
- Postgres (production)

Idempotent migrations.
Existing data preserved.
"""

from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


class Repository(ABC):
    """Abstract repository for research data."""

    @abstractmethod
    def save_research_run(self, run: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_research_run(self, run_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_research_runs(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_opportunity(self, opp: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_opportunity(self, opp_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_opportunities(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_setup(self, setup: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_setup(self, setup_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_claim(self, claim: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_claim(self, claim_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_claims(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_evidence(self, evidence: dict[str, Any]) -> None: ...

    @abstractmethod
    def save_agent_reliability(self, profile: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_agent_reliability(self, agent_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_intelligence_state(self, state: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_intelligence_state(self) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_drift_event(self, event: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_drift_events(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_research_memory(self, entry: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_research_memory(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_audit_event(self, event: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_audit_events(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_human_review(self, review: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_human_reviews(self, limit: int = 50) -> list[dict[str, Any]]: ...


class SQLiteRepository(Repository):
    """SQLite development repository."""
    """SQLite implementation of Repository."""

    def __init__(self, db_path: str = "/opt/markethq/market_hq.db") -> None:
        self.db_path = db_path
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Create J7 tables if they don't exist. Idempotent."""
        conn = self._conn()
        c = conn.cursor()

        # Research runs (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS research_runs (
                run_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                trigger TEXT DEFAULT 'manual',
                status TEXT NOT NULL DEFAULT 'RUNNING',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                result_json TEXT,
                evidence_count INTEGER DEFAULT 0,
                claim_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Opportunities (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                opportunity_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                thesis TEXT,
                confidence REAL DEFAULT 0.0,
                status TEXT DEFAULT 'DETECTED',
                evidence_refs TEXT DEFAULT '[]',
                regime TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Setups (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS setups (
                setup_id TEXT PRIMARY KEY,
                opportunity_id TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                entry_zone TEXT,
                invalidation TEXT,
                targets TEXT,
                rr REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.0,
                status TEXT DEFAULT 'CANDIDATE',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Claims (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                source TEXT,
                status TEXT DEFAULT 'UNTESTED',
                evidence_refs TEXT DEFAULT '[]',
                sample_size INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                stability REAL DEFAULT 0.0,
                first_observed TEXT,
                last_validated TEXT,
                symbols TEXT DEFAULT '[]',
                timeframes TEXT DEFAULT '[]',
                contradictory_evidence TEXT DEFAULT '[]',
                counterexamples TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Evidence (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT,
                run_id TEXT,
                evidence_type TEXT,
                content TEXT,
                confidence REAL DEFAULT 0.0,
                source TEXT,
                symbol TEXT,
                timeframe TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Agent reliability (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_reliability (
                agent_id TEXT PRIMARY KEY,
                total_executions INTEGER DEFAULT 0,
                successful_executions INTEGER DEFAULT 0,
                failed_executions INTEGER DEFAULT 0,
                unavailable_results INTEGER DEFAULT 0,
                useful_evidence_count INTEGER DEFAULT 0,
                contradicted_evidence_count INTEGER DEFAULT 0,
                outcome_alignment_score REAL DEFAULT 0.0,
                reliability_score REAL DEFAULT 0.0,
                regime_reliability TEXT DEFAULT '{}',
                timeframe_reliability TEXT DEFAULT '{}',
                symbol_reliability TEXT DEFAULT '{}',
                drift_detected INTEGER DEFAULT 0,
                last_updated TEXT
            )
        """)

        # Intelligence state (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL,
                cycle_id TEXT,
                observation TEXT DEFAULT '{}',
                active_regime TEXT DEFAULT 'UNKNOWN',
                drift_state TEXT DEFAULT '{}',
                uncertainty REAL DEFAULT 1.0,
                data_quality TEXT DEFAULT 'UNKNOWN',
                human_review_state TEXT DEFAULT 'NONE',
                last_successful_cycle TEXT,
                next_action TEXT,
                priority_explanation TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Drift events (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS drift_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drift_type TEXT NOT NULL,
                symbol TEXT,
                timeframe TEXT,
                magnitude REAL DEFAULT 0.0,
                severity TEXT DEFAULT 'NONE',
                research_trigger INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Research memory (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS research_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                category TEXT DEFAULT 'general',
                symbol TEXT,
                timeframe TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Audit events (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Human reviews (J7)
        c.execute("""
            CREATE TABLE IF NOT EXISTS human_reviews (
                review_id TEXT PRIMARY KEY,
                review_type TEXT,
                claim_id TEXT,
                decision TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Schema migrations tracking
        c.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_rr_symbol ON research_runs(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rr_status ON research_runs(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_opp_symbol ON opportunities(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_claim_status ON claims(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_drift_type ON drift_events(drift_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type)")

        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_research_run(self, run: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO research_runs
            (run_id, symbol, timeframe, trigger, status, started_at, completed_at, result_json, evidence_count, claim_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run.get("run_id"), run.get("symbol"), run.get("timeframe"),
             run.get("trigger", "manual"), run.get("status", "RUNNING"),
             run.get("started_at", self._now()), run.get("completed_at"),
             json.dumps(run.get("result", {})), run.get("evidence_count", 0),
             run.get("claim_count", 0)))
        conn.commit()
        conn.close()

    def get_research_run(self, run_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM research_runs WHERE run_id = ?", (run_id,))
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            if d.get("result_json"):
                d["result"] = json.loads(d["result_json"])
            return d
        return None

    def list_research_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM research_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_opportunity(self, opp: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO opportunities
            (opportunity_id, symbol, timeframe, thesis, confidence, status, evidence_refs, regime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (opp.get("opportunity_id"), opp.get("symbol"), opp.get("timeframe"),
             opp.get("thesis"), opp.get("confidence", 0.0), opp.get("status", "DETECTED"),
             json.dumps(opp.get("evidence_refs", [])), opp.get("regime", "")))
        conn.commit()
        conn.close()

    def get_opportunity(self, opp_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM opportunities WHERE opportunity_id = ?", (opp_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_opportunities(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM opportunities ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_setup(self, setup: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO setups
            (setup_id, opportunity_id, symbol, timeframe, entry_zone, invalidation,
             targets, rr, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (setup.get("setup_id"), setup.get("opportunity_id"), setup.get("symbol"),
             setup.get("timeframe"), setup.get("entry_zone"), setup.get("invalidation"),
             json.dumps(setup.get("targets", [])), setup.get("rr", 0.0),
             setup.get("confidence", 0.0), setup.get("status", "CANDIDATE")))
        conn.commit()
        conn.close()

    def get_setup(self, setup_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM setups WHERE setup_id = ?", (setup_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def save_claim(self, claim: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO claims
            (claim_id, text, source, status, evidence_refs, sample_size, confidence,
             stability, first_observed, last_validated, symbols, timeframes,
             contradictory_evidence, counterexamples)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.get("claim_id"), claim.get("text"), claim.get("source"),
             claim.get("status", "UNTESTED"), json.dumps(claim.get("evidence_refs", [])),
             claim.get("sample_size", 0), claim.get("confidence", 0.0),
             claim.get("stability", 0.0), claim.get("first_observed"),
             claim.get("last_validated"), json.dumps(claim.get("symbols", [])),
             json.dumps(claim.get("timeframes", [])),
             json.dumps(claim.get("contradictory_evidence", [])),
             json.dumps(claim.get("counterexamples", []))))
        conn.commit()
        conn.close()

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_claims(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM claims ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_evidence(self, evidence: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO evidence
            (claim_id, run_id, evidence_type, content, confidence, source, symbol, timeframe)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence.get("claim_id"), evidence.get("run_id"), evidence.get("evidence_type"),
             evidence.get("content"), evidence.get("confidence", 0.0), evidence.get("source"),
             evidence.get("symbol"), evidence.get("timeframe")))
        conn.commit()
        conn.close()

    def save_agent_reliability(self, profile: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO agent_reliability
            (agent_id, total_executions, successful_executions, failed_executions,
             unavailable_results, useful_evidence_count, contradicted_evidence_count,
             outcome_alignment_score, reliability_score, regime_reliability,
             timeframe_reliability, symbol_reliability, drift_detected, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile.get("agent_id"), profile.get("total_executions", 0),
             profile.get("successful_executions", 0), profile.get("failed_executions", 0),
             profile.get("unavailable_results", 0), profile.get("useful_evidence_count", 0),
             profile.get("contradicted_evidence_count", 0),
             profile.get("outcome_alignment_score", 0.0), profile.get("reliability_score", 0.0),
             json.dumps(profile.get("regime_reliability", {})),
             json.dumps(profile.get("timeframe_reliability", {})),
             json.dumps(profile.get("symbol_reliability", {})),
             1 if profile.get("drift_detected") else 0, profile.get("last_updated", self._now())))
        conn.commit()
        conn.close()

    def get_agent_reliability(self, agent_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM agent_reliability WHERE agent_id = ?", (agent_id,))
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            for k in ["regime_reliability", "timeframe_reliability", "symbol_reliability"]:
                if d.get(k):
                    d[k] = json.loads(d[k])
            return d
        return None

    def save_intelligence_state(self, state: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO intelligence_state
            (id, state, cycle_id, observation, active_regime, drift_state,
             uncertainty, data_quality, human_review_state, last_successful_cycle,
             next_action, priority_explanation, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (state.get("state", ""), state.get("cycle_id", ""),
             json.dumps(state.get("observation", {})), state.get("active_regime", "UNKNOWN"),
             json.dumps(state.get("drift_state", {})), state.get("uncertainty", 1.0),
             state.get("data_quality", "UNKNOWN"), state.get("human_review_state", "NONE"),
             state.get("last_successful_cycle", ""), state.get("next_action", ""),
             state.get("priority_explanation", ""), self._now()))
        conn.commit()
        conn.close()

    def get_intelligence_state(self) -> dict[str, Any] | None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM intelligence_state WHERE id = 1")
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            for k in ["observation", "drift_state"]:
                if d.get(k):
                    d[k] = json.loads(d[k])
            return d
        return None

    def save_drift_event(self, event: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO drift_events
            (drift_type, symbol, timeframe, magnitude, severity, research_trigger)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (event.get("drift_type"), event.get("symbol"), event.get("timeframe"),
             event.get("magnitude", 0.0), event.get("severity", "NONE"),
             1 if event.get("research_trigger") else 0))
        conn.commit()
        conn.close()

    def list_drift_events(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM drift_events ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_research_memory(self, entry: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO research_memory
            (key, value, category, symbol, timeframe)
            VALUES (?, ?, ?, ?, ?)""",
            (entry.get("key"), entry.get("value", ""), entry.get("category", "general"),
             entry.get("symbol", ""), entry.get("timeframe", "")))
        conn.commit()
        conn.close()

    def list_research_memory(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM research_memory ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_audit_event(self, event: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO audit_events
            (event_type, entity_type, entity_id, details)
            VALUES (?, ?, ?, ?)""",
            (event.get("event_type"), event.get("entity_type"),
             event.get("entity_id"), json.dumps(event.get("details", {}))))
        conn.commit()
        conn.close()

    def list_audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def save_human_review(self, review: dict[str, Any]) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO human_reviews
            (review_id, review_type, claim_id, decision, notes)
            VALUES (?, ?, ?, ?, ?)""",
            (review.get("review_id"), review.get("review_type"),
             review.get("claim_id"), review.get("decision"), review.get("notes", "")))
        conn.commit()
        conn.close()

    def list_human_reviews(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM human_reviews ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows


class PostgresRepository(Repository):
    """Postgres production repository stub.

    Requires psycopg2 or asyncpg.
    Falls back to SQLite if Postgres unavailable.
    """

    def __init__(self, db_url: str = "") -> None:
        self.db_url = db_url or os.environ.get("DATABASE_URL", "")
        self._available = bool(self.db_url)