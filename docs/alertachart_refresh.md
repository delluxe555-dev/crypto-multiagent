# Duygu & Türev Bloğu — AlertaChart Veri Kaynağı

Bölüm 2'nin (ajanlar) duygu/türev analisti artık verisini **AlertaChart'tan** alıyor.
AlertaChart'ta karşılığı olmayan iki alan (zincir üstü, Korku&Açgözlülük) eski
kaynaktan aynen geliyor.

Kod: `dataflows/alertachart_bridge.py` · Veri: `cache/alertachart/<SEMBOL>/<tf>/<BAR>.json`

---

## 1. Ne değişti

| Alan | Eski kaynak | Sorun | Yeni kaynak (AlertaChart) |
|---|---|---|---|
| Funding | OKX, 9 periyot | tek borsa | 5 borsa son settle + 7g ort. + sıradaki tahmin (`get_derivatives_history`) |
| Açık pozisyon | OKX rubik | tek borsa | 4 borsa USD + % değişim, toplam/anlık (`get_derivatives_history`) |
| Long/short | OKX **hesap** oranı 2.15 | hesapla pozisyon karışıyor | net pozisyon akışı: NL/NS adet + 4/12/24 mum (`get_orderflow`) |
| Taker | OKX, tek oran 0.86 | borsa ayrımı yok | borsa bazında taker alış/satış (`get_orderflow.cvd_by_venue`) |
| Likidasyon (gerçekleşen) | **yalnız OKX**, n≈620 | örneklem bozuk: long 7.5M$ / short 18K$ (oran 414) | 5 borsa, long/short adet+USD, en büyük 3 işlem |
| Likidasyon kümeleri | OKX OI modeli | tek borsa | tahmini harita, ±1/2/5% + fiyat bantları (`get_liquidation_map`) |
| Emir defteri | Binance **spot** | yanlış evren; ±1% değeri ±0.5 ile aynı (bozuk) | perp, ±0.1/0.25%, duvarlar, `spread_bps` (`get_order_book`) |
| CVD | yok | — | 4/12/24 mum, perp+spot, borsa bazında |
| Balina akışı | yok | — | 4 saat, ≥500K$, alım/satım/net (`get_large_trades`) |
| Likidite ısı haritası | yok | — | 2 saat, seviye + % mevcudiyet (`get_liquidity_heatmap`) |
| Duvar davranışı | yok | — | 40 duvar: çekildi / duruyor / doldu (`get_order_book_events`) |
| Chain Lab | yok | — | 23 modül, Türkçe okuma (`get_chain_lab`) |
| Opsiyon | yok | — | DVOL, IV rank, VRP, gamma flip, max pain, call/put duvarı, beklenen hareket |
| Piyasa profili | bot kendi hesaplıyordu | spot mumdan | perp POC/VAH/VAL + VWAP + delta (`get_market_profile`) |
| Genişlik | yok | — | 99 coin net alıcı % (`scan_flow`) |
| Majors funding | yok | — | BTC/ETH/SOL/XRP/BNB/DOGE (`scan_market`) |
| Haber | yok | — | 5 başlık (`get_news`) |
| Makro | yok | — | FOMC, US02Y, US10Y, 2s10s, CPI, işsizlik, ICSA (`get_macro`) |
| **Zincir üstü** | DefiLlama / mempool / blockchain.info | — | **AlertaChart'ta yok → aynı kaldı** |
| **Korku&Açgözlülük** | alternative.me | — | **AlertaChart'ta yok → aynı kaldı** |
| **Hacim sıçraması** | mum verisinden | — | **AlertaChart'ta yok → aynı kaldı** |

Ölçü: BTC bloğu **47 satır / ~5.0K karakter** (eski: 18 satır / 2.1K).
Satırların hepsi sayı taşıyor; şişkinlik yok.

---

## 2. Snapshot sözleşmesi

