"use client";

import type { ReactNode } from "react";

interface LoadingRowProps {
  label: string;
}

export function LoadingRow({ label }: LoadingRowProps) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      {label}
    </div>
  );
}
