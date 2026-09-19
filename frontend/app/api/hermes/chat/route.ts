import { randomUUID } from "node:crypto";
import { runHermesPreflight } from "@/components/workers/hermes-preflight";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type JsonRecord = Record<string, unknown>;
type ChatRequest = { message?: unknown; sessionId?: unknown };

type ManagerDirective = {
  action: "CHAT" | "RUN_RESEARCH" | "WORKER_TASK";
  task: string;
  summary: string;
  targetPaths: string[];
  implementationIntent: "NONE" | "IMPLEMENT" | "ITERATE" | "EXPERIMENT" | "RESEARCH_AND_IMPLEMENT";
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function extractResponseText(payload: unknown): string {
  if (!isRecord(payload)) return "";
  const direct = payload.output_text;
  if (typeof direct === "string" && direct.trim()) return direct.trim();

  const output = payload.output;
  if (typeof output === "string" && output.trim()) return output.trim();
  if (Array.isArray(output)) {
    const parts: string[] = [];
    for (const item of output) {
      if (typeof item === "string" && item.trim()) {
        parts.push(item.trim());
        continue;
      }
      if (!isRecord(item)) continue;
      const directText = item.text;
      if (typeof directText === "string" && directText.trim()) parts.push(directText.trim());
      const content = item.content;
      if (!Array.isArray(content)) continue;
      for (const part of content) {
        if (!isRecord(part)) continue;
        const text = part.text;
        if (typeof text === "string" && text.trim()) parts.push(text.trim());
      }
    }
    if (parts.length) return parts.join("\n\n");
  }
  return "";
}

function extractDirective(text: string): { reply: string; directive: ManagerDirective | null } {
  const match = text.match(/<MARKETHQ_ACTION>\s*([\s\S]*?)\s*<\/MARKETHQ_ACTION>/i);
  if (!match) return { reply: text.trim(), directive: null };
  try {
    const parsed = JSON.parse(match[1]) as Partial<ManagerDirective>;
    const action: ManagerDirective["action"] =
      parsed.action === "RUN_RESEARCH" || parsed.action === "WORKER_TASK" || parsed.action === "CHAT" ? parsed.action : "CHAT";
    const intent: ManagerDirective["implementationIntent"] =
      parsed.implementationIntent === "IMPLEMENT" || parsed.implementationIntent === "ITERATE" || parsed.implementationIntent === "EXPERIMENT" || parsed.implementationIntent === "RESEARCH_AND_IMPLEMENT"
        ? parsed.implementationIntent
        : "NONE";
    return {
      reply: text.replace(match[0], "").trim(),
      directive: {
        action,
        task: typeof parsed.task === "string" ? parsed.task.trim() : "",
        summary: typeof parsed.summary === "string" ? parsed.summary.trim() : "",
        targetPaths: Array.isArray(parsed.targetPaths)
          ? parsed.targetPaths
              .filter((v): v is string => typeof v === "string" && v.trim().length > 0)
              .map((v) => v.trim())
              .slice(0, 12)
          : [],
        implementationIntent: intent,
      },
    };
  } catch {
    return { reply: text.trim(), directive: null };
  }
}

/** Keep model input intentionally small. Snapshot data is for manager awareness, not for dumping the whole dashboard payload into every request. */
function compactValue(value: unknown, depth = 0): unknown {
  if (depth >= 4) return "[truncated]";
  if (value === null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") return value.length > 500 ? `${value.slice(0, 500)}…` : value;
  if (Array.isArray(value)) {
    const items = value.slice(0, 8).map((item) => compactValue(item, depth + 1));
    if (value.length > 8) items.push(`[${value.length - 8} more items]`);
    return items;
  }
  if (isRecord(value)) {
    const priority = ["status", "health", "summary", "message", "error", "errors", "warnings", "agents", "activeAgents", "runs", "activeRuns", "research", "queue", "brain", "learning", "latestRun", "latestResult", "nextAction", "nextStep"];
    const keys = Object.keys(value).sort((a, b) => (priority.indexOf(a) === -1 ? 999 : priority.indexOf(a)) - (priority.indexOf(b) === -1 ? 999 : priority.indexOf(b)));
    const result: JsonRecord = {};
    for (const key of keys.slice(0, 36)) result[key] = compactValue(value[key], depth + 1);
    if (keys.length > 36) result._omittedKeys = keys.length - 36;
    return result;
  }
  return String(value);
}

function managerContextText(value: unknown, maxChars = 12000): string {
  const compact = compactValue(value);
  const serialized = JSON.stringify(compact);
  if (serialized.length <= maxChars) return serialized;
  return `${serialized.slice(0, maxChars)}…`;
}

async function getMarketContext(): Promise<JsonRecord> {
  const base = process.env.MARKETHQ_FRONTEND_URL?.replace(/\/+$/, "") || "http://127.0.0.1:3000";
  try {
    const response = await fetch(`${base}/api/snapshot`, { cache: "no-store", headers: { Accept: "application/json" } });
    const body = await response.json().catch(() => null);
    if (response.ok && isRecord(body)) return body;
  } catch {
    // Manager can still operate without live dashboard context.
  }
  return { available: false };
}

async function callHermes(input: string, conversation: string, instructions: string): Promise<{ text: string; raw: JsonRecord }> {
  const baseUrl = (process.env.MARKETHQ_HERMES_API_URL ?? "http://127.0.0.1:8642").replace(/\/$/, "");
  const apiKey = process.env.MARKETHQ_HERMES_API_KEY;
  const model = process.env.MARKETHQ_HERMES_MODEL ?? "hermes-agent";
  if (!apiKey) throw new Error("MARKETHQ_HERMES_API_KEY is not configured.");

  const headers: Record<string, string> = {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  };
  headers["X-Hermes-Session-Id"] = conversation;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(`${baseUrl}/v1/runs`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model,
        input,
        instructions,
        session_id: conversation,
      }),
      signal: controller.signal,
      cache: "no-store",
    });
    const createdText = await response.text();
    const created = (() => {
      try {
        const parsed = JSON.parse(createdText) as unknown;
        return isRecord(parsed) ? parsed : { raw: createdText };
      } catch {
        return { raw: createdText };
      }
    })();
    if (!response.ok) throw new Error(`Hermes Runs API ${response.status}: ${JSON.stringify(created).slice(0, 1500)}`);

    const runId = typeof created.run_id === "string" ? created.run_id : typeof created.id === "string" ? created.id : "";
    if (!runId) return { text: extractResponseText(created), raw: created };

    const deadline = Date.now() + 120_000;
    let latest = created;
    while (Date.now() < deadline) {
      const statusResponse = await fetch(`${baseUrl}/v1/runs/${encodeURIComponent(runId)}`, {
        method: "GET",
        headers: { Authorization: `Bearer ${apiKey}`, "X-Hermes-Session-Id": conversation },
        signal: controller.signal,
        cache: "no-store",
      });
      const statusText = await statusResponse.text();
      try {
        const parsed = JSON.parse(statusText) as unknown;
        latest = isRecord(parsed) ? parsed : { raw: statusText };
      } catch {
        latest = { raw: statusText };
      }
      if (!statusResponse.ok) throw new Error(`Hermes run status ${statusResponse.status}: ${JSON.stringify(latest).slice(0, 1500)}`);

      const status = typeof latest.status === "string" ? latest.status.toLowerCase() : "";
      if (status === "completed" || status === "failed" || status === "cancelled") break;
      await new Promise((resolve) => setTimeout(resolve, 750));
    }

    const status = typeof latest.status === "string" ? latest.status.toLowerCase() : "completed";
    const output = extractResponseText(latest);
    if (status !== "completed") throw new Error(`Hermes run ended with status ${status || "unknown"}${output ? `: ${output.slice(0, 1000)}` : ""}`);
    return { text: output, raw: latest };
  } finally {
    clearTimeout(timeout);
  }
}

