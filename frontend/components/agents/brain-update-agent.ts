import type { AgentContext } from "./agent-types";
import { agentRunner } from "./agent-runner";
import { spawn } from "child_process";
import path from "path";
import { existsSync } from "node:fs";

type JsonRecord = Record<string, unknown>;

interface EngineSummary {
  validationsSeen: number;
  brainRuleNodesUpdated: number;
  statusEdgesCreated: number;
  researchTasksQueued: number;
  holdoutPassApplied: number;
  holdoutWeakApplied: number;
  insufficientDataApplied: number;
}

function resolveProjectRoot(): string {
  const configured = process.env.MARKETHQ_PROJECT_ROOT?.trim();
  if (configured) return configured;

  const cwd = process.cwd();
  const candidates = [cwd, path.resolve(cwd, "..")];

  for (const candidate of candidates) {
    if (
      existsSync(
        path.join(candidate, "agents", "brain_update_engine_v1.py"),
      )
    ) {
      return candidate;
    }
  }

  return cwd;
}

function getPythonExecutable(): string {
  return process.env.MARKETHQ_PYTHON?.trim() || "python";
}

function parseInteger(text: string, label: string): number {
  const match = text.match(
    new RegExp(`${label}\\s+([0-9]+)`, "i"),
  );

  if (!match) return 0;

  const value = Number(match[1]);
  return Number.isFinite(value) ? value : 0;
}

function parseEngineSummary(stdout: string): EngineSummary {
  return {
    validationsSeen: parseInteger(stdout, "validations_seen"),
    brainRuleNodesUpdated: parseInteger(
      stdout,
      "brain_rule_nodes_updated",
    ),
    statusEdgesCreated: parseInteger(
      stdout,
      "status_edges_created",
    ),
    researchTasksQueued: parseInteger(
      stdout,
      "research_tasks_queued",
    ),
    holdoutPassApplied: parseInteger(
      stdout,
      "holdout_pass_applied",
    ),
    holdoutWeakApplied: parseInteger(
      stdout,
      "holdout_weak_applied",
    ),
    insufficientDataApplied: parseInteger(
      stdout,
      "insufficient_data_applied",
    ),
  };
}

function getAgentStatus(
  context: AgentContext,
  agentId: string,
): string {
  const result = context.previousResults?.[
    agentId as keyof NonNullable<AgentContext["previousResults"]>
  ];

  return result?.status ?? "NOT_RUN";
}

function getAgentRunId(
  context: AgentContext,
  agentId: string,
): string | null {
  const result = context.previousResults?.[
    agentId as keyof NonNullable<AgentContext["previousResults"]>
  ];

  return result?.runId ?? null;
}

function runBrainUpdateEngine(
  projectRoot: string,
  pythonExecutable: string,
  enginePath: string,
): Promise<{
  stdout: string;
  stderr: string;
  exitCode: number;
}> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    let settled = false;

    const child = spawn(
      pythonExecutable,
      [enginePath],
      {
        cwd: projectRoot,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );

    const finish = (callback: () => void): void => {
      if (settled) return;
      settled = true;
      callback();
    };

    const timeout = setTimeout(() => {
      try {
        child.kill();
      } catch {
        // noop
      }

      finish(() => {
        reject(
          new Error(
            "Brain Update Engine zaman aşımına uğradı.",
          ),
        );
      });
    }, 60_000);

    child.stdout.on("data", (chunk: Buffer | string) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk: Buffer | string) => {
      stderr += chunk.toString();
    });

    child.on("error", (error) => {
      clearTimeout(timeout);
      finish(() => reject(error));
    });

    child.on("close", (code) => {
      clearTimeout(timeout);
      finish(() =>
        resolve({
          stdout,
          stderr,
          exitCode: typeof code === "number" ? code : -1,
        }),
      );
    });
  });
}

export async function runBrainUpdateAgent(
  context: AgentContext,
): Promise<JsonRecord> {
  const projectRoot = resolveProjectRoot();
  const enginePath = path.join(
    projectRoot,
    "agents",
    "brain_update_engine_v1.py",
  );

  if (!existsSync(enginePath)) {
    throw new Error(
      `Brain Update Engine bulunamadı: ${enginePath}`,
    );
  }

  const pythonExecutable = getPythonExecutable();
  const engineResult = await runBrainUpdateEngine(
    projectRoot,
    pythonExecutable,
    enginePath,
  );

  if (engineResult.exitCode !== 0) {
    throw new Error(
      [
        "Brain Update Engine başarısız oldu.",
        `exitCode=${engineResult.exitCode}`,
        engineResult.stderr.trim(),
        engineResult.stdout.trim(),
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }

  const summary = parseEngineSummary(engineResult.stdout);

  const learningStatus = getAgentStatus(context, "learning");
  const validationStatus = getAgentStatus(context, "validation");
  const ingestionStatus = getAgentStatus(
    context,
    "result-ingestion",
  );

  return {
    agent: "brain-update",
    runId: context.runId,
    strategyId: context.strategyId ?? "STR-43839FA9C6",
    status: "BRAIN_UPDATED",

    engine: {
      name: "MARKETHQ_BRAIN_UPDATE_ENGINE",
      version: "V1",
      script: enginePath,
      python: pythonExecutable,
      exitCode: engineResult.exitCode,
    },

    inputs: {
      learningAvailable: learningStatus === "COMPLETED",
      validationAvailable: validationStatus === "COMPLETED",
      resultIngestionAvailable: ingestionStatus === "COMPLETED",
      learningRunId: getAgentRunId(context, "learning"),
      validationRunId: getAgentRunId(context, "validation"),
      resultIngestionRunId: getAgentRunId(
        context,
        "result-ingestion",
      ),
    },

    summary,

    researchGraph: {
      updatePerformed: true,
      source: "brain_update_engine_v1",
      derivedLayerOnly: true,
      rawExperimentDataMutated: false,
      rawResultDataMutated: false,
      learnedRulesMutated: false,
      claimsPromotedToVerified: false,
      brainNodesUpdated: summary.brainRuleNodesUpdated,
      brainEdgesCreated: summary.statusEdgesCreated,
      researchTasksQueued: summary.researchTasksQueued,
    },

    safety: {
      researchOnly: true,
      executionEnabled: false,
      brokerExecutionEnabled: false,
      operationalDatabaseWriteEnabled: false,
      researchStorageWritePerformed: true,
      originalRulesMutated: false,
      rawExperimentDataMutated: false,
      rawResultDataMutated: false,
      verifiedClaimsPromoted: false,
    },

    mode: "RESEARCH_STORAGE_BRAIN_UPDATE_V1",

    note:
      "Brain Update yalnızca türetilmiş araştırma grafiği katmanını günceller. Learned rule, ham experiment/result ve verified claim katmanları değiştirilmez.",

    stdout: engineResult.stdout.trim(),
    stderr: engineResult.stderr.trim() || null,
    updatedAt: new Date().toISOString(),
  };
}

export function registerBrainUpdateAgent(): void {
  agentRunner.register(
    "brain-update",
    runBrainUpdateAgent,
  );
}

