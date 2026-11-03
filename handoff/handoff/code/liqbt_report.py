import pickle, numpy as np
O = pickle.load(open("liqbt_out.pkl", "rb")); rng = np.random.default_rng(0)
A = []
for ci, (c, r) in enumerate(O.items()):
    S = r["S"]; A.append(np.column_stack([S, np.full(len(S), ci), (S[:, 0] // 96).astype(int)]))
A = np.vstack(A); ISZ, ISIDE, IK, IDP, IDA, SZ, IRK, T4, T12, T24, REV, RL, AGE, CI, DAY = range(15); KS = [2, 3, 4, 5, 6]
print("samples", len(A), "| coins", len(O), "| hourly sampling, 5 distances (0.375-1.375%), 2 sides; samples overlap -> block bootstrap (coin x 3-day)")
STR = [(0, 24, "age<6h... <24"), (24, 96, "1-4d? 6-24h"), (96, 383, "24h-4d"), (383, 385, ">=4d(cap)")]
STR = [(0, 24, "price traded here <6h ago"), (24, 96, "6-24h ago"), (96, 383, "1-4d ago"), (383, 385, ">=4d ago/never")]
sname = {0: "none", 1: "low-third", 2: "mid-third", 3: "high-third"}
B = np.zeros(len(A), int)
for lo, hi, _ in STR:
    m = (A[:, AGE] >= lo) & (A[:, AGE] < hi); nz = m & (A[:, SZ] > 0)
    if nz.sum() > 30:
        q = np.quantile(A[nz, SZ], [1 / 3, 2 / 3]); B[nz] = np.where(A[nz, SZ] < q[0], 1, np.where(A[nz, SZ] < q[1], 2, 3))
A = np.column_stack([A, B]); IB = 15
def wil(k, n):
    if n == 0: return (np.nan,) * 3
    p = k / n; z = 1.96; d = 1 + z * z / n; ce = (p + z * z / 2 / n) / d; hw = z * np.sqrt(p * (1 - p) / n + z * z / 4 / n / n) / d; return p, ce - hw, ce + hw
def boot(fn, mask, nb=300):
    sub = A[mask]; keys = sub[:, CI] * 1000 + sub[:, DAY] // 3; uk, inv = np.unique(keys, return_inverse=True); idx = [np.where(inv == j)[0] for j in range(len(uk))]; out = []
    for _ in range(nb):
        pick = rng.integers(0, len(uk), len(uk)); out.append(fn(sub[np.concatenate([idx[j] for j in pick])]))
    return np.nanpercentile(out, [2.5, 97.5])
print("\nCONFOUND CHECK: share of samples by 'age' (time since price last traded at that level) and the model's cluster size")
for lo, hi, nm in STR:
    m = (A[:, AGE] >= lo) & (A[:, AGE] < hi); print(f"  {nm:26s} n={m.sum():6d}  zero-size share={(A[m,SZ]==0).mean():.2f}  median size(nonzero)={np.median(A[m&(A[:,SZ]>0),SZ]) if (m&(A[:,SZ]>0)).any() else float('nan'):.1f} bps of OI")
print("\n(a) TOUCH PROBABILITY, raw (confounded) and AGE-STRATIFIED (same distance-bin pooled over k=2..6, distance-matched lift)")
print("  RAW: overall touch rate by horizon: " + ", ".join(f"{h} {np.nanmean(A[:,c]):.3f}" for h, c in (("4h", T4), ("12h", T12), ("24h", T24))))
for hz, col in (("4h", T4), ("12h", T12), ("24h", T24)):
    print(f"-- horizon {hz}: touch rate by size bucket within each age stratum (pooled k, mean dist {A[:,IDP].mean():.2f}%)")
    for lo, hi, nm in STR:
        row = []
        for b in range(4):
            mm = (A[:, AGE] >= lo) & (A[:, AGE] < hi) & (A[:, IB] == b) & ~np.isnan(A[:, col])
            if mm.sum() < 30: row.append(f"{sname[b][:4]}: n={mm.sum()} (skip)"); continue
            p, l_, h_ = wil(np.nansum(A[mm, col]), mm.sum()); row.append(f"{sname[b][:4]} {p:.3f}[{l_:.3f},{h_:.3f}] n={mm.sum()} d={A[mm,IDP].mean():.2f}%")
        print(f"  {nm:26s} " + " | ".join(row))
def liftk(S, col, ba, bb, lo, hi):
    v = []
    for kk in KS:
        a = S[(S[:, IB] == ba) & (S[:, IK] == kk) & (S[:, AGE] >= lo) & (S[:, AGE] < hi), col]; b = S[(S[:, IB] == bb) & (S[:, IK] == kk) & (S[:, AGE] >= lo) & (S[:, AGE] < hi), col]
        a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
        if len(a) > 8 and len(b) > 8: v.append(a.mean() - b.mean())
    return np.mean(v) if v else np.nan
print("\n  Distance-matched lifts in touch probability, high-third minus low-third size, within age strata (block-bootstrap 95% CI):")
for hz, col in (("4h", T4), ("12h", T12), ("24h", T24)):
    for side, sn in ((0, "both"), (1, "long-liq"), (-1, "short-liq")):
        out = []
        for lo, hi, nm in STR[1:]:
            m = ((A[:, ISIDE] == side) if side else np.ones(len(A), bool)) & (A[:, AGE] >= lo) & (A[:, AGE] < hi) & ~np.isnan(A[:, col])
            pt = liftk(A[m], col, 3, 1, lo, hi); ci = boot(lambda S: liftk(S, col, 3, 1, lo, hi), m, 150) if not np.isnan(pt) else (np.nan, np.nan); out.append(f"{nm.split(' ago')[0] if 'ago' in nm else nm}: {pt:+.3f}[{ci[0]:+.3f},{ci[1]:+.3f}]")
        print(f"  {hz:3s} {sn:9s} " + " | ".join(out))
print("\n  Cluster present (any size) vs none, among same age stratum 6-24h & 1-4d (distance-matched), 12h touch:")
for lo, hi, nm in STR[1:3]:
    m = (A[:, AGE] >= lo) & (A[:, AGE] < hi) & ~np.isnan(A[:, T12]); a = A[m & (A[:, IB] > 0), T12]; b = A[m & (A[:, IB] == 0), T12]
    f = lambda S: np.nanmean([S[(S[:, IB] > 0) & (S[:, IK] == k), T12].mean() - S[(S[:, IB] == 0) & (S[:, IK] == k), T12].mean() for k in KS if ((S[:, IB] == 0) & (S[:, IK] == k)).sum() > 10])
    print(f"   {nm}: n_cluster={len(a)} n_none={len(b)}  touch {a.mean():.3f} vs {b.mean():.3f}  matched lift={f(A[m]):+.3f}  CI{np.round(boot(f,m,150),3)}")
print("\n(c) Logistic touch ~ dist/ATR1h + log(1+age) + log1p(size) + long-side, IRLS, naive SE (optimistic: overlapping samples)")
def logit(X, y, it=30):
    b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p); b = b + np.linalg.solve((X.T * W) @ X + 1e-6 * np.eye(len(b)), X.T @ (y - p))
    p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p); return b, np.sqrt(np.diag(np.linalg.inv((X.T * W) @ X)))
for hz, col in (("4h", T4), ("12h", T12), ("24h", T24)):
    m = ~np.isnan(A[:, col]); y = A[m, col]
    X0 = np.column_stack([np.ones(m.sum()), A[m, IDA], np.log1p(A[m, AGE]), (A[m, ISIDE] == 1).astype(float)]); b0, _ = logit(X0, y)
    X = np.column_stack([X0, np.log1p(A[m, SZ])]); b, se = logit(X, y)
    ll = lambda X_, b_: np.sum(y * np.log(1 / (1 + np.exp(-X_ @ b_))) + (1 - y) * np.log(1 - 1 / (1 + np.exp(-X_ @ b_))))
    print(f"  {hz}: dist_atr {b[1]:+.3f} | log(age) {b[2]:+.3f} | long-side {b[3]:+.3f} | log1p(size) {b[4]:+.3f} (naive z={b[4]/se[4]:+.1f}) | LR gain from size {2*(ll(X,b)-ll(X0,b0)):.1f}")
print("  Per-coin sign of 12h high-third-minus-low-third lift in 1-4d stratum:", end=" "); pos = tot = 0
for ci in range(len(O)):
    m = (A[:, CI] == ci) & ~np.isnan(A[:, T12]); v = liftk(A[m], T12, 3, 1, 96, 383)
    if not np.isnan(v): tot += 1; pos += v > 0
print(f"{pos}/{tot} coins positive")
print("\n(b) REACTION after touch (k=4 level, d=0.875%, first touch within 12h; race: +/-1h-ATR within next 2h): bounce away (reversal) vs push through (continuation)")
m0 = (A[:, IK] == 4) & ~np.isnan(A[:, REV])
def rline(mm, lab):
    r = A[mm, REV]; nr, nc, nn, na = (r == 1).sum(), (r == 2).sum(), (r == 0).sum(), (r == 3).sum(); p, lo, hi = wil(nr, nr + nc)
    print(f"  {lab:46s} touches={mm.sum():5d} rev={nr} cont={nc} neither={nn} amb={na}  P(rev|decided)={p:.3f}[{lo:.3f},{hi:.3f}]")
rline(m0, "ALL touches (baseline)")
for side, sn in ((1, "long-liq level (hit going down)"), (-1, "short-liq level (hit going up)")): rline(m0 & (A[:, ISIDE] == side), sn)
for lo, hi, nm in STR[1:]:
    for b in (0, 1, 3):
        mm = m0 & (A[:, AGE] >= lo) & (A[:, AGE] < hi) & (A[:, IB] == b)
        if mm.sum() >= 30: rline(mm, f"age {nm[:14]:14s} {sname[b]}")
def rv(S, ba, bb):
    f = lambda b: ((S[(S[:, IB] == b) & (S[:, AGE] >= 96) & np.isin(S[:, REV], [1, 2]), REV] == 1).mean())
    return f(ba) - f(bb)
m = m0 & (A[:, AGE] >= 96); ci = boot(lambda S: rv(S, 3, 1), m, 300); print(f"  reversal-share lift, high-third minus low-third (age>=1d): {rv(A[m],3,1):+.3f} CI[{ci[0]:+.3f},{ci[1]:+.3f}]")
# magnitude: mean favorable minus adverse not available; report mean realized liq below
print("\n(d) GROUND TRUTH: Gate realized liquidations vs model-swept clusters (all bars after warm-up, 26 coins)")
def rank(x): o = np.argsort(x, kind="mergesort"); r = np.empty(len(x)); r[o] = np.arange(len(x)); return r
def spear(a, b): return np.corrcoef(rank(a), rank(b))[0, 1]
i0 = 400; per = {1: ([], [], []), -1: ([], [], [])}
for c, r in O.items():
    oi = r["oi"][i0:]; pc = r["cl"][i0 - 1:-1]
    for side, sw, lq, mv in ((1, r["swl"], r["lliq"], (pc - r["l"][i0:]) / pc * 100), (-1, r["sws"], r["sliq"], (r["h"][i0:] - pc) / pc * 100)):
        per[side][0].append(sw[i0:] / oi * 1e4); per[side][1].append(lq[i0:] / oi * 1e4); per[side][2].append(mv)
for side, sn in ((1, "LONG side (model-swept long clusters vs Gate long_liq_usd)"), (-1, "SHORT side")):
    a, b, mv = [np.concatenate(x) for x in per[side]]; pcs = np.mean([spear(x, y) for x, y in zip(per[side][0], per[side][1])])
    print(f"  {sn}: bars={len(a)}; model swept>0 {(a>0).mean():.1%}, Gate realized>0 {(b>0).mean():.1%}; Spearman pooled={spear(a,b):.3f}, mean per-coin={pcs:.3f}; Spearman(realized, move size)={spear(b,mv):.3f}, Spearman(swept, move size)={spear(a,mv):.3f}")
    print(f"     P(realized>0|swept>0)={(b[a>0]>0).mean():.3f} n={(a>0).sum()} vs P(realized>0|swept==0)={(b[a==0]>0).mean():.3f} n={(a==0).sum()}")
    for lo_, hi_ in ((0.3, 0.7), (0.7, 1.5), (1.5, 3), (3, 99)):
        mm = (mv >= lo_) & (mv < hi_)
        if mm.sum() < 40: continue
        s1 = mm & (a > 0); s0 = mm & (a == 0)
        sp = spear(a[mm & (a > 0)], b[mm & (a > 0)]) if (mm & (a > 0)).sum() > 20 else float('nan')
        print(f"     move {lo_}-{hi_}%: n={mm.sum():5d} | swept>0: n={s1.sum():5d} P(real>0)={(b[s1]>0).mean() if s1.sum() else float('nan'):.3f} mean={b[s1].mean() if s1.sum() else float('nan'):.2f}bps | swept==0: n={s0.sum():5d} P(real>0)={(b[s0]>0).mean() if s0.sum() else float('nan'):.3f} mean={b[s0].mean() if s0.sum() else float('nan'):.2f}bps | Spearman within swept>0={sp:.3f}")
print("\n  Realized same-side liq in touch bar + next bar (k=4 touches, 12h), bps of OI, by age stratum x size:")
for lo, hi, nm in STR[1:]:
    for b in (0, 1, 3):
        mm = m0 & ~np.isnan(A[:, RL]) & (A[:, AGE] >= lo) & (A[:, AGE] < hi) & (A[:, IB] == b)
        if mm.sum() >= 30: x = A[mm, RL]; print(f"   age {nm[:14]:14s} {sname[b]:10s} n={mm.sum():5d} P(realized>0)={(x>0).mean():.3f} mean={x.mean():.2f} median={np.median(x):.2f}")
