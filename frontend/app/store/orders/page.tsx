"use client";

import { useCallback, useEffect, useState } from "react";

import {
  DemoBadge,
  ErrorCard,
  LoadingRow,
  NotConfiguredCard,
  StoreNav,
  StoreShell,
  money,
  str,
  useStoreStatus,
} from "../_components";

type Order = Record<string, unknown>;

const STATUS_OPTIONS = ["", "Created", "Picking", "Invoiced", "Shipped", "Delivered", "Cancelled"];

export default function StoreOrdersPage() {
  const status = useStoreStatus();
  const [items, setItems] = useState<Order[]>([]);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextPage: number, nextFilter: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(nextPage), size: "20" });
      if (nextFilter) params.set("status", nextFilter);
      const response = await fetch(`/api/store/orders?${params.toString()}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(str(data.error, "Siparişler alınamadı."));
      setItems(Array.isArray(data.content) ? data.content : []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Siparişler alınamadı.");
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
      crumb="MarketHQ / Commerce / Orders"
      title="Orders"
      description="Sipariş paketleri. Duruma göre filtrele — salt-okunur, onay/kargolama işlemi yok."
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
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTIONS.map((option) => (
              <button
                key={option || "all"}
                type="button"
                onClick={() => {
                  setFilter(option);
                  setPage(0);
                  void load(0, option);
                }}
                className={`rounded-lg px-3 py-1.5 text-sm font-bold ${
                  filter === option
                    ? "bg-slate-900 text-white"
                    : "border border-slate-200 text-slate-600 hover:border-slate-300"
                }`}
              >
                {option || "Tümü"}
              </button>
            ))}
          </div>
          {error && <div className="mt-3"><ErrorCard message={error} /></div>}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-widest text-slate-400">
                  <th className="py-2 pr-3">Sipariş no</th>
                  <th className="py-2 pr-3">Tarih</th>
                  <th className="py-2 pr-3">Müşteri</th>
                  <th className="py-2 pr-3">Durum</th>
                  <th className="py-2 text-right">Tutar</th>
                </tr>
              </thead>
              <tbody>
                {items.map((order, index) => (
                  <tr
                    key={str(order.orderNumber, `row-${index}`)}
                    className="border-b border-slate-50"
                  >
                    <td className="py-2.5 pr-3 font-mono text-xs font-bold">{str(order.orderNumber)}</td>
                    <td className="py-2.5 pr-3 text-slate-500">
                      {str(order.orderDate, "").slice(0, 16).replace("T", " ")}
                    </td>
                    <td className="py-2.5 pr-3">
                      {str(order.customerFirstName, "")} {str(order.customerLastName, "")}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className="inline-block rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-600">
                        {str(order.shipmentPackageStatus, str(order.status))}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-bold">{money(order.totalPrice, str(order.currencyCode, "₺"))}</td>
                  </tr>
                ))}
                {!loading && items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-400">
                      Sipariş bulunamadı.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-xs text-slate-400">Sayfa {page + 1}</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 0 || loading}
                onClick={() => {
                  setPage(page - 1);
                  void load(page - 1, filter);
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 font-bold text-slate-600 disabled:opacity-40"
              >
                ← Önceki
              </button>
              <button
                type="button"
                disabled={loading || items.length < 20}
                onClick={() => {
                  setPage(page + 1);
                  void load(page + 1, filter);
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 font-bold text-slate-600 disabled:opacity-40"
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
