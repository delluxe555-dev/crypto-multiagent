"""Kritik seviye testleri (LLM yok, Telegram yok: send sahte, durum dosyası geçici). Çalıştır: .venv/bin/python -W ignore tests/test_keylevels.py"""
import os, sys, tempfile, json, time
os.environ["CA_NO_TG"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE); os.chdir(HERE)
import keylevels as K, data, requests
_LF, _CA = K.levels_for, K._cfg_all
OK = [0]; BAD = []
def chk(name, cond, info=""):
    OK[0] += bool(cond)
    if not cond: BAD.append(name); print("FAIL", name, info)
H = K.H4; T0 = 1_700_000_000_000 // H * H
def C(i, o, h, l, c): return (T0 + i * H, o, h, l, c)

# --- config
chk("cfg boş (kişisel seviyeler kaldırıldı)", K.levels_for("BTCUSDT") == [] and K.levels_for("ETHUSDT") == [] and K.levels_for("SOLUSDT") == [])

# --- sınıflandırma + durum makinesi
L = 100.0
chk("alt", K.classify(C(0, 101, 102, 98, 99), L) == "alt")
chk("tepki", K.classify(C(0, 101, 102, 98, 100.5), L) == "tepki")
chk("üst", K.classify(C(0, 101, 103, 100.2, 102), L) == "üst")
chk("tam eşit kapanış üst sayılır (tepki)", K.classify(C(0, 101, 103, 99, 100), L) == "tepki")
st = {}
seq = [C(0, 101, 103, 100.5, 102), C(1, 102, 102, 98, 99), C(2, 99, 100, 97, 98), C(3, 98, 99, 96, 97), C(4, 97, 102, 96, 101), C(5, 101, 103, 99, 102), C(6, 102, 104, 101, 103)]
kinds = []
for c in seq:
    k, st = K.evaluate_candle(c, L, st, 2); kinds.append(k)
chk("durum makinesi", kinds == [None, "alt", "alt_devam", None, "geri", "tepki", None], kinds)

# --- izleyici: sahte mumlar, dedupe, ilk kurulum, yeniden deneme yok
K.levels_for = lambda s: [L] if s == "TESTUSDT" else []
K._cfg_all = lambda: {"key_levels": {"TESTUSDT": L}, "key_level_watch": {}}
msgs = []; send = lambda t: (msgs.append(t) or True)
candles = [C(0, 101, 103, 100.5, 102)]
d = tempfile.mkdtemp(); sp = os.path.join(d, "kl.json"); price = [110.0]
fetch = lambda s, n: candles[-n:]; gp = lambda s: price[0]; tm = [T0 + 10 * H]
def run(): return K.watch(send, sp, fetch, gp, now_ms=lambda: tm[0], log=lambda *a: None)
chk("ilk kurulum sessiz", run() == 0 and not msgs)
candles.append(C(1, 102, 102, 98, 99)); n = run()
chk("4s kapanış altı -> 1 uyarı", n == 1 and "🚨 4s KAPANIŞ seviyenin ALTINDA" in msgs[-1], msgs[-1:])
chk("dedupe (aynı mum tekrar yok)", run() == 0 and len(msgs) == 1)
m = msgs[0]; chk("içerik", "Kritik seviye: 100,00 $" in m and "4s kapanış: 99,00 $" in m and "−1,00%" in m and "<b>Yorum</b>" in m, m)
candles.append(C(2, 99, 100.6, 99.5, 100.4)); price[0] = 110; run()   # kapanış geri üstte
chk("kırılım sonrası kapanış üstte -> bilgi", "✅ Kapanış seviyenin üstüne döndü" in msgs[-1], msgs[-1][:80])
candles.append(C(3, 100.4, 103, 99.2, 101.5)); price[0] = 110; run()   # fitil altı, kapanış üstü
chk("tepki mesajı", "↩️ Seviyeden tepki (fitil alındı, kapanış üzerinde)" in msgs[-1] and "Mum dibi (fitil): 99,20 $" in msgs[-1], msgs[-1][:90])
nm = len(msgs); candles.append(C(4, 101.5, 104, 101, 103)); price[0] = 110; run()
chk("temiz üst mum uyarı yok", len(msgs) == nm)
# yaklaşma: ±%0,5 ilk kez, tekrar yok, histerezis + bekleme
price[0] = 100.4; run(); chk("yaklaşma uyarısı", "🎯 Fiyat kritik seviyeye yaklaştı" in msgs[-1], msgs[-1][:60]); nm = len(msgs)
price[0] = 100.3; run(); run(); chk("yaklaşma tekrar yok", len(msgs) == nm)
price[0] = 103; run(); price[0] = 100.2; run(); chk("bekleme süresi içinde tekrar yok", len(msgs) == nm)
tm[0] += 5 * 3600 * 1000; price[0] = 103; run(); price[0] = 100.2; run(); chk("bekleme sonrası tekrar", len(msgs) == nm + 1)
# aynı turda çok mum kaçırıldıysa sırayla işlenir
msgs.clear(); d2 = tempfile.mkdtemp(); sp2 = os.path.join(d2, "k.json"); cs = [C(0, 101, 103, 100.5, 102)]
gp = lambda s: 110.0; fetch = lambda s, n: cs[-n:]; K.watch(send, sp2, fetch, gp, lambda: 0, log=lambda *a: None)
cs += [C(1, 102, 102, 98, 99), C(2, 99, 99, 97, 98), C(3, 98, 99, 96, 97)]
K.watch(send, sp2, fetch, gp, now_ms=lambda: tm[0], log=lambda *a: None)
chk("kaçırılan mumlar: kırılım + teyit, 3. sessiz", len(msgs) == 2 and "hâlâ" in msgs[1], [x[:40] for x in msgs])
# ilk kurulumda en son kapanmış mum kırılımsa uyarı verir, eski mumlar için vermez
msgs.clear(); d3 = tempfile.mkdtemp(); cs3 = [C(0, 101, 103, 100.5, 102), C(1, 102, 102, 98, 99), C(2, 99, 99, 97, 98)]
K.watch(send, os.path.join(d3, "k.json"), lambda s, n: cs3[-n:], gp, lambda: 0, log=lambda *a: None)
chk("ilk kurulum: son mum altıysa tek uyarı", len(msgs) == 1 and "ALTINDA" in msgs[0] and "hâlâ" in msgs[0], [x[:50] for x in msgs])
# state dosyası json
chk("state dosyası", "TESTUSDT|100" in json.load(open(sp)))

