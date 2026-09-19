import type {
  AgentContext,
} from "./agent-types";

import { spawn } from "child_process";
import path from "path";
import { existsSync } from "node:fs";

import {
  agentRunner,
} from "./agent-runner";

import marketHQApi from "../../lib/markethq-api";

function isRecord(
  value: unknown
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getString(
  value: unknown
): string | null {
  return typeof value === "string" &&
    value.trim().length > 0
    ? value.trim()
    : null;
}

function getNumber(
  value: unknown
): number | null {
  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return value;
  }

  if (
    typeof value === "string" &&
    value.trim().length > 0
  ) {
    const parsed = Number(value);

    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
}

function findValueRecursive(
  value: unknown,
  keys: string[]
): unknown {
  if (isRecord(value)) {
    for (const key of keys) {
      if (key in value) {
        return value[key];
      }
    }

    for (const child of Object.values(value)) {
      const found =
        findValueRecursive(
          child,
          keys
        );

      if (found !== undefined) {
        return found;
      }
    }
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found =
        findValueRecursive(
          item,
          keys
        );

      if (found !== undefined) {
        return found;
      }
    }
  }

  return undefined;
}

function firstString(
  root: unknown,
  keys: string[]
): string | null {
  return getString(
    findValueRecursive(
      root,
      keys
    )
  );
}

function firstNumber(
  root: unknown,
  keys: string[]
): number | null {
  return getNumber(
    findValueRecursive(
      root,
      keys
    )
  );
}

function findRecordRecursive(
  value: unknown,
  keys: string[]
): Record<string, unknown> | null {
  if (isRecord(value)) {
    const hasTargetKey =
      keys.some(
        (key) => key in value
      );

    if (hasTargetKey) {
      return value;
    }

    for (const child of Object.values(value)) {
      const found =
        findRecordRecursive(
          child,
          keys
        );

      if (found) {
        return found;
      }
    }
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found =
        findRecordRecursive(
          item,
          keys
        );

      if (found) {
        return found;
      }
    }
  }

  return null;
}

function normalizeResultIngestion(
  result: unknown
): Record<string, unknown> {
  if (!result) {
    return {
      available: false,
      status: "NOT_AVAILABLE",
      experimentId: null,
      resultId: null,
      researchQuestion: null,
      strategyId: null,
      strategyName: null,
      symbol: null,
      timeframe: null,
      metricCount: 0,
      sourceCount: 0,
      availableSourceCount: 0,
      resultType: null,
      reason:
        "Bu orchestrator turunda Result Ingestion çıktısı bulunamadı.",
      raw: null,
    };
  }

  const experimentId =
    firstString(
      result,
      [
        "experimentId",
        "experiment_id",
      ]
    ) ??
    (
      firstNumber(
        result,
        [
          "experimentId",
          "experiment_id",
        ]
      ) !== null
        ? String(
            firstNumber(
              result,
              [
                "experimentId",
                "experiment_id",
              ]
            )
          )
        : null
    );

  const researchQuestion =
    firstString(
      result,
      [
        "researchQuestion",
        "research_question",
      ]
    );

  const strategyId =
    firstString(
      result,
      [
        "strategyId",
        "strategy_id",
      ]
    );

  const strategyName =
    firstString(
      result,
      [
        "strategyName",
        "strategy_name",
        "name",
      ]
    );

  const symbol =
    firstString(
      result,
      [
        "symbol",
        "requestedSymbol",
      ]
    );

  const timeframe =
    firstString(
      result,
      [
        "timeframe",
        "requestedTimeframe",
      ]
    );

  const status =
    firstString(
      result,
      [
        "status",
      ]
    ) ?? "UNKNOWN";

  const resultType =
    firstString(
      result,
      [
        "resultType",
        "result_type",
      ]
    );

  const sourceCount =
    firstNumber(
      result,
      [
        "sourceCount",
        "source_count",
      ]
    ) ?? 0;

  const availableSourceCount =
    firstNumber(
      result,
      [
        "availableSources",
        "availableSourceCount",
        "available_source_count",
      ]
    ) ?? 0;

  const metricCount =
    firstNumber(
      result,
      [
        "metricCount",
        "metric_count",
      ]
    ) ?? 0;

  const experimentRecord =
    findRecordRecursive(
      result,
      [
        "experimentId",
        "experiment_id",
      ]
    );

  const researchRecord =
    findRecordRecursive(
      result,
      [
        "researchQuestion",
        "research_question",
      ]
    );

  const metricsRecord =
    findRecordRecursive(
      result,
      [
        "metrics",
      ]
    );

  const provenanceRecord =
    findRecordRecursive(
      result,
      [
        "provenance",
        "sources",
      ]
    );

  const available =
    Boolean(
      experimentId ||
      researchQuestion ||
      experimentRecord ||
      researchRecord
    );

  return {
    available,

    status:

      available
        ? status
        : "NOT_AVAILABLE",

    experimentId,

    resultId:
      firstString(
        result,
        [
          "resultId",
          "result_id",
        ],
      ),

    researchQuestion,

    strategyId,

    strategyName,

    symbol,

    timeframe,

    resultType,

    metricCount,

    sourceCount,

    availableSourceCount,

    experiment: experimentRecord,

    research: researchRecord,

    metrics: metricsRecord,

    provenance: provenanceRecord,

    raw: result,
  };
}


