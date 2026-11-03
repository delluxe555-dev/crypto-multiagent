#!/usr/bin/env python3
"""make_report.py - builds ../../research_E_ict_setups.md from results_ict.json + results_per_pair.csv + trades_ict.npz"""
import json, os, csv, numpy as np, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
J = json.load(open("results_ict.json")); R = J["res"]; cells = [tuple(c) for c in J["cells"]]
SETUPS = {1: "IFVG", 2: "BreakerFlow", 3: "CISD", 4: "SuspensionBlock", 5: "OrderBlock", 6: "MSS_FVG"}; TFS = ["15m", "1h", "4h"]; STOPS = ["zone", "atr1.5"]; CN = ["gross", "0.05%/side", "0.15%/side"]
def r(ci, c): return R[f"{ci}|{'|'.join(map(str, c))}"]
def nm(c): return f"{SETUPS[c[0]]} {TFS[c[1]]} {STOPS[c[2]]} {int(c[3])}R"
f = lambda x, d=3: "n/a" if x is None else f"{x:+.{d}f}"
def ci_(x): return f"[{x[0]:+.3f}, {x[1]:+.3f}]"
d0 = dt.datetime.utcfromtimestamp(J["t0"]).date()
L = []; A = L.append
cnt = {}
for ci in (0, 1, 2):
    rs = [r(ci, c) for c in cells]
    cnt[ci] = dict(pos=sum(x["mean"] > 0 for x in rs), ci_pos=sum(x["ci"][0] > 0 for x in rs), p05=sum(x["p"] < 0.05 for x in rs), holm=sum(x["p_holm"] < 0.05 for x in rs),
                   dpos=sum(x["diff_ci"][0] > 0 for x in rs), dholm=sum(x["p_diff_holm"] < 0.05 for x in rs), dsr=sum((x["dsr72"] or 0) > 0.95 for x in rs), dsr_v3=sum((x["dsr72_v300"] or 0) > 0.95 for x in rs))
