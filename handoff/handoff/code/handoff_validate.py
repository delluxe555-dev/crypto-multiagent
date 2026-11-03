#!/usr/bin/env python3
"""handoff_validate.py - validates ./handoff (schema handoff/1.0). Read-only on sources. Writes handoff/validation_report.json|md. Exit 1 on hard failures."""
import os, re, json, math, hashlib, collections, datetime as dt, statistics, csv
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "handoff"); OUTS = os.path.join(HERE, "outputs")
REQ = ["schema_version", "exported_at", "producer", "run", "final", "analyst_reports", "research_debate", "research_manager_plan", "trader_proposal", "risk_debate", "memory", "numeric_context",
       "data_used", "data_missing", "not_produced", "mapping_notes", "not_investment_advice", "raw_native"]
REQ_BOT = ["risk", "confidence_scale", "entry_reference", "sl_method", "tp_method", "execution_assumptions", "llm_layer", "deterministic_rules"]
Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"); NUMSTR = re.compile(r"^\s*[-+]?\d+(\.\d+)?([eE][-+]?\d+)?\s*$")
SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{20,}|\b\d{8,}:[A-Za-z0-9_-]{30,}|Bearer\s+[A-Za-z0-9._-]{20,}|[A-Za-z0-9_]*API_KEY[ \t]*=[ \t]*\S{8,})")
FAIL, WARN = [], []; R = {}
def bad(c): raise ValueError("non-finite constant " + c)
def jl(p):
    with open(p, encoding="utf-8") as f: return json.load(f, parse_constant=bad)
def sha(s): return hashlib.sha256(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()
def shaf(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk(v, f"{path}[{i}]")
    else: yield path, o
def clean(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)): return None
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list): return [clean(v) for v in o]
    return o
def num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)

man = jl(os.path.join(OUT, "manifest.json")); runs = []
for r in man["runs"]:
    p = os.path.join(OUT, r["file"])
    try: o = jl(p)
    except Exception as e: FAIL.append(f"{r['file']}: unparsable/non-finite: {e}"); continue
    runs.append((r, o))
# 1. parse all json
nparse = nbad = 0
for root, _, fs in os.walk(OUT):
    for f in fs:
        if f.endswith(".json"):
            nparse += 1
            try: jl(os.path.join(root, f))
            except Exception as e: nbad += 1; FAIL.append(f"{os.path.relpath(os.path.join(root, f), OUT)}: {e}")
R["json_files_parsed"] = nparse; R["json_unparsable_or_nonfinite"] = nbad
# 2. schema fields / nulls
missing = collections.defaultdict(list); nulls = collections.Counter(); nulls_by_kind = collections.defaultdict(collections.Counter)
for r, o in runs:
    bot = o["producer"]["framework"].startswith("crypto-agents")
    for k in REQ + (REQ_BOT if bot else []):
        if k not in o: missing[k].append(r["file"])
    for top in ("producer", "run", "final", "analyst_reports", "research_debate", "risk_debate", "memory"):
        for k, v in (o.get(top) or {}).items():
            if v is None: nulls[f"{top}.{k}"] += 1; nulls_by_kind[r["variant"]][f"{top}.{k}"] += 1
    for k in ("research_manager_plan", "trader_proposal", "mtf"):
        if k in o and o[k] is None: nulls[k] += 1; nulls_by_kind[r["variant"]][k] += 1
    if o["numeric_context"].get("last_price") is None: nulls["numeric_context.last_price"] += 1; nulls_by_kind[r["variant"]]["numeric_context.last_price"] += 1
    if o["not_investment_advice"] is not True: FAIL.append(f"{r['file']}: not_investment_advice != true")
    # every null in the mapped main sections must be declared in not_produced (text match on field name)
    np_txt = " ".join(o["not_produced"]).lower()
    for top, k in [("run", "asset_type"), ("run", "instrument_context"), ("run", "started_at"), ("producer", "version"), ("producer", "git_commit")]:
        if o[top].get(k) is None and k not in np_txt and bot: WARN.append(f"{r['file']}: {top}.{k} null but not in not_produced")
