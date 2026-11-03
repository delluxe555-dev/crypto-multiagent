import pandas as pd, numpy as np, sys
sys.path.insert(0,"/workspace/crypto-agents")
from combo_bt import stats, OUT
T=pd.read_csv(f"{OUT}/trades.csv.gz",parse_dates=["t"])
cut=T.t.min()+(T.t.max()-T.t.min())*2/3; print("cutoff",cut,"range",T.t.min(),T.t.max(),"coins",T.coin.nunique())
T["oos"]=T.t>=cut
def gt(g): 
    return g.gross.mean()/(g.gross.std(ddof=1)/np.sqrt(len(g))) if len(g)>2 else np.nan
rows=[]
for (p,c),g in T.groupby(["pair","combo"]):
    s=stats(g); i=g[~g.oos]; o=g[g.oos]; so=stats(o); si=stats(i)
    pc=g.groupby("coin").net.mean(); pg=g.groupby("coin").gross.mean()
    rows.append(dict(pair=p,combo=c,n=s["n"],win=s["win"],gross=s["gross"],gross_t=gt(g),net=s["net"],pf=s["pf"],netlow=s["netlow"],
      n_is=si["n"],gross_is=i.gross.mean(),net_is=si["net"],n_oos=so["n"],gross_oos=o.gross.mean(),net_oos=so["net"],pf_oos=so["pf"],
      coins_gross_pos=f"{(pg>0).sum()}/{len(pg)}",coins_net_pos=f"{(pc>0).sum()}/{len(pc)}",long_gross=g[g.dir==1].gross.mean(),short_gross=g[g.dir==-1].gross.mean()))
R=pd.DataFrame(rows); R["family"]=R.combo.map(T.drop_duplicates("combo").set_index("combo").family)
R["robust_net"]=(R.n>=50)&(R.n_oos>=20)&(R.net_is>0)&(R.net_oos>0)
R["robust_gross"]=(R.n>=50)&(R.n_oos>=20)&(R.gross_is>0)&(R.gross_oos>0)&(R.gross_t>2)
R.to_csv(f"{OUT}/summary_by_pair_combo.csv",index=False)
pd.set_option("display.width",260,"display.max_rows",500,"display.max_columns",40)
f=lambda d:d.round(3)
print("baseline per pair");print(f(R[R.family=="baseline"][["pair","combo","n","win","gross","net","pf","net_is","net_oos"]]))
cols=["pair","combo","n","win","gross","gross_t","net","pf","netlow","gross_is","gross_oos","net_oos","n_oos","coins_gross_pos"]
print("\nTOP by gross (n>=50, excl baseline)");print(f(R[(R.n>=50)&(R.family!="baseline")].sort_values("gross",ascending=False).head(20)[cols]))
print("\nTOP by net");print(f(R[(R.n>=50)&(R.family!="baseline")].sort_values("net",ascending=False).head(12)[cols]))
print("\nrobust_net:",R.robust_net.sum()," robust_gross:");print(f(R[R.robust_gross][cols]))
C=R[R.family!="baseline"].groupby("combo").agg(family=("family","first"),n=("n","sum"),gross=("gross","mean"),net=("net","mean"),netlow=("netlow","mean"),gross_oos=("gross_oos","mean"),net_oos=("net_oos","mean"),pairs_robust_gross=("robust_gross","sum")).sort_values("gross",ascending=False)
C.to_csv(f"{OUT}/summary_by_combo.csv"); print("\nCOMBO (mean over 3 TF pairs)");print(f(C))
# per coin
N=T[T.family!="baseline"]
pcn=N.groupby(["pair","coin"]).agg(n=("net","size"),win=("net",lambda x:(x>0).mean()),gross=("gross","mean"),net=("net","mean"),netlow=("netlow","mean")).round(3)
pcn.to_csv(f"{OUT}/per_coin_all_combos.csv"); 
print("\nPER COIN, all non-baseline combos pooled (15m/1h)");print(pcn.loc["15m/1h"]);
print("\nPER COIN pooled all pairs"); print(N.groupby("coin").agg(n=("net","size"),gross=("gross","mean"),net=("net","mean"),netlow=("netlow","mean")).round(3).sort_values("gross",ascending=False))
print("\nPER FAMILY pooled");print(N.groupby("family").agg(n=("net","size"),gross=("gross","mean"),net=("net","mean"),netlow=("netlow","mean"),win=("net",lambda x:(x>0).mean())).round(3))
# combo x coin gross heatmap (15m/1h) pooled over pairs
H=N.groupby(["combo","coin"]).gross.mean().unstack().round(2); H.to_csv(f"{OUT}/combo_by_coin_gross.csv")
H2=N.groupby(["combo","coin"]).net.mean().unstack().round(2); H2.to_csv(f"{OUT}/combo_by_coin_net.csv")
# pooled best combos per-coin
for cb in C.head(4).index:
    print("\nper coin:",cb); print(f(N[N.combo==cb].groupby("coin").agg(n=("net","size"),gross=("gross","mean"),net=("net","mean"),netlow=("netlow","mean"))))
# direction
print("\nDIRECTION");print(N.groupby("dir")[["gross","net"]].mean().round(3))
# multiple testing: how many combo/pair have gross_t>2 vs expected
print("\n#pair-combo with gross_t>2:",((R.gross_t>2)&(R.n>=50)&(R.family!="baseline")).sum(),"of",((R.n>=50)&(R.family!="baseline")).sum(),"; gross_t<-2:",((R.gross_t<-2)&(R.n>=50)&(R.family!="baseline")).sum())
# stop-by-hit stats: avg cost in R
print("avg cost R:",(T.gross-T.net).mean().round(3)," low:",(T.gross-T.netlow).mean().round(3))
