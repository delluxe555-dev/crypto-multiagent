#!/usr/bin/env python3
"""confluence_paper.py - SESSIZ kagit-uzeri 'HTF trend cizgisi dokunusu + tahmini likidasyon kumesi' olcumu. Mesaj/Telegram GONDERMEZ;
paper trader'a, config'ine, state'ine dokunmaz. Yalniz anahtarsiz Gate public API okur; yalniz outputs/confluence_paper/ altina yazar.
  python3 confluence_paper.py --scan                # her 15 dk: yeni dokunuslari + kontrol (rastgele) zamanlari logla, vadesi gelen sonuclari coz
  python3 confluence_paper.py --report              # birikimli istatistik (proxy basina)
  python3 confluence_paper.py --backtest [--refetch]# ~21 gunluk Gate verisinde ayni mantigin nedensel (causal) ilk gecis testi (CI'li)
Test: --dir PATH, --asof EPOCH, --backfill-bars N (ilk taramada son N mumdaki olaylari da logla; vars. 16)
!! PROXY UYARISI: kullanicinin kapali kaynak 'GCLa-sv2' cizgisi ve Coinglass sari likidasyon isi haritasi ERISILEMEZ. Burada:
   HTF cizgi proxy'leri (2s): EMA50, EMA100, Supertrend(10,3), Bollinger orta cizgisi (SMA20). Likidasyon bolgesi proxy'si: liqmap_proto/liqbt'deki
   OI-delta x kaldirac TAHMIN modeli (Gate OI'si; Binance degil). Onceki testte tahmini kume boyutunun tek basina ongorucu gucu yoktu.
TANIMLAR (hepsi nedensel):
  2s mumlar Gate 1s mumlarindan (UTC cift saat); cizgi/yon yalniz KAPANMIS son 2s mumdan. Yon d=+1 (fiyat cizginin ustunde, cizgi yukari egimli: destek) / -1.
  Dokunus: 15m mum j'nin low'u (d=+1) cizgiye <= iner ya da high'i (d=-1) >= cikar, onceki mum tamamen trend tarafindaydi; ayni (coin,proxy) icin 16 bar refrakter.
  Giris = sonraki 15m mumun acilisi. 'rejected' = dokunus mumu kapanisinda trend tarafinda mi.
  Kume: dokunus mumundan ONCEKI tahmini kume haritasi (kapanis j-1), 0.25% kutular, +-%6 pencerede; cizgi +-0.3% / +-0.5% icindeki en buyuk kutu pencerenin
  ilk 3 kutusundan biriyse cl03 / cl05 = 1 (boyut ayrica OI'nin bps'i olarak loglanir). Taraf: 'long' (altta long-liq) / 'short'.
  Sonuc: trend yonunde net getiri (1s/4s/12s, 0.05%/taraf=10bp tur) ve tersi (reversal) yonunde; CONT/REV: giristen sonra 16 bar icinde trend yonunde >=1 ATR(2s,14)
  mi (CONT) yoksa ters yonde >=1 ATR mi (REV) once geldi (ayni mumda ikisi = BOTH, hicbiri = NONE).
  Kontrol (rastgele zaman): her coin/proxy icin 4 barda 1, trend yonu olan zamanlar; kume bayragi anlik fiyat etrafinda. Excess = olay - ayni (proxy,coin,yon) kontrol ortalamasi."""
import sys, os, csv, json, time, math, fcntl, requests
import numpy as np
from datetime import datetime, timezone, timedelta
COINS = "ARB NEAR ETH BTC ETHFI GRASS SOL DOGE XRP AVAX LINK APT SUI INJ OP WLD TIA SEI ATOM DOT FET ADA LTC BNB PYTH JUP".split()
G = "https://api.gateio.ws/api/v4/futures/usdt"; STEP = 900; HZ = {"1h": 4, "4h": 16, "12h": 48}; COST = 10.0; TZ = timezone(timedelta(hours=3))
PROXIES = ["EMA50", "EMA100", "ST10_3", "BBMID20"]; LEV = {5: .15, 10: .30, 25: .25, 50: .18, 100: .12}
BW = 0.0025; WIN = 24; TOPK = 3; REFR = 16; CR_BARS = 16; CTRL_EVERY = 4; WARM = 384; WARM2 = 120; BAND = {"03": 0.003, "05": 0.005}
EVCOLS = ["id", "kind", "coin", "proxy", "bar_t", "detected_iso", "dir", "line", "px", "rejected", "atr_px", "lvl_age", "cl03_rank", "cl03_bps", "cl05_rank", "cl05_bps", "cl_side", "logged_epoch"]
OCOLS = ["id", "entry_bar_t", "entry_px", "net_trend_1h", "net_rev_1h", "net_trend_4h", "net_rev_4h", "net_trend_12h", "net_rev_12h", "cr", "resolved_epoch"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "confluence_paper"); NOW = time.time(); BACKFILL = 16

