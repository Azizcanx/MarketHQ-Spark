import path from "node:path";

export type DevelopmentPatchGuardResult = {
  valid: boolean;
  reasons: string[];
  files: string[];
  allowedTargets: string[];
};

const normalize = (value: unknown): string => String(value || "").trim().replace(/\\/g, "/").replace(/^\.\//, "");

const isSafeRelativePath = (value: string): boolean => {
  if (!value || value.startsWith("/") || /^[A-Za-z]:\//.test(value)) return false;
  const normalized = path.posix.normalize(value);
  return normalized !== "." && normalized !== ".." && !normalized.startsWith("../") && !normalized.includes("/../");
};

export function validateDevelopmentPatch(filesInput: unknown, allowedTargets: string[] = []): DevelopmentPatchGuardResult {
  const files = Array.isArray(filesInput) ? filesInput : [];
  const allowed = allowedTargets.map(normalize).filter(Boolean);
  const reasons: string[] = [];
  const paths: string[] = [];

  if (!Array.isArray(filesInput)) reasons.push("Patch files must be an array.");

  for (const raw of files) {
    const item = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
    const filePath = normalize(item.path);
    if (!filePath) {
      reasons.push("Every patch file must declare a path.");
      continue;
    }
    if (!isSafeRelativePath(filePath)) {
      reasons.push(`Unsafe patch path: ${filePath}`);
      continue;
    }
    if (paths.includes(filePath)) {
      reasons.push(`Duplicate patch path: ${filePath}`);
      continue;
    }
    paths.push(filePath);
    if (allowed.length && !allowed.includes(filePath)) reasons.push(`Patch path is outside the explicit target scope: ${filePath}`);
  }

  if (!allowed.length) reasons.push("Patch validation requires explicit allowed target paths.");
  return { valid: reasons.length === 0 && paths.length > 0, reasons, files: paths, allowedTargets: allowed };
}
