import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

type UnknownRecord =
  Record<string, unknown>;

type ExperimentStatus =
  | "GENERATED"
  | "BLOCKED";

interface ResearchExperimentSpec {
  specVersion: string;
  plannerVersion: string | null;
  strategyId: string;
  hypothesis: string;
  objective: string;
  researchQuestion: string;
  targetDimension: string | null;
  selectedMetric: string | null;
  selectedScore: number | null;
  baselineParameters: UnknownRecord;
  fixedParameters: UnknownRecord;

    parameterSweep?: UnknownRecord;
    parameterSearchMethod?: string | null;
    parameterSearchCount?: number | null;

    optimizer?: {
      source: string | null;
      method: string | null;
      requested: boolean;
      requestedCount: number | null;
    };
  dateScope: {
    startDate: string | null;
    endDate: string | null;
    validationStartDate: string | null;
    validationEndDate: string | null;
    holdoutStartDate: string | null;
    holdoutEndDate: string | null;
    independentSliceStartDate: string | null;
    independentSliceEndDate: string | null;
  };
  costModel: {
    required: boolean;
    slippageRequired: boolean;
  };
  validationPlan: {
    trainTestHoldoutRequired: boolean;
    independentSliceRequired: boolean;
    evidenceTraceRequired: boolean;
  };
  robustnessPlan: {
    robustnessChecksRequired: boolean;
  };
  expectedOutputs: string[];
  acceptanceCriteria: string[];
  failureCriteria: string[];
  provenance: {
    sourceType: string;
    plannerAction: string | null;
    selectionUsed: boolean;
  };
}

interface ExperimentDefinition {
  experimentId: string;
  status: ExperimentStatus;
  researchEngine: "CURRENT" | "VECTORBT";

    parameterSweep?: UnknownRecord;
    parameterSearchMethod?: string | null;
    parameterSearchCount?: number | null;

    optimizer?: {
      source: string | null;
      method: string | null;
      requested: boolean;
      requestedCount: number | null;
    };

  researchQuestion: string;
  hypothesis: string;

  researchHistory: UnknownRecord;

  source: {
    queueTaskId: number | null;
    sourceType: string;
    priority: number;
    reason: string;
  };

  strategy: {
    strategyId: string;
    name: string;
    ruleDefinition: string;
    parameters: UnknownRecord;
  };

  market: {
    symbol: string;
    timeframe: string;
  };

  dateScope: {
    selectionStatus: "RESOLVED" | "REQUIRED";
    selectionSource: string;
    exactDatesRequired: boolean;
    independentSliceRequired: boolean;
    startDate: string | null;
    endDate: string | null;
    validationStartDate: string | null;
    validationEndDate: string | null;
    holdoutStartDate: string | null;
    holdoutEndDate: string | null;
    independentSliceStartDate: string | null;
    independentSliceEndDate: string | null;
    notes: string[];
  };

  dataRequirements: {
    historicalDataRequired: boolean;
    exactDatesRequired: boolean;
    symbolResultsRequired: boolean;
    regimeResultsRequired: boolean;
    independentSliceRequired: boolean;
  };

  evaluation: {
    trainTestHoldoutRequired: boolean;
    costModelRequired: boolean;
    slippageRequired: boolean;
    robustnessChecksRequired: boolean;
    evidenceTraceRequired: boolean;
  };

  successCriteria: string[];

  failureCriteria: string[];

  constraints: {
    researchOnly: boolean;
    executionEnabled: boolean;
    databaseWriteEnabled: boolean;
    brokerExecutionEnabled: boolean;
  };

  researchPlan?: {
    plannerVersion: string | null;
    planStatus: string | null;
    plannerAction: string | null;
    selectedDimension: string | null;
    selectedMetric: string | null;
    selectedScore: number | null;
    selectedQuestion: string | null;
  };

  researchSpec?: ResearchExperimentSpec;
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

function toNumber(
  value: unknown,
  fallback = 0
): number {
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
      : fallback;
  }

  return fallback;
}

