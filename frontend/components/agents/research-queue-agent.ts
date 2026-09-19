import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

type UnknownRecord =
  Record<string, unknown>;

interface QueueTask {
  id: number | null;
  question: string;
  reason: string;
  priority: number;
  targetNodeId: number | null;
  targetClaimId: number | null;
  status: string;
  createdAt: string;
  updatedAt: string;
  metadata: UnknownRecord;
}

function isRecord(
  value: unknown
): value is UnknownRecord {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    !Array.isArray(value)
  );
}

function toNumber(
  value: unknown,
  fallback = 0
): number {
  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return value;
  }

  if (
    typeof value === "string" &&
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

function toNullableNumber(
  value: unknown
): number | null {
  const parsed =
    toNumber(
      value,
      NaN
    );

  return Number.isFinite(
    parsed
  )
    ? parsed
    : null;
}

function toStringValue(
  value: unknown,
  fallback = ""
): string {
  if (
    typeof value === "string" &&
    value.trim()
  ) {
    return value.trim();
  }

  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return String(value);
  }

  return fallback;
}

function firstRecord(
  root: unknown,
  paths: string[][]
): UnknownRecord {
  for (
    const path of paths
  ) {
    let current:
      unknown = root;

    let valid = true;

    for (
      const key of path
    ) {
      if (
        !isRecord(
          current
        ) ||
        !(key in current)
      ) {
        valid = false;
        break;
      }

      current =
        current[key];
    }

    if (
      valid &&
      isRecord(current)
    ) {
      return current;
    }
  }

  return {};
}

function findArray(
  root: unknown,
  keys: string[]
): unknown[] {
  const wanted =
    new Set(
      keys.map(
        (key) =>
          key.toLowerCase()
      )
    );

  const walk = (
    value: unknown
  ): unknown[] => {
    if (
      Array.isArray(value)
    ) {
      return value;
    }

    if (
      !isRecord(value)
    ) {
      return [];
    }

    for (
      const [
        key,
        child,
      ] of Object.entries(
        value
      )
    ) {
      if (
        wanted.has(
          key.toLowerCase()
        ) &&
        Array.isArray(child)
      ) {
        return child;
      }
    }

    for (
      const child of Object.values(
        value
      )
    ) {
      const found =
        walk(child);

      if (
        found.length > 0
      ) {
        return found;
      }
    }

    return [];
  };

  return walk(root);
}

function parseMetadata(
  value: unknown
): UnknownRecord {
  if (
    isRecord(value)
  ) {
    return value;
  }

  if (
    typeof value === "string" &&
    value.trim()
  ) {
    try {
      const parsed =
        JSON.parse(
          value
        );

      return isRecord(
        parsed
      )
        ? parsed
        : {};
    } catch {
      return {};
    }
  }

  return {};
}

function normalizeTask(
  value: unknown
): QueueTask | null {
  if (
    !isRecord(value)
  ) {
    return null;
  }

  const metadata =
    parseMetadata(
      value.metadata_json ??
        value.metadata
    );

  const id =
    toNullableNumber(
      value.id ??
        value.queue_id
    );

  const question =
    toStringValue(
      value.question
    );

  if (!question) {
    return null;
  }

  return {
    id,
    question,

    reason:
      toStringValue(
        value.reason
      ),

    priority:
      toNumber(
        value.priority
      ),

    targetNodeId:
      toNullableNumber(
        value.target_node_id ??
          value.targetNodeId
      ),

    targetClaimId:
      toNullableNumber(
        value.target_claim_id ??
          value.targetClaimId
      ),

    status:
      toStringValue(
        value.status,
        "queued"
      ).toLowerCase(),

    createdAt:
      toStringValue(
        value.created_at ??
          value.createdAt
      ),

    updatedAt:
      toStringValue(
        value.updated_at ??
          value.updatedAt
      ),

    metadata,
  };
}

