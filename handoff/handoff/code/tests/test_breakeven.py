"""Başabaş stop testi: canlı defterin KOPYASI üzerinde, sahte fiyat/mum akışıyla zorlanmış senaryolar. Canlı defter/log/lessons/önbelleğe dokunmaz.
Çalıştır: .venv/bin/python -W ignore tests/test_breakeven.py"""
import os, sys, json, shutil, tempfile, copy
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="be_test_")
os.environ.update(CA_NO_TG="1", CA_TRADER_DIR=tmp, CA_LESSONS=os.path.join(tmp, "lessons.json"), CA_DRY_RUN="1")
os.makedirs(tmp, exist_ok=True); shutil.copy(os.path.join(HERE, "outputs/trader/ledger.json"), os.path.join(tmp, "ledger.json"))
sys.path.insert(0, HERE); os.chdir(HERE)
import trader, tgfmt, lessons
assert trader.TD == tmp and trader.LEDGER.startswith(tmp), "test dizini kullanılmıyor!"
ok = fails = 0
def check(name, cond, info=""):
    global ok, fails
    if cond: ok += 1; print("  ok  ", name)
    else: fails += 1; print("  FAIL", name, info)

trader.be_cfg = lambda: (True, 0.67, 0.3)
PX = {}; CANDLES = {}
trader.prices = lambda syms: {s: PX[s] for s in syms if s in PX}
trader.minute_candles = lambda s, since: [c for c in CANDLES.get(s, []) if c[0] + 60000 > since]
sent = []; trader.tg = lambda text, html=True: sent.append(text) or True
def led(): return trader.load_ledger()
def pos(sym): return next(p for p in led()["positions"] if p["symbol"] == sym and p["status"] != "x")
def now_ms(): return int(__import__("time").time() * 1000)

