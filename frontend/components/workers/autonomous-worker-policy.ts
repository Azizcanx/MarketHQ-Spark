export type AutonomousWorkerPolicy = {
  enabled: boolean;
  targetPaths: string[];
  instructions: string;
  validationCommand?: string;
  implementationIntent?: string;
  source: "REQUEST" | "ENVIRONMENT" | "DISABLED";
};

const DEFAULT_INSTRUCTIONS = "Implement only the explicitly requested research implementation change. Do not modify unrelated files, commit, merge, open a PR, access secrets, or enable live execution.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).map((item) => item.trim()).filter(Boolean);
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function envEnabled(value: string | undefined): boolean {
  return ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase());
}

function selectedTask(queueOutput: unknown): Record<string, unknown> {
  if (!isRecord(queueOutput)) return {};
  const queue = isRecord(queueOutput.queue) ? queueOutput.queue : {};
  return isRecord(queue.selectedTask) ? queue.selectedTask : {};
}

export function resolveAutonomousWorkerPolicy(
  request: Record<string, unknown>,
  queueOutput: unknown,
  environment: NodeJS.ProcessEnv = process.env,
): AutonomousWorkerPolicy {
  const selected = selectedTask(queueOutput);
  const metadata = isRecord(selected.metadata) ? selected.metadata : {};
  const enabledByRequest = request.workerEnabled === true;
  const enabledByEnvironment = envEnabled(environment.MARKETHQ_AUTONOMOUS_WORKER_ENABLE);
  const enabled = enabledByRequest || enabledByEnvironment;

  const requestTargets = strings(request.workerTargetPaths);
  const queueTargets = strings(metadata.workerTargetPaths ?? metadata.targetPaths);
  const targetPaths = requestTargets.length ? requestTargets : queueTargets;

  const instructions = text(request.workerInstructions) ?? text(metadata.workerInstructions) ?? DEFAULT_INSTRUCTIONS;
  const validationCommand = text(request.workerValidationCommand) ?? text(metadata.workerValidationCommand ?? metadata.validationCommand);
  const implementationIntent = text(request.implementationIntent) ?? text(metadata.implementationIntent ?? metadata.workerIntent);

  return {
    enabled,
    targetPaths,
    instructions,
    validationCommand,
    implementationIntent,
    source: enabledByRequest ? "REQUEST" : enabledByEnvironment ? "ENVIRONMENT" : "DISABLED",
  };
}
