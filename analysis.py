import sqlite3, json, numpy as np
from collections import defaultdict
from itertools import combinations

conn = sqlite3.connect('market_hq.db')
cur = conn.cursor()

cur.execute("""
    SELECT id, setup_signature, symbol, timeframe, setup_type, regime, direction,
           entry_price, invalidation_price, target_price, quality_score, outcome, pnl_pct,
           duration_bars, max_favorable, max_adverse, hit_target, hit_invalidation,
           atr_pct, zone_width_atr, touches, structure_type, liquidity_side, dataset_version,
           universe, universe_method, survivorship_risk, metadata_json, created_at
    FROM setup_outcomes
    WHERE outcome IN ('hit_target', 'hit_invalidation')
""")

rows = cur.fetchall()
conn.close()

data = []
for r in rows:
    meta = json.loads(r[27]) if r[27] else {}
    data.append({
        'id': r[0], 'setup_signature': r[1], 'symbol': r[2], 'timeframe': r[3],
        'setup_type': r[4], 'regime': r[5], 'direction': r[6],
        'entry_price': r[7], 'invalidation_price': r[8], 'target_price': r[9],
        'quality_score': r[10], 'outcome': r[11], 'pnl_pct': r[12],
        'duration_bars': r[13], 'max_favorable': r[14], 'max_adverse': r[15],
        'hit_target': r[16], 'hit_invalidation': r[17],
        'atr_pct': r[18], 'zone_width_atr': r[19], 'touches': r[20],
        'structure_type': r[21], 'liquidity_side': r[22], 'dataset_version': r[23],
        'universe': r[24], 'universe_method': r[25], 'survivorship_risk': r[26],
        'metadata': meta, 'created_at': r[28]
    })

# ============================================================
# FEATURE CLASSIFICATION
# ============================================================

numeric_features = ['quality_score', 'pnl_pct', 'duration_bars',
                    'atr_pct', 'zone_width_atr', 'touches']

for d in data:
    d['target'] = 1 if d['outcome'] == 'hit_target' else 0

total = len(data)
base_win_rate = sum(d['target'] for d in data) / total
print(f"Overall win rate: {base_win_rate:.4f} ({sum(d['target'] for d in data)}/{total})")
print(f"Overall avg PnL: {np.mean([d['pnl_pct'] for d in data if d['pnl_pct'] is not None]):.4f}")

# --- Correlation with outcome ---
print("\n" + "="*80)
print("FEATURE CORRELATION WITH OUTCOME")
print("="*80)

feature_correlations = {}
for feat in numeric_features:
    vals = np.array([d[feat] for d in data if d[feat] is not None])
    targs = np.array([d['target'] for d in data if d[feat] is not None])
    if len(vals) > 0:
        corr = np.corrcoef(vals, targs)[0,1]
        feature_correlations[feat] = corr
        print(f"  {feat}: corr={corr:.4f}")

# --- Categorical feature analysis ---
print("\n" + "="*80)
print("CATEGORICAL FEATURE ANALYSIS")
print("="*80)

cat_features = ['setup_type', 'regime', 'direction', 'timeframe', 'symbol', 'structure_type', 'liquidity_side']
for feat in cat_features:
    vals_set = set(d[feat] for d in data if d[feat] is not None)
    print(f"\n  {feat} ({len(vals_set)} unique values):")
    for val in sorted(vals_set):
        subset = [d for d in data if d[feat] == val]
        wr = sum(d['target'] for d in subset) / len(subset) if subset else 0
        print(f"    {val}: n={len(subset)}, win_rate={wr:.4f}")

# ============================================================
# WALK-FORWARD STABILITY (3 periods by setup_signature)
# ============================================================
print("\n" + "="*80)
print("WALK-FORWARD STABILITY (3 periods by setup_signature)")
print("="*80)

