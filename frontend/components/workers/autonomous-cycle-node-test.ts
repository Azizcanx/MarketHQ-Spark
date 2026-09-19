import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { AutonomousCycleStore } from "./autonomous-cycle-store";

test("AutonomousCycleStore: first owner acquires a lease", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
  const store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  try {
    const now = new Date("2026-09-14T10:00:00.000Z");
    const lease = store.acquireLease("cycle-1", "owner-a", 60_000, now);
    assert.equal(lease?.ownerId, "owner-a");
    assert.equal(lease?.expiresAt, "2026-09-14T10:01:00.000Z");
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("AutonomousCycleStore: active lease blocks another owner", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
  const store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  try {
    const now = new Date("2026-09-14T10:00:00.000Z");
    assert.ok(store.acquireLease("cycle-1", "owner-a", 60_000, now));
    assert.equal(
      store.acquireLease("cycle-1", "owner-b", 60_000, new Date("2026-09-14T10:00:30.000Z")),
      null,
    );
    assert.equal(store.getLease("cycle-1")?.ownerId, "owner-a");
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("AutonomousCycleStore: expired lease can be taken over", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
  const store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  try {
    const now = new Date("2026-09-14T10:00:00.000Z");
    assert.ok(store.acquireLease("cycle-1", "owner-a", 60_000, now));
    assert.ok(store.acquireLease("cycle-1", "owner-b", 60_000, new Date("2026-09-14T10:01:00.000Z")));
    assert.equal(store.getLease("cycle-1")?.ownerId, "owner-b");
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("AutonomousCycleStore: release requires matching owner", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
  const store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  try {
    assert.ok(store.acquireLease("cycle-1", "owner-a", 60_000, new Date("2026-09-14T10:00:00.000Z")));
    assert.equal(store.releaseLease("cycle-1", "owner-b"), false);
    assert.equal(store.releaseLease("cycle-1", "owner-a"), true);
    assert.equal(store.getLease("cycle-1"), null);
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("AutonomousCycleStore: TTL is clamped to one second minimum", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
  const store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  try {
    const lease = store.acquireLease("cycle-1", "owner-a", 1, new Date("2026-09-14T10:00:00.000Z"));
    assert.equal(lease?.expiresAt, "2026-09-14T10:00:01.000Z");
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
