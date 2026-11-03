"""Saatlik CANLI karar mantığının geçmiş backtest'i (KÂĞIT, gerçek emir YOK).
Canlı trader.py ile aynı: 4h trend ajanı + 1h giriş ajanı (MTF), hizalıysa tam tartışma (teknik, duygu, boğa, ayı, hakem),
hakem kararı MTF yönüyle aynı ve güven >= min_confidence ise işlem. Stop 2xATR(1h), hedef 3xATR, 24s süre limiti,
taraf başına %0,1 komisyon + %0,05 kayma, %1 risk, güvene göre kaldıraç üst sınırı, teminat sınırı %20.
Look-ahead yok: her noktada yalnızca o mum kapanışına kadarki veri. Geçmişi olmayan veriler (likidasyon, emir defteri,
zincir üstü) verilmez. Ayrı önbellek: outputs/.cache/bt1h/ (canlı mum önbelleğine/defterine dokunmaz).
Kullanım: python backtest_1h.py SOLUSDT [--n 10] [--step 30] [--max-calls 66] [--times-from eski.json --out yeni.json] [--lessons [--lessons-llm]]  (önbellek dizini: BT_CACHE_DIR)"""
import os, sys, json, time, argparse, datetime as dt
import requests, pandas as pd
os.environ.setdefault("CA_NO_KEYLEVELS", "1")   # kritik seviye satırı canlıya özel (geçmişte look-ahead olur)
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import data, agents, llm, paper, lessons
from run import parse_json

CFG = json.load(open("config.json")); T = CFG["trader"]
IST = dt.timezone(dt.timedelta(hours=3)); H = 3600_000
CDIR = os.environ.get("BT_CACHE_DIR") or os.path.join("outputs", ".cache", "bt1h"); os.makedirs(CDIR, exist_ok=True)
SPOT = "https://data-api.binance.vision/api/v3/klines"; OKX = "https://www.okx.com/api/v5"
_last = [0.0]

def okx(path, params):
    w = 0.5 - (time.time() - _last[0])
    if w > 0: time.sleep(w)
    _last[0] = time.time()
    for a in range(3):
        try:
            j = requests.get(OKX + path, params=params, timeout=15).json()
            if str(j.get("code")) == "0": return j["data"]
        except Exception: pass
        time.sleep(1 + a)
    return []

