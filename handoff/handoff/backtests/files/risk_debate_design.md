# risk_debate.py — agresif / muhafazakâr / nötr risk görüşü (tasarım notu + ölçüm)

Tarih: 2026-10-25 (Europe/Istanbul). **Canlıya bağlı DEĞİL.** `risk_rules.py`, `trader.py`, `config.json` değiştirilmedi; dosya yalnızca bir `outputs/*.json` okur ve ayrı bir çıktı yazar.

## Fikir (TradingAgents'tan esinlenen, kendi yazdığım küçük prototip)
Mevcut hat: teknik → duygu → boğa → ayı → hakem → risk (6 LLM çağrısı / 1h-1d analizi). Buna son adımda üç risk duruşu eklenir: AGRESİF, MUHAFAZAKÂR, NÖTR; her biri `{onay, size_mult(0–1), stop_atr_mult, gerekce}` döndürür.
**Güvenlik tasarımı (kritik):**
* Kural-tabanlı pozisyon (`risk_rules.size` sonucu) her zaman ÜST SINIR. LLM `size_mult` ≤ 1 ile yalnızca KÜÇÜLTEBİLİR veya VETO edebilir; büyütemez.
* Stop kural-tabanlı kalır (LLM'in `stop_atr_mult` önerisi yalnızca raporlanır, uygulanmaz → stop genişletilemez).
* Birleştirme deterministik: onay = çoğunluk (≥2/3), size_mult = üç görüşün medyanı; parse edilemeyen görüş oya katılmaz; hiçbir görüş parse edilemezse sonuç VETO (size 0) — yani LLM arızasında fail-safe 'işlem yok' (kural-tabanlı büyüklüğe geri dönmez; canlıya bağlanırsa bu karar ayrıca verilmeli). Manager modunda yönetici çıktısı yalnızca daha da küçültebilir (min) ya da veto edebilir.
* Çıktıdaki sayısal iddialar `grounding.py` ile kontrol edilir (çıktıya `grounding` alanı eklenir).

## Modlar ve LLM çağrı sayısı
| mod | ek çağrı | mevcut 6'ya göre | not |
|---|---|---|---|
| `single` | 1 | +%17 | tek istemde üç kişilik JSON — **önerilen** |
| `three` | 3 | +%50 | üç ayrı çağrı |
| `manager` | 4 | +%67 | üç görüş + "risk yöneticisi" sentezi (TradingAgents'a en yakın) |

## Gerçek koşu ölçümleri (INITUSDT 1h 2026-10-24T0600 çıktısı üzerinde, `gemini/gemini-3.1-flash-lite`)
| mod | çağrı | süre | ~token (in/out) | grounding |
|---|---|---|---|---|
| single | 1 | 6.4 s | ~1 422 / ~270 | 16 iddia, 0 doğrulanamadı |
| manager | 4 | 28.1 s | ~5 940 / ~393 | 21 iddia, 0 doğrulanamadı |

(token = karakter/3.2 yaklaşımı; sağlayıcı sayacı değil.) `three` modunu gerçek koşmadım (single ve manager arası; ~3 çağrı ≈ 20 s beklenir); `--dry` ile boru hattı testi yapıldı (sonuç sayılmaz).
Ham çıktılar: `outputs/risk_debate_runs/init_single.json|log`, `init_manager.json|log`.

Örnek: kural pozisyonu 1471.28$; single → AGRESİF onay 1.0 / MUHAFAZAKÂR veto 0.3 / NÖTR onay 0.6 → birleşik onay, size_mult 0.6 → 882.77$. manager → 0.7 → 1029.9$. **İki mod aynı girdide farklı boyut verdi (0.6 vs 0.7)** — LLM görüşleri koşudan koşuya oynak; tek koşudan "daha iyi karar" sonucu çıkarılamaz.

## Free kota etkisi
* Bu gün `gemini-3-flash-preview` günlük kotası canlı trader tarafından zaten tükenmişti; koşular `gemini-3.1-flash-lite`'a düştü (llm.py zinciri). OpenRouter free ≈ 50 istek/gün.
* Her ek çağrı aynı kotadan yer. Her analizde `single` = +1, `manager` = +4 çağrı. Saatlik tarama çok coin kapsıyorsa `manager` kotayı hızla bitirir. Öneri: yalnızca hakem "AL/SAT" dediği (geçidi geçen) adaylarda, `single` modu → fiilen günde birkaç ek çağrı.
* Kazanç iddiası YOK: bu prototip pozisyonu küçülttüğü için kâğıt sonuçları ancak yeterli örnekle (signal_paper outcomes) ölçülebilir; şu an bu örnek yok. Yani "risk görüşü getiriyi artırır" doğrulanmadı; yalnızca "boru hattı çalışıyor, maliyeti şu" denebilir.

## Çalışmayanlar / sınırlar
* Gerçek üç koşunun ayrı çağrı modunu (three) ölçmedim.
* Kota zaten kısıtlıyken gerçek bir A/B (canlı paper'da risk_debate açık/kapalı) kurulmadı — canlıya dokunmama kuralı.
* LLM görüşleri veriye dayanıyor ama "muhafazakâr" persona'nın veto'su veri-dışı gerekçelerle gelebilir; grounding yalnızca sayıları kontrol eder, mantığı değil.

Kullanım: `.venv/bin/python risk_debate.py outputs/INITUSDT_1h_2026-10-24T0600.json --mode single [--dry] --out x.json`
