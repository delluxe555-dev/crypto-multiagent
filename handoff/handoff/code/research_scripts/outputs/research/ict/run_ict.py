#!/usr/bin/env python3
"""run_ict.py - generate signals for 6 setups x 12 pairs x 3 TFs, simulate 4 configs (stop zone|atr x target 1R|2R), plus random-entry baseline (same stops/targets, K reps).
Outputs: trades_ict.npz (real trades), baseline_ict.npz (aggregated random-entry results).  Run: python run_ict.py"""
import os, sys, time, numpy as np
from multiprocessing import Pool
import ict_setups as S
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
PAIRS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","NEAR","LTC","DOT"]; TFS = ["15m","1h","4h"]
STOPS = ["zone","atr"]; TGTS = [1.0, 2.0]; COSTS = [0.0, 0.0005, 0.0015]; KREP = 10
def job(a):
    pair, tf = a; df = S.load(pair, tf); o, h, l, c = (df[x].values for x in "ohlc"); atr = S.atr14(df); n = len(df); import pandas as pd; ts = np.asarray((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s"), dtype=np.int64)
    rng = np.random.default_rng(abs(hash((pair, tf))) % (2**32) if False else (PAIRS.index(pair) * 10 + TFS.index(tf) + 12345))
    real = []; base = {}
    for mode in range(1, 7):
        si, sd, zl, zh = S.gen_signals(o, h, l, c, atr, mode)
        zr = S.zone_risk_atr(o, atr, l, h, si, sd, zl, zh); lf = float((sd == 1).mean()) if len(sd) else 0.5
        for sm, sname in enumerate(STOPS):
            for R in TGTS:
                oi, oo, od, g, k, ra = S.sim(o, h, l, c, atr, si, sd, zl, zh, sm, R, np.zeros(len(si)))
                real.append(dict(setup=mode, tf=TFS.index(tf), pair=PAIRS.index(pair), stop=sm, tgt=R, n_sig=len(si), t_in=ts[oi], t_out=ts[oo], dir=od, g=g, k=k, ra=ra))
                key = (mode, TFS.index(tf), sm, R); acc = np.zeros((KREP, 1 + len(COSTS)))
                if len(si) >= 5 and (sm == 1 or len(zr) > 0):
                    for r in range(KREP):
                        bi = np.sort(rng.integers(30, n - 2, len(si))); bd = np.where(rng.random(len(si)) < lf, 1, -1).astype(np.int64)
                        rk = np.full(len(si), S.ATR_STOP) if sm == 1 else rng.choice(zr, len(si))
                        _, _, _, bg, bk, _ = S.sim(o, h, l, c, atr, bi, bd, np.zeros(len(si)), np.zeros(len(si)), 2, R, rk)
                        acc[r, 0] = len(bg)
                        for ci, cs in enumerate(COSTS): acc[r, 1 + ci] = (bg - 2 * cs * bk).sum()
                base[key] = acc
    return pair, tf, real, base
if __name__ == "__main__":
    t0 = time.time(); jobs = [(p, t) for t in TFS for p in PAIRS]
    with Pool(8) as pool: res = pool.map(job, jobs, chunksize=1)
    cols = {k: [] for k in ["setup","tf","pair","stop","tgt","t_in","t_out","dir","g","k","ra"]}; nsig = {}
    for pair, tf, real, base in res:
        for r in real:
            m = len(r["g"]); nsig[(r["setup"], r["tf"], r["pair"])] = r["n_sig"]
            for kk in ("setup","tf","pair","stop"): cols[kk].append(np.full(m, r[kk], np.int8))
            cols["tgt"].append(np.full(m, r["tgt"], np.float32))
            for kk in ("t_in","t_out","dir","g","k","ra"): cols[kk].append(r[kk])
    out = {k: np.concatenate(v) for k, v in cols.items()}; np.savez_compressed("trades_ict.npz", **out)
    keys = sorted({k for _, _, _, b in res for k in b}); B = {}
    for key in keys: B[key] = sum(b[key] for _, _, _, b in res if key in b)   # (KREP, 1+len(COSTS)) pooled across pairs
    np.savez_compressed("baseline_ict.npz", keys=np.array(keys, dtype=float), vals=np.array([B[k] for k in keys]), costs=np.array(COSTS))
    np.savez_compressed("nsig_ict.npz", keys=np.array(list(nsig.keys())), vals=np.array(list(nsig.values())))
    print("trades", len(out["g"]), "elapsed", round(time.time() - t0, 1), "s")
