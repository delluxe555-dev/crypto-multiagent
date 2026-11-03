"""Kullanıcı tanımlı kritik seviyeler (config.json -> key_levels, örn. {"BTCUSDT": 100000}; sayı ya da sayı listesi).
1) text(): ajan istemlerindeki teknik veri bloğuna 'Kullanıcının kritik seviyesi' satırı (LLM'siz, ek LLM çağrısı yok).
2) watch(): LLM'siz izleyici — tamamlanan her 4s mum kapanışında ve seviyeye ~%0,5 yaklaşınca Telegram uyarısı (tekrar yok: durum dosyası).
Kâğıt işlem: yalnızca bilgi/uyarı, emir yok. Telegram'a göndermek için watch(send=...) fonksiyonu verilir."""
import os, json, time, datetime as dt
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
IST = dt.timezone(dt.timedelta(hours=3))
H4 = 4 * 3600 * 1000
SPOT = "https://data-api.binance.vision/api/v3"

def _cfg_all():
    try: return json.load(open(os.path.join(HERE, "config.json")))
    except Exception: return {}

def levels_for(sym):
    """[seviye, ...] (config taze okunur; yoksa [])."""
    v = (_cfg_all().get("key_levels") or {}).get(sym)
    if v is None: return []
    return sorted(float(x) for x in (v if isinstance(v, (list, tuple)) else [v]))

def watch_cfg():
    c = _cfg_all().get("key_level_watch") or {}
    return {"enabled": bool(c.get("enabled", True)), "touch_pct": float(c.get("touch_pct", 0.5)), "reset_pct": float(c.get("reset_pct", 1.0)), "touch_cooldown_h": float(c.get("touch_cooldown_h", 4)), "max_below_alerts": int(c.get("max_below_alerts", 2))}

# ---------- biçim ----------
def num(x, dec=0):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fpx(x):
    return num(x, 0 if abs(x) >= 1000 else 2 if abs(x) >= 10 else 4)
def spct(x, dec=1): return ("+" if x > 0 else "") + num(x, dec) + "%"

def classify(c, level):
    """Mum (açılış_ms, o, h, l, c) -> 'alt' (kapanış seviyenin altında) | 'tepki' (fitil altı, kapanış üstü/eşit) | 'üst' (tamamı üstte)."""
    _, o, h, l, cl = c[:5]
    if cl < level: return "alt"
    if l < level: return "tepki"
    return "üst"

# ---------- 1) istem bloğu ----------
def last_closed_4h(sym, limit=3):
    """Son kapanmış 4s mumlar [(open_ms, o, h, l, c)] (kapanmamış hariç)."""
    r = requests.get(f"{SPOT}/klines", params={"symbol": sym, "interval": "4h", "limit": limit + 1}, timeout=10).json()
    now = int(time.time() * 1000)
    return [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in r if int(x[6]) < now][-limit:]

