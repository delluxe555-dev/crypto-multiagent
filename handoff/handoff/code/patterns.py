"""Hesaplanmış (LLM'siz) formasyon bilgisi — look-ahead YOK: yalnızca df'nin 0..i satırları (analiz mumu kapanışına kadar) kullanılır.
Mum formasyonları (konum+hacim bağlamlı), grafik formasyonları (çift/üçlü tepe-dip, OBO/TOBO, üçgen, kama, bayrak/flama, kanal, range kırılımı),
harmonikler (ZigZag + Fibonacci oranları: Gartley, Bat, Alt-Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, ABCD), Fibonacci seviyeleri,
RSI/MACD uyumsuzlukları, piyasa yapısı (HH/HL/LH/LL, BOS/CHoCH, likidite süpürme, eşit tepe/dip, order block) ve standart araçlar
(EMA 9/21/50, ADX, Bollinger sıkışma, StochRSI, OBV, Ichimoku, Supertrend). Elliott dalga sayımı GÜVENİLİR olmadığı için bilerek yok.
Çıktı: ~500-850 karakterlik kompakt Türkçe metin (LLM kotası dostu; ek çağrı yok). Kalitesi düşük formasyonlar elenir."""
import numpy as np, pandas as pd
import levels
def fp(x):
    """Kompakt fiyat biçimi (büyük fiyatlarda ondalıksız)."""
    ref = abs(levels._REF[0] or x)
    d = 0 if ref >= 1000 else 1 if ref >= 100 else 2 if ref >= 10 else 3 if ref >= 1 else 4 if ref >= 0.1 else 5 if ref >= 0.01 else 7
    return f"{x:,.{d}f}"

MAX_CHARS = 850
TOL = 0.04   # harmonik oran toleransı (mutlak)

# ---------------- temel yardımcılar ----------------
def _num(x, d=2): return f"{x:.{d}f}".replace(".", ",")

def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def _ewm(x, span): return pd.Series(x).ewm(span=span, adjust=False).mean().values

def _rsi(c, n=14):
    s = pd.Series(c); d = s.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / dn.ewm(alpha=1/n, adjust=False).mean().replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50).values

def fractals(h, l, w=3):
    """Onaylı fraktal pivotlar: [(idx, fiyat, 'H'|'L')]. Pivot j yalnızca j+w kapanınca onaylanır (son w mum aday olamaz)."""
    out = []; n = len(h)
    for j in range(w, n - w):
        if h[j] >= h[j-w:j+w+1].max() and h[j] > h[j-1]: out.append((j, h[j], "H"))
        if l[j] <= l[j-w:j+w+1].min() and l[j] < l[j-1]: out.append((j, l[j], "L"))
    return sorted(out)

def zigzag(h, l, thr):
    """ATR-eşikli ZigZag: [(idx, fiyat, 'H'|'L')]; son eleman henüz onaylanmamış (süren) uç olabilir."""
    n = len(h); piv = []; d = 0; hi_i = lo_i = 0
    for j in range(1, n):
        if d == 0:
            if h[j] > h[hi_i]: hi_i = j
            if l[j] < l[lo_i]: lo_i = j
            if h[hi_i] - l[j] >= thr and hi_i < j: piv.append((hi_i, h[hi_i], "H")); d = -1; lo_i = j
            elif h[j] - l[lo_i] >= thr and lo_i < j: piv.append((lo_i, l[lo_i], "L")); d = 1; hi_i = j
            continue
        if d == 1:                                   # yukarı bacak: tepeyi izle
            if h[j] >= h[hi_i]: hi_i = j
            elif h[hi_i] - l[j] >= thr: piv.append((hi_i, h[hi_i], "H")); d = -1; lo_i = j
        else:                                        # aşağı bacak: dibi izle
            if l[j] <= l[lo_i]: lo_i = j
            elif h[j] - l[lo_i] >= thr: piv.append((lo_i, l[lo_i], "L")); d = 1; hi_i = j
    if piv:                                          # süren uç (onaylanmamış)
        if d == 1 and hi_i > piv[-1][0]: piv.append((hi_i, h[hi_i], "H"))
        elif d == -1 and lo_i > piv[-1][0]: piv.append((lo_i, l[lo_i], "L"))
    return piv

