"""trigger_watch.py — kosullu sinyallerin tetigini izler ve pozisyonlari takip eder.

Neyi izler: Telegram'a **gitmis** (telegram.ok) ve `mode == "conditional"` kararlar.
Her turda sembolun son **kapanmis** mumunu okur (motorun kendi yukleyicisi, kapanmamis
mum atilir) ve uc seyden birini yapar:

    tetik  : kapanis esigin otesinde  -> tetik mesaji + pozisyon acilir
    iptal  : kapanis gecersizlik seviyesinin otesinde -> sessizce kapatilir (mesaj yok)
    sure   : valid_until gecti -> sessizce "expired" isaretlenir (mesaj yok)

Acik pozisyonlar 1m mumlarla izlenir; TP1 / TP2 / SL vurulunca Telegram'a haber
verilir. Ayni sembol+yon icin pozisyon acikken yeni tetik mesaji GONDERILMEZ;
kapanistan sonra `TG_REENTRY_COOLDOWN_MIN` (varsayilan 60) dakika beklenir.
Ayni sembol+yon icin yalniz **en yeni** kosullu sinyal gecerlidir; eskiler sessizce
"superseded" isaretlenir (ayni anda iki mesaj gitmesin).

Kural: gurultu yok. Ayni sinyal icin tek bildirim: durum `runs/live/triggers.json`.

    python tools/trigger_watch.py --once            # tek kontrol
    python tools/trigger_watch.py --watch --interval 60
    python tools/trigger_watch.py --list            # izlenen sinyaller + pozisyonlar
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "dataflows"))

import engine  # noqa: E402
import telegram_notify as tg  # noqa: E402

STATE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live") / "triggers.json"
LIVE = STATE.parent
TR = timezone(timedelta(hours=3))

# Ayni sembol+yon kapanistan sonra bu kadar dakika yeni tetik almaz.
REENTRY_MIN = float(os.environ.get("TG_REENTRY_COOLDOWN_MIN") or 60)
# Pozisyon bu kadar saat icinde TP/SL'ye ulasmazsa sessizce kapanir (kilit acilir).
MAX_HOLD_H = float(os.environ.get("TG_POSITION_MAX_HOURS") or 72)
# Karar dosyalarini bu kadar saatten eskisini tarama (valid_bars=8 -> 15m'de 2 saat).
SCAN_HOURS = float(os.environ.get("TG_SCAN_HOURS") or 24)


# ------------------------------------------------------------------- durum
def _state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def _key(dec: dict) -> str:
    # Tetik seviyeleri anahtara girmez: ayni mumda yeniden hesaplanan seviye
    # yeni sinyal sayilmasin (sembol + mum + yon yeterli).
    raw = "|".join(str(x) for x in (dec.get("symbol"), dec.get("bar"), dec.get("action")))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _ts(iso) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- sinyaller
def _deleted_ids() -> set[str]:
    """Telegram'dan silinmis mesaj kimlikleri: o sinyaller artik izlenmez."""
    d = (tg._state().get("deleted") or {})
    return {str(k) for k in (d.keys() if isinstance(d, dict) else d)}


def signals() -> dict[str, dict]:
    """Telegram'a gitmis kosullu kararlar (sembol+mum+yon basina tek kayit).

    Ayni sembol+yon icin yalniz en yeni karar gecerlidir; daha eskiler
    `_superseded` ile isaretlenir. Bir sembolun en yeni karari farkli yondeyse
    (veya HOLD ise) eski kosullu sinyal de duser.
    """
    out: dict[str, dict] = {}
    newest_sym: dict[str, tuple[str, str]] = {}
    cutoff = time.time() - SCAN_HOURS * 3600

    for p in sorted(LIVE.glob("*/decision_*.json")):
        try:
            if p.stat().st_mtime < cutoff:
                continue
            dec = json.loads(p.read_text("utf-8"))
        except Exception:
            continue

        sym = dec.get("symbol")
        if sym:
            stamp = dec.get("built_at") or ""
            if sym not in newest_sym or stamp > newest_sym[sym][0]:
                newest_sym[sym] = (stamp, (dec.get("action") or "").upper())

        if dec.get("mode") not in ("conditional", "market"):
            continue
        if (dec.get("action") or "").upper() not in ("SHORT", "LONG", "BUY", "SELL"):
            continue
        tgr = dec.get("telegram") or {}
        if not tgr.get("ok"):
            continue
        if str(tgr.get("message_id")) in _deleted_ids():  # mesaj silinmisse sinyal de yok
            continue
        k = _key(dec)
        prev = out.get(k)
        # ayni anahtar birden fazla dosyada olabilir: en yenisini tut
        if prev is None or (dec.get("built_at") or "") > (prev.get("built_at") or ""):
            dec["_path"] = str(p)
            out[k] = dec

    # ayni sembol+yon: yalniz en yeni sinyal
    newest: dict[tuple, tuple[tuple, str]] = {}
    for k, dec in out.items():
        g = (dec.get("symbol"), (dec.get("action") or "").upper())
        stamp = (dec.get("bar") or "", dec.get("built_at") or "")
        if g not in newest or stamp > newest[g][0]:
            newest[g] = (stamp, k)
    keep = {v[1] for v in newest.values()}

    for k, dec in out.items():
        action = (dec.get("action") or "").upper()
        ns = newest_sym.get(dec.get("symbol"))
        newer_other = bool(ns and ns[0] > (dec.get("built_at") or "") and ns[1] != action)
        dec["_superseded"] = newer_other or (k not in keep)
    return out


