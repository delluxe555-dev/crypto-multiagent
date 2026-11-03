# Step E — Rule-based test of 6 ICT-style setups (from the X video) on 12 USDT-M perps × 15m/1h/4h
*Generated 2026-10-25 18:11 (Europe/Istanbul). Code: `outputs/research/ict/` (fetch_data.py, ict_setups.py, run_ict.py, stats_ict.py, make_report.py, test_nolookahead.py). Per-pair raw table: `outputs/research/ict/results_per_pair.csv`.*

## 0) TL;DR / verdict
- **No setup shows a robust edge after costs.** 72 configs (6 setups × 3 TF × 2 stop types × 2 targets), 405,319 simulated trades, 12 pairs, 2020-01-01 → 2026-10-24.
- Gross (before costs): 36/72 configs have mean R > 0, but on 15m/1h the gross edge is ≈0 (avg gross R between −0.02 and +0.03; win rate ≈ 1/(1+R), a coin-flip with R-multiples), while on **4h** IFVG / Breaker Flow / CISD / MSS+FVG show avg gross R of +0.07…+0.14. **After 0.05%/side costs: 17/72 positive; after 0.15%/side: 5/72 positive.** All 15m configs and all but one 1h config lose money net (round-trip cost is ≈0.14–0.19R per trade at 0.05%/side and ≈0.4–0.6R at 0.15%/side on 15m, because the stop is only ~0.5–0.7% away; ≈0.03–0.04R / 0.10–0.12R on 4h).
- Only the **4h** timeframe is net-positive on average at 0.05%/side. Nominal (unadjusted) one-sided p<0.05 for mean R>0: 2/72 configs (chance alone would give ≈3.6). **After Holm correction across the 72 configs: 0/72 survive** (0.15%/side: 0/72). White-style joint max-t Reality-Check p = 0.41 (0.05%/side) and 0.88 (0.15%/side) — i.e. the best of 72 is what you would expect from the best of 72 random configs.
- Best config at 0.05%/side: **BreakerFlow 4h zone 2R** — n=309, win 41.4%, avg net +0.209R, PF 1.35, 95% block-bootstrap CI [+0.032, +0.389] (excludes 0 *before* multiple-testing correction), but Holm-adjusted p = 0.72, Δ vs random entry +0.260R (CI [+0.026, +0.493], Holm p 0.88), Deflated Sharpe (N=72) = 0.000, PSR(N=1) = 0.995. At 0.15%/side the same config: avg +0.139R, CI [-0.039, +0.319] → includes 0.
- **Deflated Sharpe > 0.95: 0/72 configs** (0.05%/side; 0/72 at 0.15%/side). Best daily Sharpe of any config = 0.049 (ann. 0.93) vs expected-max-under-null SR0 = 0.305 (N=72).
- Random-entry baseline (same stops/targets/direction mix) is itself slightly negative net (−0.01 to −0.19R depending on TF/stop; mostly cost drag). Setup minus baseline: 4/72 configs have a CI above 0 nominally; 0/72 after Holm. The only hint of structure is on 4h (IFVG, Breaker Flow, CISD, MSS+FVG show gross R ≈ +0.05…+0.25 and beat the random baseline nominally) — **not significant after correcting for 72 looks, fading in recent data (2026 YTD is negative for IFVG, CISD and MSS+FVG; CISD/MSS first-half ≫ second-half, see §6), and not robust to 0.15%/side costs.** The four 4h setups are largely the same 'retest/reversal after a structure move' trade, so they are not independent confirmations of each other.
- **Verdict: no tradable edge demonstrated.** On 15m and 1h the six setups are no better than random entries with the same stop/target geometry and costs make them clearly negative. On 4h there is a small positive tilt for IFVG / Breaker Flow / CISD / MSS+FVG (net ≈ +0.04…+0.10R/trade at 0.05%/side on average, positive in both long and short for CISD/Breaker, positive on 8–10 of 12 pairs for IFVG/Breaker/CISD in the zone-stop 2R headline view) — but it is not significant after correcting for 72 configs, decays in 2026, and is ≈0 at 0.15%/side. Order Block and Suspension Block are negative on every timeframe. If anything is worth following, it is 4h only, via forward paper-trading with the frozen rules (no re-tuning), not live money.

## 1) Data, pipeline, cost model
- Data: Binance **USDT-M perpetual** klines from `data.binance.vision` (public bulk files; `fapi` REST is geo-blocked from this box, Gate futures REST only returns the latest ≤2000 candles and `data-api.binance.vision` is spot-only). 12 pairs: BTC ETH SOL BNB XRP DOGE ADA AVAX LINK NEAR LTC DOT; TFs 15m, 1h, 4h; each from its listing date (BTC/ETH 2020-01-01; SOL/AVAX/NEAR/DOGE/DOT from Jul–Oct 2020) to 2026-10-24 (closed candles only). ≈ 6.8 years, 2489 calendar days of trade exits. A few small data gaps (≤ ~12 h, 2 per pair for 6 pairs) are ignored; fewer than 15 zero-volume bars/pair.
- Cost model = the existing one (`combo_bt2.py`: round trip 0.1% / 0.3% = **0.05% and 0.15% per side, fee+slippage**), applied as net R = gross R − 2·cost·entry/risk. Gross also shown. **Not modelled: funding payments, partial fills, spread widening on news bars.** 0.05%/side is optimistic for small-cap perps on 15m (Binance taker alone ≈ 0.04–0.05%); 0.15%/side is closer to a pessimistic-but-realistic case.
- Statistics (re-used from `overfit_stats.py`): Deflated Sharpe (Bailey–López de Prado, `dsr`, `exp_max_sr`), block bootstrap (resampling **7-day blocks with all pairs together**, 5000 resamples — the more conservative variant from step B because pairs are highly correlated), Holm step-down across the 72 configs, and a White-style studentised max-t Reality Check on the same resamples. Random-entry baseline compared via bootstrap of the difference.
- DSR inputs: daily series = sum of net R of all pairs by exit day (zero on idle days), T = 2489 days; V = cross-config variance of daily Sharpe; N = 72 (this study), sensitivity N = 72+1069 = 1141 (whole registry; `hypotheses.py`) and N = 864 (×12 pairs). Because V is dominated by configs with hugely negative Sharpe (15m), SR0 is large — I therefore also show V restricted to configs with n≥300; conclusions don't change.

