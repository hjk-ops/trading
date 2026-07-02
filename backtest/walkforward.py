"""Walk-forward 검증.

전체 기간 최적화는 과최적화(overfitting)를 낳는다.
대신: 학습 구간에서 파라미터를 고르고, 바로 뒤 검증 구간(미접촉 데이터)에서만
성과를 측정한다. 이를 창을 밀며 반복 → out-of-sample 성과만 합산.

여기서 나온 승률/수익률이 '실전에 가까운' 추정치다.
전체 구간 최적화 결과와 walk-forward 결과의 차이가 크면 그 전략은 버려라.
"""
import itertools
import numpy as np
import pandas as pd

from .engine import run_backtest
from .metrics import compute_metrics


def _grid(param_grid: dict):
    keys = list(param_grid)
    for combo in itertools.product(*[param_grid[k] for k in keys]):
        yield dict(zip(keys, combo))


def optimize(strategy, df: pd.DataFrame, fee=0.0005, slippage=0.0005,
             objective: str = "sharpe") -> tuple[dict, dict]:
    """그리드 서치로 학습 구간 최적 파라미터 탐색."""
    best_params, best_score, best_metrics = None, -np.inf, None
    for params in _grid(strategy.param_grid):
        pos = strategy.generate_signals(df, **params)
        exits = strategy.exit_rules(**params) if hasattr(strategy, "exit_rules") else {}
        res = run_backtest(df, pos, fee=fee, slippage=slippage, **exits)
        m = compute_metrics(res)
        if m["trades"] < 5:  # 표본 너무 적으면 신뢰 불가
            continue
        score = m[objective]
        if score > best_score:
            best_params, best_score, best_metrics = params, score, m
    return best_params or {}, best_metrics or {}


def walk_forward(strategy, df: pd.DataFrame, n_splits: int = 5,
                 train_ratio: float = 0.7, fee=0.0005, slippage=0.0005,
                 objective: str = "sharpe"):
    """데이터를 n_splits 창으로 나눠 train→test 반복.

    Returns: (oos_equity, fold_results)
      oos_equity: out-of-sample 구간만 이어붙인 자산 곡선
      fold_results: 각 창의 (params, test_metrics)
    """
    n = len(df)
    window = n // n_splits
    train_len = int(window * train_ratio)

    oos_parts, fold_results = [], []
    all_trades = []

    for k in range(n_splits):
        start = k * window
        end = min(start + window, n)
        train = df.iloc[start:start + train_len]
        test = df.iloc[start + train_len:end]
        if len(test) < 30:
            continue

        params, _ = optimize(strategy, train, fee, slippage, objective)
        if not params:
            continue

        pos = strategy.generate_signals(test, **params)
        exits = strategy.exit_rules(**params) if hasattr(strategy, "exit_rules") else {}
        res = run_backtest(test, pos, fee=fee, slippage=slippage, **exits)
        m = compute_metrics(res)
        fold_results.append({"fold": k + 1, "params": params, **m})
        all_trades.extend(res.trades)

        # 자산곡선 이어붙이기 (배수 연결)
        base = oos_parts[-1].iloc[-1] if oos_parts else 1.0
        oos_parts.append(res.equity * base)

    if not oos_parts:
        return pd.Series(dtype=float), []

    oos_equity = pd.concat(oos_parts)
    # 합산 지표 재계산
    wins = [t for t in all_trades if t.pnl_pct > 0]
    summary = {
        "trades": len(all_trades),
        "win_rate": len(wins) / len(all_trades) if all_trades else 0.0,
        "total_return": oos_equity.iloc[-1] - 1.0,
    }
    return oos_equity, fold_results, summary
