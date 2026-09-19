import { spawn } from "node:child_process";
import path from "node:path";
import { existsSync } from "node:fs";

import type {
  AgentContext,
  AgentHandler,
} from "./agent-types";

import { agentRunner } from "./agent-runner";

type JsonRecord = Record<string, unknown>;

const PYTHON_EXECUTABLE =
  process.env.MARKETHQ_PYTHON?.trim() || "python";

const PAPER_TRADING_TIMEOUT_MS = 120_000;

function getProjectRoot(): string {
  const cwd = process.cwd();

  if (path.basename(cwd).toLowerCase() === "frontend") {
    return path.resolve(cwd, "..");
  }

  return cwd;
}

function getAdapterPath(): string {
  const projectRoot = getProjectRoot();

  /*
   * Canonical MarketHQ adapter location:
   *   <projectRoot>/paper_trading_adapter_v1.py
   *
   * Keep agents/ as a compatibility fallback because older layouts may
   * still contain the adapter there.
   */
  const candidates = [
    path.join(projectRoot, "paper_trading_adapter_v1.py"),
    path.join(
      projectRoot,
      "agents",
      "paper_trading_adapter_v1.py",
    ),
  ];

  const existingPath = candidates.find((candidate) =>
    existsSync(candidate),
  );

  return existingPath ?? candidates[0];
}

function isRecord(value: unknown): value is JsonRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getString(
  value: unknown,
  fallback = "",
): string {
  return typeof value === "string" && value.trim()
    ? value.trim()
    : fallback;
}

function getBoolean(
  value: unknown,
  fallback = false,
): boolean {
  return typeof value === "boolean"
    ? value
    : fallback;
}


function getExperiment(
  context: AgentContext,
): JsonRecord {
  /*
   * CONTRACT: Experiment Generator owns the complete experiment definition
   * (including dateScope). Experiment Runner owns the executed/frozen runtime
   * plan, but its executionPlan intentionally does not repeat every generator
   * field. Therefore Paper Trading must compose BOTH outputs instead of
   * treating Runner output as a standalone experiment.
   */
  const generatorOutput =
    context.previousResults?.["experiment-generator"]?.output;
  const runnerOutput =
    context.previousResults?.["experiment-runner"]?.output;

  const generatorExperiment =
    isRecord(generatorOutput?.experiment)
      ? generatorOutput.experiment
      : isRecord(generatorOutput)
        ? generatorOutput
        : {};

  const runnerExperiment =
    isRecord(runnerOutput?.experiment)
      ? runnerOutput.experiment
      : {};

  if (
    Object.keys(generatorExperiment).length === 0 &&
    Object.keys(runnerExperiment).length === 0
  ) {
    return {};
  }

  /*
   * Generator remains the source of the full definition. Runner overrides
   * execution/runtime fields so Paper Trading uses exactly what Runner
   * validated/executed. Nested objects are merged explicitly because Runner
   * contains strategy/market/constraints but does not carry dateScope.
   */
  return {
    ...generatorExperiment,
    ...runnerExperiment,

    experimentId: getString(
      runnerExperiment.experimentId,
      getString(
        generatorExperiment.experimentId,
        getString(generatorExperiment.id, ""),
      ),
    ),

    strategy: {
      ...(isRecord(generatorExperiment.strategy)
        ? generatorExperiment.strategy
        : {}),
      ...(isRecord(runnerExperiment.strategy)
        ? runnerExperiment.strategy
        : {}),
    },

    market: {
      ...(isRecord(generatorExperiment.market)
        ? generatorExperiment.market
        : {}),
      ...(isRecord(runnerExperiment.market)
        ? runnerExperiment.market
        : {}),
    },

    constraints: {
      ...(isRecord(generatorExperiment.constraints)
        ? generatorExperiment.constraints
        : {}),
      ...(isRecord(runnerExperiment.constraints)
        ? runnerExperiment.constraints
        : {}),
    },

    /* Runner V3 does not repeat the generator's dateScope. */
    dateScope: isRecord(generatorExperiment.dateScope)
      ? generatorExperiment.dateScope
      : isRecord(runnerExperiment.dateScope)
        ? runnerExperiment.dateScope
        : {},

    runnerExecution: {
      ...(isRecord(runnerOutput) ? runnerOutput : {}),
    },
  };
}

function getRunnerOutput(
  context: AgentContext,
): JsonRecord {
  const runnerOutput =
    context.previousResults?.["experiment-runner"]?.output;

  return isRecord(runnerOutput)
    ? runnerOutput
    : {};
}