function collectQueueTasks(
  roots: unknown[]
): QueueTask[] {
  const tasks:
    QueueTask[] = [];

  const seen =
    new Set<string>();

  for (
    const root of roots
  ) {
    const values =
      findArray(
        root,
        [
          "recent_queue",
          "research_queue",
          "queue",
          "tasks",
          "items",
        ]
      );

    for (
      const value of values
    ) {
      const task =
        normalizeTask(
          value
        );

      if (!task) {
        continue;
      }

      const key =
        String(
          task.id ??
            `${task.question}|${task.priority}`
        );

      if (
        seen.has(key)
      ) {
        continue;
      }

      seen.add(key);
      tasks.push(task);
    }
  }

  return tasks;
}

function queueRelevanceScore(
  task: QueueTask,
  strategyId?: string,
  symbol?: string,
  timeframe?: string
): number {
  let score =
    task.priority;

  const metadata =
    task.metadata;

  const taskStrategy =
    toStringValue(
      metadata.strategy_id ??
        metadata.strategyId
    );

  const taskSymbol =
    toStringValue(
      metadata.symbol
    );

  const taskTimeframe =
    toStringValue(
      metadata.timeframe
    );

  if (
    strategyId &&
    taskStrategy &&
    taskStrategy.toUpperCase() ===
      strategyId.toUpperCase()
  ) {
    score += 5;
  }

  if (
    symbol &&
    taskSymbol &&
    taskSymbol.toUpperCase() ===
      symbol.toUpperCase()
  ) {
    score += 2;
  }

  if (
    timeframe &&
    taskTimeframe &&
    taskTimeframe.toLowerCase() ===
      timeframe.toLowerCase()
  ) {
    score += 1;
  }

  if (
    task.status ===
    "working"
  ) {
    score -= 0.25;
  }

  return score;
}

function sortTasks(
  tasks: QueueTask[],
  context: AgentContext
): QueueTask[] {
  return [
    ...tasks,
  ].sort(
    (
      left,
      right
    ) => {
      const leftScore =
        queueRelevanceScore(
          left,
          context.strategyId,
          context.symbol,
          context.timeframe
        );

      const rightScore =
        queueRelevanceScore(
          right,
          context.strategyId,
          context.symbol,
          context.timeframe
        );

      if (
        rightScore !==
        leftScore
      ) {
        return (
          rightScore -
          leftScore
        );
      }

      return (
        (
          right.id ??
          0
        ) -
        (
          left.id ??
          0
        )
      );
    }
  );
}

function extractResearchDecision(
  context: AgentContext
): UnknownRecord {
  const result =
    context.previousResults?.[
      "research-decision"
    ]?.output;

  if (isRecord(result)) {
    const nestedDecision =
      isRecord(result.decision)
        ? result.decision
        : {};

    const nestedLoop =
      isRecord(result.researchLoop)
        ? result.researchLoop
        : {};

    /*
     * Research Decision currently exposes the canonical next
     * question in BOTH:
     *   output.decision.nextResearchQuestion
     *   output.researchLoop.nextResearchQuestion
     *
     * The queue must consume the canonical loop value regardless
     * of which representation is present. Merge both shapes here
     * instead of relying on only output.decision.
     */
    const nextResearchQuestion =
      toStringValue(
        nestedDecision.nextResearchQuestion ??
          nestedLoop.nextResearchQuestion ??
          result.nextResearchQuestion
      );

    const merged: UnknownRecord = {
      ...nestedDecision,
      ...(nextResearchQuestion
        ? {
            nextResearchQuestion,
          }
        : {}),
      ...(Object.keys(nestedLoop).length > 0
        ? {
            researchLoop: nestedLoop,
          }
        : {}),
      ...(isRecord(result.decisionContext)
        ? {
            decisionContext: result.decisionContext,
          }
        : {}),
    };

    if (
      Object.keys(merged).length > 0
    ) {
      return merged;
    }
  }

  const priorExperimentResult =
    context.input?.[
      "priorExperimentResult"
    ];

  if (
    isRecord(priorExperimentResult)
  ) {
    const priorDecision =
      priorExperimentResult.decision;

    if (isRecord(priorDecision)) {
      const priorLoop =
        isRecord(
          priorExperimentResult.researchLoop
        )
          ? priorExperimentResult.researchLoop
          : {};

      const nextResearchQuestion =
        toStringValue(
          priorDecision.nextResearchQuestion ??
            priorLoop.nextResearchQuestion
        );

      return {
        ...priorDecision,
        ...(nextResearchQuestion
          ? {
              nextResearchQuestion,
            }
          : {}),
        ...(Object.keys(priorLoop).length > 0
          ? {
              researchLoop: priorLoop,
            }
          : {}),
      };
    }
  }

  return {};
}

