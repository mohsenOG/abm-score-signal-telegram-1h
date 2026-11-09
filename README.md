# ABM Score Signal Telegram (1h)

Telegram BUY and SELL alerts from a 21-vote score on closed 1-hour KuCoin spot candles. The default pair is `PAXG-USDT`.

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
