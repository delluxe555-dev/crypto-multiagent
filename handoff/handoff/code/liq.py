"""Likidasyon verisi (anahtarsız, yalnızca OKX USDT-swap):
1) Gerçekleşen likidasyonlar: /public/liquidation-orders sayfalanarak (after=ts) OKX'in tuttuğu ~son 24 saatin tamamı çekilir,
   15dk / 1s / 4s / günlük pencerelere bölünür.
2) TAHMİNİ likidasyon birikimi (ısı haritası benzeri model): her zaman diliminde (15m,1h,4h,1d) mum başına OKX açık pozisyon (OI)
   değişimi; artan OI o mumun tipik fiyatından açılmış yeni pozisyon sayılır, yaygın kaldıraçlara (5-100x) dağıtılır,
   long/short hesap oranıyla ağırlıklanır, eski girişler sönümlenir, OI düşüşü havuzu orantılı küçültür, fiyatın zaten geçtiği
   seviyeler silinir. Sonuç kesin değildir; Coinglass vb. gibi tahminidir ve yalnızca OKX OI'sine dayanır."""
import os, json, time, math, requests
import extras

B = "https://www.okx.com/api/v5"
TF = {  # bar, mum sayısı, önbellek TTL (sn), en fazla uzaklık %, küme genişliği %, mum başı sönüm, etiket
    "15m": dict(bar="15m", n=96,  ttl=120,  maxd=4,  bin=0.25, decay=0.985, ad="15dk"),
    "1h":  dict(bar="1H",  n=100, ttl=300,  maxd=8,  bin=0.5,  decay=0.98,  ad="1s"),
    "4h":  dict(bar="4H",  n=100, ttl=900,  maxd=15, bin=1.0,  decay=0.98,  ad="4s"),
    "1d":  dict(bar="1D",  n=100, ttl=1800, maxd=30, bin=2.0,  decay=0.97,  ad="Günlük"),
}
LEV = {5: .15, 10: .30, 25: .25, 50: .18, 100: .12}   # varsayılan kaldıraç dağılımı (tahmin)
MM = 0.004                                            # yaklaşık bakım teminatı oranı
WIN = [("15dk", 15), ("1s", 60), ("4s", 240), ("Günlük", 1440)]

def _inst(ccy): return f"{ccy}-USDT-SWAP"

def ctval(ccy):
    try: return float(extras.get(B + "/public/instruments", {"instType": "SWAP", "instId": _inst(ccy)}, ttl=86400)["data"][0]["ctVal"])
    except Exception: return None

def _liq_orders(ccy, ttl=120, max_pages=30):
    """OKX'in sakladığı tüm (≈24 saat) dolmuş likidasyon emirleri; tüm liste TTL boyunca dosyada önbelleklenir."""
    p = os.path.join(extras.CACHE_DIR, f"liqall_{ccy}.json"); os.makedirs(extras.CACHE_DIR, exist_ok=True)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl: return json.load(open(p))
    seen, out, after, pages, now = set(), [], None, 0, time.time() * 1000
    while pages < max_pages:
        prm = {"instType": "SWAP", "uly": f"{ccy}-USDT", "state": "filled", "limit": 100}
        if after: prm["after"] = after
        r = requests.get(B + "/public/liquidation-orders", params=prm, timeout=12); pages += 1
        if r.status_code == 429: time.sleep(1); continue
        r.raise_for_status(); det = [d for blk in r.json().get("data", []) for d in blk["details"]]
        if not det: break
        for d in det:
            k = (d["ts"], d["sz"], d["bkPx"], d["posSide"])
            if k not in seen: seen.add(k); out.append({"ts": int(d["ts"]), "sz": float(d["sz"]), "px": float(d["bkPx"]), "side": d["posSide"]})
        m = min(int(d["ts"]) for d in det)
        if after and m >= after: break
        after = m
        if now - after > 25 * 3600 * 1000: break
        time.sleep(0.08)
    res = {"orders": out, "pages": pages, "oldest_h": (now - min((o["ts"] for o in out), default=now)) / 3.6e6, "fetched_ms": now}
    json.dump(res, open(p, "w")); return res

