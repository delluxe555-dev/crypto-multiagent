# time_machine.py — "kendi mumlarından bootstrap" hedef/stop vuruş oranı testi (rapor)

Tarih: 2026-10-25 (Europe/Istanbul). Dosya: `time_machine.py` (kendi yazdığım uygulama; hazır koddan kopya yok; trader.py/config.json/signal_paper_loop.sh'e dokunmaz, `signals.csv`/`outcomes.csv`'yi yalnızca okur; Gate public mum verisi).

## Yöntem
* Havuz: giriş öncesi son 960 kapanmış 15m mum (10 gün) → her mum (o,h,l,c)/önceki kapanış−1 oranları (fiyat seviyesinden bağımsız); `--demean` ile ortalama sürüklenme çıkarılır (son trend sinyale bedava kenar yazmasın).
* Yol: girişten H=16 mum (4 saat) boyunca blok-bootstrap (blok=4, 2000 yol). Stop = 1.5×ATR14, hedef = 3×ATR14 (R=2). Aynı mumda ikisi birlikte vurulursa STOP önce (muhafazakâr). Zaman aşımı kapanışta çıkış. Short için ayna.
* Başabaş (yazı-tura) vuruş oranı = 1/(1+R) = **0.333** (maliyetsiz); 10 bp maliyetle ortalama **0.380**.
* Karşılaştırma: gerçek sinyalin hedef/stop vuruşu, aynı pencere için bootstrap beklentisiyle. Önemli: henüz bitmemiş sinyallerde yalnızca "erken vuranları" saymak seçilim yanlılığı yaratır; bu yüzden beklenen değer, gerçekte GÖZLENEN mum sayısı (k) için kümülatif ilk-vuruş olasılığıdır. (İlk sürümde bu hata vardı, düzeltildi.) p-değerleri Poisson-binom.

## Komutlar
```
.venv/bin/python time_machine.py signals            # outputs/time_machine_signals.json
/workspace/repos_review/ftvenv/bin/python time_machine.py calib   # OKX 5m→15m verisi gerekir (pyarrow); outputs/time_machine_calib.json
.venv/bin/python time_machine.py one --coin ARB --dir 1 --entry-epoch 1792880100 --horizon 16
```

## 1) signal_paper sinyalleri (outputs/signal_paper/signals.csv)
CSV'de girişi olan 32 satır → aynı coin/yön/giriş mumu tekilleştirilince 28 → **21'inin en az bir kapanmış mumu var** (sinyaller çok yeni; gözlenen pencere ortalama **4.5 mum / 16**). `outcomes.csv` (1h sabit ufuk) ile ayrı bir "sabit ufuk" testi de yapıldı (14 sinyal).

| ölçü | değer |
|---|---|
| gerçek hedef vuruşu | 6 (beklenen sıfır-model ≈ 1.95) → p ≈ 0.008 |
| gerçek stop vuruşu | 5 (beklenen ≈ 6.64) → p(≤) ≈ 0.28 |
| coin başına tek sinyal (n=15, bağımlılığı azaltmak için) | hedef 3 vs 1.36 beklenen, p ≈ 0.14; stop 3 vs 4.38 |
| sabit ufuk (1h) ort. brüt | +23 bp; sıfır-model yüzdeliği 0.55 (0.5 = sıfırla aynı), Stouffer z = 0.67 |
| bootstrap ortalama EV (tam ufuk, maliyet sonrası) | −0.15 R |

## 2) Kalibrasyon testi (aracın kendi doğruluğu; OKX, rastgele giriş/yön, 10 coin × 300, n=3000)
Ortalama tahmin p_hedef 0.224 vs gerçek 0.206; p_stop 0.544 vs 0.495 → ortalama düzeyde makul (null biraz cömert/yüksek). Ama bin'lerde: tahmin 0.10→gerçek 0.16, 0.19→0.19, 0.24→0.24, 0.28→0.25, 0.32→**0.20**. **Brier 0.1663, sabit-tahmin referansı 0.1638 → tek tek sinyal için ayrıştırıcılığı YOK** (en yüksek tahmin edilen bin aşırı iyimser; oynaklık kümelenmesi/ATR uyumsuzluğu).

## Dürüst yorum
* Hedef vuruş sayısı sıfır-modelin üstünde (6 vs ~2): "yazı-turadan iyi" yönünde bir ipucu; ama (a) pencere ~4.5 mum, (b) sinyaller zaman olarak yığılmış ve %76'sı long — yani büyük olasılıkla tek bir piyasa yükselişinin farklı coinlerdeki yansıması; bağımsız örnek ≈ 15 coin (hatta daha az) ve bu durumda p ≈ 0.14 (anlamlı değil), (c) CSV büyüdükçe sayılar değişiyor. **İstatistiksel kanıt değil; şu an yetersiz örnek.**
* Stop vuruşu beklentiden az, hedef çok → henüz çözülmeyen sinyallerde sağ-kuyruk yok; 16 mum dolunca yeniden çalıştırılmalı (komut aynı).
* Araç "bu sinyal iyi" demek için değil, "başabaş vuruş oranına (%33–38) karşı şans seviyesi nedir" sorusunu cevaplamak için: coinin kendi volatilitesinde hedefe şans vuruş oranı ≈ %22–28, başabaş ≈ %38 → **sinyalsiz giriş yapısal olarak negatif beklentili (−0.15R)**; bir sinyalin değeri, bu açığı kapatacak kadar hedef vuruşu üretmesidir (R=2'de ≥ ~%38).
* Kalibrasyon, bootstrap'in her sinyali ayırt eden bir tahminci olmadığını gösteriyor; yalnızca toplu bir sıfır-model.