```json
{
  "schema": "alertachart-sentiment/1.0",
  "symbol": "BTCUSDT.P", "coin": "BTC", "venue": "Binance USDT perpetual",
  "tf": "1h", "bar": "2026-10-25T16:00:00.000Z", "fetched_at": "...", "price": 80762.85,
  "flow":   { "w": [4/12/24 mum], "oi_usd": ..., "venues": [...], "fund": [...], "liq": {...} },
  "oi":     { "unit": "USD mn", "venues": [...], "total": ... },
  "fund":   { "unit": "%/8h", "venues": [{ "last", "next", "m7", "hi", "lo" }] },
  "book":   { "mid", "spread_bps", "depth", "bw", "aw" },
  "liqmap": { "px", "within", "below", "above" },
  "heat":   { "px", "bid", "ask" },
  "whales": { "buy", "sell", "net", "top" },
  "obe":    { "n", "out", "top" },
  "lab":    [ { "m", "r", "v", "ok" } ],
  "opt":    { "dvol", "ivr", "vrp", "gamma", "pain", "call", "put", "pcr", "em" },
  "profile":{ "poc", "vah", "val", "vwap", "delta", "buyers" },
  "breadth":{ "pct", "coins", "avg24" },
  "majors": [...], "news": [...], "macro": {...},
  "errors": []
}
```

`label` yerine kısa anahtar kullanılıyor; insan okunur metni `render()` üretiyor.
`bar` = **kapanan** mumun açılışı. `tf` ile birlikte tazelik hesabı yapılır.

---

## 3. Yenileme (yeni mum kapandığında)

Sembol başına 16 MCP çağrısı, hepsi `1h` için:

| # | Araç | Parametre | Yazdığı anahtar |
|---|---|---|---|
| 1 | `get_orderflow` | `symbol, timeframe, bars=24` | `flow` |
| 2 | `get_derivatives_history` | `kind="open_interest", interval, bars=24` | `oi` |
| 3 | `get_derivatives_history` | `kind="funding", days=7` | `fund` |
| 4 | `get_order_book` | `market="perp"` | `book` |
| 5 | `get_liquidation_map` | `symbol` | `liqmap` |
| 6 | `get_liquidity_heatmap` | `market="perp", hours=2` | `heat` |
| 7 | `get_large_trades` | `market="perp", hours=4, min_usd=500000` | `whales` |
| 8 | `get_order_book_events` | `market="perp", hours=2` | `obe` |
| 9 | `get_chain_lab` | `symbol=<coin>, timeframe, language="tr"` | `lab` |
| 10 | `get_options_volatility` | `coin` | `opt` |
| 11 | `get_options` | `coin, scope="30d"` | `opt` |
| 12 | `get_market_profile` | `market="perp", session="day", sessions=1` | `profile` |
| 13 | `scan_flow` | `scan="flow_breadth", interval, bars=24` | `breadth` |
| 14 | `scan_market` | `scan="funding_high"` | `majors` |
| 15 | `get_news` | `query=<coin>, limit=5` | `news` |
| 16 | `get_macro` | — | `macro` |

Yazım: `cache/alertachart/<SEMBOL>/<tf>/<YYYY-MM-DDTHHMMZ>.json`.
`get_chain_lab.last_closed_bar` → `bar` alanı.

**Tazelik kuralı:** `bar + tf` üzerinden `1.5 × tf` dakika geçtiyse blok `BAYAT`
işaretlenir ve metnin başına uyarı eklenir (`is_fresh()`).
Yani 1h'de 90 dakika. Bot bayat snapshot'la işlem açmamalı.

**Geri düşüş:** snapshot yoksa `text()` `(None, meta)` döner; çağıran eski
`extras.text()`'e düşer. Sessiz bozulma yok — `meta["problems"]` ve `errors[]` dolu olur.

---

## 4. `run.py` entegrasyonu

`patches/0001-run-load_market-alertachart.patch` (mekanik uygulanabilir).
Özü:

```python
def load_market(symbol, interval):
    df = data.add_indicators(data.klines(symbol, interval=interval, limit=400))
    fund, fng, oi = data.funding(symbol), data.fear_greed(30), data.open_interest(symbol, interval)
    tech, sent = data.snapshot(symbol, df, fng=fng, fund=fund, oi=oi, interval=interval)
    # Türev/duygu bloğu AlertaChart'tan (5 borsa). Snapshot yoksa eski kaynağa düşer.
    ac_txt, ac_meta = alertachart_bridge.text(symbol, df, interval, legacy={
        "onchain": extras.onchain(symbol),
        "fng": ", ".join(f"{d}:{v}({c})" for d, v, c in (fng or [])[:7]),
        "vs": extras.volume_spike(df),
    })
    if ac_txt:
        return df, tech, ac_txt, ac_meta["extras"]
    ext_txt, ext = extras.text(symbol, df, interval)
    return df, tech, sent + "\n" + ext_txt, ext
```

Notlar:
- AlertaChart bloğu varken `sent` (eski funding+OI+F&G) **atılır** — aksi halde aynı
  veri iki kaynaktan, iki farklı sayıyla gelir (eski hatanın kaynağı buydu).
  F&G kaybolmaz: `legacy["fng"]` ile bloğun sonunda duruyor.
- `ac_meta["extras"]` botun `ext` sözlüğüyle uyumlu: `onchain`, `volume_spike`,
  `derivatives.liq_24h`, `alertachart`. `lessons.parse_ctx` bozulmaz.
- `fund`/`oi` yalnızca geri düşüş yolunda kullanılır; çağrı maliyeti aynı kalır.

---

## 5. Bilinen sınırlar (dürüstçe)

1. **Likidasyon haritası tahmindir** — gerçekleşen likidasyon değil, OI dağılımından
   modellenir. Blokta `TAHMİNİ` yazıyor; ajan ikisini karıştırmamalı.
2. **Isı haritası kayıtlı defterdir** — anlık değil, son 2 saatin ortalaması.
   `% mevcut` düşükse seviye güvenilmez (ör. BTC 80,531 → %32).
3. **Haber başlıkları işlenmemiş** — duygu skoru yok. Ajan kendi okur.
4. **Snapshot anlıktır** — bot taze snapshot ister; tazelik penceresi varsayılan
   240 dk (`OVERLAY_MAX_AGE_MIN`). Bu, asistan/MCP döngüsünü gerektirir; Python
   tarafı kendi başına AlertaChart'a gidemez.
5. **Spot klines ↔ perp türev** — teknik blok Binance spot, türev perp.
   Fiyat farkı basis kadar; iki blokta farklı fiyat görünmesi normal.
   (İstersen teknik bloğu da `BTCUSDT.P` mumlarına çevirebiliriz — ayrı karar.)
6. **Kapsam** — opsiyon blokları yalnız BTC/ETH/SOL gibi majörlerde dolu;
   altcoinlerde `opt` boş gelir ve o bölüm yazılmaz.

---

## 6. Hızlı kontrol

```powershell
python dataflows/alertachart_bridge.py BTCUSDT 1h
python dataflows/alertachart_bridge.py ETHUSDT 1h
```

Çıktı: `meta` (bar, yaş, tazelik, eksik kaynaklar) + blok.
`meta.problems` boş ve `stale: false` ise blok ajana verilebilir.

---

## 7. Overlay tazeleme (uzak MCP) — tek komut

Render AlertaChart MCP'sine erişemez; overlay'leri **asistan/MCP döngüsü** besler.
Tek komut:

```powershell
python tools/mcp_refresh.py                 # evrendeki tüm semboller, Railway'e yükle
python tools/mcp_refresh.py --local         # sadece cache'e yaz
python tools/mcp_refresh.py --symbols BTCUSDT.P,ETHUSDT.P
```

- Varsayılan hedef: `https://crypto-multiagent-production.up.railway.app/upload-payload`
  (token kod içinde varsayılan; ortam değişkeni gerekmez).
- Token: `~/.local/share/opencode/opencode.db` (credential, label `alertachart`).
  Suresi dolunca `refresh_token` ile yenilenir ve **aynı dosyaya geri yazılır**
  (refresh token döner; tek sahip kuralı şart).
