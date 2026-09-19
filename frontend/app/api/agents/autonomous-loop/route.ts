import { NextRequest, NextResponse } from "next/server";
import type { AgentContext } from "@/components/agents/agent-types";
import type { WorkerDispatchPolicy } from "@/components/workers/autonomous-worker-orchestrator";
import { runBoundedAutonomousCycleLoop } from "@/components/workers/autonomous-cycle-loop";

export const dynamic = "force-dynamic";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const body = record(await request.json().catch(() => ({})));
    const runId = typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : `autonomous-${Date.now()}`;
    const metadata = record(body.metadata);
    const context: AgentContext = {
      runId,
      strategyId: typeof body.strategyId === "string" ? body.strategyId : undefined,
      symbol: typeof body.symbol === "string" ? body.symbol : undefined,
      timeframe: typeof body.timeframe === "string" ? body.timeframe : undefined,
      input: record(body.input),
      previousResults: {},
      metadata: {
        ...metadata,
        cycleId: typeof body.cycleId === "string" ? body.cycleId : metadata.cycleId,
        cycleNumber: Number(body.cycleNumber ?? metadata.cycleNumber ?? 1),
        maxCycles: Math.min(Math.max(Number(body.maxCycles ?? metadata.maxCycles ?? 10), 1), 100),
        implementationIntent: typeof body.implementationIntent === "string" ? body.implementationIntent : metadata.implementationIntent,
      },
    };
    const targetPaths = Array.isArray(body.workerTargetPaths) ? body.workerTargetPaths.map(String).filter(Boolean) : [];
    const policy: WorkerDispatchPolicy = {
      enabled: body.workerEnabled === true || process.env.MARKETHQ_AUTONOMOUS_WORKER_ENABLE === "true",
      targetPaths,
      instructions: typeof body.workerInstructions === "string" ? body.workerInstructions : "Implement only the explicitly requested research implementation change. Do not modify unrelated files, commit, merge, open a PR, access secrets, or enable live execution.",
      validationCommand: typeof body.workerValidationCommand === "string" ? body.workerValidationCommand : undefined,
      implementationIntent: typeof body.implementationIntent === "string" ? body.implementationIntent : undefined,
    };
    const result = await runBoundedAutonomousCycleLoop({
      context,
      policy,
      options: { enabled: true, maxIterations: Math.min(Math.max(Number(body.maxCycles ?? 10), 1), 100) },
    });
    return NextResponse.json({ success: true, api: "MARKETHQ_AUTONOMOUS_LOOP_V1", mode: "RESEARCH_ONLY", result, safety: { researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, mainRepoMutation: false, automaticPr: false, automaticMerge: false } });
  } catch (error) {
    return NextResponse.json({ success: false, api: "MARKETHQ_AUTONOMOUS_LOOP_V1", error: error instanceof Error ? error.message : String(error), safety: { researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, mainRepoMutation: false, automaticPr: false, automaticMerge: false } }, { status: 400 });
  }
}
