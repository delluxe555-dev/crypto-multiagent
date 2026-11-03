"""Multi-family, multi-timeframe combo backtest. Standard default params, no per-run tuning.
Entry: next bar open after closed signal bar. Stop 1.5 ATR, target 3 ATR, max hold 24h. Fees 0.10% + slip 0.05% per side.
HTF values come only from last CLOSED HTF candle. One open position per coin per combo."""
import os, sys, json, numpy as np, pandas as pd
OUT="/workspace/crypto-agents/outputs/combo_bt"
COINS=["NEAR","ETH","BTC","SOL","DOGE","SUI","WLD","TIA","ONDO","BNB","XRP","AVAX","LINK","ARB","INJ"]
PAIRS=[("5m","1h"),("15m","1h"),("15m","2h")]
STOP_ATR,TGT_ATR=1.5,3.0
COST=0.0015*2     # round trip fraction (fee+slip, both sides)
COST_LOW=0.0005*2 # sensitivity (futures-like)
TFMIN={"5m":5,"15m":15,"30m":30,"45m":45,"1h":60,"2h":120,"4h":240}

def load(c): return pd.read_csv(f"{OUT}/{c}_5m.csv.gz",index_col=0,parse_dates=True)
def rs(df,tf):
    r=df.resample(f"{TFMIN[tf]}min",label="left",closed="left").agg({"o":"first","h":"max","l":"min","c":"last","v":"sum"})
    n=df["c"].resample(f"{TFMIN[tf]}min",label="left",closed="left").count()
    return r[n==TFMIN[tf]//5].dropna()
def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rma(s,n): return s.ewm(alpha=1/n,adjust=False).mean()
def atr(d,n=14):
    tr=pd.concat([d.h-d.l,(d.h-d.c.shift()).abs(),(d.l-d.c.shift()).abs()],axis=1).max(axis=1); return rma(tr,n)
def rsi(c,n=14):
    d=c.diff(); return 100-100/(1+rma(d.clip(lower=0),n)/rma((-d).clip(lower=0),n).replace(0,np.nan))
def supertrend(d,n=10,m=3.0):
    a=atr(d,n).values; h=d.h.values; l=d.l.values; c=d.c.values; N=len(c)
    hl2=(h+l)/2; ub=hl2+m*a; lb=hl2-m*a; fu=ub.copy(); fl=lb.copy(); dr=np.ones(N)
    for i in range(1,N):
        if np.isnan(a[i]): continue
        fu[i]=ub[i] if (ub[i]<fu[i-1] or c[i-1]>fu[i-1]) else fu[i-1]
        fl[i]=lb[i] if (lb[i]>fl[i-1] or c[i-1]<fl[i-1]) else fl[i-1]
        if dr[i-1]==1: dr[i]=-1 if c[i]<fl[i] else 1
        else: dr[i]=1 if c[i]>fu[i] else -1
    s=pd.Series(dr,index=d.index); s[np.isnan(a)]=0; return s
def qqe(c,rl=6,sf=5,q=3.0,bbl=50,bbm=0.35,th=3.0):
    r=rsi(c,rl); rm=ema(r,sf).values; w=rl*2-1
    ar=pd.Series(np.abs(np.r_[np.nan,np.diff(rm)])); dar=(ema(ema(ar,w),w)*q).values
    N=len(rm); lb=np.full(N,np.nan); sb=np.full(N,np.nan); tl=np.full(N,np.nan); tr=1
    for i in range(1,N):
        if np.isnan(dar[i]) or np.isnan(rm[i]): continue
        nl,ns=rm[i]-dar[i],rm[i]+dar[i]
        pl=lb[i-1] if not np.isnan(lb[i-1]) else nl; ps=sb[i-1] if not np.isnan(sb[i-1]) else ns
        lb[i]=max(pl,nl) if (rm[i-1]>pl and rm[i]>pl) else nl
        sb[i]=min(ps,ns) if (rm[i-1]<ps and rm[i]<ps) else ns
        if rm[i-1]<=ps and rm[i]>ps: tr=1
        elif rm[i-1]>=pl and rm[i]<pl: tr=-1
        tl[i]=lb[i] if tr==1 else sb[i]
    tl=pd.Series(tl,index=c.index)-50; basis=tl.rolling(bbl).mean(); dev=bbm*tl.rolling(bbl).std()
    h=pd.Series(rm,index=c.index)-50
    up=(h>th)&(h>basis+dev); dn=(h<-th)&(h<basis-dev)
    return up.astype(int)-dn.astype(int)

def camarilla(df,key):
    g=df.groupby(key).agg(H=("h","max"),L=("l","min"),C=("c","last")).shift(1)
    R=g.H-g.L; out={}
    for nm,k in [("H3",1.1/4),("H4",1.1/2),("L3",-1.1/4),("L4",-1.1/2)]: out[nm]=(g.C+R*k)
    out["PH"]=g.H; out["PL"]=g.L
    return pd.DataFrame(out)

def build(df5,ltf,htf):
    d=rs(df5,ltf).copy(); c=d.c
    d["atr"]=atr(d); d["ema5"]=ema(c,5); d["ema21"]=ema(c,21); d["ma200"]=c.rolling(200).mean()
    d["st"]=supertrend(d); d["rsi"]=rsi(c); d["mom"]=c-c.shift(10)
    e12,e26=ema(c,12),ema(c,26); m=e12-e26; d["macdh"]=m-ema(m,9)
    d["qqe"]=qqe(c)
    rr=rsi(c); mn=rr.rolling(14).min(); mx=rr.rolling(14).max(); sr=((rr-mn)/(mx-mn).replace(0,np.nan)*100).rolling(3).mean()
    d["srk"]=sr; d["srd"]=sr.rolling(3).mean()
    bm=c.rolling(20).mean(); bs=c.rolling(20).std(); d["bbu"]=bm+2*bs; d["bbl"]=bm-2*bs; d["bbm"]=bm
    bw=(d.bbu-d.bbl)/bm; d["sqz"]=bw<=bw.rolling(200).quantile(0.2)
    day=d.index.floor("D"); tp=(d.h+d.l+c)/3
    d["vwap"]=(tp*d.v).groupby(day).cumsum()/d.v.groupby(day).cumsum()
    sgn=np.sign(c.diff()).fillna(0); d["obv"]=(sgn*d.v).cumsum(); d["obve"]=ema(d["obv"],20)
    mfm=((c-d.l)-(d.h-c))/(d.h-d.l).replace(0,np.nan); d["cmf"]=(mfm*d.v).rolling(20).sum()/d.v.rolling(20).sum()
    pos=(tp*d.v).where(tp>tp.shift(),0).rolling(14).sum(); neg=(tp*d.v).where(tp<tp.shift(),0).rolling(14).sum()
    d["mfi"]=100-100/(1+pos/neg.replace(0,np.nan))
    sma_tp=tp.rolling(20).mean(); md=(tp-sma_tp).abs().rolling(20).mean(); d["cci"]=(tp-sma_tp)/(0.015*md)
    d["dhi"]=d.h.rolling(20).max().shift(1); d["dlo"]=d.l.rolling(20).min().shift(1)
    d["vspike"]=d.v>2*d.v.rolling(20).mean()
    # Camarilla daily/weekly (previous completed period)
    dk=camarilla(df5,df5.index.floor("D"))
    wk=camarilla(df5,df5.index.floor("D")-pd.to_timedelta(df5.index.dayofweek,"D"))
    for pre,cm,key in [("d",dk,day),("w",wk,day-pd.to_timedelta(d.index.dayofweek,"D"))]:
        for col in cm.columns: d[f"{pre}{col}"]=cm[col].reindex(key).values
    # HTF (closed candles only): value at HTF close time
    h=rs(df5,htf).copy(); hf=pd.DataFrame(index=h.index)
    hf["h_st"]=supertrend(h); hf["h_ema50"]=h.c>ema(h.c,50); hf["h_rsi"]=rsi(h.c); hf["h_c"]=h.c
    hm=ema(h.c,12)-ema(h.c,26); hf["h_macdh"]=hm-ema(hm,9); hf["h_mom"]=h.c-h.c.shift(10)
    hf.index=hf.index+pd.Timedelta(minutes=TFMIN[htf]); hf=hf.reset_index().rename(columns={"t":"_ct","index":"_ct"})
    lt=pd.DataFrame({"_ct":d.index+pd.Timedelta(minutes=TFMIN[ltf])},index=d.index)
    mg=pd.merge_asof(lt.reset_index(),hf,on="_ct",direction="backward").set_index(lt.index.name or "t")
    for col in hf.columns:
        if col!="_ct": d[col]=mg[col].values
    return d

def edge(x): x=pd.Series(x).fillna(False).astype(bool); return (x&~x.shift(fill_value=False)).values
def sig(d,rng):
    S={}; c,h,l,o=d.c,d.h,d.l,d.o; a=d.atr
    up,dn=d.h_st==1,d.h_st==-1
    uptr=up&(d.h_ema50==True); dntr=dn&(d.h_ema50==False)
    def add(n,fam,L,S_): S[n]=(fam,np.asarray(edge(L)),np.asarray(edge(S_)))
    def addraw(n,fam,L,S_): S[n]=(fam,np.asarray(L.fillna(False)),np.asarray(S_.fillna(False)))
    # --- baselines
    N=len(d); r1=rng.random(N); r2=rng.random(N)
    R1=pd.Series(r1,index=d.index); R2=pd.Series(r2,index=d.index)
    addraw("BASE_random",         "baseline",R1<0.02,(R1>=0.02)&(R2<0.02))
    addraw("BASE_HTFtrend_random","baseline",(R1<0.02)&up,(R2<0.02)&dn)
    mc_u=(d.macdh>0)&(d.macdh.shift()<=0); mc_d=(d.macdh<0)&(d.macdh.shift()>=0)
    addraw("BASE_MACDcross+HTF","baseline",mc_u&up,mc_d&dn)
    addraw("BASE_MACDcross_noHTF","baseline",mc_u,mc_d)
    # --- trend
    xu=(d.ema5>d.ema21)&(d.ema5.shift()<=d.ema21.shift()); xd=(d.ema5<d.ema21)&(d.ema5.shift()>=d.ema21.shift())
    addraw("T1_EMA5/21cross+MA200+HTF","trend",xu&(c>d.ma200)&up,xd&(c<d.ma200)&dn)
    addraw("T2_ST_flip+HTF_ST","trend",(d.st==1)&(d.st.shift()==-1)&up,(d.st==-1)&(d.st.shift()==1)&dn)
    addraw("T3_MA200cross+MOM+HTF","trend",(c>d.ma200)&(c.shift()<=d.ma200.shift())&(d.mom>0)&up,(c<d.ma200)&(c.shift()>=d.ma200.shift())&(d.mom<0)&dn)
    addraw("T4_Donchian20brk+HTF","trend",(c>d.dhi)&up,(c<d.dlo)&dn)
    # --- momentum
    addraw("M1_QQE_flip+HTF","momentum",(d.qqe==1)&(d.qqe.shift()!=1)&up,(d.qqe==-1)&(d.qqe.shift()!=-1)&dn)
    ku=(d.srk>d.srd)&(d.srk.shift()<=d.srd.shift())&(d.srk<30); kd=(d.srk<d.srd)&(d.srk.shift()>=d.srd.shift())&(d.srk>70)
    addraw("M2_StochRSI_cross_OS/OB+HTF","momentum",ku&up,kd&dn)
    addraw("M3_RSIpullback_reclaim40/60+HTF","momentum",(d.rsi>40)&(d.rsi.shift()<=40)&up,(d.rsi<60)&(d.rsi.shift()>=60)&dn)
    addraw("M4_MOMzero+EMA5>21+MA200","momentum",(d.mom>0)&(d.mom.shift()<=0)&(d.ema5>d.ema21)&(c>d.ma200)&up,(d.mom<0)&(d.mom.shift()>=0)&(d.ema5<d.ema21)&(c<d.ma200)&dn)
    addraw("M5_CCI_reclaim-100/+100+HTF","momentum",(d.cci>-100)&(d.cci.shift()<=-100)&up,(d.cci<100)&(d.cci.shift()>=100)&dn)
    # --- levels / pivots
    tl3=(l<=d.dL3)&(c>d.dL3)&(c>o); th3=(h>=d.dH3)&(c<d.dH3)&(c<o)
    addraw("L1_CamDaily_L3/H3reject+HTF","levels",tl3&up,th3&dn)
    addraw("L2_CamDaily_L3/H3reject_counterHTF","levels",tl3&dn,th3&up)
    addraw("L3_CamDaily_H4/L4break+MOM+HTF","levels",(c>d.dH4)&(c.shift()<=d.dH4.shift())&(d.mom>0)&up,(c<d.dL4)&(c.shift()>=d.dL4.shift())&(d.mom<0)&dn)
    addraw("L4_CamDaily_L4/H4extreme_fade","levels",(l<=d.dL4)&(c>d.dL4)&(c>o),(h>=d.dH4)&(c<d.dH4)&(c<o))
    tw=(l<=d.wL3)&(c>d.wL3)&(c>o); thw=(h>=d.wH3)&(c<d.wH3)&(c<o)
    addraw("L5_CamWeekly_L3/H3reject+HTF","levels",tw&up,thw&dn)
    addraw("L6_PrevDayHL_break+HTF+MOM","levels",(c>d.dPH)&(c.shift()<=d.dPH.shift())&(d.mom>0)&up,(c<d.dPL)&(c.shift()>=d.dPL.shift())&(d.mom<0)&dn)
    addraw("L7_CamL3reject+StochRSIcross+HTF","levels",((l.rolling(3).min()<=d.dL3)&(c>d.dL3)&ku.rolling(3).max().astype(bool))&up,((h.rolling(3).max()>=d.dH3)&(c<d.dH3)&kd.rolling(3).max().astype(bool))&dn)
    # --- volatility
    addraw("V1_BBsqueeze_breakout+HTF","volatility",d.sqz.shift().fillna(False)&(c>d.bbu)&up,d.sqz.shift().fillna(False)&(c<d.bbl)&dn)
    addraw("V2_BBband_reentry+HTF","volatility",(c.shift()<d.bbl.shift())&(c>d.bbl)&up,(c.shift()>d.bbu.shift())&(c<d.bbu)&dn)
    addraw("V3_BBband_reentry_noHTF","volatility",(c.shift()<d.bbl.shift())&(c>d.bbl),(c.shift()>d.bbu.shift())&(c<d.bbu))
    # --- volume
    addraw("VO1_VWAPreclaim+StochRSI+HTF","volume",(c>d.vwap)&(c.shift()<=d.vwap.shift())&(d.srk>d.srd)&up,(c<d.vwap)&(c.shift()>=d.vwap.shift())&(d.srk<d.srd)&dn)
    addraw("VO2_Volspike_breakout+HTF","volume",d.vspike&(c>d.dhi)&up,d.vspike&(c<d.dlo)&dn)
    fu=(d.obv>d.obve)&(d.cmf>0)&(d.mfi>50); fd=(d.obv<d.obve)&(d.cmf<0)&(d.mfi<50)
    addraw("VO3_flow(OBV+CMF+MFI)agree+EMApullback+HTF","volume",fu&(l<=d.ema21)&(c>d.ema21)&up,fd&(h>=d.ema21)&(c<d.ema21)&dn)
    # --- ensembles: majority vote
    v={"st":d.st,"ema":np.sign(d.ema5-d.ema21),"ma200":np.sign(c-d.ma200),"mom":np.sign(d.mom),"rsi":np.sign(d.rsi-50),
       "macd":np.sign(d.macdh),"qqe":d.qqe,"vwap":np.sign(c-d.vwap)}
    V8=sum(v.values()); V7=V8-v["macd"]
    fl={"obv":np.sign(d.obv-d.obve),"cmf":np.sign(d.cmf),"srk":np.sign(d.srk-d.srd),"bbm":np.sign(c-d.bbm)}
    V11=V7+sum(fl.values())
    add("E1_vote7of8_trend/mom(MACD incl)","ensemble",V8>=6,V8<=-6)
    add("E2_vote6of7(noMACD)","ensemble",V7>=6,V7<=-6)
    add("E3_vote6of7(noMACD)+HTF","ensemble",(V7>=5)&up,(V7<=-5)&dn)
    add("E4_vote9of11(+flow,stoch,bbmid)","ensemble",V11>=9,V11<=-9)
    add("E5_vote8of11+HTF","ensemble",(V11>=8)&up,(V11<=-8)&dn)
    add("E6_vote_majority6of11_pullbackEMA21+HTF","ensemble",(V11>=6)&(l<=d.ema21)&(c>d.ema21)&up,(V11<=-6)&(h>=d.ema21)&(c<d.ema21)&dn)
    os_=((d.rsi<30).astype(int)+(d.srk<15)+(d.cci<-100)+(d.mfi<20)+(c<d.bbl)+(d.cmf<-0.1))
    ob_=((d.rsi>70).astype(int)+(d.srk>85)+(d.cci>100)+(d.mfi>80)+(c>d.bbu)+(d.cmf>0.1))
    rv_l=(c>o); rv_s=(c<o)
    add("E7_OS/OB_vote4of6_reversal(noHTF)","ensemble",(os_>=4)&rv_l,(ob_>=4)&rv_s)
    add("E8_OS/OB_vote3of6_reversal+HTF","ensemble",(os_>=3)&rv_l&up,(ob_>=3)&rv_s&dn)
    lvl_l=((l<=d.dL3)|(l<=d.wL3)|(l<=d.vwap)&(c>d.vwap)); lvl_s=((h>=d.dH3)|(h>=d.wH3)|(h>=d.vwap)&(c<d.vwap))
    add("E9_vote6of11+level(Cam/VWAP)touch+HTF","ensemble",(V11>=6)&lvl_l&(c>o)&up,(V11<=-6)&lvl_s&(c<o)&dn)
    return S

def sim(d,ltf,L,Sg):
    o,h,l,c,a=d.o.values,d.h.values,d.l.values,d.c.values,d.atr.values; N=len(d); mh=24*60//TFMIN[ltf]; tr=[]
    i=250
    while i<N-2:
        dr=1 if L[i] else (-1 if Sg[i] else 0)
        if dr==0 or np.isnan(a[i]) or a[i]<=0: i+=1; continue
        e=o[i+1]; sd=STOP_ATR*a[i]; td=TGT_ATR*a[i]
        stp=e-dr*sd; tgt=e+dr*td; ex=None; j=i+1; last=min(N-1,i+mh)
        for j in range(i+1,last+1):
            if dr==1:
                if l[j]<=stp: ex=stp; break
                if h[j]>=tgt: ex=tgt; break
            else:
                if h[j]>=stp: ex=stp; break
                if l[j]<=tgt: ex=tgt; break
        if ex is None: ex=c[j]
        g=dr*(ex-e)/sd; cr=COST*e/sd; cl=COST_LOW*e/sd
        tr.append((d.index[i+1],dr,g,g-cr,g-cl)); i=j+1
    return tr

def stats(t):
    n=len(t)
    if n==0: return dict(n=0,win=np.nan,gross=np.nan,net=np.nan,pf=np.nan,netlow=np.nan,t=np.nan)
    r=t.net.values; w=r[r>0].sum(); ls=-r[r<0].sum()
    return dict(n=n,win=(t.net>0).mean(),gross=t.gross.mean(),net=r.mean(),pf=(w/ls if ls>0 else np.inf),netlow=t.netlow.mean(),
                t=(r.mean()/(r.std(ddof=1)/np.sqrt(n)) if n>2 and r.std()>0 else np.nan))

if __name__=="__main__":
    allt=[]; 
    data={c:load(c) for c in COINS}
    for ltf,htf in PAIRS:
        for coin in COINS:
            d=build(data[coin],ltf,htf); rng=np.random.default_rng(abs(hash(coin))%1000+1) if False else np.random.default_rng(COINS.index(coin)+7)
            for name,(fam,L,Sg) in sig(d,rng).items():
                for tt in sim(d,ltf,L,Sg):
                    allt.append((f"{ltf}/{htf}",name,fam,coin)+tt)
            print(ltf,htf,coin,len(allt),flush=True)
    T=pd.DataFrame(allt,columns="pair combo family coin t dir gross net netlow".split())
    T.to_csv(f"{OUT}/trades.csv.gz",index=False); print("saved",len(T))
