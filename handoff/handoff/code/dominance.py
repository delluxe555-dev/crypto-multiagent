#!/usr/bin/env python3
"""BTC.D / ETH.D / USDT.D / USDC.D dominance tracker (CoinGecko, keyless).

  python3 dominance.py --snapshot   # append a live row to outputs/dominance/dominance.csv (silent, never raises)
  python3 dominance.py --show       # Turkish summary: values, 1h/4h/24h changes, regime text
  python3 dominance.py --backfill   # approximate history (source=backfill_approx), see backfill()

CSV columns: ts_utc,btc_d,eth_d,usdt_d,usdc_d,total_mcap_usd,source
source = live | backfill_approx.  Regime text is rule-based and descriptive, NOT a forecast.
Sends no Telegram messages and does not touch trader.py / config.json.
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "outputs", "dominance")
CSV = os.path.join(DIR, "dominance.csv")
COLS = ["ts_utc", "btc_d", "eth_d", "usdt_d", "usdc_d", "total_mcap_usd", "source"]
API = "https://api.coingecko.com/api/v3"
MIN_GAP_S = 600  # skip a live snapshot if the last live row is younger than this (idempotent)
UA = {"User-Agent": "Mozilla/5.0 crypto-agents-dominance", "Accept": "application/json"}


def _get(path, timeout=20):
    """GET json; retry once (longer wait on 429). Returns dict or None. Never raises."""
    for attempt in (0, 1):
        try:
            req = urllib.request.Request(API + path, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if attempt == 0:
                time.sleep(20 if e.code == 429 else 3)
        except Exception:
            if attempt == 0:
                time.sleep(3)
    return None


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _rows():
    try:
        with open(CSV, newline="") as f:
            out = []
            for r in csv.DictReader(f):
                try:
                    out.append({"ts": _parse(r["ts_utc"]), "btc_d": float(r["btc_d"]), "eth_d": float(r["eth_d"]),
                                "usdt_d": float(r["usdt_d"]), "usdc_d": float(r["usdc_d"]),
                                "total": float(r["total_mcap_usd"]), "source": r.get("source", "live")})
                except Exception:
                    continue
            out.sort(key=lambda x: x["ts"])
            return out
    except Exception:
        return []


def _write_rows(rows):
    os.makedirs(DIR, exist_ok=True)
    tmp = CSV + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in rows:
            w.writerow([_iso(r["ts"]), f'{r["btc_d"]:.4f}', f'{r["eth_d"]:.4f}', f'{r["usdt_d"]:.4f}',
                        f'{r["usdc_d"]:.4f}', f'{r["total"]:.0f}', r["source"]])
    os.replace(tmp, CSV)


def snapshot(force=False):
    """Fetch /global and append one live row. Returns the row dict or None. Never raises."""
    try:
        rows = _rows()
        live = [r for r in rows if r["source"] == "live"]
        now = datetime.now(timezone.utc)
        if live and not force and (now - live[-1]["ts"]).total_seconds() < MIN_GAP_S:
            return live[-1]
        j = _get("/global")
        d = (j or {}).get("data") or {}
        p = d.get("market_cap_percentage") or {}
        tot = (d.get("total_market_cap") or {}).get("usd")
        if not p or not tot or "btc" not in p or "usdt" not in p:
            return None
        row = {"ts": now.replace(microsecond=0), "btc_d": float(p["btc"]), "eth_d": float(p.get("eth", 0)),
               "usdt_d": float(p["usdt"]), "usdc_d": float(p.get("usdc", 0)), "total": float(tot), "source": "live"}
        os.makedirs(DIR, exist_ok=True)
        new = not os.path.exists(CSV)
        with open(CSV, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(COLS)
            w.writerow([_iso(row["ts"]), f'{row["btc_d"]:.4f}', f'{row["eth_d"]:.4f}', f'{row["usdt_d"]:.4f}',
                        f'{row["usdc_d"]:.4f}', f'{row["total"]:.0f}', "live"])
        return row
    except Exception:
        return None


def latest():
    r = _rows()
    return r[-1] if r else None


def _at(rows, t, tol_h):
    """last row at or before t, but not older than t - tol_h."""
    best = None
    for r in rows:
        if r["ts"] <= t:
            best = r
        else:
            break
    if best and (t - best["ts"]).total_seconds() <= tol_h * 3600:
        return best
    return None


def trend(hours):
    """Change of btc_d/eth_d/usdt_d/usdc_d (percentage points) and total mcap (%) over `hours`.
    None if the CSV has no row near (now - hours)."""
    rows = _rows()
    if not rows:
        return None
    cur = rows[-1]
    ref = _at(rows, cur["ts"] - timedelta(hours=hours), max(1.0, hours * 0.35))
    if not ref:
        return None
    return {"hours": hours, "ref_ts": ref["ts"], "approx": ref["source"] != "live",
            "btc_d": cur["btc_d"] - ref["btc_d"], "eth_d": cur["eth_d"] - ref["eth_d"],
            "usdt_d": cur["usdt_d"] - ref["usdt_d"], "usdc_d": cur["usdc_d"] - ref["usdc_d"],
            "mcap_pct": (cur["total"] / ref["total"] - 1) * 100 if ref["total"] else 0.0}


def regime():
    """(window_hours, text) rule-based descriptive read. Not a forecast."""
    tr = None
    for h in (24, 4, 1):
        tr = trend(h)
        if tr:
            break
    if not tr:
        return None, "Yeterli geçmiş veri yok (CSV henüz birikiyor); rejim okunamadı."
    s = (tr["hours"] / 24.0) ** 0.5
    tb, tu, tm = 0.15 * s, 0.03 * s, 0.5 * s  # pp, pp, %
    b = 1 if tr["btc_d"] > tb else -1 if tr["btc_d"] < -tb else 0
    u = 1 if tr["usdt_d"] > tu else -1 if tr["usdt_d"] < -tu else 0
    m = 1 if tr["mcap_pct"] > tm else -1 if tr["mcap_pct"] < -tm else 0
    if b > 0 and u > 0:
        t = "Risk-off: BTC.D ↑ + USDT.D ↑ — para hem altlardan hem BTC'den stabile kayıyor." + (" Toplam piyasa değeri de düşüyor." if m < 0 else "")
    elif b > 0 and u < 0:
        t = "BTC öncülüğünde risk-on: BTC.D ↑ + USDT.D ↓ — para stabilden BTC'ye gidiyor, altlar görece geride."
    elif b < 0 and u < 0 and m > 0:
        t = "Alt dostu: BTC.D ↓ + USDT.D ↓ + toplam mcap ↑ — para stabilden altlara akıyor."
    elif b < 0 and u < 0:
        t = "Alt lehine ama teyitsiz: BTC.D ↓ + USDT.D ↓, toplam mcap yükselmiyor."
    elif b < 0 and u > 0:
        t = "Karışık / savunmacı: BTC.D ↓ + USDT.D ↑ — altlar BTC'den de zayıf, stabile kaçış var."
    elif b > 0:
        t = "BTC.D ↑, USDT.D yatay: BTC altlardan güçlü, stabile kaçış belirgin değil."
    elif b < 0:
        t = "BTC.D ↓, USDT.D yatay: altlar BTC'ye göre güçleniyor, stabile geçiş yok."
    elif u > 0:
        t = "USDT.D ↑, BTC.D yatay: temkinli taraf, stabil payı artıyor."
    elif u < 0:
        t = "USDT.D ↓, BTC.D yatay: stabil payı azalıyor, risk iştahı hafif artıyor."
    else:
        t = "BTC.D ve USDT.D belirgin değişmedi: net rejim yok."
    if u > 0 and m < 0:
        t += " (Not: toplam mcap düşerken USDT.D'nin artması kısmen mekaniktir.)"
    return tr["hours"], t


def backfill(days=30):
    """Approximate hourly history from CoinGecko market_chart (keyless, <=90 days -> hourly).
    /global/market_cap_chart (total mcap history) is PRO-only, so total is ESTIMATED:
    total_est(t) = sum(top-N coin mcaps at t) / k, with k = sum(top-N now)/real total now (constant 'rest' share).
    Dominance = coin mcap / total_est, scaled per coin to match the live anchor. Rows are labelled source=backfill_approx and only fill times
    before the first live row. Returns number of rows added (0 on failure)."""
    try:
        cur = None
        for _ in range(2):  # need a live anchor for calibration
            cur = latest()
            if cur and cur["source"] == "live":
                break
            snapshot(force=True)
        live_rows = [r for r in _rows() if r["source"] == "live"]
        if not live_rows:
            return 0
        anchor = live_rows[-1]
        first_live = live_rows[0]["ts"]
        ids = ["bitcoin", "ethereum", "tether", "ripple", "binancecoin", "solana", "usd-coin", "tron", "dogecoin", "cardano"]
        series = {}
        for i, cid in enumerate(ids):
            j = None
            for _ in range(3):
                j = _get(f"/coins/{cid}/market_chart?vs_currency=usd&days={days}")
                if j and j.get("market_caps"):
                    break
                time.sleep(25)
            if not j or not j.get("market_caps"):
                return 0
            series[cid] = {int(round(t / 3600000.0)): v for t, v in j["market_caps"]}
            time.sleep(7)
        hours = sorted(set.intersection(*[set(s) for s in series.values()]))
        if not hours:
            return 0
        # calibration at the last common hour that is closest to the anchor
        hn = hours[-1]
        topn_now = sum(series[c][hn] for c in ids)
        # use anchor's real total and dominance of btc to compute k from live data: k = topN(hn)/anchor total
        k = topn_now / anchor["total"]
        # per-coin scale so the series joins the live anchor without a jump (CoinGecko /global uses a slightly different coin set)
        tot_n = sum(series[c][hn] for c in ids) / k
        f = {key: anchor[key] / (series[cid][hn] / tot_n * 100)
             for key, cid in (("btc_d", "bitcoin"), ("eth_d", "ethereum"), ("usdt_d", "tether"), ("usdc_d", "usd-coin"))}
        out = []
        for h in hours:
            ts = datetime.fromtimestamp(h * 3600, tz=timezone.utc)
            if ts >= first_live - timedelta(minutes=30):
                continue
            tot = sum(series[c][h] for c in ids) / k
            out.append({"ts": ts, "btc_d": series["bitcoin"][h] / tot * 100 * f["btc_d"],
                        "eth_d": series["ethereum"][h] / tot * 100 * f["eth_d"],
                        "usdt_d": series["tether"][h] / tot * 100 * f["usdt_d"],
                        "usdc_d": series["usd-coin"][h] / tot * 100 * f["usdc_d"],
                        "total": tot, "source": "backfill_approx"})
        rows = [r for r in _rows() if r["source"] == "live"]
        _write_rows(sorted(out + rows, key=lambda x: x["ts"]))
        return len(out)
    except Exception:
        return 0


def _fmt(x, nd=2, sign=False):
    return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}")


def show():
    r = latest()
    if not r:
        print("Dominans verisi yok. Önce: python3 dominance.py --snapshot")
        return
    age = (datetime.now(timezone.utc) - r["ts"]).total_seconds() / 60
    print(f"Dominans (CoinGecko) — {_iso(r['ts'])} UTC, {age:.0f} dk önce, kaynak={r['source']}")
    print(f"  BTC.D  %{_fmt(r['btc_d'])}   ETH.D %{_fmt(r['eth_d'])}   USDT.D %{_fmt(r['usdt_d'])}   USDC.D %{_fmt(r['usdc_d'])}")
    print(f"  Toplam piyasa değeri: ${r['total']/1e12:.3f} T")
    for h in (1, 4, 24):
        t = trend(h)
        if t:
            ap = " (yaklaşık, backfill)" if t["approx"] else ""
            print(f"  {h:>2}s değişim: BTC.D {_fmt(t['btc_d'],2,True)} puan | ETH.D {_fmt(t['eth_d'],2,True)} | "
                  f"USDT.D {_fmt(t['usdt_d'],2,True)} | Toplam mcap %{_fmt(t['mcap_pct'],2,True)}{ap}")
        else:
            print(f"  {h:>2}s değişim: veri yok")
    h, txt = regime()
    print(f"  Rejim ({h}s pencere): {txt}" if h else f"  Rejim: {txt}")
    print("  [Kural tabanlı, betimleyici okuma — tahmin değildir. Backfill satırları yaklaşıktır.]")


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if "--snapshot" in a:
            snapshot(force="--force" in a)
        elif "--backfill" in a:
            n = backfill()
            print(f"backfill rows added: {n}")
        elif "--show" in a:
            show()
        else:
            print(__doc__)
    except Exception as e:  # never raise
        if "--snapshot" not in a:
            print("hata:", e)
