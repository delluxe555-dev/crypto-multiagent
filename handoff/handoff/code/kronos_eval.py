#!/usr/bin/env python3
"""kronos_eval.py - kronos_full.py ciktisinin (preds_<model>.jsonl) degerlendirmesi. Calistir: python3 kronos_eval.py [small mini] -> outputs/research_D_kronos.md + outputs/research/kronos/eval.json
Tanimlar: tahmin noktasi e (1s mum baslangici); baglam yalniz [e-400,e). Karar anında bilinen: last_close (e-1 kapanisi). Tahmin getirisi h mum ileri = pred_close[h-1]/last_close - 1.
Gerceklesen yon: real_close[h-1]/last_close - 1 > 0.  Strateji (24s): yon = isaret(tahmin_24); giris = e mumunun acilisi (real_open0), cikis = e+23 kapanisi; net = yon*(c23/open0-1) - 2*0.0015.
Karsilastirma: rastgele yon (p=0.5, 5000 simulasyon), her zaman long, her zaman short, yanlilik-eslestirilmis rastgele (modelle ayni 'yukari' orani). CI: (coin x 3-gun blok) bootstrap (istenen) VE gun-bloklari (tum coinler birlikte; coinler arasi korelasyon icin daha tutucu).
Coklu test: Holm-Bonferroni (aile = kronos denemeleri) + gunluk-portfoy DSR (overfit_stats.py araclari)."""
import json, sys, os, math, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import overfit_stats as O
HERE = os.path.dirname(os.path.abspath(__file__)); KD = f"{HERE}/outputs/research/kronos"; COST = 0.0015; HS = (1, 4, 12, 24)
rng = np.random.default_rng(11)
def load(model):
    rows = [json.loads(l) for l in open(f"{KD}/preds_{model}.jsonl")]
    coins = sorted(set(r["coin"] for r in rows)); ci = {c: i for i, c in enumerate(coins)}; e = np.array([r["e"] for r in rows], dtype=np.int64); lc = np.array([r["last_close"] for r in rows]); o0 = np.array([r["real_open0"] for r in rows])
    P = np.array([r["pred_close"] for r in rows]); R = np.array([r["real_close"] for r in rows]); coin = np.array([ci[r["coin"]] for r in rows]); ok = np.isfinite(P).all(1) & (lc > 0) & (o0 > 0)
    d = dict(coin=coin[ok], e=e[ok], lc=lc[ok], o0=o0[ok], P=P[ok], R=R[ok], coins=coins); d["day"] = (d["e"] - d["e"].min()) // 86400; return d
def wilson(k, n):
    if n == 0: return (float("nan"),) * 2
    p = k / n; z = 1.96; dd = 1 + z * z / n; c = (p + z * z / 2 / n) / dd; h = z * math.sqrt(p * (1 - p) / n + z * z / 4 / n / n) / dd; return c - h, c + h
def boot_mean(x, blocks, nb=3000):
    u, inv = np.unique(blocks, return_inverse=True); s = np.bincount(inv, weights=x); c = np.bincount(inv).astype(float); U = len(u); out = np.empty(nb)
    for i in range(nb): w = rng.multinomial(U, np.full(U, 1 / U)); out[i] = (w @ s) / (w @ c)
    return out
def ci_p(bs, null):  # iki-tarafli bootstrap p (null degerine gore) ve %95 aralik
    p = 2 * min((bs <= null).mean(), (bs >= null).mean()); return np.percentile(bs, [2.5, 97.5]), min(max(p, 1 / len(bs)), 1.0)
