#!/usr/bin/env python3
"""stats_ict.py - aggregate ICT-setup trades: win rate, avg net R, PF, 7-day-block bootstrap CI (all pairs together), random-entry baseline comparison,
Deflated Sharpe (re-uses ../../overfit_stats.py), Holm + White-style max-t across the 72 configs, sub-period stability. Writes results_ict.json, results_per_pair.csv.
Run: python stats_ict.py"""
import os, sys, json, math, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
sys.path.insert(0, os.path.abspath("../../.."))
import overfit_stats as O   # sr_stats, dsr, exp_max_sr (Bailey & Lopez de Prado)
SETUPS = {1: "IFVG", 2: "BreakerFlow", 3: "CISD", 4: "SuspensionBlock", 5: "OrderBlock", 6: "MSS_FVG"}; TFS = ["15m", "1h", "4h"]; STOPS = ["zone", "atr"]; TGTS = [1.0, 2.0]
PAIRS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","NEAR","LTC","DOT"]
COSTS = [0.0, 0.0005, 0.0015]; CN = ["gross", "0.05%/side", "0.15%/side"]; R_BOOT = 5000; HEAD_COST = 1; N_REG_PRIOR = 1069
z = np.load("trades_ict.npz"); T = {k: z[k] for k in z.files}; B = np.load("baseline_ict.npz")
t0 = int(T["t_out"].min()) // 86400 * 86400; day = ((T["t_out"] - t0) // 86400).astype(np.int64); nd = int(day.max()) + 1
blk = day // 7; nb = int(blk.max()) + 1; rng = np.random.default_rng(7)
W = rng.multinomial(nb, np.full(nb, 1 / nb), size=R_BOOT).astype(np.float64)   # shared resamples -> joint max-t possible
cells = [(s, tf, sm, R) for s in SETUPS for tf in range(3) for sm in range(2) for R in TGTS]
bkeys = {tuple(k): i for i, k in enumerate(B["keys"].tolist())}
def netr(m, cs): return T["g"][m] - 2 * cs * T["k"][m]
def pf(x):
    p = x[x > 0].sum(); q = -x[x < 0].sum(); return float(p / q) if q > 0 else float("inf")
res = {}; boots = {}
for ci, cs in enumerate(COSTS):
    for cell in cells:
        s, tf, sm, R = cell; m = (T["setup"] == s) & (T["tf"] == tf) & (T["stop"] == sm) & (T["tgt"] == R); x = netr(m, cs); n = len(x)
        S = np.bincount(blk[m], weights=x, minlength=nb); N = np.bincount(blk[m], minlength=nb).astype(float)
        bm = (W @ S) / np.maximum(W @ N, 1); obs = S.sum() / max(N.sum(), 1)
        row = dict(n=n, win=float((x > 0).mean()), mean=float(obs), pf=pf(x), ci=[float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))], p=float(((bm <= 0).sum() + 1) / (R_BOOT + 1)), se=float(bm.std()))
        # baseline (random entry, same stops/targets): pooled mean per replicate
        bk = bkeys.get((float(s), float(tf), float(sm), float(R)))
        if bk is not None:
            v = B["vals"][bk]; bmean = v[:, 1 + ci] / np.maximum(v[:, 0], 1); row["base_mean"] = float(bmean.mean()); row["base_sd"] = float(bmean.std()); row["base_n"] = float(v[:, 0].mean())
            d = bm - bmean[rng.integers(0, len(bmean), R_BOOT)]; row["diff"] = float(obs - bmean.mean()); row["diff_ci"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]; row["p_diff"] = float(((d <= 0).sum() + 1) / (R_BOOT + 1)); boots[(ci, cell, "d")] = d
        boots[(ci, cell)] = bm; res[(ci, cell)] = row
# Holm across 72 configs for each cost level and each test (mean>0 ; mean>baseline)
def holm(ps):
    o = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0.0
    for r, i in enumerate(o): run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj
for ci in range(3):
    for key, tag in (("p", "p_holm"), ("p_diff", "p_diff_holm")):
        ks = [c for c in cells if key in res[(ci, c)]]; adj = holm(np.array([res[(ci, c)][key] for c in ks]))
        for c, a in zip(ks, adj): res[(ci, c)][tag] = float(a)
    # White-style studentised max-t (joint, shared resamples) for H0: no config has mean>0 / > baseline
    for tag, getb in (("rc_p", lambda c: boots[(ci, c)]), ("rc_p_diff", lambda c: boots[(ci, c, "d")])):
        ks = [c for c in cells if (ci, c, "d") in boots]; M = np.array([getb(c) for c in ks]).T   # R x K
        base = np.array([res[(ci, c)]["mean"] if tag == "rc_p" else res[(ci, c)]["diff"] for c in ks]); sd = M.std(0); sd[sd == 0] = 1
        tobs = (base / sd).max(); tb = ((M - base) / sd).max(1); p = float(((tb >= tobs).sum() + 1) / (R_BOOT + 1))
        for c in ks: res[(ci, c)][tag] = p
