import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

type UnknownRecord =
  Record<string, unknown>;

type IngestionStatus =
  | "INGESTED"
  | "PARTIAL"
  | "BLOCKED";

interface SourceReference {
  agentId: string;
  runId: string | null;
  available: boolean;
}

interface NormalizedExperimentResult {
  experimentId: string;

  status:
    | IngestionStatus;

  researchQuestion: string;
  hypothesis: string;

  strategy: {
    strategyId: string;
    name: string;
    symbol: string;
    timeframe: string;
  };

  sources: {
    experimentGenerator: SourceReference;
    experimentRunner: SourceReference;
    backtest: SourceReference;
    validation: SourceReference;
    evidence: SourceReference;
    paperTrading?: SourceReference;
  };

  results: {
    backtest: UnknownRecord;
    validation: UnknownRecord;
    evidence: UnknownRecord;
    paperTrading?: UnknownRecord;
  };

  normalizedMetrics: {
    profitFactor: number | null;
    pnl: number | null;
    maxDrawdown: number | null;
    holdoutPositiveRatio: number | null;
    crossSymbolPositiveRatio: number | null;
    costSurvival: number | null;
    parameterStability: number | null;
    regimeStability: number | null;
    fullRunPositiveRatio: number | null;
    confidence: number | null;
    wfoTotalFolds: number | null;
    wfoPositiveFolds: number | null;
    wfoNegativeFolds: number | null;
    wfoInconclusiveFolds: number | null;
    wfoResolvedFolds: number | null;
    wfoPositiveRatio: number | null;
    wfoNegativeRatio: number | null;
    wfoResolvedRatio: number | null;
    wfoInconclusiveShare: number | null;
    wfoEvidenceQuality: string | null;
    robustnessScore: number | null;
    monteCarloPositiveProbability: number | null;
    stressPositiveScenarioRatio: number | null;
    stressWorstMetric: number | null;
  };

  quality: {
    sourceCount: number;
    availableSourceCount: number;
    missingSources: string[];
    metricCount: number;
  };

  conclusion: {
    resultType:
      | "POSITIVE"
      | "MIXED"
      | "NEGATIVE"
      | "UNKNOWN";

    summary: string;
  };

  nextResearchInput: {
    canFeedLearning: boolean;
    recommendedNextStep: string;
  };

  robustness?: UnknownRecord;

  provenance: {
    ingestionRunId: string;
    sourceRunIds: Record<
      string,
      string | null
    >;
  };

  safety: {
    researchOnly: boolean;
    executionEnabled: boolean;
    databaseWriteEnabled: boolean;
    brokerExecutionEnabled: boolean;
  };
}

function isRecord(
  value: unknown
): value is UnknownRecord {
  return (
    Boolean(value) &&
    typeof value ===
      "object" &&
    !Array.isArray(value)
  );
}

function toStringValue(
  value: unknown,
  fallback = ""
): string {
  if (
    typeof value ===
      "string" &&
    value.trim()
  ) {
    return value.trim();
  }

  if (
    typeof value ===
      "number" &&
    Number.isFinite(value)
  ) {
    return String(value);
  }

  return fallback;
}

function toNullableNumber(
  value: unknown
): number | null {
  if (
    typeof value ===
      "number" &&
    Number.isFinite(value)
  ) {
    return value;
  }

  if (
    typeof value ===
      "string" &&
    value.trim()
  ) {
    const parsed =
      Number(value);

    return Number.isFinite(
      parsed
    )
      ? parsed
      : null;
  }

  return null;
}

function firstRecord(
  ...values: unknown[]
): UnknownRecord {
  for (
    const value of values
  ) {
    if (
      isRecord(value)
    ) {
      return value;
    }
  }

  return {};
}

type AgentSourceId =
  | "experiment-generator"
  | "experiment-runner"
  | "backtest"
  | "validation"
  | "evidence"
  | "paper-trading";

function getAgentOutput(
  context: AgentContext,
  agentId: AgentSourceId,
): UnknownRecord {
  const previousOutput =
    context.previousResults?.[
      agentId
    ]?.output;

  if (
    isRecord(previousOutput)
  ) {
    return previousOutput;
  }

  const explicitInput =
    context.input?.[agentId];

  if (
    isRecord(explicitInput)
  ) {
    return explicitInput;
  }

  return {};
}

function getAgentRunId(
  context: AgentContext,
  agentId: AgentSourceId,
): string | null {
  const previousRunId =
    toStringValue(
      context.previousResults?.[
        agentId
      ]?.runId,
    );

  if (previousRunId) {
    return previousRunId;
  }

  const explicitInput =
    context.input?.[agentId];

  if (isRecord(explicitInput)) {
    const inputRunId =
      toStringValue(
        explicitInput.runId,
      );

    if (inputRunId) {
      return inputRunId;
    }
  }

  return null;
}

