import type { ReactNode } from "react";
import { Terminal, Search, Brain, AlertCircle, FileStack } from "lucide-react";

type Tab =
  | "agents"
  | "research"
  | "brain"
  | "logs"
  | "errors";

interface BottomTerminalProps {
  children: ReactNode;
}

const TABS: { id: Tab; icon: typeof Terminal; label: string }[] = [
  { id: "agents", icon: Terminal, label: "Agents" },
  { id: "research", icon: Search, label: "Research" },
  { id: "brain", icon: Brain, label: "Brain" },
  { id: "logs", icon: FileStack, label: "Logs" },
  { id: "errors", icon: AlertCircle, label: "Errors" },
];

export function BottomTerminal({ children }: BottomTerminalProps) {
  return (
    <div className="flex flex-col border-t border-border bg-card min-h-[160px]">
      <div className="flex items-center gap-1 border-b border-border bg-muted px-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className="flex items-center gap-1.5 rounded-t px-2 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <tab.icon className="h-3 w-3" />
            {tab.label}
          </button>
        ))}
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        {children}
      </div>
    </div>
  );
}

export function TerminalLogLine({
  children,
  type,
}: {
  children: ReactNode;
  type?: "info" | "warn" | "error";
}) {
  const color =
    type === "error"
      ? "text-destructive"
      : type === "warn"
        ? "text-chart-5"
        : "text-muted-foreground";
  return (
    <div className={`flex items-start gap-2 px-3 py-0.5 text-[11px] leading-relaxed ${color}`}>
      {children}
    </div>
  );
}
