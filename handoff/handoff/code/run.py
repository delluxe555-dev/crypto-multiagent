"""Kullanım:
  python run.py BTCUSDT                    # günlük (1d) tam analiz: 6 LLM çağrısı
  python run.py ETHUSDT --interval 1h      # gün içi: 15m | 1h | 4h | 1d
  python run.py BTCUSDT --mtf --entry 1h   # çoklu zaman dilimi: 4h trend + 1h giriş (2 LLM çağrısı), yalnızca hizalıysa sinyal
  CA_DRY_RUN=1 python run.py BTCUSDT       # LLM çağırmadan boru hattı testi (SAHTE yanıt, outputs_dryrun/)
Çıktılar: outputs/<SEMBOL>_<aralık>_<zaman>.json/.md, outputs/ledger.json/.csv (kâğıt işlem), outputs/summary.json (pano)."""
import sys, os, json, time, argparse
if os.environ.get("CA_DRY_RUN") == "1": os.environ.setdefault("CA_OUT", "outputs_dryrun")
OUTDIR = os.environ.get("CA_OUT", "outputs")
import data, agents, llm, extras, paper, risk_rules, lessons
from llm import parse_json as _pj

KEYMAP = {"decision": "karar", "confidence": "guven", "target": "hedef", "reason": "gerekce", "rationale": "gerekce",
          "approve": "onay", "approved": "onay", "position_usd": "pozisyon_usd", "note": "not", "entry": "giris"}
def parse_json(txt):
    j = _pj(txt)
    return {KEYMAP.get(k, k): v for k, v in j.items()} if isinstance(j, dict) else j

def cached(cache, path, name, fn):
    """Adım çıktısını önbelleğe al: aynı mum için yeniden çalıştırmada LLM çağrısını tekrarlama (ücretsiz limit dostu)."""
    if name in cache: print(f"[{name}] (önbellekten)"); return cache[name]
    print(f"[{name}] ..."); cache[name] = fn()
    cache.setdefault("_providers", {})[name] = llm.last_provider()
    print(f"  -> yanıtlayan: {cache['_providers'][name]}")
    json.dump(cache, open(path, "w"), ensure_ascii=False, indent=2)
    return cache[name]

def tag(t): return str(t).replace(" ", "T").replace(":", "")

def lesson_block(symbol, df, tech, sent, ext=None):
    """'Geçmiş derslerin' bloğu (canlı depo: outputs/trader/lessons.json veya CA_LESSONS). Hata olursa '' (akışı bozmaz)."""
    try:
        return lessons.block(lessons.load(), symbol, tech, sent, extras=ext, atr_pct=100 * float(df.atr14.iloc[-1]) / float(df.close.iloc[-1]))
    except Exception as e:
        print("  [ders bloğu atlandı]", e); return ""

def load_market(symbol, interval):
    df = data.add_indicators(data.klines(symbol, interval=interval, limit=400))
    fund, fng, oi = data.funding(symbol), data.fear_greed(30), data.open_interest(symbol, interval)
    tech, sent = data.snapshot(symbol, df, fng=fng, fund=fund, oi=oi, interval=interval)
    ext_txt, ext = extras.text(symbol, df, interval)
    return df, tech, sent + "\n" + ext_txt, ext

def finish(L, symbol, interval, df, when, decision, stances, extra_out):
    """Deterministik risk + kâğıt defter + hafıza güncellemesi + pano özeti."""
    price, atr = float(df.close.iloc[-1]), float(df.atr14.iloc[-1])
    rk = risk_rules.size(decision, price, atr, paper.equity(L), paper.realized_today(L), interval)
    t = paper.record(L, symbol, interval, when, decision, price, rk["stop"], decision.get("hedef"), rk["pozisyon_usd"], stances, rk["engel"])
    paper.save(L)
    s = paper.summary(L, {})
    sp = os.path.join(OUTDIR, "summary.json")
    prev = json.load(open(sp)).get("latest", {}) if os.path.exists(sp) else {}
    prev[f"{symbol}_{interval}"] = {"time": str(when), "karar": decision.get("karar"), "guven": decision.get("guven"),
                                    "fiyat": price, "stop": rk["stop"], "hedef": decision.get("hedef"),
                                    "pozisyon_usd": rk["pozisyon_usd"], "engel": rk["engel"], **extra_out}
    s["latest"] = prev; json.dump(s, open(sp, "w"), ensure_ascii=False, indent=2, default=str)
    return rk, t

