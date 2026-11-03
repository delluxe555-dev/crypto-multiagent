import mm, conv, numpy as np, json, sys, time, gc
syms = sys.argv[1].split(",")
out_path = sys.argv[2]
max_secs = float(sys.argv[3]) if len(sys.argv) > 3 else None

LAT = {  # name: (feed latency ns or None=measured, order entry/response ms each way)
    "zero (feed 0, order 0)": (0, 0),
    "low (feed 5ms, order 5ms)": (5_000_000, 5),
    "mid (feed 25ms, order 25ms)": (25_000_000, 25),
    "high (measured feed ~28ms+jitter, order 50ms)": (None, 50),
}
HALF = [0.0, 0.5, 1.0, 2.0, 4.0]
QUEUES = ["risk_averse", "prob"]
FEES = {"maker 0.02% (regular user)": 0.0002, "maker 0 (promo/zero)": 0.0, "maker -0.005% (MM rebate, hypothetical)": -0.00005}
results = {}
for sym in syms:
    raw = conv.raw_events(f"raw/{sym}.gz", 40_000_000)
    t0 = raw['exch_ts'].min()
    if max_secs: raw = raw[raw['exch_ts'] <= t0 + int(max_secs*1e9)]
    span = (raw['exch_ts'].max() - t0) / 1e9
    lat = (raw['local_ts'] - raw['exch_ts']) / 1e6
    trades = raw[(raw['ev'] & (1 << 29)) != 0] if False else None
    info = dict(rows=len(raw), span_min=span/60, feed_lat_ms_pctl={p: float(np.percentile(lat, p)) for p in (1, 50, 95, 99)},
                mid_px=float(np.median(raw['px'][raw['px'] > 0.5 * np.median(raw['px'])])))
    results[sym] = dict(info=info, runs=[])
    print(sym, info, flush=True)
    for lname, (fl, ol) in LAT.items():
        data = conv.build(raw, fl)
        for q in QUEUES:
            for hb in HALF:
                t = time.time()
                rec = mm.run(sym, data, ol, hb, queue=q)
                s = mm.summarize(rec, 0.0)
                eq = rec[:, 3] + rec[:, 1] * rec[:, 2]
                n = len(eq); k = 4
                edges = [int(i * (n - 1) / k) for i in range(k + 1)]
                s["pnl_gross_quarters"] = [float(eq[edges[i + 1]] - eq[edges[i]]) for i in range(k)]
                s["pnl_net"] = {fn: s["pnl_gross"] - f * s["traded_usd"] for fn, f in FEES.items()}
                s.update(dict(lat=lname, queue=q, half_bps=hb))
                results[sym]["runs"].append(s)
        del data; gc.collect()
        print(sym, lname, "done", flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