type QueueFeedbackType =
  | "PROMISING"
  | "MIXED"
  | "REJECT"
  | "UNKNOWN";

interface QueueFeedback {
  source: "research-decision";
  decision: QueueFeedbackType;
  action: string;
  nextResearchQuestion: string;
  researchMode: string;
  priorityAdjustment: number;
  reason: string;
}

function normalizeDecisionName(
  value: unknown
): QueueFeedbackType {
  const normalized =
    toStringValue(value)
      .toUpperCase()
      .replace(/[-\s]+/g, "_");

  if (
    normalized.includes("PROMISING") ||
    normalized.includes("ACCEPT") ||
    normalized.includes("ADVANCE")
  ) {
    return "PROMISING";
  }

  if (
    normalized.includes("MIXED") ||
    normalized.includes("REFINE") ||
    normalized.includes("IMPROVE")
  ) {
    return "MIXED";
  }

  if (
    normalized.includes("REJECT") ||
    normalized.includes("FAIL") ||
    normalized.includes("ABANDON")
  ) {
    return "REJECT";
  }

  return "UNKNOWN";
}

function buildQueueFeedback(
  decision: UnknownRecord
): QueueFeedback {
  const decisionName =
    normalizeDecisionName(
      decision.decision
    );

  const decisionBasis =
    toStringValue(
      decision.currentDecisionBasis ??
        decision.decisionBasis ??
        decision.basis
    ).toUpperCase();

  const robustnessFailureCount =
    Math.max(
      0,
      toNumber(
        decision.robustnessFailureCount,
        0
      )
    );

  const wfoResolvedSupportive =
    decision.wfoResolvedSupportive === true;

  const wfoStrongNegative =
    decision.wfoStrongNegative === true;

  const action =
    toStringValue(
      decision.action
    );

  const nextResearchQuestion =
    toStringValue(
      decision.nextResearchQuestion
    );

  /*
   * Decision output can legitimately use an action such as
   * RESEARCH_MORE_OR_DEPRIORITIZE while the evidence basis is
   * EVIDENCE_INCOMPLETE. That is not a semantic UNKNOWN for the
   * research queue: it means the current direction needs targeted
   * evidence/robustness work.
   *
   * Keep explicit PROMISING/MIXED/REJECT decisions authoritative.
   * Only classify an otherwise unknown decision from the evidence
   * basis when the basis itself gives us a strong research signal.
   */
  if (
    decisionName === "PROMISING"
  ) {
    return {
      source: "research-decision",
      decision: decisionName,
      action: action || "Run a confirmation or robustness refinement experiment.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "Can the promising result be confirmed under an independent research configuration?",
      researchMode: "CONFIRMATION_AND_REFINEMENT",
      priorityAdjustment: 3,
      reason:
        "The latest Research Decision is promising; prioritize confirmation and controlled refinement.",
    };
  }

  if (
    decisionName === "MIXED"
  ) {
    return {
      source: "research-decision",
      decision: decisionName,
      action: action || "Run a targeted improvement experiment against the weakest evidence dimension.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "Which weakness in the mixed result can be isolated and improved without introducing new overfit risk?",
      researchMode: "TARGETED_IMPROVEMENT",
      priorityAdjustment: 2,
      reason:
        "The latest Research Decision is mixed; target the weakest evidence before advancing the strategy.",
    };
  }

  if (
    decisionName === "REJECT"
  ) {
    return {
      source: "research-decision",
      decision: decisionName,
      action: action || "Generate an alternative hypothesis or replacement research direction.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "What alternative hypothesis can be tested after the rejected research result?",
      researchMode: "ALTERNATIVE_HYPOTHESIS",
      priorityAdjustment: 1,
      reason:
        "The latest Research Decision rejected the current direction; move the queue toward an alternative hypothesis.",
    };
  }

  /*
   * Evidence-incomplete decisions are a distinct feedback state.
   * If robustness has also failed, prioritize targeted improvement
   * rather than labeling the result as UNKNOWN/EXPLORATORY.
   */
  if (
    decisionBasis === "EVIDENCE_INCOMPLETE"
  ) {
    return {
      source: "research-decision",
      decision: "MIXED",
      action:
        action ||
        "Run a targeted improvement experiment against the incomplete evidence and robustness weaknesses.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "Which missing evidence and robustness weakness can be isolated and tested on a fresh independent historical slice?",
      researchMode: "TARGETED_IMPROVEMENT",
      priorityAdjustment:
        robustnessFailureCount > 0 ? 3 : 2,
      reason:
        robustnessFailureCount > 0
          ? `Evidence is incomplete and ${robustnessFailureCount} robustness failure(s) remain; target the weakest evidence dimension before advancing.`
          : "Evidence is incomplete; target the missing evidence before advancing the strategy.",
    };
  }

  /*
   * Strong WFO/robustness negatives are enough to steer the queue
   * away from confirmation, even when the top-level decision label
   * is not normalized to REJECT.
   */
  if (
    wfoStrongNegative ||
    robustnessFailureCount >= 3
  ) {
    return {
      source: "research-decision",
      decision: "MIXED",
      action:
        action ||
        "Run a targeted robustness experiment against the strongest failure mode.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "Can the identified robustness weakness be removed on a fresh independent historical slice without changing the core rule definition?",
      researchMode: "TARGETED_IMPROVEMENT",
      priorityAdjustment: 3,
      reason:
        wfoStrongNegative
          ? "The latest Research Decision contains a strong negative WFO signal; isolate the failure before considering advancement."
          : `The latest Research Decision contains ${robustnessFailureCount} robustness failure(s); isolate the failure before considering advancement.`,
    };
  }

  /*
   * A supportive WFO signal with an otherwise unresolved label is
   * not enough to call the result PROMISING. Keep it exploratory
   * until the explicit promising gates are satisfied upstream.
   */
  if (
    wfoResolvedSupportive
  ) {
    return {
      source: "research-decision",
      decision: "MIXED",
      action:
        action ||
        "Run a confirmation and evidence-completeness experiment before advancing.",
      nextResearchQuestion:
        nextResearchQuestion ||
        "Can the supportive WFO result be confirmed while satisfying the remaining independent validation and holdout gates?",
      researchMode: "CONFIRMATION_AND_REFINEMENT",
      priorityAdjustment: 2,
      reason:
        "WFO is supportive but the top-level Research Decision is not explicitly promising; confirm the remaining gates before advancing.",
    };
  }

  return {
    source: "research-decision",
    decision: "UNKNOWN",
    action:
      action ||
      "Generate a cautious follow-up research task from the latest available evidence.",
    nextResearchQuestion:
      nextResearchQuestion ||
      "What is the next independently testable research question from the available evidence?",
    researchMode: "EXPLORATORY",
    priorityAdjustment: 1,
    reason:
      "The Research Decision did not expose a known decision class or sufficiently strong evidence-basis signal; keep the next task exploratory.",
  };
}

