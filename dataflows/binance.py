"""Public crypto market data (no API key required).

Klines come from Binance USDT-M futures; Binance bazi bolgelerden (or. ABD
sunuculari) HTTP 451 dondurdugu icin ayni veri **Bybit** ve **OKX** uzerinden
yedek olarak cekilir. Hangi kaynagin kullanildigi `KLINE_SOURCE` ile sabitlenebilir
(`binance`, `bybit`, `okx` veya `auto`). Futures positioning data from
fapi.binance.com. Everything degrades gracefully: if an endpoint is blocked or
returns junk, the caller gets None and the agent says the data is missing
instead of inventing numbers.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"
BYBIT_BASE = "https://api.bybit.com"
OKX_BASE = "https://www.okx.com"

_UA = {"User-Agent": "crypto-multiagent/1.0"}

# Engellenen kaynak 15 dk boyunca tekrar denenmez (her sembolde 451 gormeyelim).
_BLOCK_SECONDS = float(os.environ.get("KLINE_BLOCK_SECONDS") or 900)
_BLOCKED: dict[str, float] = {}


def _is_blocked(name: str) -> bool:
    until = _BLOCKED.get(name) or 0.0
    return until > time.time()


def _mark_blocked(name: str) -> None:
    _BLOCKED[name] = time.time() + _BLOCK_SECONDS


def _source_order() -> list[str]:
    want = (os.environ.get("KLINE_SOURCE") or "auto").strip().lower()
    if want in ("binance", "bybit", "okx"):
        return [want]
    return ["binance", "bybit", "okx"]



def _get(url: str, params: dict[str, Any] | None = None, timeout: float = 12.0) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def _binance_klines(symbol: str, interval: str, limit: int, market: str) -> list[dict]:
    base = FUTURES_BASE if market == "perp" else SPOT_BASE
    path = "/fapi/v1/klines" if market == "perp" else "/api/v3/klines"
    raw = _get(f"{base}{path}", {"symbol": symbol, "interval": interval,
                                 "limit": max(1, min(limit, 1500))})
    if not raw or not isinstance(raw, list):
        return []
    out = []
    for k in raw:
        try:
            out.append({
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
                "trades": int(k[8]),
            })
        except (IndexError, TypeError, ValueError):
            continue
    return out


_BYBIT_IV = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
             "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
             "1d": "D", "1w": "W"}
_IV_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
          "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
          "6h": 21_600_000, "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000}


def _bybit_klines(symbol: str, interval: str, limit: int, market: str) -> list[dict]:
    """Bybit v5 klines (linear perp). Binance sembol adlari Bybit'te aynen var."""
    iv = _BYBIT_IV.get(interval)
    if not iv:
        return []
    cat = "linear" if market == "perp" else "spot"
    j = _get(f"{BYBIT_BASE}/v5/market/kline", {
        "category": cat, "symbol": symbol, "interval": iv,
        "limit": max(1, min(limit, 1000))})
    if not j or j.get("retCode") not in (0, None):
        return []
    rows = ((j.get("result") or {}).get("list") or [])
    step = _IV_MS.get(interval, 300_000)
    out = []
    for r in reversed(rows):  # Bybit en yeniden eskiye dondurur
        try:
            t = int(r[0])
            out.append({"open_time": t, "open": float(r[1]), "high": float(r[2]),
                        "low": float(r[3]), "close": float(r[4]),
                        "volume": float(r[5]), "close_time": t + step - 1,
                        "trades": 0})
        except (IndexError, TypeError, ValueError):
            continue
    return out


_OKX_IV = {"1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
           "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
           "1d": "1D", "1w": "1W"}


def _okx_inst(symbol: str, market: str) -> tuple[str, float]:
    """Binance sembolunu OKX instId'sine cevir; (instId, fiyat carpani) dondur.

    OKX'te 1000x kontrat yok: 1000PEPEUSDT -> PEPE-USDT-SWAP (fiyat /1000).
    """
    base = symbol.upper().replace(".P", "")
    scale = 1.0
    if base.startswith("1000") and base.endswith("USDT"):
        rest = base[4:-4]
        base = f"{rest}USDT"
        scale = 1000.0
    quote = "USDT"
    for q in ("USDT", "USDC", "USD"):
        if base.endswith(q):
            quote = q
            base = base[: -len(q)]
            break
    suffix = "-SWAP" if market == "perp" else ""
    return f"{base}-{quote}{suffix}", scale


def _okx_klines(symbol: str, interval: str, limit: int, market: str) -> list[dict]:
    bar = _OKX_IV.get(interval)
    inst, scale = _okx_inst(symbol, market)
    if not bar:
        return []
    j = _get(f"{OKX_BASE}/api/v5/market/candles", {
        "instId": inst, "bar": bar, "limit": max(1, min(limit, 300))})
    if not j or j.get("code") not in ("0", 0, None):
        return []
    rows = j.get("data") or []
    step = _IV_MS.get(interval, 300_000)
    out = []
    for r in reversed(rows):  # OKX en yeniden eskiye dondurur
        try:
            t = int(r[0])
            out.append({"open_time": t,
                        "open": float(r[1]) * scale, "high": float(r[2]) * scale,
                        "low": float(r[3]) * scale, "close": float(r[4]) * scale,
                        "volume": float(r[5]) / scale,
                        "close_time": t + step - 1, "trades": 0})
        except (IndexError, TypeError, ValueError):
            continue
    return out


