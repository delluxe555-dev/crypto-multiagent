# grounding.py — sayısal iddia doğrulayıcı (rapor)

Tarih: 2026-10-25 (Europe/Istanbul). Dosya: `grounding.py` (bağımsız modül; trader.py/agents.py/llm.py'ye bağlı DEĞİL; hiçbir sayı üretmez/düzeltmez).

## Ne yapar
LLM çıktısındaki (teknik_analist, duygu_analisti, boğa, ayı, hakem, risk_llm) her sayısal iddiayı, ajana verilen bağlamla (`outputs/*.json` içindeki context + prompt sabitleri) karşılaştırır. Sınıflar:
`eşleşti` (bağlamdaki bir sayı; yuvarlama/kesme toleransı, ×1/×100/×0.01 birim, k/M/bin/milyon son ekleri, TR/EN ondalık biçimi) · `türetilmiş` (bağlamdaki iki sayının fark/oran/%-farkı olarak açıklanabiliyor) · `prompt_sabiti` (%1 risk, 10.000$ gibi komut sabiti) · `doğrulanamadı` · hakem/risk stop-hedef seviyeleri için ayrı `seviye_yakın/seviye_serbest` (karar seviyesi bir veri seviyesine yakın mı).
Tolerans parametreli: `--rel-tol` (varsayılan 0 = yalnızca iddianın son hanesi kadar yuvarlama), `--level-tol 0.003`, `--no-derived`. Tarih/saat, liste numarası ("1."), "3 argüman" gibi küçük sayma sayıları iddia sayılmaz.

## Komutlar
```
cd /workspace/crypto-agents
.venv/bin/python grounding.py --check outputs/BTCUSDT_1h_2026-10-24T1300.json [-v] [--rel-tol 0.005] [--no-derived]
.venv/bin/python grounding.py --scan "outputs/*_1h_*.json" "outputs/*_1d_*.json" --out outputs/grounding_scan.json
.venv/bin/python grounding.py --scan "outputs/*_1h_*.json" "outputs/*_1d_*.json" --null-test --out outputs/grounding_scan_nulltest.json
```

## Geriye dönük ölçüm (varsayılan tolerans)
50 json bulundu; **23 tanesinde bağlam (context) kayıtlı → doğrulandı; 27'si (mtf/scan vb.) bağlam kaydedilmediği için doğrulanamıyor/atlandı.**

| ajan | iddia | doğrulanamadı | oran |
|---|---|---|---|
| teknik_analist | 251 | 3 | %1.2 |
| duygu_analisti | 178 | 3 | %1.7 |
| boğa | 124 | 1 | %0.8 |
| ayı | 164 | 4 | %2.4 |
| hakem | 74 | 1 | %1.4 |
| risk_llm | 149 | 5 | %3.4 |
| **TÜMÜ** | **942** | **18** | **%1.91** |

(eşleşti 900, türetilmiş 22, prompt_sabiti 2; ayrıca 60 seviye_yakın + 9 seviye_serbest hakem/risk stop-hedef seviyesi.) Liste numarası filtresi düzeltmesinden önce 1074 iddia / %1.68 idi: 132 "1." gibi madde numarası gürültüsü payda şişiriyordu; düzeltildi.

18 doğrulanamayan örnek (insan incelemesi gerekir): "$157k short likidasyonu" (×2), BTC "81,200" ve "~38M$" (×2), ETH "2,425", "1.75 ATR", "650$/580$/666$/6360$ pozisyon büyüklüğü" (risk LLM kendi hesabı), "40M$" (×3), BTC 1d "81,500" (×3) ve "stop 416$". Çoğu ya yuvarlama (157k, 38M) ya da LLM'nin kendi türettiği büyüklük; bir kısmı gerçekten bağlamda yok → uydurma olabilir. **Bunların hangisinin uydurma olduğunu otomatik ayırt etmiyorum**, "uydurma kanıtı" demiyorum.

## Null testi (doğrulayıcı gerçekten yanlış sayıyı yakalıyor mu?)
Her iddia %3–15 rastgele kaydırılınca (yanlış sayı simülasyonu) doğrulayıcı **%39.8'ini "doğrulanamadı" olarak işaretledi** (tesadüfi eşleşme / türetilmiş tablonun cömertliği payı ≈ %60). Yani yakalama gücü ≈ %40; bağlamda çok sayı olduğu için yanlış bir sayı çoğu zaman başka bir sayıya rastlayıp geçiyor.

## Dürüst yorum
* Gözlenen %1.9, **alt sınırdır**. Yakalama gücü ~%40 ise gerçek hatalı-sayı oranı kabaca birkaç %'ye (≈ %4–5'e kadar) çıkabilir; öte yandan 18'in bir kısmı yalnızca yuvarlama/LLM'nin kendi aritmetiği olduğundan gerçek oran daha düşük de olabilir. Aralık: "≈ %0–5", tek bir sayı değil.
* Sonuç: ajanlar **çoğunlukla bağlamdaki sayıları aktarıyor**; yaygın bir sayı uydurma sinyali yok. Ama bu "uydurma yok" kanıtı değil.
* En zayıf yer: risk_llm (%3.4) — pozisyon büyüklüğü ($) hesapları; bunlar zaten risk_rules.py ile yeniden hesaplanıyor.
* mtf/scan çıktılarında context kaydı yok → doğrulanamıyor. **Öneri:** trader.py'nin her çıktıya context'i (sayısal özet) kaydetmesi (ben dokunmadım).
* Pencere dışı "tarih/saat" ve küçük tamsayıların filtrelenmesi bazı gerçek iddiaları dışarıda bırakabilir.
