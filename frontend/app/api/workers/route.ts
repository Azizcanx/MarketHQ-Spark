import { NextResponse } from "next/server";
import path from "node:path";
import { getWorkerRuntime, getWorkerRecord, getWorkerTask, listWorkerRecords, listWorkerEvidence, listWorkerEvents, listWorkerLogs, getWorkerFeedback, dispatchWorkerTask } from "@/components/workers/dispatch-gateway";
import { currentWorkerRuntimeGate } from "@/components/workers/runtime-gate";
import { runCursorWorkerPreflight } from "@/components/workers/cursor-worker-preflight";
import { runHermesPreflight } from "@/components/workers/hermes-preflight";
import { listAutonomousCycleStates } from "@/components/workers/autonomous-cycle-state";
import { buildWorkerTaskFromResearchDecision } from "@/components/workers/worker-task-builder";
import { buildWorkerPatchQuality } from "@/components/workers/patch-quality-v2";
import type { WorkerTask, WorkerProviderId } from "@/components/workers/worker-types";

export const dynamic = "force-dynamic";

function stringMeta(metadata: Record<string, unknown> | undefined, key: string): string | null {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function decisionSummary(metadata: Record<string, unknown> | undefined): string | null {
  const value = metadata?.researchDecision ?? metadata?.decision;
  if (typeof value === "string" && value.trim()) return value.trim();
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    for (const key of ["action", "decision", "recommendation", "status", "reason"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    }
  }
  return null;
}

function recordView(record: ReturnType<typeof getWorkerRecord>) {
  if (!record) return null;
  const task = getWorkerTask(record.taskId);
  const evidence = listWorkerEvidence(record.taskId);
  const feedback = getWorkerFeedback(record.taskId);
  return {
    ...record,
    patchQuality: buildWorkerPatchQuality(record, task, evidence, feedback),
    task: task ? {
      taskId: task.taskId,
      runId: task.runId,
      title: task.title,
      targetPaths: task.targetPaths,
      provider: task.provider,
      validationCommand: task.validationCommand,
      timeoutMs: task.timeoutMs,
      attempt: task.attempt,
      maxAttempts: task.maxAttempts,
      implementationIntent: task.metadata?.implementationIntent ?? null,
      implementationIntentSource: task.metadata?.implementationIntentSource ?? null,
      researchContext: {
        strategyId: stringMeta(task.metadata, "strategyId"),
        symbol: stringMeta(task.metadata, "symbol"),
        timeframe: stringMeta(task.metadata, "timeframe"),
        researchRunId: stringMeta(task.metadata, "researchRunId") ?? stringMeta(task.metadata, "runId"),
        researchDecision: decisionSummary(task.metadata),
      },
    } : null,
  };
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const taskId = url.searchParams.get("taskId")?.trim() || "";
    const wantPreflight = url.searchParams.get("preflight") === "true";
    const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") || 25)));
    const runtime = getWorkerRuntime();
    const gate = currentWorkerRuntimeGate();
    const records = taskId ? (getWorkerRecord(taskId) ? [getWorkerRecord(taskId)!] : []) : listWorkerRecords(limit);
    const tasks = records.map(recordView);

    let preflight = undefined;
    let hermesPreflight = undefined;
    if (wantPreflight) {
      const repoRoot = path.resolve(process.env.MARKETHQ_REPO_ROOT ?? path.resolve(process.cwd(), ".."));
      const task: WorkerTask = taskId && getWorkerTask(taskId)
        ? getWorkerTask(taskId)!
        : { taskId: "preflight", runId: "preflight", title: "Cursor Worker Preflight", instructions: "Preflight only.", targetPaths: ["frontend"], provider: "cursor", maxAttempts: 1, metadata: { mutationAuthorized: false, automaticPr: false, automaticMerge: false } };
      preflight = await runCursorWorkerPreflight({ repoRoot, worktreeRoot: path.join(repoRoot, ".markethq-worktrees"), task, requireAuthentication: true });
      hermesPreflight = await runHermesPreflight();
    }

    const cycles = listAutonomousCycleStates().slice(0, limit);
    const selectedCycleId = url.searchParams.get("cycleId")?.trim() || "";

    return NextResponse.json({
      success: true,
      api: "MARKETHQ_WORKER_STATUS_V7",
      generatedAt: new Date().toISOString(),
      runtime: { enabled: runtime.isEnabled, configuredEnabled: runtime.isEnabled, executionGate: gate, maxConcurrency: runtime.concurrencyLimit, defaultTimeoutMs: runtime.timeoutLimitMs, defaultMaxAttempts: runtime.attemptLimit },
      records: tasks,
      evidence: taskId ? listWorkerEvidence(taskId) : [],
      events: taskId ? listWorkerEvents(taskId) : [],
      logs: taskId ? listWorkerLogs(taskId) : [],
      latestFeedback: taskId ? getWorkerFeedback(taskId) : null,
      cycles,
      selectedCycle: selectedCycleId ? cycles.find((cycle) => cycle.cycleId === selectedCycleId) ?? null : null,
      preflight,
      hermesPreflight,
      safety: { researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, mainRepoMutation: false, automaticPr: false, automaticMerge: false },
      providers: {
        hermesEnabled: process.env.MARKETHQ_HERMES_WORKER_ENABLE === "true",
        cursorEnabled: process.env.MARKETHQ_CURSOR_WORKER_ENABLE === "true",
        defaultProvider: process.env.MARKETHQ_DEFAULT_WORKER_PROVIDER ?? "hermes",
      },
    });
  } catch (error) {
    return NextResponse.json({ success: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const gate = currentWorkerRuntimeGate();
    if (!gate.researchOnly || gate.executionEnabled || gate.databaseWriteEnabled || gate.brokerExecutionEnabled || gate.mainRepoMutation || gate.automaticPr || gate.automaticMerge) {
      return NextResponse.json({ success: false, error: "WORKER_RUNTIME_GATE_BLOCKED" }, { status: 409 });
    }

    const requestedProvider: WorkerProviderId = body.provider === "cursor" || body.provider === "hermes"
      ? body.provider
      : (process.env.MARKETHQ_DEFAULT_WORKER_PROVIDER === "cursor" ? "cursor" : "hermes");
    const enabled = requestedProvider === "hermes"
      ? process.env.MARKETHQ_HERMES_WORKER_ENABLE === "true"
      : process.env.MARKETHQ_CURSOR_WORKER_ENABLE === "true";
    if (!enabled) return NextResponse.json({ success: false, error: "WORKER_POLICY_DISABLED", provider: requestedProvider }, { status: 409 });

    const runId = typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : "";
    const strategyId = typeof body.strategyId === "string" && body.strategyId.trim() ? body.strategyId.trim() : undefined;
    const symbol = typeof body.symbol === "string" && body.symbol.trim() ? body.symbol.trim() : undefined;
    const timeframe = typeof body.timeframe === "string" && body.timeframe.trim() ? body.timeframe.trim() : "1d";
    const targetPaths = Array.isArray(body.targetPaths)
      ? body.targetPaths.filter((value): value is string => typeof value === "string" && Boolean(value.trim())).map((value) => value.trim())
      : [];
    if (!runId) return NextResponse.json({ success: false, error: "RESEARCH_RUN_ID_REQUIRED" }, { status: 400 });
    if (!targetPaths.length) return NextResponse.json({ success: false, error: "WORKER_TARGET_PATHS_REQUIRED" }, { status: 400 });

    const task = buildWorkerTaskFromResearchDecision({
      runId, strategyId, symbol, timeframe, decision: body.decision, queueTask: body.queueTask,
      instructions: typeof body.instructions === "string" ? body.instructions : undefined,
      targetPaths,
      validationCommand: typeof body.validationCommand === "string" ? body.validationCommand : undefined,
      timeoutMs: typeof body.timeoutMs === "number" && Number.isFinite(body.timeoutMs) ? body.timeoutMs : undefined,
      implementationIntent: typeof body.implementationIntent === "string" ? body.implementationIntent : undefined,
      provider: requestedProvider,
    });
    const record = await dispatchWorkerTask(task);
    return NextResponse.json({ success: true, api: "MARKETHQ_RESEARCH_TO_WORKER_V2", task, record });
  } catch (error) {
    return NextResponse.json({ success: false, error: error instanceof Error ? error.message : String(error) }, { status: 400 });
  }
}
