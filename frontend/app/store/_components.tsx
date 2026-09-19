"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, FlaskConical, Loader2, LockKeyhole, Store as StoreIcon } from "lucide-react";

import { AppSidebar } from "@/components/app-sidebar";
import { Topbar } from "@/components/topbar";

export type StoreStatus =
  | { success: true; configured: false; source?: "live" | "mock"; message?: string }
  | {
      success: true;
      configured: true;
      reachable: boolean;
      source?: "live" | "mock";
      sellerId?: string;
      productTotal?: number;
      orderTotal?: number;
      error?: string;
    }
  | { success: false; configured?: boolean; source?: "live" | "mock"; error?: string; message?: string };

export function useStoreStatus() {
  const [status, setStatus] = useState<StoreStatus | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/store/status", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setStatus(data as StoreStatus);
      })
      .catch(() => {
        if (!cancelled) setStatus({ success: false, error: "STATUS_FETCH_FAILED" });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return status;
}

export function str(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

export function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && !Number.isNaN(Number(value))) return Number(value);
  return null;
}

export function money(value: unknown, currency = "₺"): string {
  const parsed = num(value);
  if (parsed === null) return "—";
  return `${parsed.toLocaleString("tr-TR", { maximumFractionDigits: 2 })} ${currency}`;
}

export function StoreShell({
  crumb,
  title,
  description,
  children,
}: {
  crumb: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-background">
      <AppSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex flex-1 flex-col overflow-y-auto p-4 md:p-6">
          <div className="mb-4 flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              {crumb}
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {description}
          </p>
          <div className="mt-4">{children}</div>
        </main>
      </div>
    </div>
  );
}

export function NotConfiguredCard() {
  return (
    <div className="rounded-2xl border border-amber-900/50 bg-amber-950/30 p-5">
      <div className="flex items-center gap-2 text-sm font-bold text-amber-300">
        <AlertTriangle className="h-4 w-4" /> Trendyol bağlantısı yok
      </div>
      <p className="mt-2 text-sm leading-6 text-amber-200/70">
        Satıcı bilgileri tanımlı değil (Seller ID / API Key / API Secret). Bilgiler girilene kadar
        mağaza sayfaları salt-görünür bekleme modunda.
      </p>
      <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-400/70">
        <LockKeyhole className="h-3.5 w-3.5" /> Salt-okunur · yazma işlemi yok
      </p>
    </div>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-900/60 bg-violet-950/40 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-violet-300">
      <FlaskConical className="h-3.5 w-3.5" /> Demo verisi · mock provider (canlı Trendyol bağlı değil)
    </span>
  );
}

export function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorCard({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">{message}</div>
  );
}

export function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-black tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function StoreNav() {
  const links = [
    { href: "/store", label: "Overview" },
    { href: "/store/products", label: "Products" },
    { href: "/store/inventory", label: "Inventory" },
    { href: "/store/orders", label: "Orders" },
    { href: "/store/catalog", label: "Katalog" },
    { href: "/store/analytics", label: "Finans & Analiz" },
    { href: "/store/agentspace", label: "Agent AI" },
  ];
  return (
    <nav className="flex flex-wrap gap-2">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}