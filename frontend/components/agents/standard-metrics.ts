export interface StandardMetrics {
  initialCapital: number | null;
  finalEquity: number | null;
  netPnl: number | null;
  returnPercent: number | null;
  tradeCount: number | null;
  wins: number | null;
  losses: number | null;
  winRatePercent: number | null;
  profitFactor: number | null;
  averageTradePnl: number | null;
  maxDrawdownPercent: number | null;
  sharpe: number | null;
  sortino: number | null;
  volatilityPercent: number | null;
  benchmarkReturnPercent: number | null;
  excessReturnPercent: number | null;
  observations: number;
  annualizationFactor: number;
  status: "READY" | "PARTIAL" | "UNAVAILABLE";
}

type UnknownRecord = Record<string, unknown>;

export interface StandardMetricsOptions {
  benchmarkReturnPercent?: number | null;
  annualizationFactor?: number;
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function numberOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function firstNumber(roots: UnknownRecord[], keys: string[]): number | null {
  for (const root of roots) {
    for (const key of keys) {
      const value = numberOrNull(root[key]);
      if (value !== null) return value;
    }
  }
  return null;
}

function collectNumbers(value: unknown, depth = 0): number[] {
  if (depth > 8) return [];
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectNumbers(item, depth + 1));
  }
  if (typeof value === "number" && Number.isFinite(value)) return [value];
  return [];
}

function findArray(root: UnknownRecord, keys: string[]): unknown[] | null {
  for (const key of keys) {
    if (Array.isArray(root[key])) return root[key] as unknown[];
  }
  const nested = [
    root.metrics,
    root.results,
    root.summary,
    root.backtest,
    root.validation,
    root.paperTrading,
    root.paper_trading,
  ];
  for (const candidate of nested) {
    if (!isRecord(candidate)) continue;
    const found = findArray(candidate, keys);
    if (found) return found;
  }
  return null;
}

function normalizeEquityCurve(root: UnknownRecord): number[] {
  const array = findArray(root, [
    "equityCurve",
    "equity_curve",
    "equity",
    "portfolioValue",
    "portfolio_value",
    "balanceHistory",
    "balance_history",
  ]);
  if (!array) return [];

  const values: number[] = [];
  for (const item of array) {
    if (typeof item === "number" && Number.isFinite(item)) {
      values.push(item);
      continue;
    }
    if (!isRecord(item)) continue;
    const value = firstNumber([item], [
      "equity",
      "value",
      "portfolioValue",
      "portfolio_value",
      "balance",
      "close",
    ]);
    if (value !== null) values.push(value);
  }
  return values;
}

