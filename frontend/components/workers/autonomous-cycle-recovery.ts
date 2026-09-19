import { getAutonomousCycleStore } from "./autonomous-cycle-store";
import type { AutonomousCycleState } from "./autonomous-cycle-state";

const ACTIVE = new Set<AutonomousCycleState["status"]>(["RUNNING", "DISPATCHED"]);

export type AutonomousCycleRecoveryResult = {
  inspected: number;
  recovered: number;
  states: AutonomousCycleState[];
};

export function recoverStaleAutonomousCycles(maxAgeMs = 15 * 60_000): AutonomousCycleRecoveryResult {
  const now = Date.now();
  const store = getAutonomousCycleStore();
  const states = store.list(500);
  let recovered = 0;
  const next: AutonomousCycleState[] = [];
  for (const state of states) {
    if (!ACTIVE.has(state.status)) continue;
    const age = now - Date.parse(state.updatedAt);
    if (!Number.isFinite(age) || age < maxAgeMs) continue;
    const recoveredState: AutonomousCycleState = {
      ...state,
      status: "REVIEW_REQUIRED",
      lastAction: "STOP_REVIEW",
      lastReason: `STALE_CYCLE_RECOVERED:${Math.max(0, Math.floor(age))}ms`,
      updatedAt: new Date().toISOString(),
    };
    store.upsert(recoveredState);
    next.push(recoveredState);
    recovered++;
  }
  return { inspected: states.length, recovered, states: next };
}
