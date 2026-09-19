# MarketHQ — Strategy Agent Map

**Date:** 2026-09-16
**Source:** strategy_registry_v1.py, signal_engine.py, smc_structure_v1.py

---

## 1. STRATEGY REGISTRY — 12 Strategies / 6 Families

| Strategy ID | Family | Description | Key Features |
|-------------|--------|-------------|-------------|
| ema_trend_v1 | trend | EMA20 vs EMA50 cross | EMA_FAST, EMA_SLOW |
| supertrend_v1 | trend | SuperTrend(10,3) direction | ATR, EMA |
| adx_v1 | trend | ADX>20 + DI direction | ADX, DI+/- |
| rsi_reversal_v1 | mean_reversion | RSI oversold/overbought | RSI |
| bollinger_v1 | mean_reversion | BB outer reversal | BOLL_UPPER, BOLL_LOWER |
| stoch_reversal_v1 | mean_reversion | Stochastic overbought/oversold | STOCH_K, STOCH_D |
| donchian_breakout_v1 | breakout | Donchian N=20 breakout | DONCHIAN_HIGH, DONCHIAN_LOW |
| atr_breakout_v1 | breakout | ATR expansion breakout | ATR |
| or_breakout_v1 | breakout | Opening range breakout | OR_HIGH, OR_LOW |
| vwap_v1 | volume | Close vs 20-bar VWAP | VWAP |
| rs_benchmark_v1 | relative | Relative strength vs benchmark | Benchmark data |
| smc_structure_v1 | structure | Sweep+BOS/CHoCH | Swing, BOS, CHoCH |

---

## 2. STRATEGY FAMILIES

### TREND (3 strategies)
- **Features:** EMA_FAST, EMA_SLOW, ADX, DI+, DI-
- **Engines:** signal_engine.py
- **Regimes:** TRENDING, UNKNOWN
- **Timeframes:** All (5m-1d)
- **Historical Evidence:** setup_outcomes (ADX 91% coverage)
- **Backtest Evidence:** backtest_engine.py

### MEAN_REVERSION (3 strategies)
- **Features:** RSI, BOLL_UPPER, BOLL_LOWER, STOCH_K, STOCH_D
- **Engines:** signal_engine.py
- **Regimes:** RANGE, UNKNOWN
- **Timeframes:** All (5m-1d)
- **Historical Evidence:** setup_outcomes
- **Backtest Evidence:** backtest_engine.py

### BREAKOUT (3 strategies)
- **Features:** DONCHIAN_HIGH, DONCHIAN_LOW, ATR, OR_HIGH, OR_LOW
- **Engines:** strategy_registry_v1.py
- **Regimes:** COMPRESSION, EXPANSION, UNKNOWN
- **Timeframes:** All (5m-1d)
- **Historical Evidence:** setup_outcomes (limited)
- **Backtest Evidence:** setup_backtest_engine.py

### VOLUME (1 strategy)
- **Features:** VWAP, volume_ratio
- **Engines:** signal_engine.py
- **Regimes:** Any
- **Timeframes:** All (5m-1d)
- **Historical Evidence:** volume_ratio per-setup NOT stored (dataset-level only)
- **Backtest Evidence:** backtest_engine.py

### RELATIVE (1 strategy)
- **Features:** Benchmark relative strength
- **Engines:** strategy_registry_v1.py
- **Regimes:** Any
- **Timeframes:** All
- **Historical Evidence:** None (requires benchmark data)
- **Backtest Evidence:** None

### STRUCTURE (1 strategy)
- **Features:** Swing points, BOS, CHoCH, liquidity
- **Engines:** smc_structure_v1.py
- **Regimes:** TRENDING, RANGE
- **Timeframes:** All (needs 30+ bars)
- **Historical Evidence:** setup_outcomes (structure_type 0%)
- **Backtest Evidence:** None directly

---

## 3. FEATURE → STRATEGY DEPENDENCIES

