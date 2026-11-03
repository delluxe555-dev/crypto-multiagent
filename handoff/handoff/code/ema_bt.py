"""EMA 8-13-21 kural tabanlı backtest (LLM yok). Veri: Binance spot (data.py üzerinden erişim), sayfalama ile.
Kullanım: .venv/bin/python ema_bt.py [fetch|run|all]
Kural: sinyal yalnız KAPANMIŞ mumda, işlem bir sonraki mumun AÇILIŞINDA. Parametreler sabit 8-13-21 (optimize yok).
Maliyet: taraf başına %0,10 komisyon + %0,05 kayma. Kaldıraç yok, tam sermaye bileşik."""
import os, sys, json, time
import numpy as np, pandas as pd
import data

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
TFS = {"15m": 15*60_000, "1h": 3600_000, "4h": 4*3600_000, "1d": 86400_000}
MAXBARS = {"15m": 70000, "1h": 50000, "4h": 100000, "1d": 100000}
BARS_PER_YEAR = {"15m": 35040, "1h": 8760, "4h": 2190, "1d": 365}
FEE, SLIP = 0.001, 0.0005
OUT = "outputs"; CACHE = f"{OUT}/ema_cache"

def fetch(symbol, tf):
    path = f"{CACHE}/{symbol}_{tf}.csv"
    now = int(time.time()*1000); dur = TFS[tf]
    rows, end = [], now
    while len(rows) < MAXBARS[tf]:
        params = {"symbol": symbol, "interval": tf, "limit": 1000, "endTime": end}
        j = None
        for attempt in range(4):
            for base in data.SPOT_URLS:
                try:
                    j = data._get(base + "/api/v3/klines", params)
                    if isinstance(j, list): break
                except Exception as e:
                    j = None
            if isinstance(j, list): break
            time.sleep(1.5)
        if not isinstance(j, list): raise RuntimeError(f"fetch hata {symbol} {tf}")
        if not j: break
        rows = j + rows
        end = int(j[0][0]) - 1
        if len(j) < 1000: break
    df = pd.DataFrame(rows, columns=["t","open","high","low","close","volume","ct","qv","n","tb","tq","ig"])
    df = df[["t","open","high","low","close","volume"]].astype(float)
    df["t"] = df["t"].astype("int64")
    df = df.drop_duplicates("t").sort_values("t")
    df = df[df["t"] + dur <= now].reset_index(drop=True)   # kapanmamış mumu at
    df.to_csv(path, index=False)
    return df

def load(symbol, tf):
    return pd.read_csv(f"{CACHE}/{symbol}_{tf}.csv")

