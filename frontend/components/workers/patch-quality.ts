import type { WorkerEvidence, WorkerFeedback, WorkerRecord } from "./worker-types";

export type WorkerPatchQuality = {
  status: "ACCEPTED" | "REVIEW_REQUIRED" | "REJECTED" | "NO_PATCH" | "FAILED" | "UNKNOWN";
  score: number;
  grade: "A" | "B" | "C" | "D" | "F";
  changedFileCount: number;
  targetFileCount: number;
  scopeCompliant: boolean;
  hasPatch: boolean;
  validationAttempted: boolean;
  validationPassed: boolean;
  validationFailures: number;
  unsafeEvidence: boolean;
  evidenceQuality: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  recommendation: "ACCEPT" | "REVIEW" | "FEED_BACK" | "NO_PATCH";
  reason: string;
};

function normalizedPath(value: string): string {
  return value.replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/$/, "");
}

function withinTarget(file: string, target: string): boolean {
  const f = normalizedPath(file);
  const t = normalizedPath(target);
  return f === t || f.startsWith(`${t}/`);
}

export function buildWorkerPatchQuality(
  record: WorkerRecord | null,
  evidence: WorkerEvidence[],
  feedback?: WorkerFeedback | null,
): WorkerPatchQuality {
  const changedFiles = [...new Set(evidence.flatMap((item) => item.changedFiles))];
  const targets = record?.taskId ? [] : [];
  const targetPaths = (record as WorkerRecord & { targetPaths?: string[] } | null)?.targetPaths ?? [];
  const taskTargetPaths = targetPaths.length ? targetPaths : [];
  const validationAttempted = evidence.some((item) => Boolean(item.validation?.attempted));
  const validationPassed = evidence.some((item) => Boolean(item.validation?.attempted && item.validation.passed));
  const validationFailures = evidence.filter((item) => Boolean(item.validation?.attempted && !item.validation.passed)).length;
  const hasPatch = evidence.some((item) => Boolean(item.diff)) || changedFiles.length > 0;
  const unsafeEvidence = evidence.some((item) => Boolean(item.safety && (!item.safety.researchOnly || item.safety.mainRepoMutation || item.safety.automaticPr || item.safety.automaticMerge)));
  const scopeCompliant = taskTargetPaths.length === 0 ? true : changedFiles.every((file) => taskTargetPaths.some((target) => withinTarget(file, target)));
  const evidenceQuality = feedback?.evidenceQuality ?? (validationPassed && hasPatch ? "HIGH" : validationPassed || hasPatch ? "MEDIUM" : evidence.length ? "LOW" : "NONE");
  const status = record?.status === "ACCEPTED" ? "ACCEPTED" : record?.status === "REVIEW_REQUIRED" ? "REVIEW_REQUIRED" : record?.status === "PATCH_REJECTED" ? "REJECTED" : record?.status === "NO_PATCH" ? "NO_PATCH" : record?.status === "FAILED_FINAL" ? "FAILED" : "UNKNOWN";

  let score = 0;
  if (hasPatch) score += 30;
  if (validationAttempted) score += 20;
  if (validationPassed) score += 30;
  if (scopeCompliant) score += 10;
  if (evidenceQuality === "HIGH") score += 10;
  else if (evidenceQuality === "MEDIUM") score += 5;
  if (validationFailures) score -= Math.min(20, validationFailures * 10);
  if (!scopeCompliant) score -= 30;
  if (unsafeEvidence) score = 0;
  score = Math.max(0, Math.min(100, score));

  const grade = score >= 90 ? "A" : score >= 80 ? "B" : score >= 65 ? "C" : score >= 50 ? "D" : "F";
  const recommendation = feedback?.recommendation ?? (unsafeEvidence || !scopeCompliant || status === "REVIEW_REQUIRED" ? "REVIEW" : status === "ACCEPTED" && validationPassed ? "ACCEPT" : status === "NO_PATCH" ? "NO_PATCH" : "FEED_BACK");
  const reason = unsafeEvidence ? "Safety evidence invalidates acceptance." : !scopeCompliant ? "Changed files escaped the declared target scope." : !hasPatch ? "No patch was produced." : validationPassed ? "Patch and validation evidence are present." : validationAttempted ? "Patch exists but validation did not pass." : "Patch exists without validation evidence.";

  return { status, score, grade, changedFileCount: changedFiles.length, targetFileCount: taskTargetPaths.length, scopeCompliant, hasPatch, validationAttempted, validationPassed, validationFailures, unsafeEvidence, evidenceQuality, recommendation, reason };
}
