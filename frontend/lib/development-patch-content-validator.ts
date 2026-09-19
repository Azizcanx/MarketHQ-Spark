import { createHash } from "node:crypto";
import { validateDevelopmentPatch } from "@/lib/development-patch-guard";

export const DEVELOPMENT_PATCH_CONTENT_VALIDATOR_VERSION = "development-patch-content-v1" as const;

type Json = Record<string, any>;

const record = (value: unknown): Json => value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
const normalizePath = (value: unknown) => String(value || "").trim().replace(/\\/g, "/").replace(/^\.\//, "");
const stableHash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

export type PatchContentValidationResult = {
  valid: boolean;
  status: "CONTENT_VALID" | "CONTENT_VALIDATION_UNAVAILABLE" | "CONTENT_BLOCKED";
  version: typeof DEVELOPMENT_PATCH_CONTENT_VALIDATOR_VERSION;
  files: Array<{ path: string; contentHash: string | null; contentBytes: number | null }>;
  patchDigest: string | null;
  guard: ReturnType<typeof validateDevelopmentPatch>;
  reasons: string[];
};

export function validateDevelopmentPatchContent(input: unknown, allowedTargets: string[] = []): PatchContentValidationResult {
  const patch = record(input);
  const files = Array.isArray(patch.files) ? patch.files : [];
  const guard = validateDevelopmentPatch(files, allowedTargets);
  const normalized: Array<{ path: string; contentHash: string | null; contentBytes: number | null }> = [];
  const reasons = [...guard.reasons];
  let unavailable = false;

  for (const raw of files) {
    const item = record(raw);
    const path = normalizePath(item.path);
    if (!path) continue;
    const hasContent = typeof item.content === "string";
    if (!hasContent) {
      unavailable = true;
      normalized.push({ path, contentHash: null, contentBytes: null });
      continue;
    }
    const content = item.content as string;
    normalized.push({ path, contentHash: createHash("sha256").update(content, "utf8").digest("hex"), contentBytes: Buffer.byteLength(content, "utf8") });
  }

  if (!files.length) reasons.push("Patch must contain at least one file entry.");
  if (unavailable) reasons.push("Patch content is required for deterministic content validation; structural file validation alone is insufficient.");

  const digest = unavailable || !guard.valid || normalized.length !== files.length
    ? null
    : stableHash(normalized.slice().sort((a, b) => a.path.localeCompare(b.path)));
  const valid = guard.valid && !unavailable && normalized.length === files.length && reasons.length === 0;

  return {
    valid,
    status: valid ? "CONTENT_VALID" : unavailable ? "CONTENT_VALIDATION_UNAVAILABLE" : "CONTENT_BLOCKED",
    version: DEVELOPMENT_PATCH_CONTENT_VALIDATOR_VERSION,
    files: normalized,
    patchDigest: digest,
    guard,
    reasons,
  };
}
