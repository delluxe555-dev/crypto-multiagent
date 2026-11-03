"""Başabaş (breakeven) stop kuralı yeniden-oynatma testi. LLM çağrısı YOK; canlı ledger/config/state'e YAZMAZ (yalnızca okur).
Çıktı: outputs/be_sim.json + outputs/be_sim.md. 1m mum önbelleği: /workspace/levsim_cache (canlı önbellek değil).
Kurallar (canlı trader ile aynı): stop 2xATR, hedef 3xATR, 24 sa süre, ücret %0,1/taraf + kayma %0,05/taraf, risk %1.
Belirsiz mum (aynı 1m mumda hem stop hem hedef/tetik): stop kazanır. Tetik mumunda yeni stop bir SONRAKİ mumdan itibaren geçerli.
Kullanım: .venv/bin/python be_sim.py [--days 14] [--long-days 45]"""
import os, sys, json, time, datetime as dt, argparse, random
import numpy as np, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leverage_sim as LS
HERE = LS.HERE; FEE, SLIP, RISK = LS.FEE, LS.SLIP, LS.RISK; HOLD = 1440   # dakika
SPOT = "https://data-api.binance.vision/api/v3/klines"

# varyant: ad -> dict(stages=[(tetik, yeni_stop)]) ; tetik ve yeni_stop: ('frac', f) hedefe giden yolun oranı | ('atr', k) | ('buf', b%) vb.
def V(name, trig=None, buf=0.3, trail=None):
    return dict(name=name, trig=trig, buf=buf, trail=trail)
VARIANTS = [V("taban (başabaş yok)")]
for kind, vals in (("frac", (0.33, 0.5, 0.67)), ("atr", (1.0,))):
    for t in vals:
        for b in (0.3, 0.5):
            VARIANTS.append(V(f"tetik {t}{'×ATR' if kind=='atr' else ''} tampon %{b}", (kind, t), b))
for b in (0.3, 0.5):
    VARIANTS.append(V(f"0.5 + iz {{0.75→0.25}} tampon %{b}", ("frac", 0.5), b, (0.75, 0.25)))
    VARIANTS.append(V(f"0.33 + iz {{0.75→0.25}} tampon %{b}", ("frac", 0.33), b, (0.75, 0.25)))

def stages(v, sg, entry, stop0, tgt, atr):
    """[(tetik_fiyat, yeni_stop_fiyat, tür)]"""
    D = abs(tgt - entry); out = []
    if v["trig"]:
        k, t = v["trig"]; lvl = entry + sg*(t*D if k == "frac" else t*atr)
        out.append((lvl, entry*(1 + sg*v["buf"]/100), "be"))
    if v["trail"]:
        f, lock = v["trail"]; out.append((entry + sg*f*D, entry + sg*lock*D, "kilit"))
    return out

def run_trade(v, side, entry, stop0, tgt, atr, O, H, Lo, C, end_i=None):
    """Dönüş: (neden, çıkış_fiyatı_ham, dakika_idx, hedefe_ulaştı_mı(taban için), be_idx)"""
    sg = 1 if side == "LONG" else -1; n = len(H) if end_i is None else min(end_i, len(H))
    if n == 0: return ("açık", entry, 0, None)
    st = np.full(n, stop0, dtype=float); kind = np.zeros(n, dtype=int)   # 0 = ilk stop, 1 = be, 2 = kilit
    be_i = None
    for lvl_t, lvl_s, k in stages(v, sg, entry, stop0, tgt, atr):
        hit = np.nonzero((H[:n] >= lvl_t) if sg > 0 else (Lo[:n] <= lvl_t))[0]
        if len(hit) and hit[0] + 1 < n:
            a = hit[0] + 1; seg = st[a:]
            better = (lvl_s > seg) if sg > 0 else (lvl_s < seg)
            seg[better] = lvl_s; kind[a:][better] = 1 if k == "be" else 2
            if k == "be" and be_i is None: be_i = hit[0]
    hs = np.nonzero((Lo[:n] <= st) if sg > 0 else (H[:n] >= st))[0]; ht = np.nonzero((H[:n] >= tgt) if sg > 0 else (Lo[:n] <= tgt))[0]
    i_s = hs[0] if len(hs) else 10**9; i_t = ht[0] if len(ht) else 10**9
    if i_s < 10**9 and i_s <= i_t:
        gap = min(st[i_s], O[i_s]) if sg > 0 else max(st[i_s], O[i_s])
        why = ["stop", "başabaş", "kilit"][kind[i_s]]
        return (why, gap, int(i_s), be_i)
    if i_t < 10**9: return ("hedef", tgt, int(i_t), be_i)
    return ("süre", C[n-1], n-1, be_i)