signatures = list(set(d['setup_signature'] for d in data))
np.random.seed(42)
np.random.shuffle(signatures)
n = len(signatures)
p1_sigs = set(signatures[:n//3])
p2_sigs = set(signatures[n//3:2*n//3])
p3_sigs = set(signatures[2*n//3:])

periods = {'P1': p1_sigs, 'P2': p2_sigs, 'P3': p3_sigs}
period_data = {}
for pname, sigs in periods.items():
    period_data[pname] = [d for d in data if d['setup_signature'] in sigs]
    print(f"\n{pname}: {len(period_data[pname])} setups, win_rate={sum(d['target'] for d in period_data[pname])/len(period_data[pname]):.4f}")

# Correlation per period per feature
print("\nCorrelation by period:")
for feat in numeric_features:
    corrs = {}
    for pname, pdata in period_data.items():
        vals = np.array([d[feat] for d in pdata if d[feat] is not None])
        targs = np.array([d['target'] for d in pdata if d[feat] is not None])
        if len(vals) > 2:
            corrs[pname] = np.corrcoef(vals, targs)[0,1]
        else:
            corrs[pname] = None
    print(f"  {feat}: {corrs}")

# Ranking stability
print("\nFeature ranking by |correlation| per period:")
for pname in ['P1', 'P2', 'P3']:
    pdata = period_data[pname]
    corrs = {}
    for feat in numeric_features:
        vals = np.array([d[feat] for d in pdata if d[feat] is not None])
        targs = np.array([d['target'] for d in pdata if d[feat] is not None])
        if len(vals) > 2:
            corrs[feat] = abs(np.corrcoef(vals, targs)[0,1])
        else:
            corrs[feat] = 0
    ranked = sorted(corrs.items(), key=lambda x: -x[1])
    print(f"  {pname}: {[(f'{f}:{c:.3f}') for f,c in ranked]}")

# ============================================================
# ADAPTIVE V1 FAILURE ANALYSIS
# ============================================================
print("\n" + "="*80)
print("ADAPTIVE V1 FAILURE ANALYSIS")
print("="*80)

# Adaptive weighting: quality_score is the adaptive weight
# Check if quality_score correlates with outcome
qs_target = [(d['quality_score'], d['target']) for d in data if d['quality_score'] is not None]
qs_vals = np.array([x[0] for x in qs_target])
targs = np.array([x[1] for x in qs_target])
corr_qs = np.corrcoef(qs_vals, targs)[0,1]
print(f"\nquality_score vs target correlation: {corr_qs:.4f}")

# Weight concentration: distribution of quality_score
print(f"\nquality_score distribution:")
print(f"  mean={np.mean(qs_vals):.4f} std={np.std(qs_vals):.4f}")
print(f"  median={np.median(qs_vals):.4f}")
print(f"  p10={np.percentile(qs_vals, 10):.4f} p90={np.percentile(qs_vals, 90):.4f}")

# Small sample influence: by setup_signature
print("\n--- Per-signature analysis (small sample effect) ---")
sig_stats = {}
for d in data:
    sig = d['setup_signature']
    if sig not in sig_stats:
        sig_stats[sig] = {'targets': [], 'qs': [], 'pnls': []}
    sig_stats[sig]['targets'].append(d['target'])
    sig_stats[sig]['qs'].append(d['quality_score'] if d['quality_score'] is not None else 0)
    sig_stats[sig]['pnls'].append(d['pnl_pct'] if d['pnl_pct'] is not None else 0)

# Weight concentration: how many signatures dominate?
sig_wr = {}
for sig, s in sig_stats.items():
    wr = sum(s['targets']) / len(s['targets'])
    sig_wr[sig] = wr

# Top signatures by count
sig_counts = {sig: len(s['targets']) for sig, s in sig_stats.items()}
top_sigs = sorted(sig_counts.items(), key=lambda x: -x[1])[:10]
print("\nTop 10 signatures by count:")
for sig, cnt in top_sigs:
    wr = sig_wr[sig]
    avg_qs = np.mean(sig_stats[sig]['qs'])
    avg_pnl = np.mean(sig_stats[sig]['pnls'])
    print(f"  {sig}: n={cnt}, win_rate={wr:.4f}, avg_quality={avg_qs:.4f}, avg_pnl={avg_pnl:.4f}")

# Baseline vs adaptive comparison
# Baseline: equal weight (just use win rate)
# Adaptive: weight by quality_score
print("\n--- Baseline vs Adaptive weighting ---")

# For each signature, compute baseline (WR) and adaptive (weighted by QS) predictions
# Then compare accuracy
from sklearn.metrics import accuracy_score, brier_score_loss

# Baseline: predict hit_target if WR > 0.5
baseline_preds = []
adaptive_preds = []
actuals = []

for sig, s in sig_stats.items():
    n = len(s['targets'])
    wr = sum(s['targets']) / n
    avg_qs = np.mean(s['qs'])
    # For each instance in this signature
    for i in range(n):
        actuals.append(s['targets'][i])
        baseline_preds.append(1 if wr > 0.5 else 0)
        # Adaptive: use quality_score as weight (higher QS = more confident)
        # If QS > 0.5, predict target; else predict invalidation
        adaptive_preds.append(1 if avg_qs > 0.5 else 0)

baseline_acc = accuracy_score(actuals, baseline_preds)
adaptive_acc = accuracy_score(actuals, adaptive_preds)
print(f"Baseline accuracy (WR>0.5): {baseline_acc:.4f}")
print(f"Adaptive accuracy (QS>0.5): {adaptive_acc:.4f}")
print(f"Difference: {adaptive_acc - baseline_acc:.4f}")

# Brier score
baseline_brier = brier_score_loss(actuals, baseline_preds)
adaptive_brier = brier_score_loss(actuals, adaptive_preds)
print(f"Baseline Brier: {baseline_brier:.4f}")
print(f"Adaptive Brier: {adaptive_brier:.4f}")

# Per-regime analysis
print("\n--- Per-regime analysis ---")
regimes = set(d['regime'] for d in data)
for reg in sorted(regimes):
    subset = [d for d in data if d['regime'] == reg]
    wr = sum(d['target'] for d in subset) / len(subset)
    avg_qs = np.mean([d['quality_score'] for d in subset if d['quality_score'] is not None])
    avg_pnl = np.mean([d['pnl_pct'] for d in subset if d['pnl_pct'] is not None])
    print(f"  {reg}: n={len(subset)}, WR={wr:.4f}, avg_QS={avg_qs:.4f}, avg_PnL={avg_pnl:.4f}")

# Per-setup_type analysis
print("\n--- Per-setup_type analysis ---")
stypes = set(d['setup_type'] for d in data)
for st in sorted(stypes):
    subset = [d for d in data if d['setup_type'] == st]
    wr = sum(d['target'] for d in subset) / len(subset)
    avg_qs = np.mean([d['quality_score'] for d in subset if d['quality_score'] is not None])
    print(f"  {st}: n={len(subset)}, WR={wr:.4f}, avg_QS={avg_qs:.4f}")

# Fallback analysis
print("\n--- Fallback usage ---")
fallback_types = [d for d in data if d['setup_type'] in ('fallback_r', 'fallback_test', 'fb_track')]
non_fallback = [d for d in data if d['setup_type'] not in ('fallback_r', 'fallback_test', 'fb_track')]
fb_wr = sum(d['target'] for d in fallback_types) / len(fallback_types) if fallback_types else 0
nf_wr = sum(d['target'] for d in non_fallback) / len(non_fallback) if non_fallback else 0
print(f"  Fallback types: n={len(fallback_types)}, WR={fb_wr:.4f}")
print(f"  Non-fallback: n={len(non_fallback)}, WR={nf_wr:.4f}")

# Fallback ratio
fb_ratio = len(fallback_types) / len(data)
print(f"  Fallback ratio: {fb_ratio:.4f}")

# Quality score vs PnL relationship
print("\n--- Quality score vs PnL ---")
qs_pnl = [(d['quality_score'], d['pnl_pct']) for d in data if d['quality_score'] is not None and d['pnl_pct'] is not None]
qs_vals2 = np.array([x[0] for x in qs_pnl])
pnl_vals = np.array([x[1] for x in qs_pnl])
corr_qs_pnl = np.corrcoef(qs_vals2, pnl_vals)[0,1]
print(f"  Correlation QS vs PnL: {corr_qs_pnl:.4f}")

# Bin QS and check PnL
print("\n  QS bins vs avg PnL:")
for lo in np.arange(0, 0.9, 0.1):
    hi = lo + 0.1
    bin_data = [(q, p) for q, p in qs_pnl if lo <= q < hi]
    if bin_data:
        avg_p = np.mean([p for _, p in bin_data])
        print(f"    [{lo:.1f}-{hi:.1f}): n={len(bin_data)}, avg_PnL={avg_p:.4f}")

# ============================================================
# REDUNDANCY ANALYSIS
# ============================================================
print("\n" + "="*80)
print("REDUNDANCY ANALYSIS (feature correlations)")
print("="*80)

feat_matrix = {}
for feat in numeric_features:
    vals = np.array([d[feat] for d in data if d[feat] is not None])
    feat_matrix[feat] = vals

for f1, f2 in combinations(numeric_features, 2):
    v1 = feat_matrix[f1]
    v2 = feat_matrix[f2]
    # Align by index (same data length)
    min_len = min(len(v1), len(v2))
    corr = np.corrcoef(v1[:min_len], v2[:min_len])[0,1]
    if abs(corr) > 0.3:
        print(f"  {f1} vs {f2}: corr={corr:.4f}")

# ============================================================
# LEAKAGE ANALYSIS
# ============================================================
print("\n" + "="*80)
print("LEAKAGE-RISK ANALYSIS")
print("="*80)

# Check if pnl_pct correlates with outcome (it should - it's derived from outcome)
pnl_target = [(d['pnl_pct'], d['target']) for d in data if d['pnl_pct'] is not None]
pnl_vals = np.array([x[0] for x in pnl_target])
targs = np.array([x[1] for x in pnl_target])
corr_pnl_target = np.corrcoef(pnl_vals, targs)[0,1]
print(f"  pnl_pct vs target correlation: {corr_pnl_target:.4f} (EXPECTED HIGH - leakage risk)")

# Check duration_bars vs outcome
db_target = [(d['duration_bars'], d['target']) for d in data if d['duration_bars'] is not None]
db_vals = np.array([x[0] for x in db_target])
corr_db_target = np.corrcoef(db_vals, targs)[0,1]
print(f"  duration_bars vs target correlation: {corr_db_target:.4f}")

# ============================================================
# UNSTABLE FEATURE ANALYSIS
# ============================================================
print("\n" + "="*80)
print("UNSTABLE FEATURE ANALYSIS (variance across walk-forward periods)")
print("="*80)

for feat in numeric_features:
    period_means = {}
    period_stds = {}
    for pname, pdata in period_data.items():
        vals = np.array([d[feat] for d in pdata if d[feat] is not None])
        if len(vals) > 0:
            period_means[pname] = np.mean(vals)
            period_stds[pname] = np.std(vals)
    if period_means:
        mean_of_means = np.mean(list(period_means.values()))
        std_of_means = np.std(list(period_means.values()))
        cv = std_of_means / mean_of_means if mean_of_means != 0 else float('inf')
        print(f"  {feat}: period_means={ {k: round(v,4) for k,v in period_means.items()} }, CV={cv:.4f}")

PYEOF