def evaluate(d, tag):
    n = len(d["lc"]); out = dict(model=tag, n=n, n_coins=len(d["coins"]), n_days=int(d["day"].max()) + 1); blk_cb = d["coin"].astype(np.int64) * 1000 + d["day"] // 3; blk_day = d["day"].astype(np.int64)
    res = {}
    for h in HS:
        pr = d["P"][:, h - 1] / d["lc"] - 1; rr = d["R"][:, h - 1] / d["lc"] - 1; up_p = pr > 0; up_r = rr > 0; hit = (up_p == up_r).astype(float)
        r = dict(h=h, hit=hit.mean(), hit_ci_cb=ci_p(boot_mean(hit, blk_cb), 0.5)[0].tolist(), hit_ci_day=ci_p(boot_mean(hit, blk_day), 0.5)[0].tolist(), p_hit_vs_half_cb=ci_p(boot_mean(hit, blk_cb), 0.5)[1], p_hit_vs_half_day=ci_p(boot_mean(hit, blk_day), 0.5)[1],
                 pred_up=up_p.mean(), real_up=up_r.mean(), always_long_hit=up_r.mean(), always_short_hit=1 - up_r.mean(), bias_matched_random_hit=up_p.mean() * up_r.mean() + (1 - up_p.mean()) * (1 - up_r.mean()),
                 hit_if_pred_up=hit[up_p].mean() if up_p.any() else float("nan"), hit_if_pred_down=hit[~up_p].mean() if (~up_p).any() else float("nan"), corr_pred_real=float(np.corrcoef(pr, rr)[0, 1]))
        # çapraz-kesit: ayni e'de coinlerin medyanina gore (yanlilik giderilmis)
        med = {}; 
        for ee in np.unique(d["e"]): m = d["e"] == ee; med[ee] = np.median(pr[m])
        pm = pr - np.array([med[x] for x in d["e"]]); rm = rr - np.array([np.median(rr[d["e"] == x]) for x in d["e"]]) if False else None
        res[h] = r
    # --- 24s strateji
    pr = d["P"][:, 23] / d["lc"] - 1; ret = d["R"][:, 23] / d["o0"] - 1; sgn = np.where(pr > 0, 1, -1); gross = sgn * ret; net = gross - 2 * COST; n_all = len(net)
    strat = {}
    def add(name, x):
        bs_cb = boot_mean(x, blk_cb); bs_d = boot_mean(x, blk_day); ci1, p1 = ci_p(bs_cb, 0.0); ci2, p2 = ci_p(bs_d, 0.0); strat[name] = dict(mean_bp=x.mean() * 1e4, ci_cb_bp=(ci1 * 1e4).tolist(), ci_day_bp=(ci2 * 1e4).tolist(), p_cb=p1, p_day=p2, hit=float((x > 0).mean()))
    add("Kronos yon (net %0,15/taraf)", net); add("Kronos yon (brüt)", gross); add("her zaman long (net)", ret - 2 * COST); add("her zaman short (net)", -ret - 2 * COST)
    rs = rng.choice([-1, 1], (5000, n_all)); rn = (rs * ret).mean(1) - 2 * COST; strat["rastgele yon (net) 5000 sim"] = dict(mean_bp=float(rn.mean() * 1e4), ci_cb_bp=np.percentile(rn * 1e4, [2.5, 97.5]).tolist(), kronos_pct_rank=float((rn < net.mean()).mean()))
    # yanlilik-eslestirilmis rastgele: modelle ayni long orani
    pl = (sgn == 1).mean(); rs2 = np.where(rng.random((5000, n_all)) < pl, 1, -1); rn2 = (rs2 * ret).mean(1) - 2 * COST; strat["rastgele (modelle ayni long orani)"] = dict(mean_bp=float(rn2.mean() * 1e4), ci_cb_bp=np.percentile(rn2 * 1e4, [2.5, 97.5]).tolist(), kronos_pct_rank=float((rn2 < net.mean()).mean()), long_share=float(pl))
    # çapraz kesit: ayni e'de tahmin medyanin ustu -> long, alti -> short (yanlilik giderilmis; EK analiz)
    med = np.array([np.median(pr[d["e"] == x]) for x in d["e"]]); sg2 = np.where(pr > med, 1, -1); g2 = sg2 * ret; n2 = g2 - 2 * COST; add("capraz-kesit (medyan-ustu long/alti short) net", n2); add("capraz-kesit brüt", g2)
    out["h"] = res; out["strat"] = strat; out["frac_long_signals"] = float(pl); out["mean_abs_pred_ret24"] = float(np.abs(pr).mean()); out["mean_abs_real_ret24"] = float(np.abs(ret).mean())
    # coin başına
    pc = []
    for ci, c in enumerate(d["coins"]):
        m = d["coin"] == ci; hit = (((d["P"][m, 23] / d["lc"][m] - 1) > 0) == ((d["R"][m, 23] / d["lc"][m] - 1) > 0)); k = int(hit.sum()); lo, hi = wilson(k, int(m.sum())); pc.append(dict(coin=c, n=int(m.sum()), hit=k / m.sum(), wilson=[lo, hi], pred_up=float(((d["P"][m, 23] / d["lc"][m] - 1) > 0).mean()), real_up=float(((d["R"][m, 23] / d["lc"][m] - 1) > 0).mean()), net_bp=float(net[m].mean() * 1e4), gross_bp=float(gross[m].mean() * 1e4)))
    out["per_coin"] = pc
    # günlük portföy (tüm coinler eşit ağırlık) -> DSR
    nd = out["n_days"]; dm = np.bincount(blk_day, weights=net, minlength=nd) / np.maximum(np.bincount(blk_day, minlength=nd), 1); m_, sd_, sk_, ku_ = O.sr_stats(dm[None, :]); sr = float(m_[0] / sd_[0]); out["daily_portfolio"] = dict(mean_bp=float(dm.mean() * 1e4), sd_bp=float(dm.std() * 1e4), daily_SR=sr, skew=float(sk_[0]), kurt=float(ku_[0]), n_days=nd, PSR=O.dsr(sr, nd, float(sk_[0]), float(ku_[0]), 1.0 / nd, 1))
    return out
def holm(ps, alpha=0.05):
    idx = np.argsort(ps); m = len(ps); rej = [False] * m; adj = [None] * m; run = 0.0
    for r, i in enumerate(idx): run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run; rej[i] = adj[i] < alpha
    return adj, rej
