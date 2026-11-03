#!/usr/bin/env python3
"""Fetch Binance USDT-M perpetual klines from data.binance.vision (public bulk files; api fapi is geo-blocked here).
Monthly zips up to the last complete month + daily zips for the current month. Cached as parquet-like csv.gz per pair/timeframe in ./data. Only closed candles."""
import io, os, sys, zipfile, requests, pandas as pd, datetime as dt
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); D = f"{HERE}/data"
PAIRS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","NEAR","LTC","DOT"]
TFS = ["15m","1h","4h"]
BASE = "https://data.binance.vision/data/futures/um"
COLS = "t o h l c v ct qv n tb tq ig".split()
def get(url):
    for _ in range(3):
        r = requests.get(url, timeout=60)
        if r.status_code == 200: return r.content
        if r.status_code == 404: return None
    return None
def parse(b):
    z = zipfile.ZipFile(io.BytesIO(b)); df = pd.read_csv(z.open(z.namelist()[0]), header=None)
    if not str(df.iloc[0,0]).isdigit(): df = df.iloc[1:]
    df = df.iloc[:, :6]; df.columns = COLS[:6]; return df.astype(float)
def fetch(pair, tf):
    f = f"{D}/{pair}USDT_{tf}.csv.gz"
    if os.path.exists(f): return pair, tf
    sym = pair + "USDT"; today = dt.date.today(); parts = []
    y, m = 2019, 9
    while (y, m) < (today.year, today.month):
        b = get(f"{BASE}/monthly/klines/{sym}/{tf}/{sym}-{tf}-{y}-{m:02d}.zip")
        if b: parts.append(parse(b))
        m += 1
        if m > 12: y, m = y + 1, 1
    d = today.replace(day=1)
    while d < today:   # days of the current month up to yesterday
        b = get(f"{BASE}/daily/klines/{sym}/{tf}/{sym}-{tf}-{d.isoformat()}.zip")
        if b: parts.append(parse(b))
        d += dt.timedelta(days=1)
    df = pd.concat(parts).drop_duplicates("t").sort_values("t")
    df["t"] = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True); df.set_index("t").to_csv(f); return pair, tf
if __name__ == "__main__":
    os.makedirs(D, exist_ok=True)
    jobs = [(p, t) for p in PAIRS for t in TFS]
    with ThreadPoolExecutor(8) as ex:
        for p, t in ex.map(lambda a: fetch(*a), jobs):
            d = pd.read_csv(f"{D}/{p}USDT_{t}.csv.gz", index_col=0, parse_dates=True); print(p, t, len(d), d.index[0], d.index[-1], flush=True)
