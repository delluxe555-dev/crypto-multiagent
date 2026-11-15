# Günlük RSI(14) — "15-16 bandı dönüş mü?" testi

Soru: günlük RSI 15–16'ya indiğinde tarihsel olarak dönüş mü olmuş?

Cevap: **Hayır.** 2026'daki iki örnek tesadüf; 2018'de aynı bant üç kez üst üste
"dönüş" dedi ve fiyat %32 daha düştü.

## Veri

AlertaChart `get_candles`, Binance spot günlük mumlar:

| sembol | bar | aralık |
|---|---|---|
| BTCUSDT | 3.000 | 2018-08-25 → 2026-11-15 |
| ETHUSDT | 3.000 | 2018-08-25 → 2026-11-15 |
| SOLUSDT | 2.283 | 2020-08-11 → 2026-11-15 |

RSI: Wilder(14). Olay = banda **giriş** (küme başı, arada >10 gün varsa ayrı olay).
Getiri, olay gününün kapanışından ölçülür. `dd10` = sonraki 10 günde en düşük kapanış.
`dip_tuttu` = sonraki 20 günde olay gününün dibinin altına inilmedi mi.

## 1) Bant 13,5–17,5 — tüm olaylar

**BTC, n=6**

| tarih | RSI | kapanış | +3g | +5g | +10g | +20g | dd10 | dip tuttu |
|---|---|---|---|---|---|---|---|---|
| 2018-11-21 | 15,2 | 4.661 | −15,6 | −17,1 | −10,1 | **−27,5** | −21,6 | ✗ |
| 2018-11-23 | 15,2 | 4.421 | −12,6 | −3,5 | −12,1 | **−25,3** | −17,4 | ✗ |
| 2018-11-26 | 16,2 | 3.862 | +11,2 | +8,5 | −9,2 | **−16,4** | −9,4 | ✗ |
| 2020-03-12 | 15,0 | 4.800 | +11,7 | +10,7 | +21,2 | +38,4 | **−21,2** | ✗ |
| 2026-02-05 | 16,8 | 62.910 | +11,5 | +6,6 | +9,5 | +7,3 | −4,6 | ✗ |
| 2026-06-05 | 15,6 | 61.056 | +3,3 | +0,7 | +8,6 | −2,1 | −2,6 | ✗ |

özet: +10g **+1,32%** (kazanma %50) · +20g **−4,27%** (kazanma %33) · dd10 −12,8% · dip tuttu **%0**
taban (herhangi bir gün): +10g +1,34% · +20g +2,82%

**ETH, n=2** — ikisi de 2018-11:

| tarih | RSI | kapanış | +10g | +20g | dd10 |
|---|---|---|---|---|---|
| 2018-11-20 | 17,2 | 133,8 | −15,0 | **−32,8** | −23,5 |
| 2018-11-24 | 16,4 | 114,9 | −4,3 | **−27,0** | −10,9 |

özet: +10g **−9,66%** (kazanma %0) · +20g **−29,92%** (kazanma %0) · dip tuttu %0

**SOL, n=2** — 2026-06-05 (+10g +16,3) ve 2026-11-14 (henüz açık)

### Birleşik (BTC+ETH, n=8)

| | bant 13,5–17,5 | taban |
|---|---|---|
| +10g ortalama | **−1,43%** | +1,4% |
| +20g ortalama | **−10,68%** | +3,0% |
| 10g kazanma | %37,5 | ~%55 |
| 20g kazanma | %25 | ~%55 |
| 20g içinde dip kırıldı | **8/8** | — |

**2018 kanıtı belirleyici:** 21–26 Kasım arası üç kez bant tetiklendi (4.661 → 4.421 → 3.862).
Fiyat 15 Aralık'ta 3.122'de durdu, yani ilk tetikten **−%33**. O dibin günlük RSI'ı
**25'in üstündeydi** — yani dip, RSI bandın içindeyken değil, banttan çıktıktan sonra oluştu.

## 2) RSI < 20 ve RSI < 25

