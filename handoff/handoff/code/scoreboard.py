"""Ajan karnesi (LLM'siz, KÂĞIT işlem): her ajanın yön çağrısını (BOĞA/AYI/NÖTR) sonraki 4s ve 24s gerçekleşen getiriyle karşılaştırır.
Kaynak: outputs/*_mtf-1h_*.json (4h trend + 1h giriş) ve outputs/*_1h_*.json (teknik, duygu, boğa, ayı, hakem) — işlem açılmayan mumlar dahil.
Getiri: karar mumunun KAPANIŞINDAN +4 / +24 saatlik mumun kapanışına (Binance spot data-api.binance.vision). Ek LLM çağrısı YOK.
Çıktı: outputs/trader/agent_scores.json  (döngü sonunda trader.cycle() güncelller; sabah özetinde 'Ajan karnesi' satırı).
Kural: >=30 yönlü+sonuçlanmış çağrısı olup isabeti şansın açıkça altındaysa (Wilson %95 üst sınırı < %50) veya
diğer ajanların medyanının >=15 puan altında VE sabit-yön taban çizgisinin altındaysa DEĞİŞTİRME ÖNERİLİR (otomatik uygulanmaz).
CLI: python scoreboard.py update | audit [--json out.json]"""
import os, sys, re, json, glob, math, time, argparse
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs"); TD = os.path.join(OUT, "trader")
SCORES = os.path.join(TD, "agent_scores.json"); OBS = os.path.join(TD, "agent_obs.json")
SPOT = "https://data-api.binance.vision/api/v3/klines"; H = 3600_000
AGENTS = ["mtf_4h", "mtf_giris", "teknik_analist", "duygu_analisti", "hakem"]
LABEL = {"mtf_4h": "4s trend", "mtf_giris": "1s giriş", "teknik_analist": "teknik", "duygu_analisti": "duygu", "hakem": "hakem",
         "boga": "boğa", "ayi": "ayı"}
HORIZONS = {"4s": 4, "24s": 24}
MIN_N = 30; ROLL = 100

def _stance_text(t):
    m = re.search(r"E[ĞG][İI]L[İI]M\s*[:：]\s*\**\s*(BO[ĞG]A|AYI|N[ÖO]TR)", t or "", re.I)
    if not m: return None
    v = m.group(1).upper(); return "BULL" if v.startswith("BO") else "BEAR" if v.startswith("AY") else "NEUTRAL"

def _asdict(x):
    if isinstance(x, dict): return x
    return {}

def _utc_ms(s):
    import calendar
    return calendar.timegm(time.strptime(str(s)[:16], "%Y-%m-%d %H:%M")) * 1000

def observations_from_outputs(outdir=OUT):
    """Canlı döngü çıktılarından (dry-run hariç) ajan çağrıları. Mum zamanı = mumun AÇILIŞI (UTC); karar kapanışta verilir."""
    obs = []
    for f in sorted(glob.glob(os.path.join(outdir, "*_mtf-1h_*.json"))):
        try: d = json.load(open(f))
        except Exception: continue
        if d.get("dry_run") or "symbol" not in d or "time" not in d: continue
        sym, bar = d["symbol"], d["time"]
        tr, en = _asdict(d.get("trend_4h")), _asdict(d.get("entry"))
        obs.append(dict(agent="mtf_4h", symbol=sym, bar=bar, stance={"YUKARI": "BULL", "ASAGI": "BEAR"}.get(str(tr.get("trend")).upper(), "NEUTRAL"), conf=tr.get("guven"), src="canli"))
        obs.append(dict(agent="mtf_giris", symbol=sym, bar=bar, stance={"LONG": "BULL", "SHORT": "BEAR"}.get(str(en.get("giris")).upper(), "NEUTRAL"), conf=en.get("guven"), src="canli"))
    for f in sorted(glob.glob(os.path.join(outdir, "*_1h_2*.json"))):
        try: d = json.load(open(f))
        except Exception: continue
        if d.get("dry_run") or d.get("interval") != "1h" or "symbol" not in d or "data_date" not in d: continue
        sym, bar = d["symbol"], d["data_date"]; h = _asdict(d.get("hakem"))
        for ag in ("teknik_analist", "duygu_analisti"):
            s = _stance_text(d.get(ag)); 
            if s: obs.append(dict(agent=ag, symbol=sym, bar=bar, stance=s, src="canli"))
        obs.append(dict(agent="hakem", symbol=sym, bar=bar, stance={"BUY": "BULL", "SELL": "BEAR"}.get(str(h.get("karar")).upper(), "NEUTRAL"), conf=h.get("guven"), src="canli"))
    return obs