function getAgentOutput(
  context: AgentContext,
  agentId: string,
): UnknownRecord {
  const previousResults = context.previousResults as
    | Record<string, { output?: unknown } | undefined>
    | undefined;
  const output = previousResults?.[agentId]?.output;
  return isRecord(output) ? output : {};
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

function extractQueueOutput(
  context: AgentContext
): UnknownRecord {
  return getAgentOutput(context, "research-queue");
}

function extractQueueTask(
  context: AgentContext
): UnknownRecord {
  const output =
    extractQueueOutput(
      context
    );

  const queue =
    firstRecord(
      output.queue
    );

  return firstRecord(
    queue.selectedTask
  );
}

function extractStrategyOutput(
  context: AgentContext
): UnknownRecord {
  return getAgentOutput(context, "strategy");
}

function extractMarketOutput(
  context: AgentContext
): UnknownRecord {
  return getAgentOutput(context, "market-data");
}

function extractDateResolverOutput(
  context: AgentContext
): UnknownRecord {
  return getAgentOutput(context, "research-date-resolver");
}

function extractDecisionOutput(
  context: AgentContext
): UnknownRecord {
  return getAgentOutput(context, "research-decision");
}

function getBackendBaseUrl(): string {
  return (
    process.env.MARKETHQ_BACKEND_URL ??
    "http://127.0.0.1:8010"
  ).replace(/\/+$/, "");
}

async function fetchAdaptiveResearchPlan(): Promise<UnknownRecord> {
  const url = `${getBackendBaseUrl()}/api/research-plan`;

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });

    const body = await response.json().catch(() => null);

    if (
      !response.ok ||
      !isRecord(body) ||
      body.success !== true
    ) {
      return {};
    }

    return isRecord(body.data) ? body.data : {};
  } catch {
    return {};
  }
}

function normalizeResearchDecisionOutput(
  decisionOutput: UnknownRecord
): UnknownRecord {
  return {
    ...decisionOutput,
    decision:
      toStringValue(
        decisionOutput.decision
      ) ||
      toStringValue(
        decisionOutput.state
      ),
    action:
      toStringValue(
        decisionOutput.action
      ) ||
      toStringValue(
        decisionOutput.research_action
      ),
    nextResearchQuestion:
      toStringValue(
        decisionOutput.nextResearchQuestion
      ) ||
      toStringValue(
        decisionOutput.next_research_question
      ),
  };
}

function extractHistoricalMemory(
  decisionOutput: UnknownRecord
): UnknownRecord {
  const historicalMemory =
    firstRecord(
      decisionOutput.historicalMemory,
      isRecord(decisionOutput.sourceInputs)
        ? decisionOutput.sourceInputs.historicalMemory
        : undefined,
    );

  const summary =
    firstRecord(
      historicalMemory.summary,
    );

  return {
    status:
      toStringValue(
        historicalMemory.status,
      ) || null,
    count:
      toNumber(
        historicalMemory.count,
        0,
      ),
    summary: {
      total: toNumber(summary.total, 0),
      promising: toNumber(summary.promising, 0),
      mixed: toNumber(summary.mixed, 0),
      reject: toNumber(summary.reject, 0),
      inconclusive: toNumber(summary.inconclusive, 0),
      averageConfidence: toNumber(
        summary.averageConfidence,
        0,
      ),
    },
    enabled: Boolean(
      historicalMemory.enabled,
    ),
    reason:
      toStringValue(
        historicalMemory.reason,
      ) || null,
  };
}

function normalizeParameters(
  strategyOutput: UnknownRecord
): UnknownRecord {
  const candidates = [
    strategyOutput.parameters,
    strategyOutput.params,
    strategyOutput.strategyParameters,
    strategyOutput.strategy_parameters,
  ];

  for (
    const candidate of candidates
  ) {
    if (
      isRecord(candidate)
    ) {
      return candidate;
    }
  }

  return {};
}

function generateExperimentId(
  context: AgentContext,
  queueTask: UnknownRecord
): string {
  const queueId =
    toNumber(
      queueTask.id,
      0
    );

  const strategy =
    toStringValue(
      context.strategyId,
      "STRATEGY"
    )
      .replace(
        /[^a-zA-Z0-9]/g,
        ""
      )
      .toUpperCase();

  const suffix =
    queueId > 0
      ? `Q${queueId}`
      : "QNEW";

  return `EXP-${strategy}-${suffix}-${Date.now()}`;
}

