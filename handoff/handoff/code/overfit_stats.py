#!/usr/bin/env python3
"""overfit_stats.py - asiri-uyum (overfitting) istatistikleri: Deflated Sharpe (DSR), PBO (CSCV), (coin x 3-gun) blok-bootstrap, maliyet stres testi, White-Reality-Check tarzi max-istatistik.
Fikir kaynagi: QuantDinger strategy_evolution/statistics.py (Apache-2.0) - fikirler (DSR, PBO, blok bootstrap); kod SIFIRDAN yazildi (scipy yok -> statistics.NormalDist).
Literatur: Bailey & Lopez de Prado (2014) DSR; Bailey, Borwein, Lopez de Prado, Zhu (2017) PBO/CSCV; White (2000) Reality Check.
Girdi: outputs/research/trades_r2.npz (funding_bt.py build). Hucre = (pair, cfg, combo) = 630. Gunluk seri = hucrenin tum coinlerinin gun-bazli net R toplami (cikis gunune gore).
Alt komutlar:
  python3 overfit_stats.py null            # (1) SENTETIK RASTGELE VERIDE testin calistigini goster (yanlis-pozitif orani)  -> outputs/research/overfit_null.json
  python3 overfit_stats.py real            # (2) gercek combo_bt2 islemlerinde DSR/PBO/bootstrap/maliyet stresi             -> outputs/research/overfit_real.json
  python3 overfit_stats.py worlds N        # (3) N adet sentetik 'dunya' (blok-karistirilmis fiyat) -> gercek motor -> ayni testler -> outputs/research/overfit_worlds.json
  python3 overfit_stats.py report          # uc JSON'dan outputs/research_B_overfit_stats.md
"""
import sys, os, json, math, time, itertools
import numpy as np
from statistics import NormalDist
ND = NormalDist(); EG = 0.5772156649015329
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f"{HERE}/outputs/research"
CUT_TS = 1788566400  # 2026-09-05 00:00 UTC
NCELL = 630

# ---------------------------------------------------------------- temel istatistikler
def sr_stats(x):
    """x: (..., T) gunluk seri -> (mean, sd, skew, raw_kurt). sd=0 ise nan."""
    m = x.mean(-1); d = x - m[..., None]; s2 = (d ** 2).mean(-1); sd = np.sqrt(s2)
    with np.errstate(all="ignore"):
        sk = (d ** 3).mean(-1) / sd ** 3; ku = (d ** 4).mean(-1) / sd ** 4
    return m, sd, sk, ku
def exp_max_sr(V, N):
    """E[max SR] N bagimsiz denemede, SR0 (Bailey-LdP): sqrt(V)*((1-g)Z^-1(1-1/N)+g Z^-1(1-1/(N e)))."""
    if N <= 1: return 0.0
    return math.sqrt(V) * ((1 - EG) * ND.inv_cdf(1 - 1 / N) + EG * ND.inv_cdf(1 - 1 / (N * math.e)))
def dsr(sr, T, skew, kurt, V, N):
    """Deflated Sharpe orani (olasilik): SR gunluk (yillik DEGIL). N=1 -> PSR(0)."""
    sr0 = exp_max_sr(V, N); den = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if not np.isfinite(den) or den <= 0: return float("nan")
    return ND.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den))
