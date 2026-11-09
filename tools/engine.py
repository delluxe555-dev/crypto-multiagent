"""engine.py — komite karar motoru (benim mantığım).

Grok'un bot karar katmanı (trader.py / risk_rules.py / hakem / agents.py) **kullanılmaz**.
Girdi: Binance perp mumları (kendi veri sarmalayıcım) + varsa taze AlertaChart overlay.
Çıktı: `decision/1.0` şemasında karar JSON'u + journal satırı.

Mantık özeti (agents/committee.md ile aynı kurallar):
  1. 8 oy veren ajan: teknik, demark (TD Sequential), on-chain, sentiment, orderflow,
     makro, boğa, ayı; trader yalnız danışma oyu. Risk ve Meta sadece veto eder.
  2. Yön payı >= %55 ve en az 4 geçerli oy -> aday; aksi halde HOLD.
  3. Risk katmanı seviyeleri deterministik üretir: yapısal veya ATR stop (geniş olan),
     likidite kümesi / swing hedefi, RR_net ve maliyet kapısı.
  4. Piyasa emri yalnız: veto yok + RR_net >= piyasa tabanı (max(1.75, koşullu+0.25))
     + maliyet/ATR <= 0.25. Aksi halde tetikli (koşullu) giriş; dinamik RR tabanı (1.35-1.90).
  5. Veri eksikse ajan çekimser kalır, uydurmaz; overlay bayatsa orderflow/sentiment
     oyları sayılmaz ve risk 0.5R'a iner.

Kullanım:
    python tools/engine.py BTCUSDT.P --tf 15m
    python tools/engine.py ETHUSDT.P --tf 15m --no-write
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataflows"))
sys.path.insert(0, str(ROOT / "tools"))
import alertachart_bridge as ac  # noqa: E402
import binance as bn  # noqa: E402
import demark as tdseq  # noqa: E402

ENGINE = "committee-engine/1.0"
LIVE_DIR = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")

CFG = {
    "ema": (8, 13, 21),
    "sma": (50, 200),
    "atr_n": 14,
    "rsi_n": 14,
    "cost_pct": 0.10,              # tur maliyeti: taker %0.045x2 + kayma
    "cost_atr_market_max": 0.25,   # piyasa emri icin maliyet/ATR tavani
    "cost_atr_veto": 0.50,         # bunun ustunde hic islem yok
    "rr_base": 1.35,               # koşullu giriş tabanı (kendi kalibrasyonum)
    "rr_cap": 1.90,
    "rr_market_base": 1.75,
    "atr_mult": {"5m": 2.2, "15m": 2.0, "1h": 1.75, "4h": 1.5},
    "swing_buffer_atr": 0.25,
    "thresh": 0.55,
    "min_votes": 5,
    "min_directional": 3,
    "valid_bars": 8,
    "max_sl_atr": 3.0,
    "min_sl_pct": 0.30,           # SL girişten en az %0,30 uzakta (yuvarlama sıfırlamasın)
}

TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}


# --------------------------------------------------------------------------- veri
def _dead(df: pd.DataFrame) -> bool:
    """Perp beslemesi bazen hacimsiz/duz mumlar dondurur; o zaman spot'a dusulur."""
    tail = df.tail(3)
    if len(tail) < 3 or "volume" not in tail:
        return False
    flat = bool((tail["high"] == tail["low"]).all())
    return flat and float(tail["volume"].sum()) == 0.0


def load(symbol: str, interval: str, limit: int = 400) -> tuple[pd.DataFrame, str]:
    """Perp mumları (karar fiyatı perp). Perp ölü/engelliyse spot'a düşer ve bunu söyler."""
    sym = symbol.replace(".P", "")
    rows = bn.get_klines(sym, interval, limit, market="perp")
    src = "perp"
    if not rows:
        rows = bn.get_klines(sym, interval, limit, market="spot")
        src = "spot (perp alınamadı)"
    else:
        df0 = pd.DataFrame(rows).set_index("open_time")
        if _dead(df0):
            alt = bn.get_klines(sym, interval, limit, market="spot")
            if alt:
                rows, src = alt, "spot (perp mumları ölü)"
    if not rows:
        # SystemExit degil: cagiran dongu (scan/trigger_watch) oluyu atlayip devam etsin
        raise RuntimeError(f"mum alınamadı: {sym} {interval}")
    df = pd.DataFrame(rows).set_index("open_time")
    # henüz kapanmamış mum karara girmez
    now_ms = pd.Timestamp.now(tz="UTC").value // 1_000_000
    if "close_time" in df.columns and len(df) > 2 and int(df["close_time"].iloc[-1]) > now_ms:
        df = df.iloc[:-1]
    return indicators(df), src


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l = df["close"], df["high"], df["low"]
    for n in CFG["ema"]:
        df[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    for n in CFG["sma"]:
        df[f"sma{n}"] = c.rolling(n).mean()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / CFG["atr_n"], adjust=False).mean()
    d = c.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    rs = up.ewm(alpha=1 / 14, adjust=False).mean() / dn.ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + rs)
    df["macd"] = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd"].ewm(span=9, adjust=False).mean()
    return df


