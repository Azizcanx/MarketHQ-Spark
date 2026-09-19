import type { AgentContext } from "./agent-types";
import { agentRunner } from "./agent-runner";
import { spawn } from "node:child_process";
import path from "node:path";

type UnknownRecord = Record<string, unknown>;

type CheckStatus = "PASS" | "WARN" | "FAIL";

interface ExecutionCheck {
  name: string;
  status: CheckStatus;
  detail: string;
}

const RESEARCH_EXECUTION_TIMEOUT_MS = 120_000;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toStringValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }

  return fallback;
}

function toBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();

    if (normalized === "true") return true;
    if (normalized === "false") return false;
  }

  return fallback;
}

function firstRecord(...values: unknown[]): UnknownRecord {
  for (const value of values) {
    if (isRecord(value)) return value;
  }

  return {};
}

function getAgentOutput(
  context: AgentContext,
  agentId: keyof NonNullable<AgentContext["previousResults"]>,
): UnknownRecord {
  const output = context.previousResults?.[agentId]?.output;

  return isRecord(output) ? output : {};
}

function getExperiment(context: AgentContext): UnknownRecord {
  return firstRecord(
    getAgentOutput(context, "experiment-generator").experiment,
  );
}

function buildCheck(
  name: string,
  condition: boolean,
  passDetail: string,
  failDetail: string,
): ExecutionCheck {
  return {
    name,
    status: condition ? "PASS" : "FAIL",
    detail: condition ? passDetail : failDetail,
  };
}

function buildWarningCheck(
  name: string,
  condition: boolean,
  detail: string,
): ExecutionCheck {
  return {
    name,
    status: condition ? "PASS" : "WARN",
    detail,
  };
}

function extractStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value.map((item) => toStringValue(item)).filter(Boolean);
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

/**
 * Deterministic anti-overfitting review derived from the existing
 * multi-fold chronological WFO train/OOS results.
 *
 * This is deliberately NOT an optimizer and does not modify strategy rules.
 * It only measures train-vs-OOS deterioration / consistency.
 */
