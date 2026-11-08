#!/usr/bin/env python3
"""paper.py — kağıt (paper) hesap.

Başlangıç bakiyesi `PAPER_START_BALANCE` (varsayılan **1000 USDT**). Her sinyalde
bakiyenin `PAPER_RISK_PCT` kadarı (varsayılan **%1**) risk edilir; pozisyon
büyüklüğü giriş–SL mesafesinden hesaplanır:

    qty = (bakiye * risk%) / |giriş - SL|

Notional `PAPER_MAX_LEVERAGE` (varsayılan 5x) ile sınırlanır. TP1'de pozisyonun
`PAPER_TP1_FRACTION` kadarı (varsayılan yarısı) kapatılır; kalan TP2/SL/ters
sinyal/zaman aşımında kapanır. Her kapanışta iki yönlü komisyon
(`PAPER_FEE_PCT`, varsayılan %0,05) düşülür.

Durum: `LIVE_DIR/paper.json` — state yedeğine dahildir. Eski sinyaller sayılmaz;
hesap ilk yeni sinyalde 1000 USDT ile başlar.

    from paper import configure, open_trade, tp1_trade, close_trade, summary_line
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live") / "paper.json"


# ------------------------------------------------------------------ ayar
def _cfg() -> dict:
    def f(name, default):
        try:
            return float(os.environ.get(name) or default)
        except ValueError:
            return float(default)

    return {
        "start": f("PAPER_START_BALANCE", 1000.0),
        "risk": f("PAPER_RISK_PCT", 1.0) / 100.0,
        "tp1_frac": min(max(f("PAPER_TP1_FRACTION", 0.5), 0.0), 1.0),
        "fee": f("PAPER_FEE_PCT", 0.05) / 100.0,
        "max_lev": max(1.0, f("PAPER_MAX_LEVERAGE", 5.0)),
    }


def configure(live_dir) -> None:
    """Durum dosyasını canlı dizine bağla (trigger_watch/telegram_notify çağırır)."""
    global STATE
    STATE = Path(live_dir) / "paper.json"


# ------------------------------------------------------------------ durum
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state() -> dict:
    st = None
    try:
        if STATE.is_file():
            st = json.loads(STATE.read_text("utf-8"))
    except Exception:
        st = None
    if not isinstance(st, dict):
        st = {}
    start = float(st.get("start_balance") or _cfg()["start"])
    st.setdefault("start_balance", start)
    st.setdefault("balance", start)
    st.setdefault("trades", 0)
    st.setdefault("wins", 0)
    st.setdefault("losses", 0)
    st.setdefault("open", {})
    st.setdefault("history", [])
    st.setdefault("seen", {})
    st.setdefault("started_at", _now())
    return st


def _save(st: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE)
    except Exception as exc:
        print(f"paper: durum yazılamadı: {exc}", flush=True)


# ------------------------------------------------------------------ sayılar
def _money(x, sign: bool = False) -> str:
    s = f"{float(x):+,.2f}" if sign else f"{float(x):,.2f}"
    return s.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def _net(trade: dict, qty: float, exit_px: float) -> float:
    entry = float(trade["entry"])
    short = (trade.get("action") or "").upper() in ("SHORT", "SELL")
    gross = (entry - float(exit_px)) * qty if short else (float(exit_px) - entry) * qty
    fee = qty * (entry + float(exit_px)) * _cfg()["fee"]
    return gross - fee


# ------------------------------------------------------------------ işlemler
def open_trade(pos: dict) -> dict | None:
    """Yeni sinyal için kağıt pozisyon aç. Aynı pozisyon iki kez açılmaz."""
    st = _state()
    pid = str(pos.get("id") or "")
    if not pid or pid in st["open"] or pid in st["seen"]:
        return None
    entry = float(pos.get("entry") or 0)
    if entry <= 0:
        return None

    sl = pos.get("sl")
    risk_per_unit = abs(entry - float(sl)) if sl is not None else entry * 0.005
    if risk_per_unit <= 0:
        risk_per_unit = entry * 0.005

    cfg = _cfg()
    equity = float(st["balance"])
    risk_amt = equity * cfg["risk"]
    qty = risk_amt / risk_per_unit
    notional = qty * entry
    cap = equity * cfg["max_lev"]
    if notional > cap and entry > 0:
        qty = cap / entry
        notional = cap
        risk_amt = qty * risk_per_unit
    if qty <= 0:
        return None

    trade = {
        "id": pid,
        "symbol": pos.get("symbol"),
        "action": (pos.get("action") or "").upper(),
        "entry": entry,
        "sl": pos.get("sl"),
        "tp1": pos.get("tp1"),
        "tp2": pos.get("tp2"),
        "qty": qty,
        "notional": notional,
        "risk": risk_amt,
        "tp1_done": False,
        "realized": 0.0,
        "opened_at": _now(),
        "opened_bar": pos.get("opened_bar"),
    }
    st["open"][pid] = trade
    st["seen"][pid] = _now()
    _trim_seen(st)
    _save(st)
    return trade


def tp1_trade(pid: str, price: float) -> dict | None:
    """TP1: pozisyonun bir kısmını kapat (varsayılan yarısı)."""
    st = _state()
    t = st["open"].get(str(pid))
    if not t or t.get("tp1_done"):
        return None
    qty = float(t.get("qty") or 0)
    close_qty = qty * _cfg()["tp1_frac"]
    if close_qty <= 0:
        return None
    net = _net(t, close_qty, price)
    t["qty"] = qty - close_qty
    t["realized"] = float(t.get("realized") or 0) + net
    t["tp1_done"] = True
    t["tp1_price"] = float(price)
    st["balance"] = round(float(st["balance"]) + net, 8)
    if t["qty"] <= 1e-12:
        _finalize(st, str(pid), t, price, "tp1")
    _save(st)
    return {"id": str(pid), "event": "tp1", "pnl": net, "balance": st["balance"]}


def close_trade(pid: str, price: float, event: str) -> dict | None:
    """Kalan pozisyonu kapat (tp2 / sl / reversed / timeout)."""
    st = _state()
    t = st["open"].get(str(pid))
    if not t:
        return None
    qty = float(t.get("qty") or 0)
    net = _net(t, qty, price) if qty > 0 else 0.0
    t["realized"] = float(t.get("realized") or 0) + net
    st["balance"] = round(float(st["balance"]) + net, 8)
    _finalize(st, str(pid), t, price, event)
    _save(st)
    return {"id": str(pid), "event": event, "pnl": net,
            "total": t.get("pnl"), "balance": st["balance"]}


def _finalize(st: dict, pid: str, t: dict, price: float, event: str) -> None:
    st["open"].pop(pid, None)
    t["closed_at"] = _now()
    t["exit"] = float(price)
    t["event"] = event
    t["pnl"] = round(float(t.get("realized") or 0), 6)
    st["trades"] = int(st.get("trades") or 0) + 1
    if t["pnl"] > 0:
        st["wins"] = int(st.get("wins") or 0) + 1
    elif t["pnl"] < 0:
        st["losses"] = int(st.get("losses") or 0) + 1
    hist = st.setdefault("history", [])
    hist.append(t)
    if len(hist) > 500:
        st["history"] = hist[-500:]
    st["seen"][pid] = _now()
    _trim_seen(st)


def _trim_seen(st: dict) -> None:
    seen = st.get("seen") or {}
    if len(seen) > 2000:
        keep = sorted(seen.items(), key=lambda kv: kv[1])[-2000:]
        st["seen"] = dict(keep)


# ------------------------------------------------------------------ özet
def summary() -> dict:
    st = _state()
    start = float(st["start_balance"])
    bal = float(st["balance"])
    pnl = bal - start
    return {
        "start_balance": round(start, 2),
        "balance": round(bal, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round((pnl / start * 100) if start else 0.0, 2),
        "trades": int(st.get("trades") or 0),
        "wins": int(st.get("wins") or 0),
        "losses": int(st.get("losses") or 0),
        "open": list((st.get("open") or {}).values()),
        "history": list(st.get("history") or [])[-20:],
    }


def summary_line() -> str:
    """Telegram mesajlarına eklenecek tek satırlık kasa durumu."""
    s = summary()
    tail = f"{s['trades']} işlem"
    if s["trades"]:
        tail += f" ({s['wins']}K/{s['losses']}Z)"
    pct = f"{s['pnl_pct']:+.2f}".replace(".", ",")
    return (f"💰 Kasa {_money(s['balance'])} USDT · "
            f"K/Z {_money(s['pnl'], sign=True)} USDT (%{pct}) · {tail}")