def main(symbol, interval="1d"):
    t0 = time.time(); agents.CTX["interval"] = interval; os.makedirs(os.path.join(OUTDIR, ".cache"), exist_ok=True)
    df, tech, sent, ext = load_market(symbol, interval)
    L = paper.update(paper.load(), {(symbol, interval): df})
    mem = paper.memory_text(L, symbol, interval)
    lb = lesson_block(symbol, df, tech, sent, ext)
    print(tech, "\n", sent, "\n\nHafıza:\n", mem, "\n")
    when = str(df.date.iloc[-1])
    out = {"symbol": symbol, "interval": interval, "model": llm.MODEL, "data_date": when, "tech_data": tech,
           "sentiment_data": sent, "extras": ext, "memory": mem, "lessons_block": lb, "dry_run": os.environ.get("CA_DRY_RUN") == "1"}
    cpath = os.path.join(OUTDIR, ".cache", f"{symbol}_{interval}_{tag(when)}_v2.json")
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    C = lambda name, fn: cached(cache, cpath, name, fn)
    out["teknik_analist"] = C("teknik_analist", lambda: agents.technical(tech)); print(out["teknik_analist"], "\n")
    out["duygu_analisti"] = C("duygu_analisti", lambda: agents.sentiment(sent)); print(out["duygu_analisti"], "\n")
    out["boga"] = C("boga", lambda: agents.bull(out["teknik_analist"], out["duygu_analisti"])); print(out["boga"], "\n")
    out["ayi"] = C("ayi", lambda: agents.bear(out["teknik_analist"], out["duygu_analisti"], out["boga"])); print(out["ayi"], "\n")
    raw = C("hakem_raw", lambda: agents.judge(tech, out["teknik_analist"], out["duygu_analisti"], out["boga"], out["ayi"], mem, lb)[0])
    out["hakem"] = parse_json(raw) or {}
    if not out["hakem"]: out["hakem_raw"] = raw
    print(raw, "\n")
    raw = C("risk_raw", lambda: agents.risk(tech, json.dumps(out["hakem"] or raw, ensure_ascii=False))[0])
    out["risk_llm"] = parse_json(raw)
    if out["risk_llm"] is None: out["risk_raw"] = raw
    print(raw, "\n")
    stances = {"teknik_analist": paper.stance(out["teknik_analist"]), "duygu_analisti": paper.stance(out["duygu_analisti"])}
    rk, t = finish(L, symbol, interval, df, when, out["hakem"], stances, {"mod": "tam"})
    out.update(providers=cache.get("_providers"), risk_kural=rk, kagit_islem=t, runtime_s=round(time.time() - t0, 1), llm_calls=llm.CALLS["n"])
    base = os.path.join(OUTDIR, f"{symbol}_{interval}_{tag(when)}")
    json.dump(out, open(base + ".json", "w"), ensure_ascii=False, indent=2, default=str)
    h = out["hakem"]
    md = [f"# {symbol} {interval} — {when} (sağlayıcılar: {json.dumps(cache.get('_providers'), ensure_ascii=False)})" + ("  **[DRY-RUN: SAHTE YANITLAR]**" if out["dry_run"] else ""), "",
          f"**Karar:** {h.get('karar')}  **Güven:** {h.get('guven')}  **Stop (hakem):** {h.get('stop')}  **Hedef:** {h.get('hedef')}", "",
          f"**Gerekçe:** {h.get('gerekce')}", "",
          f"**Kural tabanlı risk:** stop {rk['stop']} ({rk['stop_kaynak']}), pozisyon ${rk['pozisyon_usd']}, engel: {rk['engel']}", "",
          f"**LLM risk yöneticisi:** {json.dumps(out['risk_llm'], ensure_ascii=False)}", "", f"## Hafıza", "", mem, ""]
    for k in ["tech_data", "sentiment_data", "teknik_analist", "duygu_analisti", "boga", "ayi"]:
        md += [f"## {k}", "", out[k], ""]
    open(base + ".md", "w").write("\n".join(md))
    print(f"=== {symbol} {interval}: {h.get('karar')} (güven {h.get('guven')}), süre {out['runtime_s']}s, "
          f"{out['llm_calls']} LLM çağrısı -> {base}.md")
    return out

