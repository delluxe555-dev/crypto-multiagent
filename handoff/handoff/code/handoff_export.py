#!/usr/bin/env python3
"""handoff_export.py - EXPORT-ONLY layer (schema handoff/1.0). Reads what the bot already wrote; writes ./handoff/.
Touches no analysis logic. Never invents values: missing -> null + listed in not_produced.   Usage: python handoff_export.py"""
import os, sys, re, json, csv, math, ast, glob, shutil, hashlib, uuid, datetime as dt, collections

HERE = os.path.dirname(os.path.abspath(__file__)); OUTS = os.path.join(HERE, "outputs"); OUT = os.path.join(HERE, "handoff")
TA_TEST = "/workspace/tradingagents-test"; TA_REPO = "/workspace/TradingAgents"
SV = "handoff/1.0"; NS = uuid.UUID("6f1c2d3e-0000-4000-8000-00000000c0de")
NAN_COUNT = collections.Counter()
SECRET_KEY = re.compile(r"(api_?key|token|secret|passw(or)?d|passwd|bearer)", re.I)
IV_H = {"15m": .25, "1h": 1, "4h": 4, "1d": 24, "mtf-1h": 1}

# ---------- helpers ----------
def now_z(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def epoch_z(e): return dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def ist_to_z(s):
    """'2026-10-25T16:58:08+0300' (carries own offset) -> UTC Z. None if unparsable."""
    try: return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception: return None
def bar_z(s):
    """Bot stores candle OPEN time in UTC: '2026-10-25 12:00' or '2026-10-22' (1d)."""
    s = str(s)
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try: return dt.datetime.strptime(s, f).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception: pass
    return None
def clean(o, path=""):
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o): NAN_COUNT[path or "?"] += 1; return None
        return o
    if isinstance(o, dict): return {str(k): clean(v, path + "/" + str(k)) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v, path + "[]") for v in o]
    return o