def realized(ccy):
    """Pencere başına gerçekleşen likidasyon: long_usd, short_usd, n, oran (long/short)."""
    raw = _liq_orders(ccy); ct = ctval(ccy) or 1; now = time.time() * 1000; w = {}
    for name, mins in WIN:
        sel = [o for o in raw["orders"] if now - o["ts"] <= mins * 60000]
        lu = sum(o["sz"] * ct * o["px"] for o in sel if o["side"] == "long"); su = sum(o["sz"] * ct * o["px"] for o in sel if o["side"] == "short")
        w[name] = {"long_usd": lu, "short_usd": su, "n": len(sel), "ls_ratio": (lu / su) if su else None}
    return {"windows": w, "n_total": len(raw["orders"]), "kapsam_saat": round(raw["oldest_h"], 1), "sayfa": raw["pages"],
            "not": "Yalnızca OKX USDT-swap; OKX ~son 24 saati tutar"}

def _series(ccy, tf):
    c = TF[tf]; inst = _inst(ccy)
    cd = extras.get(B + "/market/candles", {"instId": inst, "bar": c["bar"], "limit": c["n"]}, ttl=c["ttl"])["data"]
    oi = extras.get(B + "/rubik/stat/contracts/open-interest-history", {"instId": inst, "period": c["bar"], "limit": c["n"]}, ttl=c["ttl"])["data"]
    try: ls = extras.get(B + "/rubik/stat/contracts/long-short-account-ratio-contract", {"instId": inst, "period": c["bar"], "limit": c["n"]}, ttl=c["ttl"])["data"]
    except Exception: ls = []
    oi = {int(r[0]): float(r[3]) for r in oi}; ls = {int(r[0]): float(r[1]) for r in ls}
    rows = []
    for r in sorted(cd, key=lambda r: int(r[0])):
        t = int(r[0]); h, l, cl = float(r[2]), float(r[3]), float(r[4])
        rows.append({"t": t, "h": h, "l": l, "c": cl, "oi": oi.get(t), "ls": ls.get(t)})
    return [r for r in rows if r["oi"] is not None]

def estimate(ccy, tf, k=3):
    """Tahmini likidasyon kümeleri: fiyatın altında long, üstünde short; USD tahmini + % uzaklık."""
    c = TF[tf]; rows = _series(ccy, tf)
    if len(rows) < 3: return None
    pool = []   # [fiyat, usd, taraf, giriş_index]
    for i in range(1, len(rows)):
        r, prev = rows[i], rows[i - 1]
        f = r["oi"] / prev["oi"] if prev["oi"] else 1.0
        for e in pool: e[1] *= c["decay"] * (f if f < 1 else 1)          # sönüm + OI düşüşünde orantılı kapanış
        # fiyatın bu mumda geçtiği seviyeler likide oldu sayılır
        pool = [e for e in pool if not ((e[2] == "long" and r["l"] <= e[0]) or (e[2] == "short" and r["h"] >= e[0]))]
        d = r["oi"] - prev["oi"]
        if d <= 0: continue
        entry = (r["h"] + r["l"] + r["c"]) / 3
        lr = r["ls"] or 1.0; lf = 0.5 + (lr / (1 + lr) - 0.5) * 0.5   # hesap oranını yumuşatarak long payı
        for lev, wgt in LEV.items():
            pool.append([entry * (1 - 1 / lev + MM), d * lf * wgt, "long", i])
            pool.append([entry * (1 + 1 / lev - MM), d * (1 - lf) * wgt, "short", i])
    px = rows[-1]["c"]; step = math.log(1 + c["bin"] / 100); buck = {}
    for p, u, s, _ in pool:
        dist = (p / px - 1) * 100
        if (s == "long" and not (-c["maxd"] <= dist < 0)) or (s == "short" and not (0 < dist <= c["maxd"])): continue
        key = (s, math.floor(math.log(p) / step)); b = buck.setdefault(key, [0.0, 0.0]); b[0] += u; b[1] += u * p
    cl = [{"side": s, "px": b[1] / b[0], "usd": b[0], "dist_pct": (b[1] / b[0] / px - 1) * 100} for (s, _), b in buck.items() if b[0] > 0]
    top = lambda s: sorted([x for x in cl if x["side"] == s], key=lambda x: -x["usd"])[:k]
    near = lambda s: min([x for x in cl if x["side"] == s], key=lambda x: abs(x["dist_pct"]), default=None)
    return {"price": px, "long_below": top("long"), "short_above": top("short"),
            "near_long": near("long"), "near_short": near("short"), "candles": len(rows)}

