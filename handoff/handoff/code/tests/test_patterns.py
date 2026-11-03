"""patterns.py testleri: sentetik seriler + gerçek mumlar + look-ahead yok kontrolü + kompaktlık. Çalıştır: .venv/bin/python -W ignore tests/test_patterns.py [--real]"""
import os, sys, re, random, time
os.environ["CA_NO_KEYLEVELS"] = "1"   # kritik seviye satırı canlıya özel; look-ahead karşılaştırması onsuz
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE); os.chdir(HERE)
import numpy as np, pandas as pd
import patterns, data, levels

def build(path, noise=0.0, seed=1, vol=None, wick=0.15, bars=None):
    """Kırılma noktaları (bar, fiyat) arasında doğrusal kapanış + küçük fitil -> OHLCV df."""
    rnd = random.Random(seed); xs, ys = zip(*path); n = xs[-1] + 1
    c = np.interp(np.arange(n), xs, ys) + np.array([rnd.uniform(-noise, noise) for _ in range(n)])
    o = np.r_[c[0], c[:-1]]; step = np.abs(np.diff(c, prepend=c[0])) + 0.2
    h = np.maximum(o, c) + step * wick + 0.05; l = np.minimum(o, c) - step * wick - 0.05
    v = np.full(n, 100.0) if vol is None else vol
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=n, freq="h").strftime("%Y-%m-%d %H:%M"), "open": o, "high": h, "low": l, "close": c, "volume": v})
    return data.add_indicators(df)

def lead(price=150, n=100): return [(0, price), (n, price)]
ok = fails = 0
def check(name, cond, info=""):
    global ok, fails
    if cond: ok += 1; print("  ✔", name)
    else: fails += 1; print("  ✘", name, info)