function getPriorExperimentResult(
  context: AgentContext,
): UnknownRecord {
  const candidates = [
    context.input?.["prior-experiment-result"],
    context.input?.["priorExperimentResult"],
    context.input?.["experiment-result"],
    context.input?.["experimentResult"],
    context.previousResults?.[
      "result-ingestion"
    ]?.output,
  ];

  for (
    const candidate of candidates
  ) {
    if (!isRecord(candidate)) {
      continue;
    }

    if (
      isRecord(
        candidate.result,
      )
    ) {
      return candidate.result;
    }

    if (
      isRecord(
        candidate.normalizedResult,
      )
    ) {
      return candidate.normalizedResult;
    }

    if (
      isRecord(
        candidate.experiment,
      )
    ) {
      return candidate;
    }

    return candidate;
  }

  return {};
}


function buildWfoSummaryFromList(
  rows: unknown[],
): UnknownRecord | null {
  let totalFolds = 0;
  let positiveFolds = 0;
  let negativeFolds = 0;
  let inconclusiveFolds = 0;
  let sawFold = false;

  for (const row of rows) {
    if (!isRecord(row)) {
      continue;
    }

    const positive =
      Math.max(
        0,
        toNullableNumber(
          row.positive_folds ??
            row.positiveFolds,
        ) ?? 0,
      );

    const negative =
      Math.max(
        0,
        toNullableNumber(
          row.negative_folds ??
            row.negativeFolds,
        ) ?? 0,
      );

    const inconclusive =
      Math.max(
        0,
        toNullableNumber(
          row.inconclusive_folds ??
            row.inconclusiveFolds,
        ) ?? 0,
      );

    const declaredTotal =
      toNullableNumber(
        row.fold_count ??
          row.foldCount ??
          row.total_folds ??
          row.totalFolds,
      );

    const rowTotal =
      declaredTotal ??
      positive +
        negative +
        inconclusive;

    if (
      rowTotal <= 0 &&
      positive <= 0 &&
      negative <= 0 &&
      inconclusive <= 0
    ) {
      continue;
    }

    sawFold = true;
    positiveFolds += positive;
    negativeFolds += negative;
    inconclusiveFolds += inconclusive;
    totalFolds += rowTotal;
  }

  if (!sawFold || totalFolds <= 0) {
    return null;
  }

  const resolvedFolds =
    positiveFolds + negativeFolds;

  return {
    source:
      "strategy_pipeline_v6.walk_forward",
    total_folds: totalFolds,
    positive_folds: positiveFolds,
    negative_folds: negativeFolds,
    inconclusive_folds:
      inconclusiveFolds,
    resolved_folds: resolvedFolds,
    positive_ratio:
      resolvedFolds > 0
        ? positiveFolds / resolvedFolds
        : null,
    negative_ratio:
      resolvedFolds > 0
        ? negativeFolds / resolvedFolds
        : null,
    resolved_ratio:
      totalFolds > 0
        ? resolvedFolds / totalFolds
        : null,
    inconclusive_share:
      totalFolds > 0
        ? inconclusiveFolds / totalFolds
        : null,
    evidence_quality:
      resolvedFolds >=
      Math.max(1, Math.floor(totalFolds * 0.5))
        ? "SUFFICIENT"
        : "INSUFFICIENT",
  };
}

function looksLikeCanonicalV6Wfo(
  value: UnknownRecord,
): boolean {
  const source = toStringValue(
    value.source ??
      value.wfoSource ??
      value.wfo_source,
  ).toLowerCase();

  if (
    source ===
    "strategy_pipeline_v6.walk_forward"
  ) {
    return true;
  }

  const file = toStringValue(
    value.file ??
      value.path ??
      value.sourceFile ??
      value.source_file,
  ).toLowerCase();

  return (
    file.includes(
      "strategy_pipeline_v6_",
    ) &&
    ("total_folds" in value ||
      "totalFolds" in value ||
      "walk_forward" in value ||
      "walkForward" in value)
  );
}