def swings(df: pd.DataFrame, k: int = 2, lookback: int = 200):
    d = df.tail(lookback)
    hi, lo = [], []
    for i in range(k, len(d) - k):
        w_h = d["high"].iloc[i - k:i + k + 1]
        w_l = d["low"].iloc[i - k:i + k + 1]
        if d["high"].iloc[i] == w_h.max():
            hi.append(float(d["high"].iloc[i]))
        if d["low"].iloc[i] == w_l.min():
            lo.append(float(d["low"].iloc[i]))
    return hi, lo


def structure(df: pd.DataFrame) -> tuple[str, int]:
    hi, lo = swings(df)
    if len(hi) < 2 or len(lo) < 2:
        return "belirsiz", 0
    hh, hl = hi[-1] > hi[-2], lo[-1] > lo[-2]
    if hh and hl:
        return "HH/HL", +1
    if not hh and not hl:
        return "LH/LL", -1
    return "karışık", 0


# --------------------------------------------------------------------------- ajanlar
@dataclass
class View:
    name: str
    side: str = "HOLD"
    conf: float = 0.0
    note: str = ""
    abstain: bool = False
    advisory: bool = False   # türev görüş (boğa/ayı/trader): oya sayılmaz, çift sayım olmasın

    def as_dict(self) -> dict:
        d = {"side": self.side, "conf": round(self.conf, 2), "note": self.note}
        if self.abstain:
            d["abstain"] = True
        if self.advisory:
            d["advisory"] = True
        return d


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def a_technical(d15: pd.DataFrame, d1h: pd.DataFrame, d4h: pd.DataFrame) -> View:
    r = d15.iloc[-1]
    px = float(r["close"])
    s = 0.0
    bits = []

    s += 1 if px > r["ema8"] else -1
    if r["ema8"] > r["ema13"] > r["ema21"]:
        s += 1.5
        bits.append("15m EMA8>13>21")
    elif r["ema8"] < r["ema13"] < r["ema21"]:
        s -= 1.5
        bits.append("15m EMA8<13<21")

    slope = (float(r["ema21"]) - float(d15["ema21"].iloc[-21])) / px * 100
    if abs(slope) > 0.02:
        s += 1 if slope > 0 else -1
        bits.append(f"EMA21 eğimi {slope:+.2f}%")

    st, sgn = structure(d15)
    s += 1.5 * sgn
    bits.append(f"15m yapı {st}")

    if r["rsi"] > 55:
        s += 0.5
    elif r["rsi"] < 45:
        s -= 0.5

    for d, tf in ((d1h, "1h"), (d4h, "4h")):
        x = d.iloc[-1]
        s += 1 if px > x["sma50"] else -1
        s += 1 if x["sma50"] > x["sma200"] else -1
        s += 0.5 if x["macd_hist"] > 0 else -0.5
        bits.append(f"{tf} RSI {x['rsi']:.0f}")

    side = "BUY" if s > 0 else "SELL" if s < 0 else "HOLD"
    return View("teknik", side, min(0.9, 0.35 + 0.055 * abs(s)), "; ".join(bits[:5]))


def a_demark(d15: pd.DataFrame, d1h: pd.DataFrame) -> View:
    """TD Sequential / TRP: Setup 9, Countdown 13 ve dönüş onayları.

    Tükeniş mantığı: alım 9/CD13 düşüşün sonuna (BUY), satım 9/CD13 yükselişin
    sonuna (SELL) işaret eder. Ham 9 tek başına giriş sayılmaz (eşik 1.0).
    """
    t15 = tdseq.run(d15)
    t1h = tdseq.run(d1h)

    def score(t: dict, scale: float) -> tuple[float, list[str]]:
        s, bits = 0.0, []

        def add(x: float, txt: str) -> None:
            nonlocal s
            s += x
            bits.append(txt)

        if t["buy9139"]:
            add(2.0 * scale, "9–13–9 alım onayı")
        if t["sell9139"]:
            add(-2.0 * scale, "9–13–9 satım onayı")
        if t["buy13"]:
            add(1.6 * scale, "alım CD13")
        if t["sell13"]:
            add(-1.6 * scale, "satım CD13")
        if t["buy_flip"]:
            add(1.4 * scale, "13→ters 1 alım")
        if t["sell_flip"]:
            add(-1.4 * scale, "13→ters 1 satım")
        if t["buy9"]:
            add((1.2 if t["buyM9"] else 0.9) * scale, "alım M9" if t["buyM9"] else "alım 9")
        if t["sell9"]:
            add(-(1.2 if t["sellM9"] else 0.9) * scale, "satım M9" if t["sellM9"] else "satım 9")
        # 13'e yaklaşan aktif countdown: yön vermez, hafif eğilim
        for sgn, key, label in ((1, "buy_cd", "alım"), (-1, "sell_cd", "satım")):
            cd = t.get(key)
            if cd and cd >= 8:
                add(sgn * 0.35 * scale * (cd / 13.0), f"{label} CD {cd}/13")
        return s, bits

    s15, b15 = score(t15, 1.0)
    s1h, b1h = score(t1h, 0.5)
    s = s15 + s1h
    bits = b15 + [f"1h {x}" for x in b1h]

    events = ("buy9", "sell9", "buy13", "sell13", "buy_flip", "sell_flip",
              "buy9139", "sell9139")
    has = (any(t15[k] for k in events) or any(t1h[k] for k in events)
           or (t15.get("buy_cd") or 0) >= 8 or (t15.get("sell_cd") or 0) >= 8
           or (t1h.get("buy_cd") or 0) >= 8 or (t1h.get("sell_cd") or 0) >= 8)
    if not has:
        return View("demark", abstain=True,
                    note=f"olay yok (15m alım {t15['buy_setup']}/9 · satım {t15['sell_setup']}/9)")

    if abs(s) >= 1.0:
        side = "BUY" if s > 0 else "SELL"
        return View("demark", side, min(0.85, 0.3 + 0.14 * abs(s)), "; ".join(bits[:5]))
    return View("demark", "HOLD", 0.3, "; ".join(bits[:5]) or "TD nötr")


