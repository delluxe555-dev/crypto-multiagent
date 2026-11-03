"""Sürekli çalışan KÂĞIT işlem botu (gerçek emir / borsa anahtarı YOK).
Komutlar:
  trader.py cycle [--top N]   saatlik: aşama-1 tarama + MTF + tam tartışma, koşullar sağlanırsa sanal pozisyon aç
  trader.py monitor           LLM'siz: açık pozisyonları canlı fiyatla (Binance spot data-api) kontrol et, stop/hedef/süre kapat
  trader.py summary [--send]  sabah özeti (Telegram'a --send ile)
  trader.py daemon            zamanlayıcı döngü (paper.sh start bunu çalıştırır)
Tek hedef (kısmi kâr alma yok). Başabaş kuralı: hedefe giden yolun be_trigger_frac kadarı görülünce stop girişe (+be_buffer_pct tampon) çekilir. Long ve (config allow_short ise) sanal short."""
import os, sys, json, time, fcntl, argparse, subprocess, traceback, datetime as dt
from contextlib import contextmanager
import requests
import tgfmt, lessons

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
CFG = json.load(open(os.path.join(HERE, "config.json"))); T = CFG["trader"]
TEST_DIR = os.environ.get("CA_TRADER_DIR")   # yalnızca testler: ayrı defter/durum/log klasörü (canlıya dokunmaz)
TD = TEST_DIR or os.path.join(HERE, "outputs", "trader"); LOGD = os.environ.get("CA_LOGDIR") or (os.path.join(TEST_DIR, "logs") if TEST_DIR else os.path.join(HERE, "logs")); os.makedirs(TD, exist_ok=True); os.makedirs(LOGD, exist_ok=True)
LEDGER, STATE, LOCK = os.path.join(TD, "ledger.json"), os.path.join(TD, "state.json"), os.path.join(TD, ".lock")
SPOT = "https://data-api.binance.vision/api/v3"
IST = dt.timezone(dt.timedelta(hours=3))   # Europe/Istanbul (sabit UTC+3)

def now(): return dt.datetime.now(IST)
def iso(t=None): return (t or now()).strftime("%Y-%m-%dT%H:%M:%S%z")
def log(*a):
    line = f"[{now():%Y-%m-%d %H:%M:%S}] " + " ".join(str(x) for x in a)
    print(line, flush=True); open(os.path.join(LOGD, "trader.log"), "a").write(line + "\n")

@contextmanager
def locked():
    f = open(LOCK, "w"); fcntl.flock(f, fcntl.LOCK_EX)
    try: yield
    finally: fcntl.flock(f, fcntl.LOCK_UN); f.close()

def jload(p, d): return json.load(open(p)) if os.path.exists(p) else d
def jsave(p, o):
    tmp = p + ".tmp"; json.dump(o, open(tmp, "w"), ensure_ascii=False, indent=2, default=str); os.replace(tmp, p)
def load_ledger(): return jload(LEDGER, {"equity_start": T["start_equity"], "created_at": iso(), "positions": []})
def load_state(): return jload(STATE, {})

# ---------- Telegram ----------
def _tg_env():
    env = {}
    try:
        for ln in open("/home/box/.secrets/telegram.env"):
            if "=" in ln: k, v = ln.strip().split("=", 1); env[k] = v.strip().strip('"').strip("'")
    except Exception: pass
    return env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")

def tg(text, html=True):
    if not T.get("telegram", True) or os.environ.get("CA_NO_TG") == "1": log("TG (kapalı):", text.replace("\n", " | ")); return False
    tok, chat = _tg_env()
    if not tok or not chat: log("TG: token/chat yok"); return False
    for i in range(3):
        try:
            body = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
            if html: body["parse_mode"] = "HTML"
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json=body, timeout=15)
            if r.status_code == 400 and html:   # HTML ayrıştırma hatası -> etiketsiz düz metin
                log("TG HTML hatası, düz metin:", r.text[:150]); html = False; text = __import__("re").sub(r"</?[bi]>", "", text)
                import html as _h; text = _h.unescape(text); continue
            if r.ok: log("TG gönderildi:", text.splitlines()[0][:80]); open(os.path.join(LOGD, "telegram_sent.log"), "a").write(f"--- {iso()}\n{text}\n"); return True
            log("TG hata", r.status_code, r.text[:200])
            if r.status_code == 429: time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)))
            else: break
        except Exception as e: log("TG istisna", e); time.sleep(3)
    return False

