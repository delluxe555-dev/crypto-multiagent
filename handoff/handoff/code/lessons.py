"""Hatalardan ders çıkarma (yansıma) hafızası — KÂĞIT işlem, gerçek emir YOK.
Akış: pozisyon kapanınca (stop/hedef/süre) yapılandırılmış sonuç kaydı + KURAL TABANLI ölüm sonrası etiketler (LLM'siz) ->
en fazla TEK ucuz LLM çağrısıyla 1-2 cümle Türkçe ders (kota bitmişse sessizce atlanır, kural dersi kalır) ->
outputs/trader/lessons.json (son ~30 ders + kompakt işlem satırları + toplu istatistik).
Geri besleme: block() ~550 karakterlik 'Geçmiş derslerin' bloğu (aynı coin / benzer kurulum + tek satır istatistik) 4s trend,
1s giriş ve hakem istemlerine eklenir. Dersler yalnızca bilgidir; sert risk kurallarını DEĞİŞTİRMEZ. Örneklem < guard_min_n (10) iken
hiçbir şey sıkılaştırılmaz; insights() yalnızca RAPORLAR, otomatik uygulamaz.
Test/backtest: CA_LESSONS=/tmp/x.json veya new_store() ile canlı depodan bağımsız çalışır."""
import os, re, json, time, fcntl, threading, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get("CA_LESSONS") or os.path.join(HERE, "outputs", "trader", "lessons.json")
try: CFG = json.load(open(os.path.join(HERE, "config.json"))).get("lessons", {})
except Exception: CFG = {}
MAX_RECENT = CFG.get("max_recent", 30); MAX_TRADES = CFG.get("max_trades", 1000); PROMPT_CHARS = CFG.get("prompt_chars", 550)
MIN_N = CFG.get("guard_min_n", 10); USE_LLM = CFG.get("llm", True); ENABLED = CFG.get("enabled", True)

# ---------- depo ----------
def new_store(): return {"version": 1, "updated_at": None, "recent": [], "trades": [], "stats": {}}

def load(path=None):
    path = path or STORE
    try: S = json.load(open(path)); S.setdefault("recent", []); S.setdefault("trades", []); return S
    except Exception: return new_store()

def save(S, path=None):
    path = path or STORE; os.makedirs(os.path.dirname(path), exist_ok=True)
    S["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z"); S["stats"] = stats(S)
    tmp = path + ".tmp"; json.dump(S, open(tmp, "w"), ensure_ascii=False, indent=1, default=str); os.replace(tmp, path)

def locked_update(fn, path=None):
    """Kilitli oku-değiştir-yaz (daemon izleyicisi + arka plan LLM iş parçacığı + döngü süreçleri)."""
    path = path or STORE; os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path + ".lock", "w"); fcntl.flock(f, fcntl.LOCK_EX)
    try:
        S = load(path); r = fn(S); save(S, path); return r
    finally: fcntl.flock(f, fcntl.LOCK_UN); f.close()

# ---------- giriş bağlamı (metinden ayrıştır) ----------
def _f(m, g=1):
    try: return float(m.group(g).replace(",", ""))
    except Exception: return None

