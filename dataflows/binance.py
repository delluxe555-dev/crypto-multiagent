"""Public Binance market data (no API key required).

Spot klines come from api.binance.com, futures positioning data from
fapi.binance.com. Everything degrades gracefully: if an endpoint is blocked or
returns junk, the caller gets None and the agent says the data is missing
instead of inventing numbers.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"

_UA = {"User-Agent": "crypto-multiagent/1.0"}


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


def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 500,
               market: str = "perp") -> list[dict]:
    """OHLCV candles, oldest first.

    Returns [] on failure. Each candle:
    {open_time, open, high, low, close, volume, close_time, trades}
    """
    base = FUTURES_BASE if market == "perp" else SPOT_BASE
    path = "/fapi/v1/klines" if market == "perp" else "/api/v3/klines"
    raw = _safe(_get, f"{base}{path}", {"symbol": symbol, "interval": interval,
                                        "limit": max(1, min(limit, 1500))})
    if not raw or not isinstance(raw, list):
        return []
    candles = []
    for k in raw:
        try:
            candles.append({
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
    return candles


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