# ---------------------------------------------------------------- pozisyon
def _positions(st: dict) -> dict:
    return st.setdefault("positions", {})


def _open_positions(st: dict, symbol: str | None = None, action: str | None = None) -> list[tuple[str, dict]]:
    out = []
    for pid, pos in _positions(st).items():
        if pos.get("status") != "open":
            continue
        if symbol is not None and pos.get("symbol") != symbol:
            continue
        if action is not None and pos.get("action") != action:
            continue
        out.append((pid, pos))
    return out


def _recent_close(st: dict, symbol: str, action: str, minutes: float) -> dict | None:
    if minutes <= 0:
        return None
    for pos in _positions(st).values():
        if pos.get("symbol") != symbol or pos.get("action") != action:
            continue
        if pos.get("status") == "open":
            continue
        closed = _ts(pos.get("closed_at"))
        if closed and (_now() - closed).total_seconds() < minutes * 60:
            return pos
    return None


def _r_of(pos: dict, exit_px) -> float | None:
    try:
        entry = float(pos["entry"])
        sl = float(pos["sl"])
        risk = abs(sl - entry)
        if not risk:
            return None
        short = pos.get("action") in ("SHORT", "SELL")
        return ((entry - float(exit_px)) if short else (float(exit_px) - entry)) / risk
    except Exception:
        return None


def _bar_end_ms(bar_iso, tf: str) -> int:
    dt = _ts(bar_iso)
    if not dt:
        return 0
    return int(dt.timestamp() * 1000) + engine.TF_MIN.get(tf, 15) * 60_000


def open_position(st: dict, dec: dict, key: str, close: float, bar_iso) -> dict:
    lv = dec.get("levels") or {}
    tf = dec.get("tf") or "15m"
    entry = float(lv.get("entry") or close)
    pos = {
        "id": key,
        "symbol": dec.get("symbol"),
        "action": (dec.get("action") or "").upper(),
        "tf": tf,
        "entry": entry,
        "entry_close": float(close),
        "sl": lv.get("sl"),
        "tp1": lv.get("tp1"),
        "tp2": lv.get("tp2"),
        "opened_at": _now().isoformat(timespec="seconds"),
        "opened_bar": bar_iso,
        "status": "open",
        "tp1_done": False,
        "last_ms": _bar_end_ms(bar_iso, tf) - 1,
        "decision": dec.get("_path"),
    }
    _positions(st)[key] = pos
    return pos


def close_position(pos: dict, event: str, exit_px) -> None:
    pos["status"] = event
    pos["closed_at"] = _now().isoformat(timespec="seconds")
    pos["exit"] = float(exit_px)
    pos["r"] = _r_of(pos, exit_px)


def _note_msg(pos: dict, event: str, out: dict) -> None:
    pos.setdefault("notifications", []).append({
        "event": event,
        "at": _now().isoformat(timespec="seconds"),
        "message_id": out.get("message_id"),
        "error": out.get("error"),
    })


def _notify(pos: dict, event: str, price: float, bar_iso, verbose: bool) -> dict | None:
    """Pozisyon olayini gonder; basarisizsa tekrar denemek icin kuyruga at."""
    out = tg.send_text(tg.format_position_event(pos, event, price, bar_iso))
    if out.get("ok"):
        _note_msg(pos, event, out)
        if verbose:
            print(f"{pos.get('symbol', '?'):14s} {event.upper():4s}  -> msg {out.get('message_id')}")
        return {"symbol": pos.get("symbol"), "status": event, "ok": True,
                "price": price, "msg": out.get("message_id")}
    pos.setdefault("pending", []).append({"event": event, "price": price, "bar": bar_iso})
    if verbose:
        print(f"{pos.get('symbol', '?'):14s} {event.upper():4s}  -> HATA {out.get('error')} (kuyrukta)")
    return {"symbol": pos.get("symbol"), "status": event, "ok": False, "error": out.get("error")}


