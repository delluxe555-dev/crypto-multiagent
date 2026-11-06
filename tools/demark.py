"""demark.py — TD Sequential (Setup 9 / Countdown 13) motoru.

`td_sequential_trp_v1.pine` (Pine v6) kurallarinin Python portu.
Yalnizca KAPANMIS mumlar islenir; cagiran taraf son (kapanan) bari verir.

Olaylar (son bar icin):
  - 9      : ham Setup tamamlandi (alim/satim)
  - M9     : mukemmel Setup (8. veya 9. mumun 6-7'ye gore ekstremi)
  - CD13   : Countdown 13 (CD8 kapanis dogrulamasiyla)
  - flip13 : CD13 sonrasi ilk ters yon 1 onayi
  - 9139   : ortusmesiz 9-13-9 sonrasi ters 1 onayi

Seviyeler:
  - TDST   : alim 9'dan max(high), satim 9'dan min(low)
  - setup_risk / cd_risk : risk cizgileri (varsayilan High-Low araligi,
    risk kirilimi kapanis bazli)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class _Side:
    buy: bool
    setup: int = 0
    setup_start: int | None = None
    setup_hi: float | None = None
    setup_lo: float | None = None
    range_at_hi: float | None = None
    range_at_lo: float | None = None
    tdst: float | None = None
    setup_risk: float | None = None
    cd_risk: float | None = None
    cd_active: bool = False
    cd: int = 0
    cd8_close: float | None = None
    defining_tdst: float | None = None
    cd_extreme: float | None = None
    cd_extreme_range: float | None = None
    wait_flip13: int | None = None
    chain13: int | None = None
    chain9: int | None = None


def _update_setup(s: _Side, matches: bool, i: int,
                  high: float, low: float, rng: float) -> bool:
    """Kesintisiz yon serisinde 9'a kadar sayar; 9'da doyar."""
    if not matches:
        s.setup = 0
        s.setup_start = None
        return False
    if s.setup < 9:
        s.setup += 1
        if s.setup == 1:
            s.setup_start = i
            s.setup_hi = high
            s.setup_lo = low
            s.range_at_hi = rng
            s.range_at_lo = rng
        else:
            # Esit ekstremumda ilk mum korunur; aralik ayni uc mumdan alinir.
            if high > (s.setup_hi if s.setup_hi is not None else high):
                s.setup_hi = high
                s.range_at_hi = rng
            if low < (s.setup_lo if s.setup_lo is not None else low):
                s.setup_lo = low
                s.range_at_lo = rng
        return s.setup == 9
    return False


def _include_cd_risk(s: _Side, high: float, low: float, rng: float) -> None:
    extreme = low if s.buy else high
    if s.cd_extreme is None or (extreme < s.cd_extreme if s.buy else extreme > s.cd_extreme):
        s.cd_extreme = extreme
        s.cd_extreme_range = rng


def _advance(s: _Side, own9: bool, opposite9: bool, flip: bool, i: int,
             high: list[float], low: list[float], close: list[float],
             rng: float, all_cd_bars: bool, whole_risk_bar: bool) -> dict:
    """Setup/CD yasam dongusu; Pine `advance` metodunun portu."""
    out = {"pulse": 0, "deferred": False, "canceled": False,
           "completed13": False, "confirmed13": False, "confirmed9139": False}

    # Iptal artistan ONCE: ayni mum iptal edilmis CD'nin 13'u olamaz.
    if s.cd_active and (opposite9 or (low[i] > s.defining_tdst if s.buy
                                      else high[i] < s.defining_tdst)):
        s.cd_active = False
        s.cd = 0
        s.cd8_close = None
        s.defining_tdst = None
        s.cd_extreme = None
        s.cd_extreme_range = None
        out["canceled"] = True

    if opposite9:
        s.wait_flip13 = None
        s.chain13 = None
        s.chain9 = None

    # TDST kapanisla; risk, secilen kapanis/tum-mum kosuluyla sonlanir.
    if s.tdst is not None and (close[i] > s.tdst if s.buy else close[i] < s.tdst):
        s.tdst = None

    if s.setup_risk is not None:
        if s.buy:
            broken = (high[i] < s.setup_risk) if whole_risk_bar else (close[i] < s.setup_risk)
        else:
            broken = (low[i] > s.setup_risk) if whole_risk_bar else (close[i] > s.setup_risk)
        if broken:
            s.setup_risk = None

    if s.cd_risk is not None:
        if s.buy:
            broken = (high[i] < s.cd_risk) if whole_risk_bar else (close[i] < s.cd_risk)
        else:
            broken = (low[i] > s.cd_risk) if whole_risk_bar else (close[i] > s.cd_risk)
        if broken:
            s.cd_risk = None

    if own9:
        s.tdst = s.setup_hi if s.buy else s.setup_lo
        s.setup_risk = ((s.setup_lo - s.range_at_lo) if s.buy
                        else (s.setup_hi + s.range_at_hi))
        # Ayni yon 9 aktif CD'yi/sinirini korur: sessiz recycle yok.
        if not s.cd_active:
            s.cd_active = True
            s.cd = 0
            s.cd8_close = None
            s.defining_tdst = s.tdst
            s.cd_extreme = None
            s.cd_extreme_range = None

    if s.cd_active:
        eligible = (close[i] <= low[i - 2]) if s.buy else (close[i] >= high[i - 2])
        qualified = s.cd < 12 or (s.cd8_close is not None and
                                  ((low[i] <= s.cd8_close) if s.buy
                                   else (high[i] >= s.cd8_close)))
        accepted = eligible and qualified
        if (all_cd_bars and s.cd > 0) or accepted:
            _include_cd_risk(s, high[i], low[i], rng)
        if eligible:
            if qualified:
                s.cd += 1
                out["pulse"] = s.cd
                if s.cd == 8:
                    s.cd8_close = close[i]
                if s.cd == 13:
                    out["completed13"] = True
                    s.cd_active = False
                    s.cd_risk = ((s.cd_extreme - s.cd_extreme_range) if s.buy
                                 else (s.cd_extreme + s.cd_extreme_range))
                    s.wait_flip13 = i
                    # Ilk tuketilmemis zincir korunur; yeni 13 eskisini silmez.
                    if s.chain13 is None:
                        s.chain13 = i
                        s.chain9 = None
            else:
                # Ana kosul var ama CD8 qualifier yok: 12'de kal, + yaz.
                out["deferred"] = True

    if own9 and s.chain13 is not None and s.setup_start is not None and s.setup_start > s.chain13:
        s.chain9 = i
    if flip and s.wait_flip13 is not None and i > s.wait_flip13:
        out["confirmed13"] = True
        s.wait_flip13 = None
    if flip and s.chain9 is not None and i > s.chain9:
        out["confirmed9139"] = True
        s.chain13 = None
        s.chain9 = None

    return out


def run(df: pd.DataFrame) -> dict:
    """OHLC DataFrame -> son barin TD Sequential durumu/olaylari."""
    n = len(df)
    empty = {
        "bars": n, "buy_setup": 0, "sell_setup": 0,
        "buy_cd": None, "sell_cd": None,
        "buy9": False, "sell9": False, "buyM9": False, "sellM9": False,
        "buy13": False, "sell13": False,
        "buy_flip": False, "sell_flip": False,
        "buy9139": False, "sell9139": False,
        "tdst_res": None, "tdst_sup": None,
        "setup_risk_buy": None, "setup_risk_sell": None,
        "cd_risk_buy": None, "cd_risk_sell": None,
    }
    if n < 6:
        return empty

    high = [float(x) for x in df["high"]]
    low = [float(x) for x in df["low"]]
    close = [float(x) for x in df["close"]]

    buy, sell = _Side(True), _Side(False)
    last = dict(empty)
    last.update({"bars": n})

    for i in range(n):
        if i < 5:          # close[4] / close[5] yok -> sayim baslamaz
            continue
        rng = high[i] - low[i]
        direction = -1 if close[i] < close[i - 4] else (1 if close[i] > close[i - 4] else 0)
        prior_dir = (-1 if close[i - 1] < close[i - 5]
                     else 1 if close[i - 1] > close[i - 5] else 0)
        # flipAfterEqual = true (varsayilan)
        bull_flip = direction == 1 and (prior_dir == -1 or prior_dir == 0)
        bear_flip = direction == -1 and (prior_dir == 1 or prior_dir == 0)
        buy_perfect = ((low[i] <= low[i - 2] and low[i] <= low[i - 3]) or
                       (low[i - 1] <= low[i - 2] and low[i - 1] <= low[i - 3]))
        sell_perfect = ((high[i] >= high[i - 2] and high[i] >= high[i - 3]) or
                        (high[i - 1] >= high[i - 2] and high[i - 1] >= high[i - 3]))

        b9 = _update_setup(buy, direction == -1, i, high[i], low[i], rng)
        s9 = _update_setup(sell, direction == 1, i, high[i], low[i], rng)
        bM = b9 and buy_perfect
        sM = s9 and sell_perfect
        br = _advance(buy, b9, s9, bull_flip, i, high, low, close, rng, False, False)
        sr = _advance(sell, s9, b9, bear_flip, i, high, low, close, rng, False, False)

        last.update({
            "buy_setup": buy.setup, "sell_setup": sell.setup,
            "buy_cd": buy.cd if buy.cd_active else None,
            "sell_cd": sell.cd if sell.cd_active else None,
            "buy9": b9, "sell9": s9, "buyM9": bM, "sellM9": sM,
            "buy13": br["completed13"], "sell13": sr["completed13"],
            "buy_flip": br["confirmed13"], "sell_flip": sr["confirmed13"],
            "buy9139": br["confirmed9139"], "sell9139": sr["confirmed9139"],
            "tdst_res": buy.tdst, "tdst_sup": sell.tdst,
            "setup_risk_buy": buy.setup_risk, "setup_risk_sell": sell.setup_risk,
            "cd_risk_buy": buy.cd_risk, "cd_risk_sell": sell.cd_risk,
        })

    return last


td_sequential = run


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataflows"))
    import binance as bn  # noqa: E402

    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "15m"
    rows = bn.get_klines(sym.replace(".P", ""), tf, 400, market="perp")
    d = pd.DataFrame(rows).set_index("open_time")
    print(run(d))