def main_mtf(symbol, entry_iv="1h"):
    """4h trend + düşük zaman dilimi giriş. Yalnızca 4h YUKARI & giriş LONG (veya ASAGI & SHORT) ise sinyal.
    Kâğıt defter yalnızca long tutar; SHORT sinyali kaydedilir ama işlem açılmaz."""
    t0 = time.time(); os.makedirs(os.path.join(OUTDIR, ".cache"), exist_ok=True)
    df4, tech4, sent4, _ = load_market(symbol, "4h")
    dfl, techl, sentl, ext = load_market(symbol, entry_iv)
    L = paper.update(paper.load(), {(symbol, f"mtf-{entry_iv}"): dfl})
    when = str(dfl.date.iloc[-1])
    cpath = os.path.join(OUTDIR, ".cache", f"{symbol}_mtf-{entry_iv}_{tag(when)}.json")
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    C = lambda name, fn: cached(cache, cpath, name, fn)
    tr_raw = C("trend_4h_raw", lambda: agents.trend_4h(tech4, sent4, lesson_block(symbol, df4, tech4, sent4))[0]); tr = parse_json(tr_raw) or {}
    en_raw = C("entry_raw", lambda: agents.entry_ltf(techl, sentl, json.dumps(tr, ensure_ascii=False), entry_iv, lesson_block(symbol, dfl, techl, sentl, ext))[0]); en = parse_json(en_raw) or {}
    trend, giris = str(tr.get("trend", "")).upper(), str(en.get("giris", "")).upper()
    aligned = (trend == "YUKARI" and giris == "LONG") or (trend == "ASAGI" and giris == "SHORT")
    karar = ("BUY" if giris == "LONG" else "SELL") if aligned else "HOLD"
    decision = {"karar": karar, "guven": min(tr.get("guven") or 0, en.get("guven") or 0) if aligned else None,
                "stop": en.get("stop"), "hedef": en.get("hedef"), "gerekce": f"4h: {tr.get('gerekce')} | {entry_iv}: {en.get('gerekce')}"}
    rk, t = finish(L, symbol, f"mtf-{entry_iv}", dfl, when, decision, {}, {"mod": "mtf", "trend_4h": trend, "giris": giris, "hizali": aligned})
    out = {"symbol": symbol, "mode": "mtf", "entry_interval": entry_iv, "time": when, "trend_4h": tr, "entry": en, "hizali": aligned,
           "karar": decision, "risk_kural": rk, "providers": cache.get("_providers"), "runtime_s": round(time.time() - t0, 1), "llm_calls": llm.CALLS["n"],
           "dry_run": os.environ.get("CA_DRY_RUN") == "1"}
    json.dump(out, open(os.path.join(OUTDIR, f"{symbol}_mtf-{entry_iv}_{tag(when)}.json"), "w"), ensure_ascii=False, indent=2, default=str)
    print(f"=== {symbol} MTF 4h={trend} {entry_iv}={giris} hizalı={aligned} -> {karar}; {out['llm_calls']} LLM çağrısı")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="BTCUSDT")
    ap.add_argument("--interval", default="1d", choices=["15m", "1h", "4h", "1d"])
    ap.add_argument("--mtf", action="store_true", help="4h trend + --entry giriş, yalnızca hizalıysa sinyal")
    ap.add_argument("--entry", default="1h", choices=["15m", "1h"])
    a = ap.parse_args()
    (main_mtf(a.symbol.upper(), a.entry) if a.mtf else main(a.symbol.upper(), a.interval))