def a_orderflow(o: dict | None) -> View:
    if not o:
        return View("orderflow", abstain=True, note="overlay yok")
    w = o.get("w") or []
    if not w:
        return View("orderflow", abstain=True, note="flow serisi yok")
    w12 = next((x for x in w if x.get("b") == 12), w[-1])
    cvdp, cvds = w12.get("cvdp"), w12.get("cvds")
    if cvdp is None and cvds is None:
        return View("orderflow", abstain=True, note="CVD yok")

    s = 0.0
    bits = []
    if cvdp is not None:
        s += 1.5 * _sign(cvdp)
        bits.append(f"CVD perp 12m {cvdp:+.1f}M")
    if cvds is not None:
        s += 1.0 * _sign(cvds)
        bits.append(f"CVD spot {cvds:+.1f}M")
    if cvdp is not None and cvds is not None and _sign(cvdp) != _sign(cvds):
        s *= 0.6
        bits.append("spot/perp ayrışması")

    book = ((o.get("book") or {}).get("d") or {})
    imb = float(book.get("imbalance_pct") or 0)
    s += max(-1.0, min(1.0, imb / 20))
    if imb:
        bits.append(f"defter {imb:+.1f}%")

    net = float((o.get("whales") or {}).get("net") or 0)
    if abs(net) > 5e6:
        s += 1.0 * _sign(net)
        bits.append(f"balina net {net / 1e6:+.1f}M")

    side = "BUY" if s > 0.4 else "SELL" if s < -0.4 else "HOLD"
    return View("orderflow", side, min(0.85, 0.3 + 0.12 * abs(s)), "; ".join(bits))


def a_sentiment(o: dict | None) -> View:
    if not o:
        return View("sentiment", abstain=True, note="overlay yok")
    c1 = o.get("ctx1h") or {}
    fund = c1.get("fund") or {}
    w = c1.get("w") or []
    if not fund and not w:
        return View("sentiment", abstain=True, note="funding/OI yok")

    s, bits = 0.0, []
    if fund:
        avg = sum(fund.values()) / len(fund)
        if abs(avg) > 0.03:
            s -= 1.2 * _sign(avg)  # aşırı funding = kalabalık taraf, kontraryen
            bits.append(f"funding ort {avg:+.4f}% (kalabalık {'long' if avg > 0 else 'short'})")
    w12 = next((x for x in w if x.get("b") == 12), w[-1] if w else None)
    if w12 and w12.get("oi") is not None and w12.get("px") is not None:
        s += 1.0 * _sign(w12["oi"]) * _sign(w12["px"])
        bits.append(f"OI {w12['oi']:+.2f}% · fiyat {w12['px']:+.2f}%")

    side = "BUY" if s > 0.3 else "SELL" if s < -0.3 else "HOLD"
    return View("sentiment", side, min(0.7, 0.3 + 0.15 * abs(s)), "; ".join(bits))


def _global_macro(max_age_h: float = 6.0) -> dict:
    """Overlay yoksa/eksikse paylasilan makro anlik goruntusu (apply_payload yazar).

    Bayat makro (varsayilan 6 saatten eski) kullanilmaz: eski gunluk degisim
    makro oyunu yanlis yone cekmesin.
    """
    try:
        d = json.loads((ROOT / "cache" / "alertachart" / "_macro.json").read_text("utf-8"))
        asof = d.get("asof")
        if asof:
            t = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
            if age_h > max_age_h:
                return {}
        return d.get("macro") or {}
    except Exception:
        return {}


