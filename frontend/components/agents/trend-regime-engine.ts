export type TrendDirection =
  | "UP"
  | "DOWN"
  | "SIDEWAYS"
  | "UNKNOWN";

export type MomentumState =
  | "POSITIVE"
  | "NEGATIVE"
  | "NEUTRAL"
  | "UNKNOWN";

export type VolatilityState =
  | "LOW"
  | "NORMAL"
  | "HIGH"
  | "UNKNOWN";

export type MarketRegime =
  | "TRENDING_UP"
  | "TRENDING_DOWN"
  | "RANGE_BOUND"
  | "HIGH_VOLATILITY"
  | "TRANSITION"
  | "UNKNOWN";

export type Confidence =
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "UNKNOWN";

export interface TrendRegimeBar {
  timestamp?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface TrendRegimeSnapshot {
  timestamp: string | null;
  close: number | null;

  trendDirection: TrendDirection;
  trendStrength: number;
  trendScore: number;

  momentum: MomentumState;
  momentumScore: number;

  volatility: VolatilityState;
  volatilityScore: number;

  marketRegime: MarketRegime;

  evidenceScore: number;
  confidence: Confidence;

  indicators: {
    ema20: number | null;
    ema50: number | null;
    ema200: number | null;
    atr14: number | null;
    atrPercent: number | null;
    atrPercentile: number | null;
    roc20Percent: number | null;
    rsi14: number | null;
    adx14: number | null;
    slope20Percent: number | null;
    volumeRatio: number | null;
  };

  evidence: string[];
  warnings: string[];
}

export interface TrendRegimeEngineResult {
  engine: "MARKETHQ_TREND_REGIME_ENGINE_V1";
  status: "READY" | "PARTIAL" | "INSUFFICIENT_DATA";
  symbol: string | null;
  timeframe: string | null;
  barsUsed: number;
  minimumBarsRequired: number;
  snapshot: TrendRegimeSnapshot;
  researchOnly: true;
  lookAheadSafe: true;
}

const MINIMUM_BARS = 220;

function finite(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

function clamp(
  value: number,
  min: number,
  max: number,
): number {
  return Math.min(max, Math.max(min, value));
}

function round(
  value: number | null,
  digits = 4,
): number | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  const factor = 10 ** digits;

  return Math.round(value * factor) / factor;
}

function mean(values: number[]): number | null {
  if (!values.length) {
    return null;
  }

  return (
    values.reduce(
      (sum, value) => sum + value,
      0,
    ) / values.length
  );
}

function percentileRank(
  values: number[],
  current: number,
): number | null {
  if (!values.length) {
    return null;
  }

  let belowOrEqual = 0;

  for (const value of values) {
    if (value <= current) {
      belowOrEqual += 1;
    }
  }

  return (
    belowOrEqual /
    values.length
  ) * 100;
}

function calculateEma(
  values: number[],
  period: number,
): number | null {
  if (values.length < period) {
    return null;
  }

  const seed =
    mean(
      values.slice(
        0,
        period,
      ),
    );

  if (seed === null) {
    return null;
  }

  const multiplier =
    2 / (period + 1);

  let ema = seed;

  for (
    let index = period;
    index < values.length;
    index += 1
  ) {
    ema =
      (
        values[index] -
        ema
      ) *
        multiplier +
      ema;
  }

  return ema;
}

function calculateRsi(
  values: number[],
  period = 14,
): number | null {
  if (
    values.length <
    period + 1
  ) {
    return null;
  }

  let gain = 0;
  let loss = 0;

  for (
    let index = 1;
    index <= period;
    index += 1
  ) {
    const change =
      values[index] -
      values[index - 1];

    if (change > 0) {
      gain += change;
    } else {
      loss += Math.abs(change);
    }
  }

  let averageGain =
    gain / period;

  let averageLoss =
    loss / period;

  for (
    let index = period + 1;
    index < values.length;
    index += 1
  ) {
    const change =
      values[index] -
      values[index - 1];

    const currentGain =
      change > 0
        ? change
        : 0;

    const currentLoss =
      change < 0
        ? Math.abs(change)
        : 0;

    averageGain =
      (
        averageGain *
          (period - 1) +
        currentGain
      ) / period;

    averageLoss =
      (
        averageLoss *
          (period - 1) +
        currentLoss
      ) / period;
  }

  if (averageLoss === 0) {
    return 100;
  }

  const relativeStrength =
    averageGain /
    averageLoss;

  return (
    100 -
    100 /
      (1 + relativeStrength)
  );
}

function calculateAtrSeries(
  bars: TrendRegimeBar[],
  period = 14,
): number[] {
  if (
    bars.length <
    period + 1
  ) {
    return [];
  }

  const trueRanges: number[] = [];

  for (
    let index = 0;
    index < bars.length;
    index += 1
  ) {
    const bar = bars[index];

    if (
      !finite(bar.high) ||
      !finite(bar.low) ||
      !finite(bar.close)
    ) {
      continue;
    }

    if (index === 0) {
      trueRanges.push(
        bar.high - bar.low,
      );
      continue;
    }

    const previousClose =
      bars[index - 1].close;

    if (!finite(previousClose)) {
      continue;
    }

    trueRanges.push(
      Math.max(
        bar.high - bar.low,
        Math.abs(
          bar.high -
            previousClose,
        ),
        Math.abs(
          bar.low -
            previousClose,
        ),
      ),
    );
  }

  if (
    trueRanges.length <
    period
  ) {
    return [];
  }

  const result: number[] = [];

  let atr =
    mean(
      trueRanges.slice(
        0,
        period,
      ),
    );

  if (atr === null) {
    return [];
  }

  result.push(atr);

  for (
    let index = period;
    index < trueRanges.length;
    index += 1
  ) {
    atr =
      (
        atr *
          (period - 1) +
        trueRanges[index]
      ) / period;

    result.push(atr);
  }

  return result;
}

function calculateAdx(
  bars: TrendRegimeBar[],
  period = 14,
): number | null {
  if (
    bars.length <
    period * 2 + 1
  ) {
    return null;
  }

  const tr: number[] = [];
  const plusDm: number[] = [];
  const minusDm: number[] = [];

  for (
    let index = 1;
    index < bars.length;
    index += 1
  ) {
    const current =
      bars[index];
    const previous =
      bars[index - 1];

    const highMove =
      current.high -
      previous.high;

    const lowMove =
      previous.low -
      current.low;

    const upMove =
      highMove > lowMove &&
      highMove > 0
        ? highMove
        : 0;

    const downMove =
      lowMove > highMove &&
      lowMove > 0
        ? lowMove
        : 0;

    const range =
      Math.max(
        current.high -
          current.low,
        Math.abs(
          current.high -
            previous.close,
        ),
        Math.abs(
          current.low -
            previous.close,
        ),
      );

    tr.push(range);
    plusDm.push(upMove);
    minusDm.push(downMove);
  }

  if (tr.length < period) {
    return null;
  }

  let smoothedTr =
    tr
      .slice(0, period)
      .reduce(
        (sum, value) =>
          sum + value,
        0,
      );

  let smoothedPlus =
    plusDm
      .slice(0, period)
      .reduce(
        (sum, value) =>
          sum + value,
        0,
      );

  let smoothedMinus =
    minusDm
      .slice(0, period)
      .reduce(
        (sum, value) =>
          sum + value,
        0,
      );

  const dxValues: number[] = [];

  for (
    let index = period;
    index < tr.length;
    index += 1
  ) {
    if (index > period) {
      smoothedTr =
        smoothedTr -
        smoothedTr / period +
        tr[index];

      smoothedPlus =
        smoothedPlus -
        smoothedPlus / period +
        plusDm[index];

      smoothedMinus =
        smoothedMinus -
        smoothedMinus / period +
        minusDm[index];
    }

    if (smoothedTr === 0) {
      dxValues.push(0);
      continue;
    }

    const plusDi =
      100 *
      (smoothedPlus /
        smoothedTr);

    const minusDi =
      100 *
      (smoothedMinus /
        smoothedTr);

    const denominator =
      plusDi + minusDi;

    const dx =
      denominator === 0
        ? 0
        : 100 *
          Math.abs(
            plusDi -
              minusDi,
          ) /
          denominator;

    dxValues.push(dx);
  }

  if (
    dxValues.length <
    period
  ) {
    return null;
  }

  return mean(
    dxValues.slice(
      -period,
    ),
  );
}

function calculateSlopePercent(
  values: number[],
  period = 20,
): number | null {
  if (values.length < period) {
    return null;
  }

  const window =
    values.slice(-period);

  const first =
    window[0];

  const last =
    window[window.length - 1];

  if (
    !finite(first) ||
    first === 0 ||
    !finite(last)
  ) {
    return null;
  }

  return (
    ((last - first) /
      Math.abs(first)) *
    100
  );
}

function calculateRocPercent(
  values: number[],
  period = 20,
): number | null {
  if (
    values.length <= period
  ) {
    return null;
  }

  const previous =
    values[
      values.length -
        1 -
        period
    ];

  const current =
    values[
      values.length - 1
    ];

  if (
    !finite(previous) ||
    previous === 0 ||
    !finite(current)
  ) {
    return null;
  }

  return (
    ((current - previous) /
      Math.abs(previous)) *
    100
  );
}

function normalizeBars(
  input: unknown,
): TrendRegimeBar[] {
  if (!Array.isArray(input)) {
    return [];
  }

  const normalized: TrendRegimeBar[] =
    [];

  for (const raw of input) {
    if (
      !raw ||
      typeof raw !== "object" ||
      Array.isArray(raw)
    ) {
      continue;
    }

    const row =
      raw as Record<
        string,
        unknown
      >;

    const open =
      Number(
        row.open ??
          row.Open,
      );

    const high =
      Number(
        row.high ??
          row.High,
      );

    const low =
      Number(
        row.low ??
          row.Low,
      );

    const close =
      Number(
        row.close ??
          row.Close,
      );

    const volumeValue =
      Number(
        row.volume ??
          row.Volume,
      );

    if (
      !Number.isFinite(open) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close) ||
      high < low
    ) {
      continue;
    }

    normalized.push({
      timestamp:
        typeof row.timestamp ===
        "string"
          ? row.timestamp
          : typeof row.date ===
              "string"
            ? row.date
            : undefined,
      open,
      high,
      low,
      close,
      volume:
        Number.isFinite(
          volumeValue,
        )
          ? volumeValue
          : undefined,
    });
  }

