import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

import marketHQApi from "../../lib/markethq-api";

type UnknownRecord = Record<string, unknown>;

function isRecord(
  value: unknown,
): value is UnknownRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getString(
  value: unknown,
): string | null {
  return (
    typeof value === "string" &&
    value.trim().length > 0
  )
    ? value.trim()
    : null;
}

function getNumber(
  value: unknown,
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

    return Number.isFinite(parsed)
      ? parsed
      : null;
  }

  return null;
}

function findValueRecursive(
  value: unknown,
  keys: string[],
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
          keys,
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
          keys,
        );

      if (found !== undefined) {
        return found;
      }
    }
  }

  return undefined;
}

function getPath(
  root: unknown,
  path: string[],
): unknown {
  let current: unknown = root;

  for (const key of path) {
    if (
      !isRecord(current) ||
      !(key in current)
    ) {
      return undefined;
    }

    current = current[key];
  }

  return current;
}

function getRecordAtPath(
  root: unknown,
  path: string[],
): UnknownRecord {
  const value =
    getPath(root, path);

  return isRecord(value)
    ? value
    : {};
}

function getAgentOutput(
  context: AgentContext,
  agentId: string,
): UnknownRecord {
  const previousOutput =
    context.previousResults?.[
      agentId as keyof NonNullable<
        AgentContext["previousResults"]
      >
    ]?.output;

  if (isRecord(previousOutput)) {
    return previousOutput;
  }

  const directInput =
    context.input?.[agentId];

  if (isRecord(directInput)) {
    return directInput;
  }

  return {};
}

function normalizeRanking(
  pipelineData: UnknownRecord,
): UnknownRecord {
  const pipelineStrategy =
    isRecord(pipelineData.strategy)
      ? pipelineData.strategy
      : {};

  const ranking =
    isRecord(pipelineStrategy.ranking)
      ? pipelineStrategy.ranking
      : null;

  if (ranking) {
    return ranking;
  }

  const directRanking =
    pipelineData.ranking;

  if (isRecord(directRanking)) {
    return directRanking;
  }

  return {};
}