def a_macro(o: dict | None) -> View:
    """Makro: get_macro serilerinin günlük değişimi (yön, seviye değil)."""
    mac = ((o or {}).get("slow") or {}).get("macro") or _global_macro()
    if not mac:
        return View("makro", abstain=True, note="makro seri yok")

    def ch(sym: str) -> float:
        return float((mac.get(sym) or {}).get("change") or 0)

    s, bits = 0.0, []
    y10 = ch("US10Y")
    if abs(y10) >= 0.02:
        s -= 1.0 * _sign(y10)
        bits.append(f"US10Y {y10:+.2f} yp")
    y2 = ch("US02Y")
    if abs(y2) >= 0.02:
        s -= 0.5 * _sign(y2)
        bits.append(f"US02Y {y2:+.2f}")
    hy = ch("BAMLH0A0HYM2")
    if abs(hy) >= 0.02:
        s -= 0.7 * _sign(hy)          # spread genişlemesi = risk-off
        bits.append(f"HY spread {hy:+.2f} yp")
    nfci = ch("NFCI")
    if abs(nfci) >= 0.01:
        s -= 0.5 * _sign(nfci)        # finansal koşullar sıkılaşıyor
        bits.append(f"NFCI {nfci:+.3f}")
    liq = ch("USNETLIQ")
    if liq:
        s += 0.3 * _sign(liq)         # Fed bilançosu
        bits.append(f"Fed net likidite {liq:+.0f}")

    if abs(s) < 0.35:
        return View("makro", "HOLD", 0.3, "; ".join(bits) or "makro nötr")
    side = "BUY" if s > 0 else "SELL"
    return View("makro", side, min(0.7, 0.3 + 0.12 * abs(s)), "; ".join(bits))


def a_onchain(o: dict | None) -> View:
    """Temel/On-chain: Chain Lab modülleri (flow, spot/perp liderliği, pozisyon akışı)."""
    rows = {r.get("m"): r for r in ((o or {}).get("lab") or []) if r.get("m")}
    if not rows:
        return View("onchain", abstain=True, note="Chain Lab yok")

    def val(key: str):
        r = rows.get(key) or {}
        return r.get("v")

    s, bits = 0.0, []
    f = val("flow_score")
    if f is not None:
        if f >= 55:
            s += 1.2
            bits.append(f"flow {f:.0f} (alıcı)")
        elif f <= 45:
            s -= 1.2
            bits.append(f"flow {f:.0f} (satıcı)")

    sp = val("spot_perp_lead")
    if sp is not None:
        s += 0.8 * max(-1.0, min(1.0, abs(sp) / 0.5)) * _sign(sp)
        bits.append(f"spot/perp liderliği {sp:+.2f}")

    npf = val("net_position_flow")
    if npf is not None and abs(npf) > 0:
        s += 0.8 * _sign(npf)          # negatif = net short açılışı
        bits.append(f"net pozisyon {npf:+.0f}")

    cb = val("coinbase_premium")
    if cb is not None and cb != 0:
        s += 0.5 * max(-1.0, min(1.0, abs(cb) / 0.02)) * _sign(cb)
        bits.append(f"Coinbase primi {cb:+.3f}%")

    lev = rows.get("leverage_saturation") or {}
    rank = 0
    for tok in (lev.get("r") or "").replace("%", " ").split():
        if "/100" in tok:
            try:
                rank = int(tok.split("/")[0])
            except ValueError:
                rank = 0
    fund = ((o or {}).get("ctx1h") or {}).get("fund") or {}
    favg = sum(fund.values()) / len(fund) if fund else 0.0
    if rank >= 90 and favg > 0:
        s -= 0.5                     # kaldıraç doygun + long'lar ödüyor = kalabalık
        bits.append(f"kaldıraç {rank}/100 + funding {favg:+.3f}%")

    sq = val("squeeze_risk")
    if sq is not None and abs(sq) >= 45:
        s += 0.6 * max(-1.0, min(1.0, abs(sq) / 70)) * _sign(sq)
        bits.append(f"sıkışma {sq:+.0f}")

    side = "BUY" if s > 0.35 else "SELL" if s < -0.35 else "HOLD"
    return View("onchain", side, min(0.75, 0.3 + 0.12 * abs(s)), "; ".join(bits))


def a_thesis(o: dict | None, d15: pd.DataFrame, bull: bool) -> View:
    """Boğa/Ayı: aynı kanıtı kendi yönünden sayar, kanıt yoksa HOLD."""
    r = d15.iloc[-1]
    pts, notes = 0, []
    w12 = None
    if o:
        w = o.get("w") or []
        w12 = next((x for x in w if x.get("b") == 12), w[-1] if w else None)
    st, sgn = structure(d15)
    px = float(r["close"])

    feats = [
        (True, px > r["ema8"], "fiyat EMA8 üstü", "fiyat EMA8 altı"),
        (True, r["ema8"] > r["ema21"], "EMA8>EMA21", "EMA8<EMA21"),
        (True, r["rsi"] > 50, "RSI>50", "RSI<50"),
        (True, st == "HH/HL", "HH/HL yapı", "HH/HL yok"),
        (w12 is not None, bool(w12 and (w12.get("cvdp") or 0) > 0), "CVD perp pozitif", "CVD perp negatif"),
        (w12 is not None, bool(w12 and (w12.get("cvds") or 0) > 0), "CVD spot pozitif", "CVD spot negatif"),
        (bool(((o or {}).get("book") or {}).get("d")),
         float(((o or {}).get("book") or {}).get("d", {}).get("imbalance_pct", 0) or 0) > 0,
         "defter alıcı ağır", "defter satıcı ağır"),
        (bool((o or {}).get("whales")),
         float(((o or {}).get("whales") or {}).get("net", 0) or 0) > 0,
         "balina net alıcı", "balina net satıcı"),
    ]
    for has, ok, lab_t, lab_f in feats:
        if not has:
            continue
        if ok == bull:
            pts += 1
            notes.append(lab_t if bull else lab_f)

    name = "boğa" if bull else "ayı"
    if pts >= 3:
        return View(name, "BUY" if bull else "SELL", min(0.75, 0.25 + 0.1 * pts), ", ".join(notes))
    return View(name, "HOLD", 0.3, f"{'boğa' if bull else 'ayı'} kanıtı zayıf ({pts} madde)")