  return normalized;
}

function extractRows(
  source: unknown,
): TrendRegimeBar[] {
  if (
    Array.isArray(source)
  ) {
    return normalizeBars(
      source,
    );
  }

  if (
    !source ||
    typeof source !==
      "object" ||
    Array.isArray(source)
  ) {
    return [];
  }

  const root =
    source as Record<
      string,
      unknown
    >;

  const candidates = [
    root.rows,
    root.data,
    root.records,
    root.candles,
    root.bars,
    (
      root.marketData &&
      typeof root.marketData ===
        "object"
        ? (
            root.marketData as Record<
              string,
              unknown
            >
          ).rows
        : undefined
    ),
    (
      root.marketSnapshot &&
      typeof root.marketSnapshot ===
        "object"
        ? (
            root.marketSnapshot as Record<
              string,
              unknown
            >
          ).rows
        : undefined
    ),
  ];

  for (const candidate of candidates) {
    const rows =
      normalizeBars(
        candidate,
      );

    if (rows.length) {
      return rows;
    }
  }

  return [];
}

function buildSnapshot(
  bars: TrendRegimeBar[],
): TrendRegimeSnapshot {
  const closes =
    bars.map(
      (bar) => bar.close,
    );

  const latest =
    bars[bars.length - 1];

  const close =
    latest?.close ?? null;

  const ema20 =
    calculateEma(
      closes,
      20,
    );

  const ema50 =
    calculateEma(
      closes,
      50,
    );

  const ema200 =
    calculateEma(
      closes,
      200,
    );

  const atrSeries =
    calculateAtrSeries(
      bars,
      14,
    );

  const atr14 =
    atrSeries.length
      ? atrSeries[
          atrSeries.length - 1
        ]
      : null;

  const atrPercent =
    atr14 !== null &&
    close !== null &&
    close !== 0
      ? (atr14 / close) * 100
      : null;

  const atrPercentile =
    atrPercent !== null
      ? percentileRank(
          atrSeries
            .map(
              (
                value,
                index,
              ) => {
                const closeIndex =
                  bars.length -
                  atrSeries.length +
                  index;

                const c =
                  bars[
                    closeIndex
                  ]?.close;

                return c &&
                  Number.isFinite(
                    c,
                  )
                    ? (
                        value /
                        c
                      ) * 100
                    : NaN;
              },
            )
            .filter(
              Number.isFinite,
            ),
          atrPercent,
        )
      : null;

  const roc20Percent =
    calculateRocPercent(
      closes,
      20,
    );

  const rsi14 =
    calculateRsi(
      closes,
      14,
    );

  const adx14 =
    calculateAdx(
      bars,
      14,
    );

  const slope20Percent =
    calculateSlopePercent(
      closes,
      20,
    );

  const recentVolumes =
    bars
      .slice(-20)
      .map(
        (bar) => bar.volume,
      )
      .filter(
        (
          value,
        ): value is number =>
          finite(value),
      );

  const latestVolume =
    latest?.volume ?? null;

  const averageVolume =
    mean(recentVolumes);

  const volumeRatio =
    latestVolume !== null &&
    averageVolume !== null &&
    averageVolume !== 0
      ? latestVolume /
        averageVolume
      : null;

  const trendVotes = {
    priceAbove20:
      ema20 !== null &&
      close !== null &&
      close > ema20,

    ema20Above50:
      ema20 !== null &&
      ema50 !== null &&
      ema20 > ema50,

    ema50Above200:
      ema50 !== null &&
      ema200 !== null &&
      ema50 > ema200,

    slopePositive:
      slope20Percent !==
        null &&
      slope20Percent > 0,

    slopeNegative:
      slope20Percent !==
        null &&
      slope20Percent < 0,
  };

  let trendDirection:
    TrendDirection =
    "UNKNOWN";

  let trendScore = 0;

  if (
    trendVotes.priceAbove20
  ) {
    trendScore += 20;
  }

  if (
    trendVotes.ema20Above50
  ) {
    trendScore += 25;
  }

  if (
    trendVotes.ema50Above200
  ) {
    trendScore += 30;
  }

  if (
    trendVotes.slopePositive
  ) {
    trendScore += 25;
  }

  const downVotes = [
    ema20 !== null &&
      close !== null &&
      close < ema20,

    ema20 !== null &&
      ema50 !== null &&
      ema20 < ema50,

    ema50 !== null &&
      ema200 !== null &&
      ema50 < ema200,

    slope20Percent !==
      null &&
      slope20Percent < 0,
  ].filter(Boolean).length;

  if (trendScore >= 75) {
    trendDirection = "UP";
  } else if (
    downVotes >= 3
  ) {
    trendDirection = "DOWN";
  } else if (
    trendScore <= 30 &&
    downVotes <= 1
  ) {
    trendDirection =
      "SIDEWAYS";
  } else if (
    downVotes >= 3
  ) {
    trendDirection = "DOWN";
  } else {
    trendDirection =
      "SIDEWAYS";
  }

  let trendStrength =
    trendDirection ===
      "UP"
      ? trendScore
      : trendDirection ===
          "DOWN"
        ? clamp(
            downVotes * 25,
            0,
            100,
          )
        : 35;

  if (
    adx14 !== null
  ) {
    if (adx14 >= 25) {
      trendStrength += 10;
    } else if (
      adx14 < 15
    ) {
      trendStrength -= 10;
    }
  }

  trendStrength =
    clamp(
      trendStrength,
      0,
      100,
    );

  let momentum:
    MomentumState =
    "UNKNOWN";

  let momentumScore = 50;

  if (
    roc20Percent !== null
  ) {
    if (
      roc20Percent > 5
    ) {
      momentum =
        "POSITIVE";
      momentumScore = 80;
    } else if (
      roc20Percent > 1
    ) {
      momentum =
        "POSITIVE";
      momentumScore = 65;
    } else if (
      roc20Percent < -5
    ) {
      momentum =
        "NEGATIVE";
      momentumScore = 20;
    } else if (
      roc20Percent < -1
    ) {
      momentum =
        "NEGATIVE";
      momentumScore = 35;
    } else {
      momentum =
        "NEUTRAL";
      momentumScore = 50;
    }
  }

  if (
    rsi14 !== null
  ) {
    if (
      rsi14 >= 55 &&
      momentumScore >= 50
    ) {
      momentum =
        "POSITIVE";
      momentumScore =
        Math.max(
          momentumScore,
          65,
        );
    } else if (
      rsi14 <= 45 &&
      momentumScore <= 50
    ) {
      momentum =
        "NEGATIVE";
      momentumScore =
        Math.min(
          momentumScore,
          35,
        );
    }
  }

  let volatility:
    VolatilityState =
    "UNKNOWN";

  if (
    atrPercentile !==
    null
  ) {
    if (
      atrPercentile >= 75
    ) {
      volatility = "HIGH";
    } else if (
      atrPercentile <= 25
    ) {
      volatility = "LOW";
    } else {
      volatility = "NORMAL";
    }
  }

  const volatilityScore =
    atrPercentile === null
      ? 50
      : clamp(
          atrPercentile,
          0,
          100,
        );

  let marketRegime:
    MarketRegime =
    "UNKNOWN";

  if (
    volatility === "HIGH"
  ) {
    marketRegime =
      "HIGH_VOLATILITY";
  } else if (
    trendDirection === "UP" &&
    trendStrength >= 65 &&
    (adx14 === null ||
      adx14 >= 20)
  ) {
    marketRegime =
      "TRENDING_UP";
  } else if (
    trendDirection ===
      "DOWN" &&
    trendStrength >= 65 &&
    (adx14 === null ||
      adx14 >= 20)
  ) {
    marketRegime =
      "TRENDING_DOWN";
  } else if (
    trendDirection ===
      "SIDEWAYS" &&
    (adx14 === null ||
      adx14 < 20)
  ) {
    marketRegime =
      "RANGE_BOUND";
  } else {
    marketRegime =
      "TRANSITION";
  }

  const evidence: string[] =
    [];
  const warnings: string[] =
    [];

  if (
    trendDirection === "UP"
  ) {
    evidence.push(
      "Price and moving-average structure are aligned upward.",
    );
  }

  if (
    trendDirection === "DOWN"
  ) {
    evidence.push(
      "Price and moving-average structure are aligned downward.",
    );
  }

  if (
    trendDirection ===
    "SIDEWAYS"
  ) {
    evidence.push(
      "Moving-average structure does not show a strong directional alignment.",
    );
  }

  if (
    momentum === "POSITIVE"
  ) {
    evidence.push(
      "Momentum measures are positive.",
    );
  }

  if (
    momentum === "NEGATIVE"
  ) {
    evidence.push(
      "Momentum measures are negative.",
    );
  }

  if (
    adx14 !== null &&
    adx14 >= 25
  ) {
    evidence.push(
      "ADX indicates meaningful directional strength.",
    );
  } else if (
    adx14 !== null &&
    adx14 < 20
  ) {
    evidence.push(
      "ADX indicates limited directional strength.",
    );
  }

  if (
    volatility === "HIGH"
  ) {
    warnings.push(
      "Volatility is elevated relative to the recent history.",
    );
  }

  if (
    volatility === "LOW"
  ) {
    evidence.push(
      "Volatility is relatively compressed.",
    );
  }

  if (
    volumeRatio !== null &&
    volumeRatio > 1.2
  ) {
    evidence.push(
      "Recent volume is above its 20-bar average.",
    );
  }

  const agreementSignals =
    [
      true,
      momentum !==
        "UNKNOWN",
      volatility !==
        "UNKNOWN",
      adx14 !== null,
      slope20Percent !==
        null,
    ].filter(
      Boolean,
    ).length;

  let evidenceScore =
    clamp(
      Math.round(
        (
          evidence.length /
          6
        ) *
          10,
      ),
      0,
      10,
    );

  if (
    agreementSignals >= 4
  ) {
    evidenceScore =
      clamp(
        evidenceScore + 1,
        0,
        10,
      );
  }

  if (
    marketRegime ===
    "TRANSITION"
  ) {
    evidenceScore =
      clamp(
        evidenceScore - 1,
        0,
        10,
      );
  }

  let confidence:
    Confidence =
    "LOW";

  if (
    evidenceScore >= 8 &&
    agreementSignals >= 4
  ) {
    confidence = "HIGH";
  } else if (
    evidenceScore >= 5 &&
    agreementSignals >= 3
  ) {
    confidence = "MEDIUM";
  }

  if (
    bars.length <
    MINIMUM_BARS
  ) {
    warnings.push(
      `Only ${bars.length} valid bars were available; ${MINIMUM_BARS} are preferred for the full regime model.`,
    );
  }

  return {
    timestamp:
      latest?.timestamp ??
      null,

    close,

    trendDirection,
    trendStrength: Math.round(
      trendStrength,
    ),
    trendScore: Math.round(
      trendScore,
    ),

    momentum,
    momentumScore: Math.round(
      momentumScore,
    ),

    volatility,
    volatilityScore: Math.round(
      volatilityScore,
    ),

    marketRegime,

    evidenceScore,
    confidence,

    indicators: {
      ema20: round(ema20, 6),
      ema50: round(ema50, 6),
      ema200: round(ema200, 6),
      atr14: round(atr14, 6),
      atrPercent: round(
        atrPercent,
        4,
      ),
      atrPercentile: round(
        atrPercentile,
        2,
      ),
      roc20Percent: round(
        roc20Percent,
        4,
      ),
      rsi14: round(
        rsi14,
        2,
      ),
      adx14: round(
        adx14,
        2,
      ),
      slope20Percent: round(
        slope20Percent,
        4,
      ),
      volumeRatio: round(
        volumeRatio,
        4,
      ),
    },

    evidence,
    warnings,
  };
}