# --- GERÇEK geçmiş mumlarla yeniden oynatma (son ~30 gün 4s, sentetik seviye), Telegram yok
K.levels_for, K._cfg_all = _LF, _CA
rep = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    lv = 90000.0
    r = requests.get(f"{K.SPOT}/klines", params={"symbol": sym, "interval": "4h", "limit": 180}, timeout=15).json()
    cs = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in r if int(x[6]) < time.time() * 1000]
    st = {}; ev = []
    for c in cs:
        k, st = K.evaluate_candle(c, lv, st, 2)
        if k: ev.append((time.strftime("%m-%d %H:%M", time.gmtime(c[0] / 1000)), k, round(c[4], 2), round(100 * (c[4] / lv - 1), 2)))
    rep[sym] = (lv, len(cs), ev)
    chk(f"{sym} gerçek mum yeniden oynatma çalıştı", len(cs) > 100)
    if ev: print(sym, "seviye", lv, "mum", len(cs), "uyarı sayısı", len(ev), "ilk3", ev[:3], "son3", ev[-3:])
    else: print(sym, "seviye", lv, "mum", len(cs), "uyarı yok (seviye hiç kapanışla kırılmadı)")
    if ev:   # mesaj biçimi gerçek mumla
        c = [x for x in cs if time.strftime("%m-%d %H:%M", time.gmtime(x[0] / 1000)) == ev[0][0]][0]
        print("--- örnek mesaj ---"); print(K.candle_msg(sym, lv, c, ev[0][1])); print("---")

# --- istem bloğu (gerçek canlı veri) + backtest'te kapalı
df = data.add_indicators(data.klines("BTCUSDT", interval="1h", limit=300)); df4 = data.add_indicators(data.klines("BTCUSDT", interval="4h", limit=300))
t1, _ = data.snapshot("BTCUSDT", df, interval="1h"); t4, _ = data.snapshot("BTCUSDT", df4, interval="4h")
chk("1h bloğunda kritik seviye satırı yok (config key_levels boş)", "kritik seviye" not in t1.lower())
chk("4h bloğunda kritik seviye satırı yok (config key_levels boş)", "kritik seviye" not in t4.lower())
chk("seviyesiz coin: satır yok", "kritik seviye" not in data.snapshot("SOLUSDT", data.add_indicators(data.klines("SOLUSDT", "1h", 300)), interval="1h")[0])
chk("i verilirse (backtest) satır yok", "kritik seviye" not in data.snapshot("BTCUSDT", df, i=len(df) - 5, interval="1h")[0])
os.environ["CA_NO_KEYLEVELS"] = "1"; chk("CA_NO_KEYLEVELS=1 kapalı", "kritik seviye" not in data.snapshot("BTCUSDT", df, interval="1h")[0]); del os.environ["CA_NO_KEYLEVELS"]
print("--- 4h blok satırları ---"); print("\n".join(l for l in t4.split("\n") if "kritik seviye" in l.lower() or l.startswith("Kural: 4s")))
import agents, inspect
for f in (agents.technical, agents.trend_4h, agents.entry_ltf, agents.judge): chk(f"istem KL: {f.__name__}", "{KL}" in inspect.getsource(f) or "+ KL +" in inspect.getsource(f))
print(f"{OK[0]} kontrol geçti, {len(BAD)} başarısız", BAD); sys.exit(1 if BAD else 0)
