# Adım D — Kronos tam test (2026-10-25, UTC+3)

## Model: Kronos-small — n=1305 tahmin, 29 coin × 45 gün (24 mum ufuk, her gün 1 çıkış, çakışmasız)
| ufuk | isabet [CI coin×3g] [CI gün-blok] | p(coin×blok / gün) | tahmin 'yukarı' | gerçek 'yukarı' | hep-long | hep-short | yanlılık-eşleşik rastgele | korelasyon |
|---|---|---|---|---|---|---|---|---|
| 1s | 45.6% [43.0,48.4] [40.8,50.3] | 0.001 / 0.068 | 42% | 58% | 58.1% | 41.9% | 48.7% | -0.022 |
| 4s | 52.8% [50.1,55.4] [47.4,58.5] | 0.043 / 0.310 | 39% | 58% | 57.7% | 42.3% | 48.2% | -0.007 |
| 12s | 50.9% [48.0,53.7] [45.1,56.5] | 0.495 / 0.707 | 38% | 52% | 51.7% | 48.3% | 49.6% | -0.041 |
| 24s | 50.5% [47.9,53.3] [44.1,56.6] | 0.689 / 0.849 | 41% | 50% | 50.4% | 49.6% | 49.9% | -0.025 |

24s strateji (taraf başı %0,15; ort |tahmin getirisi| 6.70%, ort |gerçek| 3.46%; long sinyal payı 41%):
| strateji | ort. bp/işlem | CI coin×3g | CI gün-blok | p (cb/gün) | rastgele içindeki yüzdelik |
|---|---|---|---|---|---|
| Kronos yon (net %0,15/taraf) | -37.1 | [-65.6,-8.9] | [-108.8,+28.8] | 0.008/0.279 | - |
| Kronos yon (brüt) | -7.1 | [-35.4,+20.7] | [-79.7,+62.2] | 0.599/0.867 | - |
| her zaman long (net) | +4.5 | [-23.3,+33.1] | [-97.3,+109.5] | 0.744/0.923 | - |
| her zaman short (net) | -64.5 | [-92.3,-36.8] | [-167.1,+35.3] | 0.000/0.232 | - |
| rastgele yon (net) 5000 sim | -30.1 | rastgele %95 [-57.3,-3.1] | - | - | Kronos > rastgelenin %31'ünden |
| rastgele (modelle ayni long orani) | -36.5 | rastgele %95 [-62.8,-9.8] | - | - | Kronos > rastgelenin %49'ünden |
| capraz-kesit (medyan-ustu long/alti short) net | -33.0 | [-59.7,-5.8] | [-57.5,-8.2] | 0.019/0.011 | - |
| capraz-kesit brüt | -3.0 | [-29.7,+24.0] | [-27.6,+22.2] | 0.833/0.801 | - |

Günlük eşit-ağırlık portföy (net): ort -37.1 bp/gün, sd 237.1, günlük SR -0.156 (yıllık ≈ -3.0), PSR(0)=0.145, 45 gün.

Coin başına (24s yön isabeti; Wilson %95; net bp = %0,15/taraf sonrası):