def _flush_pending(pos: dict, verbose: bool) -> list[dict]:
    pending = pos.get("pending") or []
    if not pending:
        return []
    events = []
    for item in list(pending):
        out = tg.send_text(tg.format_position_event(pos, item["event"], item["price"], item.get("bar")))
        if out.get("ok"):
            pending.remove(item)
            _note_msg(pos, item["event"], out)
            events.append({"symbol": pos.get("symbol"), "status": item["event"], "ok": True,
                           "price": item["price"], "msg": out.get("message_id")})
            if verbose:
                print(f"{pos.get('symbol', '?'):14s} {item['event'].upper():4s}  -> kuyruktan msg {out.get('message_id')}")
    pos["pending"] = pending
    return events


def track_positions(st: dict, verbose: bool = True) -> list[dict]:
    """Acik pozisyonlari 1m mumlarla izle; TP1/TP2/SL olaylarini dondur."""
    events: list[dict] = []

    for pid, pos in list(_positions(st).items()):
        events.extend(_flush_pending(pos, verbose))
        if pos.get("status") != "open":
            continue

        sym = pos.get("symbol")
        if not sym:
            continue

        opened = _ts(pos.get("opened_at"))
        if opened and MAX_HOLD_H and (_now() - opened).total_seconds() > MAX_HOLD_H * 3600:
            close_position(pos, "timeout", pos.get("entry") or 0)
            events.append({"symbol": sym, "status": "timeout", "pos": pid})
            if verbose:
                print(f"{sym:14s} pozisyon zaman asimi (sessiz kapatildi)")
            continue

        last_ms = int(pos.get("last_ms") or 0)
        # uzun bosluk (yeniden baslatma) varsa daha kaba mumla kapat, yoksa 1m
        gap_min = max(0.0, (_now().timestamp() * 1000 - last_ms) / 60_000)
        interval = "1m" if gap_min <= 1000 else "5m" if gap_min <= 5000 else "15m"
        try:
            df, _src = engine.load(sym, interval, 1000)
        except Exception:
            continue
        if df is None or df.empty:
            continue

        sl = pos.get("sl")
        tp1 = pos.get("tp1")
        tp2 = pos.get("tp2")
        short = pos.get("action") in ("SHORT", "SELL")

        for ts, row in df.iterrows():
            ms = int(ts)
            if ms <= last_ms:
                continue
            hi, lo = float(row["high"]), float(row["low"])
            sl_hit = sl is not None and (hi >= float(sl) if short else lo <= float(sl))
            tp2_hit = tp2 is not None and (lo <= float(tp2) if short else hi >= float(tp2))
            tp1_hit = tp1 is not None and (lo <= float(tp1) if short else hi >= float(tp1))
            pos["last_ms"] = ms

            # ayni 1m mumda SL ve TP varsa temkinli davran: SL once
            if sl_hit:
                close_position(pos, "sl", float(sl))
                events.append(_notify(pos, "sl", float(sl), _iso(ms), verbose) or {})
                break
            if tp2_hit:
                close_position(pos, "tp2", float(tp2))
                events.append(_notify(pos, "tp2", float(tp2), _iso(ms), verbose) or {})
                break
            if tp1_hit and not pos.get("tp1_done"):
                pos["tp1_done"] = True
                pos["tp1_at"] = _iso(ms)
                events.append(_notify(pos, "tp1", float(tp1), _iso(ms), verbose) or {})

    return events


# ---------------------------------------------------------------- son mum
def last_closed(sym: str, tf: str = "15m") -> tuple[float, str, str] | None:
    """Son KAPANMIS mum: (kapanis, mum acilis ISO, kaynak).

    engine.load kapanmamis mumu zaten atar; burada yalniz son satiri aliyoruz.
    Hata durumunda None doner: tek sembol donguyu durdurmaz.
    """
    try:
        df, src = engine.load(sym, tf, 200)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    ts = int(df.index[-1])
    close = float(df["close"].iloc[-1])
    return close, _iso(ts), src


