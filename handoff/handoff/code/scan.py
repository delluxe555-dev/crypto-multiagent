"""İki aşamalı tarama.
Aşama 1 (LLM'siz, ücretsiz): Binance'te 24s USDT hacmine göre ilk ~100 coin (config.json'daki hariç listesi + stabil/fiat + kaldıraçlı
token'lar hariç), her biri için seçilen aralık ve 4h mumlarından: hacim sıçraması, ATR%, gerçekleşen volatilite, 4h/alt aralık trend
uyumu, RSI aşırılığı, funding (OKX toplu) ve açık pozisyon. Çok düşük volatiliteli coinler otomatik elenir. Puanla sıralanır.
Aşama 2 (LLM): yalnızca ilk --top K adayda (+ --majors ile BTC/ETH) çok ajanlı tartışma (run.main). OpenRouter ücretsiz kotası
önceden kontrol edilir; yetmezse aşama 2 atlanır.
Kullanım: python scan.py --interval 1h --top 5 [--majors] [--no-llm]"""
import os, sys, json, time, argparse, math
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests
import data, extras

HERE = os.path.dirname(os.path.abspath(__file__)); OUTDIR = os.environ.get("CA_OUT", "outputs")
CFG = json.load(open(os.path.join(HERE, "config.json")))
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR")

def okx_perp_vol():
    try:
        d = extras.get("https://www.okx.com/api/v5/market/tickers", {"instType": "SWAP"}, ttl=600)["data"]
        return {x["instId"].split("-")[0]: float(x["volCcy24h"] or 0) * float(x["last"] or 0) for x in d if x["instId"].endswith("-USDT-SWAP")}
    except Exception: return {}

def universe(cfg):
    t = extras.get("https://data-api.binance.vision/api/v3/ticker/24hr", ttl=600)
    pv = okx_perp_vol()
    q = cfg["quote"]; ex = set(cfg["exclude"]) | set(cfg.get("exclude_meme", [])); rows = []
    for x in t:
        s = x["symbol"]
        if not s.endswith(q): continue
        base = s[:-len(q)]
        if base in ex or any(base.endswith(l) and len(base) > len(l) for l in LEVERAGED): continue
        if cfg.get("exclude_non_ascii") and not base.isascii(): continue
        vol = float(x["quoteVolume"]) + pv.get(base, 0)      # Binance spot + OKX USDT-M perp hacmi
        if vol < cfg.get("min_quote_vol_24h", 0): continue
        if float(x["quoteVolume"]) <= 0 or int(x.get("count", 0)) == 0: continue
        rows.append({"symbol": s, "base": base, "quote_vol_24h": vol, "spot_vol_24h": float(x["quoteVolume"]), "perp_vol_24h": pv.get(base, 0), "chg_24h_%": float(x["priceChangePercent"])})
    rows.sort(key=lambda r: -r["quote_vol_24h"])
    return rows[:cfg["universe_size"]]

def bulk_derivs():
    fr, oi = {}, {}
    try:
        for x in extras.get("https://www.okx.com/api/v5/public/funding-rate", {"instId": "ANY"}, ttl=600)["data"]:
            if x["instId"].endswith("-USDT-SWAP"): fr[x["instId"].split("-")[0]] = float(x["fundingRate"])
    except Exception as e: print("funding alınamadı:", e)
    try:
        for x in extras.get("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP"}, ttl=600)["data"]:
            if x["instId"].endswith("-USDT-SWAP"): oi[x["instId"].split("-")[0]] = float(x["oiUsd"])
    except Exception as e: print("OI alınamadı:", e)
    return fr, oi

def trend(df):
    r = df.iloc[-1]; slope = df.sma50.iloc[-1] - df.sma50.iloc[-6]
    if r.close > r.sma50 and slope > 0: return 1
    if r.close < r.sma50 and slope < 0: return -1
    return 0