function buildAdapterPayload(
  context: AgentContext,
): JsonRecord {
  const experiment = getExperiment(context);
  const runnerOutput = getRunnerOutput(context);

  const experimentId = getString(
    experiment.experimentId,
    getString(
      experiment.id,
      getString(context.strategyId, ""),
    ),
  );

  const strategyId = getString(
    experiment.strategyId,
    getString(
      isRecord(experiment.strategy)
        ? experiment.strategy.strategyId
        : undefined,
      getString(context.strategyId, ""),
    ),
  );

  const market =
    isRecord(experiment.market)
      ? experiment.market
      : {};

  /*
   * ExperimentDefinition stores the instrument under market.symbol/timeframe.
   * Reading experiment.symbol first caused Paper Trading to fall back to the
   * orchestrator context while the Runner had frozen another market. That
   * created the ASELS/THYAO split seen in the last run.
   */
  const symbol = getString(
    market.symbol,
    getString(context.symbol, ""),
  );

  const timeframe = getString(
    market.timeframe,
    getString(context.timeframe, "1d"),
  );

  const dateScope =
    isRecord(experiment.dateScope)
      ? experiment.dateScope
      : {};

  const runnerExecution =
    isRecord(runnerOutput.execution)
      ? runnerOutput.execution
      : {};

  return {
    runId: context.runId,

    experimentId,
    strategyId,
    symbol,
    timeframe,

    experiment,

    dateScope,

    experimentRunner: {
      status: getString(
        runnerOutput.status,
        "",
      ),

      execution: runnerExecution,

      researchExecution:
        isRecord(
          runnerOutput.researchExecution,
        )
          ? runnerOutput.researchExecution
          : {},
    },

    safety: {
      researchOnly: true,
      executionEnabled: false,
      brokerExecutionEnabled: false,
      databaseWriteEnabled: false,
      operationalDatabaseWriteEnabled: false,
    },

    paperTrading: {
      mode: "HISTORICAL_PAPER_SIMULATION",
      environment: "PAPER",
      liveExecution: false,
      brokerExecution: false,
    },
  };
}

function parseStdout(
  stdout: string,
): JsonRecord {
  const trimmed = stdout.trim();

  if (!trimmed) {
    throw new Error(
      "Paper Trading adapter boş çıktı döndürdü.",
    );
  }

  try {
    const parsed: unknown =
      JSON.parse(trimmed);

    if (!isRecord(parsed)) {
      throw new Error(
        "Paper Trading adapter JSON object döndürmedi.",
      );
    }

    return parsed;
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : String(error);

    throw new Error(
      `Paper Trading adapter JSON parse hatası: ${message}`,
    );
  }
}

function runPythonAdapter(
  payload: JsonRecord,
): Promise<JsonRecord> {
  return new Promise((resolve, reject) => {
    const adapterPath = getAdapterPath();

    const child = spawn(
      PYTHON_EXECUTABLE,
      [adapterPath],
      {
        cwd: getProjectRoot(),
        stdio: [
          "pipe",
          "pipe",
          "pipe",
        ],
        windowsHide: true,
      },
    );

    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    let settled = false;

    const timeout = setTimeout(() => {
      if (settled) {
        return;
      }

      settled = true;

      child.kill();

      reject(
        new Error(
          `Paper Trading adapter timeout: ${PAPER_TRADING_TIMEOUT_MS}ms`,
        ),
      );
    }, PAPER_TRADING_TIMEOUT_MS);

    child.stdout.on(
      "data",
      (chunk: Buffer) => {
        stdoutChunks.push(chunk);
      },
    );

    child.stderr.on(
      "data",
      (chunk: Buffer) => {
        stderrChunks.push(chunk);
      },
    );

    child.on(
      "error",
      (error) => {
        if (settled) {
          return;
        }

        settled = true;

        clearTimeout(timeout);

        reject(
          new Error(
            [
              `Paper Trading adapter başlatılamadı: ${error.message}`,
              `adapterPath=${adapterPath}`,
              `cwd=${getProjectRoot()}`,
              `python=${PYTHON_EXECUTABLE}`,
            ].join(" | "),
          ),
        );
      },
    );

    child.on(
      "close",
      (code, signal) => {
        if (settled) {
          return;
        }

        settled = true;

        clearTimeout(timeout);

        const stdout =
          Buffer.concat(stdoutChunks)
            .toString("utf8")
            .trim();

        const stderr =
          Buffer.concat(stderrChunks)
            .toString("utf8")
            .trim();

        if (stdout) {
          try {
            const parsed =
              parseStdout(stdout);

            if (code !== 0) {
              const adapterError =
                getString(
                  parsed.error,
                  "",
                );

              const adapterStatus =
                getString(
                  parsed.status,
                  "",
                );

              reject(
                new Error(
                  [
                    adapterError
                      ? `error=${adapterError}`
                      : "",
                    adapterStatus
                      ? `status=${adapterStatus}`
                      : "",
                    `exitCode=${code}`,
                    signal
                      ? `signal=${signal}`
                      : "",
                    stderr
                      ? `stderr=${stderr}`
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" | "),
                ),
              );

              return;
            }

            resolve(parsed);
            return;
          } catch (error) {
            const message =
              error instanceof Error
                ? error.message
                : String(error);

            reject(
              new Error(
                [
                  `Paper Trading adapter JSON parse hatası: ${message}`,
                  `exitCode=${code}`,
                  signal
                    ? `signal=${signal}`
                    : "",
                  stderr
                    ? `stderr=${stderr}`
                    : "",
                  `stdout=${stdout.slice(0, 4000)}`,
                ]
                  .filter(Boolean)
                  .join(" | "),
              ),
            );

            return;
          }
        }

        reject(
          new Error(
            [
              `Paper Trading adapter exitCode=${code}`,
              signal
                ? `signal=${signal}`
                : "",
              "stdout=EMPTY",
              stderr
                ? `stderr=${stderr}`
                : "",
            ]
              .filter(Boolean)
              .join(" | "),
          ),
        );
      },
    );

    child.stdin.write(
      JSON.stringify(payload),
    );

    child.stdin.end();
  });
}

