import { createHash } from "node:crypto";
import { validateDevelopmentPatchContent } from "@/lib/development-patch-content-validator";

export const DEVELOPMENT_ISOLATED_WORKSPACE_VERSION = "development-isolated-workspace-v1" as const;

type Json = Record<string, any>;
const record = (value: unknown): Json => value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
const stableHash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

export type IsolatedWorkspaceSimulationResult = {
  valid: boolean;
  status: "ISOLATED_SIMULATION_READY" | "ISOLATED_SIMULATION_BLOCKED";
  version: typeof DEVELOPMENT_ISOLATED_WORKSPACE_VERSION;
  runId: string;
  baseSha: string;
  files: Array<{ path: string; contentHash: string; contentBytes: number }>;
  patchDigest: string | null;
  contentValidation: ReturnType<typeof validateDevelopmentPatchContent>;
  guarantees: { isolated: true; patchApplied: false; repositoryTouched: false; gitTouched: false; databaseTouched: false };
  reasons: string[];
  simulationHash: string;
};

export function simulateIsolatedWorkspace(runInput: unknown, requestInput: unknown, patchInput: unknown): IsolatedWorkspaceSimulationResult {
  const run = record(runInput);
  const request = record(requestInput);
  const trigger = record(request.trigger);
  const target = record(request.target);
  const runId = String(request.developmentRunId || run.developmentRunId || "");
  const baseSha = String(trigger.sha || "");
  const allowedTargets = Array.isArray(target.files) ? target.files.map(String) : [];
  const contentValidation = validateDevelopmentPatchContent(patchInput, allowedTargets);
  const reasons = [...contentValidation.reasons];
  if (!runId) reasons.push("Isolated simulation requires a developmentRunId.");
  if (!/^[0-9a-f]{40}$/i.test(baseSha)) reasons.push("Isolated simulation requires a valid 40-character base commit SHA.");
  const files = contentValidation.files.filter((file): file is { path: string; contentHash: string; contentBytes: number } => Boolean(file.contentHash && file.contentBytes !== null));
  const valid = contentValidation.valid && Boolean(runId) && /^[0-9a-f]{40}$/i.test(baseSha) && reasons.length === 0;
  const core = { version: DEVELOPMENT_ISOLATED_WORKSPACE_VERSION, runId, baseSha, files, patchDigest: contentValidation.patchDigest, valid };
  return {
    ...core,
    status: valid ? "ISOLATED_SIMULATION_READY" : "ISOLATED_SIMULATION_BLOCKED",
    contentValidation,
    guarantees: { isolated: true, patchApplied: false, repositoryTouched: false, gitTouched: false, databaseTouched: false },
    reasons,
    simulationHash: stableHash(core),
  };
}
