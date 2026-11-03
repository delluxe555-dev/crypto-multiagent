#!/usr/bin/env python3
"""ict_setups.py - rule-based, causal (no lookahead) detectors for 6 ICT-style setups + trade simulator.
Convention everywhere: signal is evaluated at the CLOSE of bar i using bars <= i only; entry = open of bar i+1.
Parameters (fixed a-priori, never tuned): see constants below. Full definitions in outputs/research_E_ict_setups.md.
Modes: 1 IFVG, 2 BREAKER, 3 CISD, 4 SUSPENSION, 5 ORDERBLOCK, 6 MSS_FVG.
"""
import numpy as np, pandas as pd
from numba import njit

K_SW = 3        # fractal swing: bar j is swing high if high[j] > highs of 3 bars left and 3 bars right (confirmed at close of j+3)
EXPIRE = 50     # bars a zone stays alive (pending OB/FVG: from formation; flipped/active zone: from activation)
MING = 0.25     # min FVG / gap size, in ATR14 units
DISP = 1.5      # displacement candle body >= 1.5 * ATR14 (ATR of the previous bar)
OBLOOK = 5      # OB candle = last opposite-colour candle within the 5 bars before the displacement candle
CISD_MIN_SERIES = 2
CISD_MIN_DROP = 1.0   # series height >= 1 ATR
CISD_MAX_SERIES = 20
STOP_PAD = 0.1  # zone stop padding (ATR)
RISK_MIN, RISK_MAX = 0.5, 3.0   # risk floor (set stop to 0.5 ATR) / cap (skip trade) in ATR
ATR_STOP = 1.5  # ATR-stop variant: stop = 1.5 ATR from entry
MAXHOLD = 96    # bars; time exit at close
MAXZ = 128
SETUPS = {1: "IFVG", 2: "BreakerFlow", 3: "CISD", 4: "SuspensionBlock", 5: "OrderBlock", 6: "MSS_FVG"}

def load(pair, tf, d="data"):
    df = pd.read_csv(f"{d}/{pair}USDT_{tf}.csv.gz", index_col=0, parse_dates=True)
    return df

