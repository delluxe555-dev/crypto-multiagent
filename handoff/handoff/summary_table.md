# Summary table of all bot runs (bot's own values; sl_llm/tp_llm = LLM proposal, sl_rule_layer = risk_rules stop, sl_live/tp_live = live paper trader's actual stop/target when a position was opened)

| symbol | tf | date_bar_open_utc | decision | confidence | sl_llm | tp_llm | sl_rule_layer | sl_live | tp_live | result | fwd_ret_pct_24bars |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LITUSDT | mtf-1h | 2025-02-10 02:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | 1d | 2026-10-22 00:00:00 | HOLD | 68 | 79800.0 | 83500.0 |  |  |  | no_live_position; no ledger record |  |
| ETHUSDT | 1d | 2026-10-22 00:00:00 | SELL | 75 | 2552.06 | 2155.8 | 2244.79 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ADAUSDT | 1h | 2026-10-23 21:00:00 | HOLD | 45 | 0.205 | 0.22 | 0.2 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ADAUSDT | mtf-1h | 2026-10-23 21:00:00 | SELL | 70 | 0.2135 | 0.203 | 0.21 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | 1h | 2026-10-23 21:00:00 | SELL | 75 | 82150.0 | 80250.0 | 80696.35 | 81801.76 | 80095.91 | live:closed/hedef/pnl_usd=8.11 | -1.181 |
| BTCUSDT | mtf-1h | 2026-10-23 21:00:00 | SELL | 70 | 82060.88 | 80050.0 | 80866.93 | 81801.76 | 80095.91 | live:closed/hedef/pnl_usd=8.11 | -1.181 |
| ETHUSDT | 1h | 2026-10-23 21:00:00 | SELL | 75 | 2425.0 | 2360.5 | 2370.96 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -2.49 |
| ETHUSDT | mtf-1h | 2026-10-23 21:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -2.49 |
| STRKUSDT | mtf-1h | 2026-10-23 21:00:00 | HOLD |  | 0.0515 | 0.0485 | 0.05 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -7.257 |
| WLDUSDT | mtf-1h | 2026-10-23 21:00:00 | HOLD |  | 0.5 | 0.53 | 0.5 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -8.862 |
| ZROUSDT | mtf-1h | 2026-10-23 21:00:00 | HOLD |  | 1.78 | 1.68 | 1.69 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ADAUSDT | mtf-1h | 2026-10-23 22:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-23 22:00:00 | HOLD |  | 2351.55 | 2390.0 | 2351.55 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -0.863 |
| GRAMUSDT | mtf-1h | 2026-10-23 22:00:00 | HOLD |  | 1.15 | 1.26 | 1.15 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | mtf-1h | 2026-10-23 22:00:00 | HOLD |  | 0.46 | 0.5 | 0.46 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -2.579 |
| ETHUSDT | 1h | 2026-10-23 23:00:00 | SELL | 70 | 2415.0 | 2351.0 | 2351.46 | 2422.2420642857146 | 2331.9027785714293 | live:closed/hedef/pnl_usd=11.16 | -1.205 |
| ETHUSDT | mtf-1h | 2026-10-23 23:00:00 | SELL | 65 | 2415.0 | 2325.0 | 2360.5 | 2422.2420642857146 | 2331.9027785714293 | live:closed/hedef/pnl_usd=11.16 | -1.205 |
| GRAMUSDT | mtf-1h | 2026-10-23 23:00:00 | HOLD |  | 1.25 | 1.17 | 1.19 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| PUMPUSDT | 1h | 2026-10-23 23:00:00 | HOLD | 0 | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| PUMPUSDT | mtf-1h | 2026-10-23 23:00:00 | SELL | 75 | 0.00445 | 0.00405 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | mtf-1h | 2026-10-23 23:00:00 | HOLD |  | 0.51 | 0.44 | 0.47 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -2.777 |
| TIAUSDT | 1h | 2026-10-24 02:00:00 | SELL | 75 | 0.5672 | 0.5188 | 0.53 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| TIAUSDT | mtf-1h | 2026-10-24 02:00:00 | SELL | 80 | 0.5535 | 0.536 | 0.53 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| TIAUSDT | 1h | 2026-10-24 03:00:00 | SELL | 75 | 0.568 | 0.525 | 0.53 | 0.5745527714285715 | 0.5164813428571429 | live:closed/süre doldu (24s)/pnl_usd=6.3 |  |
| TIAUSDT | mtf-1h | 2026-10-24 03:00:00 | SELL | 65 | 0.563 | 0.536 | 0.53 | 0.5745527714285715 | 0.5164813428571429 | live:closed/süre doldu (24s)/pnl_usd=6.3 |  |
| WLDUSDT | 1h | 2026-10-24 03:00:00 | SELL | 85 | 0.508 | 0.449 | 0.46 | 0.5031304285714285 | 0.44970185714285715 | live:closed/süre doldu (24s)/pnl_usd=4.85 |  |
| WLDUSDT | mtf-1h | 2026-10-24 03:00:00 | SELL | 75 | 0.4885 | 0.471 | 0.46 | 0.5031304285714285 | 0.44970185714285715 | live:closed/süre doldu (24s)/pnl_usd=4.85 |  |
| INITUSDT | mtf-1h | 2026-10-24 05:00:00 | HOLD |  | 0.135 | 0.147 | 0.14 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| INITUSDT | 1h | 2026-10-24 06:00:00 | BUY | 65 | 0.14179 | 0.15949 | 0.14 |  |  | no_live_position; ledger:open |  |
| INITUSDT | mtf-1h | 2026-10-24 06:00:00 | SELL | 65 | 0.1555 | 0.1418 | 0.14 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | 1h | 2026-10-24 07:00:00 | SELL | 75 | 0.00497 | 0.00433 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | mtf-1h | 2026-10-24 07:00:00 | BUY | 75 | 0.00443349 | 0.00483052 | 0.0 |  |  | no_live_position; ledger:closed |  |
| BTCUSDT | 1h | 2026-10-24 13:00:00 | SELL | 78 | 81254.44 | 79706.56 | 80209.82 | 80746.05077714285 | 79540.94363428574 | live:closed/hedef/pnl_usd=5.32 |  |
| BTCUSDT | mtf-1h | 2026-10-24 13:00:00 | SELL | 82 | 81254.44 | 79587.0 | 80330.33 | 80746.05077714285 | 79540.94363428574 | live:closed/hedef/pnl_usd=5.32 |  |
| ETHUSDT | 1h | 2026-10-24 13:00:00 | SELL | 85 | 2392.0 | 2305.0 | 2349.46 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-24 13:00:00 | SELL | 75 | 2385.0 | 2352.0 | 2354.16 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | -1.433 |
| KATUSDT | mtf-1h | 2026-10-24 13:00:00 | HOLD |  | 0.00431 | 0.00488 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| LAUSDT | mtf-1h | 2026-10-24 13:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ONDOUSDT | 1h | 2026-10-24 13:00:00 | SELL | 75 | 0.4127 | 0.3865 | 0.4 | 0.4098844142857143 | 0.39117012857142863 | live:closed/stop/pnl_usd=-10.22 |  |
| ONDOUSDT | mtf-1h | 2026-10-24 13:00:00 | SELL | 82 | 0.413 | 0.3945 | 0.4 | 0.4098844142857143 | 0.39117012857142863 | live:closed/stop/pnl_usd=-10.22 |  |
| TRUMPUSDT | 1h | 2026-10-24 13:00:00 | SELL | 85 | 1.723 | 1.615 | 1.63 | 1.6826030714285716 | 1.601531642857143 | live:closed/stop/pnl_usd=-11.46 |  |
| TRUMPUSDT | mtf-1h | 2026-10-24 13:00:00 | SELL | 82 | 1.708 | 1.612 | 1.64 | 1.6826030714285716 | 1.601531642857143 | live:closed/stop/pnl_usd=-11.46 |  |
| AAVEUSDT | mtf-1h | 2026-10-24 14:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| DOGEUSDT | mtf-1h | 2026-10-24 14:00:00 | HOLD |  | 0.082 | 0.075 | 0.08 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-24 14:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | 0.051 |
| XPLUSDT | mtf-1h | 2026-10-24 14:00:00 | HOLD |  | 0.0755 | 0.07 | 0.07 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| AAVEUSDT | 1h | 2026-10-24 15:00:00 | SELL | 85 | 138.65 | 130.9 | 132.41 | 137.82099142857143 | 130.99956285714285 | live:closed/stop/pnl_usd=-10.07 |  |
| AAVEUSDT | mtf-1h | 2026-10-24 15:00:00 | SELL | 65 | 136.35 | 133.55 | 133.09 | 137.82099142857143 | 130.99956285714285 | live:closed/stop/pnl_usd=-10.07 |  |
| BTCUSDT | 1h | 2026-10-24 15:00:00 | SELL | 85 | 80550 | 78900 | 79181.46 | 80336.19453857142 | 78780.46596714287 | live:closed/stop/pnl_usd=-10.12 |  |
| BTCUSDT | mtf-1h | 2026-10-24 15:00:00 | SELL | 85 | 80455 | 78845 | 79337.03 | 80336.19453857142 | 78780.46596714287 | live:closed/stop/pnl_usd=-10.12 |  |
| DOGEUSDT | mtf-1h | 2026-10-24 15:00:00 | HOLD |  | 0.0812 | 0.0741 | 0.07 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-24 15:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | 1.649 |
| SUIUSDT | 1h | 2026-10-24 15:00:00 | SELL | 85 | 0.9435 | 0.912 | 0.91 | 0.9427234642857143 | 0.8960091785714286 | live:closed/süre doldu (24s)/pnl_usd=1.4 |  |
| SUIUSDT | mtf-1h | 2026-10-24 15:00:00 | SELL | 75 | 0.9535 | 0.912 | 0.91 | 0.9427234642857143 | 0.8960091785714286 | live:closed/süre doldu (24s)/pnl_usd=1.4 |  |
| DOGEUSDT | mtf-1h | 2026-10-24 16:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| DOTUSDT | 1h | 2026-10-24 16:00:00 | SELL | 80 | 1.061 | 1.01 | 1.01 | 1.0519145714285716 | 0.9908431428571429 | live:closed/stop/pnl_usd=-2.25 |  |
| DOTUSDT | mtf-1h | 2026-10-24 16:00:00 | SELL | 85 | 1.062 | 0.983 | 1.01 | 1.0519145714285716 | 0.9908431428571429 | live:closed/stop/pnl_usd=-2.25 |  |
| ETHUSDT | 1h | 2026-10-24 16:00:00 | SELL | 85 | 2344.0 | 2230.0 | 2286.42 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-24 16:00:00 | SELL | 85 | 2332.0 | 2263.0 | 2294.41 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) | 1.666 |
| ETHUSDT | 1h | 2026-10-24 17:00:00 | SELL | 85 | 2345.5 | 2282.46 | 2290.97 | 2358.680505714286 | 2277.9697914285716 | live:closed/stop/pnl_usd=-10.34 |  |
| ETHUSDT | mtf-1h | 2026-10-24 17:00:00 | SELL | 85 | 2346.0 | 2282.0 | 2299.04 | 2358.680505714286 | 2277.9697914285716 | live:closed/stop/pnl_usd=-10.34 |  |
| ANIMEUSDT | mtf-1h | 2026-10-24 18:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | mtf-1h | 2026-10-24 18:00:00 | HOLD |  | 81250 | 79700 | 80002.35 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-24 19:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | mtf-1h | 2026-10-24 19:00:00 | HOLD |  |  |  | 79957.21 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-24 20:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | mtf-1h | 2026-10-24 20:00:00 | HOLD |  |  |  | 79989.27 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | mtf-1h | 2026-10-24 20:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| BTCUSDT | 1h | 2026-10-24 21:00:00 | SELL | 70 | 81250 | 79706 | 79707.18 | 81138.60313785714 | 79361.5352807143 | live:open |  |
| BTCUSDT | mtf-1h | 2026-10-24 21:00:00 | SELL | 70 | 80850 | 79220 | 79884.89 | 81138.60313785714 | 79361.5352807143 | live:open |  |
| KATUSDT | mtf-1h | 2026-10-24 21:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-24 22:00:00 | HOLD |  | 0.00356 | 0.00324 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | mtf-1h | 2026-10-24 22:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-24 23:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | 1h | 2026-10-24 23:00:00 | SELL | 80 | 2385.0 | 2320.0 | 2323.09 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-24 23:00:00 | SELL | 65 | 2388.5 | 2327.5 | 2332.02 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| LTCUSDT | 1h | 2026-10-24 23:00:00 | SELL | 75 | 57.76 | 56.18 | 56.13 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| LTCUSDT | mtf-1h | 2026-10-24 23:00:00 | SELL | 60 | 57.75 | 56.15 | 56.36 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-25 00:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 00:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | mtf-1h | 2026-10-25 00:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| LAUSDT | mtf-1h | 2026-10-25 00:00:00 | HOLD |  |  |  | 0.05 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-25 01:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 01:00:00 | HOLD |  |  |  | 2337.78 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| KATUSDT | mtf-1h | 2026-10-25 01:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-25 02:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | 1h | 2026-10-25 02:00:00 | SELL | 85 | 2397.0 | 2320.0 | 2329.86 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 02:00:00 | SELL | 65 | 2387 | 2335 | 2338.86 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | 1h | 2026-10-25 02:00:00 | SELL | 75 | 0.0479 | 0.0457 | 0.04 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | mtf-1h | 2026-10-25 02:00:00 | SELL | 75 | 0.0488 | 0.0456 | 0.05 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ANIMEUSDT | mtf-1h | 2026-10-25 04:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 04:00:00 | HOLD |  |  |  | 2344.81 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| XRPUSDT | mtf-1h | 2026-10-25 04:00:00 | HOLD |  | 1.295 | 1.353 | 1.29 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 05:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | 1h | 2026-10-25 05:00:00 | SELL | 80 | 0.048 | 0.04417 | 0.04 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | mtf-1h | 2026-10-25 05:00:00 | SELL | 75 | 0.0515 | 0.0456 | 0.04 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 07:00:00 | HOLD |  | 2374.02 | 2292.25 | 2330.02 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | mtf-1h | 2026-10-25 07:00:00 | HOLD |  |  |  | 0.05 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 08:00:00 | HOLD |  | 2373.0 | 2297.0 | 2317.85 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | mtf-1h | 2026-10-25 08:00:00 | HOLD |  |  |  | 0.04 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | 1h | 2026-10-25 08:00:00 | SELL | 85 | 0.4563 | 0.4181 | 0.43 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | mtf-1h | 2026-10-25 08:00:00 | SELL | 82 | 0.459 | 0.4181 | 0.43 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 11:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| STRKUSDT | mtf-1h | 2026-10-25 11:00:00 | HOLD |  | 0.0478 | 0.0443 | 0.04 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | 1h | 2026-10-25 11:00:00 | SELL | 75 | 0.4621 | 0.43 | 0.44 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| WLDUSDT | mtf-1h | 2026-10-25 11:00:00 | SELL | 75 | 0.463 | 0.43 | 0.44 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| DASHUSDT | mtf-1h | 2026-10-25 12:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | 1h | 2026-10-25 12:00:00 | SELL | 80 | 2365.0 | 2230.0 | 2308.4 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 12:00:00 | SELL | 70 | 2365.5 | 2305.0 | 2315.02 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| UNIUSDT | mtf-1h | 2026-10-25 12:00:00 | HOLD |  |  |  | 6.62 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| DASHUSDT | mtf-1h | 2026-10-25 13:00:00 | HOLD |  |  |  | 51.83 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 13:00:00 | HOLD |  |  |  | 2315.05 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ZECUSDT | mtf-1h | 2026-10-25 13:00:00 | HOLD |  |  |  | 1180.25 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| DASHUSDT | mtf-1h | 2026-10-25 14:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ENAUSDT | mtf-1h | 2026-10-25 14:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 14:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ENAUSDT | mtf-1h | 2026-10-25 15:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 15:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| NEARUSDT | mtf-1h | 2026-10-25 15:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ENAUSDT | mtf-1h | 2026-10-25 16:00:00 | HOLD |  | 0.0 | 0.0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| ETHUSDT | mtf-1h | 2026-10-25 16:00:00 | HOLD |  | 0 | 0 | 0.0 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
| NEARUSDT | mtf-1h | 2026-10-25 16:00:00 | HOLD |  |  |  | 4.56 |  |  | no_live_position; ledger:no_trade (karar BUY değil (yalnızca long/nakit kâğıt işlem)) |  |
