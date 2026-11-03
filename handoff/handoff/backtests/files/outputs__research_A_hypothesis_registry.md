# Adım A — Hipotez kaydı + run card (2026-10-25, UTC+3)
Dosyalar: `hypotheses.py` (kayıt: `outputs/research/hypotheses.json`), `run_card.py` (kartlar: `outputs/research/run_cards/`), `research_backfill.py` (geriye dönük doldurma; bir kez çalıştırıldı).
Kullanım: `python3 hypotheses.py list|summary|add|state|trials`. Durumlar: exploring/testing/validated/rejected/monitoring/(+inconclusive). Kaynak fikir: QuantDinger (Apache-2.0) hipotez/trial yaklaşımı; kod sıfırdan.

## Toplam denenen yapılandırma sayısı
**≈ 1055 (yaklaşık; ±%10)** — 17 kayıt. Aile bazında:
- combo-ta: 665 (kesin) (4 kayıt)
- liq-cluster: 162 (yaklaşık) (4 kayıt)
- confluence: 32 (kesin) (2 kayıt)
- ema: 150 (yaklaşık) (1 kayıt)
- risk-mgmt: 32 (kesin) (2 kayıt)
- llm-agent: 2 (yaklaşık) (2 kayıt)
- ml-forecast: 12 (kesin) (2 kayıt)

- **combo-ta = 665 kesin**: R2 = 6 zaman-çifti × 3 stop/hedef × 35 kombinasyon = 630 (bazlar dahil; 558 baz-dışı) + R1'in R2'de olmayan 5m/1h hücreleri 35 (R1 ham 105 hücre; 70'i R2'de yeniden test edildi). Bu sayı DSR için birincil N.
- liq-cluster ~162: dokunma testi ~120 (yaklaşık: 5 mesafe×2 yön×3 ufuk×4 yaş katmanı) + radar sinyalleri 42 satır (kesin).
- ema ~150 (özet tablodaki satır sayısı), confluence 32, risk-mgmt 32 (küçük örnek), ml-forecast 12 (kronos sanity 4 + tam test 8), llm-agent ~2.
- Aileler aynı veriyi/dönemi paylaşmıyor (Binance 150g vs Gate 17-21g); toplam N "bütün arama" üst sınırı; DSR'de duyarlılık için N=630/665/~850/~1055 kullanılır.
- Durumlar: testing=4, rejected=3, monitoring=5, inconclusive=5

## Notlar
- Her kayıtta: veri kaynağı, dönem, maliyet, rapor yolu, durum geçmişi. Her yeni tarama ÖNCE `H.add_trials(...)` ile sayılmalı.
- Run card'lar otomatik uyarı üretir (kısa/tek rejim, az işlem, çok deneme, düşük maliyet, OOS yok). 10 geriye dönük kart yazıldı (`*_backfill_*`).
- Sınırlama: geçmiş sayıları rapor/çıktılardan sayıldı; kod içinde sessizce denenip raporlanmayan ara denemeler (elle parametre oynamaları) sayılamaz → gerçek N muhtemelen **daha yüksek**.