# ------------------------------------------------------------------ kontrol
def _evaluate(st: dict, k: str, dec: dict, done: dict, events: list,
              c: dict, verbose: bool) -> None:
    """Tek kosullu sinyalin tetik/iptal degerlendirmesi (check icinden cagrilir)."""
    sym = dec.get("symbol") or "?"
    tf = dec.get("tf") or "15m"
    action = (dec.get("action") or "").upper()

    # Piyasa girisi: mesaj karar aninda gitti, burada yalniz pozisyon acilir
    if (dec.get("mode") or "") == "market":
        entry = (dec.get("levels") or {}).get("entry") or dec.get("price")
        if entry is None:
            return
        for _opid, opos in _open_positions(st, sym):
            if opos.get("action") != action:
                close_position(opos, "reversed", float(entry))
                if verbose:
                    print(f"{sym:14s} ters sinyal: {opos.get('action')} pozisyon kapandi")
        pos = open_position(st, dec, k, float(entry), dec.get("bar"))
        built = _ts(dec.get("built_at"))
        if built:  # giris anindan onceki mumlari sayma
            pos["last_ms"] = int(built.timestamp() * 1000) - 1
        done[k] = {"status": "opened_market", "at": _now().isoformat(timespec="seconds"),
                   "symbol": sym, "bar": dec.get("bar"), "entry": pos.get("entry")}
        events.append({"symbol": sym, "status": "opened_market", "ok": True,
                       "entry": pos.get("entry")})
        if verbose:
            print(f"{sym:14s} PIYASA girisi {pos.get('entry')} (mesaj karar aninda gitti)")
        return

    data = last_closed(sym, tf)
    if not data:
        return
    close, bar_iso, src = data
    # karardan once KAPANMIS mumlari tetik sayma (karar o mumun kapanisindan sonra verildi)
    bar_ts = _ts(bar_iso)
    built = _ts(dec.get("built_at"))
    if bar_ts and built and bar_ts + timedelta(minutes=engine.TF_MIN.get(tf, 15)) < built:
        return

    trig = dec.get("trigger") or {}
    hit = False
    if "close_below" in trig:
        hit = close <= float(trig["close_below"])
    elif "close_above" in trig:
        hit = close >= float(trig["close_above"])

    inv_lv, inv_side = tg.invalidate_of(dec)
    cancelled = False
    if not hit and inv_lv is not None and inv_side:
        cancelled = (close > float(inv_lv)) if inv_side == "above" else (close < float(inv_lv))

    if hit:
        out = tg.send_text(tg.format_trigger(dec, close, bar_iso, c["hashtag"]))
        if not out.get("ok"):
            # mesaj gitmediyse sinyali "tetiklendi" sayma; sonraki turda tekrar dene
            if verbose:
                print(f"{sym:14s} TETIK gonderilemedi ({out.get('error')}) - tekrar denenecek")
            return

        # ters yonde acik pozisyon varsa tetik fiyatindan sessizce kapat
        for _opid, opos in _open_positions(st, sym):
            if opos.get("action") != action:
                close_position(opos, "reversed", close)
                if verbose:
                    print(f"{sym:14s} ters sinyal: {opos.get('action')} pozisyon kapandi")

        done[k] = {"status": "triggered", "at": _now().isoformat(timespec="seconds"),
                   "symbol": sym, "close": close, "bar": bar_iso,
                   "message_id": out.get("message_id"), "error": None}
        open_position(st, dec, k, close, bar_iso)
        events.append({"symbol": sym, "status": "triggered", "ok": True,
                       "close": close, "msg": out.get("message_id")})
        if verbose:
            print(f"{sym:14s} TETIK  kapanis {close}  -> msg {out.get('message_id')} (pozisyon acildi)")
    elif cancelled:
        done[k] = {"status": "invalidated", "at": _now().isoformat(timespec="seconds"),
                   "symbol": sym, "close": close, "bar": bar_iso}
        events.append({"symbol": sym, "status": "invalidated", "close": close})
        if verbose:
            print(f"{sym:14s} iptal (mesaj yok)  kapanis {close}")
    elif verbose:
        print(f"{sym:14s} bekliyor  kapanis {close}  ({src})")