def parse_ctx(tech="", sent="", extras=None):
    """Ajanlara verilen metinlerden girişteki ana göstergeleri çıkarır (ek veri çağrısı yok)."""
    tech, sent = tech or "", sent or ""; c = {}
    px = _f(re.search(r"Kapanış:\s*([\d,\.]+)", tech))
    for k, pat in (("rsi", r"RSI14:\s*(-?[\d\.]+)"), ("macd_hist", r"Hist:\s*(-?[\d,\.]+)"), ("sma50", r"SMA50:\s*([\d,\.]+)"), ("sma200", r"SMA200:\s*([\d,\.]+)"), ("atr", r"ATR14:\s*([\d,\.]+)")):
        v = _f(re.search(pat, tech)); 
        if v is not None: c[k] = v
    if px: c["price"] = px
    m = re.search(r"hafta \(\d+ mum\)[^\[]*\[fiyat ([+-][\d\.]+)%, ([^\]]+)\]", tech)
    if m: c["vwap_w_pct"] = float(m.group(1)); c["vwap_w_pos"] = m.group(2).strip()
    m = re.search(r"Hacim profili \(son 150 mum\):[^\n]*?POC [\d,\.]+ \(([+-][\d\.]+)%\)[^\n]*?fiyat (değer alanı içinde|VAH üstünde|VAL altında)", tech)
    if m: c["poc_pct"] = float(m.group(1)); c["vp_pos"] = m.group(2)
    m = re.search(r"Swing[^\n]*direnç: ([\d,\.]+) \(([+-][\d\.]+)%\)", tech)
    if m: c["swing_res_pct"] = float(m.group(2))
    m = re.search(r"Swing[^\n]*destek: ([\d,\.]+) \(([+-][\d\.]+)%\)", tech)
    if m: c["swing_sup_pct"] = float(m.group(2))
    m = re.search(r"üstte ayı/direnç: [^|\n]*?\(([+-][\d\.]+)%\)", tech)
    if m: c["fvg_res_pct"] = float(m.group(1))
    m = re.search(r"altta boğa/destek: [^|\n]*?\(([+-][\d\.]+)%\)", tech)
    if m: c["fvg_sup_pct"] = float(m.group(1))
    m = re.search(r"ort:\s*(-?[\d\.]+)%", sent)
    if m: c["funding_avg"] = float(m.group(1)) / 100
    v = _f(re.search(r"Long/short hesap oranı[^:]*: şimdi ([\d\.]+)", sent))
    if v is not None: c["ls"] = v
    v = _f(re.search(r"Taker alış/satış hacim oranı[^:]*: ([\d\.]+)", sent))
    if v is not None: c["taker"] = v
    v = _f(re.search(r"Hacim sıçraması:[^=]*= ([\d\.]+)x", sent))
    if v is not None: c["vol_spike"] = v
    m = re.search(r"Korku&Açgözlülük[^:]*:\s*[\d-]+:(\d+)", sent)
    if m: c["fng"] = int(m.group(1))
    try:
        l24 = ((extras or {}).get("derivatives") or {}).get("liq_24h")
        if l24: c["liq24_long_usd"] = l24["long_usd"]; c["liq24_short_usd"] = l24["short_usd"]
    except Exception: pass
    return c

def feats(c, atr_pct=None):
    """Yönden bağımsız koşul etiketleri (ilgili ders eşleştirme + ölüm sonrası analiz için)."""
    F = set(); p = c.get("price")
    if c.get("sma50") and c.get("sma200") and p:
        if p < c["sma50"] and p < c["sma200"]: F.add("trend_aşağı")
        elif p > c["sma50"] and p > c["sma200"]: F.add("trend_yukarı")
    if c.get("rsi") is not None: F.update(["rsi_aşırı_alım"] if c["rsi"] >= 70 else ["rsi_aşırı_satım"] if c["rsi"] <= 30 else [])
    fa = c.get("funding_avg")
    if fa is not None and abs(fa) >= 0.0003: F.add("funding_pozitif_aşırı" if fa > 0 else "funding_negatif_aşırı")
    if c.get("ls") is not None: F.update(["ls_long_kalabalık"] if c["ls"] >= 2.0 else ["ls_short_kalabalık"] if c["ls"] <= 0.8 else [])
    if c.get("vwap_w_pct") is not None: F.add("vwap_üstü" if c["vwap_w_pct"] > 0 else "vwap_altı")
    if c.get("vp_pos"): F.add({"değer alanı içinde": "değer_alanı_içi", "VAH üstünde": "VAH_üstü", "VAL altında": "VAL_altı"}[c["vp_pos"]])
    atrp = atr_pct   # metindeki fiyat/ATR küçük coinlerde 2 ondalığa yuvarlı -> ATR% dışarıdan verilir (yoksa "yakın seviye" etiketi atlanır)
    if atrp:
        for key, tag in (("swing_sup_pct", "yakın_destek"), ("fvg_sup_pct", "yakın_destek"), ("swing_res_pct", "yakın_direnç"), ("fvg_res_pct", "yakın_direnç")):
            if c.get(key) is not None and abs(c[key]) <= atrp: F.add(tag)
    if c.get("vol_spike") is not None: F.update(["hacim_zayıf"] if c["vol_spike"] < 0.8 else ["hacim_yüksek"] if c["vol_spike"] >= 1.5 else [])
    a, b = c.get("liq24_long_usd"), c.get("liq24_short_usd")
    if a is not None and b is not None and a + b >= 1e6:
        if a >= 2 * b: F.add("liq_long_baskın")
        elif b >= 2 * a: F.add("liq_short_baskın")
    return sorted(F)

