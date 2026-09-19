"use client";

import { useEffect, useState } from "react";

type ModeState = { enabled: boolean; updatedAt?: string; updatedBy?: string };

export function AutonomousModeControl() {
  const [mode, setMode] = useState<ModeState>({ enabled: false });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    try {
      const response = await fetch("/api/automation/mode", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.success === false) throw new Error(payload.error ?? `HTTP ${response.status}`);
      setMode(payload.mode ?? { enabled: false });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Autonomous mode okunamadı.");
    }
  }

  async function toggle() {
    if (busy) return;
    setBusy(true); setMessage(null);
    try {
      const next = !mode.enabled;
      const response = await fetch("/api/automation/mode", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ enabled: next, updatedBy: "PANEL" }) });
      const payload = await response.json();
      if (!response.ok || payload.success === false) throw new Error(payload.error ?? `HTTP ${response.status}`);
      setMode(payload.mode ?? { enabled: next });
      setMessage(next ? "Autonomous Mode açıldı. Scheduler yalnızca bounded research cycle çalıştırır." : "Autonomous Mode kapatıldı.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Autonomous mode değiştirilemedi.");
    } finally { setBusy(false); }
  }

  useEffect(() => { void load(); }, []);

  return <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Autonomous Operations</p>
        <h3 className="mt-1 text-lg font-bold">Autonomous Mode</h3>
        <p className="mt-1 text-xs text-muted-foreground">Research → Decision → Worker → Validation → Feedback. Live trading ve automatic merge bu kontrolden açılmaz.</p>
      </div>
      <button type="button" onClick={() => void toggle()} disabled={busy} aria-pressed={mode.enabled} className={`rounded-xl px-5 py-3 text-sm font-bold text-white disabled:opacity-50 ${mode.enabled ? "bg-emerald-600" : "bg-slate-900"}`}>
        {busy ? "..." : mode.enabled ? "AUTONOMOUS ON" : "AUTONOMOUS OFF"}
      </button>
    </div>
    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
      <span className="rounded-full bg-muted px-2 py-1">Research only</span>
      <span className="rounded-full bg-muted px-2 py-1">Execution OFF</span>
      <span className="rounded-full bg-muted px-2 py-1">PR/Merge OFF</span>
      {mode.updatedAt && <span className="rounded-full bg-muted px-2 py-1">Updated {new Date(mode.updatedAt).toLocaleString()}</span>}
    </div>
    {message && <p className="mt-3 text-xs text-muted-foreground">{message}</p>}
  </div>;
}