def a_trader(views: list[View]) -> View:
    wts = {"teknik": 1.3, "demark": 1.0, "orderflow": 1.3, "sentiment": 0.8, "makro": 0.6,
           "onchain": 0.6, "boğa": 0.5, "ayı": 0.5}
    s = 0.0
    for v in views:
        if v.abstain or v.side == "HOLD":
            continue
        s += wts.get(v.name, 0.5) * v.conf * (1 if v.side == "BUY" else -1)
    side = "BUY" if s > 0 else "SELL" if s < 0 else "HOLD"
    return View("trader", side, min(0.85, abs(s) / 2), f"net eğilim {s:+.2f}", advisory=True)


# --------------------------------------------------------------------------- risk
def _tick_for(px: float) -> float:
    """Fiyat ölçeğine göre yuvarlama adımı (~5 anlamlı basamak).

    Eski sabit 0,001 adımı DOGE/PENGU/PUMP gibi küçük fiyatlı coinlerde tüm
    seviyeleri 0'a yuvarlıyor, SL girişe eşit çıkıp anında tetikleniyordu.
    Örnek: 0,07091 → 0,00001 · 0,003691 → 0,000001 · 5,03e-06 → 1e-10.
    """
    try:
        px = abs(float(px))
    except (TypeError, ValueError):
        return 0.01
    if px <= 0 or px != px:  # 0 / NaN
        return 1e-8
    return 10.0 ** (math.floor(math.log10(px)) - 4)


def _round_tick(px: float) -> float:
    tick = _tick_for(px)
    return round(round(px / tick) * tick, 12)


def rr_floor(share: float, fresh: bool, cost_atr: float) -> float:
    """Koşullu giriş RR tabanı — kanıt zayıfladıkça yükselir (kendi kalibrasyonum)."""
    rr = CFG["rr_base"]
    if share < 0.70:
        rr += 0.15            # uzlaşma zayıf
    if not fresh:
        rr += 0.15            # yarım kanıt
    if cost_atr > 0.35:
        rr += 0.10            # maliyet ATR'nin büyük kısmı
    return round(min(rr, CFG["rr_cap"]), 2)


def rr_market_floor(rr_c: float) -> float:
    return round(min(max(CFG["rr_market_base"], rr_c + 0.25), 2.2), 2)