# ---------- kural tabanlı ölüm sonrası ----------
def _hours(a, b):
    try: return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() / 3600
    except Exception: return None

def norm_reason(r):
    r = str(r or "").lower()
    return "stop" if r.startswith("stop") else "hedef" if r.startswith("hedef") else "başabaş" if r.startswith("başabaş") or r.startswith("basabas") else "süre"

def postmortem(rec):
    """Dönüş: [(etiket, öncelik, Türkçe kısa cümle)] — öncelik büyük = daha önemli. LLM yok."""
    side, why, h = rec["side"], rec["exit_reason"], rec.get("hours"); F = set(rec.get("feats") or []); st = rec.get("stances") or {}
    sgn = 1 if side == "LONG" else -1; out = []
    atrp = rec.get("atr_pct"); mfe, mae = rec.get("mfe_pct"), rec.get("mae_pct")
    mfe_atr = mfe / atrp if (mfe is not None and atrp) else None
    stance_vs = lambda a: st.get(a) in ("BULL", "BEAR") and (st.get(a) == "BULL") != (side == "LONG")
    ctx = rec.get("ctx") or {}
    if why == "stop":
        if h is not None and h <= 3: out.append(("hızlı_stop", 9, f"Stop {h:.0f} sa içinde geldi: giriş zamanlaması/seviye zayıftı"))
        if mfe_atr is not None and mfe_atr < 0.3: out.append(("hiç_lehine_gitmedi", 8, "Fiyat girişten sonra hiç lehe gitmedi (giriş anında yön yanlıştı)"))
        elif mfe_atr is not None and mfe_atr >= 1.5: out.append(("yarı_yoldan_döndü", 8, f"Fiyat hedefe yarı yola ({mfe_atr:.1f} ATR) gelip döndü: kısmi kâr/daha yakın hedef düşünülebilir"))
        fa = ctx.get("funding_avg")
        if fa is not None and ((side == "SHORT" and fa <= -0.0003) or (side == "LONG" and fa >= 0.0003)):
            out.append(("funding_aşırı_yok_sayıldı", 8, f"Funding işlem yönünde aşırıydı ({fa*100:+.3f}%), kalabalık taraf sıkışmaya açıktır".replace(".", ",")))
        ls = ctx.get("ls")
        if ls is not None and ((side == "LONG" and ls >= 2.0) or (side == "SHORT" and ls <= 0.8)):
            out.append(("kalabalık_tarafta", 7, f"İşlem kalabalık tarafla aynı yöndeydi (L/S {ls:.2f})".replace(".", ",")))
        if (side == "SHORT" and "yakın_destek" in F) or (side == "LONG" and "yakın_direnç" in F):
            out.append(("yakın_seviyeye_girdi", 7, "Girişte hemen önünde " + ("destek" if side == "SHORT" else "direnç") + " vardı"))
        if (side == "SHORT" and "vwap_üstü" in F) or (side == "LONG" and "vwap_altı" in F):
            out.append(("vwap_ters_taraf", 5, f"Haftalık VWAP'ın {'üstünde short' if side == 'SHORT' else 'altında long'} açıldı"))
        if "değer_alanı_içi" in F: out.append(("değer_alanı_içi", 4, "Fiyat hacim profili değer alanı içindeydi (yönsüz bölge)"))
        lq = rec.get("liq_near") or {}; sd = abs(rec["stop"] / rec["entry"] - 1) * 100 if rec.get("stop") else None
        side_cl = lq.get("up") if side == "SHORT" else lq.get("down")
        if side_cl and sd is not None and abs(side_cl.get("pct", 99)) <= sd + 0.5:
            out.append(("likidasyon_mıknatısı", 6, f"Stop yakınında tahmini likidasyon kümesi vardı ({side_cl.get('pct'):+.1f}%): fitil buraya çekmiş olabilir".replace(".", ",")))
        if stance_vs("duygu_analisti") or stance_vs("teknik_analist"):
            a = "duygu" if stance_vs("duygu_analisti") else "teknik"
            out.append(("ajan_ayrışması", 6, f"{a.capitalize()} analisti ters yöndeydi; ayrışmalı kurulumlarda daha temkinli ol"))
        if rec.get("confidence", 0) >= 80: out.append(("yüksek_güven_yanıldı", 7, f"Yüksek güven (%{rec['confidence']}) yanıldı: güven düzeyi tek başına yeterli değil"))
    elif why == "hedef":
        out.append(("hedef_başarı", 5, "4s+1s uyumlu kurulum hedefe ulaştı" if rec.get("aligned") else "Kurulum hedefe ulaştı"))
        if (side == "SHORT" and "trend_aşağı" in F) or (side == "LONG" and "trend_yukarı" in F): out.append(("trend_yönünde", 4, "Trend yönünde (SMA50/200) işlem işe yaradı"))
        if h is not None and h <= 6: out.append(("hızlı_hedef", 3, f"Hedef {h:.0f} sa içinde geldi"))
    elif why == "başabaş":
        out.append(("başabaş_çıkış", 5, "Stop girişe çekilmişti" + (f"; fiyat hedefe doğru {mfe_atr:.1f} ATR gidip döndü, ücret dahil başabaşa yakın çıkıldı".replace(".", ",") if mfe_atr is not None else "; fiyat döndü, başabaşa yakın çıkıldı")))
        if h is not None and h <= 6: out.append(("hızlı_dönüş", 3, f"Dönüş {h:.0f} sa içinde geldi"))
    else:
        if mfe_atr is not None and mfe_atr < 1.0: out.append(("süre_takipsiz", 8, f"{h:.0f} sa dolunca kapandı, hareket gelmedi (en iyi lehe uzaklık {mfe_atr:.1f} ATR): bekleyen kurulum zaman kaybıdır".replace(".", ",") if h else "Süre doldu, hareket gelmedi"))
        elif mfe_atr is not None: out.append(("hedefe_yaklaştı_süre", 6, f"Hedefe yaklaştı ({mfe_atr:.1f} ATR) ama süre doldu".replace(".", ",")))
        else: out.append(("süre_doldu", 4, "Süre doldu, hedef/stop gelmedi"))
        if rec["pnl_usd"] < 0 and mae is not None and atrp and mae / atrp >= 1.5: out.append(("zararda_süre", 5, "Zararda süre doldu; stop'a yaklaşıldı"))
    out.sort(key=lambda x: -x[1]); return out