function extractBrainData(
  context: AgentContext
): unknown {
  const brain =
    context.previousResults?.[
      "brain"
    ]?.output;

  if (
    isRecord(brain) &&
    "brainData" in brain
  ) {
    return brain.brainData;
  }

  return brain ?? {};
}

function extractTaskMetadata(
  task: QueueTask | null
): UnknownRecord {
  return task?.metadata ?? {};
}

function extractScopedValue(
  metadata: UnknownRecord,
  keys: string[]
): string {
  for (const key of keys) {
    const value = toStringValue(metadata[key]);
    if (value) return value;
  }
  return "";
}

function buildDateScope(
  task: QueueTask | null,
  context: AgentContext
): UnknownRecord {
  const metadata = extractTaskMetadata(task);
  const roots: UnknownRecord[] = [
    metadata,
    isRecord(metadata.dateScope) ? metadata.dateScope : {},
    isRecord(context.input?.dateScope) ? context.input.dateScope : {},
  ];

  const read = (keys: string[]): string => {
    for (const root of roots) {
      const value = extractScopedValue(root, keys);
      if (value) return value;
    }
    return "";
  };

  const startDate = read(["startDate", "start_date", "from"]);
  const endDate = read(["endDate", "end_date", "to"]);
  const validationStartDate = read(["validationStartDate", "validation_start_date"]);
  const validationEndDate = read(["validationEndDate", "validation_end_date"]);
  const holdoutStartDate = read(["holdoutStartDate", "holdout_start_date"]);
  const holdoutEndDate = read(["holdoutEndDate", "holdout_end_date"]);
  const independentSliceStartDate = read([
    "independentSliceStartDate",
    "independent_slice_start_date",
    "independentStartDate",
  ]);
  const independentSliceEndDate = read([
    "independentSliceEndDate",
    "independent_slice_end_date",
    "independentEndDate",
  ]);

  const hasAny = [
    startDate,
    endDate,
    validationStartDate,
    validationEndDate,
    holdoutStartDate,
    holdoutEndDate,
    independentSliceStartDate,
    independentSliceEndDate,
  ].some(Boolean);

  return {
    selectionStatus: hasAny ? "PARTIAL" : "MISSING",
    selectionSource: hasAny ? "queue-task-metadata" : "none",
    startDate: startDate || null,
    endDate: endDate || null,
    validationStartDate: validationStartDate || null,
    validationEndDate: validationEndDate || null,
    holdoutStartDate: holdoutStartDate || null,
    holdoutEndDate: holdoutEndDate || null,
    independentSliceStartDate: independentSliceStartDate || null,
    independentSliceEndDate: independentSliceEndDate || null,
    exactDatesProvided: Boolean(startDate && endDate),
    independentSliceProvided: Boolean(
      independentSliceStartDate && independentSliceEndDate
    ),
    generatedByQueue: false,
  };
}

