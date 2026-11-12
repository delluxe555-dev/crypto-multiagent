"""telegram_notify.py — komite kararlarini Telegram'a sinyal olarak gonderir.

Kullanim:
    python dataflows/telegram_notify.py --whoami      # bot + sohbet bilgisi
    python dataflows/telegram_notify.py --test        # ornek sinyal
    python dataflows/telegram_notify.py --decide BTCUSDT.P --tf 15m   # motoru calistirip gonder

Yapilandirma: `config/telegram.json` (token, chat_id, hashtag, send_hold) veya
ortam degiskenleri `TG_TOKEN`, `TG_CHAT`, `TG_HASHTAG`.
`chat_id` bos ise bota en son yazan sohbet otomatik bulunur (bota /start yazmak yeterli).

Ayni sinyal (sembol + bar + yon + mod) iki kez gonderilmez; durum
`runs/live/telegram_state.json` dosyasinda tutulur.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "telegram.json"
CACHE = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")
STATE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live") / "telegram_state.json"
TR = timezone(timedelta(hours=3))  # Türkiye saati (UTC+3, yaz saati yok)


# --------------------------------------------------------------------- ayar
def cfg(create: bool = False) -> dict:
    data = {}
    if CONFIG.is_file():
        try:
            data = json.loads(CONFIG.read_text("utf-8"))
        except json.JSONDecodeError:
            data = {}
    elif create:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
    data["token"] = os.environ.get("TG_TOKEN") or data.get("token") or ""
    data["chat_id"] = os.environ.get("TG_CHAT") or data.get("chat_id")
    data["hashtag"] = os.environ.get("TG_HASHTAG") or data.get("hashtag") or "#oc"
    data["send_hold"] = bool(data.get("send_hold", False))
    data["send_candidate"] = bool(data.get("send_candidate", False))  # False = sadece tetik mesajı
    data["min_share"] = float(os.environ.get("TG_MIN_SHARE") or data.get("min_share") or 0.65)
    data["require_overlay"] = bool(data.get("require_overlay", True))
    return data


def save_chat(chat_id) -> None:
    data = cfg(create=True)
    if CONFIG.is_file():
        try:
            raw = json.loads(CONFIG.read_text("utf-8"))
        except json.JSONDecodeError:
            raw = {}
    else:
        raw = {}
    raw["chat_id"] = chat_id
    raw.setdefault("hashtag", data["hashtag"])
    raw.setdefault("send_hold", False)
    CONFIG.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------- api
def api(token: str, method: str, payload: dict | None = None, timeout: int = 20) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if payload is not None:
        data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # Telegram hatayi govdede aciklar
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "description": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def resolve_chat(c: dict | None = None) -> int | str | None:
    c = c or cfg()
    if c.get("chat_id"):
        return c["chat_id"]
    if not c.get("token"):
        return None
    up = api(c["token"], "getUpdates", {"limit": 20, "allowed_updates": '["message","channel_post"]'})
    if not up.get("ok"):
        return None
    found = None
    for u in up.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            found = chat["id"]
    if found is not None:
        save_chat(found)
    return found


# ---------------------------------------------------------------- formatlama
def _n(x, dec: int = 2) -> str:
    if x is None:
        return "-"
    s = f"{float(x):,.{dec}f}"
    return s.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def _load_cache(name: str) -> tuple[dict, float]:
    """Cache dosyasini oku: (veri, yas_dk). Yoksa ({}, 1e9)."""
    p = CACHE / name
    try:
        st = p.stat()
        return json.loads(p.read_text("utf-8")), max(0.0, (time.time() - st.st_mtime) / 60)
    except Exception:
        return {}, 1e9


def _px_short(px) -> str:
    """Fiyati kisa yaz: 74,4k / 2.082 / 0,3155."""
    try:
        v = float(px)
    except (TypeError, ValueError):
        return "?"
    if v >= 10000:
        return _n(v / 1000, 1) + "k"
    if v >= 1000:
        return _n(v, 0)
    if v >= 1:
        return _n(v, 2)
    return _n(v, 4)


def market_context(max_age_min: float = 240) -> str:
    """Tek satirlik piyasa baglami; sinyal mesajinin en altina eklenir.

    Kaynak: `_extras.json` (scan: adv/dec, MA50 ustu, BTC) ve `_market.json`
    (sikisma riski). Veri yok veya bayatsa bos doner — mesaj bozulmaz.
    """
    ex, ex_age = _load_cache("_extras.json")
    mk, mk_age = _load_cache("_market.json")
    scan = (ex.get("scan") or {}) if ex_age <= max_age_min else {}
    mk = mk if mk_age <= max_age_min else {}

    parts: list[str] = []
    adv, dec = scan.get("adv"), scan.get("dec")
    if isinstance(adv, int) and isinstance(dec, int) and (adv or dec):
        parts.append(f"{adv}↑/{dec}↓")
    ma = scan.get("above_ma50")
    if isinstance(ma, (int, float)):
        parts.append(f"MA50 üstü %{_n(ma, 1)}")
    btc = scan.get("btc") or {}
    if btc.get("px"):
        s = "BTC " + _px_short(btc["px"])
        chg = btc.get("chg")
        if isinstance(chg, (int, float)):
            s += f" ({'+' if chg >= 0 else ''}{_n(chg, 1)}%)"
        parts.append(s)
    sq = mk.get("squeeze")
    if isinstance(sq, (int, float)) and sq >= 55:
        parts.append(f"sıkışma {_n(sq, 0)}")
    if not parts:
        return ""
    return "📊 " + " · ".join(parts)


def _tr_dt(value, fmt: str = "%d.%m %H:%M") -> str:
    """ISO/UTC zamanı Türkiye saatine çevirir."""
    if not value:
        return ""
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return str(value)[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TR).strftime(fmt)


def _bar_span(bar_iso, tf: str) -> str:
    """Mum aralığını TR saatinde '03:15–03:30' gibi gösterir."""
    start = _tr_dt(bar_iso)
    if not start:
        return ""
    mins = {"15m": 15, "5m": 5, "1h": 60, "4h": 240, "1d": 1440}.get(str(tf), 15)
    s = str(bar_iso).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        end = (dt + timedelta(minutes=mins)).astimezone(TR).strftime("%H:%M")
    except ValueError:
        return start
    return f"{start}–{end}"


def _dec_for(px) -> int:
    """Fiyat ölçeğine göre ondalık sayısı.

    Küçük fiyatlı coinlerde sıfırdan sonraki anlamlı basamaklar korunur:
    0,07091 → 5 · 0,006277 → 6 · 0,00000503 → 9 hane.
    """
    try:
        px = abs(float(px or 0))
    except (TypeError, ValueError):
        return 2
    if px <= 0:
        return 2
    if px >= 10000:
        return 0
    if px >= 1000:
        return 1
    if px >= 10:
        return 2
    if px >= 1:
        return 4
    import math
    exp = math.floor(math.log10(px))
    return min(12, max(4, 4 - exp))


def _tr_numbers(text: str) -> str:
    """Metin içindeki sayıları TR biçimine çevirir (80.156 / 0,25)."""
    import re

    def f(m):
        v = float(m.group(0))
        dec = 0 if (v == int(v) and abs(v) >= 1) else _dec_for(v)
        return _n(v, dec)

    return re.sub(r"\d+(?:\.\d+)?", f, text or "")


def format_signal(dec: dict, hashtag: str = "#oc") -> str:
    action = (dec.get("action") or "HOLD").upper()
    mode = dec.get("mode") or "none"
    sym = dec.get("symbol") or "?"
    lv = dec.get("levels") or {}
    con = dec.get("consensus") or {}
    px = dec.get("price")
    d = _dec_for(px)

    emoji = {"BUY": "🟢", "SELL": "🔴", "SHORT": "🔴", "LONG": "🟢"}.get(action, "⚪")
    mode_txt = {"market": "piyasa emri", "conditional": "koşullu giriş"}.get(mode, mode)
    bar = _bar_span(dec.get("bar"), dec.get("tf", "15m"))
    built = _tr_dt(dec.get("built_at"), "%d.%m %H:%M")
    head = f"{emoji} {action} · {sym}"
    sub = f"{mode_txt} · {dec.get('tf', '15m')}"
    stamp = []
    if built:
        stamp.append(f"sinyal {built} TR")
    if bar:
        stamp.append(f"bar {bar} TR")

    if action == "HOLD":
        return "\n".join([
            head, sub, "",
            f"Oylar      {con.get('buy', 0)}B / {con.get('sell', 0)}S / {con.get('hold', 0)}H",
            f"Uzlaşma    %{con.get('share', 0) * 100:.0f}",
            "",
            hashtag,
        ])

    trig = dec.get("trigger") or {}
    trig_px = trig.get("close_below") or trig.get("close_above")
    entry = lv.get("entry")
    sl, tp1, tp2 = lv.get("sl"), lv.get("tp1"), lv.get("tp2")

    L = [head, sub]
    if stamp:
        L.append(" · ".join(stamp))
    L += ["", f"Fiyat      {_n(px, d)}"]
    if mode == "conditional" and trig_px:
        side = "altı" if action in ("SELL", "SHORT") else "üstü"
        L.append(f"Tetik      {dec.get('tf', '15m')} kapanış {side} {_n(trig_px, d)}")
    if entry and not (trig_px and abs(float(entry) - float(trig_px)) < 1e-9):
        L.append(f"Giriş      {_n(entry, d)}")

    if sl or tp1 or tp2:
        L += ["",
              f"SL         {_n(sl, d)}",
              f"TP1        {_n(tp1, d)}",
              f"TP2        {_n(tp2, d)}"]

    L += ["",
          f"RR_net     {_n(lv.get('rr_net'), 2)}",
          f"Maliyet/ATR {_n(lv.get('cost_atr'), 2)}",
          f"Risk       {_n(dec.get('risk_r'), 1)}R"]

    L += ["",
          f"Oylar      {con.get('buy', 0)}B / {con.get('sell', 0)}S / {con.get('hold', 0)}H"
          f" · uzlaşma %{con.get('share', 0) * 100:.0f}"]

    vu = _tr_dt(dec.get("valid_until"))
    inv = _tr_numbers((dec.get("invalidate") or [""])[0])
    tail = []
    if vu:
        tail.append(f"Geçerli    {vu} TR")
    if inv:
        tail.append(f"İptal      {inv}")
    if dec.get("vetoes"):
        tail.append("Veto       " + ", ".join(v.get("by", "?") for v in dec["vetoes"]))
    if tail:
        L += [""] + tail

    L += ["", hashtag]
    return "\n".join(L)


# -------------------------------------------------------------------- gonder
def invalidate_of(dec: dict) -> tuple[float | None, str | None]:
    """Gecersizlik seviyesi: once yapısal alan, yoksa metinden çıkar."""
    lvl = dec.get("invalidate_level")
    side = dec.get("invalidate_side")
    if lvl is not None and side:
        return float(lvl), str(side)
    import re
    txt = " ".join(dec.get("invalidate") or [])
    m = re.search(r"kapan[ıi]ş\s+([\d.]+)\s+(üstüne|altına)", txt)
    if m:
        return float(m.group(1)), ("above" if m.group(2) == "üstüne" else "below")
    return None, None


def _vote_highlights(dec: dict, limit: int = 3) -> list[str]:
    votes = dec.get("votes") or {}
    if not isinstance(votes, dict):
        return []
    order = ["orderflow", "teknik", "makro", "onchain", "sentiment", "haber", "boğa", "ayı", "boga", "ayi"]
    items = []
    seen = set()
    for k in order + [k for k in votes.keys() if k not in order]:
        if k in seen or k not in votes:
            continue
        seen.add(k)
        v = votes.get(k) or {}
        if not isinstance(v, dict):
            continue
        side = str(v.get("side") or "").upper()
        if not side or side in ("HOLD", "ABSTAIN", "NONE"):
            continue
        if v.get("abstain"):
            continue
        conf = v.get("conf")
        note = str(v.get("note") or "").strip()
        if len(note) > 48:
            note = note[:45].rstrip() + "..."
        label = {"onchain": "Onchain", "sentiment": "Sentiment", "haber": "Haber", "boğa": "Boğa", "ayı": "Ayı", "boga": "Boğa", "ayi": "Ayı"}.get(k, k.capitalize())
        conf_txt = f" (%{float(conf) * 100:.0f})" if isinstance(conf, (int, float)) else ""
        line = f"• {label} {side}{conf_txt}"
        if note:
            line += f" — {note}"
        items.append(line)
        if len(items) >= limit:
            break
    return items


def format_trigger(dec: dict, close: float, bar_iso, hashtag: str = "#oc",
                   paper_line: str = "", market_line: str = "") -> str:
    """Tetik çalıştığında giden mesaj: artık giriş geçerli."""
    action = (dec.get("action") or "").upper()
    sym = dec.get("symbol") or "?"
    lv = dec.get("levels") or {}
    con = dec.get("consensus") or {}
    d = _dec_for(close)
    trig = dec.get("trigger") or {}
    tlv = trig.get("close_below") or trig.get("close_above")
    op = "<" if "close_below" in trig else ">"
    span = _bar_span(bar_iso, dec.get("tf", "15m"))
    built = _tr_dt(dec.get("built_at"), "%d.%m %H:%M")
    emoji = {"BUY": "🟢", "SELL": "🔴", "SHORT": "🔴", "LONG": "🟢"}.get(action, "⚪")

    L = [f"{emoji} {sym} · {action} {hashtag}", f"Tetik çalıştı · {dec.get('tf', '15m')}" + (f" · {built} TR" if built else "")]
    line = f"{dec.get('tf', '15m')} kapanış {_n(close, d)} {op} {_n(tlv, d)}"
    if span:
        line += f" · {span} TR"
    L += [line, ""]

    if lv.get("entry") is not None:
        L.append(f"📍 Giriş (ref) {_n(lv['entry'], d)}")
    L += [f"🟥 SL          {_n(lv.get('sl'), d)}",
          f"🎯 TP1         {_n(lv.get('tp1'), d)}",
          f"🎯 TP2         {_n(lv.get('tp2'), d)}",
          "",
          f"RR_net {_n(lv.get('rr_net'), 2)} · Risk {_n(dec.get('risk_r'), 1)}R",
          "",
          f"🗳️ Oylar {con.get('buy', 0)}B / {con.get('sell', 0)}S / {con.get('hold', 0)}H · Uzlaşma %{con.get('share', 0) * 100:.0f}"]

    highlights = _vote_highlights(dec, limit=3)
    if highlights:
        L.append("")
        L.extend(highlights)

    if paper_line:
        L += ["", paper_line]
    if market_line:
        L.append(market_line)

    return "\n".join(L)


def format_market(dec: dict, price: float, hashtag: str = "#oc",
                  paper_line: str = "", market_line: str = "") -> str:
    """Piyasa girisli sinyal: tetik yok, giris anlik fiyat.

    Blok duzeni tetik mesajiyla aynidir; yalniz ust satirlar farklidir.
    """
    action = (dec.get("action") or "").upper()
    sym = dec.get("symbol") or "?"
    lv = dec.get("levels") or {}
    con = dec.get("consensus") or {}
    d = _dec_for(price)
    built = _tr_dt(dec.get("built_at"), "%d.%m %H:%M")
    emoji = {"BUY": "🟢", "SELL": "🔴", "SHORT": "🔴", "LONG": "🟢"}.get(action, "⚪")

    L = [f"{emoji} {sym} · {action} {hashtag}",
         f"Piyasa girişi · {dec.get('tf', '15m')}" + (f" · {built} TR" if built else ""),
         f"Anlık fiyat {_n(price, d)}",
         ""]

    if lv.get("entry") is not None:
        L.append(f"📍 Giriş (ref) {_n(lv['entry'], d)}")
    L += [f"🟥 SL          {_n(lv.get('sl'), d)}",
          f"🎯 TP1         {_n(lv.get('tp1'), d)}",
          f"🎯 TP2         {_n(lv.get('tp2'), d)}",
          "",
          f"RR_net {_n(lv.get('rr_net'), 2)} · Risk {_n(dec.get('risk_r'), 1)}R",
          "",
          f"🗳️ Oylar {con.get('buy', 0)}B / {con.get('sell', 0)}S / {con.get('hold', 0)}H · Uzlaşma %{con.get('share', 0) * 100:.0f}"]

    highlights = _vote_highlights(dec, limit=3)
    if highlights:
        L.append("")
        L.extend(highlights)

    if paper_line:
        L += ["", paper_line]
    if market_line:
        L.append(market_line)

    return "\n".join(L)


def _be_exit(pos: dict, sl) -> bool:
    """SL çıkışı girişe çekilmiş SL'den mi (breakeven), yoksa gerçek SL mi?"""
    if str(pos.get("sl_moved") or "") == "tp1":
        return True
    if not pos.get("tp1_done"):
        return False
    try:
        e = float(pos.get("entry"))
        s = float(sl)
    except (TypeError, ValueError):
        return False
    short = (pos.get("action") or "").upper() in ("SHORT", "SELL")
    return s < e if short else s > e


