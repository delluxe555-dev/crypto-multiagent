"""Kaldıraç simülasyonu (yalnızca simülasyon; canlı ledger/config/state'e YAZMAZ, yalnızca okur).
Çıktı: outputs/leverage_sim.json, outputs/leverage_sim.md. Önbellek: /workspace/levsim_cache (canlı önbellek değil)."""
import os, json, time, datetime as dt, statistics as st
import requests, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CD = "/workspace/levsim_cache"; os.makedirs(CD, exist_ok=True)
SPOT = "https://data-api.binance.vision/api/v3/klines"
FEE, SLIP, MM = 0.001, 0.0005, 0.004
RISK, ATRS, ATRT = 0.01, 2.0, 3.0
MARGIN_FRAC, MAX_CONC, DLL, MIN_NOT, HOLD_MS = 0.2, 20, 0.02, 10, 24*3600*1000
BASE_TIERS = [(80, 5), (70, 4), (65, 3)]
IST = dt.timezone(dt.timedelta(hours=3))
NOW_MS = int(time.time()*1000) // 60000 * 60000 - 60000   # son tam kapanmış dakika

def klines_1m(sym, start_ms, end_ms):
    """[ot, o, h, l, c] dizisi; dosya önbelleği (kapanmış mumlar)."""
    out = []; t = start_ms
    while t < end_ms:
        fn = f"{CD}/{sym}_1m_{t}.json"
        if os.path.exists(fn) and t + 1000*60000 <= NOW_MS: k = json.load(open(fn))
        else:
            for _ in range(5):
                try:
                    r = requests.get(SPOT, params={"symbol": sym, "interval": "1m", "startTime": t, "limit": 1000}, timeout=20)
                    r.raise_for_status(); k = [[x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in r.json()]; break
                except Exception: time.sleep(2)
            else: raise RuntimeError("kline alınamadı " + sym)
            if len(k) == 1000: json.dump(k, open(fn, "w"))
        if not k: break
        out += k; t = k[-1][0] + 60000
        if len(k) < 1000: break
    return [x for x in out if x[0] <= end_ms]

def ist(ms): return dt.datetime.fromtimestamp(ms/1000, IST).strftime("%m-%d %H:%M")

# ---------------- işlemler ----------------
def load_trades():
    L = json.load(open(f"{HERE}/outputs/trader/ledger.json")); out = []
    for p in L["positions"]:
        t = dt.datetime.fromisoformat(p["opened_at"]).timestamp()*1000
        out.append(dict(id=p["id"], src="canlı", symbol=p["symbol"], side=p["side"], entry_ms=int(t // 60000 * 60000 + 60000), entry=p["entry"],
                        stop=p["stop"], target=p["target"], conf=p["confidence"], actual_pnl=p.get("pnl_usd") if p["status"] == "closed" else None,
                        actual_lev=p["leverage"], actual_status=p["status"]))
    return out, L["equity_start"]

def load_bt(fn, tag):
    b = json.load(open(f"{HERE}/outputs/{fn}")); out = []
    for r in b["rows"]:
        if r.get("pnl_usd") is None: continue
        ot = dt.datetime.strptime(r["mum_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp()*1000
        out.append(dict(id=f"{tag}-{r['mum_utc']}", src=tag, symbol=b["symbol"], side=r["yon"], entry_ms=int(ot + 3600000), entry=r["giris"], stop=r["stop"],
                        target=r["hedef"], conf=r["guven"], actual_pnl=r["pnl_usd"], actual_lev=r["kaldirac"], actual_status="closed"))
    return out

# ---------------- tek pozisyon yolu ----------------
def lev_for(conf, M, variant):
    if variant == "flat": return M if conf >= 65 else 1
    cap = next((lv for th, lv in BASE_TIERS if conf >= th), 1)
    return max(1, min(round(cap * M / 5), M))

def liq_px(side, fill, lev): return fill*(1 - 1/lev + MM) if side == "LONG" else fill*(1 + 1/lev - MM)

def walk(tr, K, lev):
    """Açılıştan sonra 1m mumlarda ilk olay: LIKIT / STOP / HEDEF / SÜRE / AÇIK. Aynı mumda zararlı taraf önce (ihtiyatlı)."""
    lg = tr["side"] == "LONG"; fill, stop, tgt = tr["entry"], tr["stop"], tr["target"]
    lq = liq_px(tr["side"], fill, lev) if lev > 1 else None
    liq_first = lq is not None and (abs(fill - lq) < abs(fill - stop))
    end_t = tr["entry_ms"] + HOLD_MS; last = None
    for ot, o, h, l, c in K:
        if ot < tr["entry_ms"]: continue
        if ot >= end_t: return dict(why="SÜRE", px=last[4], t=ot, lq=lq)
        hs = l <= stop if lg else h >= stop; ht = h >= tgt if lg else l <= tgt
        hl = lq is not None and ((l <= lq) if lg else (h >= lq))
        if hl and liq_first: return dict(why="LİKİT", px=lq, t=ot+60000, lq=lq)
        if hs: return dict(why="STOP", px=stop, t=ot+60000, lq=lq)
        if hl: return dict(why="LİKİT", px=lq, t=ot+60000, lq=lq)
        if ht: return dict(why="HEDEF", px=tgt, t=ot+60000, lq=lq)
        last = (ot, o, h, l, c)
    if last is None: return dict(why="AÇIK", px=fill, t=None, lq=lq, mtm=fill)
    return dict(why="AÇIK", px=last[4], t=None, lq=lq, mtm=last[4])

def pnl_of(tr, qty, notional, margin, ex):
    sg = 1 if tr["side"] == "LONG" else -1; fee_open = notional*FEE
    if ex["why"] == "LİKİT": return -margin - fee_open
    px = ex["px"]
    if ex["why"] == "AÇIK":   # MTM: kapanış maliyeti düşülmez? -> kapanış ücreti ve kayma dahil (gerçekçi çıkış)
        pass
    xf = px*(1 - sg*SLIP)
    return qty*sg*(xf - tr["entry"]) - fee_open - qty*xf*FEE

def simulate(trades, start_eq, M, mode, variant="tiers"):
    """mode: 'same' (risk %1 sabit, kaldıraç yalnızca teminatı sınırlar, canlı kural) | 'aggr' (notional = teminat × kaldıraç)."""
    kl = {}
    for tr in trades:
        kl.setdefault(tr["symbol"], []).append(tr)
    KC = {}
    for s, ts in kl.items():
        a = min(t["entry_ms"] for t in ts); KC[s] = klines_1m(s, a, NOW_MS)
    trades = sorted(trades, key=lambda t: t["entry_ms"])
    realized = 0.0; opened = []; res = []; skipped = []; reduced = []; closed_log = []
    def eq_now(): return start_eq + realized
    for tr in trades:
        t0 = tr["entry_ms"]
        # bu ana kadar kapananları gerçekleştir
        for o in list(opened):
            if o["ex"]["t"] is not None and o["ex"]["t"] <= t0: realized += o["pnl"]; opened.remove(o); closed_log.append((o["ex"]["t"], o["pnl"]))
        eq = eq_now(); free = eq - sum(o["margin"] for o in opened)
        day0 = dt.datetime.fromtimestamp(t0/1000, IST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()*1000
        r_today = sum(p for tt, p in closed_log if tt >= day0)
        why = None
        if len(opened) >= MAX_CONC: why = "eşzamanlı sınır"
        elif r_today <= -DLL*eq: why = "günlük zarar limiti"
        elif any(o["tr"]["symbol"] == tr["symbol"] for o in opened): why = "zaten açık"
        cap = lev_for(tr["conf"], M, variant)
        max_margin = max(0.0, min(eq*MARGIN_FRAC, free)); fill = tr["entry"]
        if mode == "same":
            per_unit = abs(fill - tr["stop"]) + fill*2*(FEE + SLIP)
            notional = min(eq*RISK/per_unit*fill, max_margin*cap); lev = 1
            while lev < cap and notional/lev > max_margin: lev += 1
        else:
            lev = cap; notional = max_margin*lev
        margin = notional/lev if lev else notional
        if why is None and notional < MIN_NOT: why = "teminat yetersiz (<$10 büyüklük)"
        if why:
            skipped.append(dict(id=tr["id"], neden=why, serbest_teminat=round(free, 2))); continue
        if free < eq*MARGIN_FRAC - 1e-9 and (mode == "aggr" or notional >= max_margin*cap - 1e-9):
            reduced.append(dict(id=tr["id"], serbest_teminat=round(free, 2), istenen=round(eq*MARGIN_FRAC, 2)))
        qty = notional/fill
        ex = walk(tr, KC[tr["symbol"]], lev); p = pnl_of(tr, qty, notional, margin, ex)
        rec = dict(tr=tr, ex=ex, pnl=p, margin=margin, notional=notional, lev=lev, qty=qty, eq_open=eq)
        opened.append(rec); res.append(rec)
    for o in opened:
        if o["ex"]["t"] is not None: realized += o["pnl"]
    # --- dakikalık MTM özsermaye eğrisi ---
    mins = set()
    for r in res:
        a = r["tr"]["entry_ms"]; b = r["ex"]["t"] if r["ex"]["t"] is not None else NOW_MS
        mins.update(range(a, b + 60000, 60000))
    px_at = {}
    for s, K in KC.items(): px_at[s] = {x[0]: x[4] for x in K}
    ts = sorted(mins); peak = start_eq; mdd = 0.0; curve_min = start_eq; peak_margin = 0.0
    cl = sorted((r["ex"]["t"], r["pnl"]) for r in res if r["ex"]["t"] is not None); ci = 0; rl = 0.0
    for t in ts:
        while ci < len(cl) and cl[ci][0] <= t: rl += cl[ci][1]; ci += 1
        un = 0.0; mu = 0.0
        for r in res:
            a = r["tr"]["entry_ms"]; b = r["ex"]["t"]
            if a <= t and (b is None or t < b):
                mu += r["margin"]
                px = px_at[r["tr"]["symbol"]].get(t - t % 60000)
                if px is None: continue
                sg = 1 if r["tr"]["side"] == "LONG" else -1
                un += r["qty"]*sg*(px - r["tr"]["entry"]) - r["notional"]*FEE
        peak_margin = max(peak_margin, mu / (start_eq + rl) * 100)
        e = start_eq + rl + un; peak = max(peak, e); mdd = max(mdd, 1 - e/peak); curve_min = min(curve_min, e)
    closed = [r for r in res if r["ex"]["why"] != "AÇIK"]; opn = [r for r in res if r["ex"]["why"] == "AÇIK"]
    unreal = 0.0
    for r in opn:
        sg = 1 if r["tr"]["side"] == "LONG" else -1; px = r["ex"]["mtm"]
        unreal += r["qty"]*sg*(px - r["tr"]["entry"]) - r["notional"]*FEE
    final_real = start_eq + sum(r["pnl"] for r in closed); final_mtm = final_real + unreal
    worst = min(((r["pnl"]/r["eq_open"]*100), r["tr"]["id"]) for r in closed) if closed else (0, None)
    worst_open = None
    wins = sum(r["pnl"] > 0 for r in closed)
    return dict(M=M, mode=mode, variant=variant, bakiye_gerceklesen=round(final_real, 2), bakiye_mtm=round(final_mtm, 2),
                getiri_mtm_pct=round((final_mtm/start_eq - 1)*100, 2), getiri_gerceklesen_pct=round((final_real/start_eq - 1)*100, 2),
                max_dusus_pct=round(mdd*100, 2), tepe_teminat_kullanimi_pct=round(peak_margin, 1), en_dusuk_ozsermaye=round(curve_min, 2),
                likidasyon=sum(r["ex"]["why"] == "LİKİT" for r in res), islem=len(res), kapanan=len(closed), acik=len(opn),
                kazanma_orani_pct=round(100*wins/len(closed), 1) if closed else None, en_kotu_islem_pct=round(worst[0], 2), en_kotu_islem_id=worst[1],
                atlanan_teminat=len([s for s in skipped if s["neden"].startswith("teminat")]), atlanan_diger=[s for s in skipped if not s["neden"].startswith("teminat")],
                atlanan=skipped, teminat_kisitli_azaltilan=reduced,
                islemler=[dict(id=r["tr"]["id"], yon=r["tr"]["side"], guven=r["tr"]["conf"], kaldirac=r["lev"], teminat=round(r["margin"], 2), buyukluk=round(r["notional"], 2),
                               cikis=r["ex"]["why"], pnl=round(r["pnl"], 2), pnl_pct_hesap=round(r["pnl"]/r["eq_open"]*100, 2),
                               gerceklesen_canli_pnl=r["tr"]["actual_pnl"], cikis_zaman=ist(r["ex"]["t"]) if r["ex"]["t"] else None) for r in res])

# ---------------- duyarlılık ızgarası ----------------
def grid(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "WLDUSDT", "TIAUSDT"), days=14, every_h=2, levs=(5, 10, 20, 30, 50)):
    end = NOW_MS - HOLD_MS - 3600000; start = end - days*86400000
    out = {L: dict(n=0, struct=0, liq_first=0, stop_first=0, tgt_first=0, time=0, liq_touch=0, risk_pct=[]) for L in levs}
    per = {s: {L: dict(n=0, struct=0, liq_first=0) for L in levs} for s in symbols}; stopd = []; sinfo = {}
    for s in symbols:
        h1 = []; t = start - 30*3600000
        while t < NOW_MS:
            r = requests.get(SPOT.replace("klines", "klines"), params={"symbol": s, "interval": "1h", "startTime": t, "limit": 1000}, timeout=20).json()
            if not r: break
            h1 += r; t = r[-1][0] + 3600000
            if len(r) < 1000: break
        H = np.array([[x[0], float(x[2]), float(x[3]), float(x[4])] for x in h1])
        K = klines_1m(s, int(start), NOW_MS); A = np.array(K); ot, hi, lo = A[:, 0], A[:, 2], A[:, 3]
        tr = np.maximum(H[1:, 1] - H[1:, 2], np.maximum(abs(H[1:, 1] - H[:-1, 3]), abs(H[1:, 2] - H[:-1, 3])))
        atr = np.concatenate([[np.nan]*14, np.convolve(tr, np.ones(14)/14, "valid")])  # atr[i+1] ↔ H[i+1]; hizala
        atr_full = np.full(len(H), np.nan); atr_full[14:] = np.convolve(tr, np.ones(14)/14, "valid")
        sinfo[s] = 0
        for i in range(15, len(H)):
            t_close = H[i, 0] + 3600000
            if t_close < start or t_close > end or ((t_close - start)//3600000) % every_h: continue
            a = atr_full[i]; c = H[i, 3]
            lo0 = np.searchsorted(ot, t_close); hi0 = np.searchsorted(ot, t_close + HOLD_MS)
            if hi0 - lo0 < 1400: continue
            wh, wl = hi[lo0:hi0], lo[lo0:hi0]
            for side in ("LONG", "SHORT"):
                lg = side == "LONG"; fill = c*(1 + SLIP) if lg else c*(1 - SLIP); sg = 1 if lg else -1
                stop = fill - sg*ATRS*a; tgt = fill + sg*ATRT*a; sd = abs(fill - stop)/fill*100; stopd.append(sd); sinfo[s] += 1
                iS = np.argmax(wl <= stop) if lg and (wl <= stop).any() else (np.argmax(wh >= stop) if (not lg) and (wh >= stop).any() else 10**9)
                iT = np.argmax(wh >= tgt) if lg and (wh >= tgt).any() else (np.argmax(wl <= tgt) if (not lg) and (wl <= tgt).any() else 10**9)
                for L in levs:
                    lq = liq_px(side, fill, L); ld = abs(fill - lq)/fill*100
                    iL = (np.argmax(wl <= lq) if (wl <= lq).any() else 10**9) if lg else (np.argmax(wh >= lq) if (wh >= lq).any() else 10**9)
                    o = out[L]; o["n"] += 1; per[s][L]["n"] += 1
                    st_ = sd > ld; o["struct"] += st_; per[s][L]["struct"] += st_
                    if iL < 10**9: o["liq_touch"] += 1
                    if ld < sd and iL < 10**9 and iL <= iS and iL <= iT: o["liq_first"] += 1; per[s][L]["liq_first"] += 1
                    elif iS <= iT and iS < 10**9: o["stop_first"] += 1
                    elif iT < 10**9: o["tgt_first"] += 1
                    else: o["time"] += 1
                    o["risk_pct"].append(MARGIN_FRAC*L*(sd + 2*(FEE + SLIP)*100)/1.0)   # agresif: hesabın %'si (stop'ta; % puan)
    tab = {}
    for L in levs:
        o = out[L]; n = o["n"]; rp = np.array(o["risk_pct"])
        tab[str(L)] = dict(likidasyon_mesafesi_pct=round((1/L - MM)*100, 2), n=n, yapisal_liq_stoptan_once_pct=round(100*o["struct"]/n, 1),
                           yolda_liq_ilk_pct=round(100*o["liq_first"]/n, 2), stop_ilk_pct=round(100*o["stop_first"]/n, 1), hedef_ilk_pct=round(100*o["tgt_first"]/n, 1),
                           sure_doldu_pct=round(100*o["time"]/n, 1), liq_seviyesine_dokunus_pct=round(100*o["liq_touch"]/n, 1),
                           agresif_stop_kaybi_hesap_pct_medyan=round(float(np.median(rp)), 1), agresif_stop_kaybi_hesap_pct_p90=round(float(np.percentile(rp, 90)), 1),
                           liq_kaybi_hesap_pct=round(MARGIN_FRAC*100, 1))
    sd_ = np.array(stopd)
    return dict(sembol=list(symbols), gun=days, her_saat=every_h, kurulum_sayisi=int(len(sd_)//1), stop_mesafesi_pct=dict(medyan=round(float(np.median(sd_)), 2), p10=round(float(np.percentile(sd_, 10)), 2), p90=round(float(np.percentile(sd_, 90)), 2), maks=round(float(sd_.max()), 2)),
                tablo=tab, sembol_bazli={s: {str(L): dict(n=v["n"], yapisal_pct=round(100*v["struct"]/max(1, v["n"]), 1), liq_ilk_pct=round(100*v["liq_first"]/max(1, v["n"]), 2)) for L, v in d.items()} for s, d in per.items()})

if __name__ == "__main__":
    live, eq0 = load_trades(); v1 = load_bt("backtest_1h_SOLUSDT.json", "SOLv1"); v2 = load_bt("backtest_1h_SOLUSDT_v2.json", "SOLv2")
    sets = {"birlesik_SOLv2+canli": v2 + live, "yalniz_canli": live, "yalniz_SOLv1": v1, "yalniz_SOLv2": v2}
    out = {"olusturuldu": dt.datetime.now(IST).isoformat(timespec="seconds"), "varsayimlar": dict(risk=RISK, stop_atr=ATRS, hedef_atr=ATRT, ucret=FEE, kayma=SLIP, teminat_siniri=MARGIN_FRAC, max_eszamanli=MAX_CONC, gunluk_zarar_limiti=DLL, bakim_teminati=MM, baslangic=eq0, kademeler="güven 65-70/70-80/>=80 -> 3/4/5x taban, 10x ve 20x için ×2 / ×4 ölçeklenir; 'flat' varyantında tüm işlemler tavan kaldıracı kullanır",
           yol="Binance spot 1m mumlar (canlı trader ile aynı kaynak); aynı mumda stop+hedef -> stop; likidasyon stoptan yakınsa LİKİT (tam teminat + açılış ücreti kaybı)", acik_pozisyon="Hâlâ açık pozisyonlar son 1m kapanışla MTM (kapanış ücreti+kayma düşülmedi? hayır: açılış ücreti düşüldü, kapanış ücreti dahil değil)")}
    out["simulasyon"] = {}
    for name, ts in sets.items():
        out["simulasyon"][name] = {}
        for mode in ("same", "aggr"):
            for variant in ("tiers", "flat"):
                for M in (5, 10, 20):
                    if variant == "flat" and M == 5: pass
                    out["simulasyon"][name][f"{mode}_{variant}_{M}x"] = simulate(ts, eq0, M, mode, variant)
    # canlı doğrulama: 5x/same sonucu gerçek ledger ile
    out["dogrulama_canli_5x_same"] = [dict(id=t["id"], sim=t2["pnl"], gercek=t["actual_pnl"]) for t, t2 in zip(sorted(live, key=lambda x: x["entry_ms"]), [dict(pnl=x["pnl"]) if False else dict(pnl=x["pnl"]) for x in out["simulasyon"]["yalniz_canli"]["same_tiers_5x"]["islemler"]])]
    out["duyarlilik_izgarasi"] = grid()
    json.dump(out, open(f"{HERE}/outputs/leverage_sim.json", "w"), ensure_ascii=False, indent=1, default=str)
    print("ok")