def observations_from_backtest(path, src):
    obs = []
    try: b = json.load(open(path))
    except Exception: return obs
    for r in b.get("rows", []):
        sym, bar = b["symbol"], r["mum_utc"]
        if r.get("trend_4h"): obs.append(dict(agent="mtf_4h", symbol=sym, bar=bar, stance={"YUKARI": "BULL", "ASAGI": "BEAR"}.get(r["trend_4h"], "NEUTRAL"), src=src))
        if r.get("giris_1h"): obs.append(dict(agent="mtf_giris", symbol=sym, bar=bar, stance={"LONG": "BULL", "SHORT": "BEAR"}.get(r["giris_1h"], "NEUTRAL"), src=src))
        eg = r.get("egilim") or {}
        for ag, k in (("teknik_analist", "teknik"), ("duygu_analisti", "duygu")):
            if eg.get(k): obs.append(dict(agent=ag, symbol=sym, bar=bar, stance=eg[k], src=src))
        if r.get("hakem"): obs.append(dict(agent="hakem", symbol=sym, bar=bar, stance={"BUY": "BULL", "SELL": "BEAR"}.get(r["hakem"], "NEUTRAL"), src=src))
    return obs

_KL = {}
def klines_1h(sym, ttl=600):
    c = _KL.get(sym)
    if c and time.time() - c[0] < ttl: return c[1]
    r = requests.get(SPOT, params={"symbol": sym, "interval": "1h", "limit": 1000}, timeout=20).json()
    if not isinstance(r, list): raise RuntimeError(f"klines {sym}: {str(r)[:100]}")
    k = {int(x[0]): float(x[4]) for x in r if int(x[6]) < time.time() * 1000}   # açılış ms -> kapanış fiyatı (kapanmış mumlar)
    _KL[sym] = (time.time(), k); return k

def fwd(sym, bar, hours):
    """bar (mum açılışı UTC) kapanışından +hours saat sonraki kapanışa getiri %. Veri yoksa None."""
    k = klines_1h(sym); t0 = _utc_ms(bar); a, b = k.get(t0), k.get(t0 + hours * H)
    return round(100 * (b / a - 1), 3) if a and b else None

def wilson(h, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    p = h / n; d = 1 + z * z / n; c = p + z * z / (2 * n); w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - w) / d, (c + w) / d)

def score(obs, horizon, last=None):
    """obs: değerlendirilmiş çağrılar (r_<ufuk> dolu). Ajan başına istatistik."""
    res = {}
    for ag in sorted({o["agent"] for o in obs}):
        xs = [o for o in obs if o["agent"] == ag]; xs.sort(key=lambda o: (o["bar"], o["symbol"]))
        ev = [o for o in xs if o.get(f"r_{horizon}") is not None]
        if last: ev = ev[-last:]
        dr = [o for o in ev if o["stance"] in ("BULL", "BEAR")]
        hit = sum((o["stance"] == "BULL") == (o[f"r_{horizon}"] > 0) for o in dr)
        n_bear = sum(o["stance"] == "BEAR" for o in dr); n_bull = len(dr) - n_bear
        sret = [(1 if o["stance"] == "BULL" else -1) * o[f"r_{horizon}"] for o in dr]
        up = sum(o[f"r_{horizon}"] > 0 for o in dr)
        base = max(up, len(dr) - up) / len(dr) if dr else None     # her çağrıda "piyasanın o pencerede gittiği yönü" bilen taban DEĞİL; sabit-yön en iyisi
        maj = "BULL" if n_bull >= n_bear else "BEAR"
        const_hit = (up if maj == "BULL" else len(dr) - up) / len(dr) if dr else None   # ajanın çoğunluk yönünü hep söylese isabeti
        lo, hi = wilson(hit, len(dr))
        res[ag] = {"toplam_cagri": len(xs), "degerlendirilen": len(ev), "yonlu": len(dr), "notr_%": round(100 * (len(ev) - len(dr)) / len(ev), 1) if ev else None,
                   "isabet": hit, "isabet_%": round(100 * hit / len(dr), 1) if dr else None, "wilson95": [round(100 * lo, 1), round(100 * hi, 1)],
                   "ayi_payi_%": round(100 * n_bear / len(dr), 1) if dr else None, "sabit_yon_taban_%": round(100 * const_hit, 1) if const_hit is not None else None,
                   "sabit_yon": maj if dr else None, "ort_yonlu_getiri_%": round(sum(sret) / len(sret), 3) if sret else None}
    return res

