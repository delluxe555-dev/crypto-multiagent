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
# 24s |degisim| bu esigi asan coin dinamik slotlara girmez: pump/dump tepesinde
# alinan coin (or. INIT -%51) overlay'i de sinyali de guvenilmez kilar.
MAX_ABS_CHG_24H = float(os.environ.get("MAX_ABS_CHG_24H", "25"))


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


OKX_API = "https://www.okx.com"
# Binance'te 1000x kontrat adiyla islem goren coinler: OKX'te ayni isim yok,
# dinamik secimde atlanir (yoksa Binance'te olmayan sembol evrene girer).
SCALED_1000 = {"PEPE", "SHIB", "FLOKI", "BONK", "SATS", "LUNC", "XEC", "RATS",
               "CAT", "CHEEMS", "WHY", "TURBO", "X", "AIDOGE", "HOT"}
STABLES = {"USDC", "FDUSD", "TUSD", "DAI", "USDE", "PYUSD", "EUR", "USD1", "USDD"}


def binance_available() -> bool:
    try:
        return requests.get(f"{BINANCE_FAPI}/fapi/v1/time", timeout=8).ok
    except Exception:
        return False


def fetch_24h_tickers() -> list[dict]:
    r = requests.get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", timeout=20)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out = []
    for t in data:
        try:
            chg = float(t.get("priceChangePercent") or 0)
        except (TypeError, ValueError):
            chg = 0.0
        out.append({**t, "change_24h_pct": chg})
    return out


