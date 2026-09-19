import type {
  AgentContext,
  AgentId,
  AgentResult,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

import {
  getAgentDependencies,
  getAgentPipelineOrder,
} from "./agent-registry";

import {
  registerDefaultAgents,
} from "./register-agents";

export interface OrchestratorResult {
  success: boolean;

  status:
    | "COMPLETED"
    | "PARTIAL"
    | "FAILED";

  runId: string;

  results: AgentResult[];

  resultsByAgent: Partial<
    Record<AgentId, AgentResult>
  >;

  executionOrder: AgentId[];

  completedAgents: AgentId[];

  failedAgents: AgentId[];

  skippedAgents: AgentId[];

  startedAt: string;

  completedAt: string;

  durationMs: number;
}

function createRunId(): string {
  return (
    `run-${Date.now()}-` +
    Math.random()
      .toString(36)
      .slice(2, 10)
  );
}

function dependencySatisfied(
  dependency: AgentId,
  resultsByAgent: Partial<
    Record<AgentId, AgentResult>
  >
): boolean {
  const result =
    resultsByAgent[dependency];

  return Boolean(
    result &&
      result.success === true &&
      result.status === "COMPLETED"
  );
}

function addUniqueAgent(
  list: AgentId[],
  agentId: AgentId
): void {
  if (!list.includes(agentId)) {
    list.push(agentId);
  }
}

function removeAgent(
  list: AgentId[],
  agentId: AgentId
): void {
  const index = list.indexOf(agentId);

  if (index >= 0) {
    list.splice(index, 1);
  }
}

export async function runOrchestrator(
  options: {
    runId?: string;
    strategyId?: string;
    symbol?: string;
    timeframe?: string;
    input?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  } = {}
): Promise<OrchestratorResult> {
  registerDefaultAgents();

  const startedTimestamp =
    Date.now();

  const startedAt =
    new Date().toISOString();

  const runId =
    options.runId ??
    createRunId();

  /*
   * ============================================================
   * RESEARCH CYCLE
   * ============================================================
   *
   * Pipeline registry tek gerçek execution kaynağıdır.
   *
   * Beklenen cycle:
   *
   * Market Data
   *      ↓
   * Strategy
   *      ↓
   * Backtest
   *      ↓
   * Validation
   *      ↓
   * Evidence
   *      ↓
   * Brain
   *      ↓
   * Learning
   *      ↓
   * Research Decision
   *      ↓
   * Research Queue
   *      ↓
   * Date Resolver
   *      ↓
   * Experiment Generator
   *      ↓
   * Experiment Runner
   *      ↓
   * Result Ingestion
   *      ↓
   * Learning
   *      ↓
   * Research Decision
   *
   * Learning ve Research Decision'ın ikinci kez çalışması
   * bilinçlidir.
   *
   * Result Ingestion yalnızca bir kez çalışır ve
   * Experiment Runner'ın güncel sonucundan sonra çalışır.
   */

  const pipeline =
    getAgentPipelineOrder();

  const results: AgentResult[] = [];

  /*
   * resultsByAgent:
   *
   * Her agent'ın en son sonucunu tutar.
   *
   * Learning ve Research Decision iki kez çalıştığı için
   * ikinci çalıştırma birinci sonucu overwrite eder.
   *
   * Tam execution history ise `results` array'inde korunur.
   */
  const resultsByAgent: Partial<
    Record<AgentId, AgentResult>
  > = {};

  const executionOrder: AgentId[] = [];

  const completedAgents: AgentId[] = [];

  const failedAgents: AgentId[] = [];

  const skippedAgents: AgentId[] = [];

  async function executeAgent(
    agentId: AgentId
  ): Promise<AgentResult> {
    executionOrder.push(agentId);

    const dependencies =
      getAgentDependencies(agentId);

    /*
     * Dependency kontrolü:
     *
     * Bir agent'ın dependency'si aynı cycle içerisinde
     * COMPLETED değilse agent çalıştırılmaz.
     *
     * Bu durumda ERROR result oluşturulur ve pipeline
     * tamamen durdurulmaz.
     */
    const missingDependencies =
      dependencies.filter(
        (dependency) =>
          !dependencySatisfied(
            dependency,
            resultsByAgent
          )
      );

    if (
      missingDependencies.length > 0
    ) {
      const now =
        new Date().toISOString();

      const skippedResult: AgentResult = {
        success: false,

        agentId,

        runId,

        status: "ERROR",

        error:
          `Agent skipped because required dependencies were not completed: ${missingDependencies.join(
            ", "
          )}`,

        startedAt: now,

        completedAt: now,

        durationMs: 0,
      };

      results.push(
        skippedResult
      );

      resultsByAgent[agentId] =
        skippedResult;

      addUniqueAgent(
        skippedAgents,
        agentId
      );

      removeAgent(
        completedAgents,
        agentId
      );

      addUniqueAgent(
        failedAgents,
        agentId
      );

      return skippedResult;
    }

    /*
     * Aynı input object'i cycle boyunca paylaşılır.
     *
     * Özellikle:
     *
     * input.priorExperimentResult
     *
     * varsa ilk Learning / Research Decision turu
     * önceki research cycle sonucunu kullanabilir.
     *
     * Eğer yoksa agent kendi güvenli NOT_AVAILABLE
     * davranışını uygulamalıdır.
     */
    const context: AgentContext = {
      runId,

      strategyId:
        options.strategyId,

      symbol:
        options.symbol,

      timeframe:
        options.timeframe,

      input:
        options.input,

      /*
       * Agent'lar burada pipeline içinde kendilerinden önce
       * çalışmış agentların EN SON sonuçlarına erişir.
       *
       * Learning ve Research Decision ikinci kez çalıştığında
       * Result Ingestion artık mevcut olur.
       */
      previousResults:
        resultsByAgent,

      metadata:
        options.metadata,
    };

    let result: AgentResult;

    try {
      result =
        await agentRunner.run(
          agentId,
          context
        );
    } catch (error) {
      const now =
        new Date().toISOString();

      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error);

      result = {
        success: false,

        agentId,

        runId,

        status: "ERROR",

        error:
          `Agent execution threw an exception: ${errorMessage}`,

        startedAt: now,

        completedAt: now,

        durationMs: 0,
      };
    }

    results.push(result);

    resultsByAgent[agentId] =
      result;

    if (
      result.success === true &&
      result.status === "COMPLETED"
    ) {
      addUniqueAgent(
        completedAgents,
        agentId
      );

      removeAgent(
        failedAgents,
        agentId
      );

      removeAgent(
        skippedAgents,
        agentId
      );
    } else {
      addUniqueAgent(
        failedAgents,
        agentId
      );

      removeAgent(
        completedAgents,
        agentId
      );
    }

    return result;
  }

  /*
   * ============================================================
   * SINGLE PIPELINE EXECUTION
   * ============================================================
   *
   * Kritik mimari kural:
   *
   * Orchestrator artık kendi içinde ayrı bir "seed phase",
   * "feedback phase" veya ikinci Result Ingestion phase
   * oluşturmaz.
   *
   * Tek kaynak:
   *
   * getAgentPipelineOrder()
   *
   * Registry'deki Learning ve Research Decision tekrarları
   * bilinçli olarak burada bir kez yürütülür.
   */

  for (const agentId of pipeline) {
    const result =
      await executeAgent(agentId);

    /*
     * Bir agent başarısız olsa bile pipeline tamamen
     * kesilmez.
     *
     * Sonraki agent dependency kontrolünden geçemezse
     * doğal olarak ERROR / skipped olarak kaydedilir.
     *
     * Böylece final sonuç hangi aşamanın kırıldığını
     * eksiksiz taşıyabilir.
     */
    if (
      result.success !== true ||
      result.status !== "COMPLETED"
    ) {
      continue;
    }
  }

  const completedAt =
    new Date().toISOString();

  const success =
    failedAgents.length === 0 &&
    skippedAgents.length === 0;

  let status:
    | "COMPLETED"
    | "PARTIAL"
    | "FAILED";

  if (success) {
    status = "COMPLETED";
  } else if (
    completedAgents.length > 0
  ) {
    status = "PARTIAL";
  } else {
    status = "FAILED";
  }

  return {
    success,

    status,

    runId,

    results,

    resultsByAgent,

    executionOrder,

    completedAgents,

    failedAgents,

    skippedAgents,

    startedAt,

    completedAt,

    durationMs:
      Date.now() -
      startedTimestamp,
  };
}

export const orchestrate =
  runOrchestrator;

export class Orchestrator {
  async run(
    options: {
      runId?: string;
      strategyId?: string;
      symbol?: string;
      timeframe?: string;
      input?: Record<string, unknown>;
      metadata?: Record<string, unknown>;
    } = {}
  ): Promise<OrchestratorResult> {
    return runOrchestrator(
      options
    );
  }
}

export const orchestrator =
  new Orchestrator();