# ---------- piyasa ----------
def price(sym):
    return float(requests.get(f"{SPOT}/ticker/price", params={"symbol": sym}, timeout=10).json()["price"])

def prices(syms):
    if not syms: return {}
    r = requests.get(f"{SPOT}/ticker/price", params={"symbols": json.dumps(sorted(set(syms)), separators=(",", ":"))}, timeout=10).json()
    return {x["symbol"]: float(x["price"]) for x in r}

def excursion(sym, since_ms):
    """Açılıştan beri en yüksek/en düşük (5m mumlar; MFE/MAE için). Yalnızca hi_seen'i olmayan eski pozisyonları doldurur."""
    k = requests.get(f"{SPOT}/klines", params={"symbol": sym, "interval": "5m", "startTime": int(since_ms), "limit": 1000}, timeout=10).json()
    if not k: return None, None
    return max(float(x[2]) for x in k), min(float(x[3]) for x in k)

def minute_candles(sym, since_ms):
    """Son kontrolden beri 1m mumlar: [(açılış_ms, yüksek, düşük)]."""
    k = requests.get(f"{SPOT}/klines", params={"symbol": sym, "interval": "1m", "startTime": int(since_ms), "limit": 1000}, timeout=10).json()
    return [(int(x[0]), float(x[2]), float(x[3])) for x in k]

def minute_range(sym, since_ms):
    """Son kontrolden beri 1m mumların en yüksek/en düşüğü (fitil kaçırmamak için)."""
    k = minute_candles(sym, since_ms)
    if not k: return None, None
    return max(x[1] for x in k), min(x[2] for x in k)

# ---------- başabaş (breakeven) stop ----------
def be_cfg():
    """(açık mı, tetik oranı, tampon %) — config.json her kontrolde taze okunur (yeniden başlatmadan açılıp kapanır)."""
    try: c = json.load(open(os.path.join(HERE, "config.json")))["trader"]
    except Exception: c = T
    return bool(c.get("be_enabled", False)), float(c.get("be_trigger_frac", 0.67)), float(c.get("be_buffer_pct", 0.3))

def be_progress(p, hi, lo):
    """Girişten hedefe giden yolun, görülen en iyi fiyata göre tamamlanan oranı (0..1+)."""
    D = abs(p["target"] - p["entry"])
    return 0.0 if D <= 0 else ((hi - p["entry"]) if p["side"] == "LONG" else (p["entry"] - lo)) / D

def be_level(p, buf_pct):
    """Başabaş stop: giriş ± tampon (ücret+kayma ≈ %0,25 gidiş-dönüş çıkış maliyetini karşılar; pozitif tarafa)."""
    return p["entry"] * (1 + (1 if p["side"] == "LONG" else -1) * buf_pct / 100)

