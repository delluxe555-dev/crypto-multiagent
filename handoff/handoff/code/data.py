"""Ücretsiz, anahtarsız veri kaynakları: Binance spot (data-api.binance.vision), OKX funding, alternative.me F&G."""
import os, time, requests, pandas as pd

SPOT_URLS = ["https://api.binance.com", "https://data-api.binance.vision"]

def _get(url, params=None, timeout=15):
    r = requests.get(url, params=params, timeout=timeout); r.raise_for_status(); return r.json()

def klines(symbol, interval="1d", limit=400, end_ms=None):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if end_ms: params["endTime"] = end_ms
    last = None
    for base in SPOT_URLS:
        try:
            data = _get(base + "/api/v3/klines", params)
            if isinstance(data, list): break
        except Exception as e:
            last = e
    else:
        raise RuntimeError(f"Binance klines erişilemedi: {last}")
    df = pd.DataFrame(data, columns=["open_time","open","high","low","close","volume","close_time",
                                     "qv","trades","tb","tq","ig"])
    for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["date"] = ts.dt.date if interval == "1d" else ts.dt.strftime("%Y-%m-%d %H:%M")
    df = df[df["close_time"].astype("int64") < int(time.time()*1000)]  # kapanmamış mumu at
    return df[["date","open","high","low","close","volume"]].reset_index(drop=True)

def add_indicators(df):
    c = df["close"]
    d = c.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/14, adjust=False).mean() / dn.ewm(alpha=1/14, adjust=False).mean()
    df["rsi14"] = 100 - 100/(1+rs)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["sma50"] = c.rolling(50).mean(); df["sma200"] = c.rolling(200).mean()
    tr = pd.concat([df["high"]-df["low"], (df["high"]-c.shift()).abs(), (df["low"]-c.shift()).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    return df

def funding(symbol):
    """Önce Binance futures, olmazsa OKX perpetual funding (son 9 periyot ~3 gün)."""
    try:
        j = _get("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": symbol, "limit": 9})
        if isinstance(j, list) and j:
            return {"source": "binance-futures", "rates": [float(x["fundingRate"]) for x in j]}
    except Exception: pass
    try:
        inst = symbol.replace("USDT", "-USDT-SWAP")
        j = _get("https://www.okx.com/api/v5/public/funding-rate-history", {"instId": inst, "limit": 9})
        rates = [float(x["realizedRate"] or x["fundingRate"]) for x in j.get("data", [])]
        if rates: return {"source": "okx-swap", "rates": rates[::-1]}
    except Exception: pass
    return None

def open_interest(symbol, interval="1d"):
    """OKX toplam kontrat açık pozisyon (USD) geçmişi; son ~24 periyot."""
    try:
        period = {"15m": "5m", "1h": "1H", "4h": "1H"}.get(interval, "1D")
        j = _get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume",
                 {"ccy": symbol.replace("USDT", ""), "period": period})
        rows = [(int(r[0]), float(r[1])) for r in j.get("data", [])][:24]
        return {"source": "okx-rubik", "period": period, "oi_usd": [v for _, v in rows]}  # yeniden eskiye
    except Exception:
        return None

def fear_greed(days=30):
    try:
        j = _get("https://api.alternative.me/fng/", {"limit": days})
        return [(time.strftime("%Y-%m-%d", time.gmtime(int(x["timestamp"]))), int(x["value"]), x["value_classification"]) for x in j["data"]]
    except Exception:
        return None

def snapshot(symbol, df, i=None, fng=None, fund=None, oi=None, interval="1d"):
    """Satır i (varsayılan son) için ajanlara verilecek kompakt veri metni."""
    i_given = i
    if i is None: i = len(df)-1
    r = df.iloc[i]; c = df["close"]
    ch = lambda n: (r.close / c.iloc[i-n] - 1)*100 if i-n >= 0 else float("nan")
    last10 = df.iloc[max(0,i-9):i+1][["date","close","volume"]]
    lines = [f"Sembol: {symbol}  Mum aralığı: {interval}  Mum zamanı (UTC): {r.date}",
             f"Kapanış: {r.close:,.2f}  Değişim — 1 mum: {ch(1):+.2f}%  7 mum: {ch(7):+.2f}%  30 mum: {ch(30):+.2f}%  90 mum: {ch(90):+.2f}%",
             f"RSI14: {r.rsi14:.1f}  MACD: {r.macd:.2f}  Sinyal: {r.macd_signal:.2f}  Hist: {r.macd_hist:.2f} (önceki mum hist: {df.macd_hist.iloc[i-1]:.2f})",
             f"SMA50: {r.sma50:,.2f}  SMA200: {r.sma200:,.2f}  ATR14: {r.atr14:,.2f}",
             f"Son 30 mum en yüksek/düşük: {df.high.iloc[max(0,i-29):i+1].max():,.2f} / {df.low.iloc[max(0,i-29):i+1].min():,.2f}",
             "Son 10 mum kapanış: " + ", ".join(f"{str(d)[5:]}:{v:,.0f}" for d, v in zip(last10.date, last10.close))]
    try:
        import levels
        st = levels.text(df, i, interval)
        if st: lines.append(st)
    except Exception as e:
        lines.append(f"Yapı göstergeleri hesaplanamadı: {e}")
    try:
        import patterns
        pt = patterns.text(df, i, interval)
        if pt: lines.append(pt)
    except Exception as e:
        lines.append(f"Formasyon göstergeleri hesaplanamadı: {e}")
    if i_given is None and os.environ.get("CA_NO_KEYLEVELS") != "1":   # kullanıcı kritik seviyesi (yalnızca canlı akış; backtest'te kapalı: look-ahead olmasın)
        try:
            import keylevels
            kt = keylevels.text(symbol, df, interval)
            if kt: lines.append(kt)
        except Exception as e:
            lines.append(f"Kritik seviye satırı hesaplanamadı: {e}")
    tech = "\n".join(lines)
    s = []
    if fund:
        rates = fund["rates"]; s.append(f"Funding ({fund['source']}, son {len(rates)} periyot, 8s): " + ", ".join(f"{x*100:.4f}%" for x in rates)
                                       + f"  ort: {sum(rates)/len(rates)*100:.4f}%")
    else: s.append("Funding verisi yok.")
    if oi and oi["oi_usd"]:
        v = oi["oi_usd"]; s.append(f"Açık pozisyon (OKX, periyot {oi['period']}): şimdi {v[0]/1e9:.2f} mlr $, "
                                   f"{len(v)-1} periyot önce {v[-1]/1e9:.2f} mlr $ ({(v[0]/v[-1]-1)*100:+.1f}%)")
    if fng: s.append("Korku&Açgözlülük (yeniden eskiye): " + ", ".join(f"{d}:{v}({k})" for d, v, k in fng[:10]))
    else: s.append("Korku&Açgözlülük verisi yok.")
    return tech, "\n".join(s)
