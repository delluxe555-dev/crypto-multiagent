# Canlı döngü (`live_loop/1.0`)

Saatlik döngü **yok**. `tools/scan.py` **5 dakikada bir** (istenirse 60 sn) ucuz tarama yapar;
tam komite yalnız tetik çıktığında çalışır. Karar TF'si **15m**, bağlam 1h/4h.

## Sembol kapsamı

**Öncelik yok.** Komite hangi sembol için girdi üretilirse onu değerlendirir; evreni
botun tarama listesi belirler. Bu dokümandaki BTC/ETH sayıları yalnızca ölçek
referansıdır, "önce BTC/ETH" gibi bir kural değildir.

## Kademe 0 — tarama (5 dakikada bir, AlertaChart'sız, ~1 sn)

```bash
python tools/scan.py --once                    # tek tur
python tools/scan.py --watch --interval 300 --auto   # 5 dk'da bir, tetikte kararı yaz
```

Evren: `config/universe.txt` (sıra/öncelik yok, satır neyse o taranır) veya `--symbols`.
Varsayılan liste likit kripto perp'ler: BTC, ETH, SOL, XRP, BNB, DOGE, ADA, SUI, HYPE, NEAR, UNI, ZEC.
(tokenize hisse/emtia perp'leri — SOXL, XAU, CL… — bilinçli olarak dışarıda.)

Yalnız Binance **perp** mumlarına bakar; ATR14, 20 mum kırılımı, hacim z-skoru, EMA8/21 kesişimi
ve mum menzilini ölçer (her zaman son **kapanan** mum). Tetik çıkarsa `runs/live/scan.jsonl`'a yazar;
`--auto` ile komiteyi çalıştırıp kararı yazar (overlay bayatsa karar "overlay: bayat/yok" işaretiyle
üretilir; o durumda orderflow/sentiment/onchain çekimser kalır, RR tabanı +0.15 yükselir).

Tam komite için AlertaChart katmanı iki seviyede tutulur:

- **Hafif katman (tüm evren):** `get_orderflow` + `get_chain_lab` → `cache/alertachart/_payload.json`
  → `python tools/apply_payload.py` her sembol için `overlay_<bar>.json` üretir; makro tek dosyada
  (`cache/alertachart/_macro.json`) paylaşılır, overlay'i olmayan sembollerde de makro oyu çalışır.
- **Ağır katman (tetik alan sembol):** defter, likidasyon haritası, ısı haritası, büyük işlemler.

| Çağrı | Ne okunur |
|-------|-----------|
| `get_orderflow(symbol, "15m", 8)` | son 8 mum: fiyat, CVD perp/spot, OI, net long/short, likidasyon |
| `get_order_book(symbol, market="perp")` | orta fiyat, ±%0.1 denge, en yakın iki duvar |
| `get_chain_lab(symbol, "15m")` | flow skoru, spot/perp liderliği, net pozisyon akışı, Coinbase primi, kaldıraç |
| `get_macro()` | faiz/eğri/kredi serilerinin günlük değişimi (makro oyu) |

**Tarayıcı tetikleri** (`scan.py`, biri yeterli):

1. mum değişimi ≥ 1 × ATR (tarama TF'sinde)
2. mum menzili ≥ 1.8 × ATR
3. 20 mumluk yüksek/düşük kırılımı
4. hacim z-skoru ≥ 2.5 **ve** değişim ≥ 0.5 ATR
5. EMA8/21 kesişimi **ve** değişim ≥ 0.5 ATR

**Overlay tetikleri** (tam komite turunda, biri yeterli; eşikler sembolün kendi ölçeğinden):

1. 4 mumluk CVD perp işareti döndü **ve** |CVD| sembol ölçeğinde büyük (BTC ≈ 50M$, ETH ≈ 15M$)
2. likidasyon: son 4 mumda long veya short tarafı sembol ölçeğinde büyük (BTC ≈ 1M$, ETH ≈ 0.5M$)
3. fiyat, likidasyon haritasındaki en büyük kümeye %0.3'ten yakın
4. defter denge |%| ≥ 10 **ve** o taraftaki duvar çekildi/doldu
5. funding işareti döndü (8 saatlik ortalama)

Tetik yoksa: yaz, çık. Karar üretilmez, token harcanmaz.

## Kademe 1 — tam komite (tetikte, 10 çağrı + tarama)

`get_chain_lab(coin, "15m")`, `get_liquidation_map`, `get_liquidity_heatmap(hours=1)`,
`get_large_trades(min_usd=500k)`, `get_order_book_events(hours=1)` tazelenir;
yavaş bağlam (`get_options_volatility`, `get_news`, `get_macro`) **4 saatten eski değilse
yeniden çekilmez** — overlay dosyasında taşınır.

Üretim:

```
python tools/run_all.py                     # evrenin tamamı: karar + Telegram
python tools/run_all.py --no-telegram       # sadece kararlar
python tools/live_cycle.py BTCUSDT.P --tf 15m      # girdi metni (insan/ajan okuması)
python tools/engine.py   BTCUSDT.P --tf 15m        # tek sembol kararı
```

→ `runs/live/<zaman>/<SEMBOL>_input.md` (teknik + trend + 15m katman + yavaş bağlam)
→ `runs/live/<zaman>/decision_<SEMBOL>.json` + `runs/live/journal.jsonl`
→ Telegram sinyali (uygulanabilir kararlar; HOLD varsayılan olarak susar)

## Telegram sinyalleri (`dataflows/telegram_notify.py`)

Her yazılan karar otomatik gönderilir (`engine.write_decision` → `send_signal`). Bot
**@KxlAiBot**, hedef sohbet `config/telegram.json` içinde (`chat_id`, `hashtag: "#oc"`).
Mesajın son satırı **#oc**.

```bash
python dataflows/telegram_notify.py --whoami          # bot + sohbet
python dataflows/telegram_notify.py --test            # örnek sinyal
python dataflows/telegram_notify.py --decide ETHUSDT.P --tf 15m   # karar + gönderim
python tools/engine.py BTCUSDT.P --tf 15m --no-telegram           # sadece yaz, gönderme
```

- Gönderim kuralı: `action` BUY/SELL/SHORT/LONG **ve** `uzlaşma ≥ %65` ise gider
  (`min_share`); HOLD yalnız `send_hold: true` ise. %65 altı adaylar yazılır ama Telegram'a gitmez.
- **Tekrar koruması**: aynı `sembol + bar + yön + mod + giriş/TP1` anahtarı bir kez gider
  (`runs/live/telegram_state.json`).
- Gönderim hatası kararı bloklamaz; sonuç karar JSON'una `telegram` alanı olarak yazılır.
- Token gizli: `config/telegram.json`'u paylaşma; alternatif `TG_TOKEN` / `TG_CHAT` ortam değişkenleri.

## Tetik izleme (`tools/trigger_watch.py`)

Koşullu sinyal "bekliyor" diye kalmaz: ayrı bir döngü her 60 saniyede **son kapanmış** 15m
mumunu okur ve Telegram'a haber verir.

- **tetik** → `✅ TETİK` mesajı: kapanış eşiğin ötesinde, giriş artık geçerli (SL/TP1/TP2 aynen).
- **iptal** → `⚠️ İPTAL` mesajı: kapanış geçersizlik seviyesinin ötesinde, tetik hiç çalışmadı.
- **süre doldu** → sessizce `expired` işaretlenir, mesaj atılmaz.

Yalnız Telegram'a **gitmiş** koşullu kararlar izlenir; aynı sinyal için tek bildirim
(`runs/live/triggers.json`). Silinen mesajların sinyalleri izlenmez
(`telegram_state.json → deleted`).

```bash
python tools/trigger_watch.py --list            # ne izleniyor, tetik/iptal seviyesi
python tools/trigger_watch.py --once            # tek kontrol
python tools/trigger_watch.py --watch --interval 60
```

## Karar motoru (`tools/engine.py`, `committee-engine/1.0`)

Kararı **benim** mantığım verir; Grok'un bot karar katmanı (`trader.py`, `risk_rules.py`,
hakem, `agents.py`) **kullanılmaz**. Motor kendi göstergelerini Binance **perp**
mumlarından hesaplar (EMA 8/13/21, SMA 50/200, ATR14, RSI14, MACD hist, fractal swing).

- 8 ajan: teknik · on-chain · sentiment · orderflow · makro · boğa · ayı · trader (danışman).
- Eşik: ≥4 geçerli oy, ≥3 yön oyu, `max(BUY,SELL)/(BUY+SELL) ≥ %55`.
- Risk katmanı: 2×ATR stop (yakın swing varsa 0.25 ATR ötesi, tavan 3 ATR); RR tabanı sabit değil
  (`1.35` başlar; pay < %70 / bayat overlay / maliyet-ATR > 0.35 → +0.15/+0.15/+0.10, tavan 1.90;
  piyasa emri tabanı `max(1.75, taban+0.25)`, tavan 2.20), maliyet kapısı (piyasa emri ≤ 0.25,
  üstü veto 0.50), `risk_R` 1.0 / 0.5.
- Overlay bayat/yoksa orderflow + sentiment **çekimser** kalır; oy 4'ün altına düşerse HOLD.
- Bayat overlay ile karar üretilmez; motor `overlay.used=false` yazar.

```bash
python tools/engine.py BTCUSDT.P --tf 15m --no-write   # sadece göster
python tools/engine.py BTCUSDT.P --tf 15m              # karar + journal
```

```text
ortam: CA_NO_KEYLEVELS=1 (kişisel kritik seviyeler komite kanıtı değil)
```

## Maliyet kapısı (neden 15m'de çoğu zaman HOLD)

Perp tur maliyeti ≈ **%0.10**. Ölçüt: `maliyet / 1×ATR`.

| Sembol | 15m ATR | maliyet/ATR | Sonuç |
|--------|---------|-------------|-------|
| BTC | %0.21 | 0.48 | piyasa emri yasak (0.25 üstü), tetikli giriş uygun |
| ETH | %0.32 | 0.31 | piyasa emri yasak (0.25 üstü), tetikli giriş uygun |

Yani 15m'de BTC için piyasa emri, hareketin üçte ikisini komisyona vermek demek.
Bu yüzden komite ya HOLD der ya da **tetikli** giriş ister.

## Tazelik

- Overlay `bar + tf + 2 dk` sonrası **bayat** (`overlay_text` → `stale: true`, blok başına UYARI).
- `live_cycle.py` çıktısının sonunda `overlay yaşı` satırı vardır; 15m'de >17 dk ise karar üretilmez.
- 1h/4h trend her zaman taze Binance klines'tan hesaplanır (ucuz, ağ hatası olursa satır "hesaplanamadı" der).

## Bilinen sınırlar

- Zincir üstü veri `get_chain_lab`'dan gelir (flow skoru, spot/perp liderliği, net pozisyon akışı,
  Coinbase primi, kaldıraç doygunluğu) → Temel/On-chain ajanı **oy verir**; modül yoksa çekimser.
  Makro ajanı `get_macro` değişimleriyle oy verir (seviye değil, günlük değişim).
- Likidasyon haritası **tahmini**, ısı haritası **kayıtlı defter** (anlık değil). `% mevcut` düşükse seviye güvenilmez.
- `engine.py` mumları ve karar fiyatını **perp**'ten alır (spot/perp baz farkı yok) ve **kapanmamış mumu atar**.
  `live_cycle.py` hâlâ botun spot `data.klines`'ını kullanır (Grok tarafına dokunulmadı) — baz farkı yalnızca o metinde geçer.
- Tarama `tools/scan.py` ile 5 dakikada bir otomatik döner (`--watch --interval 300 --auto`);
  AlertaChart katmanını (overlay) yalnızca ben tazeleyebilirim, Python tarafı oraya gidemez.
  Overlay bayatsa tarayıcı karar yazmaz, "tazele" der.

> Araştırma/kağıt işlem; yatırım tavsiyesi değildir.
