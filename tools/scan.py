"""scan.py — hızlı tetik tarayıcısı (5 dakikalık / anlık).

Neden: komiteyi her turda çalıştırmak pahalı. Bu katman yalnız Binance **perp**
mumlarına bakar (AlertaChart'a gitmez, saniyeler sürer) ve "bu sembolde şimdi
bakmaya değer mi?" sorusunu yanıtlar.

Tetik çıktığında:
  - overlay taze ise (varsayılan 15m katman, ≤17 dk) `engine.decide` çalışır ve
    karar yazılır (`--auto`);
  - overlay bayat/yoksa yalnız "overlay tazele" der (AlertaChart'ı asistan çeker).

Kullanım:
    python tools/scan.py --once                       # tek tur
    python tools/scan.py --watch --interval 300        # 5 dakikada bir
    python tools/scan.py --watch --interval 60 --auto  # dakikada bir, tetikte karar
    python tools/scan.py --symbols BTCUSDT.P,ETHUSDT.P --tf 5m
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataflows"))
sys.path.insert(0, str(ROOT / "tools"))
import alertachart_bridge as ac  # noqa: E402
import binance as bn  # noqa: E402

DEFAULT_UNIVERSE = ROOT / "config" / "universe.txt"
LIVE_DIR = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")


def universe(path: Path | None, symbols: str | None) -> list[str]:
    if symbols:
        return [s.strip() for s in symbols.split(",") if s.strip()]
    p = path or DEFAULT_UNIVERSE
    if p.is_file():
        out = [ln.strip() for ln in p.read_text("utf-8").splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
        if out:
            return out
    return ["BTCUSDT.P", "ETHUSDT.P"]


def load(sym: str, interval: str, limit: int = 120) -> pd.DataFrame:
    rows = bn.get_klines(sym.replace(".P", ""), interval, limit, market="perp")
    if not rows:
        rows = bn.get_klines(sym.replace(".P", ""), interval, limit, market="spot")
    else:
        df0 = pd.DataFrame(rows)
        tail = df0.tail(3)
        if len(tail) == 3 and bool((tail["high"] == tail["low"]).all()) and float(tail["volume"].sum()) == 0.0:
            alt = bn.get_klines(sym.replace(".P", ""), interval, limit, market="spot")
            if alt:
                rows = alt
    if not rows:
        raise RuntimeError(f"mum yok: {sym} {interval}")
    df = pd.DataFrame(rows).set_index("open_time")
    # kapanmamis mumu at: tarama her zaman son KAPANAN mumu degerlendirir
    now_ms = pd.Timestamp.now(tz="UTC").value // 1_000_000
    if "close_time" in df.columns and len(df) > 2 and int(df["close_time"].iloc[-1]) > now_ms:
        df = df.iloc[:-1]
    return df


def metrics(df: pd.DataFrame) -> dict:
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    px = float(c.iloc[-1])
    o = float(df["open"].iloc[-1]) if "open" in df else float(c.iloc[-2])
    chg = (px - o) / o * 100 if o else 0.0
    rng = (float(h.iloc[-1]) - float(l.iloc[-1])) / atr if atr else 0.0

    vmed = float(v.iloc[-21:-1].median()) if len(v) > 21 else float(v.median())
    vstd = float(v.iloc[-21:-1].std() or 0) if len(v) > 21 else 0.0
    vz = (float(v.iloc[-1]) - vmed) / vstd if vstd else 0.0

    ema8 = c.ewm(span=8, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    cross = 0
    if ema8.iloc[-1] > ema21.iloc[-1] and ema8.iloc[-2] <= ema21.iloc[-2]:
        cross = 1
    elif ema8.iloc[-1] < ema21.iloc[-1] and ema8.iloc[-2] >= ema21.iloc[-2]:
        cross = -1

    hi20 = float(h.iloc[-21:-1].max()) if len(h) > 21 else float(h.max())
    lo20 = float(l.iloc[-21:-1].min()) if len(l) > 21 else float(l.min())
    brk = "up" if px > hi20 else "down" if px < lo20 else ""

    return {
        "price": px, "chg_pct": chg, "atr": atr,
        "atr_pct": atr / px * 100 if px else 0.0,
        "range_atr": rng, "vol_z": vz, "ema_cross": cross, "break": brk,
        "hi20": hi20, "lo20": lo20,
    }


def triggers(m: dict) -> list[str]:
    t = []
    if abs(m["chg_pct"]) >= m["atr_pct"] and m["atr_pct"]:
        t.append(f"mum {m['chg_pct']:+.2f}% >= 1xATR")
    if m["range_atr"] >= 1.8:
        t.append(f"menzil {m['range_atr']:.1f}xATR")
    if m["break"]:
        t.append(f"20 mum {'ust' if m['break'] == 'up' else 'alt'} kirilimi")
    if m["vol_z"] >= 2.5 and abs(m["chg_pct"]) >= 0.5 * m["atr_pct"]:
        t.append(f"hacim z {m['vol_z']:.1f}")
    if m["ema_cross"] and abs(m["chg_pct"]) >= 0.5 * m["atr_pct"]:
        t.append("EMA8/21 kesisimi")
    return t


def overlay_state(sym: str, tf: str = "15m") -> dict:
    o = ac.load_overlay(sym, tf)
    if not o:
        return {"ok": False, "stale": True, "age_min": None}
    _, meta = ac.overlay_text(sym, tf)
    return {"ok": True, "stale": bool(meta.get("stale")), "age_min": meta.get("age_min"),
            "bar": meta.get("bar")}


def open_counts(out: Path) -> dict:
    """Acik pozisyon sayilari (triggers.json) — portfoy tavani icin."""
    counts = {"open": 0, "long": 0, "short": 0}
    p = out / "triggers.json"
    if not p.is_file():
        return counts
    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return counts
    for pos in (data.get("positions") or {}).values():
        if pos.get("status") != "open":
            continue
        counts["open"] += 1
        if (pos.get("action") or "").upper() in ("SHORT", "SELL"):
            counts["short"] += 1
        else:
            counts["long"] += 1
    return counts


def run_once(symbols: list[str], tf: str, decide_tf: str, auto: bool, out: Path) -> list[dict]:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    print(f"\n[{ts}] tarama {tf} | {len(symbols)} sembol")
    hits = []
    counts = open_counts(out)
    for sym in symbols:
        try:
            m = metrics(load(sym, tf))
        except Exception as exc:  # ağ hatası sembolü atlamasın
            print(f"  {sym:14s} veri yok ({exc})")
            continue
        tg = triggers(m)
        tag = ("TETIK -> " + " | ".join(tg)) if tg else "-"
        print(f"  {sym:14s} {m['price']:>12,.2f}  {m['chg_pct']:+.2f}%  "
              f"ATR {m['atr_pct']:.2f}%  menzil {m['range_atr']:.1f}x  {tag}")
        if not tg:
            continue
        ov = overlay_state(sym, decide_tf)
        rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "symbol": sym, "tf": tf, "price": m["price"], "triggers": tg,
               "overlay": ov}
        if auto:
            import engine
            try:
                dec = engine.decide(sym, decide_tf, open_counts=counts)
                p = engine.write_decision(dec, out)
                state = "taze" if (ov["ok"] and not ov["stale"]) else "bayat/yok"
                rec["decision"] = {"action": dec["action"], "mode": dec["mode"],
                                   "share": dec["consensus"]["share"], "overlay": state,
                                   "rr_net": dec.get("levels", {}).get("rr_net"),
                                   "path": str(p)}
                # piyasa emri aninda doldurulur: portfoy sayacina ekle
                if dec.get("mode") == "market" and dec.get("action") in ("LONG", "SHORT", "BUY", "SELL"):
                    counts["open"] += 1
                    if (dec.get("action") or "").upper() in ("SHORT", "SELL"):
                        counts["short"] += 1
                    else:
                        counts["long"] += 1
                print(f"    -> {dec['action']} {dec['mode']} | pay %{dec['consensus']['share'] * 100:.0f}"
                      f" | overlay {state} | yazildi {p.name}")
            except Exception as exc:  # tek sembol karari turu durdurmasin
                print(f"    -> karar hatasi: {type(exc).__name__}: {exc}")
                rec["decision_error"] = f"{type(exc).__name__}: {exc}"
        hits.append(rec)
    if hits:
        log = out / "scan.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            for rec in hits:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return hits


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="virgülle ayrılmış liste")
    ap.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    ap.add_argument("--tf", default="5m", help="tarama mumu (varsayılan 5m)")
    ap.add_argument("--decide-tf", default="15m")
    ap.add_argument("--out", type=Path, default=LIVE_DIR)
    ap.add_argument("--auto", action="store_true", help="tetikte komiteyi çalıştır")
    ap.add_argument("--once", action="store_true", help="tek tur (varsayılan)")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=300, help="saniye (varsayılan 300 = 5 dk)")
    a = ap.parse_args(argv)

    syms = universe(a.universe, a.symbols)
    if a.watch:
        print(f"izleme: {', '.join(syms)} | her {a.interval}s | karar TF {a.decide_tf}")
        try:
            while True:
                run_once(syms, a.tf, a.decide_tf, a.auto, a.out)
                time.sleep(max(20, a.interval))
        except KeyboardInterrupt:
            print("\ndurdu")
    else:
        run_once(syms, a.tf, a.decide_tf, a.auto, a.out)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