def rule_lesson(rec, tags=None):
    tags = tags if tags is not None else postmortem(rec)
    pnl = rec["pnl_usd"]; head = f"{rec['symbol'][:-4]} {rec['side']} {'+' if pnl > 0 else ''}{pnl:.2f}$".replace(".", ",")
    if not tags: return f"{head}: belirgin bir neden saptanamadı."
    return f"{head}: " + "; ".join(t[2].rstrip(".") for t in tags[:2]) + "."

# ---------- kayıt ----------
def build_rec(p, ctx=None, mfe_pct=None, mae_pct=None, extra=None):
    """Kapanmış pozisyon sözlüğü (trader.py şeması) -> yapılandırılmış sonuç. ctx: giriş bağlamı (parse_ctx çıktısı)."""
    ctx = ctx or {}; entry = p["entry"]; sgn = 1 if p["side"] == "LONG" else -1
    if mfe_pct is None and p.get("hi_seen") is not None:
        hi, lo = p["hi_seen"], p["lo_seen"]
        mfe_pct = max(0.0, 100 * ((hi / entry - 1) if sgn > 0 else (1 - lo / entry))); mae_pct = max(0.0, 100 * ((1 - lo / entry) if sgn > 0 else (hi / entry - 1)))
    st = p.get("stances") or {}
    rec = {"id": p["id"], "symbol": p["symbol"], "side": p["side"], "leverage": p.get("leverage", 1), "confidence": p.get("confidence"),
           "entry": entry, "exit": p.get("exit"), "stop": p.get("stop_orig") or p.get("stop"), "target": p.get("target"), "atr_pct": round(100 * p["atr"] / entry, 4) if p.get("atr") else None,
           "pnl_usd": round(p["pnl_usd"], 2), "pnl_pct": round(p.get("pnl_pct", 0), 3), "roe_pct": round(p.get("roe_pct", 0), 2),
           "exit_reason": norm_reason(p.get("exit_reason")), "opened_at": p.get("opened_at"), "closed_at": p.get("closed_at"),
           "hours": round(_hours(p["opened_at"], p["closed_at"]) or 0, 2), "mfe_pct": None if mfe_pct is None else round(mfe_pct, 3), "mae_pct": None if mae_pct is None else round(mae_pct, 3),
           "stances": st, "aligned": st.get("mtf_4h") in ("BULL", "BEAR") and st.get("mtf_4h") == st.get("mtf_giris"),
           "reason": p.get("reason"), "bullets": p.get("bullets"), "liq_near": p.get("liq_near"), "ctx": ctx, "feats": feats(ctx, round(100 * p["atr"] / entry, 4) if p.get("atr") else None)}
    if extra: rec.update(extra)
    rec["closed_ms"] = _ms(rec["closed_at"])
    return rec