def format_position_event(pos: dict, event: str, price: float, bar_iso=None,
                          hashtag: str = "#oc", paper_line: str = "") -> str:
    """Tetik sonrası pozisyon olayı: TP1 / TP2 / SL (ya da BE).

    Tetik mesajı formatına dokunmaz; ayrı ve kısa bir takip bildirimi üretir.
    TP1 sonrası girişe çekilen SL vurulursa "SL" değil "BE" yazılır.
    """
    sym = pos.get("symbol") or "?"
    action = (pos.get("action") or "").upper()
    tf = pos.get("tf") or "15m"
    entry = pos.get("entry")
    sl, tp1, tp2 = pos.get("sl"), pos.get("tp1"), pos.get("tp2")
    d = _dec_for(price if price is not None else entry)
    when = _tr_dt(bar_iso or pos.get("opened_at"), "%d.%m %H:%M")
    # R hesabi ILK SL uzerinden: TP1 sonrasi SL girişe cekilse de R bozulmasin.
    risk_sl = pos.get("sl_orig") or sl

    def r_txt(exit_px) -> str:
        try:
            risk = abs(float(risk_sl) - float(entry))
            if not risk:
                return ""
            short = action in ("SHORT", "SELL")
            rr = ((float(entry) - float(exit_px)) if short
                  else (float(exit_px) - float(entry))) / risk
            return f" ({rr:+.1f}R)".replace(".", ",")
        except Exception:
            return ""

    be = event == "sl" and _be_exit(pos, sl)
    emoji = {"tp1": "🎯", "tp2": "✅", "sl": "🟥"}.get(event, "•")
    title = {"tp1": "TP1 vuruldu", "tp2": "TP2 vuruldu", "sl": "SL vuruldu"}.get(event, event)
    if be:
        emoji, title = "🛡️", "BE vuruldu"
    L = [f"{emoji} {title} · {sym} {hashtag}",
         f"{action} · {tf}" + (f" · {when} TR" if when else "")]

    if event == "tp1":
        note = " (girişe çekildi)" if pos.get("sl_moved") else ""
        L += [f"TP1 {_n(tp1, d)}{r_txt(tp1)}",
              f"Kalan TP2 {_n(tp2, d)} · SL {_n(sl, d)}{note}"]
    elif event == "tp2":
        L += [f"Giriş {_n(entry, d)} → {_n(tp2, d)}{r_txt(tp2)}",
              "Pozisyon kapandı"]
    elif be:
        L += [f"Giriş {_n(entry, d)} → {_n(sl, d)}{r_txt(sl)}",
              "TP1 sonrası SL girişteydi",
              "Pozisyon kapandı"]
    else:
        L += [f"Giriş {_n(entry, d)} → {_n(sl, d)}{r_txt(sl)}",
              "Pozisyon kapandı"]
        if pos.get("tp1_done"):
            L.insert(-1, "TP1 önceden alındı")
    if paper_line:
        L += ["", paper_line]
    return "\n".join(L)


