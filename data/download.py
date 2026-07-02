"""과거 시세(OHLCV) 다운로드 → data/*.csv 저장.

사용법:
  python -m data.download --exchange upbit  --symbol KRW-BTC --interval day --count 1500
  python -m data.download --exchange binance --symbol BTC/USDT --interval 1d --count 1500

의존성: pyupbit(업비트) 또는 ccxt(바이낸스)
"""
import argparse
import time
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent


def download_upbit(symbol: str, interval: str, count: int) -> pd.DataFrame:
    import pyupbit
    unit_map = {"day": "day", "minute60": "minute60", "minute240": "minute240"}
    df = pyupbit.get_ohlcv(symbol, interval=unit_map.get(interval, interval), count=count)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index.name = "timestamp"
    return df


def download_binance(symbol: str, interval: str, count: int) -> pd.DataFrame:
    import ccxt
    ex = ccxt.binance()
    all_rows, since = [], None
    while len(all_rows) < count:
        rows = ex.fetch_ohlcv(symbol, timeframe=interval, since=since, limit=1000)
        if not rows:
            break
        all_rows = rows + all_rows if since is None else all_rows + rows
        since = rows[-1][0] + 1
        if len(rows) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    df = pd.DataFrame(all_rows[-count:], columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.set_index("timestamp")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", choices=["upbit", "binance"], required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="day")
    p.add_argument("--count", type=int, default=1500)
    args = p.parse_args()

    fn = download_upbit if args.exchange == "upbit" else download_binance
    df = fn(args.symbol, args.interval, args.count)

    out = DATA_DIR / f"{args.exchange}_{args.symbol.replace('/', '').replace('-', '')}_{args.interval}.csv"
    df.to_csv(out)
    print(f"저장 완료: {out} ({len(df)}행, {df.index[0]} ~ {df.index[-1]})")


if __name__ == "__main__":
    main()
