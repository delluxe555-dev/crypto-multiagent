"""run_all.py — evrendeki tum semboller icin komiteyi calistirir ve kararlari yazar.

    python tools/run_all.py                 # config/universe.txt, 15m, Telegram acik
    python tools/run_all.py --tf 15m --no-telegram
    python tools/run_all.py --symbols SOLUSDT.P,DOGEUSDT.P

Tarama (`scan.py`) tetik bekler; bu script **tam tur** icindir (elle veya zamanlanmis).
Overlay bayat/yoksa orderflow+sentiment+onchain cekimser kalir; motor bunu kararda yazar.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "dataflows"))

import engine  # noqa: E402


def universe(path: Path, symbols: str | None) -> list[str]:
    if symbols:
        return [s.strip() for s in symbols.split(",") if s.strip()]
    if path.is_file():
        return [ln.strip() for ln in path.read_text("utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    return ["BTCUSDT.P", "ETHUSDT.P"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    ap.add_argument("--universe", type=Path, default=ROOT / "config" / "universe.txt")
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "live")
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args(argv)

    syms = universe(a.universe, a.symbols)
    print(f"{len(syms)} sembol · {a.tf} · telegram {'kapali' if a.no_telegram else 'acik'}\n")
    rows = []
    for sym in syms:
        try:
            dec = engine.decide(sym, a.tf)
            p = engine.write_decision(dec, a.out, notify=not a.no_telegram)
        except Exception as exc:
            print(f"{sym:14s} HATA {exc}")
            continue
        con = dec["consensus"]
        rows.append((sym, dec["action"], dec["mode"], con["buy"], con["sell"], con["hold"],
                     con["share"], (dec.get("levels") or {}).get("rr_net"), dec.get("telegram")))
        print(f"{sym:14s} {dec['action']:5s} {dec['mode']:11s} "
              f"{con['buy']}/{con['sell']}/{con['hold']} %{con['share'] * 100:.0f} "
              f"RR {(dec.get('levels') or {}).get('rr_net', '-')}")

    print("\n" + "-" * 74)
    print(f"{'sembol':14s} {'karar':5s} {'mod':11s} oy        pay   RR    telegram")
    for sym, act, mode, b, s, h, sh, rr, tg in rows:
        t = "-"
        if tg:
            t = (f"msg {tg.get('message_id')}" if tg.get("ok")
                 else f"atlandi:{tg.get('skipped')}" if tg.get("skipped") else f"hata:{tg.get('error')}")
        print(f"{sym:14s} {act:5s} {mode:11s} {b}/{s}/{h:<4d} %{sh * 100:<4.0f} {str(rr):5s} {t}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
