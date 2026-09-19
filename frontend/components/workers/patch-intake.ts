import path from "node:path";
import type { PatchIntakeResult, WorkerExecutionResult, WorkerTask } from "./worker-types";

function normalize(value: string): string {
  return path.normalize(value).replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/$/, "");
}

export function validatePatchScope(task: WorkerTask, changedFiles: string[]): PatchIntakeResult {
  if (!task.targetPaths.length) return { accepted: false, status: "REJECTED", changedFiles, reason: "Worker task has no explicit target paths." };
  const targets = task.targetPaths.map(normalize);
  const violations = changedFiles
    .map(normalize)
    .filter((file) => !targets.some((target) => file === target || file.startsWith(`${target}/`)));
  if (violations.length) return { accepted: false, status: "REJECTED", changedFiles, reason: `Changed files outside target scope: ${violations.join(", ")}` };
  return { accepted: true, status: "ACCEPTED", changedFiles };
}

export function intakePatch(
  task: WorkerTask,
  result: WorkerExecutionResult,
  options: { repoRoot: string },
): PatchIntakeResult {
  if (result.status !== "PATCH_READY") {
    return { accepted: false, status: "REJECTED", changedFiles: result.changedFiles, reason: `Patch intake requires PATCH_READY; received ${result.status}.` };
  }
  if (!result.safety.researchOnly || result.safety.mainRepoMutation || result.safety.automaticPr || result.safety.automaticMerge) {
    return { accepted: false, status: "REJECTED", changedFiles: result.changedFiles, reason: "Worker safety contract rejected the patch." };
  }
  if (!result.safety.isolatedWorktree || !result.worktreePath) {
    return { accepted: false, status: "REJECTED", changedFiles: result.changedFiles, reason: "Patch intake requires an isolated worktree." };
  }
  const repoRoot = path.resolve(options.repoRoot);
  const worktreePath = path.resolve(result.worktreePath);
  const worktreeRoot = path.join(repoRoot, ".markethq-worktrees") + path.sep;
  if (!worktreePath.startsWith(worktreeRoot)) {
    return { accepted: false, status: "REJECTED", changedFiles: result.changedFiles, reason: "Worker worktree is outside the MarketHQ isolated worktree root." };
  }
  if (result.validation?.attempted && !result.validation.passed) {
    return { accepted: false, status: "REJECTED", changedFiles: result.changedFiles, reason: "Patch validation failed." };
  }
  return validatePatchScope(task, result.changedFiles);
}
