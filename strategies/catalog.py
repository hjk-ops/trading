"""전략 카탈로그.

모든 전략은 동일 인터페이스:
  generate_signals(df, **params) -> pd.Series (0=현금, 1=매수 목표 포지션)
  param_grid: walk-forward 최적화에 쓸 파라미터 후보

주의: 시그널 계산에 미래 데이터를 절대 쓰지 않는다 (rolling만 사용).
"""
import numpy as np
import pandas as pd


class Strategy:
    name = "base"
    param_grid: dict = {}

    def generate_signals(self, df: pd.DataFrame, **params) -> pd.Series:
        raise NotImplementedError


class SmaCross(Strategy):
    """추세추종: 단기 이평 > 장기 이평이면 보유."""
    name = "SMA 골든크로스"
    param_grid = {"fast": [10, 20, 30], "slow": [50, 100, 200]}

    def generate_signals(self, df, fast=20, slow=100):
        if fast >= slow:
            return pd.Series(0, index=df.index)
        f = df["close"].rolling(fast).mean()
        s = df["close"].rolling(slow).mean()
        return (f > s).astype(int)


class RsiMeanReversion(Strategy):
    """평균회귀: RSI 과매도 매수 → 중립 복귀 시 매도."""
    name = "RSI 평균회귀"
    param_grid = {"period": [7, 14], "buy_th": [25, 30, 35], "sell_th": [50, 55, 60]}

    def generate_signals(self, df, period=14, buy_th=30, sell_th=55):
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        pos = pd.Series(np.nan, index=df.index)
        pos[rsi < buy_th] = 1
        pos[rsi > sell_th] = 0
        return pos.ffill().fillna(0).astype(int)


class BollingerReversion(Strategy):
    """평균회귀: 밴드 하단 이탈 매수 → 중심선 복귀 시 매도."""
    name = "볼린저 평균회귀"
    param_grid = {"period": [20, 30], "k": [1.5, 2.0, 2.5]}

    def generate_signals(self, df, period=20, k=2.0):
        ma = df["close"].rolling(period).mean()
        sd = df["close"].rolling(period).std()
        lower = ma - k * sd
        pos = pd.Series(np.nan, index=df.index)
        pos[df["close"] < lower] = 1
        pos[df["close"] > ma] = 0
        return pos.ffill().fillna(0).astype(int)


class DonchianBreakout(Strategy):
    """추세추종: N일 최고가 돌파 매수, M일 최저가 이탈 매도 (터틀 방식)."""
    name = "돈치안 채널 돌파"
    param_grid = {"entry_n": [20, 40, 55], "exit_n": [10, 20]}

    def generate_signals(self, df, entry_n=20, exit_n=10):
        hi = df["high"].rolling(entry_n).max().shift(1)
        lo = df["low"].rolling(exit_n).min().shift(1)
        pos = pd.Series(np.nan, index=df.index)
        pos[df["close"] > hi] = 1
        pos[df["close"] < lo] = 0
        return pos.ffill().fillna(0).astype(int)


class VolatilityBreakout(Strategy):
    """변동성 돌파 (래리 윌리엄스): 당일 시가 + 전일 레인지*k 돌파 시 매수, 당일 마감 청산.

    일봉 전용. 봉 내 돌파 여부만 판단 (미래참조 없음).
    """
    name = "변동성 돌파"
    param_grid = {"k": [0.3, 0.5, 0.7], "ma_filter": [0, 5, 20]}

    def generate_signals(self, df, k=0.5, ma_filter=0):
        rng = (df["high"] - df["low"]).shift(1)
        target = df["open"] + rng * k
        breakout = df["high"] > target
        if ma_filter > 0:
            trend_ok = df["close"].shift(1) > df["close"].rolling(ma_filter).mean().shift(1)
            breakout = breakout & trend_ok
        # 돌파한 봉만 보유(당일 진입→다음날 시가 청산 근사)
        return breakout.astype(int)


ALL_STRATEGIES = [SmaCross(), RsiMeanReversion(), BollingerReversion(),
                  DonchianBreakout(), VolatilityBreakout()]