def listing_days(sym):
    try: return len(data.klines(sym, interval="1d", limit=60))
    except Exception: return None

def features(sym, interval):
    try:
        d = data.add_indicators(data.klines(sym, interval=interval, limit=300))
        d4 = d if interval == "4h" else data.add_indicators(data.klines(sym, interval="4h", limit=300))
        if len(d) < 60 or len(d4) < 60: return None
        r = d.iloc[-1]; ret = np.log(d.close).diff().dropna().iloc[-100:]
        vs = d.volume.iloc[-1] / d.volume.iloc[-21:-1].mean() if d.volume.iloc[-21:-1].mean() else np.nan
        vs3 = d.volume.iloc[-3:].mean() / d.volume.iloc[-23:-3].mean() if d.volume.iloc[-23:-3].mean() else np.nan
        t_l, t_4 = trend(d), trend(d4)
        return {"symbol": sym, "close": r.close, "atr_%": r.atr14 / r.close * 100, "rvol_%": ret.std() * 100,
                "vol_spike": vs, "vol_spike_3": vs3, "rsi": r.rsi14, "trend_ltf": t_l, "trend_4h": t_4,
                "aligned": t_l if t_l == t_4 and t_l != 0 else 0, "macd_hist": r.macd_hist / r.close * 100, "bar": str(r.date)}
    except Exception as e:
        return {"symbol": sym, "error": str(e)[:120]}

def zs(s):
    s = s.astype(float); sd = s.std()
    return ((s - s.mean()) / sd).clip(-3, 3) if sd and not math.isnan(sd) else s * 0   # aykırı değer baskınlığını sınırla

def quota_left():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key: return None
    try:
        d = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=10).json()["data"]
        f = d.get("free_model_daily_requests") or {}
        return f.get("remaining")
    except Exception: return None