## 2) Setup definitions (all causal: evaluated at candle close of bar i, entry = open of bar i+1)
Common: ATR14 = 14-bar simple mean of true range (value at bar i uses bars ≤ i). **FVG** (bullish) = candles i-2,i-1,i with low[i] > high[i-2], zone [high[i-2], low[i]], size ≥ 0.25 ATR (bearish mirrored). **Swing** = fractal with 3 bars each side (confirmed 3 bars later, so only used after confirmation). **Structure break** = first *close* beyond the last confirmed unconsumed swing. **Retest signal** (setups 1,2,4,5,6): a zone, once *active*, is consumed on its **first touch**; the touch candle must be a rejection — long: low ≤ zone_high, close > zone_high and close > open (short mirrored: high ≥ zone_low, close < zone_low, close < open). Zones expire 50 bars after becoming active (pending zones: 50 bars after formation) and a candle closing through the far side of an active zone only consumes it (no signal). If both a long and a short signal fire on one bar they are discarded.

1. **IFVG**: bullish (bearish) FVG is *pending*; when a candle **closes** below its low (above its high) it flips: zone becomes resistance (support) active from the next bar. Trade first retest-rejection in the new direction (short after bullish FVG inversion, long after bearish inversion).
2. **Breaker Flow**: order block (definition in 5, formed by a bullish/bearish displacement) is *pending*; if price **closes** through the far side of the block before it expires, the zone flips (bullish OB → bearish breaker zone and vice-versa). Trade first retest-rejection in the flipped direction.
3. **CISD**: ≥2 (max 20) consecutive down candles ending at bar i-1 with series height (open of first candle − lowest low) ≥ 1 ATR, bar i-1 closed below the series' first open and **bar i closes above the open of the series' first candle** → long (mirror for up-series → short). Zone = [series low, series open] for the stop.
4. **Suspension Block**: lone candle x with FVGs on both sides: bullish if low[x] > high[x-2] and high[x] < low[x+2] (both gaps ≥ 0.25 ATR), confirmed at close of x+2 (bearish mirrored). Zone = candle x's range. Trade first retest-rejection in the displacement (trend) direction. (Very rare in 24/7 crypto: ~50 trades on 4h across all pairs.)
5. **Order Block**: displacement candle with body ≥ 1.5 × ATR14[i-1] that **closes beyond the last confirmed swing** (structure break). OB = last opposite-colour candle within the 5 bars before it; zone = that candle's high–low. Active from the next bar; trade first retest-rejection in the displacement direction.
6. **MSS + FVG**: market-structure state flips (first close above the last swing high while the previous break was downward = bullish MSS; mirrored for bearish; both directions traded) and a same-direction FVG (≥ 0.25 ATR) completes on the MSS candle or the next one; the FVG is the zone; trade first retest-rejection in the shift direction.

**Stops/targets** (fixed, both variants run): *zone stop*: beyond the zone / retest-candle extreme + 0.1 ATR, risk floor 0.5 ATR, trade skipped if risk > 3 ATR; *ATR stop*: 1.5 ATR from entry. Target = entry ± 1R or 2R. Stop checked before target when both are touched in the same bar; stop gaps fill at the open; time exit at the close of the 96th bar. One position at a time per (setup, pair, TF, config). **Random baseline**: for every (setup, pair, TF, config) the same number of entries at uniformly random bars (10 replicates), long/short mix matched to the setup, risk distribution (in ATR) drawn from the setup's own signals (zone stops) or 1.5 ATR, same targets/time-exit/non-overlap/cost model.

Lookahead guard: `test_nolookahead.py` re-computes every setup's signals on truncated histories and checks they are bit-identical to the full-history signals for all bars before the cut (passes: BTC 1h, ETH 15m, SOL 4h; ATR also checked) and that entry index > signal index.
Trials: parameters were fixed before looking at any result and **not** tuned; 72 configs registered in `hypotheses.py` as `ict_setups_E` (registry total 1069 → 1141).

## 3) Aggregate results — all 72 configs, 0.05%/side costs (all pairs pooled)
n = trades, win = net R>0, gross/net = avg R per trade, PF = profit factor (net), CI = 95% 7-day-block bootstrap of net avg R, base = random-entry baseline net avg R, Δ = setup − base with CI, p_H = Holm-adjusted one-sided p (mean>0), pΔ_H = Holm p for mean>baseline, PSR = P(true SR>0), DSR = Deflated Sharpe (N=72).

