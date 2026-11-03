#!/usr/bin/env python3
"""research_backfill.py - bugune kadar yapilan testleri hypotheses.json + run_cards'a GERIYE DONUK yazar (bir kez calistir; tekrar calistirirsan atlar).
Sayilar mevcut rapor/ciktilardan sayildi; 'yaklasik' olanlar trials_exact=False. Kaynaklar: outputs/combo_bt/*, liqbt_signals_report.txt, outputs/confluence_paper/backtest_report.txt, outputs/ema_bt_*, be_sim.md, leverage_sim.md."""
import hypotheses as H, run_card as RC
BIN = "Binance spot 5m (data-api.binance.vision), ~150 gun (2026-05-27..2026-10-24)"; GATE = "Gate futures 15m + OI (api.gateio.ws), ~20.8 gun, 26 coin"
items = [
 dict(id="combo_r1", title="Combo R1: 35 gosterge kombinasyonu x {5m/1h,15m/1h,15m/2h} (15 coin, stop1.5/hedef3 ATR)", family="combo-ta", state="rejected", trials=35, trials_exact=True, data=BIN + " 15 coin", period="150g", cost="0.05%/0.15% taraf",
      reports=["outputs/combo_bt/summary_by_pair_combo.csv"], notes="Ham 105 hucre; 15m/1h ve 15m/2h (70 hucre) R2'de yeniden test edildi -> benzersiz yeni hucre = 35 (5m/1h)."),
 dict(id="combo_r2", title="Combo R2: 35 kombinasyon x 6 zaman-cifti x 3 stop/hedef (29 coin)", family="combo-ta", state="testing", trials=630, trials_exact=True, data=BIN + " 29 coin", period="150g (IS/OOS yari-yari)",
      cost="0.05% ve 0.15% taraf", reports=["outputs/combo_bt/r2_report.txt", "outputs/combo_bt/r2_by_pair_cfg_combo.csv"],
      notes="Bazlar dahil 630 hucre (558 baz-disi). %0.15'te iki yarida da net-pozitif 0 hucre; %0.05'te 3 hucre (hepsi L2_CamDaily counterHTF). R1+R2 benzersiz toplam = 665."),
 dict(id="camarilla_45m_L2", title="Camarilla gunluk L3/H3 ret, HTF'ye karsi (L2) - 45m/2h & 45m/4h", family="combo-ta", state="testing", trials=0, trials_exact=True, parent="combo_r2", data=BIN, period="150g",
      cost="%0.05 taraf: net +0.05..0.06R; %0.15: -0.03..-0.08R", reports=["outputs/combo_bt/r2_report.txt"], notes="R2 icinden SECILMIS en iyi hucreler (secim yanliligi!). Ek deneme yok; overfit_stats/funding_bt ile test edilecek."),
 dict(id="e2_vote_30m", title="E2 oy kombinasyonu (6/7, MACD'siz) 30m/4h & 30m/2h", family="combo-ta", state="testing", trials=0, parent="combo_r2", data=BIN, period="150g", cost="%0.05 net +0.033R",
      reports=["outputs/combo_bt/r2_report.txt"], notes="R2 icinden secilmis ikinci en iyi aile."),
 dict(id="liq_cluster_touch", title="Likidasyon kumesi dokunma/tepki testi (OI-delta x kaldirac modeli)", family="liq-cluster", state="rejected", trials=120, trials_exact=False, data=GATE, period="20.8g",
      cost="n/a (dokunma olasiligi testi)", reports=["liqbt_report.py", "liqbt_out.pkl"], notes="5 mesafe x 2 yon x 3 ufuk x 4 yas katmani ~ 120 hucre (yaklasik). Karistirici: 'yas'. Kume etkisi guvenilir degil."),
 dict(id="liq_signals_radar", title="radar_read sinyalleri (LONGLIQ/NEWLONG/NEWSHORT/OFOI/SQUEEZE + funding asiri) x {1h,4h pencere} x {1h,4h,12h}", family="liq-cluster", state="monitoring", trials=42, trials_exact=True,
      data=GATE, period="20.8g", cost="0.05% taraf", reports=["liqbt_signals_report.txt"], notes="42 satir (+ funding bolumleri). Tek anlamli-gorunen: NEWSHORT w16/4h net +28bp [+10,+45] (n=477) - 42 hucreden secilmis, tek rejim."),
 dict(id="newshort_w16_4h", title="NEWSHORT w16 4h (en iyi gorunen sinyal)", family="liq-cluster", state="monitoring", trials=0, parent="liq_signals_radar", data=GATE, period="20.8g", cost="0.05% taraf",
      reports=["liqbt_signals_report.txt", "outputs/signal_paper/"], notes="signal_paper_loop.sh ile ileri kagit takip (bildirim yok)."),
 dict(id="confluence_gcla_proxy", title="Cizgi proxy'si (EMA50/EMA100/ST10_3/BBMID20) x kume bandi x alt-kume, nedensel", family="confluence", state="inconclusive", trials=32, trials_exact=True,
      data=GATE + " (cizgiler 2s)", period="16.8g", cost="0.05% taraf", reports=["outputs/confluence_paper/backtest_report.txt"], notes="Cluster ile kesisim n<=52; cogu CI sifiri kapsiyor. Ileri kagit takip: confluence_paper.py --scan."),
 dict(id="confluence_paper_live", title="confluence_paper ileri kagit takip", family="confluence", state="monitoring", trials=0, parent="confluence_gcla_proxy", data="Gate canli", period="ileri", cost="0.05%", reports=["outputs/confluence_paper/"]),
 dict(id="signal_paper_live", title="signal_paper ileri kagit takip (radar sinyalleri)", family="liq-cluster", state="monitoring", trials=0, parent="liq_signals_radar", data="Gate canli", period="ileri", cost="0.05%", reports=["outputs/signal_paper/"]),
 dict(id="ema_8_13_21", title="EMA 8-13-21 stratejileri A-D (L / LS) x {15m,1h,4h,1d} x coin", family="ema", state="rejected", trials=150, trials_exact=False, data="Binance spot", period="IS/OOS bolumlu",
      cost="0.10% komisyon + 0.05% kayma /taraf", reports=["outputs/ema_bt_2026-10-25T0143_summary.md"], notes="15m/1h/4h-LS buyuk zarar; 1d tek yonlu long tutma ~ B&H'den iyi degil. 150 = ozet tablosundaki satir sayisi."),
 dict(id="be_sim", title="Basabas stop varyantlari (13 varyant x {canli 7 islem, SOL 4 islem})", family="risk-mgmt", state="inconclusive", trials=26, trials_exact=True, data="canli defter", period="~2 gun",
      cost="-", reports=["outputs/be_sim.md"], notes="n=7 ve n=4: istatistiksel anlam yok."),
 dict(id="leverage_sim", title="Kaldirac tavani 5x/10x/20x x iki risk modu; 1680 kurulumluk likidasyon duyarlilik izgarasi", family="risk-mgmt", state="inconclusive", trials=6, trials_exact=True, data="canli defter + Binance yolu", period="~14g",
      cost="-", reports=["outputs/leverage_sim.md"], notes="Izgara duyarlilik analizi (strateji secimi degil), trial sayilmadi."),
 dict(id="llm_backtest_sol", title="LLM ajan 1h backtest (SOL) + backtest.py haftalik BTC", family="llm-agent", state="inconclusive", trials=2, trials_exact=False, data="Binance spot", period="kisa", cost="?", reports=["logs/backtest_1h_SOLUSDT.log", "logs/bt_sol_v2.log"], notes="4 benzersiz islem; anlamsiz."),
 dict(id="live_paper_trader", title="Canli kagit trader (LLM ajanlar) - ledger", family="llm-agent", state="monitoring", trials=0, data="canli", period="ileri", cost="gercek-benzeri", reports=["outputs/ledger.json"], notes="7 islem (3 kapali + 4 acik); anlamsiz."),
 dict(id="kronos_sanity", title="Kronos mini/small hizli sanity (n=18, sample 1 ve 5)", family="ml-forecast", state="inconclusive", trials=4, trials_exact=True, data="Gate spot 1h", period="kisa", cost="-", reports=["/workspace/repos_review/ksanity/result.json"], notes="n=18 -> yon isabeti guvenilmez; model cogunlukla 'yukari' onyargisi gosterdi (sample_count=1)."),
 dict(id="kronos_full", title="Kronos small & mini tam test: 29 coin x 45 gun x 24 mum ufuk (Gate perp 1h)", family="ml-forecast", state="testing", trials=8, trials_exact=True, data="Gate futures 1h", period="45g",
      cost="0.15% taraf", reports=["kronos_full.py", "outputs/research/kronos/"], notes="Birincil: 2 model x 24h ufuk (2 deneme); ikincil: 1h/4h/12h yon isabeti x 2 model (6)."),
]
cards = [
 ("combo_r2", dict(data_source=BIN + " 29 coin", params=dict(pairs=6, cfgs=["S1.5/T3/24h", "S2/T4/48h", "S3/T6/72h"], combos=35, entry="sonraki bar acilisi", stop_wins_on_ambiguous=True, htf="son KAPANMIS HTF mumu"),
       cost_side_pct=0.05, days=150, n_trades=int(72892), n_trials=630, oos=True, lookahead_checked=True, code="combo_bt2.py", results=dict(pos_both_halves_at_0_15=0, pos_both_halves_at_0_05=3, best_net_lo_R=0.059))),
 ("combo_r1", dict(data_source=BIN + " 15 coin", params=dict(pairs=["5m/1h", "15m/1h", "15m/2h"], stop_atr=1.5, tgt_atr=3.0, combos=35), cost_side_pct=0.05, days=150, n_trials=105, oos=True, lookahead_checked=True, code="combo_bt.py")),
 ("camarilla_45m_L2", dict(data_source=BIN, params=dict(pair="45m/2h & 45m/4h", combo="L2_CamDaily_L3/H3reject_counterHTF"), cost_side_pct=0.05, days=150, n_trades=1520, n_trials=665, oos=True, lookahead_checked=True,
       results=dict(net_lo_R=0.059, net_hi_R=-0.026, gross_t=3.0), code="combo_bt2.py", notes="SECILMIS en iyi hucre")),
 ("liq_signals_radar", dict(data_source=GATE, params=dict(signals=6, windows=["1h", "4h"], horizons=["1h", "4h", "12h"]), cost_side_pct=0.05, days=20.8, n_trades=477, n_trials=42, oos=False, lookahead_checked=True, code="liqbt_signals.py",
       results=dict(newshort_w16_4h_net_bp=28.0, ci=[10, 45]))),
 ("confluence_gcla_proxy", dict(data_source=GATE, params=dict(proxies=["EMA50", "EMA100", "ST10_3", "BBMID20"], bins_pct=0.25, bands_pct=[0.3, 0.5]), cost_side_pct=0.05, days=16.8, n_trades=1390, n_trials=32, oos=False, lookahead_checked=True, code="confluence_paper.py")),
 ("liq_cluster_touch", dict(data_source=GATE, params=dict(distances_pct="0.375-1.375", sides=2, horizons=["4h", "12h", "24h"]), days=20.8, n_trials=120, oos=False, lookahead_checked=True, code="liqbt.py")),
 ("ema_8_13_21", dict(data_source="Binance spot", params=dict(strategies="A-D x L/LS", tfs=["15m", "1h", "4h", "1d"]), cost_side_pct=0.15, n_trials=150, oos=True, code="ema_bt.py")),
 ("be_sim", dict(data_source="canli defter", params=dict(variants=13), n_trades=7, n_trials=26, oos=False, code="be_sim.py")),
 ("leverage_sim", dict(data_source="canli defter+Binance", params=dict(caps=[5, 10, 20], grid=1680), n_trades=9, n_trials=6, oos=False, code="leverage_sim.py")),
 ("kronos_sanity", dict(data_source="Gate spot 1h", params=dict(models=["mini", "small"], sample_count=[1, 5], n=18), n_trades=18, n_trials=4, oos=True, lookahead_checked=True)),
]
if __name__ == "__main__":
    have = H.load()["items"]
    for it in items:
        if it["id"] not in have: H.add(**it)
    import os, glob
    if not glob.glob(f"{RC.DIR}/*backfill*"):
        for n, kw in cards:
            kw = dict(kw); RC.card(f"backfill_{n}", hypothesis=n, **kw)
    print(H.summary())
