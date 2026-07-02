"""성과 지표 계산: 승률, 총수익률, MDD, 샤프, 손익비 등."""
import numpy as np
import pandas as pd

from .engine import BacktestResult


def bars_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 365.0
    dt = (index[1:] - index[:-1]).median()
    return pd.Timedelta(days=365) / dt


def compute_metrics(result: BacktestResult) -> dict:
    eq = result.equity
    trades = result.trades
    rets = eq.pct_change().dropna()

    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    n = len(trades)

    gross_profit = sum(t.pnl_pct for t in wins)
    gross_loss = abs(sum(t.pnl_pct for t in losses))

    total_return = eq.iloc[-1] - 1.0
    years = len(eq) / bars_per_year(eq.index)
    cagr = (eq.iloc[-1]) ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else 0.0

    peak = eq.cummax()
    mdd = ((eq - peak) / peak).min()

    bpy = bars_per_year(eq.index)
    sharpe = (rets.mean() / rets.std() * np.sqrt(bpy)) if rets.std() > 0 else 0.0

    return {
        "trades": n,
        "win_rate": len(wins) / n if n else 0.0,
        "total_return": total_return,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "avg_win": np.mean([t.pnl_pct for t in wins]) if wins else 0.0,
        "avg_loss": np.mean([t.pnl_pct for t in losses]) if losses else 0.0,
        "expectancy": np.mean([t.pnl_pct for t in trades]) if trades else 0.0,  # 1회 거래당 기대수익
    }


def format_metrics(m: dict) -> str:
    return (f"거래 {m['trades']:>4d}회 | 승률 {m['win_rate']*100:5.1f}% | "
            f"수익률 {m['total_return']*100:+7.1f}% | CAGR {m['cagr']*100:+6.1f}% | "
            f"MDD {m['mdd']*100:6.1f}% | Sharpe {m['sharpe']:5.2f} | "
            f"PF {m['profit_factor']:.2f} | 기대값 {m['expectancy']*100:+.2f}%/회")