async function runMarketResearch(message: string, context: JsonRecord): Promise<JsonRecord> {
  const base = process.env.MARKETHQ_FRONTEND_URL?.replace(/\/+$/, "") || "http://127.0.0.1:3000";
  const response = await fetch(`${base}/api/agents/orchestrator`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ input: { managerRequest: message, managerContext: context }, cycleId: `hermes-manager-${randomUUID()}`, cycleNumber: 1, maxCycles: 1, workerEnabled: false }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !isRecord(data)) throw new Error(`MarketHQ orchestrator HTTP ${response.status}`);
  return data;
}

async function dispatchWorker(message: string, directive: ManagerDirective, context: JsonRecord): Promise<JsonRecord> {
  const base = process.env.MARKETHQ_FRONTEND_URL?.replace(/\/+$/, "") || "http://127.0.0.1:3000";
  const response = await fetch(`${base}/api/workers`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ runId: `hermes-manager-${randomUUID()}`, decision: { action: directive.action, summary: directive.summary, request: message }, instructions: directive.task || message, targetPaths: directive.targetPaths, implementationIntent: directive.implementationIntent, timeframe: "1d", queueTask: { title: directive.task || message, metadata: { source: "hermes-manager", managerContext: context } }, provider: "hermes" }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !isRecord(data)) throw new Error(`Worker gateway HTTP ${response.status}`);
  return data;
}

