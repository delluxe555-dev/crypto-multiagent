# validation report

status: OK

```json
{
 "json_files_parsed": 353,
 "json_unparsable_or_nonfinite": 0,
 "schema_missing_keys": {},
 "null_fields_all_runs": {
  "run.portfolio_context": 126,
  "run.started_at": 126,
  "analyst_reports.fundamentals": 126,
  "research_debate.rounds": 126,
  "risk_debate.latest_speaker": 126,
  "risk_debate.rounds": 126,
  "producer.version": 123,
  "producer.git_commit": 123,
  "run.asset_type": 123,
  "run.instrument_context": 123,
  "analyst_reports.news": 123,
  "research_debate.full_history": 123,
  "research_debate.last_response": 123,
  "risk_debate.aggressive_history": 123,
  "risk_debate.conservative_history": 123,
  "risk_debate.neutral_history": 123,
  "risk_debate.full_history": 123,
  "research_manager_plan": 123,
  "memory.memory_note": 105,
  "run.finished_at": 96,
  "memory.past_context": 96,
  "producer.quick_think_llm": 93,
  "run.finished_at_source": 93,
  "trader_proposal": 93,
  "producer.llm_provider": 92,
  "analyst_reports.market": 92,
  "analyst_reports.sentiment": 92,
  "research_debate.bull_history": 92,
  "research_debate.bear_history": 92,
  "final.confidence": 64,
  "mtf": 31,
  "numeric_context.last_price": 7,
  "producer.llm_providers_used": 1,
  "producer.deep_think_llm": 1,
  "run.duration_seconds": 1,
  "run.llm_calls": 1,
  "run.dry_run": 1
 },
 "null_fields_by_variant": {
  "full": {
   "producer.version": 29,
   "producer.git_commit": 29,
   "run.asset_type": 29,
   "run.instrument_context": 29,
   "run.portfolio_context": 29,
   "run.started_at": 29,
   "analyst_reports.news": 29,
   "analyst_reports.fundamentals": 29,
   "research_debate.full_history": 29,
   "research_debate.last_response": 29,
   "research_debate.rounds": 29,
   "risk_debate.aggressive_history": 29,
   "risk_debate.conservative_history": 29,
   "risk_debate.neutral_history": 29,
   "risk_debate.full_history": 29,
   "risk_debate.latest_speaker": 29,
   "risk_debate.rounds": 29,
   "research_manager_plan": 29,
   "mtf": 29,
   "memory.memory_note": 8
  },
  "mtf": {
   "producer.version": 92,
   "producer.git_commit": 92,
   "producer.llm_provider": 92,
   "producer.quick_think_llm": 92,
   "run.asset_type": 92,
   "run.instrument_context": 92,
   "run.portfolio_context": 92,
   "run.started_at": 92,
   "run.finished_at": 92,
   "run.finished_at_source": 92,
   "analyst_reports.market": 92,
   "analyst_reports.sentiment": 92,
   "analyst_reports.news": 92,
   "analyst_reports.fundamentals": 92,
   "research_debate.bull_history": 92,
   "research_debate.bear_history": 92,
   "research_debate.full_history": 92,
   "research_debate.last_response": 92,
   "research_debate.rounds": 92,
   "risk_debate.aggressive_history": 92,
   "risk_debate.conservative_history": 92,
   "risk_debate.neutral_history": 92,
   "risk_debate.full_history": 92,
   "risk_debate.latest_speaker": 92,
   "risk_debate.rounds": 92,
   "memory.past_context": 92,
   "memory.memory_note": 92,
   "research_manager_plan": 92,
   "trader_proposal": 92,
   "final.confidence": 64,
   "numeric_context.last_price": 3
  },
  "full_1d": {
   "producer.version": 2,
   "producer.git_commit": 2,
   "run.asset_type": 2,
   "run.instrument_context": 2,
   "run.portfolio_context": 2,
   "run.started_at": 2,
   "analyst_reports.news": 2,
   "analyst_reports.fundamentals": 2,
   "research_debate.full_history": 2,
   "research_debate.last_response": 2,
   "research_debate.rounds": 2,
   "risk_debate.aggressive_history": 2,
   "risk_debate.conservative_history": 2,
   "risk_debate.neutral_history": 2,
   "risk_debate.full_history": 2,
   "risk_debate.latest_speaker": 2,
   "risk_debate.rounds": 2,
   "memory.memory_note": 2,
   "research_manager_plan": 2,
   "mtf": 2,
   "producer.llm_providers_used": 1,
   "producer.deep_think_llm": 1,
   "producer.quick_think_llm": 1,
   "run.finished_at": 1,
   "run.finished_at_source": 1,
   "run.duration_seconds": 1,
   "run.llm_calls": 1,
   "run.dry_run": 1,
   "memory.past_context": 1,
   "trader_proposal": 1,
   "numeric_context.last_price": 1
  },
  "tradingagents": {
   "run.portfolio_context": 3,
   "run.started_at": 3,
   "run.finished_at": 3,
   "analyst_reports.fundamentals": 3,
   "research_debate.rounds": 3,
   "risk_debate.latest_speaker": 3,
   "risk_debate.rounds": 3,
   "memory.past_context": 3,
   "memory.memory_note": 3,
   "numeric_context.last_price": 3
  }
 },
 "string_numbers_in_mapped_sections": 0,
 "string_numbers_examples": [],
 "string_numbers_in_raw_native_(bot's own, left verbatim)": 0,
 "string_numbers_raw_examples": [],
 "nan_inf_in_files": 0,
 "iso_time_violations": 0,
 "iso_time_violation_examples": [],
 "text_integrity_checks": 872,
 "text_shortened_or_changed": [],
 "secret_pattern_hits": [],
 "counts": {
  "runs": 126,
  "runs_by_variant": {
   "full/1h": 29,
   "mtf/mtf-1h": 92,
   "full_1d/1d": 2,
   "tradingagents/None": 3
  },
  "messages": 0,
  "reports_files": 76,
  "configs": 126,
  "backtests_files": 97,
  "backtests_manifest_entries": 88,
  "code_files": 108,
  "scans": 39,
  "raw_llm_txt": 371,
  "datasets_referenced_not_copied": 21
 },
 "handoff_total_bytes": 21761926,
 "handoff_total_mb": 21.76,
 "summary_table_rows": 123,
 "decision_distribution_bot_values": {
  "ALL": {
   "SELL": 54,
   "HOLD": 67,
   "BUY": 2
  },
  "full/1h": {
   "SELL": 26,
   "HOLD": 2,
   "BUY": 1
  },
  "mtf/mtf-1h": {
   "HOLD": 64,
   "SELL": 27,
   "BUY": 1
  },
  "full_1d/1d": {
   "HOLD": 1,
   "SELL": 1
  }
 },
 "decision_distribution_long_short_hold": {
  "ALL": {
   "short": 54,
   "hold": 67,
   "long": 2
  },
  "full/1h": {
   "short": 26,
   "hold": 2,
   "long": 1
  },
  "mtf/mtf-1h": {
   "hold": 64,
   "short": 27,
   "long": 1
  },
  "full_1d/1d": {
   "hold": 1,
   "short": 1
  }
 },
 "confidence": {
  "scale": "0-100 integers (guven); trader min_confidence 65",
  "stats": {
   "ALL": {
    "n": 59,
    "mean": 74.47,
    "min": 0,
    "max": 85,
    "median": 75
   },
   "full/1h": {
    "n": 29,
    "mean": 74.93,
    "min": 0,
    "max": 85,
    "median": 78
   },
   "ALL (BUY/SELL only)": {
    "n": 56,
    "mean": 76.45,
    "min": 60,
    "max": 85,
    "median": 75.0
   },
   "mtf/mtf-1h": {
    "n": 28,
    "mean": 74.21,
    "min": 60,
    "max": 85,
    "median": 75.0
   },
   "full_1d/1d": {
    "n": 2,
    "mean": 71.5,
    "min": 68,
    "max": 75,
    "median": 71.5
   }
  },
  "all_values_integers_in_0_100": true,
  "n_runs_without_confidence": 64,
  "note": "MTF HOLD (not aligned) has guven=None by bot rule"
 },
 "paper_trades": {
  "ledger_status_counts": {
   "ledger(paper.py) status=no_trade": 29,
   "MTF/other ledger.json record status=no_trade": 88,
   "no kagit_islem in file": 1,
   "ledger(paper.py) status=open": 1,
   "MTF/other ledger.json record status=open": 0,
   "MTF/other ledger.json record status=closed": 1
  },
  "blocked_reasons": {
   "karar BUY değil (yalnızca long/nakit kâğıt işlem)": 29,
   "(mtf record) karar BUY değil (yalnızca long/nakit kâğıt işlem)": 88
  },
  "live_trader_positions_linked": {
   "live_trader_position:closed/stop": 12,
   "live_trader_position:closed/hedef": 6,
   "live_trader_position:open": 2,
   "live_trader_position:closed/süre doldu (24s)": 6
  },
  "live_trader_positions_total_in_ledger": 13,
  "runs_that_opened_live_position": 26,
  "runs_without_live_position": 97
 },
 "timestamp_check": {
  "signal_time_field": "run JSON data_date / time = OPEN time of the last CLOSED candle, UTC (data.klines drops candles with close_time >= now; 1d = date only, 00:00 UTC)",
  "bar_close_utc": "= open + interval; entry (live) happens when trader cycle runs, i.e. AFTER bar close",
  "n_checked": 123,
  "gap_run_written_minus_bar_close_minutes": {
   "min": 1.6,
   "median": 5.8,
   "max": 896522.3
  },
  "runs_with_bar_time_inconsistent_with_write_time(future or >6h stale)": 2,
  "anomalies": [
   [
    "outputs/KATUSDT_1h_2026-10-24T0700.json",
    "STALE: bar close 2026-10-24T08:00:00Z but recorded_at 2026-10-24T14:28:19Z (gap 6.5 h) -> bar date inconsistent with write time"
   ],
   [
    "outputs/LITUSDT_mtf-1h_2025-02-10T0200.json",
    "STALE: bar close 2025-02-10T03:00:00Z but file_mtime 2026-10-25T17:02:21Z (gap 14942.0 h) -> bar date inconsistent with write time"
   ]
  ],
  "live_positions_opened_before_bar_close": 0,
  "timezone_handling": "bar times already UTC (no conversion). recorded_at/opened_at/closed_at/created_at carry +0300 (Europe/Istanbul) and were converted to Z by their own offset. file_mtime_utc derived from epoch. 'MTF' files carry no write-time field -> file mtime used.",
  "caveat": "for MTF files file_mtime may be later than the true run time (files can be rewritten); this check can only catch bar times that lie in the future relative to write time"
 },
 "warnings": [
  "2 runs with bar time inconsistent with write time"
 ],
 "failures": [],
 "ok": true
}
```