| coin | n | isabet [Wilson] | tahmin↑ | gerçek↑ | brüt bp | net bp |
|---|---|---|---|---|---|---|
| AAVE | 45 | 47% [33,61] | 49% | 49% | -8 | -38 |
| ADA | 45 | 51% [37,65] | 44% | 49% | -2 | -32 |
| APT | 45 | 51% [37,65] | 33% | 51% | +57 | +27 |
| ARB | 45 | 51% [37,65] | 38% | 51% | -44 | -74 |
| ATOM | 45 | 60% [45,73] | 38% | 51% | +165 | +135 |
| AVAX | 45 | 44% [31,59] | 44% | 42% | -87 | -117 |
| BNB | 45 | 56% [41,69] | 29% | 51% | +9 | -21 |
| BTC | 45 | 58% [43,71] | 53% | 51% | +6 | -24 |
| DOGE | 45 | 53% [39,67] | 53% | 47% | +10 | -20 |
| DOT | 45 | 42% [29,57] | 29% | 51% | +38 | +8 |
| ETH | 45 | 56% [41,69] | 51% | 51% | +19 | -11 |
| FET | 45 | 47% [33,61] | 47% | 47% | -25 | -55 |
| FIL | 45 | 44% [31,59] | 31% | 51% | -44 | -74 |
| INJ | 45 | 58% [43,71] | 22% | 51% | +21 | -9 |
| JUP | 45 | 40% [27,55] | 36% | 51% | -19 | -49 |
| LINK | 45 | 51% [37,65] | 53% | 49% | -24 | -54 |
| LTC | 45 | 47% [33,61] | 36% | 53% | -65 | -95 |
| NEAR | 45 | 49% [35,63] | 24% | 58% | -87 | -117 |
| ONDO | 45 | 53% [39,67] | 51% | 53% | -31 | -61 |
| OP | 45 | 44% [31,59] | 36% | 42% | -9 | -39 |
| PEPE | 45 | 44% [31,59] | 2% | 58% | -63 | -93 |
| RENDER | 45 | 47% [33,61] | 49% | 58% | -42 | -72 |
| SEI | 45 | 44% [31,59] | 60% | 49% | -96 | -126 |
| SOL | 45 | 51% [37,65] | 51% | 51% | -33 | -63 |
| SUI | 45 | 51% [37,65] | 47% | 56% | -85 | -115 |
| TIA | 45 | 60% [45,73] | 27% | 49% | +117 | +87 |
| TRX | 45 | 56% [41,69] | 62% | 36% | +14 | -16 |
| WLD | 45 | 58% [43,71] | 29% | 53% | +78 | +48 |
| XRP | 45 | 51% [37,65] | 58% | 53% | +27 | -3 |

## Model: Kronos-mini — n=1305 tahmin, 29 coin × 45 gün (24 mum ufuk, her gün 1 çıkış, çakışmasız)
| ufuk | isabet [CI coin×3g] [CI gün-blok] | p(coin×blok / gün) | tahmin 'yukarı' | gerçek 'yukarı' | hep-long | hep-short | yanlılık-eşleşik rastgele | korelasyon |
|---|---|---|---|---|---|---|---|---|
| 1s | 49.5% [46.8,52.1] [44.6,54.2] | 0.707 / 0.803 | 54% | 58% | 58.1% | 41.9% | 50.7% | -0.015 |
| 4s | 50.0% [47.6,52.6] [44.6,55.1] | 0.965 / 0.953 | 50% | 58% | 57.7% | 42.3% | 50.0% | -0.055 |
| 12s | 51.0% [48.4,53.7] [46.3,55.7] | 0.468 / 0.672 | 48% | 52% | 51.7% | 48.3% | 49.9% | -0.060 |
| 24s | 52.6% [50.0,55.2] [46.9,58.4] | 0.049 / 0.353 | 46% | 50% | 50.4% | 49.6% | 50.0% | -0.009 |

24s strateji (taraf başı %0,15; ort |tahmin getirisi| 2.12%, ort |gerçek| 3.46%; long sinyal payı 46%):
| strateji | ort. bp/işlem | CI coin×3g | CI gün-blok | p (cb/gün) | rastgele içindeki yüzdelik |
|---|---|---|---|---|---|
| Kronos yon (net %0,15/taraf) | -29.7 | [-58.3,-3.5] | [-103.3,+30.6] | 0.031/0.403 | - |
| Kronos yon (brüt) | +0.3 | [-26.8,+27.9] | [-73.6,+63.4] | 0.974/0.961 | - |
| her zaman long (net) | +4.5 | [-23.5,+31.9] | [-95.6,+106.7] | 0.783/0.926 | - |
| her zaman short (net) | -64.5 | [-91.4,-37.8] | [-169.8,+36.4] | 0.000/0.223 | - |
| rastgele yon (net) 5000 sim | -29.8 | rastgele %95 [-56.4,-3.4] | - | - | Kronos > rastgelenin %51'ünden |
| rastgele (modelle ayni long orani) | -32.7 | rastgele %95 [-59.4,-5.8] | - | - | Kronos > rastgelenin %58'ünden |
| capraz-kesit (medyan-ustu long/alti short) net | -33.2 | [-60.0,-7.3] | [-57.1,-10.4] | 0.016/0.005 | - |
| capraz-kesit brüt | -3.2 | [-29.1,+23.6] | [-26.6,+18.8] | 0.844/0.790 | - |

