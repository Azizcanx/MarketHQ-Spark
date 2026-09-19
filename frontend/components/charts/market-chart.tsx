"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

export type MarketBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20?: number | null;
  ema50?: number | null;
};

type MarketChartProps = {
  rows: MarketBar[];
};

function dateToTime(value: string): Time {
  return value.slice(0, 10) as Time;
}

export function MarketChart({
  rows,
}: MarketChartProps) {
  const containerRef =
    useRef<HTMLDivElement | null>(null);

  const chartRef =
    useRef<IChartApi | null>(null);

  const candleRef =
    useRef<ISeriesApi<"Candlestick"> | null>(null);

  const ema20Ref =
    useRef<ISeriesApi<"Line"> | null>(null);

  const ema50Ref =
    useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    const container =
      containerRef.current;

    if (!container || !rows.length) {
      return;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,

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
    });

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
  }, [rows]);

  return (
    <div
      ref={containerRef}
      className="h-[500px] w-full overflow-hidden rounded-xl"
    />
  );
}
