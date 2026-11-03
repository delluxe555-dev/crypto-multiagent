#!/usr/bin/env python3
"""radar_read.py - botun cercevesinde (OF-POS / OF-OI / funding / teknik / skor) KISA TURKCE yorum. Anahtarsiz; yalnizca Gate (+OKX, Bitget capraz kontrol).
KULLANIM: python3 radar_read.py ARB NEAR ETHFI BTW [--tf 1h|15m]
  --tf: 4-bar pencere hangi mumla olculsun (varsayilan 1h = 4 saat; 15m = 1 saat). 12s degisim her zaman ayrica verilir.
NOT: OI Gate (ve OKX) tabanlidir, Binance'ten cok kucuktur; yuzdeler YAKLASIKTIR. Bu yorum alim-satim tavsiyesi degildir.
Skor (botun kurali): yeni long +2, yeni short -2, long tasfiyesi -1, short squeeze +1; funding ucu kalabalik tarafin tersi +-1 (longlar oduyorsa -1);
  toplam >=2 LONG, <=-2 SHORT, arasi NOTR. Mıknatis/supurme/OF-DIV/opsiyon/makro bu betikte YOK (kapali kaynak veya hesaplanamiyor)."""
import sys, time, math, requests
G = "https://api.gateio.ws/api/v4/futures/usdt"; OKX = "https://www.okx.com/api/v5"; BG = "https://api.bitget.com/api/v2/mix/market"
PX_TH, OI_TH, SPIKE_TH, FUND_TH, SPREAD_TH = 0.5, 1.0, 3.0, 0.05, 0.03   # yuzde

def get(u, p=None, tries=3):
    for _ in range(tries):
        try:
            r = requests.get(u, params=p, timeout=15)
            if r.status_code == 429: time.sleep(1.5); continue
            if r.status_code != 200: return None
            return r.json()
        except Exception: time.sleep(0.5)
    return None

def gate(coin, itv):
    sec = {"15m": 900, "1h": 3600}[itv]; now = time.time(); c = f"{coin}_USDT"
    ct = get(f"{G}/contracts/{c}")
    if not ct or "name" not in ct: return None
    cd = get(f"{G}/candlesticks", {"contract": c, "interval": itv, "limit": 300}) or []
    st = get(f"{G}/contract_stats", {"contract": c, "interval": itv, "limit": 300}) or []
    cd = [x for x in cd if x["t"] + sec <= now]; stm = {s["time"]: s for s in st}
    rows = []
    for x in cd:
        s = stm.get(x["t"])
        if s and s.get("open_interest_usd"):
            rows.append(dict(t=x["t"], o=float(x["o"]), h=float(x["h"]), l=float(x["l"]), c=float(x["c"]), oi=float(s["open_interest_usd"]), lsr=float(s.get("lsr_taker") or 1),
                             lsr_acc=float(s.get("lsr_account") or 1), tlsr=float(s.get("top_lsr_account") or 1), ll=float(s.get("long_liq_usd") or 0), sl=float(s.get("short_liq_usd") or 0)))
    iv = (ct.get("funding_interval") or 28800) / 3600
    return dict(ct=ct, rows=rows, fund8=float(ct.get("funding_rate") or 0) * 8 / iv * 100, fiv=iv)