| | n | +10g | 10g kazanma | +20g | 20g kazanma | dd10 |
|---|---|---|---|---|---|---|
| BTC <20 | 8 | −2,20% | %57 | −3,20% | %43 | −12,9% |
| ETH <20 | 8 | +1,49% | %43 | −3,91% | %43 | −11,5% |
| BTC <25 | 23 | +1,60% | %55 | +3,21% | %50 | −11,1% |
| ETH <25 | 18 | +2,47% | %53 | +10,05% | %53 | −13,0% |
| SOL <25 | 11 | +9,76% | %70 | +16,83% | %60 | −13,0% |

`<20` tabandan **kötü** (BTC +10g −2,2 vs taban +1,3). ETH `<25` ortalaması yüksek
görünüyor ama iki uç olaydan geliyor (2018-12 +76%, +53%); medyan değil, kuyruk.
Her üçünde de ortalama 10 gün içinde **%11–13** düşüş var.

`RSI 20–25` bandı (BTC n=25): +10g −0,26%, +20g −0,42% → tabanın altında.

## 3) Peki asıl diplerde RSI kaçtı?

60 gün geriye / 20 gün ileriye göre "büyük dip" olarak işaretlenen 24 dip:

| sembol | dipteki günlük RSI (son 8 dip) | <20 olan |
|---|---|---|
| BTC | 30,4 · 26,7 · 34,7 · 32,1 · 33,9 · 22,8 · **16,8** · 30,3 | 1/8 |
| ETH | 37,8 · 21,1 · 31,5 · 24,8 · 34,0 · 27,7 · **19,5** · 30,5 | 1/8 |
| SOL | 38,8 · 37,1 · 32,3 · 33,2 · 31,8 · 33,0 · 32,2 · **15,7** | 1/8 |

**Dibin tipik RSI'ı 30 civarı.** RSI 15–16 bir dip işareti değil, **panik işareti**:
dip genellikle 2–6 hafta sonra, RSI 30'a dönmüşken (yükselen dip = pozitif uyumsuzluk)
oluşuyor. Bantın 8/8'inde dibin kırılması bunun kanıtı.

## 4) "RSI 30'u yukarı kesince al" testi

| | n | +10g | 10g kazanma | +20g | 20g kazanma |
|---|---|---|---|---|---|
| BTC RSI>30 kesişi | 33 | −1,16% | %36 | +2,31% | %42 |
| BTC RSI>25 kesişi | 22 | +0,11% | %41 | +3,03% | %43 |
| ETH RSI>30 kesişi | 28 | −1,61% | %43 | −0,38% | %46 |
| SOL RSI>30 kesişi | 26 | +3,84% | %44 | +12,18% | %43 |

Onay (kesişim) da tabanı geçmiyor. Yani **günlük RSI'ın hiçbir seviyesi/kesişimi tek
başına giriş sinyali değil** — ne düşük seviye, ne dönüş onayı.

## Sonuç

1. "RSI 15–16 = dönüş" **2026'ya özgü** iki olaydan türetilmiş bir yanılsama.
2. Aynı bant 2018 ayısında 3 kez tetiklendi, ardından −%33 geldi. ETH'te 2/2 olay −%27/−%33.
3. Bantın 8/8 olayında dip önce kırıldı → seviye olarak kullanılamaz (SL önce vurulur).
4. Gerçek diplerin RSI'ı ~30; RSI 15–16 dibi değil, satışın şiddetini gösteriyor.
5. Onay kesişimleri de tabanın altında → günlük RSI tek başına edge değil.

Kullanılabilir tek şey: RSI 15–16 **panik göstergesi** olarak "dip yakınız ama henüz değil"
bilgisi. Bot tarafında günlük RSI hiç kullanılmıyor (`a_technical` 1h/4h RSI), bu yüzden
değiştirilecek bir şey yok.

Not: "büyük dip + yükselen RSI uyumsuzluğu" testi bu dosyada yok — o test 20 günlük ileri
bakışla tanımlandığı için sonuçları tradable değil (lookahead). Düzgün testi, uyumsuzluk
sonrası önceki swing high'ın kapanışla geçilmesini bekleyen bir kurulumla yapılmalı.