function normalizeReturns(root: UnknownRecord, equity: number[]): number[] {
  const array = findArray(root, [
    "returns",
    "returnSeries",
    "return_series",
    "dailyReturns",
    "daily_returns",
    "periodReturns",
    "period_returns",
  ]);

  if (array) {
    const values = collectNumbers(array);
    if (values.length) return values;
  }

  if (equity.length < 2) return [];
  const returns: number[] = [];
  for (let i = 1; i < equity.length; i += 1) {
    const previous = equity[i - 1];
    const current = equity[i];
    if (previous !== 0) returns.push(current / previous - 1);
  }
  return returns;
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

function sampleStd(values: number[]): number | null {
  if (values.length < 2) return null;
  const m = mean(values);
  if (m === null) return null;
  const variance = values.reduce((sum, value) => sum + (value - m) ** 2, 0) / (values.length - 1);
  return Math.sqrt(Math.max(0, variance));
}

function maxDrawdownFromEquity(equity: number[]): number | null {
  if (!equity.length) return null;
  let peak = equity[0];
  let maxDrawdown = 0;
  for (const value of equity) {
    if (value > peak) peak = value;
    if (peak !== 0) maxDrawdown = Math.max(maxDrawdown, (peak - value) / peak);
  }
  return maxDrawdown * 100;
}

function firstRecord(root: UnknownRecord, keys: string[]): UnknownRecord | null {
  for (const key of keys) {
    if (isRecord(root[key])) return root[key];
  }
  return null;
}

function deriveTradeMetrics(root: UnknownRecord) {
  const tradeArray = findArray(root, [
    "trades",
    "tradeHistory",
    "trade_history",
    "closedTrades",
    "closed_trades",
  ]);

  if (!tradeArray) return { tradeCount: null, wins: null, losses: null, profitFactor: null };

  let wins = 0;
  let losses = 0;
  let grossProfit = 0;
  let grossLoss = 0;

  for (const item of tradeArray) {
    if (!isRecord(item)) continue;
    const pnl = firstNumber([item], ["pnl", "PnL", "netPnl", "net_pnl", "profit", "profitLoss", "profit_loss"]);
    if (pnl === null) continue;
    if (pnl > 0) {
      wins += 1;
      grossProfit += pnl;
    } else if (pnl < 0) {
      losses += 1;
      grossLoss += Math.abs(pnl);
    }
  }

  const tradeCount = wins + losses;
  return {
    tradeCount: tradeCount || null,
    wins: tradeCount ? wins : null,
    losses: tradeCount ? losses : null,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : null,
  };
}

export function calculateStandardMetrics(
  source: UnknownRecord,
  options: StandardMetricsOptions = {},
): StandardMetrics {
  const annualizationFactor = options.annualizationFactor ?? 252;
  const nested = [
    source,
    firstRecord(source, ["result", "normalizedResult", "paperTrading", "paper_trading"]) ?? {},
    firstRecord(source, ["metrics", "summary"]) ?? {},
  ];

  const initialCapital = firstNumber(nested, [
    "initialCapital", "initial_capital", "startingCapital", "starting_capital",
  ]);
  const finalEquity = firstNumber(nested, [
    "finalEquity", "final_equity", "endingEquity", "ending_equity", "finalBalance", "final_balance",
  ]);
  const directPnl = firstNumber(nested, ["netPnl", "net_pnl", "pnl", "PnL", "totalPnl", "total_pnl"]);
  const directReturn = firstNumber(nested, ["returnPercent", "return_percent", "returnPct", "return_pct"]);
  const directTradeCount = firstNumber(nested, ["tradeCount", "trade_count", "trades"]);
  const directWins = firstNumber(nested, ["wins", "winningTrades", "winning_trades"]);
  const directLosses = firstNumber(nested, ["losses", "losingTrades", "losing_trades"]);
  const directWinRate = firstNumber(nested, ["winRatePercent", "win_rate_percent", "winRate", "win_rate"]);
  const directPf = firstNumber(nested, ["profitFactor", "profit_factor", "pf"]);
  const directAvg = firstNumber(nested, ["averageTradePnl", "average_trade_pnl", "avgTradePnl", "avg_trade_pnl"]);
  const directDd = firstNumber(nested, ["maxDrawdownPercent", "max_drawdown_percent", "maxDrawdown", "max_drawdown"]);

  const equity = normalizeEquityCurve(source);
  const returns = normalizeReturns(source, equity);
  const trades = deriveTradeMetrics(source);

  const netPnl = directPnl ?? (initialCapital !== null && finalEquity !== null ? finalEquity - initialCapital : null);
  const returnPercent = directReturn ?? (
    initialCapital !== null && initialCapital !== 0 && finalEquity !== null
      ? ((finalEquity / initialCapital) - 1) * 100
      : null
  );

  const tradeCount = directTradeCount ?? trades.tradeCount;
  const wins = directWins ?? trades.wins;
  const losses = directLosses ?? trades.losses;
  const winRatePercent = directWinRate ?? (
    wins !== null && losses !== null && wins + losses > 0 ? (wins / (wins + losses)) * 100 : null
  );
  const profitFactor = directPf ?? trades.profitFactor;
  const averageTradePnl = directAvg ?? (
    netPnl !== null && tradeCount !== null && tradeCount > 0 ? netPnl / tradeCount : null
  );

  const maxDrawdownPercent = directDd ?? maxDrawdownFromEquity(equity);
  const avgReturn = mean(returns);
  const stdReturn = sampleStd(returns);
  const downside = returns.filter((value) => value < 0);
  const downsideStd = sampleStd(downside);
  const sharpe = avgReturn !== null && stdReturn !== null && stdReturn > 0
    ? (avgReturn / stdReturn) * Math.sqrt(annualizationFactor)
    : null;
  const sortino = avgReturn !== null && downsideStd !== null && downsideStd > 0
    ? (avgReturn / downsideStd) * Math.sqrt(annualizationFactor)
    : null;
  const volatilityPercent = stdReturn !== null ? stdReturn * Math.sqrt(annualizationFactor) * 100 : null;

  const benchmarkReturnPercent = numberOrNull(options.benchmarkReturnPercent) ?? firstNumber(nested, [
    "benchmarkReturnPercent", "benchmark_return_percent", "benchmarkReturn", "benchmark_return",
  ]);
  const excessReturnPercent = benchmarkReturnPercent !== null && returnPercent !== null
    ? returnPercent - benchmarkReturnPercent
    : null;

  const observations = returns.length || equity.length;
  const hasCore = netPnl !== null || returnPercent !== null || tradeCount !== null || maxDrawdownPercent !== null;

  return {
    initialCapital,
    finalEquity,
    netPnl,
    returnPercent,
    tradeCount,
    wins,
    losses,
    winRatePercent,
    profitFactor,
    averageTradePnl,
    maxDrawdownPercent,
    sharpe,
    sortino,
    volatilityPercent,
    benchmarkReturnPercent,
    excessReturnPercent,
    observations,
    annualizationFactor,
    status: hasCore ? (sharpe !== null || sortino !== null || volatilityPercent !== null ? "READY" : "PARTIAL") : "UNAVAILABLE",
  };
}

