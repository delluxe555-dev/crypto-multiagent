#!/usr/bin/env python3
"""Backtest of liqmap_proto's estimated-cluster model (causal replay on cached Gate 15m data). Writes only liqbt_out.npz / prints report."""
import json, glob, os, math, sys, numpy as np
D = "liqbt_cache"; LEV = {5: .15, 10: .30, 25: .25, 50: .18, 100: .12}
WARM = 384; STEP = 4; H = {"4h": 16, "12h": 48, "24h": 96}; KS = [2, 3, 4, 5, 6]; BW = 0.0025   # bin width 0.25%
REACT_BARS = 8; REACT_K = 4

def load(c):
    d = json.load(open(f"{D}/{c}.json")); k = {int(x["t"]): x for x in d["cd"]}; rows = []
    for s in sorted(d["st"], key=lambda s: s["time"]):
        x = k.get(s["time"])
        if x and s.get("open_interest_usd"):
            rows.append((s["time"], float(x["h"]), float(x["l"]), float(x["c"]), float(s["open_interest_usd"]), float(s.get("lsr_taker") or 1),
                         float(s.get("long_liq_usd") or 0), float(s.get("short_liq_usd") or 0)))
    return d["ct"], np.array(rows)

def run(c):
    ct, R = load(c); n = len(R); t, h, l, cl, oi, lsr, lliq, sliq = R.T
    mmr = float(ct.get("maintenance_rate") or .005); lmax = float(ct.get("leverage_max") or 100)
    levs = {a: w for a, w in LEV.items() if a <= lmax and 1 / a > 2 * mmr}; tw = sum(levs.values()); levs = {a: w / tw for a, w in levs.items()}
    cap = n * 2 * len(levs) + 50; px = np.zeros(cap); us = np.zeros(cap); sd = np.zeros(cap, int); m = 0
    def add(p, u, s):
        nonlocal m; px[m] = p; us[m] = u; sd[m] = s; m += 1
    ep = (h[0] + l[0] + cl[0]) / 3
    for a, w in levs.items(): add(ep * (1 - 1 / a + mmr), oi[0] * w, 1); add(ep * (1 + 1 / a - mmr), oi[0] * w, -1)
    r4 = np.array([h[max(0, i - 3):i + 1].max() - l[max(0, i - 3):i + 1].min() for i in range(n)])
    atr = np.array([r4[max(0, i - 55):i + 1].mean() for i in range(n)])
    swl = np.zeros(n); sws = np.zeros(n); S = []
    for i in range(1, n):
        mk = ((sd[:m] == 1) & (l[i] <= px[:m])) | ((sd[:m] == -1) & (h[i] >= px[:m]))
        swl[i] = us[:m][mk & (sd[:m] == 1)].sum(); sws[i] = us[:m][mk & (sd[:m] == -1)].sum()
        keep = ~mk; k = keep.sum(); px[:k] = px[:m][keep]; us[:k] = us[:m][keep]; sd[:k] = sd[:m][keep]; m = k
        d = oi[i] - oi[i - 1]
        if d < 0: us[:m] *= oi[i] / oi[i - 1]
        elif d > 0:
            e = (h[i] + l[i] + cl[i]) / 3; sh = lsr[i] / (1 + lsr[i]); lf = .5 + (sh - .5) * .5
            for a, w in levs.items(): add(e * (1 - 1 / a + mmr), d * w * 2 * lf, 1); add(e * (1 + 1 / a - mmr), d * w * 2 * (1 - lf), -1)
        if i < WARM or i % STEP or i + H["4h"] >= n or i < 60: continue
        P = cl[i]; pp = px[:m]; uu = us[:m]; ss = sd[:m]
        dist = (pp / P - 1) / BW   # in bin-width units (signed)
        for side in (1, -1):
            sel = ss == side; dd = (-dist[sel]) if side == 1 else dist[sel]; u_ = uu[sel]
            ok = (dd > 0) & (dd <= 20); bins = np.minimum(np.ceil(dd[ok]).astype(int), 20); tot = np.bincount(bins, weights=u_[ok], minlength=21)[1:]
            order = np.argsort(-tot); rank = np.empty(20, int); rank[order] = np.arange(20)
            for kk in KS:
                dc = (kk - .5) * BW; L = P * (1 - dc) if side == 1 else P * (1 + dc)
                sz = tot[kk - 1] / oi[i] * 1e4   # bps of OI in that 0.25% bin
                fut = slice(i + 1, i + 1 + H["24h"])
                hit = (l[fut] <= L) if side == 1 else (h[fut] >= L); first = int(np.argmax(hit)) if hit.any() else -1
                tt = {kx: (first >= 0 and first < v) if i + v < n else np.nan for kx, v in H.items()}
                rev = np.nan
                if first >= 0 and first < H["12h"] and i + 1 + first + REACT_BARS < n:
                    j = i + 1 + first; A = atr[i]; res = 0
                    for q in range(j + 1, j + 1 + REACT_BARS):
                        ex = (L - l[q]) if side == 1 else (h[q] - L); rv = (h[q] - L) if side == 1 else (L - l[q])  # ext beyond level / retrace back
                        ex, rv = (L - l[q], h[q] - L) if side == 1 else (h[q] - L, L - l[q])
                        # side==1 long-liq level hit going DOWN: continuation = further down (L-l), reversal = bounce up (h-L)
                        if ex >= A and rv >= A: res = 3; break
                        if ex >= A: res = 2; break
                        if rv >= A: res = 1; break
                    rev = res
                    # realized same-side liq in touch bar j and j+1 (per OI)
                    rl = ((lliq if side == 1 else sliq)[j:j + 2].sum()) / oi[i] * 1e4
                else: rl = np.nan
                hz_ = (l[i - 383:i + 1] <= L) if side == 1 else (h[i - 383:i + 1] >= L); ix_ = np.where(hz_)[0]; vis = float(383 - ix_[-1]) if len(ix_) else 384.0  # bars since price last traded at/through the level (cap 384)
                S.append((i, side, kk, dc * 100, dc * P / atr[i], sz, int(rank[kk - 1]), tt["4h"], tt["12h"], tt["24h"], rev, rl, vis))
    return dict(coin=c, n=n, oi=oi, h=h, l=l, cl=cl, lliq=lliq, sliq=sliq, swl=swl, sws=sws, atr=atr, S=np.array(S, float))

if __name__ == "__main__":
    out = {}
    for f in sorted(glob.glob(f"{D}/*.json")):
        c = os.path.basename(f)[:-5]; r = run(c); out[c] = r; print(c, r["n"], len(r["S"]), flush=True)
    import pickle; pickle.dump(out, open("liqbt_out.pkl", "wb"))
