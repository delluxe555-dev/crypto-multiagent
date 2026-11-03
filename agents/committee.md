# Komite protokolü (`committee/1.0`)

Canlı döngüde kararı **10 ajan** verir. Ajanların hiçbiri doğrudan emir üretmez;
önce görüş + güven, sonra oylama, sonra veto, en son risk katmanı seviyeleri hesaplar.

## Ajanlar ve veri kaynakları

| # | Ajan | Girdi | Oy |
|---|------|-------|----|
| 1 | Teknik | `live_cycle` Bölüm 1-2 (15m/1h/4h, yapı, formasyon) | evet |
| 2 | Temel/On-chain | `get_chain_lab` modülleri: `flow_score`, `spot_perp_lead`, `net_position_flow`, `coinbase_premium`, `leverage_saturation`+funding, `squeeze_risk` | evet (modül yoksa **çekimser**) |
| 3 | Haber & Sentiment | `get_news` + funding/OI rejimi | evet |
| 4 | Likidasyon/Orderflow | `get_orderflow`, `get_order_book`, `get_liquidation_map`, `get_liquidity_heatmap`, `get_large_trades`, `get_order_book_events` | evet |
| 5 | Makro | `get_macro` serilerinin **günlük değişimi** (US10Y, US02Y, HY spread, NFCI, Fed net likidite) + `get_options_volatility` | evet |
| 6 | Boğa | tüm veriyi **lehte** okur, en güçlü long tezi + tetik seviyesi | evet |
| 7 | Ayı | tüm veriyi **aleyhte** okur, en güçlü short tezi + tetik seviyesi | evet |
| 8 | Trader | sentez; giriş/stop/hedef taslağı | **danışman** (oy sayılmaz) |
| 9 | Risk | RR, maliyet/ATR, duvar mesafesi, olay riski, boyut | **VETO** |
| 10 | Meta-Auditor | veri tutarlılığı, yanlılık, çift sayım, eksik veri | **VETO** |

## Karar kuralı

> Bu protokolün **deterministik uygulaması** `tools/engine.py`'dir (`committee-engine/1.0`).
> Canlı döngüde kararı o üretir; Grok'un `trader.py` / `risk_rules.py` / hakem / `agents.py`
> karar katmanı **kullanılmaz**. Girdi: Binance **perp** mumları + taze AlertaChart overlay.

1. **Oylama:** her ajan `BUY / SELL / HOLD` + güven (0-1). Çekimser (veri yok) oy sayılmaz.
   Boğa/Ayı oy verir; Trader sentez olduğu için **danışman**dır, oya sayılmaz (çift sayım olmasın).
2. **Eşik:** en az **4 geçerli oy** (çekimserler hariç), en az **3 yön oyu** ve
   `max(BUY,SELL) / (BUY+SELL) ≥ %55` → aday işlem. Aksi halde **HOLD** (varsayılan).
   "HOLD > zorla işlem".
3. **Veto:** Risk veya Meta-Auditor `veto=true` derse aday işlem **piyasa emrine** dönüşemez.
   Veto, tetik emrini (koşullu giriş) engellemez; yalnızca anında girişi engeller.
4. **Piyasa emri şartı:** veto yok **ve** RR_net ≥ *piyasa tabanı* **ve** maliyet/ATR ≤ 0.25.
   Aksi halde işlem yalnızca **tetikli** (15m kapanışı ile onaylı) olarak yazılır.
5. **Yön yanlılığı freni:** son 30 kararın >%70'i tek yönde ise Meta-Auditor ek gerekçe ister
   (geçmişte sabit-short tabanı −1.73%, PF 0.68 üretti).
