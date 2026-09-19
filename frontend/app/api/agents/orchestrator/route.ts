import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

import type { AgentContext, AgentId, AgentResult } from "@/components/agents/agent-types";
import { agentRunner } from "@/components/agents/agent-runner";
import { getAgentPipelineOrder } from "@/components/agents/agent-registry";
import { registerDefaultAgents } from "@/components/agents/register-agents";
import { coordinateAutonomousCycleV2 } from "@/components/workers/autonomous-cycle-coordinator-v2";
import { rehydrateWorkerFeedback } from "@/components/workers/worker-feedback-context";
import { buildWorkerResearchHandoff } from "@/components/workers/worker-research-handoff";

type JsonRecord = Record<string, unknown>;
type AgentResults = Partial<Record<AgentId, AgentResult>>;
type OrchestratorStatus = "COMPLETED" | "PARTIAL" | "FAILED";

interface OrchestratorResponse {
  success: boolean;
  runId: string;
  status: OrchestratorStatus;
  mode: "RESEARCH_ONLY";
  executionOrder: AgentId[];
  completedAgents: AgentId[];
  failedAgents: AgentId[];
  skippedAgents: AgentId[];
  results: AgentResult[];
  resultsByAgent: AgentResults;
  researchDecision?: JsonRecord;
  researchQueue?: JsonRecord;
  experimentGenerator?: JsonRecord;
  experimentRunner?: JsonRecord;
  resultIngestion?: JsonRecord;
  learning?: JsonRecord;
  brainUpdate?: JsonRecord;
  adaptiveResearchPlan?: JsonRecord;
  feedbackLoop?: JsonRecord;
  workerResearchHandoff?: JsonRecord;
  workerDispatch?: JsonRecord;
  safety: JsonRecord;
  pipeline: AgentId[];
}

