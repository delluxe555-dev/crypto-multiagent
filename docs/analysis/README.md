# Eğim / ivme ölçümü (giriş anı)

Kağıt işlem girişlerinde **trendin hızı** ve **hızın değişimi**. Karar/veto/oy değil,
sadece ölçüm — sinyal üretimine etkisi sıfır.

## Neden burada

`runs/live/decision_*.json` 36 saatte siliniyor, `runs/archive/` ise 180 gün tutuyor ama
bu alanlar deploy öncesi kararlarda yok. Bu dosya **geçmişi** kalıcı yapıyor: 2026-11-10 →
2026-11-14 arası 75 kağıt işlemin giriş anındaki eğim/ivme değerleri, sonradan mumlardan
geri hesaplanmış hâliyle.

## Yöntem

Sembolün kendi **1h** mumları, EMA21 ve ATR(14, Wilder):

```
align12 = yön * (EMA21[son] - EMA21[son-12]) / ATR * (24/12)     # ATR/gün
align48 = yön * (EMA21[son] - EMA21[son-48]) / ATR * (24/48)     # ATR/gün
accel   = align12 - align48        # + dikleşiyor, − yataylıyor
ext     = yön * (giriş - EMA21) / ATR                            # + EMA ötesi (kovalama)
```

`yön` = SHORT için −1, LONG için +1. Yani pozitif değer **işlemin lehine**.

## Alanlar

| alan | anlam |
|---|---|
| `at` | giriş zamanı (UTC) |
| `sym` | sembol (`.P` = Binance USDT perpetual) |
| `side` | SHORT / LONG / SELL / BUY (kayıttaki hâli) |
| `entry` | gerçek dolum fiyatı |
| `R` | sonuç, risk birimi (TP2 ≈ +1,5…2,9 · gerçek SL ≈ −1 · BE ≈ +0,5…0,9) |
| `ev` | `tp2` / `sl` / `be` / `reversed` / `timeout` |
| `align12`, `align48`, `accel`, `ext` | yukarıdaki formüller |

## Bulgular (75 işlem, 2026-11-10…14)

| accel | n | kazanma | toplam R | PF |
|---|---|---|---|---|
| frenliyor (< −1) | 21 | %100 | +34,19 | — |
| sabit (−1…+1) | 35 | %74,3 | +31,85 | 4,31 |
| hızlanıyor (> +1) | 19 | %47,4 | +5,31 | 1,48 |

| align12 | n | kazanma | PF |
|---|---|---|---|
| ters (< 0) | 23 | %100 | — |
| zayıf hizalı (0…2) | 26 | %76,9 | 4,89 |
| güçlü hizalı (> 2) | 26 | %50,0 | 1,72 |

**Yorum:** trend hızlanırken girilen işlemler zayıf, trend nefes alırken girilenler güçlü.
11-11 gecesinin −10R'lik SL batch'i (DOGE 22:30, HYPE 01:00, BTC 02:00, UNI/ADA/XLM 02:15)
tam olarak "hızlanıyor" kovasında.

**Uyarı:** `accel` ile `ext` (EMA'ya uzaklık) korelasyonu **0,71** — büyük ölçüde aynı
"kovalama" olgusunun farklı görünümü. Tek başına `ext` ayırmıyor (%74 / %74), ayrım
"hizalı **ve** EMA ötesi" kombinasyonunda çıkıyor (%63, PF 2,7). 75 işlem tek rejim
(tek yönlü çöküş); %100'lük kovalar 21–23 işlem. Filtre olarak kullanılmamalı.

## Kalıcı hâle gelmesi

Kod tarafı (deploy sonrası, her kararda otomatik):

- `tools/engine.py` → `slope_metrics(d1h)` + `dec["slope"]`
- `tools/archive.py` → `compact()` içinde `"slope": dec.get("slope")`
  → `runs/archive/decisions/YYYY-MM-DD.jsonl` satırlarında kalıcı (180 gün)

Deploy'a kadar bu dosya tek kaynak. Yeni işlemler geldikçe elle eklenebilir:
kağıt işlem geçmişi (`/debug/paper`) + AlertaChart 1h mumları yeterli.