def ind(df):
    c = df["close"]
    for n in (8, 13, 21): df[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    df["sma50"] = c.rolling(50).mean()
    tr = pd.concat([df.high-df.low, (df.high-c.shift()).abs(), (df.low-c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    return df

def htf_state(symbol, tf):
    """Üst TF trend: kapanış>EMA21 ve kapanış>SMA50 => +1, ikisi de altında => -1, aksi 0. Yalnız kapanmış HTF mumu."""
    htf = {"15m": "4h", "1h": "4h", "4h": "1d"}.get(tf)
    if not htf: return None, None
    h = ind(load(symbol, htf))
    up = (h.close > h.e21) & (h.close > h.sma50); dn = (h.close < h.e21) & (h.close < h.sma50)
    h["st"] = np.where(up, 1, np.where(dn, -1, 0)); h.loc[h.sma50.isna(), "st"] = 0
    h["avail"] = h.t + TFS[htf]   # bu mum kapandığı an
    return h[["avail", "st"]], htf

def targets(df, symbol, tf):
    """Her mumun KAPANIŞINDA hesaplanan hedef pozisyon (+1/0/-1). Dönüş: dict ad -> array."""
    bull = ((df.e8 > df.e13) & (df.e13 > df.e21)).values
    bear = ((df.e8 < df.e13) & (df.e13 < df.e21)).values
    valid = ~df.e21.isna().values; valid[:30] = False
    A = np.where(df.e8 > df.e13, 1, -1) * valid
    B = (bull.astype(int) - bear.astype(int)) * valid
    cl = df.close.values; e21 = df.e21.values
    C = np.where(bull & (cl > e21), 1, np.where(bear & (cl < e21), -1, 0)) * valid
    out = {"A": A, "B": B, "C": C}
    h, _ = htf_state(symbol, tf)
    if h is not None:
        # sinyal mumu kapanış zamanı = t + dur; o ana kadar kapanmış son HTF mumu
        q = pd.DataFrame({"ct": df.t.values + TFS[tf]})
        m = pd.merge_asof(q, h.sort_values("avail"), left_on="ct", right_on="avail", direction="backward")
        st = m.st.fillna(0).values
        out["D"] = np.where((B == 1) & (st == 1), 1, np.where((B == -1) & (st == -1), -1, 0))
    return out

def simulate(df, tgt, lo, hi, stop_mult=None):
    """Segment [lo,hi) üzerinde. Sinyal t-1 kapanışında, işlem t açılışında. Dönüş: bar getirileri, işlemler."""
    o, h, l, c, atr = df.open.values, df.high.values, df.low.values, df.close.values, df.atr.values
    pos = 0; entry = ref = stop = 0.0; blocked = 0
    rets = np.zeros(hi - lo); trades = []; ent_t = None; ent_net_mult = 1.0
    cur_mult = 1.0
    for t in range(lo + 1, hi):
        r = 0.0
        want = int(tgt[t-1])
        if blocked and want == blocked: want = 0
        elif blocked and want != blocked: blocked = 0
        if want != pos:
            if pos != 0:  # çıkış açılışta
                px = o[t] * (1 - SLIP * pos)
                r += (1 + pos*(px/entry-1)) / (1 + pos*(ref/entry-1)) - 1; r = (1 + r) * (1 - FEE) - 1
                trades.append((ent_t, t, pos, cur_mult * (1 + pos*(px/entry - 1)) * (1 - FEE) - 1)); 
                pos = 0
            if want != 0:
                pos = want; entry = o[t] * (1 + SLIP * pos); ref = entry
                r = (1 + r) * (1 - FEE) - 1
                cur_mult = (1 - FEE); ent_t = t
                if stop_mult and not np.isnan(atr[t-1]): stop = entry - pos * stop_mult * atr[t-1]
                else: stop = None
            else:
                rets[t - lo] = r; continue
        elif pos == 0:
            continue
        # pozisyon bu mum boyunca açık: stop kontrolü
        if pos != 0 and stop is not None and ((pos == 1 and l[t] <= stop) or (pos == -1 and h[t] >= stop)):
            sp = min(stop, o[t]) if pos == 1 else max(stop, o[t])
            px = sp * (1 - SLIP * pos)
            r = (1 + r) * ((1 + pos*(px/entry-1)) / (1 + pos*(ref/entry-1))) * (1 - FEE) - 1
            trades.append((ent_t, t, pos, cur_mult * (1 + pos*(px/entry - 1)) * (1 - FEE) - 1))
            blocked = pos; pos = 0
        else:
            r = (1 + r) * ((1 + pos*(c[t]/entry-1)) / (1 + pos*(ref/entry-1))) - 1
            ref = c[t]
        rets[t - lo] = r
    if pos != 0:  # segment sonunda zorunlu kapanış (son kapanışta), maliyetli
        px = c[hi-1] * (1 - SLIP * pos)
        rets[hi-1-lo] = (1 + rets[hi-1-lo]) * ((1 + pos*(px/entry-1)) / (1 + pos*(c[hi-1]/entry-1))) * (1 - FEE) - 1
        trades.append((ent_t, hi-1, pos, cur_mult * (1 + pos*(px/entry - 1)) * (1 - FEE) - 1))
    return rets, trades

def metrics(rets, trades, tf, bh):
    eq = np.cumprod(1 + rets)
    tot = eq[-1] - 1
    dd = (eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min() if len(eq) else 0
    sd = rets.std()
    sharpe = rets.mean() / sd * np.sqrt(BARS_PER_YEAR[tf]) if sd > 0 else 0.0
    tr = np.array([x[3] for x in trades]) if trades else np.array([])
    w, lo_ = tr[tr > 0], tr[tr <= 0]
    pf = (w.sum() / -lo_.sum()) if len(lo_) and lo_.sum() < 0 else (np.inf if len(w) else 0.0)
    return dict(n_trades=len(tr), net_ret=tot*100, buyhold=bh*100,
                win_rate=(len(w)/len(tr)*100 if len(tr) else 0.0),
                avg_win=(w.mean()*100 if len(w) else 0.0), avg_loss=(lo_.mean()*100 if len(lo_) else 0.0),
                profit_factor=(float(pf) if np.isfinite(pf) else 999.0), max_dd=dd*100, sharpe=sharpe)

def buyhold(df, lo, hi):
    ent = df.open.values[lo] * (1 + SLIP); ex = df.close.values[hi-1] * (1 - SLIP)
    return (ex / ent) * (1 - FEE)**2 - 1

STRATS = [("A_LS","A",1,False,"EMA8/13 kesişim L/S"), ("A_L","A",0,False,"EMA8/13 kesişim long-only"),
          ("B_LS","B",1,False,"8>13>21 dizilim L/S"), ("B_L","B",0,False,"8>13>21 dizilim long-only"),
          ("C_LS","C",1,True,"B+EMA21 filtre+ATR1.5 stop L/S"), ("C_L","C",0,True,"B+EMA21 filtre+ATR1.5 stop long-only"),
          ("D_LS","D",1,False,"B+üst TF filtre L/S"), ("D_L","D",0,False,"B+üst TF filtre long-only")]

def run():
    rows = []
    for sym in COINS:
        for tf in TFS:
            df = ind(load(sym, tf)); n = len(df)
            tg = targets(df, sym, tf)
            cut = int(n * 0.7)
            segs = {"full": (0, n), "IS": (0, cut), "OOS": (cut, n)}
            for name, key, ls, stop, desc in STRATS:
                if key not in tg: continue
                t = tg[key].copy()
                if not ls: t = np.maximum(t, 0)
                for seg, (lo, hi) in segs.items():
                    rets, trades = simulate(df, t, lo, hi, 1.5 if stop else None)
                    m = metrics(rets, trades, tf, buyhold(df, lo, hi))
                    m.update(coin=sym, tf=tf, strat=name, segment=seg, bars=hi-lo,
                             start=pd.to_datetime(df.t[lo], unit="ms").strftime("%Y-%m-%d"),
                             end=pd.to_datetime(df.t[hi-1], unit="ms").strftime("%Y-%m-%d"))
                    rows.append(m)
    res = pd.DataFrame(rows)
    cols = ["coin","tf","strat","segment","start","end","bars","n_trades","net_ret","buyhold","win_rate","avg_win","avg_loss","profit_factor","max_dd","sharpe"]
    res = res[cols].round(2)
    ts = time.strftime("%Y-%m-%dT%H%M")
    res.to_csv(f"{OUT}/ema_bt_{ts}.csv", index=False)
    json.dump(dict(params=dict(ema=[8,13,21], fee_per_side=FEE, slip_per_side=SLIP, split="70/30 kronolojik", source="Binance spot (api.binance.com / data-api.binance.vision)"),
                   rows=json.loads(res.to_json(orient="records"))), open(f"{OUT}/ema_bt_{ts}.json", "w"), ensure_ascii=False, indent=1)
    print("yazıldı", f"{OUT}/ema_bt_{ts}.csv")
    return res

if __name__ == "__main__":
    os.makedirs(CACHE, exist_ok=True)
    a = sys.argv[1] if len(sys.argv) > 1 else "all"
    if a in ("fetch", "all"):
        for s in COINS:
            for tf in TFS:
                d = fetch(s, tf)
                print(s, tf, len(d), pd.to_datetime(d.t.iloc[0], unit="ms"), "->", pd.to_datetime(d.t.iloc[-1], unit="ms"), flush=True)
    if a in ("run", "all"): run()
