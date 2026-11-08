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
$env:PAYLOAD_UPLOAD_TOKEN="..."
python tools/mcp_refresh.py                 # 23 sembol, Render'a yukle
python tools/mcp_refresh.py --local         # sadece cache'e yaz
python tools/mcp_refresh.py --symbols BTCUSDT.P,ETHUSDT.P
```

- Token: `~/.local/share/opencode/opencode.db` (credential, label `alertachart`).
  Suresi dolunca `refresh_token` ile yenilenir ve **aynı dosyaya geri yazılır**
  (refresh token döner; tek sahip kuralı şart).
- Rate limit: `get_orderflow` 20 çağrı / 10 dk. Bu yüzden ilk tur 10, ikinci tur
  13 sembol (arada ~10 dk) önerilir: `--batch 10 --wait 620`.
- `apply_payload.py` boş/anlamsız payload'un iyi overlay'i ezmesini engeller.

### Tazelik penceresi

`OVERLAY_MAX_AGE_MIN` (varsayılan **240 dk**). 4 saatlik tazeleme ritmine uyar;
teknik ve TD Sequential mumları yine canlı Binance'ten gelir, yalnız
orderflow/duygu/makro bloğu bu yaşa kadar eskiyebilir. Daha sıkı veri istersen
`OVERLAY_MAX_AGE_MIN=60` ver ve saatlik tazele.

### Render'da kalıcı durum (deploy/restart tekrarını önler)

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

### Piyasa (market) kararları

Komite tetik beklemeden girmeye karar verirse (`mode == "market"`) mesaj aynı
blok düzeniyle **anında** gider (başlık: `Piyasa girişi` / `Anlık fiyat`),
pozisyon o anki fiyattan açılır ve TP1/TP2/SL takibi aynı şekilde işler.