function findCanonicalV6Wfo(
  root: unknown,
): UnknownRecord | null {
  const seen = new Set<object>();

  function visit(
    value: unknown,
    path: string[],
  ): UnknownRecord | null {
    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        const found = visit(
          value[index],
          [...path, String(index)],
        );
        if (found) {
          return found;
        }
      }
      return null;
    }

    if (!isRecord(value)) {
      return null;
    }

    if (seen.has(value)) {
      return null;
    }
    seen.add(value);

    const isV6Path = path.some((part) =>
      part.toLowerCase().includes("pipeline") ||
      part.toLowerCase().includes("strategy"),
    );

    const hasAggregateWfoFields =
      ("total_folds" in value ||
        "totalFolds" in value) &&
      ("positive_folds" in value ||
        "positiveFolds" in value) &&
      ("negative_folds" in value ||
        "negativeFolds" in value);

    if (
      looksLikeCanonicalV6Wfo(value) ||
      (isV6Path && hasAggregateWfoFields)
    ) {
      const walkForward =
        value.walk_forward ??
        value.walkForward;

      if (Array.isArray(walkForward)) {
        const aggregated =
          buildWfoSummaryFromList(
            walkForward,
          );
        if (aggregated) {
          return {
            ...value,
            ...aggregated,
          };
        }
      }

      return value;
    }

    const walkForward =
      value.walk_forward ??
      value.walkForward;

    if (
      Array.isArray(walkForward) &&
      isV6Path
    ) {
      const aggregated =
        buildWfoSummaryFromList(
          walkForward,
        );
      if (aggregated) {
        return aggregated;
      }
    }

    const priorityKeys = [
      "pipeline",
      "strategy",
      "wfo",
      "wfoSummary",
      "wfo_summary",
      "walk_forward",
      "walkForward",
      "data",
      "evidence",
      "result",
      "results",
    ];

    for (const key of priorityKeys) {
      if (!(key in value)) {
        continue;
      }

      const found = visit(
        value[key],
        [...path, key],
      );
      if (found) {
        return found;
      }
    }

    for (const [key, child] of Object.entries(value)) {
      if (priorityKeys.includes(key)) {
        continue;
      }

      const found = visit(
        child,
        [...path, key],
      );
      if (found) {
        return found;
      }
    }

    return null;
  }

  return visit(root, []);
}

function extractMetric(
  roots: UnknownRecord[],
  keys: string[]
): number | null {
  for (
    const root of roots
  ) {
    for (
      const key of keys
    ) {
      const direct =
        toNullableNumber(
          root[key]
        );

      if (
        direct !== null
      ) {
        return direct;
      }
    }

    const nestedCandidates = [
      root.metrics,
      root.normalizedMetrics,
      root.summary,
      root.ranking,
      root.results,
      root.validation,
      root.backtest,
      root.evidence,
      root.wfo,
      root.researchValidation,
      root.research_validation,
      root.runnerEvidence,
      root.runner_evidence,
      root.pipeline,
      root.strategy,
      root.wfoSummary,
      root.wfo_summary,
    ];

    for (
      const candidate of nestedCandidates
    ) {
      if (
        !isRecord(
          candidate
        )
      ) {
        continue;
      }

      const nested =
        extractMetric(
          [candidate],
          keys
        );

      if (
        nested !== null
      ) {
        return nested;
      }
    }
  }

  return null;
}

function extractString(
  roots: UnknownRecord[],
  keys: string[]
): string | null {
  for (const root of roots) {
    for (const key of keys) {
      const direct = root[key];
      if (typeof direct === "string" && direct.trim()) {
        return direct.trim();
      }
    }

    const nestedCandidates = [
      root.metrics,
      root.normalizedMetrics,
      root.summary,
      root.ranking,
      root.results,
      root.validation,
      root.backtest,
      root.evidence,
      root.researchValidation,
      root.wfo,
      root.runnerResearchValidation,
    ];

    for (const candidate of nestedCandidates) {
      if (!isRecord(candidate)) {
        continue;
      }
      const nested = extractString([candidate], keys);
      if (nested !== null) {
        return nested;
      }
    }
  }
  return null;
}

