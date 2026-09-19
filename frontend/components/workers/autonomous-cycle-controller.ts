import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { resolveImplementationIntent, type ImplementationIntent } from "./implementation-intent";
import type { AgentContext } from "../agents/agent-types";

export type AutonomousCycleAction = "CONTINUE_RESEARCH" | "DISPATCH_IMPLEMENTATION" | "STOP_ACCEPTED" | "STOP_REVIEW" | "STOP_FAILURE" | "STOP_CYCLE_BUDGET";
export type AutonomousCycleDecision = { action: AutonomousCycleAction; cycleId: string; reason: string; implementationIntent: ImplementationIntent; retryRecommended: boolean; nextCycleAllowed: boolean };
const DEFAULT_MAX_CYCLES = 10;
function text(value: unknown): string { return typeof value === "string" ? value.trim() : ""; }
function positiveInteger(value: unknown, fallback: number): number { const parsed = typeof value === "number" ? value : Number(value); return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback; }
function terminalFailure(record: WorkerRecord | null | undefined): boolean { return record?.status === "FAILED_FINAL" || record?.status === "TIMEOUT"; }
function qualityRecommendation(feedback: WorkerFeedback | null | undefined): string { const quality = feedback?.nextCycleInput?.patchQuality; if (!quality || typeof quality !== "object") return ""; const recommendation = (quality as Record<string, unknown>).recommendation; return typeof recommendation === "string" ? recommendation : ""; }

/** Decides the next bounded autonomous cycle; it never dispatches or mutates research semantics. */
export function decideNextAutonomousCycle(context: AgentContext, worker: WorkerRecord | null | undefined, feedback: WorkerFeedback | null | undefined): AutonomousCycleDecision {
  const metadata = context.metadata ?? {};
  const cycleId = text(metadata.cycleId) || `cycle-${context.runId}`;
  const currentCycle = positiveInteger(metadata.cycleNumber, 1);
  const maxCycles = Math.min(positiveInteger(metadata.maxCycles, DEFAULT_MAX_CYCLES), 100);
  const intent = resolveImplementationIntent(context);
  const quality = qualityRecommendation(feedback);

  if (currentCycle > maxCycles) return { action: "STOP_CYCLE_BUDGET", cycleId, reason: `AUTONOMOUS_CYCLE_BUDGET_EXCEEDED:${maxCycles}`, implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: false };
  if (!worker) return { action: intent.eligible ? "DISPATCH_IMPLEMENTATION" : "CONTINUE_RESEARCH", cycleId, reason: intent.eligible ? "EXPLICIT_IMPLEMENTATION_INTENT_READY" : "NO_WORKER_RESULT_CONTINUE_RESEARCH", implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: true };
  if (worker.status === "ACCEPTED" && feedback?.recommendation === "ACCEPT" && (quality === "" || quality === "ACCEPT")) return { action: "STOP_ACCEPTED", cycleId, reason: "IMPLEMENTATION_VERIFIED", implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: false };
  if (terminalFailure(worker)) return { action: "STOP_FAILURE", cycleId, reason: "WORKER_TERMINAL_FAILURE", implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: false };

  if (worker.status === "REVIEW_REQUIRED" || worker.status === "PATCH_REJECTED") {
    if (quality === "FEED_BACK" && feedback?.nextCycleInput?.retryRecommended === true) return { action: "DISPATCH_IMPLEMENTATION", cycleId, reason: "PATCH_QUALITY_REQUESTS_BOUNDED_RETRY", implementationIntent: intent.intent, retryRecommended: true, nextCycleAllowed: true };
    return { action: "STOP_REVIEW", cycleId, reason: quality === "REVIEW" ? "PATCH_QUALITY_REQUIRES_REVIEW" : "WORKER_REVIEW_REQUIRED", implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: false };
  }

  if (feedback?.nextCycleInput?.retryRecommended === true) return { action: "DISPATCH_IMPLEMENTATION", cycleId, reason: "WORKER_FEEDBACK_REQUESTS_BOUNDED_RETRY", implementationIntent: intent.intent, retryRecommended: true, nextCycleAllowed: true };
  return { action: "CONTINUE_RESEARCH", cycleId, reason: "NO_TERMINAL_IMPLEMENTATION_DECISION", implementationIntent: intent.intent, retryRecommended: false, nextCycleAllowed: true };
}