6. **Tetik:** `SELL` → son 3 mumun en düşüğünün 0.1 ATR altı, `BUY` → en yükseğinin 0.1 ATR üstü;
   tetik fiyatı girişten en fazla 1 ATR uzakta olabilir. Geçerlilik: 8 karar mumu (15m'de 2 saat).
   Tetik fiyatıyla seviyeler **yeniden** hesaplanır; RR eşiği yine tutmazsa işlem yazılmaz.

## Risk katmanı (deterministik, LLM'siz)

- Stop: varsayılan `ATR_MULT × ATR14` (15m 2.0 · 1h 1.75 · 4h 1.5). Giriş ile o bandın içinde
  bir swing yüksek/düşük varsa stop onun 0.25 ATR ötesine taşınır; toplam mesafe **3 ATR**'yi geçmez.
- Hedef: RR_net ≥ *koşullu taban*ı sağlayan **en yakın** likidite kümesi / ısı duvarı / swing;
  4R'den uzak seviye kullanılmaz. Uygun seviye yoksa 1.5R (TP1) ve 2.5R (TP2) varsayılanı.
- **RR tabanı sabit değil** (motor kendi kalibre eder):
  koşullu taban `1.35` → pay < %70 ise `+0.15`, overlay bayat/eksikse `+0.15`,
  maliyet/ATR > 0.35 ise `+0.10` (tavan `1.90`). Piyasa emri tabanı `max(1.75, koşullu+0.25)`,
  tavan `2.20`. Gerekçe: kanıt zayıfladıkça veya maliyet ATR'yi yiyorsa daha fazla ödül istenir;
  1.2 civarı RR 15m gürültüsünde maliyeti bile karşılamıyor.
- `RR_gross = (giriş−TP)/(SL−giriş)` (short); `RR_net` = maliyet düşülmüş.
- Maliyet varsayımı: **taker %0.045 × 2 + kayma ≈ %0.10** tur (perp).
- `maliyet/ATR` oranı: piyasa emri için tavan 0.25; 0.50'nin üstünde işlem tamamen **veto**.
- Boyut: `risk_R` (varsayılan 1.0R; overlay bayatsa/4h trend karşıysa 0.5R); miktar botta hesaplanır.
- Break-even: +1R veya TP1 dolduğunda; süre aşımı 24 saat / 96 mum.

## Çıktı (`decision/1.0`)

`runs/live/<zaman>/decision_<SEMBOL>.json`:
`action`, `mode` (`market|conditional|none`), `trigger`, `entry`, `stop`, `tp1`, `tp2`,
`rr_gross`, `rr_net`, `cost_pct`, `risk_r`, `valid_until`, `invalidate`,
`votes` (ajan → yön/güven), `vetoes`, `consensus`, `notes`, `telegram` (gönderim sonucu).

Her döngü `runs/live/journal.jsonl` dosyasına tek satır özet yazar (denetim izi).
Telegram'a yalnız **uygulanabilir** kararlar gider ve **uzlaşma ≥ %65** olmalıdır; altındaki
adaylar dosyada kalır, mesaj atılmaz.

## Ajan puanlaması (deterministik)

**Temel/On-chain** (`lab` satırları): `flow_score` 55 üstü +1.2 / 45 altı −1.2;
`spot_perp_lead` ±0.8·min(1,|v|/0.5); `net_position_flow` işareti ±0.8 (negatif = net short açılışı);
`coinbase_premium` ±0.5·min(1,|v|/0.02); `leverage_saturation` sırası ≥90 **ve** funding > 0 → −0.5
(kalabalık long); `squeeze_risk` ±0.6·min(1,|v|/70). Toplam |s| ≤ 0.35 → HOLD.

**Makro** (`slow.macro` günlük değişimler): US10Y ±0.02 üstü → ∓1.0; US02Y → ∓0.5;
HY spread → ∓0.7 (genişleme risk-off); NFCI → ∓0.5 (sıkılaşma risk-off); Fed net likidite → ±0.3.
Toplam |s| < 0.35 → HOLD (oy yine geçerli sayılır, çekimser değil).

## Tarama kadansı

Saatlik tur **yok**. `tools/scan.py` 5 dakikada bir (gerekirse 60 sn) Binance perp mumlarına bakar;
tetik çıkarsa ve overlay tazeyse tam komiteyi (`engine.decide`) çalıştırıp kararı yazar, overlay
bayatsa "tazele" der. Karar TF'si 15m, bağlam 1h/4h.

> Bu çıktı araştırma/kağıt işlem içindir; yatırım tavsiyesi değildir.
