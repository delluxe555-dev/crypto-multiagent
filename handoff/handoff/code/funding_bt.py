#!/usr/bin/env python3
"""funding_bt.py - combo_bt2 motorunun islem-duzeyi (trade-level) yeniden uretimi + funding maliyeti/kazanci + basit zorunlu likidasyon.
combo_bt / combo_bt2 DEGISTIRILMEDI; combo_bt'yi salt-okunur import eder. sim3 = combo_bt2.sim2 ile AYNI islem mantigi (giris: sonraki bar acilisi, stop belirsizlikte kazanir,
HTF = son kapanmis HTF mumu, coin/combo basina tek pozisyon) + cikis zamani + MAE (en kotu aleyhte sapma, giris fiyatina oran).
Fikir notu: funding/likidasyon modellemesi icin freqtrade'den KOD ALINMADI (GPL); formuller standart perp mekanigi (Gate/OKX dokumani) ve burada sifirdan yazildi.

Alt komutlar:
  python3 funding_bt.py build      # 29 coin x 6 pair x 3 cfg x 35 combo islem tablosu -> outputs/research/trades_r2.npz   (+ dogrulama: n == r2_agg.csv.gz)
  python3 funding_bt.py fetch      # Gate (esas, ~150g) + OKX (capraz kontrol, ~96g) funding gecmisi -> outputs/research/funding/
  python3 funding_bt.py report     # funding + likidasyon ile yeniden olcum -> outputs/research_C_funding_bt.md

MODEL VARSAYIMLARI
 * Funding: islem [t_in, t_out] araliginda dusen her uzlasma (settlement) t icin t_in < t <= t_out. Long, oran>0 iken oder; short alir. Ucret = notional x oran.
   R birimi: funding_R = -dir * toplam_oran * (e/sd)   (e/sd = 1/stop-mesafesi; notional = risk/stop-mesafesi).
   Fiyat serisi Binance SPOT; funding Gate perp'ten (Binance perp funding'e bu sunucudan erisim yok) -> proxy. Coinlerin Gate perp'i olmayan donemi 0 sayilir.
 * Likidasyon (izole marjin, sabit kaldirac L): likidasyon mesafesi = 1/L - mmr (mmr = Gate sozlesmesinin 'maintenance_rate'i; BTC 0.3%, PEPE 0.65% vb.).
   Islemin MAE'si >= bu mesafe ise (stop'tan ONCE ya da stop yoksa) zorunlu likidasyon: kayip = tum teminat = 1/L notional = -(e/sd)/L R (ek likidasyon harci yok sayildi).
   MAE bar ici sirayi bilmez -> hedef cikisi olan barin dip/tepesi de MAE'ye dahil (temkinli). Senaryolar L=5,10,20; 'stop-oncesi-likidasyon' sadece genis stoplarda (S3) isler.
"""
import sys, os, json, time, numpy as np, pandas as pd
sys.path.insert(0, "/workspace/crypto-agents")
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f"{HERE}/outputs/research"; FUND = f"{RES}/funding"
def _m():
    import combo_bt as m; return m
PAIRS = [("15m","1h"),("15m","2h"),("30m","2h"),("30m","4h"),("45m","2h"),("45m","4h")]
CFGS = {"S1.5/T3/24h": (1.5,3.0,24), "S2/T4/48h": (2.0,4.0,48), "S3/T6/72h": (3.0,6.0,72)}
CUT = pd.Timestamp("2026-09-05 00:00", tz="UTC")

def sim3(d, ltf, L, Sg, sa, ta, hh, tfmin):
    o,h,l,c,a = d.o.values,d.h.values,d.l.values,d.c.values,d.atr.values; N=len(d); mh=hh*60//tfmin; idx=d.index.as_unit('s').asi8; out=[]; i=250
    while i<N-2:
        dr = 1 if L[i] else (-1 if Sg[i] else 0)
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
        adv = (e-l[i+1:j+1].min())/e if dr==1 else (h[i+1:j+1].max()-e)/e
        out.append((idx[i+1], idx[j]+tfmin*60, dr, g, e/sd, max(adv,0.0))); i=j+1
    return out

def work(coin): return work_df(coin,None)
def work_df(coin,df=None):
    m=_m(); df=m.load(coin) if df is None else df; rows=[]
    for pi,(ltf,htf) in enumerate(PAIRS):
        d=m.build(df,ltf,htf); rng=np.random.default_rng(abs(sum(map(ord,coin)))+7); S=m.sig(d,rng)
        for ci,(cn,(sa,ta,hh)) in enumerate(CFGS.items()):
            for ki,(name,(fam,L,Sg)) in enumerate(S.items()):
                for t in sim3(d,ltf,L,Sg,sa,ta,hh,m.TFMIN[ltf]): rows.append((pi,ci,ki,)+t)
        if pi==0: names=list(S.keys())
    A=np.array(rows,dtype=np.float64); print("done",coin,len(A),flush=True); return coin,names,A

def build(nproc=3):
    from multiprocessing import Pool
    import combo_bt2 as b2
    coins=b2.COINS
    with Pool(nproc) as p: res=p.map(work,coins)
    names=res[0][1]; T=[]; cid=[]
    for ci,(c,nm,A) in enumerate(res): assert nm==names; T.append(A); cid.append(np.full(len(A),ci))
    T=np.vstack(T); cid=np.concatenate(cid)
    np.savez_compressed(f"{RES}/trades_r2.npz", pair=T[:,0].astype(np.int8), cfg=T[:,1].astype(np.int8), combo=T[:,2].astype(np.int8), t_in=T[:,3].astype(np.int64), t_out=T[:,4].astype(np.int64),
                        dir=T[:,5].astype(np.int8), g=T[:,6], k=T[:,7], mae=T[:,8], coin=cid.astype(np.int8), coins=np.array(coins), combos=np.array(names), pairs=np.array([f"{a}/{b}" for a,b in PAIRS]), cfgs=np.array(list(CFGS)))
    # dogrulama: r2_agg ile islem sayisi
    A=pd.read_csv(f"{HERE}/outputs/combo_bt/r2_agg.csv.gz"); ref=A.groupby(["pair","cfg","combo"]).n.sum()
    df=pd.DataFrame(dict(pair=np.array([f"{a}/{b}" for a,b in PAIRS])[T[:,0].astype(int)], cfg=np.array(list(CFGS))[T[:,1].astype(int)], combo=np.array(names)[T[:,2].astype(int)]))
    mine=df.groupby(["pair","cfg","combo"]).size(); j=pd.concat([ref.rename("ref"),mine.rename("mine")],axis=1).fillna(0)
    print("hucre",len(j),"| n farkli hucre:",int((j.ref!=j.mine).sum()),"| toplam ref",int(j.ref.sum()),"mine",int(j.mine.sum()))

if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else ""
    if cmd=="build": build(int(sys.argv[2]) if len(sys.argv)>2 else 3)
    elif cmd in ("fetch","report"): import funding_bt_part2 as P2; getattr(P2,cmd)()
