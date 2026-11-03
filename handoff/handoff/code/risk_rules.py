"""Kural tabanlı risk yöneticisi (LLM'siz, deterministik): ATR'ye dayalı stop ve pozisyon büyüklüğü, günlük zarar limiti."""
RISK_PER_TRADE = 0.01      # işlem başına özsermayenin %1'i
ATR_MULT = {"15m": 2.0, "1h": 2.0, "4h": 1.75, "1d": 1.5}
DAILY_LOSS_LIMIT = 0.02    # gün içi gerçekleşen zarar özsermayenin %2'sini geçerse yeni işlem yok
MAX_POS_FRAC = 0.5         # tek pozisyon özsermayenin en fazla %50'si

def size(decision, price, atr, equity, realized_today, interval="1d"):
    k = ATR_MULT.get(interval, 1.5)
    atr_stop = price - k * atr
    stop = decision.get("stop")
    try: stop = float(stop)
    except (TypeError, ValueError): stop = None
    # LLM stopu yoksa / yanlış taraftaysa / ATR stopundan çok darsa ATR stopunu kullan
    if stop is None or stop >= price or (price - stop) < 0.5 * atr: stop, src = atr_stop, f"ATR×{k}"
    else: src = "hakem"
    risk_usd = equity * RISK_PER_TRADE; per_unit = price - stop
    pos = min(risk_usd / per_unit * price, equity * MAX_POS_FRAC) if per_unit > 0 else 0
    blocked = None
    if realized_today <= -DAILY_LOSS_LIMIT * equity: blocked = f"günlük zarar limiti (%{DAILY_LOSS_LIMIT*100:.0f}) aşıldı"
    elif decision.get("karar") != "BUY": blocked = "karar BUY değil (yalnızca long/nakit kâğıt işlem)"
    return {"stop": round(stop, 2), "stop_kaynak": src, "pozisyon_usd": round(pos, 2) if not blocked else 0,
            "risk_usd": round(risk_usd, 2), "atr": round(atr, 2), "engel": blocked}
