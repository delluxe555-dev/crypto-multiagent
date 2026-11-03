"""overfit_report.py - overfit_null.json / overfit_real.json / overfit_worlds.json -> outputs/research_B_overfit_stats.md (overfit_stats.py report)."""
import json, os, math, numpy as np
import overfit_stats as O
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f"{HERE}/outputs/research"
def pct(x): return f"{x*100:.1f}%"
def main():
    L = []; P = L.append; nul = json.load(open(f"{RES}/overfit_null.json")); real = json.load(open(f"{RES}/overfit_real.json")); W = json.load(open(f"{RES}/overfit_worlds.json")) if os.path.exists(f"{RES}/overfit_worlds.json") else []
    P("# Adım B — aşırı-uyum (overfitting) istatistikleri (2026-10-25, UTC+3)\n")
    P("Kod: `overfit_stats.py` (+ `overfit_report.py`), girdi `outputs/research/trades_r2.npz` (combo_bt2 işlemleri birebir yeniden üretildi). Fikir: QuantDinger `strategy_evolution/statistics.py` (Apache-2.0) — DSR, PBO, blok bootstrap; **kod sıfırdan**, scipy yok (`statistics.NormalDist`).")
    P("Hücre = (zaman-çifti, stop/hedef, kombinasyon) = 630; günlük seri = hücrenin tüm coinlerinin çıkış gününe göre net-R toplamı (148 gün). N (deneme sayısı) = 665 (A adımı; duyarlılık 5/20/630/850/1055).\n")
    P("## 1) Test çalışıyor mu? Sentetik RASTGELE veride yanlış-pozitif oranı (N=630 sıfır-ortalamalı strateji, T=150 gün)")
    P("En iyi stratejiyi seçip test ediyoruz — tam olarak gerçek aramanın yaptığı şey.\n")
    P("| senaryo | 'naif' t>1.96 (en iyi strateji) | PSR(N=1)>0.95 | **DSR(N=630)>0.95** | PBO ort. ± sd | IS-en-iyinin OOS Sharpe'ı | güç: gerçek günlük SR 0.2 → DSR>0.95 | güç: SR 0.3 |\n|---|---|---|---|---|---|---|---|")
    for k, lab in (("rho0.0_normal", "bağımsız, normal"), ("rho0.3_normal", "ortak faktör ρ=0,3, normal"), ("rho0.3_t4", "ρ=0,3, kalın kuyruk (t4)"), ("rho_real_run", f"ρ={nul.get('rho_real',0):.2f} (gerçek hücre korelasyonu)")):
        v = nul[k]; pw = v["power_by_true_daily_SR"]; P(f"| {lab} | {pct(v['null_naive_t_gt_1.96_share_of_best'])} | {pct(v['null_PSR_N1_gt_0.95'])} | **{pct(v['null_DSR_N_gt_0.95'])}** | {v['null_PBO_mean']:.2f} ± {v['null_PBO_sd']:.2f} | {v['null_oos_SR_of_IS_best_mean']:+.3f} (IS: {v['null_is_SR_of_IS_best_mean']:+.2f}) | {pct(pw['0.2']['dsr'])} | {pct(pw['0.3']['dsr'])} |")
    P("\nYorum: (i) 630 hücreden en iyiyi seçip düz t-testi uygulamak %84-100 oranında 'anlamlı' sonuç üretir — yani **saf gürültüde bile**. (ii) DSR bunu %1'in altına indirir (yanlış-pozitif ≈ %0,5-0,9; nominal %5'in altında → tutucu). (iii) PBO null'da ≈0,5 (beklenen), IS'de seçilen stratejinin OOS Sharpe'ı ≈0 (seçim yanlılığı tam olarak IS'e özgü). (iv) **Güç düşük**: T=150 günle, gerçek günlük SR 0,2 (yıllık ≈3,8!) olan bir stratejiyi bile DSR yalnızca ~%2-4 ihtimalle onaylar; SR 0,3'te ~%13-26. Yani DSR 'reddedemedi' demek 'edge yok' kanıtı değil, 'bu veriyle ayırt edilemez' demektir.\n")
    # worlds
    if W:
        P(f"## 2) Uçtan uca sentetik 'dünyalar' (gerçek motor): {len(W)} dünya")
        P("Her dünyada 29 coinin gerçek 5m serisi **gün bloklarına bölünüp karıştırıldı** (tüm coinlerde aynı gün permütasyonu → coinler arası korelasyon ve gün-içi yapı korunur; günler arası trend/otokorelasyon yok edilir; ⇒ gerçek avantaj yok). Sonra gerçek combo_bt2 motoru (630 hücre, aynı maliyet) + aynı testler. Bu, 'gerçekte avantaj olmayan bir piyasada 630 hücre aramasında ne bulunur' sorusunun cevabı.\n")
        f = lambda key, k: np.array([w[key][k] for w in W], dtype=float)
        for ck, lab in (("cost0.05pct", "taraf başı %0,05"), ("cost0.15pct", "taraf başı %0,15")):
            nb = f(ck, "n_pos_both_halves"); npm = f(ck, "n_pos_mean"); bm = f(ck, "best_meanR"); ci = np.array([w[ck]["best_ci"] for w in W]); cib = np.array([w[ck]["best_ci_blk"] for w in W]); dsr_ = f(ck, "best_DSR_N665"); rc = f(ck, "rc_p"); rcb = f(ck, "rc_p_blk"); pbo = f(ck, "pbo_nonbase")
            P(f"**{lab}**: iki yarıda net-pozitif hücre sayısı medyan {np.median(nb):.0f} (min {nb.min():.0f}, maks {nb.max():.0f}); ortalaması >0 hücre medyan {np.median(npm):.0f} (maks {npm.max():.0f}); en iyi hücre ort. net R medyan {np.median(bm):+.3f} (maks {bm.max():+.3f}).")
            P(f"- 'Naif' sahte keşif: en iyi hücrenin coin×3g-blok %95 CI'si 0'ı dışarıda bırakıyor: {int((ci[:,0]>0).sum())}/{len(W)} dünya; gün-blok (tüm coinler) CI'si ile: {int((cib[:,0]>0).sum())}/{len(W)}.")
            P(f"- Reality-Check p<0,05: coin×blok bootstrap ile {int((rc<0.05).sum())}/{len(W)}; gün-blok ile {int((rcb<0.05).sum())}/{len(W)}. DSR(N=665)>0,95: {int((dsr_>0.95).sum())}/{len(W)}. PBO medyan {np.median(pbo):.2f} (aralık {pbo.min():.2f}-{pbo.max():.2f}).")
        P("\nGerçek veri ile kıyas (aynı maliyet): @0,05 iki yarıda pozitif **3**, ortalaması >0 **17**, en iyi hücre **+0,059R**. Sentetik dünyalarda bunlara eşit/aşan oran: ")
        a = f("cost0.05pct", "n_pos_both_halves"); b = f("cost0.05pct", "n_pos_mean"); c = f("cost0.05pct", "best_meanR")
        P(f"- iki yarıda pozitif ≥3: {int((a>=3).sum())}/{len(W)} dünya; ortalaması >0 ≥17: {int((b>=17).sum())}/{len(W)}; en iyi ≥+0,059R: {int((c>=0.0587).sum())}/{len(W)}.")
        P("Yorum: gerçek veri, rastgele-karıştırılmış dünyaların medyanından ayırt edilemiyor (hepsi ~yarı yarıya). 'Naif' coin×blok CI ile sahte keşif oranı çok yüksek; çünkü 29 coin aynı günlerde birlikte hareket ediyor, coin×blok bootstrap bağımsız birim sayısını şişirip CI'yi daraltıyor (Reality-Check'te de nominal %5 yerine 3/24 ≈ %12 yanlış-pozitif — küçük örnek, ama yön net). **Gün-blok (tüm coinler birlikte) bootstrap daha dürüst** ve gerçek veriye de bu uygulandığında CI'ler sıfırı kapsıyor. Uyarı: 24 dünya = kaba kalibrasyon; yüzde değerleri ±~%10 belirsiz.")
        P("(PBO notu: tüm hücreler maliyet yüzünden net-negatifken sıralama kalıcıdır — 'az kaybeden' IS'te de OOS'ta da az kaybeder — bu yüzden gürültü dünyasında PBO düşük çıkabilir; PBO bu yapıda 'edge var' kanıtı değildir. OOS kayıp olasılığı ve RC/DSR daha bilgilendirici.)\n")
    # real
    P("## 3) Gerçek combo_bt2 verisi\n")
    T = O.load_trades(); nb_ = np.array([not T["combos"][c % 35].startswith("BASE_") for c in range(630)]); M, _, nd = O.daily_matrix(T, O.net_r(T, 0.0005)); Cm = np.corrcoef(M[nb_ & (M.std(1) > 0)]); ev = np.linalg.eigvalsh(Cm); neff = ev.sum() ** 2 / (ev ** 2).sum()
    P(f"Hücreler birbirine çok benzer (aynı sinyal farklı HTF'de özdeş işlem verebiliyor; ortalama çift korelasyonu {(Cm.sum()-len(Cm))/(len(Cm)**2-len(Cm)):.2f}); özdeğer 'katılım oranı' ile etkin bağımsız deneme sayısı ≈ **{neff:.0f}** (altına inmek DSR'yi gevşetir; tabloda N=5 ve 20 duyarlılığı var).\n")
    for ck, lab in (("cost0.05pct", "taraf başı %0,05"), ("cost0.15pct", "taraf başı %0,15")):
        a = real[ck]; P(f"### {lab}\n- İki yarıda net-pozitif hücre: **{a['n_pos_both_halves']}**; ortalaması >0: {a['n_pos_mean']}/{a['n_cells_nonbase']}. SR0 (N=665 deneme sonrası beklenen en iyi günlük SR) = {a['SR0_by_N']['665']:.3f}; gözlenen en iyi günlük SR bundan çok küçük.")
        P(f"- Reality-Check (max-t) p: coin×blok **{a['reality_check']['p']:.3f}**, gün-blok **{a['reality_check_blk']['p']:.3f}** (H0: hiçbir hücrenin ortalaması >0 değil). PBO(558 hücre) = {a['pbo_nonbase558']['pbo']:.2f}; IS-en-iyinin OOS-kayıp olasılığı {a['pbo_nonbase558']['p_oos_loss']:.2f}; ort. OOS Sharpe {a['pbo_nonbase558']['mean_oos_sr_selected']:+.3f} (IS {a['pbo_nonbase558']['mean_is_sr_selected']:+.3f}).\n")
        P("| hücre | n | ort. net R/işlem | CI coin×3g | CI gün-blok | günlük SR (yıllık) | PSR | DSR N=5 / 20 / 665 / 1055 | IS / OOS R | başabaş maliyet %/taraf |\n|---|---|---|---|---|---|---|---|---|---|")
        for t in a["top"][:8]:
            d = t["DSR"]; P(f"| {t['name'].replace(' | ',' ; ')} | {t['n']} | {t['mean_R']:+.4f} | [{t['ci_cb'][0]:+.3f},{t['ci_cb'][1]:+.3f}] | [{t['ci_blk'][0]:+.3f},{t['ci_blk'][1]:+.3f}] | {t['daily_SR']:+.3f} ({t['SR_ann']:+.1f}) | {t['PSR']:.2f} | {d['5']:.2f} / {d['20']:.2f} / {d['665']:.3f} / {d['1055']:.3f} | {t['is_R']:+.3f} / {t['oos_R']:+.3f} | {t['breakeven_cost_side_pct']:.3f} |")
        P("")
    t = real["cost0.05pct"]["top"][0]
    P("**Maliyet stresi (en iyi hücre, ort. net R/işlem):** " + ", ".join(f"{k}: {v:+.3f}" for k, v in t["cost_stress_meanR"].items()) + f"; başabaş ≈ %{t['breakeven_cost_side_pct']:.3f}/taraf. Gerçekçi piyasa-emri maliyeti (%0,10-0,15) altında negatif.\n")
    P("## 4) Dürüst özet\n- Gerçek veride 'en iyi' hücreler (Camarilla L2, ~+0,06R @%0,05) **sentetik rastgele dünyalardaki en iyi hücrelerle aynı büyüklükte**; DSR ≈ 0, Reality-Check p ≈ 1; gün-blok CI sıfırı rahatça kapsıyor. %0,15'te hiçbir hücre pozitif değil.\n- Bu 'edge yok' kanıtı değil, **'edge var' kanıtı da yok**: 148 gün, tek rejim, 630+ deneme; test gücü düşük (bölüm 1).")
    open(f"{HERE}/outputs/research_B_overfit_stats.md", "w").write("\n".join(L) + "\n"); print("written")
