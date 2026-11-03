import pandas as pd, numpy as np
OUT="/workspace/crypto-agents/outputs/combo_bt"
A=pd.read_csv(f"{OUT}/r2_agg.csv.gz")
pd.set_option("display.width",270,"display.max_rows",500,"display.max_columns",40)
def agg(g):
    n=g.n.sum()
    if n==0: return pd.Series(dtype=float)
    mg=g.g.sum()/n; vg=g.g2.sum()/n-mg**2
    return pd.Series(dict(n=n,win=g.wh.sum()/n,gross=mg,gross_t=mg/np.sqrt(max(vg,1e-12)/n),net_hi=g.nh.sum()/n,
        pf_hi=g.ph.sum()/max(g.mh_.sum(),1e-9),net_lo=g.nl.sum()/n,pf_lo=g.pl.sum()/max(g.ml.sum(),1e-9),win_lo=g.wl.sum()/n))
def table(keys,src=A):
    rows=[]
    for k,g in src.groupby(keys):
        a=agg(g); i=agg(g[~g.oos]); o=agg(g[g.oos])
        r=dict(zip(keys,k if isinstance(k,tuple) else (k,)))
        r.update(a.to_dict()); r.update(dict(n_is=i.get("n",0),gross_is=i.get("gross"),lo_is=i.get("net_lo"),hi_is=i.get("net_hi"),
              n_oos=o.get("n",0),gross_oos=o.get("gross"),lo_oos=o.get("net_lo"),hi_oos=o.get("net_hi"),pf_lo_oos=o.get("pf_lo")))
        c=g.groupby("coin")[["n","g","nl"]].sum(); r["coins_gross_pos"]=f"{(c.g>0).sum()}/{len(c)}"; r["coins_lo_pos"]=f"{(c.nl>0).sum()}/{len(c)}"
        rows.append(r)
    return pd.DataFrame(rows)
R=table(["pair","cfg","combo","family"]); R.to_csv(f"{OUT}/r2_by_pair_cfg_combo.csv",index=False)
R["pos_lo_both"]=(R.n>=50)&(R.n_oos>=30)&(R.lo_is>0)&(R.lo_oos>0)
R["pos_hi_both"]=(R.n>=50)&(R.n_oos>=30)&(R.hi_is>0)&(R.hi_oos>0)
print("coins",A.coin.nunique(),"cells",len(R),"base-excl cells",(R.family!="baseline").sum())
print("net-positive both halves @0.15%:",R.pos_hi_both.sum()," @0.05%:",R.pos_lo_both.sum())
f=lambda d:d.round(3)
cols=["pair","cfg","combo","n","win","gross","gross_t","net_hi","pf_hi","net_lo","pf_lo","lo_is","lo_oos","hi_oos","n_oos","coins_gross_pos","coins_lo_pos"]
print("\nBASELINES");print(f(R[R.family=="baseline"].groupby(["cfg","combo"])[["n","gross","net_hi","net_lo","lo_oos"]].mean()))
N=R[(R.family!="baseline")&(R.n>=50)]
print("\nTOP 25 by net_lo");print(f(N.sort_values("net_lo",ascending=False).head(25)[cols]))
print("\nPOS BOTH HALVES @0.05% (non-baseline)");print(f(R[R.pos_lo_both&(R.family!="baseline")].sort_values("net_lo",ascending=False)[cols]))
print("\nPOS BOTH HALVES @0.15%");print(f(R[R.pos_hi_both][cols]))
print("\nBy cfg (non-baseline mean of cells)");print(f(N.groupby("cfg")[["gross","net_hi","net_lo","lo_oos"]].mean()))
print("\nBy pair");print(f(N.groupby("pair")[["gross","net_hi","net_lo","lo_oos"]].mean()))
print("\nBy pair x cfg net_lo");print(f(N.pivot_table(index="pair",columns="cfg",values="net_lo")))
print("\nBy family x cfg net_lo");print(f(N.pivot_table(index="family",columns="cfg",values="net_lo")))
# by combo across pairs/cfg
C=N.groupby("combo").agg(family=("family","first"),gross=("gross","mean"),net_hi=("net_hi","mean"),net_lo=("net_lo","mean"),lo_oos=("lo_oos","mean"),cells=("n","size"),
   pos_lo=("pos_lo_both","sum"),best_lo=("net_lo","max")).sort_values("net_lo",ascending=False)
C.to_csv(f"{OUT}/r2_by_combo.csv"); print("\nBy combo");print(f(C))
# pooled per cfg: all non-baseline
P=table(["cfg"],A[A.family!="baseline"]); print("\nPooled non-baseline by cfg");print(f(P[["cfg","n","win","gross","net_hi","net_lo","lo_is","lo_oos"]]))
# per coin pooled non-baseline, by cfg
PC=table(["coin","cfg"],A[A.family!="baseline"]); PC.to_csv(f"{OUT}/r2_by_coin_cfg.csv",index=False)
print("\nPer coin pooled (cfg S2/T4/48h) sorted by net_lo");print(f(PC[PC.cfg=="S2/T4/48h"].sort_values("net_lo",ascending=False)[["coin","n","win","gross","net_hi","net_lo","lo_is","lo_oos"]]))
print("\nPer coin pooled (cfg S3/T6/72h)");print(f(PC[PC.cfg=="S3/T6/72h"].sort_values("net_lo",ascending=False)[["coin","n","win","gross","net_hi","net_lo","lo_is","lo_oos"]]))
# top combos: per coin
TC=N.sort_values("net_lo",ascending=False).head(3)
for _,r in TC.iterrows():
    s=A[(A.pair==r.pair)&(A.cfg==r.cfg)&(A.combo==r.combo)]; print("\nPER COIN",r.pair,r.cfg,r.combo); print(f(table(["coin"],s)[["coin","n","win","gross","net_hi","net_lo","lo_is","lo_oos"]]))
# direction
print("\nDirection");print(f(table(["dir"],A[A.family!="baseline"])[["dir","n","gross","net_lo"]]))
print("\n#cells gross_t>2:",(N.gross_t>2).sum(),"gross_t<-2:",(N.gross_t<-2).sum(),"of",len(N))