# ---------------- mum formasyonları ----------------
def candles(o, h, l, c, v, atr, fr, k):
    """Son mum (k) bitişli 1-3 mumluk formasyonlar. Puan: bağlam (trend) + seviye + hacim. Puan>=2 olanlar raporlanır."""
    A = atr[k]; px = c[k]
    if A <= 0: return []
    body = lambda j: abs(c[j] - o[j]); rng = lambda j: max(h[j] - l[j], 1e-12)
    up = lambda j: h[j] - max(o[j], c[j]); lo = lambda j: min(o[j], c[j]) - l[j]
    green = lambda j: c[j] > o[j]; red = lambda j: c[j] < o[j]
    pre = (c[k-1] - c[max(0, k-6)]) / A if k >= 6 else 0.0      # önceki 5 mumun yönü (ATR cinsinden)
    dn_t, up_t = pre <= -1.5, pre >= 1.5
    sup = [p for (j, p, t) in fr if t == "L" and j < k - 1 and k - j <= 120]; res = [p for (j, p, t) in fr if t == "H" and j < k - 1 and k - j <= 120]
    at_sup = any(abs(l[k] - s) <= 0.6 * A or (l[k] <= s <= c[k]) for s in sup); at_res = any(abs(h[k] - r) <= 0.6 * A or (c[k] <= r <= h[k]) for r in res)
    vr = v[k] / v[max(0, k-20):k].mean() if k >= 5 and v[max(0, k-20):k].mean() > 0 else 1.0
    out = []
    def add(name, bias, base, ctx_ok, lvl):   # bias: +1 boğa, -1 ayı, 0 nötr
        s = base + (1 if ctx_ok else 0) + (1 if lvl else 0) + (1 if vr >= 1.3 else 0)
        out.append((s, name, bias, lvl, vr))
    b, r_ = body(k), rng(k)
    if r_ >= 0.5 * A and b <= 0.1 * r_: add("Doji", 0, 1, up_t or dn_t, at_sup or at_res)
    if r_ >= 0.8 * A and b > 0 and lo(k) >= 2 * b and up(k) <= 0.15 * r_ and min(o[k], c[k]) >= l[k] + 0.6 * r_:
        if dn_t: add("Çekiç", 1, 1, True, at_sup)
        elif up_t: add("Asılı adam", -1, 1, True, at_res)
    if r_ >= 0.8 * A and b > 0 and up(k) >= 2 * b and lo(k) <= 0.15 * r_ and max(o[k], c[k]) <= h[k] - 0.6 * r_:
        if up_t: add("Kayan yıldız", -1, 1, True, at_res)
        elif dn_t: add("Ters çekiç", 1, 1, True, at_sup)
    if r_ >= 1.2 * A and b <= 0.25 * r_ and not out:
        if lo(k) >= 0.66 * r_: add("Pin bar (alt fitil)", 1, 1, dn_t, at_sup)
        elif up(k) >= 0.66 * r_: add("Pin bar (üst fitil)", -1, 1, up_t, at_res)
    if b >= 0.9 * r_ and r_ >= 1.0 * A: add("Marubozu " + ("boğa" if green(k) else "ayı"), 1 if green(k) else -1, 1, True, False)
    if k >= 1:
        a = k - 1
        if red(a) and green(k) and o[k] <= c[a] and c[k] >= o[a] and body(a) >= 0.3 * A and b > body(a): add("Yutan boğa", 1, 1, dn_t, at_sup)
        if green(a) and red(k) and o[k] >= c[a] and c[k] <= o[a] and body(a) >= 0.3 * A and b > body(a): add("Yutan ayı", -1, 1, up_t, at_res)
        if body(a) >= 0.8 * A and b <= 0.5 * body(a) and max(o[k], c[k]) <= max(o[a], c[a]) and min(o[k], c[k]) >= min(o[a], c[a]) and green(a) != green(k) and b > 0.05 * A:
            add("Harami " + ("boğa" if green(k) else "ayı"), 1 if green(k) else -1, 1, (dn_t if green(k) else up_t), at_sup if green(k) else at_res)
        if red(a) and green(k) and body(a) >= 0.8 * A and o[k] <= c[a] and (o[a] + c[a]) / 2 < c[k] < o[a]: add("Delici hat", 1, 1, dn_t, at_sup)
        if green(a) and red(k) and body(a) >= 0.8 * A and o[k] >= c[a] and o[a] < c[k] < (o[a] + c[a]) / 2: add("Kara bulut", -1, 1, up_t, at_res)
        if abs(h[a] - h[k]) <= 0.1 * A and green(a) and red(k) and (up_t or at_res): add("Cımbız tepe", -1, 1, up_t, at_res)
        if abs(l[a] - l[k]) <= 0.1 * A and red(a) and green(k) and (dn_t or at_sup): add("Cımbız dip", 1, 1, dn_t, at_sup)
        if h[k] < h[a] and l[k] > l[a]: add("İç mum (inside bar)", 0, 1, False, False)
        elif h[k] > h[a] and l[k] < l[a] and r_ >= 1.2 * A: add("Dış mum (outside bar)", 0, 1, False, False)
    if k >= 2:
        a, bb = k - 1, k - 2
        if red(bb) and body(bb) >= 0.8 * A and body(a) <= 0.3 * body(bb) and green(k) and c[k] > (o[bb] + c[bb]) / 2: add("Sabah yıldızı", 1, 2, dn_t, at_sup)
        if green(bb) and body(bb) >= 0.8 * A and body(a) <= 0.3 * body(bb) and red(k) and c[k] < (o[bb] + c[bb]) / 2: add("Akşam yıldızı", -1, 2, up_t, at_res)
        if all(green(j) and body(j) >= 0.4 * A for j in (bb, a, k)) and c[a] > c[bb] and c[k] > c[a] and o[a] >= o[bb] and o[k] >= o[a]: add("Üç beyaz asker", 1, 2, dn_t or not up_t, at_sup)
        if all(red(j) and body(j) >= 0.4 * A for j in (bb, a, k)) and c[a] < c[bb] and c[k] < c[a] and o[a] <= o[bb] and o[k] <= o[a]: add("Üç kara karga", -1, 2, up_t or not dn_t, at_res)
    out = [x for x in out if x[0] >= 3 or (x[0] >= 2 and x[2] != 0 and x[3])]
    out.sort(key=lambda x: -x[0]); res_l = []
    for s, name, bias, lvl, vr_ in out[:2]:
        tags = []
        if lvl: tags.append("destekte" if bias > 0 else "dirençte" if bias < 0 else "seviyede")
        if vr_ >= 1.3: tags.append(f"hacim {_num(vr_, 1)}x")
        res_l.append((s, f"{name}" + (f" ({', '.join(tags)})" if tags else "")))
    return res_l