def _key(dec: dict) -> str:
    # Seviyeler anahtara GİRMEZ: aynı mumda yeniden hesaplanan giriş/TP yeni
    # sinyal sayılıp mesajı tekrarlamasın (sembol + mum + yön + mod yeterli).
    raw = "|".join(str(x) for x in (dec.get("symbol"), dec.get("bar"), dec.get("action"),
                                    dec.get("mode")))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save(st: dict) -> None:
    """Durumu atomik yaz: yarım kalan dosya dedupe kaybına yol açmasın."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def _paper_line() -> str:
    """Kağıt hesabın güncel durumu (tek satır); hata olursa boş."""
    try:
        import paper
        paper.configure(STATE.parent)
        return paper.summary_line()
    except Exception:
        return ""


def send_text(text: str) -> dict:
    c = cfg()
    if not c.get("token"):
        return {"ok": False, "error": "token yok (config/telegram.json veya TG_TOKEN)"}
    chat = resolve_chat(c)
    if chat is None:
        return {"ok": False, "error": "chat_id yok: bota /start yaz, sonra tekrar dene"}
    res = api(c["token"], "sendMessage", {"chat_id": chat, "text": text,
                                          "disable_web_page_preview": "true"})
    if not res.get("ok"):
        return {"ok": False, "error": res.get("description", "gonderilemedi")}
    return {"ok": True, "message_id": res["result"].get("message_id"), "chat_id": chat}


def send_signal(dec: dict) -> dict:
    """Karari gonderir. Ayni sinyal tekrar gonderilmez; HOLD varsayilan olarak susar."""
    try:
        c = cfg()
        action = (dec.get("action") or "HOLD").upper()
        if action == "HOLD" and not c.get("send_hold"):
            return {"ok": False, "skipped": "hold"}
        if action not in ("BUY", "SELL", "SHORT", "LONG", "HOLD"):
            return {"ok": False, "skipped": "action"}

        min_share = float(c.get("min_share") or 0.65)
        share = float((dec.get("consensus") or {}).get("share") or 0.0)
        if share < min_share:
            return {"ok": False, "skipped": f"share<{min_share:.2f}", "share": share}

        ov = dec.get("overlay") or {}
        if c.get("require_overlay", True) and not ov.get("used"):
            return {"ok": False, "skipped": "overlay yok/bayat (zayif kanit)", "overlay": ov}

        key = _key(dec)
        st = _state()
        sent = st.get("sent") or {}
        if key in sent:
            return {"ok": False, "skipped": "duplicate", "key": key}

        def _remember(mid, tracked: bool = False) -> None:
            sent[key] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "symbol": dec.get("symbol"), "action": action,
                         "message_id": mid, "tracked": tracked}
            st["sent"] = sent
            if len(sent) > 500:
                keep = sorted(sent.items(), key=lambda kv: kv[1].get("at") or "")[-500:]
                st["sent"] = dict(keep)
            _save(st)

        # Piyasa (anlik giris) karari: tetik yok, mesaj hemen gider; pozisyon izlenir
        if (dec.get("mode") or "") == "market" and action in ("BUY", "SELL", "SHORT", "LONG"):
            px = dec.get("price")
            if px is None:
                px = (dec.get("levels") or {}).get("entry")
            out = send_text(format_market(dec, float(px or 0), c["hashtag"],
                                          _paper_line(), market_context()))
            if out.get("ok"):
                _remember(out.get("message_id"))
            return {**out, "key": key}

        # Aday/koşullu mesajı göndermeden sadece takip et (tetik-only akış)
        if action in ("BUY", "SELL", "SHORT", "LONG") and not c.get("send_candidate", False):
            _remember(None, tracked=True)
            return {"ok": True, "tracked": True, "skipped": "candidate_suppressed", "key": key}

        out = send_text(format_signal(dec, c["hashtag"]))
        if out.get("ok"):
            _remember(out.get("message_id"))
        return {**out, "key": key}
    except Exception as exc:  # sinyal gonderimi karari bloklamaz
        return {"ok": False, "error": str(exc)}


# ----------------------------------------------------------------------- cli
def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    c = cfg(create=True)
    if "--whoami" in argv or not argv:
        me = api(c["token"], "getMe") if c.get("token") else {"ok": False}
        print("bot:", me.get("result", {}).get("username") if me.get("ok") else me.get("description"))
        print("chat_id:", resolve_chat(c) or "yok — bota /start yaz")
        return
    if "--test" in argv:
        dec = {
            "symbol": "TESTUSDT.P", "tf": "15m", "action": "SHORT", "mode": "conditional",
            "price": 80115.9, "bar": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "trigger": {"close_below": 79951.0},
            "levels": {"entry": 79951.0, "sl": 80322.0, "tp1": 79024.0, "tp2": 78824.0,
                       "rr_net": 1.88, "cost_atr": 0.48},
            "risk_r": 1.0, "valid_until": "2026-10-27T01:45:00+00:00",
            "invalidate": ["15m kapanış 80156.0 üstüne dönerse tetik iptal"],
            "consensus": {"buy": 2, "sell": 5, "hold": 0, "share": 0.714},
        }
        print(json.dumps(send_text(format_signal(dec, c["hashtag"])), ensure_ascii=False))
        return
    if "--decide" in argv:
        i = argv.index("--decide")
        sym = argv[i + 1] if len(argv) > i + 1 else "BTCUSDT.P"
        tf = argv[argv.index("--tf") + 1] if "--tf" in argv else "15m"
        sys.path.insert(0, str(ROOT / "tools"))
        import engine
        dec = engine.decide(sym, tf)
        print(json.dumps(engine.write_decision(dec, ROOT / "runs" / "live"), ensure_ascii=False))
        return
    print(__doc__)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