function buildRunnerResearchValidation(
  runnerOutput: UnknownRecord,
): UnknownRecord {
  const runnerRoot =
    runnerOutput;

  const researchExecution =
    getRecordAtPath(
      runnerRoot,
      ["researchExecution"],
    );

  const executionResult =
    getRecordAtPath(
      researchExecution,
      ["result"],
    );

  const backtest =
    getRecordAtPath(
      executionResult,
      ["backtest"],
    );

  const backtestResult =
    getRecordAtPath(
      backtest,
      ["result"],
    );

  const metrics =
    getRecordAtPath(
      backtestResult,
      ["metrics"],
    );

  const config =
    getRecordAtPath(
      backtestResult,
      ["config"],
    );

  const execution =
    getRecordAtPath(
      executionResult,
      ["execution"],
    );

  const safety =
    getRecordAtPath(
      executionResult,
      ["safety"],
    );

  const dateScope =
    getRecordAtPath(
      executionResult,
      ["dateScope"],
    );

  const researchExecutionStatus =
    getString(
      researchExecution.status,
    )?.toUpperCase() ??
    getString(
      executionResult.status,
    )?.toUpperCase() ??
    "UNKNOWN";

  const backtestStatus =
    getString(
      executionResult
        .backtestStatus,
    )?.toUpperCase() ??
    (
      Object.keys(backtestResult)
        .length > 0
        ? "AVAILABLE"
        : "UNKNOWN"
    );

  const backtestExecuted =
    execution.backtestExecuted === true;

  const researchExecutionPerformed =
    execution.researchExecutionPerformed === true;

  const brokerOrderPlaced =
    execution.brokerOrderPlaced === true;

  const databaseWritePerformed =
    execution.databaseWritePerformed === true;

  const researchOnly =
    safety.researchOnly === true;

  const executionEnabled =
    safety.executionEnabled === true;

  const databaseWriteEnabled =
    safety.databaseWriteEnabled === true;

  const brokerExecutionEnabled =
    safety.brokerExecutionEnabled === true;

  const experimentId =
    getString(
      executionResult.experimentId,
    );

  const runId =
    getString(
      executionResult.runId,
    );

  const symbol =
    getString(
      backtestResult.symbol,
    );

  const startDate =
    getString(
      backtestResult.start_date,
    ) ??
    getString(
      dateScope.startDate,
    ) ??
    getString(
      dateScope.independentSliceStartDate,
    );

  const endDate =
    getString(
      backtestResult.end_date,
    ) ??
    getString(
      dateScope.endDate,
    ) ??
    getString(
      dateScope.independentSliceEndDate,
    );

  const dateSelectionStatus =
    getString(
      dateScope.selectionStatus,
    )?.toUpperCase() ??
    "UNKNOWN";

  const bars =
    getNumber(
      backtestResult.bars,
    );

  const totalTrades =
    getNumber(
      metrics.total_trades,
    );

  const netPnl =
    getNumber(
      metrics.net_pnl,
    );

  const totalReturnPercent =
    getNumber(
      metrics.total_return_percent,
    );

  const profitFactor =
    getNumber(
      metrics.profit_factor,
    );

  const maxDrawdownPercent =
    getNumber(
      metrics.max_drawdown_percent,
    );

  const initialCapital =
    getNumber(
      config.initial_capital,
    );

  const commissionPercent =
    getNumber(
      config.commission_percent,
    );

  const slippagePercent =
    getNumber(
      config.slippage_percent,
    );

  const hasExecutionResult =
    Object.keys(
      executionResult,
    ).length > 0;

  const hasBacktestResult =
    Object.keys(
      backtestResult,
    ).length > 0;

  const hasMetrics =
    Object.keys(
      metrics,
    ).length > 0;

  const hasCostConfig =
    commissionPercent !== null &&
    slippagePercent !== null;

  const hasExactHistoricalDates =
    Boolean(startDate) &&
    Boolean(endDate) &&
    dateSelectionStatus === "RESOLVED";

  const resultTraceable =
    Boolean(experimentId) &&
    Boolean(runId) &&
    Boolean(symbol) &&
    hasExactHistoricalDates &&
    hasBacktestResult &&
    hasMetrics &&
    hasCostConfig;

  /*
   * Bu validation yalnızca araştırma yürütmesinin yapısal olarak
   * doğrulanmasını ifade eder.
   *
   * PASS:
   *   Runner gerçekten çalışmış,
   *   backtest gerçekten yürütülmüş,
   *   metrikler mevcut,
   *   maliyet modeli mevcut,
   *   tarih kapsamı çözülmüş,
   *   araştırma-only güvenlik koşulları korunmuş.
   *
   * FAIL:
   *   Araştırma yürütmesi başarısız olmuş veya
   *   güvenlik sınırları ihlal edilmiş.
   *
   * INCOMPLETE:
   *   Sonuç var fakat karar için gerekli izlenebilirlik
   *   alanlarından biri eksik.
   *
   * Bu değer strategy profitability PASS anlamına gelmez.
   */

  let status:
    | "PASS"
    | "FAIL"
    | "INCOMPLETE";

  const safetyViolation =
    !researchOnly ||
    executionEnabled ||
    databaseWriteEnabled ||
    brokerExecutionEnabled ||
    brokerOrderPlaced ||
    databaseWritePerformed;

  if (
    safetyViolation ||
    researchExecutionStatus === "FAILED"
  ) {
    status = "FAIL";
  } else if (
    researchExecutionStatus === "COMPLETED" &&
    backtestExecuted &&
    resultTraceable
  ) {
    status = "PASS";
  } else if (
    hasExecutionResult ||
    hasBacktestResult ||
    researchExecutionPerformed
  ) {
    status = "INCOMPLETE";
  } else {
    status = "INCOMPLETE";
  }

  const reasons: string[] = [];

  if (
    researchExecutionStatus !==
    "COMPLETED"
  ) {
    reasons.push(
      `Research execution status is ${researchExecutionStatus}.`,
    );
  }

  if (!backtestExecuted) {
    reasons.push(
      "Runner did not report a completed backtest execution.",
    );
  }

  if (!hasMetrics) {
    reasons.push(
      "Backtest metrics are unavailable.",
    );
  }

  if (!hasCostConfig) {
    reasons.push(
      "Explicit commission and slippage configuration is unavailable.",
    );
  }

  if (!hasExactHistoricalDates) {
    reasons.push(
      "Resolved exact historical experiment dates are unavailable.",
    );
  }

  if (!experimentId) {
    reasons.push(
      "Experiment ID is unavailable.",
    );
  }

  if (!symbol) {
    reasons.push(
      "Backtest symbol is unavailable.",
    );
  }

  if (
    safetyViolation
  ) {
    reasons.push(
      "Research-only safety constraints were not satisfied.",
    );
  }

  if (
    status === "PASS"
  ) {
    reasons.push(
      "Runner research execution, backtest result, cost model, historical date scope and traceability checks passed.",
    );
  }

  return {
    status,

    reason:
      reasons.length > 0
        ? reasons.join(" ")
        : "Runner research validation completed.",

    researchExecutionStatus,

    backtestStatus,

    researchExecutionPerformed,

    backtestExecuted,

    resultTraceable,

    experimentId,

    runId,

    symbol,

    startDate,

    endDate,

    dateSelectionStatus,

    bars,

    metricsAvailable:
      hasMetrics,

    costConfigAvailable:
      hasCostConfig,

    exactHistoricalDatesAvailable:
      hasExactHistoricalDates,

    safetyCompliant:
      !safetyViolation,

    researchOnly,

    executionEnabled,

    databaseWriteEnabled,

    brokerExecutionEnabled,

    brokerOrderPlaced,

    databaseWritePerformed,

    metrics: {
      totalTrades,
      netPnl,
      totalReturnPercent,
      profitFactor,
      maxDrawdownPercent,
    },

    costModel: {
      initialCapital,
      commissionPercent,
      slippagePercent,
      positionSizePercent:
        getNumber(
          config.position_size_percent,
        ),
      stopAtrMultiplier:
        getNumber(
          config.stop_atr_multiplier,
        ),
      targetAtrMultiplier:
        getNumber(
          config.target_atr_multiplier,
        ),
    },

    source: "experiment-runner.researchExecution.result",

    mode:
      "READ_ONLY_RUNNER_RESEARCH_VALIDATION",
  };
}

