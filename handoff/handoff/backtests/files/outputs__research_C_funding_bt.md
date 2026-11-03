# Adım C — funding + zorunlu likidasyon ile yeniden ölçüm (2026-10-25, UTC+3)

Kod: `funding_bt.py` (+ `funding_bt_part2.py`); işlem tablosu `outputs/research/trades_r2.npz` (combo_bt2'yi birebir yeniden üretir: 630 hücre, 2.630.285 işlem, hücre başına n farkı 0). Funding verisi: `outputs/research/funding/`.

## Varsayımlar (açık)
- **Fiyat** Binance SPOT 5m (combo_bt2 ile aynı). **Funding** Gate USDT-perp geçmişinden (Binance perp funding'ine bu sunucudan erişilemiyor → proxy); OKX ile çapraz kontrol (aşağıda).
- Funding: işlem süresince düşen her uzlaşma (settlement) için long, oran>0'da öder / short alır; R cinsinden `funding_R = -yön × Σoran × (e/sd)` (pozisyon = risk/stop-mesafesi). Uzlaşma aralığı sözleşmeye göre (Gate: çoğunlukla 8s).
- Zorunlu likidasyon (izole marjin, sabit kaldıraç L=5/10/20): likidasyon mesafesi = 1/L − mmr, **mmr = Gate sözleşmesinin `maintenance_rate`'i** (BTC 0,3%, PEPE 0,65% vb.; aşağıda coin başına). İşlemin MAE'si ≥ bu mesafe VE stop (1/k) likidasyondan önce değilse likide olur, kayıp = tüm teminat = −k/L R (≤ ~1,1R). MAE bar-içi sırayı bilmediğinden hedef barının dip/tepesi de dahil (temkinli). Likidasyon harcı/sigorta fonu kesintisi yok sayıldı.
- Funding kapsaması: işlemlerin %100.0'i Gate funding geçmişinin kapsadığı dönemde (kalan 0 funding sayıldı); OKX kapsaması %64.7.

## Gate ↔ OKX funding çapraz kontrol (aynı uzlaşma zamanlarında, 8s oranları)
| coin | ortak uzlaşma | korelasyon | Gate ort bp/8s | OKX ort bp/8s |
|---|---|---|---|---|
| AAVE | 99 | 0.58 | 0.37 | 0.31 |
| ADA | 239 | 0.55 | 0.38 | 0.41 |
| APT | 57 | 0.20 | 0.40 | 0.50 |
| ARB | 99 | 0.24 | 0.02 | -0.30 |
| ATOM | 96 | 0.48 | 0.04 | -0.38 |
| AVAX | 94 | 0.68 | 0.24 | 0.27 |
| BNB | 99 | 0.62 | 0.35 | 0.47 |
| BTC | 99 | 0.71 | 0.26 | 0.39 |
| DOGE | 99 | 0.32 | 0.40 | 0.62 |
| DOT | 254 | 0.44 | 0.71 | 0.28 |
| ETH | 99 | 0.67 | 0.35 | 0.36 |
| FET | 99 | 0.57 | 0.38 | 0.43 |
| FIL | 99 | 0.48 | 0.39 | 0.26 |
| INJ | 99 | 0.85 | 0.19 | 0.19 |
| JUP | 203 | 0.37 | 0.19 | -0.07 |
| LINK | 99 | 0.61 | 0.31 | 0.42 |
| LTC | 99 | 0.68 | 0.40 | 0.49 |
| NEAR | 97 | 0.51 | 0.66 | 0.44 |
| ONDO | 156 | 0.35 | 0.18 | 0.30 |
| OP | 74 | 0.00 | 0.11 | 0.40 |
| PEPE | 96 | 0.77 | 0.19 | 0.47 |
| RENDER | 208 | 0.38 | 0.34 | 0.28 |
| SEI | 196 | 0.49 | 0.32 | 0.05 |
| SOL | 99 | 0.67 | 0.12 | 0.31 |
| SUI | 99 | 0.63 | 0.35 | 0.48 |
| TIA | 507 | 0.20 | 0.15 | 0.11 |
| TRX | 99 | 0.91 | -0.99 | -1.35 |
| WLD | 99 | 0.73 | 0.37 | 0.61 |
| XRP | 92 | 0.82 | 0.39 | 0.39 |

Medyan korelasyon 0.57; ortalama fark (Gate−OKX) 0.01 bp/8s. (29/29 coin OKX'te ortak veriye sahip; OKX geçmişi ~96 gün.)

## Funding ölçeği
Gate 29 coin, tüm uzlaşmalar: ortalama 0.14 bp/uzlaşma (medyan 0.35), pozitif oran %67, %95 aralık [-1.9, 1.0] bp. (Referans: 1 bp = %0,01; taban oran %0,01/8s = 1 bp.)

## Aday hücreler: funding ve likidasyon etkisi (işlem başı ortalama net R; [%95 CI, coin×3-gün blok bootstrap])
Maliyet taban: taraf başı %0,05 (C_LO) ve %0,15 (C_HI). 'fund' = + funding; 'liq L' = funding + L× sabit kaldıraçla zorunlu likidasyon.

| hücre | n | long% | ort. funding_R | net@0,05 | +fund | +fund [CI] | +fund+liq5 | +liq10 | +liq20 | net@0,15 | +fund@0,15 [CI] | likide% (5/10/20x) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L2 Camarilla 45m/2h S3/T6/72h | 1520 | 53 | +0.0004 | +0.0587 | +0.0591 | [-0.003,+0.124] | +0.0591 | +0.0557 | +0.0320 | -0.0258 | -0.0254 [-0.088,+0.040] | 0.0/0.9/16.2 |
| L2 Camarilla 45m/4h S3/T6/72h | 1434 | 54 | +0.0010 | +0.0576 | +0.0586 | [-0.008,+0.122] | +0.0586 | +0.0550 | +0.0341 | -0.0261 | -0.0251 [-0.090,+0.039] | 0.0/0.9/16.5 |
| L2 Camarilla 45m/4h S2/T4/48h | 2028 | 54 | +0.0008 | +0.0526 | +0.0534 | [-0.006,+0.111] | +0.0534 | +0.0534 | +0.0455 | -0.0747 | -0.0738 [-0.133,-0.017] | 0.0/0.0/4.4 |
| E2 oy 6/7 30m/4h S3/T6/72h | 3295 | 49 | -0.0020 | +0.0328 | +0.0308 | [-0.019,+0.081] | +0.0308 | +0.0310 | +0.0226 | -0.0761 | -0.0781 [-0.128,-0.028] | 0.0/0.2/9.1 |
| E4 oy 9/11 30m/2h S3/T6/72h | 3452 | 48 | -0.0018 | +0.0141 | +0.0123 | [-0.036,+0.062] | +0.0123 | +0.0123 | -0.0073 | -0.0924 | -0.0942 [-0.143,-0.044] | 0.0/0.3/9.5 |

## Tüm 558 baz-dışı hücre: funding etkisi
- Hücre başına ortalama funding_R: ortalama -0.0007, medyan -0.0009, min -0.0028, max +0.0024 (R/işlem).
- Long payı ort. %48. Gate funding çoğunlukla pozitif → long ödüyor, short alıyor; funding_R long-ağırlıklı hücrelerde negatif.
- OKX ile (kapsanan ~96 gün) hesaplanan ortalama funding_R hücre ort.: -0.0006 (Gate: -0.0007; farklı kapsama nedeniyle birebir değil).

## Aşırı-uyum testi funding'li veride (overfit_stats.analyze, funding eklenmiş)
- **cost0.05pct**: iki yarıda net-pozitif hücre: funding'siz 3 → funding'li 3; ortalaması >0 olan hücre 17 → 15; Reality-Check p (en iyi hücre): 0.977 → 0.975; PBO(558) 0.32 → 0.32.
  - funding'li en iyi (SR'ye göre) hücre: 45m/2h | S3/T6/72h | L2_CamDaily_L3/H3reject_counterHTF n=1520 net +0.0591R [-0.006,+0.123] DSR(N=665)=0.001
- **cost0.15pct**: iki yarıda net-pozitif hücre: funding'siz 0 → funding'li 0; ortalaması >0 olan hücre 0 → 0; Reality-Check p (en iyi hücre): 1.000 → 1.000; PBO(558) 0.03 → 0.03.
  - funding'li en iyi (SR'ye göre) hücre: 45m/4h | S3/T6/72h | L2_CamDaily_L3/H3reject_counterHTF n=1434 net -0.0251R [-0.092,+0.039] DSR(N=665)=0.000

## NEWSHORT w16 / 4s tutma (liqbt_signals.py'nin yeniden yazımı; Gate 15m, ~21 gün, 26 coin) — fiyat getirisi, kısa pozisyon

Olay sayısı n=477 (rapordaki 477 ile karşılaştır; olay tanımı aynı: 4s fiyat ≤ −%0,5 ve OI ≥ +%1, refrakter 4s). Funding kapsaması %92.
| senaryo | ort. getiri bp [CI] |
|---|---|
| brüt (maliyetsiz) | +38.0 [+21.5,+54.9] |
| net %0,05/taraf (10bp tur) | +28.0 [+11.5,+44.9] |
| net %0,05 + funding | +28.1 [+11.6,+45.0] |
| net %0,15/taraf (30bp tur) | +8.0 [-8.5,+24.9] |
| net %0,15 + funding | +8.1 [-8.4,+25.0] |

Ortalama funding katkısı (short alır): +0.11 bp/işlem (4s tutma, ~yarı olasılıkla uzlaşma). Funding'in işlem başına etkisi küçük; asıl belirleyici maliyet.
- Sabit 5x: likide olan işlem %0.0; net(%0,05)+funding = +28.1 bp [notional getirisi; likidasyonda −1/L notional kaybı]
- Sabit 10x: likide olan işlem %0.2; net(%0,05)+funding = +28.2 bp [notional getirisi; likidasyonda −1/L notional kaybı]
- Sabit 20x: likide olan işlem %5.9; net(%0,05)+funding = +21.5 bp [notional getirisi; likidasyonda −1/L notional kaybı]