def pbo_cscv(X, S=14, max_comb=None, rng=None):
    """X: (N strateji, T gun) getiri. Contiguous S blok; IS = S/2 blok kombinasyonu. Donus: PBO (logit<=0 orani), OOS-kayip olasiligi, IS-SR/OOS-SR egim, n_comb.
    Siralama olcutu: gunluk Sharpe (mean/sd)."""
    N, T = X.shape; ok = X.std(1) > 0; X = X[ok]; N = X.shape[0]
    edges = np.array_split(np.arange(T), S); sm = np.array([X[:, e].sum(1) for e in edges]).T; sq = np.array([(X[:, e] ** 2).sum(1) for e in edges]).T; cnt = np.array([len(e) for e in edges])
    combs = list(itertools.combinations(range(S), S // 2))
    if max_comb and len(combs) > max_comb:
        rng = rng or np.random.default_rng(0); combs = [combs[i] for i in rng.choice(len(combs), max_comb, replace=False)]
    lam = []; oos_loss = []; xi = []; xo = []; allb = np.arange(S)
    for c in combs:
        ib = np.array(c); ob = np.setdiff1d(allb, ib)
        def srv(b):
            n = cnt[b].sum(); mu = sm[:, b].sum(1) / n; v = sq[:, b].sum(1) / n - mu * mu; return mu / np.sqrt(np.maximum(v, 1e-18))
        si, so = srv(ib), srv(ob); k = int(np.argmax(si)); w = ((so < so[k]).sum() + 1) / (N + 1)
        lam.append(math.log(w / (1 - w))); oos_loss.append(so[k] < 0); xi.append(si[k]); xo.append(so[k])
    lam = np.array(lam); xi = np.array(xi); xo = np.array(xo)
    slope = float(np.polyfit(xi, xo, 1)[0]) if xi.std() > 0 else float("nan")
    return dict(pbo=float((lam <= 0).mean()), p_oos_loss=float(np.mean(oos_loss)), slope=slope, n_comb=len(combs), n_strat=N, mean_oos_sr_selected=float(xo.mean()), mean_is_sr_selected=float(xi.mean()))

# ---------------------------------------------------------------- veri
def load_trades(fp=f"{RES}/trades_r2.npz"):
    z = np.load(fp); T = {k: z[k] for k in z.files}; T["cell"] = T["pair"].astype(np.int32) * 105 + T["cfg"].astype(np.int32) * 35 + T["combo"].astype(np.int32); return T
def net_r(T, cost_side, fund=None):
    """net R = g - 2*cost_side*k  (+ funding_R varsa)."""
    x = T["g"] - 2 * cost_side * T["k"]; return x if fund is None else x + fund
def daily_matrix(T, net, t0=None):
    t0 = t0 if t0 is not None else (T["t_in"].min() // 86400) * 86400; day = ((T["t_out"] - t0) // 86400).astype(np.int64); nd = int(day.max()) + 1
    M = np.bincount(T["cell"].astype(np.int64) * nd + day, weights=net, minlength=NCELL * nd).reshape(NCELL, nd); return M, t0, nd
def unit_matrices(T, nd_block=3, t0=None, by_coin=True, fund=None):
    """by_coin=True: (coin x 3-gun blok) birimleri (istenen yontem). by_coin=False: 3-gun bloklari, TUM coinler birlikte (coinler arasi korelasyonu korur -> daha tutucu).
    Doner Sg, Sk, Sf, Sn, U (U x 630)."""
    t0 = t0 if t0 is not None else (T["t_in"].min() // 86400) * 86400; blk = ((T["t_out"] - t0) // 86400 // nd_block).astype(np.int64); nb = int(blk.max()) + 1; nc = int(T["coin"].max()) + 1
    u = (T["coin"].astype(np.int64) * nb + blk) if by_coin else blk; U = nc * nb if by_coin else nb; ix = u * NCELL + T["cell"]
    f = lambda w: np.bincount(ix, weights=w, minlength=U * NCELL).reshape(U, NCELL)
    return f(T["g"]), f(T["k"]), (f(fund) if fund is not None else np.zeros((U, NCELL))), f(np.ones(len(u))), U
def bootstrap_means(S, Sn, R=2000, rng=None, batch=250):
    """birimleri yerine koyarak ornekle; hucre basina islem-basi ortalama net R dagilimi (R x 630) + gozlenen. S = birim bazli net-R toplami (U x 630)."""
    rng = rng or np.random.default_rng(1); U = S.shape[0]; obs = S.sum(0) / np.maximum(Sn.sum(0), 1); out = []
    for b0 in range(0, R, batch):
        W = rng.multinomial(U, np.full(U, 1 / U), size=min(batch, R - b0)).astype(np.float64); out.append((W @ S) / np.maximum(W @ Sn, 1))
    return obs, np.vstack(out)
def reality_check(obs, boot, mask, n_min=0, Sn=None):
    """Studentize edilmis max-istatistik (White RC / Hansen SPA'ya benzer): H0: hicbir hucrenin ortalamasi >0 degil. p = P(max_k t*_k >= max_k t_k)."""
    sd = boot.std(0); ok = mask & (sd > 0)
    if n_min and Sn is not None: ok &= Sn.sum(0) >= n_min
    t_obs = obs[ok] / sd[ok]; t_boot = (boot[:, ok] - obs[ok]) / sd[ok]; mx = t_boot.max(1); kbest = np.argmax(t_obs)
    return dict(max_t_obs=float(t_obs.max()), p=float((mx >= t_obs.max()).mean()), best_cell=int(np.where(ok)[0][kbest]), n_cells=int(ok.sum()))

# ---------------------------------------------------------------- (1) sentetik null
def null_layer1(nsim_dsr=2000, nsim_pbo=250, N=NCELL, T=150, rho=0.3, seed=0, df_t=None):
    rng = np.random.default_rng(seed); res = dict(N=N, T=T, rho=rho, heavy_tail_df=df_t)
    def gen(n=N):
        f = rng.standard_normal(T); e = rng.standard_normal((n, T))
        if df_t: f = rng.standard_t(df_t, T) / math.sqrt(df_t / (df_t - 2)); e = rng.standard_t(df_t, (n, T)) / math.sqrt(df_t / (df_t - 2))
        return math.sqrt(rho) * f + math.sqrt(1 - rho) * e
    naive = []; d_n1 = []; d_N = []; both = []; best_sr = []
    for _ in range(nsim_dsr):
        X = gen(); m, sd, sk, ku = sr_stats(X); sr = m / sd; k = int(np.argmax(sr)); V = float(np.var(sr, ddof=1)); best_sr.append(sr[k])
        naive.append(sr[k] * math.sqrt(T) > 1.96); d_n1.append(dsr(sr[k], T, sk[k], ku[k], V, 1) > 0.95); p = dsr(sr[k], T, sk[k], ku[k], V, N); d_N.append(p > 0.95)
    res["null_naive_t_gt_1.96_share_of_best"] = float(np.mean(naive)); res["null_PSR_N1_gt_0.95"] = float(np.mean(d_n1)); res["null_DSR_N_gt_0.95"] = float(np.mean(d_N)); res["mean_best_daily_SR"] = float(np.mean(best_sr))
    res["expected_max_SR0_theory"] = exp_max_sr(1 / T, N)
    pb = [pbo_cscv(gen(), max_comb=600, rng=rng) for _ in range(nsim_pbo)]
    res["null_PBO_mean"] = float(np.mean([p["pbo"] for p in pb])); res["null_PBO_sd"] = float(np.std([p["pbo"] for p in pb])); res["null_p_oos_loss_mean"] = float(np.mean([p["p_oos_loss"] for p in pb]))
    res["null_oos_SR_of_IS_best_mean"] = float(np.mean([p["mean_oos_sr_selected"] for p in pb])); res["null_is_SR_of_IS_best_mean"] = float(np.mean([p["mean_is_sr_selected"] for p in pb]))
    res["null_PBO_gt_0.5_share"] = float(np.mean([p["pbo"] > 0.5 for p in pb]))
    # pozitif kontrol (guc): bir stratejiye gercek edge ekle
    pw = {}
    for sr_true in (0.0, 0.10, 0.20, 0.30):
        hit_d = []; hit_p = []; hit_naive = []
        for _ in range(400):
            X = gen(); X[0] += sr_true; m, sd, sk, ku = sr_stats(X); sr = m / sd; k = int(np.argmax(sr)); V = float(np.var(sr, ddof=1))
            hit_naive.append(sr[k] * math.sqrt(T) > 1.96); hit_d.append(dsr(sr[k], T, sk[k], ku[k], V, N) > 0.95); hit_p.append(k == 0)
        pw[str(sr_true)] = dict(naive=float(np.mean(hit_naive)), dsr=float(np.mean(hit_d)), picked_true=float(np.mean(hit_p)))
    res["power_by_true_daily_SR"] = pw
    # bootstrap/RC kalibrasyonu: gunluk seriden (coin x blok yerine gun-blok) max-t kontrolu
    return res
def run_null():
    out = {}
    t = time.time()
    out["rho0.0_normal"] = null_layer1(rho=0.0, seed=1, nsim_dsr=1000, nsim_pbo=120); out["rho0.3_normal"] = null_layer1(rho=0.3, seed=2, nsim_dsr=1000, nsim_pbo=120); out["rho0.3_t4"] = null_layer1(rho=0.3, seed=3, df_t=4, nsim_dsr=1000, nsim_pbo=120)
    # gercek veriden korelasyon
    try:
        T = load_trades(); M, _, nd = daily_matrix(T, net_r(T, 0.0005)); nb = np.ones(NCELL, bool); sd = M.std(1) > 0; C = np.corrcoef(M[sd][:200]); out["real_mean_pairwise_corr_first200cells"] = float((C.sum() - len(C)) / (len(C) ** 2 - len(C)))
        out["rho_real"] = out["real_mean_pairwise_corr_first200cells"]; out["rho_real_run"] = null_layer1(rho=max(out["rho_real"], 0.0), seed=4, nsim_dsr=1000, nsim_pbo=150)
    except Exception as ex: out["real_corr_err"] = str(ex)
    out["elapsed_s"] = time.time() - t; json.dump(out, open(f"{RES}/overfit_null.json", "w"), indent=1); print(json.dumps(out, indent=1))

# ---------------------------------------------------------------- (2) gercek veri
CELLNAMES = None
def cell_name(T, c): return f"{T['pairs'][c // 105]} | {T['cfgs'][(c % 105) // 35]} | {T['combos'][c % 35]}"
def halves(T, net):
    oos = T["t_in"] >= CUT_TS; c = T["cell"]; s = lambda m: np.bincount(c[m], weights=net[m], minlength=NCELL) / np.maximum(np.bincount(c[m], minlength=NCELL), 1)
    return s(~oos), s(oos)
def analyze(T, fund=None, costs=(0.0003, 0.0005, 0.00075, 0.001, 0.0015), topk=10, R=2000, seed=1, Nlist=(5, 20, 630, 665, 850, 1055), include_pbo=True, verbose=True):
    out = {}; nonbase = np.array([not T["combos"][c % 35].startswith("BASE_") for c in range(NCELL)]); n_per = np.bincount(T["cell"], minlength=NCELL)
    UM = {m: unit_matrices(T, by_coin=(m == "cb"), fund=fund) for m in ("cb", "blk")}; out["n_trades"] = int(len(T["g"])); out["n_units"] = {m: int(UM[m][4]) for m in UM}
    for cs in (0.0005, 0.0015):
        net = net_r(T, cs, fund); M, t0, nd = daily_matrix(T, net); m, sd, sk, ku = sr_stats(M); ok = sd > 0; sr = np.where(ok, m / np.where(ok, sd, 1), -9); V = float(np.var(sr[ok & nonbase], ddof=1))
        mean_tr = np.bincount(T["cell"], weights=net, minlength=NCELL) / np.maximum(n_per, 1); h1, h2 = halves(T, net)
        sc_sr = np.where(nonbase, sr, -9); sc_mr = np.where(nonbase & (n_per >= 300), mean_tr, -9); order = list(dict.fromkeys(list(np.argsort(-sc_sr)[:topk]) + list(np.argsort(-sc_mr)[:5])))
        B = {}; RC = {}
        for mo, (Sg, Sk, Sf, Sn, U) in UM.items():
            obs, boot = bootstrap_means(Sg - 2 * cs * Sk + Sf, Sn, R=R, rng=np.random.default_rng(seed)); B[mo] = boot; RC[mo] = dict(reality_check(obs, boot, nonbase, n_min=300, Sn=Sn)); RC[mo]["best_name"] = cell_name(T, RC[mo]["best_cell"])
        tops = []
        for c in order:
            row = dict(cell=int(c), name=cell_name(T, int(c)), n=int(n_per[c]), mean_R=float(mean_tr[c]), daily_SR=float(sr[c]), SR_ann=float(sr[c] * math.sqrt(365)), skew=float(sk[c]), kurt=float(ku[c]), is_R=float(h1[c]), oos_R=float(h2[c]),
                       DSR={str(N): dsr(sr[c], nd, sk[c], ku[c], V, N) for N in Nlist}, PSR=dsr(sr[c], nd, sk[c], ku[c], V, 1))
            for mo in B:
                lo, hi = np.percentile(B[mo][:, c], [2.5, 97.5]); row[f"ci_{mo}"] = [float(lo), float(hi)]; row[f"p_le0_{mo}"] = float((B[mo][:, c] <= 0).mean())
            row["boot_ci"] = row["ci_cb"]; row["p_le0"] = row["p_le0_cb"]; sel = T["cell"] == c; f_ = 0 if fund is None else fund[sel]
            row["cost_stress_meanR"] = {f"{x*100:.3g}%": float((T["g"][sel] - 2 * x * T["k"][sel] + f_).mean()) for x in costs}
            row["breakeven_cost_side_pct"] = float((T["g"][sel].mean() + (0 if fund is None else f_.mean())) / (2 * T["k"][sel].mean()) * 100); tops.append(row)
        pos2 = (h1 > 0) & (h2 > 0) & nonbase
        out[f"cost{cs*100:.3g}pct"] = dict(V_sr_var=V, nd=nd, top=tops, reality_check=RC["cb"], reality_check_blk=RC["blk"], n_pos_both_halves=int(pos2.sum()), n_pos_mean=int(((mean_tr > 0) & nonbase).sum()), n_cells_nonbase=int(nonbase.sum()),
                                           SR0_by_N={str(N): exp_max_sr(V, N) for N in Nlist})
        if include_pbo:
            for lab, mask in (("all630", np.ones(NCELL, bool)), ("nonbase558", nonbase)): out[f"cost{cs*100:.3g}pct"][f"pbo_{lab}"] = pbo_cscv(M[mask], S=14, max_comb=1500, rng=np.random.default_rng(5))
        if verbose: print("cost", cs, "done", flush=True)
    return out
def run_real():
    T = load_trades(); t = time.time(); out = analyze(T); out["elapsed_s"] = time.time() - t
    json.dump(out, open(f"{RES}/overfit_real.json", "w"), indent=1); print("ok", out["elapsed_s"])

# ---------------------------------------------------------------- (3) sentetik dunyalar (gercek motor)
def synth_df(df, rng):
    """Gercek 5m seriyi gun bloklari halinde KARISTIR (tum coinlerde AYNI gun permutasyonu -> coinler-arasi korelasyon/volatilite kumelenmesi gun-ici korunur, gunler-arasi trend/otokorelasyon yok edilir).
    Mumlar onceki kapanisa goreli oranlarla yeniden insa edilir."""
    import pandas as pd
    d = df.copy(); idx = d.index; days = idx.normalize(); ug = pd.unique(days)
    prev = d.c.shift(1).bfill(); ro, rh, rl, rc = (d.o / prev).values, (d.h / prev).values, (d.l / prev).values, (d.c / prev).values; v = d.v.values
    pos = {g: np.where(days == g)[0] for g in ug}; order = rng.permutation(len(ug)); sel = np.concatenate([pos[ug[i]] for i in order])
    # tam gun degilse (ilk/son) uzunluk degisebilir -> ilk len(d) satiri al
    sel = sel[:len(d)]; ro, rh, rl, rc, v = ro[sel], rh[sel], rl[sel], rc[sel], v[sel]
    c = d.c.iloc[0] * np.cumprod(rc); pc = np.r_[d.c.iloc[0], c[:-1]]; o = pc * ro; h = pc * rh; l = pc * rl
    return pd.DataFrame(dict(o=o, h=np.maximum.reduce([o, h, c, l]), l=np.minimum.reduce([o, h, c, l]), c=c, v=v), index=idx[:len(o)])
def world_work(args):
    coin, seed = args; sys.path.insert(0, HERE); import funding_bt as F, combo_bt as m
    df = m.load(coin); rng = np.random.default_rng(seed); sd = synth_df(df, rng)
    return F.work_df(coin, sd)
def run_worlds(n, nproc=3):
    from multiprocessing import Pool; sys.path.insert(0, HERE); import funding_bt as F; import combo_bt2 as b2
    coins = b2.COINS; fp = f"{RES}/overfit_worlds.json"; allres = json.load(open(fp)) if os.path.exists(fp) else []
    for w in range(len(allres), n):
        t = time.time(); seed = 1000 + w
        with Pool(nproc) as p: res = p.map(world_work, [(c, seed) for c in coins])   # ayni seed -> tum coinlerde ayni gun permutasyonu
        names = res[0][1]; Tt = []; cid = []
        for ci, (c, nm, A) in enumerate(res): Tt.append(A); cid.append(np.full(len(A), ci))
        Tt = np.vstack(Tt); cid = np.concatenate(cid)
        T = dict(pair=Tt[:, 0].astype(np.int8), cfg=Tt[:, 1].astype(np.int8), combo=Tt[:, 2].astype(np.int8), t_in=Tt[:, 3].astype(np.int64), t_out=Tt[:, 4].astype(np.int64), dir=Tt[:, 5].astype(np.int8), g=Tt[:, 6], k=Tt[:, 7], mae=Tt[:, 8], coin=cid.astype(np.int8),
                 coins=np.array(coins), combos=np.array(names), pairs=np.array([f"{a}/{b}" for a, b in F.PAIRS]), cfgs=np.array(list(F.CFGS))); T["cell"] = T["pair"].astype(np.int32) * 105 + T["cfg"].astype(np.int32) * 35 + T["combo"].astype(np.int32)
        a = analyze(T, R=500, topk=3, include_pbo=True, verbose=False)
        row = dict(world=w, seed=seed, n_trades=int(len(T["g"])), elapsed_s=time.time() - t)
        for k in ("cost0.05pct", "cost0.15pct"):
            r = a[k]; top = r["top"][0]; row[k] = dict(n_pos_both_halves=r["n_pos_both_halves"], n_pos_mean=r["n_pos_mean"], best_name=top["name"], best_meanR=top["mean_R"], best_ci=top["boot_ci"], best_DSR_N665=top["DSR"]["665"], best_PSR=top["PSR"],
                                                       rc_p=r["reality_check"]["p"], rc_p_blk=r["reality_check_blk"]["p"], best_ci_blk=top["ci_blk"], best_p_le0_cb=top["p_le0_cb"], best_p_le0_blk=top["p_le0_blk"], pbo_nonbase=r["pbo_nonbase558"]["pbo"], gross_mean_all=float(T["g"].mean()), top_oos_R=top["oos_R"], top_is_R=top["is_R"])
        allres.append(row); json.dump(allres, open(fp, "w"), indent=1); print("world", w, row, flush=True)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "null": run_null()
    elif cmd == "real": run_real()
    elif cmd == "worlds": run_worlds(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    elif cmd == "report": import overfit_report as R; R.main()