export function analyzeTrendAndRegime(
  source: unknown,
  options: {
    symbol?: string | null;
    timeframe?: string | null;
    minimumBars?: number;
  } = {},
): TrendRegimeEngineResult {
  const bars =
    extractRows(source);

  const minimumBars =
    options.minimumBars ??
    MINIMUM_BARS;

  if (!bars.length) {
    return {
      engine:
        "MARKETHQ_TREND_REGIME_ENGINE_V1",
      status:
        "INSUFFICIENT_DATA",
      symbol:
        options.symbol ??
        null,
      timeframe:
        options.timeframe ??
        null,
      barsUsed: 0,
      minimumBarsRequired:
        minimumBars,
      snapshot: {
        timestamp: null,
        close: null,
        trendDirection:
          "UNKNOWN",
        trendStrength: 0,
        trendScore: 0,
        momentum:
          "UNKNOWN",
        momentumScore: 50,
        volatility:
          "UNKNOWN",
        volatilityScore: 50,
        marketRegime:
          "UNKNOWN",
        evidenceScore: 0,
        confidence:
          "UNKNOWN",
        indicators: {
          ema20: null,
          ema50: null,
          ema200: null,
          atr14: null,
          atrPercent: null,
          atrPercentile: null,
          roc20Percent: null,
          rsi14: null,
          adx14: null,
          slope20Percent: null,
          volumeRatio: null,
        },
        evidence: [],
        warnings: [
          "No valid OHLC rows were available.",
        ],
      },
      researchOnly: true,
      lookAheadSafe: true,
    };
  }

  const snapshot =
    buildSnapshot(bars);

  return {
    engine:
      "MARKETHQ_TREND_REGIME_ENGINE_V1",
    status:
      bars.length >=
      minimumBars
        ? "READY"
        : "PARTIAL",
    symbol:
      options.symbol ??
      null,
    timeframe:
      options.timeframe ??
      null,
    barsUsed:
      bars.length,
    minimumBarsRequired:
      minimumBars,
    snapshot,
    researchOnly: true,
    lookAheadSafe: true,
  };
}