def text(symbol, df, interval, fetch4h=None):
    """Teknik veri bloğuna eklenecek satır(lar). Seviye yoksa ''. df: son satır = son kapanmış mum."""
    lv = levels_for(symbol)
    if not lv: return ""
    px = float(df["close"].iloc[-1]); out = []
    c4 = None
    try:
        if interval == "4h":
            r = df.iloc[-1]; c4 = (None, float(r.open), float(r.high), float(r.low), float(r.close)); when = str(r.date)
        else:
            c = (fetch4h or last_closed_4h)(symbol, 1)[-1]; c4 = c
            when = dt.datetime.fromtimestamp(c[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception: pass
    for L in lv:
        d = 100 * (px / L - 1)
        s = f"Kullanıcının kritik seviyesi: {fpx(L)} $ — son kapanış {fpx(px)} $, seviyeye uzaklık {spct(d)} (fiyat seviyenin {'üstünde' if d >= 0 else 'ALTINDA'})."
        if c4:
            k = classify(c4, L)
            st = {"alt": "4s KAPANIŞ seviyenin ALTINDA (ana ayı kırılımı)", "tepki": f"fitil seviyenin altına indi ({fpx(c4[3])}) ama kapanış {fpx(c4[4])} üstünde (BOĞA tepkisi)", "üst": "tamamen seviyenin üstünde, seviyeye inmedi"}[k]
            s += f" Son kapanmış 4s mum (UTC {when}): {st}."
        out.append(s)
    out.append("Kural: 4s mum KAPANIŞI seviyenin altındaysa büyük ayı (kırılım) sinyalidir; fitil seviyenin altına inip kapanış üstündeyse boğa tepkisi sinyalidir; yalnızca anlık/fitil dokunuşu kırılım sayılmaz.")
    return "\n".join(out)

# ---------- 2) izleyici ----------
def _jload(p, d):
    try: return json.load(open(p))
    except Exception: return d
def _jsave(p, o):
    tmp = p + ".tmp"; json.dump(o, open(tmp, "w"), ensure_ascii=False, indent=1); os.replace(tmp, p)

def evaluate_candle(c, level, st, max_below):
    """Tek tamamlanmış 4s mumu değerlendir. st: {'state': 'üst'|'alt'|None, 'below_n': int}. Dönüş: (uyarı_türü|None, yeni_st).
    Türler: 'alt' (kırılım), 'alt_devam' (2. ardışık altı kapanış), 'tepki' (fitil altı/kapanış üstü), 'geri' (kırılım sonrası kapanış tekrar üstte)."""
    k = classify(c, level); prev = st.get("state"); n = st.get("below_n", 0); kind = None
    if k == "alt":
        n += 1; kind = "alt" if n == 1 else ("alt_devam" if n <= max_below else None)
    else:
        if prev == "alt": kind = "geri"
        elif k == "tepki": kind = "tepki"
        n = 0
    return kind, dict(st, state="alt" if k == "alt" else "üst", below_n=n)

def comment(kind, d_close, n=1):
    return {"alt": "4s kapanış kırılımı: düşüş devamı riski arttı; kısa vadeli long'larda dikkat. Tek kapanış ilk uyarıdır, ikinci 4s kapanış altta kalırsa teyit sayılır.",
            "alt_devam": f"{n}. ardışık 4s kapanış seviyenin altında: kırılım teyit ediliyor, seviye artık direnç olabilir (retest).",
            "tepki": "Alıcılar seviyeyi savundu: fitil altı likidite alındı, kapanış üstte. Boğa tepkisi sinyali; kalıcı olması için sonraki 4s kapanışlar üstte kalmalı.",
            "geri": "Kapanış seviyenin üstüne döndü: önceki kırılım geri alındı (sahte kırılım ihtimali). Yeni 4s kapanış üstte kalırsa boğa lehine."}[kind]

def _tmsg(c):
    return dt.datetime.fromtimestamp(c[0] / 1000, IST).strftime("%d.%m %H:%M") + " – " + dt.datetime.fromtimestamp((c[0] + H4) / 1000, IST).strftime("%H:%M") + " (UTC+3)"

def candle_msg(sym, level, c, kind, n=1):
    import tgfmt
    pair = tgfmt.pair(sym); d = 100 * (c[4] / level - 1)
    head = {"alt": "🚨 4s KAPANIŞ seviyenin ALTINDA", "alt_devam": "🚨 4s KAPANIŞ hâlâ seviyenin ALTINDA", "tepki": "↩️ Seviyeden tepki (fitil alındı, kapanış üzerinde)", "geri": "✅ Kapanış seviyenin üstüne döndü (kırılım geri alındı)"}[kind]
    L = [f"<b>{head} · {pair}</b>", "", "📍 <b>Seviye</b>", f"Kritik seviye: {tgfmt.px(level)}", f"4s kapanış: {tgfmt.px(c[4])} ({tgfmt.sgn_pct(d, 2)})"]
    if c[3] < level: L.append(f"Mum dibi (fitil): {tgfmt.px(c[3])} ({tgfmt.sgn_pct(100*(c[3]/level-1), 2)})")
    L += [f"Mum: {_tmsg(c)}", "", "🧠 <b>Yorum</b>", comment(kind, d, n), "", "<i>Kâğıt işlem — bilgilendirme, gerçek emir yok.</i>"]
    return "\n".join(L)

def touch_msg(sym, level, price):
    import tgfmt
    d = 100 * (price / level - 1)
    L = [f"<b>🎯 Fiyat kritik seviyeye yaklaştı · {tgfmt.pair(sym)}</b>", "", "📍 <b>Seviye</b>", f"Kritik seviye: {tgfmt.px(level)}", f"Şu anki fiyat: {tgfmt.px(price)} ({tgfmt.sgn_pct(d, 2)})", "",
         "🧠 <b>Yorum</b>", "Karar anı yaklaşıyor: asıl işaret 4s mum KAPANIŞI olacak (altında kapanış = kırılım; fitil alıp üstte kapanış = tepki). Kapanışta ayrıca haber vereceğim.", "", "<i>Kâğıt işlem — bilgilendirme, gerçek emir yok.</i>"]
    return "\n".join(L)

def _price(sym): return float(requests.get(f"{SPOT}/ticker/price", params={"symbol": sym}, timeout=10).json()["price"])

def watch(send, state_path=None, fetch4h=None, get_price=None, now_ms=None, log=print):
    """Bir kontrol turu (daemon her ~2 dk çağırır). send(text)->bool. Dönüş: gönderilen uyarı sayısı.
    İlk çalışmada yalnızca EN SON kapanmış 4s mum değerlendirilir (eski mumlar için uyarı yok)."""
    cfg = watch_cfg()
    if not cfg["enabled"]: return 0
    sp = state_path or os.path.join(HERE, "outputs", "trader", "keylevel_state.json"); S = _jload(sp, {}); sent = 0
    fetch4h = fetch4h or (lambda s, n: last_closed_4h(s, n)); get_price = get_price or _price
    cfgl = _cfg_all().get("key_levels") or {}
    for sym in cfgl:
        lv = levels_for(sym)
        if not lv: continue
        try: cs = fetch4h(sym, 8)
        except Exception as e: log("kritik seviye: mum alınamadı", sym, e); continue
        px = None
        for L in lv:
            key = f"{sym}|{L:g}"; st = S.setdefault(key, {})
            if st.get("last_open") is None and cs:      # ilk kurulum: durum ÖNCEKİ kapanmış mumdan başlar; en son kapanmış mum normal işlenir (taze olduğu için uyarı verebilir)
                base = cs[-2] if len(cs) >= 2 else cs[-1]; kb = classify(base, L) == "alt"
                st.update(last_open=base[0], state="alt" if kb else "üst", below_n=1 if kb else 0); log("kritik seviye kuruldu", key, st["state"])
            fired = False
            for c in cs:
                if c[0] <= st.get("last_open", 0): continue
                kind, st2 = evaluate_candle(c, L, st, cfg["max_below_alerts"]); st.update(st2); st["last_open"] = c[0]
                if kind:
                    fired = True
                    ok = send(candle_msg(sym, L, c, kind, st.get("below_n", 1)))   # durum her durumda ilerler (Telegram kapalıysa döngü yok)
                    sent += 1 if ok else 0; st["last_alert"] = {"kind": kind, "open": c[0], "sent": bool(ok)}
            # yaklaşma (touch): ilk kez ±%0,5; histerezis ve bekleme süresi ile tekrar yok
            try:
                px = px if px is not None else get_price(sym)
                dist = abs(100 * (px / L - 1)); t = now_ms() if now_ms else int(time.time() * 1000)
                if st.get("touch_active"):
                    if dist > cfg["reset_pct"]: st["touch_active"] = False
                elif dist <= cfg["touch_pct"] and t - st.get("last_touch_ms", 0) >= cfg["touch_cooldown_h"] * 3600000:
                    ok = send(touch_msg(sym, L, px)) if not fired else False   # aynı turda kapanış uyarısı gittiyse yaklaşma ayrıca gönderilmez
                    st.update(touch_active=True, last_touch_ms=t); sent += 1 if ok else 0
            except Exception as e: log("kritik seviye: fiyat hatası", sym, e)
    _jsave(sp, S); return sent
