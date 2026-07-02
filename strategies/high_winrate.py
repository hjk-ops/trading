"""고승률 전략 모음.

설계 원리: "과매도 급락 후 단기 반등" 확률이 높다는 통계적 경향 + 짧은 익절.
익절폭 < 손절폭이므로 승률은 높지만 한 번의 손실이 크다.
→ 승률만 보지 말고 반드시 기대값(expectancy)과 PF를 함께 볼 것.

전략이 tp/sl을 쓰려면 exit_rules()로 반환한다 (엔진이 봉 내 체결 처리).
"""
import numpy as np
import pandas as pd

from .catalog import Strategy


class Rsi2Scalp(Strategy):
    """RSI(2) 극단 과매도 매수 → 짧은 익절. (래리 코너스 스타일, 대표적 고승률 구조)"""
    name = "RSI2 스캘핑"
    param_grid = {"buy_th": [5, 10, 15], "tp": [0.01, 0.02, 0.03], "sl": [0.05, 0.08],
                  "max_hold": [3, 5]}

    def exit_rules(self, buy_th=10, tp=0.02, sl=0.05, max_hold=5):
        return {"take_profit": tp, "stop_loss": sl}

    def generate_signals(self, df, buy_th=10, tp=0.02, sl=0.05, max_hold=5):
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        entry = rsi < buy_th
        # 진입 후 max_hold봉 보유 (TP/SL이 먼저 닿으면 엔진이 청산)
        pos = entry.astype(int)
        for k in range(1, max_hold):
            pos = pos | entry.shift(k).fillna(False).astype(int)
        return pos.astype(int)


class DipBuyer(Strategy):
    """N봉 연속 하락 + 급락폭 조건 매수 → 짧은 익절."""
    name = "급락 반등 매수"
    param_grid = {"down_bars": [2, 3], "drop_pct": [0.03, 0.05, 0.08],
                  "tp": [0.015, 0.025], "sl": [0.06, 0.10], "max_hold": [3, 5]}

    def exit_rules(self, down_bars=3, drop_pct=0.05, tp=0.02, sl=0.08, max_hold=5):
        return {"take_profit": tp, "stop_loss": sl}

    def generate_signals(self, df, down_bars=3, drop_pct=0.05, tp=0.02, sl=0.08, max_hold=5):
        down = (df["close"] < df["close"].shift(1))
        consec = down.rolling(down_bars).sum() >= down_bars
        drop = df["close"] / df["close"].shift(down_bars) - 1 <= -drop_pct
        entry = consec & drop
        pos = entry.astype(int)
        for k in range(1, max_hold):
            pos = pos | entry.shift(k).fillna(False).astype(int)
        return pos.astype(int)


class BollingerSnapback(Strategy):
    """밴드 하단 강이탈 매수 → 짧은 고정 익절 (기존 볼린저보다 승률 지향)."""
    name = "볼린저 스냅백"
    param_grid = {"period": [20], "k": [2.0, 2.5, 3.0],
                  "tp": [0.01, 0.02], "sl": [0.05, 0.08], "max_hold": [3, 5]}

    def exit_rules(self, period=20, k=2.5, tp=0.015, sl=0.06, max_hold=5):
        return {"take_profit": tp, "stop_loss": sl}

    def generate_signals(self, df, period=20, k=2.5, tp=0.015, sl=0.06, max_hold=5):
        ma = df["close"].rolling(period).mean()
        sd = df["close"].rolling(period).std()
        entry = df["close"] < (ma - k * sd)
        pos = entry.astype(int)
        for h in range(1, max_hold):
            pos = pos | entry.shift(h).fillna(False).astype(int)
        return pos.astype(int)


HIGH_WINRATE_STRATEGIES = [Rsi2Scalp(), DipBuyer(), BollingerSnapback()]
