# crypto-agents — Basit çok ajanlı kripto analiz sistemi

TradingAgents'tan (TauricResearch) esinlenen, kriptoya özel, küçük ve anlaşılır bir sistem.
**Yatırım tavsiyesi değildir; araştırma/deneme amaçlıdır. Gerçek parayla otomatik işlem yapmaz.**

## Nasıl çalışır?
1. **Veri (ücretsiz, anahtarsız):**
   - Binance spot mumları (`api.binance.com`, erişilemezse `data-api.binance.vision`) → RSI14, MACD, SMA50, SMA200, ATR14
   - Funding oranı: Binance Futures (bu sunucudan bölge engelli) → yedek olarak **OKX** perpetual funding
   - Açık pozisyon (OI): OKX istatistik API'si
   - Korku & Açgözlülük endeksi: alternative.me
2. **Ajanlar (her biri 1 LLM çağrısı, toplam 6):**
   teknik analist → duygu/türev analisti → boğa → ayı (boğaya cevap verir) → hakem (BUY/SELL/HOLD + güven + stop + hedef) → risk yöneticisi (stop kontrolü, %1 risk ile pozisyon büyüklüğü)
3. **Model:** OpenRouter (OpenAI uyumlu API). Varsayılan ücretsiz model `nvidia/nemotron-3.5-lightning:free`; `CA_MODEL` ortam değişkeniyle değiştirilebilir.

## Kullanım
```bash
cd /workspace/crypto-agents
set -a; . /home/box/.secrets/openrouter.env; set +a     # OPENROUTER_API_KEY
.venv/bin/python run.py BTCUSDT                         # günlük (1d, varsayılan)
.venv/bin/python run.py ETHUSDT --interval 1h           # gün içi: 15m | 1h | 4h | 1d
CA_MODEL="baska/model" .venv/bin/python run.py BTCUSDT  # farklı model
.venv/bin/python backtest.py BTCUSDT 10                 # 10 haftalık tarihte geriye dönük test (10 çağrı)
```
Çıktılar `outputs/` klasörüne `.json` (tam) ve `.md` (okunur özet) olarak yazılır.

## Zaman aralığı (interval)
- Göstergeler seçilen mum aralığında hesaplanır (ör. `1h` için SMA200 = son 200 saat).
- `1d`'den kısa aralıklarda ajanlara "gün içi" modda oldukları söylenir: teknik yapı, funding ve OI öne çıkar;
  haber/makro ve Korku&Açgözlülük ikinci planda kalır. Ufuk: 15m → birkaç saat, 1h → ~1 gün, 4h → 2-3 gün, 1d → 1-2 hafta.
- **Gün içi işlemde komisyon ve kayma (slippage) çok önemlidir:** Binance spotta tipik komisyon ~%0,1 (alış+satış ≈ %0,2),
  vadelide ~%0,02-0,05 + funding. Kısa aralıklarda beklenen hareket bu maliyetlere yakın olabilir; sinyal kâğıt üstünde
  kârlı görünse bile maliyetlerden sonra zarar edebilir. Backtest'e maliyet eklemeden gün içi sonuçlara güvenmeyin.