def main(models):
    allo = {}; L = []; P = L.append
    P("# Adım D — Kronos tam test (2026-10-25, UTC+3)\n")
    for mo in models:
        fp = f"{KD}/preds_{mo}.jsonl"
        if not os.path.exists(fp): continue
        d = load(mo); allo[mo] = evaluate(d, mo)
    json.dump(allo, open(f"{KD}/eval.json", "w"), indent=1, default=float)
    ps = []; labs = []
    for mo, o in allo.items():
        for h, r in o["h"].items(): ps.append(max(r["p_hit_vs_half_day"], r["p_hit_vs_half_cb"])); labs.append(f"{mo} yön isabeti h={h}")
        for nm in ("Kronos yon (net %0,15/taraf)", "capraz-kesit (medyan-ustu long/alti short) net"): ps.append(max(o["strat"][nm]["p_cb"], o["strat"][nm]["p_day"])); labs.append(f"{mo} {nm}")
    adj, rej = holm(np.array(ps)) if ps else ([], [])
    for mo, o in allo.items():
        P(f"## Model: Kronos-{mo} — n={o['n']} tahmin, {o['n_coins']} coin × {o['n_days']} gün (24 mum ufuk, her gün 1 çıkış, çakışmasız)")
        P("| ufuk | isabet [CI coin×3g] [CI gün-blok] | p(coin×blok / gün) | tahmin 'yukarı' | gerçek 'yukarı' | hep-long | hep-short | yanlılık-eşleşik rastgele | korelasyon |\n|---|---|---|---|---|---|---|---|---|")
        for h, r in o["h"].items(): P(f"| {h}s | {r['hit']*100:.1f}% [{r['hit_ci_cb'][0]*100:.1f},{r['hit_ci_cb'][1]*100:.1f}] [{r['hit_ci_day'][0]*100:.1f},{r['hit_ci_day'][1]*100:.1f}] | {r['p_hit_vs_half_cb']:.3f} / {r['p_hit_vs_half_day']:.3f} | {r['pred_up']*100:.0f}% | {r['real_up']*100:.0f}% | {r['always_long_hit']*100:.1f}% | {r['always_short_hit']*100:.1f}% | {r['bias_matched_random_hit']*100:.1f}% | {r['corr_pred_real']:+.3f} |")
        P(f"\n24s strateji (taraf başı %0,15; ort |tahmin getirisi| {o['mean_abs_pred_ret24']*100:.2f}%, ort |gerçek| {o['mean_abs_real_ret24']*100:.2f}%; long sinyal payı {o['frac_long_signals']*100:.0f}%):")
        P("| strateji | ort. bp/işlem | CI coin×3g | CI gün-blok | p (cb/gün) | rastgele içindeki yüzdelik |\n|---|---|---|---|---|---|")
        for nm, s in o["strat"].items():
            if "ci_day_bp" in s: P(f"| {nm} | {s['mean_bp']:+.1f} | [{s['ci_cb_bp'][0]:+.1f},{s['ci_cb_bp'][1]:+.1f}] | [{s['ci_day_bp'][0]:+.1f},{s['ci_day_bp'][1]:+.1f}] | {s['p_cb']:.3f}/{s['p_day']:.3f} | - |")
            else: P(f"| {nm} | {s['mean_bp']:+.1f} | rastgele %95 [{s['ci_cb_bp'][0]:+.1f},{s['ci_cb_bp'][1]:+.1f}] | - | - | Kronos > rastgelenin %{s['kronos_pct_rank']*100:.0f}'ünden |")
        dp = o["daily_portfolio"]; P(f"\nGünlük eşit-ağırlık portföy (net): ort {dp['mean_bp']:+.1f} bp/gün, sd {dp['sd_bp']:.1f}, günlük SR {dp['daily_SR']:+.3f} (yıllık ≈ {dp['daily_SR']*math.sqrt(365):+.1f}), PSR(0)={dp['PSR']:.3f}, {dp['n_days']} gün.\n")
        P("Coin başına (24s yön isabeti; Wilson %95; net bp = %0,15/taraf sonrası):\n\n| coin | n | isabet [Wilson] | tahmin↑ | gerçek↑ | brüt bp | net bp |\n|---|---|---|---|---|---|---|")
        for c in o["per_coin"]: P(f"| {c['coin']} | {c['n']} | {c['hit']*100:.0f}% [{c['wilson'][0]*100:.0f},{c['wilson'][1]*100:.0f}] | {c['pred_up']*100:.0f}% | {c['real_up']*100:.0f}% | {c['gross_bp']:+.0f} | {c['net_bp']:+.0f} |")
        P("")
    if ps:
        P("## Çoklu test düzeltmesi (Holm-Bonferroni; aile = bu raporda bakılan testler)\n| test | p (tutucu: iki bootstrap'ın büyüğü) | Holm düzeltilmiş p | reddedildi (α=0,05) |\n|---|---|---|---|")
        for l, p, a, r in zip(labs, ps, adj, rej): P(f"| {l} | {p:.3f} | {a:.3f} | {'EVET' if r else 'hayır'} |")
    open(f"{HERE}/outputs/research_D_kronos.md", "w").write("\n".join(L) + "\n"); print("\n".join(L[:60]))
if __name__ == "__main__": main(sys.argv[1:] or ["small", "mini"])