| Feature | Used By | Required |
|---------|---------|----------|
| EMA_FAST/EMA_SLOW | ema_trend_v1 | Yes |
| ADX/DI | adx_v1 | Yes |
| ATR | supertrend_v1, atr_breakout_v1 | Yes |
| RSI | rsi_reversal_v1 | Yes |
| BOLL_UPPER/LOWER | bollinger_v1 | Yes |
| STOCH_K/D | stoch_reversal_v1 | Yes |
| DONCHIAN_HIGH/LOW | donchian_breakout_v1 | Yes |
| OR_HIGH/LOW | or_breakout_v1 | Yes |
| VWAP | vwap_v1 | Yes |
| volume_ratio | vwap_v1 | Partial |
| Swing/BOS/CHoCH | smc_structure_v1 | Yes |
| liquidity | smc_structure_v1 | Partial |

---

## 4. REGIME COMPATIBILITY

| Regime | Compatible Families |
|--------|-------------------|
| TRENDING | trend, structure |
| RANGE | mean_reversion, structure |
| COMPRESSION | breakout |
| EXPANSION | breakout, trend |
| UNKNOWN | All (low confidence) |

---

## 5. TIMEFRAME COMPATIBILITY

| Timeframe | Coverage | Notes |
|-----------|----------|-------|
| 5m | 45 datasets | All features available |
| 15m | 45 datasets | All features available |
| 1h | 45 datasets | All features available |
| 4h | 45 datasets | All features available |
| 1d | 45 datasets | All features available |

---

## 6. DATA AVAILABILITY

| Feature | Coverage | Status |
|---------|----------|--------|
| OHLCV | 45/45 | ✅ |
| volume_ratio | 43/45 | ✅ |
| ADX | 45/45, 11,516 setups | ✅ |
| ATR | 43/45 | ✅ |
| RSI | 43/45 | ✅ |
| Bollinger | 43/45 | ✅ |
| Structure events | 43/45, 2,716 events | ✅ |
| structure_type | 0% | ❌ UNAVAILABLE |
| liquidity_side | 0% | ❌ UNAVAILABLE |
| MFE/MAE | 2 setups | ❌ INSUFFICIENT |

---

## 7. STRATEGY RESEARCH AGENT MAP

| Phase D Agent | Strategy Family | Strategies | Required Features |
|---------------|----------------|------------|-------------------|
| TrendResearchAgent | trend | ema_trend_v1, supertrend_v1, adx_v1 | EMA, ADX, ATR |
| BreakoutResearchAgent | breakout | donchian_breakout_v1, atr_breakout_v1, or_breakout_v1 | Donchian, ATR, OR |
| ReversalResearchAgent | mean_reversion | rsi_reversal_v1, bollinger_v1, stoch_reversal_v1 | RSI, BB, Stochastic |
| MomentumResearchAgent | momentum | (derived from signal_engine) | momentum_at_entry |
| VolatilityResearchAgent | volatility | (derived from signal_engine) | ATR, volatility_state |
| LiquidityResearchAgent | liquidity | (derived from smc_structure) | liquidity, structure |
| StructureResearchAgent | structure | smc_structure_v1 | Swing, BOS, CHoCH |

---

## 8. ENGINE DEPENDENCIES

| Engine | Used By |
|--------|---------|
| signal_engine.py | All strategy agents |
| smc_structure_v1.py | StructureResearchAgent |
| strategy_registry_v1.py | Strategy signal generation |
| setup_quality_engine_v4.py | Quality scoring |
| backtest_engine.py | Historical evidence |
| setup_engine_v1.py | Setup generation |
| regime_filter.py | Regime detection |

---

## 9. KNOWN LIMITATIONS

1. structure_type/liquidity_side: 0% coverage — Setup engine gap
2. MFE/MAE: Only 2 records — insufficient post-setup data
3. volume_ratio per-setup: Not stored (dataset-level only)
4. Quality V4: r=0.16 correlation, not production-ready
5. FB/TEST data: yfinance corruption — mark unreliable
6. No benchmark data for rs_benchmark_v1
7. No historical backtest evidence for breakout strategies
8. No OOS results for most strategies

---

## 10. RESEARCH VS PERFORMANCE BOUNDARY

| Can Say | Cannot Say |
|---------|-----------|
| "momentum is strong" | "momentum strategy wins 70%" |
| "RSI oversold" | "RSI reversal has 60% win rate" |
| "trending regime" | "trend strategies outperform in backtest" |
| "breakout detected" | "breakout strategy profitable OOS" |
| "CHoCH detected" | "CHoCH has positive expectancy" |

Performance claims require:
- Backtest with sample size
- Walk-forward validation
- OOS testing
- Calibration

None of these exist yet for strategy agents.