| setup | TF | stop | tgt | n | win% | gross R | **net R** | PF | CI net | base R | Δ vs base [CI] | p_H | pΔ_H | PSR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IFVG | 15m | zone | 1R | 39707 | 48.9 | -0.019 | **-0.206** | 0.66 | [-0.221, -0.192] | -0.201 | -0.006 [-0.022, +0.011] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 15m | zone | 2R | 36951 | 32.9 | -0.020 | **-0.206** | 0.74 | [-0.226, -0.188] | -0.189 | -0.017 [-0.041, +0.006] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 15m | atr1.5 | 1R | 39747 | 49.7 | -0.005 | **-0.148** | 0.74 | [-0.161, -0.135] | -0.142 | -0.006 [-0.022, +0.010] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 15m | atr1.5 | 2R | 36061 | 33.4 | -0.002 | **-0.144** | 0.81 | [-0.163, -0.126] | -0.139 | -0.006 [-0.027, +0.016] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 1h | zone | 1R | 8773 | 48.8 | -0.024 | **-0.109** | 0.80 | [-0.131, -0.085] | -0.099 | -0.010 [-0.041, +0.024] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 1h | zone | 2R | 8237 | 33.2 | -0.011 | **-0.096** | 0.87 | [-0.128, -0.061] | -0.085 | -0.011 [-0.049, +0.034] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 1h | atr1.5 | 1R | 8941 | 49.6 | -0.009 | **-0.073** | 0.86 | [-0.096, -0.050] | -0.065 | -0.008 [-0.039, +0.020] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 1h | atr1.5 | 2R | 8201 | 33.6 | +0.003 | **-0.062** | 0.91 | [-0.096, -0.028] | -0.059 | -0.003 [-0.046, +0.040] | 1.00 | 1.00 | 0.00 | 0.000 |
| IFVG | 4h | zone | 1R | 2234 | 52.1 | +0.042 | **+0.004** | 1.01 | [-0.046, +0.053] | -0.053 | +0.057 [-0.013, +0.130] | 1.00 | 1.00 | 0.57 | 0.000 |
| IFVG | 4h | zone | 2R | 2058 | 37.0 | +0.096 | **+0.058** | 1.09 | [-0.023, +0.136] | -0.044 | +0.102 [+0.008, +0.196] | 1.00 | 1.00 | 0.94 | 0.000 |
| IFVG | 4h | atr1.5 | 1R | 2259 | 52.8 | +0.056 | **+0.026** | 1.05 | [-0.028, +0.079] | -0.043 | +0.069 [-0.002, +0.131] | 1.00 | 1.00 | 0.85 | 0.000 |
| IFVG | 4h | atr1.5 | 2R | 2048 | 37.8 | +0.123 | **+0.093** | 1.15 | [+0.010, +0.170] | -0.023 | +0.116 [+0.008, +0.217] | 1.00 | 1.00 | 0.99 | 0.000 |
| BreakerFlow | 15m | zone | 1R | 4051 | 49.6 | -0.006 | **-0.151** | 0.74 | [-0.184, -0.119] | -0.178 | +0.027 [-0.014, +0.072] | 1.00 | 1.00 | 0.00 | 0.000 |
| BreakerFlow | 15m | zone | 2R | 4027 | 33.8 | +0.002 | **-0.143** | 0.81 | [-0.191, -0.095] | -0.164 | +0.021 [-0.036, +0.080] | 1.00 | 1.00 | 0.00 | 0.000 |
| BreakerFlow | 15m | atr1.5 | 1R | 4188 | 50.3 | +0.008 | **-0.127** | 0.77 | [-0.161, -0.094] | -0.156 | +0.029 [-0.021, +0.076] | 1.00 | 1.00 | 0.00 | 0.000 |
| BreakerFlow | 15m | atr1.5 | 2R | 4153 | 33.9 | +0.007 | **-0.128** | 0.83 | [-0.176, -0.077] | -0.139 | +0.011 [-0.062, +0.077] | 1.00 | 1.00 | 0.00 | 0.000 |
| BreakerFlow | 1h | zone | 1R | 1080 | 49.9 | -0.001 | **-0.069** | 0.87 | [-0.135, -0.004] | -0.090 | +0.022 [-0.061, +0.097] | 1.00 | 1.00 | 0.02 | 0.000 |
| BreakerFlow | 1h | zone | 2R | 1066 | 35.1 | +0.039 | **-0.029** | 0.96 | [-0.123, +0.065] | -0.095 | +0.067 [-0.056, +0.193] | 1.00 | 1.00 | 0.28 | 0.000 |
| BreakerFlow | 1h | atr1.5 | 1R | 1121 | 51.5 | +0.030 | **-0.033** | 0.94 | [-0.093, +0.028] | -0.044 | +0.011 [-0.072, +0.085] | 1.00 | 1.00 | 0.16 | 0.000 |
| BreakerFlow | 1h | atr1.5 | 2R | 1108 | 36.0 | +0.074 | **+0.011** | 1.02 | [-0.080, +0.103] | -0.102 | +0.113 [+0.015, +0.215] | 1.00 | 0.78 | 0.59 | 0.000 |
| BreakerFlow | 4h | zone | 1R | 311 | 54.7 | +0.093 | **+0.058** | 1.12 | [-0.061, +0.178] | -0.089 | +0.147 [-0.027, +0.324] | 1.00 | 1.00 | 0.83 | 0.000 |
| BreakerFlow | 4h | zone | 2R | 309 | 41.4 | +0.244 | **+0.209** | 1.35 | [+0.032, +0.389] | -0.050 | +0.260 [+0.026, +0.493] | 0.72 | 0.88 | 0.99 | 0.000 |
| BreakerFlow | 4h | atr1.5 | 1R | 316 | 52.8 | +0.054 | **+0.024** | 1.05 | [-0.086, +0.141] | -0.024 | +0.048 [-0.110, +0.218] | 1.00 | 1.00 | 0.66 | 0.000 |
| BreakerFlow | 4h | atr1.5 | 2R | 315 | 39.0 | +0.154 | **+0.124** | 1.20 | [-0.048, +0.306] | -0.037 | +0.161 [-0.118, +0.424] | 1.00 | 1.00 | 0.93 | 0.000 |
| CISD | 15m | zone | 1R | 24731 | 50.8 | +0.018 | **-0.118** | 0.79 | [-0.136, -0.099] | -0.132 | +0.014 [-0.006, +0.035] | 1.00 | 1.00 | 0.00 | 0.000 |
| CISD | 15m | zone | 2R | 23008 | 34.6 | +0.023 | **-0.111** | 0.85 | [-0.136, -0.088] | -0.128 | +0.017 [-0.017, +0.050] | 1.00 | 1.00 | 0.00 | 0.000 |
| CISD | 15m | atr1.5 | 1R | 26595 | 51.1 | +0.022 | **-0.131** | 0.77 | [-0.151, -0.112] | -0.147 | +0.015 [-0.007, +0.037] | 1.00 | 1.00 | 0.00 | 0.000 |
| CISD | 15m | atr1.5 | 2R | 25085 | 34.1 | +0.021 | **-0.132** | 0.83 | [-0.158, -0.107] | -0.142 | +0.010 [-0.019, +0.040] | 1.00 | 1.00 | 0.00 | 0.000 |
| CISD | 1h | zone | 1R | 5992 | 51.3 | +0.026 | **-0.034** | 0.93 | [-0.068, +0.001] | -0.059 | +0.025 [-0.018, +0.069] | 1.00 | 1.00 | 0.02 | 0.000 |
| CISD | 1h | zone | 2R | 5576 | 34.9 | +0.029 | **-0.032** | 0.95 | [-0.081, +0.019] | -0.054 | +0.022 [-0.032, +0.080] | 1.00 | 1.00 | 0.10 | 0.000 |
| CISD | 1h | atr1.5 | 1R | 6487 | 51.2 | +0.025 | **-0.045** | 0.91 | [-0.078, -0.011] | -0.067 | +0.022 [-0.016, +0.060] | 1.00 | 1.00 | 0.00 | 0.000 |
| CISD | 1h | atr1.5 | 2R | 6145 | 34.4 | +0.029 | **-0.040** | 0.94 | [-0.087, +0.008] | -0.053 | +0.013 [-0.045, +0.079] | 1.00 | 1.00 | 0.05 | 0.000 |
| CISD | 4h | zone | 1R | 1507 | 52.2 | +0.043 | **+0.016** | 1.03 | [-0.048, +0.083] | -0.024 | +0.040 [-0.048, +0.143] | 1.00 | 1.00 | 0.68 | 0.000 |
| CISD | 4h | zone | 2R | 1409 | 37.3 | +0.110 | **+0.083** | 1.13 | [-0.018, +0.187] | -0.034 | +0.118 [-0.004, +0.235] | 1.00 | 1.00 | 0.96 | 0.000 |
| CISD | 4h | atr1.5 | 1R | 1684 | 52.5 | +0.050 | **+0.017** | 1.04 | [-0.051, +0.088] | -0.031 | +0.048 [-0.029, +0.132] | 1.00 | 1.00 | 0.69 | 0.000 |
| CISD | 4h | atr1.5 | 2R | 1598 | 36.5 | +0.095 | **+0.063** | 1.10 | [-0.034, +0.163] | -0.021 | +0.084 [-0.022, +0.195] | 1.00 | 1.00 | 0.90 | 0.000 |
| SuspensionBlock | 15m | zone | 1R | 1085 | 48.3 | -0.025 | **-0.159** | 0.73 | [-0.224, -0.095] | -0.125 | -0.034 [-0.118, +0.064] | 1.00 | 1.00 | 0.00 | 0.000 |
| SuspensionBlock | 15m | zone | 2R | 1082 | 33.1 | -0.021 | **-0.154** | 0.79 | [-0.240, -0.064] | -0.138 | -0.016 [-0.123, +0.109] | 1.00 | 1.00 | 0.00 | 0.000 |
| SuspensionBlock | 15m | atr1.5 | 1R | 1160 | 48.4 | -0.027 | **-0.163** | 0.72 | [-0.221, -0.105] | -0.147 | -0.016 [-0.103, +0.052] | 1.00 | 1.00 | 0.00 | 0.000 |
| SuspensionBlock | 15m | atr1.5 | 2R | 1158 | 34.4 | +0.029 | **-0.108** | 0.85 | [-0.191, -0.021] | -0.140 | +0.032 [-0.067, +0.130] | 1.00 | 1.00 | 0.01 | 0.000 |
| SuspensionBlock | 1h | zone | 1R | 250 | 40.4 | -0.192 | **-0.246** | 0.61 | [-0.377, -0.117] | -0.052 | -0.194 [-0.347, -0.039] | 1.00 | 1.00 | 0.00 | 0.000 |
| SuspensionBlock | 1h | zone | 2R | 250 | 25.6 | -0.234 | **-0.288** | 0.63 | [-0.461, -0.110] | -0.074 | -0.214 [-0.425, +0.017] | 1.00 | 1.00 | 0.00 | 0.000 |
| SuspensionBlock | 1h | atr1.5 | 1R | 267 | 45.3 | -0.091 | **-0.152** | 0.74 | [-0.279, -0.021] | -0.060 | -0.092 [-0.256, +0.099] | 1.00 | 1.00 | 0.01 | 0.000 |
| SuspensionBlock | 1h | atr1.5 | 2R | 266 | 28.2 | -0.148 | **-0.209** | 0.72 | [-0.387, -0.016] | -0.081 | -0.128 [-0.359, +0.099] | 1.00 | 1.00 | 0.01 | 0.000 |
| SuspensionBlock | 4h | zone | 1R | 48 | 50.0 | +0.010 | **-0.021** | 0.96 | [-0.297, +0.259] | -0.012 | -0.009 [-0.391, +0.529] | 1.00 | 1.00 | 0.44 | 0.000 |
| SuspensionBlock | 4h | zone | 2R | 48 | 31.2 | -0.133 | **-0.164** | 0.76 | [-0.534, +0.221] | -0.055 | -0.109 [-0.643, +0.474] | 1.00 | 1.00 | 0.21 | 0.000 |
| SuspensionBlock | 4h | atr1.5 | 1R | 50 | 44.0 | -0.131 | **-0.164** | 0.72 | [-0.429, +0.110] | -0.021 | -0.143 [-0.617, +0.344] | 1.00 | 1.00 | 0.12 | 0.000 |
| SuspensionBlock | 4h | atr1.5 | 2R | 50 | 28.0 | -0.201 | **-0.234** | 0.68 | [-0.583, +0.163] | +0.011 | -0.245 [-0.838, +0.232] | 1.00 | 1.00 | 0.12 | 0.000 |
| OrderBlock | 15m | zone | 1R | 3037 | 49.7 | -0.004 | **-0.139** | 0.76 | [-0.178, -0.101] | -0.141 | +0.002 [-0.045, +0.047] | 1.00 | 1.00 | 0.00 | 0.000 |
| OrderBlock | 15m | zone | 2R | 3026 | 32.5 | -0.040 | **-0.175** | 0.77 | [-0.226, -0.125] | -0.140 | -0.035 [-0.106, +0.037] | 1.00 | 1.00 | 0.00 | 0.000 |
| OrderBlock | 15m | atr1.5 | 1R | 3204 | 49.4 | -0.010 | **-0.155** | 0.73 | [-0.192, -0.118] | -0.135 | -0.020 [-0.072, +0.031] | 1.00 | 1.00 | 0.00 | 0.000 |
| OrderBlock | 15m | atr1.5 | 2R | 3191 | 32.1 | -0.043 | **-0.188** | 0.76 | [-0.240, -0.136] | -0.148 | -0.040 [-0.114, +0.025] | 1.00 | 1.00 | 0.00 | 0.000 |
| OrderBlock | 1h | zone | 1R | 813 | 50.3 | +0.008 | **-0.051** | 0.90 | [-0.127, +0.023] | -0.065 | +0.013 [-0.086, +0.131] | 1.00 | 1.00 | 0.08 | 0.000 |
| OrderBlock | 1h | zone | 2R | 808 | 33.4 | -0.014 | **-0.073** | 0.90 | [-0.168, +0.026] | -0.069 | -0.005 [-0.110, +0.105] | 1.00 | 1.00 | 0.08 | 0.000 |
| OrderBlock | 1h | atr1.5 | 1R | 884 | 50.8 | +0.018 | **-0.048** | 0.91 | [-0.119, +0.018] | -0.083 | +0.034 [-0.047, +0.112] | 1.00 | 1.00 | 0.09 | 0.000 |
| OrderBlock | 1h | atr1.5 | 2R | 879 | 32.3 | -0.031 | **-0.097** | 0.86 | [-0.189, -0.002] | -0.089 | -0.008 [-0.127, +0.122] | 1.00 | 1.00 | 0.03 | 0.000 |
| OrderBlock | 4h | zone | 1R | 203 | 46.3 | -0.076 | **-0.104** | 0.81 | [-0.254, +0.040] | -0.029 | -0.075 [-0.278, +0.098] | 1.00 | 1.00 | 0.08 | 0.000 |
| OrderBlock | 4h | zone | 2R | 201 | 26.9 | -0.198 | **-0.226** | 0.70 | [-0.410, -0.037] | -0.025 | -0.200 [-0.482, +0.083] | 1.00 | 1.00 | 0.01 | 0.000 |
| OrderBlock | 4h | atr1.5 | 1R | 216 | 47.7 | -0.046 | **-0.077** | 0.86 | [-0.218, +0.067] | -0.033 | -0.044 [-0.310, +0.151] | 1.00 | 1.00 | 0.15 | 0.000 |
| OrderBlock | 4h | atr1.5 | 2R | 214 | 28.5 | -0.142 | **-0.173** | 0.76 | [-0.357, +0.012] | +0.036 | -0.209 [-0.471, +0.055] | 1.00 | 1.00 | 0.04 | 0.000 |
| MSS_FVG | 15m | zone | 1R | 6684 | 49.1 | -0.016 | **-0.189** | 0.68 | [-0.215, -0.162] | -0.178 | -0.011 [-0.044, +0.021] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 15m | zone | 2R | 6634 | 33.3 | -0.014 | **-0.187** | 0.76 | [-0.225, -0.150] | -0.176 | -0.011 [-0.061, +0.035] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 15m | atr1.5 | 1R | 6873 | 48.8 | -0.022 | **-0.170** | 0.71 | [-0.198, -0.142] | -0.150 | -0.020 [-0.060, +0.016] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 15m | atr1.5 | 2R | 6810 | 32.8 | -0.022 | **-0.170** | 0.78 | [-0.209, -0.131] | -0.147 | -0.023 [-0.077, +0.031] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 1h | zone | 1R | 1651 | 50.0 | +0.001 | **-0.080** | 0.85 | [-0.131, -0.029] | -0.092 | +0.012 [-0.050, +0.077] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 1h | zone | 2R | 1638 | 32.0 | -0.054 | **-0.134** | 0.82 | [-0.210, -0.055] | -0.086 | -0.048 [-0.143, +0.045] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 1h | atr1.5 | 1R | 1725 | 50.0 | -0.000 | **-0.069** | 0.87 | [-0.123, -0.018] | -0.073 | +0.004 [-0.067, +0.077] | 1.00 | 1.00 | 0.00 | 0.000 |
| MSS_FVG | 1h | atr1.5 | 2R | 1706 | 33.2 | -0.012 | **-0.080** | 0.89 | [-0.156, -0.008] | -0.049 | -0.032 [-0.132, +0.056] | 1.00 | 1.00 | 0.02 | 0.000 |
| MSS_FVG | 4h | zone | 1R | 524 | 55.0 | +0.098 | **+0.063** | 1.14 | [-0.038, +0.156] | -0.023 | +0.086 [-0.036, +0.200] | 1.00 | 1.00 | 0.90 | 0.000 |
| MSS_FVG | 4h | zone | 2R | 512 | 35.5 | +0.042 | **+0.007** | 1.01 | [-0.137, +0.148] | -0.041 | +0.048 [-0.122, +0.230] | 1.00 | 1.00 | 0.54 | 0.000 |
| MSS_FVG | 4h | atr1.5 | 1R | 552 | 54.9 | +0.096 | **+0.065** | 1.14 | [-0.040, +0.159] | -0.036 | +0.101 [-0.029, +0.218] | 1.00 | 1.00 | 0.90 | 0.000 |
| MSS_FVG | 4h | atr1.5 | 2R | 541 | 35.3 | +0.050 | **+0.018** | 1.03 | [-0.131, +0.167] | -0.045 | +0.063 [-0.101, +0.223] | 1.00 | 1.00 | 0.60 | 0.000 |

