#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config" / "universe.txt"

BASE = os.environ.get("ALERTACHART_BASE", "https://app.alertachart.com")
SESSION = os.environ["ALERTACHART_SESSION"]
CSRF = os.environ["ALERTACHART_CSRF"]
UP_URL = os.environ["RAILWAY_UPLOAD_URL"]
TOK = os.environ["PAYLOAD_UPLOAD_TOKEN"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": BASE,
    "Referer": f"{BASE}/",
    "Content-Type": "application/json",
}

def cookie_str():
    parts = [f"session={SESSION}"]
    if CSRF:
        token = CSRF.split("|")[0]
        parts.append(f"csrf={token}")
        parts.append(f"XSRF-TOKEN={token}")
    return "; ".join(parts)

def load_universe():
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

def round15(dt: datetime):
    m = dt.minute // 15 * 15
    return dt.replace(minute=m, second=0, microsecond=0)

def main():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Cookie"] = cookie_str()
    token = CSRF.split("|")[0]
    s.headers["x-csrf-token"] = token
    s.headers["X-CSRF-Token"] = token

    syms = load_universe()
    now = datetime.now(timezone.utc)
    bar = round15(now)
    bar_iso = bar.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    payload = {"macro": {}, "symbols": {}}

    try:
        r = s.get(f"{BASE}/api/macro", timeout=30)
        if r.ok:
            data = r.json()
            if isinstance(data, dict):
                payload["macro"] = data.get("macro") or data.get("data") or data
        else:
            print(f"macro status {r.status_code}")
    except Exception as e:
        print(f"macro err {e}")

    for sym in syms:
        try:
            entry = {"bar": bar_iso, "price": 0, "w": [], "fund": {}, "oi_usd": 0, "lab": []}
            try:
                r = s.post(f"{BASE}/api/orderflow", json={"symbol": sym, "timeframe": "15m", "bars": 24}, timeout=30)
                if r.ok:
                    j = r.json()
                    if isinstance(j, dict):
                        entry["price"] = j.get("price") or j.get("last") or 0
                        entry["w"] = j.get("w") or j.get("windows") or j.get("data") or []
                        entry["fund"] = j.get("fund") or {}
                        entry["oi_usd"] = j.get("oi_usd") or j.get("oi") or 0
                else:
                    print(f"{sym} orderflow {r.status_code}")
            except Exception as e:
                print(f"{sym} orderflow err {e}")
            try:
                r = s.post(f"{BASE}/api/chainlab", json={"symbol": sym, "timeframe": "15m"}, timeout=30)
                if r.ok:
                    j = r.json()
                    if isinstance(j, dict):
                        entry["lab"] = j.get("lab") or j.get("modules") or j.get("data") or []
                    elif isinstance(j, list):
                        entry["lab"] = j
                else:
                    print(f"{sym} chainlab {r.status_code}")
            except Exception as e:
                print(f"{sym} chainlab err {e}")
            payload["symbols"][sym] = entry
            time.sleep(0.25)
        except Exception as e:
            print(f"{sym} err {e}")

    session = requests.Session()
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    r = session.post(UP_URL, json=payload, headers={"X-Upload-Token": TOK}, timeout=90)
    print("UPLOAD", r.status_code)
    print(r.text[:300])
    r.raise_for_status()
    print("DONE")

if __name__ == "__main__":
    main()
