"use client";

import { Bell, Menu, Search, ShieldCheck, Wifi } from "lucide-react";

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#202631] bg-[#080a0f]/95 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <button type="button" className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#252c37] text-[#8b95a3] lg:hidden" aria-label="Open navigation"><Menu className="h-4 w-4" /></button>
        <div className="hidden items-center gap-3 md:flex"><div className="rounded-lg border border-[#252c37] bg-[#0d1118] p-2"><Search className="h-4 w-4 text-[#707b8b]" /></div><span className="font-mono text-[11px] tracking-wide text-[#5f6978]">Ürün, barkod ve sipariş ara...</span></div>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-full border border-[#26382d] bg-[#0d1711] px-3 py-1.5 sm:flex"><ShieldCheck className="h-3.5 w-3.5 text-[#58d68d]" /><span className="font-mono text-[10px] font-bold tracking-[0.12em] text-[#79df9a]">READ ONLY</span></div>
        <div className="hidden items-center gap-2 rounded-full border border-[#252c37] bg-[#0d1118] px-3 py-1.5 sm:flex"><Wifi className="h-3.5 w-3.5 text-[#58d68d]" /><span className="font-mono text-[10px] font-bold tracking-[0.12em] text-[#8d97a5]">STORE ONLINE</span></div>
        <button type="button" className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[#252c37] text-[#7f8998] transition hover:bg-[#151a22] hover:text-[#f3f5f7]" aria-label="Notifications"><Bell className="h-4 w-4" /><span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-[#58d68d]" /></button>
      </div>
    </header>
  );
}