def fetch_24h_tickers_okx() -> list[dict]:
    """OKX USDT swap 24s hacimleri, Binance sembol adina cevrilmis.

    Donen alanlar Binance ticker'iyla ayni: symbol / quoteVolume.
    """
    r = requests.get(f"{OKX_API}/api/v5/market/tickers",
                     params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    # TradFi perp'leri (hisse/ETF) AlertaChart kapsami disinda: instCategory=1 kripto.
    crypto_ids: set[str] = set()
    try:
        ir = requests.get(f"{OKX_API}/api/v5/public/instruments",
                          params={"instType": "SWAP"}, timeout=20)
        for ins in (ir.json().get("data") or []):
            if str(ins.get("instCategory", "1")) == "1":
                crypto_ids.add(str(ins.get("instId", "")))
    except Exception as e:
        log(f"OKX enstrüman listesi alınamadı (TradFi filtresi yok): {e}")
    out = []
    for x in r.json().get("data") or []:
        inst = str(x.get("instId", ""))
        if not inst.endswith("-USDT-SWAP"):
            continue
        if crypto_ids and inst not in crypto_ids:
            continue
        base = inst[: -len("-USDT-SWAP")]
        if base in SCALED_1000 or base in STABLES:
            continue
        try:
            last = float(x.get("last") or 0)
            qv = float(x.get("volCcy24h") or 0) * last  # base hacim * fiyat
        except (TypeError, ValueError):
            continue
        if last <= 0 or qv <= 0:
            continue
        try:
            open24 = float(x.get("open24h") or 0)
        except (TypeError, ValueError):
            open24 = 0.0
        chg = ((last - open24) / open24 * 100.0) if open24 > 0 else 0.0
        out.append({"symbol": f"{base}USDT", "quoteVolume": qv, "last": last,
                    "base": base, "change_24h_pct": chg})
    return out


def fetch_30m_metrics_okx(base: str) -> dict | None:
    """OKX 5m mumlarla 30 dk hacim/hareket (Binance kapaliyken)."""
    try:
        r = requests.get(f"{OKX_API}/api/v5/market/candles",
                         params={"instId": f"{base}-USDT-SWAP", "bar": "5m",
                                 "limit": 7}, timeout=15)
        if not r.ok:
            return None
        rows = list(reversed(r.json().get("data") or []))[:-1]  # kapanmamis mumu at
        if len(rows) < 6:
            return None
        rows = rows[-6:]
        o = float(rows[0][1])
        c = float(rows[-1][4])
        if o <= 0:
            return None
        vol_base = sum(float(k[6]) for k in rows)  # volCcy = base hacim
        quote_vol = vol_base * ((o + c) / 2)
        pct = abs((c - o) / o * 100.0)
        return {"quote_vol_30m": quote_vol, "pct_30m": pct,
                "score": quote_vol * pct}
    except Exception:
        return None


def fetch_tradfi_symbols() -> set[str]:
    """AlertaChart orderflow/chainlab kapsamı dışındaki TradFi perpetual'lar.

    Binance'te hisse/ETF perp'leri `contractType=TRADIFI_PERPETUAL` olarak
    işaretlenir (SOXL, SNDK, SOXS, AAPL...). Bunlar evrene girerse overlay
    hep boş kalır ve dinamik slotları boşa harcar. `ALLOW_TRADFI=1` ile kapatılır.
    """
    if os.environ.get("ALLOW_TRADFI", "0").strip().lower() in ("1", "true", "yes", "on"):
        return set()
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/exchangeInfo", timeout=25)
        r.raise_for_status()
        out = set()
        for s in r.json().get("symbols") or []:
            if str(s.get("contractType", "")).upper() == "TRADIFI_PERPETUAL":
                out.add(str(s.get("symbol", "")).upper())
        return out
    except Exception as e:
        log(f"exchangeInfo çekilemedi (TradFi filtresi atlandı): {e}")
        return set()


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
    src = "binance"
    tickers: list[dict] = []
    if binance_available():
        try:
            tickers = fetch_24h_tickers()
        except Exception as e:
            log(f"ticker çekilemedi: {e}")
    if not tickers:
        src = "okx"
        try:
            tickers = fetch_24h_tickers_okx()
            log(f"Binance kapalı (bölge), OKX ticker kullanılıyor: {len(tickers)} sembol")
        except Exception as e:
            log(f"OKX ticker da çekilemedi: {e}")
            return []

    # USDT perpetual, likit, çekirdekte olmayan
    tradfi = fetch_tradfi_symbols() if src == "binance" else set()
    if tradfi:
        log(f"TradFi perp filtresi: {len(tradfi)} sembol dışlandı (AlertaChart kapsamı yok)")
    cands = []
    hot = []
    for t in tickers:
        sym = str(t.get("symbol", ""))
        if not sym.endswith("USDT"):
            continue
        if sym.upper() in tradfi:
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
        try:
            chg = float(t.get("change_24h_pct") or 0)
        except (TypeError, ValueError):
            chg = 0.0
        if MAX_ABS_CHG_24H > 0 and abs(chg) > MAX_ABS_CHG_24H:
            hot.append(f"{sym}({chg:+.0f}%)")
            continue
        cands.append((sym, qv, t.get("base")))
    if hot:
        log(f"aşırı hareket ({MAX_ABS_CHG_24H:.0f}%) dışlandı: {len(hot)} sembol · "
            f"{', '.join(hot[:6])}")

    cands.sort(key=lambda x: x[1], reverse=True)
    cands = cands[:CANDIDATE_POOL]

    scored = []
    for sym, _qv, base in cands:
        m = (fetch_30m_metrics(sym) if src == "binance"
             else fetch_30m_metrics_okx(base or sym[:-4]))
        if m and m["quote_vol_30m"] > 0 and m["pct_30m"] > 0:
            scored.append((to_perp(sym), m["score"], m["quote_vol_30m"], m["pct_30m"]))
        time.sleep(0.05)  # rate-limit dostu

    scored.sort(key=lambda x: x[1], reverse=True)
    picks = [s[0] for s in scored[:DYNAMIC_SLOTS]]
    if scored:
        top = ", ".join(f"{s[0]}({s[3]:.2f}%/v{s[2]/1e6:.1f}M)" for s in scored[: min(5, len(scored))])
        log(f"kaynak={src} aday={len(cands)} skorlu={len(scored)} seçilen={picks} | top: {top}")
    else:
        log(f"kaynak={src} skorlanabilir aday bulunamadı")
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