def synth():
    print("Sentetik testler")
    # düz seri: formasyon yok, çökmemeli
    flat = build([(0, 100), (200, 100.5)], noise=0.3); t = patterns.text(flat); check("düz seri çökmeden metin üretir", t.startswith("Formasyonlar") and "Harmonik" not in t and "Grafik" not in t, t)
    # çift tepe: 100 -> 130 (tepe1) -> 112 -> 130 (tepe2) -> 120 (boyun 112 kırılmadı)
    p = [(0, 100), (60, 100), (80, 130), (95, 112), (110, 130.3), (118, 121)]
    t = patterns.text(build(p, noise=0.2)); check("çift tepe", "Çift tepe" in t, t)
    p = [(0, 100), (60, 100), (80, 130), (95, 112), (110, 130.3), (125, 108)]
    t = patterns.text(build(p, noise=0.2)); check("çift tepe boyun kırıldı", "Çift tepe" in t and "kırıldı" in t, t)
    # çift dip
    p = [(0, 130), (60, 130), (80, 100), (95, 118), (110, 100.3), (118, 109)]
    t = patterns.text(build(p, noise=0.2)); check("çift dip", "Çift dip" in t, t)
    # OBO
    p = [(0, 100), (50, 100), (65, 125), (75, 110), (90, 140), (100, 110), (113, 124.5), (121, 112)]
    t = patterns.text(build(p, noise=0.2)); check("omuz-baş-omuz", "OBO" in t, t)
    p = [(0, 150), (50, 150), (65, 125), (75, 140), (90, 110), (100, 140), (113, 125.5), (121, 138)]
    t = patterns.text(build(p, noise=0.2)); check("ters OBO", "Ters OBO" in t, t)
    # yükselen üçgen: düz direnç 130, yükselen dipler
    p = [(0, 100), (40, 100), (55, 130), (70, 108), (85, 130), (98, 115), (110, 130), (120, 121), (128, 129)]
    t = patterns.text(build(p, noise=0.15)); check("yükselen üçgen", "Yükselen üçgen" in t, t)
    # simetrik üçgen
    p = [(0, 100), (40, 100), (55, 140), (70, 108), (85, 133), (98, 114), (110, 127), (120, 118), (127, 124)]
    t = patterns.text(build(p, noise=0.15)); check("simetrik üçgen / daralan yapı", "üçgen" in t or "kama" in t, t)
    # yükselen kama
    p = [(0, 100), (40, 100), (55, 120), (69, 108), (83, 128), (96, 120), (110, 134), (122, 129), (128, 133)]
    t = patterns.text(build(p, noise=0.15)); check("kama (yükselen)", "kama" in t, t)
    # boğa bayrağı: direk 100->140 (10 bar), 12 bar yatay/hafif aşağı
    p = [(0, 100), (60, 100), (72, 150), (84, 142), (86, 143)]
    t = patterns.text(build(p, noise=0.4)); check("boğa bayrağı", "bayrak" in t.lower() or "flama" in t.lower(), t)
    # range yukarı kırılım
    rr = [(0, 100)] + [(20 + 8 * j, 110 if j % 2 else 100) for j in range(6)] + [(76, 100), (84, 118), (88, 113)]
    rr = sorted(set(rr)); t = patterns.text(build(rr, noise=0.4)); check("range kırılımı (ya da yapı)", "Range" in t or "range" in t or "kırılım" in t, t)
    # harmonik: boğa Gartley X=100 A=200 B=138.2 C=169.1 D=121.4 (XA=100)
    X, A, B, C, D = 100, 200, 138.2, 169.1, 121.4
    p = [(0, 150), (20, 150), (30, X), (50, A), (68, B), (82, C), (100, D)]
    t = patterns.text(build(p, noise=0.3)); check("boğa Gartley (PRZ'de)", "Gartley" in t and "Boğa" in t, t)
    # Bat: AB 0.45, AD 0.886
    B = A - 0.45 * 100; C = B + 0.5 * (A - B); D = A - 0.886 * 100
    p = [(0, 150), (20, 150), (30, 100), (50, 200), (68, B), (82, C), (100, D)]
    t = patterns.text(build(p, noise=0.3)); check("Bat", "Bat" in t, t)
    # Butterfly: AB 0.786, AD 1.272 (D, X'in altı)
    B = A - 0.786 * 100; C = B + 0.5 * (A - B); D = A - 1.272 * 100
    p = [(0, 150), (20, 150), (30, 100), (50, 200), (68, B), (82, C), (100, D)]
    t = patterns.text(build(p, noise=0.3)); check("Butterfly", "Butterfly" in t, t)
    # Crab: AB 0.5, AD 1.618
    B = A - 0.5 * 100; C = B + 0.6 * (A - B); D = A - 1.618 * 100
    p = [(0, 190), (20, 190), (30, 100), (50, 200), (68, B), (82, C), (100, D)]
    t = patterns.text(build(p, noise=0.3)); check("Crab", "Crab" in t, t)
    # Ayı Gartley (tersi)
    X, A = 200, 100; B = A + 0.618 * 100; C = B - 0.5 * (B - A); D = A + 0.786 * 100
    p = [(0, 150), (20, 150), (30, X), (50, A), (68, B), (82, C), (100, D)]
    t = patterns.text(build(p, noise=0.3)); check("ayı Gartley", "Ayı Gartley" in t, t)
    # ABCD boğa: A=200 B=150 C=175 D=125 (AB=CD=50, BC/AB=.5)
    p = [(0, 190), (60, 190), (75, 200), (90, 150), (102, 175), (117, 125)]
    t = patterns.text(build(p, noise=0.2)); check("ABCD", "ABCD" in t or "Harmonik" in t, t)
    # mum: düşüş trendi + destek + yutan boğa + hacim
    c = [(0, 150), (40, 150), (70, 120), (80, 128), (90, 120.5), (100, 108)]
    df = build(c + [(104, 108)], noise=0.1)
    df = df.iloc[:101].copy().reset_index(drop=True)
    df.loc[100, ["open", "close", "high", "low", "volume"]] = [df.close[99] - 0.2, df.close[99] + 3.5, df.close[99] + 3.7, df.close[99] - 0.8, 400]
    df.loc[99, ["open", "close"]] = [df.close[98] , df.close[98] - 1.6]
    df = data.add_indicators(df[["date", "open", "high", "low", "close", "volume"]])
    t = patterns.text(df); check("mum formasyonu satırı üretildi (bağlamlı)", t.splitlines()[1].startswith("Mum:"), t)
    # çekiç yapısı
    df2 = df.copy(); p0 = df2.close[99]
    df2.loc[100, ["open", "high", "low", "close", "volume"]] = [p0 - 0.3, p0 + 0.2, p0 - 5.0, p0 + 0.1, 350]; df2 = data.add_indicators(df2[["date", "open", "high", "low", "close", "volume"]])
    t = patterns.text(df2); print("   mum satırı:", t.splitlines()[1])
    # doğrudan mum fonksiyonu birimleri
    o = np.array([10, 10, 10, 10, 10, 10, 9.0]); 
    # Yutan boğa/hammer yön doğrulaması: direkt çağrı
    n = 40; c0 = np.linspace(120, 100, n); o0 = c0 + 0.5; h0 = o0 + 0.3; l0 = c0 - 0.3; v0 = np.full(n, 100.0)
    k = n - 1; o0[k], c0[k], h0[k], l0[k], v0[k] = 99.0, 103.5, 103.7, 98.8, 300      # önceki kırmızı gövdeyi yutar
    atr = patterns._atr(h0, l0, c0); fr = patterns.fractals(h0, l0)
    res = patterns.candles(o0, h0, l0, c0, v0, atr, [(5, 99.5, "L")] + fr, k)
    check("yutan boğa algılandı (düşüş trendi, destek, hacim)", any("Yutan boğa" in t for _, t in res), res)
    o1, c1, h1, l1 = o0.copy(), c0.copy(), h0.copy(), l0.copy(); o1[k], c1[k], h1[k], l1[k] = 100.5, 100.8, 100.9, 95.0
    res = patterns.candles(o1, h1, l1, c1, v0, atr, [(5, 95.2, "L")] + fr, k)
    check("çekiç algılandı", any("Çekiç" in t for _, t in res), res)
    # kayan yıldız yukarı trendde
    c2 = np.linspace(100, 120, n); o2 = c2 - 0.5; h2 = c2 + 0.3; l2 = o2 - 0.3; v2 = np.full(n, 100.0)
    o2[k], c2[k], h2[k], l2[k], v2[k] = 120.0, 119.9, 125.5, 119.8, 300
    atr2 = patterns._atr(h2, l2, c2); res = patterns.candles(o2, h2, l2, c2, v2, atr2, [(5, 125.2, "H")], k)
    check("kayan yıldız algılandı", any("Kayan yıldız" in t for _, t in res), res)
    # uyumsuzluk: fiyat HH, RSI LH
    p = [(0, 100), (40, 100), (60, 130), (70, 118), (90, 131), (100, 126)]
    t = patterns.text(build(p, noise=0.5)); print("   uyumsuzluk satırı:", [x for x in t.splitlines() if x.startswith("Uyum")])

