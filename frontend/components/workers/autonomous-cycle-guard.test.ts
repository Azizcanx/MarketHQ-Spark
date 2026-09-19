import type { AgentContext } from "../agents/agent-types";
import type { AutonomousCycleState } from "./autonomous-cycle-state";
import { guardAutonomousCycleDispatch } from "./autonomous-cycle-guard";

function context(overrides: Record<string, unknown> = {}): AgentContext {
  return {
    runId: "run-1",
    metadata: overrides,
  } as AgentContext;
}

function state(overrides: Partial<AutonomousCycleState> = {}): AutonomousCycleState {
  return {
    cycleId: "cycle-1",
    runId: "run-1",
    cycleNumber: 1,
    maxCycles: 2,
    status: "RUNNING",
    lastAction: "DISPATCH",
    lastReason: "TEST",
    attempts: 1,
    updatedAt: "2026-09-14T10:00:00.000Z",
    ...overrides,
  };
}

describe("guardAutonomousCycleDispatch", () => {
  it("allows dispatch when no persisted state exists", () => {
    expect(guardAutonomousCycleDispatch(context(), null)).toEqual({
      allowed: true,
      reason: "ACTIVE_CYCLE",
    });
  });

  it("rejects a mismatched cycle id", () => {
    expect(guardAutonomousCycleDispatch(context({ cycleId: "cycle-2" }), state())).toEqual({
      allowed: false,
      reason: "CYCLE_ID_MISMATCH",
    });
  });

  it.each(["ACCEPTED", "REVIEW_REQUIRED", "FAILED", "BUDGET_EXCEEDED"] as const)(
    "rejects terminal status %s",
    (status) => {
      expect(guardAutonomousCycleDispatch(context({ cycleId: "cycle-1" }), state({ status }))).toEqual({
        allowed: false,
        reason: "TERMINAL_CYCLE",
      });
    },
  );

  it("rejects a cycle number beyond the persisted budget", () => {
    expect(guardAutonomousCycleDispatch(context({ cycleId: "cycle-1", cycleNumber: 3 }), state({ maxCycles: 2 }))).toEqual({
      allowed: false,
      reason: "BUDGET_EXCEEDED",
    });
  });

  it("allows an active cycle inside the budget", () => {
    expect(guardAutonomousCycleDispatch(context({ cycleId: "cycle-1", cycleNumber: 2 }), state())).toEqual({
      allowed: true,
      reason: "ACTIVE_CYCLE",
    });
  });
});