export async function runValidationAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  /*
   * ============================================================
   * 1. EXISTING MARKET HQ PIPELINE VALIDATION
   * ============================================================
   *
   * Eski validation metriklerini koruyoruz.
   * Research Decision hâlâ bunları kullanıyor:
   *
   * cost_survival
   * parameter_stability
   * regime_stability
   * wfo_positive_ratio
   * cross_symbol_positive_ratio
   * classification
   * score
   */

  const pipeline =
    await marketHQApi.pipeline();

  if (!pipeline.success) {
    throw new Error(
      "MarketHQ pipeline data could not be loaded for validation.",
    );
  }

  const data =
    pipeline.data;

  if (!isRecord(data)) {
    throw new Error(
      "MarketHQ pipeline response contains no valid validation data.",
    );
  }

  const pipelineData =
    data;

  const pipelineStrategy =
    isRecord(
      pipelineData.strategy,
    )
      ? pipelineData.strategy
      : null;

  /*
   * Eski sistem ranking olmadan da Runner validation
   * çalışabilsin diye ranking'i artık hard-fail sebebi
   * yapmıyoruz.
   */
  const ranking =
    normalizeRanking(
      pipelineData,
    );

  /*
   * ============================================================
   * 2. PREVIOUS AGENT RESULTS
   * ============================================================
   */

  const previousBacktest =
    context.previousResults?.[
      "backtest"
    ];

  const previousStrategy =
    context.previousResults?.[
      "strategy"
    ];

  const backtestOutput =
    previousBacktest?.output ??
    null;

  const strategyOutput =
    previousStrategy?.output ??
    null;

  const explicitStrategyInput =
    context.input?.[
      "strategy"
    ] ?? null;

  const explicitBacktestInput =
    context.input?.[
      "backtest"
    ] ?? null;

  const strategyInput =
    explicitStrategyInput ??
    strategyOutput;

  const backtestInput =
    explicitBacktestInput ??
    backtestOutput;

  /*
   * ============================================================
   * 3. EXPERIMENT RUNNER RESULT
   * ============================================================
   *
   * Runner'ın gerçek çıktısı:
   *
   * experimentRunner
   *   researchExecution
   *     result
   *       backtest
   *         result
   *           metrics
   *           config
   *       execution
   *       safety
   *       dateScope
   */

  const runnerOutput =
    getAgentOutput(
      context,
      "experiment-runner",
    );

  const runnerResearchValidation =
    buildRunnerResearchValidation(
      runnerOutput,
    );

  const runnerRobustnessSummary =
    isRecord(
      runnerOutput.robustnessSummary,
    )
      ? runnerOutput.robustnessSummary
      : {};

  const robustnessValidation = {
    available:
      Object.keys(
        runnerRobustnessSummary,
      ).length > 0,

    oosStable:
      runnerRobustnessSummary.stable ?? null,

    oosRetentionRatio:
      runnerRobustnessSummary.retentionRatio ??
      null,

    monteCarloStatus:
      runnerRobustnessSummary.monteCarloStatus ??
      null,

    monteCarloPositiveProbability:
      runnerRobustnessSummary.monteCarloPositiveProbability ??
      null,

    stressPositiveScenarioRatio:
      runnerRobustnessSummary.stressPositiveScenarioRatio ??
      null,

    stressWorstMetric:
      runnerRobustnessSummary.stressWorstMetric ??
      null,

    robustnessScore:
      runnerRobustnessSummary.robustnessScore ??
      null,
  };

  /*
   * ============================================================
   * 4. STRATEGY ID
   * ============================================================
   */

  const strategyId =
    getString(
      context.strategyId,
    ) ??
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyId",
          "strategy_id",
        ],
      ),
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyId",
          "strategy_id",
        ],
      ),
    ) ??
    getString(
      findValueRecursive(
        pipelineData,
        [
          "strategy_id",
          "strategyId",
        ],
      ),
    ) ??
    getString(
      findValueRecursive(
        pipelineStrategy,
        [
          "strategy_id",
          "strategyId",
        ],
      ),
    ) ??
    null;

  /*
   * ============================================================
   * 5. STRATEGY NAME
   * ============================================================
   */

  const strategyName =
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyName",
          "strategy_name",
        ],
      ),
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyName",
          "strategy_name",
        ],
      ),
    ) ??
    getString(
      findValueRecursive(
        pipelineStrategy,
        [
          "strategy_name",
          "strategyName",
        ],
      ),
    ) ??
    null;

  /*
   * ============================================================
   * 6. EXISTING VALIDATION METRICS
   * ============================================================
   */

  const validation = {
    costSurvival:
      ranking.cost_survival ??
      ranking.costSurvival ??
      null,

    parameterStability:
      ranking.parameter_stability ??
      ranking.parameterStability ??
      null,

    regimeStability:
      ranking.regime_stability ??
      ranking.regimeStability ??
      null,

    walkForwardPositiveRatio:
      ranking.wfo_positive_ratio ??
      ranking.walkForwardPositiveRatio ??
      null,

    crossSymbolPositiveRatio:
      ranking.cross_symbol_positive_ratio ??
      ranking.crossSymbolPositiveRatio ??
      null,

    classification:
      ranking.classification ??
      null,

    score:
      ranking.score ??
      null,
  };

  /*
   * ============================================================
   * 7. RUNNER VALIDATION ALIASES
   * ============================================================
   *
   * Research Decision v5 zaten:
   *
   * runnerEvidence.researchValidationStatus
   *
   * okuyor.
   *
   * Bu yüzden hem nested researchValidation,
   * hem de doğrudan alias veriyoruz.
   */

  const runnerValidationStatus =
    getString(
      runnerResearchValidation.status,
    )?.toUpperCase() ??
    "UNKNOWN";

  /*
   * ============================================================
   * 8. FINAL OUTPUT
   * ============================================================
   */

  return {
    agent:
      "validation",

    runId:
      context.runId,

    strategyId,

    strategyName,

    /*
     * Eski validation contract korunuyor.
     */
    validation,

    /*
     * Eski ranking korunuyor.
     */
    ranking,

    /*
     * Yeni gerçek Runner validation.
     */
    researchValidation:
      runnerResearchValidation,

    robustnessValidation,

    /*
     * Research Decision'ın doğrudan okuyabileceği alias.
     */
    researchValidationStatus:
      runnerValidationStatus,

    /*
     * Runner sonucu trace edilebilir şekilde
     * ayrıca kaynak olarak tutuluyor.
     */
    runnerValidation:
      runnerResearchValidation,

    pipelineData,

    strategyInput,

    backtestInput,

    /*
     * Agent state.
     */
    previousAgentState: {
      strategyAvailable:
        Boolean(strategyOutput),

      backtestAvailable:
        Boolean(backtestOutput),

      experimentRunnerAvailable:
        Object.keys(
          runnerOutput,
        ).length > 0,

      strategyRunId:
        previousStrategy?.runId ??
        null,

      backtestRunId:
        previousBacktest?.runId ??
        null,

      strategySuccess:
        previousStrategy?.success ??
        false,

      backtestSuccess:
        previousBacktest?.success ??
        false,

      experimentRunnerSuccess:
        context.previousResults?.[
          "experiment-runner"
        ]?.success ??
        false,
    },

    /*
     * Research context.
     */
    researchContext: {
      symbol:
        context.symbol ??
        null,

      timeframe:
        context.timeframe ??
        null,

      backendPipelineLoaded:
        pipeline.success,

      rankingAvailable:
        Object.keys(
          ranking,
        ).length > 0,

      runnerValidationAvailable:
        Object.keys(
          runnerResearchValidation,
        ).length > 0,

      runnerValidationStatus,

      runnerResultTraceable:
        runnerResearchValidation
          .resultTraceable === true,

      runnerBacktestAvailable:
        runnerResearchValidation
          .metricsAvailable === true,

      runnerCostConfigAvailable:
        runnerResearchValidation
          .costConfigAvailable === true,

      runnerDateScopeAvailable:
        runnerResearchValidation
          .exactHistoricalDatesAvailable === true,
    },

    /*
     * Açıklayıcı not.
     */
    note:
      "Bu ajan mevcut MarketHQ araştırma ranking metriklerini korur ve Experiment Runner'ın gerçek researchExecution sonucunu ayrıca yapısal olarak doğrular. Runner validation PASS yalnızca araştırma yürütmesinin, backtest sonucunun, maliyet modelinin, tarih kapsamının ve izlenebilirliğin doğrulandığını ifade eder; stratejinin kârlı olduğu anlamına gelmez. Veritabanına yazmaz ve broker işlemi gerçekleştirmez.",

    mode:
      "READ_ONLY_VALIDATION_V2",

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerValidationAgent(): void {
  agentRunner.register(
    "validation",
    runValidationAgent,
  );
}