_FETCHERS = {"binance": _binance_klines, "bybit": _bybit_klines, "okx": _okx_klines}

# Son basarili kaynak (selftest/teshis icin).
LAST_SOURCE = ""


def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 500,
               market: str = "perp") -> list[dict]:
    """OHLCV candles, oldest first.

    Kaynak sirasi: `KLINE_SOURCE` (varsayilan `auto` = Binance -> Bybit -> OKX).
    Binance 451/403 dondururse 15 dk atlanir. Returns [] on failure. Each candle:
    {open_time, open, high, low, close, volume, close_time, trades}
    """
    for name in _source_order():
        if _is_blocked(name):
            continue
        try:
            rows = _FETCHERS[name](symbol, interval, limit, market)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 451, 418):
                _mark_blocked(name)
            continue
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            _mark_blocked(name)
            continue
        if rows:
            globals()["LAST_SOURCE"] = name
            return rows
    return []


def get_ticker(symbol: str = "BTCUSDT", market: str = "perp") -> dict | None:
    base = FUTURES_BASE if market == "perp" else SPOT_BASE
    path = "/fapi/v1/ticker/24hr" if market == "perp" else "/api/v3/ticker/24hr"
    return _safe(_get, f"{base}{path}", {"symbol": symbol})


def get_funding(symbol: str = "BTCUSDT") -> list[dict] | None:
    """Recent funding-rate prints (8h cadence)."""
    raw = _safe(_get, f"{FUTURES_BASE}/fapi/v1/fundingRate",
                {"symbol": symbol, "limit": 30})
    if not raw:
        return None
    out = []
    for r in raw:
        try:
            out.append({"time": int(r["fundingTime"]), "rate": float(r["fundingRate"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def get_open_interest_hist(symbol: str = "BTCUSDT", period: str = "1h",
                           limit: int = 96) -> list[dict] | None:
    raw = _safe(_get, f"{FUTURES_BASE}/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": min(limit, 500)})
    if not raw:
        return None
    out = []
    for r in raw:
        try:
            out.append({"time": int(r["timestamp"]),
                        "oi": float(r["sumOpenInterest"]),
                        "oi_value": float(r["sumOpenInterestValue"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def get_long_short_ratio(symbol: str = "BTCUSDT", period: str = "1h",
                         limit: int = 96) -> dict | None:
    """Top-trader and global long/short account ratios."""
    top = _safe(_get, f"{FUTURES_BASE}/futures/data/topLongShortAccountRatio",
                {"symbol": symbol, "period": period, "limit": min(limit, 500)})
    glob = _safe(_get, f"{FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
                 {"symbol": symbol, "period": period, "limit": min(limit, 500)})
    if not top and not glob:
        return None
    def last(rows):
        if not rows:
            return None
        try:
            return {"ratio": float(rows[-1]["longShortRatio"]),
                    "long": float(rows[-1]["longAccount"]),
                    "short": float(rows[-1]["shortAccount"]),
                    "time": int(rows[-1]["timestamp"])}
        except (KeyError, TypeError, ValueError):
            return None
    return {"top_traders": last(top), "global": last(glob)}


def get_taker_volume(symbol: str = "BTCUSDT", period: str = "1h",
                     limit: int = 96) -> list[dict] | None:
    """Taker buy vs sell volume, the cleanest aggressive-flow proxy."""
    raw = _safe(_get, f"{FUTURES_BASE}/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": period, "limit": min(limit, 500)})
    if not raw:
        return None
    out = []
    for r in raw:
        try:
            out.append({"time": int(r["timestamp"]),
                        "buy": float(r["buySellRatio"]),
                        "buy_vol": float(r["buyVol"]),
                        "sell_vol": float(r["sellVol"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def get_open_interest(symbol: str = "BTCUSDT") -> dict | None:
    raw = _safe(_get, f"{FUTURES_BASE}/fapi/v1/openInterest", {"symbol": symbol})
    if not raw:
        return None
    try:
        return {"oi": float(raw["openInterest"]), "time": int(raw.get("time", 0) * 1000)}
    except (KeyError, TypeError, ValueError):
        return None


def fetch_market_snapshot(symbol: str, timeframe: str, bars: int, market: str = "perp") -> dict:
    """One call that gathers everything the agents need. Missing pieces stay None."""
    candles = get_klines(symbol, timeframe, bars, market)
    snap: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "market": market,
        "candles": candles,
        "ticker": None,
        "funding": None,
        "open_interest_hist": None,
        "open_interest": None,
        "long_short": None,
        "taker_volume": None,
        "fetched_at": int(time.time() * 1000),
    }
    if market != "perp":
        snap["ticker"] = get_ticker(symbol, market)
        return snap

    snap["ticker"] = get_ticker(symbol, market)
    snap["funding"] = get_funding(symbol)
    snap["open_interest_hist"] = get_open_interest_hist(symbol, _oi_period(timeframe))
    snap["open_interest"] = get_open_interest(symbol)
    snap["long_short"] = get_long_short_ratio(symbol, _oi_period(timeframe))
    snap["taker_volume"] = get_taker_volume(symbol, _oi_period(timeframe))
    return snap


def _oi_period(timeframe: str) -> str:
    mapping = {"1m": "5m", "3m": "5m", "5m": "5m", "15m": "15m", "30m": "30m",
               "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
               "12h": "12h", "1d": "1d", "3d": "1d", "1w": "1d"}
    return mapping.get(timeframe, "1h")