def iso(e): return datetime.fromtimestamp(e, TZ).strftime("%Y-%m-%d %H:%M:%S%z")
def log(msg):
    try:
        with open(os.path.join(OUT, "scan.log"), "a") as f: f.write(f"{iso(NOW)} {msg}\n")
    except Exception: pass
def get(u, p=None):
    for k in range(3):
        try:
            r = requests.get(u, params=p, timeout=20)
            if r.status_code == 429: time.sleep(1.5 * (k + 1)); continue
            if r.status_code != 200: return None
            return r.json()
        except Exception: time.sleep(0.7)
    return None
def read_csv(p):
    try:
        with open(p, newline="") as f: return list(csv.DictReader(f))
    except Exception: return []
def write_csv(p, cols, rows):
    tmp = p + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); [w.writerow({k: r.get(k, "") for k in cols}) for r in rows]
    os.replace(tmp, p)

# ---------------------------------------------------------------- data
def fetch_raw(coin):
    c = f"{coin}_USDT"; ct = get(f"{G}/contracts/{c}")
    if not ct or "name" not in ct: return None
    cd = get(f"{G}/candlesticks", {"contract": c, "interval": "15m", "limit": 2000}); ss = get(f"{G}/contract_stats", {"contract": c, "interval": "15m", "limit": 2000})
    h1 = get(f"{G}/candlesticks", {"contract": c, "interval": "1h", "limit": 2000 if BT_FETCH else 600})
    if not all(isinstance(x, list) and x for x in (cd, ss, h1)): return None
    return dict(now=NOW, ct=dict(mmr=float(ct.get("maintenance_rate") or .005), lmax=float(ct.get("leverage_max") or 100)),
                c15={int(x["t"]): [float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])] for x in cd if int(x["t"]) <= NOW},
                oi={int(s["time"]): [float(s["open_interest_usd"]), float(s.get("lsr_taker") or 1)] for s in ss if s.get("open_interest_usd")},
                h1={int(x["t"]): [float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])] for x in h1 if int(x["t"]) + 3600 <= NOW})
BT_FETCH = False

def build_grid(raw, now):
    """15m ortak izgara (eksik mum/OI ileri doldurulur). ncl = kapanmis mum sayisi; son (olusmakta olan) mum varsa yalniz acilisi giris icin kullanilir."""
    c15 = {int(k): v for k, v in raw["c15"].items()}; oi = {int(k): v for k, v in raw["oi"].items()}
    t0 = max(min(c15), min(oi)); t1 = max(c15); ts = np.arange(t0, t1 + 1, STEP); n = len(ts)
    O = np.zeros(n); H = np.zeros(n); L = np.zeros(n); C = np.zeros(n); OI = np.zeros(n); LS = np.zeros(n); gaps = 0
    po = None; pl = 1.0; pc = None
    for i, t in enumerate(ts):
        x = c15.get(int(t))
        if x is None: gaps += 1; x = [pc, pc, pc, pc] if pc is not None else None
        if x is None: x = [0, 0, 0, 0]
        O[i], H[i], L[i], C[i] = x; pc = x[3]
        y = oi.get(int(t))
        if y is not None: po, pl = y[0], y[1]
        OI[i] = po if po is not None else 0; LS[i] = pl
    ncl = int(np.sum(ts + STEP <= now))
    return dict(t=ts, o=O, h=H, l=L, c=C, oi=OI, lsr=LS, n=n, ncl=ncl, gaps=gaps, mmr=raw["ct"]["mmr"], lmax=raw["ct"]["lmax"])

