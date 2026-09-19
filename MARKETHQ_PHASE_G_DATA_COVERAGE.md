# MARKETHQ PHASE G — DATA COVERAGE

**Date:** 2026-09-16
**Purpose:** Document data availability for Phase G analysis

---

## Dataset Status

### Assets

| Asset | 15m | 1h | 4h | Status |
|-------|-----|-----|-----|--------|
| THYAO.IS | Available | Available | Available | PRIMARY |

### Timeframes

| Timeframe | Coverage | N Setups | N Outcomes | Sufficient |
|-----------|----------|----------|------------|------------|
| 15m | Limited | TBD | TBD | DEPENDS |
| 1h | Available | TBD | TBD | LIKELY |
| 4h | Available | TBD | TBD | LIKELY |

### Data Requirements per Analysis

| Analysis | Min N | Timeframe | Status |
|----------|-------|-----------|--------|
| Entry zone analysis | 30 | 1h | PENDING |
| Invalidation analysis | 30 | 1h | PENDING |
| Target analysis | 30 | 1h | PENDING |
| Quality analysis | 30 per bucket | 1h | PENDING |
| Regime analysis | 30 per regime | 1h | PENDING |
| Strategy family analysis | 30 per family | 1h | PENDING |
| Walk-forward | 3 windows | 1h | PENDING |
| Agent attribution | 30 per agent | 1h | PENDING |
| Evidence attribution | 30 per evidence type | 1h | PENDING |
| Failure analysis | 20 failures | 1h | PENDING |
| Multi-asset | 5 assets | 1h | INSUFFICIENT |

---

## Coverage Assessment Rules

- N ≥ 30: DATA_SUFFICIENT
- N ≥ 10: LIMITED
- N < 10: LOW_SAMPLE
- No data: UNAVAILABLE

---

## Known Limitations

1. **Single asset** — THYAO.IS only, no cross-asset validation
2. **Survivorship bias** — not assessed
3. **Timeframe isolation** — transfer between timeframes not tested
4. **Regime distribution** — depends on historical data
5. **Quality V4** — experimental, limited sample

---

## Data Sources

- yfinance: real OHLCV, no fake data
- FeatureCache: Phase C snapshots
- Agent results: Phase D stored results
- Opportunity Engine: Phase E
- Setup Engine: Phase F

---

## Data Freshness

- yfinance data: live pull (no caching issues expected)
- Feature snapshots: generated per replay
- No pre-computed outcomes used