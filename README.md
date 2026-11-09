# ABM Score Signal Telegram (1h)

The bot monitors `PAXG-USDT` on KuCoin spot and sends Telegram alerts from closed 1-hour candles.

## How signals work

The bot uses Heikin Ashi candles by default. It combines 21 votes from moving averages, RSI, MACD, Bollinger Bands, breakouts, and rate of change. The bias score is the sum of the votes divided by 21.

With the default thresholds, the bot sends a BUY alert when the bias crosses above `+0.20` and a SELL alert when it crosses below `-0.20`. Both alerts go to all configured chats.

## Setup

```sh
python -m pip install numpy pandas requests PyYAML ta
```

Create `crendetials.yml` beside `config.py` with your bot token and chat IDs. The first chat receives startup and heartbeat messages.

```yaml
TELEGRAM_BOT_TOKEN: "your-bot-token"
CHAT_IDS:
  - 123456789
```

Run `python main.py`.