let agentsRegistered = false;
function ensureAgentsRegistered(): void { if (!agentsRegistered) { registerDefaultAgents(); agentsRegistered = true; } }
function isRecord(value: unknown): value is JsonRecord { return typeof value === "object" && value !== null && !Array.isArray(value); }
function toJsonSafe(value: unknown): unknown {
  const ancestors = new WeakSet<object>();
  const MAX_STRING_LENGTH = 250_000;
  function visit(item: unknown): unknown {
    if (item === undefined) return null;
    if (item === null || typeof item === "number" || typeof item === "boolean") return item;
    if (typeof item === "string") return item.length > MAX_STRING_LENGTH ? `${item.slice(0, MAX_STRING_LENGTH)}…[truncated]` : item;
    if (typeof item === "bigint") return item.toString();
    if (item instanceof Date) return item.toISOString();
    if (typeof item !== "object") return String(item);
    if (ancestors.has(item)) return "[Circular reference omitted]";
    ancestors.add(item);
    try {
      if (Array.isArray(item)) return item.map(visit);
      if (isRecord(item)) { const output: JsonRecord = {}; for (const [key, child] of Object.entries(item)) output[key] = visit(child); return output; }
      return String(item);
    } finally { ancestors.delete(item); }
  }
  return visit(value);
}
function toSafeResponse<T>(value: T): T { return toJsonSafe(value) as T; }
function getOutput(resultsByAgent: AgentResults, agentId: AgentId): JsonRecord | undefined { const result = resultsByAgent[agentId]; return result && isRecord(result.output) ? result.output : undefined; }
function compactAgentResult(result: AgentResult): AgentResult { const { output: _output, ...metadata } = result; return metadata as AgentResult; }
function compactOutputForResponse(agentId: AgentId, output: JsonRecord | undefined): JsonRecord | undefined {
  if (!output) return undefined;
  if (agentId === "experiment-generator") return output;
  const compact: JsonRecord = { agent: output.agent ?? agentId, runId: output.runId ?? null };
  const summaryKeys = ["success","status","strategyId","strategy_id","symbol","timeframe","decision","action","decisionBasis","decisionConfidence","nextResearchQuestion","researchLoop","queue","dateScope","experimentId","experiment_id","resultId","result_id","learningDecision","learningScore","validationStatus","researchOnly","executionEnabled","generatedAt"];
  for (const key of summaryKeys) if (key in output) compact[key] = output[key];
  if (isRecord(output.experiment)) compact.experiment = { ...output.experiment };
  if (isRecord(output.researchPlan)) compact.researchPlan = { ...output.researchPlan };
  if (isRecord(output.researchSpec)) compact.researchSpec = { ...output.researchSpec };
  if (agentId === "experiment-runner" && isRecord(output.researchExecution)) {
    const executionResult = isRecord(output.researchExecution.result) ? output.researchExecution.result : {};
    const executionMeta = isRecord(executionResult.execution) ? executionResult.execution : {};
    compact.researchExecution = { status: output.researchExecution.status ?? null, completed: output.researchExecution.completed ?? false, blocked: output.researchExecution.blocked ?? false, succeeded: output.researchExecution.succeeded ?? false, engine: typeof executionMeta.researchEngine === "string" ? executionMeta.researchEngine : null };
    if (isRecord(executionResult.backtest)) {
      const backtestResult = isRecord(executionResult.backtest.result) ? executionResult.backtest.result : {};
      if (isRecord(backtestResult.parameterSweep)) compact.parameterSweep = { ...backtestResult.parameterSweep };
      if (isRecord(backtestResult.best)) compact.best = { ...backtestResult.best };
      if (isRecord(backtestResult.overfitDiagnostics)) compact.overfitDiagnostics = { ...backtestResult.overfitDiagnostics };
    }
  }
  if (agentId === "result-ingestion" && isRecord(output.result)) compact.result = { ...output.result };
  if (agentId === "learning") { if (isRecord(output.learningContext)) compact.learningContext = { ...output.learningContext }; if (isRecord(output.researchMemory)) compact.researchMemory = { ...output.researchMemory }; }
  return compact;
}
function buildPublicResultsByAgent(resultsByAgent: AgentResults): AgentResults { const publicResults: AgentResults = {}; for (const [agentId, result] of Object.entries(resultsByAgent) as [AgentId, AgentResult][]) if (result) publicResults[agentId] = { ...compactAgentResult(result), output: compactOutputForResponse(agentId, isRecord(result.output) ? result.output : undefined) }; return publicResults; }
async function fetchAdaptiveResearchPlan(): Promise<JsonRecord> {
  const backendUrl = process.env.MARKETHQ_BACKEND_URL?.replace(/\/+$/, "") || "http://127.0.0.1:8010";
  try { const response = await fetch(`${backendUrl}/api/research-plan`, { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" }); const body = await response.json().catch(() => null); if (!response.ok || !isRecord(body) || body.success !== true) return { available: false, status: "UNAVAILABLE", reason: isRecord(body) ? String(body.error ?? `HTTP ${response.status}`) : `HTTP ${response.status}` }; return isRecord(body.data) ? { available: true, ...body.data } : { available: false, status: "INVALID_RESPONSE" }; } catch (error) { return { available: false, status: "UNAVAILABLE", reason: error instanceof Error ? error.message : String(error) }; }
}
function buildSafety(): JsonRecord { return { researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, brokerOrderPlaced: false, databaseWritePerformed: false, liveTradingAllowed: false, liveExecutionAllowed: false }; }
function repoRoot(): string { return process.env.MARKETHQ_REPO_ROOT || path.resolve(process.cwd(), ".."); }
function buildContext(body: JsonRecord, runId: string, resultsByAgent: AgentResults, phase: "PHASE_1" | "PHASE_2_FEEDBACK", executionIndex: number): AgentContext {
  const strategyId = typeof body.strategyId === "string" ? body.strategyId : undefined;
  const symbol = typeof body.symbol === "string" ? body.symbol : undefined;
  const timeframe = typeof body.timeframe === "string" ? body.timeframe : undefined;
  const input: JsonRecord = isRecord(body.input) ? { ...body.input } : {};
  if (typeof body.researchEngine === "string") input.researchEngine = body.researchEngine;
  if (isRecord(body.strategyDefinition)) input.strategyDefinition = body.strategyDefinition;
  if (isRecord(body.parameterSweep)) input.parameterSweep = body.parameterSweep;
  if (typeof body.parameterSearchMethod === "string") input.parameterSearchMethod = body.parameterSearchMethod;
  if (Number.isFinite(Number(body.parameterSearchCount))) input.parameterSearchCount = Number(body.parameterSearchCount);
  const metadata: JsonRecord = { orchestrator: "MarketHQ Orchestrator", mode: "RESEARCH_ONLY", phase, executionIndex, previousAgentCount: Object.keys(resultsByAgent).length, feedbackLoop: phase === "PHASE_2_FEEDBACK", postRunnerValidation: phase === "PHASE_2_FEEDBACK", runnerResultAvailable: Boolean(resultsByAgent["experiment-runner"]), researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false };
  for (const key of ["cycleId","cycleNumber","maxCycles","implementationIntent","workerEnabled","workerTargetPaths","workerInstructions","workerValidationCommand"]) if (key in body) metadata[key] = body[key];
  const context: AgentContext = { runId, strategyId, symbol, timeframe, input, previousResults: { ...resultsByAgent }, metadata };
  return rehydrateWorkerFeedback(context, { repoRoot: repoRoot() });
}
function isCompleted(result: AgentResult | undefined): boolean { return Boolean(result && result.success === true && result.status === "COMPLETED"); }
function buildFinalResponse(runId: string, pipeline: AgentId[], executionOrder: AgentId[], results: AgentResult[], resultsByAgent: AgentResults, completedAgents: AgentId[], failedAgents: AgentId[], skippedAgents: AgentId[]): OrchestratorResponse {
  let status: OrchestratorStatus = "COMPLETED"; if (failedAgents.length > 0) status = completedAgents.length > 0 ? "PARTIAL" : "FAILED"; else if (skippedAgents.length > 0) status = "PARTIAL";
  return { success: failedAgents.length === 0 && skippedAgents.length === 0, runId, mode: "RESEARCH_ONLY", status, executionOrder, completedAgents, failedAgents, skippedAgents, results: results.map(compactAgentResult), resultsByAgent: buildPublicResultsByAgent(resultsByAgent), researchDecision: compactOutputForResponse("research-decision", getOutput(resultsByAgent, "research-decision")), researchQueue: compactOutputForResponse("research-queue", getOutput(resultsByAgent, "research-queue")), experimentGenerator: compactOutputForResponse("experiment-generator", getOutput(resultsByAgent, "experiment-generator")), experimentRunner: compactOutputForResponse("experiment-runner", getOutput(resultsByAgent, "experiment-runner")), resultIngestion: compactOutputForResponse("result-ingestion", getOutput(resultsByAgent, "result-ingestion")), learning: compactOutputForResponse("learning", getOutput(resultsByAgent, "learning")), brainUpdate: compactOutputForResponse("brain-update", getOutput(resultsByAgent, "brain-update")), safety: buildSafety(), pipeline };
}
async function runAgentSequence(agents: AgentId[], phase: "PHASE_1" | "PHASE_2_FEEDBACK", runId: string, body: JsonRecord, results: AgentResult[], resultsByAgent: AgentResults, executionOrder: AgentId[], completedAgents: AgentId[], failedAgents: AgentId[], skippedAgents: AgentId[]): Promise<void> {
  for (const agentId of agents) {
    executionOrder.push(agentId);
    if (agentId === "result-ingestion" && !isCompleted(resultsByAgent["experiment-runner"])) { skippedAgents.push(agentId); continue; }
    if (agentId === "experiment-generator" && !isCompleted(resultsByAgent["research-date-resolver"])) { skippedAgents.push(agentId); continue; }
    if (agentId === "experiment-runner" && !isCompleted(resultsByAgent["experiment-generator"])) { skippedAgents.push(agentId); continue; }
    if (agentId === "research-date-resolver" && !isCompleted(resultsByAgent["research-queue"])) { skippedAgents.push(agentId); continue; }
    if (agentId === "research-queue" && !isCompleted(resultsByAgent["research-decision"])) { skippedAgents.push(agentId); continue; }
    if (agentId === "learning" && (!isCompleted(resultsByAgent["brain"]) || !isCompleted(resultsByAgent["evidence"]))) { skippedAgents.push(agentId); continue; }
    if (agentId === "brain-update" && (!isCompleted(resultsByAgent["result-ingestion"]) || !isCompleted(resultsByAgent["validation"]) || !isCompleted(resultsByAgent["learning"]))) { skippedAgents.push(agentId); continue; }
    if (agentId === "research-decision" && (!isCompleted(resultsByAgent["learning"]) || !isCompleted(resultsByAgent["evidence"]) || !isCompleted(resultsByAgent["validation"]))) { skippedAgents.push(agentId); continue; }
    const context = buildContext(body, runId, resultsByAgent, phase, executionOrder.length);
    try { const result = await agentRunner.run(agentId, context); results.push(result); resultsByAgent[agentId] = result; if (result.success === true && result.status === "COMPLETED") completedAgents.push(agentId); else failedAgents.push(agentId); } catch { failedAgents.push(agentId); }
  }
}

export async function GET(): Promise<NextResponse> {
  try { ensureAgentsRegistered(); return NextResponse.json(toSafeResponse({ success: true, agent: "orchestrator", pipeline: getAgentPipelineOrder(), mode: "RESEARCH_ONLY", researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, feedbackLoop: ["experiment-generator","experiment-runner","result-ingestion","validation","learning","brain-update","research-decision"], architecture: { phase1: ["market-data","trend-regime","strategy","backtest","validation","evidence","brain","learning","research-decision","research-queue","research-date-resolver","experiment-generator","experiment-runner"], phase2: ["result-ingestion","validation","learning","brain-update","research-decision"], validationRuns: 2, feedbackLoop: true, workerBoundary: "RESEARCH_DECISION -> IMPLEMENTATION_INTENT -> DISPATCH_GATEWAY -> WORKER_RUNTIME" }, safety: buildSafety() })); } catch (error) { return NextResponse.json({ success: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 }); }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const startedAt = Date.now();
  const runId = `orchestrator-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  try {
    ensureAgentsRegistered();
    const body = await request.json().catch(() => ({}));
    const input: JsonRecord = isRecord(body) ? body : {};
    const pipeline = getAgentPipelineOrder();
    const phase1 = pipeline.filter((agentId) => agentId !== "result-ingestion" && agentId !== "brain-update");
    const phase2: AgentId[] = ["result-ingestion","validation","learning","brain-update","research-decision"];
    const results: AgentResult[] = []; const resultsByAgent: AgentResults = {}; const executionOrder: AgentId[] = []; const completedAgents: AgentId[] = []; const failedAgents: AgentId[] = []; const skippedAgents: AgentId[] = [];
    await runAgentSequence(phase1,"PHASE_1",runId,input,results,resultsByAgent,executionOrder,completedAgents,failedAgents,skippedAgents);
    await runAgentSequence(phase2,"PHASE_2_FEEDBACK",runId,input,results,resultsByAgent,executionOrder,completedAgents,failedAgents,skippedAgents);
    const response = buildFinalResponse(runId,pipeline,executionOrder,results,resultsByAgent,completedAgents,failedAgents,skippedAgents);
    response.adaptiveResearchPlan = await fetchAdaptiveResearchPlan();
    response.feedbackLoop = { enabled: true, phase1Completed: phase1.filter((agentId) => completedAgents.includes(agentId)), phase2Completed: phase2.filter((agentId) => completedAgents.includes(agentId)), durationMs: Date.now() - startedAt };
    const decision = resultsByAgent["research-decision"];
    const queue = resultsByAgent["research-queue"];
    const workerPolicy = { enabled: input.workerEnabled === true || ["1","true","yes","on"].includes(String(process.env.MARKETHQ_AUTONOMOUS_WORKER_ENABLE ?? "").toLowerCase()), targetPaths: Array.isArray(input.workerTargetPaths) ? input.workerTargetPaths.map(String).filter(Boolean) : [], instructions: typeof input.workerInstructions === "string" ? input.workerInstructions : "Implement only the explicitly requested research implementation change. Do not modify unrelated files, commit, merge, open a PR, access secrets, or enable live execution.", validationCommand: typeof input.workerValidationCommand === "string" ? input.workerValidationCommand : undefined, implementationIntent: typeof input.implementationIntent === "string" ? input.implementationIntent : undefined };
    const workerContext = buildContext(input, runId, resultsByAgent, "PHASE_2_FEEDBACK", executionOrder.length + 1);
    const workerCycle = await coordinateAutonomousCycleV2(workerContext, null, null, workerPolicy);
    response.workerDispatch = toJsonSafe(workerCycle) as JsonRecord;
    response.workerResearchHandoff = toJsonSafe(buildWorkerResearchHandoff(workerContext, { repoRoot: repoRoot() })) as JsonRecord;
    return NextResponse.json(toSafeResponse(response));
  } catch (error) { return NextResponse.json(toSafeResponse({ success: false, runId, status: "FAILED", mode: "RESEARCH_ONLY", error: error instanceof Error ? error.message : String(error), safety: buildSafety() }), { status: 500 }); }
}
