"use client";

import { Suspense, useEffect, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setupMode, setSetupMode] = useState(false);

  useEffect(() => {
    fetch("/api/auth/login", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setSetupMode(!d.configured))
      .catch(() => setSetupMode(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user, password }),
      });
      const data = await response.json();
      if (!response.ok || data.success !== true) {
        setError(data.error === "TOO_MANY_ATTEMPTS" ? "Çok fazla deneme — 1 dk bekleyin."
          : data.error === "AUTH_NOT_CONFIGURED" ? "Yönetici tanımlı değil — sunucuda kurulum komutunu çalıştırın."
          : "Kullanıcı adı veya şifre hatalı.");
        return;
      }
      router.replace(params.get("next") || "/store");
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-6 shadow-lg">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#3a2b20] bg-[#12100d] text-[#f28a42]"><KeyRound className="h-4 w-4" /></div>
          <div>
            <div className="text-sm font-black tracking-tight">MarketHQ Commerce</div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Yönetici girişi</div>
          </div>
        </div>
        {setupMode ? (
          <div className="rounded-xl border border-amber-900/50 bg-amber-950/30 p-4 text-xs leading-6 text-amber-200/80">
            Yönetici hesabı tanımlı değil. Sunucuda şu komutu çalıştır:
            <pre className="mt-2 overflow-x-auto rounded-lg bg-black/40 p-2 text-[10px] text-amber-300">cd /opt/markethq && node scripts/set-admin-password.mjs</pre>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" required
              placeholder="Kullanıcı adı" className="w-full rounded-xl border border-input bg-background px-3 py-2.5 text-sm focus:border-ring focus:outline-none" />
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required
              placeholder="Şifre" className="w-full rounded-xl border border-input bg-background px-3 py-2.5 text-sm focus:border-ring focus:outline-none" />
            {error && <div className="rounded-xl border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</div>}
            <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Giriş yap
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense fallback={null}><LoginForm /></Suspense>;
}