# ---------------- grafik formasyonları ----------------
def _near(a, b, tol): return abs(a - b) <= tol

def double_triple(piv, A, px, k, c):
    out = []
    for kind in ("H", "L"):
        P = [p for p in piv if p[2] == kind]
        if len(P) < 2: continue
        opp = lambda i0, i1: [q for q in piv if q[2] != kind and i0 < q[0] < i1]
        tol = max(0.5 * A, 0.002 * px)
        # üçlü
        if len(P) >= 3:
            p1, p2, p3 = P[-3:]
            if k - p3[0] <= 15 and max(p1[1], p2[1], p3[1]) - min(p1[1], p2[1], p3[1]) <= tol and p3[0] - p1[0] >= 16 and opp(p1[0], p3[0]):
                nk = (min if kind == "H" else max)(q[1] for q in opp(p1[0], p3[0])); lv = np.mean([p1[1], p2[1], p3[1]]); hgt = abs(lv - nk)
                if hgt < 3 * A or (c[k] < nk - hgt if kind == 'H' else c[k] > nk + hgt): continue
                brk = c[k] < nk if kind == "H" else c[k] > nk
                out.append((3, f"Üçlü {'tepe' if kind == 'H' else 'dip'} {fp(lv)}, boyun {fp(nk)}, " + (f"boyun kırıldı → hedef {fp(nk - hgt if kind == 'H' else nk + hgt)}" if brk else f"boyun kırılmadı (hedef {fp(nk - hgt if kind == 'H' else nk + hgt)})")))
                continue
        p1, p2 = P[-2:]
        if k - p2[0] <= 15 and p2[0] - p1[0] >= 8 and _near(p1[1], p2[1], tol):
            mid = opp(p1[0], p2[0])
            if not mid: continue
            nk = (min if kind == "H" else max)(q[1] for q in mid); lv = (p1[1] + p2[1]) / 2; hgt = abs(lv - nk)
            if hgt < 3 * A: continue
            if (c[k] < nk - hgt) if kind == 'H' else (c[k] > nk + hgt): continue   # hedef zaten gerçekleşti
            brk = c[k] < nk if kind == "H" else c[k] > nk; tgt = nk - hgt if kind == "H" else nk + hgt
            out.append((3 if brk else 2, f"Çift {'tepe' if kind == 'H' else 'dip'} {fp(p1[1])}/{fp(p2[1])}, boyun {fp(nk)}, " + (f"boyun kırıldı → hedef {fp(tgt)}" if brk else f"boyun kırılmadı (hedef {fp(tgt)})")))
    return out

def head_shoulders(piv, A, px, k, c):
    out = []
    for kind in ("H", "L"):
        P = [p for p in piv if p[2] == kind]
        if len(P) < 3: continue
        s1, hd, s2 = P[-3:]
        if k - s2[0] > 15: continue
        sg = 1 if kind == "H" else -1
        if sg * (hd[1] - s1[1]) < 1.0 * A or sg * (hd[1] - s2[1]) < 1.0 * A or abs(s1[1] - s2[1]) > 0.5 * abs(hd[1] - (s1[1] + s2[1]) / 2) or min(hd[0] - s1[0], s2[0] - hd[0]) < 6: continue
        t1 = [q for q in piv if q[2] != kind and s1[0] < q[0] < hd[0]]; t2 = [q for q in piv if q[2] != kind and hd[0] < q[0] < s2[0]]
        if not t1 or not t2: continue
        a, b = t1[-1], t2[0]
        if abs(hd[1] - a[1]) < 3 * A: continue
        slope = (b[1] - a[1]) / max(1, b[0] - a[0]); nk_now = b[1] + slope * (k - b[0])
        nk_hd = a[1] + slope * (hd[0] - a[0]); hgt = abs(hd[1] - nk_hd); brk = c[k] < nk_now if kind == "H" else c[k] > nk_now
        tgt = nk_now - hgt if kind == "H" else nk_now + hgt
        out.append((3 if brk else 2, f"{'OBO (omuz-baş-omuz)' if kind == 'H' else 'Ters OBO (TOBO)'} baş {fp(hd[1])}, boyun ≈{fp(nk_now)}, " + (f"kırıldı → hedef {fp(tgt)}" if brk else f"kırılmadı (hedef {fp(tgt)})")))
    return out

def _fit(pts, k):
    x = np.array([p[0] for p in pts], float); y = np.array([p[1] for p in pts], float)
    m, b0 = np.polyfit(x, y, 1); res = np.abs(y - (m * x + b0)).max()
    return m, b0, res

def trend_shapes(piv, A, px, k, c, h, l):
    for pv in (piv, piv[:-1]):          # süren (onaysız) son pivotu içeren ve içermeyen iki deneme
        r = _trend_shapes(pv, A, px, k, c, h, l)
        if r: return r
    return []