PENDING_BE = []
def maybe_move_be(p, last, t_ms):
    """Tetik geçildiyse stop'u başabaşa çeker (yalnızca bir kez, yalnızca stop'u iyileştirecekse). Dönüş: True/False."""
    on, frac, buf = be_cfg()
    if not on or p.get("be_moved_at"): return False
    prog = be_progress(p, p["hi_seen"], p["lo_seen"])
    if prog < frac: return False
    new = be_level(p, buf); long = p["side"] == "LONG"
    if (new <= p["stop"]) if long else (new >= p["stop"]): return False        # zaten daha iyi/aynı stop
    p["stop_orig"] = p.get("stop_orig", p["stop"]); old = p["stop"]; p["stop"] = new
    p["be_moved_at"] = iso(); p["be_progress"] = round(prog, 3); p["be_trigger_frac"] = frac; p["be_buffer_pct"] = buf
    p["be_from_ms"] = (t_ms // 60000 + 1) * 60000     # yeni stop yalnızca bir SONRAKİ 1m mumdan itibaren geçerli (tetik mumunda sıra bilinmez)
    PENDING_BE.append((dict(p), old, last)); log("BAŞABAŞ", p["symbol"], p["side"], "stop", fmt(old), "->", fmt(new), f"ilerleme {prog:.2f}")
    return True

# ---------- muhasebe ----------
def equity(L): return L["equity_start"] + sum(p["pnl_usd"] for p in L["positions"] if p["status"] == "closed")
def realized_since(L, t0): return sum(p["pnl_usd"] for p in L["positions"] if p["status"] == "closed" and p["closed_at"] >= iso(t0))
def day_start(): n = now(); return n.replace(hour=0, minute=0, second=0, microsecond=0)
def opens(L): return [p for p in L["positions"] if p["status"] == "open"]
def fmt(x): return f"{x:,.2f}" if x >= 100 else f"{x:,.4f}" if x >= 1 else f"{x:.6g}"

def open_position(L, sym, side, atr, conf, reason, stances, providers, bar, bullets=None, ctx=None):
    fee, slip = T["fee"], T["slippage"]
    ref = price(sym); fill = ref * (1 + slip) if side == "LONG" else ref * (1 - slip)
    sgn = 1 if side == "LONG" else -1
    stop = fill - sgn * T["atr_stop_mult"] * atr; target = fill + sgn * T["atr_target_mult"] * atr
    eq = equity(L); risk = eq * T["risk_per_trade"]
    # kaldıraç (sanal): risk sabit %1; büyüklük stop mesafesinden; kaldıraç yalnızca teminatı küçültür, üst sınır güvene bağlı (asla > max_leverage)
    cap = next((lv for th, lv in sorted(T["leverage_tiers"], reverse=True) if conf >= th), 1); cap = max(1, min(cap, T["max_leverage"], 5))
    free = eq - sum(p["margin"] for p in opens(L))                  # boşta teminat
    max_margin = max(0.0, min(eq * T.get("max_margin_frac", T["max_pos_frac"]), free))
    per_unit = abs(fill - stop) + fill * 2 * (fee + slip)            # stop + iki taraf ücret/kayma dahil risk %1'i aşmasın
    notional = min(risk / per_unit * fill, max_margin * cap)
    lev = 1
    while lev < cap and notional / lev > max_margin: lev += 1
    margin = notional / lev; qty = notional / fill
    if notional < T.get("min_notional_usd", 50): log("AÇILMADI", sym, f"büyüklük ${notional:,.2f} < borsa min ${T.get('min_notional_usd')} veya yetersiz teminat (boşta ${free:,.0f})"); return None
    liq = fill * (1 - 1 / lev) if side == "LONG" else fill * (1 + 1 / lev)   # yaklaşık (bakım teminatı hariç); lev=1 long'da 0
    p = {"id": f"{sym}-{bar}", "symbol": sym, "side": side, "signal_bar_utc": bar, "opened_at": iso(), "ref_price": ref, "entry": fill,
         "stop": stop, "target": target, "atr": atr, "qty": qty, "notional": notional, "risk_usd": qty * abs(fill - stop) + notional * fee * 2,
         "fee_open": notional * fee, "leverage": lev, "leverage_cap": cap, "margin": margin, "liq_approx": liq if lev > 1 else None, "confidence": conf, "reason": reason, "bullets": bullets, "stances": stances, "providers": providers, "status": "open", "entry_ctx": ctx,
         "hi_seen": fill, "lo_seen": fill,
         "last_check_ms": int(time.time() * 1000)}
    try:
        import liq; p["liq_near"] = liq.nearest(sym, T["interval"])   # tahmini, yalnızca bilgi amaçlı
    except Exception: p["liq_near"] = None
    L["positions"].append(p)
    tg(tgfmt.open_msg(p, equity(L)))
    log("AÇ", sym, side, fill, stop, target, round(notional, 2)); return p

def close_position(L, p, px_raw, why):
    fee, slip = T["fee"], T["slippage"]; long = p["side"] == "LONG"
    fill = px_raw * (1 - slip) if long else px_raw * (1 + slip)
    gross = p["qty"] * ((fill - p["entry"]) if long else (p["entry"] - fill))
    fee_close = p["qty"] * fill * fee; pnl = gross - p["fee_open"] - fee_close
    p.update(status="closed", exit=fill, exit_raw=px_raw, exit_reason=why, closed_at=iso(), fee_close=fee_close, pnl_usd=pnl,
             pnl_pct=100 * pnl / p["notional"], roe_pct=100 * pnl / p.get("margin", p["notional"]), move="UP" if px_raw > p["ref_price"] else "DOWN")
    eq = equity(L)
    try: p["lesson"] = lessons.on_close(p)      # ağsız: yapılandırılmış kayıt + kural tabanlı ders (lessons.json)
    except Exception as e: log("ders kaydı hatası", e)
    PENDING_CLOSE.append((dict(p), eq))        # Telegram: kilit bırakıldıktan sonra (ders için tek ucuz LLM çağrısı beklenebilir)
    log("KAPAT", p["symbol"], why, fill, round(pnl, 2))

PENDING_CLOSE = []
def flush_closed():
    """Kapanış mesajlarını gönder; her biri için tek ucuz LLM ile ders (≤25 sn bekler, olmazsa kural dersi)."""
    while PENDING_CLOSE:
        p, eq = PENDING_CLOSE.pop(0); lesson = p.get("lesson")
        try: lesson = lessons.finalize(p) or lesson
        except Exception as e: log("ders LLM hatası", e)
        tg(tgfmt.close_msg(p, eq, lesson))

# ---------- izleyici ----------
def monitor():
    try: return _monitor()
    finally: flush_be(); flush_closed()

def flush_be():
    """Stop-çekme bildirimleri (kilit bırakıldıktan sonra)."""
    while PENDING_BE:
        p, old, last = PENDING_BE.pop(0)
        try: tg(tgfmt.be_msg(p, old, last, equity(load_ledger())))
        except Exception as e: log("başabaş mesajı hatası", e)

def _monitor():
    with locked():
        L = load_ledger(); op = opens(L)
        if not op: write_summary(L); return 0
        try: px = prices([p["symbol"] for p in op])
        except Exception as e: log("monitor fiyat hatası", e); return 0
        n = 0; t_ms = int(time.time() * 1000)
        for p in op:
            s = p["symbol"]; last = px.get(s)
            if last is None: continue
            try: cs = minute_candles(s, p["last_check_ms"])
            except Exception: cs = []
            hi = max([c[1] for c in cs] + [last]); lo = min([c[2] for c in cs] + [last]); long = p["side"] == "LONG"
            hi_s, lo_s = hi, lo      # stop kontrolü için aralık: başabaşa yeni çekildiyse yalnızca çekme anından sonraki mumlar
            if p.get("be_from_ms") and p["be_from_ms"] > p["last_check_ms"]:
                cs2 = [c for c in cs if c[0] >= p["be_from_ms"]]
                hi_s = max([c[1] for c in cs2] + [last]); lo_s = min([c[2] for c in cs2] + [last])
            if p.get("hi_seen") is None:   # MFE/MAE: eski pozisyonları açılıştan itibaren (5m mumlarla) doldur
                try:
                    h0, l0 = excursion(s, dt.datetime.fromisoformat(p["opened_at"]).timestamp() * 1000)
                    p["hi_seen"], p["lo_seen"] = max(h0 or p["entry"], p["entry"]), min(l0 or p["entry"], p["entry"])
                except Exception: p["hi_seen"], p["lo_seen"] = p["entry"], p["entry"]
            p["hi_seen"] = max(p["hi_seen"], hi); p["lo_seen"] = min(p["lo_seen"], lo)
            hit_stop = lo_s <= p["stop"] if long else hi_s >= p["stop"]
            hit_tgt = hi >= p["target"] if long else lo <= p["target"]
            if hit_stop:   # ikisi birden olduysa ihtiyatlı: stop
                close_position(L, p, min(p["stop"], last) if long else max(p["stop"], last), "başabaş" if p.get("be_moved_at") else "stop"); n += 1
            elif hit_tgt:
                close_position(L, p, p["target"], "hedef"); n += 1
            elif now() - dt.datetime.fromisoformat(p["opened_at"]) >= dt.timedelta(hours=T["max_hold_hours"]):
                close_position(L, p, last, f"süre doldu ({T['max_hold_hours']}s)"); n += 1
            else:
                p["last_check_ms"] = t_ms; p["last_price"] = last
                maybe_move_be(p, last, t_ms)
                p["unrealized_usd"] = p["qty"] * ((last - p["entry"]) if long else (p["entry"] - last)) - p["fee_open"]
        jsave(LEDGER, L); write_summary(L)
    return n

# ---------- saatlik döngü ----------
def cycle(top=None):
    import scan, run, llm
    st = load_state(); day = dt.datetime.utcnow().strftime("%Y-%m-%d")
    if st.get("llm_day") != day: st.update(llm_day=day, llm_calls=0)
    budget = T["daily_llm_budget"] - st["llm_calls"]
    with locked():
        L = load_ledger()
        if "btc_start" not in L: L["btc_start"] = price("BTCUSDT"); jsave(LEDGER, L)
    if budget < T["min_budget_per_coin"]:
        log(f"döngü atlandı: günlük LLM bütçesi bitti ({st['llm_calls']}/{T['daily_llm_budget']})"); return
    res = scan.main(argparse.Namespace(interval=T["interval"], top=top or T["top_n"], majors=False, no_llm=True))
    targets = res["shortlist"] + [m for m in T["majors"] if m not in res["shortlist"]]
    log("aday:", targets); report = {"time": iso(), "targets": targets, "results": {}}
    n0 = llm.CALLS["n"]
    for sym in targets:
        with locked():
            L = load_ledger(); held = {p["symbol"] for p in opens(L)}
        if sym in held: report["results"][sym] = "zaten açık pozisyon var"; continue
        if T["daily_llm_budget"] - st["llm_calls"] - (llm.CALLS["n"] - n0) < T["min_budget_per_coin"]:
            report["results"][sym] = "bütçe bitti"; log("bütçe bitti, kalan adaylar atlandı"); break
        try:
            m = run.main_mtf(sym, T["interval"]); k = m["karar"]["karar"]
            r = {"mtf": f"4h={m['trend_4h'].get('trend')} {T['interval']}={m['entry'].get('giris')} hizalı={m['hizali']}"}
            if T["require_mtf"] and not m["hizali"]: report["results"][sym] = r | {"sonuc": "MTF hizasız -> işlem yok"}; continue
            if k == "SELL" and not T["allow_short"]: report["results"][sym] = r | {"sonuc": "short kapalı"}; continue
            o = run.main(sym, T["interval"]); h = o["hakem"]; conf = int(h.get("guven") or 0)
            r |= {"hakem": h.get("karar"), "guven": conf, "gerekce": h.get("gerekce")}
            want = k if T["require_mtf"] else h.get("karar")
            if h.get("karar") not in ("BUY", "SELL") or h.get("karar") != want or conf < T["min_confidence"]:
                report["results"][sym] = r | {"sonuc": "eşik/uyum sağlanmadı -> işlem yok"}; continue
            atr = float(o["extras"].get("atr") or 0) if isinstance(o.get("extras"), dict) else 0
            if not atr:
                import data; atr = float(data.add_indicators(data.klines(sym, T["interval"], 100))["atr14"].iloc[-1])
            with locked():
                L = load_ledger(); eq = equity(L)
                why = None
                if len(opens(L)) >= T["max_concurrent"]: why = f"en fazla {T['max_concurrent']} eşzamanlı pozisyon"
                elif realized_since(L, day_start()) <= -T["daily_loss_limit"] * eq: why = "günlük zarar limiti"
                elif sym in {p["symbol"] for p in opens(L)}: why = "zaten açık"
                if why: report["results"][sym] = r | {"sonuc": f"engellendi: {why}"}; continue
                stances = {"teknik_analist": o.get("teknik_stance") or __import__("paper").stance(o["teknik_analist"]),
                           "duygu_analisti": __import__("paper").stance(o["duygu_analisti"]),
                           "hakem": "BULL" if h["karar"] == "BUY" else "BEAR",
                           "mtf_4h": {"YUKARI": "BULL", "ASAGI": "BEAR"}.get(str(m["trend_4h"].get("trend")).upper(), "NEUTRAL"),
                           "mtf_giris": {"LONG": "BULL", "SHORT": "BEAR"}.get(str(m["entry"].get("giris")).upper(), "NEUTRAL")}
                try:
                    ctx = lessons.parse_ctx(o.get("tech_data"), o.get("sentiment_data"), o.get("extras"))
                    ctx["mtf"] = {"trend_4h": m.get("trend_4h"), "giris_1h": m.get("entry")}
                except Exception: ctx = None
                p = open_position(L, sym, "LONG" if h["karar"] == "BUY" else "SHORT", atr, conf, h.get("gerekce"), stances,
                                  {"debate": o.get("providers"), "mtf": m.get("providers")}, o["data_date"], h.get("maddeler"), ctx)
                jsave(LEDGER, L); write_summary(L)
            report["results"][sym] = r | {"sonuc": f"AÇILDI {p['side']} {p['leverage']}x @ {fmt(p['entry'])}" if p else "atlandı: min. işlem büyüklüğü/teminat yetersiz"}
        except SystemExit as e:   # llm.AllProvidersExhausted
            report["results"][sym] = f"durdu: tüm sağlayıcılar tükendi ({e})"; log("tüm LLM sağlayıcıları tükendi; döngü durdu")
            if st.get("exhausted_note_day") != day:
                st["exhausted_note_day"] = day
                tg(tgfmt.note_msg("LLM kotası tükendi", ["Tüm sağlayıcılar (Gemini, OpenRouter) şu an yanıt vermiyor.",
                   "Yeni işlem açılmıyor; açık pozisyonların stop/hedef takibi sürüyor.", "Her saat yeniden denenecek."]))
            break
        except Exception as e:
            report["results"][sym] = f"hata: {e}"; log("hata", sym, e, traceback.format_exc()[-500:])
    used = llm.CALLS["n"] - n0; st["llm_calls"] += used; st["last_cycle"] = iso(); st["last_cycle_llm"] = used
    st["providers_used"] = sorted({f"{x['provider']}/{x['model']}" for x in llm.CALLS["log"] if x.get("ok")})
    st["failovers"] = sum(1 for x in llm.CALLS["log"] if not x.get("ok"))
    jsave(STATE, st); report["llm_calls"] = used; report["providers"] = st["providers_used"]
    jsave(os.path.join(TD, "last_cycle.json"), report)
    with open(os.path.join(TD, "cycles.jsonl"), "a") as f: f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    with locked(): write_summary(load_ledger())
    try:   # ajan karnesi (yalnızca dahili; Telegram'a gitmez, öneriler otomatik uygulanmaz)
        import scoreboard; scoreboard.update()
    except Exception as e: log("karne güncellenemedi", e)
    log(f"döngü bitti: {used} LLM çağrısı, bugün {st['llm_calls']}/{T['daily_llm_budget']}")

# ---------- özet / istatistik ----------
def agent_hits(L):
    out = {}
    for p in L["positions"]:
        if p["status"] != "closed": continue
        for a, s in (p.get("stances") or {}).items():
            if s not in ("BULL", "BEAR"): continue
            d = out.setdefault(a, {"n": 0, "hit": 0}); d["n"] += 1; d["hit"] += int((s == "BULL") == (p["move"] == "UP"))
    return {a: dict(d, **{"isabet_%": round(100 * d["hit"] / d["n"], 1)}) for a, d in out.items()}

def write_summary(L):
    cl = [p for p in L["positions"] if p["status"] == "closed"]; op = opens(L); eq = equity(L)
    st = load_state()
    s = {"updated_at": iso(), "mode": "KÂĞIT (gerçek emir yok)", "equity_start": L["equity_start"], "equity_realized": round(eq, 2),
         "margin_in_use": round(sum(p.get("margin", 0) for p in op), 2), "unrealized_usd": round(sum(p.get("unrealized_usd") or 0 for p in op), 2), "return_%": round(100 * (eq / L["equity_start"] - 1), 3),
         "btc_start": L.get("btc_start"), "closed_n": len(cl), "wins": sum(p["pnl_usd"] > 0 and p.get("exit_reason") != "başabaş" for p in cl), "breakeven_n": sum(p.get("exit_reason") == "başabaş" for p in cl),
         "open_positions": [{k: p.get(k) for k in ("symbol", "side", "entry", "stop", "stop_orig", "be_moved_at", "target", "notional", "leverage", "margin", "liq_approx", "confidence", "opened_at", "last_price", "unrealized_usd")} for p in op],
         "recent_closed": [{k: p.get(k) for k in ("symbol", "side", "leverage", "margin", "entry", "exit", "exit_reason", "pnl_usd", "pnl_pct", "roe_pct", "closed_at")} for p in cl[-10:]],
         "agent_hit_rates": agent_hits(L), "last_cycle": st.get("last_cycle"), "llm_calls_today_utc": st.get("llm_calls"),
         "llm_budget": T["daily_llm_budget"], "providers_used": st.get("providers_used"), "config": T}
    jsave(os.path.join(TD, "summary.json"), s)
    sp = os.path.join(HERE, "outputs", "summary.json"); S = jload(sp, {})
    if isinstance(S, dict) and not TEST_DIR: S["paper_trader"] = s; jsave(sp, S)
    return s

def morning(send=False):
    import data, scan
    with locked():
        L = load_ledger(); op = opens(L)
        try: px = prices([p["symbol"] for p in op] + ["BTCUSDT"])
        except Exception: px = {}
    t24 = now() - dt.timedelta(hours=24); eq = equity(L)
    cl = [p for p in L["positions"] if p["status"] == "closed" and p["closed_at"] >= iso(t24)]
    new = [p for p in L["positions"] if p["opened_at"] >= iso(t24)]
    def unr(p):
        last = px.get(p["symbol"], p["entry"]); return p["qty"] * (last - p["entry"]) * (1 if p["side"] == "LONG" else -1) - p["fee_open"]
    btc = px.get("BTCUSDT"); bh = 100 * (btc / L["btc_start"] - 1) if btc and L.get("btc_start") else None
    risks = []
    try:
        fr, _ = scan.bulk_derivs()
        f = [f"{b} {fr[b]*100:+.3f}%".replace(".", ",") for b in sorted({p["symbol"][:-4] for p in op} | {"BTC", "ETH"}) if b in fr]
        if f: risks.append("Funding: " + ", ".join(f))
        uni = {r["symbol"][:-4] for r in jload(os.path.join(HERE, "outputs", "scan_latest.json"), {}).get("ranked", [])}
        ext = sorted(((b, v) for b, v in fr.items() if b in uni and abs(v) >= 0.0005), key=lambda x: -abs(x[1]))[:3]
        if ext: risks.append("Aşırı funding: " + ", ".join(f"{b} {v*100:+.3f}%".replace(".", ",") for b, v in ext))
    except Exception: pass
    try:
        fg = data.fear_greed(2)
        if fg: risks.append(f"Korku/Açgözlülük: {fg[0][1]} ({fg[0][2]})")
    except Exception: pass
    st = load_state(); dead = jload(os.path.join(HERE, "outputs", ".cache", "llm_dead.json"), {})
    dead = [k for k, v in dead.items() if v > time.time()]
    if dead: risks.append("Kota dolu: " + ", ".join(dead))
    if st.get("llm_calls") is not None: risks.append(f"LLM bütçesi (UTC günü): {st.get('llm_calls')}/{T['daily_llm_budget']}")
    d = {"date": now().strftime("%d.%m.%Y %H:%M") + " (UTC+3)", "n_open": len(new), "n_closed": len(cl), "pnl24": sum(p["pnl_usd"] for p in cl),
         "closed": cl, "open": [dict(p, now=px.get(p["symbol"], p["entry"]), unr=unr(p)) for p in op],
         "equity": eq, "ret": 100 * (eq / L["equity_start"] - 1), "unr": sum(unr(p) for p in op), "bh": bh, "hits": agent_hits(L), "risks": risks}
    try: d["lessons"] = lessons.morning_lines(lessons.load())
    except Exception: d["lessons"] = []
    txt = tgfmt.morning_msg(d); print(txt)
    if send: tg(txt)
    return txt

# ---------- zamanlayıcı ----------
def daemon():
    log(f"daemon başladı pid={os.getpid()}")
    st = load_state(); last_hour = st.get("last_cycle_hour"); last_morning = st.get("last_morning"); cyc = None; mon_t = 0; kl_t = 0
    hh, mm = map(int, T["morning_summary"].split(":"))
    while True:
        n = now()
        try:
            if time.time() - mon_t >= T["monitor_every_s"]:
                mon_t = time.time(); monitor()
        except Exception as e: log("monitor hata", e)
        try:   # kritik seviye izleyici (LLM'siz): 4s kapanış + ±%0,5 yaklaşma uyarısı (keylevels.py)
            if time.time() - kl_t >= T["monitor_every_s"]:
                kl_t = time.time(); import keylevels
                keylevels.watch(tg, state_path=os.path.join(os.path.dirname(STATE), "keylevel_state.json"), log=log)
        except Exception as e: log("kritik seviye hata", e)
        hour_key = n.strftime("%Y-%m-%dT%H")
        if n.minute >= T["cycle_minute"] and hour_key != last_hour and (cyc is None or cyc.poll() is not None):
            last_hour = hour_key; st = load_state(); st["last_cycle_hour"] = hour_key; jsave(STATE, st)
            cyc = subprocess.Popen([sys.executable, "-u", __file__, "cycle"], stdout=open(os.path.join(LOGD, "cycle.log"), "a"), stderr=subprocess.STDOUT, cwd=HERE)
            log("saatlik döngü başlatıldı", hour_key, "pid", cyc.pid)
        day = n.strftime("%Y-%m-%d")
        if (n.hour, n.minute) >= (hh, mm) and last_morning != day and n.hour < 12:
            last_morning = day; st = load_state(); st["last_morning"] = day; jsave(STATE, st)
            subprocess.Popen([sys.executable, "-u", __file__, "summary", "--send"], stdout=open(os.path.join(LOGD, "summary.log"), "a"), stderr=subprocess.STDOUT, cwd=HERE)
            log("sabah özeti başlatıldı")
        time.sleep(15)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["cycle", "monitor", "summary", "daemon", "status"])
    ap.add_argument("--top", type=int); ap.add_argument("--send", action="store_true"); a = ap.parse_args()
    if a.cmd == "cycle": cycle(a.top)
    elif a.cmd == "monitor": print("kapanan:", monitor())
    elif a.cmd == "summary": morning(a.send)
    elif a.cmd == "daemon": daemon()
    else:
        with locked(): print(json.dumps(write_summary(load_ledger()), ensure_ascii=False, indent=1, default=str)[:3000])
