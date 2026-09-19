"use client";

import { useEffect, useMemo, useState } from "react";

import {
  DemoBadge,
  ErrorCard,
  LoadingRow,
  NotConfiguredCard,
  StoreNav,
  StoreShell,
  money,
  num,
  str,
  useStoreStatus,
} from "../_components";

type Product = Record<string, unknown>;
const LOW_STOCK_AT = 5;

export default function StoreInventoryPage() {
  const status = useStoreStatus();
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onlyLow, setOnlyLow] = useState(false);

  useEffect(() => {
    if (!(status?.success && status.configured && status.reachable)) return;
    let cancelled = false;
    setLoading(true);
    fetch("/api/store/products?page=0&size=50", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.success === false) throw new Error(str(data.error, "Stok alınamadı."));
        setItems(Array.isArray(data.content) ? data.content : []);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Stok alınamadı.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const rows = useMemo(() => {
    const mapped = items.map((item) => ({ item, stock: num(item.quantity) ?? 0 }));
    mapped.sort((a, b) => a.stock - b.stock);
    return onlyLow ? mapped.filter((row) => row.stock <= LOW_STOCK_AT) : mapped;
  }, [items, onlyLow]);

  const lowCount = useMemo(() => items.filter((i) => (num(i.quantity) ?? 0) <= LOW_STOCK_AT).length, [items]);
  const configured = status?.success && status.configured && status.reachable;

  return (
    <StoreShell
      crumb="MarketHQ / Commerce / Inventory"
      title="Inventory"
      description="Stok seviyeleri düşükten yükseğe. Kritik eşik 5 adet — salt-okunur, stok güncellenemez."
    >
      <StoreNav />
      {status?.source === "mock" && <div className="mt-4"><DemoBadge /></div>}
      {!status && <LoadingRow label="Yükleniyor…" />}
      {status?.success && !status.configured && <NotConfiguredCard />}
      {status?.success && status.configured && !status.reachable && (
        <ErrorCard message={`Trendyol'a erişilemedi: ${str(status.error)}.`} />
      )}
      {configured && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-sm text-slate-500">
              {items.length} ürün · <span className="font-bold text-rose-600">{lowCount} kritik stok</span>
            </span>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-600">
              <input
                type="checkbox"
                checked={onlyLow}
                onChange={(event) => setOnlyLow(event.target.checked)}
                className="h-4 w-4 accent-rose-600"
              />
              Sadece kritik stok
            </label>
          </div>
          {error && <div className="mt-3"><ErrorCard message={error} /></div>}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-widest text-slate-400">
                  <th className="py-2 pr-3">Ürün</th>
                  <th className="py-2 pr-3">Barkod</th>
                  <th className="py-2 pr-3 text-right">Stok</th>
                  <th className="py-2 pr-3">Durum</th>
                  <th className="py-2 text-right">Satış fiyatı</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ item, stock }, index) => (
                  <tr key={str(item.barcode, `row-${index}`)} className="border-b border-slate-50">
                    <td className="max-w-[320px] truncate py-2.5 pr-3 font-bold">{str(item.title)}</td>
                    <td className="py-2.5 pr-3 font-mono text-xs text-slate-500">{str(item.barcode)}</td>
                    <td className="py-2.5 pr-3 text-right font-black">{stock}</td>
                    <td className="py-2.5 pr-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          stock === 0
                            ? "bg-rose-100 text-rose-700"
                            : stock <= LOW_STOCK_AT
                              ? "bg-amber-100 text-amber-700"
                              : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {stock === 0 ? "Tükendi" : stock <= LOW_STOCK_AT ? "Kritik" : "Normal"}
                      </span>
                    </td>
                    <td className="py-2.5 text-right">{money(item.salePrice)}</td>
                  </tr>
                ))}
                {!loading && rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-400">
                      Gösterilecek ürün yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-400">Not: ilk 50 ürün üzerinden hesaplanır.</p>
        </section>
      )}
    </StoreShell>
  );
}
