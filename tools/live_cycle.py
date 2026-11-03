"""Canlı döngü: bir sembol için komitenin okuyacağı girdiyi üretir.

Katmanlar:
  1) TEKNİK  — karar TF'sinde (varsayılan 15m) Binance klines + göstergeler + yapı/formasyon
  2) TREND   — 1h ve 4h kapanış/RSI/SMA (yön bağlamı, ucuz)
  3) HIZLI   — AlertaChart 15m katmanı (flow, defter, likidasyon haritası, ısı, balina, Chain Lab)
     + 1h flow özeti + yavaş bağlam (opsiyon/makro/haber) overlay dosyasında varsa

Kullanım (sembol serbest; öncelik sırası yok):
    python tools/live_cycle.py <SEMBOL> --tf 15m
    python tools/live_cycle.py <SEMBOL> --tf 15m --out runs/live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataflows"))
import alertachart_bridge as ac  # noqa: E402

# Kullanıcının AlertaChart'a girdiği kişisel "kritik seviye" komite kanıtı sayılmaz
# (kullanıcı talebi, 2026-10-26). klines/snapshot bunu bu bayrakla atlar.
os.environ["CA_NO_KEYLEVELS"] = "1"

sys.path.insert(0, str(ac.BOT_CODE))
import data  # noqa: E402


def _spot(symbol: str) -> str:
    """Binance spot sembolü (botun klines'ı .P kabul etmiyor)."""
    return symbol.replace(".P", "")


def _klines(symbol: str, interval: str, limit: int = 400):
    return data.add_indicators(data.klines(_spot(symbol), interval=interval, limit=limit))


def tech_block(symbol: str, tf: str) -> str:
    df = _klines(symbol, tf)
    for n in (8, 13, 21):
        df[f"ema{n}"] = df["close"].ewm(span=n, adjust=False).mean()
    tech, _ = data.snapshot(_spot(symbol), df, interval=tf)
    r = df.iloc[-1]
    px = float(r["close"])
    pos = "üstünde" if px > r["ema8"] else "altında"
    spread = (float(r["ema8"]) - float(r["ema21"])) / px * 100
    tech += (
        f"\nEMA8 {r['ema8']:,.2f} · EMA13 {r['ema13']:,.2f} · EMA21 {r['ema21']:,.2f}"
        f" (fiyat EMA8'in {pos}; EMA8-EMA21 farkı {spread:+.2f}%)"
        f"\nATR mesafesi: 1×ATR {float(r['atr14']):,.2f} = %{float(r['atr14']) / px * 100:.2f}"
    )
    return tech


def trend_line(symbol: str, interval: str) -> str:
    try:
        df = _klines(symbol, interval, 400)
        r = df.iloc[-1]
        px = float(r["close"])

        def ch(n):
            return (px / float(df["close"].iloc[-1 - n]) - 1) * 100

        above50 = px > float(r["sma50"])
        above200 = px > float(r["sma200"])
        return (
            f"{interval}: kapanış {px:,.2f} · 1 mum {ch(1):+.2f}% · 8 mum {ch(8):+.2f}% · "
            f"24 mum {ch(24):+.2f}% · RSI {float(r['rsi14']):.0f} · MACD hist {float(r['macd_hist']):+.2f} · "
            f"SMA50 {float(r['sma50']):,.2f} ({'üstü' if above50 else 'altı'}) · "
            f"SMA200 {float(r['sma200']):,.2f} ({'üstü' if above200 else 'altı'}) · "
            f"son24 yüksek/düşük {float(df['high'].iloc[-24:].max()):,.2f}/{float(df['low'].iloc[-24:].min()):,.2f}"
        )
    except Exception as e:
        return f"{interval}: trend hesaplanamadı ({e})"


def slow_block(o: dict) -> str:
    lines = []
    c1 = o.get("ctx1h") or {}
    if c1:
        w = ", ".join(
            f"{x['b']}m px {x.get('px'):+.2f}% CVD {x.get('cvdp'):+.1f}M OI {x.get('oi'):+.2f}% "
            f"liq L {x.get('ll', 0) / 1e6:.2f}M/S {x.get('ls', 0) / 1e6:.2f}M"
            for x in c1.get("w", [])
        )
        lines.append("1h flow: " + w)
        if c1.get("fund"):
            lines.append("Funding (perp): " + " · ".join(f"{k} {v:+.4f}%" for k, v in c1["fund"].items()))
        if c1.get("oi_usd"):
            lines.append(f"Açık pozisyon (toplam): {c1['oi_usd'] / 1e9:.2f} milyar$")
    s = o.get("slow") or {}
    if s.get("news"):
        lines.append("Haberler:")
        for n in s["news"][:3]:
            lines.append(f"  - {n.get('time', '')[:16]} {n.get('title', '')}")
    if s.get("opt"):
        x = s["opt"]
        lines.append(
            "Opsiyon: IV rank {ivr} · IV {iv} · RV {rv} · VRP {vrp} · "
            "25d skew put {sp} / call {sc} · GEX {gex} · max pain {mp}".format(**x)
        )
    if s.get("macro"):
        lines.append("Makro: " + " · ".join(f"{k} {v}" for k, v in s["macro"].items()))
    return "\n".join(lines)


def build(symbol: str, tf: str = "15m") -> tuple[str, dict]:
    overlay = ac.load_overlay(symbol, tf)
    if overlay is None:
        raise SystemExit(f"overlay yok: cache/alertachart/{ac.ac_symbol(symbol)}/{tf}/overlay_*.json")

    now = datetime.now(timezone.utc)
    bar = overlay.get("bar") or "?"
    meta = {
        "schema": "live-cycle/1.0",
        "symbol": ac.ac_symbol(symbol),
        "tf": tf,
        "bar": bar,
        "built_at": now.isoformat(timespec="seconds"),
        "overlay_path": overlay.get("_path"),
    }

    parts = [f"### SEMBOL {ac.ac_symbol(symbol)} · karar TF {tf} · mum {bar}"]
    tech = tech_block(symbol, tf)
    if overlay.get("price"):
        last_close = float(tech.split("Kapanış: ")[1].split()[0].replace(",", "").replace(" ", ""))
        basis = (overlay["price"] / last_close - 1) * 100 if last_close else 0
        tech += f"\nSpot/perp bazı: {basis:+.3f}% (teknik spot mumlardan, karar perp fiyatından)"
    parts.append("\n### 1) TEKNİK (karar TF)\n" + tech)
    parts.append("\n### 2) TREND\n" + trend_line(symbol, "1h") + "\n" + trend_line(symbol, "4h"))
    parts.append("\n### 3) HIZLI KATMAN (AlertaChart " + tf + ")")
    overlay_block, ometa = ac.overlay_text(symbol, tf)
    parts[-1] += "\n" + (overlay_block or ac.render_overlay(overlay))
    sl = slow_block(overlay)
    if sl:
        parts.append("\n### 4) YAVAŞ BAĞLAM\n" + sl)

    meta.update({"overlay_age_min": ometa.get("age_min"), "overlay_stale": ometa.get("stale")})
    parts.append(
        "\n### TAZELİK\n"
        f"overlay yaşı: {ometa.get('age_min')} dk (bayat: {ometa.get('stale')}) · "
        f"üretim: {meta['built_at']}"
    )
    return "\n".join(parts), meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--out", default=str(ROOT / "runs" / "live"))
    a = ap.parse_args(argv)

    text, meta = build(a.symbol, a.tf)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    d = Path(a.out) / stamp
    d.mkdir(parents=True, exist_ok=True)
    safe = ac.ac_symbol(a.symbol).replace(".", "_")
    (d / f"{safe}_input.md").write_text(text, encoding="utf-8")
    (d / f"{safe}_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{d / (safe + '_input.md')}  ({len(text)} karakter)")
    print(f"bayat={meta['overlay_stale']} yaş={meta['overlay_age_min']} dk")


if __name__ == "__main__":
    main()