const runPaperTradingAgent: AgentHandler =
  async (
    context: AgentContext,
  ): Promise<JsonRecord> => {
    const experiment =
      getExperiment(context);

    const runnerOutput =
      getRunnerOutput(context);

    /*
     * AgentResult.status is the orchestrator lifecycle status and must be
     * COMPLETED before Paper Trading starts. Runner output.status is the
     * experiment-plan status (normally READY), so it must NOT be compared to
     * the AgentResult lifecycle value.
     */
    const runnerAgentResult =
      context.previousResults?.["experiment-runner"];

    const runnerAgentStatus =
      getString(
        runnerAgentResult?.status,
        "",
      );

    const runnerPlanStatus =
      getString(
        runnerOutput.status,
        "",
      );

    if (
      !isRecord(experiment) ||
      Object.keys(experiment).length === 0
    ) {
      const generatorOutput =
        context.previousResults?.["experiment-generator"]?.output;
      const runnerOutput =
        context.previousResults?.["experiment-runner"]?.output;
      const generatorKeys =
        isRecord(generatorOutput)
          ? Object.keys(generatorOutput)
          : [];
      const runnerKeys =
        isRecord(runnerOutput)
          ? Object.keys(runnerOutput)
          : [];

      throw new Error(
        [
          "Paper Trading çalıştırılamadı: experiment contract bulunamadı.",
          `generatorOutputKeys=${generatorKeys.join(",") || "NONE"}`,
          `runnerOutputKeys=${runnerKeys.join(",") || "NONE"}`,
        ].join(" | "),
      );
    }

    if (runnerAgentStatus !== "COMPLETED") {
      throw new Error(
        [
          "Paper Trading çalıştırılamadı: Experiment Runner lifecycle tamamlanmadı.",
          `agentStatus=${runnerAgentStatus || "MISSING"}`,
          `planStatus=${runnerPlanStatus || "MISSING"}`,
        ].join(" | "),
      );
    }

    const runnerExecution =
      isRecord(runnerOutput.researchExecution)
        ? runnerOutput.researchExecution
        : {};

    const runnerExecutionStatus =
      getString(
        runnerExecution.status,
        "",
      );

    if (
      runnerExecutionStatus &&
      runnerExecutionStatus !== "COMPLETED"
    ) {
      throw new Error(
        [
          "Paper Trading çalıştırılamadı: Experiment Runner research execution tamamlanmadı.",
          `agentStatus=${runnerAgentStatus}`,
          `planStatus=${runnerPlanStatus || "MISSING"}`,
          `researchExecutionStatus=${runnerExecutionStatus}`,
        ].join(" | "),
      );
    }

    const runnerExperiment =
      isRecord(runnerOutput.experiment)
        ? runnerOutput.experiment
        : {};
    const runnerMarket =
      isRecord(runnerExperiment.market)
        ? runnerExperiment.market
        : {};
    const frozenSymbol = getString(
      runnerMarket.symbol,
      "",
    );
    const frozenTimeframe = getString(
      runnerMarket.timeframe,
      "",
    );
    const paperSymbol = getString(
      isRecord(experiment.market)
        ? experiment.market.symbol
        : undefined,
      getString(context.symbol, ""),
    );
    const paperTimeframe = getString(
      isRecord(experiment.market)
        ? experiment.market.timeframe
        : undefined,
      getString(context.timeframe, "1d"),
    );

    if (
      frozenSymbol &&
      paperSymbol &&
      frozenSymbol.toUpperCase() !== paperSymbol.toUpperCase()
    ) {
      throw new Error(
        [
          "Paper Trading çalıştırılamadı: frozen market symbol uyuşmazlığı.",
          `runner=${frozenSymbol}`,
          `experiment=${paperSymbol}`,
        ].join(" | "),
      );
    }

    if (
      frozenTimeframe &&
      paperTimeframe &&
      frozenTimeframe !== paperTimeframe
    ) {
      throw new Error(
        [
          "Paper Trading çalıştırılamadı: frozen timeframe uyuşmazlığı.",
          `runner=${frozenTimeframe}`,
          `experiment=${paperTimeframe}`,
        ].join(" | "),
      );
    }

    const experimentId =
      getString(
        experiment.experimentId,
        getString(
          experiment.id,
          "",
        ),
      );

    if (!experimentId) {
      throw new Error(
        "Paper Trading çalıştırılamadı: experimentId eksik.",
      );
    }

    const adapterPayload =
      buildAdapterPayload(context);

    const startedAt =
      new Date().toISOString();

    const adapterResult =
      await runPythonAdapter(
        adapterPayload,
      );

    const completedAt =
      new Date().toISOString();

    if (
      adapterResult.success === false ||
      getString(adapterResult.status, "").toUpperCase() === "FAILED" ||
      getString(adapterResult.status, "").toUpperCase() === "ERROR"
    ) {
      const adapterError = getString(
        adapterResult.error,
        "Paper Trading adapter başarısız sonuç döndürdü.",
      );

      throw new Error(
        [
          adapterError,
          `adapterPath=${getAdapterPath()}`,
          `python=${PYTHON_EXECUTABLE}`,
        ].join(" | "),
      );
    }

    const adapterSafety =
      isRecord(
        adapterResult.safety,
      )
        ? adapterResult.safety
        : {};

    const adapterExecution =
      isRecord(
        adapterResult.execution,
      )
        ? adapterResult.execution
        : {};

    const paperResult =
      isRecord(
        adapterResult.paperResult,
      )
        ? adapterResult.paperResult
        : adapterResult;

    return {
      success:
        getBoolean(
          adapterResult.success,
          true,
        ),

      mode:
        "PAPER_TRADING_RESEARCH_ONLY_V1",

      status:
        getString(
          adapterResult.status,
          "COMPLETED",
        ),

      experimentId,

      strategyId:
        getString(
          adapterPayload.strategyId,
        ),

      symbol:
        getString(
          adapterPayload.symbol,
        ),

      timeframe:
        getString(
          adapterPayload.timeframe,
          "1d",
        ),

      paperResult,

      execution: {
        ...adapterExecution,

        liveExecution: false,
        brokerOrderPlaced: false,
        realMoneyExecution: false,
      },

      safety: {
        researchOnly: true,
        executionEnabled: false,
        brokerExecutionEnabled: false,
        brokerOrderPlaced: false,
        databaseWriteEnabled: false,
        operationalDatabaseWriteEnabled: false,
        researchStorageWritePerformed:
          false,
        adapterSafety,
      },

      persistence: {
        persistenceMode:
          "RESULT_INGESTION",
        writesPerformedByAgent:
          false,
        storageStage:
          "RESULT_INGESTION",
        note:
          "Paper Trading simülasyonu üretir; kalıcı Research Storage yazımı Result Ingestion katmanında yapılır.",
      },

      adapter: {
        path:
          getAdapterPath(),
        python:
          PYTHON_EXECUTABLE,
      },

      timing: {
        startedAt,
        completedAt,
        durationMs:
          Math.max(
            0,
            new Date(
              completedAt,
            ).getTime() -
              new Date(
                startedAt,
              ).getTime(),
          ),
      },

      researchOnly:
        true,

      executionEnabled:
        false,

      databaseWritePerformed:
        false,

      brokerOrderPlaced:
        false,
    };
  };

export function registerPaperTradingAgent(): void {
  agentRunner.register(
    "paper-trading",
    runPaperTradingAgent,
  );
}

