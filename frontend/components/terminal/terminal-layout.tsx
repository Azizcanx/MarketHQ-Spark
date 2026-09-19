"use client";

import { ReactNode } from "react";
import { TopBar } from "./top-bar";
import { LeftSidebar } from "./left-sidebar";
import { RightPanel, MarketStateCard, ActiveSetupsCard, AgentActivityCard, ResearchStatusCard, AlertsCard } from "./right-panel";
import { BottomTerminal, TerminalLogLine } from "./bottom-terminal";

interface TerminalLayoutProps {
  children: ReactNode;
  rightPanel?: ReactNode;
  bottomChildren?: ReactNode;
}

export function TerminalLayout({ children, rightPanel, bottomChildren }: TerminalLayoutProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <LeftSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <div className="mx-auto max-w-[1700px]">{children}</div>
          </main>
          {rightPanel && (
            <aside className="hidden w-72 shrink-0 border-l border-border bg-card overflow-y-auto lg:block">
              <div className="p-3 space-y-3">{rightPanel}</div>
            </aside>
          )}
        </div>
        <BottomTerminal>{bottomChildren}</BottomTerminal>
      </div>
    </div>
  );
}

export { RightPanel, MarketStateCard, ActiveSetupsCard, AgentActivityCard, ResearchStatusCard, AlertsCard, BottomTerminal, TerminalLogLine };