def jload(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def wj(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(clean(o), f, ensure_ascii=False, indent=1, allow_nan=False, default=str)
def sha(b): return hashlib.sha256(b).hexdigest()
def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()
def rid(key): return str(uuid.uuid5(NS, key))
def rel(p): return os.path.relpath(p, OUT)
def mask(o):
    if isinstance(o, dict): return {k: ("***" if SECRET_KEY.search(k) and k != "key_env" and v not in (None, False, True) else mask(v)) for k, v in o.items()}
    if isinstance(o, list): return [mask(v) for v in o]
    return o
def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copyfile(src, dst); return dst
def consts(path, names=None):
    """Module-level literal constants via ast (no import, no side effects)."""
    out = {}
    for n in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                tg = [t] if isinstance(t, ast.Name) else (t.elts if isinstance(t, ast.Tuple) else [])
                try:
                    v = ast.literal_eval(n.value)
                    if isinstance(t, ast.Tuple): vals = list(v)
                    else: vals = [v]
                    for x, val in zip(tg, vals):
                        if isinstance(x, ast.Name) and (not names or x.id in names): out[x.id] = val
                except Exception: pass
    return out
def excerpt(fname, anchor, n):
    """Verbatim code excerpt: {file, line_start, line_end, code}."""
    p = os.path.join(HERE, fname); L = open(p, encoding="utf-8").read().split("\n")
    for i, l in enumerate(L):
        if re.search(anchor, l): return {"file": fname, "line_start": i + 1, "line_end": min(len(L), i + n), "code": "\n".join(L[i:i + n])}
    return {"file": fname, "line_start": None, "line_end": None, "code": None, "note": f"anchor not found: {anchor}"}
def num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)
def numeric_only(d):
    if not isinstance(d, dict): return None
    return {k: v for k, v in d.items() if num(v)}

# ---------- config / rule layer ----------
CFG = jload(os.path.join(HERE, "config.json")); TR = CFG["trader"]
RR = consts(os.path.join(HERE, "risk_rules.py")); PP = consts(os.path.join(HERE, "paper.py"))
RADAR = consts(os.path.join(HERE, "radar_read.py")); SPAP = consts(os.path.join(HERE, "signal_paper.py"))
CONF = consts(os.path.join(HERE, "confluence_paper.py"))

def build_rules():
    R = []
    add = lambda **k: R.append(k)
    add(id="data.indicators", layer="data", source="data.py:add_indicators/klines", llm_free=True,
        parameters={"rsi": "RSI14 Wilder-style ewm(alpha=1/14, adjust=False)", "macd": "EMA12-EMA26, signal EMA9", "sma": [50, 200],
                    "atr14": "simple rolling mean (14) of True Range", "candle_policy": "klines() drops candles whose close_time >= now (only CLOSED candles)",
                    "date_field": "candle OPEN time, UTC ('%Y-%m-%d %H:%M'; 1d = date only)"},
        code=[excerpt("data.py", r"df = df\[df\[\"close_time\"\]", 1), excerpt("data.py", r"def add_indicators", 12)])
    add(id="scan.universe_filters", layer="scan stage-1", source="scan.py:universe/main", llm_free=True,
        parameters={k: CFG.get(k) for k in ("universe_size", "quote", "exclude", "min_quote_vol_24h", "exclude_non_ascii", "require_okx_perp", "min_listing_days", "max_abs_chg_24h_%", "min_atr_pct", "low_vol_percentile", "exclude_meme")} | {"LEVERAGED_suffixes": ["UP", "DOWN", "BULL", "BEAR"]},
        conditions=["universe(): keep symbols ending with quote; drop base in exclude+exclude_meme; drop leveraged-token suffixes; drop non-ASCII base if exclude_non_ascii; vol = Binance spot quoteVolume + OKX USDT-M perp volume must be >= min_quote_vol_24h; spot quoteVolume>0 and trade count>0; sort by vol desc, keep universe_size",
                    "main(): if require_okx_perp -> drop symbols without OKX perp (scan.py:93); if min_listing_days -> drop listings younger than that (scan.py:96-100)",
                    "main(): thr = max(min_atr_pct[interval], percentile(atr_%, low_vol_percentile)); atr_% < thr -> dropped; |24h change| > max_abs_chg_24h_% -> dropped; quote_vol_24h < min -> dropped"],
        code=[excerpt("scan.py", r"def universe", 18), excerpt("scan.py", r"thr = max\(", 6), excerpt("scan.py", r"if CFG.get\(\"require_okx_perp\"\)", 9)])
    add(id="scan.score", layer="scan stage-1", source="scan.py:main/features/trend/zs", llm_free=True,
        weights={"zs(log(vol_spike_3))": 1.5, "zs(log(vol_spike))": 1.0, "zs(atr_%)": 1.0, "|aligned| (raw, not z)": 1.0, "zs(rsi_ext)": 0.7, "zs(|funding_%|)": 0.5, "zs(log(quote_vol_24h))": 0.3},
        parameters={"zs": "z-score clipped to [-3,3]", "rsi_ext": "max(|RSI-50|,15)-15", "trend()": "+1 if close>sma50 and sma50[-1]-sma50[-6]>0; -1 mirror; else 0", "aligned": "trend_ltf if trend_ltf==trend_4h and !=0 else 0",
                    "vol_spike": "last volume / mean of previous 20", "vol_spike_3": "mean last 3 / mean of prior 20 (bars -23..-4)", "shortlist": f"top {TR['top_n']} by skor (+ majors {TR['majors']})"},
        code=[excerpt("scan.py", r"ok\[\"skor\"\] =", 3), excerpt("scan.py", r"^def trend", 5), excerpt("scan.py", r"^def features", 12)])
    add(id="mtf.alignment", layer="signal", source="run.py:main_mtf", llm_free=True, note="inputs are LLM outputs (trend_4h.trend, entry.giris); the combination rule itself is deterministic",
        conditions=["aligned = (trend=='YUKARI' and giris=='LONG') or (trend=='ASAGI' and giris=='SHORT')",
                    "if aligned: karar = BUY if giris=='LONG' else SELL; else karar = HOLD", "guven = min(trend_4h.guven, entry.guven) if aligned else None"],
        code=[excerpt("run.py", r"trend, giris = ", 5)])
    add(id="trader.entry_gate", layer="paper trader", source="trader.py:cycle", llm_free=True,
        parameters={k: TR.get(k) for k in ("interval", "top_n", "majors", "min_confidence", "require_mtf", "allow_short", "max_concurrent", "daily_loss_limit", "daily_llm_budget", "min_budget_per_coin", "cycle_minute")},
        conditions=["require_mtf -> MTF must be aligned", "hakem.karar must be BUY/SELL and equal MTF karar and hakem.guven >= min_confidence",
                    "blocked if open positions >= max_concurrent, or realized_since(day_start()) <= -daily_loss_limit*equity, or symbol already open",
                    "SELL opens a SHORT only if allow_short"],
        code=[excerpt("trader.py", r"if T\[\"require_mtf\"\] and not", 8), excerpt("trader.py", r"atr = float\(o\[\"extras\"\]", 14)])
    add(id="trader.sizing_stops", layer="paper trader", source="trader.py:open_position", llm_free=True, note="LLM stop/hedef are NOT passed to open_position; stop/target are ATR multiples only",
        parameters={k: TR.get(k) for k in ("atr_stop_mult", "atr_target_mult", "risk_per_trade", "fee", "slippage", "leverage_tiers", "max_leverage", "max_margin_frac", "max_pos_frac", "min_notional_usd", "start_equity")},
        formulas={"fill": "ref=live Binance spot ticker at order time; LONG fill=ref*(1+slippage), SHORT fill=ref*(1-slippage)", "stop": "fill -/+ atr_stop_mult*ATR14(1h)", "target": "fill +/- atr_target_mult*ATR14(1h)",
                  "notional": "min(risk_usd/(|fill-stop|+fill*2*(fee+slippage))*fill, max_margin*leverage_cap)", "leverage_cap": "tier by confidence: >=80:5x, >=70:4x, >=65:3x else 1x (<= max_leverage)"},
        code=[excerpt("trader.py", r"^def open_position", 22)])
    add(id="trader.exit_rules", layer="paper trader", source="trader.py:_monitor/close_position/maybe_move_be", llm_free=True,
        parameters={"monitor_every_s": TR.get("monitor_every_s"), "max_hold_hours": TR.get("max_hold_hours"), "be_enabled": TR.get("be_enabled"), "be_trigger_frac": TR.get("be_trigger_frac"), "be_buffer_pct": TR.get("be_buffer_pct"), "fee": TR.get("fee"), "slippage": TR.get("slippage")},
        conditions=["every monitor pass: high/low of 1-MINUTE candles since last check (+ last price); stop hit if low<=stop (LONG) / high>=stop (SHORT) -> WICK triggers, not candle close",
                    "stop and target in same pass -> stop wins", "stop fill = min(stop,last) LONG / max(stop,last) SHORT; target fill = target; both then slippage against us + fee",
                    "time exit after max_hold_hours at last price", "breakeven: be_progress = (best price seen - entry)/(target - entry) (SHORT mirrored); when >= be_trigger_frac, stop -> entry*(1 +/- be_buffer_pct/100) (be_level), once, only if it improves the stop"],
        code=[excerpt("trader.py", r"hit_stop = ", 8), excerpt("trader.py", r"^def close_position", 6), excerpt("trader.py", r"^def maybe_move_be", 8)])
    add(id="risk_rules.size", layer="risk (run.py finish -> paper.py ledger)", source="risk_rules.py", llm_free=True,
        parameters={k: RR.get(k) for k in ("RISK_PER_TRADE", "ATR_MULT", "DAILY_LOSS_LIMIT", "MAX_POS_FRAC")},
        conditions=["stop = LLM hakem.stop if valid (below price and >= 0.5*ATR away) else price - ATR_MULT[interval]*ATR (stop_kaynak 'hakem' or 'ATR×k')", "size = min(equity*1%/(price-stop)*price, equity*50%)",
                    "blocked if realized_today <= -2% equity; blocked if karar != BUY (long/cash only)"],
        code=[{"file": "risk_rules.py", "line_start": 1, "line_end": len(open(os.path.join(HERE, "risk_rules.py")).read().split("\n")), "code": open(os.path.join(HERE, "risk_rules.py"), encoding="utf-8").read()}])
    add(id="paper.ledger", layer="paper ledger (outputs/ledger.json)", source="paper.py", llm_free=True,
        parameters={"FEE_per_side": PP.get("FEE"), "SLIP_per_side": PP.get("SLIP"), "START_EQUITY": PP.get("START_EQUITY"), "HORIZON_BARS": PP.get("HORIZON_BARS")},
        conditions=["entry = signal bar CLOSE (price=df.close.iloc[-1]); status 'open' only if karar=='BUY' and size_usd>0 and not blocked", "exits checked on bars AFTER signal bar: low<=stop -> stop; high>=hedef -> hedef; else time exit after HORIZON bars at close",
                    "bar-level (wick) check; stop checked before target within the same bar"], code=[excerpt("paper.py", r"^def update", 16)])
    add(id="keylevels", layer="signal context", source="keylevels.py", llm_free=True, parameters={"key_levels": CFG.get("key_levels"), "key_level_watch": CFG.get("key_level_watch")},
        conditions=["classify(4h candle, level): close<level -> 'alt' (bear break); low<level<=close -> 'tepki' (bull reaction); else 'üst'"], code=[excerpt("keylevels.py", r"^def classify", 5)])
    add(id="radar_read.score", layer="radar (not in live decision path)", source="radar_read.py", llm_free=True,
        parameters={k: RADAR.get(k) for k in ("PX_TH", "OI_TH", "SPIKE_TH", "FUND_TH", "SPREAD_TH")},
        conditions=["story(): |px|<0.5% or |oi|<1% -> 0; px>0&oi>0 -> +2; px<0&oi>0 -> -2; px<0&oi<0 -> -1; else +1", "funding: fmax = max-|abs| funding across venues (8h-equiv %); |fmax|>=FUND_TH -> fsc = -1 if fmax>0 else +1", "score = sc4 + fsc; >=2 LONG egilimli, <=-2 SHORT egilimli, else NOTR"],
        code=[excerpt("radar_read.py", r"^def story", 8), excerpt("radar_read.py", r"fmax = max", 5)])
    add(id="signal_paper", layer="silent signal tracker (LLM-free)", source="signal_paper.py", llm_free=True,
        parameters={k: SPAP.get(k) for k in ("COINS", "STEP", "HZ", "COST", "WINS", "FUND_TH", "FUND_REFR")},
        conditions=["NEWLONG p>=+0.5 & oi>=+1; NEWSHORT p<=-0.5 & oi>=+1; LONGLIQ p<=-0.5 & oi<=-1; SQUEEZE p>=+0.5 & oi<=-1; OFOI_UP/DN |oi|>=3; FUND_POS/NEG |funding 8h-eq|>=0.05%",
                    "windows w in {4,16} x 15m; entry = NEXT 15m bar OPEN after signal bar; exit = close of bar j+H, H in {4,16,48}; cost 10bp round trip; baseline = other coins same window"],
        code=[excerpt("signal_paper.py", r"^COINS", 3)])
    add(id="confluence_paper", layer="silent signal tracker (LLM-free)", source="confluence_paper.py", llm_free=True,
        parameters={k: CONF.get(k) for k in ("PROXIES", "LEV", "BW", "WIN", "TOPK", "REFR", "CR_BARS", "CTRL_EVERY", "WARM", "WARM2", "BAND", "HZ", "COST")},
        conditions=["HTF line proxies (EMA50, EMA100, Supertrend(10,3), Bollinger mid SMA20) on 2h candles from last CLOSED 2h bar", "touch: 15m low<=line (dir +1) or high>=line (dir -1) after a bar fully on trend side; 16-bar refractory", "entry = next 15m bar open; cost 10bp round trip"],
        code=[excerpt("confluence_paper.py", r"^PROXIES", 2)])
    add(id="lessons.guard", layer="memory/lessons", source="lessons.py + config.json", llm_free=False, parameters=CFG.get("lessons"),
        note="lessons are informational only per config note; guard_min_n below which no setting changes", code=[])
    return R

def llm_layer():
    return {
        "summary": "Direction (BUY/SELL/HOLD; LONG/SHORT; YUKARI/ASAGI) is chosen by LLM calls. Deterministic code only gates, sizes, sets ATR stops and executes.",
        "full_debate (run.main, 6 calls)": {
            "teknik_analist": {"role": "quick", "enters": "commentary + 'EĞİLİM: BOĞA|AYI|NÖTR' tag (tag used only for per-agent hit-rate stats, paper.stance)", "decides_direction": False},
            "duygu_analisti": {"role": "quick", "enters": "commentary + EĞİLİM tag (stats only)", "decides_direction": False},
            "boga": {"role": "quick", "enters": "argument text only", "decides_direction": False},
            "ayi": {"role": "quick", "enters": "argument text only", "decides_direction": False},
            "hakem": {"role": "deep", "enters": "JSON {karar BUY|SELL|HOLD, guven 0-100, stop, hedef, gerekce, maddeler}", "decides_direction": True, "used_by": "trader.cycle (karar, guven -> open if >= min_confidence and equals MTF karar); risk_rules (hakem.stop if valid); hakem.hedef is the ledger target in paper.py"},
            "risk_llm": {"role": "deep", "enters": "JSON {onay, stop, pozisyon_usd, not}", "decides_direction": False, "used_by": "stored in run output only; run.finish()/trader do not read it (backtest note: 'canlıda işlem kararını etkilemiyor')"}},
        "mtf (run.main_mtf, 2 calls)": {
            "trend_4h": {"role": "deep", "enters": "JSON {trend YUKARI|ASAGI|YATAY, guven, gerekce}", "decides_direction": True},
            "entry_ltf": {"role": "deep", "enters": "JSON {giris LONG|SHORT|YOK, guven, stop, hedef, gerekce}", "decides_direction": True, "note": "its stop/hedef are not used by the live paper trader (ATR multiples used)"}},
        "prompt_files": ["agents.py (all role prompts: RULE, PAT, KL, mode(), technical, sentiment, bull, bear, judge, risk, trend_4h, entry_ltf)", "lessons.py (lesson block text injected into judge/MTF prompts)", "keylevels.py:text (data block lines)"],
        "provider_chain": "config.json providers: gemini -> openrouter (-> ollama disabled); role quick/deep model per provider; actual responder recorded per step in run 'providers'"}

RULES = build_rules()
DET_RULES_COMPACT = [{k: v for k, v in r.items() if k != "code"} | {"code_refs": [{"file": c["file"], "line_start": c.get("line_start"), "line_end": c.get("line_end")} for c in r.get("code", [])]} for r in RULES]

def exec_assumptions():
    return {"live_paper_trader (trader.py)": {"commission_pct_per_side": TR["fee"] * 100, "slippage_pct_per_side": TR["slippage"] * 100, "leverage": {"tiers_confidence_to_x": TR["leverage_tiers"], "max": TR["max_leverage"]},
            "position_size_rule": f"risk {TR['risk_per_trade']*100}% of equity per stop distance (stop dist + 2*(fee+slip)); margin cap {TR['max_margin_frac']*100}% of equity x leverage_cap; min notional ${TR['min_notional_usd']}",
            "stop_trigger": "1-minute candle high/low since last check (monitor every ~%ss) -> intrabar wick triggers stop" % TR["monitor_every_s"], "stop_priority": "stop before target if both in same pass",
            "stop_fill": "min(stop,last) LONG / max(stop,last) SHORT", "time_exit_hours": TR["max_hold_hours"], "breakeven": {"enabled": TR["be_enabled"], "trigger_frac_of_target_path": TR["be_trigger_frac"], "buffer_pct": TR["be_buffer_pct"]},
            "start_equity_usd": TR["start_equity"], "max_concurrent": TR["max_concurrent"], "daily_loss_limit": TR["daily_loss_limit"], "shorts_allowed": TR["allow_short"]},
            "paper_ledger (paper.py, outputs/ledger.json)": {"commission_pct_per_side": PP["FEE"] * 100, "slippage_pct_per_side": PP["SLIP"] * 100, "leverage": "none (spot, long-only)", "start_equity_usd": PP["START_EQUITY"],
            "position_size_rule": f"risk_rules.size: {RR['RISK_PER_TRADE']*100}% risk, cap {RR['MAX_POS_FRAC']*100}% equity", "stop_trigger": "bar low/high of subsequent bars of the SAME interval (1h wick)", "horizon_bars": PP["HORIZON_BARS"]},
            "signal_paper/confluence_paper": {"cost_bp_round_trip": SPAP["COST"], "entry": "next 15m bar open"}}

COMMON = {"confidence_scale": None, "entry_reference": {
    "live_paper_trader": "live Binance spot ticker price at the moment the cycle opens the position (minutes after the signal bar closed), +/- slippage; NOT signal-bar close, NOT next-bar open",
    "paper_ledger (paper.py)": "signal bar CLOSE (df.close.iloc[-1]); exits evaluated from the following bar",
    "signal_paper/confluence_paper": "next 15m bar OPEN after the signal bar"},
    "execution_assumptions": exec_assumptions(), "llm_layer": llm_layer(), "deterministic_rules": DET_RULES_COMPACT}

def atr_label(src):
    m = re.search(r"ATR\S?\s*([0-9.]+)", src or "")
    return f"atr_mult({m.group(1)})" if m else ("llm_level(hakem.stop; valid only if below price and >=0.5*ATR away, else atr_mult(k))" if src == "hakem" else None)

def method_fields(rk, llm_stop_present):
    sl = {"live_paper_trader": f"atr_mult({TR['atr_stop_mult']}) of ATR14(1h) from fill, then breakeven(frac={TR['be_trigger_frac']}, buffer_pct={TR['be_buffer_pct']})",
          "risk_rules_layer": atr_label(rk.get("stop_kaynak")) if isinstance(rk, dict) else None,
          "llm_proposed": "price_level (hakem/entry JSON 'stop'; prompt asks to align with swing/FVG/VWAP/POC/pivot levels; not used by live trader)" if llm_stop_present else None}
    tp = {"live_paper_trader": f"atr_mult({TR['atr_target_mult']}) of ATR14(1h) from fill (single target, no partials)", "paper_ledger": "llm_level (hakem.hedef as-is)", "llm_proposed": "price_level (hakem/entry JSON 'hedef')" if llm_stop_present else None}
    return sl, tp

# ---------- data stores ----------
TRADER_L = jload(os.path.join(OUTS, "trader/ledger.json")) if os.path.exists(os.path.join(OUTS, "trader/ledger.json")) else {"positions": []}
POS = {p["id"]: p for p in TRADER_L["positions"]}
OLD_L = jload(os.path.join(OUTS, "ledger.json")) if os.path.exists(os.path.join(OUTS, "ledger.json")) else {"trades": []}
OLDT = {t["id"]: t for t in OLD_L["trades"]}
CFG_MASKED = mask(CFG)

def tag(t): return str(t).replace(" ", "T").replace(":", "")
def split_name(fn):
    m = re.match(r"^([A-Z0-9]+)_(mtf-1h|1h|1d)_(.+)\.json$", fn); return m.groups() if m else None

def data_used_missing(raw):
    used, miss = [], []
    ex = raw.get("extras")
    if isinstance(ex, dict):
        for k, lab in (("derivatives", "derivatives (OKX)"), ("orderbook", "orderbook (Binance spot depth)"), ("onchain", "onchain/stablecoin (DefiLlama etc.)"), ("volume_spike", "volume_spike (klines)")):
            (used if ex.get(k) not in (None, {}, []) else miss).append(lab if ex.get(k) not in (None, {}, []) else f"extras.{k} empty/absent")
    elif "extras" in raw: miss.append("extras absent/None")
    text = (raw.get("tech_data") or "") + "\n" + (raw.get("sentiment_data") or "")
    if text.strip(): used.append("Binance spot klines (tech_data)")
    for ln in text.split("\n"):
        if re.search(r"verisi yok|alınamadı|hesaplanamadı|yok\.$", ln) and len(ln) < 220: miss.append("text: " + ln.strip())
    return sorted(set(used)), sorted(set(miss))

NOT_PRODUCED_BASE = ["producer.version (bot has no version)", "producer.git_commit (/workspace/crypto-agents is not a git repository)", "run.asset_type (bot does not store it; filename uses 'na')",
                     "run.instrument_context", "run.portfolio_context", "run.started_at (only recorded_at/finish exists)", "analyst_reports.news (no news analyst)", "analyst_reports.fundamentals (no fundamentals analyst)",
                     "research_debate.full_history", "research_debate.last_response", "research_debate.rounds (single pass boga->ayi, count not stored)", "research_manager_plan (hakem is the single decision step; mapped to final)",
                     "risk_debate.* (outputs/risk_debate_runs are an unconnected design test, not linked to runs)", "messages (bot does not keep a message list; no messages/<RUN_ID>.json)", "numeric_context.last_price when not in file"]

def reports_for(base_id, name_base):
    d = os.path.join(OUT, "reports", base_id); n = []
    src = os.path.join(OUTS, name_base + ".md")
    if os.path.exists(src): copy(src, os.path.join(d, name_base + ".md")); n.append(rel(os.path.join(d, name_base + ".md")))
    return n

def raw_llm(name_base, kind):
    cp = os.path.join(OUTS, ".cache", name_base + ("_v2.json" if kind == "full" else ".json"))
    if not os.path.exists(cp) and kind == "full": cp = os.path.join(OUTS, ".cache", name_base + ".json")
    return (jload(cp), cp) if os.path.exists(cp) else (None, None)

def build_run(fn, kind):
    sym, iv, t = split_name(fn); p = os.path.join(OUTS, fn); raw = jload(p); name_base = fn[:-5]; run_id = rid("crypto-agents/outputs/" + fn)
    st = os.stat(p); mtime_z = epoch_z(st.st_mtime)
    if kind == "mtf":
        when = raw.get("time"); h = raw.get("karar") or {}; rk = raw.get("risk_kural"); provs = raw.get("providers") or {}
    else:
        when = raw.get("data_date"); h = raw.get("hakem") or {}; rk = raw.get("risk_kural") or None; provs = raw.get("providers") or {}
    cache, cpath = raw_llm(name_base, kind)
    ledger_key = f"{sym}-{iv}-{when}"; pos = POS.get(f"{sym}-{when}"); led = OLDT.get(ledger_key)
    kag = raw.get("kagit_islem") if kind == "full" else None
    sl_m, tp_m = method_fields(rk, kind == "full" and bool(h.get("stop")) or kind == "mtf" and bool(h.get("stop")))
    used, miss = data_used_missing(raw if kind == "full" else {})
    if kind == "mtf": used, miss = ["Binance spot klines 4h + entry interval", "extras (derivatives/orderbook/onchain) fed to entry agent: not stored in mtf output"], []
    np_ = list(NOT_PRODUCED_BASE)
    if kind == "mtf": np_ += ["analyst_reports.market/sentiment (MTF has no analyst texts; see raw_native.trend_4h / entry)", "research_debate.bull_history/bear_history (no debate in MTF)", "trader_proposal (MTF output has no kagit_islem; see paper_ledger_record link)", "run.finished_at (no timestamp field in file; file_mtime_utc given)", "risk.risk_llm (MTF has no LLM risk step)"]
    if kind == "full" and not kag: np_.append("trader_proposal/kagit_islem (absent in this legacy file)")
    if kind == "full" and "risk_kural" not in raw: np_.append("risk.risk_kural (absent in this legacy file)")
    if cache is None: np_.append("raw LLM text cache (.cache entry missing)")
    dec_text = None; dec_note = None
    if kind == "full":
        hr = (cache or {}).get("hakem_raw")
        dec_text = hr if isinstance(hr, str) else (json.dumps(raw.get("hakem"), ensure_ascii=False, indent=2) if raw.get("hakem") else None)
        dec_note = "decision_text = verbatim LLM text from .cache hakem_raw" if isinstance(hr, str) else "decision_text = JSON serialization of hakem object (no raw cache)"
    else:
        dec_text = h.get("gerekce"); dec_note = "decision_text = karar.gerekce (the bot's own '4h: ... | 1h: ...' string)"
    conf_vals = h.get("guven")
    prov_vals = sorted({v for v in provs.values() if isinstance(v, str)}) if provs else []
    deep_keys = ("hakem_raw", "risk_raw", "trend_4h_raw", "entry_raw"); quick_keys = ("teknik_analist", "duygu_analisti", "boga", "ayi")
    deep = sorted({provs[k] for k in deep_keys if k in provs}); quick = sorted({provs[k] for k in quick_keys if k in provs})
    legacy_model = raw.get("model")
    roles = ["teknik_analist", "duygu_analisti", "boga", "ayi", "hakem", "risk_llm"] if kind == "full" else ["trend_4h", "entry_ltf"]
    out = {"schema_version": SV, "exported_at": EXPORTED_AT,
           "producer": {"framework": "crypto-agents (custom)", "version": None, "git_commit": None, "llm_provider": (legacy_model if kind == "full" else None) or None,
                        "llm_providers_used": prov_vals or None, "deep_think_llm": (deep[0] if len(deep) == 1 else deep) if deep else None, "quick_think_llm": (quick[0] if len(quick) == 1 else quick) if quick else None,
                        "selected_analysts": roles, "output_language": "Turkish (agents.py RULE: 'Türkçe')"},
           "run": {"run_id": run_id, "ticker": raw.get("symbol"), "asset_type": None, "trade_date": (bar_z(when) or "")[:10] or None, "timeframe": iv, "variant": kind if iv != "1d" else "full_1d",
                   "signal_bar_open_utc": bar_z(when), "signal_bar_time_semantics": "OPEN time (UTC) of the last CLOSED candle (data.klines drops candles with close_time >= now); 1d = date only",
                   "instrument_context": None, "portfolio_context": None, "started_at": None,
                   "finished_at": ist_to_z((kag or {}).get("recorded_at")) if kag else None, "finished_at_source": "kagit_islem.recorded_at (+0300 converted to UTC)" if kag else None,
                   "file_mtime_utc": mtime_z, "duration_seconds": raw.get("runtime_s"), "llm_calls": raw.get("llm_calls"), "dry_run": raw.get("dry_run"), "source_file": os.path.relpath(p, HERE)},
           "final": {"rating": h.get("karar"), "confidence": conf_vals, "decision_text": dec_text, "decision_structured": h or None, "decision_text_source": dec_note},
           "analyst_reports": {"market": raw.get("teknik_analist") if kind == "full" else None, "sentiment": raw.get("duygu_analisti") if kind == "full" else None, "news": None, "fundamentals": None},
           "inputs_seen_by_agents": {"tech_data": raw.get("tech_data"), "sentiment_data": raw.get("sentiment_data")} if kind == "full" else None,
           "research_debate": {"bull_history": raw.get("boga") if kind == "full" else None, "bear_history": raw.get("ayi") if kind == "full" else None, "full_history": None, "last_response": None, "rounds": None},
           "research_manager_plan": None,
           "trader_proposal": kag if kind == "full" else None,
           "risk_debate": {"aggressive_history": None, "conservative_history": None, "neutral_history": None, "full_history": None, "latest_speaker": None, "rounds": None},
           "risk": {"risk_llm": raw.get("risk_llm") if "risk_llm" in raw else raw.get("risk"), "risk_kural": rk},
           "mtf": {"trend_4h": raw.get("trend_4h"), "entry": raw.get("entry"), "hizali": raw.get("hizali")} if kind == "mtf" else None,
           "memory": {"past_context": raw.get("memory") if kind == "full" else None, "memory_note": raw.get("lessons_block") if kind == "full" else None},
           "numeric_context": {"_aciklama": "Numeric values the bot itself produced/used, as they appear. Nothing added.", "last_price": None,
                               "other": {"extras": raw.get("extras") if kind == "full" else None, "decision": numeric_only(h), "risk_llm": numeric_only(raw.get("risk_llm")), "risk_kural": numeric_only(rk), "kagit_islem": numeric_only(kag), "trend_4h": numeric_only(raw.get("trend_4h")), "entry": numeric_only(raw.get("entry"))}},
           "raw_llm_outputs": {k: v for k, v in (cache or {}).items() if k != "_providers"} or None,
           "linked_records": {"paper_trader_position": pos, "paper_trader_link": "trader/ledger.json positions[id == SYMBOL-<signal bar>]" if pos else None, "paper_ledger_record": led, "paper_ledger_link": f"ledger.json trades[id == {ledger_key}]" if led else None},
           "confidence_scale": None, "entry_reference": COMMON["entry_reference"], "sl_method": sl_m, "tp_method": tp_m, "execution_assumptions": COMMON["execution_assumptions"],
           "llm_layer": COMMON["llm_layer"], "deterministic_rules": COMMON["deterministic_rules"],
           "data_used": used, "data_missing": miss, "not_produced": np_,
           "mapping_notes": {"final.rating": "hakem.karar (kind=full) or karar.karar (kind=mtf), value unchanged (BUY/SELL/HOLD)", "analyst_reports.market": "teknik_analist (full text)", "analyst_reports.sentiment": "duygu_analisti (full text)",
                             "research_debate.bull/bear": "boga / ayi (single pass)", "research_manager_plan": "null: hakem mapped to final.*, not duplicated", "memory.past_context": "memory", "memory.memory_note": "lessons_block",
                             "risk": "risk_llm (LLM, advisory, not read by trader) + risk_kural (rule layer) as-is; legacy 1d file 'risk' key mapped to risk_llm",
                             "numeric_context.last_price": None, "time_handling": "data_date/time = candle OPEN time already UTC; kagit_islem.recorded_at and trader opened_at carry +0300 (Istanbul) and were converted to Z; file_mtime_utc from epoch",
                             "mtf": "kind=mtf: analyst_reports empty; structured agent outputs in 'mtf' and raw_native"},
           "not_investment_advice": True}
    # last_price: only from the file / bot-written linked ledger record
    if kind == "full" and num((kag or {}).get("entry")): out["numeric_context"]["last_price"] = kag["entry"]; out["mapping_notes"]["numeric_context.last_price"] = "kagit_islem.entry (= signal bar close per run.finish)"
    elif led and num(led.get("entry")): out["numeric_context"]["last_price"] = led["entry"]; out["mapping_notes"]["numeric_context.last_price"] = "ledger.json record entry (= signal bar close), linked record, not in run file"
    out["raw_native"] = raw
    return out, run_id, sym, iv, when, raw, pos, led

# ---------- main ----------
def main():
    global EXPORTED_AT; EXPORTED_AT = now_z()
    if os.path.exists(OUT): shutil.rmtree(OUT)
    for d in ("runs", "messages", "config", "reports", "code", "backtests", "raw", "scans"): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    M = {"schema_version": SV, "generated_at": EXPORTED_AT, "runs": [], "messages": [], "configs": [], "reports": [], "backtests": [], "scans": [], "code_files": [], "datasets_referenced_not_copied": [], "skipped": []}
    table, confs = [], []
    # --- bot runs ---
    names = sorted(os.listdir(OUTS))
    for fn in names:
        sn = split_name(fn)
        if not sn or fn.startswith("backtest_"): continue
        raw0 = jload(os.path.join(OUTS, fn))
        if sn[1] == "mtf-1h": kind = "mtf"
        elif "hakem" in raw0 and "tech_data" in raw0: kind = "full"
        else: M["skipped"].append({"file": fn, "reason": "not a run (scanner output or other)"}); continue
        if fn.startswith(("scan_",)): continue
        out, run_id, sym, iv, when, raw, pos, led = build_run(fn, kind)
        fname = f"{sym}_na_{out['run']['trade_date'] or 'na'}_{run_id}.json"
        rp = os.path.join(OUT, "runs", fname)
        # config per run
        cfgd = {"schema_version": SV, "run_id": run_id, "config_json (masked)": CFG_MASKED, "interval": iv, "providers_actually_used": raw.get("providers"), "model_chain_label": raw.get("model"),
                "limits": {"trader": mask(TR), "risk_rules": {k: RR.get(k) for k in ("RISK_PER_TRADE", "ATR_MULT", "DAILY_LOSS_LIMIT", "MAX_POS_FRAC")}, "paper": {k: PP.get(k) for k in ("FEE", "SLIP", "START_EQUITY", "HORIZON_BARS")}},
                "note": "config.json is read at export time; per-run settings that were changed later (e.g. backups be_*) are not versioned by the bot", "api_keys": "never written (key-bearing fields masked '***'; key_env holds only an env-var NAME)"}
        wj(os.path.join(OUT, "config", run_id + ".json"), cfgd); M["configs"].append({"run_id": run_id, "file": f"config/{run_id}.json"})
        reps = reports_for(run_id, fn[:-5]); [M["reports"].append({"run_id": run_id, "file": r}) for r in reps]
        if out["raw_llm_outputs"]:
            for k, v in out["raw_llm_outputs"].items():
                if isinstance(v, str):
                    os.makedirs(os.path.join(OUT, "raw", run_id), exist_ok=True); open(os.path.join(OUT, "raw", run_id, k + ".txt"), "w", encoding="utf-8").write(v)
        out["reports"] = reps
        if num(raw.get("guven")) or num((out["final"].get("confidence"))): confs.append(out["final"]["confidence"])
        wj(rp, out)
        M["runs"].append({"run_id": run_id, "ticker": sym, "asset_type": None, "trade_date": out["run"]["trade_date"], "timeframe": iv, "variant": out["run"]["variant"], "file": f"runs/{fname}"})
        h = out["final"]["decision_structured"] or {}
        # summary table row
        if pos: res = f"live:{pos.get('status')}" + (f"/{pos.get('exit_reason')}/pnl_usd={round(pos['pnl_usd'],2)}" if pos.get('status') == 'closed' else "")
        elif kind == "full" and out["trader_proposal"]: res = f"no_live_position; ledger:{out['trader_proposal'].get('status')}" + (f" ({out['trader_proposal'].get('blocked')})" if out['trader_proposal'].get('blocked') else "")
        elif led: res = f"no_live_position; ledger:{led.get('status')}" + (f" ({led.get('blocked')})" if led.get('blocked') else "")
        else: res = "no_live_position; no ledger record"
        fwd = (led or (out["trader_proposal"] if kind == "full" else None) or {}).get("fwd_ret_%")
        led2 = led or {}
        table.append({"symbol": sym, "tf": iv, "date_bar_open_utc": (bar_z(when) or "").replace("T", " ").replace("Z", ""), "decision": h.get("karar"), "confidence": h.get("guven"), "sl_llm": h.get("stop"), "tp_llm": h.get("hedef"),
                      "sl_rule_layer": (raw.get("risk_kural") or {}).get("stop"), "sl_live": pos.get("stop_orig") or pos.get("stop") if pos else None, "tp_live": pos.get("target") if pos else None, "result": res,
                      "fwd_ret_pct_24bars": led2.get("fwd_ret_%"), "run_id": run_id, "kind": kind})
    # --- legacy odd 1d file (risk key) is a 'full' by keys ('hakem','tech_data'): handled above ---
    # --- scans ---
    for fn in names:
        if re.match(r"^scan_(1h_.*|latest)\.json$", fn):
            raw = jload(os.path.join(OUTS, fn)); wj(os.path.join(OUT, "scans", fn), {"schema_version": SV, "source": "scan.py", "raw": raw}); M["scans"].append({"file": f"scans/{fn}", "source": "scan.py"})
    # --- TradingAgents runs ---
    ta_runs = export_ta(M)
    # --- backtests / paper ---
    export_backtests(M)
    # --- code ---
    export_code(M)
    # --- tables, rules, equity ---
    wj(os.path.join(OUT, "deterministic_rules.json"), {"schema_version": SV, "rules": RULES, "notes": ["indicator/pattern computation (levels.py, patterns.py, extras.py, liq.py) is listed as code (copied to code/) not enumerated as rules: they produce data blocks for the LLM, not entry/exit decisions", "radar_read.py is a standalone reader; not in the live decision path"]})
    wj(os.path.join(OUT, "llm_layer.json"), {"schema_version": SV, **llm_layer()})
    write_tables(table); equity_curve()
    # confidence scale (observed)
    cv = [c for c in confs if num(c)]
    scale = {"declared": "0-100 integer (prompt: 'guven' 0-100; trader min_confidence=%s, leverage tiers 65/70/80)" % TR["min_confidence"], "observed_min": min(cv) if cv else None, "observed_max": max(cv) if cv else None, "n_observed": len(cv)}
    for r in M["runs"]:
        pth = os.path.join(OUT, r["file"]); o = jload(pth); o["confidence_scale"] = scale; wj(pth, o)
    wj(os.path.join(OUT, "manifest.json"), M)
    write_readme(M, scale)
    print("export done:", {k: len(v) for k, v in M.items() if isinstance(v, list)}, "NaN->null:", sum(NAN_COUNT.values()))

def export_ta(M):
    specs = [("BTC-USD", f"{TA_TEST}/BTC-USD", f"{TA_TEST}/BTC-USD/results/BTC-USD/TradingAgentsStrategy_logs/full_states_log_2026-10-22.json", f"{TA_TEST}/BTC-USD.log", f"{TA_TEST}/run_coin.py"),
             ("BTC-USD", f"{TA_TEST}/openrouter/BTC-USD", f"{TA_TEST}/openrouter/BTC-USD/results/BTC-USD/TradingAgentsStrategy_logs/full_states_log_2026-10-22.json", f"{TA_TEST}/openrouter/BTC-USD.log", f"{TA_TEST}/openrouter/run_or.py"),
             ("ETH-USD", f"{TA_TEST}/openrouter/ETH-USD", f"{TA_TEST}/openrouter/ETH-USD/results/ETH-USD/TradingAgentsStrategy_logs/full_states_log_2026-10-22.json", f"{TA_TEST}/openrouter/ETH-USD.log", f"{TA_TEST}/openrouter/run_or.py")]
    git_head = None
    try:
        import subprocess; git_head = subprocess.run(["git", "-C", TA_REPO, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", TA_REPO, "status", "--short"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception: dirty = None
    for tk, d, flog, log, script in specs:
        if not os.path.exists(flog): M["skipped"].append({"file": flog, "reason": "missing"}); continue
        fs = jload(os.path.join(d, "final_state.json")); st = fs["state"]; fl = jload(flog); rs = fl.get("run_settings") or {}
        run_id = rid("tradingagents-test/" + os.path.relpath(flog, TA_TEST))
        rdb = st["investment_debate_state"]; kdb = st["risk_debate_state"]
        # state['*_debate_state'] were stringified by the test script (str(v)); full_states_log has real dicts -> use log dicts
        idb = fl["investment_debate_state"]; rkb = fl["risk_debate_state"]
        np_ = ["run.started_at/finished_at (not stored)", "messages (test scripts dropped 'messages' from final_state.json and TradingAgents full_states_log has none) -> no messages/<RUN_ID>.json",
               "analyst_reports.fundamentals (fundamentals analyst not selected; value is empty string in source)", "numeric_context.last_price & other (TradingAgents state has no numeric fields; numbers only inside report text)",
               "risk_debate.latest_speaker (key absent in state)", "memory.past_context / memory_note / portfolio_context (empty strings in source)", "research_debate.rounds (only config max_debate_rounds)"]
        out = {"schema_version": SV, "exported_at": EXPORTED_AT,
               "producer": {"framework": "TradingAgents", "version": rs.get("version"), "git_commit": git_head, "git_dirty_files": dirty, "llm_provider": rs.get("llm_provider"), "deep_think_llm": rs.get("deep_think_llm"), "quick_think_llm": rs.get("quick_think_llm"), "selected_analysts": rs.get("analysts"), "output_language": rs.get("output_language")},
               "run": {"run_id": run_id, "ticker": st.get("company_of_interest"), "asset_type": st.get("asset_type"), "trade_date": st.get("trade_date"), "instrument_context": st.get("instrument_context"), "portfolio_context": st.get("portfolio_context") or None, "started_at": None, "finished_at": None, "duration_seconds": fs.get("runtime_s"), "source_file": flog},
               "final": {"rating": st.get("final_rating"), "decision_text": st.get("final_trade_decision")},
               "analyst_reports": {"market": st.get("market_report"), "sentiment": st.get("sentiment_report"), "news": st.get("news_report"), "fundamentals": st.get("fundamentals_report") or None},
               "research_debate": {"bull_history": idb.get("bull_history"), "bear_history": idb.get("bear_history"), "full_history": idb.get("history"), "last_response": idb.get("current_response"), "rounds": None, "config_max_debate_rounds": rs.get("max_debate_rounds")},
               "research_manager_plan": st.get("investment_plan"), "trader_proposal": st.get("trader_investment_plan"),
               "risk_debate": {"aggressive_history": rkb.get("aggressive_history"), "conservative_history": rkb.get("conservative_history"), "neutral_history": rkb.get("neutral_history"), "full_history": rkb.get("history"), "latest_speaker": rkb.get("latest_speaker"), "rounds": None, "config_max_risk_discuss_rounds": rs.get("max_risk_discuss_rounds")},
               "memory": {"past_context": st.get("past_context") or None, "memory_note": st.get("memory_note") or None},
               "numeric_context": {"_aciklama": "TradingAgents state has no numeric fields.", "last_price": None, "other": {}},
               "data_used": sorted({f"{k}:{v}" for k, v in (rs.get("data_vendors") or {}).items()}), "data_missing": [x for x in ("fundamentals (analyst not selected)",)], "not_produced": np_,
               "mapping_notes": {"source": "TradingAgents-native mapping: state.* fields 1:1; debate dicts from full_states_log (final_state.json holds them str()-ified)", "ollama_run_models": fs.get("models")},
               "not_investment_advice": True, "raw_native": {"final_state.json": fs, "full_states_log_2026-10-22.json": fl}}
        fname = f"{tk}_na_{st.get('trade_date')}_{run_id}.json"; wj(os.path.join(OUT, "runs", fname), out)
        wj(os.path.join(OUT, "config", run_id + ".json"), {"schema_version": SV, "run_id": run_id, "run_settings": rs, "driver_script": os.path.basename(script), "driver_script_source": open(script, encoding="utf-8").read(), "models_field": fs.get("models"), "api_keys": "none written"})
        M["configs"].append({"run_id": run_id, "file": f"config/{run_id}.json"})
        M["runs"].append({"run_id": run_id, "ticker": tk, "asset_type": st.get("asset_type"), "trade_date": st.get("trade_date"), "timeframe": None, "variant": "tradingagents", "file": f"runs/{fname}"})
        rep_src = os.path.join(d, "report")
        if os.path.isdir(rep_src):
            for root, _, files in os.walk(rep_src):
                for f in files:
                    dst = os.path.join(OUT, "reports", run_id, os.path.relpath(os.path.join(root, f), rep_src)); copy(os.path.join(root, f), dst); M["reports"].append({"run_id": run_id, "file": rel(dst)})
        if os.path.exists(os.path.join(d, "memory.md")): dst = copy(os.path.join(d, "memory.md"), os.path.join(OUT, "reports", run_id, "memory.md")); M["reports"].append({"run_id": run_id, "file": rel(dst)})
        if os.path.exists(log):
            txt = open(log, encoding="utf-8", errors="replace").read()
            if SECRET_RE.search(txt): M["skipped"].append({"file": log, "reason": "contains key-like string"})
            else: dst = copy(log, os.path.join(OUT, "reports", run_id, "stdout_debug.log")); M["reports"].append({"run_id": run_id, "file": rel(dst)})
    return True

SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{20,}|\b\d{8,}:[A-Za-z0-9_-]{30,}|Bearer\s+[A-Za-z0-9._-]{20,}|[A-Za-z0-9_]*API_KEY[ \t]*=[ \t]*\S{8,})")
SKIP_DIRS = {".cache", "ema_cache", "combo_bt", "venv", "__pycache__", "bt_cache", "data", "cache", "funding"}
MAX_EMBED = 1_000_000

def wrap_file(p, relp, M):
    sz = os.path.getsize(p); ext = os.path.splitext(p)[1].lower(); wid = relp.replace("/", "__")
    base = {"schema_version": SV, "source": relp, "source_size_bytes": sz, "source_sha256": sha_file(p)}
    if ext == ".json":
        raw = jload(p); wj(os.path.join(OUT, "backtests", wid + ".json"), base | {"source": relp, "raw": raw}); M["backtests"].append({"file": f"backtests/{wid}.json", "source": relp, "kind": "json"})
    elif ext == ".jsonl" and sz <= MAX_EMBED:
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]; wj(os.path.join(OUT, "backtests", wid + ".json"), base | {"raw": {"jsonl_lines": rows}}); M["backtests"].append({"file": f"backtests/{wid}.json", "source": relp, "kind": "jsonl"})
    elif ext == ".csv":
        with open(p, newline="", encoding="utf-8") as f: rd = list(csv.DictReader(f))
        cols = list(rd[0].keys()) if rd else []
        if sz <= MAX_EMBED:
            def conv(v):
                if v is None or v == "": return None
                try:
                    x = float(v)
                    if math.isnan(x) or math.isinf(x): return None
                    return int(x) if re.fullmatch(r"-?\d+", v.strip()) else x
                except Exception: return v
            raw = {"columns": cols, "n_rows": len(rd), "rows": [{k: conv(v) for k, v in r.items()} for r in rd], "note": "numeric-looking cells converted to JSON numbers, empty -> null; original CSV copied in backtests/files/"}
        else: raw = {"columns": cols, "n_rows": len(rd), "rows": None, "note": "file >1MB: rows not embedded, see copied CSV"}
        copy(p, os.path.join(OUT, "backtests", "files", wid)); wj(os.path.join(OUT, "backtests", wid + ".json"), base | {"raw": raw}); M["backtests"].append({"file": f"backtests/{wid}.json", "source": relp, "kind": "csv", "copied": f"backtests/files/{wid}"})
    elif ext in (".md", ".txt", ".log") and sz <= 3_000_000:
        txt = open(p, encoding="utf-8", errors="replace").read()
        if SECRET_RE.search(txt): M["skipped"].append({"file": relp, "reason": "key-like string"}); return
        copy(p, os.path.join(OUT, "backtests", "files", wid)); M["backtests"].append({"file": f"backtests/files/{wid}", "source": relp, "kind": ext[1:], "sha256": base["source_sha256"]})
    elif ext in (".py",): copy(p, os.path.join(OUT, "code", "research_scripts", relp)); M["code_files"].append(f"code/research_scripts/{relp}")
    else: M["datasets_referenced_not_copied"].append({"path": relp, "size_bytes": sz, "reason": "binary/raw dataset or >1MB non-embeddable"})

def export_backtests(M):
    skip_runs = re.compile(r"^([A-Z0-9]+USDT)_(mtf-1h|1h|1d)_.*\.(json|md)$"); handled = re.compile(r"^scan_(1h_.*|latest)\.(json|csv)$")
    for root, dirs, files in os.walk(OUTS):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            p = os.path.join(root, f); relp = os.path.relpath(p, OUTS)
            if root == OUTS and (skip_runs.match(f) and not f.startswith("backtest_") or handled.match(f)): continue
            if f.endswith((".lock", ".tmp", ".pid")) or f == ".lock": continue
            if f.startswith("scan_") and f.endswith(".csv") and root == OUTS: continue
            wrap_file(p, "outputs/" + relp, M)
    for d in SKIP_DIRS:
        for pth in glob.glob(os.path.join(OUTS, "**", d), recursive=True):
            if os.path.isdir(pth) and "venv" not in pth:
                tot = sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(pth) for x in fs); M["datasets_referenced_not_copied"].append({"path": "outputs/" + os.path.relpath(pth, OUTS) + "/", "size_bytes": tot, "reason": "raw data/cache directory (referenced, not copied)"})
    M["datasets_referenced_not_copied"].append({"path": "outputs/research/hft/venv/", "size_bytes": None, "reason": "python virtualenv (excluded)"})
    for extra in ("liqbt_out.pkl", "liqbt_cache"):
        pth = os.path.join(HERE, extra)
        if os.path.exists(pth): M["datasets_referenced_not_copied"].append({"path": extra, "size_bytes": os.path.getsize(pth) if os.path.isfile(pth) else sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(pth) for x in fs), "reason": "pickle / cache (excluded)"})
    for extra in ("liqbt_signals_report.txt", "grounding_report.md", "time_machine_report.md", "risk_debate_design.md"):
        if os.path.exists(os.path.join(HERE, extra)): wrap_file(os.path.join(HERE, extra), extra, M)

