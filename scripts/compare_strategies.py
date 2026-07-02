"""모든 전략을 백테스트 + walk-forward로 비교.

사용법:
  python -m scripts.compare_strategies --csv data/upbit_KRWBTC_day.csv

출력:
  [In-Sample]  전체 구간 최적화 성과 → 과최적화된 '최상의 경우' (믿지 말 것)
  [Walk-Fwd]   미접촉 데이터 성과   → 실전에 가까운 추정치 (이걸 믿어라)
"""
import argparse
import pandas as pd

from backtest.engine import run_backtest
from backtest.metrics import compute_metrics, format_metrics
from backtest.walkforward import optimize, walk_forward
from strategies.catalog import ALL_STRATEGIES
from strategies.high_winrate import HIGH_WINRATE_STRATEGIES


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
    return df[["open", "high", "low", "close", "volume"]].dropna()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--fee", type=float, default=0.0005)
    p.add_argument("--slippage", type=float, default=0.0005)
    p.add_argument("--splits", type=int, default=5)
    p.add_argument("--objective", default="sharpe", choices=["sharpe", "win_rate", "total_return"],
                   help="파라미터 최적화 목적함수 (승률 최대화: win_rate)")
    args = p.parse_args()

    df = load_csv(args.csv)
    print(f"데이터: {len(df)}봉, {df.index[0].date()} ~ {df.index[-1].date()}")

    # Buy & Hold 기준선
    bh = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    print(f"단순 보유(Buy&Hold) 수익률: {bh*100:+.1f}%  ← 전략이 이걸 못 이기면 의미 없음\n")

    rows = []
    for strat in ALL_STRATEGIES + HIGH_WINRATE_STRATEGIES:
        print(f"=== {strat.name} ===")
        # 1) 전체 구간 최적화 (참고용)
        best_params, m_is = optimize(strat, df, args.fee, args.slippage, objective=args.objective)
        if m_is:
            print(f"  [In-Sample] params={best_params}")
            print(f"              {format_metrics(m_is)}")
        else:
            print("  [In-Sample] 유효한 결과 없음 (거래 부족)")
            continue

        # 2) Walk-forward (실전 추정)
        wf = walk_forward(strat, df, n_splits=args.splits,
                          fee=args.fee, slippage=args.slippage,
                          objective=args.objective)
        if len(wf) == 3 and wf[2]["trades"] > 0:
            oos_eq, folds, summary = wf
            print(f"  [Walk-Fwd]  거래 {summary['trades']}회 | "
                  f"승률 {summary['win_rate']*100:.1f}% | "
                  f"수익률 {summary['total_return']*100:+.1f}%")
            rows.append({"전략": strat.name,
                         "IS승률": m_is["win_rate"],
                         "WF승률": summary["win_rate"],
                         "WF수익률": summary["total_return"],
                         "WF거래수": summary["trades"]})
        else:
            print("  [Walk-Fwd]  거래 없음")
        print()

    if rows:
        table = pd.DataFrame(rows).sort_values("WF수익률", ascending=False)
        print("=" * 70)
        print("종합 순위 (Walk-Forward 수익률 기준):")
        for _, r in table.iterrows():
            gap = (r["IS승률"] - r["WF승률"]) * 100
            flag = " ⚠️과최적화 의심" if gap > 15 else ""
            print(f"  {r['전략']:<12s} WF승률 {r['WF승률']*100:5.1f}% "
                  f"(IS {r['IS승률']*100:5.1f}%) | "
                  f"WF수익 {r['WF수익률']*100:+7.1f}% | {int(r['WF거래수'])}회{flag}")


if __name__ == "__main__":
    main()
