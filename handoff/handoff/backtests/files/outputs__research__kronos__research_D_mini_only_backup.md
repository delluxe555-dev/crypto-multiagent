# Adım D — Kronos tam test (2026-10-25, UTC+3)

## Model: Kronos-mini — n=1305 tahmin, 29 coin × 45 gün (24 mum ufuk, her gün 1 çıkış, çakışmasız)
| ufuk | isabet [CI coin×3g] [CI gün-blok] | p(coin×blok / gün) | tahmin 'yukarı' | gerçek 'yukarı' | hep-long | hep-short | yanlılık-eşleşik rastgele | korelasyon |
|---|---|---|---|---|---|---|---|---|
| 1s | 49.5% [46.9,52.1] [44.5,54.2] | 0.696 / 0.825 | 54% | 58% | 58.1% | 41.9% | 50.7% | -0.015 |
| 4s | 50.0% [47.5,52.6] [44.5,54.9] | 0.999 / 0.967 | 50% | 58% | 57.7% | 42.3% | 50.0% | -0.055 |
| 12s | 51.0% [48.3,53.6] [46.2,55.7] | 0.464 / 0.656 | 48% | 52% | 51.7% | 48.3% | 49.9% | -0.060 |
| 24s | 52.6% [49.9,55.3] [46.7,58.3] | 0.057 / 0.351 | 46% | 50% | 50.4% | 49.6% | 50.0% | -0.009 |

24s strateji (taraf başı %0,15; ort |tahmin getirisi| 2.12%, ort |gerçek| 3.46%; long sinyal payı 46%):
| strateji | ort. bp/işlem | CI coin×3g | CI gün-blok | p (cb/gün) | rastgele içindeki yüzdelik |
|---|---|---|---|---|---|
| Kronos yon (net %0,15/taraf) | -29.7 | [-56.9,-4.3] | [-102.5,+32.3] | 0.024/0.385 | - |
| Kronos yon (brüt) | +0.3 | [-27.3,+27.3] | [-69.7,+66.2] | 0.983/0.939 | - |
| her zaman long (net) | +4.5 | [-23.3,+33.1] | [-97.3,+109.5] | 0.744/0.923 | - |
| her zaman short (net) | -64.5 | [-92.3,-36.8] | [-167.1,+35.3] | 0.000/0.232 | - |
| rastgele yon (net) 5000 sim | -30.1 | rastgele %95 [-57.3,-3.1] | - | - | Kronos > rastgelenin %52'ünden |
| rastgele (modelle ayni long orani) | -32.8 | rastgele %95 [-59.6,-7.1] | - | - | Kronos > rastgelenin %59'ünden |
| capraz-kesit (medyan-ustu long/alti short) net | -33.2 | [-59.4,-6.9] | [-55.7,-10.9] | 0.011/0.006 | - |
| capraz-kesit brüt | -3.2 | [-28.9,+23.0] | [-26.7,+19.7] | 0.824/0.788 | - |

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
| mini yön isabeti h=1 | 0.825 | 1.000 | hayır |
| mini yön isabeti h=4 | 0.999 | 1.000 | hayır |
| mini yön isabeti h=12 | 0.656 | 1.000 | hayır |
| mini yön isabeti h=24 | 0.351 | 1.000 | hayır |
| mini Kronos yon (net %0,15/taraf) | 0.385 | 1.000 | hayır |
| mini capraz-kesit (medyan-ustu long/alti short) net | 0.011 | 0.068 | hayır |
