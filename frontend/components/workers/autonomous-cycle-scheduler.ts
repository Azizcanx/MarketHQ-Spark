import { randomUUID } from "node:crypto";
import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import type { WorkerDispatchPolicy } from "./autonomous-worker-orchestrator";
import { runOneAutonomousCycle, type AutonomousCycleRunResult } from "./autonomous-cycle-runner";
import { recoverStaleAutonomousCycles } from "./autonomous-cycle-recovery";
import { getAutonomousCycleState } from "./autonomous-cycle-state";
import { guardAutonomousCycleDispatch } from "./autonomous-cycle-guard";
import { getAutonomousCycleStore } from "./autonomous-cycle-store";
import { getAutonomousModeState } from "./autonomous-mode-store";

export type AutonomousCycleSchedulerOptions = { enabled?: boolean; recoveryMaxAgeMs?: number; leaseTtlMs?: number; ownerId?: string };
export type AutonomousCycleSchedulerResult = { executed: boolean; reason: string; recovery: ReturnType<typeof recoverStaleAutonomousCycles>; cycle?: AutonomousCycleRunResult };
function cycleIdFrom(context: AgentContext): string { const candidate = context.metadata?.cycleId; return typeof candidate === "string" && candidate.trim() ? candidate.trim() : `cycle-${context.runId}`; }

/** One invocation performs at most one cycle. Persistent mode is OFF by default. */
export async function runScheduledAutonomousCycle(input: { context: AgentContext; policy: WorkerDispatchPolicy; worker?: WorkerRecord | null; feedback?: WorkerFeedback | null; options?: AutonomousCycleSchedulerOptions }): Promise<AutonomousCycleSchedulerResult> {
  const enabled = input.options?.enabled ?? (process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER === "true" || getAutonomousModeState().enabled);
  const recovery = recoverStaleAutonomousCycles(input.options?.recoveryMaxAgeMs);
  if (!enabled) return { executed: false, reason: "SCHEDULER_DISABLED", recovery };
  const cycleId = cycleIdFrom(input.context);
  const state = getAutonomousCycleState(cycleId);
  const guard = guardAutonomousCycleDispatch(input.context, state);
  if (!guard.allowed) return { executed: false, reason: `GUARD_${guard.reason}`, recovery };
  const ownerId = input.options?.ownerId ?? `scheduler-${randomUUID()}`;
  const leaseStore = getAutonomousCycleStore();
  const lease = leaseStore.acquireLease(cycleId, ownerId, input.options?.leaseTtlMs);
  if (!lease) return { executed: false, reason: "CYCLE_LEASE_HELD", recovery };
  try { return { executed: true, reason: "ONE_BOUNDED_CYCLE_EXECUTED", recovery, cycle: await runOneAutonomousCycle(input) }; }
  finally { leaseStore.releaseLease(cycleId, ownerId); }
}
