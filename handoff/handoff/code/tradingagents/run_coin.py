import sys, time, json, traceback, os
os.environ.setdefault("TRADINGAGENTS_NO_UPDATE_CHECK","1")
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
ticker, date = sys.argv[1], sys.argv[2]
out = f"/workspace/tradingagents-test/{ticker}"
os.makedirs(out, exist_ok=True)
cfg = DEFAULT_CONFIG.copy()
cfg.update(llm_provider="ollama", deep_think_llm="qwen3-4b-local", quick_think_llm="qwen3-4b-local",
           backend_url="http://localhost:11434/v1", max_debate_rounds=1, max_risk_discuss_rounds=1,
           max_tool_rounds=6, news_article_limit=8, global_news_article_limit=5, temperature=0.3,
           results_dir=out+"/results", memory_log_path=out+"/memory.md", llm_max_retries=2)
t0=time.time()
try:
    ta = TradingAgentsGraph(selected_analysts=("market","social","news"), debug=True, config=cfg)
    state, decision = ta.propagate(ticker, date, asset_type="crypto")
    dt=time.time()-t0
    print("\n=== FINAL DECISION:", decision, f"runtime {dt:.0f}s ===")
    keep = {k:(v if isinstance(v,(str,int,float)) else str(v)) for k,v in state.items() if k!="messages"}
    json.dump({"decision":decision,"runtime_s":dt,"state":keep}, open(out+"/final_state.json","w"), indent=2, default=str)
    try: print("report saved:", ta.save_reports(state, ticker, save_path=out+"/report"))
    except Exception as e: print("save_reports failed", e)
except Exception:
    traceback.print_exc(); print("FAILED after", time.time()-t0)