Günlük eşit-ağırlık portföy (net): ort -29.7 bp/gün, sd 229.7, günlük SR -0.129 (yıllık ≈ -2.5), PSR(0)=0.170, 45 gün.

Coin başına (24s yön isabeti; Wilson %95; net bp = %0,15/taraf sonrası):

| coin | n | isabet [Wilson] | tahmin↑ | gerçek↑ | brüt bp | net bp |
|---|---|---|---|---|---|---|
| AAVE | 45 | 56% [41,69] | 31% | 49% | +73 | +43 |
| ADA | 45 | 44% [31,59] | 42% | 49% | -39 | -69 |
| APT | 45 | 47% [33,61] | 51% | 51% | -32 | -62 |
| ARB | 45 | 49% [35,63] | 53% | 51% | -145 | -175 |
| ATOM | 45 | 58% [43,71] | 36% | 51% | +92 | +62 |
| AVAX | 45 | 51% [37,65] | 47% | 42% | -61 | -91 |
| BNB | 45 | 53% [39,67] | 49% | 51% | +17 | -13 |
| BTC | 45 | 51% [37,65] | 51% | 51% | -29 | -59 |
| DOGE | 45 | 51% [37,65] | 56% | 47% | -47 | -77 |
| DOT | 45 | 58% [43,71] | 40% | 51% | +68 | +38 |
| ETH | 45 | 49% [35,63] | 49% | 51% | -10 | -40 |
| FET | 45 | 51% [37,65] | 47% | 47% | -60 | -90 |
| FIL | 45 | 60% [45,73] | 42% | 51% | +104 | +74 |
| INJ | 45 | 60% [45,73] | 51% | 51% | +78 | +48 |
| JUP | 45 | 58% [43,71] | 40% | 51% | +82 | +52 |
| LINK | 45 | 67% [52,79] | 47% | 49% | +82 | +52 |
| LTC | 45 | 42% [29,57] | 49% | 53% | -95 | -125 |
| NEAR | 45 | 53% [39,67] | 42% | 58% | +18 | -12 |
| ONDO | 45 | 49% [35,63] | 51% | 53% | +41 | +11 |
| OP | 45 | 49% [35,63] | 49% | 42% | -50 | -80 |
| PEPE | 45 | 47% [33,61] | 36% | 58% | -76 | -106 |
| RENDER | 45 | 56% [41,69] | 53% | 58% | -2 | -32 |
| SEI | 45 | 51% [37,65] | 40% | 49% | -47 | -77 |
| SOL | 45 | 62% [48,75] | 40% | 51% | -19 | -49 |
| SUI | 45 | 49% [35,63] | 40% | 56% | -136 | -166 |
| TIA | 45 | 64% [50,77] | 40% | 49% | +120 | +90 |
| TRX | 45 | 42% [29,57] | 58% | 36% | -2 | -32 |
| WLD | 45 | 47% [33,61] | 49% | 53% | +68 | +38 |
| XRP | 45 | 53% [39,67] | 60% | 53% | +16 | -14 |

## Çoklu test düzeltmesi (Holm-Bonferroni; aile = bu raporda bakılan testler)
| test | p (tutucu: iki bootstrap'ın büyüğü) | Holm düzeltilmiş p | reddedildi (α=0,05) |
|---|---|---|---|
| small yön isabeti h=1 | 0.068 | 0.680 | hayır |
| small yön isabeti h=4 | 0.310 | 1.000 | hayır |
| small yön isabeti h=12 | 0.707 | 1.000 | hayır |
| small yön isabeti h=24 | 0.849 | 1.000 | hayır |
| small Kronos yon (net %0,15/taraf) | 0.279 | 1.000 | hayır |
| small capraz-kesit (medyan-ustu long/alti short) net | 0.019 | 0.213 | hayır |
| mini yön isabeti h=1 | 0.803 | 1.000 | hayır |
| mini yön isabeti h=4 | 0.965 | 1.000 | hayır |
| mini yön isabeti h=12 | 0.672 | 1.000 | hayır |
| mini yön isabeti h=24 | 0.353 | 1.000 | hayır |
| mini Kronos yon (net %0,15/taraf) | 0.403 | 1.000 | hayır |
| mini capraz-kesit (medyan-ustu long/alti short) net | 0.016 | 0.192 | hayır |
