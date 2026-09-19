# MARKETHQ PHASE I — DATA COVERAGE REPORT

**Date:** 2026-09-16
**Asset:** THYAO.IS
**Timeframe:** 1h
**Period:** Jun 25 - Sep 16, 2026 (531 bars)

---

## Coverage by Data Type

| Data Type | Available | Quality | Notes |
|---|---|---|---|
| OHLCV | ✓ 531 bars | High | Real yfinance data |
| Volume | ✓ 531 bars | High | Non-zero volume |
| ATR | ✓ | High | 2.41 |
| ADX | ✓ | High | 30.7 |
| SMA Fast/Slow | ✓ | High | Computed |
| EMA Fast/Slow | ✓ | High | Computed |
| RSI | ✓ | High | 69.2 |
| MACD | ✓ | High | Computed |
| Bollinger | ✓ | High | Upper/lower computed |
| Structure | ✓ | High | Available |
| Liquidity | ✓ | High | Available |
| Momentum | ✓ | High | Available |
| Regime | ✓ | High | 9-strategy matrix |
| MFE/MAE | ✗ | N/A | Not in feature set |
| Setup outcomes | ✗ | N/A | No setups generated |
| Historical validation | ✗ | N/A | No outcomes |

## Coverage by Asset/Timeframe/Regime

| Dimension | Coverage | Status |
|---|---|---|
| THYAO.IS 1h | 531 bars | SUFFICIENT |
| BTC-USD 1h | 716 bars | SUFFICIENT |
| Multi-asset | 1 asset tested | INSUFFICIENT for scale |
| Multi-timeframe | 1 timeframe | INSUFFICIENT for robustness |
| Regime diversity | 1 regime (UNKNOWN) | INSUFFICIENT |

## Coverage by Strategy Family

| Family | Coverage | Status |
|---|---|---|
| Trend | Agents exist, non-functional | BLOCKED |
| Breakout | Agents exist, non-functional | BLOCKED |
| Reversal | Agents exist, non-functional | BLOCKED |
| Momentum | Agents exist, non-functional | BLOCKED |
| Volatility | Agents exist, non-functional | BLOCKED |
| Liquidity | Agents exist, non-functional | BLOCKED |
| Structure | Agents exist, non-functional | BLOCKED |

## Coverage Gaps

1. **Agent execution** — All 7 agents fail (registry/runtime bug)
2. **Setup generation** — No setups (no agent evidence)
3. **Outcome simulation** — No outcomes (no setups)
4. **Multi-asset** — Only THYAO.IS tested
5. **Multi-timeframe** — Only 1h tested
6. **Regime diversity** — Only UNKNOWN regime (agents don't run)
7. **MFE/MAE** — Not in feature set
8. **Historical validation** — No outcomes to validate

## Recommendation

Fix the agent registry/runtime bug first, then expand coverage:
1. Multi-asset (5-10 assets)
2. Multi-timeframe (1h, 4h, 1d)
3. Regime diversity (trending, ranging, volatile)
4. MFE/MAE features
