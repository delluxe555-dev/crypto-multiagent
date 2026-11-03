#!/usr/bin/env python3
"""fetcher_alertachart.py — AlertaChart'tan orderflow/Chain Lab/macro çekip payload üretir.

Railway Cron: */5 * * * *  (her 5 dakikada bir)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "alertachart"
UNIVERSE = ROOT / "config" / "universe.txt"

BASE = os.environ.get("ALERTACHART_BASE", "https://app.alertachart.com").rstrip("/")
SESSION = os.environ.get("ALERTACHART_SESSION", "").strip()
CSRF = os.environ.get("ALERTACHART_CSRF", "").strip()
RAW_COOKIES = os.environ.get("ALERTACHART_COOKIES", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": BASE,
    "Referer": f"{BASE}/",
    "Content-Type": "application/json",
}

def cookie_str() -> str:
    if RAW_COOKIES:
        return RAW_COOKIES
    parts = []
    if SESSION:
        parts.append(f"session={SESSION}")
    if CSRF:
        # bazı ortamlarda sadece csrf değeri lazım olabilir
        parts.append(f"csrf={CSRF.split('|')[0] if '|' in CSRF else CSRF}")
        parts.append(f"XSRF-TOKEN={CSRF.split('|')[0] if '|' in CSRF else CSRF}")
    return "; ".join(parts)

def load_universe() -> list[str]:
    if UNIVERSE.is_file():
        syms = []
        for line in UNIVERSE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            syms.append(s)
        return syms
    return [
        "BTCUSDT.P","ETHUSDT.P","SOLUSDT.P","XRPUSDT.P","BNBUSDT.P",
        "DOGEUSDT.P","ADAUSDT.P","SUIUSDT.P","HYPEUSDT.P","NEARUSDT.P",
        "UNIUSDT.P","ZECUSDT.P",
    ]

def round15(dt: datetime) -> datetime:
    m = dt.minute // 15 * 15
    return dt.replace(minute=m, second=0, microsecond=0)

def main() -> int:
    cookies = cookie_str()
    if not cookies:
        print("[ERR] ALERTACHART_SESSION ve/veya ALERTACHART_COOKIES eksik", flush=True)
        return 1

    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Cookie"] = cookies
    if CSRF:
        token = CSRF.split("|")[0]
        s.headers["x-csrf-token"] = token
        s.headers["X-CSRF-Token"] = token

    syms = load_universe()
    now = datetime.now(timezone.utc)
    bar = round15(now)
    bar_iso = bar.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    payload = {"macro": {}, "symbols": {}}

    # MACRO
    try:
        r = s.get(f"{BASE}/api/macro", timeout=30)
        if r.ok:
            data = r.json()
            # normalize if needed
            if isinstance(data, dict):
                payload["macro"] = data.get("macro") or data.get("data") or data
    except Exception as e:
        print(f"[WARN] macro: {e}", flush=True)

    # ORDERFLOW + CHAINLAB per symbol (best effort)
    for sym in syms:
        try:
            entry = {"bar": bar_iso, "price": 0, "w": [], "fund": {}, "oi_usd": 0, "lab": []}
            # try orderflow
            try:
                r = s.post(f"{BASE}/api/orderflow", json={"symbol": sym, "timeframe": "15m", "bars": 24}, timeout=30)
                if r.ok:
                    j = r.json()
                    # try to map
                    if isinstance(j, dict):
                        entry["price"] = j.get("price") or j.get("last") or 0
                        entry["w"] = j.get("w") or j.get("windows") or []
                        entry["fund"] = j.get("fund") or {}
                        entry["oi_usd"] = j.get("oi_usd") or 0
            except Exception as e:
                print(f"[WARN] {sym} orderflow: {e}", flush=True)
            # try chainlab
            try:
                r = s.post(f"{BASE}/api/chainlab", json={"symbol": sym, "timeframe": "15m"}, timeout=30)
                if r.ok:
                    j = r.json()
                    if isinstance(j, dict):
                        entry["lab"] = j.get("lab") or j.get("modules") or []
                    elif isinstance(j, list):
                        entry["lab"] = j
            except Exception as e:
                print(f"[WARN] {sym} chainlab: {e}", flush=True)
            payload["symbols"][sym] = entry
            time.sleep(0.4)  # hafif bekleme
        except Exception as e:
            print(f"[ERR] {sym}: {e}", flush=True)

    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / "_payload.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] wrote {out} ({len(payload['symbols'])} symbols)", flush=True)

    # apply
    import subprocess
    res = subprocess.run([sys.executable, str(ROOT / "tools" / "apply_payload.py")], cwd=str(ROOT))
    return res.returncode

if __name__ == "__main__":
    raise SystemExit(main())
