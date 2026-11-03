"""Hesaplanmış (LLM'siz) piyasa yapısı: FVG, VWAP (gün/hafta ±1σ), hacim profili (POC/VAH/VAL/HVN/LVN),
klasik pivotlar (günlük/haftalık), fraktal swing seviyeleri. Look-ahead yok: yalnızca verilen df'nin
0..i satırları (analiz mumu kapanışına kadar) kullanılır. Çıktı kompakt Türkçe metin (LLM kotası dostu)."""
import numpy as np, pandas as pd

_REF = [None]
def fp(x):
    """Fiyatı büyüklüğe göre biçimle (ondalık sayısı analiz fiyatına göre sabit)."""
    a = abs(_REF[0] or x)
    d = 2 if a >= 100 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.1 else 6 if a >= 0.01 else 8
    return f"{x:,.{d}f}"

def pct(lv, px): return f"{(lv/px-1)*100:+.1f}%"

def _ts(df):
    d = df["date"].astype(str)
    return pd.to_datetime(d, utc=True)

def fvg(df, px, atr, look=100, k=3):
    h, l = df["high"].values, df["low"].values; n = len(df); s = max(2, n - look)
    bull, bear = [], []
    for j in range(s, n):
        if l[j] > h[j-2]:                                   # boğa boşluğu: [h[j-2], l[j]]
            lo, hi = h[j-2], l[j]
            if j + 1 < n: hi = min(hi, l[j+1:].min())       # kısmi dolum: üst sınır sonraki en düşük dibe iner
            if hi - lo > 0.1 * atr: bull.append((lo, hi))
        if h[j] < l[j-2]:                                   # ayı boşluğu: [h[j], l[j-2]]
            lo, hi = h[j], l[j-2]
            if j + 1 < n: lo = max(lo, h[j+1:].max())
            if hi - lo > 0.1 * atr: bear.append((lo, hi))
    bull = sorted([z for z in bull if z[1] < px], key=lambda z: px - z[1])[:k]
    bear = sorted([z for z in bear if z[0] > px], key=lambda z: z[0] - px)[:k]
    f = lambda zs: ", ".join(f"{fp(a)}–{fp(b)} ({pct(b if b < px else a, px)})" for a, b in zs) or "yok"
    return f"FVG (son {look} mum, dolmamış) — üstte ayı/direnç: {f(bear)} | altta boğa/destek: {f(bull)}"

def vwap(df, ts, px, period):
    key = ts.dt.floor("D") if period == "D" else (ts - pd.to_timedelta(ts.dt.weekday, unit="D")).dt.floor("D")
    if ts.iloc[0] > key.iloc[-1]: return None            # periyodun başı veride yok (ör. 15m'de hafta) -> atla
    m = key == key.iloc[-1]; d = df[m.values]
    tp = (d.high + d.low + d.close) / 3; v = d.volume
    if v.sum() <= 0: return None
    vw = (tp * v).sum() / v.sum(); sd = np.sqrt(((tp - vw) ** 2 * v).sum() / v.sum())
    return vw, sd, len(d)

def vwap_text(df, ts, px, interval):
    out = []
    if interval in ("15m", "1h", "4h"):
        r = vwap(df, ts, px, "D")
        if r: out.append(f"gün (UTC, {r[2]} mum) {fp(r[0])} [fiyat {pct(px, r[0])}]")
    r = vwap(df, ts, px, "W")
    if r:
        vw, sd, n = r; pos = "+1σ üstü" if px > vw + sd else "-1σ altı" if px < vw - sd else "VWAP–+1σ arası" if px >= vw else "-1σ–VWAP arası"
        out.append(f"hafta ({n} mum) {fp(vw)} ±1σ {fp(vw-sd)}–{fp(vw+sd)} [fiyat {pct(px, vw)}, {pos}]")
    return "VWAP: " + " · ".join(out) if out else None

