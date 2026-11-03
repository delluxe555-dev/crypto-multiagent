import mm, conv, numpy as np, time
raw = conv.raw_events("raw/btcusdt.gz", 20_000_000)
print("rows", len(raw), "secs", (raw['exch_ts'].max()-raw['exch_ts'].min())/1e9)
for name, fl, ol in [("zero",0,0),("meas+5ms",None,5)]:
    d = conv.build(raw, fl)
    for hb in [0.0, 1.0]:
        t=time.time(); rec = mm.run("btcusdt", d, ol, hb)
        print(name, "half", hb, mm.summarize(rec,0), round(time.time()-t,1),"s")
