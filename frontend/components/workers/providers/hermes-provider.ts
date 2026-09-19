import type { WorkerExecutionResult, WorkerLogKind, WorkerProgressCallback, WorkerProvider, WorkerTask } from "../worker-types";

export type HermesProviderOptions = {
  baseUrl?: string;
  apiKey?: string;
  model?: string;
  sessionId?: string;
};

const now = () => new Date().toISOString();

function extractRunOutput(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const run = payload as Record<string, unknown>;
  const output = run.output;
  if (typeof output === "string") return output.trim();
  if (Array.isArray(output)) {
    const texts: string[] = [];
    for (const item of output) {
      if (!item || typeof item !== "object") continue;
      const record = item as Record<string, unknown>;
      if (typeof record.text === "string") texts.push(record.text);
      const content = record.content;
      if (Array.isArray(content)) {
        for (const part of content) {
          if (part && typeof part === "object" && typeof (part as Record<string, unknown>).text === "string") {
            texts.push(String((part as Record<string, unknown>).text));
          }
        }
      }
    }
    return texts.join("\n").trim();
  }
  return "";
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text();
  try {
    const parsed = JSON.parse(text) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return { raw: text };
  }
}

function truncate(text: string, max = 300): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return "";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

// Hermes runs SSE frames are `data: {json}\n\n` (event name lives inside the JSON's
// `event` field). Split on the blank-line boundary and parse each `data:` payload.
function parseSseFrames(buffer: string, onEvent: (evt: Record<string, unknown>) => void): string {
  let idx: number;
  while ((idx = buffer.indexOf("\n\n")) !== -1) {
    const frame = buffer.slice(0, idx);
    buffer = buffer.slice(idx + 2);
    for (const line of frame.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const parsed = JSON.parse(payload);
        if (parsed && typeof parsed === "object") onEvent(parsed as Record<string, unknown>);
      } catch {
        // skip malformed frame
      }
    }
  }
  return buffer;
}

export class HermesProvider implements WorkerProvider {
  readonly id = "hermes" as const;
  constructor(private readonly options: HermesProviderOptions = {}) {}

