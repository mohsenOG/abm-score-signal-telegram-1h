from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

import config
from kucoin_rest import Candle, KuCoinREST


def _ts_to_utc(ts_seconds: int) -> pd.Timestamp:
    return pd.to_datetime(int(ts_seconds), unit="s", utc=True)


@dataclass
class FetchResult:
    df: pd.DataFrame
    new_candle_ts: List[pd.Timestamp]


class DataEngine:
    def __init__(self, rest: KuCoinREST, timeframe: config.TimeframeConfig) -> None:
        self.rest = rest
        self.timeframe = timeframe
        self.server_offset_ms: int = 0
        self._last_server_sync_ms: int = 0

        self.df: pd.DataFrame = pd.DataFrame()
        self.last_processed_ts: Optional[pd.Timestamp] = None

    def _timeframe_delta(self) -> pd.Timedelta:
        return pd.Timedelta(seconds=self.timeframe.timeframe_seconds)

    def _timeframe_freq(self) -> str:
        return f"{self.timeframe.timeframe_seconds}s"

    def _format_timeframe(self) -> str:
        return self.timeframe.kline_type

    # ---- time sync ----
    def sync_server_time(self) -> None:
        server_ms = self.rest.get_server_time_ms()
        local_ms = int(pd.Timestamp.utcnow().timestamp() * 1000)
        self.server_offset_ms = server_ms - local_ms
        self._last_server_sync_ms = local_ms
        print(f"[time] server_ms={server_ms} local_ms={local_ms} offset_ms={self.server_offset_ms}")

    def server_now_utc(self) -> pd.Timestamp:
        local_ms = int(pd.Timestamp.utcnow().timestamp() * 1000)
        server_ms = local_ms + self.server_offset_ms
        return pd.to_datetime(server_ms, unit="ms", utc=True)

    def maybe_resync_time(self) -> None:
        local_ms = int(pd.Timestamp.utcnow().timestamp() * 1000)
        if (local_ms - self._last_server_sync_ms) >= config.SERVER_TIME_RESYNC_SECONDS * 1000:
            print(f"[time] resync due (interval={config.SERVER_TIME_RESYNC_SECONDS}s)")
            self.sync_server_time()

    # ---- candle helpers ----
    def _candles_to_df(self, candles: List[Candle]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "turnover"]).astype(float)
        rows = []
        for c in candles:
            rows.append(
                {
                    "ts": _ts_to_utc(c.ts),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "turnover": c.turnover,
                }
            )
        df = pd.DataFrame(rows).set_index("ts").sort_index()
        return df[~df.index.duplicated(keep="last")]

    def _merge_df(self, new_df: pd.DataFrame) -> None:
        if self.df.empty:
            self.df = new_df.copy()
            return
        combined = pd.concat([self.df, new_df], axis=0)
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        self.df = combined

    def _detect_missing_candles(self, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> List[pd.Timestamp]:
        if self.df.empty or start_ts > end_ts:
            return []
        expected = pd.date_range(start=start_ts, end=end_ts, freq=self._timeframe_freq(), tz="UTC")
        present = set(self.df.index)
        return [ts for ts in expected if ts not in present]

    def _backfill_missing(self, missing: List[pd.Timestamp]) -> None:
        if not missing:
            return

        delta = self._timeframe_delta()
        missing_sorted = sorted(missing)
        seg_start = missing_sorted[0]
        seg_end = missing_sorted[0]

        def flush(a: pd.Timestamp, b: pd.Timestamp) -> None:
            start_at = int(a.timestamp())
            end_at = int((b + delta).timestamp())
            print(f"[backfill] timeframe={self._format_timeframe()} startAt={start_at} endAt={end_at} ({a} -> {b})")
            candles = self.rest.get_klines(
                symbol=config.SYMBOL,
                kline_type=self.timeframe.kline_type,
                start_at=start_at,
                end_at=end_at,
            )
            self._merge_df(self._candles_to_df(candles))

        for ts in missing_sorted[1:]:
            if ts == seg_end + delta:
                seg_end = ts
            else:
                flush(seg_start, seg_end)
                seg_start = ts
                seg_end = ts
        flush(seg_start, seg_end)

    # ---- public ----
    def warmup(self) -> None:
        last_closed = self.get_latest_closed_candle_ts()
        end_at = int((last_closed + self._timeframe_delta()).timestamp()) - 1
        start_at = end_at - (self.timeframe.warmup_candles * self.timeframe.timeframe_seconds)
        print(
            f"[warmup] fetching symbol={config.SYMBOL} type={self.timeframe.kline_type} "
            f"startAt={start_at} endAt={end_at} candles={self.timeframe.warmup_candles}"
        )
        candles = self.rest.get_klines(
            symbol=config.SYMBOL,
            kline_type=self.timeframe.kline_type,
            start_at=start_at,
            end_at=end_at,
        )
        self.df = self._candles_to_df(candles)
        if self.df.empty:
            raise RuntimeError(f"Warmup returned no candles for {self.timeframe.kline_type}.")
        print(
            f"[warmup] loaded timeframe={self.timeframe.kline_type} candles={len(self.df)} "
            f"first={self.df.index.min()} last={self.df.index.max()}"
        )
        self.last_processed_ts = None

    def get_latest_closed_candle_ts(self) -> pd.Timestamp:
        server_now = self.server_now_utc()
        candidate = server_now - pd.Timedelta(seconds=config.SAFE_CLOSE_DELAY_SECONDS)
        delta = self._timeframe_delta()
        boundary = candidate.floor(self._timeframe_freq())
        return boundary - delta

    def fetch_and_update(self) -> FetchResult:
        last_closed = self.get_latest_closed_candle_ts()

        if self.last_processed_ts is not None and last_closed <= self.last_processed_ts:
            return FetchResult(df=self.df.copy(), new_candle_ts=[])

        end_at = int((last_closed + self._timeframe_delta()).timestamp())
        start_at = end_at - (self.timeframe.fetch_last_n_candles * self.timeframe.timeframe_seconds)
        print(f"[fetch] timeframe={self._format_timeframe()} last_closed={last_closed} startAt={start_at} endAt={end_at}")
        candles = self.rest.get_klines(
            symbol=config.SYMBOL,
            kline_type=self.timeframe.kline_type,
            start_at=start_at,
            end_at=end_at,
        )
        self._merge_df(self._candles_to_df(candles))

        missing = self._detect_missing_candles(self.df.index.min(), last_closed)
        if missing:
            print(f"[gap] timeframe={self._format_timeframe()} missing_candles={len(missing)} (will backfill)")
            self._backfill_missing(missing)

        eligible = self.df.index[self.df.index <= last_closed]
        if eligible.empty:
            return FetchResult(df=self.df.copy(), new_candle_ts=[])

        if self.last_processed_ts is None:
            new_ts = [last_closed] if last_closed in eligible else []
        else:
            new_ts = [ts for ts in eligible if ts > self.last_processed_ts]

        return FetchResult(df=self.df.copy(), new_candle_ts=new_ts)

    def mark_processed(self, ts: pd.Timestamp) -> None:
        if self.last_processed_ts is None or ts > self.last_processed_ts:
            self.last_processed_ts = ts
