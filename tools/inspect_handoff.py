import json, os, statistics as st
from collections import Counter

b = r'C:\Users\KXL\Documents\Varsayılan Proje\crypto-multiagent\handoff\handoff\backtests'
d = json.load(open(os.path.join(b, 'outputs__trader__ledger.json.json'), encoding='utf-8'))
raw = d.get('raw', d)
tr = raw.get('positions') or raw.get('trades') or []
print('total records', len(tr))
print('status', Counter(t.get('status') for t in tr))
print('side', Counter(t.get('side') for t in tr))

closed = [t for t in tr if t.get('status') == 'closed']
print('closed', len(closed))
for t in closed:
    sym = t.get('symbol'); side = t.get('side'); lev = t.get('leverage')
    pnl = t.get('pnl_usd'); pct = t.get('pnl_pct'); why = t.get('exit_reason')
    print('%-12s %-5s lev%-3s pnl=%8.2f pct=%7.3f  %s' % (sym, side, lev, pnl, pct or 0, why))

w = [t['pnl_usd'] for t in closed if t['pnl_usd'] > 0]
l = [t['pnl_usd'] for t in closed if t['pnl_usd'] <= 0]
print('wins', len(w), 'losses', len(l), 'net', round(sum(w) + sum(l), 2))
if w and l:
    print('avg win', round(st.mean(w), 2), 'avg loss', round(st.mean(l), 2),
          'PF', round(sum(w) / abs(sum(l)), 2))
print('exit reasons', Counter(t.get('exit_reason') for t in closed))

# runs: confidence vs outcome, htf alignment
print()
print('--- runs ---')
rb = os.path.join(os.path.dirname(b), 'runs')
files = sorted(os.listdir(rb))
print('run files', len(files))
conf = []
for f in files:
    r = json.load(open(os.path.join(rb, f), encoding='utf-8'))
    fin = r.get('final') or {}
    c = fin.get('confidence')
    if c is not None:
        conf.append(c)
print('conf n', len(conf), 'mean', round(st.mean(conf), 1) if conf else None)