def atr14(df):
    c = df["c"]; tr = pd.concat([df["h"] - df["l"], (df["h"] - c.shift()).abs(), (df["l"] - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(14).mean().values   # value at i uses bars <= i only

@njit(cache=True)
def _add(zl, zh, zd, zb, zs, alive, lo, hi, d, born, status):
    k = -1
    for q in range(MAXZ):
        if not alive[q]: k = q; break
    if k < 0:
        k = 0
        for q in range(MAXZ):
            if zb[q] < zb[k]: k = q
    zl[k] = lo; zh[k] = hi; zd[k] = d; zb[k] = born; zs[k] = status; alive[k] = True

@njit(cache=True)
def gen_zone_signals(o, h, l, c, atr, mode):
    """modes 1,2,4,5,6. Returns arrays (bar i of the retest-rejection candle, dir, zone_lo, zone_hi)."""
    n = len(o)
    zl = np.zeros(MAXZ); zh = np.zeros(MAXZ); zd = np.zeros(MAXZ, np.int64); zb = np.zeros(MAXZ, np.int64); zs = np.zeros(MAXZ, np.int64); alive = np.zeros(MAXZ, np.bool_)
    si = np.empty(n, np.int64); sd = np.empty(n, np.int64); sl_ = np.empty(n); sh_ = np.empty(n); ns = 0
    lastSH = np.nan; lastSL = np.nan; shc = True; slc = True; state = 0; pend_dir = 0; pend_bar = -10
    for i in range(20, n):
        a = atr[i]
        if np.isnan(a) or a <= 0: continue
        # 0) confirm fractal swing at j=i-3 (uses bars up to i)
        j = i - K_SW
        okh = True; okl = True
        for q in range(1, K_SW + 1):
            if h[j - q] >= h[j] or h[j + q] >= h[j]: okh = False
            if l[j - q] <= l[j] or l[j + q] <= l[j]: okl = False
        if okh: lastSH = h[j]; shc = False
        if okl: lastSL = l[j]; slc = False
        # 1) process existing zones against bar i (zones created at bar i act from i+1)
        for k in range(MAXZ):
            if not alive[k]: continue
            if i - zb[k] > EXPIRE: alive[k] = False; continue
            if zs[k] == 0:   # pending (IFVG / breaker): waits for a CLOSE through the far side -> flips role
                if zd[k] == 1 and c[i] < zl[k]: zd[k] = -1; zs[k] = 1; zb[k] = i
                elif zd[k] == -1 and c[i] > zh[k]: zd[k] = 1; zs[k] = 1; zb[k] = i
            else:            # active zone: FIRST touch decides (consumed either way)
                if zd[k] == 1:
                    if l[i] <= zh[k]:
                        alive[k] = False
                        if c[i] > zh[k] and c[i] > o[i]:
                            if ns > 0 and si[ns - 1] == i:
                                if sd[ns - 1] != 1: sd[ns - 1] = 0
                            else: si[ns] = i; sd[ns] = 1; sl_[ns] = zl[k]; sh_[ns] = zh[k]; ns += 1
                else:
                    if h[i] >= zl[k]:
                        alive[k] = False
                        if c[i] < zl[k] and c[i] < o[i]:
                            if ns > 0 and si[ns - 1] == i:
                                if sd[ns - 1] != -1: sd[ns - 1] = 0
                            else: si[ns] = i; sd[ns] = -1; sl_[ns] = zl[k]; sh_[ns] = zh[k]; ns += 1
        # 2) structure breaks on close (first close beyond an unconsumed confirmed swing)
        brk_up = False; brk_dn = False; mss_up = False; mss_dn = False
        if (not shc) and c[i] > lastSH:
            brk_up = True; shc = True; mss_up = (state == -1); state = 1
        if (not slc) and c[i] < lastSL:
            brk_dn = True; slc = True; mss_dn = (state == 1); state = -1
        # 3) create new zones
        if mode == 1:   # FVG formed by candles i-2,i-1,i ; pending until a close through it
            if l[i] > h[i - 2] and (l[i] - h[i - 2]) >= MING * a: _add(zl, zh, zd, zb, zs, alive, h[i - 2], l[i], 1, i, 0)
            if h[i] < l[i - 2] and (l[i - 2] - h[i]) >= MING * a: _add(zl, zh, zd, zb, zs, alive, h[i], l[i - 2], -1, i, 0)
        elif mode == 2 or mode == 5:   # order block = last opposite candle before displacement candle that closes beyond last swing
            body = c[i] - o[i]; ap = atr[i - 1]
            if not np.isnan(ap) and ap > 0:
                st = 0 if mode == 2 else 1
                if brk_up and body >= DISP * ap:
                    for k in range(i - 1, i - 1 - OBLOOK, -1):
                        if c[k] < o[k]: _add(zl, zh, zd, zb, zs, alive, l[k], h[k], 1, i, st); break
                if brk_dn and -body >= DISP * ap:
                    for k in range(i - 1, i - 1 - OBLOOK, -1):
                        if c[k] > o[k]: _add(zl, zh, zd, zb, zs, alive, l[k], h[k], -1, i, st); break
        elif mode == 4:   # lone candle x=i-2 with FVG on both sides (x-2,x-1,x) and (x,x+1,x+2)
            x = i - 2
            if l[x] > h[x - 2] and h[x] < l[i] and (l[x] - h[x - 2]) >= MING * a and (l[i] - h[x]) >= MING * a:
                _add(zl, zh, zd, zb, zs, alive, l[x], h[x], 1, i, 1)
            if h[x] < l[x - 2] and l[x] > h[i] and (l[x - 2] - h[x]) >= MING * a and (l[x] - h[i]) >= MING * a:
                _add(zl, zh, zd, zb, zs, alive, l[x], h[x], -1, i, 1)
        elif mode == 6:   # MSS (first close beyond swing against prior structure) + FVG completed at bar i or i+1
            if mss_up: pend_dir = 1; pend_bar = i
            if mss_dn: pend_dir = -1; pend_bar = i
            if pend_dir != 0:
                if i - pend_bar > 1: pend_dir = 0
                elif pend_dir == 1 and l[i] > h[i - 2] and (l[i] - h[i - 2]) >= MING * a:
                    _add(zl, zh, zd, zb, zs, alive, h[i - 2], l[i], 1, i, 1); pend_dir = 0
                elif pend_dir == -1 and h[i] < l[i - 2] and (l[i - 2] - h[i]) >= MING * a:
                    _add(zl, zh, zd, zb, zs, alive, h[i], l[i - 2], -1, i, 1); pend_dir = 0
    return si[:ns], sd[:ns], sl_[:ns], sh_[:ns]

@njit(cache=True)
def gen_cisd(o, h, l, c, atr):
    """CISD: >=2 consecutive down candles ending at i-1 whose height (series open - lowest low) >= 1 ATR; bar i closes above the OPEN of the series' first candle
    (and bar i-1 closed below it, i.e. first break) -> long. Mirror for short."""
    n = len(o); si = np.empty(n, np.int64); sd = np.empty(n, np.int64); sl_ = np.empty(n); sh_ = np.empty(n); ns = 0
    for i in range(20, n):
        a = atr[i]
        if np.isnan(a) or a <= 0: continue
        if c[i - 1] < o[i - 1]:
            m = 1
            while m < CISD_MAX_SERIES and i - 1 - m >= 0 and c[i - 1 - m] < o[i - 1 - m]: m += 1
            so = o[i - m]; lo = l[i - m]
            for k in range(i - m, i): lo = min(lo, l[k])
            if m >= CISD_MIN_SERIES and (so - lo) >= CISD_MIN_DROP * a and c[i - 1] < so and c[i] > so:
                si[ns] = i; sd[ns] = 1; sl_[ns] = lo; sh_[ns] = so; ns += 1; continue
        if c[i - 1] > o[i - 1]:
            m = 1
            while m < CISD_MAX_SERIES and i - 1 - m >= 0 and c[i - 1 - m] > o[i - 1 - m]: m += 1
            so = o[i - m]; hi = h[i - m]
            for k in range(i - m, i): hi = max(hi, h[k])
            if m >= CISD_MIN_SERIES and (hi - so) >= CISD_MIN_DROP * a and c[i - 1] > so and c[i] < so:
                si[ns] = i; sd[ns] = -1; sl_[ns] = so; sh_[ns] = hi; ns += 1
    return si[:ns], sd[:ns], sl_[:ns], sh_[:ns]

def gen_signals(o, h, l, c, atr, mode):
    if mode == 3: r = gen_cisd(o, h, l, c, atr)
    else: r = gen_zone_signals(o, h, l, c, atr, mode)
    si, sd, zl, zh = r; m = sd != 0
    return si[m], sd[m], zl[m], zh[m]

@njit(cache=True)
def sim(o, h, l, c, atr, si, sd, zl, zh, stop_mode, R, risk_atr_in):
    """stop_mode 0: zone stop (beyond zone / retest candle extreme, +0.1 ATR pad, floor 0.5 ATR, cap 3 ATR -> skip); 1: 1.5 ATR; 2: explicit risk_atr_in[q] (random baseline).
    Entry = open[i+1]. Target = entry +/- R*risk. Both hit in one bar -> stop first. Stop gap-through fills at the open. Time exit after MAXHOLD bars at close.
    One position at a time. Returns (i_entry, i_exit, dir, gross_R, entry/risk, risk/atr)."""
    n = len(o); m = len(si)
    oi = np.empty(m, np.int64); oo = np.empty(m, np.int64); od = np.empty(m, np.int64); og = np.empty(m); ok = np.empty(m); orr = np.empty(m); nt = 0; last_exit = -1
    for q in range(m):
        i = si[q]
        if i < last_exit or i + 1 >= n: continue
        a = atr[i]; e = o[i + 1]; d = sd[q]
        if stop_mode == 0:
            if d == 1: s = min(zl[q], l[i]) - STOP_PAD * a; risk = e - s
            else: s = max(zh[q], h[i]) + STOP_PAD * a; risk = s - e
            if risk > RISK_MAX * a: continue
            if risk < RISK_MIN * a: risk = RISK_MIN * a
        elif stop_mode == 1: risk = ATR_STOP * a
        else: risk = risk_atr_in[q] * a
        if d == 1: s = e - risk; tg = e + R * risk
        else: s = e + risk; tg = e - R * risk
        j_last = min(n - 1, i + MAXHOLD); ex = np.nan; jx = j_last
        for j in range(i + 1, j_last + 1):
            if d == 1:
                if l[j] <= s: ex = min(s, o[j]); jx = j; break
                if h[j] >= tg: ex = tg; jx = j; break
            else:
                if h[j] >= s: ex = max(s, o[j]); jx = j; break
                if l[j] <= tg: ex = tg; jx = j; break
        if np.isnan(ex): ex = c[jx]
        oi[nt] = i + 1; oo[nt] = jx; od[nt] = d; og[nt] = d * (ex - e) / risk; ok[nt] = e / risk; orr[nt] = risk / a; nt += 1; last_exit = jx
    return oi[:nt], oo[:nt], od[:nt], og[:nt], ok[:nt], orr[:nt]

def zone_risk_atr(o, atr, l, h, si, sd, zl, zh):
    """risk/ATR per signal for the zone-stop mode (vectorised twin of sim's zone-stop; used to feed the random baseline)."""
    a = atr[si]; e = o[np.minimum(si + 1, len(o) - 1)]
    risk = np.where(sd == 1, e - (np.minimum(zl, l[si]) - STOP_PAD * a), (np.maximum(zh, h[si]) + STOP_PAD * a) - e)
    ok = risk <= RISK_MAX * a; risk = np.maximum(risk, RISK_MIN * a)
    return (risk / a)[ok]
