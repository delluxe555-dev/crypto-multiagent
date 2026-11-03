"""Round 2: entry TF 15m/30m/45m, HTF 1h/2h/4h, wider ATR stop/target, longer hold, 29 coins. Aggregated output only.
45m bars: 9x5m bars aligned to UTC-midnight grid (32 bars/day), NOT to the hour grid (bars start 00:00,00:45,01:30,...)."""
import sys, os, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0,"/workspace/crypto-agents")
import combo_bt as m
OUT=m.OUT
COINS=[f.split("_5m")[0] for f in sorted(os.listdir(OUT)) if f.endswith("_5m.csv.gz")]
PAIRS=[("15m","1h"),("15m","2h"),("30m","2h"),("30m","4h"),("45m","2h"),("45m","4h")]
CFGS={"S1.5/T3/24h":(1.5,3.0,24),"S2/T4/48h":(2.0,4.0,48),"S3/T6/72h":(3.0,6.0,72)}
CUT=pd.Timestamp("2026-09-05 00:00",tz="UTC")
C_HI,C_LO=0.003,0.001   # round trip: 0.15%/side and 0.05%/side (fee+slippage)

def sim2(d,ltf,L,Sg,sa,ta,hh):
    o,h,l,c,a=d.o.values,d.h.values,d.l.values,d.c.values,d.atr.values; N=len(d); mh=hh*60//m.TFMIN[ltf]; tr=[]; idx=d.index
    i=250
    while i<N-2:
        dr=1 if L[i] else (-1 if Sg[i] else 0)
        if dr==0 or np.isnan(a[i]) or a[i]<=0: i+=1; continue
        e=o[i+1]; sd=sa*a[i]; td=ta*a[i]; stp=e-dr*sd; tgt=e+dr*td; ex=None; j=i+1; last=min(N-1,i+mh)
        for j in range(i+1,last+1):
            if dr==1:
                if l[j]<=stp: ex=stp; break
                if h[j]>=tgt: ex=tgt; break
            else:
                if h[j]>=stp: ex=stp; break
                if l[j]<=tgt: ex=tgt; break
        if ex is None: ex=c[j]
        g=dr*(ex-e)/sd
        tr.append((idx[i+1],dr,g,g-C_HI*e/sd,g-C_LO*e/sd)); i=j+1
    return tr

def work(coin):
    df=m.load(coin); rows=[]
    for ltf,htf in PAIRS:
        d=m.build(df,ltf,htf); rng=np.random.default_rng(abs(sum(map(ord,coin)))+7)
        S=m.sig(d,rng)
        for name,(fam,L,Sg) in S.items():
            for cn,(sa,ta,hh) in CFGS.items():
                for t,dr,g,nh,nl in sim2(d,ltf,L,Sg,sa,ta,hh):
                    rows.append((f"{ltf}/{htf}",cn,name,fam,coin,dr,t>=CUT,g,nh,nl))
    T=pd.DataFrame(rows,columns="pair cfg combo family coin dir oos g nh nl".split())
    T["g2"]=T.g**2; T["nh2"]=T.nh**2
    T["wh"]=(T.nh>0).astype(int); T["wl"]=(T.nl>0).astype(int)
    T["ph"]=T.nh.clip(lower=0); T["mh_"]=(-T.nh).clip(lower=0); T["pl"]=T.nl.clip(lower=0); T["ml"]=(-T.nl).clip(lower=0)
    T["n"]=1
    A=T.groupby(["pair","cfg","combo","family","coin","dir","oos"])[["n","g","g2","nh","nh2","nl","wh","wl","ph","mh_","pl","ml"]].sum().reset_index()
    print("done",coin,len(T),flush=True); return A
if __name__=="__main__":
    print(len(COINS),COINS,flush=True)
    with Pool(8) as p: res=p.map(work,COINS)
    pd.concat(res).to_csv(f"{OUT}/r2_agg.csv.gz",index=False); print("saved")