# DSR on daily R series (all pairs summed by exit day, zero on idle days), N = 72 configs (this study) and N = 72 + 1069 (whole registry); also N=864 (config x pair)
D = {}
for ci, cs in enumerate(COSTS):
    X = np.zeros((len(cells), nd))
    for k, cell in enumerate(cells):
        s, tf, sm, R = cell; m = (T["setup"] == s) & (T["tf"] == tf) & (T["stop"] == sm) & (T["tgt"] == R); X[k] = np.bincount(day[m], weights=netr(m, cs), minlength=nd)
    mu, sd, sk, ku = O.sr_stats(X); sr = np.where(sd > 0, mu / np.where(sd > 0, sd, 1), 0.0); V = float(np.var(sr, ddof=1))
    for k, cell in enumerate(cells):
        r = res[(ci, cell)]; r["daily_sr"] = float(sr[k]); r["sr_ann"] = float(sr[k] * math.sqrt(365))
        r["psr"] = O.dsr(sr[k], nd, sk[k], ku[k], V, 1); r["dsr72"] = O.dsr(sr[k], nd, sk[k], ku[k], V, 72); r["dsr864"] = O.dsr(sr[k], nd, sk[k], ku[k], V, 864); r["dsr1141"] = O.dsr(sr[k], nd, sk[k], ku[k], V, 72 + N_REG_PRIOR)
    big = np.array([res[(ci, c)]["n"] >= 300 for c in cells]); V3 = float(np.var(sr[big], ddof=1))
    for k, cell in enumerate(cells):
        r = res[(ci, cell)]; r["dsr72_v300"] = O.dsr(sr[k], nd, sk[k], ku[k], V3, 72); r["dsr1141_v300"] = O.dsr(sr[k], nd, sk[k], ku[k], V3, 72 + N_REG_PRIOR)
    D[ci] = dict(V300=V3, sr0_72_v300=O.exp_max_sr(V3, 72), sr0_1141_v300=O.exp_max_sr(V3, 72 + N_REG_PRIOR), V=V, nd=nd, sr0_72=O.exp_max_sr(V, 72), sr0_1141=O.exp_max_sr(V, 72 + N_REG_PRIOR), best_sr=float(sr.max()))
# sub-periods: halves (split at 2023-09-01) and calendar years for headline cost
cut = 1693526400   # 2023-09-01 UTC
for cell in cells:
    s, tf, sm, R = cell; m = (T["setup"] == s) & (T["tf"] == tf) & (T["stop"] == sm) & (T["tgt"] == R); x = netr(m, COSTS[HEAD_COST]); to = T["t_out"][m]; yr = (to // 31556952 + 1970).astype(int)
    r = res[(HEAD_COST, cell)]; r["h1"] = float(x[to < cut].mean()) if (to < cut).any() else None; r["h2"] = float(x[to >= cut].mean()) if (to >= cut).any() else None
    r["h1n"] = int((to < cut).sum()); r["h2n"] = int((to >= cut).sum()); r["years"] = {int(y): [int((yr == y).sum()), float(x[yr == y].mean())] for y in np.unique(yr)}
# per pair rows
import csv
rows = []
for s in SETUPS:
    for tf in range(3):
        for p in range(len(PAIRS)):
            for sm in range(2):
                for R in TGTS:
                    m = (T["setup"] == s) & (T["tf"] == tf) & (T["pair"] == p) & (T["stop"] == sm) & (T["tgt"] == R); g = T["g"][m]
                    row = [SETUPS[s], TFS[tf], PAIRS[p], STOPS[sm], R, int(m.sum()), round(float((g > 0).mean()), 4) if m.sum() else "", round(float(g.mean()), 4) if m.sum() else ""]
                    for cs in COSTS[1:]:
                        x = netr(m, cs); row += [round(float((x > 0).mean()), 4) if m.sum() else "", round(float(x.mean()), 4) if m.sum() else "", round(pf(x), 3) if m.sum() else ""]
                    rows.append(row)
with open("results_per_pair.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["setup","tf","pair","stop","target_R","n","win_gross","avgR_gross","win_0.05","avgR_0.05","pf_0.05","win_0.15","avgR_0.15","pf_0.15"]); w.writerows(rows)
out = dict(cells=[list(c) for c in cells], res={f"{ci}|{'|'.join(map(str, c))}": v for (ci, c), v in res.items()}, D={str(k): v for k, v in D.items()}, nd=nd, nblocks=nb, t0=t0, n_trades=int(len(T["g"])))
json.dump(out, open("results_ict.json", "w"), indent=1)
print("done", len(rows), "per-pair rows", "days", nd, "blocks", nb)
# console digest
for ci in (1, 2):
    print("=== cost", CN[ci]); ks = sorted(cells, key=lambda c: -res[(ci, c)]["mean"])[:8]
    for c in ks:
        r = res[(ci, c)]; print(SETUPS[c[0]], TFS[c[1]], STOPS[c[2]], c[3], "n", r["n"], "mean %.3f" % r["mean"], "CI [%.3f,%.3f]" % tuple(r["ci"]), "base %.3f" % r.get("base_mean", np.nan), "diffCI [%.3f,%.3f]" % tuple(r["diff_ci"]), "p %.3f holm %.3f pdiff %.3f holm %.3f" % (r["p"], r["p_holm"], r["p_diff"], r["p_diff_holm"]), "dsr72 %.3f dsr1141 %.3f" % (r["dsr72"], r["dsr1141"]))
    print("RC p mean>0:", res[(ci, cells[0])]["rc_p"], " RC p diff>0:", res[(ci, cells[0])]["rc_p_diff"], D[ci])
