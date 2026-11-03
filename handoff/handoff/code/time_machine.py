#!/usr/bin/env python3
"""time_machine.py — ÖZGÜN uygulama (hiçbir hazır koddan kopya yok). Fikir: bir sinyalin hedef/stop vuruş oranını, o coinin KENDİ yakın mumlarından
bootstrap ile ürettiğimiz "sinyalsiz rastgele yürüyüş" dünyasıyla kıyasla. Sinyalin gerçek vuruş oranı bu sıfır-modelin üstünde değilse "kenar" yoktur.
  * Havuz: giriş anından önceki N kapanmış mum; her mum, önceki kapanışa oranlarla (o,h,l,c)/pc-1 saklanır (fiyat seviyesinden bağımsız).
  * Yol: giriş fiyatından başlayıp H mum boyunca blok-bootstrap ile mum örnekle; aynı mumda stop ve hedef birlikte vurulursa STOP önce sayılır (muhafazakâr).
  * Yön: short için ayna. Stop = S*ATR14, Hedef = T*ATR14 (ATR giriş öncesi mumlardan). R=T/S. Başabaş vuruş oranı = 1/(1+R) (maliyetsiz); maliyet dahil: (1+c)/(1+R) civarı.
  * --demean: havuzdaki ortalama sürüklenmeyi çıkarır (son dönem trendi sinyale "bedava" kenar yazmasın).
Alt komutlar:
  python3 time_machine.py signals  [--signals outputs/signal_paper/signals.csv --outcomes outputs/signal_paper/outcomes.csv]   # gerçek sinyal logunu test et (Gate public)
  python3 time_machine.py calib    [--n 400]                                                                                  # kalibrasyon: öngörülen vuruş oranı gerçekle uyuşuyor mu (rastgele girişler, OKX verisi)
  python3 time_machine.py one --coin ARB --dir 1 --entry-epoch 1792880100 --horizon 16
"""
import os, sys, json, time, math, argparse, glob
import numpy as np, pandas as pd, requests
HERE = os.path.dirname(os.path.abspath(__file__)); STEP = 900
GATE = "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"

def gate_candles(coin, n=2000, interval="15m", to=None):
    p = {"contract": f"{coin}_USDT", "interval": interval, "limit": n}
    if to: p["to"] = int(to)
    r = requests.get(GATE, params=p, timeout=25); r.raise_for_status()
    d = pd.DataFrame(r.json()); d["t"] = d["t"].astype(int)
    for c in "ohlcv": d[c] = d[c].astype(float)
    return d.sort_values("t").reset_index(drop=True)[["t", "o", "h", "l", "c", "v"]]

def atr14(d):
    pc = d.c.shift(); tr = pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])

def make_pool(hist, demean=True):
    """hist: kapanmış mumlar (giriş öncesi). -> (K,4) oranlar [o,h,l,c]/pc-1"""
    pc = hist.c.shift().values[1:]; a = np.stack([hist.o.values[1:] / pc - 1, hist.h.values[1:] / pc - 1, hist.l.values[1:] / pc - 1, hist.c.values[1:] / pc - 1], 1)
    if demean: a = a - a[:, 3].mean()
    return a

