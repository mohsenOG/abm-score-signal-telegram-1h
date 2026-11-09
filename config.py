"""
Global configuration for ABM Bias Signal Machine (KuCoin REST, 1h, bar-close).
Edit this file directly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

# -----------------------------
# Core market settings
# -----------------------------
SYMBOL: str = "PAXG-USDT"

@dataclass(frozen=True)
class TimeframeConfig:
    key: str
    kline_type: str
    timeframe_seconds: int
    warmup_candles: int
    fetch_last_n_candles: int
    label: str


TIMEFRAMES: Dict[str, TimeframeConfig] = {
    "1hour": TimeframeConfig(
        key="1hour",
        kline_type="1hour",
        timeframe_seconds=60 * 60,
        warmup_candles=1500,
        fetch_last_n_candles=200,
        label="1h",
    ),
    "1day": TimeframeConfig(
        key="1day",
        kline_type="1day",
        timeframe_seconds=24 * 60 * 60,
        warmup_candles=1500,
        fetch_last_n_candles=200,
        label="1d",
    ),
}

# -----------------------------
# Polling / timing
# -----------------------------
SAFE_CLOSE_DELAY_SECONDS: int = 10
POLL_INTERVAL_SECONDS: int = 60
FETCH_LAST_N_CANDLES: int = 200
SERVER_TIME_RESYNC_SECONDS: int = 2 * 60 * 60  # 7200
WARMUP_CANDLES: int = 1500                     # KuCoin max per query
ALIVE_INTERVAL_SECONDS: int = 6 * 60 * 60      # 21600

# -----------------------------
# HTTP / retry policy
# -----------------------------
HTTP_CONNECT_TIMEOUT_SECONDS: int = 180
HTTP_READ_TIMEOUT_SECONDS: int = 180
HTTP_RETRY_PERIOD_SECONDS: int = 180
HTTP_MAX_RETRIES: int = 100

# -----------------------------
# Pine/indicator parameters
# -----------------------------
BIAS_THRESHOLD: float = 0.2
USE_HEIKIN_ASHI: bool = True

# -----------------------------
# Telegram
# -----------------------------
TELEGRAM_ENABLED: bool = True
with Path(__file__).with_name("crendetials.yml").open(encoding="utf-8") as credentials_file:
    _telegram_credentials = yaml.safe_load(credentials_file)

TELEGRAM_BOT_TOKEN: str = _telegram_credentials["TELEGRAM_BOT_TOKEN"]
CHAT_IDS = _telegram_credentials["CHAT_IDS"]

# Startup and alive messages go only to the first configured chat ID.
ADMIN_CHAT_ID: int = CHAT_IDS[0]

# -----------------------------
# Risk engine (advisory only)
# -----------------------------
# atr_source: "OHLC" (default) or "HA"
risk_engine = {
    "enabled": True,
    "atr_source": "OHLC",
    "atr_length": 14,
    "sl_atr_mult": 1.2,
    "tp1_atr_mult": 1.0,
    "tp1_close_pct": 0.35,
    "tp2_trail_atr_mult": 1.0,
    "long_factors": [3, 5, 7, 10],
    "short_factor": 2,
    "volatility_regime_atr_pct_bands": [0.6, 1.2, 2.0],
    "confidence_risk_map": [
        {"min_conf": 0.0, "max_conf": 0.55, "risk_pct": 0.5},
        {"min_conf": 0.55, "max_conf": 0.65, "risk_pct": 1.0},
        {"min_conf": 0.65, "max_conf": 0.75, "risk_pct": 2.0},
        {"min_conf": 0.75, "max_conf": 0.85, "risk_pct": 3.5},
        {"min_conf": 0.85, "max_conf": 1.01, "risk_pct": 5.0},
    ],
}

# Hard Stop Loss (HARD SL) settings (for execution safety, esp. factor certificates)
# Soft SL (from ATR) is a warning level: the trade idea may be invalid.
# Hard SL is the REAL stop you place with your broker to protect capital.
# IMPORTANT: position sizing must be based on HARD SL so risk_pct remains the true max loss.

HARD_SL_BUFFER_UNDERLYING_PCT: float = 1.0
# Extra safety margin (in underlying %) added on top of the soft SL.

HARD_SL_MIN_UNDERLYING_PCT: float = 2.5
# Minimum hard stop distance (in underlying %) regardless of ATR (prevents too-tight stops).
