#!/usr/bin/env python3
"""ac_extras.py — AlertaChart MCP'sinin piyasa-ustu araclarini `_extras.json`'a indirger.

Neden: Railway AlertaChart MCP'sine erisemiyor (OAuth tek-sahip kurali); bu
script asistan oturumundan calisir ve botun okuyacagi hafif dosyayi uretir.

Toplanan katmanlar (hepsi `_extras.json`, apply_payload yazar):
  scan      : scan_market — overview (adv/dec, MA50 ustu pay, momentum bantlari,
              BTC/ETH) + gainers/losers/volume_spikes + funding_high/low
  news      : get_news — son basliklar + yeni listelenen varliklar
  options   : get_options (BTC/ETH) — max pain, gamma flip, dealer gamma,
              call/put duvari, put/call OI, ATM IV, 25d skew, beklenen hareket
  deriv     : get_derivatives_history (BTC/ETH) — OI 7g degisimi, funding ort.
  book      : get_order_book_events — spoof/duvar/depth basinci (majors)
  hours     : get_volume_hours — canli saatler ve alici payi (majors)
  calendar  : get_stock_calendar — yaklasan IPO ve bolunmeler

Kullanim:
    python tools/ac_extras.py                 # topla + Railway'e yukle
    python tools/ac_extras.py --local         # sadece cache'e yaz
    python tools/ac_extras.py --symbols BTCUSDT.P,ETHUSDT.P
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mcp_refresh as mr  # noqa: E402  (OAuth + MCP istemcisi yeniden kullanilir)

ROOT = mr.ROOT
CACHE = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")

# Order-book olaylari ve volume-hours yalnizca en likit perpetual'larda anlamli.
BOOK_MAJORS = ["BTCUSDT.P", "ETHUSDT.P", "SOLUSDT.P", "XRPUSDT.P", "BNBUSDT.P", "DOGEUSDT.P"]
OPTION_COINS = ["BTC", "ETH"]


def _f(x, nd: int = 2):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _sym_row(r: dict) -> dict:
    return {
        "s": r.get("symbol"),
        "px": r.get("price"),
        "chg": _f(r.get("change_24h_pct")),
        "vol": _i(r.get("volume_24h_usd")),
        "vs30": _f(r.get("volume_vs_30d_average")),
        "ma50": _f(r.get("price_vs_ma50_pct")),
    }


def fetch_scan(mcp: mr.MCP) -> dict:
    out: dict = {}
    try:
        o = mcp.call("scan_market", {"scan": "overview", "market": "perp"})
        out["adv"] = _i(o.get("advancing"))
        out["dec"] = _i(o.get("declining"))
        out["above_ma50"] = _f(o.get("above_ma50_pct"))
        out["above_ma50_vol"] = _f(o.get("above_ma50_volume_weighted_pct"))
        out["bands"] = {k: _f(v) for k, v in (o.get("momentum_bands_pct") or {}).items()}
        for k in ("btc", "eth"):
            r = o.get(k) or {}
            if r:
                out[k] = _sym_row(r)
        out["gainers"] = [_sym_row(r) for r in (o.get("top_gainers") or [])[:5]]
        out["losers"] = [_sym_row(r) for r in (o.get("top_losers") or [])[:5]]
        out["spikes"] = [_sym_row(r) for r in (o.get("volume_spikes") or [])[:5]]
        out["coins"] = _i(o.get("coins_scanned"))
        out["at"] = o.get("as_of")
    except Exception as exc:
        print(f"scan_market overview atlandi: {str(exc)[:140]}", flush=True)

    for scan, key in (("funding_high", "fund_hi"), ("funding_low", "fund_lo")):
        try:
            r = mcp.call("scan_market", {"scan": scan, "market": "perp", "limit": 8})
            out[key] = [{"c": x.get("coin"), "f8h": _f(x.get("funding_8h_pct"), 4),
                         "apr": _f(x.get("funding_apr_pct"), 1),
                         "oi": _i(x.get("open_interest_usd"))}
                        for x in (r.get("rows") or [])[:8]]
            if key == "fund_hi":
                out["majors"] = {x.get("coin"): _f(x.get("funding_8h_pct"), 4)
                                 for x in (r.get("majors") or []) if x.get("coin")}
        except Exception as exc:
            print(f"{scan} atlandi: {str(exc)[:140]}", flush=True)
    return out


def fetch_news(mcp: mr.MCP) -> dict:
    try:
        n = mcp.call("get_news", {"limit": 20})
    except Exception as exc:
        print(f"get_news atlandi: {str(exc)[:140]}", flush=True)
        return {}
    heads = [{"t": h.get("title"), "src": h.get("source"), "at": h.get("published_at")}
             for h in (n.get("headlines") or [])[:20] if h.get("title")]
    listings = [{"a": x.get("asset"), "ex": x.get("exchange"), "m": x.get("market"),
                 "st": x.get("status"), "s": x.get("symbol"), "at": x.get("at")}
                for x in (n.get("new_listings") or [])[:10]]
    return {"headlines": heads, "listings": listings, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def fetch_options(mcp: mr.MCP) -> dict:
    out: dict = {}
    for coin in OPTION_COINS:
        try:
            o = mcp.call("get_options", {"coin": coin, "scope": "30d"})
        except Exception as exc:
            print(f"get_options {coin} atlandi: {str(exc)[:140]}", flush=True)
            continue
        fe = o.get("front_expiry") or {}
        fl = o.get("flow_24h") or {}
        out[coin] = {
            "px": _f(o.get("index")),
            "max_pain": _f(o.get("max_pain")),
            "gamma_flip": _f(o.get("gamma_flip")),
            "dealer_gamma": _f(o.get("dealer_gamma_usd_per_1pct"), 0),
            "call_wall": _f((o.get("call_wall") or {}).get("strike")),
            "put_wall": _f((o.get("put_wall") or {}).get("strike")),
            "pc_oi": _f((o.get("all_expiries") or {}).get("put_call_oi_ratio")),
            "oi_usd": _i((o.get("all_expiries") or {}).get("open_interest_usd")),
            "iv": _f(fe.get("atm_iv_pct")),
            "rr25": _f(fe.get("risk_reversal_25d_pct")),
            "bfly25": _f(fe.get("butterfly_25d_pct")),
            "straddle": _f(fe.get("atm_straddle_usd")),
            "expiry": fe.get("expiry"),
            "em_lo": _f((o.get("expected_move") or {}).get("lower")),
            "em_hi": _f((o.get("expected_move") or {}).get("upper")),
            "pc_vol": _f(fl.get("put_call_volume_ratio")),
            "at": o.get("as_of"),
        }
    return out


def fetch_deriv(mcp: mr.MCP) -> dict:
    out: dict = {}
    for coin in OPTION_COINS:
        d: dict = {}
        try:
            oi = mcp.call("get_derivatives_history", {"symbol": coin, "kind": "open_interest",
                                                      "interval": "1d", "bars": 30})
            cols = oi.get("columns") or []
            rows = oi.get("rows") or oi.get("daily_mean") or []
            if rows:
                iv = cols.index("total") if "total" in cols else len(cols) - 1
                def tot(row):
                    try:
                        v = row[iv]
                        return float(v) if v is not None else None
                    except (TypeError, ValueError, IndexError):
                        return None
                i1 = tot(rows[-1])
                if i1 is not None:
                    d["oi_usd"] = _i(i1 * 1e6)  # unit: USD millions
                i0 = tot(rows[0])
                if i0 and i1:
                    d["oi_chg_30d"] = _f((i1 / i0 - 1) * 100, 1)
                if len(rows) >= 8:
                    j1 = tot(rows[-8])
                    if j1 and i1:
                        d["oi_chg_7d"] = _f((i1 / j1 - 1) * 100, 1)
        except Exception as exc:
            print(f"deriv OI {coin} atlandi: {str(exc)[:140]}", flush=True)
        try:
            f = mcp.call("get_derivatives_history", {"symbol": coin, "kind": "funding", "days": 30})
            venues = f.get("venues") or []
            if venues:
                means = [v.get("mean_window_per_8h_pct") for v in venues
                         if v.get("mean_window_per_8h_pct") is not None]
                preds = [v.get("predicted_next_per_period_pct") for v in venues
                         if v.get("predicted_next_per_period_pct") is not None]
                d["fund_mean"] = _f(sum(means) / len(means), 4) if means else None
                d["fund_next"] = _f(sum(preds) / len(preds), 4) if preds else None
                d["venues"] = len(venues)
        except Exception as exc:
            print(f"deriv funding {coin} atlandi: {str(exc)[:140]}", flush=True)
        if d:
            out[coin] = d
    return out


def fetch_book(mcp: mr.MCP, syms: list[str]) -> dict:
    out: dict = {}
    for sym in syms:
        try:
            b = mcp.call("get_order_book_events", {"symbol": sym, "market": "perp", "hours": 2})
        except Exception as exc:
            print(f"ob_events {sym} atlandi: {str(exc)[:120]}", flush=True)
            continue
        w = b.get("walls") or {}
        oc = w.get("outcomes") or {}
        dep = b.get("depth_within_1pct") or {}
        now = dep.get("now") or {}
        out[sym] = {
            "walls": _i(w.get("count")),
            "filled": _i(oc.get("filled")),
            "pulled": _i(oc.get("pulled")),
            "spoofs": len(w.get("spoofs") or []),
            "icebergs": len(b.get("icebergs") or []),
            "bids": _i(now.get("bids_usd")),
            "asks": _i(now.get("asks_usd")),
            "press": _f(now.get("book_pressure_pct"), 1),
            "press_mean": _f((dep.get("window_mean") or {}).get("book_pressure_pct"), 1),
        }
    return out


def fetch_hours(mcp: mr.MCP, syms: list[str]) -> dict:
    out: dict = {}
    for sym in syms:
        try:
            h = mcp.call("get_volume_hours", {"symbol": sym, "market": "perp", "days": 30})
        except Exception as exc:
            print(f"volume_hours {sym} atlandi: {str(exc)[:120]}", flush=True)
            continue
        by_hour = h.get("by_hour_utc") or []
        if not by_hour:
            continue
        vols = sorted(by_hour, key=lambda x: float(x.get("volume") or 0))
        out[sym] = {
            "quiet": [int(x.get("hour")) for x in vols[:5]],
            "busy": [int(x.get("hour")) for x in vols[-5:]],
            "hour_vol": {int(x.get("hour")): _i(x.get("volume")) for x in by_hour},
            "hour_buyers": {int(x.get("hour")): _f(x.get("buyers_pct"), 1) for x in by_hour},
        }
    return out


def fetch_calendar(mcp: mr.MCP) -> dict:
    out: dict = {}
    for kind in ("ipos", "splits"):
        try:
            c = mcp.call("get_stock_calendar", {"kind": kind, "window": "upcoming", "limit": 10})
        except Exception as exc:
            print(f"calendar {kind} atlandi: {str(exc)[:120]}", flush=True)
            continue
        rows = c.get("upcoming") or c.get("recent") or []
        out[kind] = [{"d": r.get("date"), "m": r.get("market"), "s": r.get("symbol"),
                      "n": r.get("name"), "ex": r.get("exchange")}
                     for r in rows[:10]]
    return out


def build(mcp: mr.MCP, syms: list[str]) -> dict:
    book_syms = [s for s in BOOK_MAJORS if s in syms] or BOOK_MAJORS[:3]
    extras = {
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan": fetch_scan(mcp),
        "news": fetch_news(mcp),
        "options": fetch_options(mcp),
        "deriv": fetch_deriv(mcp),
        "book": fetch_book(mcp, book_syms),
        "hours": fetch_hours(mcp, book_syms[:4]),
        "calendar": fetch_calendar(mcp),
    }
    return extras


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--upload-url", default=os.environ.get("UPLOAD_URL") or mr.DEFAULT_URL)
    ap.add_argument("--upload-token", default=os.environ.get("PAYLOAD_UPLOAD_TOKEN")
                    or mr.DEFAULT_UPLOAD_TOKEN)
    ap.add_argument("--oauth-file", default="")
    ap.add_argument("--opencode-db", default=str(mr.DEFAULT_DB))
    ap.add_argument("--label", default="alertachart")
    a = ap.parse_args(argv)

    env_token = os.environ.get("ALERTACHART_ACCESS_TOKEN", "").strip()
    if env_token:
        access = env_token
    elif a.oauth_file:
        data, save = mr.load_file(Path(a.oauth_file))
        access = mr.refresh_token(data, save)
    else:
        data, save = mr.load_oauth(Path(a.opencode_db), a.label)
        access = mr.refresh_token(data, save)

    syms = ([s.strip() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else mr.load_universe(a.upload_url, a.upload_token))
    mcp = mr.MCP(access)
    extras = build(mcp, syms)

    sc = extras.get("scan") or {}
    print(f"scan: adv {sc.get('adv')} / dec {sc.get('dec')} · MA50 üstü %{sc.get('above_ma50')}"
          f" · haber {len((extras.get('news') or {}).get('headlines') or [])}"
          f" · opsiyon {len(extras.get('options') or {})}"
          f" · türev {len(extras.get('deriv') or {})}"
          f" · defter {len(extras.get('book') or {})}"
          f" · saat {len(extras.get('hours') or {})}"
          f" · takvim {len(extras.get('calendar') or {})}", flush=True)

    if a.local:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "_extras.json").write_text(json.dumps(extras, ensure_ascii=False), encoding="utf-8")
        print(f"yazildi: {CACHE / '_extras.json'}", flush=True)
        return 0

    if not a.upload_token:
        raise SystemExit("PAYLOAD_UPLOAD_TOKEN yok")
    print(mr.upload({"extras": extras}, a.upload_url, a.upload_token), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
