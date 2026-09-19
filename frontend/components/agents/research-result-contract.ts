import type { AgentId, AgentResult } from "./agent-types";

export const RESEARCH_RESULT_SCHEMA_VERSION = "research_result_v1";

type JsonRecord = Record<string, unknown>;
type AgentResults = Partial<Record<AgentId, AgentResult>>;

export interface ResearchResultContract {
  schemaVersion: string;
  run: { runId: string; status: string; mode: "RESEARCH_ONLY" };
  request: { strategyId: string; symbol: string; timeframe: string; researchQuestion: string | null };
  data: JsonRecord | null;
  dateResolution: JsonRecord | null;
  hypothesis: { source: "strategy" | "brain" | "none"; output: JsonRecord | null };
  experiment: JsonRecord | null;
  execution: { runner: JsonRecord | null; resultIngestion: JsonRecord | null };
  validation: JsonRecord | null;
  overfitDiagnostics: JsonRecord | null;
  evidence: JsonRecord | null;
  learning: JsonRecord | null;
  brainUpdate: JsonRecord | null;
  decision: JsonRecord | null;
  pipeline: { order: AgentId[]; completed: AgentId[]; failed: AgentId[]; skipped: AgentId[] };
  safety: JsonRecord;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getOutput(results: AgentResults, agentId: AgentId): JsonRecord | null {
  const result = results[agentId];
  if (!result?.output) return null;

  const output = isRecord(result.output) ? { ...result.output } : null;
  if (!output) return null;

  // AgentRunner keeps numeric research metrics in AgentResult.metrics so the
  // orchestrator can safely compact the large raw execution payload. Reattach
  // those small metrics to the canonical runner output for the UI contract.
  if (isRecord(result.metrics) && Object.keys(result.metrics).length > 0) {
    output.metrics = { ...result.metrics };
  }

  return output;
}

function getOverfitDiagnostics(results: AgentResults): JsonRecord | null {
  const runner = getOutput(results, "experiment-runner");
  const robustness = runner ? runner.robustness : null;
  if (!isRecord(robustness)) return null;
  return isRecord(robustness.overfitDiagnostics) ? robustness.overfitDiagnostics : null;
}

function buildHypothesis(results: AgentResults): ResearchResultContract["hypothesis"] {
  const strategyOutput = getOutput(results, "strategy");
  if (strategyOutput) return { source: "strategy", output: strategyOutput };

  const brainOutput = getOutput(results, "brain");
  if (brainOutput) return { source: "brain", output: brainOutput };

  return { source: "none", output: null };
}

export function buildResearchResultContract(args: {
  runId: string;
  status: string;
  strategyId: string;
  symbol: string;
  timeframe: string;
  researchQuestion: string | null;
  results: AgentResults;
  executionOrder: AgentId[];
  completedAgents: AgentId[];
  failedAgents: AgentId[];
  skippedAgents: AgentId[];
  safety: JsonRecord;
}): ResearchResultContract {
  return {
    schemaVersion: RESEARCH_RESULT_SCHEMA_VERSION,
    run: { runId: args.runId, status: args.status, mode: "RESEARCH_ONLY" },
    request: {
      strategyId: args.strategyId,
      symbol: args.symbol,
      timeframe: args.timeframe,
      researchQuestion: args.researchQuestion,
    },
    data: getOutput(args.results, "market-data"),
    dateResolution: getOutput(args.results, "research-date-resolver"),
    hypothesis: buildHypothesis(args.results),
    experiment: getOutput(args.results, "experiment-generator"),
    execution: {
      runner: getOutput(args.results, "experiment-runner"),
      resultIngestion: getOutput(args.results, "result-ingestion"),
    },
    validation: getOutput(args.results, "validation"),
    overfitDiagnostics: getOverfitDiagnostics(args.results),
    evidence: getOutput(args.results, "evidence"),
    learning: getOutput(args.results, "learning"),
    brainUpdate: getOutput(args.results, "brain-update"),
    decision: getOutput(args.results, "research-decision"),
    pipeline: {
      order: args.executionOrder,
      completed: args.completedAgents,
      failed: args.failedAgents,
      skipped: args.skippedAgents,
    },
    safety: args.safety,
  };
}
