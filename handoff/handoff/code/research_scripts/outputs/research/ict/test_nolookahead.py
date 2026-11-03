"""Causality test: signals computed on a truncated history must equal the signals of the full history for all bars < cut (prefix invariance).
Also checks that the swing/ATR inputs never change when future bars are removed. Run: python test_nolookahead.py"""
import numpy as np, ict_setups as S
for pair, tf in [("BTC", "1h"), ("ETH", "15m"), ("SOL", "4h")]:
    df = S.load(pair, tf); o, h, l, c = (df[x].values for x in "ohlc"); atr = S.atr14(df)
    for cut in (len(df) // 2, len(df) // 3 + 17):
        a2 = S.atr14(df.iloc[:cut])
        assert np.allclose(a2[14:], atr[14:cut]), "ATR not causal"
        for mode in range(1, 7):
            full = S.gen_signals(o, h, l, c, atr, mode); part = S.gen_signals(o[:cut], h[:cut], l[:cut], c[:cut], a2, mode)
            mf = full[0] < cut
            for x, y in zip(full, part): assert np.array_equal(x[mf], y), (pair, tf, cut, mode)
            print(pair, tf, cut, S.SETUPS[mode], "OK", mf.sum(), "signals before cut identical")
        # trades: entry strictly after signal bar
        si, sd, zl, zh = S.gen_signals(o, h, l, c, atr, 5); r = S.sim(o, h, l, c, atr, si, sd, zl, zh, 0, 2.0, np.zeros(len(si)))
        assert (r[0] > 0).all(); print("entry index > signal index OK")
print("ALL CAUSALITY TESTS PASSED")
