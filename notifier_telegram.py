from __future__ import annotations

import time
from typing import List, Optional

import pandas as pd
import requests

import config


def build_signal_message(
    *,
    symbol: str,
    kline_type: str,
    side: str,
    ts: pd.Timestamp,
    close: float,
    bias: float,
    bias_threshold: float,
    total_votes: int,
    confidence: float,
) -> str:
    return (
        f"[{symbol} {kline_type}] {side}\n"
        f"ts={ts} | close={close:.4f}\n"
        f"bias={bias:.5f} | thr=±{bias_threshold}\n"
        f"total_votes={total_votes} / 21 | confidence={confidence:.3f}"
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_ids: List[int]) -> None:
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.session = requests.Session()

    def _reset_session(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
        self.session = requests.Session()

    def send(self, text: str, *, startup: bool = False) -> None:
        if not config.TELEGRAM_ENABLED:
            return

        max_attempts = 1 if startup else config.HTTP_MAX_RETRIES
        timeout = (5, 5) if startup else (
            config.HTTP_CONNECT_TIMEOUT_SECONDS, config.HTTP_READ_TIMEOUT_SECONDS
        )

        for chat_id in self.chat_ids:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}

            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = self.session.post(
                        url,
                        json=payload,
                        timeout=timeout,
                    )
                    if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                        raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:500]}", response=resp)

                    resp.raise_for_status()
                    print(f"[telegram] sent chat_id={chat_id}")
                    break

                except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                    last_exc = exc
                    self._reset_session()
                    print(f"[telegram] send failed attempt={attempt}/{max_attempts} chat_id={chat_id} err={repr(exc)}")
                    if attempt >= max_attempts:
                        print(f"[telegram] giving up chat_id={chat_id} last_err={repr(last_exc)}")
                        break
                    print(f"[telegram] retrying in {config.HTTP_RETRY_PERIOD_SECONDS}s")
                    time.sleep(config.HTTP_RETRY_PERIOD_SECONDS)