export async function runResearchQueueAgent(
  context: AgentContext
): Promise<
  Record<string, unknown>
> {
  const brainData =
    extractBrainData(
      context
    );

  const decision =
    extractResearchDecision(
      context
    );

  const roots =
    [
      brainData,
      context.previousResults?.brain?.output,
      context.input?.brain,
      context.input,
    ];

  const allTasks =
    collectQueueTasks(
      roots
    );

  const activeTasks =
    allTasks.filter(
      (task) =>
        task.status ===
          "queued" ||
        task.status ===
          "working"
    );

  const ordered =
    sortTasks(
      activeTasks,
      context
    );

  const recommendedTask =
    ordered[0] ??
    null;

  const nextResearchQuestion =
    toStringValue(
      decision.nextResearchQuestion ??
        context.input?.nextResearchQuestion
    );

  const action =
    toStringValue(
      decision.action
    );

  const decisionName =
    toStringValue(
      decision.decision
    );

  const decisionStrategyId =
    toStringValue(
      decision.strategyId
    );

  const strategyId =
    context.strategyId ||
    decisionStrategyId ||
    "STR-43839FA9C6";

  const feedback =
    buildQueueFeedback(
      decision
    );

  const normalizedFeedbackQuestion =
    feedback.nextResearchQuestion
      .trim()
      .toLowerCase();

  const normalizedRecommendedQuestion =
    recommendedTask?.question
      .trim()
      .toLowerCase() ??
    "";

  /*
   * The Research Decision's canonical nextResearchQuestion is
   * authoritative for the next research-loop hop.
   *
   * The historical Brain queue is still used as a source of
   * candidate tasks, but it must never override a fresh Decision
   * question. This is the exact invariant required by the E2E:
   *
   *   Decision.researchLoop.nextResearchQuestion
   *       ===
   *   Queue.selectedTask.question
   */
  const decisionDrivenTask =
    Boolean(normalizedFeedbackQuestion) &&
    normalizedFeedbackQuestion !==
      normalizedRecommendedQuestion
      ? {
          id: null,
          question:
            feedback.nextResearchQuestion,
          reason:
            feedback.reason,
          priority:
            feedback.priorityAdjustment + 10,
          targetNodeId:
            null,
          targetClaimId:
            null,
          status:
            "recommended",
          createdAt: "",
          updatedAt: "",
          metadata: {
            strategy_id:
              strategyId,
            source:
              toStringValue(
                (isRecord(decision.researchLoop)
                  ? decision.researchLoop.source
                  : undefined),
                "research-decision-memory"
              ),
            feedbackType:
              feedback.decision,
            decision:
              feedback.decision,
            action:
              feedback.action,
            nextResearchQuestion:
              feedback.nextResearchQuestion,
            researchMode:
              feedback.researchMode,
            priorityAdjustment:
              feedback.priorityAdjustment,
            feedbackReason:
              feedback.reason,
            generatedFromHistoricalMemory:
              true,
            avoidsBlindRepeat:
              true,
          },
        }
      : null;

  const syntheticTask =
    recommendedTask
      ? null
      : {
          id: null,

          question:
            feedback.nextResearchQuestion,

          reason:
            feedback.reason,

          priority:
            feedback.priorityAdjustment,

          targetNodeId:
            null,

          targetClaimId:
            null,

          status:
            "recommended",

          createdAt: "",

          updatedAt: "",

          metadata: {
            strategy_id:
              strategyId,

            source:
              "research-decision",

            feedbackType:
              feedback.decision,

            decision:
              feedback.decision,

            action:
              feedback.action,

            nextResearchQuestion:
              feedback.nextResearchQuestion,

            researchMode:
              feedback.researchMode,

            priorityAdjustment:
              feedback.priorityAdjustment,

            feedbackReason:
              feedback.reason,
          },
        };

  const selectedTask =
    decisionDrivenTask ??
    recommendedTask ??
    syntheticTask;

  const taskMetadata =
    extractTaskMetadata(selectedTask);

  const resolvedSymbol =
    toStringValue(
      taskMetadata.symbol,
      toStringValue(
        taskMetadata.symbol_id,
        context.symbol ?? ""
      )
    );

  const resolvedTimeframe =
    toStringValue(
      taskMetadata.timeframe,
      context.timeframe ?? "1d"
    );

  const resolvedMarket =
    toStringValue(
      taskMetadata.market
    );

  const dateScope =
    buildDateScope(
      selectedTask,
      context
    );

  const topTasks =
    ordered
      .slice(0, 10)
      .map(
        (
          task
        ) => ({
          ...task,

          relevanceScore:
            Number(
              queueRelevanceScore(
                task,
                context.strategyId,
                context.symbol,
                context.timeframe
              ).toFixed(4)
            ),
        })
      );

  return {
    agent:
      "research-queue",

    runId:
      context.runId,

    strategyId,

    symbol:
      resolvedSymbol ||
      null,

    timeframe:
      resolvedTimeframe,

    market:
      resolvedMarket ||
      null,

    dateScope,

    queue: {
      source:
        "MarketHQ Brain research queue",

      activeCount:
        activeTasks.length,

      visibleCount:
        allTasks.length,

      queuedCount:
        activeTasks.filter(
          (task) =>
            task.status ===
            "queued"
        ).length,

      workingCount:
        activeTasks.filter(
          (task) =>
            task.status ===
            "working"
        ).length,

      selectedTask,

      topTasks,
    },

    decisionContext: {
      decision:
        decisionName ||
        null,

      action:
        action ||
        null,

      nextResearchQuestion:
        nextResearchQuestion ||
        null,
    },

    feedback: {
      source:
        feedback.source,

      decision:
        feedback.decision,

      action:
        feedback.action,

      nextResearchQuestion:
        feedback.nextResearchQuestion,

      researchMode:
        feedback.researchMode,

      priorityAdjustment:
        feedback.priorityAdjustment,

      reason:
        feedback.reason,
    },

    queuePolicy: {
      ordering:
        "priority_desc_then_context_relevance_then_queue_id",

      activeStatuses: [
        "queued",
        "working",
      ],

      databaseWriteEnabled:
        false,

      queueMutation:
        false,

      executionEnabled:
        false,

      researchOnly:
        true,
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
      "READ_ONLY_RESEARCH_QUEUE",

    calculatedAt:
      new Date().toISOString(),
  };
}

export function registerResearchQueueAgent(): void {
  agentRunner.register(
    "research-queue",
    runResearchQueueAgent
  );
}