R["schema_missing_keys"] = {k: len(v) for k, v in missing.items()}
if missing: FAIL.append(f"missing required keys: {R['schema_missing_keys']}")
R["null_fields_all_runs"] = dict(nulls.most_common()); R["null_fields_by_variant"] = {k: dict(v.most_common()) for k, v in nulls_by_kind.items()}
# 3. string numbers / NaN / ISO times (mapped sections only; raw_native reported separately)
SKIP_TEXT_KEYS = ("decision_text", "reason", "gerekce", "code", "driver_script_source")
str_num_mapped, str_num_raw, nonz_time, iso_bad = [], [], [], []
TIMEKEYS = ("started_at", "finished_at", "signal_bar_open_utc", "exported_at", "file_mtime_utc")
for r, o in runs:
    for path, v in walk({k: x for k, x in o.items() if k != "raw_native"}):
        if isinstance(v, str) and NUMSTR.match(v) and not path.startswith("/inputs_seen") and "/stop_kaynak" not in path: str_num_mapped.append((r["file"], path, v))
        if path.split("/")[-1] in TIMEKEYS and v is not None and not Z.match(str(v)): iso_bad.append((r["file"], path, v))
    for path, v in walk(o["raw_native"]):
        if isinstance(v, str) and NUMSTR.match(v): str_num_raw.append((r["file"], path, v))
R["string_numbers_in_mapped_sections"] = len(str_num_mapped); R["string_numbers_examples"] = str_num_mapped[:8]
R["string_numbers_in_raw_native_(bot's own, left verbatim)"] = len(str_num_raw); R["string_numbers_raw_examples"] = [list(x) for x in str_num_raw[:8]]
R["nan_inf_in_files"] = nbad; R["iso_time_violations"] = len(iso_bad); R["iso_time_violation_examples"] = iso_bad[:5]
if str_num_mapped: FAIL.append(f"{len(str_num_mapped)} numeric strings in mapped sections")
if iso_bad: FAIL.append(f"{len(iso_bad)} non-ISO-Z times")
# 4. text integrity vs source
len_diff = []; checks = 0
def chk(label, a, b, f):
    global checks; checks += 1
    if a is None and b is None: return
    if a is None or b is None or sha(a) != sha(b) or len(a) != len(b): len_diff.append(f"{f}: {label} len {len(a or '')} vs {len(b or '')}")
