"use client";

import type { ReactNode } from "react";

interface StoreShellProps {
  crumb: string;
  title: string;
  description: string;
  children: ReactNode;
}

export function StoreShell({
  crumb,
  title,
  description,
  children,
}: StoreShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="flex flex-1 flex-col overflow-hidden">
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
