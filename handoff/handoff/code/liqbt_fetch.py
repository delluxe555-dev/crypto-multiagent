import json, os, time, requests
G="https://api.gateio.ws/api/v4/futures/usdt"; D="liqbt_cache"
COINS="ARB NEAR ETH BTC ETHFI GRASS SOL DOGE XRP AVAX LINK APT SUI INJ OP WLD TIA SEI ATOM DOT FET ADA LTC BNB PYTH JUP".split()
def get(u,p=None):
    for _ in range(4):
        r=requests.get(u,params=p,timeout=25)
        if r.status_code==429: time.sleep(2); continue
        r.raise_for_status(); return r.json()
for c in COINS:
    f=f"{D}/{c}.json"
    if os.path.exists(f): continue
    try:
        ct=get(f"{G}/contracts/{c}_USDT")
        st=get(f"{G}/contract_stats",{"contract":f"{c}_USDT","interval":"15m","limit":2000})
        cd=get(f"{G}/candlesticks",{"contract":f"{c}_USDT","interval":"15m","limit":2000})
        json.dump({"ct":ct,"st":st,"cd":cd},open(f,"w")); print(c,len(st),len(cd),ct.get("maintenance_rate"),ct.get("leverage_max"))
    except Exception as e: print(c,"ERR",str(e)[:80])
    time.sleep(0.3)
