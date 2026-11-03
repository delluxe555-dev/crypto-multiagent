import numpy as np, json, sys, time
from numba import njit
from hftbacktest import (BacktestAsset, HashMapMarketDepthBacktest, BUY, SELL, GTX, LIMIT, BUY_EVENT, SELL_EVENT)
import conv

SPEC = {"btcusdt": dict(tick=0.1, lot=0.001), "ethusdt": dict(tick=0.01, lot=0.001), "solusdt": dict(tick=0.001, lot=0.01)}

@njit
def strategy(hbt, half_bps, skew_bps, order_notional, max_notional, requote_bps, rec):
    """Symmetric quoting around mid with linear inventory skew.
    bid/ask = mid * (1 -/+ half_bps/1e4 - skew_bps/1e4 * inventory/max_inventory). Post-only (GTX). Re-evaluates every 100 ms."""
    tick = hbt.depth(0).tick_size
    lot = hbt.depth(0).lot_size
    next_id = 1
    step = 0
    rec_i = 0
    while hbt.elapse(100_000_000) == 0:
        hbt.clear_inactive_orders(0)
        depth = hbt.depth(0)
        bb = depth.best_bid_tick
        ba = depth.best_ask_tick
        step += 1
        if bb <= 0 or ba <= 0 or ba >= 1_000_000_000_000 or bb >= ba:
            continue
        mid = 0.5 * (bb + ba) * tick
        pos = hbt.position(0)
        sv = hbt.state_values(0)
        inv_notional = pos * mid
        ratio = inv_notional / max_notional
        if ratio > 1.0: ratio = 1.0
        if ratio < -1.0: ratio = -1.0
        bid_px = mid * (1.0 - half_bps / 1e4 - skew_bps / 1e4 * ratio)
        ask_px = mid * (1.0 + half_bps / 1e4 - skew_bps / 1e4 * ratio)
        bid_tick = np.floor(bid_px / tick)
        ask_tick = np.ceil(ask_px / tick)
        if bid_tick > ba - 1: bid_tick = ba - 1
        if ask_tick < bb + 1: ask_tick = bb + 1
        want_bid = inv_notional < max_notional
        want_ask = inv_notional > -max_notional
        qty = np.round(order_notional / mid / lot) * lot
        if qty < lot: qty = lot
        thr = requote_bps / 1e4 * mid / tick   # ticks
        bid_live = False
        ask_live = False
        orders = hbt.orders(0)
        vals = orders.values()
        while vals.has_next():
            o = vals.get()
            if o.side == BUY:
                bid_live = True
                if o.cancellable and ((not want_bid) or abs(o.price_tick - bid_tick) > thr):
                    hbt.cancel(0, o.order_id, False)
            else:
                ask_live = True
                if o.cancellable and ((not want_ask) or abs(o.price_tick - ask_tick) > thr):
                    hbt.cancel(0, o.order_id, False)
        if want_bid and not bid_live:
            hbt.submit_buy_order(0, next_id, bid_tick * tick, qty, GTX, LIMIT, False)
            next_id += 1
        if want_ask and not ask_live:
            hbt.submit_sell_order(0, next_id, ask_tick * tick, qty, GTX, LIMIT, False)
            next_id += 1
        if step % 10 == 0 and rec_i < rec.shape[0]:   # record every 1 s
            rec[rec_i, 0] = hbt.current_timestamp
            rec[rec_i, 1] = pos
            rec[rec_i, 2] = mid
            rec[rec_i, 3] = sv.balance
            rec[rec_i, 4] = sv.fee
            rec[rec_i, 5] = sv.num_trades
            rec[rec_i, 6] = sv.trading_value
            rec_i += 1
    return rec_i

def run(sym, data, order_lat_ms, half_bps, skew_bps=2.0, order_notional=200.0, max_notional=1000.0, requote_bps=0.5,
        maker_fee=0.0, taker_fee=0.0, queue="risk_averse"):
    sp = SPEC[sym]
    a = (BacktestAsset().data([data]).linear_asset(1.0)
         .constant_order_latency(int(order_lat_ms * 1e6), int(order_lat_ms * 1e6))
         .no_partial_fill_exchange().trading_value_fee_model(maker_fee, taker_fee)
         .tick_size(sp["tick"]).lot_size(sp["lot"]).last_trades_capacity(0))
    if queue == "risk_averse": a = a.risk_adverse_queue_model()
    elif queue == "prob": a = a.power_prob_queue_model(2.0)
    hbt = HashMapMarketDepthBacktest([a])
    rec = np.full((20000, 7), np.nan)
    n = strategy(hbt, half_bps, skew_bps, order_notional, max_notional, requote_bps, rec)
    hbt.close()
    return rec[:n]

def summarize(rec, maker_fee):
    ts, pos, mid, bal, fee, ntr, tv = rec.T
    eq_gross = bal + pos * mid           # before fees
    eq_net = eq_gross - fee
    inv = pos * mid
    ret = np.diff(eq_net)
    return dict(
        fills=int(ntr[-1]), traded_usd=float(tv[-1]), pnl_gross=float(eq_gross[-1]-eq_gross[0]), fees=float(fee[-1]),
        pnl_net=float(eq_net[-1]-eq_net[0]), max_dd=float((np.maximum.accumulate(eq_net)-eq_net).max()),
        inv_max_abs=float(np.abs(inv).max()), inv_mean_abs=float(np.abs(inv).mean()), inv_end=float(inv[-1]),
        pnl_sec_std=float(ret.std()), secs=int(len(ts)),
        pnl_per_fill=float((eq_gross[-1]-eq_gross[0])/max(ntr[-1],1)))
