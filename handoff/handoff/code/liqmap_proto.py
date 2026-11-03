#!/usr/bin/env python3
"""liqmap_proto.py - PROTOTYPE tahmini likidasyon kumesi (isi haritasi) modeli. Anahtarsiz, yalnizca acik Gate (+opsiyonel OKX) verisi.
KULLANIM: python3 liqmap_proto.py ARB NEAR BTW [--bin 0.5] [--thr 25e6] [--oi-mult 3.0] [--no-okx]
NASIL CALISIR (Coinglass/Coinank benzeri 'OI-delta x kaldirac' modeli):
  * Gate contract_stats (15dk, ~21 gun): open_interest_usd, lsr_taker, mark_price; Gate mumlari (high/low).
  * Her 15dk mumda OI artisi (+dOI) = yeni acilan pozisyon, mumun tipik fiyatindan acilmis sayilir. (Gercekte long OI = short OI;
    her iki tarafa da ~dOI yazilir, aralarindaki dagilim taker oranina gore +-%25 kaydirilir.)
  * Kaldirac kovalari 5/10/25/50/100x (kontratin max kaldiracini asanlar atilir), liq fiyati = giris*(1 -/+ 1/lev -/+ mmr)
    (mmr = Gate maintenance_rate; mmr yuksekse kaldirac siniri 1/(2*mmr)).
  * OI azalinca tum havuz orantili kuculur (kapanislar); fiyat bir seviyeyi gecince (mum low/high) o seviye silinir (likide oldu varsayilir).
  * Pencere basindaki mevcut OI, ilk mumdan acilmis sayilir (bilinmeyen gecmis -> belirsizlik).
  * --oi-mult / OKX: Gate OI'si piyasanin kucuk payi; boyutlari (Gate+OKX)/Gate ile olcekler (Binance'e hala ulasilmaz).
SINIRLAR: bu TAHMIN; borsa verisi degil. Kaldirac dagilimi varsayim, giris fiyatlari OI farkindan cikarilir (gercek pozisyon girisi bilinmez),
  isolated/cross ayrimi ve hedge/emir defteri yok, Binance/Bybit OI yok. Siralama (hangi seviye daha yogun) daha guvenilir, USD buyuklugu daha az."""
import sys, math, time, requests
G = "https://api.gateio.ws/api/v4/futures/usdt"
LEV = {5: .15, 10: .30, 25: .25, 50: .18, 100: .12}

def get(u, p=None):
    for _ in range(3):
        r = requests.get(u, params=p, timeout=20)
        if r.status_code == 429: time.sleep(1.5); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError("rate limited")

def okx_oi_usd(ccy):
    try:
        d = get("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP", "instId": f"{ccy}-USDT-SWAP"})["data"][0]
        return float(d["oiUsd"])
    except Exception: return None

def load(ccy):
    c = f"{ccy}_USDT"; ct = get(f"{G}/contracts/{c}")
    st = get(f"{G}/contract_stats", {"contract": c, "interval": "15m", "limit": 2000})
    cd = get(f"{G}/candlesticks", {"contract": c, "interval": "15m", "limit": 2000})
    k = {int(x["t"]): x for x in cd}
    rows = []
    for s in sorted(st, key=lambda s: s["time"]):
        x = k.get(s["time"])
        if not x or not s.get("open_interest_usd"): continue
        rows.append(dict(t=s["time"], h=float(x["h"]), l=float(x["l"]), c=float(x["c"]), oi=float(s["open_interest_usd"]), lsr=float(s.get("lsr_taker") or 1)))
    return ct, rows