function inferHypothesis(
  question: string,
  decision: UnknownRecord
): string {
  const explicit =
    toStringValue(
      decision.hypothesis
    );

  if (explicit) {
    return explicit;
  }

  if (
    question
      .toLowerCase()
      .includes(
        "reproduce"
      )
  ) {
    return (
      "The same rule definition, cost model and regime conditions should reproduce a materially consistent strategy edge on a fresh independent historical slice."
    );
  }

  if (
    question
      .toLowerCase()
      .includes(
        "evidence"
      )
  ) {
    return (
      "Additional independent evidence should clarify whether the reported strategy result is reproducible and sufficiently traceable."
    );
  }

  return (
    "The selected research question should be testable through a controlled historical experiment without changing the original strategy definition."
  );
}

function buildRuleDefinition(
  strategyOutput: UnknownRecord
): string {
  const candidates = [
    strategyOutput.ruleDefinition,
    strategyOutput.rule_definition,
    strategyOutput.rules,
    strategyOutput.strategyRules,
    strategyOutput.definition,
  ];

  for (
    const candidate of candidates
  ) {
    const value =
      toStringValue(
        candidate
      );

    if (value) {
      return value;
    }
  }

  return (
    "Preserve the original strategy rule definition exactly as represented by the source strategy output."
  );
}

function buildStrategyName(
  strategyOutput: UnknownRecord,
  context: AgentContext
): string {
  return (
    toStringValue(
      strategyOutput.name
    ) ||
    toStringValue(
      strategyOutput.strategyName
    ) ||
    toStringValue(
      strategyOutput.strategy_name
    ) ||
    context.strategyId ||
    "Unknown Strategy"
  );
}

function buildSymbol(
  queueTask: UnknownRecord,
  marketOutput: UnknownRecord,
  context: AgentContext
): string {
  const metadata =
    isRecord(
      queueTask.metadata
    )
      ? queueTask.metadata
      : {};

  return (
    toStringValue(
      metadata.symbol
    ) ||
    toStringValue(
      queueTask.symbol
    ) ||
    toStringValue(
      marketOutput.symbol
    ) ||
    context.symbol ||
    "UNKNOWN"
  );
}

function buildTimeframe(
  queueTask: UnknownRecord,
  marketOutput: UnknownRecord,
  context: AgentContext
): string {
  const metadata =
    isRecord(
      queueTask.metadata
    )
      ? queueTask.metadata
      : {};

  return (
    toStringValue(
      metadata.timeframe
    ) ||
    toStringValue(
      queueTask.timeframe
    ) ||
    toStringValue(
      marketOutput.timeframe
    ) ||
    context.timeframe ||
    "1d"
  );
}

function normalizeIsoDate(
  value: unknown
): string | null {
  const raw = toStringValue(value);
  if (!raw) {
    return null;
  }

  const match = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : null;
}

function extractDateValue(
  sources: UnknownRecord[],
  keys: string[]
): string | null {
  for (const source of sources) {
    for (const key of keys) {
      const normalized = normalizeIsoDate(source[key]);
      if (normalized) {
        return normalized;
      }
    }
  }

  return null;
}

