"""롱숏 전략 (선물 전용).

시그널: +1 롱 / 0 현금 / -1 숏. run_backtest_sized로 백테스트.
주의: 숏은 청산 리스크와 펀딩비(미반영)가 있는 선물 거래 기준이다.
"""
import pandas as pd
from .catalog import Strategy


class SmaCrossLS(Strategy):
    """이평 골든크로스 롱 / 데드크로스 숏."""
    name = "SMA 롱숏"
    param_grid = {"fast": [10, 20, 30], "slow": [100, 200]}

    def generate_signals(self, df, fast=20, slow=200):
        f = df["close"].rolling(fast).mean()
        s = df["close"].rolling(slow).mean()
        sig = pd.Series(0, index=df.index)
        sig[f > s] = 1
        sig[f < s] = -1
        return sig


class DonchianLS(Strategy):
    """N봉 최고가 돌파 롱 / 최저가 이탈 숏 (양방향 터틀)."""
    name = "돈치안 롱숏"
    param_grid = {"n": [20, 40, 55]}

    def generate_signals(self, df, n=40):
        hi = df["high"].rolling(n).max().shift(1)
        lo = df["low"].rolling(n).min().shift(1)
        sig = pd.Series(float("nan"), index=df.index)
        sig[df["close"] > hi] = 1
        sig[df["close"] < lo] = -1
        return sig.ffill().fillna(0)


LONG_SHORT_STRATEGIES = [SmaCrossLS(), DonchianLS()]