H = 1
best = sorted(cells, key=lambda c: -r(H, c)["mean"])[:6]
b0 = best[0]
A("# Step E — Rule-based test of 6 ICT-style setups (from the X video) on 12 USDT-M perps × 15m/1h/4h")
A(f"*Generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} (Europe/Istanbul). Code: `outputs/research/ict/` (fetch_data.py, ict_setups.py, run_ict.py, stats_ict.py, make_report.py, test_nolookahead.py). Per-pair raw table: `outputs/research/ict/results_per_pair.csv`.*\n")
A("## 0) TL;DR / verdict")
tot = J["n_trades"]
A(f"- **No setup shows a robust edge after costs.** 72 configs (6 setups × 3 TF × 2 stop types × 2 targets), {tot:,} simulated trades, 12 pairs, {d0} → 2026-10-24.")
A(f"- Gross (before costs): {cnt[0]['pos']}/72 configs have mean R > 0, but on 15m/1h the gross edge is ≈0 (avg gross R between −0.02 and +0.03; win rate ≈ 1/(1+R), a coin-flip with R-multiples), while on **4h** IFVG / Breaker Flow / CISD / MSS+FVG show avg gross R of +0.07…+0.14. **After 0.05%/side costs: {cnt[1]['pos']}/72 positive; after 0.15%/side: {cnt[2]['pos']}/72 positive.** All 15m configs and all but one 1h config lose money net (round-trip cost is ≈0.14–0.19R per trade at 0.05%/side and ≈0.4–0.6R at 0.15%/side on 15m, because the stop is only ~0.5–0.7% away; ≈0.03–0.04R / 0.10–0.12R on 4h).")
A(f"- Only the **4h** timeframe is net-positive on average at 0.05%/side. Nominal (unadjusted) one-sided p<0.05 for mean R>0: {cnt[1]['p05']}/72 configs (chance alone would give ≈3.6). **After Holm correction across the 72 configs: {cnt[1]['holm']}/72 survive** (0.15%/side: {cnt[2]['holm']}/72). White-style joint max-t Reality-Check p = {r(1, cells[0])['rc_p']:.2f} (0.05%/side) and {r(2, cells[0])['rc_p']:.2f} (0.15%/side) — i.e. the best of 72 is what you would expect from the best of 72 random configs.")
A(f"- Best config at 0.05%/side: **{nm(b0)}** — n={r(H,b0)['n']}, win {r(H,b0)['win']*100:.1f}%, avg net {f(r(H,b0)['mean'])}R, PF {r(H,b0)['pf']:.2f}, 95% block-bootstrap CI {ci_(r(H,b0)['ci'])} (excludes 0 *before* multiple-testing correction), but Holm-adjusted p = {r(H,b0)['p_holm']:.2f}, Δ vs random entry {f(r(H,b0)['diff'])}R (CI {ci_(r(H,b0)['diff_ci'])}, Holm p {r(H,b0)['p_diff_holm']:.2f}), Deflated Sharpe (N=72) = {r(H,b0)['dsr72']:.3f}, PSR(N=1) = {r(H,b0)['psr']:.3f}. At 0.15%/side the same config: avg {f(r(2,b0)['mean'])}R, CI {ci_(r(2,b0)['ci'])} → includes 0.")
A(f"- **Deflated Sharpe > 0.95: {cnt[1]['dsr']}/72 configs** (0.05%/side; {cnt[2]['dsr']}/72 at 0.15%/side). Best daily Sharpe of any config = {J['D']['1']['best_sr']:.3f} (ann. {J['D']['1']['best_sr']*365**.5:.2f}) vs expected-max-under-null SR0 = {J['D']['1']['sr0_72']:.3f} (N=72).")
A(f"- Random-entry baseline (same stops/targets/direction mix) is itself slightly negative net (−0.01 to −0.19R depending on TF/stop; mostly cost drag). Setup minus baseline: {cnt[1]['dpos']}/72 configs have a CI above 0 nominally; {cnt[1]['dholm']}/72 after Holm. The only hint of structure is on 4h (IFVG, Breaker Flow, CISD, MSS+FVG show gross R ≈ +0.05…+0.25 and beat the random baseline nominally) — **not significant after correcting for 72 looks, fading in recent data (2026 YTD is negative for IFVG, CISD and MSS+FVG; CISD/MSS first-half ≫ second-half, see §6), and not robust to 0.15%/side costs.** The four 4h setups are largely the same 'retest/reversal after a structure move' trade, so they are not independent confirmations of each other.")
A("- **Verdict: no tradable edge demonstrated.** On 15m and 1h the six setups are no better than random entries with the same stop/target geometry and costs make them clearly negative. On 4h there is a small positive tilt for IFVG / Breaker Flow / CISD / MSS+FVG (net ≈ +0.04…+0.10R/trade at 0.05%/side on average, positive in both long and short for CISD/Breaker, positive on 8–10 of 12 pairs for IFVG/Breaker/CISD in the zone-stop 2R headline view) — but it is not significant after correcting for 72 configs, decays in 2026, and is ≈0 at 0.15%/side. Order Block and Suspension Block are negative on every timeframe. If anything is worth following, it is 4h only, via forward paper-trading with the frozen rules (no re-tuning), not live money.\n")
A("## 1) Data, pipeline, cost model")
A(f"- Data: Binance **USDT-M perpetual** klines from `data.binance.vision` (public bulk files; `fapi` REST is geo-blocked from this box, Gate futures REST only returns the latest ≤2000 candles and `data-api.binance.vision` is spot-only). 12 pairs: BTC ETH SOL BNB XRP DOGE ADA AVAX LINK NEAR LTC DOT; TFs 15m, 1h, 4h; each from its listing date (BTC/ETH 2020-01-01; SOL/AVAX/NEAR/DOGE/DOT from Jul–Oct 2020) to 2026-10-24 (closed candles only). ≈ 6.8 years, {J['nd']} calendar days of trade exits. A few small data gaps (≤ ~12 h, 2 per pair for 6 pairs) are ignored; fewer than 15 zero-volume bars/pair.")
A("- Cost model = the existing one (`combo_bt2.py`: round trip 0.1% / 0.3% = **0.05% and 0.15% per side, fee+slippage**), applied as net R = gross R − 2·cost·entry/risk. Gross also shown. **Not modelled: funding payments, partial fills, spread widening on news bars.** 0.05%/side is optimistic for small-cap perps on 15m (Binance taker alone ≈ 0.04–0.05%); 0.15%/side is closer to a pessimistic-but-realistic case.")
A("- Statistics (re-used from `overfit_stats.py`): Deflated Sharpe (Bailey–López de Prado, `dsr`, `exp_max_sr`), block bootstrap (resampling **7-day blocks with all pairs together**, 5000 resamples — the more conservative variant from step B because pairs are highly correlated), Holm step-down across the 72 configs, and a White-style studentised max-t Reality Check on the same resamples. Random-entry baseline compared via bootstrap of the difference.")
A("- DSR inputs: daily series = sum of net R of all pairs by exit day (zero on idle days), T = " + str(J["nd"]) + " days; V = cross-config variance of daily Sharpe; N = 72 (this study), sensitivity N = 72+1069 = 1141 (whole registry; `hypotheses.py`) and N = 864 (×12 pairs). Because V is dominated by configs with hugely negative Sharpe (15m), SR0 is large — I therefore also show V restricted to configs with n≥300; conclusions don't change.\n")
A("## 2) Setup definitions (all causal: evaluated at candle close of bar i, entry = open of bar i+1)")
A("""Common: ATR14 = 14-bar simple mean of true range (value at bar i uses bars ≤ i). **FVG** (bullish) = candles i-2,i-1,i with low[i] > high[i-2], zone [high[i-2], low[i]], size ≥ 0.25 ATR (bearish mirrored). **Swing** = fractal with 3 bars each side (confirmed 3 bars later, so only used after confirmation). **Structure break** = first *close* beyond the last confirmed unconsumed swing. **Retest signal** (setups 1,2,4,5,6): a zone, once *active*, is consumed on its **first touch**; the touch candle must be a rejection — long: low ≤ zone_high, close > zone_high and close > open (short mirrored: high ≥ zone_low, close < zone_low, close < open). Zones expire 50 bars after becoming active (pending zones: 50 bars after formation) and a candle closing through the far side of an active zone only consumes it (no signal). If both a long and a short signal fire on one bar they are discarded.

1. **IFVG**: bullish (bearish) FVG is *pending*; when a candle **closes** below its low (above its high) it flips: zone becomes resistance (support) active from the next bar. Trade first retest-rejection in the new direction (short after bullish FVG inversion, long after bearish inversion).
2. **Breaker Flow**: order block (definition in 5, formed by a bullish/bearish displacement) is *pending*; if price **closes** through the far side of the block before it expires, the zone flips (bullish OB → bearish breaker zone and vice-versa). Trade first retest-rejection in the flipped direction.
3. **CISD**: ≥2 (max 20) consecutive down candles ending at bar i-1 with series height (open of first candle − lowest low) ≥ 1 ATR, bar i-1 closed below the series' first open and **bar i closes above the open of the series' first candle** → long (mirror for up-series → short). Zone = [series low, series open] for the stop.
4. **Suspension Block**: lone candle x with FVGs on both sides: bullish if low[x] > high[x-2] and high[x] < low[x+2] (both gaps ≥ 0.25 ATR), confirmed at close of x+2 (bearish mirrored). Zone = candle x's range. Trade first retest-rejection in the displacement (trend) direction. (Very rare in 24/7 crypto: ~50 trades on 4h across all pairs.)
5. **Order Block**: displacement candle with body ≥ 1.5 × ATR14[i-1] that **closes beyond the last confirmed swing** (structure break). OB = last opposite-colour candle within the 5 bars before it; zone = that candle's high–low. Active from the next bar; trade first retest-rejection in the displacement direction.
6. **MSS + FVG**: market-structure state flips (first close above the last swing high while the previous break was downward = bullish MSS; mirrored for bearish; both directions traded) and a same-direction FVG (≥ 0.25 ATR) completes on the MSS candle or the next one; the FVG is the zone; trade first retest-rejection in the shift direction.

**Stops/targets** (fixed, both variants run): *zone stop*: beyond the zone / retest-candle extreme + 0.1 ATR, risk floor 0.5 ATR, trade skipped if risk > 3 ATR; *ATR stop*: 1.5 ATR from entry. Target = entry ± 1R or 2R. Stop checked before target when both are touched in the same bar; stop gaps fill at the open; time exit at the close of the 96th bar. One position at a time per (setup, pair, TF, config). **Random baseline**: for every (setup, pair, TF, config) the same number of entries at uniformly random bars (10 replicates), long/short mix matched to the setup, risk distribution (in ATR) drawn from the setup's own signals (zone stops) or 1.5 ATR, same targets/time-exit/non-overlap/cost model.

Lookahead guard: `test_nolookahead.py` re-computes every setup's signals on truncated histories and checks they are bit-identical to the full-history signals for all bars before the cut (passes: BTC 1h, ETH 15m, SOL 4h; ATR also checked) and that entry index > signal index.
Trials: parameters were fixed before looking at any result and **not** tuned; 72 configs registered in `hypotheses.py` as `ict_setups_E` (registry total 1069 → 1141).
""")
A("## 3) Aggregate results — all 72 configs, 0.05%/side costs (all pairs pooled)")
A("n = trades, win = net R>0, gross/net = avg R per trade, PF = profit factor (net), CI = 95% 7-day-block bootstrap of net avg R, base = random-entry baseline net avg R, Δ = setup − base with CI, p_H = Holm-adjusted one-sided p (mean>0), pΔ_H = Holm p for mean>baseline, PSR = P(true SR>0), DSR = Deflated Sharpe (N=72).\n")
A("| setup | TF | stop | tgt | n | win% | gross R | **net R** | PF | CI net | base R | Δ vs base [CI] | p_H | pΔ_H | PSR | DSR |"); A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in cells:
    x = r(1, c); g = r(0, c)
    A(f"| {SETUPS[c[0]]} | {TFS[c[1]]} | {STOPS[c[2]]} | {int(c[3])}R | {x['n']} | {x['win']*100:.1f} | {f(g['mean'])} | **{f(x['mean'])}** | {x['pf']:.2f} | {ci_(x['ci'])} | {f(x['base_mean'])} | {f(x['diff'])} {ci_(x['diff_ci'])} | {x['p_holm']:.2f} | {x['p_diff_holm']:.2f} | {x['psr']:.2f} | {x['dsr72']:.3f} |")
