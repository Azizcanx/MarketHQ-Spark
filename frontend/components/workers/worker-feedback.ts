import type { WorkerEvidence, WorkerEvaluation, WorkerFeedback, WorkerRecord } from "./worker-types";
import type { WorkerPatchQuality } from "./patch-quality-v2";

export function buildWorkerFeedback(
  record: WorkerRecord | WorkerEvaluation,
  evaluation: WorkerEvaluation | WorkerEvidence[],
  patchQuality?: WorkerPatchQuality | null,
): WorkerFeedback {
  const isEvaluation = "finalStatus" in record;
  const resolvedEvaluation = isEvaluation ? record : evaluation as WorkerEvaluation;
  const evidence = isEvaluation ? evaluation as WorkerEvidence[] : [];
  const status = resolvedEvaluation.finalStatus;
  const taskId = resolvedEvaluation.taskId;
  const runId = resolvedEvaluation.runId || evidence[0]?.runId || "";
  const error = isEvaluation ? undefined : (record as WorkerRecord).error;
  const qualityRecommendation = patchQuality?.recommendation;
  const recommendation: WorkerFeedback["recommendation"] = qualityRecommendation ?? resolvedEvaluation.recommendation;
  const accepted = recommendation === "ACCEPT" && resolvedEvaluation.accepted;
  const kind: WorkerFeedback["kind"] = accepted
    ? "IMPLEMENTATION_VERIFIED"
    : status === "NO_PATCH"
      ? "IMPLEMENTATION_NO_PATCH"
      : recommendation === "REVIEW"
        ? "IMPLEMENTATION_REVIEW"
        : "IMPLEMENTATION_BLOCKED";
  const summary = accepted
    ? `Worker implementation accepted after ${resolvedEvaluation.attempts} attempt(s).`
    : status === "NO_PATCH"
      ? "Worker completed without a patch."
      : patchQuality?.reason ?? error ?? `Worker implementation ended with ${status}.`;
  const evidenceQuality: WorkerFeedback["evidenceQuality"] =
    patchQuality?.evidenceQuality === "NONE" ? "LOW" : (patchQuality?.evidenceQuality ?? resolvedEvaluation.evidenceQuality);
  return {
    taskId,
    runId,
    kind,
    recommendation,
    attempts: resolvedEvaluation.attempts,
    validationFailures: resolvedEvaluation.validationFailures,
    validationPasses: resolvedEvaluation.validationPasses,
    failureCount: resolvedEvaluation.failureCount,
    changedFiles: resolvedEvaluation.changedFiles,
    evidenceQuality,
    learningEligible: false,
    researchImpact: "IMPLEMENTATION_ONLY",
    summary,
    failureDetails: [
      ...(error ? [error] : []),
      ...(patchQuality && patchQuality.recommendation !== "ACCEPT" ? [patchQuality.reason] : []),
    ],
    nextCycleInput: {
      implementationStatus: kind,
      implementationIntent: "IMPLEMENTATION_ONLY",
      recommendation,
      retryRecommended: recommendation === "FEED_BACK",
      changedFiles: resolvedEvaluation.changedFiles,
      patchQuality: patchQuality
        ? {
            score: patchQuality.score,
            grade: patchQuality.grade,
            status: patchQuality.status,
            scopeCompliant: patchQuality.scopeCompliant,
            hasPatch: patchQuality.hasPatch,
            validationAttempted: patchQuality.validationAttempted,
            validationPassed: patchQuality.validationPassed,
            validationFailures: patchQuality.validationFailures,
            unsafeEvidence: patchQuality.unsafeEvidence,
            evidenceQuality: patchQuality.evidenceQuality,
            recommendation: patchQuality.recommendation,
            reason: patchQuality.reason,
          }
        : undefined,
    },
    createdAt: new Date().toISOString(),
  };
}
