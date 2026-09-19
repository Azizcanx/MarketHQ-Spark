import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export type AutonomousModeState = { enabled: boolean; updatedAt: string; updatedBy: string };

function dbPath(): string {
  const repoRoot = path.resolve(process.env.MARKETHQ_REPO_ROOT ?? path.resolve(process.cwd(), ".."));
  return process.env.MARKETHQ_WORKER_DB_PATH ?? path.join(repoRoot, "automation", "worker-runtime.sqlite");
}

function open(): DatabaseSync {
  const db = new DatabaseSync(dbPath());
  db.exec("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;");
  db.exec("CREATE TABLE IF NOT EXISTS autonomous_mode (id INTEGER PRIMARY KEY CHECK (id = 1), enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)");
  return db;
}

export function getAutonomousModeState(): AutonomousModeState {
  const db = open();
  try {
    const row = db.prepare("SELECT enabled, updated_at, updated_by FROM autonomous_mode WHERE id = 1").get() as { enabled?: number; updated_at?: string; updated_by?: string } | undefined;
    return { enabled: row?.enabled === 1, updatedAt: row?.updated_at ?? "", updatedBy: row?.updated_by ?? "DEFAULT_OFF" };
  } finally { db.close(); }
}

export function setAutonomousMode(enabled: boolean, updatedBy = "PANEL"): AutonomousModeState {
  const db = open();
  try {
    const updatedAt = new Date().toISOString();
    db.prepare("INSERT INTO autonomous_mode (id, enabled, updated_at, updated_by) VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at, updated_by=excluded.updated_by").run(enabled ? 1 : 0, updatedAt, updatedBy);
    return { enabled, updatedAt, updatedBy };
  } finally { db.close(); }
}
