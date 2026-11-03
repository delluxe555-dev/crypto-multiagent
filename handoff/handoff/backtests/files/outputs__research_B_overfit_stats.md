# Adım B — aşırı-uyum (overfitting) istatistikleri (2026-10-25, UTC+3)

Kod: `overfit_stats.py` (+ `overfit_report.py`), girdi `outputs/research/trades_r2.npz` (combo_bt2 işlemleri birebir yeniden üretildi). Fikir: QuantDinger `strategy_evolution/statistics.py` (Apache-2.0) — DSR, PBO, blok bootstrap; **kod sıfırdan**, scipy yok (`statistics.NormalDist`).
Hücre = (zaman-çifti, stop/hedef, kombinasyon) = 630; günlük seri = hücrenin tüm coinlerinin çıkış gününe göre net-R toplamı (148 gün). N (deneme sayısı) = 665 (A adımı; duyarlılık 5/20/630/850/1055).

## 1) Test çalışıyor mu? Sentetik RASTGELE veride yanlış-pozitif oranı (N=630 sıfır-ortalamalı strateji, T=150 gün)
En iyi stratejiyi seçip test ediyoruz — tam olarak gerçek aramanın yaptığı şey.

| senaryo | 'naif' t>1.96 (en iyi strateji) | PSR(N=1)>0.95 | **DSR(N=630)>0.95** | PBO ort. ± sd | IS-en-iyinin OOS Sharpe'ı | güç: gerçek günlük SR 0.2 → DSR>0.95 | güç: SR 0.3 |
|---|---|---|---|---|---|---|---|
| bağımsız, normal | 100.0% | 100.0% | **0.0%** | 0.48 ± 0.12 | +0.008 (IS: +0.38) | 2.0% | 13.0% |
| ortak faktör ρ=0,3, normal | 85.6% | 94.2% | **0.7%** | 0.50 ± 0.12 | +0.002 (IS: +0.32) | 3.5% | 25.8% |
| ρ=0,3, kalın kuyruk (t4) | 84.2% | 95.4% | **0.9%** | 0.52 ± 0.11 | -0.011 (IS: +0.30) | 3.5% | 26.5% |
| ρ=0.25 (gerçek hücre korelasyonu) | 89.3% | 96.2% | **0.5%** | 0.49 ± 0.12 | +0.005 (IS: +0.33) | 2.0% | 19.5% |

Yorum: (i) 630 hücreden en iyiyi seçip düz t-testi uygulamak %84-100 oranında 'anlamlı' sonuç üretir — yani **saf gürültüde bile**. (ii) DSR bunu %1'in altına indirir (yanlış-pozitif ≈ %0,5-0,9; nominal %5'in altında → tutucu). (iii) PBO null'da ≈0,5 (beklenen), IS'de seçilen stratejinin OOS Sharpe'ı ≈0 (seçim yanlılığı tam olarak IS'e özgü). (iv) **Güç düşük**: T=150 günle, gerçek günlük SR 0,2 (yıllık ≈3,8!) olan bir stratejiyi bile DSR yalnızca ~%2-4 ihtimalle onaylar; SR 0,3'te ~%13-26. Yani DSR 'reddedemedi' demek 'edge yok' kanıtı değil, 'bu veriyle ayırt edilemez' demektir.

## 2) Uçtan uca sentetik 'dünyalar' (gerçek motor): 24 dünya
Her dünyada 29 coinin gerçek 5m serisi **gün bloklarına bölünüp karıştırıldı** (tüm coinlerde aynı gün permütasyonu → coinler arası korelasyon ve gün-içi yapı korunur; günler arası trend/otokorelasyon yok edilir; ⇒ gerçek avantaj yok). Sonra gerçek combo_bt2 motoru (630 hücre, aynı maliyet) + aynı testler. Bu, 'gerçekte avantaj olmayan bir piyasada 630 hücre aramasında ne bulunur' sorusunun cevabı.

**taraf başı %0,05**: iki yarıda net-pozitif hücre sayısı medyan 4 (min 0, maks 88); ortalaması >0 hücre medyan 17 (maks 143); en iyi hücre ort. net R medyan +0.072 (maks +0.227).
- 'Naif' sahte keşif: en iyi hücrenin coin×3g-blok %95 CI'si 0'ı dışarıda bırakıyor: 10/24 dünya; gün-blok (tüm coinler) CI'si ile: 3/24.
- Reality-Check p<0,05: coin×blok bootstrap ile 3/24; gün-blok ile 0/24. DSR(N=665)>0,95: 0/24. PBO medyan 0.27 (aralık 0.06-0.54).
**taraf başı %0,15**: iki yarıda net-pozitif hücre sayısı medyan 0 (min 0, maks 5); ortalaması >0 hücre medyan 0 (maks 10); en iyi hücre ort. net R medyan -0.018 (maks +0.150).
- 'Naif' sahte keşif: en iyi hücrenin coin×3g-blok %95 CI'si 0'ı dışarıda bırakıyor: 2/24 dünya; gün-blok (tüm coinler) CI'si ile: 0/24.
- Reality-Check p<0,05: coin×blok bootstrap ile 0/24; gün-blok ile 0/24. DSR(N=665)>0,95: 0/24. PBO medyan 0.04 (aralık 0.00-0.10).