A("\n## 4) Aggregate at 0.15%/side (realistic-pessimistic): top 12 configs by net R, plus summary counts")
A(f"Configs with mean>0: {cnt[2]['pos']}/72; CI lower bound>0: {cnt[2]['ci_pos']}/72; Holm p<0.05: {cnt[2]['holm']}/72; DSR>0.95: {cnt[2]['dsr']}/72.\n")
A("| config | n | win% | net R | PF | CI | base R | Δ [CI] | p_H | DSR(N=72) |"); A("|---|---|---|---|---|---|---|---|---|---|")
for c in sorted(cells, key=lambda c: -r(2, c)["mean"])[:12]:
    x = r(2, c); A(f"| {nm(c)} | {x['n']} | {x['win']*100:.1f} | {f(x['mean'])} | {x['pf']:.2f} | {ci_(x['ci'])} | {f(x['base_mean'])} | {f(x['diff'])} {ci_(x['diff_ci'])} | {x['p_holm']:.2f} | {x['dsr72']:.3f} |")
A("\n### Summary counts (72 configs)")
A("| cost | mean R>0 | CI_low>0 | nominal p<0.05 | Holm p<0.05 | Δ-vs-baseline CI_low>0 | Δ Holm p<0.05 | DSR(N=72)>0.95 | DSR (V over n≥300)>0.95 | Reality-Check p (mean>0) | RC p (Δ>baseline) |"); A("|---|---|---|---|---|---|---|---|---|---|---|")
for ci in (0, 1, 2):
    k = cnt[ci]; A(f"| {CN[ci]} | {k['pos']} | {k['ci_pos']} | {k['p05']} | {k['holm']} | {k['dpos']} | {k['dholm']} | {k['dsr']} | {k['dsr_v3']} | {r(ci, cells[0])['rc_p']:.2f} | {r(ci, cells[0])['rc_p_diff']:.2f} |")