## 4) Aggregate at 0.15%/side (realistic-pessimistic): top 12 configs by net R, plus summary counts
Configs with mean>0: 5/72; CI lower bound>0: 0/72; Holm p<0.05: 0/72; DSR>0.95: 0/72.

| config | n | win% | net R | PF | CI | base R | Δ [CI] | p_H | DSR(N=72) |
|---|---|---|---|---|---|---|---|---|---|
| BreakerFlow 4h zone 2R | 309 | 41.4 | +0.139 | 1.22 | [-0.039, +0.319] | -0.126 | +0.266 [+0.037, +0.491] | 1.00 | 0.000 |
| BreakerFlow 4h atr1.5 2R | 315 | 39.0 | +0.063 | 1.10 | [-0.108, +0.245] | -0.101 | +0.164 [-0.116, +0.427] | 1.00 | 0.000 |
| IFVG 4h atr1.5 2R | 2048 | 37.8 | +0.034 | 1.05 | [-0.049, +0.111] | -0.084 | +0.118 [+0.008, +0.219] | 1.00 | 0.000 |
| CISD 4h zone 2R | 1409 | 37.2 | +0.029 | 1.04 | [-0.073, +0.134] | -0.086 | +0.115 [-0.011, +0.232] | 1.00 | 0.000 |
| MSS_FVG 4h atr1.5 1R | 552 | 54.9 | +0.002 | 1.00 | [-0.103, +0.098] | -0.100 | +0.102 [-0.021, +0.220] | 1.00 | 0.000 |
| CISD 4h atr1.5 2R | 1598 | 36.5 | -0.002 | 1.00 | [-0.099, +0.099] | -0.082 | +0.080 [-0.024, +0.191] | 1.00 | 0.000 |
| MSS_FVG 4h zone 1R | 524 | 55.0 | -0.007 | 0.99 | [-0.108, +0.087] | -0.094 | +0.087 [-0.039, +0.200] | 1.00 | 0.000 |
| BreakerFlow 4h zone 1R | 311 | 54.7 | -0.012 | 0.98 | [-0.133, +0.109] | -0.166 | +0.154 [-0.014, +0.329] | 1.00 | 0.000 |
| IFVG 4h zone 2R | 2058 | 37.0 | -0.017 | 0.98 | [-0.099, +0.061] | -0.123 | +0.106 [+0.010, +0.205] | 1.00 | 0.000 |
| IFVG 4h atr1.5 1R | 2259 | 52.8 | -0.033 | 0.94 | [-0.087, +0.020] | -0.104 | +0.071 [+0.000, +0.132] | 1.00 | 0.000 |
| BreakerFlow 4h atr1.5 1R | 316 | 52.8 | -0.036 | 0.93 | [-0.147, +0.080] | -0.088 | +0.052 [-0.104, +0.222] | 1.00 | 0.000 |
| CISD 4h zone 1R | 1507 | 52.1 | -0.039 | 0.92 | [-0.103, +0.028] | -0.076 | +0.037 [-0.050, +0.139] | 1.00 | 0.000 |