def raw_klines(sym, iv, limit=1000, end_ms=None):
    p = {"symbol": sym, "interval": iv, "limit": limit}
    if end_ms: p["endTime"] = end_ms
    k = requests.get(SPOT, params=p, timeout=20).json()
    df = pd.DataFrame(k, columns=["ot","open","high","low","close","volume","ct","qv","n","tb","tq","ig"])
    for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
    df["ot"] = df["ot"].astype("int64"); df["ct"] = df["ot"] + {"1h": H, "4h": 4*H, "1m": 60_000}[iv]
    df["date"] = pd.to_datetime(df["ot"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    return df[df["ct"] <= int(time.time()*1000)].reset_index(drop=True)

def upto(df, t_ms, n=400):
    """t_ms anında KAPANMIŞ son n mum + göstergeler (canlıdaki gibi 400 mum)."""
    d = df[df["ct"] <= t_ms].tail(n).reset_index(drop=True)
    return data.add_indicators(d[["date","open","high","low","close","volume"]].copy())

def hist_sent(sym, t_ms, df, fng_all):
    inst = sym.replace("USDT", "-USDT-SWAP"); L = []; miss = []
    f = okx("/public/funding-rate-history", {"instId": inst, "limit": 9, "after": t_ms})
    rates = [float(x.get("realizedRate") or x["fundingRate"]) for x in f][::-1]
    fund = {"source": "okx-swap", "rates": rates} if rates else None
    oi_rows = [r for r in okx("/rubik/stat/contracts/open-interest-history", {"instId": inst, "period": "1H", "end": t_ms, "limit": 30}) if int(r[0]) <= t_ms][:24]
    oi = {"source": "okx", "period": "1H", "oi_usd": [float(r[3]) for r in oi_rows]} if oi_rows else None
    day = dt.datetime.fromtimestamp(t_ms/1000, dt.timezone.utc).strftime("%Y-%m-%d")
    fng = [x for x in fng_all if x[0] <= day][:10] if fng_all else None
    _, sent = data.snapshot(sym, df, fng=fng, fund=fund, oi=oi, interval="1h")
    ls = [r for r in okx("/rubik/stat/contracts/long-short-account-ratio-contract", {"instId": inst, "period": "1H", "end": t_ms, "limit": 30}) if int(r[0]) <= t_ms][:24]
    if ls: L.append(f"Long/short hesap oranı (okx): şimdi {float(ls[0][1]):.2f}, {len(ls)-1} periyot önce {float(ls[-1][1]):.2f}")
    else: miss.append("long_short")
    tk = [r for r in okx("/rubik/stat/taker-volume-contract", {"instId": inst, "period": "1H", "end": t_ms, "limit": 30}) if int(r[0]) + H <= t_ms][:24]
    if tk:
        sell = sum(float(r[1]) for r in tk); buy = sum(float(r[2]) for r in tk)
        if sell: L.append(f"Taker alış/satış hacim oranı (son 24 periyot): {buy/sell:.2f}")
    else: miss.append("taker")
    vs = data.volume_spike if False else None
    v = df["volume"]; base = v.iloc[-21:-1].mean()
    if base: L.append(f"Hacim sıçraması: son mum hacmi / önceki 20 mum ort. = {v.iloc[-1]/base:.2f}x")
    if not fund: miss.append("funding")
    if not oi: miss.append("oi")
    return sent + ("\n" + "\n".join(L) if L else ""), miss

def sim_exit(sym, k1, i, side, fill, stop, target):
    """i = karar mumu indeksi; sonraki 24 saatlik mumda stop/hedef/süre. Aynı mumda ikisi -> 1m ile çöz, yine belirsizse stop."""
    lg = side == "LONG"; fut = k1.iloc[i+1:i+1+T["max_hold_hours"]]
    for _, r in fut.iterrows():
        hs = r.low <= stop if lg else r.high >= stop; ht = r.high >= target if lg else r.low <= target
        if hs and ht:
            m = raw_klines(sym, "1m", 60, end_ms=int(r.ct) - 1); m = m[m.ot >= r.ot]
            for _, q in m.iterrows():
                s2 = q.low <= stop if lg else q.high >= stop; t2 = q.high >= target if lg else q.low <= target
                if s2: return stop, "STOP", int(q.ct)
                if t2: return target, "HEDEF", int(q.ct)
            return stop, "STOP", int(r.ct)
        if hs: return stop, "STOP", int(r.ct)
        if ht: return target, "HEDEF", int(r.ct)
    return float(fut.close.iloc[-1]), "SÜRE", int(fut.ct.iloc[-1])

def size(eq, fill, stop, conf):
    fee, slip = T["fee"], T["slippage"]
    cap = next((lv for th, lv in sorted(T["leverage_tiers"], reverse=True) if conf >= th), 1); cap = max(1, min(cap, T["max_leverage"], 5))
    max_margin = eq * T.get("max_margin_frac", T["max_pos_frac"])
    per_unit = abs(fill - stop) + fill * 2 * (fee + slip)
    notional = min(eq * T["risk_per_trade"] / per_unit * fill, max_margin * cap)
    lev = 1
    while lev < cap and notional / lev > max_margin: lev += 1
    return notional, lev, cap

def ist(ms): return dt.datetime.fromtimestamp(ms/1000, IST).strftime("%Y-%m-%d %H:%M")

def main(sym, n, step, max_calls, times_from=None, out_path=None, tag=None, use_lessons=False, lessons_llm=False):
    t0 = time.time(); agents.CTX["interval"] = "1h"
    k1 = raw_klines(sym, "1h", 1000); k4 = raw_klines(sym, "4h", 1000)
    fng_all = data.fear_greed(90) or []
    last = len(k1) - 1 - T["max_hold_hours"]
    idxs = sorted(last - step * j for j in range(n))
    if times_from:   # önceki koşunun AYNI karar mumları (karşılaştırma için)
        want = [r["mum_utc"] for r in json.load(open(times_from))["rows"]]
        pos = {d: j for j, d in enumerate(k1.date)}; idxs = sorted(pos[w] for w in want)
        assert len(idxs) == len(want) and all(j + 24 < len(k1) for j in idxs), "karar noktaları eşleşmedi"
    eq = float(T["start_equity"]); peak = eq; mdd = 0.0; rows = []; dead_note = None
    fee, slip = T["fee"], T["slippage"]
    S = lessons.new_store() if use_lessons else None   # yalnızca bellekte/rapor için; canlı lessons.json'a DOKUNMAZ
    for i in idxs:
        t_ms = int(k1.ct.iloc[i]); when = k1.date.iloc[i]
        d1, d4 = upto(k1, t_ms), upto(k4, t_ms)
        tech1, _ = data.snapshot(sym, d1, interval="1h"); tech4, _ = data.snapshot(sym, d4, interval="4h")
        sent1, miss = hist_sent(sym, t_ms, d1, fng_all)
        sent4 = sent1.replace(sent1.splitlines()[-1], "") if False else sent1   # canlıda 4h türev metni de 1H periyotlu
        cpath = os.path.join(CDIR, f"{sym}_{when.replace(' ', 'T').replace(':', '')}.json")
        cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
        def C(name, fn):
            if name in cache: return cache[name]
            if llm.CALLS["n"] >= max_calls: raise RuntimeError("bütçe")
            cache[name] = fn(); cache.setdefault("_providers", {})[name] = llm.last_provider()
            json.dump(cache, open(cpath, "w"), ensure_ascii=False, indent=2); return cache[name]
        price = float(d1.close.iloc[-1]); atr = float(d1.atr14.iloc[-1])
        # ders bloğu: yalnızca bu karar anından ÖNCE kapanmış işlemlerden (look-ahead yok)
        lb4 = lessons.block(S, sym, tech4, sent1, before_ms=t_ms, atr_pct=100*atr/price) if S else ""
        lb1 = lessons.block(S, sym, tech1, sent1, before_ms=t_ms, atr_pct=100*atr/price) if S else ""
        fut = k1.iloc[i+1:i+1+24]; mv24 = float(fut.close.iloc[-1]) / price - 1
        row = {"zaman_ist": ist(t_ms), "mum_utc": when, "fiyat": price, "atr": atr, "sonraki_24s_%": round(mv24*100, 2), "eksik_veri": miss}
        try:
            tr = parse_json(C("trend_4h_raw", lambda: agents.trend_4h(tech4, sent1, lb4)[0])) or {}
            en = parse_json(C("entry_raw", lambda: agents.entry_ltf(tech1, sent1, json.dumps(tr, ensure_ascii=False), "1h", lb1)[0])) or {}
            trend, giris = str(tr.get("trend", "")).upper(), str(en.get("giris", "")).upper()
            aligned = (trend == "YUKARI" and giris == "LONG") or (trend == "ASAGI" and giris == "SHORT")
            k = ("BUY" if giris == "LONG" else "SELL") if aligned else "HOLD"
            row.update(trend_4h=trend, giris_1h=giris, mtf_guven=[tr.get("guven"), en.get("guven")], hizali=aligned)
            karar, conf, h = "HOLD", None, {}
            if aligned:
                mem = "Geçmiş karar yok (hafıza boş)."
                ta = C("teknik_analist", lambda: agents.technical(tech1)); sa = C("duygu_analisti", lambda: agents.sentiment(sent1))
                bu = C("boga", lambda: agents.bull(ta, sa)); be = C("ayi", lambda: agents.bear(ta, sa, bu))
                h = parse_json(C("hakem_raw", lambda: agents.judge(tech1, ta, sa, bu, be, mem, lb1)[0])) or {}
                conf = int(h.get("guven") or 0); row.update(hakem=h.get("karar"), hakem_guven=conf, gerekce=h.get("gerekce"),
                                                            egilim={"teknik": paper.stance(ta), "duygu": paper.stance(sa)})
                if h.get("karar") == k and conf >= T["min_confidence"]: karar = k
                else: row["not"] = "eşik/uyum sağlanmadı -> işlem yok"
            else: row["not"] = "MTF hizasız -> işlem yok"
        except RuntimeError as e:
            row.update(karar="ATLANDI", not_=f"LLM bütçesi ({max_calls}) doldu"); rows.append(row); print(row); continue
        except SystemExit as e:
            dead_note = str(e); row.update(karar="ATLANDI", not_=f"sağlayıcılar tükendi: {e}"); rows.append(row); print(row); break
        row.update(karar=karar, guven=conf if karar != "HOLD" else (conf if conf else None), providers=cache.get("_providers"))
        dirc = h.get("karar") if h.get("karar") in ("BUY", "SELL") else None
        row["yon_cagrisi"] = dirc; row["yon_dogru"] = (dirc == "BUY") == (mv24 > 0) if dirc else None
        if karar in ("BUY", "SELL"):
            side = "LONG" if karar == "BUY" else "SHORT"; sg = 1 if side == "LONG" else -1
            fill = price * (1 + sg * slip); stop = fill - sg * T["atr_stop_mult"] * atr; target = fill + sg * T["atr_target_mult"] * atr
            notional, lev, cap = size(eq, fill, stop, conf); qty = notional / fill
            px, why, t_exit = sim_exit(sym, k1, i, side, fill, stop, target)
            xf = px * (1 - sg * slip); pnl = qty * sg * (xf - fill) - notional * fee - qty * xf * fee
            eq += pnl; peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
            row.update(yon=side, giris=fill, stop=stop, hedef=target, kaldirac=lev, kaldirac_ust=cap, buyukluk_usd=round(notional, 2),
                       teminat_usd=round(notional/lev, 2), cikis=px, cikis_nedeni=why, cikis_zaman_ist=ist(t_exit), pnl_usd=round(pnl, 2), bakiye=round(eq, 2))
            if S is not None:
                row["ders_blogu_vardi"] = bool(lb1)
                stn = {"teknik_analist": paper.stance(ta), "duygu_analisti": paper.stance(sa), "hakem": "BULL" if h.get("karar") == "BUY" else "BEAR",
                       "mtf_4h": {"YUKARI": "BULL", "ASAGI": "BEAR"}.get(trend, "NEUTRAL"), "mtf_giris": {"LONG": "BULL", "SHORT": "BEAR"}.get(giris, "NEUTRAL")}
                rec = lessons.rec_from_backtest(dict(row, symbol=sym), t_ms, t_exit, k1, i, lessons.parse_ctx(tech1, sent1), aligned, stn)
                ll = None
                if lessons_llm and llm.CALLS["n"] < max_calls:
                    rec_t = dict(rec); rec_t["lesson_rule"] = lessons.rule_lesson(rec)
                    ll = cache.get("ders_llm") or lessons.llm_lesson(rec_t)
                    if ll: cache["ders_llm"] = ll; json.dump(cache, open(cpath, "w"), ensure_ascii=False, indent=2)
                row["ders"] = lessons.add(S, rec, ll)["lesson"]
        rows.append(row); print(json.dumps({k_: row.get(k_) for k_ in ("zaman_ist","trend_4h","giris_1h","hakem","hakem_guven","karar","cikis_nedeni","pnl_usd","bakiye")}, ensure_ascii=False))
    tr_ = [r for r in rows if r.get("pnl_usd") is not None]; dc = [r for r in rows if r.get("yon_cagrisi")]
    p0 = float(k1.close.iloc[idxs[0]]); p1 = float(k1.close.iloc[idxs[-1] + 24])
    res = {"symbol": sym, "mod": "1h MTF (4h trend + 1h giriş) + tam tartışma, canlı trader.py kuralları", "kagit": True,
           "baslangic_ist": ist(int(k1.ct.iloc[idxs[0]])), "bitis_ist": ist(int(k1.ct.iloc[idxs[-1] + 24])), "adim_saat": step,
           "baslangic_bakiye": T["start_equity"], "son_bakiye": round(eq, 2), "getiri_%": round(100*(eq/T["start_equity"]-1), 2),
           "islem_sayisi": len(tr_), "kazanan": sum(r["pnl_usd"] > 0 for r in tr_),
           "kazanma_orani_%": round(100*sum(r["pnl_usd"] > 0 for r in tr_)/len(tr_), 1) if tr_ else None,
           "yon_isabeti_%": round(100*sum(r["yon_dogru"] for r in dc)/len(dc), 1) if dc else None, "yon_cagrisi_n": len(dc),
           "mtf_giris_isabeti_%": (lambda g: round(100*sum(g)/len(g), 1) if g else None)([(r["giris_1h"] == "LONG") == (r["sonraki_24s_%"] > 0) for r in rows if r.get("giris_1h") in ("LONG", "SHORT")]),
           "max_dusus_%": round(100*mdd, 2), "al_tut_%": round(100*(p1/p0 - 1), 2),
           "llm_cagrisi": llm.CALLS["n"], "saglayicilar": sorted({f"{x['provider']}/{x['model']}" for x in llm.CALLS["log"] if x.get("ok")}),
           "yedege_gecis": sum(1 for x in llm.CALLS["log"] if not x.get("ok")), "sure_s": round(time.time() - t0, 1),
           "eksik_veri": "Geçmiş likidasyon, emir defteri, zincir üstü/stablecoin verisi yok (verilmedi). Funding/OI/LS/taker OKX SOL-USDT-SWAP enstrüman geçmişinden (canlıda ccy toplamı). Hafıza boş. LLM risk yöneticisi çağrısı atlandı (canlıda işlem kararını etkilemiyor). Giriş = karar mumu kapanışı (canlıda birkaç dk sonraki fiyat).",
           "uyari": "Örneklem çok küçük (10 nokta); model eğitiminden sonraki dönem olsa da kesin kanıt değildir.", "rows": rows}
    if S is not None:
        res["hafiza"] = "ders hafızası AÇIK (yalnızca karar anından önce kapanmış işlemlerin dersleri istemlere eklendi)"
        res["dersler"] = {"istatistik": lessons.stats(S), "dersler": [{k_: r[k_] for k_ in ("id", "side", "pnl_usd", "exit_reason", "tags", "lesson", "lesson_src")} for r in S["recent"]], "icgoru": lessons.insights(S)}
    if tag: res["surum"] = tag
    out = out_path or os.path.join("outputs", f"backtest_1h_{sym}.json"); json.dump(res, open(out, "w"), ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k_: v for k_, v in res.items() if k_ != "rows"}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("symbol", nargs="?", default="SOLUSDT")
    ap.add_argument("--n", type=int, default=10); ap.add_argument("--step", type=int, default=30); ap.add_argument("--max-calls", type=int, default=66)
    ap.add_argument("--times-from", help="önceki sonuç JSON'undaki aynı karar mumlarını kullan")
    ap.add_argument("--out", help="çıktı JSON yolu"); ap.add_argument("--tag", help="sürüm etiketi")
    ap.add_argument("--lessons", action="store_true", help="karar noktaları boyunca ders biriktir ve sonraki kararların istemine ekle (kural tabanlı; ayrı önbellek)")
    ap.add_argument("--lessons-llm", action="store_true", help="--lessons ile birlikte işlem başına 1 ucuz LLM dersi (max-calls'a sayılır)")
    a = ap.parse_args()
    if a.lessons and not os.environ.get("BT_CACHE_DIR"):   # istemler değiştiği için önbellek ayrı
        CDIR = os.path.join("outputs", ".cache", "bt1h_lessons"); os.makedirs(CDIR, exist_ok=True)
    main(a.symbol.upper(), a.n, a.step, a.max_calls, a.times_from, a.out, a.tag, a.lessons or a.lessons_llm, a.lessons_llm)