# by timeframe summary
A("\n### Average net R by setup × timeframe (mean over the 4 configs, 0.05%/side; gross in brackets)")
A("| setup | 15m | 1h | 4h |"); A("|---|---|---|---|")
for s in SETUPS:
    row = []
    for tf in range(3):
        cc = [c for c in cells if c[0] == s and c[1] == tf]; row.append(f"{np.mean([r(1,c)['mean'] for c in cc]):+.3f} ({np.mean([r(0,c)['mean'] for c in cc]):+.3f})")
    A(f"| {SETUPS[s]} | " + " | ".join(row) + " |")
A("\n## 5) Per setup × pair × timeframe (headline config fixed a priori: zone stop, 2R target, 0.05%/side)")
A("Cell = `n / win% / avg net R / PF`. All 4 configs × 2 cost levels (+gross) for every pair are in `outputs/research/ict/results_per_pair.csv`.\n")
rows = list(csv.DictReader(open("results_per_pair.csv")))
for s in SETUPS.values():
    A(f"**{s}**\n"); A("| pair | 15m | 1h | 4h |"); A("|---|---|---|---|")
    pairs = [p for p in dict.fromkeys(x["pair"] for x in rows)]
    posc = {tf: 0 for tf in TFS}
    for p in pairs:
        cells_ = []
        for tf in TFS:
            q = [x for x in rows if x["setup"] == s and x["tf"] == tf and x["pair"] == p and x["stop"] == "zone" and float(x["target_R"]) == 2.0][0]
            if int(q["n"]) == 0: cells_.append("0 / – / – / –"); continue
            pfv = float(q["pf_0.05"]); posc[tf] += float(q["avgR_0.05"]) > 0; cells_.append(f"{q['n']} / {float(q['win_0.05'])*100:.0f} / {float(q['avgR_0.05']):+.3f} / {pfv:.2f}")
        A(f"| {p} | " + " | ".join(cells_) + " |")
    A("| pairs with net R>0 | " + " | ".join(f"{posc[tf]}/12" for tf in TFS) + " |\n")