## Yeni eklenenler (v2)
| Dosya | Ne yapar |
|---|---|
| `scan.py` | **İki aşamalı tarama.** Aşama 1 (LLM'siz): Binance spot'ta 24s USDT hacmine göre ilk 100 coin; `config.json`'daki hariç listesi (stabil/fiat, TRX, TON, BNB…), kaldıraçlı token'lar, düşük volatilite (ATR% eşiği + alt %10), 24s'te >%40 oynayan anomaliler ve düşük likidite elenir. Hacim sıçraması, ATR%, 4h/alt aralık trend uyumu, RSI aşırılığı, funding (OKX toplu) ile puanlanır. Aşama 2: ilk `--top` adayda (ve `--majors` ile BTC/ETH) çok ajanlı tartışma. Kota önceden kontrol edilir. |
| `extras.py` | Türev verisi (funding, OI, long/short oranı, taker akışı, likidasyonlar), Binance emir defteri dengesizliği (±%0,5/±%1), hacim sıçraması, zincir üstü/akış (stablecoin arzı – DefiLlama; BTC hashrate/ücret – mempool.space; işlem sayısı – blockchain.info; ETH TVL – DefiLlama). Binance Futures bu sunucudan bölge engelli → OKX kullanılır. HTTP önbellekli. |
| `paper.py` | Kâğıt işlem defteri (`outputs/ledger.json/.csv`): karar, giriş, stop, hedef, büyüklük; stop/hedef/süre ile kapanış, %0,1 komisyon + %0,05 kayma. Hafıza: geçmiş kararlar + sonuçlar ve ajan isabet oranı hakeme özet olarak verilir. `outputs/summary.json`: pano için son kararlar, kâğıt PnL, ajan istatistikleri. |
| `risk_rules.py` | Kural tabanlı risk: ATR'ye dayalı stop, işlem başına %1 risk ile pozisyon büyüklüğü, pozisyon tavanı %50, günlük %2 zarar limiti. Yalnızca long/nakit. |
| `run.py --mtf --entry 1h` | Çoklu zaman dilimi: 4h trend ajanı + 1h/15m giriş ajanı (2 çağrı); yalnızca hizalıysa sinyal. |
| `backtest.py` | Seçilen N geçmiş tarihte yalnızca hakem (1 çağrı/tarih, önbellekli), ATR stop, maliyetler dahil, aynı pencerelerde al-ve-tut ile kıyas. |
| `CA_DRY_RUN=1` | LLM çağırmadan boru hattı testi (sahte yanıt, `outputs_dryrun/`). Sonuç değildir. |

```bash
.venv/bin/python scan.py --interval 1h --top 5 --majors   # tarama + ilk 5 aday (+BTC/ETH) için tartışma
.venv/bin/python scan.py --interval 4h --no-llm           # sadece ücretsiz aşama 1
.venv/bin/python backtest.py BTCUSDT 10 --interval 1d --step 7
```
Not: Bir tam analiz 6 istek; `--top 5 --majors` ≈ 42 istek → ücretsiz günlük 50 sınırının neredeyse tamamı.
Kısa sinyaller (SHORT/SELL) kaydedilir ama kâğıt defterde açılmaz. Açık pozisyonların toplamı için ayrı bir portföy tavanı henüz yok.

## Likidasyon verisi (liq.py) — 15dk / 1s / 4s / Günlük

Duygu ajanına giden metinde likidasyonlar zaman dilimlerine göre ayrı bölümler halinde verilir (`— 15dk —`, `— 1s —`, `— 4s —`, `— Günlük —`).

- **Gerçekleşen likidasyonlar:** OKX `public/liquidation-orders` uç noktası `after=ts` ile sayfalanır (sayfa başı 100 kayıt). OKX yalnızca **~son 24 saati** tutar; BTC'de bu ~15 sayfa / ~1.500 kayıt eder. Her pencere için long $, short $, adet ve long/short oranı. **Yalnızca OKX USDT-swap** — piyasanın tamamı değil.
- **Tahmini likidasyon kümeleri (ısı haritası benzeri, TAHMİNİ):** her zaman diliminde son ~100 mumun OKX açık pozisyon (OI) geçmişi + mum fiyatı kullanılır. OI artışı o mumun tipik fiyatından yeni pozisyon sayılır, 5x/10x/25x/50x/100x kaldıraçlara dağıtılır (bakım teminatı ~%0,4), long/short hesap oranıyla ağırlıklanır, eski girişler sönümlenir, OI düşüşü havuzu küçültür, fiyatın zaten geçtiği seviyeler silinir. Fiyatın altındaki en yoğun 3 long-liq ve üstündeki en yoğun 3 short-liq kümesi, tahmini $ ve % uzaklıkla verilir. Uzaklık sınırı: 15dk ±%4, 1s ±%8, 4s ±%15, günlük ±%30. Pencere öncesinden kalan pozisyonlar modele girmez; tutarlar yalnızca OKX OI'sine göredir.
- Telegram "AÇILDI" mesajında karar zaman diliminin en yoğun tahmini kümeleri tek satırda gösterilir: `🧲 Tahmini likidasyon (1s): ↑ … · ↓ …`.
- Ek LLM çağrısı yok; istekler önbellekli (likidasyon listesi 2 dk, mum/OI 2–30 dk). Elle deneme: `.venv/bin/python liq.py BTCUSDT ETHUSDT`.

## Sınırlamalar
- OpenRouter ücretsiz hesapta **günde 50 istek** sınırı var (bakiye yüklenince 1000'e çıkar). Bir analiz = 6 istek.
- Küçük/ücretsiz modeller hata yapabilir; JSON çıktısı bozuk gelirse ham metin `hakem_raw` / `risk_raw` alanına kaydedilir.
- Backtest'te model, test tarihlerinden sonraki fiyatları eğitim verisinden biliyor olabilir (look-ahead riski);
  backtest yalnızca teknik veri + Korku&Açgözlülük kullanır, tek "hakem" çağrısıyla çalışır ve komisyon içermez.

## Sağlayıcı zinciri (config.json → "providers")
Sırayla: **Gemini** (analistler `gemini-3.1-flash-lite` → `gemini-flash-lite-latest`; hakem/risk/MTF `gemini-3-flash-preview` → flash-lite yedekleri) →
**OpenRouter** ücretsiz modeller → (isteğe bağlı) yerel **Ollama** `qwen3-4b-local` (`enabled:false`). 429/5xx/zaman aşımı/boş yanıtta sıradakine geçer;
her adımda yanıtlayan sağlayıcı/model çıktıya (`providers`) ve konsola yazılır. Günlük kota hatası (Gemini model başına, OpenRouter sağlayıcı başına)
`outputs/.cache/llm_dead.json`'a `retryDelay` süresince kaydedilir, böylece sonraki çalıştırmalar boşuna denemez.
Not: Gemini ücretsiz katmanında `gemini-3-flash-preview` **günde 20 istek/model** (gözlenen `GenerateRequestsPerDayPerProjectPerModel-FreeTier`).

## Tarayıcı evreni (sıkılaştırılmış)
Binance spot USDT çiftleri; stabil/fiat/sarılı + TRX/TON/BNB hariç; kaldıraçlı ve ASCII olmayan semboller hariç; 24s hacim (spot + OKX USDT-M perp) ≥ 20 M$;
OKX USDT-M perp zorunlu (tokenize hisseleri de eler); 30 günden yeni listelemeler hariç; |24s değişim| > %40 anomali; düşük volatilite (ATR% eşiği/10. yüzdelik) elenir.
İsteğe bağlı `exclude_meme` listesi.

## Sürekli kâğıt işlem botu (trader.py + paper.sh) — GERÇEK EMİR YOK
```
./paper.sh start|stop|status|restart     # daemon (nohup+setsid); ~/.bashrc / ~/.profile'daki `paper.sh ensure` kancası yeniden başlatmada geri kaldırır
./paper.sh cycle [--top N]               # elle bir saatlik döngü
./paper.sh summary [--send]              # sabah özeti (Telegram'a --send ile)
```
- Her saat ~:01 (1h mum kapanışından sonra): aşama-1 tarama → ilk `top_n` aday + BTC/ETH → MTF (4h trend + 1h giriş) → hizalıysa tam 6 ajanlı tartışma →
  hakem BUY/SELL, güven ≥ `min_confidence` (65) ve MTF ile aynı yöndeyse canlı fiyattan sanal LONG/SHORT açılır (ücret %0,1 + kayma %0,05 her taraf).
- Stop = 2×ATR(1h), hedef = 3×ATR (tek hedef, kısmi kâr alma yok), en fazla 24 saat. Risk işlem başına özsermayenin %1'i (ücret dahil); büyüklük stop mesafesinden.
- Sanal kaldıraç: yalnızca teminatı küçültür; üst sınır güvene göre 65–70 → 3x, 70–80 → 4x, ≥80 → 5x (asla > 5x). Pozisyon başına teminat ≤ özsermayenin %20'si,
  en fazla 5 eşzamanlı pozisyon, günlük gerçekleşen zarar %2'yi aşarsa yeni işlem yok; 10 $ altı büyüklük (borsa minimumu) atlanır. Başlangıç özsermaye 1.000 $.
- Her 2 dakikada LLM'siz izleyici: Binance spot canlı fiyat + son 1m mum fitilleri ile stop/hedef/süre kontrolü; ikisi birden değdiyse ihtiyatlı olarak stop.
- Telegram (/home/box/.secrets/telegram.env): yalnızca açılış/kapanışta ve her gün 08:30 (İstanbul) sabah özeti. Olay yoksa mesaj yok.
- Dosyalar: `outputs/trader/{ledger,state,summary,last_cycle}.json`, `cycles.jsonl`; pano için `outputs/summary.json` → `paper_trader`; loglar `logs/`.
- Günlük LLM bütçesi `daily_llm_budget` (400); tüm sağlayıcılar tükenirse döngü sessizce durur, sonraki saat tekrar dener.

## Hatalardan ders çıkarma (lessons.py) — hafıza + yansıma
Önceki "hafıza" (`paper.memory_text`: aynı coinin son kararları + ajan isabetleri, backtest'te hep boştu) olduğu gibi kalır; üstüne işlem sonuçlarından öğrenen hafif bir katman eklendi. **Gerçek emir yok; dersler yalnızca bilgidir, sert risk kurallarını (stop, %1 risk, kaldıraç sınırı, limitler) asla değiştirmez.**
- **Kayıt:** pozisyon kapanınca (STOP / HEDEF / SÜRE) `lessons.on_close` ağsız çalışır: sembol, yön, kaldıraç, güven, giriş/çıkış, K/Z, süre, **MFE/MAE** (izleyici açılıştan beri en yüksek/en düşük fiyatı `hi_seen/lo_seen` olarak tutar; eski pozisyonlar 5m mumlarla doldurulur), ajan duruşları (4s trend, 1s giriş, hakem, teknik, duygu), gerekçe maddeleri ve girişteki göstergeler (funding, L/S, taker, 24s likidasyon, haftalık VWAP konumu, hacim profili değer alanı, yakın swing/FVG, SMA50/200, RSI, hacim sıçraması, tahmini likidasyon kümeleri) `outputs/trader/lessons.json`'a yazılır. Yeni pozisyonlarda bu bağlam `entry_ctx` olarak deftere de kaydedilir (eskiler için `outputs/<SEMBOL>_1h_<mum>.json`'dan çıkarılır).
- **Ders üretimi:** önce **kural tabanlı etiketler** (LLM'siz), ör. `hızlı_stop` (≤3 sa), `hiç_lehine_gitmedi`, `yarı_yoldan_döndü`, `funding_aşırı_yok_sayıldı`, `kalabalık_tarafta`, `yakın_seviyeye_girdi`, `vwap_ters_taraf`, `likidasyon_mıknatısı`, `ajan_ayrışması`, `yüksek_güven_yanıldı`, `süre_takipsiz`. En önemli 2 etiket kural dersini oluşturur. Ardından işlem başına **en fazla 1 ucuz LLM çağrısı** (`role=quick`, mevcut sağlayıcı zinciri) 1-2 cümlelik Türkçe ders yazar; kota bitmişse/hata olursa/≤25 sn'de gelmezse sessizce kural dersi kalır (geç gelirse depo sonradan güncellenir). Kural değişikliği öneren LLM dersleri elenir.
- **Depo:** son ~30 ders + kompakt işlem satırları + toplu istatistik (taraf, güven kovası, kaldıraç, 4s/1s uyumu, coin, çıkış nedeni; kazanma oranı ve net K/Z).
- **Geri besleme:** 4s trend, 1s giriş ve hakem istemlerine ≤550 karakterlik "Geçmiş derslerin" bloğu eklenir: aynı coin veya benzer kurulum (ortak koşul etiketleri) için en ilgili 3-5 ders + tek satır istatistik. Ders yoksa blok eklenmez.
- **Koruma:** `insights()` yalnızca RAPORLAR; her grupta n ≥ 10 ve genel kazanma oranından ≥20 puan sapma yoksa hiçbir şey söylenmez, hiçbiri otomatik uygulanmaz (`config.json → lessons.guard_min_n`).
- **Telegram:** kapanış mesajına tek satır `📝 Ders:`, 08:30 özetine `📝 Ders` bölümü (istatistik + son dersler) eklendi. Kapanış mesajı artık kilit bırakıldıktan sonra gönderilir (ders için ≤25 sn beklenebilir).
- **Backtest:** `python backtest_1h.py SOLUSDT --lessons [--lessons-llm]` karar noktaları boyunca bellekte ders biriktirir; her kararda yalnızca **o andan önce kapanmış** işlemlerin dersleri istemlere girer (look-ahead yok). Canlı `lessons.json`'a dokunmaz; önbellek ayrı (`outputs/.cache/bt1h_lessons`). `--lessons-llm` işlem başına 1 ders çağrısı ekler (`--max-calls`'a sayılır). Sonuç JSON'unda `dersler` alanı.
- Ayarlar: `config.json → lessons` (`enabled`, `llm`, `max_recent`, `prompt_chars`, `guard_min_n`). Test için `CA_LESSONS=/tmp/x.json` ile ayrı depo.

## Formasyon motoru (patterns.py) ve ajan karnesi (scoreboard.py)

**Neden:** Ajanlar grafik okumayı LLM'in "hafızasından" yapmasın; formasyonlar **LLM'siz, deterministik** hesaplanıp `data.snapshot()` içinde
`levels.py` gibi kompakt bir blok (~500–800 karakter) olarak mevcut istemlere eklenir. **Ek LLM çağrısı yoktur** (coin başına 6 çağrı aynı).

### patterns.py — ne tespit eder
Yalnızca **kapanmış mumlar** kullanılır; look-ahead yoktur (fraktal pivot 3 mum sonra onaylanır, Ichimoku bulutu 26 mum kaydırılır; test: i. mumda metin, veri i'de kesilince birebir aynı).
| Grup | İçerik |
|---|---|
| Mum | Doji, çekiç / ters çekiç, kayan yıldız, yutan boğa/ayı, harami, piercing / dark cloud, sabah/akşam yıldızı, üç beyaz asker / üç kara karga, cımbız tepe/dip, marubozu, inside/outside bar — **konum** (destek/direnç/trend) ve **hacim** bağlamıyla; bağlamsız mum yazılmaz |
| Grafik | Çift/üçlü tepe-dip, omuz-baş-omuz ve ters OBO, yükselen/alçalan/simetrik üçgen, yükselen/alçalan kama, boğa/ayı bayrağı ve flaması, range kırılımı/retest — **boyun çizgisi, kırıldı/kırılmadı, ölçülü hedef** |
| Harmonik | ZigZag (ATR eşikli) + Fibonacci oranları: Gartley, Bat, Alt-Bat, Butterfly, Crab, Deep Crab, Cypher, Shark (yaklaşık varyant), ABCD. Yön, **PRZ**, oranlar ve **geçersizlik** seviyesi. Tolerans ±0,04 |
| Fibonacci | Son ana salınımın 0,382/0,5/0,618/0,786 geri çekilme ve 1,272/1,618 uzantıları |
| Uyumsuzluk | RSI ve MACD **düzenli + gizli** uyumsuzluk (her iki osilatör aynıysa tek satır, daha güçlü) |
| Yapı | HH/HL/LH/LL, **BOS / CHoCH**, order block (mitige edilmemiş), likidite süpürme, eşit tepe/dip |
| Araçlar | EMA 9/21/50, ADX(+DI/-DI), Bollinger sıkışması/%B, StochRSI, OBV (uyumsuzluk), Ichimoku, Supertrend |
| **Yok** | **Elliott dalgaları bilerek eklenmedi**: sayım öznel ve algoritmik olarak güvenilir değil; uydurma sinyal üretmektense hiç yok. |

Blok başlığı: `Formasyonlar (hesaplanmış, yalnızca kapanmış mumlar; burada olmayan formasyonu UYDURMA)`. Anlamlı bir şey yoksa satır "yok" der.
Kalite filtreleri: pivot yüksekliği ≥ 3×ATR, formasyon yakın (≤15 mum) olmalı, hedef zaten gerçekleştiyse gösterilmez, düz/gürültülü seride formasyon üretilmez.

### İstem değişiklikleri (agents.py)
Teknik analist (artık "formasyon uzmanı" rolünde), 4h trend, 1h giriş ve hakem istemlerine ortak `PAT` kuralı eklendi: **yalnızca blokta olanı kullan, uydurma**;
tek formasyona güvenme, trend/seviye/hacim/gösterge ile **çakışma (confluence)** ara (≥2 bağımsız kanıt), zayıf/çelişkili olanı yok say, **geçersizlik seviyesini söyle**, "boyun kırılmadı" gibi durumları aynen koru.

**Ayrı "Formasyon uzmanı" aşaması eklenmedi:** coin başına +1 LLM çağrısı (6→7, bütçenin ~%17'si; günlük 400'lük ücretsiz kotada) demekti ve bilgi zaten deterministik hesaplanıyor.
Bunun yerine okuma görevi mevcut teknik analist çağrısına bindirildi (aynı çağrı bütçesi).

### Ajan karnesi (scoreboard.py) — YALNIZCA dahili
- Her döngü sonunda `outputs/trader/agent_scores.json` (ve ham gözlemler `agent_obs.json`) güncellenir; **Telegram'a gitmez**, sabah özetinde satır yoktur.
- Her ajanın BULL/BEAR/NEUTRAL kararı, karar mumunun kapanışından **+4s ve +24s** sonraki gerçekleşen hareketle (Binance data-api mumları) karşılaştırılır; yönlü isabet, Wilson %95 aralığı, sabit-yön tabanı ve son 100 çağrı kayan isabeti tutulur. Karar mumu = mumun AÇILIŞ saati (UTC), karar +1s kapanışında verilir.
- Boğa/ayı ajanları zorunlu savunmacı oldukları için skorlanmaz. Risk ajanı karara karışmıyor.
- **Değiştirme önerisi yalnızca önerir, asla otomatik uygulamaz:** ≥30 yönlü çağrı **ve** isabet şansın açıkça altında (Wilson üst sınır <%50) ya da diğer ajanların medyanından ≥15 puan düşük + sabit-yön tabanının altında. Karar kullanıcıda.
- Elle: `.venv/bin/python scoreboard.py update | audit`.

### Testler
`.venv/bin/python -W ignore tests/test_patterns.py` — sentetik serilerde her dedektör (çift tepe/dip, OBO, üçgen, kama, bayrak, range, Gartley/Bat/Butterfly/Crab, ABCD, mumlar), gerçek BTC/ETH/SOL 1h/4h mumlarında **look-ahead yok** (246 karşılaştırma), kompaktlık (ort. ~500, maks. <850 karakter) ve hız kontrolü.
LLM'siz tam hat: `CA_DRY_RUN=1 CA_NO_TG=1 python run.py BTCUSDT --mtf --entry 1h` (çıktı `outputs_dryrun/`, canlı defter/önbelleğe dokunmaz).

**SOL 1h backtest v3 (formasyon bloğu açık, aynı 10 nokta, ayrı önbellek):** son bakiye $1011.95 (v1 $992.59 / v2 $992.57), 1 işlem (kazanan), 32 LLM çağrısı. Örneklem 10 nokta/1 işlem — istatistiksel kanıt değildir, LLM çıktısı da deterministik değildir.

## Başabaş stopu (breakeven) — trader.py (be_sim.py ile seçildi)
Kural: açık pozisyonda fiyat girişten hedefe giden yolun **%67'sini** (`be_trigger_frac: 0.67`) gördüğünde (1m yüksek/düşükle ölçülür) stop **girişe çekilir**: yeni stop = giriş ± **%0,3** (`be_buffer_pct`, kâr tarafında; ~%0,25 çıkış masrafını karşılar). Yeni stop **bir sonraki tam dakikadan** geçerlidir (aynı mumdaki sıra belirsizliğinde stop kazanır kuralı korunur). Çekilmiş stop vurulursa işlem **⚪ BAŞABAŞ** olarak kapanır (çıkış etiketi `başabaş`, "kazanç" sayılmaz; stop değeri en kötü dolumla hesaplanır). Telegram: stop çekildiğinde tek seferlik **🛡 Stop girişe çekildi**, kapanışta **⚪ BAŞABAŞ**. Açık pozisyonlar da kurala tabidir (eşiği zaten geçmişse monitör ilk turda bir kez çeker + bildirir). Kapatmak için `config.json → trader.be_enabled: false` (canlı okunur, yeniden başlatma gerekmez).
- Seçim yöntemi: `be_sim.py` (LLM'siz, 1m mumlarla yeniden oynatma; çıktı `outputs/be_sim.md/.json`): tetik 0,33/0,5/0,67/1,0×ATR-eşdeğeri × tampon %0/0,3/0,5 × izleyen-stop varyantları. 0,33 ve 1,0 hedef vuruşunu yarıya indirip düşüşü artırdı; %0,5 tampon neredeyse her yerde daha kötüydü; izleyen stop ek değer katmadı (uygulanmadı). **0,67 + %0,3** 7 görünümün 5'inde tabanın üstünde/eşit, en az kaçırılan hedef.
- **Dürüst sınırlar:** örneklem küçük (canlı 7, SOL 4 işlem; kalan kısım rastgele giriş ızgarası). Kazanma oranı ↑ (%40,7 → %46,9; çıkışların ~%13'ü başabaş) ama beklenen getiri farkı gürültü içinde (ΔR ≈ +0,0025 ± 0,0038). Yani kural esas olarak **risk/davranış koruması**; kâr artışı vaat etmez.
- Dosyalar: `trader.py` (be_cfg/maybe_move_be/flush_be), `lessons.py` (başabaş ≠ kayıp/kazanç), `tgfmt.py` (be_msg, close_msg, morning_msg), `tests/test_breakeven.py` (25 kontrol; ledger'a dokunmaz: `CA_TRADER_DIR`, `CA_NO_TG=1`), `be_sim.py --days 14 --long-days 45`.

## Kullanıcı kritik seviyeleri (keylevels.py) — LLM'siz
`config.json → key_levels`: `{}` (boş — kişisel seviye tanımlı değil; istenirse `{"BTCUSDT": <sayı>}` biçiminde eklenir, canlı okunur). Ayarlar: `key_level_watch` (`enabled`, `touch_pct` 0,5, `reset_pct` 1,0, `touch_cooldown_h` 4, `max_below_alerts` 2).
1. **İstemlere enjeksiyon (ek LLM çağrısı yok):** `data.snapshot()` canlı akışta teknik veri bloğuna `Kullanıcının kritik seviyesi: … seviyeye uzaklık ±x% … Son kapanmış 4s mum: …` satırını ekler. `agents.py` içindeki ortak `KL` kuralı teknik, 4h trend, 1h giriş ve hakem istemlerine eklidir: **4s KAPANIŞ seviyenin altında = büyük ayı kırılım sinyali; fitil altı + kapanış üstü = boğa tepkisi; yalnız fitil kırılım sayılmaz.** Backtest'lerde kapalıdır (`i` verilirse veya `CA_NO_KEYLEVELS=1`; look-ahead olmasın).
2. **İzleyici (daemon, ~2 dk'da bir, LLM'siz):** her tamamlanan 4s mum için (Binance spot, UTC 4s ızgarası): **🚨 4s KAPANIŞ seviyenin ALTINDA** (2. ardışık altı kapanışta "hâlâ" teyidi; sonrası sessiz), **↩️ Seviyeden tepki (fitil alındı, kapanış üzerinde)**, kırılım sonrası kapanış tekrar üstteyse **✅ bilgi** mesajı; ayrıca fiyat seviyeye ilk kez ±%0,5 yaklaşınca **🎯** (histerezis %1 + 4 saat bekleme). Mum başına tek uyarı: `outputs/trader/keylevel_state.json`. İlk kurulumda yalnızca en son kapanmış mum değerlendirilir.
- Testler: `tests/test_keylevels.py` (34 kontrol: durum makinesi, dedupe, yaklaşma, kaçırılan mumlar, son 180 gerçek 4s mumla yeniden oynatma, istem bloğu, backtest'te kapalı); `CA_NO_TG=1` ile Telegram'a gitmez.
