"use client";

import { useEffect, useState } from "react";
import { Wifi, WifiOff, Cpu } from "lucide-react";

type SystemStatus = "online" | "degraded" | "offline" | "loading";

function useSystemStatus(): SystemStatus {
  const [status, setStatus] = useState<SystemStatus>("loading");
  useEffect(() => {
    let cancelled = false;
    fetch("/api/health", { cache: "no-store" })
      .then((r) => {
        if (cancelled) return;
        if (!r.ok) throw new Error("unreachable");
        return r.json();
      })
      .then(() => {
        if (!cancelled) setStatus("online");
      })
      .catch(() => {
        if (!cancelled) setStatus("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return status;
}

export function TopBar() {
  const status = useSystemStatus();
  const statusColor =
    status === "online"
      ? "text-chart-2"
      : status === "degraded"
        ? "text-chart-5"
        : status === "offline"
          ? "text-destructive"
          : "text-muted-foreground";
  const statusIcon =
    status === "online" ? (
      <Wifi className={`h-3.5 w-3.5 ${statusColor}`} />
    ) : status === "offline" ? (
      <WifiOff className={`h-3.5 w-3.5 ${statusColor}`} />
    ) : (
      <Cpu className={`h-3.5 w-3.5 ${statusColor}`} />
    );

  return (
    <header className="flex h-10 items-center gap-4 border-b border-border bg-card px-4 text-sm text-muted-foreground">
      <div className="flex items-center gap-2 font-bold tracking-tight">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary text-[10px] text-primary-foreground">
          AZ
        </div>
        <span className="text-foreground">AzizBusiness</span>
      </div>
      <nav className="flex items-center gap-1 ml-auto">
        <span className="mr-2 text-[10px] uppercase tracking-widest">Status</span>
        {statusIcon}
        <span className={`text-[10px] uppercase ${statusColor}`}>
          {status === "loading" ? "…" : status}
        </span>
      </nav>
    </header>
  );
}