interface ResearchMemoryPersistence {
  enabled: boolean;
  persisted: boolean;
  status: string;
  reason?: string;
  error?: string;
  exitCode?: number | null;
  adapterPath?: string;
  cwd?: string;
  projectRoot?: string;
  pythonExecutable?: string;
  stderr?: string;
  rawOutput?: string;
  [key: string]: unknown;
}

function compactMemoryValue(
  value: unknown,
  maxStringLength = 2000,
): unknown {
  if (typeof value === "string") {
    return value.length > maxStringLength
      ? `${value.slice(0, maxStringLength)}…`
      : value;
  }

  if (Array.isArray(value)) {
    return value.slice(0, 20).map((item) =>
      compactMemoryValue(item, maxStringLength),
    );
  }

  if (isRecord(value)) {
    const entries = Object.entries(value).slice(0, 40);
    return Object.fromEntries(
      entries.map(([key, child]) => [
        key,
        compactMemoryValue(child, maxStringLength),
      ]),
    );
  }

  return value;
}

function numberOrNull(value: unknown): number | null {
  const parsed = getNumber(value);
  return parsed !== null ? parsed : null;
}

function deriveMemoryDecision(
  resultType: string | null,
): "PROMISING" | "MIXED" | "REJECT" | "INCONCLUSIVE" {
  switch (resultType) {
    case "POSITIVE":
      return "PROMISING";
    case "NEGATIVE":
      return "REJECT";
    case "MIXED":
      return "MIXED";
    default:
      return "INCONCLUSIVE";
  }
}

function findFirstFiniteNumberRecursive(
  value: unknown,
  keys: string[],
  visited = new Set<unknown>(),
): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "object" || typeof value === "function") {
    if (visited.has(value)) {
      return null;
    }
    visited.add(value);
  }

  if (isRecord(value)) {
    for (const key of keys) {
      if (!(key in value)) {
        continue;
      }

      const candidate =
        numberOrNull(value[key]);

      if (candidate !== null) {
        return candidate;
      }
    }

    for (const child of Object.values(value)) {
      const found =
        findFirstFiniteNumberRecursive(
          child,
          keys,
          visited,
        );

      if (found !== null) {
        return found;
      }
    }
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found =
        findFirstFiniteNumberRecursive(
          item,
          keys,
          visited,
        );

      if (found !== null) {
        return found;
      }
    }
  }

  return null;
}

