import type { ReactNode } from "react";

interface RightPanelProps {
  children: ReactNode;
}

export function RightPanel({ children }: RightPanelProps) {
  return (
    <aside className="flex min-h-0 flex-1 flex-col border-l border-border bg-card overflow-y-auto">
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </aside>
  );
}

export function MarketStateCard({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2 border-b border-border px-3 py-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        Market State
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

export function ActiveSetupsCard({ children }: { children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-b border-border px-3 py-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        Active Setups
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

export function AgentActivityCard({ children }: { children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-b border-border px-3 py-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        Agent Activity
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

export function ResearchStatusCard({ children }: { children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-b border-border px-3 py-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        Research Status
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

export function AlertsCard({ children }: { children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-b border-border px-3 py-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        Alerts
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}
