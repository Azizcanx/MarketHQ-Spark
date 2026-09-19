import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { WorkerEvidence, WorkerFeedback, WorkerLifecycleEvent, WorkerLogEntry, WorkerRecord, WorkerTask, WorkerStatus } from "./worker-types";

export class WorkerStore {
  private readonly db: DatabaseSync;

  constructor(dbPath: string) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    this.db = new DatabaseSync(dbPath);
    this.db.exec(`
      PRAGMA journal_mode = WAL;
      PRAGMA busy_timeout = 10000;
      CREATE TABLE IF NOT EXISTS worker_tasks (
        task_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        title TEXT NOT NULL,
        instructions TEXT NOT NULL,
        target_paths_json TEXT NOT NULL,
        provider TEXT NOT NULL,
        validation_command TEXT,
        timeout_ms INTEGER,
        attempt INTEGER NOT NULL DEFAULT 1,
        max_attempts INTEGER NOT NULL DEFAULT 2,
        metadata_json TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS worker_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        provider TEXT NOT NULL,
        status TEXT NOT NULL,
        job_id TEXT,
        worktree_path TEXT,
        changed_files_json TEXT NOT NULL DEFAULT '[]',
        validation_json TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_worker_runs_task ON worker_runs(task_id, attempt);
      CREATE TABLE IF NOT EXISTS worker_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        at TEXT NOT NULL,
        message TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_worker_events_task ON worker_events(task_id, id);
      CREATE TABLE IF NOT EXISTS worker_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        job_id TEXT,
        status TEXT NOT NULL,
        success INTEGER NOT NULL,
        changed_files_json TEXT NOT NULL DEFAULT '[]',
        diff TEXT,
        validation_json TEXT,
        error TEXT,
        safety_json TEXT NOT NULL,
        captured_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_worker_evidence_task ON worker_evidence(task_id, attempt, id);
      CREATE TABLE IF NOT EXISTS worker_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        recommendation TEXT NOT NULL,
        attempts INTEGER NOT NULL,
        validation_failures INTEGER NOT NULL,
        validation_passes INTEGER NOT NULL,
        failure_count INTEGER NOT NULL,
        changed_files_json TEXT NOT NULL DEFAULT '[]',
        evidence_quality TEXT NOT NULL,
        learning_eligible INTEGER NOT NULL DEFAULT 0,
        research_impact TEXT NOT NULL,
        summary TEXT NOT NULL,
        failure_details_json TEXT,
        next_cycle_input_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_worker_feedback_task ON worker_feedback(task_id, id);
      CREATE TABLE IF NOT EXISTS worker_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        kind TEXT NOT NULL,
        message TEXT NOT NULL,
        at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_worker_logs_task ON worker_logs(task_id, id);
    `);
  }

  close(): void { this.db.close(); }

  upsertTask(task: WorkerTask, status: WorkerStatus = "QUEUED"): void {
    const now = new Date().toISOString();
    this.db.prepare(`
      INSERT INTO worker_tasks
      (task_id, run_id, title, instructions, target_paths_json, provider,
       validation_command, timeout_ms, attempt, max_attempts, metadata_json,
       status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(task_id) DO UPDATE SET
        run_id=excluded.run_id,
        title=excluded.title,
        instructions=excluded.instructions,
        target_paths_json=excluded.target_paths_json,
        provider=excluded.provider,
        validation_command=excluded.validation_command,
        timeout_ms=excluded.timeout_ms,
        attempt=excluded.attempt,
        max_attempts=excluded.max_attempts,
        metadata_json=excluded.metadata_json,
        status=excluded.status,
        updated_at=excluded.updated_at
    `).run(task.taskId, task.runId, task.title, task.instructions, JSON.stringify(task.targetPaths), task.provider, task.validationCommand ?? null, task.timeoutMs ?? null, task.attempt ?? 1, task.maxAttempts ?? 2, JSON.stringify(task.metadata ?? {}), status, now, now);
  }

  getTask(taskId: string): WorkerTask | null {
    const row = this.db.prepare(`SELECT * FROM worker_tasks WHERE task_id=?`).get(taskId) as any;
    if (!row) return null;
    return { taskId: row.task_id, runId: row.run_id, title: row.title, instructions: row.instructions, targetPaths: JSON.parse(row.target_paths_json), provider: row.provider, validationCommand: row.validation_command ?? undefined, timeoutMs: row.timeout_ms ?? undefined, attempt: row.attempt, maxAttempts: row.max_attempts, metadata: row.metadata_json ? JSON.parse(row.metadata_json) : {} };
  }

  setTaskStatus(taskId: string, status: WorkerStatus): void {
    this.db.prepare(`UPDATE worker_tasks SET status=?, updated_at=? WHERE task_id=?`).run(status, new Date().toISOString(), taskId);
  }

  listQueuedTasks(limit = 50): WorkerTask[] {
    const rows = this.db.prepare(`SELECT * FROM worker_tasks WHERE status = 'QUEUED' ORDER BY created_at ASC, task_id ASC LIMIT ?`).all(limit) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id, title: row.title, instructions: row.instructions, targetPaths: JSON.parse(row.target_paths_json), provider: row.provider, validationCommand: row.validation_command ?? undefined, timeoutMs: row.timeout_ms ?? undefined, attempt: row.attempt, maxAttempts: row.max_attempts, metadata: row.metadata_json ? JSON.parse(row.metadata_json) : {} }));
  }

  recoverInterruptedRuns(): number {
    const result = this.db.prepare(`UPDATE worker_tasks SET status='QUEUED', updated_at=? WHERE status IN ('DISPATCHED', 'STARTING', 'RUNNING', 'PATCH_INTAKE', 'VALIDATING')`).run(new Date().toISOString());
    return Number(result.changes ?? 0);
  }

  startRun(task: WorkerTask): void {
    const now = new Date().toISOString();
    this.db.prepare(`INSERT INTO worker_runs (task_id, run_id, attempt, provider, status, changed_files_json, created_at, started_at) VALUES (?, ?, ?, ?, ?, '[]', ?, ?)`).run(task.taskId, task.runId, task.attempt ?? 1, task.provider, "STARTING", now, now);
  }

  updateRun(taskId: string, attempt: number, patch: Partial<WorkerRecord>): void {
    const fields: string[] = []; const values: unknown[] = [];
    const map: Record<string, string> = { status: "status", jobId: "job_id", worktreePath: "worktree_path", error: "error", startedAt: "started_at", completedAt: "completed_at" };
    for (const [key, column] of Object.entries(map)) if (key in patch) { fields.push(`${column}=?`); values.push((patch as any)[key] ?? null); }
    if ("changedFiles" in patch) { fields.push("changed_files_json=?"); values.push(JSON.stringify(patch.changedFiles ?? [])); }
    if ("validation" in patch) { fields.push("validation_json=?"); values.push(JSON.stringify(patch.validation ?? null)); }
    if (!fields.length) return;
    values.push(taskId, attempt);
    this.db.prepare(`UPDATE worker_runs SET ${fields.join(", ")} WHERE task_id=? AND attempt=?`).run(...values);
  }

  recordEvidence(evidence: WorkerEvidence): void {
    this.db.prepare(`INSERT INTO worker_evidence (task_id, run_id, attempt, job_id, status, success, changed_files_json, diff, validation_json, error, safety_json, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(evidence.taskId, evidence.runId, evidence.attempt, evidence.jobId ?? null, evidence.status, evidence.success ? 1 : 0, JSON.stringify(evidence.changedFiles), evidence.diff ?? null, evidence.validation ? JSON.stringify(evidence.validation) : null, evidence.error ?? null, JSON.stringify(evidence.safety), evidence.capturedAt);
  }

  listEvidence(taskId: string): WorkerEvidence[] {
    const rows = this.db.prepare(`SELECT * FROM worker_evidence WHERE task_id=? ORDER BY attempt ASC, id ASC`).all(taskId) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id, attempt: row.attempt, jobId: row.job_id ?? undefined, status: row.status, success: Boolean(row.success), changedFiles: JSON.parse(row.changed_files_json || "[]"), diff: row.diff ?? undefined, validation: row.validation_json ? JSON.parse(row.validation_json) : undefined, error: row.error ?? undefined, safety: JSON.parse(row.safety_json), capturedAt: row.captured_at }));
  }

  recordFeedback(feedback: WorkerFeedback): void {
    this.db.prepare(`INSERT INTO worker_feedback (task_id, run_id, kind, recommendation, attempts, validation_failures, validation_passes, failure_count, changed_files_json, evidence_quality, learning_eligible, research_impact, summary, failure_details_json, next_cycle_input_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(feedback.taskId, feedback.runId, feedback.kind, feedback.recommendation, feedback.attempts, feedback.validationFailures, feedback.validationPasses, feedback.failureCount, JSON.stringify(feedback.changedFiles), feedback.evidenceQuality, feedback.learningEligible ? 1 : 0, feedback.researchImpact, feedback.summary, feedback.failureDetails ? JSON.stringify(feedback.failureDetails) : null, JSON.stringify(feedback.nextCycleInput), feedback.createdAt);
  }

  latestFeedback(taskId: string): WorkerFeedback | null {
    const row = this.db.prepare(`SELECT * FROM worker_feedback WHERE task_id=? ORDER BY id DESC LIMIT 1`).get(taskId) as any;
    if (!row) return null;
    return { taskId: row.task_id, runId: row.run_id, kind: row.kind, recommendation: row.recommendation, attempts: row.attempts, validationFailures: row.validation_failures, validationPasses: row.validation_passes, failureCount: row.failure_count, changedFiles: JSON.parse(row.changed_files_json || "[]"), evidenceQuality: row.evidence_quality, learningEligible: false, researchImpact: row.research_impact, summary: row.summary, failureDetails: row.failure_details_json ? JSON.parse(row.failure_details_json) : undefined, nextCycleInput: JSON.parse(row.next_cycle_input_json || "{}"), createdAt: row.created_at };
  }

  latestFeedbackForContext(criteria: { strategyId?: string; symbol?: string; timeframe?: string }): WorkerFeedback | null {
    const rows = this.db.prepare(`SELECT f.*, t.metadata_json AS task_metadata_json FROM worker_feedback f INNER JOIN worker_tasks t ON t.task_id=f.task_id ORDER BY f.id DESC LIMIT 200`).all() as any[];
    for (const row of rows) {
      const metadata = row.task_metadata_json ? JSON.parse(row.task_metadata_json) : {};
      if (criteria.strategyId && metadata.strategyId !== criteria.strategyId) continue;
      if (criteria.symbol && metadata.symbol !== criteria.symbol) continue;
      if (criteria.timeframe && metadata.timeframe !== criteria.timeframe) continue;
      return { taskId: row.task_id, runId: row.run_id, kind: row.kind, recommendation: row.recommendation, attempts: row.attempts, validationFailures: row.validation_failures, validationPasses: row.validation_passes, failureCount: row.failure_count, changedFiles: JSON.parse(row.changed_files_json || "[]"), evidenceQuality: row.evidence_quality, learningEligible: false, researchImpact: row.research_impact, summary: row.summary, failureDetails: row.failure_details_json ? JSON.parse(row.failure_details_json) : undefined, nextCycleInput: JSON.parse(row.next_cycle_input_json || "{}"), createdAt: row.created_at };
    }
    return null;
  }

  listFeedback(limit = 50): WorkerFeedback[] {
    const rows = this.db.prepare(`SELECT * FROM worker_feedback ORDER BY id DESC LIMIT ?`).all(limit) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id, kind: row.kind, recommendation: row.recommendation, attempts: row.attempts, validationFailures: row.validation_failures, validationPasses: row.validation_passes, failureCount: row.failure_count, changedFiles: JSON.parse(row.changed_files_json || "[]"), evidenceQuality: row.evidence_quality, learningEligible: false, researchImpact: row.research_impact, summary: row.summary, failureDetails: row.failure_details_json ? JSON.parse(row.failure_details_json) : undefined, nextCycleInput: JSON.parse(row.next_cycle_input_json || "{}"), createdAt: row.created_at }));
  }

  transition(event: WorkerLifecycleEvent): void {
    this.db.prepare(`INSERT INTO worker_events (task_id, run_id, attempt, from_status, to_status, at, message) VALUES (?, ?, ?, ?, ?, ?, ?)`).run(event.taskId, event.runId, event.attempt, event.from, event.to, event.at, event.message ?? null);
    this.setTaskStatus(event.taskId, event.to);
  }

  listEvents(taskId: string, limit = 100): WorkerLifecycleEvent[] {
    const safeLimit = Math.max(1, Math.min(500, Math.floor(limit)));
    const rows = this.db.prepare(`SELECT task_id, run_id, attempt, from_status, to_status, at, message FROM worker_events WHERE task_id=? ORDER BY id ASC LIMIT ?`).all(taskId, safeLimit) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id, attempt: row.attempt, from: row.from_status ?? null, to: row.to_status, at: row.at, message: row.message ?? undefined }));
  }

  appendLog(entry: WorkerLogEntry): void {
    this.db.prepare(`INSERT INTO worker_logs (task_id, run_id, attempt, kind, message, at) VALUES (?, ?, ?, ?, ?, ?)`).run(entry.taskId, entry.runId, entry.attempt, entry.kind, entry.message, entry.at);
  }

  listLogs(taskId: string, limit = 500): WorkerLogEntry[] {
    const safeLimit = Math.max(1, Math.min(2000, Math.floor(limit)));
    const rows = this.db.prepare(`SELECT task_id, run_id, attempt, kind, message, at FROM worker_logs WHERE task_id=? ORDER BY id ASC LIMIT ?`).all(taskId, safeLimit) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id, attempt: row.attempt, kind: row.kind as WorkerLogEntry["kind"], message: row.message, at: row.at }));
  }

  latest(taskId: string): WorkerRecord | null {
    const task = this.db.prepare(`SELECT * FROM worker_tasks WHERE task_id=?`).get(taskId) as any;
    if (!task) return null;
    const row = this.db.prepare(`SELECT * FROM worker_runs WHERE task_id=? ORDER BY attempt DESC, id DESC LIMIT 1`).get(taskId) as any;
    if (!row) return { taskId: task.task_id, runId: task.run_id, provider: task.provider, attempt: task.attempt, maxAttempts: task.max_attempts, status: task.status, changedFiles: [], createdAt: task.created_at };
    return { taskId: row.task_id, runId: row.run_id, provider: row.provider, attempt: task.attempt, maxAttempts: task.max_attempts, status: task.status, jobId: row.job_id ?? undefined, worktreePath: row.worktree_path ?? undefined, changedFiles: JSON.parse(row.changed_files_json || "[]"), validation: row.validation_json ? JSON.parse(row.validation_json) : undefined, error: row.error ?? undefined, createdAt: row.created_at, startedAt: row.started_at ?? undefined, completedAt: row.completed_at ?? undefined };
  }

  list(limit = 50): WorkerRecord[] {
    const rows = this.db.prepare(`
      SELECT t.task_id, t.run_id AS task_run_id, t.provider AS task_provider,
        t.attempt AS task_attempt, t.max_attempts, t.status AS task_status,
        t.created_at AS task_created_at, t.updated_at,
        r.id AS run_id_row, r.run_id, r.attempt AS run_attempt,
        r.provider AS run_provider, r.status AS run_status, r.job_id,
        r.worktree_path, r.changed_files_json, r.validation_json, r.error,
        r.created_at AS run_created_at, r.started_at, r.completed_at
      FROM worker_tasks t
      LEFT JOIN worker_runs r ON r.task_id=t.task_id
        AND r.attempt=(SELECT MAX(r2.attempt) FROM worker_runs r2 WHERE r2.task_id=t.task_id)
      ORDER BY COALESCE(r.id, 0) DESC, t.created_at DESC, t.task_id ASC
      LIMIT ?
    `).all(limit) as any[];
    return rows.map((row) => ({ taskId: row.task_id, runId: row.run_id ?? row.task_run_id, provider: row.run_provider ?? row.task_provider, attempt: row.run_attempt ?? row.task_attempt ?? 1, maxAttempts: row.max_attempts ?? 2, status: row.run_status ?? row.task_status, jobId: row.job_id ?? undefined, worktreePath: row.worktree_path ?? undefined, changedFiles: JSON.parse(row.changed_files_json || "[]"), validation: row.validation_json ? JSON.parse(row.validation_json) : undefined, error: row.error ?? undefined, createdAt: row.run_created_at ?? row.task_created_at, startedAt: row.started_at ?? undefined, completedAt: row.completed_at ?? undefined }));
  }
}
