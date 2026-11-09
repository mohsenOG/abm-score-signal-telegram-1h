"""
Global configuration for ABM Bias Signal Machine (KuCoin REST, 1h, bar-close).
Edit this file directly.
"""

from dataclasses import dataclass
from pathlib import Path

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


TIMEFRAME = TimeframeConfig(
    key="1hour",
    kline_type="1hour",
    timeframe_seconds=60 * 60,
    warmup_candles=1500,
    fetch_last_n_candles=200,
    label="1h",
)

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