def usdk(x):
    a = abs(x)
    return f"${x/1e9:.2f}B" if a >= 1e9 else f"${x/1e6:.1f}M" if a >= 1e6 else f"${x/1e3:.0f}K" if a >= 1e3 else f"${x:.0f}"

def pfmt(x): return f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}" if x >= 10 else f"{x:.4f}" if x >= 0.1 else f"{x:.6g}"

def report(symbol):
    ccy = symbol.replace("USDT", ""); out = {"realized": None, "estimated": {}}
    try: out["realized"] = realized(ccy)
    except Exception as e: out["realized_err"] = str(e)[:120]
    for tf in TF:
        try: out["estimated"][tf] = estimate(ccy, tf)
        except Exception as e: out["estimated"][tf] = None; out.setdefault("est_err", {})[tf] = str(e)[:120]
    return out

def text(rep):
    """Duygu ajanı için kısa, bölümlü metin."""
    R = rep.get("realized"); E = rep.get("estimated") or {}
    if not R and not any(E.values()): return ""
    L = [f"Likidasyonlar (yalnızca OKX USDT-swap; gerçekleşen örneklem n={R['n_total']}, kapsam ~{R['kapsam_saat']}s; kümeler TAHMİNİ, OKX OI modelinden, büyükten küçüğe):" if R
         else "Likidasyonlar (yalnızca OKX; kümeler TAHMİNİ, OKX OI modelinden):"]
    tf_of = {"15dk": "15m", "1s": "1h", "4s": "4h", "Günlük": "1d"}
    for name, _ in WIN:
        L.append(f"— {name} —")
        if R:
            w = R["windows"][name]; q = w["ls_ratio"]; ratio = (">99" if q > 99 else f"{q:.2f}") if q is not None else (">99" if w["long_usd"] else "-")
            L.append(f"  Gerçekleşen: long {usdk(w['long_usd'])} / short {usdk(w['short_usd'])}, n={w['n']}, L/S={ratio}")
        e = E.get(tf_of[name])
        if e:
            f = lambda xs: ", ".join(f"{pfmt(x['px'])} ({x['dist_pct']:+.1f}%, ~{usdk(x['usd'])})" for x in xs) or "yok"
            L.append(f"  Tahmini long-liq altta: {f(e['long_below'])}")
            L.append(f"  Tahmini short-liq üstte: {f(e['short_above'])}")
    return "\n".join(L)

def nearest(symbol, interval):
    """Telegram için: karar zaman dilimindeki en büyük yakın tahmini kümeler (üstte short-liq, altta long-liq)."""
    tf = interval if interval in TF else "1h"
    e = estimate(symbol.replace("USDT", ""), tf)
    if not e: return None
    up = e["short_above"][0] if e["short_above"] else None; dn = e["long_below"][0] if e["long_below"] else None
    return {"tf": TF[tf]["ad"], "up": up and {"px": up["px"], "pct": up["dist_pct"], "usd": up["usd"]}, "down": dn and {"px": dn["px"], "pct": dn["dist_pct"], "usd": dn["usd"]}}

if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["BTCUSDT"]:
        print(f"### {s}"); print(text(report(s))); print()