def _trend_shapes(piv, A, px, k, c, h, l):
    """Üçgen / kama / kanal: son 2-4 tepe ve dip pivotuna doğru fit. Eğim ATR/mum cinsinden."""
    H = [p for p in piv if p[2] == "H" and k - p[0] <= 90][-4:]; L = [p for p in piv if p[2] == "L" and k - p[0] <= 90][-4:]
    if len(H) < 2 or len(L) < 2 or max(H[-1][0], L[-1][0]) < k - 15: return []
    mh, bh, rh = _fit(H, k); ml, bl, rl = _fit(L, k)
    sh, sl = mh / A, ml / A; up_k, lo_k = mh * k + bh, ml * k + bl
    if up_k <= lo_k or (up_k - lo_k) > 14 * A: return []
    first0 = min(H[0][0], L[0][0]); w0 = (mh * first0 + bh) - (ml * first0 + bl)
    if w0 < 3 * A or k - first0 < 15: return []
    if rh > max(0.7 * A, 0.1 * w0) or rl > max(0.7 * A, 0.1 * w0): return []
    flat = 0.03; first = min(H[0][0], L[0][0]); wid0 = (mh * first + bh) - (ml * first + bl)
    conv = (up_k - lo_k) < 0.85 * wid0
    name = None
    if abs(sh) < flat and sl > flat: name = "Yükselen üçgen"; bias = "üst kırılım"
    elif abs(sl) < flat and sh < -flat: name = "Alçalan üçgen"; bias = "alt kırılım"
    elif sh < -flat and sl > flat: name = "Simetrik üçgen"; bias = "yön belirsiz (kırılımı bekle)"
    elif sh > flat and sl > flat and conv and sl > sh: name = "Yükselen kama"; bias = "ayı eğilimli"
    elif sh < -flat and sl < -flat and conv and sh < sl: name = "Düşen kama"; bias = "boğa eğilimli"
    elif abs(sh - sl) < 0.02 and sh > flat: name = "Yükselen kanal"; bias = "trend yönü"
    elif abs(sh - sl) < 0.02 and sh < -flat: name = "Alçalan kanal"; bias = "trend yönü"
    elif abs(sh) < flat and abs(sl) < flat and (up_k - lo_k) <= 8 * A: name = "Yatay range"; bias = "kırılımı bekle"
    if not name: return []
    pos = "üst çizgiyi KIRDI" if c[k] > up_k + 0.2 * A else "alt çizgiyi KIRDI" if c[k] < lo_k - 0.2 * A else "içinde"
    hgt = (mh * first + bh) - (ml * first + bl)
    tail = f" kırılım hedefi ±{fp(abs(hgt))}" if name.endswith("üçgen") else ""
    sc = 3 if pos != "içinde" else 2
    return [(sc, f"{name} (üst ≈{fp(up_k)}, alt ≈{fp(lo_k)}, fiyat {pos}; {bias}){tail}")]

def flags(h, l, c, A, k):
    for e in range(k - 4, max(k - 26, 12), -1):                    # direk bitişi e
        for p0 in range(max(0, e - 10), e - 2):
            move = c[e] - c[p0]
            if abs(move) >= 4 * A:
                cons = slice(e + 1, k + 1); rg = h[cons].max() - l[cons].min(); sgn = 1 if move > 0 else -1
                retr = (c[e] - (l[cons].min() if sgn > 0 else h[cons].max())) * sgn / abs(move)
                if 4 <= k - e <= 22 and retr <= 0.5 and rg <= 0.6 * abs(move) and (c[k] - c[e]) * sgn <= 0.25 * abs(move):
                    lvl = h[cons].max() if sgn > 0 else l[cons].min()
                    slope = np.polyfit(np.arange(k - e), (h[e+1:k+1] + l[e+1:k+1])[:k-e] / 2, 1)[0] / A
                    kind = "Bayrak" if abs(slope) > 0.03 else "Flama"
                    return [(3, f"{'Boğa' if sgn > 0 else 'Ayı'} {'bayrağı' if kind == 'Bayrak' else 'flaması'} (direk {_num(abs(move)/A, 1)} ATR, geri çekilme %{retr*100:.0f}, kırılım seviyesi {fp(lvl)}, hedef ≈{fp(lvl + sgn*abs(move))})")]
    return []

def range_break(h, l, c, A, k, px):
    s = max(0, k - 45); H, L = h[s:k-2].max(), l[s:k-2].min()
    if H - L > 7 * A or H - L < 1.5 * A or k - s < 25: return []
    th = sum(1 for x in h[s:k-2] if x >= H - 0.3 * A); tl = sum(1 for x in l[s:k-2] if x <= L + 0.3 * A)
    if th < 2 or tl < 2: return []
    r5 = c[k-4:k+1]
    if (r5 > H + 0.2 * A).any() and c[k] > H:
        rt = any(l[j] <= H + 0.3 * A and c[j] > H for j in range(k - 4, k + 1)) and c[k] > H + 0.2 * A
        return [(3, f"Range yukarı kırılım (üst {fp(H)}, alt {fp(L)}" + (", retest tuttu" if rt else ", retest bekleniyor") + f", hedef ≈{fp(H + (H - L))})")]
    if (r5 < L - 0.2 * A).any() and c[k] < L:
        rt = any(h[j] >= L - 0.3 * A and c[j] < L for j in range(k - 4, k + 1)) and c[k] < L - 0.2 * A
        return [(3, f"Range aşağı kırılım (alt {fp(L)}, üst {fp(H)}" + (", retest tuttu" if rt else ", retest bekleniyor") + f", hedef ≈{fp(L - (H - L))})")]
    return []