def _ms(s):
    try: return int(dt.datetime.fromisoformat(s).timestamp() * 1000)
    except Exception:
        try: return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone(dt.timedelta(hours=3))).timestamp() * 1000)
        except Exception: return None

def add(S, rec, lesson=None):
    """rec'e etiket + kural dersi ekler, depoya yazar (aynı id'yi yeniler). Dönüş: rec."""
    tags = postmortem(rec); rec["tags"] = [t[0] for t in tags]; rec["lesson_rule"] = rule_lesson(rec, tags)
    rec["lesson"] = lesson or rec["lesson_rule"]; rec["lesson_src"] = "llm" if lesson else "kural"
    S["recent"] = [r for r in S["recent"] if r["id"] != rec["id"]] + [rec]; S["recent"] = S["recent"][-MAX_RECENT:]
    row = {k: rec.get(k) for k in ("id", "symbol", "side", "leverage", "confidence", "aligned", "pnl_usd", "pnl_pct", "exit_reason", "hours", "closed_ms", "tags", "feats")}
    row["win"] = rec["pnl_usd"] > 0 and rec["exit_reason"] != "başabaş"   # başabaş çıkışı (≈0 K/Z) kazanç sayılmaz
    S["trades"] = [r for r in S["trades"] if r["id"] != rec["id"]] + [row]; S["trades"] = S["trades"][-MAX_TRADES:]
    return rec

# ---------- istatistik ----------
def _cb(c): c = c or 0; return "<65" if c < 65 else "65-69" if c < 70 else "70-79" if c < 80 else "80+"

def _grp(rows, key):
    g = {}
    for r in rows:
        k = str(key(r)); d = g.setdefault(k, {"n": 0, "win": 0, "pnl": 0.0}); d["n"] += 1; d["win"] += int(r["win"]); d["pnl"] += r["pnl_usd"]
    for d in g.values(): d["wr"] = round(100 * d["win"] / d["n"], 1); d["pnl"] = round(d["pnl"], 2)
    return g

