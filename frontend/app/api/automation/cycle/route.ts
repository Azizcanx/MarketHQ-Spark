import { NextRequest, NextResponse } from "next/server";
import { POST as runResearchOrchestrator } from "@/app/api/agents/orchestrator/route";
import { getAutonomousCycleState, listAutonomousCycleStates } from "@/components/workers/autonomous-cycle-state";
import { guardAutonomousCycleDispatch } from "@/components/workers/autonomous-cycle-guard";
import { getAutonomousModeState } from "@/components/workers/autonomous-mode-store";
import type { AgentContext } from "@/components/agents/agent-types";

export const dynamic = "force-dynamic";
export const maxDuration = 300;
const safety = { researchOnly: true, executionEnabled: false, brokerExecutionEnabled: false, mainRepoMutation: false, automaticPr: false, automaticMerge: false };
function text(value: unknown): string | undefined { return typeof value === "string" && value.trim() ? value.trim() : undefined; }
function cycleIdFrom(input: Record<string, unknown>): string { const explicit = text(input.cycleId); if (explicit) return explicit; return `autonomous|${text(input.strategyId) ?? "default-strategy"}|${text(input.symbol) ?? "default-symbol"}|${text(input.timeframe) ?? "1d"}`; }
function buildContext(input: Record<string, unknown>, cycleId: string, cycleNumber: number): AgentContext { return { runId: `automation-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, strategyId: text(input.strategyId), symbol: text(input.symbol), timeframe: text(input.timeframe) ?? "1d", input: typeof input.input === "object" && input.input !== null && !Array.isArray(input.input) ? input.input as Record<string, unknown> : {}, metadata: { cycleId, cycleNumber, maxCycles: Number(input.maxCycles ?? process.env.MARKETHQ_AUTONOMOUS_MAX_CYCLES ?? 10) } }; }
function maxIterationsFrom(input: Record<string, unknown>): number { return Math.min(Math.max(Number(input.maxIterations ?? input.maxCycles ?? process.env.MARKETHQ_AUTONOMOUS_MAX_CYCLES ?? 10), 1), 10); }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function nextCycleAllowed(payload: Record<string, unknown>): boolean { const dispatch = payload.workerDispatch; if (!isRecord(dispatch)) return false; const cycle = dispatch.cycle; if (!isRecord(cycle)) return false; const decision = cycle.decision; return isRecord(decision) && decision.nextCycleAllowed === true; }
function decisionReason(payload: Record<string, unknown>): string | undefined { const dispatch = payload.workerDispatch; if (!isRecord(dispatch)) return undefined; const cycle = dispatch.cycle; if (!isRecord(cycle)) return undefined; const decision = cycle.decision; return isRecord(decision) && typeof decision.reason === "string" ? decision.reason : undefined; }
function automationSecretAuthorized(request: NextRequest): boolean { const expected = process.env.MARKETHQ_AUTOMATION_SECRET?.trim(); if (!expected) return true; const provided = request.headers.get("x-markethq-automation-secret")?.trim(); return Boolean(provided && provided === expected); }

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    if (!automationSecretAuthorized(request)) return NextResponse.json({ success: false, executed: false, reason: "AUTOMATION_UNAUTHORIZED", safety }, { status: 401 });
    const mode = getAutonomousModeState();
    const envEnabled = process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER === "true";
    if (!mode.enabled && !envEnabled) return NextResponse.json({ success: false, executed: false, reason: "SCHEDULER_DISABLED", mode, safety }, { status: 409 });
    const body = await request.json().catch(() => ({}));
    const input = body && typeof body === "object" && !Array.isArray(body) ? body as Record<string, unknown> : {};
    const cycleId = cycleIdFrom(input);
    const maxCycles = Math.min(Math.max(Number(input.maxCycles ?? process.env.MARKETHQ_AUTONOMOUS_MAX_CYCLES ?? 10), 1), 100);
    const maxIterations = maxIterationsFrom({ ...input, maxCycles });
    let lastPayload: Record<string, unknown> | undefined;
    let executedCycles = 0;
    let stopReason = "AUTONOMOUS_LOOP_ITERATION_BUDGET_EXCEEDED";
    for (let iteration = 0; iteration < maxIterations; iteration += 1) {
      const state = getAutonomousCycleState(cycleId);
      const cycleNumber = state ? state.cycleNumber + 1 : 1;
      if (cycleNumber > maxCycles) { stopReason = `AUTONOMOUS_CYCLE_BUDGET_EXCEEDED:${maxCycles}`; break; }
      const context = buildContext({ ...input, maxCycles }, cycleId, cycleNumber);
      const guard = guardAutonomousCycleDispatch(context, state);
      if (!guard.allowed) { stopReason = `GUARD_${guard.reason}`; break; }
      const orchestratorRequest = new NextRequest(new URL("/api/agents/orchestrator", request.url), { method: "POST", headers: { "content-type": "application/json", accept: "application/json" }, body: JSON.stringify({ ...input, cycleId, cycleNumber, maxCycles, workerEnabled: input.workerEnabled ?? process.env.MARKETHQ_AUTONOMOUS_WORKER_ENABLE === "true", workerTargetPaths: Array.isArray(input.workerTargetPaths) ? input.workerTargetPaths : (process.env.MARKETHQ_AUTONOMOUS_WORKER_TARGET_PATHS ?? "").split(",").map((value) => value.trim()).filter(Boolean), workerInstructions: text(input.workerInstructions) ?? "Implement only the explicitly requested research implementation change. Do not modify unrelated files, commit, merge, open a PR, access secrets, or enable live execution.", workerValidationCommand: text(input.workerValidationCommand) }) });
      const response = await runResearchOrchestrator(orchestratorRequest);
      const payload = await response.json() as Record<string, unknown>;
      lastPayload = payload;
      executedCycles += 1;
      if (!response.ok) { stopReason = typeof payload.error === "string" ? payload.error : "ORCHESTRATOR_FAILED"; break; }
      if (!nextCycleAllowed(payload)) { stopReason = decisionReason(payload) ?? "NEXT_CYCLE_NOT_ALLOWED"; break; }
    }
    const finalState = getAutonomousCycleState(cycleId);
    return NextResponse.json({ ...(lastPayload ?? { success: false }), autonomousCycle: { cycleId, maxCycles, maxIterations, executed: executedCycles > 0, executedCycles, stopped: true, stopReason, scheduler: "ENABLED", mode, state: finalState }, safety });
  } catch (error) { return NextResponse.json({ success: false, executed: false, error: error instanceof Error ? error.message : String(error), safety }, { status: 500 }); }
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const mode = getAutonomousModeState();
  const url = new URL(request.url);
  const cycleId = url.searchParams.get("cycleId")?.trim() || "";
  const limitRaw = Number(url.searchParams.get("limit") ?? 25);
  const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(Math.floor(limitRaw), 1), 100) : 25;
  const cycles = listAutonomousCycleStates().slice(0, limit);
  const cycle = cycleId ? getAutonomousCycleState(cycleId) : null;
  const counts = cycles.reduce<Record<string, number>>((acc, item) => { acc[item.status] = (acc[item.status] ?? 0) + 1; return acc; }, {});
  const automationSecretConfigured = Boolean(process.env.MARKETHQ_AUTOMATION_SECRET?.trim());
  const externalUrlConfigured = Boolean(process.env.MARKETHQ_AUTOMATION_URL?.trim());
  return NextResponse.json({ success: true, scheduler: mode.enabled || process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER === "true" ? "ENABLED" : "DISABLED", mode, cycle, cycles, telemetry: { returned: cycles.length, counts, latestUpdatedAt: cycles[0]?.updatedAt ?? null }, configuration: { automationSecretConfigured, externalUrlConfigured, externalSchedulerOptIn: process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER === "true" }, safety });
}
