import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { AutonomousCycleStore } from "./autonomous-cycle-store";

const dbPath = path.join(os.tmpdir(), `markethq-cycle-lease-${Date.now()}-${Math.random().toString(16).slice(2)}.sqlite`);
const store = new AutonomousCycleStore(dbPath);
const now = new Date("2026-09-14T10:00:00.000Z");

const first = store.acquireLease("lease-cycle", "owner-a", 60_000, now);
assert.ok(first);
assert.equal(store.acquireLease("lease-cycle", "owner-b", 60_000, now), null);
assert.equal(store.getLease("lease-cycle")?.ownerId, "owner-a");
assert.equal(store.releaseLease("lease-cycle", "owner-b"), false);
assert.equal(store.releaseLease("lease-cycle", "owner-a"), true);
assert.ok(store.acquireLease("lease-cycle", "owner-b", 60_000, now));
assert.equal(store.acquireLease("lease-cycle", "owner-c", 60_000, new Date("2026-09-14T10:00:59.999Z")), null);
assert.ok(store.acquireLease("lease-cycle", "owner-c", 60_000, new Date("2026-09-14T10:01:00.000Z")));

store.close();
try { fs.rmSync(dbPath, { force: true }); } catch {}
try { fs.rmSync(`${dbPath}-wal`, { force: true }); } catch {}
try { fs.rmSync(`${dbPath}-shm`, { force: true }); } catch {}
console.log("AUTONOMOUS CYCLE LEASE TEST PASS");
