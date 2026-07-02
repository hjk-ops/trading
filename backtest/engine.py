"""백테스팅 엔진.

핵심 원칙 (과최적화/미래참조 방지):
- 시그널은 봉 마감 후 계산 → 체결은 '다음 봉 시가' (look-ahead bias 방지)
- 수수료 + 슬리피지 반영 (기본값: 업비트 0.05% 수수료, 0.05% 슬리피지)
- 포지션: 0 (현금) 또는 1 (풀 매수). 공매도 미지원 (현물 기준)
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    pnl_pct: float  # 수수료/슬리피지 차감 후 수익률


@dataclass
class BacktestResult:
    equity: pd.Series          # 누적 자산 곡선 (1.0 시작)
    trades: list = field(default_factory=list)
    params: dict = field(default_factory=dict)
    strategy_name: str = ""


def run_backtest(
    df: pd.DataFrame,
    position: pd.Series,
    fee: float = 0.0005,
    slippage: float = 0.0005,
    take_profit: float | None = None,
    stop_loss: float | None = None,
) -> BacktestResult:
    """position: 각 봉 마감 시점의 목표 포지션 (0 또는 1).

    포지션 변경은 다음 봉 시가에 체결된다.
    take_profit/stop_loss: 진입가 대비 비율 (예: 0.015 = +1.5% 익절, 0.03 = -3% 손절).
    봉 내에서 TP와 SL이 동시에 닿을 수 있으면 '보수적으로 SL 먼저' 체결로 가정한다.
    df는 open/high/low/close 컬럼과 DatetimeIndex 필요.
    """
    pos = position.reindex(df.index).fillna(0).astype(float).clip(0, 1)
    open_px = df["open"].values
    close_px = df["close"].values
    n = len(df)

    cost = fee + slippage
    equity = np.ones(n)
    cash_eq = 1.0          # 현재 자산 (배수)
    holding = False
    entry_px = 0.0
    entry_i = 0
    trades: list[Trade] = []

    high_px = df["high"].values
    low_px = df["low"].values

    # pos[i]는 i번 봉 마감 시점의 목표. 실제 진입/청산은 i+1번 봉 시가.
    for i in range(n):
        target = pos.iloc[i - 1] if i > 0 else 0.0  # 전 봉 마감 시그널
        px_open = open_px[i]

        # --- 봉 내 SL/TP 체크 (보유 중일 때, SL 우선 = 보수적) ---
        if holding and (take_profit or stop_loss):
            sl_px = entry_px * (1 - stop_loss) if stop_loss else None
            tp_px = entry_px * (1 + take_profit) if take_profit else None
            exit_px = None
            if sl_px and low_px[i] <= sl_px:
                # 갭하락으로 시가가 이미 SL 아래면 시가 체결
                exit_px = min(sl_px, px_open) * (1 - cost)
            elif tp_px and high_px[i] >= tp_px:
                exit_px = max(tp_px, px_open) * (1 - cost) if px_open > tp_px else tp_px * (1 - cost)
            if exit_px is not None:
                r = exit_px / entry_px
                cash_eq *= r
                trades.append(Trade(df.index[entry_i], df.index[i],
                                    entry_px, exit_px, r - 1))
                holding = False
                equity[i] = cash_eq
                continue

        if not holding and target >= 0.5:
            entry_px = px_open * (1 + cost)  # 매수: 불리하게 체결
            entry_i = i
            holding = True
        elif holding and target < 0.5:
            exit_px = px_open * (1 - cost)   # 매도: 불리하게 체결
            r = exit_px / entry_px
            cash_eq *= r
            trades.append(Trade(df.index[entry_i], df.index[i],
                                entry_px, exit_px, r - 1))
            holding = False

        # 봉 마감 기준 평가 자산
        if holding:
            equity[i] = cash_eq * (close_px[i] * (1 - cost)) / entry_px
        else:
            equity[i] = cash_eq

    # 마지막까지 보유 중이면 종가 청산 처리
    if holding:
        exit_px = close_px[-1] * (1 - cost)
        r = exit_px / entry_px
        cash_eq *= r
        trades.append(Trade(df.index[entry_i], df.index[-1],
                            entry_px, exit_px, r - 1))
        equity[-1] = cash_eq

    return BacktestResult(equity=pd.Series(equity, index=df.index), trades=trades)