def simulate(pool, entry, d, atr, S, T, H, M=2000, block=4, seed=0, cost_bp=10.0):
    """M bootstrap yolu. Dönen: p_target, p_stop, p_timeout, EV_gross_R, EV_net_R, breakeven (maliyetsiz), breakeven_net"""
    rng = np.random.default_rng(seed); K = len(pool)
    stop = entry - d * S * atr; tgt = entry + d * T * atr
    price = np.full(M, entry); alive = np.ones(M, bool); res = np.zeros(M); code = np.zeros(M, int); cum_t = []; cum_s = []   # 1 hedef, -1 stop, 0 zaman aşımı
    nb = int(math.ceil(H / block)); starts = rng.integers(0, max(1, K - block + 1), size=(M, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(M, -1)[:, :H] % K
    for k in range(H):
        r = pool[idx[:, k]]
        o = price * (1 + (0.0 if k == 0 else r[:, 0])); h = price * (1 + np.maximum(r[:, 1], np.maximum(r[:, 0], r[:, 3]) if k else r[:, 1])); l = price * (1 + np.minimum(r[:, 2], np.minimum(r[:, 0], r[:, 3]) if k else r[:, 2])); c = price * (1 + r[:, 3])
        if k == 0: o = np.full(M, entry); h = np.maximum(h, o); l = np.minimum(l, o)
        hit_s = (l <= stop) if d == 1 else (h >= stop); hit_t = (h >= tgt) if d == 1 else (l <= tgt)
        new_s = alive & hit_s; new_t = alive & hit_t & ~hit_s
        code[new_s] = -1; code[new_t] = 1; alive &= ~(new_s | new_t); price = c
        cum_t.append(float((code == 1).mean())); cum_s.append(float((code == -1).mean()))   # k. muma kadar kümülatif ilk-vuruş olasılığı
    res = np.where(code == 1, T, np.where(code == -1, -S, d * (price - entry) / (S * atr) * S))   # zaman aşımı: kapanışta çık (R birimi = stop mesafesi)
    res = res / S
    R = T / S; c_R = (cost_bp / 1e4) * entry / (S * atr)       # tur maliyeti, R cinsinden
    return {"p_target": float((code == 1).mean()), "p_stop": float((code == -1).mean()), "p_timeout": float((code == 0).mean()),
            "cum_t": cum_t, "cum_s": cum_s, "EV_gross_R": float(res.mean()), "EV_net_R": float(res.mean() - c_R), "breakeven": 1 / (1 + R), "breakeven_net": (1 + c_R) / (1 + R), "cost_R": c_R}

def realized(fwd, entry, d, atr, S, T, H):
    """Gerçek ileri mumlarda aynı kural. -> (code, bars_used) code: 1/-1/0(zaman aşımı, H mum doldu)/None(henüz belirsiz)"""
    stop = entry - d * S * atr; tgt = entry + d * T * atr
    for k, (h, l) in enumerate(zip(fwd.h.values[:H], fwd.l.values[:H])):
        hs = (l <= stop) if d == 1 else (h >= stop); ht = (h >= tgt) if d == 1 else (l <= tgt)
        if hs: return -1, k + 1
        if ht: return 1, k + 1
    return (0, H) if len(fwd) >= H else (None, len(fwd))

def pbin_pvalue(ps, k, upper=True, n=20000, seed=1):
    """Poisson-binomial: P(X >= k) (upper) ya da P(X <= k), simülasyonla."""
    rng = np.random.default_rng(seed); ps = np.asarray(ps); X = (rng.random((n, len(ps))) < ps[None, :]).sum(1)
    return float((X >= k).mean() if upper else (X <= k).mean())

def pctile_return(pool, entry, d, atr_unused, H, M=4000, seed=3, block=4):
    """H mumluk kapanış getirisinin (yön ayarlı, bp) bootstrap dağılımı."""
    rng = np.random.default_rng(seed); K = len(pool); nb = int(math.ceil(H / block)); st = rng.integers(0, max(1, K - block + 1), size=(M, nb))
    idx = (st[:, :, None] + np.arange(block)[None, None, :]).reshape(M, -1)[:, :H] % K
    lr = np.log1p(pool[idx, 3]).sum(1); return d * (np.exp(lr) - 1) * 1e4

def cmd_signals(a):
    sig = pd.read_csv(a.signals); out = pd.read_csv(a.outcomes) if os.path.exists(a.outcomes) else pd.DataFrame()
    sig = sig[sig.entry_px.notna() & (sig.entry_px != "")].copy(); sig["entry_px"] = sig.entry_px.astype(float)
    n_raw = len(sig); sig = sig.drop_duplicates(subset=["coin", "dir", "entry_bar_t"]); n_dedup = len(sig)   # aynı coin/yön/giriş mumu = aynı sonuç, iki kez sayılmasın
    rows = []; cache = {}
    for _, s in sig.iterrows():
        coin = s.coin
        if coin not in cache:
            try: cache[coin] = gate_candles(coin, 2000)
            except Exception as e: cache[coin] = None; print("fetch hata", coin, str(e)[:80])
            time.sleep(0.12)
        cd = cache[coin]
        if cd is None: continue
        et = int(s.entry_bar_t); hist = cd[cd.t < et].tail(a.pool + 1); fwd = cd[cd.t >= et].reset_index(drop=True)
        if len(hist) < 200: continue
        pool = make_pool(hist, a.demean); atr = atr14(hist.tail(200)); d = int(s.dir)
        sim = simulate(pool, float(s.entry_px), d, atr, a.stop, a.target, a.horizon, M=a.paths, block=a.block, seed=a.seed, cost_bp=a.cost_bp)
        fwd = fwd[fwd.t + STEP <= time.time() - 5].reset_index(drop=True)      # henüz kapanmamış mumu at
        code, used = realized(fwd, float(s.entry_px), d, atr, a.stop, a.target, a.horizon); kk = min(a.horizon, len(fwd))
        if kk < 1: continue
        # Seçilim yanlılığını önlemek için BEKLENEN değer, gerçekte gözlenen pencere (kk mum) için hesaplanır; erken vuranları tek başına saymak yanıltır
        rows.append(dict(sig_id=s.sig_id, coin=coin, signal=s.signal, w=s.w, dir=d, atr_pct=round(atr / float(s.entry_px) * 100, 3), real_t=int(code == 1), real_s=int(code == -1), kk=kk,
                         exp_t=sim["cum_t"][kk - 1], exp_s=sim["cum_s"][kk - 1], **{k: round(v, 4) for k, v in sim.items() if k not in ("cum_t", "cum_s")}))
    R = pd.DataFrame(rows); res = {"params": {k: v for k, v in vars(a).items() if k != "f"} | {"cmd": "signals"}, "n_signals": int(len(R))}
    if len(R):
        rs = R; res["observed_window_mean_bars"] = round(float(R.kk.mean()), 1); res["full_horizon_bars"] = a.horizon
        res["breakeven_no_cost"] = round(1 / (1 + a.target / a.stop), 4); res["breakeven_with_cost_mean"] = round(float(R.breakeven_net.mean()), 4)
        res["bootstrap_mean_p_target_full_horizon"] = round(float(R.p_target.mean()), 4); res["bootstrap_mean_p_stop_full_horizon"] = round(float(R.p_stop.mean()), 4); res["bootstrap_mean_EV_net_R"] = round(float(R.EV_net_R.mean()), 4)
        kt = int(rs.real_t.sum()); ks = int(rs.real_s.sum()); res["observed_real_target_hits"] = kt; res["observed_real_stop_hits"] = ks
        res["expected_target_hits_under_null_same_window"] = round(float(rs.exp_t.sum()), 2); res["expected_stop_hits_under_null_same_window"] = round(float(rs.exp_s.sum()), 2)
        res["p_value_target_ge_null"] = round(pbin_pvalue(rs.exp_t.values, kt, True), 4); res["p_value_stop_le_null"] = round(pbin_pvalue(rs.exp_s.values, ks, False), 4)
        res["n_rows_in_csv_with_entry"] = n_raw; res["n_after_dedupe_coin_dir_entrybar"] = n_dedup
        r1 = R.drop_duplicates(subset=["coin"]); k1t = int(r1.real_t.sum()); k1s = int(r1.real_s.sum())
        res["one_signal_per_coin"] = {"n": int(len(r1)), "real_target": k1t, "exp_target": round(float(r1.exp_t.sum()), 2), "p_target": round(pbin_pvalue(r1.exp_t.values, k1t, True), 4),
                                      "real_stop": k1s, "exp_stop": round(float(r1.exp_s.sum()), 2), "p_stop_le": round(pbin_pvalue(r1.exp_s.values, k1s, False), 4)}
        res["share_long"] = round(float((R.dir == 1).mean()), 2)
        res["note"] = "Pencere = sinyalden bu yana GÖZLENEN mum sayısı (<= ufuk). Sinyaller üst üste biniyor (aynı coin/zaman) -> bağımsız değil; p-değerleri iyimser."
        # sabit-ufuk testi: outcomes.csv (1h/4h/12h net/gross bp) bootstrap null yüzdelik dilimine karşı
        pr = []
        if len(out):
            for _, o in out.iterrows():
                coin = o.coin; cd = cache.get(coin)
                if cd is None or o.horizon not in ("1h", "4h", "12h"): continue
                H = {"1h": 4, "4h": 16, "12h": 48}[o.horizon]; et = int(o.exit_bar_t) - H * STEP  # exit_bar_t = çıkış mumu başlangıcı
                hist = cd[cd.t < et].tail(a.pool + 1)
                if len(hist) < 200: continue
                pool = make_pool(hist, a.demean); null = pctile_return(pool, float(o.entry_px), int(o.dir), 0, H, seed=a.seed)
                pr.append(dict(sig_id=o.sig_id, horizon=o.horizon, gross_bp=float(o.gross_bp), pct=float((null < float(o.gross_bp)).mean()), null_sd_bp=float(null.std())))
        if pr:
            P = pd.DataFrame(pr)
            from statistics import NormalDist
            z = float(np.sum([NormalDist().inv_cdf(min(max(p, 1e-3), 1 - 1e-3)) for p in P.pct]) / math.sqrt(len(P)))
            res["fixed_horizon"] = {"n": int(len(P)), "mean_gross_bp": round(float(P.gross_bp.mean()), 2), "mean_null_percentile": round(float(P.pct.mean()), 3), "stouffer_z": round(z, 2),
                                    "mean_null_sd_bp": round(float(P.null_sd_bp.mean()), 1), "note": "yüzdelik 0.5 = sıfır modelle aynı; >0.5 sinyal sıfırdan iyi"}
            res["fixed_horizon_rows"] = P.round(3).to_dict("records")
    res["rows"] = R.to_dict("records"); json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    keys = [k for k in res if k not in ("rows", "fixed_horizon_rows", "params")]; print(json.dumps({k: res[k] for k in keys}, ensure_ascii=False, indent=1)); print("->", a.out)

def okx_5m(coin):
    f = glob.glob(os.path.join(HERE, "freqtrade_xcheck/user_data/data/okx/futures", f"{coin}_USDT_USDT-5m-futures.feather"))
    if not f: return None
    x = pd.read_feather(f[0]).set_index("date")[["open", "high", "low", "close", "volume"]].rename(columns=dict(open="o", high="h", low="l", close="c", volume="v"))
    r = x.resample("15min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}); n = x.c.resample("15min").count(); r = r[n == 3].dropna()
    r["t"] = ((r.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype(int); return r.reset_index(drop=True)[["t", "o", "h", "l", "c", "v"]]

def cmd_calib(a):
    """Kalibrasyon: rastgele giriş/yön; bootstrap p_target ile gerçek (ileri mum) hedef vuruşu karşılaştır. Aracın kendi doğruluk testi."""
    rng = np.random.default_rng(a.seed); rows = []
    coins = sorted({os.path.basename(f).split("_USDT")[0] for f in glob.glob(os.path.join(HERE, "freqtrade_xcheck/user_data/data/okx/futures/*-5m-futures.feather"))})
    for coin in coins:
        d = okx_5m(coin)
        if d is None or len(d) < 2000: continue
        for _ in range(a.n):
            i = int(rng.integers(a.pool + 1, len(d) - a.horizon - 1)); hist = d.iloc[i - a.pool:i]; fwd = d.iloc[i:i + a.horizon + 1].reset_index(drop=True)
            if (fwd.t.diff().dropna() != STEP).any(): continue
            pool = make_pool(hist, a.demean); atr = atr14(hist.tail(200)); dr = int(rng.choice([-1, 1])); entry = float(fwd.o.iloc[0])
            sim = simulate(pool, entry, dr, atr, a.stop, a.target, a.horizon, M=a.paths, block=a.block, seed=int(rng.integers(1e9)), cost_bp=a.cost_bp)
            code, used = realized(fwd, entry, dr, atr, a.stop, a.target, a.horizon)
            if code is None: continue
            rows.append(dict(coin=coin, p_target=sim["p_target"], p_stop=sim["p_stop"], real_t=int(code == 1), real_s=int(code == -1), ev=sim["EV_net_R"]))
    R = pd.DataFrame(rows); res = {"params": {k: v for k, v in vars(a).items() if k != "f"} | {"cmd": "calib"}, "n": int(len(R)), "mean_pred_p_target": round(float(R.p_target.mean()), 4), "mean_real_target": round(float(R.real_t.mean()), 4),
                                    "mean_pred_p_stop": round(float(R.p_stop.mean()), 4), "mean_real_stop": round(float(R.real_s.mean()), 4), "breakeven": round(1 / (1 + a.target / a.stop), 4)}
    R["bin"] = pd.qcut(R.p_target, 5, duplicates="drop"); g = R.groupby("bin", observed=True).agg(pred=("p_target", "mean"), real=("real_t", "mean"), n=("real_t", "size"))
    res["bins"] = [{"pred": round(r.pred, 4), "real": round(r.real, 4), "n": int(r.n)} for r in g.itertuples()]
    res["brier_target"] = round(float(((R.p_target - R.real_t) ** 2).mean()), 4); res["brier_baseline_const"] = round(float(((R.real_t.mean() - R.real_t) ** 2).mean()), 4)
    res["per_coin"] = R.groupby("coin").agg(pred=("p_target", "mean"), real=("real_t", "mean"), n=("real_t", "size")).round(4).reset_index().to_dict("records")
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1); print(json.dumps({k: v for k, v in res.items() if k != "per_coin"}, ensure_ascii=False, indent=1)); print("->", a.out)

def cmd_one(a):
    cd = gate_candles(a.coin, 2000); hist = cd[cd.t < a.entry_epoch].tail(a.pool + 1); fwd = cd[cd.t >= a.entry_epoch].reset_index(drop=True)
    pool = make_pool(hist, a.demean); atr = atr14(hist.tail(200)); entry = float(fwd.o.iloc[0]) if len(fwd) else float(hist.c.iloc[-1])
    print(json.dumps({"entry": entry, "atr": atr, **simulate(pool, entry, a.dir, atr, a.stop, a.target, a.horizon, M=a.paths, block=a.block, seed=a.seed, cost_bp=a.cost_bp), "real": realized(fwd, entry, a.dir, atr, a.stop, a.target, a.horizon)}, indent=1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
    def common(p):
        p.add_argument("--pool", type=int, default=960, help="havuz: giriş öncesi kapanmış 15m mum sayısı (960 = 10 gün)"); p.add_argument("--stop", type=float, default=1.5); p.add_argument("--target", type=float, default=3.0)
        p.add_argument("--horizon", type=int, default=16, help="max mum (15m); 16 = 4s"); p.add_argument("--paths", type=int, default=2000); p.add_argument("--block", type=int, default=4); p.add_argument("--seed", type=int, default=11)
        p.add_argument("--cost-bp", type=float, default=10.0); p.add_argument("--no-demean", dest="demean", action="store_false"); p.set_defaults(demean=True)
    p = sp.add_parser("signals"); common(p); p.add_argument("--signals", default=os.path.join(HERE, "outputs/signal_paper/signals.csv")); p.add_argument("--outcomes", default=os.path.join(HERE, "outputs/signal_paper/outcomes.csv")); p.add_argument("--out", default=os.path.join(HERE, "outputs/time_machine_signals.json")); p.set_defaults(f=cmd_signals)
    p = sp.add_parser("calib"); common(p); p.add_argument("--n", type=int, default=300); p.add_argument("--out", default=os.path.join(HERE, "outputs/time_machine_calib.json")); p.set_defaults(f=cmd_calib)
    p = sp.add_parser("one"); common(p); p.add_argument("--coin", required=True); p.add_argument("--dir", type=int, required=True); p.add_argument("--entry-epoch", type=int, required=True); p.set_defaults(f=cmd_one)
    a = ap.parse_args(); a.f(a)
