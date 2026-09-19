import { currentWorkerRuntimeGate } from "./runtime-gate";

export type HermesPreflight = {
  enabled: boolean;
  configured: boolean;
  reachable: boolean;
  baseUrl: string | null;
  model: string | null;
  error: string | null;
};

export async function runHermesPreflight(): Promise<HermesPreflight> {
  const enabled = process.env.MARKETHQ_HERMES_WORKER_ENABLE === "true";
  const baseUrl = (process.env.MARKETHQ_HERMES_API_URL ?? "http://127.0.0.1:8642").replace(/\/$/, "");
  const model = process.env.MARKETHQ_HERMES_MODEL ?? "hermes-agent";
  const apiKey = process.env.MARKETHQ_HERMES_API_KEY;
  const gate = currentWorkerRuntimeGate();

  if (!gate.researchOnly || gate.executionEnabled || gate.databaseWriteEnabled || gate.brokerExecutionEnabled || gate.mainRepoMutation || gate.automaticPr || gate.automaticMerge) {
    return { enabled, configured: false, reachable: false, baseUrl: null, model: null, error: "WORKER_RUNTIME_GATE_BLOCKED" };
  }
  if (!enabled) return { enabled: false, configured: false, reachable: false, baseUrl: null, model: null, error: "WORKER_POLICY_DISABLED" };
  if (!apiKey) return { enabled: true, configured: false, reachable: false, baseUrl, model, error: "MARKETHQ_HERMES_API_KEY is not configured." };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    // Hermes exposes GET /v1/models as a cheap authenticated liveness/discovery check.
    // Avoid POST /v1/chat/completions here so a dashboard health check never consumes a model run.
    const response = await fetch(`${baseUrl}/v1/models`, {
      method: "GET",
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: controller.signal,
      cache: "no-store",
    });
    return { enabled: true, configured: true, reachable: response.ok, baseUrl, model, error: response.ok ? null : `Hermes API ${response.status}` };
  } catch (error) {
    return { enabled: true, configured: true, reachable: false, baseUrl, model, error: error instanceof Error ? error.message : String(error) };
  } finally {
    clearTimeout(timeout);
  }
}
