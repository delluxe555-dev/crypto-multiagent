"""Geriye dönük test (ücretsiz limit dostu): seçilen N geçmiş tarihte YALNIZCA hakemi (1 LLM çağrısı/tarih, kompakt veri) çalıştırır.
BUY -> sonraki H mum long (ATR stop ile), HOLD/SELL -> nakit. Taraf başına %0,1 komisyon + %0,05 kayma düşülür.
Aynı pencerelerde al-ve-tut ile karşılaştırır. LLM yanıtları outputs/.cache/bt_* altında saklanır (tekrar çalıştırmak bedava).
Kullanım: python backtest.py BTCUSDT [N=10] [--interval 1d] [--step 7]
Uyarılar: (1) Model bu tarihlerden sonrasını eğitimden biliyor olabilir (look-ahead). (2) N küçük -> istatistiksel anlamı zayıf.
(3) Geçmiş funding/OI/emir defteri yok; yalnızca teknik veri + Korku&Açgözlülük (1d) kullanılır."""
import sys, os, json, argparse
import data, llm, paper, risk_rules
from llm import chat, parse_json

OUTDIR = os.environ.get("CA_OUT", "outputs")

def main(symbol, n, interval, step):
    hz = paper.HORIZON_BARS.get(interval, 7) if interval != "1d" else 7
    df = data.add_indicators(data.klines(symbol, interval=interval, limit=1000))
    fng_all = {d: (v, k) for d, v, k in (data.fear_greed(1000) or [])} if interval == "1d" else {}
    last = len(df) - 1 - hz
    idxs = [i for i in [last - step * k for k in range(n)][::-1] if i > 200]
    cdir = os.path.join(OUTDIR, ".cache"); os.makedirs(cdir, exist_ok=True)
    cpath = os.path.join(cdir, f"bt_{symbol}_{interval}.json"); cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    cost = paper.FEE + paper.SLIP
    rows, eq_s, eq_b = [], 1.0, 1.0
    for i in idxs:
        tech, _ = data.snapshot(symbol, df, i=i, interval=interval)
        d = str(df.date.iloc[i]); f = fng_all.get(d)
        sent = f"Korku&Açgözlülük {d}: {f[0]} ({f[1]})" if f else "Duygu verisi yok"
        if d not in cache:
            cache[d] = chat("Sen bir kripto yatırım komitesisin. Yalnızca verilen veriyi kullan.",
                            f"{tech}\n{sent}\n\nÖnümüzdeki {hz} mum için karar ver. Gidiş-dönüş maliyet ~%{cost*200:.1f}. SADECE JSON (anahtarlar aynen): "
                            '{"karar":"BUY|SELL|HOLD","guven":0-100,"gerekce":"<30 kelime>"}', max_tokens=1000, role="deep")
            cache.setdefault('_providers', {})[d] = llm.last_provider()
            json.dump(cache, open(cpath, "w"), ensure_ascii=False, indent=2)
        j = parse_json(cache[d]) or {}
        j = {{"decision": "karar", "confidence": "guven", "reason": "gerekce"}.get(k, k): v for k, v in j.items()}
        karar = j.get("karar") if j.get("karar") in ("BUY", "SELL", "HOLD") else "HOLD"
        entry = df.close.iloc[i]; atr = df.atr14.iloc[i]
        stop = entry - risk_rules.ATR_MULT.get(interval, 1.5) * atr
        fut = df.iloc[i + 1:i + 1 + hz]; exitpx, why = fut.close.iloc[-1], "süre"
        for _, r in fut.iterrows():
            if r.low <= stop: exitpx, why = stop, "stop"; break
        bh = fut.close.iloc[-1] / entry - 1
        st = (exitpx * (1 - cost)) / (entry * (1 + cost)) - 1 if karar == "BUY" else 0.0
        eq_b *= 1 + bh; eq_s *= 1 + st
        rows.append({"date": d, "close": round(entry, 2), "karar": karar, "guven": j.get("guven"), "cikis": why if karar == "BUY" else None,
                     "al_tut_%": round(bh * 100, 2), "strateji_%": round(st * 100, 2), "gerekce": j.get("gerekce")})
        print(rows[-1])
    dec = [r for r in rows if r["karar"] in ("BUY", "SELL")]
    res = {"symbol": symbol, "interval": interval, "model": llm.MODEL, "providers": sorted(set(v for k, v in cache.get("_providers", {}).items() if v)), "n": len(rows), "ufuk_mum": hz, "adim_mum": step,
           "maliyet_taraf_basi": cost, "strateji_getiri_%": round((eq_s - 1) * 100, 2), "al_tut_ayni_pencereler_%": round((eq_b - 1) * 100, 2),
           "yon_isabeti_%": round(100 * sum((r["karar"] == "BUY") == (r["al_tut_%"] > 0) for r in dec) / len(dec), 1) if dec else None,
           "BUY_sayisi": sum(r["karar"] == "BUY" for r in rows), "yeni_llm_cagrisi": llm.CALLS["n"],
           "uyari": "Küçük örnek + olası look-ahead; sonuç kanıt değildir.", "rows": rows}
    json.dump(res, open(os.path.join(OUTDIR, f"backtest_{symbol}_{interval}.json"), "w"), ensure_ascii=False, indent=2, default=str)
    print(f"=== Strateji: {res['strateji_getiri_%']}%  Al-tut (aynı pencereler): {res['al_tut_ayni_pencereler_%']}%  "
          f"Yön isabeti: {res['yon_isabeti_%']}%  LLM çağrısı: {res['yeni_llm_cagrisi']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("symbol"); ap.add_argument("n", nargs="?", type=int, default=10)
    ap.add_argument("--interval", default="1d", choices=["15m", "1h", "4h", "1d"]); ap.add_argument("--step", type=int, default=7)
    a = ap.parse_args(); main(a.symbol.upper(), a.n, a.interval, a.step)
