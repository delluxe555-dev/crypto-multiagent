# F — hftbacktest mini-experiment (market making, BTC/ETH/SOL)

Run: Sun 25 Oct 2026 (Europe/Istanbul). Code + raw data + results: `research/hft/` (`collect.py`, `conv.py`, `mm.py`, `experiment.py`, `results.json`, `tables.md`, `raw/*.gz`).
No API keys, no real orders, paper simulation only.

## TL;DR
- **Nothing here shows an edge.** A simple symmetric-quote + inventory-skew market maker on Binance USDT-M perps **loses money gross** (before fees) in almost every configuration, with or without latency, on all 3 coins.
- With the **regular-user maker fee (0.02%)** it loses far more: fees are 10–100× the spread capture. E.g. BTC quoting at the touch: gross −$5.2, net −$17.7 on $62.6k traded in 56 min (zero latency).
- **Zero latency was NOT better than with latency** (gross PnL is similarly negative, slightly *less* negative with latency because fewer fills = less adverse selection). So there is no "latency kills the edge" story — there simply was no edge at zero latency to begin with. By the hftbacktest author's own rule ("if it only works at zero latency it doesn't work"), this strategy fails the first test already.
- The only positive numbers come from a **hypothetical maker rebate (−0.005%)** or from a handful of fills at wide quotes (noise). A rebate isn't available to a normal account.
- **A 56-minute Sunday sample proves nothing statistically.** All of this is a plumbing test of hftbacktest + a sanity check, not evidence for or against market making.