def levels(side: str, entry: float, d15: pd.DataFrame, o: dict | None,
           rr_min: float | None = None) -> dict:
    atr = float(d15["atr"].iloc[-1])
    hi, lo = swings(d15)
    buf = CFG["swing_buffer_atr"] * atr
    mult = CFG["atr_mult"].get("15m", 2.0)

    if side == "SELL":
        atr_sl = entry + mult * atr
        near_hi = [x for x in hi if entry < x <= atr_sl]
        if near_hi:
            sl = min(max(near_hi) + buf, entry + CFG["max_sl_atr"] * atr)
        else:
            sl = atr_sl
        sl = max(sl, entry + 0.3 * atr)
        # SL girişe çok yaklaşmasın: yuvarlama sonrası sıfır mesafe/immediate SL olmasın
        sl = max(sl, entry + min(CFG["min_sl_pct"] / 100 * entry, CFG["max_sl_atr"] * atr))
        risk = sl - entry
        raw = set()
        lm = (o or {}).get("lm") or {}
        for c in lm.get("below") or []:
            if c.get("distance_pct", 0) < 0 and (c.get("est_usd") or 0) >= 15e6:
                raw.add(_round_tick((c["price_from"] + c["price_to"]) / 2))
        for wall in ((o or {}).get("heat") or {}).get("bid") or []:
            if (wall.get("present_pct") or 0) >= 60:
                raw.add(_round_tick(float(wall["price"])))
        raw |= {_round_tick(x) for x in lo if x < entry}
        cands = sorted((x for x in raw if entry - 4 * risk <= x <= entry - 0.3 * risk), reverse=True)
    else:
        atr_sl = entry - mult * atr
        near_lo = [x for x in lo if atr_sl <= x < entry]
        if near_lo:
            sl = max(min(near_lo) - buf, entry - CFG["max_sl_atr"] * atr)
        else:
            sl = atr_sl
        sl = min(sl, entry - 0.3 * atr)
        # SL girişe çok yaklaşmasın: yuvarlama sonrası sıfır mesafe/immediate SL olmasın
        sl = min(sl, entry - min(CFG["min_sl_pct"] / 100 * entry, CFG["max_sl_atr"] * atr))
        risk = entry - sl
        raw = set()
        lm = (o or {}).get("lm") or {}
        for c in lm.get("above") or []:
            if c.get("distance_pct", 0) > 0 and (c.get("est_usd") or 0) >= 15e6:
                raw.add(_round_tick((c["price_from"] + c["price_to"]) / 2))
        for wall in ((o or {}).get("heat") or {}).get("ask") or []:
            if (wall.get("present_pct") or 0) >= 60:
                raw.add(_round_tick(float(wall["price"])))
        raw |= {_round_tick(x) for x in hi if x > entry}
        cands = sorted(x for x in raw if entry + 0.3 * risk <= x <= entry + 4 * risk)

    cost = CFG["cost_pct"] / 100 * entry

    def rr_net(px: float) -> float:
        if not risk:
            return 0.0
        d = (entry - px) if side == "SELL" else (px - entry)
        return (d - cost) / (risk + cost)

    # hedef: RR eşiğini karşılayan EN YAKIN seviye; yoksa ATR tabanlı varsayılan
    rr_min = CFG["rr_base"] if rr_min is None else rr_min
    good = [x for x in cands if rr_net(x) >= rr_min]
    if good:
        tp1 = good[0]
        later = [x for x in good[1:] if abs(x - tp1) >= 0.5 * risk]
        tp2 = later[0] if later else (tp1 - 1.0 * risk if side == "SELL" else tp1 + 1.0 * risk)
    else:
        tp1 = entry - 1.5 * risk if side == "SELL" else entry + 1.5 * risk
        tp2 = entry - 2.5 * risk if side == "SELL" else entry + 2.5 * risk
    if side == "SELL":
        rr_g = (entry - tp1) / risk if risk else 0
        rr_n = (entry - tp1 - cost) / (risk + cost) if risk else 0
    else:
        rr_g = (tp1 - entry) / risk if risk else 0
        rr_n = (tp1 - entry - cost) / (risk + cost) if risk else 0

    entry_r = _round_tick(entry)
    sl_r = _round_tick(sl)
    tp1_r = _round_tick(tp1)
    tp2_r = _round_tick(tp2)
    tick = _tick_for(entry)
    if side == "SELL":
        sl_r = max(sl_r, entry_r + tick)
        tp1_r = min(tp1_r, entry_r - tick)
        tp2_r = min(tp2_r, tp1_r - tick)
    else:
        sl_r = min(sl_r, entry_r - tick)
        tp1_r = max(tp1_r, entry_r + tick)
        tp2_r = max(tp2_r, tp1_r + tick)

    return {
        "entry": entry_r, "sl": sl_r,
        "tp1": tp1_r, "tp2": tp2_r,
        "atr": atr, "risk": risk, "rr_gross": round(rr_g, 2), "rr_net": round(rr_n, 2),
        "cost_pct": CFG["cost_pct"], "cost_atr": round(CFG["cost_pct"] / (atr / entry * 100), 2),
        "sl_atr": round(risk / atr, 2) if atr else 0,
    }


def risk_gate(side: str, lv: dict, rr_min: float | None = None) -> tuple[bool, list[str]]:
    rr_min = CFG["rr_base"] if rr_min is None else rr_min
    v = []
    if lv["rr_net"] < rr_min:
        v.append(f"RR_net {lv['rr_net']} < {rr_min}")
    if lv["cost_atr"] > CFG["cost_atr_veto"]:
        v.append(f"maliyet/ATR {lv['cost_atr']} > {CFG['cost_atr_veto']}")
    if lv["sl_atr"] > CFG["max_sl_atr"]:
        v.append(f"SL {lv['sl_atr']}×ATR > {CFG['max_sl_atr']}")
    return (len(v) == 0), v


def meta_gate(o: dict | None, fresh: bool, side: str, d4h: pd.DataFrame) -> tuple[bool, list[str]]:
    v = []
    if not fresh:
        v.append("overlay yok/bayat → orderflow-sentiment kanıtı yok")
    x = d4h.iloc[-1]
    px = float(d4h["close"].iloc[-1])
    if side == "BUY" and x["sma50"] < x["sma200"] and px < x["sma50"]:
        v.append("4h trend karşı yönde")
    if side == "SELL" and x["sma50"] > x["sma200"] and px > x["sma50"]:
        v.append("4h trend karşı yönde")
    return (len(v) == 0), v


def journal_bias(side: str) -> tuple[bool, float, int]:
    """Son 30 kararın >%70'i aynı yöndeyse yanlılık freni (protokol md.5)."""
    p = LIVE_DIR / "journal.jsonl"
    if not p.exists():
        return False, 0.0, 0
    rows = []
    for line in p.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        a = r.get("action")
        if a in ("SHORT", "LONG"):
            rows.append(a)
    rows = rows[-30:]
    if len(rows) < 20:
        return False, 0.0, len(rows)
    same = sum(1 for a in rows if (a == "SHORT") == (side == "SELL"))
    pct = same / len(rows)
    return pct > 0.70, pct, len(rows)