for r, o in runs:
    src = os.path.join(HERE, o["run"]["source_file"]) if o["run"].get("source_file", "").startswith("outputs") else None
    if src and os.path.exists(src):
        raw = clean(jl_raw := json.load(open(src, encoding="utf-8")))
        if json.dumps(o["raw_native"], sort_keys=True, ensure_ascii=False) != json.dumps(raw, sort_keys=True, ensure_ascii=False): FAIL.append(f"{r['file']}: raw_native != source")
        checks += 1
        if r["variant"] != "mtf":
            for lab, a, b in (("market", o["analyst_reports"]["market"], raw.get("teknik_analist")), ("sentiment", o["analyst_reports"]["sentiment"], raw.get("duygu_analisti")),
                              ("bull", o["research_debate"]["bull_history"], raw.get("boga")), ("bear", o["research_debate"]["bear_history"], raw.get("ayi")),
                              ("memory", o["memory"]["past_context"], raw.get("memory")), ("lessons", o["memory"]["memory_note"], raw.get("lessons_block"))): chk(lab, a, b, r["file"])
            h = raw.get("hakem") or {}; dt_ = o["final"]["decision_text"] or ""
            if h.get("gerekce") and h["gerekce"] not in dt_ and r["variant"] != "mtf": len_diff.append(f"{r['file']}: hakem.gerekce not contained in decision_text")
            for m in (h.get("maddeler") or []):
                if m not in dt_: len_diff.append(f"{r['file']}: hakem madde missing in decision_text"); break
            if o["final"]["rating"] != h.get("karar"): FAIL.append(f"{r['file']}: rating != hakem.karar")
        else:
            if o["final"]["rating"] != (raw.get("karar") or {}).get("karar"): FAIL.append(f"{r['file']}: rating != karar.karar")
            chk("decision_text", o["final"]["decision_text"], (raw.get("karar") or {}).get("gerekce"), r["file"])
        # raw .txt copies vs cache
        base = os.path.basename(src)[:-5]
        for suf in ("_v2.json", ".json"):
            cp = os.path.join(OUTS, ".cache", base + suf)
            if os.path.exists(cp):
                c = json.load(open(cp, encoding="utf-8"))
                for k, v in c.items():
                    if isinstance(v, str):
                        tp = os.path.join(OUT, "raw", o["run"]["run_id"], k + ".txt")
                        if not os.path.exists(tp) or open(tp, encoding="utf-8").read() != v: len_diff.append(f"{r['file']}: raw/{k}.txt differs from cache")
                        checks += 1
                break
    else:  # TradingAgents
        ta = o["raw_native"]; st = ta["final_state.json"]["state"]; lg = ta["full_states_log_2026-10-22.json"]
        for lab, a, b in (("market", o["analyst_reports"]["market"], st.get("market_report")), ("sentiment", o["analyst_reports"]["sentiment"], st.get("sentiment_report")), ("news", o["analyst_reports"]["news"], st.get("news_report")),
                          ("final", o["final"]["decision_text"], st.get("final_trade_decision")), ("plan", o["research_manager_plan"], st.get("investment_plan")), ("trader", o["trader_proposal"], st.get("trader_investment_plan")),
                          ("bull", o["research_debate"]["bull_history"], lg["investment_debate_state"].get("bull_history")), ("risk_hist", o["risk_debate"]["full_history"], lg["risk_debate_state"].get("history"))): chk(lab, a, b, r["file"])
# md reports vs source
for rep in man["reports"]:
    p = os.path.join(OUT, rep["file"]); checks += 1
    if not os.path.exists(p): FAIL.append("missing report " + rep["file"]); continue
    if rep["file"].endswith(".md") and re.search(r"reports/[0-9a-f-]{36}/[A-Z0-9]+USDT_", rep["file"]):
        s = os.path.join(OUTS, os.path.basename(rep["file"]))
        if shaf(p) != shaf(s): len_diff.append(f"{rep['file']}: md differs from source")
for c in man["code_files"]:
    p = os.path.join(OUT, c); s = None
    if c.startswith("code/") and "/" not in c[5:] and c not in ("code/config.json", "code/.env.example"):
        s = os.path.join(HERE, c[5:])
        if os.path.exists(s) and shaf(p) != shaf(s): len_diff.append(f"{c}: differs from source")
R["text_integrity_checks"] = checks; R["text_shortened_or_changed"] = len_diff
if len_diff: FAIL.append(f"{len(len_diff)} text integrity differences")
# 5. secrets
sec = []
for root, _, fs in os.walk(OUT):
    for f in fs:
        if f.endswith((".pyc", ".npz", ".gz")): continue
        p = os.path.join(root, f); t = open(p, encoding="utf-8", errors="replace").read()
        m = SECRET_RE.search(t)
        if m: sec.append((os.path.relpath(p, OUT), m.group(0)[:6] + "***"))
        if re.search(r"(^|/)\.env$", p): sec.append((p, ".env file"))