### Summary counts (72 configs)
| cost | mean R>0 | CI_low>0 | nominal p<0.05 | Holm p<0.05 | Δ-vs-baseline CI_low>0 | Δ Holm p<0.05 | DSR(N=72)>0.95 | DSR (V over n≥300)>0.95 | Reality-Check p (mean>0) | RC p (Δ>baseline) |
|---|---|---|---|---|---|---|---|---|---|---|
| gross | 36 | 8 | 13 | 0 | 6 | 0 | 0 | 0 | 0.09 | 0.34 |
| 0.05%/side | 17 | 2 | 2 | 0 | 4 | 0 | 0 | 0 | 0.41 | 0.53 |
| 0.15%/side | 5 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0.88 | 0.25 |

### Average net R by setup × timeframe (mean over the 4 configs, 0.05%/side; gross in brackets)
| setup | 15m | 1h | 4h |
|---|---|---|---|
| IFVG | -0.176 (-0.011) | -0.085 (-0.010) | +0.045 (+0.079) |
| BreakerFlow | -0.137 (+0.003) | -0.030 (+0.035) | +0.104 (+0.136) |
| CISD | -0.123 (+0.021) | -0.038 (+0.027) | +0.045 (+0.075) |
| SuspensionBlock | -0.146 (-0.011) | -0.224 (-0.166) | -0.146 (-0.114) |
| OrderBlock | -0.164 (-0.024) | -0.068 (-0.005) | -0.145 (-0.116) |
| MSS_FVG | -0.179 (-0.018) | -0.091 (-0.016) | +0.038 (+0.071) |

