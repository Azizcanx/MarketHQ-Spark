"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

export type TradeChartRow = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20?: number | null;
  ema50?: number | null;
};

export type TradeChartTrade = {
  side?: string | null;
  entry_time?: string | null;
  exit_time?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  stop_price?: number | null;
  target_price?: number | null;
  zone_high?: number | null;
  zone_low?: number | null;
};

type TradeChartProps = {
  rows: TradeChartRow[];
  trade: TradeChartTrade;
};

function closestTime(
  rows: TradeChartRow[],
  target?: string | null
) {
  if (!target || !rows.length) {
    return null;
  }

  const targetTime = new Date(
    String(target).replace(" ", "T")
  ).getTime();

  if (!Number.isFinite(targetTime)) {
    return null;
  }

  let best = rows[0];

  let bestDistance = Math.abs(
    new Date(
      rows[0].timestamp
    ).getTime() - targetTime
  );

  for (const row of rows.slice(1)) {
    const rowTime =
      new Date(
        row.timestamp
      ).getTime();

    const distance =
      Math.abs(
        rowTime - targetTime
      );

    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  }

  return best;
}

function dateToTime(
  value: string
): Time {
  return value.slice(
    0,
    10
  ) as Time;
}

export function TradeChart({
  rows,
  trade,
}: TradeChartProps) {
  const containerRef =
    useRef<HTMLDivElement | null>(
      null
    );

  const chartRef =
    useRef<IChartApi | null>(
      null
    );

  const candleRef =
    useRef<ISeriesApi<"Candlestick"> | null>(
      null
    );

  const ema20Ref =
    useRef<ISeriesApi<"Line"> | null>(
      null
    );

  const ema50Ref =
    useRef<ISeriesApi<"Line"> | null>(
      null
    );

  useEffect(() => {
    const container =
      containerRef.current;

    if (!container || !rows.length) {
      return;
    }

    const chart = createChart(
      container,
      {
        width:
          container.clientWidth,
        height: 520,

        layout: {
          background: {
            color: "#ffffff",
          },
          textColor: "#64748b",
        },

        grid: {
          vertLines: {
            color: "#f1f5f9",
          },
          horzLines: {
            color: "#f1f5f9",
          },
        },

        crosshair: {
          vertLine: {
            color: "#94a3b8",
          },
          horzLine: {
            color: "#94a3b8",
          },
        },

        rightPriceScale: {
          borderColor: "#e2e8f0",
        },

        timeScale: {
          borderColor: "#e2e8f0",
          timeVisible: false,
        },
      }
    );

    chartRef.current = chart;

    const candleSeries =
      chart.addSeries(
        CandlestickSeries,
        {
          borderVisible: false,
          wickVisible: true,

          upColor: "#16a34a",
          downColor: "#dc2626",
          wickUpColor: "#16a34a",
          wickDownColor: "#dc2626",

          lastValueVisible: true,
          priceLineVisible: false,
        }
      );

    const ema20Series =
      chart.addSeries(
        LineSeries,
        {
          color: "#2563eb",
          lineWidth: 2,
          title: "EMA20",

          lastValueVisible: true,
          priceLineVisible: false,
        }
      );

    const ema50Series =
      chart.addSeries(
        LineSeries,
        {
          color: "#111827",
          lineWidth: 2,
          title: "EMA50",

          lastValueVisible: true,
          priceLineVisible: false,
        }
      );

    candleRef.current =
      candleSeries;

    ema20Ref.current =
      ema20Series;

    ema50Ref.current =
      ema50Series;

    const candles = rows
      .filter(
        (row) =>
          Number.isFinite(row.open) &&
          Number.isFinite(row.high) &&
          Number.isFinite(row.low) &&
          Number.isFinite(row.close)
      )
      .map((row) => ({
        time: dateToTime(
          row.timestamp
        ),
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
      }));

    const ema20 = rows
      .filter(
        (row) =>
          row.ema20 !== null &&
          row.ema20 !== undefined &&
          Number.isFinite(row.ema20)
      )
      .map((row) => ({
        time: dateToTime(
          row.timestamp
        ),
        value: Number(row.ema20),
      }));

    const ema50 = rows
      .filter(
        (row) =>
          row.ema50 !== null &&
          row.ema50 !== undefined &&
          Number.isFinite(row.ema50)
      )
      .map((row) => ({
        time: dateToTime(
          row.timestamp
        ),
        value: Number(row.ema50),
      }));

    candleSeries.setData(
      candles
    );

    ema20Series.setData(
      ema20
    );

    ema50Series.setData(
      ema50
    );

    const entryRow =
      closestTime(
        rows,
        trade.entry_time
      );

    const exitRow =
      closestTime(
        rows,
        trade.exit_time
      );

    const markers = [];

    if (entryRow) {
      markers.push({
        time: dateToTime(
          entryRow.timestamp
        ),

        position:
          String(trade.side).toUpperCase() ===
          "SHORT"
            ? "aboveBar"
            : "belowBar",

        color: "#2563eb",

        shape:
          String(trade.side).toUpperCase() ===
          "SHORT"
            ? "arrowDown"
            : "arrowUp",

        text: "ENTRY",
      } as const);
    }

    if (exitRow) {
      markers.push({
        time: dateToTime(
          exitRow.timestamp
        ),

        position:
          String(trade.side).toUpperCase() ===
          "SHORT"
            ? "belowBar"
            : "aboveBar",

        color: "#111827",
        shape: "circle",
        text: "EXIT",
      } as const);
    }

    createSeriesMarkers(
      candleSeries,
      markers
    );

    if (
      trade.entry_price !== null &&
      trade.entry_price !== undefined
    ) {
      candleSeries.createPriceLine({
        price: Number(
          trade.entry_price
        ),
        color: "#2563eb",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "ENTRY",
      });
    }

    if (
      trade.exit_price !== null &&
      trade.exit_price !== undefined
    ) {
      candleSeries.createPriceLine({
        price: Number(
          trade.exit_price
        ),
        color: "#111827",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "EXIT",
      });
    }

    if (
      trade.stop_price !== null &&
      trade.stop_price !== undefined
    ) {
      candleSeries.createPriceLine({
        price: Number(
          trade.stop_price
        ),
        color: "#dc2626",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "SL",
      });
    }

    if (
      trade.target_price !== null &&
      trade.target_price !== undefined
    ) {
      candleSeries.createPriceLine({
        price: Number(
          trade.target_price
        ),
        color: "#16a34a",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "TP",
      });
    }

    if (
      trade.zone_high !== null &&
      trade.zone_high !== undefined &&
      trade.zone_low !== null &&
      trade.zone_low !== undefined
    ) {
      for (const [px, title] of [
        [trade.zone_high, "ZONE_HI"],
        [trade.zone_low, "ZONE_LO"],
      ] as const) {
        candleSeries.createPriceLine({
          price: Number(px),
          color: "#8b5cf6",
          lineWidth: 1,
          lineStyle: 3,
          axisLabelVisible: true,
          title,
        });
      }
    }

    chart
      .timeScale()
      .fitContent();

    const resizeObserver =
      new ResizeObserver(() => {
        if (
          !containerRef.current ||
          !chartRef.current
        ) {
          return;
        }

        chartRef.current.applyOptions({
          width:
            containerRef.current
              .clientWidth,
        });
      });

    resizeObserver.observe(
      container
    );

    return () => {
      resizeObserver.disconnect();

      chart.remove();

      chartRef.current = null;
      candleRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
    };
  }, [rows, trade]);

  return (
    <div
      ref={containerRef}
      className="h-[520px] w-full overflow-hidden rounded-xl"
    />
  );
}