R["secret_pattern_hits"] = sec
if sec: FAIL.append(f"secret-like strings: {sec[:5]}")
# 6. counts
cnt = lambda d: sum(len(fs) for _, _, fs in os.walk(os.path.join(OUT, d)))
R["counts"] = {"runs": len(runs), "runs_by_variant": dict(collections.Counter(r["variant"] + "/" + str(r["timeframe"]) for r, _ in runs)), "messages": cnt("messages"), "reports_files": len(man["reports"]), "configs": len(man["configs"]),
               "backtests_files": cnt("backtests"), "backtests_manifest_entries": len(man["backtests"]), "code_files": cnt("code"), "scans": len(man["scans"]), "raw_llm_txt": cnt("raw"), "datasets_referenced_not_copied": len(man["datasets_referenced_not_copied"])}
tot = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs); R["handoff_total_bytes"] = tot; R["handoff_total_mb"] = round(tot / 1e6, 2)
# summary table
with open(os.path.join(OUT, "summary_table.csv"), newline="", encoding="utf-8") as f: st_rows = list(csv.DictReader(f))
bot_runs = [x for x in runs if x[0]["variant"] in ("full", "mtf", "full_1d")]
R["summary_table_rows"] = len(st_rows); 
if len(st_rows) != len(bot_runs): FAIL.append(f"summary_table rows {len(st_rows)} != bot runs {len(bot_runs)}")
# 7. decision distribution / confidence / paper trades
dist = collections.defaultdict(collections.Counter); dist_tf = collections.defaultdict(collections.Counter); confs = collections.defaultdict(list)
for r, o in bot_runs:
    k = o["final"]["rating"]; dist["ALL"][k] += 1; dist[r["variant"] + "/" + r["timeframe"]][k] += 1
    c = o["final"].get("confidence")
    if num(c): confs["ALL"].append(c); confs[r["variant"] + "/" + r["timeframe"]].append(c)
    if num(c) and k in ("BUY", "SELL"): confs["ALL (BUY/SELL only)"].append(c)
LONG = {"BUY": "long", "SELL": "short", "HOLD": "hold"}
R["decision_distribution_bot_values"] = {g: dict(c) for g, c in dist.items()}
R["decision_distribution_long_short_hold"] = {g: {LONG.get(k, k): v for k, v in c.items()} for g, c in dist.items()}
def stat(v): return {"n": len(v), "mean": round(statistics.mean(v), 2), "min": min(v), "max": max(v), "median": statistics.median(v)} if v else None
R["confidence"] = {"scale": "0-100 integers (guven); trader min_confidence 65", "stats": {g: stat(v) for g, v in confs.items()}, "all_values_integers_in_0_100": all(isinstance(x, int) and 0 <= x <= 100 for x in confs["ALL"]),
                   "n_runs_without_confidence": sum(1 for r, o in bot_runs if not num(o["final"].get("confidence"))), "note": "MTF HOLD (not aligned) has guven=None by bot rule"}
opened = collections.Counter(); blocked = collections.Counter(); live = collections.Counter()
for r, o in bot_runs:
    tp = o.get("trader_proposal"); lr = o["linked_records"]
    if r["variant"] != "mtf":
        if tp: opened["ledger(paper.py) status=" + str(tp.get("status"))] += 1; 
        if tp and tp.get("blocked"): blocked[tp["blocked"]] += 1
        if not tp: opened["no kagit_islem in file"] += 1
    if lr.get("paper_ledger_record"): 
        t = lr["paper_ledger_record"]; opened["MTF/other ledger.json record status=" + str(t.get("status"))] += 1 if r["variant"] == "mtf" else 0
        if t.get("blocked") and r["variant"] == "mtf": blocked["(mtf record) " + t["blocked"]] += 1
    if lr.get("paper_trader_position"): live["live_trader_position:" + lr["paper_trader_position"]["status"] + ("/" + str(lr["paper_trader_position"].get("exit_reason")) if lr["paper_trader_position"]["status"] == "closed" else "")] += 1
R["paper_trades"] = {"ledger_status_counts": dict(opened), "blocked_reasons": dict(blocked), "live_trader_positions_linked": dict(live),
                     "live_trader_positions_total_in_ledger": len(jl(os.path.join(OUTS, "trader/ledger.json"))["positions"]),
                     "runs_that_opened_live_position": sum(1 for r, o in bot_runs if o["linked_records"].get("paper_trader_position")),
                     "runs_without_live_position": sum(1 for r, o in bot_runs if not o["linked_records"].get("paper_trader_position"))}