# ---------------- harmonikler ----------------
R = lambda x, lo, hi: lo - TOL <= x <= hi + TOL
# ad: (AB/XA, BC/AB, D tipi, D aralığı)  D tipi: 'AD' = |D-A|/XA ; 'XC' = D, XC bacağının geri çekilişi (Cypher/Shark)
HARM = {"Gartley": ((0.618, 0.618), (0.382, 0.886), "AD", (0.786, 0.786)), "Bat": ((0.382, 0.5), (0.382, 0.886), "AD", (0.886, 0.886)),
        "Alt-Bat": ((0.382, 0.382), (0.382, 0.886), "AD", (1.13, 1.13)), "Butterfly": ((0.786, 0.786), (0.382, 0.886), "AD", (1.272, 1.618)),
        "Crab": ((0.382, 0.618), (0.382, 0.886), "AD", (1.618, 1.618)), "Derin Crab": ((0.886, 0.886), (0.382, 0.886), "AD", (1.618, 1.618)),
        "Cypher": ((0.382, 0.618), (1.13, 1.414), "XC", (0.786, 0.786)), "Shark": ((1.13, 1.618), (1.618, 2.24), "XC", (0.886, 1.13))}

def harmonics(piv, A, px, k, h, l, c):
    out = []; n = len(piv)
    for m in (n - 1, n - 2):                       # C pivotu: son pivot veya sondan ikinci
        if m < 3: continue
        X, Ap, B, Cp = piv[m-3], piv[m-2], piv[m-1], piv[m]
        if k - Cp[0] > 60 or k - X[0] > 160: continue
        bull = Cp[2] == "H"                        # X dip, A tepe, B dip, C tepe -> D dip (boğa)
        sg = 1 if bull else -1                     # D yönü: boğada aşağı
        XA, AB, BC = abs(Ap[1] - X[1]), abs(B[1] - Ap[1]), abs(Cp[1] - B[1])
        if XA < 3 * A or AB <= 0 or BC <= 0: continue
        e = float(l[Cp[0]+1:k+1].min()) if bull and Cp[0] < k else float(h[Cp[0]+1:k+1].max()) if (not bull) and Cp[0] < k else Cp[1]   # C'den beri D yönündeki en uç
        if m == n - 2 and not ((e < Cp[1]) if bull else (e > Cp[1])): continue
        ab_xa, bc_ab = AB / XA, BC / AB
        for name, ((a0, a1), (b0, b1), dt, (d0, d1)) in HARM.items():
            if not (R(ab_xa, a0, a1) and R(bc_ab if dt == "AD" else BC / XA, b0, b1)): continue
            if dt == "AD": ds = [Ap[1] - sg * 0 + (-sg) * 0] and sorted([Ap[1] + sg * 0 - (d * XA) * (1 if bull else -1) * -1 * -1 for d in (d0 - TOL, d1 + TOL)])
            else: XC = abs(Cp[1] - X[1]); ds = sorted([Cp[1] - sg * 0 + (-1 if bull else 1) * d * XC for d in (d0 - TOL, d1 + TOL)])
            if dt == "AD":   # D = A -/+ d*XA (boğada A'dan aşağı)
                ds = sorted([Ap[1] - (1 if bull else -1) * d * XA for d in (d0 - TOL, d1 + TOL)])
            lo_p, hi_p = ds[0], ds[1]
            inz = lo_p - 0.4 * A <= e <= hi_p + 0.4 * A
            dist = (c[k] - hi_p) / A if bull else (lo_p - c[k]) / A       # PRZ'ye kalan mesafe (ATR; >0: henüz ulaşmadı)
            if inz and k - int(np.argmin(l[Cp[0]+1:k+1]) + Cp[0] + 1 if bull else np.argmax(h[Cp[0]+1:k+1]) + Cp[0] + 1) <= 8:
                st = "PRZ'de (tamamlandı)"; sc = 3
            elif (e > hi_p if bull else e < lo_p) and 0 < dist <= 2.0 and Cp[0] >= k - 40:
                st = f"PRZ'ye {_num(dist, 1)} ATR kaldı"; sc = 2
            else: continue
            inval = X[1] if name in ("Gartley", "Bat", "Cypher") else (lo_p - A if bull else hi_p + A)
            if name in ("Gartley", "Bat", "Cypher") and ((bull and c[k] < X[1]) or (not bull and c[k] > X[1])): continue
            ad = abs(Ap[1] - e) / XA
            out.append((sc, f"{'Boğa' if bull else 'Ayı'} {name} PRZ {fp(lo_p)}–{fp(hi_p)} [{st}] (AB/XA {_num(ab_xa)}, BC/AB {_num(bc_ab)}, AD/XA {_num(ad)}; geçersiz {'<' if bull else '>'}{fp(inval)}; ilk hedef {fp(e + (1 if bull else -1) * 0.382 * abs(Ap[1] - e))})"))
    # ABCD
    for m in (n - 1, n - 2):
        if m < 2: continue
        Ap, B, Cp = piv[m-2], piv[m-1], piv[m]
        if k - Cp[0] > 40: continue
        bull = Cp[2] == "H"; AB, BC = abs(B[1] - Ap[1]), abs(Cp[1] - B[1])
        if AB < 3 * A or not (0.382 - TOL <= BC / AB <= 0.886 + TOL): continue
        e = float(l[Cp[0]+1:k+1].min()) if bull and Cp[0] < k else float(h[Cp[0]+1:k+1].max()) if (not bull) and Cp[0] < k else Cp[1]
        if (bull and e >= Cp[1]) or (not bull and e <= Cp[1]): continue
        ratio = abs(Cp[1] - e) / AB
        for t in (1.0, 1.272):
            if abs(ratio - t) <= 0.06 * t and c[k] <= Cp[1] + 0 if bull else False: pass
        hit = [t for t in (1.0, 1.272) if abs(ratio - t) <= 0.06 * t]
        if hit and abs(c[k] - e) <= 1.5 * A and (np.argmin(l[Cp[0]+1:k+1]) if bull else np.argmax(h[Cp[0]+1:k+1])) + Cp[0] + 1 >= k - 6:
            out.append((2, f"{'Boğa' if bull else 'Ayı'} ABCD D≈{fp(e)} [tamamlandı] (CD/AB {_num(ratio)}, BC/AB {_num(BC/AB)}; geçersiz {'<' if bull else '>'}{fp(e - (1 if bull else -1) * A)})"))
    out.sort(key=lambda x: -x[0]); return out[:2]

