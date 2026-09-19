import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { AutonomousCycleStore } from "./autonomous-cycle-store";

describe("AutonomousCycleStore leases", () => {
  let dir: string;
  let store: AutonomousCycleStore;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "markethq-lease-test-"));
    store = new AutonomousCycleStore(path.join(dir, "worker-runtime.sqlite"));
  });

  afterEach(() => {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("allows the first owner to acquire a lease", () => {
    const now = new Date("2026-09-14T10:00:00.000Z");
    const lease = store.acquireLease("cycle-1", "owner-a", 60_000, now);

    expect(lease).not.toBeNull();
    expect(lease?.ownerId).toBe("owner-a");
    expect(lease?.expiresAt).toBe("2026-09-14T10:01:00.000Z");
  });

  it("rejects another owner while the lease is active", () => {
    const now = new Date("2026-09-14T10:00:00.000Z");
    expect(store.acquireLease("cycle-1", "owner-a", 60_000, now)).not.toBeNull();

    const second = store.acquireLease("cycle-1", "owner-b", 60_000, new Date("2026-09-14T10:00:30.000Z"));
    expect(second).toBeNull();
    expect(store.getLease("cycle-1")?.ownerId).toBe("owner-a");
  });

  it("allows takeover after expiry", () => {
    const now = new Date("2026-09-14T10:00:00.000Z");
    expect(store.acquireLease("cycle-1", "owner-a", 60_000, now)).not.toBeNull();

    const takeover = store.acquireLease("cycle-1", "owner-b", 60_000, new Date("2026-09-14T10:01:00.000Z"));
    expect(takeover).not.toBeNull();
    expect(store.getLease("cycle-1")?.ownerId).toBe("owner-b");
  });

  it("only releases a lease when the owner matches", () => {
    const now = new Date("2026-09-14T10:00:00.000Z");
    expect(store.acquireLease("cycle-1", "owner-a", 60_000, now)).not.toBeNull();

    expect(store.releaseLease("cycle-1", "owner-b")).toBe(false);
    expect(store.getLease("cycle-1")?.ownerId).toBe("owner-a");

    expect(store.releaseLease("cycle-1", "owner-a")).toBe(true);
    expect(store.getLease("cycle-1")).toBeNull();
  });

  it("clamps unsafe TTL values", () => {
    const now = new Date("2026-09-14T10:00:00.000Z");
    const lease = store.acquireLease("cycle-1", "owner-a", 1, now);

    expect(lease?.expiresAt).toBe("2026-09-14T10:00:01.000Z");
  });
});
