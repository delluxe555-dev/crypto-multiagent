# Devre kesici: art arda 4 zarar → 2 saat yeni giriş yok

2026-11-15/16 testeresinde kasa −553 USDT yazdı (11-15: −445,65 · 11-16: −107,86).
Bu dosya, o kaybı durdurmak için seçilen kuralın ölçümünü ve reddedilen
alternatifleri kaydeder.

## Kural

```
son 4 kapanan pozisyonun R'si < 0 ise
    4. kapanıştan itibaren 2 saat yeni giriş açılmaz
kazanç (R >= 0) sayacı sıfırlar
```

- Kapanış sırasına göre oynatılır; açık pozisyonlar sayılmaz.
- Duraklama Telegram'a sinyal göndermeyi de kapsar (`check()` içinde
  `_evaluate`'den önce), yani sadece pozisyon değil mesaj da gitmez.
- Duraklama sırasında sinyal "done" işaretlenmez: süre bitince hâlâ geçerliyse
  giriş açılabilir.
- Kod: `tools/trigger_watch.py` → `_loss_pause()`, `check()`.
  Env: `TG_LOSS_STREAK_N` (varsayılan 4), `TG_LOSS_PAUSE_H` (varsayılan 2).
  Kapatmak için `TG_LOSS_STREAK_N=0`.

## Ölçüm (120 işlem, 2026-11-10 → 11-16)

| Gün | Gerçek | Kural olsaydı | Engellenen | Fark |
|---|---|---|---|---|
| 11-10 | −10,17 | −0,32 | 2 | +9,85 |
| 11-11 | +15,35 | +89,66 | 7 | +74,32 |
| 11-12 | +237,13 | +237,13 | 0 | 0 |
| 11-13 | +315,37 | +315,37 | 0 | 0 |
| 11-14 | +337,69 | +337,69 | 0 | 0 |
| 11-15 | −404,67 | **−118,21** | 21 | **+286,46** |
| 11-16 | −148,84 | **−78,87** | 11 | +69,97 |
| **Toplam** | **+341,86** | **+782,45** | 41 | **+440,59** |

Kritik: trend günlerine (11-12/13/14) **hiç dokunmuyor**, yalnız testere
günlerinde devreye giriyor. Kural, canlı paper geçmişi üzerinde koddaki
`_loss_pause()` mantığıyla replay edildiğinde aynı sonucu veriyor
(+782,45 / +341,86).

## Reddedilen alternatifler

| Aday | Sonuç | Neden reddedildi |
|---|---|---|
| Aynı yönde 3+ pozisyon (6 saat) | 115/120 işlem engellenir, +375 | Filtre değil kapatma düğmesi; 11-14'ün +337'si de giderdi |
| Aynı anda max 6 açık | 46 işlem engellenir, **−89** | Net zarar |
| Aynı anda max 8 açık | 26 işlem engellenir, **−37** | Net zarar; konsantrasyon kazananı ayırmıyor |
| Aynı anda max 10 açık | 16 işlem engellenir, **−18** | Net zarar |
| 3 ardisik zarar → 4 saat | +612 toplam | 11-13 trend gününün ortasında duraklatıp **−217** yazdırdı |
| 4h SMA50'ye %8+ uzaksa short yok | 53 işlem kalır, +470,79 | +129 tek başına; devre kesiciyle birlikte +223 (daha kötü, 11-16 toparlanmasını kaçırıyor) |

Devre kesici 9 varyant arasından seçildi; 120 işlem / 6 gün / tek rejim
olduğu için şans payı var. Mekanizma yine de sağlam: üst üste 4 stop,
piyasanın o yönde çalışmadığının en basit kanıtı.

## 4h trend kapısı (`meta_gate`) neden bu işi yapmıyor

`tools/engine.py:1060` → 4h SMA50/SMA200 dizilimi + fiyatın SMA50 tarafı.
11-13 → 11-16 arası 2.493 kararda:

| Aday | Kapının geçirdiği | Kapının engellediği |
|---|---|---|
| BUY | n=81 · 12h −1,63% · kazanma %20 | n=453 · −1,64% · %21 |
| SELL | n=1.797 · +1,45% · %61 | n=162 · +1,77% · %72 |

- 120 işlemin **118'ini geçirmiş**; engellediği 2 işlem kârdaymış (+11,94).
- Sebep: 4h'de tüm coinler düşüş trendinde, "SELL serbest" koşulu her an sağlanıyor.
  MA'lar trendin bittiğini günler içinde göremez — yön filtresi, zamanlama değil.
- Tamamen kaldırmak long sinyalini ~6 katına çıkarır (12h kazanma %20), bu yüzden
  BUY tarafı kalıyor; SELL tarafının kaldırılması ayrı bir karar.

## Engellenen shortların gerekçesi (11-13 → 11-16, yalnız meta veto)

| Sembol | Karar | SMA50>SMA200 | Fiyat SMA50 üstü | MA50-MA200 farkı | 12h yön |
|---|---|---|---|---|---|
| 1000PEPEUSDT.P | 78 | 78 | 0 | +5,5% | +2,63% |
| INJUSDT.P | 47 | 43 | 1 | +0,7% | +0,20% |
| FETUSDT.P | 18 | 0 | 7 | −20,1% | +1,84% |
| AVAXUSDT.P | 8 | 0 | 2 | −8,5% | +3,13% |
| XLMUSDT.P | 2 | 0 | 0 | −13,6% | +1,58% |

Yani shortların çoğu "4h trend yukarı dönmüş" diye değil, **1000PEPE ve INJ'de
MA50 hâlâ MA200 üstünde** olduğu için engellendi. 12h yönleri pozitif olsa da
botun ~1 ATR SL'si o yöne gitmeden önce vuruluyor (11-15'in asıl sorunu).