function summarizeResultType(
  metrics: NormalizedExperimentResult["normalizedMetrics"],
  availableSourceCount: number
): {
  resultType:
    | "POSITIVE"
    | "MIXED"
    | "NEGATIVE"
    | "UNKNOWN";

  summary: string;
} {
  if (
    availableSourceCount ===
    0
  ) {
    return {
      resultType:
        "UNKNOWN",
      summary:
        "No source research result was available for ingestion.",
    };
  }

  const positiveSignals =
    [
      metrics.profitFactor !==
        null &&
        metrics.profitFactor >
          1,

      metrics.pnl !== null &&
        metrics.pnl > 0,

      metrics.holdoutPositiveRatio !==
        null &&
        metrics.holdoutPositiveRatio >=
          0.5,

      metrics.crossSymbolPositiveRatio !==
        null &&
        metrics.crossSymbolPositiveRatio >=
          0.5,

      metrics.costSurvival !==
        null &&
        metrics.costSurvival >=
          0.5,

      metrics.parameterStability !==
        null &&
        metrics.parameterStability >=
          0.5,

      metrics.regimeStability !==
        null &&
        metrics.regimeStability >=
          0.5,
    ].filter(
      Boolean
    ).length;

  const negativeSignals =
    [
      metrics.profitFactor !==
        null &&
        metrics.profitFactor <
          1,

      metrics.pnl !== null &&
        metrics.pnl < 0,

      metrics.holdoutPositiveRatio !==
        null &&
        metrics.holdoutPositiveRatio <
          0.5,

      metrics.crossSymbolPositiveRatio !==
        null &&
        metrics.crossSymbolPositiveRatio <
          0.5,

      metrics.costSurvival !==
        null &&
        metrics.costSurvival <
          0.5,

      metrics.parameterStability !==
        null &&
        metrics.parameterStability <
          0.5,

      metrics.regimeStability !==
        null &&
        metrics.regimeStability <
          0.5,
    ].filter(
      Boolean
    ).length;

  if (
    positiveSignals >=
      4 &&
    positiveSignals >
      negativeSignals
  ) {
    return {
      resultType:
        "POSITIVE",
      summary:
        "Available research outputs contain predominantly positive normalized signals.",
    };
  }

  if (
    negativeSignals >=
      4 &&
    negativeSignals >
      positiveSignals
  ) {
    return {
      resultType:
        "NEGATIVE",
      summary:
        "Available research outputs contain predominantly negative normalized signals.",
    };
  }

  if (
    positiveSignals >
      0 ||
    negativeSignals >
      0
  ) {
    return {
      resultType:
        "MIXED",
      summary:
        "Research outputs contain mixed or incomplete signals and require further evaluation.",
    };
  }

  return {
    resultType:
      "UNKNOWN",
    summary:
      "Source outputs were available but no interpretable normalized metrics were found.",
  };
}

