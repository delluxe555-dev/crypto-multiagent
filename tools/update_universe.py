#!/usr/bin/env python3
"""update_universe.py — Dinamik evren güncelleyici.

Çekirdek coinleri korur, 30 dk'lık pencerede "gelen hacim × hareket" skoruna
göre çekirdekte olmayan +5 coin ekler. Her 30 dk'da bir çalışır.

Skor = hacim_30dk_usd * |değişim_30dk_%|
Ön eleme: 24s quoteVolume ile top adaylar, sonra 5m mumlarla 30dk metrik.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config" / "universe.txt"
BINANCE_FAPI = "https://fapi.binance.com"

DYNAMIC_MARKER = "# --- DYNAMIC (30m) ---"
DYNAMIC_SLOTS = int(os.environ.get("DYNAMIC_SLOTS", "5"))
INTERVAL_SEC = max(300, int(os.environ.get("UNIVERSE_UPDATE_INTERVAL", "1800")))  # 30 dk
MIN_QUOTE_VOL_24H = float(os.environ.get("MIN_QUOTE_VOL_24H", "50000000"))  # 50M USDT
CANDIDATE_POOL = int(os.environ.get("CANDIDATE_POOL", "60"))


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    print(f"[universe {ts}] {msg}", flush=True)


def read_universe() -> tuple[list[str], list[str]]:
    """(core_lines, core_symbols) döner. Dinamik bölüm hariç tutulur."""
    if not UNIVERSE.is_file():
        return [], []
    lines = UNIVERSE.read_text("utf-8").splitlines()
    core_lines: list[str] = []
    core_syms: list[str] = []
    for line in lines:
        if line.strip() == DYNAMIC_MARKER:
            break
        core_lines.append(line)
        s = line.strip()
        if s and not s.startswith("#"):
            core_syms.append(s)
    # sondaki boş satırları temizle
    while core_lines and not core_lines[-1].strip():
        core_lines.pop()
    return core_lines, core_syms


def write_universe(core_lines: list[str], dynamic_syms: list[str]):
    UNIVERSE.parent.mkdir(parents=True, exist_ok=True)
    out = list(core_lines)
    out.append("")
    out.append(DYNAMIC_MARKER)
    out.append(f"# Güncellendi: {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z · skor=hacim_30dk_usd×|Δ30dk%|")
    for s in dynamic_syms:
        out.append(s)
    UNIVERSE.write_text("\n".join(out) + "\n", encoding="utf-8")


def to_perp(sym: str) -> str:
    sym = sym.strip().upper()
    if sym.endswith(".P"):
        return sym
    if sym.endswith("USDT"):
        return sym + ".P"
    return sym


def base_sym(perp: str) -> str:
    p = perp.strip().upper()
    if p.endswith(".P"):
        p = p[:-2]
    return p


def fetch_24h_tickers() -> list[dict]:
    r = requests.get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", timeout=20)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def fetch_30m_metrics(symbol: str) -> dict | None:
    """Son ~30 dk için 5m klines (7 bar) ile hacim ve değişim hesapla."""
    try:
        r = requests.get(
            f"{BINANCE_FAPI}/fapi/v1/klines",
            params={"symbol": symbol, "interval": "5m", "limit": 7},
            timeout=15,
        )
        if not r.ok:
            return None
        rows = r.json()
        if not isinstance(rows, list) or len(rows) < 6:
            return None
        # son kapanmamış mumu at
        rows = rows[:-1]
        if len(rows) < 6:
            return None
        rows = rows[-6:]  # 30 dk
        o = float(rows[0][1])
        c = float(rows[-1][4])
        if o <= 0:
            return None
        quote_vol = sum(float(k[7]) for k in rows)  # quote asset volume
        pct = abs((c - o) / o * 100.0)
        return {"quote_vol_30m": quote_vol, "pct_30m": pct, "score": quote_vol * pct}
    except Exception:
        return None


def pick_dynamic(core_syms: list[str]) -> list[str]:
    core_set = {s.strip().upper() for s in core_syms}
    try:
        tickers = fetch_24h_tickers()
    except Exception as e:
        log(f"ticker çekilemedi: {e}")
        return []

    # USDT perpetual, likit, çekirdekte olmayan
    cands = []
    for t in tickers:
        sym = str(t.get("symbol", ""))
        if not sym.endswith("USDT"):
            continue
        perp = to_perp(sym)
        if perp in core_set:
            continue
        try:
            qv = float(t.get("quoteVolume") or 0)
        except Exception:
            qv = 0.0
        if qv < MIN_QUOTE_VOL_24H:
            continue
        cands.append((sym, qv))

    cands.sort(key=lambda x: x[1], reverse=True)
    cands = cands[:CANDIDATE_POOL]

    scored = []
    for sym, _qv in cands:
        m = fetch_30m_metrics(sym)
        if m and m["quote_vol_30m"] > 0 and m["pct_30m"] > 0:
            scored.append((to_perp(sym), m["score"], m["quote_vol_30m"], m["pct_30m"]))
        time.sleep(0.05)  # rate-limit dostu

    scored.sort(key=lambda x: x[1], reverse=True)
    picks = [s[0] for s in scored[:DYNAMIC_SLOTS]]
    if scored:
        top = ", ".join(f"{s[0]}({s[3]:.2f}%/v{s[2]/1e6:.1f}M)" for s in scored[: min(5, len(scored))])
        log(f"aday={len(cands)} skorlu={len(scored)} seçilen={picks} | top: {top}")
    else:
        log("skorlanabilir aday bulunamadı")
    return picks


def run_once():
    core_lines, core_syms = read_universe()
    if not core_syms:
        log("çekirdek evren boş, atlanıyor")
        return
    picks = pick_dynamic(core_syms)
    write_universe(core_lines, picks)
    log(f"güncellendi: çekirdek={len(core_syms)} dinamik={len(picks)}")


def main():
    once = "--once" in sys.argv
    log(f"başladı · her {INTERVAL_SEC}s · slot={DYNAMIC_SLOTS} · çekirdek+dinamik")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"hata: {e}")
        if once:
            break
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
