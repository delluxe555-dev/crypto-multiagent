import sys; sys.argv=["x"]
import re
src=open("/workspace/crypto-agents/combo_fetch.py").read().split("with ThreadPoolExecutor")[0]
exec(src)
NEW=["APT","OP","FIL","ATOM","DOT","LTC","ADA","TRX","PEPE","SEI","FET","RENDER","JUP","AAVE"]
def safe(s):
    try: return fetch(s)
    except Exception as e: print("FAIL",s,e); return None
with ThreadPoolExecutor(4) as ex:
    for s in ex.map(safe,NEW):
        if s:
            d=pd.read_csv(f"{OUT}/{s}_5m.csv.gz",index_col=0,parse_dates=True); print(s,len(d),d.index[0],d.index[-1])
