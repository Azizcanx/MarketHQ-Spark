import type { WorkerEvidence, WorkerEvaluation, WorkerRecord, WorkerStatus } from "./worker-types";

export function evaluateWorkerEvidence(
  record: WorkerRecord | string,
  evidence: WorkerEvidence[],
  finalStatus?: WorkerStatus,
): WorkerEvaluation {
  const taskId = typeof record === "string" ? record : record.taskId;
  const runId = typeof record === "string" ? (evidence[0]?.runId ?? "") : record.runId;
  const status = finalStatus ?? (typeof record === "string" ? (evidence.at(-1)?.status ?? "REVIEW_REQUIRED") : record.status);
  const attempts = Math.max(typeof record === "string" ? 0 : record.attempt, evidence.length || 1);
  const patchReadyAttempts = evidence.filter((item) => item.status === "PATCH_READY").length;
  const validationPasses = evidence.filter((item) => item.validation?.attempted && item.validation.passed).length;
  const validationFailures = evidence.filter((item) => item.validation?.attempted && !item.validation.passed).length;
  const failureCount = evidence.filter((item) => !item.success || ["FAILED", "TIMEOUT", "PATCH_REJECTED"].includes(item.status)).length;
  const changedFiles = [...new Set(evidence.flatMap((item) => item.changedFiles))];
  const hasDiff = evidence.some((item) => Boolean(item.diff));
  const evidenceQuality: WorkerEvaluation["evidenceQuality"] = validationPasses > 0 && hasDiff ? "HIGH" : validationPasses > 0 || hasDiff ? "MEDIUM" : "LOW";
  const accepted = status === "ACCEPTED";
  const recommendation: WorkerEvaluation["recommendation"] = accepted ? "ACCEPT" : status === "NO_PATCH" ? "NO_PATCH" : status === "REVIEW_REQUIRED" ? "REVIEW" : "FEED_BACK";
  return { taskId, runId, attempts, finalStatus: status, accepted, patchReadyAttempts, validationPasses, validationFailures, failureCount, changedFiles, evidenceQuality, recommendation, evaluatedAt: new Date().toISOString() };
}
