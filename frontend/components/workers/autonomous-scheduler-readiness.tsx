"use client";

import { useEffect, useState } from "react";

type Readiness = {
  scheduler?: string;
  mode?: { enabled?: boolean };
  configuration?: { automationSecretConfigured?: boolean; externalUrlConfigured?: boolean; externalSchedulerOptIn?: boolean };
  telemetry?: { returned?: number; latestUpdatedAt?: string | null };
};

function Status({ value, label }: { value?: boolean; label: string }) {
  return <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-xs"><span>{label}</span><span className={`rounded-full px-2 py-1 font-semibold ${value ? "bg-emerald-100 text-emerald-700" : "bg-muted text-muted-foreground"}`}>{value ? "READY" : "NOT SET"}</span></div>;
}

export function AutonomousSchedulerReadiness() {
  const [data, setData] = useState<Readiness | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const response = await fetch("/api/automation/cycle?limit=1", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setData(await response.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scheduler readiness okunamadı.");
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, []);

  const config = data?.configuration;
  const externallyReady = Boolean(config?.automationSecretConfigured && config?.externalUrlConfigured);
  const active = data?.scheduler === "ENABLED";

  return <section className="rounded-2xl border border-border bg-card p-4 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-xs text-muted-foreground">External automation handoff</p><h2 className="text-lg font-semibold">Scheduler Readiness</h2><p className="mt-1 text-xs text-muted-foreground">Chat dışı tetikleme için deployment tarafındaki son eksikleri gösterir.</p></div>
      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${active ? "bg-emerald-100 text-emerald-700" : "bg-muted text-muted-foreground"}`}>{active ? "ENABLED" : "OFF"}</span>
    </div>
    {error ? <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">{error}</div> : <>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Status value={config?.automationSecretConfigured} label="Automation secret" />
        <Status value={config?.externalUrlConfigured} label="Automation URL" />
        <Status value={config?.externalSchedulerOptIn} label="External scheduler opt-in" />
        <Status value={data?.mode?.enabled} label="Persistent autonomous mode" />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span>{externallyReady ? "Deployment handoff configured." : "Deployment configuration still required."}</span>
        <span>·</span><span>{data?.telemetry?.returned ?? 0} durable cycle state</span>
        {data?.telemetry?.latestUpdatedAt ? <><span>·</span><span>last {new Date(data.telemetry.latestUpdatedAt).toLocaleString()}</span></> : null}
      </div>
    </>}
  </section>;
}