- Rate limit: `get_orderflow` 20 çağrı / 10 dk. Bu yüzden ilk tur 13, ikinci tur
  kalan semboller (arada ~10 dk) önerilir: `--batch 13 --wait 620`.
- `apply_payload.py` boş/anlamsız payload'un iyi overlay'i ezmesini engeller.
- Tur sonunda 2 ek çağrı: `scan_flow(flow_breadth)` + `scan_flow(squeeze_radar, limit=60)`
  → `_market.json` (sıkışma vetosu ve makro genişlik oyu).

### Tazelik penceresi

`OVERLAY_MAX_AGE_MIN` (varsayılan **240 dk**). 4 saatlik tazeleme ritmine uyar;
teknik ve TD Sequential mumları yine canlı Binance'ten gelir, yalnız
orderflow/duygu/makro bloğu bu yaşa kadar eskiyebilir. Daha sıkı veri istersen
`OVERLAY_MAX_AGE_MIN=60` ver ve saatlik tazele.

### Railway (canlı ortam)

| Öğe | Değer |
|---|---|
| Servis | `crypto-multiagent-production` |
| Adres | `https://crypto-multiagent-production.up.railway.app` |
| Healthcheck | `/health` (commit + kasa satırı döner) |
| Kalıcı disk | volume → `/app/runs` (durum: `live/paper.json`, `live/triggers.json`, `live/journal.jsonl` + `cache/alertachart` overlay'leri) |
| Ortam değişkeni | **gerekmez** (token'lar kodda varsayılan; `CA_AC_CACHE` Dockerfile'da) |

`railway.json` healthcheck'i ve `restartPolicyType: ALWAYS`'ı tanımlar; uygulama
uyumaz. Overlay cache'i `CA_AC_CACHE=/app/runs/cache/alertachart` ile kalıcı
diskte durur, yani deploy cache'i silmez. Sağlık kontrolü:
`GET /debug/selftest?token=...` → Binance erişimi, overlay sayısı, tetik izleyici.

### Render'da kalıcı durum (eski, yedek)

Render her deploy'da konteyner diskini siler; `runs/live` silinince aynı mumun
sinyali yeniden gidebilir. İki yol var:

**A) Ücretli plan + disk (en temiz).** Panelden iki disk ekle:

| Disk | Mount Path | Boyut |
|---|---|---|
| `botstate` | `/app/runs/live` | 1 GB |
| `overlaycache` | `/app/cache` | 1 GB |

Tek disk kullanacaksan `/var/data` gibi bir yola bağla ve `LIVE_DIR` ile
`cache/alertachart` yolunu ona taşı (`LIVE_DIR=/var/data/live`).

**B) Ücretsiz plan: GitHub `state` branch'ine yedek (kurulu).**
`tools/state_backup.py` durumu (`triggers.json`, `telegram_state.json`,
`journal.jsonl`, son 6 saatin kararları) tek zip olarak **ayrı `state`
branch'ine** yazar; `main`'e dokunmaz, böylece Render yeniden deploy olmaz.
Konteyner açılışında geri yüklenir.

Gerekli ortam değişkenleri (Render → Environment):

| Değişken | Değer |
|---|---|
| `GH_STATE_TOKEN` | fine-grained PAT, **Contents: Read/Write** (yalnız bu repo) |
| `GH_STATE_REPO` | `delluxe555-dev/crypto-multiagent` (varsayılan) |
| `GH_STATE_BRANCH` | `state` (varsayılan) |

Dockerfile akışı: açılışta `state_backup.py --pull`, sonra 5 dk'da bir
`--push`. İçerik değişmediyse push atlanır (commit şişmez). Durum:
`GET /debug/state?token=...` → token var mı, son push/pull sonucu, boyut.

Elle deneme:

```powershell
$env:GH_STATE_TOKEN="github_pat_..."
python tools/state_backup.py --push
python tools/state_backup.py --status
```

Not: `state` branch'ine **sır koymayın** (telegram token'ı `config/` altında,
zip'e girmez; yalnız `runs/live` yedeklenir).

### Küçük fiyatlı coinler (DOGE / PENGU / 1000PEPE…)

