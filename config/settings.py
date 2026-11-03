"""Central configuration for the crypto multi-agent system."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class AgentWeights:
    """How much each agent's opinion counts in the consensus vote.

    Technical and derivatives carry the most weight because they are the two
    layers that actually see price behaviour and positioning. KAMA / Vortex /
    CMF are deliberately low-weight confirmation tools only.
    """

    technical: float = 0.22
    derivatives: float = 0.22
    news: float = 0.13
    fundamental: float = 0.10
    macro: float = 0.08
    bull_researcher: float = 0.075
    bear_researcher: float = 0.075


@dataclass
class ConsensusRules:
    """Voting / agreement rules."""

    # A raw weighted score above this is a directional candidate.
    min_score: float = 0.18
    # Share of weighted votes that must point the same way (agreement).
    min_agreement: float = 0.55
    # Below this agreement the system prefers HOLD over forcing a trade.
    strong_agreement: float = 0.72
    # If the two sides are this close, treat the market as undecided.
    max_conflict: float = 0.25


@dataclass
class RiskRules:
    """Risk-management defaults. The risk agent may adapt these per trade."""

    account_equity: float = 10_000.0
    risk_per_trade_pct: float = 1.0        # % of equity risked per trade
    max_position_pct: float = 100.0        # cap on notional vs equity (leverage aware)
    atr_stop_mult: float = 1.6             # SL = entry -/+ ATR * mult
    atr_stop_mult_min: float = 1.0
    atr_stop_mult_max: float = 2.6
    min_rr: float = 1.3                    # reject setups below this reward/risk
    target_rr: float = 1.8
    max_drawdown_pct: float = 15.0
    low_vol_atr_pct: float = 0.35          # ATR as % of price
    high_vol_atr_pct: float = 2.2


@dataclass
class Settings:
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    bars: int = 500
    market: str = "perp"

    # Indicator lengths
    ema_fast: int = 8
    ema_mid: int = 13
    ema_slow: int = 21
    sma_mid: int = 50
    sma_long: int = 200
    kama_len: int = 21
    vortex_len: int = 14
    cmf_len: int = 20
    rsi_len: int = 14
    atr_len: int = 14
    swing_lookback: int = 3

    # Agent weights + rules
    weights: AgentWeights = field(default_factory=AgentWeights)
    consensus: ConsensusRules = field(default_factory=ConsensusRules)
    risk: RiskRules = field(default_factory=RiskRules)

    # Optional LLM narration (agents stay deterministic; the LLM only writes prose)
    use_llm: bool = False
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_SETTINGS = Settings()

# Binance interval strings accepted by the klines endpoint
VALID_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w",
}
