#!/usr/bin/env python3
"""kronos_full.py - Kronos (small/mini) sizintisiz tam test: Gate perp 1s(=1 saat) mumlari, 29 coin (combo evreni), son ~N gun.
CALISTIR (kvenv python!): /workspace/repos_review/kvenv/bin/python kronos_full.py --model small --days 50 --threads 4 [--coins BTC,ETH] [--limit N]
Her tahmin noktasi e icin YALNIZ [e-400, e) baglami verilir (gelecek mumlar modele girmez); 24 mum ileri tahmin; sample_count=5 (Kronos icinde ortalanir).
Noktalar 24 saat arayla (ortusmez). Cikti: outputs/research/kronos/preds_<model>.jsonl (devam edilebilir: yapilmis (coin,e) atlanir).
Degerlendirme: kronos_eval.py. Kronos kodu: /workspace/repos_review/Kronos (MIT). Bu dosya yeni; canli trader'a dokunmaz."""
import sys, os, json, time, argparse, requests
import numpy as np, pandas as pd
sys.path.insert(0, "/workspace/repos_review/Kronos")
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f"{HERE}/outputs/research/kronos"; CACHE = f"{OUT}/cache"
COINS = "AAVE ADA APT ARB ATOM AVAX BNB BTC DOGE DOT ETH FET FIL INJ JUP LINK LTC NEAR ONDO OP PEPE RENDER SEI SOL SUI TIA TRX WLD XRP".split()
G = "https://api.gateio.ws/api/v4/futures/usdt"; LB, H = 400, 24
CFG = {"mini": ("NeoQuasar/Kronos-Tokenizer-2k", "NeoQuasar/Kronos-mini", 2048), "small": ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-small", 512)}

def contract(c): return f"{c}_USDT"
def load(c):
    fp = f"{CACHE}/{c}.json"
    if not os.path.exists(fp):
        for _ in range(3):
            try:
                r = requests.get(f"{G}/candlesticks", params={"contract": contract(c), "interval": "1h", "limit": 2000}, timeout=20)
                if r.status_code == 200 and r.json(): json.dump(r.json(), open(fp, "w")); break
            except Exception: pass
            time.sleep(1)
        else: return None
    d = pd.DataFrame(json.load(open(fp)))
    d["timestamps"] = pd.to_datetime(d.t.astype(int), unit="s")
    for k, n in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume"), ("sum", "amount")): d[n] = d[k].astype(float)
    d = d.sort_values("timestamps").reset_index(drop=True)
    d = d.iloc[:-1]   # son (olusmakta olan) mumu at
    return d[["timestamps", "open", "high", "low", "close", "volume", "amount"]]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--model", default="small"); ap.add_argument("--days", type=int, default=50); ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--coins", default=""); ap.add_argument("--limit", type=int, default=0); ap.add_argument("--batch", type=int, default=4); ap.add_argument("--sc", type=int, default=5)
    ap.add_argument("--out", default=""); a = ap.parse_args()
    import torch; torch.set_num_threads(a.threads); torch.manual_seed(0)
    from model import Kronos, KronosTokenizer, KronosPredictor
    tk, mp, ctx = CFG[a.model]; pr = KronosPredictor(Kronos.from_pretrained(mp), KronosTokenizer.from_pretrained(tk), device="cpu", max_context=ctx)
    outp = a.out or f"{OUT}/preds_{a.model}.jsonl"; done = set()
    if os.path.exists(outp):
        for l in open(outp):
            try: x = json.loads(l); done.add((x["coin"], x["e"]))
            except Exception: pass
    coins = a.coins.split(",") if a.coins else COINS; jobs = []; meta = {}
    for c in coins:
        d = load(c)
        if d is None or len(d) < LB + a.days * 24 + 50: print("skip", c, None if d is None else len(d)); continue
        N = len(d); meta[c] = d
        for k in range(a.days):
            e = N - H - k * 24
            if e - LB >= 0 and (c, int(d.timestamps.iloc[e].timestamp())) not in done: jobs.append((c, e))
    jobs.sort(key=lambda x: (x[1], x[0]));
    if a.limit: jobs = jobs[:a.limit]
    print(f"model={a.model} jobs={len(jobs)} threads={a.threads} batch={a.batch}", flush=True); t0 = time.time(); n = 0
    with open(outp, "a") as f:
        for i in range(0, len(jobs), a.batch):
            b = jobs[i:i + a.batch]; dl = []; xt = []; yt = []
            for c, e in b:
                d = meta[c]; x = d.iloc[e - LB:e]; dl.append(x[["open", "high", "low", "close", "volume", "amount"]].reset_index(drop=True)); xt.append(x.timestamps.reset_index(drop=True))
                yt.append(pd.Series(pd.date_range(d.timestamps.iloc[e - 1] + pd.Timedelta(hours=1), periods=H, freq="1h")))
            try: P = pr.predict_batch(dl, xt, yt, pred_len=H, T=1.0, top_p=0.9, sample_count=a.sc, verbose=False)
            except Exception as ex:
                print("batch fail", b, str(ex)[:100], flush=True); continue
            for (c, e), p in zip(b, P):
                d = meta[c]; fut = d.iloc[e:e + H]
                f.write(json.dumps(dict(coin=c, e=int(d.timestamps.iloc[e].timestamp()), model=a.model, last_close=float(d.close.iloc[e - 1]), pred_close=[round(float(v), 8) for v in p.close.values],
                                        real_open0=float(fut.open.iloc[0]), real_close=[float(v) for v in fut.close.values], real_high=[float(v) for v in fut.high.values], real_low=[float(v) for v in fut.low.values],
                                        ctx_up=float(d.close.iloc[e - 1] / d.close.iloc[e - 25] - 1))) + "\n")
            f.flush(); n += len(b)
            if (i // a.batch) % 10 == 0: print(f"{n}/{len(jobs)} {time.time()-t0:.0f}s ({(time.time()-t0)/n:.2f}s/forecast)", flush=True)
    print("DONE", n, f"{time.time()-t0:.0f}s", flush=True)