# --------------------------------------------------------------------------- komite
def decide(symbol: str, tf: str = "15m", use_overlay: bool = True) -> dict:
    d15, src15 = load(symbol, tf)
    d1h, _ = load(symbol, "1h", 400)
    d4h, _ = load(symbol, "4h", 400)

    o, ometa = None, {"stale": True, "age_min": None}
    if use_overlay:
        o = ac.load_overlay(symbol, tf)
        if o is not None:
            _, ometa = ac.overlay_text(symbol, tf)
    fresh = bool(o) and not ometa.get("stale", True)
    ov = o if fresh else None

    views = [
        a_technical(d15, d1h, d4h),
        a_demark(d15, d1h),
        a_onchain(ov),
        a_sentiment(ov),
        a_orderflow(ov),
        a_macro(ov),
    ]
    views.append(a_thesis(ov, d15, bull=True))
    views.append(a_thesis(ov, d15, bull=False))
    views.append(a_trader(views))

    named = {v.name: v for v in views}
    voters = [v for v in views if not v.abstain and not v.advisory]
    valid = voters
    buy = sum(1 for v in valid if v.side == "BUY")
    sell = sum(1 for v in valid if v.side == "SELL")
    hold = len(valid) - buy - sell
    dirn = buy + sell
    share = (max(buy, sell) / dirn) if dirn else 0.0
    cand = "BUY" if buy > sell else "SELL" if sell > buy else "HOLD"
    enough = (fresh and len(valid) >= CFG["min_votes"] and dirn >= CFG["min_directional"]
              and share >= CFG["thresh"] and cand != "HOLD")

    px = float(d15["close"].iloc[-1])
    bar = datetime.fromtimestamp(int(d15.index[-1]) / 1000, tz=timezone.utc)
    dec = {
        "schema": "decision/1.0", "engine": ENGINE,
        "symbol": ac.ac_symbol(symbol), "tf": tf, "bar": bar.isoformat(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "price": px, "price_source": src15,
        "overlay": {"path": (o or {}).get("_path"), "age_min": ometa.get("age_min"),
                    "stale": ometa.get("stale"), "used": fresh},
        "action": "HOLD", "mode": "none", "trigger": None,
        "consensus": {"buy": buy, "sell": sell, "hold": hold, "valid_votes": len(valid),
                      "directional": dirn, "share": round(share, 3), "candidate": cand,
                      "advisory": {v.name: v.side for v in views if v.advisory}},
        "votes": {v.name: v.as_dict() for v in views},
        "vetoes": [], "notes": [],
    }

    if not enough:
        why = []
        if not fresh:
            why.append("overlay taze değil (sinyal için taze overlay şart)")
        if len(valid) < CFG["min_votes"]:
            why.append(f"geçerli oy {len(valid)} < {CFG['min_votes']} (veri eksik)")
        if dirn < CFG["min_directional"]:
            why.append(f"yön oyu {dirn} < {CFG['min_directional']}")
        if dirn and share < CFG["thresh"]:
            why.append(f"yön payı %{share * 100:.0f} < %{CFG['thresh'] * 100:.0f}")
        if cand == "HOLD":
            why.append("yönler eşit")
        dec["notes"].append("; ".join(why) or "aday yok")
        dec["mode"] = "none"
        dec["consensus"]["directional"] = dirn
        dec["disclaimer"] = "Araştırma/kağıt işlem çıktısı; yatırım tavsiyesi değildir."
        return dec

    atr_now = float(d15["atr"].iloc[-1])
    cost_atr_now = CFG["cost_pct"] / (atr_now / px * 100) if atr_now else 99.0
    rr_c = rr_floor(share, fresh, cost_atr_now)
    rr_m = rr_market_floor(rr_c)
    dec["rr_floor"] = rr_c
    dec["rr_market_floor"] = rr_m
    lv = levels(cand, px, d15, ov, rr_c)
    r_ok, r_v = risk_gate(cand, lv, rr_c)
    m_ok, m_v = meta_gate(ov, fresh, cand, d4h)
    bias, bpct, bn = journal_bias(cand)
    if bias:
        m_ok = False
        m_v.append(f"son {bn} kararın %{bpct * 100:.0f}'i aynı yönde (yanlılık freni)")
    dec["levels"] = {k: lv[k] for k in ("entry", "sl", "tp1", "tp2", "rr_gross", "rr_net",
                                       "cost_pct", "cost_atr", "sl_atr", "atr")}
    if not r_ok:
        dec["vetoes"].append({"by": "risk", "why": r_v})
    if not m_ok:
        dec["vetoes"].append({"by": "meta", "why": m_v})

    market_ok = (r_ok and m_ok
                 and lv["rr_net"] >= rr_m
                 and lv["cost_atr"] <= CFG["cost_atr_market_max"])
    if market_ok:
        dec.update({"action": cand, "mode": "market", "entry": lv["entry"],
                    "stop": lv["sl"], "tp1": lv["tp1"], "tp2": lv["tp2"]})
    elif r_ok:
        lo_n = float(d15["low"].iloc[-4:-1].min())
        hi_n = float(d15["high"].iloc[-4:-1].max())
        trig = (max(lo_n - 0.1 * lv["atr"], px - 1.0 * lv["atr"]) if cand == "SELL"
                else min(hi_n + 0.1 * lv["atr"], px + 1.0 * lv["atr"]))
        # seviyeleri GERÇEK giriş (tetik) fiyatıyla yeniden hesapla: RR yanıltıcı olmasın
        lv2 = levels(cand, _round_tick(trig), d15, ov, rr_c)
        r2_ok, r2_v = risk_gate(cand, lv2, rr_c)
        if not r2_ok:
            dec["action"] = "HOLD"
            dec["vetoes"].append({"by": "risk", "why": [f"tetik girişiyle: {x}" for x in r2_v]})
            dec["notes"].append("tetik fiyatıyla RR/seviye şartı sağlanmadı: " + "; ".join(r2_v))
        else:
            dec["levels"] = {k: lv2[k] for k in ("entry", "sl", "tp1", "tp2", "rr_gross", "rr_net",
                                                 "cost_pct", "cost_atr", "sl_atr", "atr")}
            mins = TF_MIN.get(tf, 15) * CFG["valid_bars"]
            inv_lv = _round_tick(hi_n + 0.1 * lv2["atr"]) if cand == "SELL" else _round_tick(lo_n - 0.1 * lv2["atr"])
            dec.update({
                "action": "SHORT" if cand == "SELL" else "LONG", "mode": "conditional",
                "trigger": {"close_below" if cand == "SELL" else "close_above": _round_tick(trig)},
                "entry": _round_tick(trig), "stop": lv2["sl"], "tp1": lv2["tp1"], "tp2": lv2["tp2"],
                "valid_until": (bar + timedelta(minutes=mins)).isoformat(),
                "invalidate_level": inv_lv,
                "invalidate_side": "above" if cand == "SELL" else "below",
                "invalidate": (
                    [f"{tf} kapanış {inv_lv} üstüne dönerse tetik iptal"]
                    if cand == "SELL" else
                    [f"{tf} kapanış {inv_lv} altına dönerse tetik iptal"]),
            })
            dec["notes"].append("piyasa emri kapalı: " + "; ".join(
                [x for x in (r_v + m_v)] + [f"RR_net {lv2['rr_net']} / maliyet/ATR {lv2['cost_atr']}"]))
    else:
        dec["action"] = "HOLD"
        dec["notes"].append("risk katmanı adayı reddetti: " + "; ".join(r_v))

    dec["risk_r"] = 1.0 if (fresh and m_ok) else 0.5
    dec["disclaimer"] = "Araştırma/kağıt işlem çıktısı; yatırım tavsiyesi değildir."
    return dec


# --------------------------------------------------------------------------- CLI
def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--out", default=str(LIVE_DIR))
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-telegram", action="store_true", help="sinyali gonder ama Telegram'a atma")
    a = ap.parse_args(argv)

    dec = decide(a.symbol, a.tf, use_overlay=not a.no_overlay)
    line = (f"{dec['symbol']:14s} {dec['action']:6s} {dec['mode']:11s} "
            f"oy {dec['consensus']['buy']}/{dec['consensus']['sell']}/{dec['consensus']['hold']} "
            f"pay %{dec['consensus']['share'] * 100:.0f} "
            f"| {dec.get('levels', {}).get('rr_net', '-')}RR / eşik {dec.get('rr_floor', '-')}")
    print(line)
    for v in dec["votes"].items():
        print(f"   {v[0]:9s} {v[1]['side']:5s} {v[1]['conf']:.2f}  {v[1]['note'][:90]}")
    if dec["vetoes"]:
        print("   veto:", dec["vetoes"])
    if dec["notes"]:
        print("   not:", "; ".join(dec["notes"])[:200])

    if a.no_write:
        return
    p = write_decision(dec, a.out, notify=not a.no_telegram)
    print(f"→ {p}")


def write_decision(dec: dict, out: str | Path, notify: bool = True) -> Path:
    """Karar JSON'unu ve journal satırını yazar; uygulanabilir kararı Telegram'a gönderir."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    d = Path(out) / stamp
    d.mkdir(parents=True, exist_ok=True)
    safe = dec["symbol"].replace(".", "_")
    p = d / f"decision_{safe}.json"

    if notify:
        try:
            import telegram_notify
            tg = telegram_notify.send_signal(dec)
        except Exception as exc:
            tg = {"ok": False, "error": str(exc)}
        if tg.get("ok"):
            if tg.get("tracked"):
                print(f"   telegram: izlendi (aday gonderilmedi)")
            else:
                print(f"   telegram: gonderildi (msg {tg.get('message_id')})")
        elif tg.get("error"):
            print(f"   telegram: gonderilemedi ({tg['error']})")
        elif tg.get("skipped"):
            print(f"   telegram: atlandi ({tg['skipped']})")
        dec["telegram"] = tg

    p.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    j = Path(out) / "journal.jsonl"
    with j.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "cycle": stamp, "engine": ENGINE, "symbol": dec["symbol"], "bar": dec["bar"],
            "action": dec["action"], "mode": dec["mode"],
            "consensus": dec["consensus"], "price": dec["price"],
            "rr_net": dec.get("levels", {}).get("rr_net"),
            "rr_floor": dec.get("rr_floor"),
            "vetoes": [v["by"] for v in dec["vetoes"]],
            "telegram": (dec.get("telegram") or {}).get("message_id") or (dec.get("telegram") or {}).get("skipped"),
        }, ensure_ascii=False) + "\n")
    return p


if __name__ == "__main__":
    main()
