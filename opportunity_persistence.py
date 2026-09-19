# -*- coding: utf-8 -*-
"""Opportunity Engine Persistence.

Tables:
- opportunities: opportunity lifecycle records
- opportunity_evidence: evidence items linked to opportunities

Safe, idempotent migration. No data deletion.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from opportunity_model import Opportunity, SetupCandidate

DB_PATH = "/opt/markethq/market_hq.db"


class OpportunityPersistence:
    """Persistence for Opportunity Engine."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Migration ───────────────────────────────────────────────

    def migrate(self) -> dict[str, Any]:
        """Create opportunity tables if not exist. Idempotent + safe."""
        conn = self._conn()
        cursor = conn.cursor()
        created = []

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                opportunity_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                market_context TEXT,
                regime TEXT DEFAULT 'UNKNOWN',
                direction TEXT DEFAULT 'UNKNOWN',
                thesis TEXT,
                status TEXT DEFAULT 'DETECTED',
                confidence REAL DEFAULT 0.0,
                uncertainty REAL DEFAULT 1.0,
                agent_results_json TEXT DEFAULT '[]',
                source_agents_json TEXT DEFAULT '[]',
                supporting_evidence_json TEXT DEFAULT '[]',
                conflicting_evidence_json TEXT DEFAULT '[]',
                unavailable_evidence_json TEXT DEFAULT '[]',
                strategy_families_json TEXT DEFAULT '[]',
                strategy_count INTEGER DEFAULT 0,
                independent_families INTEGER DEFAULT 0,
                correlated_families INTEGER DEFAULT 0,
                feature_snapshot_id TEXT,
                first_detected_at TEXT,
                last_updated_at TEXT,
                validated_at TEXT,
                invalidated_at TEXT,
                expired_at TEXT,
                invalidation_reason TEXT,
                expiry_reason TEXT,
                metadata_json TEXT DEFAULT '{}',
                setup_candidate_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        created.append("opportunities")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                agent_id TEXT,
                feature TEXT,
                value REAL,
                direction TEXT,
                strength REAL,
                source TEXT,
                explanation TEXT,
                timestamp TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
            )
        """)
        created.append("opportunity_evidence")

        # Indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opp_symbol_tf
            ON opportunities(symbol, timeframe)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opp_status
            ON opportunities(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opp_detected
            ON opportunities(detected_at)
        """)

        conn.commit()
        conn.close()
        return {"tables_created": created}

    # ─── CRUD ────────────────────────────────────────────────────

    def save_opportunity(self, opp: Opportunity) -> None:
        """Insert or replace opportunity record."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO opportunities (
                opportunity_id, symbol, timeframe, detected_at,
                market_context, regime, direction, thesis, status,
                confidence, uncertainty,
                agent_results_json, source_agents_json,
                supporting_evidence_json, conflicting_evidence_json,
                unavailable_evidence_json,
                strategy_families_json, strategy_count,
                independent_families, correlated_families,
                feature_snapshot_id,
                first_detected_at, last_updated_at,
                validated_at, invalidated_at, expired_at,
                invalidation_reason, expiry_reason,
                metadata_json, setup_candidate_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            opp.opportunity_id, opp.symbol, opp.timeframe, opp.detected_at,
            opp.market_context, opp.regime, opp.direction, opp.thesis, opp.status,
            opp.confidence, opp.uncertainty,
            json.dumps(opp.agent_results, default=str),
            json.dumps([sa.__dict__ for sa in opp.source_agents], default=str),
            json.dumps(opp.supporting_evidence, default=str),
            json.dumps(opp.conflicting_evidence, default=str),
            json.dumps(opp.unavailable_evidence, default=str),
            json.dumps(opp.strategy_families, default=str),
            opp.strategy_count, opp.independent_families, opp.correlated_families,
            opp.feature_snapshot_id,
            opp.first_detected_at, opp.last_updated_at,
            opp.validated_at, opp.invalidated_at, opp.expired_at,
            opp.invalidation_reason, opp.expiry_reason,
            json.dumps(opp.metadata, default=str), opp.setup_candidate_id,
        ))
        conn.commit()
        conn.close()

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        """Retrieve opportunity by ID."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM opportunities WHERE opportunity_id = ?",
            (opportunity_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)

    def list_opportunities(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List opportunities with optional filters."""
        conn = self._conn()
        cursor = conn.cursor()
        query = "SELECT * FROM opportunities WHERE 1=1"
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if timeframe:
            query += " AND timeframe = ?"
            params.append(timeframe)
        if status:
            query += " AND status = ?"
            params.append(status)
        if direction:
            query += " AND direction = ?"
            params.append(direction)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def update_opportunity(self, opp: Opportunity) -> None:
        """Update an existing opportunity."""
        self.save_opportunity(opp)  # INSERT OR REPLACE

    def delete_opportunity(self, opportunity_id: str) -> bool:
        """Delete opportunity and its evidence."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM opportunity_evidence WHERE opportunity_id = ?", (opportunity_id,))
        cursor.execute("DELETE FROM opportunities WHERE opportunity_id = ?", (opportunity_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted > 0

    # ─── Evidence ────────────────────────────────────────────────

    def save_evidence(self, opportunity_id: str, evidence_type: str,
                      items: list[dict[str, Any]]) -> None:
        """Save evidence items for an opportunity."""
        conn = self._conn()
        cursor = conn.cursor()
        for item in items:
            cursor.execute("""
                INSERT INTO opportunity_evidence
                (opportunity_id, evidence_type, agent_id, feature, value,
                 direction, strength, source, explanation, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                opportunity_id, evidence_type,
                item.get("agent_id", ""),
                item.get("feature", ""),
                item.get("value"),
                item.get("direction", ""),
                item.get("strength"),
                item.get("source", ""),
                item.get("explanation", ""),
                item.get("timestamp", ""),
            ))
        conn.commit()
        conn.close()

    def get_evidence(self, opportunity_id: str) -> list[dict[str, Any]]:
        """Get all evidence for an opportunity."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM opportunity_evidence WHERE opportunity_id = ? ORDER BY id",
            (opportunity_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ─── Lifecycle ───────────────────────────────────────────────

    def set_status(self, opportunity_id: str, status: str,
                   reason: str = "") -> bool:
        """Update opportunity status with reason."""
        opp = self.get_opportunity(opportunity_id)
        if opp is None:
            return False

        conn = self._conn()
        cursor = conn.cursor()

        if status == "INVALIDATED":
            cursor.execute(
                "UPDATE opportunities SET status=?, invalidation_reason=?, invalidated_at=?, last_updated_at=? WHERE opportunity_id=?",
                (status, reason, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), opportunity_id),
            )
        elif status == "EXPIRED":
            cursor.execute(
                "UPDATE opportunities SET status=?, expiry_reason=?, expired_at=?, last_updated_at=? WHERE opportunity_id=?",
                (status, reason, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), opportunity_id),
            )
        elif status == "VALIDATED":
            cursor.execute(
                "UPDATE opportunities SET status=?, validated_at=?, last_updated_at=? WHERE opportunity_id=?",
                (status, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), opportunity_id),
            )
        else:
            cursor.execute(
                "UPDATE opportunities SET status=?, last_updated_at=? WHERE opportunity_id=?",
                (status, datetime.now(timezone.utc).isoformat(), opportunity_id),
            )

        conn.commit()
        conn.close()
        return True

    def count(self) -> int:
        """Total opportunity count."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM opportunities")
        count = cursor.fetchone()[0]
        conn.close()
        return count