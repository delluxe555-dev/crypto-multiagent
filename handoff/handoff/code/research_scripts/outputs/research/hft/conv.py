"""Wrapper around hftbacktest's Binance futures converter (same event mapping), split into
 (1) raw_events(): parse our collected raw feed -> un-ordered event array (local_ts = real receive time)
 (2) build(): apply feed-latency policy + hftbacktest's own correct_local_timestamp / correct_event_order / validate."""
import gzip, json, sys, zlib, numpy as np
import hftbacktest.data.utils.binancefutures as bf
from hftbacktest.data.validation import correct_local_timestamp, correct_event_order, validate_event_order
from hftbacktest.types import (DEPTH_EVENT, DEPTH_CLEAR_EVENT, DEPTH_SNAPSHOT_EVENT, TRADE_EVENT, BUY_EVENT, SELL_EVENT, event_dtype)

def raw_events(path, max_rows=60_000_000, t_start=None, t_end=None):
    """t_start/t_end: epoch ns of local receive time (optional crop; snapshot rows are always kept)."""
    tmp = np.empty(max_rows, event_dtype); n = 0
    f = gzip.open(path, 'rb')
    try:
        while True:
            try: line = f.readline()
            except (EOFError, zlib.error): break
            if not line: break
            if not line.endswith(b"\n"): break
            lts = int(line[:19]); msg = json.loads(line[20:])
            data = msg.get('data')
            if data is not None:
                if t_start and lts < t_start: continue
                if t_end and lts > t_end: continue
                e = data['e']
                if e == 'trade':
                    if data['X'] != 'MARKET': continue
                    tmp[n] = (TRADE_EVENT | (SELL_EVENT if data['m'] else BUY_EVENT), int(data['T'])*1_000_000, lts, float(data['p']), float(data['q']), 0, 0, 0); n += 1
                elif e == 'depthUpdate':
                    et = int(data['T'])*1_000_000
                    for px, q in data['b']:
                        tmp[n] = (DEPTH_EVENT | BUY_EVENT, et, lts, float(px), float(q), 0,0,0); n += 1
                    for px, q in data['a']:
                        tmp[n] = (DEPTH_EVENT | SELL_EVENT, et, lts, float(px), float(q), 0,0,0); n += 1
            else:
                et = int(msg['T'])*1_000_000
                for side, key, ev in ((BUY_EVENT,'bids',0),(SELL_EVENT,'asks',1)):
                    lv = msg[key]
                    if lv:
                        tmp[n] = (DEPTH_CLEAR_EVENT | side, et, lts, float(lv[-1][0]), 0, 0,0,0); n += 1
                        for px, q in lv:
                            tmp[n] = (DEPTH_SNAPSHOT_EVENT | side, et, lts, float(px), float(q), 0,0,0); n += 1
    finally:
        f.close()
    return tmp[:n].copy()

def build(raw, feed_latency_ns=None):
    """feed_latency_ns=None -> use measured receive times (shifted so min latency >= 0);
       0 -> zero feed latency; >0 -> constant synthetic feed latency (local_ts = exch_ts + L)."""
    tmp = raw.copy()
    if feed_latency_ns is not None:
        tmp['local_ts'] = tmp['exch_ts'] + int(feed_latency_ns)
    else:
        tmp = correct_local_timestamp(tmp, 0)
    data = correct_event_order(tmp, np.argsort(tmp['exch_ts'], kind='mergesort'), np.argsort(tmp['local_ts'], kind='mergesort'))
    validate_event_order(data)
    return data