A("## 6) Stability: best configs by sub-period (0.05%/side net R; split at 2023-09-01, and by calendar year)")
A("| config | n | first half (≤2023-08) | second half | years (n: avg R) |"); A("|---|---|---|---|---|")
for c in best + [c for c in sorted(cells, key=lambda c: -r(H, c)["mean"])[6:10]]:
    x = r(H, c); yrs = "; ".join(f"{y}: {v[0]}: {v[1]:+.2f}" for y, v in sorted(x["years"].items(), key=lambda t: int(t[0])))
    A(f"| {nm(c)} | {x['n']} | {f(x['h1'])} (n={x['h1n']}) | {f(x['h2'])} (n={x['h2n']}) | {yrs} |")
A("\n### 6b) 4h direction split (net R at 0.05%/side; descriptive, not a new test)")
import numpy as _np
_z = _np.load("trades_ict.npz"); A("| setup | stop/tgt | long n / avg net R | short n / avg net R |"); A("|---|---|---|---|")
for _s in (1, 2, 3, 6):
    for _sm, _R in ((0, 2.0), (1, 2.0), (0, 1.0)):
        _m = (_z["setup"] == _s) & (_z["tf"] == 2) & (_z["stop"] == _sm) & (_z["tgt"] == _R); _o = []
        for _d in (1, -1):
            _mm = _m & (_z["dir"] == _d); _x = _z["g"][_mm] - 2 * 0.0005 * _z["k"][_mm]; _o.append(f"{_mm.sum()} / {_x.mean():+.3f}")
        A(f"| {SETUPS[_s]} 4h | {STOPS[_sm]} {int(_R)}R | {_o[0]} | {_o[1]} |")
A("""
## 7) Interpretation and caveats
- **Win rate ≈ 1/(1+R) on 15m/1h** (≈50% at 1R, ≈33% at 2R; 4h reaches 37–41% at 2R for IFVG/Breaker/CISD): the entry rule adds little or no directional information over a random entry on the lower timeframes; the video's 'ideal chart' examples are a selection effect.
- Costs matter more than the setups: median zone-stop risk is a fraction of a percent on 15m/1h, so a 0.1% round trip costs ≈0.14–0.19R per trade (0.4–0.6R at 0.15%/side). This alone makes every 15m configuration clearly negative (and every 15m gross edge ≈ 0).
- The 4h tilt (gross R +0.05…+0.25 for IFVG / Breaker / CISD / MSS+FVG) is not just long-side bull drift: CISD and Breaker are positive on both long and short trades (§6b); only MSS+FVG is long-only positive. But the baseline matches direction mix, not regime timing, and 2026 YTD is negative for IFVG/CISD/MSS+FVG. Treat it as a hypothesis, not a result: n is only 300–2000 trades per config, trades from 12 correlated pairs overlap in time (hence 7-day all-pair blocks), and 72 configs were examined.
- Not an out-of-sample test: definitions were fixed before looking, but the whole 2020–2026 history was used once; no parameter was tuned (a parameter sweep would add trials and make DSR worse). 
- Interpretive choices are mine (the video gives no formal rules): e.g. FVG min size 0.25 ATR, 50-bar expiry, first-touch-only, rejection-candle confirmation, 1.5 ATR displacement. Other readings of 'ICT' (premium/discount filters, killzones, higher-timeframe bias, partial TP, trailing) were **not** tested and are discretionary by nature; if they had an edge it would have to come from a discretionary overlay that cannot be backtested here.
- Funding not included (small drag/benefit for multi-bar holds), no liquidity limits, intrabar stop-vs-target ordering resolved pessimistically (stop first).
- Suspension Block has very few trades (esp. 4h: ~50) → CIs are wide; no conclusion possible except 'no evidence'.
""")
open("../../research_E_ict_setups.md", "w").write("\n".join(L)); print("written", len(L), "lines")