def build(ccy, binpct=0.5, oi_mult=None, use_okx=True):
    ct, rows = load(ccy)
    mmr = float(ct.get("maintenance_rate") or 0.005); lmax = float(ct.get("leverage_max") or 100)
    levs = {l: w for l, w in LEV.items() if l <= lmax and 1 / l > 2 * mmr}
    if not levs: levs = {5: 1.0} if 0.2 > 2 * mmr else {2: 1.0}
    tw = sum(levs.values()); levs = {l: w / tw for l, w in levs.items()}
    pool = []  # [liq_px, usd, side]
    prev_oi = rows[0]["oi"]; ep0 = (rows[0]["h"] + rows[0]["l"] + rows[0]["c"]) / 3
    for l, w in levs.items():
        pool += [[ep0 * (1 - 1 / l + mmr), prev_oi * w, "long"], [ep0 * (1 + 1 / l - mmr), prev_oi * w, "short"]]
    for r in rows[1:]:
        pool = [e for e in pool if not ((e[2] == "long" and r["l"] <= e[0]) or (e[2] == "short" and r["h"] >= e[0]))]
        d = r["oi"] - prev_oi
        if d < 0 and prev_oi > 0:
            f = r["oi"] / prev_oi
            for e in pool: e[1] *= f
        elif d > 0:
            ep = (r["h"] + r["l"] + r["c"]) / 3; sh = r["lsr"] / (1 + r["lsr"]); lf = 0.5 + (sh - 0.5) * 0.5
            for l, w in levs.items():
                pool.append([ep * (1 - 1 / l + mmr), d * w * 2 * lf, "long"]); pool.append([ep * (1 + 1 / l - mmr), d * w * 2 * (1 - lf), "short"])
        prev_oi = r["oi"]
    px = rows[-1]["c"]; step = math.log(1 + binpct / 100); b = {}
    for p, u, s in pool:
        if (s == "long" and p >= px) or (s == "short" and p <= px): continue
        x = b.setdefault((s, math.floor(math.log(p) / step)), [0.0, 0.0]); x[0] += u; x[1] += u * p
    gate_oi = rows[-1]["oi"]; mult = oi_mult
    okx = None
    if mult is None:
        okx = okx_oi_usd(ccy) if use_okx else None
        mult = (gate_oi + okx) / gate_oi if okx else 1.0
    cl = [dict(side=s, px=v[1] / v[0], usd=v[0] * mult, gate_usd=v[0], dist=(v[1] / v[0] / px - 1) * 100) for (s, _), v in b.items() if v[0] > 0]
    return dict(ccy=ccy, px=px, bars=len(rows), days=len(rows) / 96, gate_oi=gate_oi, okx_oi=okx, mult=mult, levs=levs, mmr=mmr, clusters=cl)

def usd(x): return f"${x/1e6:.2f}M" if abs(x) >= 1e6 else f"${x/1e3:.0f}K"
def pf(x): return f"{x:,.2f}" if x >= 10 else f"{x:.5g}"

def show(m, thr=25e6, k=4):
    print(f"### {m['ccy']}  px={pf(m['px'])}  {m['days']:.1f} gun/{m['bars']} bar  GateOI={usd(m['gate_oi'])}"
          f" OKX_OI={usd(m['okx_oi']) if m['okx_oi'] else '-'}  olcek x{m['mult']:.2f}  mmr={m['mmr']}  kaldirac={list(m['levs'])}")
    cl = m["clusters"]; tot = {s: sum(c["usd"] for c in cl if c["side"] == s) for s in ("long", "short")}
    for s, nm in (("short", "USTTE short-liq (fiyat yukselirse)"), ("long", "ALTTA long-liq (fiyat duserse)")):
        xs = sorted([c for c in cl if c["side"] == s], key=lambda c: -c["usd"])[:k]
        print(f"  {nm}: toplam {usd(tot[s])}")
        for c in sorted(xs, key=lambda c: abs(c["dist"])): print(f"     {pf(c['px']):>10} ({c['dist']:+5.1f}%)  ~{usd(c['usd'])}  (Gate-only {usd(c['gate_usd'])})")
    near = [c for c in cl if abs(c["dist"]) <= 1.5]
    big = [c for c in near if c["usd"] >= thr]; rel = [c for c in near if c["usd"] >= 0.0025 * m["gate_oi"] * m["mult"]]
    print(f"  MAGNET-NEAR (<=%1.5, >= {usd(thr)}): {'EVET ' + ', '.join(pf(c['px']) + ' ' + usd(c['usd']) for c in big) if big else 'yok'}"
          f" | goreli esik (>= OI'nin 25bps'i): {'EVET ' + ', '.join(c['side'] + ' ' + pf(c['px']) + ' ' + usd(c['usd']) for c in rel) if rel else 'yok'}\n")

if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda n, d: float(a[a.index(n) + 1]) if n in a else d
    coins = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--bin", "--thr", "--oi-mult"))]
    for c in coins or ["ARB"]:
        try: show(build(c.upper().replace("USDT", ""), opt("--bin", 0.5), opt("--oi-mult", None) if "--oi-mult" in a else None, "--no-okx" not in a), opt("--thr", 25e6))
        except Exception as e: print(f"### {c}: HATA {str(e)[:150]}\n")
