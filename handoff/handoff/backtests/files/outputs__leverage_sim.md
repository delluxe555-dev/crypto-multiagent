# Kaldıraç simülasyonu (kâğıt, yeni LLM çağrısı yok)
Oluşturuldu: 2026-10-24T17:47:42+03:00 (UTC+3). Canlı ledger/config/state'e dokunulmadı.

**Veri:** SOL backtest v2'nin 2 işlemi + canlı ledger'daki 7 işlem (BTC, ETH, TIA, WLD, ONDO, BTC, TRUMP), tek $1.000 hesapta kronolojik. Fiyat yolu Binance 1 dk mumları. Her şey aynı: %1 risk, stop 2×ATR, hedef 3×ATR, ücret %0,1 + kayma %0,05/taraf, teminat sınırı %20, en çok 20 pozisyon. Doğrulama: 5x/mevcut kural simülasyonu canlı kapanan BTC (+8,11 $) ve ETH (+11,16 $) sonuçlarını birebir tutturdu.
Kademeler: mevcut 3/4/5x; "10x" tavanı 6/8/10x, "20x" tavanı 12/16/20x (aynı oranda ölçeklendi). Tüm işlemleri tavanda tutan varyant JSON'da (`*_flat_*`).

**Önemli:** 9 işlemin 5'i hâlâ açık, sonuçlar çoğunlukla açık kâr/zarara (son fiyat) dayanıyor; yalnızca 4 işlem kapandı.

## A) Aynı risk modu (şu anki kural: kaldıraç yalnızca teminatı sınırlar)
| Tavan | Final (gerçekleşen / açıklar dahil) | Getiri % (açıklar dahil) | Maks. düşüş % | Likidasyon | En kötü işlem % hesap | Kazanma (kapanan) | Teminat yetersizliğiyle atlanan | Tepe teminat kullanımı % |
|---|---|---|---|---|---|---|---|---|
| 5x | 1011,69 / 1020,22 $ | 2,02 | 2,0 | 0 | -0,97 | %75,0 (4 işlem) | 0 | 71,4 |
| 10x | 1012,46 / 1020,85 $ | 2,08 | 2,09 | 0 | -0,97 | %75,0 (4 işlem) | 0 | 69,9 |
| 20x | 1012,46 / 1020,85 $ | 2,08 | 2,09 | 0 | -0,97 | %75,0 (4 işlem) | 0 | 69,9 |

Fark neredeyse yok: risk hep ~%1 ($10), stop mesafesi aynı. 10x/20x yalnızca dar stoplu işlemlerde (ör. BTC) teminat tavanını gevşetip pozisyonu biraz büyütüyor (BTC 4x/815 $ → 6x/1.133 $). 10x ile 20x birebir aynı çıktı, çünkü risk kuralı tavandan önce devreye giriyor.

## B) Agresif mod (büyüklük = %20 teminat × kaldıraç, stop aynı → risk büyür)
| Tavan | Final (gerçekleşen / açıklar dahil) | Getiri % (açıklar dahil) | Maks. düşüş % | Likidasyon | En kötü işlem % hesap | Kazanma (kapanan) | Teminat yetersizliğiyle atlanan | Tepe teminat kullanımı % |
|---|---|---|---|---|---|---|---|---|
| 5x | 1010,92 / 1059,33 $ | 5,93 | 5,48 | 0 | -1,71 | %75,0 (4 işlem) | 0 | 99,1 |
| 10x | 1021,05 / 1116,1 $ | 11,61 | 10,03 | 0 | -3,43 | %75,0 (4 işlem) | 0 | 98,1 |
| 20x | 1038,92 / 1221,9 $ | 22,19 | 17,18 | 0 | -6,86 | %75,0 (4 işlem) | 0 | 96,5 |

