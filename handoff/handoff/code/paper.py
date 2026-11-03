"""Kâğıt üstünde işlem defteri + hafıza + ajan isabet istatistikleri. Gerçek para / borsa anahtarı YOK.
Dosyalar: outputs/ledger.json (tam), outputs/ledger.csv (tablo), outputs/summary.json (pano için)."""
import os, json, csv, time, re, datetime as dt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get("CA_OUT", "outputs"))
LEDGER = os.path.join(OUT, "ledger.json")
FEE, SLIP = 0.001, 0.0005          # taraf başına %0,1 komisyon + %0,05 kayma
START_EQUITY = 10_000.0
HORIZON_BARS = {"15m": 16, "1h": 24, "4h": 15, "1d": 10}   # pozisyonun en fazla açık kalacağı mum sayısı

def load():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {"equity_start": START_EQUITY, "trades": []}

def save(L):
    os.makedirs(OUT, exist_ok=True); json.dump(L, open(LEDGER, "w"), ensure_ascii=False, indent=2, default=str)
    cols = ["id", "symbol", "interval", "time", "karar", "guven", "entry", "stop", "hedef", "size_usd", "status",
            "exit", "exit_time", "pnl_usd", "ret_%", "exit_reason"]
    with open(os.path.join(OUT, "ledger.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); [w.writerow(t) for t in L["trades"]]

def equity(L):
    return L["equity_start"] + sum(t.get("pnl_usd") or 0 for t in L["trades"] if t["status"] == "closed")

def realized_today(L):
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    return sum(t.get("pnl_usd") or 0 for t in L["trades"] if t["status"] == "closed" and str(t.get("exit_time", ""))[:10] == today)

def stance(text):
    """Bir ajan metninin sonundaki 'EĞİLİM: BOĞA|AYI|NÖTR' etiketini oku (yoksa None)."""
    m = re.search(r"E[ĞG][İI]L[İI]M\s*[:：]\s*\**\s*(BO[ĞG]A|AYI|N[ÖO]TR)", text or "", re.I)
    if not m: return None
    v = m.group(1).upper(); return "BULL" if v.startswith("BO") else "BEAR" if v.startswith("AY") else "NEUTRAL"

def record(L, symbol, interval, when, decision, entry, stop, hedef, size_usd, stances, blocked=None):
    t = {"id": f"{symbol}-{interval}-{when}", "symbol": symbol, "interval": interval, "time": str(when),
         "karar": decision.get("karar"), "guven": decision.get("guven"), "entry": entry, "stop": stop, "hedef": hedef,
         "size_usd": size_usd, "stances": stances, "status": "open" if (decision.get("karar") == "BUY" and size_usd and not blocked) else "no_trade",
         "blocked": blocked, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    L["trades"] = [x for x in L["trades"] if x["id"] != t["id"]] + [t]   # aynı mum için tekrar yazma
    return t

def update(L, df_by_key):
    """Açık pozisyonları mumlarla güncelle: stop/hedef dokunursa veya ufuk dolarsa kapat. Kayıtları da sonuçlandır."""
    for t in L["trades"]:
        df = df_by_key.get((t["symbol"], t["interval"]))
        if df is None: continue
        dates = [str(d) for d in df["date"]]
        if t["time"] not in dates: continue
        i0 = dates.index(t["time"]); hz = HORIZON_BARS.get(t["interval"].replace("mtf-", ""), 10)
        fut = df.iloc[i0 + 1:i0 + 1 + hz]
        if len(fut) >= hz or (t["status"] == "open" and len(fut)):
            # sonuç (ileri getiri) — ajan isabeti için, işlem açılmasa bile
            if len(fut) >= hz: t["fwd_ret_%"] = round((fut.close.iloc[-1] / t["entry"] - 1) * 100, 3)
        if t["status"] != "open": continue
        for _, r in fut.iterrows():
            if t.get("stop") and r.low <= t["stop"]: _close(t, t["stop"], r.date, "stop"); break
            if t.get("hedef") and r.high >= t["hedef"]: _close(t, t["hedef"], r.date, "hedef"); break
        else:
            if len(fut) >= hz: _close(t, fut.close.iloc[-1], fut.date.iloc[-1], "süre")
            elif len(fut): t["mtm_ret_%"] = round((fut.close.iloc[-1] * (1 - FEE - SLIP) / (t["entry"] * (1 + FEE + SLIP)) - 1) * 100, 3)
    return L

def _close(t, px, when, why):
    buy = t["entry"] * (1 + FEE + SLIP); sell = px * (1 - FEE - SLIP); r = sell / buy - 1
    t.update(status="closed", exit=px, exit_time=str(when), exit_reason=why, **{"ret_%": round(r * 100, 3)},
             pnl_usd=round(t["size_usd"] * r, 2))

def agent_stats(L, symbol=None):
    """Ajan isabeti: BULL ve ileri getiri>0, BEAR ve <0 ise doğru. NEUTRAL sayılmaz. Hakem: BUY>0 / SELL<0."""
    st = {}
    for t in L["trades"]:
        if symbol and t["symbol"] != symbol: continue
        r = t.get("fwd_ret_%")
        if r is None: continue
        items = dict(t.get("stances") or {}); items["hakem"] = {"BUY": "BULL", "SELL": "BEAR"}.get(t.get("karar"), "NEUTRAL")
        for a, s in items.items():
            if s not in ("BULL", "BEAR"): continue
            d = st.setdefault(a, {"n": 0, "dogru": 0}); d["n"] += 1; d["dogru"] += int((s == "BULL") == (r > 0))
    for d in st.values(): d["isabet_%"] = round(100 * d["dogru"] / d["n"], 1)
    return st

def memory_text(L, symbol, interval, k=5):
    past = [t for t in L["trades"] if t["symbol"] == symbol and t["interval"] == interval][-k:]
    if not past: return "Geçmiş karar yok (hafıza boş)."
    lines = [f"- {t['time']}: {t['karar']} (güven {t['guven']}) giriş {t['entry']:,.2f} -> "
             + (f"ileri getiri {t['fwd_ret_%']:+.2f}%" if t.get("fwd_ret_%") is not None else "sonuç henüz yok")
             + (f", işlem {t['exit_reason']} {t['ret_%']:+.2f}%" if t.get("status") == "closed" else "") for t in past]
    s = agent_stats(L, symbol)
    if s: lines.append("Ajan isabetleri: " + ", ".join(f"{a} %{d['isabet_%']} (n={d['n']})" for a, d in s.items()))
    return "\n".join(lines)

def summary(L, latest):
    eq = equity(L)
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "paper": {"equity_start": L["equity_start"], "equity": round(eq, 2),
            "pnl_usd": round(eq - L["equity_start"], 2), "open": [t for t in L["trades"] if t["status"] == "open"],
            "closed_n": sum(t["status"] == "closed" for t in L["trades"])},
            "latest": latest, "agent_stats": agent_stats(L), "fees": {"fee_per_side": FEE, "slippage_per_side": SLIP}}
