"""trigger_watch.py — kosullu sinyallerin tetigini izler, tetik cikinca Telegram'a yazar.

Neyi izler: Telegram'a **gitmis** (telegram.ok) ve `mode == "conditional"` kararlar.
Her turda sembolun son **kapanmis** mumunu okur (motorun kendi yukleyicisi, kapanmamis
mum atilir) ve uc seyden birini yapar:

    tetik  : kapanis esigin otesinde  -> "✅ TETIK" mesaji (giris artik gecerli)
    iptal  : kapanis gecersizlik seviyesinin otesinde -> sessizce kapatilir (mesaj yok)
    sure   : valid_until gecti -> sessizce "expired" isaretlenir (mesaj yok)

Kural: **sadece tetik calisinca** Telegram'a mesaj gider; gurultu yok.
Ayni sinyal icin tek bildirim: durum `runs/live/triggers.json`.

    python tools/trigger_watch.py --once            # tek kontrol
    python tools/trigger_watch.py --watch --interval 60
    python tools/trigger_watch.py --list            # izlenen sinyaller
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "dataflows"))

import engine  # noqa: E402
import telegram_notify as tg  # noqa: E402

STATE = ROOT / "runs" / "live" / "triggers.json"
LIVE = ROOT / "runs" / "live"
TR = timezone(timedelta(hours=3))


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
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def _key(dec: dict) -> str:
    trig = dec.get("trigger") or {}
    raw = "|".join(str(x) for x in (dec.get("symbol"), dec.get("bar"), dec.get("action"),
                                    trig.get("close_below"), trig.get("close_above")))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- sinyaller
def _deleted_ids() -> set[str]:
    """Telegram'dan silinmis mesaj kimlikleri: o sinyaller artik izlenmez."""
    d = (tg._state().get("deleted") or {})
    return {str(k) for k in (d.keys() if isinstance(d, dict) else d)}


def signals() -> dict[str, dict]:
    """Telegram'a gitmis kosullu kararlar (sembol+bar+tetik basina tek kayit)."""
    out: dict[str, dict] = {}
    for p in sorted(LIVE.glob("*/decision_*.json")):
        try:
            dec = json.loads(p.read_text("utf-8"))
        except Exception:
            continue
        if dec.get("mode") != "conditional":
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
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(iso) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def last_closed(symbol: str, tf: str) -> tuple[float, str, str] | None:
    """(kapanis, mum_acilis_iso, kaynak) — son kapanmis mum."""
    try:
        df, src = engine.load(symbol, tf, 120)
    except SystemExit:
        return None
    if df.empty:
        return None
    row = df.iloc[-1]
    open_ms = int(df.index[-1])
    return float(row["close"]), datetime.fromtimestamp(open_ms / 1000, timezone.utc).isoformat(), src


# ------------------------------------------------------------------ kontrol
def check(verbose: bool = True) -> list[dict]:
    st = _state()
    done = st.get("signals") or {}
    c = tg.cfg()
    events: list[dict] = []

    for k, dec in signals().items():
        if k in done:
            continue
        sym = dec.get("symbol") or "?"
        tf = dec.get("tf") or "15m"

        vu = _ts(dec.get("valid_until"))
        if vu and _now() > vu:
            done[k] = {"status": "expired", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "bar": dec.get("bar")}
            events.append({"symbol": sym, "status": "expired"})
            if verbose:
                print(f"{sym:14s} expired (sure doldu)")
            continue

        data = last_closed(sym, tf)
        if not data:
            continue
        close, bar_iso, src = data
        # karardan once KAPANMIS mumlari tetik sayma (karar o mumun kapanisindan sonra verildi)
        bar_ts = _ts(bar_iso)
        built = _ts(dec.get("built_at"))
        if bar_ts and built and bar_ts + timedelta(minutes=engine.TF_MIN.get(tf, 15)) < built:
            continue

        trig = dec.get("trigger") or {}
        hit = trig_hit = False
        if "close_below" in trig:
            hit = trig_hit = close <= float(trig["close_below"])
        elif "close_above" in trig:
            hit = trig_hit = close >= float(trig["close_above"])

        inv_lv, inv_side = tg.invalidate_of(dec)
        cancelled = False
        if not hit and inv_lv is not None and inv_side:
            cancelled = (close > float(inv_lv)) if inv_side == "above" else (close < float(inv_lv))

        if hit:
            out = tg.send_text(tg.format_trigger(dec, close, bar_iso, c["hashtag"]))
            done[k] = {"status": "triggered", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "close": close, "bar": bar_iso,
                       "message_id": out.get("message_id"), "error": out.get("error")}
            events.append({"symbol": sym, "status": "triggered", "ok": out.get("ok"),
                           "close": close, "msg": out.get("message_id")})
            if verbose:
                print(f"{sym:14s} TETIK  kapanis {close}  -> "
                      f"{'msg ' + str(out.get('message_id')) if out.get('ok') else 'HATA ' + str(out.get('error'))}")
        elif cancelled:
            done[k] = {"status": "invalidated", "at": _now().isoformat(timespec="seconds"),
                       "symbol": sym, "close": close, "bar": bar_iso}
            events.append({"symbol": sym, "status": "invalidated", "close": close})
            if verbose:
                print(f"{sym:14s} iptal (mesaj yok)  kapanis {close}")
        elif verbose:
            print(f"{sym:14s} bekliyor  kapanis {close}  ({src})")

    st["signals"] = done
    st["checked_at"] = _now().isoformat(timespec="seconds")
    _save(st)
    return events


def listing() -> None:
    st = _state().get("signals") or {}
    sigs = signals()
    print(f"{'sembol':14s} {'yon':6s} {'tetik':>10s} {'iptal':>10s} {'durum':10s} gecerlilik")
    for k, dec in sigs.items():
        trig = dec.get("trigger") or {}
        tlv = trig.get("close_below") or trig.get("close_above")
        op = "<" if "close_below" in trig else ">"
        inv, _side = tg.invalidate_of(dec)
        s = st.get(k, {}).get("status", "bekliyor")
        vu = tg._tr_dt(dec.get("valid_until"))
        d = tg._dec_for(dec.get("price"))
        print(f"{dec.get('symbol', '?'):14s} {dec.get('action', ''):6s} "
              f"{op + ' ' + tg._n(tlv, d):>10s} "
              f"{tg._n(inv, d):>10s} {s:10s} {vu} TR")


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
            except Exception as exc:
                print(f"hata: {exc}", flush=True)
            time.sleep(max(15, a.interval))
    else:
        check(verbose=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
