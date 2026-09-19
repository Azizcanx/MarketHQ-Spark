"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type MarketEvent = {
  event: string;
  data: unknown;
  event_id: string;
  timestamp: string;
};

export type MarketState = {
  symbol: string;
  binance_symbol: string;
  price: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  timeframe: string;
  timestamp: string | null;
  data_source: string;
  last_update: string;
};

export type MarketDataStatus =
  | { state: "idle" }
  | { state: "connecting" }
  | { state: "connected"; connected: boolean }
  | { state: "error"; error: string };

export function useMarketData() {
  const [status, setStatus] = useState<MarketDataStatus>({ state: "idle" });
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [marketState, setMarketState] = useState<MarketState[]>([]);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const staleTimerRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setStatus({ state: "connecting" });

    try {
      const es = new EventSource("/api/market-events");

      es.onopen = () => {
        setStatus({ state: "connected", connected: true });
        setIsStale(false);
        if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
        staleTimerRef.current = setTimeout(() => setIsStale(true), 120_000);
      };

      es.addEventListener("MARKET_UPDATE", (e) => {
        try {
          const data = JSON.parse(e.data);
          const event: MarketEvent = {
            event: "MARKET_UPDATE",
            data,
            event_id: `mkt-${Date.now()}`,
            timestamp: data.timestamp || new Date().toISOString(),
          };
          setEvents((prev) => [...prev.slice(-49), event]);
          setLastUpdate(event.timestamp);
          setIsStale(false);
          if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
          staleTimerRef.current = setTimeout(() => setIsStale(true), 120_000);
        } catch {
          // ignore parse errors
        }
      });

      es.addEventListener("MARKET_STATUS", (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.status === "disconnected") {
            setStatus({ state: "error", error: "DISCONNECTED" });
          }
        } catch {
          // ignore
        }
      });

      es.onerror = () => {
        setStatus({ state: "error", error: "DISCONNECTED" });
        setIsStale(true);
      };

      eventSourceRef.current = es;
    } catch {
      setStatus({ state: "error", error: "DISCONNECTED" });
    }
  }, []);

  // Fetch market state on mount and periodically
  const fetchMarketState = useCallback(async () => {
    try {
      const res = await fetch("/api/market-state", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success && Array.isArray(data.market_state)) {
        setMarketState(data.market_state);
        setLastUpdate(data.requested_at || null);
        setIsStale(data.is_stale || false);
      }
    } catch {
      // API unreachable — status already reflects error
    }
  }, []);

  useEffect(() => {
    connect();
    fetchMarketState();
    const stateInterval = setInterval(fetchMarketState, 60_000);
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      clearInterval(stateInterval);
    };
  }, [connect, fetchMarketState]);

  return {
    status,
    events,
    marketState,
    lastUpdate,
    isStale,
    reconnect: connect,
    refresh: fetchMarketState,
  };
}