async function persistResearchStorage(
  context: AgentContext,
  experiment: UnknownRecord,
  normalizedResult: UnknownRecord,
  runner: UnknownRecord,
  validation: UnknownRecord,
  evidence: UnknownRecord,
): Promise<UnknownRecord> {
  const enabled =
    process.env.MARKETHQ_RESEARCH_STORAGE_ENABLED !== "false";

  if (!enabled) {
    return {
      enabled: false,
      persisted: false,
      status: "DISABLED",
      reason:
        "MARKETHQ_RESEARCH_STORAGE_ENABLED=false; Research Storage persistence intentionally disabled.",
      safety: {
        researchOnly: true,
        operationalDatabaseWriteEnabled: false,
        researchStorageWritePerformed: false,
        brokerExecutionEnabled: false,
      },
    };
  }

  const cwd = process.cwd();
  const configuredProjectRoot =
    process.env.MARKETHQ_PROJECT_ROOT?.trim();

  const projectRoot =
    configuredProjectRoot ||
    (
      path.basename(cwd).toLowerCase() === "frontend"
        ? path.resolve(cwd, "..")
        : cwd
    );

  const adapterCandidates = [
    path.join(projectRoot, "research_storage_adapter_v1.py"),
    path.join(projectRoot, "agents", "research_storage_adapter_v1.py"),
  ];

  const adapterPath =
    adapterCandidates.find((candidate) =>
      existsSync(candidate)
    ) ?? adapterCandidates[0];

  const pythonExecutable =
    process.env.MARKETHQ_PYTHON?.trim() || "python";

  const payload = JSON.stringify({
    runId: context.runId,
    experiment,
    normalizedResult,
    runner,
    validation,
    evidence,
  });

  console.log(
    "[MarketHQ][ResultIngestion][ResearchStorage] starting persistence",
    JSON.stringify({
      runId: context.runId,
      experimentId: normalizedResult.experimentId ?? null,
      resultId: normalizedResult.resultId ?? null,
      adapterPath,
      adapterExists: existsSync(adapterPath),
      cwd,
      projectRoot,
      pythonExecutable,
    }),
  );

  if (!existsSync(adapterPath)) {
    return Promise.resolve({
      enabled: true,
      persisted: false,
      status: "FAILED",
      reason: "RESEARCH_STORAGE_ADAPTER_NOT_FOUND",
      error: `Research Storage adapter bulunamadı. Aranan yollar: ${adapterCandidates.join(" | ")}`,
      adapterPath,
      cwd,
      projectRoot,
      safety: {
        researchOnly: true,
        operationalDatabaseWriteEnabled: false,
        researchStorageWritePerformed: false,
        brokerExecutionEnabled: false,
      },
    });
  }

  return new Promise<UnknownRecord>((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;

    const finish = (result: UnknownRecord): void => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    const child = spawn(
      pythonExecutable,
      [adapterPath],
      {
        cwd: projectRoot,
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );

    const timeout = setTimeout(() => {
      child.kill();
      finish({
        enabled: true,
        persisted: false,
        status: "FAILED",
        reason: "RESEARCH_STORAGE_TIMEOUT",
        error:
          "Research Storage adapter zaman aşımına uğradı.",
        adapterPath,
        stderr: stderr.trim() || undefined,
        safety: {
          researchOnly: true,
          operationalDatabaseWriteEnabled: false,
          researchStorageWritePerformed: false,
          brokerExecutionEnabled: false,
        },
      });
    }, 30_000);

    child.stdout.on("data", (chunk: Buffer | string) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk: Buffer | string) => {
      stderr += chunk.toString();
    });

    child.on("error", (error) => {
      clearTimeout(timeout);
      finish({
        enabled: true,
        persisted: false,
        status: "FAILED",
        reason: "RESEARCH_STORAGE_PROCESS_ERROR",
        error: error.message,
        adapterPath,
        stderr: stderr.trim() || undefined,
        safety: {
          researchOnly: true,
          operationalDatabaseWriteEnabled: false,
          researchStorageWritePerformed: false,
          brokerExecutionEnabled: false,
        },
      });
    });

    child.on("close", (exitCode) => {
      clearTimeout(timeout);
      const rawOutput = stdout.trim();

      if (!rawOutput) {
        finish({
          enabled: true,
          persisted: false,
          status: "FAILED",
          reason: "RESEARCH_STORAGE_EMPTY_OUTPUT",
          exitCode,
          adapterPath,
          stderr: stderr.trim() || undefined,
          safety: {
            researchOnly: true,
            operationalDatabaseWriteEnabled: false,
            researchStorageWritePerformed: false,
            brokerExecutionEnabled: false,
          },
        });
        return;
      }

      try {
        const parsed: unknown = JSON.parse(rawOutput);

        if (!isRecord(parsed)) {
          finish({
            enabled: true,
            persisted: false,
            status: "FAILED",
            reason: "RESEARCH_STORAGE_INVALID_OUTPUT",
            exitCode,
            adapterPath,
            stderr: stderr.trim() || undefined,
            safety: {
              researchOnly: true,
              operationalDatabaseWriteEnabled: false,
              researchStorageWritePerformed: false,
              brokerExecutionEnabled: false,
            },
          });
          return;
        }

        finish({
          ...parsed,
          enabled: true,
          persisted: parsed.success === true,
          status: parsed.success === true ? "PERSISTED" : "FAILED",
          exitCode,
          adapterPath,
          stderr: stderr.trim() || undefined,
        });
      } catch (error) {
        finish({
          enabled: true,
          persisted: false,
          status: "FAILED",
          reason: "RESEARCH_STORAGE_INVALID_JSON",
          error:
            error instanceof Error
              ? error.message
              : String(error),
          exitCode,
          adapterPath,
          rawOutput,
          stderr: stderr.trim() || undefined,
          safety: {
            researchOnly: true,
            operationalDatabaseWriteEnabled: false,
            researchStorageWritePerformed: false,
            brokerExecutionEnabled: false,
          },
        });
      }
    });

    child.stdin.on("error", (error) => {
      clearTimeout(timeout);
      finish({
        enabled: true,
        persisted: false,
        status: "FAILED",
        reason: "RESEARCH_STORAGE_STDIN_ERROR",
        error: error.message,
        adapterPath,
        stderr: stderr.trim() || undefined,
        safety: {
          researchOnly: true,
          operationalDatabaseWriteEnabled: false,
          researchStorageWritePerformed: false,
          brokerExecutionEnabled: false,
        },
      });
    });

    child.stdin.write(payload);
    child.stdin.end();
  });
}

export async function runResultIngestionAgent(
  context: AgentContext
): Promise<
  Record<string, unknown>