def fib(piv, A, px, k):
    if len(piv) < 2: return None
    a, b = piv[-2], piv[-1]; leg = b[1] - a[1]
    if abs(leg) < 4 * A or k - b[0] > 80: return None
    up = leg > 0; lv = {f"{r}".replace(".", ","): b[1] - r * leg for r in (0.382, 0.5, 0.618, 0.786)}
    ext = {"1,272": b[1] + 0.272 * leg, "1,618": b[1] + 0.618 * leg}
    near = sorted(lv.items(), key=lambda kv: abs(kv[1] - px))[:2]
    s = f"Fib ({'dip' if up else 'tepe'} {fp(a[1])}→{'tepe' if up else 'dip'} {fp(b[1])}): " + " ".join(f"{n}={fp(v)}" + ("*" if abs(v - px) <= 0.5 * A else "") for n, v in sorted(near, key=lambda kv: kv[0]))
    s += f" · ext 1,272={fp(ext['1,272'])}"
    if abs(lv["0,618"] - px) <= 0.6 * A or abs((lv["0,618"] + lv["0,786"]) / 2 - px) <= 0.4 * A: s += " · altın bölge yakın"
    return s

# ---------------- uyumsuzluk ----------------
def divergences(h, l, c, A, k, rsi, macd):
    """Fraktal pivotlar üzerinde RSI/MACD düzenli+gizli uyumsuzluk. Her iki osilatör aynı yönde ise tek satırda birleşir."""
    fr = fractals(h, l, 3); found = {}
    for kind in ("H", "L"):
        P = [p for p in fr if p[2] == kind and k - p[0] <= 50]
        if len(P) < 2 or k - P[-1][0] > 10: continue
        p1, p2 = P[-2], P[-1]
        if p2[0] - p1[0] < 6: continue
        dp = p2[1] - p1[1]
        for nm, osc, thr in (("RSI", rsi, 3.0), ("MACD", macd, 0.15 * A)):
            do = osc[p2[0]] - osc[p1[0]]
            if kind == "H":
                if dp > 0.3 * A and do < -thr and (nm != "RSI" or rsi[p1[0]] >= 55): found.setdefault(("düzenli ayı", p2[0], "fiyat HH, osilatör LH"), []).append(nm)
                if dp < -0.3 * A and do > thr: found.setdefault(("gizli ayı", p2[0], "fiyat LH, osilatör HH"), []).append(nm)
            else:
                if dp < -0.3 * A and do > thr and (nm != "RSI" or rsi[p1[0]] <= 45): found.setdefault(("düzenli boğa", p2[0], "fiyat LL, osilatör HL"), []).append(nm)
                if dp > 0.3 * A and do < -thr: found.setdefault(("gizli boğa", p2[0], "fiyat HL, osilatör LL"), []).append(nm)
    out = []
    for (nm, j, why), osc in found.items():
        out.append((2 + (len(osc) > 1), f"{'+'.join(osc)} {nm} uyumsuzluğu ({why}, {k - j} mum önce)"))
    out.sort(key=lambda x: -x[0]); return out