function buildDateScope(
  queueTask: UnknownRecord,
  decisionOutput: UnknownRecord,
  dateResolverOutput: UnknownRecord,
  context: AgentContext
): {
  selectionStatus: "RESOLVED" | "REQUIRED";
  selectionSource: string;
  exactDatesRequired: boolean;
  independentSliceRequired: boolean;
  startDate: string | null;
  endDate: string | null;
  validationStartDate: string | null;
  validationEndDate: string | null;
  holdoutStartDate: string | null;
  holdoutEndDate: string | null;
  independentSliceStartDate: string | null;
  independentSliceEndDate: string | null;
  notes: string[];
} {
  const metadata =
    isRecord(queueTask.metadata)
      ? queueTask.metadata
      : {};
  const input =
    isRecord(context.input)
      ? context.input
      : {};

  const resolverScope =
    firstRecord(
      dateResolverOutput.dateScope
    );

  const sources = [
    resolverScope,
    metadata,
    queueTask,
    decisionOutput,
    input,
  ];

  const startDate = extractDateValue(
    sources,
    ["startDate", "start_date", "periodStart", "period_start", "dataStart", "data_start"],
  );
  const endDate = extractDateValue(
    sources,
    ["endDate", "end_date", "periodEnd", "period_end", "dataEnd", "data_end"],
  );
  const validationStartDate = extractDateValue(
    sources,
    ["validationStartDate", "validation_start_date"],
  );
  const validationEndDate = extractDateValue(
    sources,
    ["validationEndDate", "validation_end_date"],
  );
  const holdoutStartDate = extractDateValue(
    sources,
    ["holdoutStartDate", "holdout_start_date"],
  );
  const holdoutEndDate = extractDateValue(
    sources,
    ["holdoutEndDate", "holdout_end_date"],
  );
  const independentSliceStartDate = extractDateValue(
    sources,
    ["independentSliceStartDate", "independent_slice_start_date", "independentStartDate", "independent_start_date"],
  );
  const independentSliceEndDate = extractDateValue(
    sources,
    ["independentSliceEndDate", "independent_slice_end_date", "independentEndDate", "independent_end_date"],
  );

  const resolverResolved =
    toStringValue(
      dateResolverOutput.status
    ).toUpperCase() === "READY" ||
    toStringValue(
      resolverScope.selectionStatus
    ).toUpperCase() === "RESOLVED";

  const resolved = Boolean(
    resolverResolved &&
    startDate &&
    endDate &&
    independentSliceStartDate &&
    independentSliceEndDate
  );

  const notes: string[] = [];
  if (!resolved) {
    notes.push(
      "Exact experiment dates are not inventable at generation time; Research Queue or experiment input must supply the historical windows before execution.",
    );
  }

  return {
    selectionStatus: resolved ? "RESOLVED" : "REQUIRED",
    selectionSource: resolved
      ? (resolverResolved
          ? `research-date-resolver:${toStringValue(
              resolverScope.selectionSource,
              "resolved",
            )}`
          : "research-queue-or-context-input")
      : "awaiting-explicit-historical-window",
    exactDatesRequired: true,
    independentSliceRequired: true,
    startDate,
    endDate,
    validationStartDate,
    validationEndDate,
    holdoutStartDate,
    holdoutEndDate,
    independentSliceStartDate,
    independentSliceEndDate,
    notes,
  };
}

function generateSuccessCriteria(
  question: string
): string[] {
  const criteria = [
    "Original strategy rule definition remains unchanged.",
    "Historical inputs and experiment assumptions are fully traceable.",
    "The selected research question receives a direct and reproducible answer.",
    "Costs and slippage assumptions are explicitly represented.",
    "Results can be evaluated on independent data where required.",
  ];

  if (
    question
      .toLowerCase()
      .includes(
        "reproduce"
      )
  ) {
    criteria.push(
      "Fresh independent historical results show materially consistent behavior with the original research result."
    );
  }

  return criteria;
}

function generateFailureCriteria(
  question: string
): string[] {
  const criteria = [
    "Original rules cannot be reconstructed exactly.",
    "Required historical data or experiment provenance is missing.",
    "Results depend on undocumented parameter changes.",
    "The outcome cannot be independently reproduced or audited.",
    "Execution or broker integration is required.",
  ];

  if (
    question
      .toLowerCase()
      .includes(
        "cost"
      )
  ) {
    criteria.push(
      "The reported result disappears under the specified cost model."
    );
  }

  return criteria;
}

function dateResolverScopeValue(
  output: UnknownRecord,
  key: string
): string {
  const scope = firstRecord(output.dateScope);
  return toStringValue(scope[key]);
}

export async function runExperimentGeneratorAgent(
  context: AgentContext
): Promise<
  Record<string, unknown>