def R_of(side, entry, stop0, exit_raw, risk_unit=None):
    sg = 1 if side == "LONG" else -1
    xf = exit_raw*(1 - sg*SLIP); per = abs(entry - stop0) + entry*2*(FEE + SLIP)
    return (sg*(xf - entry) - entry*FEE - xf*FEE)/per

def get_k(sym, a_ms, b_ms):
    K = np.array(LS.klines_1m(sym, int(a_ms), int(b_ms)))
    return K[:, 0], K[:, 1], K[:, 2], K[:, 3], K[:, 4]

def hourly(sym, start_ms):
    h1 = []; t = start_ms
    while t < LS.NOW_MS:
        for _ in range(5):
            try: r = requests.get(SPOT, params={"symbol": sym, "interval": "1h", "startTime": int(t), "limit": 1000}, timeout=20).json(); break
            except Exception: time.sleep(2)
        if not r: break
        h1 += r; t = r[-1][0] + 3600000
        if len(r) < 1000: break
    return np.array([[x[0], float(x[2]), float(x[3]), float(x[4])] for x in h1])

def make_grid(symbols, days, every_h=2):
    end = LS.NOW_MS - 24*3600000 - 3600000; start = end - days*86400000; T = []
    for s in symbols:
        Hh = hourly(s, start - 30*3600000)
        tr = np.maximum(Hh[1:, 1] - Hh[1:, 2], np.maximum(abs(Hh[1:, 1] - Hh[:-1, 3]), abs(Hh[1:, 2] - Hh[:-1, 3])))
        atr = np.full(len(Hh), np.nan); atr[14:] = np.convolve(tr, np.ones(14)/14, "valid")
        for i in range(15, len(Hh)):
            tc = Hh[i, 0] + 3600000
            if tc < start or tc > end or ((tc - start)//3600000) % every_h: continue
            a = atr[i]; c = Hh[i, 3]
            m4 = c - Hh[i-4, 3]; m24 = c - Hh[i-24, 3] if i >= 24 else 0.0
            for side in ("LONG", "SHORT"):
                sg = 1 if side == "LONG" else -1; fill = c*(1 + sg*SLIP)
                T.append(dict(src="ızgara", id=f"{s}-{side}-{int(tc)}", symbol=s, side=side, entry_ms=int(tc), entry=fill, stop=fill - sg*2*a, target=fill + sg*3*a, atr=a, trend=bool(m4*sg > 0 and m24*sg > 0)))
    return T

def eval_trades(trades, variants, end_ms=None):
    """Her işlem × varyant için sonuç satırı."""
    KC = {}
    for s in {t["symbol"] for t in trades}:
        a = min(t["entry_ms"] for t in trades if t["symbol"] == s); KC[s] = get_k(s, a, LS.NOW_MS)
    res = {v["name"]: [] for v in variants}
    for t in trades:
        ot, O, H, Lo, C = KC[t["symbol"]]; i0 = int(np.searchsorted(ot, t["entry_ms"])); i1 = int(np.searchsorted(ot, t["entry_ms"] + HOLD*60000))
        complete = (i1 - i0) >= HOLD - 2 and ot[-1] >= t["entry_ms"] + HOLD*60000
        sl = slice(i0, min(i1, len(ot)))
        args = (O[sl], H[sl], Lo[sl], C[sl])
        base_why = None
        for v in variants:
            why, px, idx, be_i = run_trade(v, t["side"], t["entry"], t["stop"], t["target"], t["atr"], *args)
            if v["name"].startswith("taban"): base_why = why
            if not complete and why == "süre": why = "açık"
            res[v["name"]].append(dict(id=t["id"], symbol=t["symbol"], side=t["side"], entry_ms=t["entry_ms"], exit_ms=int(ot[i0 + idx]) + 60000, why=why, R=R_of(t["side"], t["entry"], t["stop"], px),
                                       base=base_why, be_i=None if be_i is None else int(be_i), src=t["src"], trend=t.get("trend"), stop_pct=abs(t["entry"]/t["stop"]-1)*100))
    return res

def portfolio(rows, start_eq=1000.0, max_pos=20, risk=RISK, notional_cap=0.8):
    """Sıralı bileşik: giriş anındaki gerçekleşmiş özsermayenin %1'i risk; aynı sembolde tek pozisyon. Dönüş: (bakiye, mdd%, işlem sayısı)."""
    rows = sorted(rows, key=lambda r: r["entry_ms"]); eq = start_eq; openp = []; peak = eq; mdd = 0.0; n = 0; curve_pts = []
    for r in rows:
        for o in sorted([o for o in openp if o["exit_ms"] <= r["entry_ms"]], key=lambda o: o["exit_ms"]):
            eq += o["pnl"]; openp.remove(o); peak = max(peak, eq); mdd = max(mdd, 1 - eq/peak)
        if any(o["symbol"] == r["symbol"] for o in openp) or len(openp) >= max_pos: continue
        ru = eq*risk; sd = r["stop_pct"]/100 + 2*(FEE + SLIP); notion = min(ru/sd, eq*notional_cap); pnl = r["R"]*sd*notion   # R*per_unit*qty
        if r["why"] == "açık": pass
        openp.append(dict(symbol=r["symbol"], exit_ms=r["exit_ms"], pnl=pnl)); n += 1
    for o in sorted(openp, key=lambda o: o["exit_ms"]):
        eq += o["pnl"]; peak = max(peak, eq); mdd = max(mdd, 1 - eq/peak)
    return eq, mdd*100, n

def summarize(res, trades_by_id, variants, tag, pf_fn=None, incl_open=False):
    out = []; base = {r["id"]: r for r in res[variants[0]["name"]]}
    for v in variants:
        rows = [r for r in res[v["name"]] if incl_open or r["why"] != "açık"]; n = len(rows)
        if not n: continue
        R = np.array([r["R"] for r in rows]); be = [r for r in rows if r["why"] in ("başabaş", "kilit")]
        missed = [r for r in be if base[r["id"]]["why"] == "hedef"]
        saved = [r for r in be if base[r["id"]]["why"] == "stop"]
        mR = sum(base[r["id"]]["R"] - r["R"] for r in missed); sR = sum(r["R"] - base[r["id"]]["R"] for r in saved)
        pf = pf_fn(res[v["name"]]) if pf_fn else None
        dR = np.array([r["R"] - base[r["id"]]["R"] for r in rows]); se = float(dR.std(ddof=1)/np.sqrt(n)) if n > 1 else 0.0
        out.append(dict(varyant=v["name"], n=n, d_ort_R=round(float(dR.mean()), 4), d_se=round(se, 4), kazanma_pct=round(100*np.mean(R > 0), 1), basabas_pay_pct=round(100*len(be)/n, 1), hedef_pct=round(100*np.mean([r["why"] == "hedef" for r in rows]), 1),
                        stop_pct=round(100*np.mean([r["why"] == "stop" for r in rows]), 1), ort_R=round(float(R.mean()), 3), beklenti_usd_per_islem=round(float(R.mean())*10, 2),
                        kacan_hedef_n=len(missed), kacan_R_toplam=round(mR, 1), kurtarilan_stop_n=len(saved), kurtarilan_R_toplam=round(sR, 1), net_R_fark_taban=round(float(R.sum() - sum(base[r["id"]]["R"] for r in rows)), 1),
                        bakiye=None if pf is None else round(pf[0], 1), mdd_pct=None if pf is None else round(pf[1], 1), pf_islem=None if pf is None else pf[2]))
    return out

def grid_pf(rows_all, seeds=20):
    """Izgara: her seed'de sembol×giriş başına rastgele tek yön seç (ajan gibi), sıralı bileşik; ortalama bakiye / en kötü mdd."""
    by = {}
    for r in rows_all: by.setdefault((r["symbol"], r["entry_ms"]), {})[r["side"]] = r
    bal = []; dd = []; ns = []
    for sd in range(seeds):
        rnd = random.Random(sd); pick = [rnd.choice(list(d.values())) for d in by.values()]
        e, m, n = portfolio([p for p in pick if p["why"] != "açık"]); bal.append(e); dd.append(m); ns.append(n)
    return float(np.mean(bal)), float(np.mean(dd)), float(np.mean(ns))

def live_trades():
    L = json.load(open(f"{HERE}/outputs/trader/ledger.json")); T = []
    for p in L["positions"]:
        t = dt.datetime.fromisoformat(p["opened_at"]).timestamp()*1000
        T.append(dict(src="canlı", id=p["id"], symbol=p["symbol"], side=p["side"], entry_ms=int(t//60000*60000 + 60000), entry=p["entry"], stop=p["stop"], target=p["target"], atr=p["atr"]))
    return T

def sol_trades():
    seen = set(); T = []
    for fn in ("backtest_1h_SOLUSDT.json", "backtest_1h_SOLUSDT_v2.json", "backtest_1h_SOLUSDT_v3.json"):
        b = json.load(open(f"{HERE}/outputs/{fn}"))
        for r in b["rows"]:
            if r.get("pnl_usd") is None: continue
            ot = dt.datetime.strptime(r["mum_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp()*1000
            key = (r["mum_utc"], r["yon"])
            if key in seen: continue
            seen.add(key); T.append(dict(src="SOL-backtest", id=f"SOL-{r['mum_utc']}-{r['yon']}", symbol="SOLUSDT", side=r["yon"], entry_ms=int(ot + 3600000), entry=r["giris"], stop=r["stop"], target=r["hedef"], atr=r["atr"]))
    return T

def table(rows, cols):
    h = "| " + " | ".join(cols) + " |\n|" + "---|"*len(cols) + "\n"
    return h + "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=14); ap.add_argument("--long-days", type=int, default=45); a = ap.parse_args()
    SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "WLDUSDT", "TIAUSDT", "ONDOUSDT")
    out = {"olusturuldu": dt.datetime.now(LS.IST).isoformat(timespec="seconds")}; md = ["# Başabaş stop yeniden-oynatma testi\n"]
    cols = ["varyant", "n", "kazanma_pct", "basabas_pay_pct", "hedef_pct", "stop_pct", "ort_R", "beklenti_usd_per_islem", "kacan_hedef_n", "kurtarilan_stop_n", "net_R_fark_taban", "d_ort_R", "d_se"]
    for tag, tr in (("canlı defter (7 işlem: 3 kapanmış + 4 açık, açıklar son fiyatla)", live_trades()), ("SOL backtest (4 benzersiz işlem)", sol_trades())):
        res = eval_trades(tr, VARIANTS); s = summarize(res, None, VARIANTS, tag, lambda rows: portfolio(rows), incl_open=True); out[tag] = dict(ozet=s)
        md += [f"\n## {tag}\n", table(s, cols + ["bakiye", "mdd_pct"])]
    tr = make_grid(SYMS, a.long_days); res = eval_trades(tr, VARIANTS); end = max(t["entry_ms"] for t in tr); t14 = end - a.days*86400000
    sub = lambda f: {k: [r for r in v if f(r)] for k, v in res.items()}
    views = [(f"ızgara SON {a.days} GÜN", sub(lambda r: r["entry_ms"] > t14)), (f"ızgara {a.long_days} GÜN (hepsi)", res)]
    span = (end - min(t["entry_ms"] for t in tr))/3
    t0 = min(t["entry_ms"] for t in tr)
    for k in range(3): views.append((f"ızgara {a.long_days} gün — dilim {k+1}/3", sub(lambda r, k=k: t0 + k*span <= r["entry_ms"] < t0 + (k+1)*span + (1 if k == 2 else 0))))
    views.append((f"ızgara {a.long_days} gün — yalnız TREND YÖNÜNDE girişler (4s ve 24s momentum ile uyumlu; ajan MTF filtresi vekili)", sub(lambda r: r["trend"])))
    views.append((f"ızgara {a.long_days} gün — yalnız TERS yön girişler", sub(lambda r: not r["trend"])))
    for tag, rr in views:
        s = summarize(rr, None, VARIANTS, tag, grid_pf); out[tag] = dict(ozet=s)
        md += [f"\n## {tag} ({len(rr[VARIANTS[0]['name']])} işlem)\n", table(s, cols + ["bakiye", "mdd_pct"])]
    json.dump(out, open(f"{HERE}/outputs/be_sim.json", "w"), ensure_ascii=False, indent=1, default=str)
    open(f"{HERE}/outputs/be_sim.md", "w").write("".join(md)); print("".join(md))
