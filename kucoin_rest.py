from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

import config


@dataclass(frozen=True)
class Candle:
    ts: int  # candle start time (seconds, UTC)
    open: float
    close: float
    high: float
    low: float
    volume: float
    turnover: float


class KuCoinREST:
    """KuCoin spot public REST client (no websockets)."""

    BASE_URL = "https://api.kucoin.com"

    def __init__(self) -> None:
        self.session = requests.Session()

    def _reset_session(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
        self.session = requests.Session()

    def _request_json(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.BASE_URL + path
        last_exc: Optional[BaseException] = None

        for attempt in range(1, config.HTTP_MAX_RETRIES + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=(config.HTTP_CONNECT_TIMEOUT_SECONDS, config.HTTP_READ_TIMEOUT_SECONDS),
                )

                # Retryable statuses
                if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                    raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:500]}", response=resp)

                resp.raise_for_status()
                return resp.json()

            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_exc = exc
                self._reset_session()
                print(
                    f"[kucoin_rest] request failed attempt={attempt}/{config.HTTP_MAX_RETRIES} "
                    f"method={method} path={path} params={params} err={repr(exc)}"
                )
                if attempt >= config.HTTP_MAX_RETRIES:
                    break
                print(f"[kucoin_rest] retrying in {config.HTTP_RETRY_PERIOD_SECONDS}s")
                time.sleep(config.HTTP_RETRY_PERIOD_SECONDS)

        raise RuntimeError(
            f"KuCoin REST request failed after retries: {method} {path} params={params} last={repr(last_exc)}"
        )

    def get_server_time_ms(self) -> int:
        j = self._request_json("GET", "/api/v1/timestamp")
        return int(j["data"])

    def get_klines(
        self,
        *,
        symbol: str,
        kline_type: str,
        start_at: Optional[int] = None,
        end_at: Optional[int] = None,
    ) -> List[Candle]:
        params: Dict[str, Any] = {
            "symbol": symbol,
            "tradeType": "SPOT",
            "klineType": "TRADE",
            "interval": kline_type,
        }
        if start_at is not None:
            params["startAt"] = int(start_at)
        if end_at is not None:
            params["endAt"] = int(end_at)

        j = self._request_json("GET", "/api/ua/v2/market/kline", params=params)
        if j.get("code") != "200000":
            raise RuntimeError(f"KuCoin kline request failed: {j.get('code')} {j.get('msg', '')}")
        rows = j["data"]["list"]

        candles: List[Candle] = []
        for r in rows:
            candles.append(
                Candle(
                    ts=int(r[0]),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]),
                    turnover=float(r[6]),
                )
            )
        return candles
