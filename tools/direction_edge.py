import csv, os, statistics as st
from collections import Counter, defaultdict

b = r'C:\Users\KXL\Documents\Varsayılan Proje\crypto-multiagent\handoff\handoff'
rows = list(csv.DictReader(open(os.path.join(b, 'summary_table.csv'), encoding='utf-8')))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


data = []
for r in rows:
    f = num(r['fwd_ret_pct_24bars'])
    d = r['decision']
    executed = r['result'].startswith('live:closed') or r['result'].startswith('live:open')
    data.append({'sym': r['symbol'], 'tf': r['tf'], 'dec': d, 'fwd': f,
                 'exec': executed, 'conf': num(r['confidence'])})

with_fwd = [x for x in data if x['fwd'] is not None]
print('rows', len(data), 'with fwd', len(with_fwd))

dir_rows = [x for x in with_fwd if x['dec'] in ('BUY', 'SELL')]
print('directional rows with fwd', len(dir_rows),
      'BUY', sum(1 for x in dir_rows if x['dec'] == 'BUY'),
      'SELL', sum(1 for x in dir_rows if x['dec'] == 'SELL'))

hit = sum(1 for x in dir_rows if (x['dec'] == 'BUY') == (x['fwd'] > 0))
base_short = sum(1 for x in with_fwd if x['fwd'] < 0) / len(with_fwd)
print('direction hit rate', round(100 * hit / len(dir_rows), 1), '%')
print('always-SHORT baseline (fwd<0 share)', round(100 * base_short, 1), '%')

se = [x for x in dir_rows if x['dec'] == 'SELL']
print('SELL-only hit (fwd<0)', round(100 * sum(1 for x in se if x['fwd'] < 0) / len(se), 1), '%')

print('\nexecuted vs skipped (SELL only)')
se_exec = [x for x in se if x['exec']]
se_skip = [x for x in se if not x['exec']]
for label, grp in (('executed', se_exec), ('skipped', se_skip)):
    if grp:
        print(' ', label, 'n=', len(grp),
              'mean fwd %', round(st.mean(x['fwd'] for x in grp), 3),
              'hit %', round(100 * sum(1 for x in grp if x['fwd'] < 0) / len(grp), 1))

print('\nby confidence bucket (SELL, all)')
buckets = defaultdict(list)
for x in se:
    c = x['conf']
    if c is None:
        continue
    k = '<65' if c < 65 else '65-74' if c < 75 else '75-79' if c < 80 else '>=80'
    buckets[k].append(x['fwd'])
for k in ('<65', '65-74', '75-79', '>=80'):
    v = buckets.get(k)
    if v:
        print(' ', k, 'n=', len(v), 'mean fwd %', round(st.mean(v), 3),
              'hit %', round(100 * sum(1 for y in v if y < 0) / len(v), 1))

print('\nby tf (SELL, all)')
for tf in sorted({x['tf'] for x in se}):
    v = [x['fwd'] for x in se if x['tf'] == tf]
    print(' ', tf, 'n=', len(v), 'mean fwd %', round(st.mean(v), 3),
          'hit %', round(100 * sum(1 for y in v if y < 0) / len(v), 1))

# live trade stats from trader ledger
import json
led = json.load(open(os.path.join(b, 'backtests', 'outputs__trader__ledger.json.json'), encoding='utf-8'))['raw']
pos = led['positions']
closed = [p for p in pos if p['status'] == 'closed']
w = [p['pnl_usd'] for p in closed if p['pnl_usd'] > 0]
l = [p['pnl_usd'] for p in closed if p['pnl_usd'] <= 0]
print('\nlive ledger: positions', len(pos), 'closed', len(closed),
      'wins', len(w), 'losses', len(l),
      'net', round(sum(w) + sum(l), 2),
      'PF', round(sum(w) / abs(sum(l)), 2) if l else None)
print('exit reasons', Counter(p['exit_reason'] for p in closed))
print('all sides', Counter(p['side'] for p in pos))