# 8. timestamps: signal bar vs close time
IV = {"1h": 1, "mtf-1h": 1, "1d": 24, "4h": 4, "15m": .25}
def P(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
gaps, anomalies = [], []; opened_before_close = 0
for r, o in bot_runs:
    bo = o["run"]["signal_bar_open_utc"]
    if not bo: anomalies.append((r["file"], "no bar time")); continue
    close = P(bo) + dt.timedelta(hours=IV[r["timeframe"]])
    ref = o["run"]["finished_at"] or o["run"]["file_mtime_utc"]; refsrc = "recorded_at" if o["run"]["finished_at"] else "file_mtime"
    g = (P(ref) - close).total_seconds() / 60; gaps.append(g)
    if g < 0: anomalies.append((o["run"]["source_file"], f"{refsrc} {ref} is BEFORE bar close {close.strftime('%Y-%m-%dT%H:%M:%SZ')} (gap {g:.0f} min) -> bar time inconsistent with write time"))
    if g > (36 if r["timeframe"] == "1d" else 6) * 60: anomalies.append((o["run"]["source_file"], f"STALE: bar close {close.strftime('%Y-%m-%dT%H:%M:%SZ')} but {refsrc} {ref} (gap {g/60:.1f} h) -> bar date inconsistent with write time"))
    pos = o["linked_records"].get("paper_trader_position")
    if pos:
        oa = dt.datetime.strptime(pos["opened_at"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dt.timezone.utc)
        if oa < close: opened_before_close += 1
R["timestamp_check"] = {"signal_time_field": "run JSON data_date / time = OPEN time of the last CLOSED candle, UTC (data.klines drops candles with close_time >= now; 1d = date only, 00:00 UTC)",
    "bar_close_utc": "= open + interval; entry (live) happens when trader cycle runs, i.e. AFTER bar close", "n_checked": len(gaps), "gap_run_written_minus_bar_close_minutes": {"min": round(min(gaps), 1), "median": round(statistics.median(gaps), 1), "max": round(max(gaps), 1)},
    "runs_with_bar_time_inconsistent_with_write_time(future or >6h stale)": len(anomalies), "anomalies": anomalies[:10], "live_positions_opened_before_bar_close": opened_before_close,
    "timezone_handling": "bar times already UTC (no conversion). recorded_at/opened_at/closed_at/created_at carry +0300 (Europe/Istanbul) and were converted to Z by their own offset. file_mtime_utc derived from epoch. 'MTF' files carry no write-time field -> file mtime used.",
    "caveat": "for MTF files file_mtime may be later than the true run time (files can be rewritten); this check can only catch bar times that lie in the future relative to write time"}
if anomalies: WARN.append(f"{len(anomalies)} runs with bar time inconsistent with write time")
R["warnings"] = WARN; R["failures"] = FAIL; R["ok"] = not FAIL
wr = json.dump(R, open(os.path.join(OUT, "validation_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
with open(os.path.join(OUT, "validation_report.md"), "w", encoding="utf-8") as f:
    f.write("# validation report\n\nstatus: " + ("OK" if not FAIL else "FAIL") + "\n\n```json\n" + json.dumps(R, ensure_ascii=False, indent=1, default=str)[:60000] + "\n```\n")
print(json.dumps({k: R[k] for k in ("ok", "counts", "handoff_total_mb", "json_files_parsed", "json_unparsable_or_nonfinite", "string_numbers_in_mapped_sections", "iso_time_violations", "text_integrity_checks", "text_shortened_or_changed", "secret_pattern_hits")}, ensure_ascii=False, indent=1, default=str))
print("FAIL:", FAIL[:10]); print("WARN:", WARN[:10]); raise SystemExit(0 if not FAIL else 1)