L0 = led(); opened = {p["symbol"]: p for p in L0["positions"] if p["status"] == "open"}
print("açık:", list(opened))
# --- 1) TIA short: lo_seen zaten tetiği (≥%67) geçmiş -> ilk kontrolde çekilmeli, bir kez bildirilmeli
tia = opened["TIAUSDT"]; e, tg_ = tia["entry"], tia["target"]
PX.update({s: p.get("last_price") or p["entry"] for s, p in opened.items()})
print("1) TIA: zaten tetiği geçmiş açık pozisyon")
trader.monitor()
p = pos("TIAUSDT")
exp = tia["entry"] * (1 - 0.003)
check("stop başabaşa çekildi (giriş −%0,3)", abs(p["stop"] - exp) < 1e-9, (p["stop"], exp))
check("stop_orig korundu", abs(p["stop_orig"] - tia["stop"]) < 1e-12)
check("be_moved_at dolu", bool(p.get("be_moved_at")))
n_be = sum("Stop girişe çekildi" in m for m in sent); check("tam 1 bildirim", n_be >= 1 and sum("TIA/USDT" in m and "çekildi" in m for m in sent) == 1, sent[:1])
trader.monitor(); check("ikinci kontrolde tekrar bildirim yok", sum("TIA/USDT" in m and "çekildi" in m for m in sent) == 1)
check("açık pozisyon alanları korunuyor", all(k in p for k in ("entry", "qty", "notional", "fee_open", "margin", "leverage", "target", "opened_at")))
print(next(m for m in sent if "TIA/USDT" in m and "çekildi" in m))
# --- 2) TIA: fiyat BE stopunun üstüne çıkar -> 'başabaş' kapanış, K/Z ≈ +%0,05 (ücret+kayma sonrası)
print("2) TIA: başabaş çıkışı + PnL")
sent.clear(); be_stop = p["stop"]; ot = (now_ms() // 60000 + 3) * 60000
PX["TIAUSDT"] = be_stop; CANDLES["TIAUSDT"] = [(ot, be_stop * 1.002, be_stop * 0.99)]   # fiyat tam stop seviyesinde (boşluk yok)
eq0 = trader.equity(led()); trader.monitor(); q = [x for x in led()["positions"] if x["symbol"] == "TIAUSDT"][0]
check("durum closed, neden 'başabaş'", q["status"] == "closed" and q["exit_reason"] == "başabaş", (q["status"], q.get("exit_reason")))
want = q["qty"] * (q["entry"] - q["exit"]) - q["fee_open"] - q["fee_close"]
check("PnL muhasebesi tutarlı", abs(q["pnl_usd"] - want) < 1e-9)
pct = 100 * q["pnl_usd"] / q["notional"]; check("net ≈ +%0,05 notional (−%0,3 başabaş +%0,3 tampon −ücret/kayma)", 0.0 < pct < 0.15, pct)
check("özsermaye pnl kadar değişti", abs(trader.equity(led()) - eq0 - q["pnl_usd"]) < 1e-9)
check("kapanış mesajı gönderildi (⚪ BAŞABAŞ)", any("⚪ BAŞABAŞ" in m and "TIA/USDT" in m for m in sent))
check("lessons: çıkış nedeni başabaş + win=False", (lambda S: next(r for r in S["trades"] if r["id"] == q["id"]))(lessons.load())["exit_reason"] == "başabaş" and not next(r for r in lessons.load()["trades"] if r["id"] == q["id"])["win"])
print(next(m for m in sent if "⚪ BAŞABAŞ" in m)); print("  ders:", q.get("lesson"))
# --- 3) ONDO short (tetik altı) -> ilerlemeyle tetikle; tetik mumunda stop yeni seviyeden değerlendirilmez
print("3) ONDO: tetik altı -> tetik -> aynı mumda fitil geri dönüşü")
o = pos("ONDOUSDT"); check("ONDO başlangıçta çekilmemiş", not o.get("be_moved_at"), o.get("be_progress"))
D = o["entry"] - o["target"]; trig_px = o["entry"] - 0.70 * D
PX["ONDOUSDT"] = trig_px * 1.0005; now_m = now_ms() // 60000 * 60000
CANDLES["ONDOUSDT"] = [(now_m, trig_px * 1.002, trig_px * 0.999)]; o["lo_seen"] = min(o["lo_seen"], trig_px); 
L = led(); [x for x in L["positions"] if x["symbol"] == "ONDOUSDT"][0]["lo_seen"] = o["lo_seen"]; trader.jsave(trader.LEDGER, L)
trader.monitor(); o = pos("ONDOUSDT"); check("ONDO stop çekildi", bool(o.get("be_moved_at")) and abs(o["stop"] - o["entry"] * 0.997) < 1e-9)
# sonraki kontrol: çekme anından ÖNCEKİ mum (ot < be_from_ms) BE stopunu aşan fitil içerir -> kapanmamalı
PX["ONDOUSDT"] = trig_px; CANDLES["ONDOUSDT"] = [(o["be_from_ms"] - 60000, o["stop"] * 1.01, trig_px * 0.998)]
trader.monitor(); o = pos("ONDOUSDT"); check("tetik mumunun fitili stopu tetiklemedi", o["status"] == "open")
CANDLES["ONDOUSDT"] = [(o["be_from_ms"] + 60000, o["stop"] * 1.003, trig_px * 0.998)]; PX["ONDOUSDT"] = o["stop"] * 1.002
trader.monitor(); q = [x for x in led()["positions"] if x["symbol"] == "ONDOUSDT"][0]
check("sonraki mumdaki fitil → 'başabaş' kapanış", q["status"] == "closed" and q["exit_reason"] == "başabaş", q.get("exit_reason"))
# --- 4) TRUMP: hedef çekmeden sonra gelirse 'hedef'; stop tetikten önce gelirse 'stop'
print("4) TRUMP: tetik -> hedef;  WLD: devre dışı + stop")
tr = pos("TRUMPUSDT"); PX["TRUMPUSDT"] = tr["target"] * 0.999; now_m = now_ms() // 60000 * 60000
CANDLES["TRUMPUSDT"] = [(now_m, tr["entry"] * 0.999, tr["target"] * 0.9995)]; sent.clear()
trader.monitor(); q = [x for x in led()["positions"] if x["symbol"] == "TRUMPUSDT"][0]
check("hedef etiketi korundu (tetik+hedef aynı turda)", q["exit_reason"] == "hedef", q.get("exit_reason"))
trader.be_cfg = lambda: (False, 0.67, 0.3)
w = pos("WLDUSDT"); check("WLD (ilk turda çekilmiş) → bayrak kapalıyken yeni çekme olmaz, mevcut stop geçerli", bool(w.get("be_moved_at")))
trader.be_cfg = lambda: (True, 0.67, 0.3)
# yeni sahte pozisyon: tetik görülmeden stop -> 'stop'
L = led(); fake = copy.deepcopy([x for x in L["positions"] if x["symbol"] == "BTCUSDT" and x["status"] == "closed"][0])
fake.update(id="FAKE-1", symbol="XRPUSDT", status="open", side="LONG", entry=100.0, stop=98.0, target=103.0, ref_price=100.0, qty=5.0, notional=500.0, fee_open=0.5, margin=100.0, hi_seen=100.0, lo_seen=100.0,
            last_check_ms=now_ms() - 120000, opened_at=trader.iso(), stances={}, move=None); [fake.pop(k, None) for k in ("closed_at", "exit", "exit_reason", "pnl_usd", "pnl_pct", "roe_pct", "fee_close", "exit_raw", "lesson", "be_moved_at", "stop_orig", "be_from_ms")]
L["positions"].append(fake); trader.jsave(trader.LEDGER, L)
PX["XRPUSDT"] = 98.5; CANDLES["XRPUSDT"] = [(now_ms() // 60000 * 60000, 101.0, 97.9)]   # önce tetik (102 ≥ +2? yok): 101<102.0; stop 97.9<98 -> stop
trader.monitor(); q = [x for x in led()["positions"] if x["id"] == "FAKE-1"][0]
check("tetik görülmeden stop → 'stop' (başabaş değil)", q["exit_reason"] == "stop" and q["pnl_usd"] < 0, (q.get("exit_reason"), q.get("pnl_usd")))
# --- 5) LONG simetri
fake2 = copy.deepcopy(fake); fake2.update(id="FAKE-2", status="open", hi_seen=100.0, lo_seen=100.0, last_check_ms=now_ms() - 120000); [fake2.pop(k, None) for k in ("closed_at", "exit", "exit_reason", "pnl_usd", "pnl_pct", "roe_pct", "fee_close", "exit_raw", "lesson")]
L = led(); L["positions"].append(fake2); trader.jsave(trader.LEDGER, L)
PX["XRPUSDT"] = 102.2; CANDLES["XRPUSDT"] = [(now_ms() // 60000 * 60000, 102.3, 101.5)]
trader.monitor(); f2 = [x for x in led()["positions"] if x["id"] == "FAKE-2"][0]
check("LONG: stop giriş +%0,3'e çekildi", f2["status"] == "open" and abs(f2["stop"] - 100.3) < 1e-9, (f2["status"], f2["stop"]))
PX["XRPUSDT"] = 100.3; CANDLES["XRPUSDT"] = [(f2["be_from_ms"] + 60000, 101.0, 100.2)]
trader.monitor(); f2 = [x for x in led()["positions"] if x["id"] == "FAKE-2"][0]
check("LONG: başabaş çıkışı, K/Z küçük pozitif", f2["exit_reason"] == "başabaş" and 0 < f2["pnl_usd"] < 1.0, (f2.get("exit_reason"), f2.get("pnl_usd")))
# --- 5b) boşluk: fiyat BE stopunun ötesine geçmişse ihtiyatlı (daha kötü) dolum, hâlâ 'başabaş' etiketi
fake3 = copy.deepcopy(fake2); fake3.update(id="FAKE-3", status="open", symbol="DOGEUSDT", hi_seen=100.0, lo_seen=100.0, last_check_ms=now_ms() - 120000, stop=98.0); [fake3.pop(k, None) for k in ("closed_at", "exit", "exit_reason", "pnl_usd", "pnl_pct", "roe_pct", "fee_close", "exit_raw", "lesson", "be_moved_at", "stop_orig", "be_from_ms")]
L = led(); L["positions"].append(fake3); trader.jsave(trader.LEDGER, L)
PX["DOGEUSDT"] = 102.2; CANDLES["DOGEUSDT"] = [(now_ms() // 60000 * 60000, 102.3, 101.5)]; trader.monitor()
f3 = [x for x in led()["positions"] if x["id"] == "FAKE-3"][0]; PX["DOGEUSDT"] = 99.9; CANDLES["DOGEUSDT"] = [(f3["be_from_ms"] + 60000, 100.5, 99.8)]; trader.monitor()
f3 = [x for x in led()["positions"] if x["id"] == "FAKE-3"][0]; check("boşlukta ihtiyatlı dolum (son fiyattan), etiket 'başabaş', küçük zarar", f3["exit_reason"] == "başabaş" and abs(f3["exit_raw"] - 99.9) < 1e-9 and -3 < f3["pnl_usd"] < 0, (f3.get("exit_raw"), f3.get("pnl_usd")))
# --- 6) özet / sabah mesajı / motor
s = trader.write_summary(led()); check("summary: breakeven_n ve wins ayrı", s["breakeven_n"] >= 2 and s["wins"] >= 1, (s["breakeven_n"], s["wins"]))
st = lessons.stats(lessons.load()); check("lessons.stats 'çıkış' içinde başabaş", "başabaş" in st["çıkış"], st["çıkış"])
d = dict(date="x", n_open=0, n_closed=1, pnl24=0.1, closed=[dict(symbol="TIAUSDT", side="SHORT", exit_reason="başabaş", pnl_pct=0.05, pnl_usd=0.11)], open=[dict(w, now=w["entry"], unr=0)], equity=1000, ret=0, unr=0, bh=None, hits={}, risks=[], lessons=[])
m = tgfmt.morning_msg(d); check("sabah özeti: ⚪ + 🛡 işareti", "⚪" in m and "🛡 (başabaş)" in m)
print(f"\nSONUÇ: {ok} geçti, {fails} başarısız"); shutil.rmtree(tmp, ignore_errors=True); sys.exit(1 if fails else 0)
