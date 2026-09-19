import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { AutonomousCycleState } from "./autonomous-cycle-state";

function resolveDbPath(): string {
  const repoRoot = path.resolve(process.env.MARKETHQ_REPO_ROOT ?? path.resolve(process.cwd(), ".."));
  return process.env.MARKETHQ_WORKER_DB_PATH ?? path.join(repoRoot, "automation", "worker-runtime.sqlite");
}

export type AutonomousCycleLease = { cycleId: string; ownerId: string; expiresAt: string };

export class AutonomousCycleStore {
  private readonly db: DatabaseSync;

  constructor(dbPath = resolveDbPath()) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    this.db = new DatabaseSync(dbPath);
    this.db.exec(`
      PRAGMA journal_mode = WAL;
      PRAGMA busy_timeout = 10000;
      CREATE TABLE IF NOT EXISTS autonomous_cycle_states (
        cycle_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, cycle_number INTEGER NOT NULL,
        max_cycles INTEGER NOT NULL, status TEXT NOT NULL, last_action TEXT NOT NULL,
        last_reason TEXT NOT NULL, worker_task_id TEXT, worker_status TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
        implementation_intent TEXT, feedback_recommendation TEXT,
        patch_quality_grade TEXT, patch_quality_score REAL,
        retry_recommended INTEGER NOT NULL DEFAULT 0,
        next_cycle_allowed INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS idx_autonomous_cycle_states_updated ON autonomous_cycle_states(updated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_autonomous_cycle_states_run ON autonomous_cycle_states(run_id, updated_at DESC);
      CREATE TABLE IF NOT EXISTS autonomous_cycle_leases (
        cycle_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, expires_at TEXT NOT NULL, acquired_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_autonomous_cycle_leases_expiry ON autonomous_cycle_leases(expires_at);
    `);
    this.ensureColumn("implementation_intent", "TEXT");
    this.ensureColumn("feedback_recommendation", "TEXT");
    this.ensureColumn("patch_quality_grade", "TEXT");
    this.ensureColumn("patch_quality_score", "REAL");
    this.ensureColumn("retry_recommended", "INTEGER NOT NULL DEFAULT 0");
    this.ensureColumn("next_cycle_allowed", "INTEGER NOT NULL DEFAULT 0");
  }

  private ensureColumn(name: string, definition: string): void {
    const columns = this.db.prepare(`PRAGMA table_info(autonomous_cycle_states)`).all() as Array<{ name: string }>;
    if (!columns.some((column) => column.name === name)) {
      this.db.exec(`ALTER TABLE autonomous_cycle_states ADD COLUMN ${name} ${definition}`);
    }
  }

  upsert(state: AutonomousCycleState): AutonomousCycleState {
    this.db.prepare(`
      INSERT INTO autonomous_cycle_states
        (cycle_id, run_id, cycle_number, max_cycles, status, last_action, last_reason,
         worker_task_id, worker_status, attempts, updated_at, implementation_intent,
         feedback_recommendation, patch_quality_grade, patch_quality_score,
         retry_recommended, next_cycle_allowed)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(cycle_id) DO UPDATE SET
        run_id=excluded.run_id, cycle_number=excluded.cycle_number, max_cycles=excluded.max_cycles,
        status=excluded.status, last_action=excluded.last_action, last_reason=excluded.last_reason,
        worker_task_id=excluded.worker_task_id, worker_status=excluded.worker_status,
        attempts=excluded.attempts, updated_at=excluded.updated_at,
        implementation_intent=excluded.implementation_intent,
        feedback_recommendation=excluded.feedback_recommendation,
        patch_quality_grade=excluded.patch_quality_grade, patch_quality_score=excluded.patch_quality_score,
        retry_recommended=excluded.retry_recommended, next_cycle_allowed=excluded.next_cycle_allowed
    `).run(
      state.cycleId, state.runId, state.cycleNumber, state.maxCycles, state.status, state.lastAction,
      state.lastReason, state.workerTaskId ?? null, state.workerStatus ?? null, state.attempts,
      state.updatedAt, state.implementationIntent ?? null, state.feedbackRecommendation ?? null,
      state.patchQualityGrade ?? null, state.patchQualityScore ?? null,
      state.retryRecommended ? 1 : 0, state.nextCycleAllowed ? 1 : 0,
    );
    return state;
  }

  get(cycleId: string): AutonomousCycleState | null {
    const row = this.db.prepare(`SELECT * FROM autonomous_cycle_states WHERE cycle_id=?`).get(cycleId) as any;
    return row ? this.map(row) : null;
  }

  list(limit = 50): AutonomousCycleState[] {
    const safeLimit = Math.max(1, Math.min(500, Math.floor(limit)));
    const rows = this.db.prepare(`SELECT * FROM autonomous_cycle_states ORDER BY updated_at DESC LIMIT ?`).all(safeLimit) as any[];
    return rows.map((row) => this.map(row));
  }

  acquireLease(cycleId: string, ownerId: string, ttlMs = 120_000, now = new Date()): AutonomousCycleLease | null {
    const safeTtl = Math.max(1_000, Math.min(3_600_000, Math.floor(ttlMs)));
    const acquiredAt = now.toISOString();
    const expiresAt = new Date(now.getTime() + safeTtl).toISOString();
    const result = this.db.prepare(`
      INSERT INTO autonomous_cycle_leases (cycle_id, owner_id, expires_at, acquired_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(cycle_id) DO UPDATE SET owner_id=excluded.owner_id, expires_at=excluded.expires_at, acquired_at=excluded.acquired_at
      WHERE autonomous_cycle_leases.expires_at <= ?
    `).run(cycleId, ownerId, expiresAt, acquiredAt, acquiredAt);
    if (Number(result.changes ?? 0) !== 1) return null;
    return { cycleId, ownerId, expiresAt };
  }

  releaseLease(cycleId: string, ownerId: string): boolean {
    const result = this.db.prepare(`DELETE FROM autonomous_cycle_leases WHERE cycle_id=? AND owner_id=?`).run(cycleId, ownerId);
    return Number(result.changes ?? 0) === 1;
  }

  getLease(cycleId: string): AutonomousCycleLease | null {
    const row = this.db.prepare(`SELECT cycle_id, owner_id, expires_at FROM autonomous_cycle_leases WHERE cycle_id=?`).get(cycleId) as { cycle_id: string; owner_id: string; expires_at: string } | undefined;
    return row ? { cycleId: row.cycle_id, ownerId: row.owner_id, expiresAt: row.expires_at } : null;
  }

  close(): void { this.db.close(); }

  private map(row: any): AutonomousCycleState {
    return {
      cycleId: row.cycle_id, runId: row.run_id, cycleNumber: Number(row.cycle_number), maxCycles: Number(row.max_cycles),
      status: row.status, lastAction: row.last_action, lastReason: row.last_reason,
      workerTaskId: row.worker_task_id ?? undefined, workerStatus: row.worker_status ?? undefined,
      attempts: Number(row.attempts ?? 0), updatedAt: row.updated_at,
      implementationIntent: row.implementation_intent ?? undefined,
      feedbackRecommendation: row.feedback_recommendation ?? undefined,
      patchQualityGrade: row.patch_quality_grade ?? undefined,
      patchQualityScore: row.patch_quality_score == null ? undefined : Number(row.patch_quality_score),
      retryRecommended: Boolean(row.retry_recommended), nextCycleAllowed: Boolean(row.next_cycle_allowed),
    };
  }
}

let singleton: AutonomousCycleStore | null = null;
export function getAutonomousCycleStore(): AutonomousCycleStore { if (!singleton) singleton = new AutonomousCycleStore(); return singleton; }