## 5) Per setup × pair × timeframe (headline config fixed a priori: zone stop, 2R target, 0.05%/side)
Cell = `n / win% / avg net R / PF`. All 4 configs × 2 cost levels (+gross) for every pair are in `outputs/research/ict/results_per_pair.csv`.

**IFVG**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 3082 / 32 / -0.359 / 0.60 | 649 / 35 / -0.115 / 0.84 | 164 / 30 / -0.154 / 0.79 |
| ETH | 3085 / 32 / -0.276 / 0.67 | 668 / 35 / -0.051 / 0.93 | 181 / 40 / +0.160 / 1.26 |
| SOL | 2984 / 34 / -0.125 / 0.83 | 693 / 33 / -0.078 / 0.89 | 181 / 34 / -0.008 / 0.99 |
| BNB | 3383 / 33 / -0.279 / 0.67 | 772 / 32 / -0.154 / 0.80 | 189 / 38 / +0.078 / 1.12 |
| XRP | 3029 / 34 / -0.186 / 0.76 | 634 / 34 / -0.075 / 0.90 | 158 / 47 / +0.360 / 1.66 |
| DOGE | 2827 / 32 / -0.224 / 0.72 | 618 / 31 / -0.171 / 0.77 | 144 / 37 / +0.039 / 1.06 |
| ADA | 3115 / 33 / -0.173 / 0.78 | 721 / 32 / -0.111 / 0.85 | 175 / 37 / +0.021 / 1.03 |
| AVAX | 3075 / 35 / -0.094 / 0.87 | 688 / 36 / +0.012 / 1.02 | 153 / 32 / -0.083 / 0.88 |
| LINK | 3344 / 33 / -0.168 / 0.78 | 770 / 34 / -0.048 / 0.93 | 192 / 37 / +0.059 / 1.09 |
| NEAR | 2936 / 33 / -0.141 / 0.81 | 665 / 36 / +0.014 / 1.02 | 155 / 37 / +0.065 / 1.10 |
| LTC | 3121 / 32 / -0.229 / 0.71 | 689 / 30 / -0.206 / 0.73 | 176 / 40 / +0.148 / 1.24 |
| DOT | 2970 / 32 / -0.210 / 0.73 | 670 / 30 / -0.169 / 0.77 | 190 / 35 / +0.008 / 1.01 |
| pairs with net R>0 | 0/12 | 2/12 | 9/12 |

**BreakerFlow**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 408 / 35 / -0.204 / 0.74 | 102 / 33 / -0.106 / 0.86 | 29 / 41 / +0.190 / 1.31 |
| ETH | 410 / 32 / -0.211 / 0.73 | 103 / 34 / -0.053 / 0.93 | 33 / 39 / +0.145 / 1.23 |
| SOL | 329 / 32 / -0.168 / 0.78 | 81 / 33 / -0.052 / 0.93 | 26 / 42 / +0.240 / 1.41 |
| BNB | 351 / 37 / -0.119 / 0.84 | 86 / 35 / -0.068 / 0.90 | 40 / 50 / +0.438 / 1.86 |
| XRP | 330 / 35 / -0.112 / 0.85 | 101 / 31 / -0.155 / 0.79 | 21 / 52 / +0.539 / 2.10 |
| DOGE | 331 / 34 / -0.123 / 0.83 | 93 / 34 / -0.062 / 0.91 | 21 / 29 / -0.172 / 0.77 |
| ADA | 322 / 37 / -0.027 / 0.96 | 91 / 41 / +0.170 / 1.27 | 24 / 33 / -0.030 / 0.96 |
| AVAX | 297 / 33 / -0.127 / 0.83 | 89 / 31 / -0.113 / 0.84 | 19 / 32 / -0.083 / 0.88 |
| LINK | 330 / 33 / -0.144 / 0.81 | 96 / 39 / +0.060 / 1.09 | 18 / 56 / +0.638 / 2.40 |
| NEAR | 258 / 35 / -0.057 / 0.92 | 65 / 40 / +0.135 / 1.22 | 23 / 39 / +0.153 / 1.25 |
| LTC | 371 / 31 / -0.221 / 0.72 | 81 / 35 / -0.056 / 0.92 | 27 / 48 / +0.408 / 1.76 |
| DOT | 290 / 33 / -0.145 / 0.80 | 78 / 37 / +0.024 / 1.04 | 28 / 32 / -0.029 / 0.96 |
| pairs with net R>0 | 0/12 | 4/12 | 8/12 |

**CISD**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 2018 / 36 / -0.184 / 0.77 | 446 / 36 / -0.016 / 0.98 | 113 / 37 / +0.072 / 1.11 |
| ETH | 1988 / 35 / -0.141 / 0.81 | 476 / 37 / +0.010 / 1.01 | 131 / 41 / +0.179 / 1.29 |
| SOL | 1855 / 38 / +0.024 / 1.03 | 445 / 40 / +0.137 / 1.22 | 120 / 37 / +0.062 / 1.10 |
| BNB | 2160 / 35 / -0.148 / 0.81 | 467 / 35 / -0.040 / 0.94 | 127 / 37 / +0.063 / 1.10 |
| XRP | 1836 / 33 / -0.165 / 0.78 | 452 / 36 / +0.011 / 1.02 | 110 / 35 / +0.044 / 1.07 |
| DOGE | 1793 / 36 / -0.072 / 0.90 | 395 / 35 / -0.042 / 0.94 | 92 / 42 / +0.227 / 1.38 |
| ADA | 1918 / 33 / -0.140 / 0.81 | 481 / 36 / -0.005 / 0.99 | 108 / 33 / -0.042 / 0.94 |
| AVAX | 1827 / 34 / -0.082 / 0.89 | 474 / 34 / -0.061 / 0.91 | 108 / 42 / +0.235 / 1.40 |
| LINK | 2075 / 34 / -0.087 / 0.88 | 494 / 32 / -0.115 / 0.84 | 145 / 32 / -0.057 / 0.92 |
| NEAR | 1699 / 34 / -0.065 / 0.91 | 481 / 34 / -0.046 / 0.93 | 114 / 38 / +0.114 / 1.18 |
| LTC | 2012 / 34 / -0.145 / 0.81 | 517 / 31 / -0.147 / 0.80 | 121 / 37 / +0.065 / 1.10 |
| DOT | 1827 / 34 / -0.111 / 0.85 | 448 / 34 / -0.041 / 0.94 | 120 / 38 / +0.094 / 1.15 |
| pairs with net R>0 | 1/12 | 3/12 | 10/12 |

