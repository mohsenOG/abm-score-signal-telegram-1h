from __future__ import annotations

import time
import traceback

import pandas as pd

import config
from data_engine import DataEngine
from indicators import compute_bias_and_votes
from kucoin_rest import KuCoinREST
from notifier_telegram import TelegramNotifier, build_signal_message
from signals import compute_signals


def _print_startup_summary() -> None:
    timeframe = config.TIMEFRAME
    print("=== ABM Bias Signal Machine (KuCoin REST / bar-close) ===")
    print(f"symbol={config.SYMBOL}")
    print(f"timeframe={timeframe.kline_type}")
    print(f"warmup_candles={timeframe.warmup_candles}")
    print(f"fetch_last_n={timeframe.fetch_last_n_candles}")
    print(f"safe_close_delay_s={config.SAFE_CLOSE_DELAY_SECONDS} poll_interval_s={config.POLL_INTERVAL_SECONDS}")
    print(f"server_time_resync_s={config.SERVER_TIME_RESYNC_SECONDS} alive_interval_s={config.ALIVE_INTERVAL_SECONDS}")
    print(f"use_heikin_ashi={config.USE_HEIKIN_ASHI} bias_threshold={config.BIAS_THRESHOLD}")
    print(
        f"http_connect_timeout_s={config.HTTP_CONNECT_TIMEOUT_SECONDS} http_read_timeout_s={config.HTTP_READ_TIMEOUT_SECONDS} "
        f"retry_period_s={config.HTTP_RETRY_PERIOD_SECONDS} max_retries={config.HTTP_MAX_RETRIES}"
    )
    print(f"telegram_enabled={config.TELEGRAM_ENABLED} chat_ids={config.CHAT_IDS} admin_chat_id={config.ADMIN_CHAT_ID}")


def _build_startup_message(*, engine: DataEngine, df: pd.DataFrame) -> str:
    last = df.index.max()
    close = float(df.loc[last, "close"])
    return (
        f"[startup] {config.SYMBOL} {engine.timeframe.kline_type}\n"
        f"server_offset_ms={engine.server_offset_ms}\n"
        f"last_candle_ts={last} close={close:.4f}\n"
        f"warmup_loaded={len(df)}"
    )


def _build_alive_message(*, engine: DataEngine, df: pd.DataFrame) -> str:
    last = df.index.max()
    close = float(df.loc[last, "close"])
    bias = float(df.loc[last, "bias"]) if "bias" in df.columns else float("nan")
    conf = float(df.loc[last, "confidence"]) if "confidence" in df.columns else float("nan")
    tv = int(df.loc[last, "total_votes"]) if "total_votes" in df.columns else 0
    return (
        f"[alive] {config.SYMBOL} {engine.timeframe.kline_type}\n"
        f"server_now={engine.server_now_utc()} offset_ms={engine.server_offset_ms}\n"
        f"last_ts={last} close={close:.4f}\n"
        f"bias={bias:.5f} votes={tv}/21 conf={conf:.3f}\n"
        f"candles_in_mem={len(df)} last_processed={engine.last_processed_ts}"
    )


def _print_warmup_signals(timeframe_key: str, df: pd.DataFrame) -> None:
    sig_df = df[(df["buy_signal"] | df["sell_signal"])].copy()
    if not sig_df.empty:
        last10 = sig_df.tail(10)
        print(f"=== last signals (max 10) from warmup [{timeframe_key}] ===")
        for ts, row in last10.iterrows():
            side = "BUY" if bool(row["buy_signal"]) else "SELL"
            print(
                f"sig timeframe={timeframe_key} ts={ts} side={side} close={float(row['close']):.4f} "
                f"bias={float(row['bias']):.5f} votes={int(row['total_votes'])}/21 conf={float(row['confidence']):.3f}"
            )
    else:
        print(f"=== last signals (max 10) from warmup [{timeframe_key}] === none ===")


def main() -> int:
    _print_startup_summary()

    timeframe = config.TIMEFRAME
    engine = DataEngine(KuCoinREST(), timeframe)
    notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, list(config.CHAT_IDS))
    admin_notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, [config.ADMIN_CHAT_ID])

    try:
        engine.sync_server_time()
    except Exception:
        print("[fatal] server time sync failed")
        traceback.print_exc()
        return 1

    try:
        engine.warmup()
    except Exception:
        print(f"[fatal] warmup failed timeframe={timeframe.key}")
        traceback.print_exc()
        return 1

    now = engine.server_now_utc()
    candidate = now - pd.Timedelta(seconds=config.SAFE_CLOSE_DELAY_SECONDS)
    boundary = candidate.floor(f"{timeframe.timeframe_seconds}s")
    last_closed = boundary - pd.Timedelta(seconds=timeframe.timeframe_seconds)
    print(
        f"[timing] timeframe={timeframe.key} server_now={now} candidate={candidate} "
        f"boundary={boundary} last_closed_start={last_closed}"
    )

    df = compute_bias_and_votes(engine.df)
    df = compute_signals(df)
    _print_warmup_signals(timeframe.key, df)

    if config.TELEGRAM_ENABLED:
        admin_notifier.send(_build_startup_message(engine=engine, df=df), startup=True)

    next_alive = engine.server_now_utc() + pd.Timedelta(seconds=config.ALIVE_INTERVAL_SECONDS)

    print("[main] entering polling loop (UTC)")
    while True:
        try:
            engine.maybe_resync_time()

            if engine.server_now_utc() >= next_alive:
                msg = _build_alive_message(engine=engine, df=df)
                print(msg.replace("\n", " | "))
                admin_notifier.send(msg)
                next_alive = engine.server_now_utc() + pd.Timedelta(seconds=config.ALIVE_INTERVAL_SECONDS)

            fr = engine.fetch_and_update()
            if fr.new_candle_ts:
                df = compute_bias_and_votes(fr.df)
                df = compute_signals(df)

                for ts in sorted(fr.new_candle_ts):
                    if ts not in df.index:
                        continue
                    row = df.loc[ts]
                    close = float(row["close"])
                    bias = float(row["bias"])
                    tv = int(row["total_votes"])
                    conf = float(row["confidence"])
                    buy = bool(row["buy_signal"])
                    sell = bool(row["sell_signal"])

                    print(
                        f"[candle] timeframe={timeframe.key} ts={ts} close={close:.4f} bias={bias:.5f} "
                        f"votes={tv}/21 conf={conf:.3f} buy={buy} sell={sell}"
                    )

                    if buy or sell:
                        side = "BUY" if buy else "SELL"
                        msg = build_signal_message(
                            symbol=config.SYMBOL,
                            kline_type=timeframe.kline_type,
                            side=side,
                            ts=ts,
                            close=close,
                            bias=bias,
                            bias_threshold=float(config.BIAS_THRESHOLD),
                            total_votes=tv,
                            confidence=conf,
                        )
                        print(f"[signal] timeframe={timeframe.key} {side} ts={ts} close={close:.4f} bias={bias:.5f}")
                        notifier.send(msg)

                    engine.mark_processed(ts)

            time.sleep(config.POLL_INTERVAL_SECONDS)

        except Exception:
            print("[loop] unhandled exception")
            traceback.print_exc()
            time.sleep(config.HTTP_RETRY_PERIOD_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
