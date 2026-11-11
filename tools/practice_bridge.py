#!/usr/bin/env python3
"""practice_bridge.py — kagit islemleri Alerta Practice hesabina aynalar.

Botun actigi her pozisyon, ayni sembol/yon/buyuklukte bir **practice emri** olarak
AlertaChart'in Alerta Practice (paper trading) hesabina da girer:

  acilis  -> market emri, notional = kagit islemin notional'i, TP2 + SL takili
  TP1     -> pozisyonun %50'si kapatilir (PAPER_TP1_FRACTION)
  TP2/SL/timeout/ters -> kalan tamamen kapatilir

Kimlik `ac_mcp.py`den gelir (botun kendi OAuth grant'i). Kimlik yoksa hicbir sey
patlamaz: pozisyon `practice_pending` olarak isaretlenir, kimlik gelince
`retry_pending` bir kez daha dener.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import ac_mcp

TP1_FRAC = 0.5
MAX_TRIES = 3
MIN_NOTIONAL = 5.0

ROOT = Path(__file__).resolve().parents[1]
LOG = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live") / "practice.log"


def _log(msg: str) -> None:
    """practice.log: ne denendi, ne oldu (son 200 satir tutulur)."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        old = []
        if LOG.is_file():
            old = LOG.read_text("utf-8", "replace").splitlines()[-199:]
        old.append(line)
        LOG.write_text("\n".join(old) + "\n", encoding="utf-8")
    except Exception:
        pass


def _market(sym: str) -> str:
    return "perp" if str(sym or "").upper().endswith(".P") else "spot"


def _side(action: str) -> str:
    return "short" if str(action or "").upper() in ("SHORT", "SELL") else "long"