**SuspensionBlock**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 66 / 23 / -0.676 / 0.34 | 21 / 33 / -0.088 / 0.88 | 11 / 55 / +0.490 / 2.03 |
| ETH | 91 / 37 / -0.073 / 0.90 | 17 / 6 / -0.910 / 0.11 | 7 / 14 / -0.678 / 0.10 |
| SOL | 102 / 37 / +0.005 / 1.01 | 14 / 14 / -0.618 / 0.31 | 3 / 33 / -0.027 / 0.96 |
| BNB | 122 / 35 / -0.156 / 0.80 | 30 / 33 / -0.072 / 0.90 | 6 / 67 / +0.816 / 3.42 |
| XRP | 79 / 29 / -0.256 / 0.68 | 19 / 16 / -0.571 / 0.35 | 0 / – / – / – |
| DOGE | 71 / 31 / -0.179 / 0.76 | 18 / 17 / -0.664 / 0.25 | 2 / 0 / -1.021 / 0.00 |
| ADA | 89 / 30 / -0.219 / 0.71 | 26 / 15 / -0.592 / 0.34 | 1 / 0 / -1.026 / 0.00 |
| AVAX | 90 / 39 / +0.048 / 1.07 | 25 / 36 / +0.029 / 1.04 | 4 / 25 / -0.469 / 0.39 |
| LINK | 95 / 32 / -0.163 / 0.78 | 21 / 43 / +0.243 / 1.41 | 5 / 20 / -0.422 / 0.48 |
| NEAR | 104 / 32 / -0.115 / 0.84 | 28 / 32 / -0.068 / 0.90 | 4 / 25 / -0.272 / 0.64 |
| LTC | 89 / 33 / -0.166 / 0.77 | 13 / 15 / -0.408 / 0.42 | 2 / 0 / -1.034 / 0.00 |
| DOT | 84 / 35 / -0.084 / 0.89 | 18 / 28 / -0.244 / 0.68 | 3 / 0 / -1.036 / 0.00 |
| pairs with net R>0 | 2/12 | 2/12 | 2/12 |

**OrderBlock**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 328 / 31 / -0.306 / 0.64 | 77 / 35 / -0.049 / 0.93 | 28 / 29 / -0.185 / 0.75 |
| ETH | 314 / 30 / -0.281 / 0.65 | 83 / 41 / +0.148 / 1.24 | 21 / 24 / -0.319 / 0.59 |
| SOL | 229 / 30 / -0.209 / 0.73 | 65 / 42 / +0.220 / 1.37 | 19 / 37 / +0.124 / 1.21 |
| BNB | 266 / 33 / -0.202 / 0.75 | 71 / 32 / -0.096 / 0.87 | 15 / 27 / -0.205 / 0.72 |
| XRP | 237 / 28 / -0.288 / 0.64 | 77 / 34 / -0.057 / 0.92 | 13 / 15 / -0.569 / 0.35 |
| DOGE | 264 / 33 / -0.164 / 0.78 | 67 / 28 / -0.216 / 0.71 | 13 / 8 / -0.764 / 0.17 |
| ADA | 221 / 33 / -0.132 / 0.82 | 66 / 32 / -0.126 / 0.82 | 19 / 37 / +0.079 / 1.12 |
| AVAX | 246 / 37 / +0.014 / 1.02 | 60 / 28 / -0.181 / 0.75 | 16 / 38 / +0.064 / 1.10 |
| LINK | 241 / 37 / -0.029 / 0.96 | 61 / 26 / -0.344 / 0.55 | 13 / 15 / -0.562 / 0.35 |
| NEAR | 193 / 30 / -0.205 / 0.73 | 51 / 41 / +0.138 / 1.23 | 14 / 43 / +0.266 / 1.46 |
| LTC | 270 / 34 / -0.121 / 0.83 | 75 / 33 / -0.073 / 0.90 | 12 / 17 / -0.661 / 0.21 |
| DOT | 217 / 34 / -0.107 / 0.85 | 55 / 25 / -0.319 / 0.59 | 18 / 22 / -0.357 / 0.55 |
| pairs with net R>0 | 1/12 | 3/12 | 4/12 |

**MSS_FVG**

| pair | 15m | 1h | 4h |
|---|---|---|---|
| BTC | 674 / 34 / -0.278 / 0.67 | 152 / 37 / -0.034 / 0.95 | 58 / 29 / -0.195 / 0.74 |
| ETH | 643 / 33 / -0.223 / 0.72 | 153 / 35 / -0.055 / 0.92 | 48 / 29 / -0.173 / 0.76 |
| SOL | 532 / 34 / -0.139 / 0.82 | 132 / 30 / -0.170 / 0.77 | 39 / 41 / +0.167 / 1.27 |
| BNB | 569 / 34 / -0.221 / 0.73 | 134 / 26 / -0.339 / 0.59 | 39 / 44 / +0.244 / 1.42 |
| XRP | 574 / 32 / -0.243 / 0.70 | 125 / 39 / +0.074 / 1.11 | 39 / 41 / +0.144 / 1.24 |
| DOGE | 517 / 34 / -0.151 / 0.80 | 129 / 31 / -0.164 / 0.78 | 37 / 27 / -0.221 / 0.71 |
| ADA | 538 / 33 / -0.152 / 0.80 | 123 / 28 / -0.214 / 0.72 | 44 / 48 / +0.372 / 1.69 |
| AVAX | 526 / 32 / -0.192 / 0.75 | 140 / 31 / -0.137 / 0.81 | 32 / 25 / -0.279 / 0.64 |
| LINK | 566 / 35 / -0.086 / 0.88 | 155 / 35 / -0.039 / 0.94 | 47 / 28 / -0.198 / 0.73 |
| NEAR | 469 / 36 / -0.054 / 0.92 | 140 / 24 / -0.348 / 0.57 | 39 / 33 / -0.022 / 0.97 |
| LTC | 568 / 32 / -0.197 / 0.75 | 132 / 33 / -0.136 / 0.81 | 46 / 43 / +0.174 / 1.30 |
| DOT | 458 / 29 / -0.269 / 0.67 | 123 / 34 / -0.071 / 0.90 | 44 / 39 / +0.102 / 1.16 |
| pairs with net R>0 | 0/12 | 1/12 | 6/12 |

