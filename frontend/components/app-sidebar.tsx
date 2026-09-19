"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, ClipboardList, LineChart, LogOut, Package, Settings, ShoppingCart, Store } from "lucide-react";

type NavItem = { label: string; href: string; icon: ComponentType<{ className?: string }> };

const storeItems: NavItem[] = [
  { label: "Store Overview", href: "/store", icon: Store },
  { label: "Products", href: "/store/products", icon: Package },
  { label: "Inventory", href: "/store/inventory", icon: Package },
  { label: "Orders", href: "/store/orders", icon: ShoppingCart },
  { label: "Katalog", href: "/store/catalog", icon: ClipboardList },
  { label: "Finans & Analiz", href: "/store/analytics", icon: LineChart },
  { label: "Agent AI", href: "/store/agentspace", icon: Bot },
];

function isActivePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavButton({ item, pathname }: { item: NavItem; pathname: string }) {
  const Icon = item.icon;
  const active = isActivePath(pathname, item.href);
  return <Link href={item.href} className={["group relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition", active ? "bg-[#171d26] text-[#f3f5f7] shadow-sm before:absolute before:left-0 before:top-2 before:h-5 before:w-0.5 before:rounded-full before:bg-[#f28a42]" : "text-slate-400 hover:bg-[#12171e] hover:text-[#f3f5f7]"].join(" ")}><Icon className={["h-4 w-4 shrink-0", active ? "text-[#f28a42]" : "text-slate-500 group-hover:text-slate-300"].join(" ")} /><span className="truncate transition-colors">{item.label}</span></Link>;
}

export function AppSidebar() {
  const pathname = usePathname();
  function logout() { void fetch("/api/auth/logout", { method: "POST" }).then(() => { window.location.href = "/login"; }); }
  return <aside className="hidden min-h-screen w-[248px] shrink-0 border-r border-[#202631] bg-[#090c11] lg:flex lg:flex-col"><div className="flex h-16 items-center border-b border-[#202631] px-5"><Link href="/store" className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#3a2b20] bg-[#12100d] text-[#f28a42]"><Store className="h-4 w-4" /></div><div><div className="text-sm font-bold tracking-tight text-[#f3f5f7]">MarketHQ</div><div className="text-[9px] font-bold uppercase tracking-[0.2em] text-[#697382]">Commerce</div></div></Link></div><div className="flex-1 space-y-7 overflow-y-auto p-4"><div className="space-y-2"><div className="px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-[#626d7d]">E-Ticaret</div><div className="space-y-1">{storeItems.map((item) => <NavButton key={item.href} item={item} pathname={pathname} />)}</div></div></div><div className="border-t border-[#202631] p-4"><button type="button" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-[#8892a0] transition hover:bg-[#12171e] hover:text-[#f3f5f7]"><Settings className="h-4 w-4" /><span>Settings</span></button><button type="button" onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-[#8892a0] transition hover:bg-[#12171e] hover:text-[#f3f5f7]"><LogOut className="h-4 w-4" /><span>Çıkış</span></button><div className="mt-3 rounded-xl border border-[#1f352a] bg-[#0b1711] px-3 py-2.5"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#58d68d]" /><span className="text-[11px] font-bold text-[#79df9a]">Salt-okunur mod</span></div><div className="mt-1 text-[10px] text-[#659f78]">Sipariş/stok işlemleri kapalı</div></div></div></aside>;
}
