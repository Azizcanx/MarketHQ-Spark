"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function StoreNav() {
  const pathname = usePathname();

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
      {links.map((link) => {
        const isActive = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
              isActive
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
