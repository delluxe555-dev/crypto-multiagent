#!/usr/bin/env python3
"""Bot-stili sinyallerin geriye donuk testi (Gate 15m, ~21 gun, liqbt_cache). Yalniz yeni dosya; paper trader'a dokunmaz."""
import json, glob, os, numpy as np
D = "liqbt_cache"; HZ = {"1h": 4, "4h": 16, "12h": 48}; COST_BP = 10.0; rng = np.random.default_rng(1)
coins = sorted(os.path.basename(f)[:-5] for f in glob.glob(f"{D}/*.json")); data = {}
for c in coins:
    d = json.load(open(f"{D}/{c}.json")); k = {int(x["t"]): x for x in d["cd"]}; iv = (d["ct"].get("funding_interval") or 28800) / 3600; rows = []
    for s in sorted(d["st"], key=lambda s: s["time"]):
        x = k.get(s["time"])
        if x and s.get("open_interest_usd"): rows.append((s["time"], float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(s["open_interest_usd"]), float(s.get("last_funding_rate") or 0) * 8 / iv * 100))
    data[c] = np.array(rows)
T = np.array(sorted(set(int(t) for c in coins for t in data[c][:, 0]))); ti = {int(t): i for i, t in enumerate(T)}; nT = len(T); nC = len(coins)
M = {k: np.full((nC, nT), np.nan) for k in "ohlc"}; OI = np.full((nC, nT), np.nan); FU = np.full((nC, nT), np.nan)
for ci, c in enumerate(coins):
    for r in data[c]:
        j = ti[int(r[0])]; M["o"][ci, j], M["h"][ci, j], M["l"][ci, j], M["c"][ci, j], OI[ci, j], FU[ci, j] = r[1:]
RET = {}
for hn, H in HZ.items():
    R = np.full((nC, nT), np.nan); R[:, :nT - H] = M["c"][:, H:] / M["o"][:, 1:nT - H + 1] - 1; RET[hn] = R * 1e4   # bp, giris=sonraki mum acilisi, cikis=t+H kapanisi
MK = {}
for hn in HZ:
    R = RET[hn]; s = np.nansum(R, 0); n = (~np.isnan(R)).sum(0); MK[hn] = (s[None, :] - np.nan_to_num(R)) / np.maximum(n[None, :] - (~np.isnan(R)), 1)
UN = {hn: np.nanmean(RET[hn], 1) for hn in HZ}
print(f"coins={nC} bars/coin~{nT} span={nT/96:.1f}d | forward return: entry next-bar open, exit close of t+H; cost {COST_BP:.0f}bp round trip (0.05%/side)")

def signals(w):
    ev = []   # (type, dir, ci, j)
    for ci in range(nC):
        c = M["c"][ci]; oi = OI[ci]; last = {}
        for j in range(w, nT - 1):
            if np.isnan(c[j]) or np.isnan(c[j - w]) or np.isnan(oi[j]) or np.isnan(oi[j - w]): continue
            p = (c[j] / c[j - w] - 1) * 100; o = (oi[j] / oi[j - w] - 1) * 100; hits = []
            if abs(p) >= .5 and abs(o) >= 1:
                hits.append(("NEWLONG", 1) if p > 0 and o > 0 else ("NEWSHORT", -1) if p < 0 and o > 0 else ("LONGLIQ", -1) if p < 0 else ("SQUEEZE", 1))
            if abs(o) >= 3 and p != 0: hits.append(("OFOI_UP" if o > 0 else "OFOI_DN", 1 if p > 0 else -1))
            for t_, d_ in hits:
                if j - last.get(t_, -999) >= w: ev.append((t_, d_, ci, j)); last[t_] = j
    return ev
def fsignals(th, refr=32):
    ev = []
    for ci in range(nC):
        f = FU[ci]; last = {}
        for j in range(nT - 1):
            if np.isnan(f[j]): continue
            t_ = "FUND_POS" if f[j] >= th else "FUND_NEG" if f[j] <= -th else None
            if t_ and j - last.get(t_, -999) >= refr * 3: ev.append((t_, -1 if t_ == "FUND_POS" else 1, ci, j)); last[t_] = j
    return ev
mid = nT // 2
def boot(vals, blocks, nb=400):
    u, inv = np.unique(blocks, return_inverse=True); idx = [np.where(inv == k)[0] for k in range(len(u))]; out = []
    for _ in range(nb):
        pick = rng.integers(0, len(u), len(u)); out.append(vals[np.concatenate([idx[k] for k in pick])].mean())
    return np.percentile(out, [2.5, 97.5])
def report(ev, label):
    types = sorted(set(e[0] for e in ev)); 
    for t_ in types:
        E = [e for e in ev if e[0] == t_]
        for hn in HZ:
            d = np.array([e[1] for e in E]); ci = np.array([e[2] for e in E]); j = np.array([e[3] for e in E]); r = RET[hn][ci, j]; ok = ~np.isnan(r)
            d, ci, j, r = d[ok], ci[ok], j[ok], r[ok]
            if len(r) < 5: print(f"{label:6s}{t_:9s}{hn:4s} n={len(r)} (az)"); continue
            g = d * r; net = g - COST_BP; un = d * UN[hn][ci]; mk = d * MK[hn][ci, j]; ex = g - mk
            blocks = ci * 1000 + (T[j] - T[0]) // (3 * 86400); 
            c1 = boot(net, blocks); c2 = boot(ex, blocks)
            h1 = j < mid; pc = [net[ci == k].mean() for k in range(nC) if (ci == k).sum() >= 5]; pce = [ex[ci == k].mean() for k in range(nC) if (ci == k).sum() >= 5]
            print(f"{label:6s}{t_:9s}{hn:4s} n={len(g):5d} hit={100*(g>0).mean():4.1f}% gross={g.mean():+7.1f}bp net={net.mean():+7.1f}bp [{c1[0]:+.0f},{c1[1]:+.0f}] | base(coin uncond)={un.mean():+6.1f} same-time mkt={mk.mean():+6.1f} excess={ex.mean():+6.1f}bp [{c2[0]:+.0f},{c2[1]:+.0f}] | half1 n={h1.sum()} gross={g[h1].mean() if h1.any() else float('nan'):+6.1f} ex={ex[h1].mean() if h1.any() else float('nan'):+6.1f} | half2 n={(~h1).sum()} gross={g[~h1].mean() if (~h1).any() else float('nan'):+6.1f} ex={ex[~h1].mean() if (~h1).any() else float('nan'):+6.1f} | coins net>0 {sum(x>0 for x in pc)}/{len(pc)} excess>0 {sum(x>0 for x in pce)}/{len(pce)}")
        print()
if __name__ == "__main__":
    for w, nm in ((4, "w=1h(4x15m)"), (16, "w=4h(16x15m)")):
        print("=" * 30, nm); report(signals(w), "")
    print("=" * 30, "funding extreme (fade crowd) >= |0.05|%/8h"); report(fsignals(0.05), "")
    print("=" * 30, "funding (sensitivity) >= |0.03|%/8h"); report(fsignals(0.03), "")
    # vol test for OF-OI
    for w in (4, 16):
        ev = [e for e in signals(w) if e[0].startswith("OFOI")]; 
        for hn, H in HZ.items():
            a = np.array([abs(RET[hn][e[2], e[3]]) for e in ev if not np.isnan(RET[hn][e[2], e[3]])]); b = np.nanmean(np.abs(RET[hn]))
            print(f"OF-OI w={w}: mean |fwd ret| {hn} after signal {a.mean():.1f}bp (n={len(a)}) vs all bars {b:.1f}bp")
