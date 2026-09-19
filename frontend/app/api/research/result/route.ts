import { NextRequest, NextResponse } from "next/server";

import { POST as runOrchestrator } from "@/app/api/agents/orchestrate/route";
import type { AgentId, AgentResult } from "@/components/agents/agent-types";
import {
  buildResearchResultContract,
  type ResearchResultContract,
} from "@/components/agents/research-result-contract";

type JsonRecord = Record<string, unknown>;
type AgentResults = Partial<Record<AgentId, AgentResult>>;

type OrchestratorPayload = JsonRecord & {
  success?: boolean;
  runId?: string;
  status?: string;
  executionOrder?: AgentId[];
  completedAgents?: AgentId[];
  failedAgents?: AgentId[];
  skippedAgents?: AgentId[];
  resultsByAgent?: AgentResults;
  safety?: JsonRecord;
};

type CachedResearchResult = {
  payload: OrchestratorPayload;
  researchResult: ResearchResultContract;
};

const canonicalCache = new Map<string, CachedResearchResult>();

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function agentIds(value: unknown): AgentId[] {
  return Array.isArray(value)
    ? value.filter((item): item is AgentId => typeof item === "string")
    : [];
}

function cacheKey(body: JsonRecord): string {
  return JSON.stringify({
    strategyId: stringOrNull(body.strategyId) ?? "",
    symbol: stringOrNull(body.symbol) ?? "",
    timeframe: stringOrNull(body.timeframe) ?? "",
    researchQuestion: stringOrNull(body.researchQuestion),
    researchEngine: stringOrNull(body.researchEngine) ?? "CURRENT",
    strategyDefinition: body.strategyDefinition ?? null,
    parameterSweep: body.parameterSweep ?? null,
    parameterSearchMethod: body.parameterSearchMethod ?? null,
    parameterSearchCount: body.parameterSearchCount ?? null,
  });
}

function toFiniteMetrics(value: unknown): Record<string, number> | null {
  if (!isRecord(value)) return null;
  const metrics: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) metrics[key] = numeric;
  }
  return Object.keys(metrics).length > 0 ? metrics : null;
}

function extractExperimentRunnerMetrics(result: AgentResult): Record<string, number> | undefined {
  if (result.metrics && Object.keys(result.metrics).length > 0) {
    return result.metrics;
  }

  const output = isRecord(result.output) ? result.output : null;
  const researchExecution = output && isRecord(output.researchExecution)
    ? output.researchExecution
    : null;
  const executionResult = researchExecution && isRecord(researchExecution.result)
    ? researchExecution.result
    : null;
  const backtest = executionResult && isRecord(executionResult.backtest)
    ? executionResult.backtest
    : null;
  const backtestResult = backtest && isRecord(backtest.result)
    ? backtest.result
    : null;
  const best = backtestResult && isRecord(backtestResult.best)
    ? backtestResult.best
    : null;

  return (
    toFiniteMetrics(executionResult?.metrics) ??
    toFiniteMetrics(backtestResult?.metrics) ??
    toFiniteMetrics(best?.metrics) ??
    undefined
  );
}

function normalizePublicAgentResults(resultsByAgent: AgentResults): AgentResults {
  const normalized: AgentResults = { ...resultsByAgent };
  const runner = normalized["experiment-runner"];

  if (runner) {
    const metrics = extractExperimentRunnerMetrics(runner);
    if (metrics) {
      normalized["experiment-runner"] = {
        ...runner,
        metrics,
      };
    }
  }

  return normalized;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const requestBody = await request.clone().json().catch(() => ({}));
    const body = isRecord(requestBody) ? requestBody : {};
    const forceNew = body.forceNew === true;
    const key = cacheKey(body);
    const cached = canonicalCache.get(key);

    if (cached && !forceNew) {
      return NextResponse.json({
        ...cached.payload,
        researchResult: cached.researchResult,
        cache: { hit: true, source: "canonical_research_result" },
      });
    }

    const orchestratorResponse = await runOrchestrator(request);
    const payload = (await orchestratorResponse.json()) as OrchestratorPayload;

    if (!orchestratorResponse.ok) {
      return NextResponse.json(payload, { status: orchestratorResponse.status });
    }

    const runId = stringOrNull(payload.runId) ?? `research-result-${Date.now()}`;
    const status = stringOrNull(payload.status) ?? "FAILED";
    const rawResultsByAgent = isRecord(payload.resultsByAgent)
      ? (payload.resultsByAgent as AgentResults)
      : {};
    const resultsByAgent = normalizePublicAgentResults(rawResultsByAgent);
    const executionOrder = agentIds(payload.executionOrder);
    const completedAgents = agentIds(payload.completedAgents);
    const failedAgents = agentIds(payload.failedAgents);
    const skippedAgents = agentIds(payload.skippedAgents);

    const contract: ResearchResultContract = buildResearchResultContract({
      runId,
      status,
      strategyId: stringOrNull(body.strategyId) ?? "",
      symbol: stringOrNull(body.symbol) ?? "",
      timeframe: stringOrNull(body.timeframe) ?? "",
      researchQuestion: stringOrNull(body.researchQuestion),
      results: resultsByAgent,
      executionOrder,
      completedAgents,
      failedAgents,
      skippedAgents,
      safety: isRecord(payload.safety) ? payload.safety : {},
    });

    const finalPayload: OrchestratorPayload = {
      ...payload,
      status,
      executionOrder,
      completedAgents,
      failedAgents,
      skippedAgents,
      resultsByAgent,
    };

    const completed = payload.success === true && status === "COMPLETED" && failedAgents.length === 0 && skippedAgents.length === 0;
    if (completed) {
      canonicalCache.set(key, { payload: finalPayload, researchResult: contract });
    }

    const error = completed
      ? undefined
      : `Research pipeline tamamlanamadı: status=${status}; failed=[${failedAgents.join(", ") || "none"}]; skipped=[${skippedAgents.join(", ") || "none"}]`;

    return NextResponse.json({
      ...finalPayload,
      researchResult: contract,
      ...(error ? { error } : {}),
      cache: { hit: false, source: completed ? "fresh_research_run" : "uncached_partial_or_failed_run" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        status: "FAILED",
        error: error instanceof Error ? error.message : String(error),
        safety: {
          researchOnly: true,
          executionEnabled: false,
          databaseWriteEnabled: false,
          brokerExecutionEnabled: false,
        },
      },
      { status: 500 },
    );
  }
}