Gerçek veri ile kıyas (aynı maliyet): @0,05 iki yarıda pozitif **3**, ortalaması >0 **17**, en iyi hücre **+0,059R**. Sentetik dünyalarda bunlara eşit/aşan oran: 
- iki yarıda pozitif ≥3: 16/24 dünya; ortalaması >0 ≥17: 14/24; en iyi ≥+0,059R: 13/24.
Yorum: gerçek veri, rastgele-karıştırılmış dünyaların medyanından ayırt edilemiyor (hepsi ~yarı yarıya). 'Naif' coin×blok CI ile sahte keşif oranı çok yüksek; çünkü 29 coin aynı günlerde birlikte hareket ediyor, coin×blok bootstrap bağımsız birim sayısını şişirip CI'yi daraltıyor (Reality-Check'te de nominal %5 yerine 3/24 ≈ %12 yanlış-pozitif — küçük örnek, ama yön net). **Gün-blok (tüm coinler birlikte) bootstrap daha dürüst** ve gerçek veriye de bu uygulandığında CI'ler sıfırı kapsıyor. Uyarı: 24 dünya = kaba kalibrasyon; yüzde değerleri ±~%10 belirsiz.
(PBO notu: tüm hücreler maliyet yüzünden net-negatifken sıralama kalıcıdır — 'az kaybeden' IS'te de OOS'ta da az kaybeder — bu yüzden gürültü dünyasında PBO düşük çıkabilir; PBO bu yapıda 'edge var' kanıtı değildir. OOS kayıp olasılığı ve RC/DSR daha bilgilendirici.)

## 3) Gerçek combo_bt2 verisi

Hücreler birbirine çok benzer (aynı sinyal farklı HTF'de özdeş işlem verebiliyor; ortalama çift korelasyonu 0.24); özdeğer 'katılım oranı' ile etkin bağımsız deneme sayısı ≈ **5** (altına inmek DSR'yi gevşetir; tabloda N=5 ve 20 duyarlılığı var).

### taraf başı %0,05
- İki yarıda net-pozitif hücre: **3**; ortalaması >0: 17/558. SR0 (N=665 deneme sonrası beklenen en iyi günlük SR) = 0.349; gözlenen en iyi günlük SR bundan çok küçük.
- Reality-Check (max-t) p: coin×blok **0.977**, gün-blok **1.000** (H0: hiçbir hücrenin ortalaması >0 değil). PBO(558 hücre) = 0.32; IS-en-iyinin OOS-kayıp olasılığı 0.79; ort. OOS Sharpe -0.115 (IS +0.151).

| hücre | n | ort. net R/işlem | CI coin×3g | CI gün-blok | günlük SR (yıllık) | PSR | DSR N=5 / 20 / 665 / 1055 | IS / OOS R | başabaş maliyet %/taraf |
|---|---|---|---|---|---|---|---|---|---|
| 45m/2h ; S3/T6/72h ; L2_CamDaily_L3/H3reject_counterHTF | 1520 | +0.0587 | [-0.006,+0.122] | [-0.063,+0.183] | +0.080 (+1.5) | 0.83 | 0.26 / 0.06 / 0.001 / 0.000 | +0.040 / +0.092 | 0.119 |
| 45m/4h ; S3/T6/72h ; L2_CamDaily_L3/H3reject_counterHTF | 1434 | +0.0576 | [-0.008,+0.122] | [-0.075,+0.196] | +0.070 (+1.3) | 0.80 | 0.23 / 0.04 / 0.000 / 0.000 | +0.068 / +0.040 | 0.119 |
| 45m/4h ; S2/T4/48h ; L2_CamDaily_L3/H3reject_counterHTF | 2028 | +0.0526 | [-0.005,+0.112] | [-0.077,+0.184] | +0.067 (+1.3) | 0.79 | 0.21 / 0.04 / 0.000 / 0.000 | +0.058 / +0.042 | 0.091 |
| 30m/4h ; S3/T6/72h ; E2_vote6of7(noMACD) | 3295 | +0.0328 | [-0.017,+0.082] | [-0.094,+0.172] | +0.044 (+0.8) | 0.71 | 0.14 / 0.02 / 0.000 / 0.000 | -0.010 / +0.114 | 0.080 |
| 30m/2h ; S3/T6/72h ; E2_vote6of7(noMACD) | 3295 | +0.0328 | [-0.017,+0.082] | [-0.094,+0.172] | +0.044 (+0.8) | 0.71 | 0.14 / 0.02 / 0.000 / 0.000 | -0.010 / +0.114 | 0.080 |
| 30m/2h ; S3/T6/72h ; E4_vote9of11(+flow,stoch,bbmid) | 3452 | +0.0141 | [-0.038,+0.062] | [-0.102,+0.151] | +0.021 (+0.4) | 0.60 | 0.08 / 0.01 / 0.000 / 0.000 | -0.048 / +0.134 | 0.063 |
| 30m/4h ; S3/T6/72h ; E4_vote9of11(+flow,stoch,bbmid) | 3452 | +0.0141 | [-0.038,+0.062] | [-0.102,+0.151] | +0.021 (+0.4) | 0.60 | 0.08 / 0.01 / 0.000 / 0.000 | -0.048 / +0.134 | 0.063 |
| 45m/4h ; S3/T6/72h ; E5_vote8of11+HTF | 2216 | +0.0123 | [-0.045,+0.069] | [-0.138,+0.171] | +0.015 (+0.3) | 0.57 | 0.07 / 0.01 / 0.000 / 0.000 | -0.052 / +0.123 | 0.064 |

