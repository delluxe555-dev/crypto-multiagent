"""AlertaChart veri köprüsü — duygu/türev bloğunun tek kaynağı.

Neden var
---------
Botun eski `extras.py` katmanı türev verisini tek borsadan (OKX) ve eksik çekiyordu:
likidasyon örneklemi bozuk (15dk long $7.5M / short $18K), emir defteri spot,
CVD / net pozisyon / balina akışı / likidasyon haritası / opsiyon hiç yok.

Bu modül, AlertaChart'ın 5 borsalık toplu verisini tek bir snapshot'tan okur ve
`extras.text()` ile **aynı imzaya** sahip bir metin üretir; böylece ajan kodu
değişmeden veri kaynağı değişir.

    from dataflows import alertachart_bridge as ac
    block, meta = ac.text("BTCUSDT", interval="1h", legacy={"onchain": oc, "fng": fng})
    if block is None:                      # snapshot yok/bayat -> eski kaynağa düş
        block, raw = extras.text(symbol, df, interval)

Sözleşme
--------
Snapshot `cache/alertachart/<SEMBOL>/<tf>/<BAR>.json`, şema `alertachart-sentiment/1.0`.
Üretici tarafı (asistan/MCP) çağrı listesi: `docs/alertachart_refresh.md`.
AlertaChart'ta KARŞILIĞI OLMAYAN alanlar (zincir üstü, Korku&Açgözlülük) eski
kaynaktan `legacy=` ile geçirilir ve metnin sonunda ayrı başlıkta görünür.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "alertachart-sentiment/1.0"
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("CA_AC_CACHE", ROOT / "cache" / "alertachart"))
# AlertaChart'ta karşılığı olmayan iki alanı (zincir üstü, Korku&Açgözlülük) çeken bot kodu.
BOT_CODE = Path(os.environ.get("CA_BOT_CODE", ROOT / "handoff" / "handoff" / "code"))
TF_MIN = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}

# Chain Lab modül kimliği -> insan etiketi.
LAB_LABELS = {
    "spot_perp_lead": "Spot/perp öncülüğü", "oi_regime": "OI rejimi",
    "squeeze_risk": "Sıkışma riski", "flow_score": "Akış skoru",
    "venue_flow_share": "Borsa payı", "delta_divergence": "Delta uyumsuzluğu",
    "absorption": "Absorpsiyon", "delta_z_score": "Delta z",
    "aggressor_ratio": "Agresör oranı", "session_cvd": "Seans CVD",
    "average_trade_size": "Ort. işlem boyu", "leverage_saturation": "Kaldıraç doygunluğu",
    "funding_cost": "Funding maliyeti", "funding_spread": "Funding farkı",
    "net_position_flow": "Net pozisyon akışı", "oi_spike": "OI sıçraması",
    "liquidation_cascade": "Likidasyon kaskadı", "flush_ratio": "Flush oranı",
    "liquidation_imbalance": "Likidasyon dengesizliği", "coinbase_premium": "Coinbase primi",
    "flow_breadth": "Akış genişliği", "iv_rank": "IV rank",
    "variance_risk_premium": "VRP",
}
# Kendi bölümünde gösterilen modüller Chain Lab listesinde tekrarlanmaz.
LAB_DEDUP = {"oi_regime", "squeeze_risk", "leverage_saturation", "oi_spike",
             "funding_cost", "funding_spread", "iv_rank", "variance_risk_premium",
             "liquidation_cascade", "liquidation_imbalance"}

# Snapshot anahtarı -> onu üreten AlertaChart aracı (denetim ve yenileme için).
SOURCES = {
    "flow": "get_orderflow (timeframe, bars>=24) — CVD/OI/funding/likidasyon, 5 borsa",
    "oi": "get_derivatives_history(kind=open_interest)",
    "fund": "get_derivatives_history(kind=funding, days>=7)",
    "book": "get_order_book(market=perp)",
    "liqmap": "get_liquidation_map (TAHMİNİ)",
    "heat": "get_liquidity_heatmap(market=perp, hours=2)",
    "whales": "get_large_trades(market=perp, hours=4, min_usd>=500k)",
    "obe": "get_order_book_events(market=perp, hours=2)",
    "lab": "get_chain_lab(timeframe, language=tr) — 23 modül",
    "opt": "get_options + get_options_volatility (BTC/ETH/SOL...)",
    "profile": "get_market_profile(market=perp, session=day)",
    "breadth": "scan_flow(scan=flow_breadth)",
    "majors": "scan_market(scan=funding_high) -> majors",
    "news": "get_news(query=coin)",
    "macro": "get_macro",
}
# AlertaChart'ta yok -> eski kaynaktan gelir (extras.onchain, data.fear_greed).
LEGACY_ONLY = {"onchain", "fear_greed"}


# ---------------------------------------------------------------- yardımcılar
def ac_symbol(symbol: str) -> str:
    """BTCUSDT -> BTCUSDT.P (perp). Zaten nokta içeren yazım korunur."""
    s = str(symbol).upper().strip()
    return s if "." in s else s + ".P"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def bar_age_min(snap: dict, now: datetime | None = None) -> float | None:
    """Kapanan mumun üzerinden geçen dakika. Bar zamanı mumun AÇILIŞI kabul edilir."""
    t = _parse(snap.get("bar"))
    if t is None:
        return None
    tf = TF_MIN.get(snap.get("tf", ""), 60)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - (t + timedelta(minutes=tf))).total_seconds() / 60.0)


def is_fresh(snap: dict, grace: float = 0.5, now: datetime | None = None,
             strict: bool = False) -> bool:
    """Mum aralığının 1.5 katından eski değilse taze say.

    `strict=True` (canlı döngü): yeni mum kapandıktan 2 dakika sonra eski sayılır.
    """
    age = bar_age_min(snap, now)
    tf = TF_MIN.get(snap.get("tf", ""), 60)
    if age is None:
        return False
    return age <= (tf + 2 if strict else tf * (1 + grace))


def load(symbol: str, tf: str = "1h") -> dict | None:
    """En yeni geçerli snapshot (bar zamanına göre). Yoksa None."""
    d = CACHE / ac_symbol(symbol) / tf
    if not d.is_dir():
        return None
    best, best_bar = None, None
    for p in d.glob("*.json"):
        try:
            snap = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if snap.get("schema") != SCHEMA:
            continue
        bar = _parse(snap.get("bar")) or datetime.min.replace(tzinfo=timezone.utc)
        if best_bar is None or bar > best_bar:
            best, best_bar = snap, bar
            snap["_path"] = str(p)
    return best


def validate(snap: dict) -> list[str]:
    """Eksik/bozuk alanları döndürür; boş liste = tam.

    `opt`, `news`, `macro` isteğe bağlı: altcoinlerde opsiyon, bazı anlarda haber yok.
    Bunlar `problems`'a yazılmaz, `meta["sources"]` listesinden görülür.
    """
    if not snap:
        return ["snapshot yok"]
    bad = [f"şema {snap.get('schema')!r}"] if snap.get("schema") != SCHEMA else []
    for key in ("symbol", "tf", "bar", "price", "flow"):
        if snap.get(key) in (None, "", {}):
            bad.append(f"eksik: {key}")
    for key in SOURCES:
        if key in ("flow", "opt", "news", "macro"):
            continue
        if snap.get(key) in (None, [], {}):
            bad.append(f"eksik: {key}")
    if snap.get("errors"):
        bad += [f"kaynak hatası: {e}" for e in snap["errors"]]
    return bad


# ---------------------------------------------------------------- biçimleme
def _f(x, nd: int = 2) -> str:
    return "—" if x is None else f"{x:,.{nd}f}"


def _sgn(x, nd: int = 2, unit: str = "%") -> str:
    return "—" if x is None else f"{x:+.{nd}f}{unit}"


def _mln(x, nd: int = 1) -> str:
    """İşaretli USD: +151.5M$, -9.3M$."""
    if x is None:
        return "—"
    return ("+" if x > 0 else "-" if x < 0 else "") + _abs_mln(x, nd)


def _abs_mln(x, nd: int = 1) -> str:
    """Mutlak USD; 1M$ altını K$ ile gösterir."""
    if x is None:
        return "—"
    a = abs(x)
    if a == 0:
        return "0$"
    return f"{a/1e3:,.0f}K$" if a < 1e6 else f"{a/1e6:,.{nd}f}M$"


def _lab_short(name: str) -> str:
    return str(name).replace("Hyperliquid", "HL").replace(" perpetual", "").replace(" perp", "").replace(" spot", "")


def legacy_bundle(symbol: str, df=None) -> dict:
    """AlertaChart'ta OLMAYAN alanları eski kaynaktan çeker (aynı kalsın).

    - zincir üstü: DefiLlama stablecoin/TVL, mempool/blockchain.info (BTC)
    - Korku&Açgözlülük: alternative.me
    - hacim sıçraması: mum verisinden (AlertaChart'ta tek oran olarak yok)
    Bot koduna erişilemezse boş döner; blok yine üretilir.
    """
    out: dict = {}
    if not BOT_CODE.is_dir():
        return out
    if str(BOT_CODE) not in sys.path:
        sys.path.insert(0, str(BOT_CODE))
    try:
        import extras  # noqa: PLC0415  (bot kodu, isteğe bağlı)
        out["onchain"] = extras.onchain(symbol) or None
        if df is not None:
            out["vs"] = extras.volume_spike(df)
    except Exception:
        pass
    try:
        import data  # noqa: PLC0415
        fng = data.fear_greed(10)
        if fng:
            out["fng"] = ", ".join(f"{d}:{v}({c})" for d, v, c in fng[:7])
    except Exception:
        pass
    return out


def extras_dict(snap: dict | None, legacy: dict | None = None) -> dict:
    """Botun `ext` sözlüğüyle uyumlu alanlar (lessons.liq_24h, onchain, volume_spike)."""
    leg = legacy or {}
    out: dict = {
        "alertachart": {k: snap.get(k) is not None for k in SOURCES} if snap else None,
        "onchain": leg.get("onchain"),
        "volume_spike": leg.get("vs"),
    }
    liq = ((snap or {}).get("flow") or {}).get("liq") or {}
    if liq.get("l") and liq.get("s"):
        out["derivatives"] = {"source": "alertachart",
                              "liq_24h": {"long_usd": liq["l"]["usd"], "short_usd": liq["s"]["usd"]}}
    return out


# ---------------------------------------------------------------- gövde
def render(snap: dict, legacy: dict | None = None, detail: str = "full") -> str:
    """Snapshot -> ajan prompt'una girecek Türkçe metin bloğu."""
    L: list[str] = []
    legacy = legacy or {}
    g = snap.get
    age = bar_age_min(snap)
    bar = (g("bar") or "").replace("T", " ").replace(":00.000Z", "").replace(".000Z", "")[:16]
    tag = "BAYAT" if not is_fresh(snap) else "taze"
    L.append(f"[AlertaChart · 5 borsa · {g('tf')} · kapanan mum {bar} UTC · "
             f"{_f(age, 0)} dk önce · {tag}]")
    L.append(f"{g('symbol')} ({g('venue')}) · {_f(g('price'))}")

    # --- akış
    flow = g("flow") or {}
    venues = flow.get("venues", [])
    exchanges = sorted({_lab_short(v.get("v", "")) for v in venues})
    L[0] = (f"[AlertaChart · {len(exchanges) or '?'} borsa · {g('tf')} · kapanan mum {bar} UTC · "
            f"{_f(age, 0)} dk önce · {tag}]")
    for w in flow.get("w", []):
        L.append(f"{w.get('b')} mum: fiyat {_sgn(w.get('px'))} · CVD perp {_mln((w.get('cvdp') or 0) * 1e6)}"
                 f" / spot {_mln((w.get('cvds') or 0) * 1e6)} · OI {_sgn(w.get('oi'))}"
                 f" · net long {_f(w.get('nl'), 0)} / net short {_f(w.get('ns'), 0)}"
                 f" · liq long {_abs_mln(w.get('ll'))} / short {_abs_mln(w.get('ls'))}")
    perp = [v for v in venues if "perp" in v.get("v", "")]
    spot = [v for v in venues if "spot" in v.get("v", "")]
    if perp:
        L.append("CVD perp: " + " · ".join(f"{_lab_short(v['v'])} {_mln(v.get('cvd', 0) * 1e3)}" for v in perp))
    if spot:
        L.append("CVD spot: " + " · ".join(f"{_lab_short(v['v'])} {_mln(v.get('cvd', 0) * 1e3)}" for v in spot))
    if legacy.get("vs"):
        L.append(f"Hacim sıçraması: son mum hacmi / önceki 20 mum ort. = {legacy['vs']:.2f}x")

    lab_by = {m.get("m"): m.get("r") for m in (g("lab") or [])}

    # --- funding
    fund = g("fund") or {}
    if fund.get("venues"):
        L.append("Funding, son settle (7g ort / sıradaki): " + " · ".join(
            f"{v['v']} {_sgn(v.get('last'), 4)} ({_sgn(v.get('m7'), 4)} / {_sgn(v.get('next'), 4)})"
            for v in fund["venues"]))
    for key, label in (("funding_cost", "Funding maliyeti"), ("funding_spread", "Funding farkı")):
        if lab_by.get(key):
            L.append(f"{label}: {lab_by[key]}")
    if g("majors"):
        L.append("Majors funding (8s): " + " · ".join(
            f"{m['coin']} {_sgn(m.get('funding_8h_pct'), 4)}" for m in g("majors")))

    # --- açık pozisyon
    oi = g("oi") or {}
    if oi.get("venues"):
        L.append(f"Açık pozisyon: toplam {_f(oi.get('total'))}M$ (anlık {_f((flow.get('oi_usd') or 0)/1e6)}M$)"
                 f" · " + " · ".join(f"{v['v']} {_f(v.get('usd'))}M$ ({_sgn(v.get('chg'))})" for v in oi["venues"]))
    for key, label in (("leverage_saturation", "Kaldıraç doygunluğu"), ("oi_regime", "OI rejimi"),
                       ("oi_spike", "OI sıçraması"), ("squeeze_risk", "Sıkışma riski")):
        if lab_by.get(key):
            L.append(f"{label}: {lab_by[key]}")

    # --- likidasyon
    liq = flow.get("liq") or {}
    if liq:
        since = (liq.get("since") or "")[:16].replace("T", " ")
        L.append(f"Gerçekleşen likidasyon ({since} UTC'den beri): long "
                 f"{_f((liq.get('l') or {}).get('n'), 0)} işlem {_abs_mln((liq.get('l') or {}).get('usd'))}"
                 f" / short {_f((liq.get('s') or {}).get('n'), 0)} işlem "
                 f"{_abs_mln((liq.get('s') or {}).get('usd'))}"
                 + (f" · kaskad: {lab_by['liquidation_cascade']}" if lab_by.get("liquidation_cascade") else "")
                 + (f" · {lab_by['liquidation_imbalance']}" if lab_by.get("liquidation_imbalance") else ""))
        tops = (liq.get("top") or [])[:2]
        if tops:
            L.append("  en büyük: " + " · ".join(
                f"{t.get('s')} {_abs_mln(t.get('usd'))} @ {_f(t.get('px'))} ({t.get('v')})" for t in tops))
    lm = g("liqmap") or {}
    if lm.get("within"):
        L.append("Likidasyon haritası (TAHMİNİ): " + " · ".join(
            f"±%{z.get('pct')} long {_abs_mln(z.get('l'))} / short {_abs_mln(z.get('s'))}" for z in lm["within"]))
        if lm.get("below"):
            L.append("  long kümeleri: " + " · ".join(
                f"{_f(b.get('price_from'), 0)}-{_f(b.get('price_to'), 0)} ({_sgn(b.get('distance_pct'))}, {_abs_mln(b.get('est_usd'))})"
                for b in lm["below"][:3]))
        if lm.get("above"):
            L.append("  short kümeleri: " + " · ".join(
                f"{_f(a.get('price_from'), 0)}-{_f(a.get('price_to'), 0)} ({_sgn(a.get('distance_pct'))}, {_abs_mln(a.get('est_usd'))})"
                for a in lm["above"][:3]))

    # --- defter / likidite
    book = g("book") or {}
    if book:
        depth = " · ".join(f"±%{d.get('pct')} bid {_abs_mln(d.get('bid'))} / ask {_abs_mln(d.get('ask'))}"
                           f" (denge {_sgn(d.get('imb'), 1)})" for d in book.get("depth", [])[:2])
        L.append(f"Emir defteri (perp): spread {_f(book.get('spread_bps'), 2)} bps · {depth}")
        bw = ", ".join(f"{_f(w.get('price'))} ({_abs_mln(w.get('usd'))}, {_sgn(w.get('distance_pct'))})"
                       for w in book.get("bw", [])[:2])
        aw = ", ".join(f"{_f(w.get('price'))} ({_abs_mln(w.get('usd'))}, {_sgn(w.get('distance_pct'))})"
                       for w in book.get("aw", [])[:2])
        if bw or aw:
            L.append(f"Duvarlar: bid {bw} | ask {aw}")
    obe = g("obe") or {}
    if obe.get("out"):
        o = obe["out"]
        L.append(f"Duvar davranışı (2s, {obe.get('n')} duvar): çekildi {o.get('pulled')} · duruyor {o.get('standing')}"
                 f" · doldu {o.get('filled')} · bant dışı {o.get('out of the recorded band')}")
    heat = g("heat") or {}
    if heat.get("bid") or heat.get("ask"):
        hb = " · ".join(f"{_f(x.get('price'))} ({_sgn(x.get('distance_pct'))}, %{x.get('present_pct')} mevcut, {_abs_mln(x.get('avg_resting_usd'))})"
                        for x in heat.get("bid", [])[:2])
        ha = " · ".join(f"{_f(x.get('price'))} ({_sgn(x.get('distance_pct'))}, %{x.get('present_pct')} mevcut, {_abs_mln(x.get('avg_resting_usd'))})"
                        for x in heat.get("ask", [])[:2])
        L.append(f"Likidite ısı haritası: bid {hb} | ask {ha}")

    # --- balina
    wh = g("whales") or {}
    if wh:
        L.append(f"Balina (son {wh.get('h')}s, >= {_abs_mln(wh.get('min'))}): alım {_abs_mln(wh.get('buy'))}"
                 f" ({wh.get('nb')}) / satım {_abs_mln(wh.get('sell'))} ({wh.get('ns')})"
                 f" -> net {_mln(wh.get('net'))}")
        if wh.get("top"):
            L.append("  en büyük: " + " · ".join(
                f"{t.get('side')} {_abs_mln(t.get('usd'))} @ {_f(t.get('price'))}" for t in wh["top"][:3]))

    # --- chain lab
    lab = g("lab") or []
    rows = [m for m in lab if m.get("ok") is not False and m.get("m") not in LAB_DEDUP]
    if rows:
        rows = rows if detail == "full" else rows[:10]
        L.append("Chain Lab:")
        for m in rows:
            L.append(f"  {LAB_LABELS.get(m.get('m'), m.get('m'))}: {m.get('r')}")

    # --- opsiyon
    o = g("opt") or {}
    if o:
        em = o.get("em") or {}
        L.append(f"Opsiyon: DVOL {_f(o.get('dvol'), 1)} (IV rank {o.get('ivr')}) · RV {_f(o.get('rv'), 1)}"
                 f" · VRP {_sgn(o.get('vrp'), 1, '')} · gamma flip {_f(o.get('gamma'), 0)}"
                 f" · max pain {_f(o.get('pain'), 0)} · call wall {_f(o.get('call'), 0)} / put wall {_f(o.get('put'), 0)}"
                 f" · P/C OI {_f(o.get('pcr'))} · OI {_f((o.get('oi_usd') or 0)/1e9)} mlr$")
        if em:
            L.append(f"  {_f(em.get('d'), 1)}g beklenen hareket {_f(em.get('lo'), 0)}-{_f(em.get('hi'), 0)}"
                     f" (IV {_f(em.get('iv'), 1)}, RR25 {_sgn(em.get('rr'), 1, '')})")

    # --- profil / genişlik
    pr = g("profile") or {}
    if pr:
        L.append(f"Piyasa profili ({pr.get('s')}, perp): POC {_f(pr.get('poc'))} / VAH {_f(pr.get('vah'))}"
                 f" / VAL {_f(pr.get('val'))} · VWAP {_f(pr.get('vwap'))}"
                 f" · delta {_f(pr.get('delta'), 0)} (alıcı %{_f(pr.get('buyers'), 1)})")
    br = g("breadth") or {}
    if br:
        streak = str(br.get("streak") or "")
        if streak.startswith("4 bars at or above 50%"):
            streak = "son 4 mum >=%50"
        L.append(f"Genişlik: {br.get('coins')} coin, son 1h net alıcı %{_f(br.get('pct'), 1)}"
                 f" ({br.get('nb')}/{br.get('coins')}) · 24s ort %{_f(br.get('avg24'), 1)} · {streak}")

    # --- makro / haber
    mc = g("macro") or {}
    if mc:
        def _num(x):
            if x is None:
                return "—"
            return f"{x:,.0f}" if abs(x) >= 1000 else _f(x)
        ser = " · ".join(f"{s['k']} {_num(s.get('v'))}" for s in mc.get("s", []))
        L.append(f"Makro: FOMC {mc.get('fomc')} ({(mc.get('at') or '')[:10]}) · Fed proj {mc.get('fed')} · {ser}")
    news = g("news") or []
    if news:
        L.append("Haber (son): " + " | ".join(f"{n.get('t')} [{n.get('s')}]" for n in news[:3 if detail != "full" else 5]))

    # --- AlertaChart'ta olmayanlar
    tail = []
    if legacy.get("onchain"):
        oc = legacy["onchain"]
        tail.append("Zincir üstü/akış (AlertaChart'ta yok, eski kaynak): " + ", ".join(
            f"{k}={v:,.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in oc.items()))
    if legacy.get("fng"):
        tail.append("Korku&Açgözlülük (AlertaChart'ta yok, eski kaynak): " + str(legacy["fng"]))
    if tail:
        L.append("— AlertaChart'ta olmayan —")
        L += tail

    return "\n".join(L)


def text(symbol: str, df=None, interval: str = "1h", legacy: dict | None = None,
         detail: str = "full") -> tuple[str | None, dict]:
    """`extras.text()` yerine geçen giriş noktası.

    Dönüş: (blok, meta). Blok None ise çağıran eski kaynağa düşmeli.
    `df` yalnızca imza uyumu için; AlertaChart fiyatı kendi snapshot'ından gelir.
    """
    snap = load(symbol, interval)
    if not snap:
        return None, {"ok": False, "reason": f"snapshot yok: {CACHE / ac_symbol(symbol) / interval}",
                      "problems": ["snapshot yok"]}
    problems = validate(snap)
    # legacy=None -> AlertaChart'ta olmayanları eski kaynaktan otomatik çek.
    # legacy={}   -> hiç ekleme (test/hızlı yol).
    if legacy is None:
        legacy = legacy_bundle(symbol, df)
    block = render(snap, legacy=legacy, detail=detail)
    meta = {"ok": True, "bar": snap.get("bar"), "age_min": round(bar_age_min(snap) or -1, 1),
            "stale": not is_fresh(snap), "problems": problems, "path": snap.get("_path"),
            "sources": sorted(k for k in SOURCES if snap.get(k) not in (None, [], {})),
            "extras": extras_dict(snap, legacy)}
    if meta["stale"]:
        block = ("UYARI: bu türev bloğu bayat (kapanan mum " + str(snap.get("bar")) +
                 "). Yeni mum kapandıysa yenile.\n") + block
    return block, meta


def load_overlay(symbol: str, tf: str = "15m") -> dict | None:
    """En yeni 15m/5m hızlı katman dosyası (`overlay_*.json`)."""
    d = CACHE / ac_symbol(symbol) / tf
    if not d.is_dir():
        return None
    best = bestk = None
    for p in d.glob("overlay_*.json"):
        try:
            o = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if o.get("schema") != "alertachart-overlay/1.0":
            continue
        k = (_parse(o.get("bar")) or _parse(o.get("asof"))
             or datetime.min.replace(tzinfo=timezone.utc))
        if bestk is None or k > bestk:
            best, bestk, o["_path"] = o, k, str(p)
    return best


def render_overlay(o: dict) -> str:
    """15m hızlı katman -> kısa metin (karar TF'sinin taze verisi)."""
    L: list[str] = []
    tf = o.get("tf", "15m")
    bar = (o.get("bar") or "").replace("T", " ")[:16]
    t = _parse(o.get("bar"))
    age = None
    if t:
        age = (datetime.now(timezone.utc) - (t + timedelta(minutes=TF_MIN.get(tf, 15)))).total_seconds() / 60
    L.append(f"[AlertaChart {tf} · kapanan mum {bar} UTC · {_f(age, 0)} dk önce]")

    b = o.get("book") or {}
    if b:
        d = b.get("d") or {}
        L.append(f"Fiyat {_f(b.get('mid'))} · spread {_f(b.get('spread'), 2)} bps · defter ±%{d.get('within_pct')}: "
                 f"bid {_abs_mln(d.get('bids_usd'))} / ask {_abs_mln(d.get('asks_usd'))}"
                 f" (denge {_sgn(d.get('imbalance_pct'), 1)})")
        bw = ", ".join(f"{_f(w.get('price'))} ({_abs_mln(w.get('usd'))})" for w in b.get("bw", [])[:2])
        aw = ", ".join(f"{_f(w.get('price'))} ({_abs_mln(w.get('usd'))})" for w in b.get("aw", [])[:2])
        if bw or aw:
            L.append(f"Duvarlar: bid {bw} | ask {aw}")

    for w in o.get("w", []):
        L.append(f"{w.get('b')} mum: {_sgn(w.get('px'))}"
                 f" · CVD perp {_mln((w.get('cvdp') or 0) * 1e6)} / spot {_mln((w.get('cvds') or 0) * 1e6)}"
                 f" · OI {_sgn(w.get('oi'))} · NL {_f(w.get('nl'), 0)} / NS {_f(w.get('ns'), 0)}"
                 f" · liq L {_abs_mln(w.get('ll'))} / S {_abs_mln(w.get('ls'))}")
    if o.get("venues"):
        L.append("Borsa CVD (perp): " + " · ".join(
            f"{_lab_short(v['v'])} {_mln((v.get('cvd') or 0) * 1e3)}" for v in o["venues"]))

    liq = o.get("liq") or {}
    if liq:
        since = (liq.get("since") or "")[:16].replace("T", " ")
        l, s = liq.get("l") or {}, liq.get("s") or {}
        L.append(f"Likidasyon ({since} UTC'den beri): L {_f(l.get('count'), 0)} işlem {_abs_mln(l.get('usd'))}"
                 f" / S {_f(s.get('count'), 0)} işlem {_abs_mln(s.get('usd'))}")
        tops = [f"{x.get('side')} {_abs_mln(x.get('usd'))} @ {_f(x.get('price'))} ({_lab_short(x.get('venue') or '')})"
                for x in (liq.get("top") or [])[:2]]
        if tops:
            L.append("  en büyük: " + " · ".join(tops))

    lm = o.get("lm") or {}
    if lm.get("within"):
        L.append("Harita (TAHMİNİ): " + " · ".join(
            f"±%{z.get('pct')} L {_abs_mln(z.get('longs_below_usd'))} / S {_abs_mln(z.get('shorts_above_usd'))}"
            for z in lm["within"]))
        for key, tag in (("below", "long"), ("above", "short")):
            if lm.get(key):
                L.append(f"  {tag} küme: " + " · ".join(
                    f"{_f(x.get('price_from'), 0)}-{_f(x.get('price_to'), 0)}"
                    f" ({_sgn(x.get('distance_pct'))}, {_abs_mln(x.get('est_usd'))})" for x in lm[key][:2]))

    h = o.get("heat") or {}
    if h.get("bid") or h.get("ask"):
        def _lv(xs):
            return " · ".join(f"{_f(x.get('price'))} (%{x.get('present_pct')}, {_abs_mln(x.get('avg_resting_usd'))})"
                              for x in xs[:2])
        L.append(f"Isı: bid {_lv(h.get('bid', []))} | ask {_lv(h.get('ask', []))}")

    wh = o.get("whales") or {}
    if wh:
        L.append(f"Balina (1s, {wh.get('n')} işlem): alım {_abs_mln(wh.get('buy'))}"
                 f" / satım {_abs_mln(wh.get('sell'))} -> net {_mln(wh.get('net'))}")

    obe = o.get("obe") or {}
    if obe.get("out"):
        L.append(f"Duvar davranışı (1s, {obe.get('n')}): "
                 + " · ".join(f"{k} {v}" for k, v in obe["out"].items()))

    rows = [m for m in (o.get("lab") or []) if m.get("m") not in LAB_DEDUP]
    if rows:
        L.append("Chain Lab:")
        for m in rows[:12]:
            L.append(f"  {LAB_LABELS.get(m.get('m'), m.get('m'))}: {m.get('r')}")

    mac = ((o.get("slow") or {}).get("macro") or {})
    if mac:
        def _mv(sym, fmt="{:.2f}"):
            d = mac.get(sym) or {}
            if d.get("change") in (None, 0):
                return None
            return f"{sym} {fmt.format(d['latest'])} ({d['change']:+g})"
        bits = [x for x in (_mv("US10Y"), _mv("US02Y"), _mv("BAMLH0A0HYM2", "{:.2f}"),
                            _mv("NFCI", "{:.3f}"), _mv("USNETLIQ", "{:.0f}")) if x]
        if bits:
            L.append("Makro (günlük değişim): " + " · ".join(bits))
    return "\n".join(L)


def overlay_text(symbol: str, tf: str = "15m") -> tuple[str | None, dict]:
    """15m katmanı: (blok, meta). Yoksa (None, {...})."""
    o = load_overlay(symbol, tf)
    if not o:
        return None, {"ok": False, "reason": f"overlay yok: {CACHE / ac_symbol(symbol) / tf}"}
    t = _parse(o.get("bar"))
    now = datetime.now(timezone.utc)
    age = (now - (t + timedelta(minutes=TF_MIN.get(tf, 15)))).total_seconds() / 60 if t else None
    # OVERLAY_MAX_AGE_MIN: kac dakika eski overlay "taze" sayilsin (varsayilan 60 dk).
    try:
        max_age = float(os.environ.get("OVERLAY_MAX_AGE_MIN") or 0) or 60.0
    except ValueError:
        max_age = 60.0
    meta = {"ok": True, "bar": o.get("bar"), "age_min": round(age, 1) if age is not None else None,
            "stale": (age is None or age > max_age), "path": o.get("_path")}
    block = render_overlay(o)
    if meta["stale"]:
        block = f"UYARI: hızlı katman bayat ({o.get('bar')}). Yenile.\n" + block
    return block, meta


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"
    blk, meta = text(sym, interval=tf)
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    print("-" * 70)
    print(blk or "(snapshot yok)")
