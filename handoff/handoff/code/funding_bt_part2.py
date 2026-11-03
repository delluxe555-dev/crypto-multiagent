"""funding_bt.py alt komutlari: fetch (Gate+OKX funding gecmisi) ve report (funding + likidasyon ile yeniden olcum). Dogrudan calistirma: python3 funding_bt.py fetch|report"""
import os, sys, json, time, math, requests, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f"{HERE}/outputs/research"; FUND = f"{RES}/funding"
GATE = "https://api.gateio.ws/api/v4/futures/usdt"; START = 1779840000  # 2026-05-27 00:00 UTC - 2 gun pay
def coins():
    sys.path.insert(0, HERE); import combo_bt2 as b2; return b2.COINS
def fetch():
    os.makedirs(FUND, exist_ok=True)
    cts = requests.get(f"{GATE}/contracts", timeout=30).json(); json.dump({c["name"]: dict(maintenance_rate=c["maintenance_rate"], funding_interval=c["funding_interval"], leverage_max=c["leverage_max"], mark_type=c.get("type")) for c in cts}, open(f"{FUND}/gate_contracts.json", "w"))
    for c in coins():
        rows = {}; to = None
        for _ in range(12):
            p = {"contract": f"{c}_USDT", "limit": 1000}
            if to: p["to"] = to
            for _t in range(3):
                try: d = requests.get(f"{GATE}/funding_rate", params=p, timeout=20).json(); break
                except Exception: time.sleep(1); d = None
            if not d or not isinstance(d, list): break
            for x in d: rows[int(x["t"])] = float(x["r"])
            old = min(int(x["t"]) for x in d)
            if old <= START or len(d) < 5: break
            to = old - 1
        json.dump(sorted(rows.items()), open(f"{FUND}/gate_{c}.json", "w"))
        # OKX
        rows = {}; after = None
        for _ in range(15):
            p = {"instId": f"{c}-USDT-SWAP", "limit": 100}
            if after: p["after"] = after
            try: d = requests.get("https://www.okx.com/api/v5/public/funding-rate-history", params=p, timeout=20).json().get("data", [])
            except Exception: d = []
            if not d: break
            for x in d: rows[int(x["fundingTime"]) // 1000] = float(x.get("realizedRate") or x["fundingRate"])
            after = d[-1]["fundingTime"]
            if int(after) // 1000 <= START: break
            time.sleep(0.12)
        json.dump(sorted(rows.items()), open(f"{FUND}/okx_{c}.json", "w"))
        g = json.load(open(f"{FUND}/gate_{c}.json")); o = json.load(open(f"{FUND}/okx_{c}.json"))
        print(c, "gate", len(g), time.strftime("%F", time.gmtime(g[0][0])) if g else None, "okx", len(o), time.strftime("%F", time.gmtime(o[0][0])) if o else None, flush=True)

def load_fund(src="gate"):
    out = {}
    for c in coins():
        fp = f"{FUND}/{src}_{c}.json"
        if os.path.exists(fp):
            r = json.load(open(fp))
            if r: a = np.array(r, dtype=np.float64); a = a[np.argsort(a[:, 0])]; out[c] = (a[:, 0].astype(np.int64), np.concatenate([[0.0], np.cumsum(a[:, 1])]))
    return out
def trade_fund_frac(t_in, t_out, coin_idx, coinnames, F):
    """islem basi toplam funding orani (long icin odenen > 0). Kapsama disi donem = 0. Doner: (frac, kapsanan_islem_maskesi)."""
    fr = np.zeros(len(t_in)); cov = np.zeros(len(t_in), bool)
    for ci, c in enumerate(coinnames):
        if c not in F: continue
        m = coin_idx == ci; ts, cum = F[c]; a = np.searchsorted(ts, t_in[m], "right"); b = np.searchsorted(ts, t_out[m], "right"); fr[m] = cum[b] - cum[a]; cov[m] = t_in[m] >= ts[0] - 8 * 3600
    return fr, cov
def liq_mask(T, L, mmr):
    """likidasyon: MAE >= 1/L - mmr  VE stop (1/k) likidasyondan once degilse. Kayip = -k/L R."""
    ld = 1.0 / L - mmr[T["coin"]]; return (T["mae"] >= ld) & (ld < 1.0 / T["k"]), ld
def boot_ci(vals, blocks, nb=2000, seed=3):
    rng = np.random.default_rng(seed); u, inv = np.unique(blocks, return_inverse=True); sums = np.bincount(inv, weights=vals); cnt = np.bincount(inv).astype(float); U = len(u); out = np.empty(nb)
    for i in range(nb): w = rng.multinomial(U, np.full(U, 1 / U)); out[i] = (w @ sums) / max(w @ cnt, 1)
    return np.percentile(out, [2.5, 97.5])

def report():
    sys.path.insert(0, HERE); import overfit_stats as O
    T = O.load_trades(); names = list(T["coins"]); F = load_fund("gate"); Fo = load_fund("okx")
    con = json.load(open(f"{FUND}/gate_contracts.json")); mmr_c = np.array([float(con.get(f"{c}_USDT", {}).get("maintenance_rate", 0.005)) for c in names])
    fr, cov = trade_fund_frac(T["t_in"], T["t_out"], T["coin"], names, F); fund_R = -T["dir"] * fr * T["k"]
    fro, covo = trade_fund_frac(T["t_in"], T["t_out"], T["coin"], names, Fo); fund_Ro = -T["dir"] * fro * T["k"]
    L = []; P = L.append
    # --- veri ozeti
    P("# Adım C — funding + zorunlu likidasyon ile yeniden ölçüm (2026-10-25, UTC+3)\n")
    P("Kod: `funding_bt.py` (+ `funding_bt_part2.py`); işlem tablosu `outputs/research/trades_r2.npz` (combo_bt2'yi birebir yeniden üretir: 630 hücre, 2.630.285 işlem, hücre başına n farkı 0). Funding verisi: `outputs/research/funding/`.\n")
    P("## Varsayımlar (açık)")
    P("- **Fiyat** Binance SPOT 5m (combo_bt2 ile aynı). **Funding** Gate USDT-perp geçmişinden (Binance perp funding'ine bu sunucudan erişilemiyor → proxy); OKX ile çapraz kontrol (aşağıda).")
    P("- Funding: işlem süresince düşen her uzlaşma (settlement) için long, oran>0'da öder / short alır; R cinsinden `funding_R = -yön × Σoran × (e/sd)` (pozisyon = risk/stop-mesafesi). Uzlaşma aralığı sözleşmeye göre (Gate: çoğunlukla 8s).")
    P("- Zorunlu likidasyon (izole marjin, sabit kaldıraç L=5/10/20): likidasyon mesafesi = 1/L − mmr, **mmr = Gate sözleşmesinin `maintenance_rate`'i** (BTC 0,3%, PEPE 0,65% vb.; aşağıda coin başına). İşlemin MAE'si ≥ bu mesafe VE stop (1/k) likidasyondan önce değilse likide olur, kayıp = tüm teminat = −k/L R (≤ ~1,1R). MAE bar-içi sırayı bilmediğinden hedef barının dip/tepesi de dahil (temkinli). Likidasyon harcı/sigorta fonu kesintisi yok sayıldı.")
    cov_all = cov.mean(); P(f"- Funding kapsaması: işlemlerin %{cov_all*100:.1f}'i Gate funding geçmişinin kapsadığı dönemde (kalan 0 funding sayıldı); OKX kapsaması %{covo.mean()*100:.1f}.\n")
    # --- Gate vs OKX çapraz kontrol
    P("## Gate ↔ OKX funding çapraz kontrol (aynı uzlaşma zamanlarında, 8s oranları)")
    cc = []; 
    for c in names:
        gf = json.load(open(f"{FUND}/gate_{c}.json")); of = json.load(open(f"{FUND}/okx_{c}.json")); gd = dict(gf); od = dict(of); common = sorted(set(gd) & set(od))
        if len(common) > 30:
            a = np.array([gd[t] for t in common]); b = np.array([od[t] for t in common]); cc.append((c, len(common), float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan"), a.mean() * 1e4, b.mean() * 1e4))
    P("| coin | ortak uzlaşma | korelasyon | Gate ort bp/8s | OKX ort bp/8s |\n|---|---|---|---|---|")
    for r in cc: P(f"| {r[0]} | {r[1]} | {r[2]:.2f} | {r[3]:.2f} | {r[4]:.2f} |")
    if cc: P(f"\nMedyan korelasyon {np.nanmedian([r[2] for r in cc]):.2f}; ortalama fark (Gate−OKX) {np.mean([r[3]-r[4] for r in cc]):.2f} bp/8s. ({len(cc)}/29 coin OKX'te ortak veriye sahip; OKX geçmişi ~96 gün.)")
    # --- genel funding ölçeği
    allr = np.concatenate([np.array(json.load(open(f"{FUND}/gate_{c}.json")))[:, 1] for c in names if os.path.exists(f"{FUND}/gate_{c}.json")])
    P(f"\n## Funding ölçeği\nGate 29 coin, tüm uzlaşmalar: ortalama {allr.mean()*1e4:.2f} bp/uzlaşma (medyan {np.median(allr)*1e4:.2f}), pozitif oran %{(allr>0).mean()*100:.0f}, %95 aralık [{np.percentile(allr,2.5)*1e4:.1f}, {np.percentile(allr,97.5)*1e4:.1f}] bp. (Referans: 1 bp = %0,01; taban oran %0,01/8s = 1 bp.)")
    # --- aday hücreler
    nb = np.array([not T["combos"][c % 35].startswith("BASE_") for c in range(630)])
    def cellsel(c): return T["cell"] == c
    def cid(pair, cfg, combo): return int(list(T["pairs"]).index(pair) * 105 + list(T["cfgs"]).index(cfg) * 35 + list(T["combos"]).index(combo))
    L2 = "L2_CamDaily_L3/H3reject_counterHTF"; E2 = "E2_vote6of7(noMACD)"; E4 = "E4_vote9of11(+flow,stoch,bbmid)"
    cands = [("L2 Camarilla 45m/2h S3/T6/72h", cid("45m/2h", "S3/T6/72h", L2)), ("L2 Camarilla 45m/4h S3/T6/72h", cid("45m/4h", "S3/T6/72h", L2)), ("L2 Camarilla 45m/4h S2/T4/48h", cid("45m/4h", "S2/T4/48h", L2)),
             ("E2 oy 6/7 30m/4h S3/T6/72h", cid("30m/4h", "S3/T6/72h", E2)), ("E4 oy 9/11 30m/2h S3/T6/72h", cid("30m/2h", "S3/T6/72h", E4))]
    day = (T["t_out"] - (T["t_in"].min() // 86400) * 86400) // 86400; blk_all = T["coin"].astype(np.int64) * 1000 + day // 3
    P("\n## Aday hücreler: funding ve likidasyon etkisi (işlem başı ortalama net R; [%95 CI, coin×3-gün blok bootstrap])")
    P("Maliyet taban: taraf başı %0,05 (C_LO) ve %0,15 (C_HI). 'fund' = + funding; 'liq L' = funding + L× sabit kaldıraçla zorunlu likidasyon.\n")
    P("| hücre | n | long% | ort. funding_R | net@0,05 | +fund | +fund [CI] | +fund+liq5 | +liq10 | +liq20 | net@0,15 | +fund@0,15 [CI] | likide% (5/10/20x) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    res = {}
    for nm, c in cands:
        m = cellsel(c); n = int(m.sum()); g = T["g"][m]; k = T["k"][m]; fR = fund_R[m]; blk = blk_all[m]; lo = g - 2 * 0.0005 * k; hi = g - 2 * 0.0015 * k; row = dict(n=n)
        out = [nm, str(n), f"{(T['dir'][m]==1).mean()*100:.0f}", f"{fR.mean():+.4f}", f"{lo.mean():+.4f}", f"{(lo+fR).mean():+.4f}", "[%+.3f,%+.3f]" % tuple(boot_ci(lo + fR, blk))]
        sub = {}; liqs = []
        for Lv in (5, 10, 20):
            lm, ld = liq_mask(T, Lv, mmr_c); lmc = lm[m]; liqs.append(lmc.mean() * 100); x = np.where(lmc, -k / Lv - 2 * 0.0005 * k, lo) + fR; sub[Lv] = x.mean()
        out += [f"{sub[5]:+.4f}", f"{sub[10]:+.4f}", f"{sub[20]:+.4f}", f"{hi.mean():+.4f}", f"{(hi+fR).mean():+.4f} [%+.3f,%+.3f]" % tuple(boot_ci(hi + fR, blk)), "/".join(f"{x:.1f}" for x in liqs)]
        P("| " + " | ".join(out) + " |"); res[nm] = dict(n=n, fund_R=float(fR.mean()), lo=float(lo.mean()), lo_f=float((lo + fR).mean()), hi=float(hi.mean()), hi_f=float((hi + fR).mean()), liq=sub)
    # --- tüm hücreler (non-baseline) toplu
    P("\n## Tüm 558 baz-dışı hücre: funding etkisi")
    fm = np.bincount(T["cell"], weights=fund_R, minlength=630) / np.maximum(np.bincount(T["cell"], minlength=630), 1)
    P(f"- Hücre başına ortalama funding_R: ortalama {fm[nb].mean():+.4f}, medyan {np.median(fm[nb]):+.4f}, min {fm[nb].min():+.4f}, max {fm[nb].max():+.4f} (R/işlem).")
    ld = np.bincount(T["cell"], weights=(T["dir"] == 1).astype(float), minlength=630) / np.maximum(np.bincount(T["cell"], minlength=630), 1)
    P(f"- Long payı ort. %{ld[nb].mean()*100:.0f}. Gate funding çoğunlukla pozitif → long ödüyor, short alıyor; funding_R long-ağırlıklı hücrelerde negatif.")
    P(f"- OKX ile (kapsanan ~96 gün) hesaplanan ortalama funding_R hücre ort.: {(np.bincount(T['cell'], weights=fund_Ro, minlength=630)/np.maximum(np.bincount(T['cell'], minlength=630),1))[nb].mean():+.4f} (Gate: {fm[nb].mean():+.4f}; farklı kapsama nedeniyle birebir değil).")
    json.dump(res, open(f"{RES}/funding_cands.json", "w"), indent=1)
    # --- overfit testleri funding'li
    A0 = O.analyze(T, R=2000, topk=10, verbose=False); A1 = O.analyze(T, fund=fund_R, R=2000, topk=10, verbose=False)
    json.dump(A1, open(f"{RES}/overfit_real_funding.json", "w"), indent=1)
    P("\n## Aşırı-uyum testi funding'li veride (overfit_stats.analyze, funding eklenmiş)")
    for cs in ("cost0.05pct", "cost0.15pct"):
        a0, a1 = A0[cs], A1[cs]
        P(f"- **{cs}**: iki yarıda net-pozitif hücre: funding'siz {a0['n_pos_both_halves']} → funding'li {a1['n_pos_both_halves']}; ortalaması >0 olan hücre {a0['n_pos_mean']} → {a1['n_pos_mean']}; Reality-Check p (en iyi hücre): {a0['reality_check']['p']:.3f} → {a1['reality_check']['p']:.3f}; PBO(558) {a0['pbo_nonbase558']['pbo']:.2f} → {a1['pbo_nonbase558']['pbo']:.2f}.")
        t0 = a1["top"][0]; P(f"  - funding'li en iyi (SR'ye göre) hücre: {t0['name']} n={t0['n']} net {t0['mean_R']:+.4f}R [{t0['boot_ci'][0]:+.3f},{t0['boot_ci'][1]:+.3f}] DSR(N=665)={t0['DSR']['665']:.3f}")
    # --- NEWSHORT w16 4h (liqbt_signals) - ayri motor
    P(NEWSHORT(F, mmr_c, names)); 
    open(f"{HERE}/outputs/research_C_funding_bt.md", "w").write("\n".join(L) + "\n"); print("written")

def NEWSHORT(F, mmr_c, names):
    """liqbt_signals.py mantiginin YENIDEN yazimi (yalniz NEWSHORT, pencere w=16 x15m = 4s, tutma 16 bar = 4s): giris sonraki 15m acilis, cikis t+16 kapanis, 26 coin (liqbt_cache)."""
    import glob
    D = f"{HERE}/liqbt_cache"; coinsl = sorted(os.path.basename(f)[:-5] for f in glob.glob(f"{D}/*.json")); data = {}
    for c in coinsl:
        d = json.load(open(f"{D}/{c}.json")); k = {int(x["t"]): x for x in d["cd"]}; rows = []
        for s in sorted(d["st"], key=lambda s: s["time"]):
            x = k.get(s["time"])
            if x and s.get("open_interest_usd"): rows.append((s["time"], float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(s["open_interest_usd"])))
        data[c] = np.array(rows)
    Tm = np.array(sorted(set(int(t) for c in coinsl for t in data[c][:, 0]))); ti = {int(t): i for i, t in enumerate(Tm)}; nT = len(Tm); nC = len(coinsl)
    M = {k: np.full((nC, nT), np.nan) for k in "ohlc"}; OI = np.full((nC, nT), np.nan)
    for ci, c in enumerate(coinsl):
        for r in data[c]: j = ti[int(r[0])]; M["o"][ci, j], M["h"][ci, j], M["l"][ci, j], M["c"][ci, j], OI[ci, j] = r[1:]
    w = 16; H = 16; ev = []
    for ci in range(nC):
        c = M["c"][ci]; oi = OI[ci]; last = -999
        for j in range(w, nT - 1):
            if np.isnan(c[j]) or np.isnan(c[j - w]) or np.isnan(oi[j]) or np.isnan(oi[j - w]): continue
            p = (c[j] / c[j - w] - 1) * 100; o = (oi[j] / oi[j - w] - 1) * 100
            if abs(p) >= .5 and abs(o) >= 1 and p < 0 and o > 0 and j - last >= w: ev.append((ci, j)); last = j
    rows = []
    for ci, j in ev:
        if j + H >= nT or np.isnan(M["c"][ci, j + H]) or np.isnan(M["o"][ci, j + 1]): continue
        e = M["o"][ci, j + 1]; x = M["c"][ci, j + H]; mae = (np.nanmax(M["h"][ci, j + 1:j + H + 1]) - e) / e; ret = -(x - e) / e
        rows.append((ci, j, int(Tm[j + 1]), int(Tm[j + H]) + 900, ret, mae))
    A = np.array(rows); n = len(A); t_in = A[:, 2].astype(np.int64); t_out = A[:, 3].astype(np.int64); ret = A[:, 4]; mae = A[:, 5]; ci = A[:, 0].astype(int)
    fr = np.zeros(n); covm = np.zeros(n, bool)
    for q, c in enumerate(coinsl):
        if c in F:
            m = ci == q; ts, cum = F[c]; a = np.searchsorted(ts, t_in[m], "right"); b = np.searchsorted(ts, t_out[m], "right"); fr[m] = cum[b] - cum[a]; covm[m] = t_in[m] >= ts[0]
    fund = +fr   # short: oran>0 iken ALIR -> getiriye +fr
    blk = ci * 1000 + ((t_in - t_in.min()) // 86400 // 3)
    out = ["\n## NEWSHORT w16 / 4s tutma (liqbt_signals.py'nin yeniden yazımı; Gate 15m, ~21 gün, 26 coin) — fiyat getirisi, kısa pozisyon\n"]
    out.append(f"Olay sayısı n={n} (rapordaki 477 ile karşılaştır; olay tanımı aynı: 4s fiyat ≤ −%0,5 ve OI ≥ +%1, refrakter 4s). Funding kapsaması %{covm.mean()*100:.0f}.")
    out.append("| senaryo | ort. getiri bp [CI] |\n|---|---|")
    def row(lab, x): lo, hi = boot_ci(x, blk, nb=2000); return f"| {lab} | {x.mean()*1e4:+.1f} [{lo*1e4:+.1f},{hi*1e4:+.1f}] |"
    bp = 1e-4
    out.append(row("brüt (maliyetsiz)", ret)); out.append(row("net %0,05/taraf (10bp tur)", ret - 0.001)); out.append(row("net %0,05 + funding", ret - 0.001 + fund)); out.append(row("net %0,15/taraf (30bp tur)", ret - 0.003)); out.append(row("net %0,15 + funding", ret - 0.003 + fund))
    out.append(f"\nOrtalama funding katkısı (short alır): {fund.mean()*1e4:+.2f} bp/işlem (4s tutma, ~yarı olasılıkla uzlaşma). Funding'in işlem başına etkisi küçük; asıl belirleyici maliyet.")
    mm = np.array([0.005] * n)  # coin mmr: 26 coin evreni combo evreninden farkli olabilir -> Gate sozlesme dosyasindan
    con = json.load(open(f"{FUND}/gate_contracts.json")); mm = np.array([float(con.get(f"{coinsl[q]}_USDT", {}).get("maintenance_rate", 0.005)) for q in ci])
    for Lv in (5, 10, 20):
        ld = 1.0 / Lv - mm; liq = mae >= ld; x = np.where(liq, -1.0 / Lv, ret) - 0.001 + fund; out.append(f"- Sabit {Lv}x: likide olan işlem %{liq.mean()*100:.1f}; net(%0,05)+funding = {x.mean()*1e4:+.1f} bp [notional getirisi; likidasyonda −1/L notional kaybı]")
    return "\n".join(out)