def verdicts(sc):
    """sc: ajan -> 4s skor (rolling). Otomatik uygulanmaz."""
    rates = {a: s["isabet_%"] for a, s in sc.items() if s["yonlu"] >= MIN_N and s["isabet_%"] is not None}
    out = {}
    for a, s in sc.items():
        n = s["yonlu"]
        if n < MIN_N: out[a] = {"durum": "yetersiz örneklem", "not": f"n={n} < {MIN_N}"}; continue
        others = sorted(v for k, v in rates.items() if k != a)
        med = others[len(others) // 2] if others else None
        clearly_below = s["wilson95"][1] < 50
        rel_below = med is not None and s["isabet_%"] <= med - 15 and s["isabet_%"] < (s["sabit_yon_taban_%"] or 0)
        if clearly_below or rel_below:
            out[a] = {"durum": "DEĞİŞTİRME ÖNERİSİ", "not": f"isabet %{s['isabet_%']} (n={n}, Wilson95 {s['wilson95'][0]}–{s['wilson95'][1]})" + (f", diğer medyan %{med}" if med is not None else "")}
        else: out[a] = {"durum": "izle/tamam", "not": f"isabet %{s['isabet_%']} (n={n})"}
    return out

def update(outdir=OUT, save=True):
    """Gözlemleri topla, yeni pencereler için getiri doldur, skorları ve önerileri yaz. Ağ hatasında sessizce eskiyi korur."""
    os.makedirs(TD, exist_ok=True)
    store = json.load(open(OBS)) if os.path.exists(OBS) else {}
    for o in observations_from_outputs(outdir):
        key = f"{o['agent']}|{o['symbol']}|{o['bar']}"
        if key not in store: store[key] = o
    now_ms = time.time() * 1000
    for o in store.values():
        t0 = _utc_ms(o["bar"])
        for name, hrs in HORIZONS.items():
            if o.get(f"r_{name}") is None and now_ms > t0 + (hrs + 1) * H + 120_000:
                try: o[f"r_{name}"] = fwd(o["symbol"], o["bar"], hrs)
                except Exception: pass
    obs = list(store.values())
    res = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kural": f">={MIN_N} yönlü çağrı + isabet şansın açıkça altında (Wilson95 üst<%50) veya medyanın >=15 puan altı -> öneri (otomatik uygulanmaz)",
           "roll_n": ROLL, "ufuklar": {}}
    for name, hrs in HORIZONS.items():
        res["ufuklar"][name] = {"tum": score(obs, name), "son%d" % ROLL: score(obs, name, ROLL)}
    res["oneriler"] = verdicts(res["ufuklar"]["4s"]["son%d" % ROLL])
    res["oneriler_24s"] = verdicts(res["ufuklar"]["24s"]["son%d" % ROLL])
    if save:
        json.dump(store, open(OBS + ".tmp", "w"), ensure_ascii=False); os.replace(OBS + ".tmp", OBS)
        json.dump(res, open(SCORES + ".tmp", "w"), ensure_ascii=False, indent=1); os.replace(SCORES + ".tmp", SCORES)
    return res

def audit(extra=True):
    store = json.load(open(OBS)) if os.path.exists(OBS) else {}
    live = observations_from_outputs()
    bt = observations_from_backtest(os.path.join(OUT, "backtest_1h_SOLUSDT.json"), "bt_v1") + observations_from_backtest(os.path.join(OUT, "backtest_1h_SOLUSDT_v2.json"), "bt_v2")
    allobs = {}
    for o in live + bt: allobs[f"{o['src']}|{o['agent']}|{o['symbol']}|{o['bar']}"] = dict(o)
    now_ms = time.time() * 1000
    for o in allobs.values():
        t0 = _utc_ms(o["bar"])
        for name, hrs in HORIZONS.items():
            o[f"r_{name}"] = fwd(o["symbol"], o["bar"], hrs) if now_ms > t0 + (hrs + 1) * H + 120_000 else None
    return list(allobs.values())

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["update", "audit"]); ap.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "update":
        r = update(); print(json.dumps(r["oneriler"], ensure_ascii=False, indent=1))
    else:
        obs = audit(); rep = {}
        for src_name, flt in (("canli", lambda o: o["src"] == "canli"), ("bt_v1+v2", lambda o: o["src"].startswith("bt")), ("hepsi", lambda o: True)):
            xs = [o for o in obs if flt(o)]; rep[src_name] = {h: score(xs, h) for h in HORIZONS}
        rep["n_obs"] = len(obs)
        if a.json: json.dump({"rapor": rep, "obs": obs}, open(a.json, "w"), ensure_ascii=False, indent=1)
        for k in ("canli", "bt_v1+v2", "hepsi"):
            for h in HORIZONS:
                print(f"\n== {k} / {h}")
                for ag, s in rep[k][h].items():
                    print(f"{ag:16s} çağrı={s['toplam_cagri']:3d} değ={s['degerlendirilen']:3d} yönlü={s['yonlu']:3d} isabet={s['isabet_%']}% W95={s['wilson95']} nötr={s['notr_%']}% ayı_payı={s['ayi_payi_%']}% sabityön={s['sabit_yon']}:{s['sabit_yon_taban_%']}% ort_ret={s['ort_yonlu_getiri_%']}")
