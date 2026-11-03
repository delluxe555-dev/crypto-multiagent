"""Telegram mesaj şablonları (parse_mode=HTML, Türkçe sayı biçimi). Kâğıt işlem — gerçek emir yok."""
import re, html, datetime as dt

def esc(x): return html.escape(str(x), quote=False)

def num(x, dec=2):
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 else "") + s

def px(x):
    """Fiyat: büyükse küsuratsız, küçükse anlamlı basamak."""
    a = abs(x)
    dec = 0 if a >= 1000 else 2 if a >= 10 else 4 if a >= 0.1 else 6
    return num(x, dec) + " $"

def usd(x, dec=None):
    if dec is None: dec = 0 if abs(x) >= 100 else 2
    return num(x, dec) + " $"

def sgn_pct(x, dec=2): return ("+" if x > 0 else "") + num(x, dec) + "%"
def sgn_usd(x): return ("+" if x > 0 else "") + usd(x, 2)
def pair(sym): return esc(sym[:-4] + "/USDT" if sym.endswith("USDT") else sym)

def dur(a_iso, b_iso):
    d = dt.datetime.fromisoformat(b_iso) - dt.datetime.fromisoformat(a_iso)
    m = int(d.total_seconds() // 60); h, m = divmod(m, 60); g, h = divmod(h, 24)
    return " ".join(x for x in [f"{g} gün" if g else "", f"{h} sa" if h else "", f"{m} dk" if (m or not (g or h)) else ""] if x)

def bullets(p, k=3):
    """En fazla 3 kısa madde; hakemin 'maddeler' alanı varsa onu, yoksa gerekçeyi cümle/yan cümlelere bölerek (yarım kesmeden)."""
    b = [str(x).strip().rstrip(".") for x in (p.get("bullets") or []) if str(x).strip()]
    if not b:
        txt = re.sub(r"\s+", " ", str(p.get("reason") or "")).strip()
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            sent = sent.strip().rstrip(".")
            if not sent: continue
            if len(sent) > 130:   # çok uzun cümle -> yalnızca ';' veya ' - ' ile ayrılmış tam parçalar
                b += [x.strip() for x in re.split(r";\s+|\s+[-–]\s+", sent) if len(x.strip()) > 12]
            else: b.append(sent)
    out = []
    for x in b:
        x = re.sub(r"(?<=\d)\.(?=\d{1,2}\b)", ",", x)          # 2.16 -> 2,16 (binlik noktalara dokunmaz)
        x = x[0].upper() + x[1:] if x else x
        if len(x) <= 140 and x not in out: out.append(x)
        if len(out) == k: break
    return out

AGENT = {"teknik_analist": "Teknik analist", "duygu_analisti": "Duygu analisti", "hakem": "Hakem", "mtf_4h": "4s trend", "mtf_giris": "1s giriş"}

def kmb(x):
    a = abs(x)
    if a >= 1e9: return "~" + num(x / 1e9, 1) + " Mr $"
    if a >= 1e6: return "~" + num(x / 1e6, 1) + " M $"
    if a >= 1e3: return "~" + num(x / 1e3, 0) + " B $"
    return "~" + num(x, 0) + " $"

def liq_line(p):
    """Karar zaman dilimindeki en yoğun tahmini likidasyon kümeleri (üstte/altta) ve tahmini birikim tutarı."""
    q = p.get("liq_near") or {}
    if not (q.get("up") or q.get("down")): return []
    def part(x):
        if not x: return "—"
        a = f" · birikim {kmb(x['usd'])}" if x.get("usd") else ""
        return f"{px(x['px'])} ({sgn_pct(x['pct'], 1)}){a}"
    return [f"🧲 Tahmini likidasyon ({esc(q.get('tf',''))}):",
            f"   ↑ Short-liq: {part(q.get('up'))}",
            f"   ↓ Long-liq: {part(q.get('down'))}"]

def open_msg(p, balance):
    long = p["side"] == "LONG"; e = p["entry"]
    st = p.get("stances") or {}
    aligned = st.get("mtf_4h") in ("BULL", "BEAR") and st.get("mtf_4h") == st.get("mtf_giris")
    L = [f"<b>{'🟢' if long else '🔻'} {p['side']} AÇILDI · {pair(p['symbol'])}</b>", "",
         "📍 <b>Seviyeler</b>", f"Giriş: {px(e)}",
         f"Stop: {px(p['stop'])} ({sgn_pct(100*(p['stop']/e-1))})", f"Hedef: {px(p['target'])} ({sgn_pct(100*(p['target']/e-1))})"] + liq_line(p) + ["",
         "💰 <b>Pozisyon</b>", f"Büyüklük: {usd(p['notional'])}",
         f"Kaldıraç: {p.get('leverage',1)}x · Teminat: {usd(p.get('margin', p['notional']))}",
         f"Risk: ~{usd(p['risk_usd'], 0 if p['risk_usd'] >= 10 else 1)} (%{num(100*p['risk_usd']/balance, 1)})", "",
         "🧠 <b>Karar</b>", f"Güven: %{p['confidence']}" + (" · 4s+1s uyumlu" if aligned else "")]
    L += [f"• {esc(b)}" for b in bullets(p)]
    L += ["", f"💼 Sanal bakiye: {usd(balance)}"]
    return "\n".join(L)

def close_msg(p, balance, lesson=None):
    r = p["exit_reason"]
    be = r == "başabaş"
    head = "✅ HEDEF" if r == "hedef" else "🔴 STOP" if r == "stop" else "⚪ BAŞABAŞ" if be else "⏱ SÜRE DOLDU"
    L = [f"<b>{head} · {p['side']} KAPANDI · {pair(p['symbol'])}</b>", "",
         "📍 <b>İşlem</b>", f"Giriş: {px(p['entry'])}", f"Çıkış: {px(p['exit'])}", f"Süre: {dur(p['opened_at'], p['closed_at'])}"] + ([f"🛡 Stop girişe çekilmişti ({dur(p['opened_at'], p['be_moved_at'])} sonra)"] if p.get("be_moved_at") else []) + ["",
         f"{'⚪' if be else '📈' if p['pnl_usd'] > 0 else '📉'} <b>Sonuç</b>", f"K/Z: {sgn_pct(p['pnl_pct'])} · {sgn_usd(p['pnl_usd'])}",
         f"Teminata göre: {sgn_pct(p.get('roe_pct', p['pnl_pct']), 1)} ({p.get('leverage',1)}x)", "Ücret ve kayma dahil", ""]
    if lesson: L += [f"📝 <b>Ders:</b> {esc(one_line(lesson))}", ""]
    L += [f"💼 Yeni sanal bakiye: {usd(balance, 2)}"]
    return "\n".join(L)

def be_msg(p, old_stop, last, balance):
    """Stop başabaşa çekildi bildirimi. p: be_moved_at/be_progress/be_buffer_pct dolu pozisyon; last: şu anki fiyat."""
    long = p["side"] == "LONG"; e = p["entry"]; sg = 1 if long else -1
    mv = 100 * sg * (last / e - 1); unr = p["qty"] * sg * (last - e) - p["fee_open"]
    L = [f"<b>🛡 Stop girişe çekildi · {p['side']} · {pair(p['symbol'])}</b>", "",
         "📍 <b>Seviyeler</b>", f"Giriş: {px(e)}", f"Eski stop: {px(old_stop)}",
         f"Yeni stop: {px(p['stop'])} ({sgn_pct(100*(p['stop']/e-1))}) · giriş + %{num(p.get('be_buffer_pct', 0.3), 1)} tampon",
         f"Hedef: {px(p['target'])} ({sgn_pct(100*(p['target']/e-1))})", "",
         "📈 <b>Durum</b>", f"Şu anki fiyat: {px(last)}", f"Anlık kâr: {sgn_pct(mv)} · {sgn_usd(unr)}",
         f"Hedefe giden yol: %{num(100*p.get('be_progress', 0), 0)} görüldü", "",
         "ℹ️ Fiyat dönerse pozisyon bu seviyeden kapanır (ücret ve kayma dahil ≈ başabaş); hedefe gitmeye devam ederse hedefte kâr alınır.", "",
         f"💼 Sanal bakiye: {usd(balance)}"]
    return "\n".join(L)

def one_line(x, n=240):
    x = re.sub(r"\s+", " ", str(x)).strip()
    return x if len(x) <= n else x[:n].rsplit(" ", 1)[0] + "…"

def note_msg(title, lines):
    return "\n".join([f"<b>⚠️ {esc(title)}</b>", ""] + [esc(x) for x in lines])

def morning_msg(d):
    """d: trader.morning() tarafından hazırlanan sözlük."""
    L = [f"<b>☀️ GÜNAYDIN · Kâğıt İşlem Özeti</b>", f"<i>{esc(d['date'])}</i>", "",
         "📊 <b>Günün özeti</b> (son 24 saat)", f"Açılan: {d['n_open']} · Kapanan: {d['n_closed']}",
         f"Net K/Z: {sgn_usd(d['pnl24'])} (ücret dahil)"]
    for c in d["closed"][:6]:
        icon = "⚪" if c["exit_reason"] == "başabaş" else "✅" if c["pnl_usd"] > 0 else "🔴"
        L.append(f"{icon} {pair(c['symbol'])} {c['side']} · {esc(c['exit_reason'])} · {sgn_pct(c['pnl_pct'])} ({sgn_usd(c['pnl_usd'])})")
    L += ["", "📂 <b>Açık pozisyonlar</b>"]
    if not d["open"]: L.append("Yok")
    for o in d["open"]:
        L.append(f"• {pair(o['symbol'])} {o['side']} {o.get('leverage',1)}x · giriş {px(o['entry'])} → şimdi {px(o['now'])} ({sgn_usd(o['unr'])})")
        L.append(f"   Stop {px(o['stop'])}{' 🛡 (başabaş)' if o.get('be_moved_at') else ''} · Hedef {px(o['target'])}")
    L += ["", "🏁 <b>Performans vs BTC al-tut</b>",
          f"Sanal bakiye: {usd(d['equity'], 2)} ({sgn_pct(d['ret'])})", f"Açık K/Z: {sgn_usd(d['unr'])}"]
    if d.get("bh") is not None: L.append(f"BTC al-tut (başlangıçtan): {sgn_pct(d['bh'])}")
    L += ["", "🎯 <b>Ajan isabet oranları</b>"]
    if not d["hits"]: L.append("Henüz kapanmış işlem yok")
    for a, h in d["hits"].items(): L.append(f"{esc(AGENT.get(a, a))}: %{num(h['isabet_%'], 0)} ({h['hit']}/{h['n']})")
    if d.get("lessons"):
        L += ["", "📝 <b>Ders</b>"] + [esc(one_line(x, 200)) for x in d["lessons"]]
    L += ["", "⚠️ <b>Dikkat</b>"] + [f"• {esc(x)}" for x in (d["risks"] or ["Kayda değer risk notu yok"])]
    L += ["", "<i>Kâğıt işlem — gerçek emir yok.</i>"]
    return "\n".join(L)
