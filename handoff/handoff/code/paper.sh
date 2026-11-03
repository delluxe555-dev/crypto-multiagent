#!/usr/bin/env bash
# Kâğıt işlem botu kontrolü: ./paper.sh start|stop|status|restart|ensure|cycle|summary   (gerçek emir YOK)
cd "$(dirname "$0")"; D=$(pwd); PID=$D/logs/daemon.pid; STOPF=$D/logs/STOPPED; PY=$D/.venv/bin/python
mkdir -p logs
running() { [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null && tr "\0" " " < /proc/"$(cat "$PID")"/cmdline 2>/dev/null | grep -q "trader.py daemon"; }
case "$1" in
  start)  rm -f "$STOPF"; if running; then echo "zaten çalışıyor (pid $(cat $PID))"; exit 0; fi
          PYTHONUNBUFFERED=1 nohup setsid "$PY" -u trader.py daemon >> logs/daemon.out 2>&1 < /dev/null & echo $! > "$PID"; sleep 1
          running && echo "başladı (pid $(cat $PID))" || { echo "başlatılamadı, bkz logs/daemon.out"; exit 1; } ;;
  stop)   touch "$STOPF"; if running; then kill "$(cat $PID)"; sleep 1; echo "durduruldu"; else echo "çalışmıyordu"; fi; rm -f "$PID" ;;
  restart) "$0" stop; "$0" start ;;
  ensure) [ -f "$STOPF" ] || running || "$0" start >/dev/null 2>&1 ;;   # yeniden başlatma sonrası otomatik kaldırma (bashrc kancası)
  status) if running; then echo "ÇALIŞIYOR pid $(cat $PID)"; else echo "DURMUŞ$([ -f $STOPF ] && echo ' (elle durduruldu)')"; fi
          "$PY" - <<'P'
import json
s=json.load(open("outputs/trader/summary.json")) if __import__("os").path.exists("outputs/trader/summary.json") else {}
st=json.load(open("outputs/trader/state.json")) if __import__("os").path.exists("outputs/trader/state.json") else {}
print(f"özsermaye ${s.get('equity_realized')} (getiri {s.get('return_%')}%), açık K/Z ${s.get('unrealized_usd')}, kapanan {s.get('closed_n')} (kazanan {s.get('wins')})")
for p in s.get("open_positions", []): print("  AÇIK", p["symbol"], p["side"], f"{p.get('leverage',1)}x teminat ${p.get('margin') or 0:.0f}", "giriş", round(p["entry"],6), "stop", round(p["stop"],6), "hedef", round(p["target"],6), "büyüklük $%.0f" % p["notional"])
print("son döngü:", st.get("last_cycle"), "| LLM bugün (UTC):", st.get("llm_calls"), "| son özet:", st.get("last_morning"))
P
          echo "--- son log"; tail -n 8 logs/trader.log 2>/dev/null ;;
  cycle)  shift; "$PY" -u trader.py cycle "$@" ;;
  summary) shift; "$PY" -u trader.py summary "$@" ;;
  *) echo "kullanım: $0 start|stop|status|restart|ensure|cycle [--top N]|summary [--send]"; exit 1 ;;
esac
