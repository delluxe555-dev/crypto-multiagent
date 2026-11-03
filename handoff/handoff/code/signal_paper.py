#!/usr/bin/env python3
"""signal_paper.py - SESSIZ kagit-uzeri sinyal takibi. Mesaj/Telegram GONDERMEZ; mevcut paper trader'a, config'ine, state'ine dokunmaz.
Yalniz anahtarsiz Gate public API okur; yalniz outputs/signal_paper/ altina yazar.
  python3 signal_paper.py --scan      # her 15 dk (cron/scheduler): sinyalleri bul + bekleyenleri / vadesi gelenleri coz
  python3 signal_paper.py --report    # birikimli istatistik; NEWSHORT w=16 4h'i backtestle kiyaslar
Test secenekleri: --dir PATH (cikti klasoru), --asof EPOCH (zamani geri al), --backfill-bars N (ilk calismada son N mumdaki sinyalleri de logla)
Tanimlar liqbt_signals.py ile ayni: pencere w (4 ve 16 x 15m); fiyat degisimi c[j]/c[j-w]-1, OI degisimi oi[j]/oi[j-w]-1 (kapanmis mumlar);
  NEWLONG p>=+0.5 & oi>=+1; NEWSHORT p<=-0.5 & oi>=+1; LONGLIQ p<=-0.5 & oi<=-1; SQUEEZE p>=+0.5 & oi<=-1; OFOI_UP/DN |oi|>=3 (yon = fiyat isareti);
  FUND_POS/NEG |funding 8s-esdeger| >= 0.05% (kalabalik tersi). Ayni sinyal tipi, coin basina w bar icinde tekrar yazilmaz (funding: 96 bar).
  Giris = sinyal mumundan sonraki 15m mumun acilisi (j+1; mum henuz yoksa 'pending'); cikis = j+H kapanisi, H=4,16,48 (1s/4s/12s).
  Maliyet 0.05%/taraf = 10bp tur. Baseline = ayni giris/cikis penceresinde DIGER coinlerin ortalama getirisi (same-time market)."""
import sys, os, csv, json, time, fcntl, requests
from datetime import datetime, timezone, timedelta
COINS = "ARB NEAR ETH BTC ETHFI GRASS SOL DOGE XRP AVAX LINK APT SUI INJ OP WLD TIA SEI ATOM DOT FET ADA LTC BNB PYTH JUP".split()
G = "https://api.gateio.ws/api/v4/futures/usdt"; STEP = 900; HZ = {"1h": 4, "4h": 16, "12h": 48}; COST = 10.0; WINS = (4, 16); FUND_TH = 0.05; FUND_REFR = 96
TZ = timezone(timedelta(hours=3))
SIGCOLS = ["sig_id", "bar_t", "detected_iso", "coin", "signal", "w", "dir", "price_chg_pct", "oi_chg_pct", "funding_8h_pct", "entry_bar_t", "entry_px", "status", "logged_epoch"]
OUTCOLS = ["sig_id", "coin", "signal", "w", "dir", "horizon", "entry_px", "exit_bar_t", "exit_px", "ret_bp", "gross_bp", "net_bp", "mkt_bp", "excess_bp", "n_mkt", "resolved_epoch"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "signal_paper"); NOW = time.time(); BACKFILL = 0

def iso(e): return datetime.fromtimestamp(e, TZ).strftime("%Y-%m-%d %H:%M:%S%z")
def log(msg):
    try:
        with open(os.path.join(OUT, "scan.log"), "a") as f: f.write(f"{iso(NOW)} {msg}\n")
    except Exception: pass
def get(u, p=None):
    for k in range(3):
        try:
            r = requests.get(u, params=p, timeout=15)
            if r.status_code == 429: time.sleep(1.5 * (k + 1)); continue
            if r.status_code != 200: return None
            return r.json()
        except Exception: time.sleep(0.7)
    return None
def read_csv(p):
    try:
        with open(p, newline="") as f: return list(csv.DictReader(f))
    except FileNotFoundError: return []
    except Exception: return []
def write_csv(p, cols, rows):
    tmp = p + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); [w.writerow({k: r.get(k, "") for k in cols}) for r in rows]
    os.replace(tmp, p)
def append_csv(p, cols, rows):
    new = not os.path.exists(p) or os.path.getsize(p) == 0
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new: w.writeheader()
        [w.writerow({k: r.get(k, "") for k in cols}) for r in rows]

