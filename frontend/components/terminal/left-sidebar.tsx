"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Globe, Brain, GitFork, Users, FileQuestion, Briefcase, BarChart3, Settings } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", icon: Globe, label: "Markets" },
  { href: "/research", icon: FileQuestion, label: "Research" },
  { href: "/strategies", icon: GitFork, label: "Strategies" },
  { href: "/agents", icon: Users, label: "Agents" },
  { href: "/runs", icon: Briefcase, label: "Runs" },
  { href: "/brain", icon: Brain, label: "Brain" },
  { href: "/learning", icon: BarChart3, label: "Memory" },
];

export function LeftSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 overflow-y-auto border-r border-border bg-sidebar p-2">
      {NAV_ITEMS.map((item) => {
        const active = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
              ${active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/60"
              }
              ${!active ? "hover:text-sidebar-foreground" : ""}
            `}
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
          </Link>
        );
      })}
      <div className="mt-4 mt-auto border-t border-border pt-4">
        <Link
          href="/settings"
          className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
            ${pathname.startsWith("/settings")
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-sidebar-foreground hover:bg-sidebar-accent/60"
            }
          `}
        >
          <Settings className="h-4 w-4 shrink-0" />
          Settings
        </Link>
      </div>
    </nav>
  );
}
