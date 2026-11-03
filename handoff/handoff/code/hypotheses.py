#!/usr/bin/env python3
"""hypotheses.py - arastirma hipotezleri kaydi (registry) + deneme (trial) sayaci.
Fikir kaynagi: QuantDinger (Apache-2.0) strategy_evolution'daki 'hipotez yasam dongusu / deneme sayisi' yaklasimi; kod sifirdan yazildi.
Durumlar: exploring -> testing -> validated | rejected | monitoring. Dosya: outputs/research/hypotheses.json
Kullanim:  python3 hypotheses.py list | summary | add ID "baslik" --family F --state exploring --trials N
           python3 hypotheses.py state ID testing "not" | trials ID +N "not"
Kod icinden: import hypotheses as H; H.add(...); H.add_trials('id', 12, 'not'); H.set_state('id','rejected','neden')
Kural: her yeni backtest/parametre taramasi ONCE trial sayisini arttirir (aksi halde deflated-Sharpe yanlis olur)."""
import json, os, sys, time, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); FP = f"{HERE}/outputs/research/hypotheses.json"
STATES = ("exploring", "testing", "validated", "rejected", "monitoring", "inconclusive")
def now(): return time.strftime("%Y-%m-%dT%H:%M:%S%z")
def load():
    if os.path.exists(FP): return json.load(open(FP))
    return {"version": 1, "items": {}}
def save(r):
    os.makedirs(os.path.dirname(FP), exist_ok=True); tmp = FP + ".tmp"; json.dump(r, open(tmp, "w"), indent=1, ensure_ascii=False); os.replace(tmp, FP)
def add(id, title, family="", state="exploring", trials=0, trials_exact=True, data="", period="", cost="", reports=(), notes="", parent=None, **extra):
    assert state in STATES; r = load()
    if id in r["items"]: raise KeyError(f"{id} zaten var")
    r["items"][id] = dict(id=id, title=title, family=family, state=state, trials=trials, trials_exact=trials_exact, data=data, period=period, cost=cost, reports=list(reports),
                          notes=notes, parent=parent, created=now(), history=[dict(ts=now(), state=state, note="olusturuldu")], **extra); save(r)
def set_state(id, state, note=""):
    assert state in STATES; r = load(); it = r["items"][id]; it["state"] = state; it["history"].append(dict(ts=now(), state=state, note=note)); save(r)
def add_trials(id, n, note=""):
    r = load(); it = r["items"][id]; it["trials"] += n; it["history"].append(dict(ts=now(), state=it["state"], note=f"+{n} deneme: {note}")); save(r)
def total_trials(family=None):
    r = load(); it = [x for x in r["items"].values() if family is None or x["family"] == family]
    return sum(x["trials"] for x in it), any(not x.get("trials_exact", True) for x in it)
def summary():
    r = load(); fam = {}
    for x in r["items"].values():
        f = fam.setdefault(x["family"] or "-", dict(n=0, trials=0, approx=False)); f["n"] += 1; f["trials"] += x["trials"]; f["approx"] |= not x.get("trials_exact", True)
    tot, ap = total_trials(); return dict(n_hypotheses=len(r["items"]), total_trials=tot, approx=ap, by_family=fam,
                                         by_state={s: sum(1 for x in r["items"].values() if x["state"] == s) for s in STATES})
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("args", nargs="*"); ap.add_argument("--family", default=""); ap.add_argument("--state", default="exploring"); ap.add_argument("--trials", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "list":
        for x in load()["items"].values(): print(f"{x['id']:28s} {x['state']:12s} trials={x['trials']:5d}{'' if x.get('trials_exact',True) else '~'} [{x['family']}] {x['title']}")
    elif a.cmd == "summary": print(json.dumps(summary(), indent=1, ensure_ascii=False))
    elif a.cmd == "add": add(a.args[0], a.args[1], a.family, a.state, a.trials)
    elif a.cmd == "state": set_state(a.args[0], a.args[1], " ".join(a.args[2:]))
    elif a.cmd == "trials": add_trials(a.args[0], int(a.args[1]), " ".join(a.args[2:]))