def vprofile(df, px, n, bins=40):
    d = df.tail(n); lo, hi = d.low.min(), d.high.max()
    if not hi > lo: return None
    edges = np.linspace(lo, hi, bins + 1); mid = (edges[:-1] + edges[1:]) / 2; hist = np.zeros(bins)
    for a, b, v in zip(d.low.values, d.high.values, d.volume.values):   # mum hacmini high-low aralığına eşit dağıt
        i0 = min(int((a - lo) / (hi - lo) * bins), bins - 1); i1 = min(int((b - lo) / (hi - lo) * bins), bins - 1)
        hist[i0:i1 + 1] += v / (i1 - i0 + 1)
    poc = int(hist.argmax()); tot = hist.sum(); a = b = poc; acc = hist[poc]
    while acc < 0.7 * tot and (a > 0 or b < bins - 1):
        up = hist[b + 1] if b < bins - 1 else -1; dn = hist[a - 1] if a > 0 else -1
        if up >= dn: b += 1; acc += up
        else: a -= 1; acc += dn
    val, vah = edges[a], edges[b + 1]
    sm = np.convolve(hist, np.ones(3) / 3, mode="same")
    pk = [j for j in range(1, bins - 1) if sm[j] > sm[j-1] and sm[j] >= sm[j+1] and abs(j - poc) > 2]
    tr = [j for j in range(1, bins - 1) if sm[j] < sm[j-1] and sm[j] <= sm[j+1] and a <= j <= b]
    hvn = sorted(pk, key=lambda j: -sm[j])[:2]; lvn = sorted(tr, key=lambda j: sm[j])[:2]
    pos = "değer alanı içinde" if val <= px <= vah else ("VAH üstünde" if px > vah else "VAL altında")
    s = f"POC {fp(mid[poc])} ({pct(mid[poc], px)}) · VAH {fp(vah)} · VAL {fp(val)} — fiyat {pos}"
    if hvn: s += " · HVN " + ", ".join(fp(mid[j]) for j in sorted(hvn))
    if lvn: s += " · LVN " + ", ".join(fp(mid[j]) for j in sorted(lvn))
    return s

def pivots(df, ts, period):
    key = ts.dt.floor("D") if period == "D" else (ts - pd.to_timedelta(ts.dt.weekday, unit="D")).dt.floor("D")
    g = df.set_index(key.values).groupby(level=0).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    if len(g) < 2 or ts.iloc[0] > pd.Timestamp(g.index[-2]).tz_localize("UTC"): return None   # önceki periyot eksiksiz değilse atla
    prev = g.iloc[-2]                                    # son TAMAMLANMIŞ periyot (son grup devam ediyor)
    H, L, C = prev.high, prev.low, prev.close; P = (H + L + C) / 3
    R1, S1 = 2*P - L, 2*P - H; R2, S2 = P + (H - L), P - (H - L); R3, S3 = H + 2*(P - L), L - 2*(H - P)
    return f"P {fp(P)} · R1 {fp(R1)} R2 {fp(R2)} R3 {fp(R3)} · S1 {fp(S1)} S2 {fp(S2)} S3 {fp(S3)}"

def swings(df, px, atr, look=200, w=2, k=3):
    d = df.tail(look); h, l = d.high.values, d.low.values; n = len(d); highs, lows = [], []
    for j in range(w, n - w):                            # fraktal: her iki yanda w mum teyidi (kapanmış mumlarla)
        if h[j] == h[j-w:j+w+1].max(): highs.append(h[j])
        if l[j] == l[j-w:j+w+1].min(): lows.append(l[j])
    def pick(xs, above):
        xs = sorted([x for x in xs if (x > px if above else x < px)], key=lambda x: abs(x - px)); out = []
        for x in xs:
            if all(abs(x - y) > 0.3 * atr for y in out): out.append(x)
            if len(out) == k: break
        return ", ".join(f"{fp(x)} ({pct(x, px)})" for x in out) or "yok"
    return f"Swing (fraktal, son {look} mum) — direnç: {pick(highs, True)} | destek: {pick(lows, False)}"

def text(df, i=None, interval="1h"):
    """df: göstergeli mum tablosu (date, open, high, low, close, volume, atr14). Yalnızca 0..i satırları kullanılır."""
    if i is None: i = len(df) - 1
    d = df.iloc[:i + 1].reset_index(drop=True)
    if len(d) < 30: return ""
    try:
        ts = _ts(d); px = float(d.close.iloc[-1]); _REF[0] = px; atr = float(d.atr14.iloc[-1]) if "atr14" in d and pd.notna(d.atr14.iloc[-1]) else px * 0.01
        L = ["Yapı (hesaplanmış, yalnızca kapanmış mumlar):"]
        v = vwap_text(d, ts, px, interval)
        if v: L.append(v)
        vp = vprofile(d, px, 150)
        if vp: L.append(f"Hacim profili (son 150 mum): {vp}")
        short_n = {"15m": 96, "1h": 24, "4h": 42}.get(interval)   # ~1 gün (15m/1h), ~1 hafta (4h)
        if short_n:
            vp2 = vprofile(d, px, short_n, bins=30)
            if vp2: L.append(f"Hacim profili (son {short_n} mum): {vp2}")
        if interval != "1d":
            p = pivots(d, ts, "D")
            if p: L.append(f"Pivot günlük (önceki gün): {p}")
        p = pivots(d, ts, "W")
        if p: L.append(f"Pivot haftalık (önceki hafta): {p}")
        L.append(fvg(d, px, atr)); L.append(swings(d, px, atr))
        return "\n".join(L)
    except Exception as e:
        return f"Yapı göstergeleri hesaplanamadı: {e}"