> {
  const queueOutput =
    extractQueueOutput(
      context
    );

  const queueTask =
    extractQueueTask(
      context
    );

  const strategyOutput =
    extractStrategyOutput(
      context
    );

  // V1.2: imported strategy becomes the preferred canonical strategy source.
  // The imported definition is data only; no imported code is executed.
  const importedStrategy =
    isRecord(strategyOutput.importedStrategy)
      ? strategyOutput.importedStrategy
      : null;

  const marketOutput =
    extractMarketOutput(
      context
    );

  const decisionOutput =
    normalizeResearchDecisionOutput(
      extractDecisionOutput(
        context
      )
    );

  const researchHistory =
    extractHistoricalMemory(
      decisionOutput
    );

  const dateResolverOutput =
    extractDateResolverOutput(
      context
    );

  const requestedResearchEngine =
    toStringValue(
      isRecord(context.input)
        ? context.input.researchEngine
        : null
    ).toUpperCase();

  const researchEngine: "CURRENT" | "VECTORBT" =
    requestedResearchEngine === "VECTORBT"
      ? "VECTORBT"
      : "CURRENT";


  const adaptiveResearchPlan =
    await fetchAdaptiveResearchPlan();

  const queue =
    firstRecord(
      queueOutput.queue
    );

  const sourceTaskId =
    Number.isFinite(
      toNumber(
        queueTask.id,
        NaN
      )
    )
      ? toNumber(
          queueTask.id
        )
      : null;

  const plannerStatus =
    toStringValue(
      adaptiveResearchPlan.plan_status
    ).toUpperCase();

  const plannerSameQuestionActive =
    adaptiveResearchPlan.same_question_active === true;

  const plannerQuestion =
    toStringValue(
      adaptiveResearchPlan.selected_question
    );

  const plannerCanGuideResearch =
    plannerStatus === "READY" &&
    !plannerSameQuestionActive &&
    Boolean(plannerQuestion);

  const question =
    (plannerCanGuideResearch
      ? plannerQuestion
      : "") ||
    toStringValue(
      queueTask.question
    ) ||
    toStringValue(
      decisionOutput.nextResearchQuestion
    );

  if (!question) {
    return {
      agent:
        "experiment-generator",

      status:
        "BLOCKED",

      reason:
        "No research question was available from Research Queue or Research Decision.",

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
        "RESEARCH_EXPERIMENT_DEFINITION_ONLY",
    };
  }

  const strategyId =
    toStringValue(
      importedStrategy?.strategyId
    ) ||
    context.strategyId ||
    toStringValue(
      strategyOutput.strategyId
    ) ||
    "UNKNOWN_STRATEGY";

  const symbol =
    buildSymbol(
      queueTask,
      marketOutput,
      context
    );

  const timeframe =
    buildTimeframe(
      queueTask,
      marketOutput,
      context
    );

  const strategyName =
    toStringValue(
      importedStrategy?.name
    ) ||
    buildStrategyName(
      strategyOutput,
      context
    );

  const importedRuleDefinition =
    typeof importedStrategy?.ruleDefinition ===
    "string"
      ? importedStrategy.ruleDefinition
      : importedStrategy?.ruleDefinition !==
          undefined
        ? JSON.stringify(
            importedStrategy.ruleDefinition
          ) ?? ""
        : "";

  const ruleDefinition =
    importedRuleDefinition ||
    buildRuleDefinition(
      strategyOutput
    );






  const priority =
    toNumber(
      queueTask.priority,
      0
    );

  const reason =
    toStringValue(
      queueTask.reason
    ) ||
    "Generated from the selected Research Queue task.";

  const experimentId =
    generateExperimentId(
      context,
      queueTask
    );

  const hypothesis =
    inferHypothesis(
      question,
      decisionOutput
    );

  const dateScope =
    buildDateScope(
      queueTask,
      decisionOutput,
      dateResolverOutput,
      context
    );

  const generatorInput =
    isRecord(context.input)
      ? context.input
      : {};

  const importedStrategyDefinition =
    isRecord(generatorInput.strategyDefinition)
      ? generatorInput.strategyDefinition
      : isRecord(generatorInput.importedStrategy)
        ? generatorInput.importedStrategy
        : isRecord(generatorInput.strategyImport)
          ? generatorInput.strategyImport
          : {};

  const importedParameters =
    isRecord(importedStrategyDefinition.parameters)
      ? importedStrategyDefinition.parameters
      : {};

  const generatedParameters =
    normalizeParameters(strategyOutput);

  const parameters =
    Object.keys(generatedParameters).length > 0
      ? generatedParameters
      : importedParameters;

  
  const requestedParameterSweep =
    isRecord(generatorInput.parameterSweep)
      ? generatorInput.parameterSweep
      : {};

  const parameterSweepRequested =
    Object.keys(requestedParameterSweep).length > 0;

  const parameterSearchMethod =
    typeof generatorInput.parameterSearchMethod === "string" &&
    generatorInput.parameterSearchMethod.trim().length > 0
      ? generatorInput.parameterSearchMethod.trim()
      : parameterSweepRequested
        ? "grid"
        : null;

  const rawParameterSearchCount =
    Number(generatorInput.parameterSearchCount);

  const parameterSearchCount =
    Number.isFinite(rawParameterSearchCount)
      ? rawParameterSearchCount
      : null;

  const researchOptimizer = {
    source:
      parameterSweepRequested
        ? "SYSTEMATIC_TRADING_FRAMEWORK"
        : null,
    method:
      parameterSearchMethod,
    requested:
      parameterSweepRequested,
    requestedCount:
      parameterSearchCount,
  };const researchSpec: ResearchExperimentSpec = {
    specVersion: "RESEARCH_EXPERIMENT_SPEC_V1",
    plannerVersion:
      toStringValue(
        adaptiveResearchPlan.planner_version
      ) || null,
    strategyId,
    hypothesis,
    objective:
      toStringValue(
        adaptiveResearchPlan.selected_dimension
      ) || "research_validation",
    researchQuestion: question,
    targetDimension:
      toStringValue(
        adaptiveResearchPlan.selected_dimension
      ) || null,
    selectedMetric:
      toStringValue(
        adaptiveResearchPlan.selected_metric
      ) || null,
    selectedScore:
      Number.isFinite(
        Number(
          adaptiveResearchPlan.selected_score
        )
      )
        ? Number(
            adaptiveResearchPlan.selected_score
          )
        : null,
    baselineParameters: parameters,
    fixedParameters: parameters,

    parameterSweep:
      parameterSweepRequested
        ? requestedParameterSweep
        : undefined,

    parameterSearchMethod,

    parameterSearchCount,

    optimizer:
      parameterSweepRequested
        ? researchOptimizer
        : undefined,
    dateScope: {
      startDate: dateScope.startDate,
      endDate: dateScope.endDate,
      validationStartDate: dateScope.validationStartDate,
      validationEndDate: dateScope.validationEndDate,
      holdoutStartDate: dateScope.holdoutStartDate,
      holdoutEndDate: dateScope.holdoutEndDate,
      independentSliceStartDate:
        dateScope.independentSliceStartDate,
      independentSliceEndDate:
        dateScope.independentSliceEndDate,
    },
    costModel: {
      required: true,
      slippageRequired: true,
    },
    validationPlan: {
      trainTestHoldoutRequired: true,
      independentSliceRequired: true,
      evidenceTraceRequired: true,
    },
    robustnessPlan: {
      robustnessChecksRequired: true,
    },
    expectedOutputs: [
      "primary_metric",
      "cost_survival",
      "validation_summary",
      "evidence_trace",
    ],
    acceptanceCriteria: generateSuccessCriteria(question),
    failureCriteria: generateFailureCriteria(question),
    provenance: {
      sourceType: "adaptive_research_planner",
      plannerAction:
        toStringValue(
          adaptiveResearchPlan.planner_action
        ) || null,
      selectionUsed: plannerCanGuideResearch,
    },
  };













  const experiment:
    ExperimentDefinition = {
      experimentId,

      status:
        dateScope.selectionStatus === "RESOLVED"
          ? "GENERATED"
          : "BLOCKED",

      researchEngine,



      parameterSweep:

        parameterSweepRequested

          ? requestedParameterSweep

          : undefined,


      parameterSearchMethod,


      parameterSearchCount,


      optimizer:

        parameterSweepRequested

          ? researchOptimizer

          : undefined,
      researchQuestion:
        question,

      hypothesis,

      researchHistory,

      source: {
        queueTaskId:
          sourceTaskId,

        sourceType:
          "brain_research_queue",

        priority,

        reason,
      },

      strategy: {
        strategyId,

        name:
          strategyName,

        ruleDefinition,

        parameters: Object.keys(parameters).length > 0 ? parameters : importedParameters,
      },

      market: {
        symbol,

        timeframe,
      },

      dateScope,

      dataRequirements: {
        historicalDataRequired:
          true,

        exactDatesRequired:
          true,

        symbolResultsRequired:
          true,

        regimeResultsRequired:
          true,

        independentSliceRequired:
          true,
      },

      evaluation: {
        trainTestHoldoutRequired:
          true,

        costModelRequired:
          true,

        slippageRequired:
          true,

        robustnessChecksRequired:
          true,

        evidenceTraceRequired:
          true,
      },

      successCriteria:
        generateSuccessCriteria(
          question
        ),

      failureCriteria:
        generateFailureCriteria(
          question
        ),

      constraints: {
        researchOnly:
          true,

        executionEnabled:
          false,

        databaseWriteEnabled:
          false,

        brokerExecutionEnabled:
          false,
      },

      researchPlan: {
        plannerVersion:
          toStringValue(
            adaptiveResearchPlan.planner_version
          ) || null,
        planStatus:
          toStringValue(
            adaptiveResearchPlan.plan_status
          ) || null,
        plannerAction:
          toStringValue(
            adaptiveResearchPlan.planner_action
          ) || null,
        selectedDimension:
          toStringValue(
            adaptiveResearchPlan.selected_dimension
          ) || null,
        selectedMetric:
          toStringValue(
            adaptiveResearchPlan.selected_metric
          ) || null,
        selectedScore:
          Number.isFinite(
            Number(
              adaptiveResearchPlan.selected_score
            )
          )
            ? Number(
                adaptiveResearchPlan.selected_score
              )
            : null,
        selectedQuestion:
          plannerQuestion || null,
      },

      researchSpec,
    };

  return {
    agent:
      "experiment-generator",

    runId:
      context.runId,

    experiment,

    dateScope: {
      selectionStatus:
        dateScope.selectionStatus,
      selectionSource:
        dateScope.selectionSource,
      independentSliceStartDate:
        dateScope.independentSliceStartDate,
      independentSliceEndDate:
        dateScope.independentSliceEndDate,
      exactDatesReady:
        dateScope.selectionStatus === "RESOLVED",
      notes:
        dateScope.notes,
    },

    queueContext: {
      activeCount:
        toNumber(
          queue.activeCount
        ),

      selectedTask:
        queueTask,

      selectionSource:
        "research-queue",
    },

    dateResolverContext: {
      status:
        toStringValue(
          dateResolverOutput.status
        ) || null,
      selectionSource:
        toStringValue(
          dateResolverScopeValue(dateResolverOutput, "selectionSource")
        ) || null,
    },

    decisionContext: {
      decision:
        toStringValue(
          decisionOutput.decision
        ) || null,

      action:
        toStringValue(
          decisionOutput.action
        ) || null,

      nextResearchQuestion:
        toStringValue(
          decisionOutput.nextResearchQuestion
        ) || null,

      historicalMemory: researchHistory,
    },

    researchPlanContext: {
      plannerVersion:
        toStringValue(
          adaptiveResearchPlan.planner_version
        ) || null,
      planStatus:
        toStringValue(
          adaptiveResearchPlan.plan_status
        ) || null,
      plannerAction:
        toStringValue(
          adaptiveResearchPlan.planner_action
        ) || null,
      selectedDimension:
        toStringValue(
          adaptiveResearchPlan.selected_dimension
        ) || null,
      selectedMetric:
        toStringValue(
          adaptiveResearchPlan.selected_metric
        ) || null,
      selectedScore:
        Number.isFinite(
          Number(
            adaptiveResearchPlan.selected_score
          )
        )
          ? Number(
              adaptiveResearchPlan.selected_score
            )
          : null,
      selectedQuestion:
        plannerQuestion || null,
      sameQuestionActive:
        plannerSameQuestionActive,
      selectionUsed:
        plannerCanGuideResearch,
    },

    researchHistory,

    researchSpec,

    generationPolicy: {
      preserveOriginalRules:
        true,

      preserveResearchQuestion:
        true,

      requireExplicitCosts:
        true,

      requireIndependentValidation:
        true,

      requireExplicitHistoricalDates:
        true,

      requireIndependentSliceDates:
        true,

      requireEvidenceTrace:
        true,

      requireDateResolution:
        true,

      dateResolutionAgent:
        "research-date-resolver",

      mutateQueue:
        false,

      writeDatabase:
        false,
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

    mode:
      "RESEARCH_EXPERIMENT_DEFINITION_ONLY",

    generatedAt:
      new Date().toISOString(),
  };
}

export function registerExperimentGeneratorAgent(): void {
  agentRunner.register(
    "experiment-generator",
    runExperimentGeneratorAgent
  );
}