def stats(S, before_ms=None):
    rows = [r for r in S["trades"] if before_ms is None or (r.get("closed_ms") or 0) <= before_ms]
    return {"toplam": _grp(rows, lambda r: "hepsi").get("hepsi", {"n": 0}), "taraf": _grp(rows, lambda r: r["side"]), "güven": _grp(rows, lambda r: _cb(r.get("confidence"))),
            "kaldıraç": _grp(rows, lambda r: f"{r.get('leverage', 1)}x"), "uyum_4s_1s": _grp(rows, lambda r: "uyumlu" if r.get("aligned") else "uyumsuz"),
            "coin": _grp(rows, lambda r: r["symbol"][:-4]), "çıkış": _grp(rows, lambda r: r["exit_reason"])}

def insights(S, min_n=None, before_ms=None):
    """Yalnızca RAPOR: n >= min_n ve genel kazanma oranından ≥20 puan sapan gruplar. Otomatik sıkılaştırma YOK."""
    min_n = min_n or MIN_N; s = stats(S, before_ms); tot = s["toplam"]; out = []
    if tot.get("n", 0) < min_n: return [f"Örneklem küçük (n={tot.get('n', 0)} < {min_n}): istatistiksel çıkarım yapılmaz, hiçbir ayar değişmez."]
    for dim in ("taraf", "güven", "kaldıraç", "uyum_4s_1s", "coin", "çıkış"):
        for k, d in s[dim].items():
            if dim == "çıkış" or d["n"] < min_n: continue
            if abs(d["wr"] - tot["wr"]) >= 20: out.append(f"{dim} {k}: n={d['n']}, kazanma %{d['wr']:.0f} (genel %{tot['wr']:.0f}), net {d['pnl']:+.2f}$ — {'zayıf' if d['wr'] < tot['wr'] else 'güçlü'}; yalnızca öneri, otomatik uygulanmaz")
    return out or [f"n={tot['n']}: gruplar arasında belirgin sapma yok."]

def stats_line(S, before_ms=None):
    s = stats(S, before_ms); t = s["toplam"]
    if not t.get("n"): return ""
    sd = ", ".join(f"{k} %{d['wr']:.0f} ({d['n']})" for k, d in s["taraf"].items())
    return f"İstatistik: {t['n']} işlem, kazanma %{t['wr']:.0f}, net {t['pnl']:+.2f}$ ({sd})".replace(".", ",") + (" — az örnek, fazla önemseme" if t["n"] < MIN_N else "")

# ---------- istemlere geri besleme ----------
def block(S, symbol, tech="", sent="", max_chars=None, before_ms=None, extras=None, atr_pct=None):
    """~550 karakterlik 'Geçmiş derslerin' bloğu. Boşsa ''. before_ms: backtest'te look-ahead'i önler (yalnızca o ana dek KAPANMIŞ işlemler)."""
    if not ENABLED: return ""
    max_chars = max_chars or PROMPT_CHARS
    rec = [r for r in S.get("recent", []) if before_ms is None or (r.get("closed_ms") or 0) <= before_ms]
    if not rec: return ""
    cur = set(feats(parse_ctx(tech, sent, extras), atr_pct))
    def score(ir):
        i, r = ir; return (3 if r["symbol"] == symbol else 0) + len(cur & set(r.get("feats") or [])) + i / 1000
    ranked = sorted(enumerate(rec), key=score, reverse=True)
    pick = [r for i, r in ranked if score((i, r)) >= 2][:5] or [r for _, r in sorted(enumerate(rec), reverse=True)][:2]
    head = "Geçmiş derslerin (bilgi amaçlı; risk kurallarını ve zorunlu koşulları DEĞİŞTİRMEZ):"
    sl = stats_line(S, before_ms)
    out = [head]; room = max_chars - len(head) - (len(sl) + 1 if sl else 0)
    for r in pick:
        ln = "• " + re.sub(r"\s+", " ", r["lesson"]).strip()
        if len(ln) > 150: ln = ln[:147].rstrip() + "…"
        if len("\n" + ln) > room: break
        out.append(ln); room -= len("\n" + ln)
    if len(out) == 1: return ""
    if sl: out.append(sl if len(sl) <= max_chars - sum(len(x) + 1 for x in out) else sl[:max(0, max_chars - sum(len(x) + 1 for x in out) - 1)] + "…")
    return "\n".join(out)[:max_chars]