> {
  const generator =
    getAgentOutput(
      context,
      "experiment-generator"
    );

  const runner =
    getAgentOutput(
      context,
      "experiment-runner"
    );

  const paperTrading =
    getAgentOutput(
      context,
      "paper-trading"
    );

  const backtest =
    getAgentOutput(
      context,
      "backtest"
    );

  const validation =
    getAgentOutput(
      context,
      "validation"
    );

  const evidence =
    getAgentOutput(
      context,
      "evidence"
    );

  const priorExperimentResult =
    getPriorExperimentResult(
      context,
    );

  const experiment =
    firstRecord(
      generator.experiment,
      runner.experiment,
      priorExperimentResult.experiment,
      priorExperimentResult,
    );

  const strategy =
    firstRecord(
      experiment.strategy,
      priorExperimentResult.strategy,
    );

  const market =
    firstRecord(
      experiment.market,
      priorExperimentResult.market,
    );

  const experimentId =
    toStringValue(
      experiment.experimentId,
      toStringValue(
        priorExperimentResult.experimentId,
      ),
    );

  const researchQuestion =
    toStringValue(
      experiment.researchQuestion,
      toStringValue(
        priorExperimentResult.researchQuestion,
      ),
    );

  const hypothesis =
    toStringValue(
      experiment.hypothesis,
      toStringValue(
        priorExperimentResult.hypothesis,
      ),
    );

  const strategyId =
    toStringValue(
      strategy.strategyId,
      context.strategyId ??
        "UNKNOWN_STRATEGY"
    );

  const strategyName =
    toStringValue(
      strategy.name,
      strategyId
    );

  const symbol =
    toStringValue(
      market.symbol,
      context.symbol ??
        "UNKNOWN"
    );

  const timeframe =
    toStringValue(
      market.timeframe,
      context.timeframe ??
        "1d"
    );

  if (
    !experimentId ||
    !researchQuestion
  ) {
    return {
      agent:
        "result-ingestion",

      runId:
        context.runId,

      status:
        "BLOCKED",

      reason:
        "No current or prior experiment result with a valid experiment ID and research question was available. Same-run ingestion intentionally waits for a later research cycle or an explicit prior result input.",

      ingestionSource:
        Object.keys(
          priorExperimentResult,
        ).length > 0
          ? "EXPLICIT_OR_PREVIOUS_RESULT"
          : "NONE",

      safety: {
        researchOnly:
          true,

        executionEnabled:
          false,

        databaseWriteEnabled:
          false,

        brokerExecutionEnabled:
          false,
      },

      mode:
        "READ_ONLY_RESULT_INGESTION",
    };
  }

  const sourceList:
    SourceReference[] = [
      {
        agentId:
          "experiment-generator",
        runId:
          getAgentRunId(
            context,
            "experiment-generator"
          ),
        available:
          Object.keys(
            generator
          ).length > 0,
      },
      {
        agentId:
          "experiment-runner",
        runId:
          getAgentRunId(
            context,
            "experiment-runner"
          ),
        available:
          Object.keys(
            runner
          ).length > 0,
      },
      {
        agentId:
          "paper-trading",
        runId:
          getAgentRunId(
            context,
            "paper-trading"
          ),
        available:
          Object.keys(
            paperTrading
          ).length > 0,
      },
      {
        agentId:
          "backtest",
        runId:
          getAgentRunId(
            context,
            "backtest"
          ),
        available:
          Object.keys(
            backtest
          ).length > 0,
      },
      {
        agentId:
          "validation",
        runId:
          getAgentRunId(
            context,
            "validation"
          ),
        available:
          Object.keys(
            validation
          ).length > 0,
      },
      {
        agentId:
          "evidence",
        runId:
          getAgentRunId(
            context,
            "evidence"
          ),
        available:
          Object.keys(
            evidence
          ).length > 0,
      },
    ];

  const missingSources =
    sourceList
      .filter(
        (source) =>
          !source.available &&
          source.agentId !== "paper-trading"
      )
      .map(
        (source) =>
          source.agentId
      );

  const availableSourceCount =
    sourceList.filter(
      (source) =>
        source.available
    ).length;

  const canonicalV6Wfo =
    findCanonicalV6Wfo(
      evidence,
    ) ??
    findCanonicalV6Wfo(
      context.input?.["pipeline"],
    ) ??
    findCanonicalV6Wfo(
      context.input?.["strategy"],
    );

  // WFO fallback intentionally excludes the experiment-runner root.
  // Runner WFO is a local 8-fold experiment artifact and must never
  // override the canonical V6 strategy-pipeline WFO evidence.
  const metricRoots = [
    backtest,
    validation,
    evidence,
    generator,
  ];

  const runnerMetricRoots = [
    runner,
  ];

  const normalizedMetrics =
    {
      profitFactor:
        extractMetric(
          metricRoots,
          [
            "profitFactor",
            "profit_factor",
            "pf",
          ]
        ),

      pnl:
        extractMetric(
          metricRoots,
          [
            "pnl",
            "PnL",
            "netPnl",
            "net_pnl",
            "totalPnl",
          ]
        ),

      maxDrawdown:
        extractMetric(
          metricRoots,
          [
            "maxDrawdown",
            "max_drawdown",
            "drawdown",
            "maxDd",
          ]
        ),

      holdoutPositiveRatio:
        extractMetric(
          metricRoots,
          [
            "holdoutPositiveRatio",
            "holdout_positive_ratio",
            "holdoutRatio",
            "holdout_positive",
          ]
        ),

      crossSymbolPositiveRatio:
        extractMetric(
          metricRoots,
          [
            "crossSymbolPositiveRatio",
            "cross_symbol_positive_ratio",
            "crossSymbolPositive",
          ]
        ),

      costSurvival:
        extractMetric(
          metricRoots,
          [
            "costSurvival",
            "cost_survival",
            "costRobustness",
            "cost_robustness",
          ]
        ),

      parameterStability:
        extractMetric(
          metricRoots,
          [
            "parameterStability",
            "parameter_stability",
          ]
        ),

      regimeStability:
        extractMetric(
          metricRoots,
          [
            "regimeStability",
            "regime_stability",
          ]
        ),

      fullRunPositiveRatio:
        extractMetric(
          metricRoots,
          [
            "fullRunPositiveRatio",
            "full_run_positive_ratio",
            "fullRunRatio",
            "pooledPositiveRatio",
          ]
        ),

      confidence:
        extractMetric(
          metricRoots,
          [
            "confidence",
            "confidenceScore",
          ]
        ),

      wfoTotalFolds:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.total_folds ??
                canonicalV6Wfo.totalFolds,
            )
          : extractMetric(
              metricRoots,
              ["totalFolds", "total_folds"],
            ),

      wfoPositiveFolds:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.positive_folds ??
                canonicalV6Wfo.positiveFolds,
            )
          : extractMetric(
              metricRoots,
              [
                "positiveFolds",
                "positive_folds",
              ],
            ),

      wfoNegativeFolds:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.negative_folds ??
                canonicalV6Wfo.negativeFolds,
            )
          : extractMetric(
              metricRoots,
              [
                "negativeFolds",
                "negative_folds",
              ],
            ),

      wfoInconclusiveFolds:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.inconclusive_folds ??
                canonicalV6Wfo.inconclusiveFolds,
            )
          : extractMetric(
              metricRoots,
              [
                "inconclusiveFolds",
                "inconclusive_folds",
              ],
            ),

      wfoResolvedFolds:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.resolved_folds ??
                canonicalV6Wfo.resolvedFolds,
            )
          : extractMetric(
              metricRoots,
              [
                "resolvedFolds",
                "resolved_folds",
              ],
            ),

      wfoPositiveRatio:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.positive_ratio ??
                canonicalV6Wfo.positiveRatio,
            )
          : extractMetric(
              metricRoots,
              [
                "positiveRatio",
                "positive_ratio",
              ],
            ),

      wfoNegativeRatio:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.negative_ratio ??
                canonicalV6Wfo.negativeRatio,
            )
          : extractMetric(
              metricRoots,
              [
                "negativeRatio",
                "negative_ratio",
              ],
            ),

      wfoResolvedRatio:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.resolved_ratio ??
                canonicalV6Wfo.resolvedRatio,
            )
          : extractMetric(
              metricRoots,
              [
                "resolvedRatio",
                "resolved_ratio",
              ],
            ),

      wfoInconclusiveShare:
        canonicalV6Wfo
          ? toNullableNumber(
              canonicalV6Wfo.inconclusive_share ??
                canonicalV6Wfo.inconclusiveShare,
            )
          : extractMetric(
              metricRoots,
              [
                "inconclusiveShare",
                "inconclusive_share",
              ],
            ),

      wfoEvidenceQuality:
        canonicalV6Wfo
          ? toStringValue(
              canonicalV6Wfo.evidence_quality ??
                canonicalV6Wfo.evidenceQuality,
            ) || null
          : extractString(
              metricRoots,
              [
                "evidenceQuality",
                "evidence_quality",
              ],
            ),

      robustnessScore:
        extractMetric(
          runnerMetricRoots,
          [
            "robustnessScore",
            "robustness_score",
          ],
        ),

      monteCarloPositiveProbability:
        extractMetric(
          runnerMetricRoots,
          [
            "monteCarloPositiveProbability",
            "monte_carlo_positive_probability",
            "positiveProbability",
          ],
        ),

      stressPositiveScenarioRatio:
        extractMetric(
          runnerMetricRoots,
          [
            "stressPositiveScenarioRatio",
            "stress_positive_scenario_ratio",
            "positiveScenarioRatio",
          ],
        ),

      stressWorstMetric:
        extractMetric(
          runnerMetricRoots,
          [
            "stressWorstMetric",
            "stress_worst_metric",
            "worstMetric",
          ],
        ),

    };

  const metricCount =
    Object.values(
      normalizedMetrics
    ).filter(
      (
        value
      ) =>
        value !== null
    ).length;

  const conclusion =
    summarizeResultType(
      normalizedMetrics,
      availableSourceCount
    );

  let ingestionStatus:
    IngestionStatus;

  if (
    missingSources.length ===
      0 &&
    metricCount > 0
  ) {
    ingestionStatus =
      "INGESTED";
  } else if (
    availableSourceCount > 0
  ) {
    ingestionStatus =
      "PARTIAL";
  } else {
    ingestionStatus =
      "BLOCKED";
  }

  const normalizedResult:
    NormalizedExperimentResult = {
      experimentId,

      status:
        ingestionStatus,

      researchQuestion,

      hypothesis,

      strategy: {
        strategyId,
        name:
          strategyName,
        symbol,
        timeframe,
      },

      sources: {
        experimentGenerator:
          sourceList.find(
            (source) =>
              source.agentId === "experiment-generator",
          )!,
        experimentRunner:
          sourceList.find(
            (source) =>
              source.agentId === "experiment-runner",
          )!,
        backtest:
          sourceList.find(
            (source) =>
              source.agentId === "backtest",
          )!,
        validation:
          sourceList.find(
            (source) =>
              source.agentId === "validation",
          )!,
        evidence:
          sourceList.find(
            (source) =>
              source.agentId === "evidence",
          )!,
        paperTrading:
          sourceList.find(
            (source) =>
              source.agentId === "paper-trading",
          ),
      },

      results: {
        backtest,
        validation,
        evidence,
        paperTrading:
          Object.keys(paperTrading).length > 0
            ? paperTrading
            : undefined,
      },

      normalizedMetrics,

      robustness:
        isRecord(runner.robustnessSummary)
          ? {
              ...runner.robustnessSummary,
            }
          : undefined,

      quality: {
        sourceCount:
          sourceList.length,

        availableSourceCount,

        missingSources,

        metricCount,
      },

      conclusion,

      nextResearchInput: {
        canFeedLearning:
          ingestionStatus !==
            "BLOCKED" &&
          metricCount > 0,

        recommendedNextStep:
          conclusion.resultType ===
          "POSITIVE"
            ? "Pass the normalized experiment result to Learning for independent assessment and replication tracking."
            : conclusion.resultType ===
                "NEGATIVE"
              ? "Pass the normalized experiment result to Learning and Research Decision to evaluate whether the candidate should be deprioritized or retested."
              : "Pass the normalized experiment result to Learning and Research Decision for further evidence or robustness analysis.",
      },

      provenance: {
        ingestionRunId:
          context.runId,

        sourceRunIds: {
          experimentGenerator:
            getAgentRunId(
              context,
              "experiment-generator"
            ),

          experimentRunner:
            getAgentRunId(
              context,
              "experiment-runner"
            ),

          backtest:
            getAgentRunId(
              context,
              "backtest"
            ),

          validation:
            getAgentRunId(
              context,
              "validation"
            ),

          evidence:
            getAgentRunId(
              context,
              "evidence"
            ),

          paperTrading:
            getAgentRunId(
              context,
              "paper-trading"
            ),
        },
      },

      safety: {
        researchOnly:
          true,

        executionEnabled:
          false,

        databaseWriteEnabled:
          false,

        brokerExecutionEnabled:
          false,
      },
    };

  const storage = await persistResearchStorage(
    context,
    experiment,
    normalizedResult as unknown as UnknownRecord,
    runner,
    validation,
    evidence,
  );

  return {
    agent:
      "result-ingestion",

    runId:
      context.runId,

    // Expose the canonical experiment identity at the agent-output root.
    // E2E/Downstream agents may consume the Result Ingestion output directly.
    experimentId,

    researchQuestion,

    strategyId,

    strategyName,

    symbol,

    timeframe,

    result:
      normalizedResult,

    paperTrading:
      Object.keys(paperTrading).length > 0
        ? paperTrading
        : undefined,

    storage,

    ingestion: {
      status:
        ingestionStatus,

      sourceCount:
        sourceList.length,

      availableSourceCount,

      missingSources,

      metricCount,

      learningReady:
        normalizedResult.nextResearchInput.canFeedLearning,

      sourceCycle:
        Object.keys(
          priorExperimentResult,
        ).length > 0 &&
        Object.keys(
          generator,
        ).length === 0 &&
        Object.keys(
          runner,
        ).length === 0
          ? "PRIOR_CYCLE_RESULT"
          : "CURRENT_PIPELINE",
    },

    safety: {
      researchOnly:
        true,

      executionEnabled:
        false,

      databaseWriteEnabled:
        false,

      brokerExecutionEnabled:
        false,

      operationalDatabaseWriteEnabled:
        false,

      researchStorageWriteEnabled:
        storage.persisted === true,

      researchStorageWritePerformed:
        storage.persisted === true,
    },

    mode:
      "RESEARCH_STORAGE_RESULT_INGESTION_V1",

    cycle: {
      usedPriorCycleResult:
        Object.keys(
          priorExperimentResult,
        ).length > 0 &&
        Object.keys(
          generator,
        ).length === 0 &&
        Object.keys(
          runner,
        ).length === 0,

      currentGeneratorAvailable:
        Object.keys(
          generator,
        ).length > 0,

      currentRunnerAvailable:
        Object.keys(
          runner,
        ).length > 0,
    },

    ingestedAt:
      new Date().toISOString(),
  };
}

export function registerResultIngestionAgent(): void {
  agentRunner.register(
    "result-ingestion",
    runResultIngestionAgent
  );
}