def main(a):
    t0 = time.time(); uni = universe(CFG); fr, oi = bulk_derivs()
    dropped = []
    if CFG.get("require_okx_perp") and fr:
        dropped += [{"symbol": u["symbol"], "elendi": "OKX USDT-M perp yok"} for u in uni if u["base"] not in fr]
        uni = [u for u in uni if u["base"] in fr]
    if CFG.get("min_listing_days"):
        with ThreadPoolExecutor(6) as ex: days = list(ex.map(lambda u: listing_days(u["symbol"]), uni))
        keep = []
        for u, d in zip(uni, days):
            if d is not None and d < CFG["min_listing_days"]: dropped.append({"symbol": u["symbol"], "elendi": f"yeni listeleme ({d} gün)"})
            else: keep.append(u)
        uni = keep
    print(f"Evren (filtre sonrası): {len(uni)} coin; ön filtrede elenen {len(dropped)} (hariç: {', '.join(CFG['exclude'])})")
    with ThreadPoolExecutor(6) as ex: feats = list(ex.map(lambda u: features(u["symbol"], a.interval), uni))
    meta = {u["symbol"]: u for u in uni}
    rows = [dict(meta[f["symbol"]], **f) for f in feats if f and "error" not in f]
    errs = [f for f in feats if f and "error" in f]
    df = pd.DataFrame(rows)
    df["funding_%"] = df.base.map(fr) * 100; df["oi_usd"] = df.base.map(oi)
    # otomatik düşük volatilite eleme
    thr = max(CFG["min_atr_pct"].get(a.interval, 0.5), np.percentile(df["atr_%"], CFG["low_vol_percentile"]))
    df["elendi"] = np.where(df["atr_%"] < thr, f"düşük volatilite (ATR% < {thr:.2f})", "")
    df.loc[df["chg_24h_%"].abs() > CFG.get("max_abs_chg_24h_%", 1e9), "elendi"] = "anomali: 24s değişim çok büyük (delist/pump riski)"
    df.loc[df["quote_vol_24h"] < CFG.get("min_quote_vol_24h", 0), "elendi"] = "düşük likidite"
    ok = df[df.elendi == ""].copy()
    rsi_ext = (ok.rsi - 50).abs().clip(lower=15) - 15          # 35-65 arası 0, dışında aşırılık
    fund_ext = ok["funding_%"].abs().fillna(0)
    ok["skor"] = (1.5 * zs(np.log(ok.vol_spike_3.clip(lower=0.05))) + 1.0 * zs(np.log(ok.vol_spike.clip(lower=0.05)))
                  + 1.0 * zs(ok["atr_%"]) + 1.0 * ok.aligned.abs() + 0.7 * zs(rsi_ext) + 0.5 * zs(fund_ext)
                  + 0.3 * zs(np.log(ok.quote_vol_24h)))
    ok["yon"] = np.select([ok.aligned > 0, ok.aligned < 0], ["long-yanlı", "short-yanlı"], "kararsız")
    ok = ok.sort_values("skor", ascending=False)
    cols = ["symbol", "skor", "yon", "close", "chg_24h_%", "quote_vol_24h", "vol_spike", "vol_spike_3", "atr_%", "rvol_%", "rsi",
            "trend_4h", "trend_ltf", "funding_%", "oi_usd", "bar"]
    os.makedirs(OUTDIR, exist_ok=True); stamp = time.strftime("%Y%m%d-%H%M")
    ok[cols].to_csv(os.path.join(OUTDIR, f"scan_{a.interval}_{stamp}.csv"), index=False)
    short = ok.head(a.top).symbol.tolist()
    targets = short + [m for m in (["BTCUSDT", "ETHUSDT"] if a.majors else []) if m not in short]
    res = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "interval": a.interval, "universe_n": len(uni), "scored_n": len(ok),
           "elenen": dropped + df[df.elendi != ""][["symbol", "elendi"]].to_dict("records"), "hatalar": errs, "shortlist": short, "stage2_targets": targets,
           "ranked": json.loads(ok[cols].round(4).to_json(orient="records")), "stage2": {}}
    pd.set_option("display.width", 200)
    print(ok[cols[:12]].head(15).round(2).to_string(index=False))
    print(f"\nKısa liste: {short}  | elenen (düşük vol/anomali/likidite): {len(res['elenen'])}  | süre {time.time()-t0:.0f}s")
    if not a.no_llm:
        need = CFG["llm_calls_per_coin"] * len(targets)
        provs = [p.get("name") for p in CFG.get("providers", []) if p.get("enabled", True)]
        others = [p for p in provs if p != "openrouter"]
        left = None if others else quota_left()   # Gemini/Ollama varsa ön kontrol yok; zincir tükenirse AllProvidersExhausted ile durur
        if left is not None and left < need:
            res["stage2_skipped"] = f"OpenRouter ücretsiz kota yetersiz: kalan {left}, gereken ~{need}. --top küçült veya yarın/kredi ile çalıştır."
            print(res["stage2_skipped"])
        else:
            import run
            for s in targets:
                try: run.main(s, a.interval); res["stage2"][s] = "tamam (bkz. outputs/summary.json)"
                except SystemExit as e: res["stage2"][s] = f"durdu: {e}"; break
                except Exception as e: res["stage2"][s] = f"hata: {e}"
    json.dump(res, open(os.path.join(OUTDIR, f"scan_{a.interval}_{stamp}.json"), "w"), ensure_ascii=False, indent=2, default=str)
    json.dump(res, open(os.path.join(OUTDIR, f"scan_latest.json"), "w"), ensure_ascii=False, indent=2, default=str)
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1h", choices=["15m", "1h", "4h", "1d"])
    ap.add_argument("--top", type=int, default=5); ap.add_argument("--majors", action="store_true", help="BTC/ETH'yi de aşama 2'ye ekle")
    ap.add_argument("--no-llm", action="store_true", help="yalnızca aşama 1")
    main(ap.parse_args())
