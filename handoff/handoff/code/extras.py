"""Ek veri: türevler (funding, OI, long/short, taker, likidasyon), emir defteri dengesizliği, hacim sıçraması,
zincir üstü/akış verisi. Hepsi anahtarsız. Binance Futures bu sunucudan bölge engelli olduğu için önce denenir, olmazsa OKX.
HTTP yanıtları outputs/.cache/http altında kısa süre (TTL) önbelleğe alınır."""
import os, json, time, hashlib, requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "outputs", ".cache", "http")

_LAST = {"rubik": 0.0}

def get(url, params=None, ttl=300, timeout=12):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.md5((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
    p = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        return json.load(open(p))
    for attempt in range(3):
        if "/rubik/" in url:   # OKX rubik uçları ~5 istek/2 sn sınırlı
            w = 0.45 - (time.time() - _LAST["rubik"])
            if w > 0: time.sleep(w)
            _LAST["rubik"] = time.time()
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 429 and attempt < 2: time.sleep(1.0 + attempt); continue
        r.raise_for_status(); j = r.json()
        if isinstance(j, dict) and str(j.get("code", "0")) == "50011" and attempt < 2: time.sleep(1.0 + attempt); continue
        break
    if not (isinstance(j, dict) and str(j.get("code", "0")) not in ("0", "")):   # hata yanıtlarını önbelleğe alma
        json.dump(j, open(p, "w"))
    return j

def _okx_period(interval): return {"15m": "5m", "1h": "1H", "4h": "1H"}.get(interval, "1D")

def derivatives(symbol, interval="1d"):
    ccy = symbol.replace("USDT", ""); per = _okx_period(interval); out = {"source": None}
    # 1) Binance futures (çoğu zaman engelli)
    try:
        j = get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                {"symbol": symbol, "period": "1h" if interval != "1d" else "1d", "limit": 24})
        if isinstance(j, list) and j:
            out.update(source="binance-futures", long_short=[float(x["longShortRatio"]) for x in j][::-1])
            oi = get("https://fapi.binance.com/futures/data/openInterestHist",
                     {"symbol": symbol, "period": "1h" if interval != "1d" else "1d", "limit": 24})
            out["oi_usd"] = [float(x["sumOpenInterestValue"]) for x in oi][::-1]
            return out
    except Exception: pass
    # 2) OKX
    out["source"] = "okx"
    try:
        j = get("https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio", {"ccy": ccy, "period": per})
        out["long_short"] = [float(r[1]) for r in j["data"][:24]]          # yeniden eskiye
    except Exception: pass
    try:
        j = get("https://www.okx.com/api/v5/rubik/stat/taker-volume", {"ccy": ccy, "instType": "CONTRACTS", "period": per})
        rows = j["data"][:24]; sell = sum(float(r[1]) for r in rows); buy = sum(float(r[2]) for r in rows)
        out["taker_buy_sell"] = buy / sell if sell else None
    except Exception: pass
    try:
        import liq   # gerçekleşen (15dk/1s/4s/günlük) + tahmini likidasyon kümeleri
        out["liq"] = liq.report(symbol)
        w = (out["liq"].get("realized") or {}).get("windows", {}).get("Günlük")
        if w: out["liq_24h"] = {"long_usd": w["long_usd"], "short_usd": w["short_usd"], "n": w["n"]}
    except Exception: pass
    return out

def orderbook(symbol):
    for base in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            j = get(base + "/api/v3/depth", {"symbol": symbol, "limit": 1000}, ttl=30)
            if "bids" not in j: continue
            bids = [(float(p), float(q)) for p, q in j["bids"]]; asks = [(float(p), float(q)) for p, q in j["asks"]]
            mid = (bids[0][0] + asks[0][0]) / 2; res = {"mid": mid, "spread_bps": (asks[0][0] - bids[0][0]) / mid * 1e4}
            for pct in (0.5, 1.0):
                b = sum(p * q for p, q in bids if p >= mid * (1 - pct / 100)); a = sum(p * q for p, q in asks if p <= mid * (1 + pct / 100))
                res[f"imb_{pct}%"] = (b - a) / (b + a) if b + a else None
                res[f"bid_usd_{pct}%"], res[f"ask_usd_{pct}%"] = b, a
            return res
        except Exception: continue
    return None

def volume_spike(df, n=20):
    v = df["volume"]; base = v.iloc[-n-1:-1].mean()
    return v.iloc[-1] / base if base else None

def onchain(symbol):
    out = {}
    try:
        st = get("https://stablecoins.llama.fi/stablecoincharts/all", ttl=3600)
        tot = [float(x["totalCirculatingUSD"]["peggedUSD"]) for x in st[-31:]]
        out["stablecoin_mcap_bn"] = tot[-1] / 1e9; out["stablecoin_7g_%"] = (tot[-1] / tot[-8] - 1) * 100
        out["stablecoin_30g_%"] = (tot[-1] / tot[0] - 1) * 100
    except Exception: pass
    if symbol.startswith("BTC"):
        try:
            h = get("https://mempool.space/api/v1/mining/hashrate/1m", ttl=3600)["hashrates"]
            out["hashrate_30g_%"] = (h[-1]["avgHashrate"] / h[0]["avgHashrate"] - 1) * 100
            out["mempool_fee_sat_vb"] = get("https://mempool.space/api/v1/fees/recommended", ttl=600)["halfHourFee"]
        except Exception: pass
        try: out["btc_gunluk_tx"] = get("https://api.blockchain.info/stats", ttl=3600)["n_tx"]
        except Exception: pass
    if symbol.startswith("ETH"):
        try:
            t = get("https://api.llama.fi/v2/historicalChainTvl/Ethereum", ttl=3600)
            out["eth_tvl_bn"] = t[-1]["tvl"] / 1e9; out["eth_tvl_7g_%"] = (t[-1]["tvl"] / t[-8]["tvl"] - 1) * 100
        except Exception: pass
    return out

def text(symbol, df, interval="1d"):
    d, ob, oc, vs = derivatives(symbol, interval), orderbook(symbol), onchain(symbol), volume_spike(df)
    L = []
    if d.get("long_short"): L.append(f"Long/short hesap oranı ({d['source']}): şimdi {d['long_short'][0]:.2f}, {len(d['long_short'])-1} periyot önce {d['long_short'][-1]:.2f}")
    if d.get("taker_buy_sell"): L.append(f"Taker alış/satış hacim oranı (son 24 periyot): {d['taker_buy_sell']:.2f}")
    if d.get("liq"):
        import liq; t = liq.text(d["liq"])
        if t: L.append(t)
    if ob: L.append(f"Emir defteri (Binance spot): spread {ob['spread_bps']:.2f} bps, dengesizlik ±%0.5: {ob['imb_0.5%']:+.2f}, ±%1: {ob['imb_1.0%']:+.2f} (+ = alıcı ağırlıklı)")
    if vs: L.append(f"Hacim sıçraması: son mum hacmi / önceki 20 mum ort. = {vs:.2f}x")
    if oc: L.append("Zincir üstü/akış: " + ", ".join(f"{k}={v:,.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in oc.items()))
    return "\n".join(L), {"derivatives": d, "orderbook": ob, "onchain": oc, "volume_spike": vs}
