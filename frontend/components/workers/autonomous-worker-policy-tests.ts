import { resolveAutonomousWorkerPolicy } from "./autonomous-worker-policy";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const request = resolveAutonomousWorkerPolicy(
  { workerEnabled: true, implementationIntent: "ITERATE" },
  { queue: { selectedTask: { metadata: { workerTargetPaths: ["src/strategy"], workerInstructions: "iterate safely", workerValidationCommand: "node --version" } } } },
  process.env,
);
assert(request.enabled, "Request must enable autonomous worker policy.");
assert(request.source === "REQUEST", "Request source was not preserved.");
assert(request.implementationIntent === "ITERATE", "Request intent was not preferred.");
assert(request.targetPaths.length === 1 && request.targetPaths[0] === "src/strategy", "Queue target path fallback failed.");
assert(request.instructions === "iterate safely", "Queue instructions fallback failed.");
assert(request.validationCommand === "node --version", "Queue validation command fallback failed.");

const env = resolveAutonomousWorkerPolicy(
  {},
  { queue: { selectedTask: { metadata: { targetPaths: ["src/feature"], implementationIntent: "IMPLEMENT" } } } },
  { ...process.env, MARKETHQ_AUTONOMOUS_WORKER_ENABLE: "true" },
);
assert(env.enabled && env.source === "ENVIRONMENT", "Environment opt-in failed.");
assert(env.implementationIntent === "IMPLEMENT", "Queue implementation intent fallback failed.");

const disabled = resolveAutonomousWorkerPolicy({}, { queue: { selectedTask: { metadata: {} } } }, process.env);
assert(!disabled.enabled && disabled.source === "DISABLED", "Worker must remain disabled by default.");
assert(disabled.targetPaths.length === 0, "Policy must never infer broad target paths.");

console.log("AUTONOMOUS_WORKER_POLICY_TEST PASS");
