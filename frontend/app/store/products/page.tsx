"use client";

import { useCallback, useEffect, useState } from "react";
import { Search } from "lucide-react";

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

export default function StoreProductsPage() {
  const status = useStoreStatus();
  const [items, setItems] = useState<Product[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextPage: number, barcode: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(nextPage), size: "20" });
      if (barcode.trim()) params.set("barcode", barcode.trim());
      const response = await fetch(`/api/store/products?${params.toString()}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(str(data.error, "Ürünler alınamadı."));
      setItems(Array.isArray(data.content) ? data.content : []);
      setTotal(num(data.totalElements));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ürünler alınamadı.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (status?.success && status.configured && status.reachable) void load(0, "");
  }, [status, load]);

  const configured = status?.success && status.configured && status.reachable;

  return (
    <StoreShell
      crumb="MarketHQ / Commerce / Products"
      title="Products"
      description="Onaylı Trendyol ürünleri. Barkod ile ara, sayfala — salt-okunur."
    >
      <StoreNav />
      {status?.source === "mock" && <div className="mt-4"><DemoBadge /></div>}
      {!status && <LoadingRow label="Yükleniyor…" />}
      {status?.success && !status.configured && <NotConfiguredCard />}
      {status?.success && status.configured && !status.reachable && (
        <ErrorCard message={`Trendyol'a erişilemedi: ${str(status.error)}.`} />
      )}
      {configured && (
        <section className="rounded-2xl border border-border bg-card p-5">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setPage(0);
              setAppliedQuery(query);
              void load(0, query);
            }}
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Barkod ile ara…"
                className="w-full rounded-xl border border-input bg-background py-2.5 pl-9 pr-3 text-sm focus:border-ring focus:outline-none"
              />
            </div>
            <button
              type="submit"
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90"
            >
              Ara
            </button>
          </form>
          {error && <div className="mt-3"><ErrorCard message={error} /></div>}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-[10px] uppercase tracking-widest text-muted-foreground">
                  <th className="py-2 pr-3">Ürün</th>
                  <th className="py-2 pr-3">Marka</th>
                  <th className="py-2 pr-3">Barkod</th>
                  <th className="py-2 pr-3 text-right">Stok</th>
                  <th className="py-2 pr-3 text-right">Satış</th>
                  <th className="py-2 text-right">Liste</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr key={str(item.barcode, `row-${index}`)} className="border-b border-border/50">
                    <td className="max-w-[320px] truncate py-2.5 pr-3 font-bold">{str(item.title)}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{str(item.brand)}</td>
                    <td className="py-2.5 pr-3 font-mono text-xs text-muted-foreground">{str(item.barcode)}</td>
                    <td className="py-2.5 pr-3 text-right font-bold">{str(item.quantity, "0")}</td>
                    <td className="py-2.5 pr-3 text-right">{money(item.salePrice)}</td>
                    <td className="py-2.5 text-right text-muted-foreground">{money(item.listPrice)}</td>
                  </tr>
                ))}
                {!loading && items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-muted-foreground">
                      {appliedQuery ? "Sonuç yok." : "Ürün bulunamadı."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-xs text-muted-foreground">
              Sayfa {page + 1}
              {total !== null ? ` · toplam ${total}` : ""}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 0 || loading}
                onClick={() => {
                  setPage(page - 1);
                  void load(page - 1, appliedQuery);
                }}
                className="rounded-lg border border-border px-3 py-1.5 font-bold text-muted-foreground disabled:opacity-40"
              >
                ← Önceki
              </button>
              <button
                type="button"
                disabled={loading || items.length < 20}
                onClick={() => {
                  setPage(page + 1);
                  void load(page + 1, appliedQuery);
                }}
                className="rounded-lg border border-border px-3 py-1.5 font-bold text-muted-foreground disabled:opacity-40"
              >
                Sonraki →
              </button>
            </div>
          </div>
        </section>
      )}
    </StoreShell>
  );
}