## 6) Stability: best configs by sub-period (0.05%/side net R; split at 2023-09-01, and by calendar year)
| config | n | first half (≤2023-08) | second half | years (n: avg R) |
|---|---|---|---|---|
| BreakerFlow 4h zone 2R | 309 | +0.248 (n=153) | +0.172 (n=156) | 2020: 33: +0.21; 2021: 46: +0.43; 2022: 44: +0.35; 2023: 39: -0.05; 2024: 46: +0.53; 2025: 52: -0.06; 2026: 49: +0.06 |
| BreakerFlow 4h atr1.5 2R | 315 | +0.086 (n=157) | +0.161 (n=158) | 2020: 33: +0.18; 2021: 49: +0.33; 2022: 45: +0.01; 2023: 40: -0.34; 2024: 46: +0.47; 2025: 52: +0.01; 2026: 50: +0.16 |
| IFVG 4h atr1.5 2R | 2048 | +0.073 (n=980) | +0.112 (n=1068) | 2020: 199: +0.15; 2021: 310: -0.04; 2022: 289: +0.13; 2023: 257: +0.06; 2024: 332: +0.22; 2025: 390: +0.15; 2026: 271: -0.04 |
| CISD 4h zone 2R | 1409 | +0.143 (n=756) | +0.014 (n=653) | 2020: 142: +0.05; 2021: 230: +0.22; 2022: 253: +0.17; 2023: 206: +0.08; 2024: 200: -0.04; 2025: 205: +0.12; 2026: 173: -0.08 |
| MSS_FVG 4h atr1.5 1R | 552 | +0.086 (n=308) | +0.038 (n=244) | 2020: 57: +0.23; 2021: 115: +0.08; 2022: 74: +0.08; 2023: 72: -0.01; 2024: 84: +0.16; 2025: 89: +0.03; 2026: 61: -0.13 |
| MSS_FVG 4h zone 1R | 524 | +0.062 (n=292) | +0.064 (n=232) | 2020: 52: +0.11; 2021: 113: +0.00; 2022: 68: +0.18; 2023: 69: -0.01; 2024: 79: +0.23; 2025: 83: +0.03; 2026: 60: -0.09 |
| CISD 4h atr1.5 2R | 1598 | +0.130 (n=846) | -0.013 (n=752) | 2020: 158: +0.04; 2021: 255: +0.24; 2022: 270: +0.20; 2023: 243: -0.03; 2024: 232: -0.01; 2025: 245: +0.13; 2026: 195: -0.22 |
| BreakerFlow 4h zone 1R | 311 | +0.131 (n=155) | -0.014 (n=156) | 2020: 34: +0.44; 2021: 48: +0.23; 2022: 43: -0.01; 2023: 39: -0.12; 2024: 46: +0.09; 2025: 52: -0.04; 2026: 49: -0.10 |
| IFVG 4h zone 2R | 2058 | +0.038 (n=995) | +0.077 (n=1063) | 2020: 192: +0.17; 2021: 327: -0.08; 2022: 293: +0.09; 2023: 259: -0.01; 2024: 327: +0.19; 2025: 382: +0.13; 2026: 278: -0.08 |
| IFVG 4h atr1.5 1R | 2259 | +0.018 (n=1079) | +0.034 (n=1180) | 2020: 210: +0.05; 2021: 347: -0.04; 2022: 325: +0.09; 2023: 278: -0.02; 2024: 366: +0.13; 2025: 436: +0.03; 2026: 297: -0.07 |

### 6b) 4h direction split (net R at 0.05%/side; descriptive, not a new test)
| setup | stop/tgt | long n / avg net R | short n / avg net R |
|---|---|---|---|
| IFVG 4h | zone 2R | 1007 / +0.104 | 1051 / +0.014 |
| IFVG 4h | atr1.5 2R | 1009 / +0.104 | 1039 / +0.082 |
| IFVG 4h | zone 1R | 1085 / +0.007 | 1149 / +0.001 |
| BreakerFlow 4h | zone 2R | 156 / +0.227 | 153 / +0.191 |
| BreakerFlow 4h | atr1.5 2R | 162 / +0.059 | 153 / +0.192 |
| BreakerFlow 4h | zone 1R | 158 / +0.003 | 153 / +0.115 |
| CISD 4h | zone 2R | 696 / +0.072 | 713 / +0.094 |
| CISD 4h | atr1.5 2R | 783 / +0.058 | 815 / +0.067 |
| CISD 4h | zone 1R | 743 / +0.016 | 764 / +0.015 |
| MSS_FVG 4h | zone 2R | 261 / +0.062 | 251 / -0.050 |
| MSS_FVG 4h | atr1.5 2R | 280 / +0.103 | 261 / -0.072 |
| MSS_FVG 4h | zone 1R | 268 / +0.067 | 256 / +0.059 |

## 7) Interpretation and caveats
- **Win rate ≈ 1/(1+R) on 15m/1h** (≈50% at 1R, ≈33% at 2R; 4h reaches 37–41% at 2R for IFVG/Breaker/CISD): the entry rule adds little or no directional information over a random entry on the lower timeframes; the video's 'ideal chart' examples are a selection effect.
- Costs matter more than the setups: median zone-stop risk is a fraction of a percent on 15m/1h, so a 0.1% round trip costs ≈0.14–0.19R per trade (0.4–0.6R at 0.15%/side). This alone makes every 15m configuration clearly negative (and every 15m gross edge ≈ 0).
- The 4h tilt (gross R +0.05…+0.25 for IFVG / Breaker / CISD / MSS+FVG) is not just long-side bull drift: CISD and Breaker are positive on both long and short trades (§6b); only MSS+FVG is long-only positive. But the baseline matches direction mix, not regime timing, and 2026 YTD is negative for IFVG/CISD/MSS+FVG. Treat it as a hypothesis, not a result: n is only 300–2000 trades per config, trades from 12 correlated pairs overlap in time (hence 7-day all-pair blocks), and 72 configs were examined.
- Not an out-of-sample test: definitions were fixed before looking, but the whole 2020–2026 history was used once; no parameter was tuned (a parameter sweep would add trials and make DSR worse). 
- Interpretive choices are mine (the video gives no formal rules): e.g. FVG min size 0.25 ATR, 50-bar expiry, first-touch-only, rejection-candle confirmation, 1.5 ATR displacement. Other readings of 'ICT' (premium/discount filters, killzones, higher-timeframe bias, partial TP, trailing) were **not** tested and are discretionary by nature; if they had an edge it would have to come from a discretionary overlay that cannot be backtested here.
- Funding not included (small drag/benefit for multi-bar holds), no liquidity limits, intrabar stop-vs-target ordering resolved pessimistically (stop first).
- Suspension Block has very few trades (esp. 4h: ~50) → CIs are wide; no conclusion possible except 'no evidence'.
