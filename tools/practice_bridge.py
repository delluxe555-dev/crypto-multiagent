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

import ac_mcp

TP1_FRAC = 0.5
MAX_TRIES = 3
MIN_NOTIONAL = 5.0


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
        print(f"practice acilis hatasi {sym}: {pos['practice_error']}", flush=True)
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
    print(f"practice acildi {sym} {args['side']} {args['notional_usd']} USD", flush=True)
    return pos["practice"]


def on_tp1(pos: dict) -> None:
    """TP1: practice pozisyonunun yarisini kapat."""
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
        print(f"practice TP1 {sym}: %{frac * 100:.0f} kapatildi", flush=True)
    except Exception as exc:  # noqa: BLE001
        pr["tp1_error"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"practice TP1 hatasi {sym}: {pr['tp1_error']}", flush=True)


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
        print(f"practice kapandi {sym} ({event})", flush=True)
    except Exception as exc:  # noqa: BLE001
        pr["close_error"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"practice kapatma hatasi {sym}: {pr['close_error']}", flush=True)


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
