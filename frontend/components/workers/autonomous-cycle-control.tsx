"use client";

import { useEffect, useState } from "react";

type CycleState = { status?: string; cycleNumber?: number; maxCycles?: number; lastAction?: string; lastReason?: string; updatedAt?: string };
type CycleResponse = { success?: boolean; executed?: boolean; reason?: string; autonomousCycle?: { cycleId?: string; cycleNumber?: number; maxCycles?: number; state?: CycleState | null }; cycle?: CycleState | null; error?: string };

export function AutonomousCycleControl() {
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("1d");
  const [maxCycles, setMaxCycles] = useState("10");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CycleResponse | null>(null);
  const [modeEnabled, setModeEnabled] = useState(false);
  const [cycleState, setCycleState] = useState<CycleState | null>(null);

  function currentCycleId() {
    return `autonomous|${strategyId.trim() || "default-strategy"}|${symbol.trim() || "default-symbol"}|${timeframe.trim() || "1d"}`;
  }

  async function loadMode() {
    try {
      const response = await fetch("/api/automation/mode", { cache: "no-store" });
      const payload = await response.json();
      setModeEnabled(payload?.mode?.enabled === true);
    } catch { /* status remains conservative */ }
  }

  async function loadCycleState() {
    try {
      const response = await fetch(`/api/automation/cycle?cycleId=${encodeURIComponent(currentCycleId())}`, { cache: "no-store" });
      const payload = await response.json();
      if (payload?.success) setCycleState(payload.cycle ?? null);
    } catch { /* cockpit remains source of truth */ }
  }

  async function runCycle() {
    if (running || !modeEnabled) return;
    setRunning(true); setResult(null);
    try {
      const body: Record<string, unknown> = { timeframe, maxCycles: Math.min(Math.max(Number(maxCycles) || 10, 1), 100) };
      if (strategyId.trim()) body.strategyId = strategyId.trim();
      if (symbol.trim()) body.symbol = symbol.trim();
      const response = await fetch("/api/automation/cycle", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) });
      const payload = await response.json() as CycleResponse;
      if (!response.ok && !payload.reason) throw new Error(payload.error ?? `HTTP ${response.status}`);
      setResult(payload);
      setCycleState(payload.autonomousCycle?.state ?? payload.cycle ?? null);
    } catch (error) {
      setResult({ success: false, error: error instanceof Error ? error.message : "Cycle başlatılamadı." });
    } finally { setRunning(false); }
  }

  useEffect(() => {
    void loadMode();
    void loadCycleState();
    const timer = window.setInterval(() => { void loadMode(); void loadCycleState(); }, 5000);
    return () => window.clearInterval(timer);
  }, [strategyId, symbol, timeframe]);

  return <section className="rounded-2xl border border-border bg-card p-4 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Autonomous Operations</p><h3 className="mt-1 text-lg font-bold">Bounded Cycle Runner</h3><p className="mt-1 text-xs text-muted-foreground">Tek seferde kontrollü research cycle çalıştırır. Kalıcı mode OFF ise çalışmaz.</p></div>
      <button type="button" onClick={() => void runCycle()} disabled={running || !modeEnabled} className="rounded-xl bg-slate-900 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{running ? "RUNNING…" : modeEnabled ? "RUN CYCLE" : "MODE OFF"}</button>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <input value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="Strategy ID (opsiyonel)" className="rounded-xl border border-border bg-background px-3 py-2 text-xs outline-none" />
      <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol (opsiyonel)" className="rounded-xl border border-border bg-background px-3 py-2 text-xs outline-none" />
      <input value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe" className="rounded-xl border border-border bg-background px-3 py-2 text-xs outline-none" />
      <input value={maxCycles} onChange={(e) => setMaxCycles(e.target.value)} inputMode="numeric" placeholder="Max cycles" className="rounded-xl border border-border bg-background px-3 py-2 text-xs outline-none" />
    </div>
    {cycleState && <div className="mt-3 grid gap-2 rounded-xl border border-border bg-muted/30 p-3 text-xs sm:grid-cols-3">
      <div><span className="text-muted-foreground">Durum</span><div className="font-semibold">{cycleState.status ?? "UNKNOWN"}</div></div>
      <div><span className="text-muted-foreground">Cycle</span><div className="font-semibold">{cycleState.cycleNumber ?? "—"}/{cycleState.maxCycles ?? "—"}</div></div>
      <div><span className="text-muted-foreground">Son aksiyon</span><div className="font-semibold">{cycleState.lastAction ?? "—"}</div></div>
      {cycleState.lastReason && <div className="sm:col-span-3"><span className="text-muted-foreground">Reason</span><div>{cycleState.lastReason}</div></div>}
    </div>}
    {result && <div className={`mt-3 rounded-xl border p-3 text-xs ${result.executed ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}><strong>{result.executed ? "Cycle executed" : result.reason ?? "Cycle sonucu"}</strong>{result.autonomousCycle?.cycleNumber && <span> · cycle {result.autonomousCycle.cycleNumber}/{result.autonomousCycle.maxCycles}</span>}{result.error && <div className="mt-1">{result.error}</div>}</div>}
  </section>;
}