def build_htf(raw):
    h1 = {int(k): v for k, v in raw["h1"].items()}; b = {}
    for t in sorted(h1): b.setdefault(t // 7200 * 7200, []).append(t)
    T = []; O = []; H = []; L = []; C = []
    for k in sorted(b):
        ls = b[k]
        if len(ls) < 2: continue
        T.append(k); O.append(h1[ls[0]][0]); H.append(max(h1[x][1] for x in ls)); L.append(min(h1[x][2] for x in ls)); C.append(h1[ls[-1]][3])
    T = np.array(T); O = np.array(O); H = np.array(H); L = np.array(L); C = np.array(C); N = len(C)
    if N < WARM2 + 30: return None
    def ema(n):
        a = 2 / (n + 1); e = np.empty(N); e[0] = C[0]
        for i in range(1, N): e[i] = a * C[i] + (1 - a) * e[i - 1]
        return e
    tr = np.empty(N); tr[0] = H[0] - L[0]; tr[1:] = np.maximum.reduce([H[1:] - L[1:], np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])])
    atr14 = np.full(N, np.nan); atr14[13:] = np.convolve(tr, np.ones(14) / 14, mode="valid")
    # supertrend(10,3)
    n_ = 10; m_ = 3.0; a10 = np.full(N, np.nan); a10[n_ - 1] = tr[:n_].mean()
    for i in range(n_, N): a10[i] = (a10[i - 1] * (n_ - 1) + tr[i]) / n_
    hl2 = (H + L) / 2; ub = hl2 + m_ * a10; lb = hl2 - m_ * a10; fub = ub.copy(); flb = lb.copy(); sd = np.zeros(N); sl = np.full(N, np.nan); d = 1
    for i in range(n_, N):
        if i > n_:
            fub[i] = ub[i] if (ub[i] < fub[i - 1] or C[i - 1] > fub[i - 1]) else fub[i - 1]
            flb[i] = lb[i] if (lb[i] > flb[i - 1] or C[i - 1] < flb[i - 1]) else flb[i - 1]
            if d == 1 and C[i] < flb[i]: d = -1
            elif d == -1 and C[i] > fub[i]: d = 1
        else: d = 1 if C[i] > hl2[i] else -1
        sd[i] = d; sl[i] = flb[i] if d == 1 else fub[i]
    bb = np.full(N, np.nan); bb[19:] = np.convolve(C, np.ones(20) / 20, mode="valid")
    lines = {"EMA50": ema(50), "EMA100": ema(100), "ST10_3": sl, "BBMID20": bb}; dirs = {}
    for p, ln in lines.items():
        if p == "ST10_3": dirs[p] = sd.copy()
        else:
            dd = np.sign(C - ln); sl3 = np.zeros(N); sl3[3:] = ln[3:] - ln[:-3]; dd[np.sign(sl3) != dd] = 0; dirs[p] = dd
        dirs[p][:WARM2] = 0
    return dict(T=T, lines=lines, dirs=dirs, atr=atr14)

# ---------------------------------------------------------------- cluster model replay (liqbt ile ayni mantik)
def replay(g, need, ncl):
    """need: {i: [(key, L), ...]} -> {i: {key: feature dict}}; ozellik = i'den ONCEKI (j-1 kapanisi) tahmini harita."""
    t, h, l, c, oi, lsr = g["t"], g["h"], g["l"], g["c"], g["oi"], g["lsr"]; mmr = g["mmr"]; lmax = g["lmax"]
    levs = {a: w for a, w in LEV.items() if a <= lmax and 1 / a > 2 * mmr} or {5: 1.0}; tw = sum(levs.values()); levs = {a: w / tw for a, w in levs.items()}
    cap = ncl * 2 * len(levs) + 50; px = np.zeros(cap); us = np.zeros(cap); sd = np.zeros(cap, int); m = 0; res = {}
    def add(p, u, s):
        nonlocal m; px[m] = p; us[m] = u; sd[m] = s; m += 1
    ep = (h[0] + l[0] + c[0]) / 3
    for a, w in levs.items(): add(ep * (1 - 1 / a + mmr), oi[0] * w, 1); add(ep * (1 + 1 / a - mmr), oi[0] * w, -1)
    for i in range(1, ncl):
        if i in need and m:
            P = c[i - 1]; b = np.floor((px[:m] / P - 1) / BW).astype(int); ok = (b >= -WIN) & (b < WIN)
            tot = np.bincount(b[ok] + WIN, weights=us[:m][ok], minlength=2 * WIN); oi_ = max(oi[i - 1], 1.0); r = {}
            for key, L in need[i]:
                f = {}
                for nm, bd in BAND.items():
                    lo = int(math.floor((L * (1 - bd) / P - 1) / BW)); hi = int(math.floor((L * (1 + bd) / P - 1) / BW)); lo = max(lo, -WIN); hi = min(hi, WIN - 1)
                    if lo > hi: f[nm] = (99, 0.0, ""); continue
                    seg = tot[lo + WIN:hi + WIN + 1]; mx = seg.max(); am = int(seg.argmax()) + lo
                    f[nm] = ((1 + int((tot > mx).sum())) if mx > 0 else 99, mx / oi_ * 1e4, "long" if am < 0 else "short")
                r[key] = f
            res[i] = r
        mk = ((sd[:m] == 1) & (l[i] <= px[:m])) | ((sd[:m] == -1) & (h[i] >= px[:m])); keep = ~mk; k = int(keep.sum())
        px[:k] = px[:m][keep]; us[:k] = us[:m][keep]; sd[:k] = sd[:m][keep]; m = k
        d = oi[i] - oi[i - 1]
        if d < 0 and oi[i - 1] > 0: us[:m] *= oi[i] / oi[i - 1]
        elif d > 0:
            e = (h[i] + l[i] + c[i]) / 3; sh = lsr[i] / (1 + lsr[i]); lf = .5 + (sh - .5) * .5
            for a, w in levs.items(): add(e * (1 - 1 / a + mmr), d * w * 2 * lf, 1); add(e * (1 + 1 / a - mmr), d * w * 2 * (1 - lf), -1)
    return res