Seviyeler fiyat ölçeğine göre yuvarlanır (`_tick_for`, ~5 anlamlı basamak):

| Fiyat | Yuvarlama adımı | Telegram'da |
|---|---|---|
| 75.673,9 | 1 | `75.674` |
| 1.212,67 | 0,1 | `1.212,7` |
| 222,22 | 0,01 | `222,22` |
| 0,07056 (DOGE) | 0,000001 | `0,070560` |
| 0,006391 (PENGU) | 0,0000001 | `0,0063910` |
| 0,005268 (1000PEPE) | 0,0000001 | `0,0052680` |

Eskiden sabit 0,001 adımı küçük coinlerde SL/TP'yi `0,000` yapıyor, SL girişe
eşit çıkıp anında tetikleniyordu. Ayrıca SL girişe en az **%0,60** (ve en az
**0,60 ATR**) uzakta tutulur (`min_sl_pct` / `min_sl_atr`, ATR tavanını
aşmadan). Geçersiz seviyeli (SL/TP sıfır veya girişin yanlış tarafında)
sinyaller hiç açılmaz.

### Giriş kalitesi (seçicilik)

"Her coine girip anında SL olma" sorununa karşı dört kapı vardır; biri bile
geçmezse sinyal üretilmez (Telegram'a mesaj gitmez):

| Kapı | Kural | Ayar |
|---|---|---|
| Trend | 4h SMA50/SMA200 yönü + fiyat SMA50'nin doğru tarafında | `meta_gate` (zorunlu) |
| Uzama | Fiyat EMA21'den en fazla 1,20 ATR uzakta (piyasa emrinde 0,60) | `max_ext_atr` / `market_max_ext_atr` |
| Tetik | Koşullu tetik her zaman fiyatın **önünde**: en az 0,35 ATR / %0,20 ileride kapanış | `trig_buf_atr` / `trig_buf_pct` |
| Kırılım | Tetik en yakın swing desteğinin **altında** / direncinin **üstünde** (en az 0,25 ATR / %0,10 tampon); tetik fiyattan 3 ATR'dan uzağa düşemez | `clear_buf_atr` / `clear_buf_pct` / `max_trig_atr` |

### Sıkışma vetosu ve akış genişliği (piyasa katmanı)

`mcp_refresh.py` her turda iki `scan_flow` çağrısı daha yapar ve payload'a yazar;
`apply_payload.py` bunları `cache/alertachart/_market.json` dosyasına böler:

```json
{"asof": "...", "breadth": {"pct": 30, "avg24": 44.4, "coins": 100, "streak": "..."},
 "squeeze": {"QNTUSDT.P": {"score": 94.3, "reads": "short squeeze risk", "...": "..."}}}
```

| Kapı | Kural | Ayar |
|---|---|---|
| Sıkışma vetosu | SHORT adayı +70 ve üstü skorla (short kalabalığı) / LONG adayı −70 ve altı skorla (long kalabalığı) açılmaz | `squeeze_veto` (`SQUEEZE_VETO`) |
| Akış genişliği | 100 perp'te net alıcı payı ≥%60 ise makro oyu +0,4; ≤%40 ise −0,4 | `_global_market()` |

`_market.json` `MARKET_MAX_AGE_MIN` (varsayılan **240 dk**) sonrası yok sayılır;
radar listesinde olmayan sembolde kapı açıktır. Kararda `market` alanı
(`breadth_pct`, `squeeze`, `squeeze_reads`) ve veto varsa `vetoes[].by == "squeeze"` görünür.

### Dinamik evren: aşırı hareket filtresi

24 saatlik |değişim| `MAX_ABS_CHG_24H` (varsayılan **%25**) üstündeki coin dinamik
slotlara alınmaz (pump/dump tepesinde alınan coin'in overlay'i ve sinyali güvenilmez;
ör. INIT −%51). Çekirdek evren etkilenmez.

Ek olarak aynı sembol+yon kapanışından sonra **120 dk** yeni tetik almaz
(`TG_REENTRY_COOLDOWN_MIN`). Portföy tavanı (açık pozisyon / aynı yön sayısı)
**yoktur**: sinyal üretimi açık pozisyon sayısından bağımsızdır. Journal
yanlılık freni yalnız piyasa emrini kapatır; koşullu sinyali durdurmaz.

Eski davranış: tetik `min(son 3 mumun dibi − 0,1 ATR, fiyat − 1 ATR)` idi; son
mumun dibi zaten bir swing desteği ise tetik tam desteğin üstüne denk geliyor,
fiyat oradan tepki verince SHORT dipte açılıyordu (XRP 1,0531 ↔ destek 1,0543).
Artık kırılım teyidi istenir: SHORT tetiği en yakın swing dibinin `clear_buf`
kadar altında, LONG tetiği en yakın swing tepesinin `clear_buf` kadar üstünde
kapanış ister. Yakında (3 ATR içinde) seviye yoksa fiyat tamponu kullanılır;
tetik yine de 3 ATR'dan uzağa düşerse karar `trigger_distance` vetosuyla iptal
edilir (`trigger_dist_atr` kararda saklanır).

### Giriş (dolum) fiyatı

Pozisyon, sinyaldeki referans seviyeden (`levels.entry`) değil **gerçek dolum**
fiyatından açılır:

- Koşullu sinyalde dolum = tetik mumunun kapanışı (mesajda görünen fiyat).
- Piyasa sinyalinde dolum = açılış anındaki son kapanmış 1m mumun kapanışı.
- Referans seviye `ref_entry` olarak saklanır (mesajdaki `Giriş (ref)`).

Gecikme/gap yüzünden fiyat SL'yi geçmişse, TP1'i aşmışsa veya gerçek dolumla
RR `TG_MIN_FILL_RR` (varsayılan **1,0**) altına düşerse işlem açılmaz ve mesaj
gönderilmez (`missed_fill`). Restart sonrası `TG_MARKET_MAX_DELAY_MIN`
(varsayılan **10 dk**) değerinden daha eski piyasa kararları da `stale_market`
olarak atlanır.

### Piyasa (market) kararları

Komite tetik beklemeden girmeye karar verirse (`mode == "market"`) mesaj aynı
blok düzeniyle **anında** gider (başlık: `Piyasa girişi` / `Anlık fiyat`),
pozisyon o anki fiyattan açılır ve TP1/TP2/SL takibi aynı şekilde işler.

### Kağıt hesap (paper trading)

Her gönderilen sinyalde `tools/paper.py` sanal bir pozisyon açar; bakiye
**1000 USDT** ile başlar. Hesap `runs/live/paper.json`'da tutulur ve state
yedeğine dahildir (deploy/restart'ta geri gelir). Eski sinyaller sayılmaz:
dosya yoksa ilk yeni sinyalde 1000 USDT ile başlar.

| Değişken | Varsayılan | Anlam |
|---|---|---|
| `PAPER_START_BALANCE` | 1000 | Başlangıç bakiyesi (USDT) |
| `PAPER_RISK_PCT` | 1.0 | İşlem başına risk (% bakiye) |
| `PAPER_TP1_FRACTION` | 0.5 | TP1'de kapatılan kısım |
| `PAPER_FEE_PCT` | 0.05 | Yön başına komisyon (%) |
| `PAPER_MAX_LEVERAGE` | 5 | Notional / bakiye üst sınırı |

Pozisyon büyüklüğü `qty = (bakiye × risk%) / |giriş − SL|` ile hesaplanır.
TP1'de yarım kapatılır, kalan TP2/SL/ters sinyal/zaman aşımında kapanır.
Komisyon her kapanışta iki yönlü düşülür.

Hesabı sıfırlamak için (varsayılan 1000 USDT, açık takip pozisyonları sessizce
`reset` durumuna alınır):

```
curl -X POST "https://crypto-multiagent-production.up.railway.app/debug/paper/reset?token=..."
```

Telegram'da tetik ve TP1/TP2/SL mesajlarının sonuna tek satır eklenir:

```
💰 Kasa 1.019,49 USDT · K/Z +19,49 USDT (%+1,95) · 1 işlem (1K/0Z)
```

Durum: `GET /debug/paper?token=...` → bakiye, K/Z, açık pozisyonlar, son işlemler.

---

## 8. Ek katman (extras): tarama, haber, opsiyon, türev, defter

`tools/ac_extras.py` tek turda şunları toplar ve `_extras.json` olarak yükler
(`apply_payload.py` katman katman birleştirir; boş katman öncekini **ezmez**):

| Katman | MCP aracı | İçerik | Kullanan ajan |
|---|---|---|---|
| `scan` | `scan_market` | overview (adv/dec, MA50 üstü, momentum bantları, BTC/ETH), gainers/losers, hacim patlamaları, funding uçları, squeeze | `a_macro` (genişlik + risk iştahı) |
| `news` | `get_news` | 20 başlık + yeni listelenenler | `a_sentiment` (ton), `a_macro` (`news_global`, sistemik) |
| `options` | `get_options` | BTC/ETH: max pain, gamma flip, dealer gamma, call/put duvarı, IV, 25d skew, put/call OI | `a_onchain` (yalnız BTC/ETH) |
| `deriv` | `get_derivatives_history` | BTC/ETH 7g OI + funding ortalaması | `a_thesis` (boğa/ayı özelliği) |
| `book` | `get_order_book_events` | majörlerde spoof/depth olayları | `a_orderflow` |
| `hours` | `get_volume_hours` | saatlik hacim profili (sakin saat notu) | `a_orderflow` |
| `calendar` | `get_stock_calendar` | makro/hisse takvimi (özet) | — (bilgi; oya girmez) |

Tazelik: `_global_extras()` **180 dk**. Dosya yoksa katman sessizce atlanır.

Haber vetosu: `news_gate()` — sembol tonu |skor| ≥ **2.4** ise o yöndeki sinyal
veto edilir (`dec["extras"]["news_gate"]`).

```powershell
python tools/ac_extras.py            # topla + Railway'e yükle
python tools/ac_extras.py --local    # sadece cache'e yaz
```

Kontrol: `GET /debug/extras?token=...` (katman yaşları + özet sayaçlar).

---

## 9. Botun kendi AlertaChart kimliği + `mcp_loop`

Railway AlertaChart MCP'sine **ağ olarak erişebiliyor** (401 + `WWW-Authenticate`
döner). Eksik olan tek şey kimlikti. Bot artık kendi OAuth grant'iyle çalışıyor:

| Öğe | Değer |
|---|---|
| İstemci | `mcpc_aJjjTJVyMrycPW1JdS1fGgnE` (`crypto-multiagent-bot`, dynamic registration) |
| Kapsam | `alertachart.read alertachart.write offline_access` |
| Kimlik dosyası | `/app/runs/cache/alertachart/_oauth.json` (kalıcı disk, `0600`) |
| Yazma yolu | `POST /admin/oauth` (`X-Upload-Token`), gövde `{"refresh","client_id","access","expires"}` |
| İstemci kodu | `tools/ac_mcp.py` (yenileme + **dosya kilidi**: rotasyon tek sahip) |
| Döngü | `tools/mcp_loop.py` (Dockerfile CMD içinde) |

`mcp_loop` ritmi:

| İş | Varsayılan | Değişken |
|---|---|---|
| Overlay (`mcp_refresh.py`) | 120 dk | `OVERLAY_REFRESH_MIN` |
| Extras (`ac_extras.py`) | 45 dk | `EXTRAS_REFRESH_MIN` |

Yeniden başlatmada veri tazeyse hemen tur atmaz (dosya yaşına bakar). Yani
overlay'ler artık asistan oturumuna bağlı değil; 7/24 kendi kendine tazelenir.

Asistanın kendi OpenCode MCP kimliği **ayrı** kalır (farklı istemci), yani biri
diğerinin refresh token'ını döndürmez.

---

## 10. Alerta Practice aynası

Botun açtığı her kağıt pozisyon AlertaChart'ın **Alerta Practice** hesabına da
girer (`tools/practice_bridge.py`):

| Olay | Practice emri |
|---|---|
| Açılış | `place_practice_order` — market, aynı sembol/yon, notional = kağıt işlemin notional'i, TP2 + SL takılı, kaldıraç 1 |
| TP1 | `close_practice_position` — `fraction: 0.5` |
| TP2 / SL / ters / zaman aşımı | `close_practice_position` — `fraction: 1` |

Kimlik yoksa hiçbir şey patlamaz: pozisyon `practice_pending` olarak işaretlenir,
`track_positions` her turda (en fazla 3 kez) yeniden dener. Notional < 5 USD ise
emir gönderilmez.

| Değişken | Varsayılan | Anlam |
|---|---|---|
| `PRACTICE_MIRROR` | `1` | `0` → aynalama kapalı |
| `PRACTICE_TP1_FRACTION` | `0.5` | TP1'de kapatılan kısım |

Durum: `GET /debug/practice?token=...` → hesap, açık pozisyon sayısı, aynalanan
/ bekleyen, son `practice.log` satırları. Uçtan uca test:
`POST /debug/practice-test?notional=20` (`X-Upload-Token`) — küçük BTC emri açar
ve hemen kapatır.

---

## 11. Telegram'da piyasa bağlamı satırı

Sinyal mesajlarının (tetik ve piyasa girişi) **en altına** tek satır eklenir;
blok düzeni ve etiketler değişmez:

```
💰 Kasa 883,56 USDT · K/Z -116,44 USDT (%-11,64) · 15 işlem (3K/12Z)
📊 501↑/249↓ · MA50 üstü %15,2 · BTC 74,4k (+1,4%)
```

- Kaynak: `_extras.json` (`scan`: adv/dec, MA50 üstü, BTC) + `_market.json`
  (sıkışma ≥ 55 ise `sıkışma NN`).
- Tazelik: **240 dk**; veri yok/bayatsa satır hiç eklenmez (mesaj bozulmaz).
- TP1/TP2/SL olay mesajlarına eklenmez — yalnız giriş mesajlarında.

---

## 12. TP1 sonrası SL girişe çekilir (breakeven)

TP1 vurulduğu anda SL **girişin kâr tarafına** taşınır:

| Yön | Yeni SL | Örnek (giriş 0,3155 / ilk SL 0,32073) |
|---|---|---|
| SHORT | giriş − pay | 0,31498 (girişin biraz **altı**) |
| LONG | giriş + pay | girişin biraz **üstü** |

- `pay = |giriş − ilk SL| × TP1_BE_FRAC` (varsayılan **0,10** = riskin %10'u,
  0–0,5 arası kırpılır). Yani SL tam girişte değil, biraz kârda durur.
- Sıra: `pos["sl"] = be_sl(pos)` → `paper.move_sl()` → `practice.on_tp1()` →
  Telegram. Mesaj ve practice aynası **yeni** SL'i görür.
- TP1'in vurulduğu mumda yeni SL test edilmez (`continue`), anında sahte SL olmaz.
- `sl_orig` açılışta saklanır; tüm R hesapları **ilk risk** üzerinden yapılır
  (SL'de çıkış +0,1R, TP2 +2,1R gibi).
- Telegram TP1 mesajı: `Kalan TP2 0,30440 · SL 0,31498 (girişe çekildi)`.
- TP1 sonrası bu SL vurulursa mesaj **SL değil BE** der:
  `🛡️ BE vuruldu · FETUSDT.P` / `TP1 sonrası SL girişteydi`. Gerçek SL
  (TP1 görmemiş) hâlâ `🟥 SL vuruldu` olarak gider.
- Practice motoru kâr tarafındaki SL'i reddederse eski SL (`sl_orig`) ile devam
  edilir, `practice.log`'a `yeni SL kabul edilmedi, eski SL korundu` yazılır;
  kapatma yine botun kendi SL'sinden olur.

| Değişken | Varsayılan | Anlam |
|---|---|---|
| `TP1_BE_FRAC` | `0.1` | SL'in girişten kâr tarafına kaydırıldığı risk oranı |