def lookahead(real=True):
    print("Look-ahead testi (gerçek mumlar)")
    random.seed(7); bad = 0; tot = 0; lens = []; tmax = 0; cnt = {}
    sets = [("BTCUSDT", "1h"), ("ETHUSDT", "1h"), ("SOLUSDT", "1h"), ("BTCUSDT", "4h"), ("ETHUSDT", "4h"), ("SOLUSDT", "4h")]
    for sym, iv in sets:
        df = data.add_indicators(data.klines(sym, iv, 1000))
        for i in sorted(random.sample(range(120, len(df)), 40)):
            t0 = time.time(); a = patterns.text(df, i, iv); tmax = max(tmax, time.time() - t0)
            b = patterns.text(df.iloc[:i + 1].copy(), None, iv)
            # tam snapshot da aynı mı
            tot += 1
            if a != b: bad += 1; print("  FARK", sym, iv, i, "\n", a, "\n", b)
            if "hesaplanamadı" in a: bad += 1; print("  HATA", a)
            lens.append(len(a))
            for key in ("Çift tepe", "Çift dip", "Üçlü", "OBO", "üçgen", "kama", "kanal", "ayrak", "lama", "Range", "Gartley", "Bat", "Butterfly", "Crab", "Cypher", "Shark", "ABCD", "uyumsuzluğu", "CHoCH", "BOS", "OB ", "süpürme", "Yutan", "Çekiç", "Kayan", "Doji", "Marubozu", "Harami", "yıldızı", "Fib"):
                if key in a: cnt[key] = cnt.get(key, 0) + 1
        # indikatörlü df ile kesilmiş df aynı snapshot'ı üretmeli
        i = len(df) - 40; s1 = data.snapshot(sym, df, i, interval=iv)[0]; s2 = data.snapshot(sym, df.iloc[:i + 1].copy(), None, interval=iv)[0]
        tot += 1
        if s1 != s2: bad += 1; print("  SNAPSHOT FARKI", sym, iv)
    check(f"look-ahead yok ({tot} karşılaştırma, hata {bad})", bad == 0)
    check(f"kompakt: ort {np.mean(lens):.0f} / maks {max(lens)} karakter (sınır ~{patterns.MAX_CHARS+150})", max(lens) <= patterns.MAX_CHARS + 150 and np.mean(lens) <= 800, (np.mean(lens), max(lens)))
    check(f"hız: en yavaş çağrı {tmax:.2f}s", tmax < 2.0)
    print("   tespit sıklıkları (240 örnekte):", dict(sorted(cnt.items(), key=lambda kv: -kv[1])))

if __name__ == "__main__":
    synth(); lookahead()
    print(f"\nSONUÇ: {ok} geçti, {fails} başarısız"); sys.exit(1 if fails else 0)