def fetch(coin, st, limit):
    c = f"{coin}_USDT"
    if coin not in st["fiv"]:
        ct = get(f"{G}/contracts/{c}")
        if not ct or "name" not in ct: return None
        st["fiv"][coin] = (ct.get("funding_interval") or 28800) / 3600
    cd = get(f"{G}/candlesticks", {"contract": c, "interval": "15m", "limit": limit}); ss = get(f"{G}/contract_stats", {"contract": c, "interval": "15m", "limit": limit})
    if not isinstance(cd, list) or not isinstance(ss, list) or not cd or not ss: return None
    candles = {int(x["t"]): (float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])) for x in cd if int(x["t"]) <= NOW}
    stats = {}
    for s in ss:
        t = int(s["time"])
        if t + STEP <= NOW and s.get("open_interest_usd"):
            stats[t] = (float(s["open_interest_usd"]), float(s.get("last_funding_rate") or 0) * 8 / st["fiv"][coin] * 100)
    return candles, stats

def detect(coin, candles, stats, cs, log_after):
    """Backtest ile ayni mantik; cs = coin state (last_fired, last_t). Donus: yeni sinyal listesi (yalniz bar_t > log_after)."""
    ev = []; ts = sorted(t for t in candles if t in stats and t + STEP <= NOW)
    for t in ts:
        if cs["last_t"] and t <= cs["last_t"]: continue
        c = candles[t][3]; oi, fu = stats[t]; hits = []
        for w in WINS:
            t0 = t - w * STEP
            if t0 not in candles or t0 not in stats: continue
            p = (c / candles[t0][3] - 1) * 100; o = (oi / stats[t0][0] - 1) * 100
            if abs(p) >= .5 and abs(o) >= 1: hits.append((("NEWLONG", 1) if p > 0 and o > 0 else ("NEWSHORT", -1) if p < 0 and o > 0 else ("LONGLIQ", -1) if p < 0 else ("SQUEEZE", 1), w, p, o))
            if abs(o) >= 3 and p != 0: hits.append((("OFOI_UP" if o > 0 else "OFOI_DN", 1 if p > 0 else -1), w, p, o))
        if fu >= FUND_TH: hits.append((("FUND_POS", -1), 0, float("nan"), float("nan")))
        elif fu <= -FUND_TH: hits.append((("FUND_NEG", 1), 0, float("nan"), float("nan")))
        for (name, d), w, p, o in hits:
            k = f"{name}|{w}"; gap = (t - cs["last_fired"].get(k, -10**12)) / STEP; need = FUND_REFR if w == 0 else w
            if gap >= need:
                cs["last_fired"][k] = t
                if t > log_after: ev.append(dict(bar_t=t, coin=coin, signal=name, w=w, dir=d, price_chg_pct=round(p, 3) if p == p else "", oi_chg_pct=round(o, 3) if o == o else "", funding_8h_pct=round(fu, 5)))
    if ts: cs["last_t"] = max(cs["last_t"] or 0, ts[-1])
    return ev

def mkt(C, entry_t, exit_t, skip):
    v = []
    for c, cd in C.items():
        if c == skip or entry_t not in cd or exit_t not in cd: continue
        v.append((cd[exit_t][3] / cd[entry_t][0] - 1) * 1e4)
    return (sum(v) / len(v), len(v)) if v else (None, 0)

def scan():
    sp = os.path.join(OUT, "state.json"); sigp = os.path.join(OUT, "signals.csv"); outp = os.path.join(OUT, "outcomes.csv")
    try: st = json.load(open(sp))
    except Exception: st = {}
    st.setdefault("fiv", {}); st.setdefault("coins", {}); C = {}; failed = []; newsig = []
    latest_closed = (int(NOW) // STEP) * STEP - STEP
    for coin in COINS:
        try:
            cs = st["coins"].setdefault(coin, {"last_t": 0, "last_fired": {}}); first = not cs["last_t"]
            r = fetch(coin, st, 2000 if first else 400)
            if not r: failed.append(coin); continue
            candles, stats = r; C[coin] = candles
            la = latest_closed - STEP * max(BACKFILL, 1) if first else cs["last_t"]
            newsig += detect(coin, candles, stats, cs, la if first else cs["last_t"] if cs["last_t"] else la)
        except Exception as e: failed.append(coin); log(f"ERR {coin} {str(e)[:80]}")
        time.sleep(0.15)
    sigs = read_csv(sigp); have = {r["sig_id"] for r in sigs}; added = 0
    for e in newsig:
        sid = f"{e['coin']}|{e['signal']}|{e['w']}|{e['bar_t']}"
        if sid in have: continue
        et = e["bar_t"] + STEP; cd = C.get(e["coin"], {}); ep = cd[et][0] if et in cd else ""
        e.update(sig_id=sid, detected_iso=iso(e["bar_t"] + STEP), entry_bar_t=et, entry_px=ep, status="open" if ep != "" else "pending", logged_epoch=int(NOW)); sigs.append(e); have.add(sid); added += 1
    filled = 0
    for s in sigs:   # bekleyenlerin girisini doldur
        if s["status"] == "pending":
            cd = C.get(s["coin"], {}); et = int(s["entry_bar_t"])
            if et in cd: s["entry_px"] = cd[et][0]; s["status"] = "open"; filled += 1
    if added or filled: write_csv(sigp, SIGCOLS, sigs)
    outs = read_csv(outp); done = {(o["sig_id"], o["horizon"]) for o in outs}; newout = []
    for s in sigs:
        if s["status"] != "open": continue
        j = int(s["bar_t"]); d = int(s["dir"]); ep = float(s["entry_px"]); cd = C.get(s["coin"])
        for hn, H in HZ.items():
            if (s["sig_id"], hn) in done: continue
            xt = j + H * STEP
            if xt + STEP > NOW: continue                      # cikis mumu henuz kapanmadi
            if not cd or xt not in cd: continue                # veri yok (API hatasi / cok eski): sonraki taramada tekrar denenir
            xp = cd[xt][3]; ret = (xp / ep - 1) * 1e4; g = d * ret; m, n = mkt(C, j + STEP, xt, s["coin"])
            newout.append(dict(sig_id=s["sig_id"], coin=s["coin"], signal=s["signal"], w=s["w"], dir=d, horizon=hn, entry_px=ep, exit_bar_t=xt, exit_px=xp, ret_bp=round(ret, 2), gross_bp=round(g, 2),
                               net_bp=round(g - COST, 2), mkt_bp=round(m, 2) if m is not None else "", excess_bp=round(g - d * m, 2) if m is not None else "", n_mkt=n, resolved_epoch=int(NOW))); done.add((s["sig_id"], hn))
    if newout: append_csv(outp, OUTCOLS, newout)
    tmp = sp + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, sp)
    msg = f"scan ok coins={len(C)}/{len(COINS)} failed={failed} new_signals={added} filled={filled} new_outcomes={len(newout)} total_signals={len(sigs)}"; log(msg); print(msg)