const managerInstructions = `You are Hermes, the personal manager for MarketHQ Research OS. Speak naturally in Turkish, like a capable manager talking with the owner. Understand vague requests, ask only when an essential detail is missing, and otherwise take responsibility for planning the next step.

You have three execution modes:
1) CHAT: answer, explain, inspect status, discuss architecture, or plan without executing a MarketHQ run.
2) RUN_RESEARCH: when the user asks you to araştır, başlat, dene, test et, çalıştır the MarketHQ research team. This action is research-only.
3) WORKER_TASK: when the user explicitly asks to implement/fix/change something in the codebase. Identify bounded targetPaths from the request. Never claim a code change happened unless the worker gateway confirms it.

Rules:
- You are the manager, not a passive chatbot. State what you understood and the next action.
- Use the supplied compact live MarketHQ manager context when it helps.
- Research actions may be started directly.
- Implementation actions require an explicit implementation intent and bounded target paths; keep automatic merge, PR creation, broker execution, and live execution disabled.
- Do not invent results, files, metrics, or agent activity.
- At the very end append exactly one machine block, hidden from the user by the UI:
<MARKETHQ_ACTION>{"action":"CHAT|RUN_RESEARCH|WORKER_TASK","task":"...","summary":"...","targetPaths":[],"implementationIntent":"NONE|IMPLEMENT|ITERATE|EXPERIMENT|RESEARCH_AND_IMPLEMENT"}</MARKETHQ_ACTION>`;

export async function GET() {
  const preflight = await runHermesPreflight();
  return Response.json({ success: true, preflight, manager: true, conversation: "stateful_named_conversation" });
}

export async function POST(request: Request) {
  let body: ChatRequest;
  try { body = (await request.json()) as ChatRequest; }
  catch { return Response.json({ success: false, error: "Geçersiz JSON." }, { status: 400 }); }

  const message = typeof body.message === "string" ? body.message.trim() : "";
  if (!message) return Response.json({ success: false, error: "Mesaj boş olamaz." }, { status: 400 });
  if (message.length > 12_000) return Response.json({ success: false, error: "Mesaj 12.000 karakteri aşamaz." }, { status: 413 });

  const preflight = await runHermesPreflight();
  if (!preflight.enabled || !preflight.configured || !preflight.reachable) return Response.json({ success: false, error: preflight.error ?? "Hermes hazır değil.", preflight }, { status: 503 });

  const requestedSession: string = typeof body.sessionId === "string" && body.sessionId.trim() ? body.sessionId.trim() : `manager-${randomUUID()}`;
  const conversation = `markethq-manager-${requestedSession.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 96)}`;
  const context = await getMarketContext();
  const compactContext = managerContextText(context, 12000);

  try {
    const first = await callHermes(`Owner request:\n${message}\n\nCompact live MarketHQ manager context:\n${compactContext}`, conversation, managerInstructions);
    const parsed = extractDirective(first.text);
    const directive: ManagerDirective = parsed.directive ?? { action: "CHAT", task: "", summary: "", targetPaths: [], implementationIntent: "NONE" };
    let execution: JsonRecord | null = null;

    if (directive.action === "RUN_RESEARCH") execution = await runMarketResearch(directive.task || message, context);
    else if (directive.action === "WORKER_TASK") {
      if (directive.implementationIntent === "NONE" || directive.targetPaths.length === 0) return Response.json({ success: true, reply: parsed.reply || "Bunu kod tarafında yapmak için hangi bölüm/dosya üzerinde çalışacağımı netleştirmem gerekiyor.", sessionId: requestedSession, conversation, action: directive, execution: null, preflight });
      execution = await dispatchWorker(message, directive, context);
    }

    if (execution) {
      const followUp = await callHermes(`Action completed. User request: ${message}\n\nAction: ${JSON.stringify(directive)}\n\nCompact execution result:\n${managerContextText(execution, 16000)}\n\nRespond to the owner in natural Turkish: what actually happened, current status, important failures, and next step. Do not invent success.`, conversation, managerInstructions);
      return Response.json({ success: true, reply: extractDirective(followUp.text).reply || followUp.text || parsed.reply, sessionId: requestedSession, conversation, action: directive, execution, runId: typeof followUp.raw.id === "string" ? followUp.raw.id : null, preflight, safety: { researchOnly: true, executionEnabled: false, brokerExecutionEnabled: false, automaticPr: false, automaticMerge: false } });
    }

    return Response.json({ success: true, reply: parsed.reply || first.text || "Hazırım.", sessionId: requestedSession, conversation, action: directive, execution: null, preflight });
  } catch (error) {
    return Response.json({ success: false, error: error instanceof Error ? error.message : String(error), sessionId: requestedSession, conversation, preflight }, { status: 502 });
  }
}