def export_code(M):
    keep_ext = (".py", ".sh", ".json", ".md")
    for f in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, f)
        if not os.path.isfile(p) or f in ("handoff_export.py", "handoff_validate.py") or not f.endswith(keep_ext) or f == "liqbt_out.pkl": continue
        txt = open(p, encoding="utf-8", errors="replace").read()
        if SECRET_RE.search(txt): M["skipped"].append({"file": f, "reason": "key-like string"}); continue
        if f == "config.json": wj(os.path.join(OUT, "code", f), {"_note": "masked copy (no secrets found; key_env = env var names only)", **CFG_MASKED}); M["code_files"].append("code/config.json"); continue
        copy(p, os.path.join(OUT, "code", f)); M["code_files"].append("code/" + f)
    for f in sorted(glob.glob(os.path.join(HERE, "tests", "*.py"))): copy(f, os.path.join(OUT, "code", "tests", os.path.basename(f))); M["code_files"].append("code/tests/" + os.path.basename(f))
    for f in ("handoff_export.py", "handoff_validate.py"):
        if os.path.exists(os.path.join(HERE, f)): copy(os.path.join(HERE, f), os.path.join(OUT, "code", f)); M["code_files"].append("code/" + f)
    envn = ["# Key NAMES only (generated by handoff_export.py from config.json providers[].key_env and trader.py). No values."] + sorted({p["key_env"] for p in CFG["providers"] if p.get("key_env")} | {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"})
    open(os.path.join(OUT, "code", ".env.example"), "w").write("\n".join(f"{n}=" if not n.startswith("#") else n for n in envn) + "\n"); M["code_files"].append("code/.env.example")
    # TradingAgents customised / driver files
    for src, dst in [(f"{TA_TEST}/run_coin.py", "tradingagents/run_coin.py"), (f"{TA_TEST}/openrouter/run_or.py", "tradingagents/run_or.py"), (f"{TA_REPO}/pyproject.toml", "tradingagents/pyproject.toml"), (f"{TA_REPO}/requirements.txt", "tradingagents/requirements.txt"),
                     (f"{TA_REPO}/main.py", "tradingagents/main.py"), (f"{TA_REPO}/tradingagents/default_config.py", "tradingagents/tradingagents/default_config.py"), (f"{TA_REPO}/tradingagents/agents/tools.py", "tradingagents/tradingagents/agents/tools.py (MODIFIED vs git HEAD)".replace(" (MODIFIED vs git HEAD)", ""))]:
        if os.path.exists(src): copy(src, os.path.join(OUT, "code", dst)); M["code_files"].append("code/" + dst)
    for root, _, files in os.walk(f"{TA_REPO}/tradingagents/agents"):
        if "__pycache__" in root: continue
        for f in files:
            if f.endswith(".py"):
                dst = os.path.join(OUT, "code", "tradingagents", "tradingagents", "agents", os.path.relpath(os.path.join(root, f), f"{TA_REPO}/tradingagents/agents")); copy(os.path.join(root, f), dst); rr = "code/" + os.path.relpath(dst, os.path.join(OUT, "code"))
                if rr not in M["code_files"]: M["code_files"].append(rr)
    try:
        import subprocess; diff = subprocess.run(["git", "-C", TA_REPO, "diff"], capture_output=True, text=True, timeout=20).stdout
        open(os.path.join(OUT, "code", "tradingagents", "git_diff_vs_HEAD.patch"), "w").write(diff); M["code_files"].append("code/tradingagents/git_diff_vs_HEAD.patch")
    except Exception: pass

def write_tables(rows):
    cols = ["symbol", "tf", "date_bar_open_utc", "decision", "confidence", "sl_llm", "tp_llm", "sl_rule_layer", "sl_live", "tp_live", "result", "fwd_ret_pct_24bars", "run_id", "kind"]
    rows = sorted(rows, key=lambda r: (r["date_bar_open_utc"], r["symbol"], r["tf"]))
    with open(os.path.join(OUT, "summary_table.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); [w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols}) for r in rows]
    with open(os.path.join(OUT, "summary_table.md"), "w", encoding="utf-8") as f:
        f.write("# Summary table of all bot runs (bot's own values; sl_llm/tp_llm = LLM proposal, sl_rule_layer = risk_rules stop, sl_live/tp_live = live paper trader's actual stop/target when a position was opened)\n\n")
        f.write("| " + " | ".join(cols[:-2]) + " |\n|" + "---|" * (len(cols) - 2) + "\n")
        for r in rows: f.write("| " + " | ".join("" if r.get(k) is None else str(r.get(k)) for k in cols[:-2]) + " |\n")

def equity_curve():
    P = [p for p in TRADER_L["positions"] if p.get("status") == "closed"]; P.sort(key=lambda p: p["closed_at"]); eq = TRADER_L["equity_start"]
    with open(os.path.join(OUT, "equity_curve.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time_utc", "balance_usd", "event"]); w.writerow([ist_to_z(TRADER_L.get("created_at")), eq, "ledger created (equity_start)"])
        for p in P: eq += p["pnl_usd"]; w.writerow([ist_to_z(p["closed_at"]), round(eq, 6), f"closed {p['id']} {p['exit_reason']} pnl_usd={p['pnl_usd']:.4f}"])
    # example trade record (c)
    ex = [p for p in P if p["id"] == "BTCUSDT-2026-10-24 13:00"]
    if ex:
        p = ex[0]; wj(os.path.join(OUT, "example_trade_record.json"), {"schema_version": SV, "source": "outputs/trader/ledger.json positions[id=BTCUSDT-2026-10-24 13:00]", "linked_run_file": "BTCUSDT_1h_2026-10-24T1300.json", "position_as_stored": p,
            "flat_view": {"entry": p["entry"], "entry_time_utc": ist_to_z(p["opened_at"]), "exit": p["exit"], "exit_time_utc": ist_to_z(p["closed_at"]), "pnl_usd": p["pnl_usd"], "pnl_pct": p["pnl_pct"], "sl": p["stop"], "tp": p["target"], "exit_reason": p["exit_reason"], "side": p["side"], "leverage": p["leverage"]}})

def write_readme(M, scale):
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(f"""# handoff/ (schema {SV})
Generated by `python handoff_export.py` (idempotent: folder is rebuilt; run_id = uuid5 of source filename). Validate with `python handoff_validate.py`.
Export-only: no analysis code, prompts, indicators, rules, daemons or cron were touched.

## Layout
- `manifest.json` - index (runs, messages, configs, reports, backtests, scans, code_files, datasets referenced but not copied, skipped)
- `runs/<SYMBOL>_na_<TRADE_DATE>_<RUN_ID>.json` - one per bot run (`na` = asset_type not stored by bot). Contains the schema mapping AND `raw_native` (bot's own JSON verbatim, own field names; NaN/Inf -> null).
- `config/<RUN_ID>.json`, `reports/<RUN_ID>/` (bot .md reports; TradingAgents report trees+HTML), `raw/<RUN_ID>/*.txt` (verbatim LLM outputs from outputs/.cache), `scans/` (scan.py stage-1 outputs)
- `backtests/` - every machine-readable result wrapped as {{schema_version, source, raw}}; CSVs <=1MB embedded (numbers as numbers) + original copied to `backtests/files/`; md/txt copied as-is.
- `code/` - bot source (*.py incl. prompts in agents.py, config.json masked, README, tests, .env.example names only), TradingAgents driver/modified files.
- `deterministic_rules.json` (LLM-free rule layer with verbatim code excerpts), `llm_layer.json`
- `summary_table.csv|md`, `equity_curve.csv` (assembled from closed positions with the bot's own equity() formula; the bot writes no equity-curve file), `example_trade_record.json`
- `validation_report.json|md` (from handoff_validate.py)

## Mapping (crypto-agents custom 6-role bot -> handoff/1.0)
| schema | source |
|---|---|
| final.rating | hakem.karar (mtf: karar.karar), unchanged BUY/SELL/HOLD |
| final.decision_text | verbatim hakem_raw LLM text from .cache (else JSON of hakem); structured hakem in final.decision_structured |
| analyst_reports.market / sentiment | teknik_analist / duygu_analisti (full text); news, fundamentals = null (no such agents) |
| research_debate.bull/bear | boga / ayi (single pass); full_history/last_response/rounds = null |
| research_manager_plan | null (hakem is the one decision step, mapped to final) |
| trader_proposal | kagit_islem as-is |
| risk | risk_llm (advisory LLM; not read by trader) + risk_kural (rule layer) |
| memory.past_context / memory_note | memory / lessons_block |
| numeric_context | extras and numeric fields as they appear; last_price only from kagit_islem.entry (= signal-bar close) or linked ledger record |
| run.trade_date / signal_bar_open_utc | data_date / time = candle OPEN time, already UTC |
| run.finished_at | kagit_islem.recorded_at (+0300 -> UTC Z); null for MTF files; file_mtime_utc always given |

Confidence scale: {scale}. Times: all Z; source +0300 values converted from their own offset.
Messages: the bot keeps no message list -> no `messages/` files (recorded in not_produced). TradingAgents test runs also have none (test scripts dropped `messages`).
""")

EXPORTED_AT = now_z()
if __name__ == "__main__": main()