def report():
    sigs = read_csv(os.path.join(OUT, "signals.csv")); outs = read_csv(os.path.join(OUT, "outcomes.csv"))
    print(f"signals logged: {len(sigs)} (pending entry: {sum(s['status']=='pending' for s in sigs)}) | outcomes resolved: {len(outs)} | cost {COST:.0f}bp/round trip | baseline = same-time other-coin average")
    by = {}
    for s in sigs: by.setdefault((s["signal"], int(s["w"])), [0, 0])[0] += 1
    for o in outs: pass
    types = sorted(set((o["signal"], int(o["w"])) for o in outs) | set(by))
    print(f"{'signal':9s} {'w':>3s} {'n_sig':>5s} | " + " | ".join(f"{h:>4s} n   hit%  net_bp excess_bp" for h in HZ))
    for t in types:
        row = f"{t[0]:9s} {t[1]:>3d} {by.get(t, [0])[0]:>5d} | "; cells = []
        for hn in HZ:
            r = [o for o in outs if o["signal"] == t[0] and int(o["w"]) == t[1] and o["horizon"] == hn]
            if not r: cells.append(f"{'':>4s} {0:<3d} {'-':>5s} {'-':>7s} {'-':>9s}"); continue
            g = [float(o["gross_bp"]) for o in r]; n_ = [float(o["net_bp"]) for o in r]; ex = [float(o["excess_bp"]) for o in r if o["excess_bp"] != ""]
            cells.append(f"{'':>4s} {len(r):<3d} {100*sum(x>0 for x in g)/len(g):5.1f} {sum(n_)/len(n_):+7.1f} {(sum(ex)/len(ex) if ex else float('nan')):+9.1f}")
        print(row + " | ".join(cells))
    r = [o for o in outs if o["signal"] == "NEWSHORT" and int(o["w"]) == 16 and o["horizon"] == "4h"]
    print("\nNEWSHORT w=16 (4h pencere), 4h ileri getiri: canli vs backtest")
    if r:
        g = [float(o["gross_bp"]) for o in r]; n_ = [float(o["net_bp"]) for o in r]; ex = [float(o["excess_bp"]) for o in r if o["excess_bp"] != ""]
        print(f"  canli    n={len(r):4d} hit={100*sum(x>0 for x in g)/len(g):.1f}% net={sum(n_)/len(n_):+.1f}bp excess={sum(ex)/len(ex):+.1f}bp (n={len(ex)})")
    else: print("  canli    n=0 (henuz cozulmus sonuc yok)")
    print("  backtest n= 477 hit=60.6% net=+28.0bp excess=+14.6bp (Gate 15m, ~21 gun, dusus rejimi)")
    if r and len(r) < 30: print("  UYARI: n < 30 — canli sonuc istatistiksel olarak anlamsiz; karar icin en az ~100 sinyal biriktir.")

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
        else: print(__doc__)
    except Exception as e:
        log(f"FATAL {type(e).__name__} {str(e)[:120]}"); print("hata (loglandi):", type(e).__name__)
    sys.exit(0)