# ---------------- piyasa yapısı ----------------
def structure(o, h, l, c, v, A, k, fr, zz):
    parts = []
    H = [p for p in fr if p[2] == "H"][-3:]; L = [p for p in fr if p[2] == "L"][-3:]
    if len(H) >= 2 and len(L) >= 2:
        hh = H[-1][1] > H[-2][1]; hl = L[-1][1] > L[-2][1]
        st = {(True, True): "HH/HL (yükselen)", (False, False): "LH/LL (düşen)", (True, False): "HH/LL (genişleyen)", (False, True): "LH/HL (daralan)"}[(hh, hl)]
        prior = "up" if (hh and hl) else "down" if (not hh and not hl) else None
        parts.append(st); sh, sl = H[-1], L[-1]; cut = k - 10
        up_b = [j for j in range(max(sh[0] + 1, cut), k + 1) if c[j] > sh[1]]
        dn_b = [j for j in range(max(sl[0] + 1, cut), k + 1) if c[j] < sl[1]]
        if up_b: parts.append(("CHoCH↑" if prior == "down" else "BOS↑") + f" ({k - up_b[0]} mum önce, {fp(sh[1])})")
        elif dn_b: parts.append(("CHoCH↓" if prior == "up" else "BOS↓") + f" ({k - dn_b[0]} mum önce, {fp(sl[1])})")
    # eşit tepe/dip (likidite havuzu)
    for kind, nm in (("H", "tepe"), ("L", "dip")):
        P = [p for p in fr if p[2] == kind and k - p[0] <= 80]
        for i in range(len(P) - 1, 0, -1):
            if abs(P[i][1] - P[i-1][1]) <= 0.15 * A and P[i][0] - P[i-1][0] >= 5:
                lvl = max(P[i][1], P[i-1][1]) if kind == "H" else min(P[i][1], P[i-1][1])
                swept = any((h[j] > lvl and c[j] < lvl) if kind == "H" else (l[j] < lvl and c[j] > lvl) for j in range(P[i][0] + 1, k + 1))
                if not swept and abs(lvl - c[k]) <= 5 * A: parts.append(f"eşit {nm} {fp(lvl)} (likidite havuzu)")
                break
    # likidite süpürme: son 2 mumda ZigZag tepe/dibini iğneyle aşıp geri kapanış
    for kind in ("H", "L"):
        for p in [q for q in zz if q[2] == kind and k - q[0] <= 60 and q[0] < k - 2][::-1][:3]:
            sw = [j for j in range(k - 1, k + 1) if ((h[j] > p[1] + 0.1 * A and c[j] < p[1]) if kind == "H" else (l[j] < p[1] - 0.1 * A and c[j] > p[1]))]
            if sw: parts.append(f"likidite süpürme {'↑ (ayı sinyali)' if kind == 'H' else '↓ (boğa sinyali)'} {fp(p[1])}"); break
    # order block: >=2 ATR gövdeli itki mumu ardından son karşıt mum; mitige edilmemiş, fiyata <=4 ATR
    obs_ = []
    for j in range(max(3, k - 40), k - 1):
        if abs(c[j] - o[j]) >= 2.0 * A:
            sgn = 1 if c[j] > o[j] else -1
            for q in range(j - 1, max(0, j - 4), -1):
                if (c[q] < o[q]) if sgn > 0 else (c[q] > o[q]):
                    zlo, zhi = l[q], h[q]
                    if not any((c[x] < zlo) if sgn > 0 else (c[x] > zhi) for x in range(j + 1, k + 1)): obs_.append((sgn, zlo, zhi))
                    break
    px = c[k]
    below = [z for z in obs_ if z[0] > 0 and z[2] <= px + 0.3 * A and px - z[2] <= 4 * A]; above = [z for z in obs_ if z[0] < 0 and z[1] >= px - 0.3 * A and z[1] - px <= 4 * A]
    if below: z = max(below, key=lambda z: z[2]); parts.append(f"boğa OB {fp(z[1])}–{fp(z[2])}")
    if above: z = min(above, key=lambda z: z[1]); parts.append(f"ayı OB {fp(z[1])}–{fp(z[2])}")
    return parts

# ---------------- standart araçlar ----------------
def tools(o, h, l, c, v, A, k, rsi):
    P = []; n = len(c)
    e9, e21, e50 = _ewm(c, 9), _ewm(c, 21), _ewm(c, 50)
    order = "9>21>50 (yükselen)" if e9[k] > e21[k] > e50[k] else "9<21<50 (düşen)" if e9[k] < e21[k] < e50[k] else "karışık"
    sgn = np.sign(e9 - e21); cr = [j for j in range(k, max(k - 12, 1), -1) if sgn[j] != sgn[j-1]]
    P.append("EMA " + order + (f", {k - cr[0]} mum önce {'yukarı' if sgn[k] > 0 else 'aşağı'} kesişim" if cr else ""))
    # ADX
    up_m = np.diff(h, prepend=h[0]); dn_m = -np.diff(l, prepend=l[0])
    pdm = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0); mdm = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    sm = lambda x: pd.Series(x).ewm(alpha=1/14, adjust=False).mean().values
    trs = sm(tr); pdi = 100 * sm(pdm) / np.where(trs > 0, trs, np.nan); mdi = 100 * sm(mdm) / np.where(trs > 0, trs, np.nan)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi); adx = pd.Series(dx).ewm(alpha=1/14, adjust=False).mean().values
    if not np.isnan(adx[k]): P.append(f"ADX {adx[k]:.0f} ({'güçlü' if adx[k] >= 25 else 'zayıf/yatay'} trend, {'+DI' if pdi[k] > mdi[k] else '-DI'} üstün)")
    # Bollinger
    sma = pd.Series(c).rolling(20).mean().values; sd = pd.Series(c).rolling(20).std(ddof=0).values; w = 4 * sd / sma
    wk = w[max(0, k - 119):k + 1]; wk = wk[~np.isnan(wk)]
    if len(wk) > 40:
        pr = (wk < w[k]).mean() * 100; pb = (c[k] - (sma[k] - 2 * sd[k])) / (4 * sd[k]) if sd[k] > 0 else .5
        P.append(f"BB genişlik %{_num(w[k]*100,1)} ({'SIKIŞMA' if pr <= 15 else 'geniş' if pr >= 85 else 'normal'}), %B {_num(pb)}")
    # StochRSI
    rs = pd.Series(rsi); mn, mx = rs.rolling(14).min(), rs.rolling(14).max(); st = ((rs - mn) / (mx - mn).replace(0, np.nan)).rolling(3).mean() * 100
    if not np.isnan(st.iloc[k]) and (st.iloc[k] >= 80 or st.iloc[k] <= 20): P.append(f"StochRSI {st.iloc[k]:.0f} ({'aşırı alım' if st.iloc[k] >= 80 else 'aşırı satım'})")
    # OBV
    obv = np.cumsum(np.where(np.diff(c, prepend=c[0]) > 0, v, np.where(np.diff(c, prepend=c[0]) < 0, -v, 0.0)))
    if k >= 20:
        od, pdx = obv[k] - obv[k-20], c[k] - c[k-20]
        P.append("OBV " + ("↑" if od > 0 else "↓") + (" (fiyatla uyumsuz!)" if od * pdx < 0 and abs(pdx) > 1 * A else ""))
    # Ichimoku (bulut 26 mum kaydırılmış: bugünkü bulut 26 mum önceki hesaplardan -> look-ahead yok)
    if k >= 78:
        hh = lambda a, b, j: (h[j-a+1:j+1].max() + l[j-a+1:j+1].min()) / 2
        j = k - 26; sa = (hh(9, 0, j) + hh(26, 0, j)) / 2; sb = hh(52, 0, j)
        top, bot = max(sa, sb), min(sa, sb); tk, kj = hh(9, 0, k), hh(26, 0, k)
        P.append(f"Ichimoku: {'bulut üstü' if c[k] > top else 'bulut altı' if c[k] < bot else 'bulut içi'}, TK {'>' if tk > kj else '<'} KJ, bulut {fp(bot)}–{fp(top)}")
    # Supertrend (10,3)
    at10 = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(10).mean().values
    hl2 = (h + l) / 2; ub, lb = hl2 + 3 * at10, hl2 - 3 * at10; fu, fl = ub.copy(), lb.copy(); dr = np.ones(n); fl_i = None
    for j in range(11, n):
        fu[j] = ub[j] if (ub[j] < fu[j-1] or c[j-1] > fu[j-1]) else fu[j-1]
        fl[j] = lb[j] if (lb[j] > fl[j-1] or c[j-1] < fl[j-1]) else fl[j-1]
        dr[j] = 1 if (dr[j-1] == -1 and c[j] > fu[j-1]) else -1 if (dr[j-1] == 1 and c[j] < fl[j-1]) else dr[j-1]
    flips = [j for j in range(k, max(k - 15, 12), -1) if dr[j] != dr[j-1]]
    P.append(f"Supertrend {'AL' if dr[k] > 0 else 'SAT'} ({fp(fl[k] if dr[k] > 0 else fu[k])})" + (f", {k - flips[0]} mum önce döndü" if flips else ""))
    return P