def check(verbose: bool = True) -> list[dict]:
    st = _state()
    done = st.get("signals") or {}
    c = tg.cfg()
    events: list[dict] = []

    # once acik pozisyonlar: TP1 / TP2 / SL
    events.extend(track_positions(st, verbose))

    for k, dec in signals().items():
        if k in done:
            continue
        sym = dec.get("symbol") or "?"
        tf = dec.get("tf") or "15m"
        action = (dec.get("action") or "").upper()

        if dec.get("_superseded"):
            done[k] = {"status": "superseded", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "bar": dec.get("bar")}
            if verbose:
                print(f"{sym:14s} superseded (daha yeni karar var)")
            continue

        # ayni sembol+yon icin pozisyon acikken yeni tetik yok
        if _open_positions(st, sym, action):
            done[k] = {"status": "position_open", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "bar": dec.get("bar")}
            if verbose:
                print(f"{sym:14s} pozisyon acik (yeni tetik yok)")
            continue

        # kapanistan hemen sonra ayni yonde tekrar giris yok
        recent = _recent_close(st, sym, action, REENTRY_MIN)
        if recent:
            done[k] = {"status": "cooldown", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "bar": dec.get("bar"), "after": recent.get("closed_at")}
            if verbose:
                print(f"{sym:14s} bekleme ({REENTRY_MIN:.0f} dk) yeni tetik yok")
            continue

        vu = _ts(dec.get("valid_until"))
        if vu and _now() > vu:
            done[k] = {"status": "expired", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "bar": dec.get("bar")}
            events.append({"symbol": sym, "status": "expired"})
            if verbose:
                print(f"{sym:14s} expired (sure doldu)")
            continue

        try:
            _evaluate(st, k, dec, done, events, c, verbose)
        except Exception as exc:  # tek sembol hatasi turu durdurmasin
            print(f"{sym:14s} kontrol hatasi: {exc}", flush=True)
            continue

    st["signals"] = done
    st["checked_at"] = _now().isoformat(timespec="seconds")

    # durum dosyasi sonsuz buyumesin: eski kapanmis sinyalleri/pozisyonlari kirp
    if len(done) > 2000:
        keep = sorted(done.items(), key=lambda kv: kv[1].get("at") or "")[-2000:]
        st["signals"] = done = dict(keep)
    positions = _positions(st)
    if len(positions) > 500:
        closed = sorted(((pid, p) for pid, p in positions.items() if p.get("status") != "open"),
                        key=lambda kv: kv[1].get("closed_at") or "")
        for pid, _p in closed[:max(0, len(positions) - 500)]:
            positions.pop(pid, None)

    _save(st)
    return events


def listing() -> None:
    st = _state()
    sigs = signals()
    done = st.get("signals") or {}
    print(f"{'sembol':14s} {'yon':6s} {'tetik':>10s} {'iptal':>10s} {'durum':14s} gecerlilik")
    for k, dec in sigs.items():
        trig = dec.get("trigger") or {}
        tlv = trig.get("close_below") or trig.get("close_above")
        op = "<" if "close_below" in trig else ">"
        inv, _side = tg.invalidate_of(dec)
        s = done.get(k, {}).get("status", "bekliyor")
        if dec.get("_superseded") and s == "bekliyor":
            s = "superseded"
        vu = tg._tr_dt(dec.get("valid_until"))
        d = tg._dec_for(dec.get("price"))
        print(f"{dec.get('symbol', '?'):14s} {dec.get('action', ''):6s} "
              f"{op + ' ' + tg._n(tlv, d):>10s} "
              f"{tg._n(inv, d):>10s} {s:14s} {vu} TR")

    positions = _positions(st)
    if positions:
        print("\n--- pozisyonlar ---")
        print(f"{'sembol':14s} {'yon':6s} {'giris':>10s} {'SL':>10s} {'TP1':>10s} {'TP2':>10s} {'durum':10s} R")
        for _pid, pos in sorted(positions.items(), key=lambda kv: kv[1].get("opened_at") or ""):
            d = tg._dec_for(pos.get("entry"))
            r = pos.get("r")
            print(f"{pos.get('symbol', '?'):14s} {pos.get('action', ''):6s} "
                  f"{tg._n(pos.get('entry'), d):>10s} {tg._n(pos.get('sl'), d):>10s} "
                  f"{tg._n(pos.get('tp1'), d):>10s} {tg._n(pos.get('tp2'), d):>10s} "
                  f"{pos.get('status', ''):10s} {'' if r is None else f'{r:+.1f}'}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)

    if a.list:
        listing()
        return

    if a.watch:
        print(f"tetik izleme · her {a.interval}s · durum {STATE.name}", flush=True)
        while True:
            try:
                stamp = datetime.now(TR).strftime("%H:%M:%S")
                ev = check(verbose=True)
                if not ev:
                    print(f"[{stamp} TR] kontrol: yeni olay yok", flush=True)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:  # dongu asla olmesin
                print(f"hata: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(max(15, a.interval))
    else:
        check(verbose=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
