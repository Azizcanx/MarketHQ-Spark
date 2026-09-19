export type AgentStatus =
  | "IDLE"
  | "READY"
  | "RUNNING"
  | "COMPLETED"
  | "ERROR";

export type AgentId =
  | "market-data"
  | "trend-regime"
  | "strategy"
  | "backtest"
  | "validation"
  | "evidence"
  | "brain"
  | "learning"
  | "research-decision"
  | "research-queue"
  | "experiment-generator"
  | "experiment-runner"
  | "paper-trading"
  | "result-ingestion"
  | "orchestrator"
  | "research-date-resolver"
  | "brain-update";

export interface AgentContext {
  runId: string;
  strategyId?: string;
  symbol?: string;
  timeframe?: string;
  input?: Record<string, unknown>;
  previousResults?: Partial<
    Record<AgentId, AgentResult>
  >;
  metadata?: Record<string, unknown>;
}

export interface AgentResult {
  success: boolean;
  agentId: AgentId;
  runId: string;
  status: AgentStatus;
  output?: Record<string, unknown>;
  metrics?: Record<string, number>;
  warnings?: string[];
  error?: string;
  startedAt: string;
  completedAt: string;
  durationMs?: number;
}

export type AgentHandler = (
  context: AgentContext,
) => Promise<
  Record<string, unknown>
>;

export interface AgentDefinition {
  id: AgentId;
  name: string;
  description: string;
  dependencies: AgentId[];
}

export interface Agent {
  definition: AgentDefinition;
  run: (
    context: AgentContext,
  ) => Promise<AgentResult>;
}