# ---------------- ana giriş ----------------
def text(df, i=None, interval="1h"):
    """Satır i'ye kadar (dahil, kapanmış mumlar) formasyon bloğu. Hata olursa '' (akışı bozmaz)."""
    if i is None: i = len(df) - 1
    d = df.iloc[:i + 1]
    if len(d) < 80: return ""
    try:
        o, h, l, c, v = (d[x].values.astype(float) for x in ("open", "high", "low", "close", "volume")); k = len(c) - 1
        if len(c) > 400: o, h, l, c, v = (x[-400:] for x in (o, h, l, c, v)); k = len(c) - 1
        atr = _atr(h, l, c); A = float(atr[k]); px = float(c[k]); levels._REF[0] = px
        if not A > 0: return ""
        rsi = _rsi(c); macd = _ewm(c, 12) - _ewm(c, 26)
        fr = fractals(h, l, 3)
        zz = zigzag(h[-250:], l[-250:], max(2.0 * A, 0.004 * px)); off = len(h) - len(h[-250:]); zz = [(j + off, p, t) for j, p, t in zz]
        zz_f = zigzag(h[-120:], l[-120:], max(1.2 * A, 0.0025 * px)); off2 = len(h) - len(h[-120:]); zz_f = [(j + off2, p, t) for j, p, t in zz_f]
        cand = candles(o, h, l, c, v, atr, fr, k)
        chart = double_triple(zz, A, px, k, c) + head_shoulders(zz, A, px, k, c) + trend_shapes(zz_f, A, px, k, c, h, l) + flags(h, l, c, A, k) + range_break(h, l, c, A, k, px)
        chart.sort(key=lambda x: -x[0])
        harm = harmonics(zz, A, px, k, h, l, c); fb = fib(zz, A, px, k); dv = divergences(h, l, c, A, k, rsi, macd); ms = structure(o, h, l, c, v, A, k, fr, zz); tl = tools(o, h, l, c, v, A, k, rsi)
        L = [f"Formasyonlar (hesaplanmış, yalnızca kapanmış mumlar; burada olmayan formasyonu UYDURMA):"]
        L.append("Mum: " + ("; ".join(t for _, t in cand) if cand else "anlamlı mum formasyonu yok"))
        if chart: L.append("Grafik: " + "; ".join(t for _, t in chart[:2]))
        if harm: L.append("Harmonik: " + "; ".join(t for _, t in harm[:1]))
        if fb: L.append(fb)
        if dv: L.append("Uyumsuzluk: " + "; ".join(t for _, t in dv[:2]))
        if ms: L.append("Yapı: " + ", ".join(ms))
        L.append("Araçlar: " + " · ".join(tl))
        s = "\n".join(L)
        # kompaktlık: sığmazsa en düşük öncelikli parçaları at
        drop = [lambda L: [x for x in L if not x.startswith("Uyumsuzluk")], lambda L: [x for x in L if not x.startswith("Fib")]]
        for fn in drop:
            if len(s) <= MAX_CHARS: break
            L = fn(L); s = "\n".join(L)
        if len(s) > MAX_CHARS:     # son çare: araçlar satırını kısalt
            L[-1] = "Araçlar: " + " · ".join(tl[:5]); s = "\n".join(L)
        return s[:MAX_CHARS + 150]
    except Exception as e:
        return f"Formasyon göstergeleri hesaplanamadı: {e}"
