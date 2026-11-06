#!/usr/bin/env python3
"""fetcher_render.py — Render üzerinde her 5 dk'da bir AlertaChart'tan veri çeker.

GitHub Actions Cloudflare 525 ile engellendiği için fetcher'ı doğrudan
Render servisi içinde çalıştırıyoruz. Aynı cache'e yazar ve apply_payload'ı tetikler.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config" / "universe.txt"
CACHE = ROOT / "cache" / "alertachart"

BASE = (os.environ.get("ALERTACHART_BASE") or "https://app.alertachart.com").rstrip("/")
SESSION = os.environ.get("ALERTACHART_SESSION", "").strip()
CSRF = os.environ.get("ALERTACHART_CSRF", "").strip()

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
        if syms:
            return syms
    return [
        "BTCUSDT.P", "ETHUSDT.P", "SOLUSDT.P", "XRPUSDT.P", "BNBUSDT.P",
        "DOGEUSDT.P", "ADAUSDT.P", "SUIUSDT.P", "HYPEUSDT.P", "NEARUSDT.P",
        "UNIUSDT.P", "ZECUSDT.P",
    ]


def round15(dt: datetime):
    m = dt.minute // 15 * 15
    return dt.replace(minute=m, second=0, microsecond=0)


def fetch_once() -> dict | None:
    if not SESSION or not CSRF:
        print("[fetch] ALERTACHART_SESSION/ALERTACHART_CSRF eksik, atlanıyor", flush=True)
        return None

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

    payload = {"macro": {}, "symbols": {}, "_fetched_at": now.isoformat()}

    try:
        r = s.get(f"{BASE}/api/macro", timeout=30)
        if r.ok:
            try:
                data = r.json()
            except Exception:
                print(f"[fetch] macro non-json {r.status_code} body={(r.text or '')[:120]}", flush=True)
                data = {}
            if isinstance(data, dict):
                payload["macro"] = data.get("macro") or data.get("data") or data
        else:
            print(f"[fetch] macro status {r.status_code} body={(r.text or '')[:120]}", flush=True)
    except Exception as e:
        print(f"[fetch] macro err {e}", flush=True)

    for sym in syms:
        try:
            entry = {"bar": bar_iso, "price": 0, "w": [], "fund": {}, "oi_usd": 0, "lab": []}
            try:
                r = s.post(f"{BASE}/api/orderflow", json={"symbol": sym, "timeframe": "15m", "bars": 24}, timeout=30)
                if r.ok:
                    try:
                        j = r.json()
                    except Exception:
                        print(f"[fetch] {sym} orderflow non-json {r.status_code} body={(r.text or '')[:120]}", flush=True)
                        j = {}
                    if isinstance(j, dict):
                        entry["price"] = j.get("price") or j.get("last") or 0
                        entry["w"] = j.get("w") or j.get("windows") or j.get("data") or []
                        entry["fund"] = j.get("fund") or {}
                        entry["oi_usd"] = j.get("oi_usd") or j.get("oi") or 0
                else:
                    print(f"[fetch] {sym} orderflow {r.status_code} body={(r.text or '')[:120]}", flush=True)
            except Exception as e:
                print(f"[fetch] {sym} orderflow err {e}", flush=True)
            try:
                r = s.post(f"{BASE}/api/chainlab", json={"symbol": sym, "timeframe": "15m"}, timeout=30)
                if r.ok:
                    try:
                        j = r.json()
                    except Exception:
                        print(f"[fetch] {sym} chainlab non-json {r.status_code} body={(r.text or '')[:120]}", flush=True)
                        j = {}
                    if isinstance(j, dict):
                        entry["lab"] = j.get("lab") or j.get("modules") or j.get("data") or []
                    elif isinstance(j, list):
                        entry["lab"] = j
                else:
                    print(f"[fetch] {sym} chainlab {r.status_code} body={(r.text or '')[:120]}", flush=True)
            except Exception as e:
                print(f"[fetch] {sym} chainlab err {e}", flush=True)
            payload["symbols"][sym] = entry
            time.sleep(0.25)
        except Exception as e:
            print(f"[fetch] {sym} err {e}", flush=True)

    return payload


def apply(payload: dict):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / "_payload.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        res = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "apply_payload.py")],
            cwd=str(ROOT),
            timeout=180,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(f"[fetch] apply_payload rc={res.returncode} stderr={(res.stderr or '')[:200]}", flush=True)
    except Exception as e:
        print(f"[fetch] apply_payload err {e}", flush=True)


def main():
    interval = max(60, int(os.environ.get("FETCH_INTERVAL", "300")))
    enabled = (os.environ.get("ALERTA_HTTP_FETCH", "0").strip().lower() in ("1", "true", "yes", "on"))
    if not enabled:
        print(
            "[fetch] HTTP fetcher kapalı (ALERTA_HTTP_FETCH=0). "
            "Overlay'lar /upload-payload ile (MCP) beslenir; "
            "AlertaChart JSON uçları netleşince ALERTA_HTTP_FETCH=1 ile aç.",
            flush=True,
        )
        return
    print(f"[fetch] render fetcher başladı · her {interval}s · base={BASE}", flush=True)
    while True:
        try:
            payload = fetch_once()
            if payload:
                syms = payload.get("symbols") or {}
                meaningful = sum(1 for v in syms.values() if (v.get("w") or v.get("lab") or v.get("price")))
                has_macro = bool(payload.get("macro"))
                if meaningful > 0 or has_macro:
                    apply(payload)
                    print(f"[fetch] OK · {meaningful}/{len(syms)} sembolde veri, makro={'var' if has_macro else 'yok'} · {datetime.now(timezone.utc).strftime('%H:%M:%SZ')}", flush=True)
                else:
                    print(f"[fetch] anlamlı veri yok ({len(syms)} sembol boş), mevcut overlay korunuyor · {datetime.now(timezone.utc).strftime('%H:%M:%SZ')}", flush=True)
        except Exception as e:
            print(f"[fetch] döngü hatası: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
