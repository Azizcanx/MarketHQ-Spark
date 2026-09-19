"use client";

import { useEffect, useMemo, useState } from "react";

type ProviderId = "hermes" | "cursor";
type ProviderState = { hermesEnabled?: boolean; cursorEnabled?: boolean; defaultProvider?: string };
type HermesHealth = { enabled?: boolean; configured?: boolean; reachable?: boolean; baseUrl?: string | null; model?: string | null; error?: string | null };

export function WorkerProviderControl() {
  const [providers, setProviders] = useState<ProviderState>({});
  const [provider, setProvider] = useState<ProviderId>("hermes");
  const [health, setHealth] = useState<HermesHealth | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const response = await fetch("/api/workers?limit=1", { cache: "no-store" });
      const data = await response.json();
      const next = data?.providers ?? {};
      setProviders(next);
      if (next.defaultProvider === "cursor" && next.cursorEnabled) setProvider("cursor");
      else if (next.hermesEnabled) setProvider("hermes");
      else if (next.cursorEnabled) setProvider("cursor");
    } catch {
      setMessage("Provider durumu alınamadı.");
    }
  }

  useEffect(() => { void load(); }, []);

  const enabled = useMemo(() => provider === "hermes" ? providers.hermesEnabled === true : providers.cursorEnabled === true, [provider, providers]);

  async function checkHermes() {
    setChecking(true);
    setMessage("");
    try {
      const response = await fetch("/api/workers?preflight=true&limit=1", { cache: "no-store" });
      const data = await response.json();
      setHealth(data.hermesPreflight ?? null);
      if (!response.ok || !data.success) throw new Error(data.error ?? "Preflight failed");
      setMessage(data.hermesPreflight?.reachable ? "Hermes gateway erişilebilir." : `Hermes hazır değil: ${data.hermesPreflight?.error ?? "erişilemiyor"}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally { setChecking(false); }
  }

  async function run() {
    setBusy(true);
    setMessage("");
    try {
      const runId = `cockpit-${provider}-${Date.now()}`;
      const response = await fetch("/api/workers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ provider, runId, targetPaths: ["frontend/components/workers"], implementationIntent: "ITERATE", decision: { nextResearchQuestion: "Inspect the worker provider integration for one small, safe research-only improvement and report evidence." }, queueTask: { question: "Inspect the worker provider integration for one small, safe research-only improvement and report evidence." }, instructions: "Research-only worker task. Do not trade, access brokers, write databases, modify the main repository, create commits, create PRs, or merge. Work only within the explicit target path. If a safe implementation improvement is clearly justified, make only that focused change and validate it; otherwise report NO_PATCH with evidence.", validationCommand: "npx tsc --noEmit" }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error ?? "Worker dispatch failed");
      setMessage(`${provider.toUpperCase()} worker dispatch edildi: ${data.record?.status ?? "QUEUED"}`);
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs text-muted-foreground">Worker provider routing</p>
          <h2 className="text-lg font-bold">Hermes / Cursor</h2>
          <p className="mt-1 text-xs text-muted-foreground">Gerçek gateway durumu burada kontrol edilir. Worker hâlâ research-only güvenlik katmanında.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={provider} onChange={(event) => setProvider(event.target.value as ProviderId)} className="rounded-xl border border-border bg-background px-3 py-2 text-sm">
            <option value="hermes">Hermes {providers.hermesEnabled ? "· READY" : "· OFF"}</option>
            <option value="cursor">Cursor {providers.cursorEnabled ? "· READY" : "· OFF"}</option>
          </select>
          {provider === "hermes" && <button type="button" onClick={() => void checkHermes()} disabled={checking} className="rounded-xl border border-border px-4 py-2 text-sm font-semibold disabled:opacity-50">{checking ? "Checking…" : "Check Gateway"}</button>}
          <button type="button" onClick={() => void run()} disabled={busy || !enabled} className="rounded-xl border border-border px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Dispatching…" : "Run Worker"}</button>
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Selected</div><div className="mt-1 font-semibold">{provider.toUpperCase()}</div></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Provider gate</div><div className="mt-1 font-semibold">{enabled ? "ENABLED" : "DISABLED"}</div></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Gateway</div><div className="mt-1 font-semibold">{health?.reachable ? "REACHABLE" : health?.configured ? "OFFLINE" : "UNKNOWN"}</div></div>
        <div className="rounded-xl border border-border p-3"><div className="text-[11px] text-muted-foreground">Execution</div><div className="mt-1 font-semibold">BLOCKED</div></div>
      </div>
      {health?.baseUrl && <div className="mt-3 rounded-xl border border-border bg-muted/40 p-3 text-xs">Gateway: {health.baseUrl} · Model: {health.model ?? "configured"}</div>}
      {message && <div className="mt-3 rounded-xl border border-border bg-muted/40 p-3 text-xs">{message}</div>}
    </section>
  );
}