def okx_x(coin):
    out = {}
    d = get(f"{OKX}/public/funding-rate", {"instId": f"{coin}-USDT-SWAP"})
    try:
        x = d["data"][0]; iv = (int(x["nextFundingTime"]) - int(x["fundingTime"])) / 3.6e6 or 8; out["fund8"] = float(x["fundingRate"]) * 8 / iv * 100
    except Exception: pass
    d = get(f"{OKX}/rubik/stat/contracts/open-interest-history", {"instId": f"{coin}-USDT-SWAP", "period": "1H", "limit": 20})
    try: out["oi"] = [(int(r[0]) // 1000, float(r[3])) for r in d["data"]][::-1]
    except Exception: pass
    d = get(f"{OKX}/market/candles", {"instId": f"{coin}-USDT-SWAP", "bar": "1H", "limit": 20})
    try: out["px"] = [(int(r[0]) // 1000, float(r[4])) for r in d["data"] if r[8] == "1"][::-1]
    except Exception: pass
    return out

def bitget_x(coin):
    out = {}; s = f"{coin}USDT"
    d = get(f"{BG}/current-fund-rate", {"symbol": s, "productType": "usdt-futures"})
    try: x = d["data"][0]; out["fund8"] = float(x["fundingRate"]) * 8 / float(x.get("fundingRateInterval") or 8) * 100
    except Exception: pass
    d = get(f"{BG}/open-interest", {"symbol": s, "productType": "usdt-futures"}); t = get(f"{BG}/ticker", {"symbol": s, "productType": "usdt-futures"})
    try: out["oi_usd"] = float(d["data"]["openInterestList"][0]["size"]) * float(t["data"][0]["lastPr"])
    except Exception: pass
    return out

def rsi(c, n=14):
    if len(c) < n + 2: return None
    g = l = 0.0
    for i in range(1, n + 1): d = c[i] - c[i - 1]; g += max(d, 0); l += max(-d, 0)
    g /= n; l /= n
    for i in range(n + 1, len(c)): d = c[i] - c[i - 1]; g = (g * (n - 1) + max(d, 0)) / n; l = (l * (n - 1) + max(-d, 0)) / n
    return 100 - 100 / (1 + g / l) if l else 100.0

def atr(rows, n=14):
    tr = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rows, rows[1:])]
    if len(tr) < n: return None
    a = sum(tr[:n]) / n
    for x in tr[n:]: a = (a * (n - 1) + x) / n
    return a

def ema(v, n):
    k = 2 / (n + 1); e = v[0]; out = []
    for x in v: e = x * k + e * (1 - k); out.append(e)
    return out

def swings(rows, k=3):
    hi, lo = [], []
    for i in range(k, len(rows) - k):
        if rows[i]["h"] == max(r["h"] for r in rows[i - k:i + k + 1]): hi.append(rows[i]["h"])
        if rows[i]["l"] == min(r["l"] for r in rows[i - k:i + k + 1]): lo.append(rows[i]["l"])
    return hi, lo

def pct(a, b): return (a / b - 1) * 100 if b else float("nan")
def usd(x): return f"${x/1e6:.2f}M" if abs(x) >= 1e6 else f"${x/1e3:.0f}K" if abs(x) >= 1e3 else f"${x:.0f}"
def pf(x): return f"{x:,.2f}" if x >= 10 else f"{x:.5g}"

def story(px, oi):
    """OF-POS: (hikaye, skor). Esik: fiyat >= %0.5 ve OI >= %1."""
    if abs(px) < PX_TH or abs(oi) < OI_TH: return "belirgin hikaye yok (fiyat/OI esik alti)", 0
    if px > 0 and oi > 0: return "yeni longlar aciliyor (trend yakit aliyor)", 2
    if px < 0 and oi > 0: return "yeni shortlar aciliyor", -2
    if px < 0 and oi < 0: return "long tasfiyesi: dusus pozisyon kapatmayla geliyor", -1
    return "short squeeze: yukselis short kapanisiyla geliyor", 1

def read(coin, tf="1h"):
    g1 = gate(coin, "1h")
    if not g1 or len(g1["rows"]) < 60: return f"### {coin}: Gate'te yok ya da yetersiz veri."
    gt = g1 if tf == "1h" else gate(coin, tf); R = gt["rows"]; R1 = g1["rows"]; ok = okx_x(coin); bg = bitget_x(coin)
    px = R[-1]["c"]; w = 4; lab = "4s" if tf == "1h" else "1s"
    p4, o4 = pct(px, R[-1 - w]["c"]), pct(R[-1]["oi"], R[-1 - w]["oi"])
    p12, o12 = pct(R1[-1]["c"], R1[-13]["c"]), pct(R1[-1]["oi"], R1[-13]["oi"])
    st4, sc4 = story(p4, o4); st12, _ = story(p12, o12)
    spike = abs(o4) >= SPIKE_TH
    cl = [r["c"] for r in R1]; rs = rsi(cl); a = atr(R1); e20, e50 = ema(cl, 20)[-1], ema(cl, 50)[-1]
    gap = (e20 - e50) / px / (a / px) if a else 0
    trend = "YUKARI" if px > e50 and e20 > e50 and gap > .3 else "ASAGI" if px < e50 and e20 < e50 and gap < -.3 else "YATAY"
    hi, lo = swings(R1[-200:]); res = min([x for x in hi if x > px], default=None); sup = max([x for x in lo if x < px], default=None)
    h24 = max(r["h"] for r in R1[-24:]); l24 = min(r["l"] for r in R1[-24:]); band = (px - l24) / (h24 - l24) * 100 if h24 > l24 else 50
    fs = {"Gate": g1["fund8"]}; fs.update({k: v for k, v in (("OKX", ok.get("fund8")), ("Bitget", bg.get("fund8"))) if v is not None})
    fmax = max(fs.values(), key=abs); spread = max(fs.values()) - min(fs.values()); fsc = 0; fnote = "nötr"
    if abs(fmax) >= FUND_TH: fsc = -1 if fmax > 0 else 1; fnote = f"UC: {'longlar oduyor (kalabalik long)' if fmax > 0 else 'shortlar oduyor (kalabalik short)'}"
    if spread >= SPREAD_TH: fnote += f" | borsalar arasi fark {spread:.3f}%"
    ll4 = sum(r["ll"] for r in R1[-4:]); sl4 = sum(r["sl"] for r in R1[-4:]); ll12 = sum(r["ll"] for r in R1[-12:]); sl12 = sum(r["sl"] for r in R1[-12:])
    score = sc4 + fsc; bias = "LONG egilimli" if score >= 2 else "SHORT egilimli" if score <= -2 else "NOTR"
    # capraz kontrol
    xc = []
    if ok.get("px") and len(ok["px"]) > 4: xc.append(f"OKX fiyat 4s {pct(ok['px'][-1][1], ok['px'][-5][1]):+.2f}%")
    if ok.get("oi") and len(ok["oi"]) > 13: xc.append(f"OKX OI 4s {pct(ok['oi'][-1][1], ok['oi'][-5][1]):+.2f}% / 12s {pct(ok['oi'][-1][1], ok['oi'][-13][1]):+.2f}% (OI {usd(ok['oi'][-1][1])})")
    if bg.get("oi_usd"): xc.append(f"Bitget OI {usd(bg['oi_usd'])}")
    L = [f"### {coin} — {pf(px)} (Gate perp) | OI Gate {usd(R[-1]['oi'])} (YAKLASIK; Binance'ten kucuk)",
         f"Degisim {lab}: fiyat {p4:+.2f}%, OI {o4:+.2f}% | 12s: fiyat {p12:+.2f}%, OI {o12:+.2f}%",
         f"OF-POS ({lab}): {st4}" + (f"  [{'+' if sc4>0 else ''}{sc4}]" if sc4 else "") + f" | 12s: {st12}",
         f"OF-OI: {'OI SICRAMASI (%+.1f%%, esik %%3)' % o4 if spike else 'yok (|OI| < %3)'}" + f" | Gate tasfiye: son 4s long {usd(ll4)} / short {usd(sl4)}, 12s long {usd(ll12)} / short {usd(sl12)}",
         f"Funding (8s-esdeger): " + ", ".join(f"{k} {v:+.4f}%" for k, v in fs.items()) + f" → {fnote}" + (f"  [{'+' if fsc>0 else ''}{fsc}]" if fsc else ""),
         f"Teknik (1s): trend {trend} | RSI {rs:.0f} | ATR {a/px*100:.2f}% | 24s bandinda %{band:.0f} konum" + (" (premium)" if band > 80 else " (discount)" if band < 20 else ""),
         f"Seviyeler: direnc {pf(res) + f' ({pct(res,px):+.1f}%)' if res else 'yok'} | destek {pf(sup) + f' ({pct(sup,px):+.1f}%)' if sup else 'yok'} (swing)",
         f"SKOR {score:+d} → {bias}"]
    if bias.startswith("LONG"): L.append(f"Teyit: {pf(res) if res else 'direnc'} ustunde tutunma | Iptal: {pf(sup) if sup else 'destek'} alti kapanis")
    elif bias.startswith("SHORT"): L.append(f"Teyit: {pf(sup) if sup else 'destek'} alti tutunma | Iptal: {pf(res) if res else 'direnc'} ustu kapanis")
    else: L.append(f"Yukari teyit: {pf(res) if res else '-'} ustu | asagi teyit: {pf(sup) if sup else '-'} alti (iki yonde de bekle-gor)")
    if xc: L.append("Capraz kontrol: " + "; ".join(xc))
    return "\n".join(L)

if __name__ == "__main__":
    a = sys.argv[1:]; tf = a[a.index("--tf") + 1] if "--tf" in a else "1h"
    coins = [x.upper().replace("USDT", "") for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--tf")]
    for c in coins or ["ARB"]: print(read(c, tf)); print()
    print("Not: OI Gate/OKX tabanli, Binance'ten kucuk; yuzdeler yaklasiktir. Mıknatis/supurme/OF-DIV/opsiyon/makro dahil degil. Alim-satim tavsiyesi degildir.")