Her işlemin stop kaybı: 5x'te ~%1,0–1,7, 10x'te ~%3,4, 20x'te ~%6,9 hesap (en kötü gerçekleşen). Kazanç da aynı oranda büyüdü, ama bu örnekte işlemlerin çoğu lehe gitti; yalnızca SOL backtest'in 2 işleminde (1 kazanan, 1 stop) agresif mod zarar büyüttü: 5x −%1,3, 10x −%2,6, 20x −%5,3. Sadece canlı 7 işlemde 20x agresif: +%29 (açık dahil), maks. düşüş %17,2.
Teminat: agresif modda 5 açık pozisyon teminatın ~%96–99'unu kullanıyor; 6. ve sonrası pozisyonlar "teminat yetersiz" diye atlanır (bu örnekte en fazla 5 eşzamanlı olduğu için 0 atlama göründü). Aynı risk modunda tepe kullanım ~%70.
Bu örnekte hiç likidasyon yok, ama TIA/WLD stopları (%4,2–4,4) 20x likidasyon mesafesine (%4,6) çok yakın.

## C) Duyarlılık ızgarası (yalnızca fiyat yolu)
BTC, ETH, SOL, WLD, TIA; son 14 gün, her 2 saatte 1h kapanışında long ve short, 1680 kurulum. Stop mesafesi (2×ATR): medyan %1,82, p10 %0,79, p90 %4,93. Likidasyon: bakım teminatı %0,4.
| Kaldıraç | Likidasyon mesafesi % | Stop, likidasyondan uzak (yapısal) % | Yolda önce likit olan % | Stop önce % | Hedef önce % | 24s süre doldu % | Likit seviyesine dokunan % | Agresif: stop kaybı hesap % (medyan / p90) |
|---|---|---|---|---|---|---|---|---|
| 5x | 19,6 | 0,0 | 0,0 | 50,3 | 30,1 | 19,6 | 1,5 | 2,1 / 5,2 |
| 10x | 9,6 | 0,0 | 0,0 | 50,3 | 30,1 | 19,6 | 8,0 | 4,2 / 10,5 |
| 20x | 4,6 | 13,8 | 7,2 | 44,5 | 29,9 | 18,4 | 24,0 | 8,5 / 20,9 |
| 30x | 2,93 | 38,6 | 24,52 | 31,0 | 28,9 | 15,5 | 38,7 | 12,7 / 31,4 |
| 50x | 1,6 | 55,7 | 38,51 | 23,6 | 25,4 | 12,5 | 58,8 | 21,2 / 52,3 |
Likidasyon stoptan önce gelir (20x'te sembol bazında stop > likit mesafesi): BTC: 0,0%, ETH: 0,0%, SOL: 0,0%, WLD: 14,3%, TIA: 54,8%. Likidasyon tam teminat kaybı = hesabın %20'si (agresif modda).

## Uyarılar
- Çok küçük örneklem: 9 işlem (4 kapanan) ve 14 günlük tek piyasa rejimi (düşüş ağırlıklı). Sistemin kanıtlanmış bir avantajı yok; yüksek kaldıraç avantajı değil, hem kazancı hem kaybı büyütür.
- Izgarada yön rastgele; amaç likidasyon sıklığını görmek, strateji getirisi değil. Dakika içi sıra bilinmiyor (aynı mumda stop+hedef → stop). Gerçek borsada ani fitil, kayma ve likidasyon ücreti daha kötü olabilir. Açık pozisyonlar son fiyatla değerlendi.
- Simülasyon yalnızca kâğıt; gerçek emir yok.

## Öneri
Aynı risk modunda kaldıracı 10x/20x'e çıkarmanın somut faydası yok (±birkaç $), ama likidasyon riskini de 20x'e kadar artırmıyor; en fazla 10x tavan makul. Agresif modda (risk büyütme) 10x'i bile edge kanıtlanana kadar önermem; 20x'te tipik bir stop hesabın ~%8,5'i (p90 %21), volatil coinlerde (TIA/WLD) stoptan önce likidasyon riski var. Öneri: şimdilik 5x'te kal (veya en fazla aynı-risk modunda 10x tavan). Büyüme istiyorsan kaldıraç yerine işlem başına riski kademeli artır (%1 → %1,5) ve önce en az 30–50 kapanan işlem biriktir.
