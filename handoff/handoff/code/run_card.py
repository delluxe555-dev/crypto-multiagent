#!/usr/bin/env python3
"""run_card.py - her backtest kosusu icin JSON 'kart': veri kaynagi, parametreler, maliyet, uyari ozeti.
Fikir kaynagi: QuantDinger (Apache-2.0) / Vibe-Trading (MIT) 'run artifact' yaklasimi; kod sifirdan yazildi.
Kullanim: import run_card as RC; RC.card('ad', data_source=..., params={...}, cost_side_pct=0.05, days=150, n_trades=..., n_trials=..., results={...}, files=[...], hypothesis='id')
Kartlar: outputs/research/run_cards/<zaman>_<ad>.json ; uyarilar otomatik uretilir (az gun/tek rejim, az islem, cok deneme, dusuk maliyet...)."""
import json, os, time, re, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); DIR = f"{HERE}/outputs/research/run_cards"
def auto_warnings(days=None, n_trades=None, n_trials=None, cost_side_pct=None, oos=None, lookahead_checked=None, extra=()):
    w = []
    if days is not None and days < 365: w.append(f"Tek rejim/kisa pencere: {days:g} gun (<1 yil); sonuclar rejime ozgu olabilir.")
    if n_trades is not None and n_trades < 100: w.append(f"Az islem/olay: n={n_trades}; guven araligi genis, anlamsiz olabilir.")
    if n_trials is not None and n_trials > 20: w.append(f"Coklu test: ayni veride ~{n_trials} yapilandirma denendi; en iyiyi secmek sisirir (deflated Sharpe/PBO gerekli).")
    if cost_side_pct is not None and cost_side_pct < 0.10: w.append(f"Maliyet dusuk: taraf basi %{cost_side_pct}; gercekci piyasa emri maliyeti %0.10-0.15 olabilir.")
    if oos is False: w.append("Ayrik OOS yok (ya da ayni verinin yarisi).")
    if lookahead_checked is False: w.append("Ileriye bakma (look-ahead) kontrolu yapilmadi.")
    return w + list(extra)
def card(name, data_source, params, cost_side_pct=None, days=None, n_trades=None, n_trials=None, results=None, files=(), hypothesis=None, oos=None, lookahead_checked=None,
         extra_warnings=(), notes="", code=None, ts=None):
    os.makedirs(DIR, exist_ok=True); ts = ts or time.strftime("%Y%m%dT%H%M%S")
    c = dict(name=name, created=time.strftime("%Y-%m-%dT%H:%M:%S%z"), hypothesis=hypothesis, data_source=data_source, params=params, cost_side_pct=cost_side_pct, days=days,
             n_trades=n_trades, n_trials=n_trials, oos=oos, lookahead_checked=lookahead_checked, results=results or {}, files=list(files), code=code, notes=notes,
             warnings=auto_warnings(days, n_trades, n_trials, cost_side_pct, oos, lookahead_checked, extra_warnings))
    if code and os.path.exists(f"{HERE}/{code}"): c["code_sha1"] = hashlib.sha1(open(f"{HERE}/{code}", "rb").read()).hexdigest()[:12]
    fp = f"{DIR}/{ts}_{re.sub(r'[^A-Za-z0-9_.-]+','_',name)}.json"; json.dump(c, open(fp, "w"), indent=1, ensure_ascii=False); return fp
if __name__ == "__main__":
    import sys
    for f in sorted(os.listdir(DIR)):
        c = json.load(open(f"{DIR}/{f}")); print(f"{f}: {len(c['warnings'])} uyari - {c['name']}")