  async execute(task: WorkerTask, onProgress?: WorkerProgressCallback): Promise<WorkerExecutionResult> {
    const startedAt = now();
    const startedMs = Date.now();
    const baseUrl = (this.options.baseUrl ?? process.env.MARKETHQ_HERMES_API_URL ?? "http://127.0.0.1:8642").replace(/\/$/, "");
    const apiKey = this.options.apiKey ?? process.env.MARKETHQ_HERMES_API_KEY;
    const model = this.options.model ?? process.env.MARKETHQ_HERMES_MODEL ?? "hermes-agent";
    const sessionId = this.options.sessionId ?? process.env.MARKETHQ_HERMES_SESSION_ID;
    const runProvider = process.env.MARKETHQ_HERMES_RUN_PROVIDER ?? "nous";
    const runModel = process.env.MARKETHQ_HERMES_RUN_MODEL ?? "deepseek/deepseek-v4-pro";
    const jobId = `mhq-hermes-${task.taskId}`;
    const safety = { researchOnly: true, mainRepoMutation: false, automaticMerge: false, automaticPr: false, isolatedWorktree: false } as const;
    const emit = (kind: WorkerLogKind, message: string) => { if (onProgress && message) onProgress({ kind, message }); };

    if (!apiKey) return this.failed(task, jobId, startedAt, startedMs, "MARKETHQ_HERMES_API_KEY is not configured.", safety);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), task.timeoutMs ?? 120_000);
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      };
      if (sessionId) headers["X-Hermes-Session-Id"] = sessionId;

      // Hermes Runs API gives MarketHQ a durable run id and a status surface,
      // while Hermes itself owns the agent loop and its tool execution.
      const body: Record<string, unknown> = {
        model: runModel,
        provider: runProvider,
        input: [
          "You are the Hermes execution agent for MarketHQ.",
          "Operate only on research and implementation analysis requested by MarketHQ.",
          "Do not trade, call brokers, move money, create automatic PRs, merge, or mutate the production main branch.",
          "Prefer inspection, diagnosis, implementation planning, validation, and evidence collection.",
          `Task: ${task.title}`,
          `Run ID: ${task.runId}`,
          `Target paths: ${task.targetPaths.length ? task.targetPaths.join(", ") : "none specified"}`,
          "",
          task.instructions,
        ].join("\n"),
        instructions: "Return a concise execution summary with actions taken, evidence, validation status, blockers, and next recommended step.",
      };
      if (sessionId) body.session_id = sessionId;

      const response = await fetch(`${baseUrl}/v1/runs`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const created = await readJson(response);
      if (!response.ok) {
        return this.failed(task, jobId, startedAt, startedMs, `Hermes Runs API ${response.status}: ${JSON.stringify(created).slice(0, 1500)}`, safety);
      }

      const runId = typeof created.run_id === "string" ? created.run_id : jobId;
      emit("system", `dispatched · run ${runId}`);

      // Best-effort live event stream: forward agent activity as log lines while the
      // status poll (below) remains the source of truth for terminal state and output.
      const streamPromise = (async () => {
        try {
          const streamResponse = await fetch(`${baseUrl}/v1/runs/${encodeURIComponent(runId)}/events`, {
            method: "GET",
            headers: { Authorization: `Bearer ${apiKey}`, ...(sessionId ? { "X-Hermes-Session-Id": sessionId } : {}) },
            signal: controller.signal,
            cache: "no-store",
          });
          if (!streamResponse.ok || !streamResponse.body) return;
          const reader = streamResponse.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let deltaBuffer = "";
          const flushDelta = () => {
            if (!deltaBuffer) return;
            const text = deltaBuffer;
            deltaBuffer = "";
            emit("delta", text);
          };
          const handleEvent = (evt: Record<string, unknown>) => {
            const name = typeof evt.event === "string" ? evt.event : "";
            if (name === "message.delta") {
              if (typeof evt.delta === "string") deltaBuffer += evt.delta;
              if (deltaBuffer.length >= 200) flushDelta();
            } else {
              flushDelta();
              if (name === "tool.started") {
                emit("tool", `▸ ${String(evt.tool ?? "tool")}${evt.preview ? ` · ${truncate(String(evt.preview))}` : ""}`);
              } else if (name === "tool.completed") {
                emit("tool", `✓ ${String(evt.tool ?? "tool")}${typeof evt.duration === "number" ? ` (${evt.duration}s)` : ""}${evt.error ? " · error" : ""}`);
              } else if (name === "reasoning.available") {
                emit("reasoning", truncate(typeof evt.text === "string" ? evt.text : "", 500));
              } else if (name.startsWith("run.")) {
                emit("system", name);
              } else if (name === "approval.request") {
                emit("system", "approval required");
              } else if (name.startsWith("subagent.")) {
                emit("system", name);
              }
            }
          };
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            buffer = parseSseFrames(buffer, handleEvent);
          }
          flushDelta();
        } catch {
          // streaming is best-effort; polling still drives completion
        }
      })();

      const deadline = Date.now() + (task.timeoutMs ?? 120_000);
      let latest: Record<string, unknown> = created;

      while (Date.now() < deadline) {
        const statusResponse = await fetch(`${baseUrl}/v1/runs/${encodeURIComponent(runId)}`, {
          method: "GET",
          headers: { Authorization: `Bearer ${apiKey}`, ...(sessionId ? { "X-Hermes-Session-Id": sessionId } : {}) },
          signal: controller.signal,
          cache: "no-store",
        });
        latest = await readJson(statusResponse);
        if (!statusResponse.ok) {
          return this.failed(task, String(runId), startedAt, startedMs, `Hermes run status ${statusResponse.status}: ${JSON.stringify(latest).slice(0, 1500)}`, safety);
        }

        const status = typeof latest.status === "string" ? latest.status.toLowerCase() : "";
        if (status === "completed" || status === "failed" || status === "cancelled") break;
        await new Promise((resolve) => setTimeout(resolve, 1_000));
      }

      // Let the event stream flush any final lines before we settle.
      await streamPromise.catch(() => undefined);

      const status = typeof latest.status === "string" ? latest.status.toLowerCase() : "completed";
      const output = extractRunOutput(latest);
      if (status !== "completed") {
        return this.failed(task, String(runId), startedAt, startedMs, output || `Hermes run ended with status ${status}.`, safety);
      }

      return {
        success: true,
        status: "NO_PATCH",
        jobId: String(runId),
        runId: task.runId,
        taskId: task.taskId,
        changedFiles: [],
        diff: output || JSON.stringify(latest).slice(0, 20_000),
        validation: { attempted: false, passed: false },
        startedAt,
        completedAt: now(),
        durationMs: Date.now() - startedMs,
        safety,
      };
    } catch (error) {
      return this.failed(task, jobId, startedAt, startedMs, error instanceof Error ? error.message : String(error), safety);
    } finally {
      clearTimeout(timeout);
      controller.abort();
    }
  }

  private failed(task: WorkerTask, jobId: string, startedAt: string, startedMs: number, error: string, safety: WorkerExecutionResult["safety"]): WorkerExecutionResult {
    return { success: false, status: "FAILED", jobId, runId: task.runId, taskId: task.taskId, changedFiles: [], error, startedAt, completedAt: now(), durationMs: Date.now() - startedMs, safety };
  }
}