def _f(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def enabled() -> bool:
    flag = os.environ.get("PRACTICE_MIRROR", "1").strip()
    if flag in ("0", "false", "False"):
        return False
    return ac_mcp.available()


def account() -> dict:
    return ac_mcp.call("get_practice", {})


def on_open(pos: dict, trade: dict | None) -> dict | None:
    """Kagit islem acildi: practice'te ayni yonde market emri ac."""
    if not enabled():
        return None
    sym = pos.get("symbol")
    notional = _f((trade or {}).get("notional"))
    if not sym or not notional or notional < MIN_NOTIONAL:
        return None
    args = {
        "symbol": sym,
        "market": _market(sym),
        "side": _side(pos.get("action")),
        "type": "market",
        "notional_usd": round(notional, 2),
        "leverage": 1,
    }
    tp2 = _f(pos.get("tp2"))
    sl = _f(pos.get("sl"))
    if tp2:
        args["take_profit"] = tp2
    if sl:
        args["stop_loss"] = sl
    try:
        out = ac_mcp.call("place_practice_order", args)
    except Exception as exc:  # noqa: BLE001
        pos["practice_pending"] = int(pos.get("practice_pending") or 0) + 1
        pos["practice_error"] = f"{type(exc).__name__}: {exc}"[:200]
        _log(f"acilis HATA {sym}: {pos['practice_error']}")
        return None
    pos.pop("practice_error", None)
    pos["practice_pending"] = 0
    pos["practice"] = {
        "symbol": sym,
        "side": args["side"],
        "notional": args["notional_usd"],
        "tp2": tp2,
        "sl": sl,
        "opened_at": pos.get("opened_at"),
        "result": (out or {}).get("order") or (out or {}).get("position") or out,
    }
    _log(f"acildi {sym} {args['side']} {args['notional_usd']} USD tp2={tp2} sl={sl}")
    return pos["practice"]


def _benign(err: str) -> bool:
    """Practice motoru TP/SL'de pozisyonu kendi kapatmis olabilir: hata degil."""
    e = (err or "").lower()
    return any(k in e for k in ("no open position", "no position", "not found",
                                "position does not exist", "already closed",
                                "pozisyon yok"))


def _put_brackets(pos: dict, tag: str = "TP1") -> None:
    """TP2/SL takilarini (yeniden) tak; kâr tarafindaki SL reddedilirse eski SL."""
    pr = pos.get("practice") or {}
    if not pr:
        return
    sym = pr.get("symbol") or pos.get("symbol")
    tp2 = _f(pos.get("tp2"))
    sl = _f(pos.get("sl"))
    sl_orig = _f(pos.get("sl_orig"))
    if not (tp2 or sl):
        return
    try:
        ac_mcp.call("set_practice_brackets", {
            "symbol": sym, "market": _market(sym),
            "take_profit": tp2, "stop_loss": sl})
        pr["bracket_sl"] = sl
        pr.pop("bracket_error", None)
        _log(f"{tag} {sym}: takilar yeniden takildi (tp2={tp2} sl={sl})")
        return
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"[:200]
    if sl_orig and sl_orig != sl:
        try:
            ac_mcp.call("set_practice_brackets", {
                "symbol": sym, "market": _market(sym),
                "take_profit": tp2, "stop_loss": sl_orig})
            pr["bracket_sl"] = sl_orig
            pr.pop("bracket_error", None)
            _log(f"{tag} {sym}: yeni SL kabul edilmedi, eski SL korundu "
                 f"(tp2={tp2} sl={sl_orig})")
            return
        except Exception as exc2:  # noqa: BLE001
            msg = f"{type(exc2).__name__}: {exc2}"[:200]
    pr["bracket_error"] = msg
    _log(f"{tag} taka HATA {sym}: {msg}")


def re_brackets(pos: dict) -> None:
    """SL tasindiktan sonra takilari guncelle (kapatma yapmaz)."""
    if not (pos.get("practice") or {}) or not enabled():
        return
    _put_brackets(pos, tag="SL tasima")


def on_tp1(pos: dict) -> None:
    """TP1: practice pozisyonunun yarisini kapat, TP2/SL takilarini geri koy."""
    pr = pos.get("practice") or {}
    if not pr or not enabled():
        return
    sym = pr.get("symbol") or pos.get("symbol")
    frac = max(0.01, min(1.0, float(os.environ.get("PRACTICE_TP1_FRACTION") or TP1_FRAC)))
    try:
        out = ac_mcp.call("close_practice_position",
                          {"symbol": sym, "market": _market(sym), "fraction": frac})
        pr["tp1_closed"] = True
        pr["tp1_result"] = out
        _log(f"TP1 {sym}: %{frac * 100:.0f} kapatildi")
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"[:200]
        if _benign(msg):
            pr["tp1_closed"] = True
            pr["closed_by_engine"] = "tp1"
            _log(f"TP1 {sym}: motor zaten kapatmis")
            return
        pr["tp1_error"] = msg
        _log(f"TP1 HATA {sym}: {msg}")
        return
    # Kismi kapatma takilari dusurebilir: TP2/SL'i yeniden tak (TP1 artik gecti).
    # SL artik girisе cekilmis olabilir (kâr tarafinda). Practice motoru bunu
    # reddederse eski SL ile devam et; kapatma yine botun kendi SL'sinden olur.
    _put_brackets(pos, tag="TP1")


def on_close(pos: dict, event: str) -> None:
    """TP2/SL/timeout/ters: practice pozisyonunun kalanini kapat."""
    pr = pos.get("practice") or {}
    if not pr or not enabled():
        return
    sym = pr.get("symbol") or pos.get("symbol")
    try:
        out = ac_mcp.call("close_practice_position",
                          {"symbol": sym, "market": _market(sym), "fraction": 1})
        pr["closed"] = True
        pr["close_event"] = event
        pr["close_result"] = out
        _log(f"kapandi {sym} ({event})")
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"[:200]
        if _benign(msg):
            pr["closed"] = True
            pr["close_event"] = event
            pr["closed_by_engine"] = event
            _log(f"kapandi {sym} ({event}) - motor zaten kapatmis")
            return
        pr["close_error"] = msg
        _log(f"kapatma HATA {sym}: {msg}")


def retry_pending(positions: dict) -> int:
    """Kimlik yokken acilamayan practice emirlerini (en fazla MAX_TRIES) tekrar dene."""
    if not enabled():
        return 0
    n = 0
    for pos in positions.values():
        if pos.get("status") != "open" or pos.get("practice"):
            continue
        tries = int(pos.get("practice_pending") or 0)
        if tries >= MAX_TRIES:
            continue
        # notional kagit taraftan: paper state'teki islem
        try:
            import paper
            tr = (paper._state().get("open") or {}).get(str(pos.get("id")))
        except Exception:
            tr = None
        if on_open(pos, tr):
            n += 1
    return n
