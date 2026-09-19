# AZIZBUSINESS PERSISTENCE ARCHITECTURE

**Date:** 2026-09-17

---

## Overview

Repository/Storage abstraction layer supporting SQLite (development)
and Postgres (production).

## Design Principles

1. **Idempotent migration** — Safe to run multiple times
2. **Existing data preserved** — Never delete data on migration
3. **SQLite for dev** — Zero config, file-based
4. **Postgres ready** — Repository interface supports both
5. **DB-less tests unaffected** — Deterministic tests don't need DB

## Repository Pattern

```
Repository (ABC)
├── SQLiteRepository  (development)
└── PostgresRepository (production stub)
```

## Tables

### J0-J6 Tables (existing)
- agent_runs, agent_results, evidence_items, agent_claims, feature_snapshots
- schema_migrations

### J7 Tables (new)
- research_runs — Research execution records
- opportunities — Detected opportunities
- setups — Research-backed setups
- claims — Validated claims
- evidence — Evidence items
- agent_reliability — Per-agent reliability profiles
- intelligence_state — System intelligence state
- drift_events — Detected drift events
- research_memory — Research memory entries
- audit_events — Audit trail
- human_reviews — Human review decisions

## Indexes

- research_runs(symbol, status)
- opportunities(symbol)
- claims(status)
- drift_events(drift_type)
- audit_events(event_type)

## Migration Safety

- CREATE TABLE IF NOT EXISTS
- INSERT OR REPLACE for upserts
- No DROP TABLE
- No data deletion
- Migration tracking in schema_migrations

## Connection Handling

- SQLite: timeout=30, check_same_thread=False
- Postgres: connection pool (J8)

## Data Integrity

- Foreign key constraints where applicable
- NOT NULL constraints on required fields
- UNIQUE constraints on primary keys
- JSON serialization for complex types

## Backup/Restore

SQLite: copy file
Postgres: pg_dump/pg_restore (J8)

## Testing

- Repository tests use in-memory or temp files
- Migration tests run twice (idempotency)
- Restart tests simulate process crash
- Duplicate tests verify idempotent save