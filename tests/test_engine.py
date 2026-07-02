"""엔진 정합성 테스트: 합성 데이터로 미래참조/체결 로직 검증."""
import numpy as np
import pandas as pd
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics

def make_df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p*1.01, "low": p*0.99,
                         "close": p, "volume": 1.0}, index=idx)

def test_next_bar_execution():
    df = make_df([100, 110, 121, 121])
    pos = pd.Series([0, 1, 1, 0], index=df.index)
    res = run_backtest(df, pos, fee=0, slippage=0)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert abs(t.entry_price - 121) < 1e-9  # 시그널 다음 봉(index 2) 시가
    print("OK: next-bar 체결 확인 (미래참조 없음)")

def test_costs_reduce_pnl():
    df = make_df([100]*10 + [110]*10)
    pos = pd.Series([1]*19 + [0], index=df.index)
    r0 = run_backtest(df, pos, fee=0, slippage=0)
    r1 = run_backtest(df, pos, fee=0.001, slippage=0.001)
    assert r1.equity.iloc[-1] < r0.equity.iloc[-1]
    print("OK: 수수료/슬리피지 반영 확인")

def test_metrics():
    df = make_df(list(range(100, 200)))
    pos = pd.Series(1, index=df.index)
    m = compute_metrics(run_backtest(df, pos, fee=0.0005, slippage=0.0005))
    assert m["trades"] == 1 and m["total_return"] > 0.8
    print(f"OK: 지표 계산 확인 (수익률 {m['total_return']*100:.1f}%)")

if __name__ == "__main__":
    test_next_bar_execution(); test_costs_reduce_pnl(); test_metrics()
    print("모든 테스트 통과")