def outcome(g, j, d, A):
    """j = sinyal mumu indeksi. Giris = mum j+1 acilisi. Yalniz kapanmis mumlarla cozulebilen alanlari dondurur."""
    e = j + 1; n = g["n"]; ncl = g["ncl"]
    if e >= n or e > ncl: return {}
    ref = g["o"][e]; r = dict(entry_px=ref, entry_bar_t=int(g["t"][e]))
    if not ref > 0: return {}
    for hn, H in HZ.items():
        x = j + H
        if x < ncl:
            gr = d * (g["c"][x] / ref - 1) * 1e4; r[f"net_trend_{hn}"] = round(gr - COST, 2); r[f"net_rev_{hn}"] = round(-gr - COST, 2)
    if e + CR_BARS <= ncl and A and A == A and A > 0:
        lab = "NONE"
        for k in range(e, e + CR_BARS):
            fav = (g["h"][k] - ref) if d > 0 else (ref - g["l"][k]); adv = (ref - g["l"][k]) if d > 0 else (g["h"][k] - ref); f = fav >= A; a = adv >= A
            if f and a: lab = "BOTH"; break
            if f: lab = "CONT"; break
            if a: lab = "REV"; break
        r["cr"] = lab
    return r

def analyze(coin, ci, g, hz, feat_from):
    """Tum pencerede dokunus/kontrol adaylari -> (feat_from <= bar_t) olanlara kume ozelligi ekler. Refrakter icin tum gecmis taranir."""
    t, o, h, l, c = g["t"], g["o"], g["h"], g["l"], g["c"]; ncl = g["ncl"]; T2e = hz["T"] + 7200
    kmap = np.searchsorted(T2e, t, side="right") - 1; cand = []; last = {p: -10**9 for p in PROXIES}
    for j in range(WARM2, ncl):
        k = kmap[j]
        if k < WARM2: continue
        for p in PROXIES:
            d = int(hz["dirs"][p][k]); L = hz["lines"][p][k]; A = hz["atr"][k]
            if d == 0 or not (L == L) or not (A == A): continue
            touch = (d > 0 and l[j - 1] > L and l[j] <= L) or (d < 0 and h[j - 1] < L and h[j] >= L)
            if touch and j - last[p] >= REFR:
                last[p] = j
                if t[j] >= feat_from:
                    age = 384; lo_ = max(0, j - 384)
                    for q in range(j - 1, lo_ - 1, -1):
                        if l[q] <= L <= h[q]: age = j - q; break
                    cand.append(dict(kind="touch", j=j, proxy=p, dir=d, line=L, atr_px=A, rejected=int(d * (c[j] - L) >= 0), lvl_age=age))
            if (j + ci) % CTRL_EVERY == 0 and t[j] >= feat_from: cand.append(dict(kind="control", j=j, proxy=p, dir=d, line=L, atr_px=A, rejected="", lvl_age=""))
    need = {}
    for x in cand: need.setdefault(x["j"], []).append((id(x), x["line"] if x["kind"] == "touch" else c[x["j"] - 1]))
    res = replay(g, need, ncl) if cand else {}; out = []
    for x in cand:
        f = res.get(x["j"], {}).get(id(x))
        if not f: continue
        j = x["j"]; bt = int(t[j])
        ev = dict(id=f"{x['kind']}|{coin}|{x['proxy']}|{bt}", kind=x["kind"], coin=coin, proxy=x["proxy"], bar_t=bt, detected_iso=iso(bt + STEP), dir=x["dir"], line=round(float(x["line"]), 8), px=float(c[j]),
                  rejected=x["rejected"], atr_px=float(x["atr_px"]), lvl_age=x["lvl_age"], cl03_rank=f["03"][0], cl03_bps=round(f["03"][1], 2), cl05_rank=f["05"][0], cl05_bps=round(f["05"][1], 2), cl_side=f["05"][2], j=j)
        out.append(ev)
    return out