function clampConfidence(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function deriveResearchConfidence(
  ingestedResult: Record<string, unknown>,
  context: AgentContext,
): number | null {
  const confidenceKeys = [
    "confidence",
    "researchConfidence",
    "research_confidence",
    "evidenceConfidence",
    "evidence_confidence",
    "validationConfidence",
    "validation_confidence",
  ];

  // 1) Prefer an explicit confidence already attached to
  // Result Ingestion / its normalized metrics.
  const directIngestionConfidence =
    findFirstFiniteNumberRecursive(
      ingestedResult,
      confidenceKeys,
    );

  if (directIngestionConfidence !== null) {
    return clampConfidence(
      directIngestionConfidence,
    );
  }

  // 2) Result Ingestion may not expose confidence at its root,
  // while the same research run's validation/evidence/backtest
  // outputs can already contain an explicit confidence value.
  // This is a read-only fallback: it does not change any rules
  // or execution behaviour.
  const previousResults =
    context.previousResults ?? {};

  const confidenceSources: unknown[] = [
    previousResults["validation"]?.output,
    previousResults["evidence"]?.output,
    previousResults["backtest"]?.output,
    previousResults["brain"]?.output,
  ];

  for (const source of confidenceSources) {
    const candidate =
      findFirstFiniteNumberRecursive(
        source,
        confidenceKeys,
      );

    if (candidate !== null) {
      return clampConfidence(candidate);
    }
  }

  // 3) If no explicit confidence exists anywhere in the current
  // research inputs, derive a deterministic coverage confidence.
  const sourceCount =
    numberOrNull(ingestedResult.sourceCount) ?? 0;

  const availableSourceCount =
    numberOrNull(
      ingestedResult.availableSourceCount,
    ) ?? 0;

  const metricCount =
    numberOrNull(ingestedResult.metricCount) ?? 0;

  if (
    sourceCount <= 0 &&
    availableSourceCount <= 0 &&
    metricCount <= 0
  ) {
    return null;
  }

  const sourceCoverage =
    sourceCount > 0
      ? Math.min(
          1,
          availableSourceCount / sourceCount,
        )
      : 0;

  const metricCoverage =
    Math.min(1, metricCount / 20);

  return Number(
    (
      sourceCoverage * 0.6 +
      metricCoverage * 0.4
    ).toFixed(4),
  );
}

function extractResearchLoop(
  ingestedResult: Record<string, unknown>,
): Record<string, unknown> {
  const raw = ingestedResult.raw;
  const loop = isRecord(raw) && isRecord(raw.researchLoop)
    ? raw.researchLoop
    : isRecord(ingestedResult.researchLoop)
      ? ingestedResult.researchLoop
      : {};

  return {
    sourceType: getString(loop.sourceType) ?? null,
    feedbackType: getString(loop.feedbackType) ?? null,
    decision: getString(loop.decision) ?? null,
    action: getString(loop.action) ?? null,
    researchMode: getString(loop.researchMode) ?? null,
    priorityAdjustment: getNumber(loop.priorityAdjustment),
    feedbackReason: getString(loop.feedbackReason) ?? null,
    nextResearchQuestion: getString(loop.nextResearchQuestion) ?? null,
    generatedFromHistoricalMemory:
      loop.generatedFromHistoricalMemory === true,
    avoidsBlindRepeat:
      loop.avoidsBlindRepeat === true,
  };
}

function buildResearchMemoryPayload(
  context: AgentContext,
  ingestedResult: Record<string, unknown>,
  learningData: Record<string, unknown>,
): Record<string, unknown> {
  const resultType =
    getString(ingestedResult.resultType);

  const decision =
    deriveMemoryDecision(resultType);

  const experimentId =
    getString(ingestedResult.experimentId);

  const researchQuestion =
    getString(ingestedResult.researchQuestion);

  const strategyId =
    getString(ingestedResult.strategyId) ??
    getString(context.strategyId);

  const strategyName =
    getString(ingestedResult.strategyName);

  const symbol =
    getString(ingestedResult.symbol) ??
    getString(context.symbol);

  const timeframe =
    getString(ingestedResult.timeframe) ??
    getString(context.timeframe);

  const metrics =
    isRecord(ingestedResult.metrics)
      ? ingestedResult.metrics
      : {};

  const conclusion =
    isRecord(ingestedResult.raw)
      ? (
          isRecord(
            ingestedResult.raw.conclusion,
          )
            ? ingestedResult.raw.conclusion
            : {}
        )
      : {};

  const quality =
    isRecord(ingestedResult.raw)
      ? (
          isRecord(
            ingestedResult.raw.quality,
          )
            ? ingestedResult.raw.quality
            : {}
        )
      : {};

  const nextResearchInput =
    isRecord(ingestedResult.raw)
      ? (
          isRecord(
            ingestedResult.raw.nextResearchInput,
          )
            ? ingestedResult.raw.nextResearchInput
            : {}
        )
      : {};

  const researchLoop =
    extractResearchLoop(ingestedResult);

  const confidence =
    deriveResearchConfidence(
      ingestedResult,
      context,
    );

  const title =
    `${strategyName ?? strategyId ?? "Strategy"} research learning` +
    (symbol ? ` · ${symbol}` : "");

  const summary =
    getString(conclusion.summary) ??
    (
      resultType
        ? `Research result classified as ${resultType}.`
        : "Research result was ingested but could not be classified."
    );

  return {
    runId: context.runId,
    experimentId,
    resultId:
      getString(
        findValueRecursive(
          ingestedResult,
          [
            "resultId",
            "result_id",
          ],
        ),
      ) ??
      null,

    memoryType: "EXPERIMENT_LEARNING",
    title,
    summary,

    decision,
    confidence,

    status:
      decision === "INCONCLUSIVE"
        ? "ACTIVE"
        : "ACTIVE",

    evidence: {
      researchQuestion,
      resultType,
      metrics: compactMemoryValue(
        metrics,
      ),
      quality: compactMemoryValue(
        quality,
      ),
      conclusion: compactMemoryValue(
        conclusion,
      ),
    },

    learning: {
      strategyId,
      strategyName,
      symbol,
      timeframe,
      decision,
      confidence,
      resultType,
      performance: compactMemoryValue(metrics),
      validation: compactMemoryValue(
        findValueRecursive(
          context.previousResults?.["validation"]?.output ?? null,
          ["validation", "validationResult", "validationStatus", "validationMetrics"],
        ) ?? context.previousResults?.["validation"]?.output ?? null,
      ),
      robustness: compactMemoryValue(
        findValueRecursive(
          context.previousResults?.["validation"]?.output ?? null,
          ["robustness", "robustnessScore", "robustnessMetrics"],
        ),
      ),
      wfo: compactMemoryValue(
        findValueRecursive(
          context.previousResults?.["validation"]?.output ?? null,
          ["wfo", "walkForward", "walkForwardValidation", "walkForwardResult"],
        ),
      ),
      nextResearchInput:
        compactMemoryValue(
          nextResearchInput,
        ),
      researchLoop: compactMemoryValue(
        researchLoop,
      ),
      backendLearningSnapshot:
        compactMemoryValue(
          learningData,
        ),
    },

    metadata: {
      source:
        "MarketHQ Learning Agent",
      mode:
        "RESEARCH_STORAGE_MEMORY_V1",
      provenanceRunId:
        context.runId,
      durableMemory:
        true,
      originalRulesMutated:
        false,
    },
  };
}

async function persistResearchMemory(
  context: AgentContext,
  memoryPayload: Record<string, unknown>,
): Promise<ResearchMemoryPersistence> {
  const enabled =
    process.env.MARKETHQ_RESEARCH_STORAGE_ENABLED !== "false";

  if (!enabled) {
    return {
      enabled: false,
      persisted: false,
      status: "DISABLED",
      reason:
        "MARKETHQ_RESEARCH_STORAGE_ENABLED=false; Research Memory persistence intentionally disabled.",
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
    path.join(
      projectRoot,
      "research_memory_adapter_v1.py",
    ),
    path.join(
      projectRoot,
      "agents",
      "research_memory_adapter_v1.py",
    ),
  ];

  const adapterPath =
    adapterCandidates.find((candidate) =>
      existsSync(candidate)
    ) ?? adapterCandidates[0];

  const pythonExecutable =
    process.env.MARKETHQ_PYTHON || "python";

  const payload =
    JSON.stringify({
      runId: context.runId,

      // Research Memory Adapter V1 contract:
      // identity fields are required at the root level.
      experimentId:
        getString(memoryPayload.experimentId),
      resultId:
        getString(memoryPayload.resultId),

      memory: memoryPayload,
    });

  console.log(
    "[MarketHQ][Learning][ResearchMemory] starting persistence",
    JSON.stringify({
      runId: context.runId,
      experimentId: memoryPayload.experimentId ?? null,
      resultId: memoryPayload.resultId ?? null,
      adapterPath,
      cwd,
      projectRoot,
      pythonExecutable,
    }),
  );

  return new Promise<ResearchMemoryPersistence>(
    (resolve) => {
      let stdout = "";
      let stderr = "";
      let settled = false;

      const finish = (
        result: ResearchMemoryPersistence,
      ): void => {
        if (settled) return;
        settled = true;
        resolve(result);
      };

      const child =
        spawn(
          pythonExecutable,
          [adapterPath],
          {
            cwd: projectRoot,
            windowsHide: true,
            stdio: [
              "pipe",
              "pipe",
              "pipe",
            ],
          },
        );

      const timeout =
        setTimeout(() => {
          child.kill();
          finish({
            enabled: true,
            persisted: false,
            status: "FAILED",
            reason:
              "RESEARCH_MEMORY_TIMEOUT",
            error:
              "Research Memory adapter zaman aşımına uğradı.",
            adapterPath,
            stderr:
              stderr.trim() || undefined,
          });
        }, 30_000);

      child.stdout.on(
        "data",
        (chunk: Buffer | string) => {
          stdout += chunk.toString();
        },
      );

      child.stderr.on(
        "data",
        (chunk: Buffer | string) => {
          stderr += chunk.toString();
        },
      );

      child.on(
        "error",
        (error) => {
          clearTimeout(timeout);
          finish({
            enabled: true,
            persisted: false,
            status: "FAILED",
            reason:
              "RESEARCH_MEMORY_PROCESS_ERROR",
            error: error.message,
            adapterPath,
            stderr:
              stderr.trim() || undefined,
          });
        },
      );

      child.on(
        "close",
        (exitCode) => {
          clearTimeout(timeout);

          const rawOutput =
            stdout.trim();

          if (!rawOutput) {
            finish({
              enabled: true,
              persisted: false,
              status: "FAILED",
              reason:
                "RESEARCH_MEMORY_EMPTY_OUTPUT",
              exitCode,
              adapterPath,
              stderr:
                stderr.trim() || undefined,
            });
            return;
          }

          try {
            const parsed:
              unknown =
              JSON.parse(rawOutput);

            if (!isRecord(parsed)) {
              finish({
                enabled: true,
                persisted: false,
                status: "FAILED",
                reason:
                  "RESEARCH_MEMORY_INVALID_OUTPUT",
                exitCode,
                adapterPath,
                stderr:
                  stderr.trim() || undefined,
              });
              return;
            }

            finish({
              ...parsed,
              enabled: true,
              persisted:
                parsed.success === true,
              status:
                parsed.success === true
                  ? "PERSISTED"
                  : "FAILED",
              exitCode,
              adapterPath,
              stderr:
                stderr.trim() || undefined,
            });
          } catch (error) {
            finish({
              enabled: true,
              persisted: false,
              status: "FAILED",
              reason:
                "RESEARCH_MEMORY_INVALID_JSON",
              error:
                error instanceof Error
                  ? error.message
                  : String(error),
              exitCode,
              adapterPath,
              rawOutput,
              stderr:
                stderr.trim() || undefined,
            });
          }
        },
      );

      child.stdin.on(
        "error",
        (error) => {
          clearTimeout(timeout);
          finish({
            enabled: true,
            persisted: false,
            status: "FAILED",
            reason:
              "RESEARCH_MEMORY_STDIN_ERROR",
            error: error.message,
            adapterPath,
            stderr:
              stderr.trim() || undefined,
          });
        },
      );

      child.stdin.write(payload);
      child.stdin.end();
    },
  );
}

export async function runLearningAgent(
  context: AgentContext
): Promise<Record<string, unknown>> {
  const learning =
    await marketHQApi.learning();

  if (!learning.success) {
    throw new Error(
      "MarketHQ learning data could not be loaded."
    );
  }

  const data = learning.data;

  if (!isRecord(data)) {
    throw new Error(
      "MarketHQ learning response contains no valid data."
    );
  }

  const previousBrain =
    context.previousResults?.[
      "brain"
    ];

  const previousEvidence =
    context.previousResults?.[
      "evidence"
    ];

  const previousValidation =
    context.previousResults?.[
      "validation"
    ];

  const previousBacktest =
    context.previousResults?.[
      "backtest"
    ];

  const previousStrategy =
    context.previousResults?.[
      "strategy"
    ];

  const previousMarketData =
    context.previousResults?.[
      "market-data"
    ];

  const previousResultIngestion =
    context.previousResults?.[
      "result-ingestion"
    ];

  const previousExperimentRunner =
    context.previousResults?.[
      "experiment-runner"
    ];

  const brainOutput =
    previousBrain?.output ?? null;

  const evidenceOutput =
    previousEvidence?.output ?? null;

  const validationOutput =
    previousValidation?.output ?? null;

  const backtestOutput =
    previousBacktest?.output ?? null;

  const strategyOutput =
    previousStrategy?.output ?? null;

  const marketDataOutput =
    previousMarketData?.output ?? null;

  const resultIngestionOutput =
    previousResultIngestion?.output ?? null;

  const experimentRunnerOutput =
    previousExperimentRunner?.output ?? null;

  const explicitBrainInput =
    context.input?.["brain"] ?? null;

  const explicitEvidenceInput =
    context.input?.["evidence"] ?? null;

  const explicitValidationInput =
    context.input?.["validation"] ?? null;

  const explicitBacktestInput =
    context.input?.["backtest"] ?? null;

  const explicitStrategyInput =
    context.input?.["strategy"] ?? null;

  const explicitMarketDataInput =
    context.input?.["market-data"] ?? null;

  const explicitResultIngestionInput =
    context.input?.[
      "result-ingestion"
    ] ?? null;

  const brainInput =
    explicitBrainInput ??
    brainOutput;

  const evidenceInput =
    explicitEvidenceInput ??
    evidenceOutput;

  const validationInput =
    explicitValidationInput ??
    validationOutput;

  const backtestInput =
    explicitBacktestInput ??
    backtestOutput;

  const strategyInput =
    explicitStrategyInput ??
    strategyOutput;

  const marketDataInput =
    explicitMarketDataInput ??
    marketDataOutput;

  const resultIngestionInput =
    explicitResultIngestionInput ??
    resultIngestionOutput;

  /*
   * Phase 2'de Learning, Result Ingestion sonrasinda calisir.
   * Ancak orchestrator context'i bazi kosullarda onceki agent output'unu
   * eksik tasiyabilir. Research Memory persistence'in kritik kimlikleri
   * Result Ingestion'a tek basina baglanmamali.
   *
   * Experiment Runner canonical fallback kaynagidir:
   * - experimentId -> Runner experiment contract'i
   * - resultId -> varsa Result Ingestion, yoksa adapter latest result'i
   *
   * Bu fallback sadece research memory identity icindir; orijinal strateji
   * kurallarini veya execution davranisini degistirmez.
   */
  const experimentIdFallback =
    firstString(
      experimentRunnerOutput,
      [
        "experimentId",
        "experiment_id",
      ],
    ) ??
    firstString(
      findRecordRecursive(
        experimentRunnerOutput,
        [
          "experiment",
        ],
      ),
      [
        "experimentId",
        "experiment_id",
        "id",
      ],
    );

  const resultIdFallback =
    firstString(
      resultIngestionInput,
      [
        "resultId",
        "result_id",
      ],
    ) ??
    firstString(
      experimentRunnerOutput,
      [
        "resultId",
        "result_id",
      ],
    );

  const normalizedIngestion =
    normalizeResultIngestion(
      resultIngestionInput,
    );

  const ingestedResult: Record<string, unknown> = {
    ...normalizedIngestion,
    experimentId:
      normalizedIngestion.experimentId ??
      experimentIdFallback,
    resultId:
      normalizedIngestion.resultId ??
      resultIdFallback,
  };

  const strategyId =
    getString(
      context.strategyId
    ) ??
    getString(
      findValueRecursive(
        resultIngestionInput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        brainOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        evidenceOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        validationOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        data,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    null;

  const strategyName =
    getString(
      findValueRecursive(
        resultIngestionInput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        brainOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        evidenceOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        validationOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        data,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    null;

  const memoryPayload =
    buildResearchMemoryPayload(
      context,
      ingestedResult,
      data,
    );

  /*
   * Research Memory is durable experiment memory, so it must only be
   * persisted after the current experiment has a canonical identity.
   * The orchestrator executes Learning twice: Phase 1 before Experiment
   * Runner and Phase 2 after Result Ingestion. Persisting during Phase 1
   * is both premature and can cause a duplicate/invalid storage attempt.
   */
  const canPersistResearchMemory =
    Boolean(
      ingestedResult.experimentId ||
        experimentIdFallback,
    ) &&
    Boolean(
      resultIngestionInput ||
        experimentRunnerOutput,
    );

  const researchMemory =
    canPersistResearchMemory
      ? await persistResearchMemory(
          context,
          memoryPayload,
        )
      : {
          enabled:
            process.env.MARKETHQ_RESEARCH_STORAGE_ENABLED !==
            "false",
          persisted: false,
          status: "SKIPPED",
          reason:
            "Research Memory persistence deferred until POST_RUNNER when a canonical experiment identity is available.",
          experimentId:
            memoryPayload.experimentId ?? null,
          resultId:
            memoryPayload.resultId ?? null,
        };

  const researchLoop =
    extractResearchLoop(ingestedResult);

  return {
    agent: "learning",

    runId:
      context.runId,

    strategyId,

    strategyName,

    learningData: data,

    resultIngestionInput,

    ingestedResult,

    learningContext: {
      ingestionAvailable:
        ingestedResult.available,

      ingestionStatus:
        ingestedResult.status,

      experimentId:
        ingestedResult.experimentId,

      researchQuestion:
        ingestedResult.researchQuestion,

      resultType:
        ingestedResult.resultType,

      sourceCount:
        ingestedResult.sourceCount,

      availableSourceCount:
        ingestedResult.availableSourceCount,

      metricCount:
        ingestedResult.metricCount,
    },

    researchMemory,

    researchLoop,

    memoryPersistenceDiagnostics: {
      enabled: researchMemory.enabled ?? null,
      persisted: researchMemory.persisted ?? false,
      status: researchMemory.status ?? null,
      reason: researchMemory.reason ?? null,
      adapterPath: researchMemory.adapterPath ?? null,
      experimentId: memoryPayload.experimentId ?? null,
      resultId: memoryPayload.resultId ?? null,
      usedExperimentRunnerFallback:
        !normalizedIngestion.experimentId &&
        Boolean(experimentIdFallback),
    },

    memoryPayload,

    brainInput,

    evidenceInput,

    validationInput,

    backtestInput,

    strategyInput,

    marketDataInput,

    previousAgentState: {
      brainAvailable:
        Boolean(brainOutput),

      evidenceAvailable:
        Boolean(evidenceOutput),

      validationAvailable:
        Boolean(validationOutput),

      backtestAvailable:
        Boolean(backtestOutput),

      strategyAvailable:
        Boolean(strategyOutput),

      marketDataAvailable:
        Boolean(marketDataOutput),

      resultIngestionAvailable:
        Boolean(resultIngestionInput),

      brainRunId:
        previousBrain?.runId ?? null,

      evidenceRunId:
        previousEvidence?.runId ?? null,

      validationRunId:
        previousValidation?.runId ?? null,

      backtestRunId:
        previousBacktest?.runId ?? null,

      strategyRunId:
        previousStrategy?.runId ?? null,

      marketDataRunId:
        previousMarketData?.runId ?? null,

      resultIngestionRunId:
        previousResultIngestion?.runId ??
        null,

      experimentRunnerAvailable:
        Boolean(experimentRunnerOutput),

      experimentRunnerRunId:
        previousExperimentRunner?.runId ??
        null,

      brainSuccess:
        previousBrain?.success ?? false,

      evidenceSuccess:
        previousEvidence?.success ??
        false,

      validationSuccess:
        previousValidation?.success ??
        false,

      backtestSuccess:
        previousBacktest?.success ??
        false,

      strategySuccess:
        previousStrategy?.success ??
        false,

      marketDataSuccess:
        previousMarketData?.success ??
        false,

      resultIngestionSuccess:
        previousResultIngestion?.success ??
        false,

      experimentRunnerSuccess:
        previousExperimentRunner?.success ??
        false,
    },

    researchContext: {
      symbol:
        context.symbol ?? null,

      timeframe:
        context.timeframe ?? null,

      backendLearningLoaded:
        learning.success,

      learningDataAvailable:
        Boolean(data),

      resultIngestionAvailable:
        ingestedResult.available,

      experimentRunnerAvailable:
        Boolean(experimentRunnerOutput),

      experimentId:
        ingestedResult.experimentId,

      researchQuestion:
        ingestedResult.researchQuestion,
    },

    mode:
      "RESEARCH_STORAGE_MEMORY_V1",

    note:
      "Bu ajan mevcut MarketHQ öğrenme verilerini ve Result Ingestion tarafından normalize edilen deney sonuçlarını değerlendirir. Sonuçtan türetilen kompakt araştırma hafızasını Research Storage V1 içindeki research_memory tablosuna yazar; orijinal strateji kurallarını değiştirmez ve broker işlemi gerçekleştirmez.",

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerLearningAgent(): void {
  agentRunner.register(
    "learning",
    runLearningAgent
  );
}







