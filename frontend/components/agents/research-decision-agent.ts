import type { AgentContext } from "./agent-types";
import { agentRunner } from "./agent-runner";

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function toOptionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toRatio(value: unknown): number {
  const n = toNumber(value);
  if (n > 1) return Math.max(0, Math.min(1, n / 100));
  return Math.max(0, Math.min(1, n));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function getPath(root: unknown, paths: string[][]): unknown {
  for (const path of paths) {
    let current: unknown = root;
    let ok = true;

    for (const key of path) {
      if (!isRecord(current) || !(key in current)) {
        ok = false;
        break;
      }
      current = current[key];
    }

    if (ok && current !== undefined && current !== null) return current;
  }

  return undefined;
}

function findByKeys(root: unknown, keys: string[]): unknown {
  const wanted = new Set(keys.map((key) => key.toLowerCase()));

  const walk = (value: unknown): unknown => {
    if (Array.isArray(value)) {
      for (const item of value) {
        const found = walk(item);
        if (found !== undefined) return found;
      }
      return undefined;
    }

    if (!isRecord(value)) return undefined;

    for (const [key, child] of Object.entries(value)) {
      if (wanted.has(key.toLowerCase()) && child !== undefined && child !== null) {
        return child;
      }
    }

    for (const child of Object.values(value)) {
      const found = walk(child);
      if (found !== undefined) return found;
    }

    return undefined;
  };

  return walk(root);
}

function firstDefined(root: unknown, keys: string[], fallback: string): string {
  if (!isRecord(root)) return fallback;

  for (const key of keys) {
    const value = root[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }

  return fallback;
}

function firstNumber(root: unknown, keys: string[], fallback = 0): number {
  return toNumber(findByKeys(root, keys), fallback);
}

function firstOptionalNumber(root: unknown, keys: string[]): number | null {
  return toOptionalNumber(findByKeys(root, keys));
}

function firstOptionalString(root: unknown, keys: string[]): string | null {
  const found = findByKeys(root, keys);
  return typeof found === "string" && found.trim() ? found.trim() : null;
}

function normalizeObject(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

function normalizeReview(source: unknown): UnknownRecord {
  const root = normalizeObject(source);
  const review = getPath(root, [
    ["strategyReview"],
    ["strategy_review"],
    ["review"],
    ["strategyReviewData"],
  ]);
  return isRecord(review) ? review : root;
}

function normalizeValidation(source: unknown): UnknownRecord {
  const root = normalizeObject(source);
  const ranking = getPath(root, [
    ["validation", "ranking"],
    ["ranking"],
    ["pipelineData", "strategy", "ranking"],
  ]);
  return isRecord(ranking) ? ranking : root;
}

function normalizeEvidence(source: unknown): UnknownRecord {
  const root = normalizeObject(source);
  const evidence = getPath(root, [
    ["evidenceData", "consolidation", "summary"],
    ["consolidation", "summary"],
    ["consolidationData", "summary"],
    ["evidenceData"],
    ["consolidation"],
    ["consolidationData"],
    ["evidence"],
  ]);
  return isRecord(evidence) ? evidence : root;
}

function getAgentOutput(
  previous: AgentContext["previousResults"],
  input: AgentContext["input"],
  agentId: keyof NonNullable<AgentContext["previousResults"]>,
): UnknownRecord {
  const previousOutput = previous?.[agentId]?.output;
  if (isRecord(previousOutput)) return previousOutput;

  const directInput = input?.[agentId];
  if (isRecord(directInput)) return directInput;

  return {};
}

function getResultIngestionOutput(
  previous: AgentContext["previousResults"],
  input: AgentContext["input"],
): UnknownRecord {
  const previousOutput = previous?.["result-ingestion"]?.output;
  if (isRecord(previousOutput)) return previousOutput;

  const directCandidates = [
    input?.["result-ingestion"],
    input?.resultIngestion,
  ];

  for (const candidate of directCandidates) {
    if (isRecord(candidate)) return candidate;
  }

  return {};
}

function extractNormalizedMetrics(resultIngestionOutput: UnknownRecord): UnknownRecord {
  const candidate = getPath(resultIngestionOutput, [
    ["result", "normalizedMetrics"],
    ["normalizedMetrics"],
    ["result", "normalizedResult", "normalizedMetrics"],
    ["normalizedResult", "normalizedMetrics"],
  ]);

  return isRecord(candidate) ? candidate : {};
}

function buildResultIngestionWfo(resultIngestionOutput: UnknownRecord): UnknownRecord {
  const metrics = extractNormalizedMetrics(resultIngestionOutput);

  const totalFolds = firstOptionalNumber(metrics, ["wfoTotalFolds", "totalFolds", "total_folds"]);
  const positiveFolds = firstOptionalNumber(metrics, ["wfoPositiveFolds", "positiveFolds", "positive_folds"]);
  const negativeFolds = firstOptionalNumber(metrics, ["wfoNegativeFolds", "negativeFolds", "negative_folds"]);
  const inconclusiveFolds = firstOptionalNumber(metrics, [
    "wfoInconclusiveFolds",
    "inconclusiveFolds",
    "inconclusive_folds",
  ]);
  const resolvedFolds = firstOptionalNumber(metrics, ["wfoResolvedFolds", "resolvedFolds", "resolved_folds"]);

  const positiveRatioRaw = firstOptionalNumber(metrics, ["wfoPositiveRatio", "positiveRatio", "positive_ratio"]);
  const negativeRatioRaw = firstOptionalNumber(metrics, ["wfoNegativeRatio", "negativeRatio", "negative_ratio"]);
  const resolvedRatioRaw = firstOptionalNumber(metrics, ["wfoResolvedRatio", "resolvedRatio", "resolved_ratio"]);
  const inconclusiveShareRaw = firstOptionalNumber(metrics, [
    "wfoInconclusiveShare",
    "inconclusiveShare",
    "inconclusive_share",
  ]);
  const evidenceQuality =
    firstOptionalString(metrics, ["wfoEvidenceQuality", "evidenceQuality", "evidence_quality"])?.toUpperCase() ??
    "UNKNOWN";

  const derivedInconclusiveShare =
    inconclusiveShareRaw !== null
      ? clamp01(inconclusiveShareRaw)
      : totalFolds !== null && totalFolds > 0 && inconclusiveFolds !== null
        ? clamp01(inconclusiveFolds / totalFolds)
        : null;

  const derivedPositiveRatio =
    positiveRatioRaw !== null
      ? clamp01(positiveRatioRaw)
      : resolvedFolds !== null && resolvedFolds > 0 && positiveFolds !== null
        ? clamp01(positiveFolds / resolvedFolds)
        : null;

  const derivedNegativeRatio =
    negativeRatioRaw !== null
      ? clamp01(negativeRatioRaw)
      : resolvedFolds !== null && resolvedFolds > 0 && negativeFolds !== null
        ? clamp01(negativeFolds / resolvedFolds)
        : null;

  const derivedResolvedRatio =
    resolvedRatioRaw !== null
      ? clamp01(resolvedRatioRaw)
      : totalFolds !== null && totalFolds > 0 && resolvedFolds !== null
        ? clamp01(resolvedFolds / totalFolds)
        : null;

  const available =
    totalFolds !== null ||
    positiveFolds !== null ||
    negativeFolds !== null ||
    inconclusiveFolds !== null ||
    positiveRatioRaw !== null ||
    negativeRatioRaw !== null ||
    resolvedRatioRaw !== null ||
    inconclusiveShareRaw !== null ||
    evidenceQuality !== "UNKNOWN";

  return {
    available,
    normalizedMetrics: metrics,
    wfo: {
      totalFolds,
      positiveFolds,
      negativeFolds,
      inconclusiveFolds,
      resolvedFolds,
      positiveRatio: derivedPositiveRatio,
      negativeRatio: derivedNegativeRatio,
      resolvedRatio: derivedResolvedRatio,
      inconclusiveShare: derivedInconclusiveShare,
      evidenceQuality,
    },
  };
}

function buildRunnerEvidence(
  runnerOutput: UnknownRecord,
  validationOutput: UnknownRecord,
): UnknownRecord {
  const root = normalizeObject(runnerOutput);
  const validationRoot = normalizeObject(validationOutput);

  const experimentStatus =
    firstOptionalString(root, ["status"])?.toUpperCase() ??
    firstOptionalString(getPath(root, [["experiment"]]), ["status"])?.toUpperCase() ??
    "UNKNOWN";

  const researchValidation = normalizeObject(
    getPath(root, [
      ["researchValidation"],
      ["experiment", "researchValidation"],
    ]) ??
      findByKeys(root, ["researchValidation"]) ??
      getPath(validationRoot, [
        ["researchValidation"],
        ["runnerValidation"],
      ]) ??
      findByKeys(validationRoot, ["researchValidation", "runnerValidation"]),
  );

  const wfo = normalizeObject(
    getPath(researchValidation, [["wfo"]]) ??
      findByKeys(researchValidation, ["wfo", "walkForward", "walk_forward"]) ??
      getPath(root, [["walkForwardOOS"]]) ??
      findByKeys(root, ["walkForwardOOS", "walk_forward_oos"]),
  );

  const overfittingReview = normalizeObject(
    getPath(researchValidation, [["overfittingReview"]]) ??
      getPath(root, [["overfittingReview"]]) ??
      findByKeys(root, ["overfittingReview", "overfitting_review"]),
  );

  const rawResearchValidationStatus =
    firstOptionalString(researchValidation, ["status"])?.toUpperCase() ?? "UNKNOWN";

  const effectiveStatus =
    experimentStatus === "BLOCKED"
      ? "BLOCKED"
      : rawResearchValidationStatus;

  return {
    experimentStatus,
    researchValidation,
    wfo,
    overfittingReview,
    researchValidationStatus: effectiveStatus,
    rawResearchValidationStatus,
  };
}

function buildPreviousAgentState(
  previous: AgentContext["previousResults"],
): UnknownRecord {
  if (!previous) return {};

  return Object.fromEntries(
    Object.entries(previous).map(([agentId, result]) => [
      agentId,
      {
        success: Boolean(result?.success),
        status: result?.status ?? "UNKNOWN",
        runId: result?.runId ?? null,
      },
    ]),
  );
}

export async function runResearchDecisionAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  const previous = context.previousResults ?? {};
  const input = context.input ?? {};

  const validationOutput = getAgentOutput(previous, input, "validation");
  const evidenceOutput = getAgentOutput(previous, input, "evidence");
  const learningOutput = getAgentOutput(previous, input, "learning");
  const resultIngestionOutput = getResultIngestionOutput(previous, input);
  const runnerOutput = getAgentOutput(previous, input, "experiment-runner");

  const validation = normalizeValidation(validationOutput);
  const evidence = normalizeEvidence(evidenceOutput);
  const review = normalizeReview(
    getPath(evidenceOutput, [["strategyReview"], ["strategy_review"]]) ??
      findByKeys(evidenceOutput, ["strategy_review", "strategyReview"]),
  );

  const resultIngestionEvidence = buildResultIngestionWfo(resultIngestionOutput);
  const runnerEvidence = buildRunnerEvidence(
    runnerOutput,
    validationOutput,
  );
  const ingestedWfo = normalizeObject(resultIngestionEvidence.wfo);
  const runnerWfo = normalizeObject(runnerEvidence.wfo);

  const hasCanonicalIngestedWfo =
    resultIngestionEvidence.available &&
    ingestedWfo.totalFolds !== null &&
    Number(ingestedWfo.totalFolds) > 0;

  const selectedWfo = hasCanonicalIngestedWfo ? ingestedWfo : runnerWfo;
  const selectedWfoSource = hasCanonicalIngestedWfo
    ? "result-ingestion"
    : "experiment-runner";

  const reviewVerdict = String(
    firstDefined(review, ["verdict", "review_verdict"], "INSUFFICIENT"),
  )
    .trim()
    .toUpperCase();

  const reviewScore = toRatio(
    firstNumber(review, ["score", "review_score", "strategy_review_score"]),
  );

  const crossSymbol = toRatio(
    firstNumber(validation, [
      "cross_symbol_positive_ratio",
      "cross_symbol_ratio",
      "crossSymbolPositiveRatio",
    ]),
  );

  const costRobustness = toRatio(
    firstNumber(validation, [
      "cost_survival",
      "cost_survival_ratio",
      "cost_robustness",
      "cost_robustness_ratio",
    ]),
  );

  const parameterStability = toRatio(
    firstNumber(validation, ["parameter_stability", "parameter_stability_ratio"]),
  );

  const regimeStability = toRatio(
    firstNumber(validation, ["regime_stability", "regime_stability_ratio"]),
  );

  const holdoutPositive = firstNumber(evidence, [
    "holdout_positive",
    "holdout_positive_folds",
    "positive_holdout_folds",
  ]);
  const holdoutTotal = firstNumber(evidence, [
    "holdout_total",
    "holdout_total_folds",
    "total_holdout_folds",
  ]);
  const holdoutRatio = holdoutTotal > 0 ? holdoutPositive / holdoutTotal : 0;

  const positiveFullRuns = firstNumber(evidence, ["positive_full_runs", "positive_runs"]);
  const symbolsTested = firstNumber(evidence, [
    "symbol_runs_combined",
    "symbols_tested",
    "symbols_across_records",
  ]);
  const fullRunRatio = symbolsTested > 0 ? positiveFullRuns / symbolsTested : 0;

  const wfoEvidenceQuality = String(selectedWfo.evidenceQuality ?? "UNKNOWN").toUpperCase();
  const wfoPositiveRatio = firstOptionalNumber(selectedWfo, ["positiveRatio", "positive_ratio"]);
  const wfoNegativeRatio = firstOptionalNumber(selectedWfo, ["negativeRatio", "negative_ratio"]);
  const wfoResolvedRatio = firstOptionalNumber(selectedWfo, ["resolvedRatio", "resolved_ratio"]);
  const wfoInconclusiveShare = firstOptionalNumber(selectedWfo, [
    "inconclusiveShare",
    "inconclusive_share",
  ]);

  const runnerResearchValidationStatus = String(
    runnerEvidence.researchValidationStatus ?? "UNKNOWN",
  ).toUpperCase();

  const runnerOverfittingReview = normalizeObject(runnerEvidence.overfittingReview);
  const runnerOverfittingStatus = String(
    runnerOverfittingReview.status ?? "UNKNOWN",
  ).toUpperCase();

  const runnerOverfittingRiskScore = firstOptionalNumber(runnerOverfittingReview, [
    "riskScore",
    "risk_score",
  ]);

  const normalizedMetrics = extractNormalizedMetrics(resultIngestionOutput);
  const runnerRobustnessSummary = normalizeObject(
    getPath(runnerOutput, [["robustnessSummary"]]) ??
      getPath(runnerOutput, [["researchExecution", "result", "robustnessSummary"]]) ??
      findByKeys(runnerOutput, ["robustnessSummary"]),
  );
  const runnerRobustnessScore =
    firstOptionalNumber(normalizedMetrics, ["robustnessScore"]) ??
    firstOptionalNumber(runnerRobustnessSummary, ["robustnessScore"]);
  const monteCarloPositiveProbability =
    firstOptionalNumber(normalizedMetrics, ["monteCarloPositiveProbability"]) ??
    firstOptionalNumber(runnerRobustnessSummary, ["monteCarloPositiveProbability"]);
  const stressPositiveScenarioRatio =
    firstOptionalNumber(normalizedMetrics, ["stressPositiveScenarioRatio"]) ??
    firstOptionalNumber(runnerRobustnessSummary, ["stressPositiveScenarioRatio"]);
  const stressWorstMetric =
    firstOptionalNumber(normalizedMetrics, ["stressWorstMetric"]) ??
    firstOptionalNumber(runnerRobustnessSummary, ["stressWorstMetric"]);
  const runnerRobustnessAvailable =
    runnerRobustnessScore !== null ||
    monteCarloPositiveProbability !== null ||
    stressPositiveScenarioRatio !== null ||
    stressWorstMetric !== null;
  const robustnessEvidenceStrong =
    runnerRobustnessScore !== null &&
    runnerRobustnessScore >= 0.50 &&
    (monteCarloPositiveProbability === null || monteCarloPositiveProbability >= 0.50) &&
    (stressPositiveScenarioRatio === null || stressPositiveScenarioRatio >= 0.50);
  const robustnessEvidenceNegative =
    runnerRobustnessScore !== null &&
    runnerRobustnessScore < 0.50 ||
    monteCarloPositiveProbability !== null &&
    monteCarloPositiveProbability < 0.50 ||
    stressPositiveScenarioRatio !== null &&
    stressPositiveScenarioRatio < 0.50;

  const robustnessComponent =
    (crossSymbol + costRobustness + parameterStability + regimeStability) / 4;

  const compositeScore =
    0.35 * reviewScore +
    0.30 * robustnessComponent +
    0.20 * holdoutRatio +
    0.15 * fullRunRatio;

  const confidence = Math.min(
    1,
    0.50 + 0.25 * reviewScore + 0.25 * robustnessComponent,
  );

  const evidenceCompletenessPenalty =
    wfoEvidenceQuality === "INSUFFICIENT"
      ? 0.10
      : wfoEvidenceQuality === "UNKNOWN"
        ? 0.05
        : 0;

  const runnerAdjustedConfidence = Math.max(
    0,
    confidence - evidenceCompletenessPenalty,
  );

  const wfoStrongNegative =
    wfoNegativeRatio !== null &&
    wfoResolvedRatio !== null &&
    wfoResolvedRatio > 0 &&
    wfoNegativeRatio >= 0.60;

  const wfoResolvedSupportive =
    wfoEvidenceQuality === "SUFFICIENT" &&
    wfoResolvedRatio !== null &&
    wfoResolvedRatio > 0 &&
    wfoPositiveRatio !== null &&
    wfoPositiveRatio >= 0.60 &&
    (wfoNegativeRatio ?? 1) < 0.40;

  const robustnessFailureCount = [
    crossSymbol < 0.60,
    costRobustness < 0.50,
    parameterStability < 0.50,
    regimeStability < 0.50,
  ].filter(Boolean).length;

  let decision: string;

  if (reviewVerdict === "CONTRADICTORY") {
    decision = "REJECT_RESEARCH_CANDIDATE";
  } else if (wfoStrongNegative) {
    decision = "REJECT_RESEARCH_CANDIDATE";
  } else if (robustnessEvidenceNegative) {
    decision = compositeScore >= 0.45
      ? "MIXED_NEEDS_MORE_RESEARCH"
      : "WEAK_RESEARCH_CANDIDATE";
  } else if (
    compositeScore >= 0.72 &&
    reviewVerdict === "SUPPORTIVE" &&
    runnerResearchValidationStatus === "PASS" &&
    runnerOverfittingStatus !== "HIGH" &&
    wfoResolvedSupportive &&
    robustnessFailureCount === 0 &&
    holdoutRatio >= 0.60
  ) {
    decision = "PROMISING_RESEARCH_CANDIDATE";
  } else if (
    compositeScore >= 0.45 ||
    reviewVerdict === "SUPPORTIVE" ||
    wfoResolvedSupportive
  ) {
    decision = "MIXED_NEEDS_MORE_RESEARCH";
  } else if (compositeScore >= 0.25) {
    decision = "WEAK_RESEARCH_CANDIDATE";
  } else {
    decision = "REJECT_RESEARCH_CANDIDATE";
  }

  if (
    decision === "PROMISING_RESEARCH_CANDIDATE" &&
    wfoEvidenceQuality !== "SUFFICIENT"
  ) {
    decision = "MIXED_NEEDS_MORE_RESEARCH";
  }

  if (
    decision === "PROMISING_RESEARCH_CANDIDATE" &&
    (runnerResearchValidationStatus !== "PASS" || runnerOverfittingStatus === "HIGH")
  ) {
    decision = "MIXED_NEEDS_MORE_RESEARCH";
  }

  if (
    decision === "PROMISING_RESEARCH_CANDIDATE" &&
    (costRobustness < 0.50 ||
      parameterStability < 0.50 ||
      regimeStability < 0.50 ||
      crossSymbol < 0.60 ||
      holdoutRatio < 0.55)
  ) {
    decision = "MIXED_NEEDS_MORE_RESEARCH";
  }

  const actionByDecision: Record<string, string> = {
    PROMISING_RESEARCH_CANDIDATE: "PAPER_RESEARCH_CONTINUE",
    MIXED_NEEDS_MORE_RESEARCH: "RESEARCH_MORE_INDEPENDENT_EVIDENCE",
    WEAK_RESEARCH_CANDIDATE: "RESEARCH_MORE_OR_DEPRIORITIZE",
    REJECT_RESEARCH_CANDIDATE: "DEPRIORITIZE_RESEARCH",
  };

  const reasons: string[] = [];

  if (reviewVerdict === "SUPPORTIVE") {
    reasons.push("Strategy-level independent evidence is supportive.");
  } else if (reviewVerdict === "PARTIALLY_SUPPORTIVE") {
    reasons.push("Independent strategy evidence is only partially supportive.");
  } else if (reviewVerdict === "CONTRADICTORY") {
    reasons.push("Independent evidence contains a contradiction.");
  } else {
    reasons.push("Independent strategy evidence remains insufficient.");
  }

  if (crossSymbol < 0.60) {
    reasons.push(`Cross-symbol success ratio is only ${(crossSymbol * 100).toFixed(2)}%.`);
  }
  if (costRobustness < 0.50) {
    reasons.push(`Cost robustness is only ${(costRobustness * 100).toFixed(2)}%.`);
  }
  if (parameterStability < 0.50) {
    reasons.push(`Parameter stability is only ${(parameterStability * 100).toFixed(2)}%.`);
  }
  if (regimeStability < 0.50) {
    reasons.push(`Regime stability is only ${(regimeStability * 100).toFixed(2)}%.`);
  }
  if (holdoutRatio < 0.55) {
    reasons.push(`Independent holdout positive ratio is only ${(holdoutRatio * 100).toFixed(2)}%.`);
  }

  if (runnerRobustnessAvailable) {
    if (runnerRobustnessScore !== null) {
      reasons.push(`Runner robustness score is ${(runnerRobustnessScore * 100).toFixed(2)}%.`);
    }
    if (monteCarloPositiveProbability !== null) {
      reasons.push(`Monte Carlo positive probability is ${(monteCarloPositiveProbability * 100).toFixed(2)}%.`);
    }
    if (stressPositiveScenarioRatio !== null) {
      reasons.push(`Stress positive-scenario ratio is ${(stressPositiveScenarioRatio * 100).toFixed(2)}%.`);
    }
  }

  if (wfoEvidenceQuality === "INSUFFICIENT") {
    const inconclusiveText =
      wfoInconclusiveShare !== null
        ? ` (${(wfoInconclusiveShare * 100).toFixed(1)}% of WFO folds are inconclusive).`
        : ".";
    reasons.push(
      `WFO evidence quality is insufficient${inconclusiveText} Resolved WFO evidence is required before treating WFO as supportive or negative evidence.`,
    );
  } else if (wfoNegativeRatio !== null && wfoNegativeRatio > 0.50) {
    reasons.push(
      `Resolved WFO negative ratio is ${(wfoNegativeRatio * 100).toFixed(2)}%.`,
    );
  }

  if (wfoResolvedRatio !== null && wfoResolvedRatio === 0 && wfoEvidenceQuality !== "INSUFFICIENT") {
    reasons.push("No resolved WFO folds are available for decision support.");
  }

  if (runnerOverfittingStatus === "HIGH") {
    reasons.push(
      "Runner anti-overfitting review is HIGH; the candidate is capped below PROMISING until robustness evidence improves.",
    );
  }

  if (runnerResearchValidationStatus === "FAIL") {
    reasons.push(
      "Experiment Runner research validation is FAIL; the runner completed with one or more failed research gates.",
    );
  } else if (runnerResearchValidationStatus === "BLOCKED") {
    reasons.push(
      "Experiment Runner is BLOCKED; runner-specific validation is unavailable and is not treated as negative evidence.",
    );
  }

  if (
    wfoEvidenceQuality !== "UNKNOWN" &&
    wfoPositiveRatio !== null &&
    wfoNegativeRatio !== null
  ) {
    reasons.push(
      `Runner WFO classification: positive ${(wfoPositiveRatio * 100).toFixed(1)}%, negative ${(wfoNegativeRatio * 100).toFixed(1)}%. Inconclusive folds remain separate from negative evidence.`,
    );
  }

  const decisionBasis =
    decision === "PROMISING_RESEARCH_CANDIDATE"
      ? "ALL_CORE_GATES_PASS"
      : decision === "REJECT_RESEARCH_CANDIDATE"
        ? reviewVerdict === "CONTRADICTORY"
          ? "CONTRADICTORY_EVIDENCE"
          : wfoStrongNegative
            ? "STRONG_NEGATIVE_WFO"
            : "LOW_COMPOSITE_SCORE"
        : wfoEvidenceQuality !== "SUFFICIENT"
          ? "EVIDENCE_INCOMPLETE"
          : runnerResearchValidationStatus === "FAIL"
            ? "RUNNER_VALIDATION_FAILED"
            : runnerResearchValidationStatus === "BLOCKED"
              ? "RUNNER_VALIDATION_UNAVAILABLE"
              : runnerOverfittingStatus === "HIGH"
              ? "OVERFITTING_RISK_HIGH"
              : robustnessEvidenceNegative
                ? "ROBUSTNESS_V1_NEGATIVE"
                : robustnessFailureCount >= 2
                  ? "ROBUSTNESS_MIXED"
                  : "MIXED_EVIDENCE";

  return {
    agent: "research-decision",
    runId: context.runId,
    strategyId: context.strategyId ?? "STR-43839FA9C6",
    strategyName:
      firstDefined(input.strategy, ["strategyName", "strategy_name", "name"], "") ||
      firstDefined(evidenceOutput, ["strategyName", "strategy_name", "name"], ""),
    decision: {
      decision,
      action: actionByDecision[decision],
      decisionBasis,
      compositeScore: Number(compositeScore.toFixed(4)),
      decisionConfidence: Number(runnerAdjustedConfidence.toFixed(4)),
      strategyReviewVerdict: reviewVerdict,
      strategyReviewScore: Number(reviewScore.toFixed(4)),
      crossSymbolRatio: Number(crossSymbol.toFixed(4)),
      costRobustness: Number(costRobustness.toFixed(4)),
      parameterStability: Number(parameterStability.toFixed(4)),
      regimeStability: Number(regimeStability.toFixed(4)),
      independentHoldoutRatio: Number(holdoutRatio.toFixed(4)),
      independentFullRunRatio: Number(Math.max(0, Math.min(1, fullRunRatio)).toFixed(4)),
      runnerResearchValidationStatus,
      runnerOverfittingStatus,
      runnerOverfittingRiskScore:
        runnerOverfittingRiskScore === null
          ? null
          : Number(runnerOverfittingRiskScore.toFixed(4)),
      robustnessScore:
        runnerRobustnessScore === null
          ? null
          : Number(runnerRobustnessScore.toFixed(4)),
      monteCarloPositiveProbability:
        monteCarloPositiveProbability === null
          ? null
          : Number(monteCarloPositiveProbability.toFixed(4)),
      stressPositiveScenarioRatio:
        stressPositiveScenarioRatio === null
          ? null
          : Number(stressPositiveScenarioRatio.toFixed(4)),
      stressWorstMetric,
      robustnessEvidenceStrong,
      robustnessEvidenceNegative,
      wfoEvidenceQuality,
      wfoPositiveRatio:
        wfoPositiveRatio === null ? null : Number(wfoPositiveRatio.toFixed(4)),
      wfoNegativeRatio:
        wfoNegativeRatio === null ? null : Number(wfoNegativeRatio.toFixed(4)),
      wfoResolvedRatio:
        wfoResolvedRatio === null ? null : Number(wfoResolvedRatio.toFixed(4)),
      wfoInconclusiveShare:
        wfoInconclusiveShare === null ? null : Number(wfoInconclusiveShare.toFixed(4)),
      reasons,
      nextResearchQuestion:
        wfoEvidenceQuality === "INSUFFICIENT"
          ? "Can a fresh independent historical slice produce resolved WFO outcomes while preserving the same rule definition, cost model and regime robustness?"
          : "Can a fresh independent historical slice reproduce the strategy edge while preserving the same rule definition, cost model and regime robustness?",
    },
      researchLoop: {
        source: "research-decision",

        memoryCount: 0,

        nextResearchQuestion:
          wfoEvidenceQuality === "INSUFFICIENT"
            ? "Can a fresh independent historical slice produce resolved WFO outcomes while preserving the same rule definition, cost model and regime robustness?"
            : "Can a fresh independent historical slice reproduce the strategy edge while preserving the same rule definition, cost model and regime robustness?",
      },
    sourceInputs: {
      validation: validationOutput,
      evidence: evidenceOutput,
      learning: learningOutput,
      resultIngestion: resultIngestionOutput,
      experimentRunner: runnerOutput,
      selectedWfo: {
        ...selectedWfo,
        source: selectedWfoSource,
      },
      runnerResearchValidation: runnerEvidence.researchValidation,
      runnerOverfittingReview,
      review,
      previousAgentState: buildPreviousAgentState(previous),
    },
    evidenceQuality: {
      wfo: wfoEvidenceQuality,
      wfoSource: selectedWfoSource,
      runnerResearchValidation: runnerResearchValidationStatus,
      overfittingReview: runnerOverfittingStatus,
      confidencePenalty: evidenceCompletenessPenalty,
      confidenceBeforeRunnerAdjustment: Number(confidence.toFixed(4)),
      confidenceAfterRunnerAdjustment: Number(runnerAdjustedConfidence.toFixed(4)),
    },
    decisionMatrix: {
      promisingRequires: [
        "SUPPORTIVE_REVIEW",
        "RUNNER_VALIDATION_PASS",
        "WFO_SUFFICIENT_AND_SUPPORTIVE",
        "HOLDOUT_>=_60_PERCENT",
        "CROSS_SYMBOL_>=_60_PERCENT",
        "COST_ROBUSTNESS_>=_50_PERCENT",
        "PARAMETER_STABILITY_>=_50_PERCENT",
        "REGIME_STABILITY_>=_50_PERCENT",
        "NO_HIGH_OVERFITTING_RISK",
      ],
      currentDecisionBasis: decisionBasis,
      robustnessFailureCount,
      wfoStrongNegative,
      wfoResolvedSupportive,
    },
    safety: {
      researchOnly: true,
      executionEnabled: false,
      databaseWriteEnabled: false,
      brokerExecutionEnabled: false,
    },
    mode: "READ_ONLY_RESEARCH_DECISION",
    calculatedAt: new Date().toISOString(),
  };
}

export function registerResearchDecisionAgent(): void {
  agentRunner.register("research-decision", runResearchDecisionAgent);
}