function buildOverfittingReview(
  walkForwardOOS: unknown,
): UnknownRecord {
  if (!isRecord(walkForwardOOS)) {
    return {
      status: "UNKNOWN",
      riskScore: null,
      method: "WFO_TRAIN_OOS_GAP_V1",
      reason: "Walk-forward OOS output was not available.",
      foldCount: 0,
      resolvedFoldCount: 0,
    };
  }

  const rawFolds = Array.isArray(walkForwardOOS.folds)
    ? walkForwardOOS.folds.filter(isRecord)
    : [];

  const completedFolds = rawFolds.filter(
    (fold) =>
      toStringValue(fold.status).toUpperCase() ===
      "COMPLETED",
  );

  if (completedFolds.length === 0) {
    return {
      status: "UNKNOWN",
      riskScore: null,
      method: "WFO_TRAIN_OOS_GAP_V1",
      reason: "No completed WFO folds were available.",
      foldCount: rawFolds.length,
      resolvedFoldCount: 0,
    };
  }

  const toFiniteNumber = (
    value: unknown,
  ): number | null => {
    const numeric =
      typeof value === "number"
        ? value
        : Number(value);

    return Number.isFinite(numeric)
      ? numeric
      : null;
  };

  const oosMetrics = completedFolds
    .map((fold) =>
      toFiniteNumber(fold.oosMetric),
    )
    .filter(
      (value): value is number =>
        value !== null,
    );

  const trainMetrics = completedFolds
    .map((fold) =>
      toFiniteNumber(fold.trainMetric),
    )
    .filter(
      (value): value is number =>
        value !== null,
    );

  const retentionRatios = completedFolds
    .map((fold) =>
      toFiniteNumber(
        fold.oosRetentionRatio,
      ),
    )
    .filter(
      (value): value is number =>
        value !== null &&
        Number.isFinite(value),
    );

  const positiveOOS = oosMetrics.filter(
    (value) => value > 0,
  ).length;

  const negativeOOS = oosMetrics.filter(
    (value) => value < 0,
  ).length;

  const positiveTrain = trainMetrics.filter(
    (value) => value > 0,
  ).length;

  const resolvedFoldCount = oosMetrics.length;

  const oosPositiveRatio =
    resolvedFoldCount > 0
      ? positiveOOS / resolvedFoldCount
      : null;

  const oosNegativeRatio =
    resolvedFoldCount > 0
      ? negativeOOS / resolvedFoldCount
      : null;

  const trainPositiveRatio =
    trainMetrics.length > 0
      ? positiveTrain / trainMetrics.length
      : null;

  const retentionMean =
    retentionRatios.length > 0
      ? retentionRatios.reduce(
          (sum, value) => sum + value,
          0,
        ) / retentionRatios.length
      : null;

  const sortedRetention = [
    ...retentionRatios,
  ].sort((a, b) => a - b);

  const retentionMedian =
    sortedRetention.length === 0
      ? null
      : sortedRetention.length % 2 === 1
        ? sortedRetention[
            Math.floor(
              sortedRetention.length / 2,
            )
          ]
        : (
            sortedRetention[
              sortedRetention.length / 2 - 1
            ] +
            sortedRetention[
              sortedRetention.length / 2
            ]
          ) / 2;

  const inconclusiveFolds =
    completedFolds.length -
    resolvedFoldCount;

  const inconclusiveShare =
    completedFolds.length > 0
      ? inconclusiveFolds /
        completedFolds.length
      : 1;

  /*
   * Risk components:
   *   - negative OOS frequency
   *   - train/OOS retention deterioration
   *   - inconclusive share
   *
   * Retention is treated conservatively:
   *   1.0 = OOS retained 100% of train metric
   *   0.0 = no retained edge
   *   <0  = OOS reversed sign
   */
  const retentionRisk =
    retentionMedian === null
      ? 1
      : Math.max(
          0,
          Math.min(
            1,
            1 -
              Math.max(
                -1,
                Math.min(
                  1,
                  retentionMedian,
                ),
              ),
          ),
        );

  const negativeRisk =
    oosNegativeRatio === null
      ? 1
      : oosNegativeRatio;

  const inconclusiveRisk =
    inconclusiveShare;

  const rawRiskScore =
    0.45 * negativeRisk +
    0.45 * retentionRisk +
    0.10 * inconclusiveRisk;

  const riskScore = Math.max(
    0,
    Math.min(1, rawRiskScore),
  );

  let status:
    | "LOW"
    | "MEDIUM"
    | "HIGH";

  if (
    (oosNegativeRatio !== null &&
      oosNegativeRatio >= 0.60) ||
    (retentionMedian !== null &&
      retentionMedian <= 0)
  ) {
    status = "HIGH";
  } else if (
    riskScore >= 0.50 ||
    (oosNegativeRatio !== null &&
      oosNegativeRatio >= 0.40) ||
    (retentionMedian !== null &&
      retentionMedian < 0.50)
  ) {
    status = "MEDIUM";
  } else {
    status = "LOW";
  }

  return {
    status,
    riskScore: Number(
      riskScore.toFixed(4),
    ),
    method: "WFO_TRAIN_OOS_GAP_V1",
    foldCount: rawFolds.length,
    resolvedFoldCount,
    trainPositiveRatio:
      trainPositiveRatio === null
        ? null
        : Number(
            trainPositiveRatio.toFixed(4),
          ),
    oosPositiveRatio:
      oosPositiveRatio === null
        ? null
        : Number(
            oosPositiveRatio.toFixed(4),
          ),
    oosNegativeRatio:
      oosNegativeRatio === null
        ? null
        : Number(
            oosNegativeRatio.toFixed(4),
          ),
    retentionMean:
      retentionMean === null
        ? null
        : Number(
            retentionMean.toFixed(4),
          ),
    retentionMedian:
      retentionMedian === null
        ? null
        : Number(
            retentionMedian.toFixed(4),
          ),
    inconclusiveShare:
      Number(
        inconclusiveShare.toFixed(4),
      ),
    interpretation:
      status === "HIGH"
        ? "WFO train-to-OOS deterioration indicates elevated overfitting risk."
        : status === "MEDIUM"
          ? "WFO shows partial train-to-OOS deterioration; further robustness review is warranted."
          : "WFO shows limited train-to-OOS deterioration in the available folds.",
  };
}

