import requests, pandas as pd, time, os, sys
from concurrent.futures import ThreadPoolExecutor
OUT="/workspace/crypto-agents/outputs/combo_bt"
COINS=["NEAR","ETH","BTC","SOL","DOGE","SUI","WLD","TIA","ONDO","BNB","XRP","AVAX","LINK","ARB","INJ"]
DAYS=150
def fetch(sym):
    f=f"{OUT}/{sym}_5m.csv.gz"
    if os.path.exists(f): return sym
    end=int(time.time()*1000); start=end-DAYS*86400000
    rows=[]; t=start
    while t<end:
        for base in ["https://data-api.binance.vision","https://api.binance.com"]:
            try:
                r=requests.get(base+"/api/v3/klines",params={"symbol":sym+"USDT","interval":"5m","startTime":t,"limit":1000},timeout=20); r.raise_for_status(); d=r.json(); break
            except Exception as e: d=None; time.sleep(1)
        if not d: break
        rows+=d; t=d[-1][0]+300000
        if len(d)<1000: break
    df=pd.DataFrame(rows,columns="t o h l c v ct qv n tb tq ig".split())
    for c in "ohlcv": df[c]=df[c].astype(float)
    df["t"]=pd.to_datetime(df["t"],unit="ms",utc=True)
    df=df[["t","o","h","l","c","v"]].drop_duplicates("t").set_index("t")
    df=df.iloc[:-1]  # drop possibly open candle
    df.to_csv(f); return sym
with ThreadPoolExecutor(4) as ex:
    for s in ex.map(fetch,COINS): 
        d=pd.read_csv(f"{OUT}/{s}_5m.csv.gz",index_col=0,parse_dates=True); print(s,len(d),d.index[0],d.index[-1])