### taraf başı %0,15
- İki yarıda net-pozitif hücre: **0**; ortalaması >0: 0/558. SR0 (N=665 deneme sonrası beklenen en iyi günlük SR) = 0.808; gözlenen en iyi günlük SR bundan çok küçük.
- Reality-Check (max-t) p: coin×blok **1.000**, gün-blok **1.000** (H0: hiçbir hücrenin ortalaması >0 değil). PBO(558 hücre) = 0.03; IS-en-iyinin OOS-kayıp olasılığı 1.00; ort. OOS Sharpe -0.230 (IS +0.041).

| hücre | n | ort. net R/işlem | CI coin×3g | CI gün-blok | günlük SR (yıllık) | PSR | DSR N=5 / 20 / 665 / 1055 | IS / OOS R | başabaş maliyet %/taraf |
|---|---|---|---|---|---|---|---|---|---|
| 45m/4h ; S3/T6/72h ; L2_CamDaily_L3/H3reject_counterHTF | 1434 | -0.0261 | [-0.093,+0.038] | [-0.157,+0.111] | -0.031 (-0.6) | 0.35 | 0.00 / 0.00 / 0.000 / 0.000 | -0.019 / -0.038 | 0.119 |
| 45m/2h ; S3/T6/72h ; L2_CamDaily_L3/H3reject_counterHTF | 1520 | -0.0258 | [-0.090,+0.037] | [-0.146,+0.094] | -0.035 (-0.7) | 0.33 | 0.00 / 0.00 / 0.000 / 0.000 | -0.048 / +0.013 | 0.119 |
| 45m/4h ; S3/T6/72h ; L5_CamWeekly_L3/H3reject+HTF | 316 | -0.1400 | [-0.280,+0.006] | [-0.377,+0.136] | -0.088 (-1.7) | 0.16 | 0.00 / 0.00 / 0.000 / 0.000 | -0.141 / -0.139 | -0.025 |
| 45m/4h ; S2/T4/48h ; L2_CamDaily_L3/H3reject_counterHTF | 2028 | -0.0747 | [-0.134,-0.014] | [-0.204,+0.053] | -0.093 (-1.8) | 0.13 | 0.00 / 0.00 / 0.000 / 0.000 | -0.075 / -0.075 | 0.091 |
| 45m/4h ; S3/T6/72h ; E5_vote8of11+HTF | 2216 | -0.0756 | [-0.134,-0.019] | [-0.224,+0.085] | -0.094 (-1.8) | 0.14 | 0.00 / 0.00 / 0.000 / 0.000 | -0.143 / +0.042 | 0.064 |
| 45m/4h ; S3/T6/72h ; T4_Donchian20brk+HTF | 1850 | -0.0810 | [-0.145,-0.020] | [-0.251,+0.097] | -0.096 (-1.8) | 0.14 | 0.00 / 0.00 / 0.000 / 0.000 | -0.160 / +0.052 | 0.059 |
| 45m/4h ; S3/T6/72h ; T2_ST_flip+HTF_ST | 1053 | -0.0996 | [-0.183,-0.017] | [-0.276,+0.099] | -0.099 (-1.9) | 0.12 | 0.00 / 0.00 / 0.000 / 0.000 | -0.252 / +0.187 | 0.051 |
| 30m/4h ; S3/T6/72h ; E2_vote6of7(noMACD) | 3295 | -0.0761 | [-0.127,-0.027] | [-0.204,+0.069] | -0.102 (-2.0) | 0.12 | 0.00 / 0.00 / 0.000 / 0.000 | -0.123 / +0.013 | 0.080 |

**Maliyet stresi (en iyi hücre, ort. net R/işlem):** 0.03%: +0.076, 0.05%: +0.059, 0.075%: +0.038, 0.1%: +0.016, 0.15%: -0.026; başabaş ≈ %0.119/taraf. Gerçekçi piyasa-emri maliyeti (%0,10-0,15) altında negatif.

## 4) Dürüst özet
- Gerçek veride 'en iyi' hücreler (Camarilla L2, ~+0,06R @%0,05) **sentetik rastgele dünyalardaki en iyi hücrelerle aynı büyüklükte**; DSR ≈ 0, Reality-Check p ≈ 1; gün-blok CI sıfırı rahatça kapsıyor. %0,15'te hiçbir hücre pozitif değil.
- Bu 'edge yok' kanıtı değil, **'edge var' kanıtı da yok**: 148 gün, tek rejim, 630+ deneme; test gücü düşük (bölüm 1).
