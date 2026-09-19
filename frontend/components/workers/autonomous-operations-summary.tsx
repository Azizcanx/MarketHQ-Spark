"use client";

import { useEffect, useState } from "react";

type Cycle = { cycleId?: string; status?: string; cycleNumber?: number; maxCycles?: number; lastAction?: string; lastReason?: string; workerTaskId?: string; workerStatus?: string; attempts?: number; implementationIntent?: string; feedbackRecommendation?: string; patchQualityGrade?: string; patchQualityScore?: number; retryRecommended?: boolean; nextCycleAllowed?: boolean; updatedAt?: string };
type Summary = { mode?: { enabled?: boolean }; scheduler?: string; cycle?: Cycle | null; cycles?: Cycle[]; telemetry?: { returned?: number; counts?: Record<string, number>; latestUpdatedAt?: string | null }; runtime?: { enabled?: boolean; maxConcurrency?: number }; records?: Array<{ status?: string }>; safety?: Record<string, boolean> };
function pill(on: boolean | undefined) { return on ? "bg-emerald-100 text-emerald-700" : "bg-muted text-muted-foreground"; }
function shortId(value?: string) { return value ? value.length > 24 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value : "—"; }
function time(value?: string) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }

export function AutonomousOperationsSummary() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function load() { try { const [modeResponse, workerResponse, cycleResponse] = await Promise.all([fetch("/api/automation/mode", { cache: "no-store" }), fetch("/api/workers?limit=25", { cache: "no-store" }), fetch("/api/automation/cycle?limit=10", { cache: "no-store" })]); const [mode, worker, cycle] = await Promise.all([modeResponse.json(), workerResponse.json(), cycleResponse.json()]); setData({ mode: mode.mode, runtime: worker.runtime, records: worker.records, scheduler: cycle.scheduler, cycle: cycle.cycle, cycles: cycle.cycles, telemetry: cycle.telemetry, safety: cycle.safety }); setError(null); } catch (err) { setError(err instanceof Error ? err.message : "Operations summary okunamadı."); } }
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 5000); return () => window.clearInterval(timer); }, []);
  const records = data?.records ?? [];
  const active = records.filter((record) => ["QUEUED", "DISPATCHED", "STARTING", "RUNNING", "PATCH_READY", "PATCH_INTAKE", "VALIDATING"].includes(record.status ?? "")).length;
  const accepted = records.filter((record) => record.status === "ACCEPTED").length;
  const review = records.filter((record) => record.status === "REVIEW_REQUIRED" || record.status === "PATCH_REJECTED").length;
  const cycles = data?.cycles ?? [];
  return (
    <section className="rounded-2xl border border-border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs text-muted-foreground">Operations overview</p><h2 className="text-lg font-semibold">Autonomous Runtime Status</h2></div>{error ? <span className="text-xs text-amber-700">{error}</span> : <span className="text-[11px] text-muted-foreground">5s live refresh</span>}</div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Mode</div><span className={`mt-1 inline-flex rounded-full px-2 py-1 text-[11px] font-semibold ${pill(data?.mode?.enabled)}`}>{data?.mode?.enabled ? "ON" : "OFF"}</span></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Scheduler</div><span className={`mt-1 inline-flex rounded-full px-2 py-1 text-[11px] font-semibold ${pill(data?.scheduler === "ENABLED")}`}>{data?.scheduler ?? "—"}</span></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Worker Runtime</div><span className={`mt-1 inline-flex rounded-full px-2 py-1 text-[11px] font-semibold ${pill(data?.runtime?.enabled)}`}>{data?.runtime?.enabled ? "ENABLED" : "DISABLED"}</span><div className="mt-1 text-[11px] text-muted-foreground">concurrency {data?.runtime?.maxConcurrency ?? "—"}</div></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Workers</div><div className="mt-1 text-sm font-semibold">{active} active · {accepted} accepted</div><div className="text-[11px] text-muted-foreground">{review} review/rejected</div></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Latest Cycle</div><div className="mt-1 text-sm font-semibold">{data?.cycle ? `${data.cycle.cycleNumber}/${data.cycle.maxCycles}` : "—"}</div><div className="text-[11px] text-muted-foreground">{data?.cycle?.status ?? "No cycle"} · {data?.cycle?.lastAction ?? "—"}</div></div>
      </div>
      <div className="mt-4 rounded-xl border border-border p-3"><div className="flex items-center justify-between gap-2"><div><div className="text-sm font-semibold">Cycle Provenance</div><div className="text-[11px] text-muted-foreground">Research kararından sonraki bounded cycle kararı ve feedback izi</div></div><div className="text-[11px] text-muted-foreground">{data?.telemetry?.returned ?? 0} durable states</div></div>
        {cycles.length ? <div className="mt-3 space-y-2">{cycles.map((cycle) => <div key={`${cycle.cycleId}-${cycle.updatedAt}`} className="rounded-lg bg-muted/40 p-3 text-xs"><div className="grid gap-2 sm:grid-cols-[1.25fr_.7fr_1.1fr_1.8fr] sm:items-center"><div><div className="font-medium">{shortId(cycle.cycleId)}</div><div className="text-[10px] text-muted-foreground">cycle {cycle.cycleNumber}/{cycle.maxCycles} · {time(cycle.updatedAt)}</div></div><div className="font-medium">{cycle.status ?? "—"}</div><div><div>{cycle.lastAction ?? "—"}</div><div className="text-[10px] text-muted-foreground">{cycle.implementationIntent ?? "intent —"}</div></div><div className="text-muted-foreground">{cycle.lastReason ?? "—"}</div></div><div className="mt-2 flex flex-wrap gap-2 text-[10px]"><span className="rounded-full border border-border px-2 py-1">feedback: {cycle.feedbackRecommendation ?? "—"}</span><span className="rounded-full border border-border px-2 py-1">quality: {cycle.patchQualityGrade ?? "—"}{cycle.patchQualityScore != null ? ` (${cycle.patchQualityScore})` : ""}</span><span className="rounded-full border border-border px-2 py-1">retry: {cycle.retryRecommended ? "YES" : "NO"}</span><span className="rounded-full border border-border px-2 py-1">next: {cycle.nextCycleAllowed ? "ALLOWED" : "STOP"}</span>{cycle.workerTaskId ? <span className="rounded-full border border-border px-2 py-1">task: {shortId(cycle.workerTaskId)}</span> : null}</div></div>)}</div> : <div className="mt-3 text-xs text-muted-foreground">Henüz durable cycle geçmişi yok.</div>}
      </div>
    </section>
  );
}