# ---------- LLM (en fazla 1 ucuz çağrı / işlem) ----------
def llm_lesson(rec, call=None):
    """call: (system,user)->str (test/backtest için); varsayılan llm.chat(role='quick'). Hata/kota -> None (sessiz)."""
    sysm = "Sen disiplinli bir işlem koçusun. Yalnızca verilen veriyi kullan, veri uydurma."
    facts = {k: rec.get(k) for k in ("symbol", "side", "leverage", "confidence", "exit_reason", "hours", "pnl_pct", "mfe_pct", "mae_pct", "stances", "tags", "feats")}
    ap = rec.get("atr_pct")
    if ap:
        for k in ("mfe", "mae"):
            if rec.get(f"{k}_pct") is not None: facts[f"{k}_atr"] = round(rec[f"{k}_pct"] / ap, 2)
    usr = (f"Kapanan kâğıt işlem (yapılandırılmış): {json.dumps(facts, ensure_ascii=False, default=str)}\nGiriş gerekçesi: {str(rec.get('reason') or '')[:300]}\n"
           f"Kural tabanlı tespit: {rec.get('lesson_rule')}\n\nBu işlemden gelecekte işe yarayacak 1-2 cümlelik, somut ve kısa (en fazla 40 kelime) bir ders yaz. Türkçe. "
           "Tek işlemden genelleme yapma ('bu işlemde ...' diye yaz); yalnızca yukarıdaki alanlardaki bilgi ve sayıları kullan, yeni sayı uydurma; "
           "stop/hedef/kaldıraç kurallarını değiştirmeyi önerme, yalnızca bir dahaki sefere neye dikkat edileceğini söyle. Sadece dersin metnini döndür.")
    try:
        if call is None:
            import llm; txt = llm.chat(sysm, usr, role="quick", max_tokens=400, retries=1)
        else: txt = call(sysm, usr)
    except (Exception, SystemExit): return None
    txt = re.sub(r"\s+", " ", re.sub(r"[*_`#>]", "", str(txt or ""))).strip().strip('"')
    if len(txt) < 15: return None
    if re.search(r"(stop|hedef|kaldıraç)[^.;]*?(çek|değiştir|sıkılaştır|artır|azalt|büyüt|küçült|kısmen)", txt.lower()): return None   # kural değişikliği önerisi -> kural dersi kalır
    return txt[:260].rsplit(" ", 1)[0] + "…" if len(txt) > 260 else txt

def _budget_ok():
    try:
        st = json.load(open(os.path.join(HERE, "outputs", "trader", "state.json"))); b = json.load(open(os.path.join(HERE, "config.json")))["trader"]["daily_llm_budget"]
        return (st.get("llm_calls") or 0) < b - 3
    except Exception: return True

# ---------- canlı trader için ----------
def _tag(t): return str(t).replace(" ", "T").replace(":", "")

def backfill_ctx(p):
    """Eski pozisyonlarda entry_ctx yoksa, o saatlik tartışmanın çıktı dosyasından (outputs/<SYM>_1h_<bar>.json) çıkar."""
    try:
        d = json.load(open(os.path.join(HERE, "outputs", f"{p['symbol']}_1h_{_tag(p['signal_bar_utc'])}.json")))
        c = parse_ctx(d.get("tech_data"), d.get("sentiment_data"), d.get("extras"))
        try:
            m = json.load(open(os.path.join(HERE, "outputs", f"{p['symbol']}_mtf-1h_{_tag(p['signal_bar_utc'])}.json")))
            c["mtf"] = {"trend_4h": (m.get("trend_4h") or {}), "giris_1h": (m.get("entry") or {})}
        except Exception: pass
        return c
    except Exception: return {}