/**
 * Runs the real MarketHQ research-only Python execution adapter.
 *
 * Project layout:
 *
 * MarketHQ/
 * â”œâ”€â”€ agents/
 * â”‚   â””â”€â”€ research_execution_adapter_v1.py
 * â””â”€â”€ frontend/
 *     â””â”€â”€ components/
 *         â””â”€â”€ agents/
 *             â””â”€â”€ experiment-runner-agent.ts
 *
 * The Runner is executed from the frontend project, so process.cwd()
 * points to:
 *
 *   MarketHQ/frontend
 *
 * The adapter itself lives one directory above that:
 *
 *   MarketHQ/agents/research_execution_adapter_v1.py
 *
 * Safety:
 * - historical research/backtest only
 * - no broker execution
 * - no database writes
 * - no live order placement
 * - experiment JSON is passed through stdin
 */
async function runResearchExecutionAdapter(
  context: AgentContext,
  experiment: UnknownRecord,
): Promise<UnknownRecord> {
  const frontendRoot = process.cwd();

  /*
   * The Next.js/tsx command is executed from MarketHQ/frontend.
   * Move one directory up to the actual MarketHQ project root.
   */
  const projectRoot = path.resolve(frontendRoot, "..");

  const adapterPath = path.join(
    projectRoot,
    "agents",
    "research_execution_adapter_v1.py",
  );

  const pythonExecutable =
    process.env.MARKETHQ_PYTHON || "python";

  const payload = JSON.stringify({
    runId: context.runId,
    experiment,
  });

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
        status: "FAILED",
        reason: "RESEARCH_EXECUTION_TIMEOUT",
        error:
          `Research execution adapter exceeded ${RESEARCH_EXECUTION_TIMEOUT_MS} ms.`,
        adapterPath,
        projectRoot,
        stderr: stderr.trim() || undefined,
      });
    }, RESEARCH_EXECUTION_TIMEOUT_MS);

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

    child.on("error", (error) => {
      clearTimeout(timeout);

      finish({
        status: "FAILED",
        reason: "RESEARCH_EXECUTION_PROCESS_ERROR",
        error: error.message,
        adapterPath,
        projectRoot,
        stderr: stderr.trim() || undefined,
      });
    });

    child.on("close", (exitCode) => {
      clearTimeout(timeout);

      const rawOutput = stdout.trim();

      if (!rawOutput) {
        finish({
          status: "FAILED",
          reason: "RESEARCH_EXECUTION_EMPTY_OUTPUT",
          exitCode,
          adapterPath,
          projectRoot,
          stderr: stderr.trim() || undefined,
        });

        return;
      }

      try {
        const parsed: unknown = JSON.parse(rawOutput);

        if (!isRecord(parsed)) {
          finish({
            status: "FAILED",
            reason: "RESEARCH_EXECUTION_INVALID_OUTPUT",
            exitCode,
            adapterPath,
            projectRoot,
            stderr: stderr.trim() || undefined,
          });

          return;
        }

        finish({
          ...parsed,
          exitCode,
          adapterPath,
          projectRoot,
          stderr: stderr.trim() || undefined,
        });
      } catch (error) {
        finish({
          status: "FAILED",
          reason: "RESEARCH_EXECUTION_INVALID_JSON",
          error:
            error instanceof Error
              ? error.message
              : String(error),
          exitCode,
          adapterPath,
          projectRoot,
          rawOutput,
          stderr: stderr.trim() || undefined,
        });
      }
    });

    child.stdin.on("error", (error) => {
      clearTimeout(timeout);

      finish({
        status: "FAILED",
        reason: "RESEARCH_EXECUTION_STDIN_ERROR",
        error: error.message,
        adapterPath,
        projectRoot,
        stderr: stderr.trim() || undefined,
      });
    });

    /*
     * Send the complete experiment definition to the Python adapter.
     */
    child.stdin.write(payload);
    child.stdin.end();
  });
}