## Data
- Source: **live Binance USDT-M futures websocket** (`fstream`, public, no key): `<sym>@depth@0ms` L2 diffs + `<sym>@trade` trades, plus an initial order-book snapshot via the public ws-fapi `depth` request. Binance REST (`fapi`/`api`) returns HTTP 451 from this box, and data.binance.vision has no futures depth-diff / bookTicker files, so a live collection was the only free route.
- Collected 18:07–19:08 Istanbul (UTC+3); **usable contiguous window 18:07:19 → 19:03:40 (56.4 min)**, no gaps >5 s in any symbol (collector stalled/reconnected after 19:03:40, the tail was discarded).
- Event rows after conversion (incl. hftbacktest's exch/local event duplication): BTCUSDT 3,496,130; ETHUSDT 3,555,761; SOLUSDT 873,157.
- Price levels: BTC ≈ $80,615, ETH ≈ $2,342, SOL ≈ $101.5. Tick/lot inferred from data (BTC 0.1/0.001, ETH 0.01/0.001, SOL 0.001/0.01) because exchangeInfo is unreachable.
- Conversion: my own parser producing the same event layout as hftbacktest's documented Binance converter (the library one wants a ~6 GB buffer), with `correct_event_order` / local-timestamp handling.

## Method
- Engine: hftbacktest 2.4.4 (`HashMapMarketDepthBacktest`, linear asset, post-only GTX limit orders, no partial fill exchange).
- Strategy (`mm.py`): every 100 ms compute mid; bid/ask = mid ∓ half_spread ∓ skew, skew = 2 bp × (inventory $ / $1000 cap), clamped to stay passive. Clip $200 per side, max inventory $1,000 (long/short), re-quote when the target moves >0.5 bp. Half-spreads tested: 0 (= at/inside touch, clamped to passive), 0.5, 1, 2, 4 bp.
- Queue models: **risk-averse** (primary; order only fills once the queue ahead is fully traded) and **power-prob (x²)** (sensitivity). The two give nearly identical results (a few % fills difference, mostly at the touch).
- Latency scenarios (feed latency / order entry & response latency, each way):
  1. 0 / 0 ms (reference)
  2. 5 / 5 ms
  3. 25 / 25 ms
  4. "measured" feed latency of the recorded stream (this box→Binance, roughly 28 ms + jitter after shifting min latency to 0) / 50 ms order latency
  Caveat: the box clock drifted a few tens of ms relative to Binance over the hour, so the "measured" feed latency is only approximate; I treated it as a pessimistic scenario.
- **Fees:** all orders are maker/post-only, taker is never used. Fee applied = **regular user VIP0 maker 0.02% (taker 0.05% would apply only if crossing the spread; never happens here)**. Net PnL = gross − 0.02% × traded notional (computed analytically). Also shown: hypothetical −0.005% maker rebate (market-maker program only). BNB discount (0.018%) would change nothing material. End inventory marked at mid.

## Results (per coin)
Gross PnL excludes fees. Tables below: risk-averse queue model; full data incl. power-prob in `results.json`.

### BTCUSDT (mid ≈ 80614.9)

Risk-averse queue model. PnL in USD. Net = after 0.02% maker fee. 'Rebate' = hypothetical −0.005% maker fee (MM program; not a regular user).

| half-spread (bp) | feed/order latency | fills | traded $ | gross PnL | net @0.02% | net @ rebate | max DD (gross) | mean/max abs inv $ | end inv $ | gross PnL per quarter |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 / 0 ms | 388 | 62,561 | -5.23 | -17.74 | -2.10 | 5.23 | 329 / 806 | 322 | -1.58, -1.62, -1.17, -0.86 |
| 0.5 | 0 / 0 ms | 231 | 37,245 | -3.16 | -10.61 | -1.30 | 3.16 | 192 / 645 | 161 | -0.95, -1.08, -0.70, -0.44 |
| 1 | 0 / 0 ms | 86 | 13,865 | -0.68 | -3.46 | 0.01 | 0.75 | 98 / 323 | 0 | -0.16, -0.27, -0.10, -0.16 |
| 2 | 0 / 0 ms | 6 | 968 | -0.06 | -0.26 | -0.02 | 0.64 | 177 / 323 | 0 | -0.17, 0.12, 0.14, -0.16 |
| 4 | 0 / 0 ms | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0 / 0 | 0 | 0.00, 0.00, 0.00, 0.00 |
| 0 | 5 / 5 ms | 366 | 59,015 | -4.91 | -16.71 | -1.95 | 4.91 | 317 / 807 | 322 | -1.34, -1.61, -1.12, -0.84 |
| 0.5 | 5 / 5 ms | 223 | 35,956 | -3.17 | -10.36 | -1.38 | 3.17 | 189 / 484 | 161 | -0.92, -1.09, -0.75, -0.41 |
| 1 | 5 / 5 ms | 84 | 13,544 | -0.67 | -3.37 | 0.01 | 0.73 | 81 / 323 | 0 | -0.15, -0.34, -0.11, -0.07 |
| 2 | 5 / 5 ms | 6 | 968 | 0.04 | -0.15 | 0.09 | 0.30 | 49 / 161 | 0 | -0.08, 0.05, 0.07, 0.00 |
| 4 | 5 / 5 ms | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0 / 0 | 0 | 0.00, 0.00, 0.00, 0.00 |
| 0 | 25 / 25 ms | 328 | 52,886 | -4.56 | -15.14 | -1.92 | 4.56 | 317 / 807 | 322 | -1.22, -1.62, -0.97, -0.75 |
| 0.5 | 25 / 25 ms | 225 | 36,278 | -2.84 | -10.09 | -1.02 | 2.84 | 192 / 644 | 161 | -0.79, -1.08, -0.60, -0.36 |
| 1 | 25 / 25 ms | 94 | 15,156 | -1.07 | -4.10 | -0.31 | 1.11 | 88 / 484 | 0 | -0.36, -0.39, -0.15, -0.16 |
| 2 | 25 / 25 ms | 6 | 968 | 0.03 | -0.17 | 0.08 | 0.30 | 49 / 161 | 0 | -0.08, 0.05, 0.06, 0.00 |
| 4 | 25 / 25 ms | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0 / 0 | 0 | 0.00, 0.00, 0.00, 0.00 |
| 0 | measured (~28 ms+jitter) / 50 ms | 320 | 51,597 | -4.47 | -14.78 | -1.89 | 4.47 | 323 / 807 | 322 | -1.11, -1.63, -0.98, -0.75 |
| 0.5 | measured (~28 ms+jitter) / 50 ms | 213 | 34,344 | -2.88 | -9.75 | -1.16 | 2.88 | 185 / 484 | 161 | -0.84, -0.97, -0.64, -0.43 |
| 1 | measured (~28 ms+jitter) / 50 ms | 92 | 14,833 | -0.90 | -3.87 | -0.16 | 0.95 | 82 / 484 | 0 | -0.24, -0.39, -0.21, -0.07 |
| 2 | measured (~28 ms+jitter) / 50 ms | 10 | 1,613 | -0.20 | -0.52 | -0.12 | 0.59 | 73 / 323 | 0 | -0.14, -0.13, 0.06, 0.00 |
| 4 | measured (~28 ms+jitter) / 50 ms | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0 / 0 | 0 | 0.00, 0.00, 0.00, 0.00 |

### ETHUSDT (mid ≈ 2341.52)

Risk-averse queue model. PnL in USD. Net = after 0.02% maker fee. 'Rebate' = hypothetical −0.005% maker fee (MM program; not a regular user).

| half-spread (bp) | feed/order latency | fills | traded $ | gross PnL | net @0.02% | net @ rebate | max DD (gross) | mean/max abs inv $ | end inv $ | gross PnL per quarter |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 / 0 ms | 885 | 176,566 | -13.26 | -48.57 | -4.43 | 13.26 | 332 / 1000 | 574 | -4.03, -3.64, -4.22, -1.37 |
| 0.5 | 0 / 0 ms | 629 | 125,494 | -9.16 | -34.25 | -2.88 | 9.16 | 207 / 615 | 183 | -2.87, -2.11, -3.20, -0.97 |
| 1 | 0 / 0 ms | 263 | 52,454 | -3.93 | -14.42 | -1.31 | 3.96 | 93 / 408 | 190 | -1.22, -0.94, -1.44, -0.33 |
| 2 | 0 / 0 ms | 24 | 4,791 | -1.14 | -2.09 | -0.90 | 1.41 | 113 / 402 | -2 | 0.01, -0.19, -0.97, 0.01 |
| 4 | 0 / 0 ms | 2 | 399 | 0.39 | 0.31 | 0.41 | 0.79 | 195 / 399 | -398 | 0.00, 0.00, -0.07, 0.46 |
| 0 | 5 / 5 ms | 854 | 170,377 | -12.94 | -47.01 | -4.42 | 12.97 | 337 / 1000 | 379 | -3.81, -3.58, -4.37, -1.18 |
| 0.5 | 5 / 5 ms | 616 | 122,889 | -8.70 | -33.27 | -2.55 | 8.70 | 204 / 615 | 382 | -2.76, -2.00, -3.06, -0.88 |
| 1 | 5 / 5 ms | 271 | 54,048 | -3.96 | -14.77 | -1.26 | 3.99 | 99 / 598 | 190 | -1.14, -0.95, -1.55, -0.32 |
| 2 | 5 / 5 ms | 24 | 4,791 | -1.08 | -2.04 | -0.85 | 1.38 | 101 / 402 | -2 | 0.03, -0.19, -0.93, 0.00 |
| 4 | 5 / 5 ms | 2 | 399 | 0.40 | 0.32 | 0.42 | 0.78 | 195 / 399 | -398 | 0.00, 0.00, -0.07, 0.46 |
| 0 | 25 / 25 ms | 752 | 150,028 | -11.15 | -41.16 | -3.65 | 11.25 | 330 / 813 | -14 | -3.41, -3.42, -3.28, -1.05 |
| 0.5 | 25 / 25 ms | 581 | 115,917 | -8.10 | -31.28 | -2.30 | 8.11 | 211 / 613 | 185 | -2.57, -2.06, -2.57, -0.89 |
| 1 | 25 / 25 ms | 289 | 57,647 | -3.95 | -15.48 | -1.07 | 3.97 | 110 / 411 | 187 | -1.06, -1.03, -1.54, -0.32 |
| 2 | 25 / 25 ms | 38 | 7,580 | -0.81 | -2.33 | -0.43 | 1.43 | 101 / 402 | 0 | 0.29, -0.03, -1.07, 0.00 |
| 4 | 25 / 25 ms | 2 | 399 | 0.40 | 0.32 | 0.42 | 0.78 | 195 / 399 | -398 | 0.00, 0.00, -0.07, 0.46 |
| 0 | measured (~28 ms+jitter) / 50 ms | 705 | 140,643 | -10.92 | -39.05 | -3.89 | 10.97 | 329 / 1000 | 187 | -2.94, -3.76, -3.22, -1.00 |
| 0.5 | measured (~28 ms+jitter) / 50 ms | 557 | 111,122 | -7.78 | -30.01 | -2.22 | 7.80 | 214 / 615 | 183 | -2.35, -2.30, -2.34, -0.79 |
| 1 | measured (~28 ms+jitter) / 50 ms | 275 | 54,858 | -3.96 | -14.93 | -1.22 | 3.98 | 108 / 411 | 187 | -1.17, -1.04, -1.44, -0.31 |
| 2 | measured (~28 ms+jitter) / 50 ms | 44 | 8,776 | -0.92 | -2.68 | -0.48 | 1.37 | 95 / 601 | -2 | 0.30, -0.08, -1.14, 0.00 |
| 4 | measured (~28 ms+jitter) / 50 ms | 5 | 997 | 1.10 | 0.90 | 1.15 | 1.39 | 325 / 799 | -597 | 0.00, 0.00, 0.41, 0.70 |

### SOLUSDT (mid ≈ 101.53)

Risk-averse queue model. PnL in USD. Net = after 0.02% maker fee. 'Rebate' = hypothetical −0.005% maker fee (MM program; not a regular user).

| half-spread (bp) | feed/order latency | fills | traded $ | gross PnL | net @0.02% | net @ rebate | max DD (gross) | mean/max abs inv $ | end inv $ | gross PnL per quarter |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 / 0 ms | 5461 | 1,092,856 | -21.08 | -239.66 | 33.56 | 21.09 | 187 / 794 | -207 | -7.77, -5.60, -5.41, -2.30 |
| 0.5 | 0 / 0 ms | 508 | 101,655 | -4.38 | -24.71 | 0.70 | 4.39 | 25 / 603 | -4 | -1.03, -1.11, -1.55, -0.70 |
| 1 | 0 / 0 ms | 200 | 40,021 | -3.01 | -11.02 | -1.01 | 3.17 | 135 / 404 | -6 | -0.36, -1.11, -1.36, -0.18 |
| 2 | 0 / 0 ms | 38 | 7,604 | -0.08 | -1.60 | 0.30 | 0.63 | 144 / 599 | -1 | 0.32, -0.06, -0.13, -0.20 |
| 4 | 0 / 0 ms | 7 | 1,401 | 0.51 | 0.23 | 0.58 | 1.01 | 166 / 600 | 600 | 0.00, 0.73, 0.56, -0.77 |
| 0 | 5 / 5 ms | 5351 | 1,070,839 | -19.82 | -233.99 | 33.72 | 19.83 | 184 / 794 | -207 | -7.23, -5.44, -5.04, -2.11 |
| 0.5 | 5 / 5 ms | 530 | 106,061 | -4.66 | -25.88 | 0.64 | 4.67 | 25 / 603 | -4 | -1.19, -1.10, -1.70, -0.68 |
| 1 | 5 / 5 ms | 214 | 42,825 | -2.94 | -11.51 | -0.80 | 3.14 | 137 / 404 | -6 | -0.35, -1.08, -1.29, -0.23 |
| 2 | 5 / 5 ms | 40 | 8,004 | 0.22 | -1.38 | 0.62 | 0.69 | 156 / 599 | -1 | 0.32, 0.41, -0.25, -0.27 |
| 4 | 5 / 5 ms | 7 | 1,401 | 0.51 | 0.23 | 0.58 | 1.01 | 166 / 600 | 600 | 0.00, 0.73, 0.56, -0.77 |
| 0 | 25 / 25 ms | 5025 | 1,005,602 | -18.31 | -219.43 | 31.97 | 18.31 | 184 / 795 | -206 | -7.02, -4.88, -4.47, -1.94 |
| 0.5 | 25 / 25 ms | 592 | 118,470 | -4.98 | -28.68 | 0.94 | 4.99 | 27 / 603 | -4 | -1.36, -1.14, -1.76, -0.72 |
| 1 | 25 / 25 ms | 243 | 48,630 | -3.13 | -12.85 | -0.70 | 3.18 | 141 / 404 | 195 | -0.48, -1.09, -1.21, -0.35 |
| 2 | 25 / 25 ms | 50 | 10,004 | -0.55 | -2.55 | -0.05 | 1.09 | 161 / 402 | -2 | 0.31, -0.18, -0.38, -0.30 |
| 4 | 25 / 25 ms | 7 | 1,401 | 1.40 | 1.12 | 1.47 | 1.01 | 219 / 601 | 601 | 0.00, 1.55, 0.62, -0.77 |
| 0 | measured (~28 ms+jitter) / 50 ms | 4443 | 889,141 | -19.53 | -197.36 | 24.93 | 19.54 | 171 / 800 | -205 | -6.62, -6.07, -5.21, -1.64 |
| 0.5 | measured (~28 ms+jitter) / 50 ms | 658 | 131,678 | -5.32 | -31.66 | 1.26 | 5.33 | 33 / 603 | -6 | -1.39, -1.25, -1.90, -0.77 |
| 1 | measured (~28 ms+jitter) / 50 ms | 263 | 52,633 | -3.34 | -13.87 | -0.71 | 3.44 | 142 / 605 | 193 | -0.66, -1.38, -1.09, -0.21 |
| 2 | measured (~28 ms+jitter) / 50 ms | 60 | 12,006 | -0.88 | -3.28 | -0.28 | 1.21 | 162 / 402 | -3 | 0.18, -0.18, -0.60, -0.28 |
| 4 | measured (~28 ms+jitter) / 50 ms | 8 | 1,601 | 1.86 | 1.54 | 1.94 | 0.58 | 189 / 401 | 401 | 0.00, 1.55, 0.77, -0.46 |
## Zero latency vs latency (summary, risk-averse, touch quoting, half-spread 0)
| coin | 0/0 ms fills | gross | net @0.02% | 5/5 ms gross | 25/25 ms gross | measured/50 ms gross |
|---|---|---|---|---|---|---|
| BTC | 388 | −5.23 | −17.74 | −4.91 | −4.56 | −4.47 |
| ETH | 885 | −13.26 | −48.57 | −12.94 | −11.15 | −10.92 |
| SOL | 5,461 | −21.08 | −239.66 | −19.82 | −18.31 | −19.53 |

Latency reduces fills (BTC 388→320, ETH 885→705, SOL 5,461→4,443) and gross loss shrinks proportionally — i.e. the loss is per-fill adverse selection, not a latency effect. The strategy loses at zero latency already.

## Observations
- **Spread vs fee:** the quoted spread at BTC/ETH/SOL is almost always 1 tick = ~0.012 bp (BTC), ~0.043 bp (ETH), ~0.098 bp (SOL) of price, so the gross capture per round trip is a fraction of a basis point at best, vs a 4 bp maker round-trip fee (2×0.02%). Not close.
- **Wider quotes** (≥2 bp) are often profitable in the tiny sample but have 0–60 fills in 56 min and no statistical meaning (a handful of lucky or unlucky fills; SOL 4 bp: 7 fills).
- **Inventory risk:** mean absolute inventory ~$25–$340, max hits the $1,000 cap on ETH at touch; end-of-run inventory sometimes still non-zero ($160–$600) — gross PnL includes mark-to-mid on that. Max gross drawdown ≈ the total loss (PnL is monotonically negative at touch quoting), i.e. losses accrue steadily rather than from one big move. Per-quarter gross PnL is negative in all four quarters for every touch-quoting run, consistent across the hour (but the same single hour).
- **Per coin:** SOL trades most (5.5k fills at touch, $1.1M traded) so fees are largest ($218 at 0.02%) — net −$240. BTC fewest fills at touch (388) as its queue is deep and fast-moving at 1 tick.
- Hypothetical −0.005% rebate would make touch quoting on SOL net +$33 (zero latency) / +$25–34 across latency scenarios; on BTC/ETH still ≈ −$2 to −$4. That needs a market-maker fee tier, not a regular account, and still rests on one hour.

## Limitations / blockers
- 56 min, a **Sunday** (quiet, low volatility, thin flow) — not representative; no statistical significance (no confidence intervals, a single path).
- Simple strategy: fixed spread, no signal (no order-book imbalance/volatility adjustment, no GLFT parameter fitting); clip sizes small ($200) so queue-position effects dominate.
- Latency model is constant, no jitter beyond what's in the feed; the exchange-side matching is idealised (no market impact of our own orders on the book data, which is replayed).
- Clock drift on this box distorts measured feed latency.
- Blockers hit: Binance REST 451 (geo-block) → used websocket snapshot; no exchangeInfo → inferred tick/lot; no free historical L2 diff for futures → live collection; library converter memory → custom parser.
- Not a recommendation to trade. For real use you'd need multi-day/multi-regime data, a signal, and maker-fee-tier economics.

## Verdict
hftbacktest works and is a proper tool (latency, queue-position models, event-level replay), but a naive MM at regular-user fees is a clear fail on this data; the fee structure alone rules it out. Interesting next step if wanted: use hftbacktest only to test whether our existing signals can be executed passively (limit-order entries) vs market orders, where the maker/taker difference matters more than spread capture.
