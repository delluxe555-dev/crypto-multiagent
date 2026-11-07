"""apply_payload.py — asistanin MCP'den topladigi hafif katmani overlay dosyalarina boler.

Asistan `cache/alertachart/_payload.json` dosyasini su yapiyla yazar:

{
  "macro": {"US10Y": {"latest": 5.0, "change": 0.04, "change_1y": 1.01}, ...},
  "symbols": {
    "SOLUSDT.P": {
      "bar": "2026-10-27T00:15:00.000Z",
      "price": 100.9,
      "w": [{"b":4,...},{"b":8,...}],
      "venues": [{"v":"Binance","cvd":-1234.5}],
      "fund": {"Binance": 0.01, ...},
      "oi_usd": 1234567,
      "lab": [{"m":"flow_score","v":64.2,"r":"..."}]
    }
  }
}

Sonra: python tools/apply_payload.py [payload.json] [--tf 15m]
Her sembol icin `cache/alertachart/<SEMBOL>/<tf>/overlay_<bar>.json` yazilir (schema 1.0).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "alertachart"


def stamp(bar: str) -> str:
    """2026-10-27T00:15:00.000Z -> 2026-10-27T0015Z"""
    s = bar.replace("-", "").replace(":", "").replace(".000", "")
    s = s.replace("T", "T")[:13]
    return f"{s}Z" if not s.endswith("Z") else s


def meaningful(s: dict) -> bool:
    """Bos payload sembolu iyi overlay'i ezmesin (bar yine de tazelenirdi)."""
    if s.get("w") or s.get("lab") or s.get("venues") or s.get("fund"):
        return True
    for k in ("price", "oi_usd"):
        try:
            if float(s.get(k) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload", nargs="?", default=str(CACHE / "_payload.json"))
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--default-tf-min", type=int, default=15)
    a = ap.parse_args(argv)

    p = Path(a.payload)
    data = json.loads(p.read_text("utf-8"))
    macro = data.get("macro") or {}
    syms = data.get("symbols") or {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if macro:  # sembollerin overlay'i olmasa da makro oyu calissin
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "_macro.json").write_text(
            json.dumps({"asof": now, "macro": macro}, ensure_ascii=False), encoding="utf-8")
    out = []
    skipped = []
    for sym, s in syms.items():
        if not meaningful(s):
            skipped.append(sym)
            continue
        bar = s.get("bar") or now
        o = {
            "schema": "alertachart-overlay/1.0",
            "symbol": sym,
            "coin": sym.replace("USDT.P", "").replace("USDT", ""),
            "tf": a.tf,
            "bar": bar,
            "asof": now,
            "price": s.get("price"),
            "partial": True,
            "w": s.get("w") or [],
            "venues": s.get("venues") or [],
            "ctx1h": {"w": [], "fund": s.get("fund") or {}, "oi_usd": s.get("oi_usd")},
            "lab": s.get("lab") or [],
            "slow": {"macro": macro},
            "errors": s.get("errors") or [],
        }
        d = CACHE / sym / a.tf
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"overlay_{stamp(bar)}.json"
        f.write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
        out.append((sym, bar, len(o["w"]), len(o["lab"]), f.name))

    print(f"{'sembol':16s} {'bar':22s} w  lab  dosya")
    for sym, bar, nw, nl, name in out:
        print(f"{sym:16s} {bar:22s} {nw:<2d} {nl:<4d} {name}")
    print(f"\n{len(out)} overlay yazildi · makro seri {len(macro)} · {CACHE}")
    if skipped:
        print(f"atlandi (bos veri, mevcut overlay korundu): {len(skipped)} sembol · {', '.join(skipped[:10])}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