export async function runExperimentRunnerAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  const experiment = getExperiment(context);

  const backtest = getAgentOutput(
    context,
    "backtest",
  );

  const validation = getAgentOutput(
    context,
    "validation",
  );

  const evidence = getAgentOutput(
    context,
    "evidence",
  );

  const experimentId = toStringValue(
    experiment.experimentId,
  );

  const researchQuestion = toStringValue(
    experiment.researchQuestion,
  );

  const hypothesis = toStringValue(
    experiment.hypothesis,
  );

  const strategy = firstRecord(
    experiment.strategy,
  );

  const market = firstRecord(
    experiment.market,
  );

  const dataRequirements = firstRecord(
    experiment.dataRequirements,
  );

  const evaluation = firstRecord(
    experiment.evaluation,
  );

  const constraints = firstRecord(
    experiment.constraints,
  );

  const strategyId = toStringValue(
    strategy.strategyId,
    context.strategyId ?? "UNKNOWN_STRATEGY",
  );

  const symbol = toStringValue(
    market.symbol,
    context.symbol ?? "UNKNOWN",
  );

  const timeframe = toStringValue(
    market.timeframe,
    context.timeframe ?? "1d",
  );

  if (!experimentId || !researchQuestion) {
    return {
      agent: "experiment-runner",

      status: "BLOCKED",

      reason:
        "Experiment Generator did not provide a valid experiment ID and research question.",

      executionPlan: null,

      readiness: {
        ready: false,
        hardFailureCount: 1,
        researchGateFailureCount: 0,
        executionReady: false,
      },

      researchExecution: {
        status: "BLOCKED",
        completed: false,
        blocked: true,
        succeeded: false,

        result: {
          status: "BLOCKED",
          reason: "EXPERIMENT_DEFINITION_INVALID",
        },
      },

      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },

      mode: "RESEARCH_EXPERIMENT_RUNNER_V2",
    };
  }

  const checks: ExecutionCheck[] = [];

  /*
   * HARD:
   * Only structural prerequisites that prevent the research
   * plan from being resolved.
   */
  checks.push(
    buildCheck(
      "experiment_identity",
      Boolean(experimentId),
      "Experiment ID is present and uniquely identifies the research task.",
      "Experiment ID is missing.",
    ),
  );

  checks.push(
    buildCheck(
      "research_question",
      Boolean(researchQuestion),
      "Research question is explicit and testable.",
      "Research question is missing.",
    ),
  );

  checks.push(
    buildCheck(
      "strategy_identity",
      Boolean(
        strategyId &&
        strategyId !== "UNKNOWN_STRATEGY",
      ),
      "Strategy identity is available.",
      "Strategy identity could not be resolved.",
    ),
  );

  checks.push(
    buildCheck(
      "market_scope",
      Boolean(
        symbol &&
        symbol !== "UNKNOWN" &&
        timeframe
      ),
      `Market scope resolved as ${symbol} / ${timeframe}.`,
      "Symbol or timeframe is missing.",
    ),
  );

  /*
   * WARN:
   * Research requirements.
   */
  checks.push(
    buildWarningCheck(
      "historical_data",
      toBoolean(
        dataRequirements.historicalDataRequired,
        true,
      ),
      "Historical data is explicitly required by the experiment.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "exact_dates",
      toBoolean(
        dataRequirements.exactDatesRequired,
        false,
      ),
      "Exact historical dates are required for traceability.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "independent_slice",
      toBoolean(
        dataRequirements.independentSliceRequired,
        false,
      ),
      "The experiment requests an independent historical slice.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "cost_model",
      toBoolean(
        evaluation.costModelRequired,
        true,
      ),
      "Cost assumptions are explicitly required.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "slippage",
      toBoolean(
        evaluation.slippageRequired,
        true,
      ),
      "Slippage assumptions are explicitly required.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "holdout",
      toBoolean(
        evaluation.trainTestHoldoutRequired,
        true,
      ),
      "Train/test/holdout evaluation is required.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "robustness",
      toBoolean(
        evaluation.robustnessChecksRequired,
        true,
      ),
      "Robustness checks are required.",
    ),
  );

  checks.push(
    buildWarningCheck(
      "evidence_trace",
      toBoolean(
        evaluation.evidenceTraceRequired,
        true,
      ),
      "Evidence traceability is required.",
    ),
  );

  /*
   * Existing research outputs are informational.
   * They do not block the independent execution.
   */
  const backtestAvailable =
    Object.keys(backtest).length > 0;

  const validationAvailable =
    Object.keys(validation).length > 0;

  const evidenceAvailable =
    Object.keys(evidence).length > 0;

  const researchGateChecks: ExecutionCheck[] = [
    {
      name: "backtest_input",

      status: backtestAvailable
        ? "PASS"
        : "WARN",

      detail: backtestAvailable
        ? "Existing Backtest output is available as an input reference."
        : "No Backtest output is currently available; an independent run may be required upstream.",
    },

    {
      name: "validation_input",

      status: validationAvailable
        ? "PASS"
        : "WARN",

      detail: validationAvailable
        ? "Existing Validation output is available as an input reference."
        : "No Validation output is currently available; independent validation remains open.",
    },

    {
      name: "evidence_input",

      status: evidenceAvailable
        ? "PASS"
        : "WARN",

      detail: evidenceAvailable
        ? "Existing Evidence output is available as an input reference."
        : "No Evidence output is currently available; evidence capture remains open.",
    },
  ];

  const hardFailures = checks.filter(
    (check) => check.status === "FAIL",
  );

  const warnings = [
    ...checks,
    ...researchGateChecks,
  ].filter(
    (check) => check.status === "WARN",
  );

  const researchGateFailures = uniqueStrings([
    !backtestAvailable
      ? "backtest_input"
      : "",

    !validationAvailable
      ? "validation_input"
      : "",

    !evidenceAvailable
      ? "evidence_input"
      : "",
  ]);

  const executionSteps = [
    {
      step: 1,

      name: "freeze_experiment_definition",

      purpose:
        "Experiment soru, strategy, symbol, timeframe ve parametre kapsamÄ±nÄ± deÄŸiÅŸtirmeden sabitle.",

      status: "REQUIRED",
    },

    {
      step: 2,

      name: "resolve_historical_data",

      purpose:
        "Belirlenen tarih/symbol/timeframe kapsamÄ±ndaki historical data provenance bilgisini doÄŸrula.",

      status: "REQUIRED",
    },

    {
      step: 3,

      name: "apply_original_rule_definition",

      purpose:
        "Strategy'nin mevcut kural tanÄ±mÄ±nÄ± aynen kullan; araÅŸtÄ±rma amacÄ± dÄ±ÅŸÄ±nda yeni kural ekleme.",

      status: "REQUIRED",
    },

    {
      step: 4,

      name: "apply_cost_and_slippage",

      purpose:
        "Experiment'te tanÄ±mlanan cost ve slippage varsayÄ±mlarÄ±nÄ± uygula.",

      status: "REQUIRED",
    },

    {
      step: 5,

      name: "run_independent_validation",

      purpose:
        "Holdout, robustness ve baÄŸÄ±msÄ±z slice kontrollerini gerÃ§ek bir research execution katmanÄ±nda Ã§alÄ±ÅŸtÄ±r.",

      status: "NEXT_EXECUTION_STAGE",
    },

    {
      step: 6,

      name: "capture_evidence_trace",

      purpose:
        "SonuÃ§larÄ± experiment ID ve kaynak Ã§Ä±ktÄ±larla iliÅŸkilendir.",

      status: "REQUIRED",
    },

    {
      step: 7,

      name: "send_to_result_ingestion",

      purpose:
        "Deney sonuÃ§larÄ±nÄ± bir sonraki Result Ingestion katmanÄ±na teslim et.",

      status: "NEXT_PIPELINE_STAGE",
    },
  ];

  const sourceResults = {
    backtest: {
      available: backtestAvailable,

      runId:
        toStringValue(backtest.runId) ||
        null,
    },

    validation: {
      available: validationAvailable,

      runId:
        toStringValue(validation.runId) ||
        null,
    },

    evidence: {
      available: evidenceAvailable,

      runId:
        toStringValue(evidence.runId) ||
        null,
    },
  };

  const successCriteria = extractStringArray(
    experiment.successCriteria,
  );

  const failureCriteria = extractStringArray(
    experiment.failureCriteria,
  );

  const manifest = firstRecord(
    experiment.manifest,
  );

  const planReady =
    hardFailures.length === 0;

  /*
   * REAL RESEARCH EXECUTION
   *
   * The adapter is only called after the Runner has validated
   * the structural experiment contract.
   */
  const executionResult = planReady
    ? await runResearchExecutionAdapter(
        context,
        experiment,
      )
    : {
        status: "BLOCKED",
        reason:
          "RESEARCH_EXECUTION_PLAN_NOT_READY",
      };

  const executionStatus = toStringValue(
    executionResult.status,
    "FAILED",
  ).toUpperCase();

  const overfittingReview =
    buildOverfittingReview(
      executionResult.walkForwardOOS,
    );

  const researchValidation = {
    status: executionStatus,
    wfo:
      isRecord(
        executionResult.walkForwardOOS,
      )
        ? {
            ...executionResult.walkForwardOOS,
          }
        : null,
    overfittingReview,
    independentResearchOnly: true,
  };

  const executionCompleted =
    executionStatus === "COMPLETED";

  const executionBlocked =
    executionStatus === "BLOCKED";

  const executionSucceeded =
    executionCompleted;

  /*
   * Agent status is the pipeline-level execution status.
   * Keep experiment/plan status separate: a READY plan that successfully
   * executes must still return COMPLETED so the orchestrator can advance to
   * Result Ingestion. A failed/blocked execution must stop the dependent stage.
   */
  const agentStatus = executionCompleted
    ? "COMPLETED"
    : executionBlocked
      ? "BLOCKED"
      : "FAILED";

  const executionPlan = {
    experimentId,

    status: planReady
      ? "READY"
      : "BLOCKED",

    planStatus: planReady
      ? "READY_FOR_RESEARCH_EXECUTION"
      : "BLOCKED",

    researchQuestion,

    hypothesis,

    manifest,

    strategy: {
      strategyId,

      name: toStringValue(
        strategy.name,
      ),

      ruleDefinition: toStringValue(
        strategy.ruleDefinition,
      ),

      parameters:
        isRecord(strategy.parameters)
          ? strategy.parameters
          : {},
    },

    market: {
      symbol,
      timeframe,
    },

    requiredEvaluation: {
      dataRequirements,
      evaluation,
    },

    executionSteps,

    checks,

    researchGateChecks,

    researchGateFailures,

    sourceResults,

    successCriteria,

    failureCriteria,

    orchestration: {
      currentAgent:
        "experiment-runner",

      nextStage:
        executionCompleted
          ? "result-ingestion"
          : "research-execution",

      resultIngestionStage:
        "result-ingestion",

      /*
       * The Runner now actually invokes the independent
       * research/backtest adapter.
       */
      backtestReexecution: true,

      note:
        "Runner deney kontratÄ±nÄ± ve research readiness'i doÄŸrular; gerÃ§ek baÄŸÄ±msÄ±z tarihsel araÅŸtÄ±rmayÄ± research-only execution adapter Ã¼zerinden Ã§alÄ±ÅŸtÄ±rÄ±r.",
    },

    researchExecution: {
      status: executionStatus,

      completed:
        executionCompleted,

      blocked:
        executionBlocked,

      succeeded:
        executionSucceeded,

      result:
        executionResult,
    },

    constraints: {
      /*
       * Hard safety boundary.
       */
      researchOnly: true,

      executionEnabled: false,

      databaseWriteEnabled: false,

      brokerExecutionEnabled: false,

      originalResearchConstraints: {
        researchOnly: toBoolean(
          constraints.researchOnly,
          true,
        ),

        executionEnabled: toBoolean(
          constraints.executionEnabled,
          false,
        ),

        databaseWriteEnabled: toBoolean(
          constraints.databaseWriteEnabled,
          false,
        ),

        brokerExecutionEnabled: toBoolean(
          constraints.brokerExecutionEnabled,
          false,
        ),
      },
    },

    generatedAt:
      new Date().toISOString(),
  };

  return {
    agent: "experiment-runner",

    runId: context.runId,

    strategyId,

    symbol,

    timeframe,

    /*
     * Pipeline status reflects the actual execution outcome.
     * The experiment.planStatus above remains the plan/readiness state.
     */
    success:
      executionSucceeded,

    status:
      agentStatus,

    experiment:
      executionPlan,

    readiness: {
      ready:
        planReady,

      hardFailureCount:
        hardFailures.length,

      warningCount:
        warnings.length,

      researchGateFailureCount:
        researchGateFailures.length,

      /*
       * TRUE only when the actual independent
       * research execution completed successfully.
       */
      executionReady:
        planReady &&
        executionSucceeded,
    },

    researchGates: {
      status:
        researchGateFailures.length === 0
          ? "CLEAR"
          : "OPEN",

      failures:
        researchGateFailures,

      note:
        "Research gate failures describe evidence availability; they do not convert a structurally valid experiment plan into BLOCKED.",
    },

    sourceResults,

    researchExecution: {
      status:
        executionStatus,

      completed:
        executionCompleted,

      blocked:
        executionBlocked,

      succeeded:
        executionSucceeded,

      result:
        executionResult,
    },

    robustnessSummary:
      isRecord(executionResult.robustnessSummary)
        ? {
            ...executionResult.robustnessSummary,
          }
        : null,

    robustness:
      isRecord(executionResult.robustness)
        ? {
            ...executionResult.robustness,
          }
        : null,

    walkForwardOOS:
      isRecord(executionResult.walkForwardOOS)
        ? {
            ...executionResult.walkForwardOOS,
          }
        : null,

    researchValidation,

    overfittingReview,

    safety: {
      researchOnly: true,

      executionEnabled: false,

      databaseWriteEnabled: false,

      brokerExecutionEnabled: false,
    },

    storageContract: {
      stage: "RESULT_INGESTION",
      persistenceMode:
        process.env.MARKETHQ_RESEARCH_STORAGE_ENABLED === "false"
          ? "DISABLED"
          : "RESEARCH_STORAGE_V1",
      writesInRunner: false,
      datasetReferenceRequired: true,
      experimentRecordRequired: true,
      resultRecordRequired: true,
      artifactReferenceRequired: true,
      researchMemoryStage: "LEARNING",
      note:
        "Runner research execution yapar; kalÄ±cÄ± Research Storage yazÄ±mÄ± Result Ingestion katmanÄ±nda yapÄ±lÄ±r.",
    },

    mode:
      "RESEARCH_EXPERIMENT_RUNNER_V3",

    completedAt:
      new Date().toISOString(),
  };
}

export function registerExperimentRunnerAgent(): void {
  agentRunner.register(
    "experiment-runner",
    runExperimentRunnerAgent,
  );
}




