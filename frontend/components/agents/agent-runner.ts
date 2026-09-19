import type {
  Agent,
  AgentContext,
  AgentHandler,
  AgentId,
  AgentResult,
} from "./agent-types";

import {
  getAgent,
  updateAgentStatus,
} from "./agent-registry";

export class AgentRunner {
  private handlers: Partial<Record<AgentId, AgentHandler>> = {};

  register(agentId: AgentId, handler: AgentHandler): void {
    getAgent(agentId);
    this.handlers[agentId] = handler;
  }

  isRegistered(agentId: AgentId): boolean {
    return typeof this.handlers[agentId] === "function";
  }

  private safeUpdateAgentStatus(
    agentId: AgentId,
    status: "IDLE" | "READY" | "RUNNING" | "COMPLETED" | "ERROR",
  ): string | null {
    try {
      updateAgentStatus(agentId, status);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  }

  async run(agentId: AgentId, context: AgentContext): Promise<AgentResult> {
    const startedTimestamp = Date.now();
    const startedAt = new Date().toISOString();

    let definition;
    try {
      definition = getAgent(agentId);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        agentId,
        runId: context.runId,
        status: "ERROR",
        error: message,
        startedAt,
        completedAt: new Date().toISOString(),
        durationMs: Date.now() - startedTimestamp,
      };
    }

    const handler = this.handlers[agentId];
    if (!handler) {
      const statusError = this.safeUpdateAgentStatus(agentId, "ERROR");
      const errorMessage = `Agent handler not registered: ${definition.name}`;
      return {
        success: false,
        agentId,
        runId: context.runId,
        status: "ERROR",
        error: statusError
          ? `${errorMessage}; registry status update failed: ${statusError}`
          : errorMessage,
        startedAt,
        completedAt: new Date().toISOString(),
        durationMs: Date.now() - startedTimestamp,
      };
    }

    const runningStatusError = this.safeUpdateAgentStatus(agentId, "RUNNING");

    try {
      const output = await handler(context);

      let normalizedOutput = output;
      let metrics: Record<string, number> | undefined;

      if (agentId === "experiment-runner" && output && typeof output === "object") {
        const outputRecord = output as Record<string, unknown>;
        const researchExecution = outputRecord.researchExecution;
        const executionResult =
          researchExecution && typeof researchExecution === "object"
            ? (researchExecution as Record<string, unknown>).result
            : undefined;
        const backtestResult =
          executionResult && typeof executionResult === "object"
            ? (() => {
                const backtest = (executionResult as Record<string, unknown>).backtest;
                return backtest && typeof backtest === "object"
                  ? (backtest as Record<string, unknown>).result
                  : undefined;
              })()
            : undefined;
        const bestResult =
          backtestResult && typeof backtestResult === "object"
            ? (() => {
                const best = (backtestResult as Record<string, unknown>).best;
                return best && typeof best === "object" ? best : undefined;
              })()
            : undefined;

        const metricSources = [
          executionResult,
          backtestResult,
          bestResult,
          outputRecord.metrics,
        ];

        for (const source of metricSources) {
          if (!source || typeof source !== "object" || Array.isArray(source)) continue;
          const sourceRecord = source as Record<string, unknown>;
          const numericMetrics: Record<string, number> = {};

          if (sourceRecord.metrics && typeof sourceRecord.metrics === "object" && !Array.isArray(sourceRecord.metrics)) {
            for (const [key, value] of Object.entries(sourceRecord.metrics as Record<string, unknown>)) {
              const numericValue = Number(value);
              if (Number.isFinite(numericValue)) numericMetrics[key] = numericValue;
            }
          }

          if (Object.keys(numericMetrics).length === 0) {
            for (const [key, value] of Object.entries(sourceRecord)) {
              if (!key.endsWith("_percent") && !["sharpe_ratio", "trade_count", "win_rate", "net_pnl", "profit", "final_value"].includes(key)) continue;
              const numericValue = Number(value);
              if (Number.isFinite(numericValue)) numericMetrics[key] = numericValue;
            }
          }

          if (Object.keys(numericMetrics).length > 0) {
            metrics = numericMetrics;
            break;
          }
        }

        const diagnostics =
          executionResult && typeof executionResult === "object"
            ? (executionResult as Record<string, unknown>).overfitDiagnostics
            : undefined;

        if (diagnostics && typeof diagnostics === "object") {
          const existingRobustness = outputRecord.robustness;
          normalizedOutput = {
            ...output,
            robustness: {
              ...(existingRobustness && typeof existingRobustness === "object" ? existingRobustness : {}),
              overfitDiagnostics: diagnostics,
            },
          };
        }
      }

      const handlerStatus =
        output && typeof output === "object"
          ? String((output as Record<string, unknown>).status ?? "").toUpperCase()
          : "";
      const handlerFailed = ["BLOCKED", "FAILED", "ERROR"].includes(handlerStatus);

      if (handlerFailed) {
        const errorStatusUpdate = this.safeUpdateAgentStatus(agentId, "ERROR");
        const warnings: string[] = [];
        const handlerOutput = output && typeof output === "object"
          ? output as Record<string, unknown>
          : {};

        if (runningStatusError) warnings.push(`Agent RUNNING status update failed: ${runningStatusError}`);
        if (errorStatusUpdate) warnings.push(`Agent ERROR status update failed: ${errorStatusUpdate}`);

        const handlerReason = typeof handlerOutput.reason === "string" ? handlerOutput.reason : undefined;
        const handlerError = typeof handlerOutput.error === "string" ? handlerOutput.error : undefined;
        const handlerErrors = Array.isArray(handlerOutput.errors)
          ? handlerOutput.errors.map((value) => String(value)).filter(Boolean)
          : undefined;

        const nestedResearchExecution =
          handlerOutput.researchExecution && typeof handlerOutput.researchExecution === "object"
            ? handlerOutput.researchExecution as Record<string, unknown>
            : undefined;
        const nestedResult =
          nestedResearchExecution?.result && typeof nestedResearchExecution.result === "object"
            ? nestedResearchExecution.result as Record<string, unknown>
            : undefined;
        const nestedReason = typeof nestedResult?.reason === "string" ? nestedResult.reason : undefined;
        const nestedError = typeof nestedResult?.error === "string" ? nestedResult.error : undefined;
        const nestedErrors = Array.isArray(nestedResult?.errors)
          ? nestedResult.errors.map((value) => String(value)).filter(Boolean)
          : undefined;

        const effectiveReason = handlerReason || nestedReason;
        const effectiveError = handlerError || nestedError;
        const effectiveErrors = handlerErrors?.length ? handlerErrors : nestedErrors;

        return {
          success: false,
          agentId,
          runId: context.runId,
          status: "ERROR",
          output: normalizedOutput,
          ...(metrics ? { metrics } : {}),
          ...(effectiveReason ? { reason: effectiveReason } : {}),
          ...(effectiveErrors && effectiveErrors.length > 0 ? { errors: effectiveErrors } : {}),
          ...(effectiveError ? { error: effectiveError } : { error: `Agent handler returned status ${handlerStatus}` }),
          ...(warnings.length > 0 ? { warnings } : {}),
          startedAt,
          completedAt: new Date().toISOString(),
          durationMs: Date.now() - startedTimestamp,
        };
      }

      const completedStatusError = this.safeUpdateAgentStatus(agentId, "COMPLETED");
      const warnings: string[] = [];

      if (runningStatusError) warnings.push(`Agent RUNNING status update failed: ${runningStatusError}`);
      if (completedStatusError) warnings.push(`Agent COMPLETED status update failed: ${completedStatusError}`);

      return {
        success: true,
        agentId,
        runId: context.runId,
        status: "COMPLETED",
        output: normalizedOutput,
        ...(metrics ? { metrics } : {}),
        ...(warnings.length > 0 ? { warnings } : {}),
        startedAt,
        completedAt: new Date().toISOString(),
        durationMs: Date.now() - startedTimestamp,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const errorStatusUpdate = this.safeUpdateAgentStatus(agentId, "ERROR");
      const warnings: string[] = [];

      if (runningStatusError) warnings.push(`Agent RUNNING status update failed: ${runningStatusError}`);
      if (errorStatusUpdate) warnings.push(`Agent ERROR status update failed: ${errorStatusUpdate}`);

      return {
        success: false,
        agentId,
        runId: context.runId,
        status: "ERROR",
        error: message,
        ...(warnings.length > 0 ? { warnings } : {}),
        startedAt,
        completedAt: new Date().toISOString(),
        durationMs: Date.now() - startedTimestamp,
      };
    }
  }
}

export function createAgent(
  definition: ReturnType<typeof getAgent>,
  handler: AgentHandler,
): Agent {
  return {
    definition,
    async run(context: AgentContext): Promise<AgentResult> {
      const runner = new AgentRunner();
      runner.register(definition.id, handler);
      return runner.run(definition.id, context);
    },
  };
}

export const agentRunner = new AgentRunner();
