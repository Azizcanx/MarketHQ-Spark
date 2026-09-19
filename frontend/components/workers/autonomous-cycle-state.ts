import type { AutonomousCycleAction, AutonomousCycleDecision } from "./autonomous-cycle-controller";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { getAutonomousCycleStore } from "./autonomous-cycle-store";

export type AutonomousCycleState = {
  cycleId: string;
  runId: string;
  cycleNumber: number;
  maxCycles: number;
  status: "RUNNING" | "CONTINUE_RESEARCH" | "DISPATCHED" | "ACCEPTED" | "REVIEW_REQUIRED" | "FAILED" | "BUDGET_EXCEEDED";
  lastAction: AutonomousCycleAction;
  lastReason: string;
  workerTaskId?: string;
  workerStatus?: string;
  attempts: number;
  implementationIntent?: string;
  feedbackRecommendation?: string;
  patchQualityGrade?: string;
  patchQualityScore?: number;
  retryRecommended: boolean;
  nextCycleAllowed: boolean;
  updatedAt: string;
};

function positiveInteger(value: unknown, fallback: number): number { const parsed = typeof value === "number" ? value : Number(value); return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback; }
function qualityFromFeedback(feedback?: WorkerFeedback | null): { grade?: string; score?: number; recommendation?: string } {
  const value = feedback?.nextCycleInput?.patchQuality;
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const quality = value as Record<string, unknown>;
  return { grade: typeof quality.grade === "string" ? quality.grade : undefined, score: typeof quality.score === "number" && Number.isFinite(quality.score) ? quality.score : undefined, recommendation: typeof quality.recommendation === "string" ? quality.recommendation : undefined };
}
export function getAutonomousCycleState(cycleId: string): AutonomousCycleState | null { return getAutonomousCycleStore().get(cycleId); }
export function listAutonomousCycleStates(): AutonomousCycleState[] { return getAutonomousCycleStore().list(500); }
export function recordAutonomousCycleState(input: { cycleId: string; runId: string; cycleNumber?: number; maxCycles?: number; decision: AutonomousCycleDecision; worker?: WorkerRecord | null; feedback?: WorkerFeedback | null }): AutonomousCycleState {
  const worker = input.worker ?? null;
  const previous = getAutonomousCycleStore().get(input.cycleId);
  const quality = qualityFromFeedback(input.feedback);
  const state: AutonomousCycleState = {
    cycleId: input.cycleId, runId: input.runId,
    cycleNumber: positiveInteger(input.cycleNumber, previous?.cycleNumber ?? 1),
    maxCycles: Math.min(positiveInteger(input.maxCycles, previous?.maxCycles ?? 10), 100),
    status: input.decision.action === "STOP_ACCEPTED" ? "ACCEPTED" : input.decision.action === "STOP_REVIEW" ? "REVIEW_REQUIRED" : input.decision.action === "STOP_FAILURE" ? "FAILED" : input.decision.action === "STOP_CYCLE_BUDGET" ? "BUDGET_EXCEEDED" : input.decision.action === "DISPATCH_IMPLEMENTATION" ? "DISPATCHED" : input.decision.action === "CONTINUE_RESEARCH" ? "CONTINUE_RESEARCH" : "RUNNING",
    lastAction: input.decision.action, lastReason: input.decision.reason,
    workerTaskId: worker?.taskId ?? previous?.workerTaskId, workerStatus: worker?.status ?? previous?.workerStatus,
    attempts: input.feedback?.attempts ?? worker?.attempt ?? previous?.attempts ?? 0,
    implementationIntent: input.decision.implementationIntent || previous?.implementationIntent,
    feedbackRecommendation: input.feedback?.recommendation ?? quality.recommendation ?? previous?.feedbackRecommendation,
    patchQualityGrade: quality.grade ?? previous?.patchQualityGrade,
    patchQualityScore: quality.score ?? previous?.patchQualityScore,
    retryRecommended: input.decision.retryRecommended, nextCycleAllowed: input.decision.nextCycleAllowed,
    updatedAt: new Date().toISOString(),
  };
  return getAutonomousCycleStore().upsert(state);
}
export function upsertAutonomousCycleState(state: AutonomousCycleState): AutonomousCycleState { return getAutonomousCycleStore().upsert(state); }