def on_close(p):
    """Kapanışta ANINDA (ağsız): yapılandırılmış kayıt + kural dersi -> lessons.json. Dönüş: kural dersi (Telegram için yedek)."""
    if not ENABLED: return None
    ctx = p.get("entry_ctx") or backfill_ctx(p)
    rec = build_rec(p, ctx)
    return locked_update(lambda S: add(S, rec)["lesson"])

def finalize(p, wait_s=25):
    """Tek ucuz LLM çağrısı: ders metnini iyileştirir. En fazla wait_s bekler; gecikirse kural dersi döner, iş parçacığı bitince depoyu günceller."""
    S = load(); rec = next((r for r in S["recent"] if r["id"] == p["id"]), None)
    if not rec: return None
    if not (USE_LLM and CFG.get("llm", True) and _budget_ok() and os.environ.get("CA_DRY_RUN") != "1"): return rec["lesson"]
    box = {}
    def work():
        t = llm_lesson(rec)
        if t:
            def upd(S):
                for r in S["recent"]:
                    if r["id"] == rec["id"]: r["lesson"] = t; r["lesson_src"] = "llm"
            try: locked_update(upd)
            except Exception: pass
            box["t"] = t
    th = threading.Thread(target=work, daemon=True); th.start(); th.join(wait_s)
    return box.get("t") or rec["lesson"]

def morning_lines(S, max_n=2):
    """Sabah özeti için: [istatistik satırı, son ders(ler)...]. Ders yoksa []."""
    if not S.get("recent"): return []
    L = [stats_line(S)]
    for r in S["recent"][-max_n:][::-1]: L.append("Son ders: " + r["lesson"])
    ins = [x for x in insights(S) if "yalnızca öneri" in x][:1]
    return [x for x in L + ins if x]

def rec_from_backtest(row, t_open_ms, t_exit_ms, k1, i, ctx, aligned, stances):
    """backtest_1h satırı -> ders kaydı (look-ahead yok: kayıt, çıkış zamanından önce erişilebilir değil, closed_ms ile filtrelenir)."""
    side, fill = row["yon"], row["giris"]; sg = 1 if side == "LONG" else -1
    seg = k1[(k1.ct > t_open_ms) & (k1.ct <= t_exit_ms + 1)]
    hi, lo = (float(seg.high.max()), float(seg.low.min())) if len(seg) else (fill, fill)
    mfe = max(0.0, 100 * ((hi / fill - 1) if sg > 0 else (1 - lo / fill))); mae = max(0.0, 100 * ((1 - lo / fill) if sg > 0 else (hi / fill - 1)))
    why = {"STOP": "stop", "HEDEF": "hedef", "SÜRE": "süre"}[row["cikis_nedeni"]]
    iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%dT%H:%M:%S%z")
    p = {"id": f"{row['mum_utc']}-{side}", "symbol": row.get("symbol", "SOLUSDT"), "side": side, "leverage": row["kaldirac"], "confidence": row["guven"], "entry": fill,
         "exit": row["cikis"], "stop": row["stop"], "target": row["hedef"], "atr": row["atr"], "pnl_usd": row["pnl_usd"], "pnl_pct": 100 * row["pnl_usd"] / row["buyukluk_usd"],
         "roe_pct": 100 * row["pnl_usd"] / row["teminat_usd"], "exit_reason": why, "opened_at": iso(t_open_ms), "closed_at": iso(t_exit_ms), "stances": stances, "reason": row.get("gerekce")}
    return build_rec(p, ctx, mfe_pct=mfe, mae_pct=mae, extra={"aligned": aligned})