# ---------------------------------------------------------------- scan
def scan():
    sp = os.path.join(OUT, "state.json"); evp = os.path.join(OUT, "events.csv"); op = os.path.join(OUT, "outcomes.csv")
    try: st = json.load(open(sp))
    except Exception: st = {}
    st.setdefault("coins", {}); failed = []; GR = {}; new = []
    latest_closed = (int(NOW) // STEP) * STEP - STEP
    for ci, coin in enumerate(COINS):
        try:
            raw = fetch_raw(coin)
            if not raw: failed.append(coin); continue
            g = build_grid(raw, NOW); hz = build_htf(raw)
            if hz is None or g["ncl"] < WARM + 50: failed.append(coin); continue
            GR[coin] = g; cs = st["coins"].setdefault(coin, {"last_t": 0}); first = not cs["last_t"]
            la = latest_closed - STEP * max(BACKFILL, 1) if first else cs["last_t"]
            evs = analyze(coin, ci, g, hz, la + STEP); new += [e for e in evs if e["bar_t"] > la]
            cs["last_t"] = max(cs["last_t"], int(g["t"][g["ncl"] - 1]))
        except Exception as e: failed.append(coin); log(f"ERR {coin} {type(e).__name__} {str(e)[:80]}")
        time.sleep(0.15)
    evs = read_csv(evp); have = {e["id"] for e in evs}; outs = {o["id"]: o for o in read_csv(op)}; added = 0
    for e in new:
        if e["id"] in have: continue
        e["logged_epoch"] = int(NOW); evs.append(e); have.add(e["id"]); outs.setdefault(e["id"], {"id": e["id"]}); added += 1
    resolved = 0
    for e in evs:
        o = outs.setdefault(e["id"], {"id": e["id"]}); g = GR.get(e["coin"])
        if g is None or all(o.get(k, "") != "" for k in ("net_trend_1h", "net_trend_4h", "net_trend_12h", "cr")): continue
        j = int((int(e["bar_t"]) - g["t"][0]) // STEP)
        if j < 0 or j >= g["n"] or int(g["t"][j]) != int(e["bar_t"]): continue
        r = outcome(g, j, int(e["dir"]), float(e["atr_px"])); ch = False
        for k, v in r.items():
            if o.get(k, "") == "": o[k] = v; ch = True
        if ch: o["resolved_epoch"] = int(NOW); resolved += 1
    if added: write_csv(evp, EVCOLS, evs)
    if added or resolved: write_csv(op, OCOLS, [outs[e["id"]] for e in evs])
    tmp = sp + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, sp)
    nt = sum(e["kind"] == "touch" for e in evs)
    msg = f"scan ok coins={len(GR)}/{len(COINS)} failed={failed} new_events={added} (touch={sum(e['kind']=='touch' for e in new)}) outcomes_updated={resolved} total_events={len(evs)} (touch={nt})"; log(msg); print(msg)

# ---------------------------------------------------------------- stats
def fnum(x):
    try: return float(x) if x != "" and x is not None else float("nan")
    except Exception: return float("nan")
def prep(rows):
    """rows: event+outcome birlesik dict listesi -> sayisal alanlar + kontrol bazli excess."""
    for r in rows:
        for hn in HZ: r[f"nt{hn}"] = fnum(r.get(f"net_trend_{hn}")); r[f"nr{hn}"] = fnum(r.get(f"net_rev_{hn}"))
        cr = r.get("cr", ""); r["cont"] = (1.0 if cr == "CONT" else 0.0) if cr != "" else float("nan"); r["rev"] = (1.0 if cr == "REV" else 0.0) if cr != "" else float("nan")
        r["c03"] = int(fnum(r["cl03_rank"]) <= TOPK); r["c05"] = int(fnum(r["cl05_rank"]) <= TOPK); r["cell"] = (r["coin"], int(fnum(r["bar_t"]) // (3 * 86400)))
    M = ("nt1h", "nt4h", "nt12h", "cont", "rev"); base = {}; pool = {}
    for r in rows:
        if r["kind"] != "control": continue
        for m in M:
            v = r[m]
            if v == v:
                for key in ((r["proxy"], r["coin"], int(r["dir"])), (r["proxy"], int(r["dir"]))):
                    s = base.setdefault((key, m), [0.0, 0]); s[0] += v; s[1] += 1
    for r in rows:
        for m in M:
            b = base.get(((r["proxy"], r["coin"], int(r["dir"])), m)); b2 = base.get(((r["proxy"], int(r["dir"])), m))
            bv = b[0] / b[1] if b and b[1] >= 5 else (b2[0] / b2[1] if b2 else float("nan")); r["x" + m] = r[m] - bv if r[m] == r[m] else float("nan")
    return rows
def cell_arrays(rows, key):
    cells = sorted({r["cell"] for r in rows}); ix = {c: i for i, c in enumerate(cells)}; s = np.zeros(len(cells)); n = np.zeros(len(cells))
    for r in rows:
        v = r[key]
        if v == v: s[ix[r["cell"]]] += v; n[ix[r["cell"]]] += 1
    return cells, s, n
def boot(rows, key, rows2=None, B=2000, seed=7):
    """coin x 3-gun blok bootstrap; rows2 verilirse ortalama FARKI (rows - rows2). -> (stat, lo, hi)"""
    cells = sorted({r["cell"] for r in rows} | ({r["cell"] for r in rows2} if rows2 else set())); ix = {c: i for i, c in enumerate(cells)}; K = len(cells)
    def arr(rs):
        s = np.zeros(K); n = np.zeros(K)
        for r in rs:
            v = r[key]
            if v == v: s[ix[r["cell"]]] += v; n[ix[r["cell"]]] += 1
        return s, n
    s1, n1 = arr(rows); s2, n2 = arr(rows2) if rows2 is not None else (None, None)
    def stat(a, b, c_, d_):
        with np.errstate(all="ignore"):
            x = a.sum(-1) / b.sum(-1)
            return x - (c_.sum(-1) / d_.sum(-1)) if c_ is not None else x
    pt = float(stat(s1, n1, s2, n2)); rng = np.random.default_rng(seed); idx = rng.integers(0, K, (B, K))
    bs = stat(s1[idx], n1[idx], s2[idx] if s2 is not None else None, n2[idx] if n2 is not None else None); bs = bs[np.isfinite(bs)]
    return (pt, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))) if len(bs) > 50 else (pt, float("nan"), float("nan"))
def mean(rs, k):
    v = [r[k] for r in rs if r[k] == r[k]]; return (sum(v) / len(v), len(v)) if v else (float("nan"), 0)
def fm(x, f="+.1f"): return "   -  " if x != x else format(x, f)
def line(name, rs, ci=False):
    n = len(rs); cr_n = mean(rs, "cont")[1]; hit = [r["nt4h"] > 0 for r in rs if r["nt4h"] == r["nt4h"]]; w = "!" if n < 30 else " "
    s = f"  {name:<22s}{w}n={n:<5d} CONT {fm(100*mean(rs,'cont')[0],'5.1f')}% REV {fm(100*mean(rs,'rev')[0],'5.1f')}% (n={cr_n:<4d}) | trend net bp 1h {fm(mean(rs,'nt1h')[0])} 4h {fm(mean(rs,'nt4h')[0])} 12h {fm(mean(rs,'nt12h')[0])} hit4h {fm(100*sum(hit)/len(hit) if hit else float('nan'),'4.0f')}% | rev net 4h {fm(mean(rs,'nr4h')[0])}"
    if rs and rs[0]["kind"] != "control" or ci:
        e4 = mean(rs, "xnt4h"); s += f" | EXCESS4h {fm(e4[0])}"
        if ci and e4[1] >= 10: pt, lo, hi = boot(rs, "xnt4h"); s += f" [{fm(lo,'+.0f')},{fm(hi,'+.0f')}]"
        ec = mean(rs, "xcont")
        if ci and ec[1] >= 10: pt, lo, hi = boot(rs, "xcont"); s += f" | CONT excess {100*pt:+.1f}pp [{100*lo:+.1f},{100*hi:+.1f}]"
        elif ec[1]: s += f" | CONT excess {100*ec[0]:+.1f}pp"
        er = mean(rs, "xrev")
        if ci and er[1] >= 10: pt, lo, hi = boot(rs, "xrev"); s += f" | REV excess {100*pt:+.1f}pp [{100*lo:+.1f},{100*hi:+.1f}]"
        elif er[1]: s += f" | REV excess {100*er[0]:+.1f}pp"
    return s
def tables(rows, ci):
    out = []; ctl_all = [r for r in rows if r["kind"] == "control"]
    out.append(f"n_touch={sum(r['kind']=='touch' for r in rows)}  n_control={len(ctl_all)}  | excess = olay - ayni (proxy,coin,yon) KONTROL (rastgele zaman) ortalamasi; '!' = n<30 (anlamsiz); maliyet {COST:.0f}bp tur")
    for p in PROXIES:
        T = [r for r in rows if r["kind"] == "touch" and r["proxy"] == p]; Cn = [r for r in rows if r["kind"] == "control" and r["proxy"] == p]
        out.append(f"\n[{p}]  touch={len(T)} | kume(cl05) orani: touch {100*sum(r['c05'] for r in T)/max(len(T),1):.1f}% vs kontrol {100*sum(r['c05'] for r in Cn)/max(len(Cn),1):.1f}%  | cl03: touch {100*sum(r['c03'] for r in T)/max(len(T),1):.1f}% vs kontrol {100*sum(r['c03'] for r in Cn)/max(len(Cn),1):.1f}%")
        out.append(line("control (rastgele)", Cn)); out.append(line("touch HEPSI", T, ci))
        A = [r for r in T if r["c05"]]; B = [r for r in T if not r["c05"]]
        out.append(line("touch + cluster(0.5%)", A, ci)); out.append(line("touch - cluster(0.5%)", B, ci)); out.append(line("touch + cluster(0.3%)", [r for r in T if r["c03"]], ci))
        out.append(line("touch rejected(kapanis ok)", [r for r in T if r["rejected"] in (1, "1")], ci)); out.append(line("control + cluster(0.5%)", [r for r in Cn if r["c05"]]))
        if ci and len(A) >= 10 and len(B) >= 10:
            for k, nm in (("xnt4h", "4h trend net"), ("xcont", "CONT orani")):
                pt, lo, hi = boot(A, k, B); sc = 1 if k == "xnt4h" else 100; out.append(f"  >> kume etkisi (touch+cl - touch-cl) {nm}: {sc*pt:+.1f} [{sc*lo:+.1f},{sc*hi:+.1f}]" + ("" if k == "xnt4h" else " pp"))
    return out

def load_rows(evs, outs):
    om = {o["id"]: o for o in outs}; rows = []
    for e in evs:
        r = dict(e); r.update({k: v for k, v in om.get(e["id"], {}).items() if k != "id"}); rows.append(r)
    return prep(rows)

def report():
    rows = load_rows(read_csv(os.path.join(OUT, "events.csv")), read_csv(os.path.join(OUT, "outcomes.csv")))
    print("PROXY UYARISI: GCLa-sv2 ve Coinglass isi haritasi yok; cizgi = EMA/Supertrend/BB proxy, kume = OI-delta x kaldirac TAHMINI. Veri birikmeye basladi, kucuk n'e guvenme.")
    print("\n".join(tables(rows, ci=len([r for r in rows if r["kind"] == "touch"]) >= 40)))
    print("\nBACKTEST karsilastirma: outputs/confluence_paper/backtest_report.txt (varsa)")

# ---------------------------------------------------------------- backtest
def backtest(refetch):
    global BT_FETCH, NOW
    BT_FETCH = True; cd = os.path.join(OUT, "bt_cache"); os.makedirs(cd, exist_ok=True); allrows = []; t_start = time.time(); info = []
    for ci, coin in enumerate(COINS):
        fp = os.path.join(cd, f"{coin}.json"); raw = None
        if not refetch and os.path.exists(fp):
            try: raw = json.load(open(fp))
            except Exception: raw = None
        if raw is None:
            raw = fetch_raw(coin)
            if not raw: info.append(f"{coin}:fetch-fail"); continue
            json.dump(raw, open(fp, "w")); time.sleep(0.2)
        now = raw["now"]; g = build_grid(raw, now); hz = build_htf({**raw, "h1": {int(k): v for k, v in raw["h1"].items()}})
        if hz is None: info.append(f"{coin}:htf-short"); continue
        feat_from = int(g["t"][min(WARM, g["n"] - 1)]); evs = analyze(coin, ci, g, hz, feat_from)
        for e in evs:
            r = dict(e); r.update(outcome(g, e["j"], int(e["dir"]), e["atr_px"])); allrows.append(r)
        info.append(f"{coin}:{g['n']}bars gaps={g['gaps']} ev={len(evs)}")
    rows = prep(allrows); bt = [r for r in rows]; days = (max(r["bar_t"] for r in rows) - min(r["bar_t"] for r in rows)) / 86400 if rows else 0
    out = [f"BACKTEST confluence (nedensel) - {len(COINS)} Gate perp, {days:.1f} gun (kume modeli {WARM/96:.0f} gun isinma sonrasi), HTF cizgi proxy'leri 1s->2s mumlardan", "PROXY: GCLa-sv2 / Coinglass YOK; cizgi=EMA50/EMA100/Supertrend(10,3)/BB-orta(20) 2s; kume=OI-delta x kaldirac tahmini (Gate OI). CI = coin x 3-gun blok bootstrap %95 (2000 tekrar); baseline sabit varsayildi."]
    out += tables(rows, ci=True)
    # bolunmus yarilar + yas katmanlama (tum proxy'ler havuzlanmis; olaylar ortusur => CI genis oldugunu unutma)
    T = [r for r in rows if r["kind"] == "touch"]
    if T:
        tm = sorted(r["bar_t"] for r in T); mid = tm[len(tm) // 2]; out.append("\n[Havuz: 4 proxy birlikte (olaylar proxy'ler arasi ORTUSUR, bagimsiz degil)]")
        for nm, f in (("ilk yari", lambda r: r["bar_t"] < mid), ("ikinci yari", lambda r: r["bar_t"] >= mid)):
            h_ = [r for r in T if f(r)]; A = [r for r in h_ if r["c05"]]; B = [r for r in h_ if not r["c05"]]
            out.append(f"  {nm}: touch n={len(h_)} excess4h {mean(h_,'xnt4h')[0]:+.1f} | +cl n={len(A)} excess4h {mean(A,'xnt4h')[0]:+.1f} | -cl n={len(B)} excess4h {mean(B,'xnt4h')[0]:+.1f}")
        ages = sorted(fnum(r["lvl_age"]) for r in T); md = ages[len(ages) // 2]
        for nm, f in ((f"seviye yasi < {md:.0f} bar (yakinda islem gormus)", lambda r: fnum(r["lvl_age"]) < md), (f"seviye yasi >= {md:.0f} bar", lambda r: fnum(r["lvl_age"]) >= md)):
            h_ = [r for r in T if f(r)]; A = [r for r in h_ if r["c05"]]; B = [r for r in h_ if not r["c05"]]
            out.append(f"  yas katmani {nm}: +cl n={len(A)} excess4h {mean(A,'xnt4h')[0]:+.1f} / -cl n={len(B)} excess4h {mean(B,'xnt4h')[0]:+.1f}")
        ca = {}
        for r in T: ca.setdefault(r["coin"], []).append(r["xnt4h"])
        pos = sum(1 for v in ca.values() if np.nanmean(v) > 0); out.append(f"  coin tutarliligi: touch excess4h > 0 olan coin {pos}/{len(ca)}")
    out += ["", "KISITLAR: tek rejim (~3 hafta, buyuk olcude dusus), proxy'ler kullanicinin kapali kaynak cizgisi/isi haritasi DEGIL, kume tahmini (Binance degil, Gate OI), ~48+ hucre test edildi (coklu karsilastirma),",
            "olaylar bloklar icinde ortusur (CI kismen telafi eder), 4 proxy ayni dokunuslari buyuk oranda paylasir. Giris = sonraki mum acilisi; cizgi/yon yalniz kapanmis 2s mumdan (nedensel).", "Kume bayragi = bolgenin pencere icindeki ilk-3 kutudan biri olmasi; onceki testte kume boyutunun tek basina ongoru gucu yoktu.", "Veri durumu: " + "; ".join(info)]
    txt = "\n".join(out); open(os.path.join(OUT, "backtest_report.txt"), "w").write(txt + "\n"); write_csv(os.path.join(OUT, "backtest_events.csv"), EVCOLS + ["net_trend_1h", "net_trend_4h", "net_trend_12h", "net_rev_4h", "cr"], rows); print(txt)

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--dir" in a: OUT = a[a.index("--dir") + 1]
    if "--asof" in a: NOW = float(a[a.index("--asof") + 1])
    if "--backfill-bars" in a: BACKFILL = int(a[a.index("--backfill-bars") + 1])
    os.makedirs(OUT, exist_ok=True)
    try:
        lk = open(os.path.join(OUT, ".lock"), "w"); fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception: print("baska bir kopya calisiyor, cikiliyor"); sys.exit(0)
    try:
        if "--scan" in a: scan()
        elif "--report" in a: report()
        elif "--backtest" in a: backtest("--refetch" in a)
        else: print(__doc__)
    except Exception as e:
        import traceback; log(f"FATAL {type(e).__name__} {str(e)[:120]}"); print("hata (loglandi):", type(e).__name__)
        if "--debug" in a: traceback.print_exc()
    sys.exit(0)
