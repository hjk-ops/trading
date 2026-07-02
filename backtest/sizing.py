"""수익 극대화 모듈: 변동성 타겟팅 + 레짐 필터.

원리:
1) 변동성 타겟팅 — 포지션 크기를 '목표 변동성 / 실현 변동성'으로 조절.
   시장이 거칠 때 자동 축소, 안정적일 때 확대 → MDD 감소 → 복리 보존.
   weight = min(1, target_vol / realized_vol)
2) 레짐 필터 — 가격이 장기 이평선 아래면 신규 진입 차단 (하락장 회피).

부분 포지션(0.0~1.0)을 지원하는 벡터화 백테스트 포함.
비용 = (수수료+슬리피지) × |비중 변화량| 으로 리밸런싱 비용까지 반영.
"""
import numpy as np
import pandas as pd


def realized_vol(df: pd.DataFrame, window: int = 30) -> pd.Series:
    """연환산 실현 변동성 (봉 주기 자동 감지)."""
    ret = df["close"].pct_change()
    dt = (df.index[1:] - df.index[:-1]).median()
    bars_per_year = pd.Timedelta(days=365) / dt
    return ret.rolling(window).std() * np.sqrt(bars_per_year)


def vol_target_weight(df: pd.DataFrame, target_vol: float = 0.4,
                      window: int = 30, max_weight: float = 1.0) -> pd.Series:
    """변동성 타겟 비중. target_vol=0.4 → 연 40% 변동성 목표."""
    rv = realized_vol(df, window)
    w = (target_vol / rv).clip(upper=max_weight)
    return w.fillna(0)


def regime_filter(df: pd.DataFrame, ma_period: int = 120) -> pd.Series:
    """장기 이평선 위에 있을 때만 1 (진입 허용)."""
    return (df["close"] > df["close"].rolling(ma_period).mean()).astype(int)


def run_backtest_sized(df: pd.DataFrame, weight: pd.Series,
                       fee: float = 0.0005, slippage: float = 0.0005) -> pd.Series:
    """부분 포지션 백테스트 (벡터화). weight: 0.0~1.0 목표 비중.

    체결: 다음 봉부터 반영 (shift). 비용: 비중 변화량에 비례.
    반환: 자산 곡선 (1.0 시작).
    """
    w = weight.reindex(df.index).fillna(0).clip(0, 1)
    ret = df["close"].pct_change().fillna(0)
    cost = fee + slippage
    w_prev = w.shift(1).fillna(0)
    strat_ret = w_prev * ret - cost * (w - w_prev).abs()
    return (1 + strat_ret).cumprod()


def equity_metrics(equity: pd.Series) -> dict:
    ret = equity.pct_change().dropna()
    dt = (equity.index[1:] - equity.index[:-1]).median()
    bpy = pd.Timedelta(days=365) / dt
    years = len(equity) / bpy
    peak = equity.cummax()
    return {
        "total_return": equity.iloc[-1] - 1,
        "cagr": equity.iloc[-1] ** (1 / years) - 1 if years > 0 else 0,
        "mdd": ((equity - peak) / peak).min(),
        "sharpe": ret.mean() / ret.std() * np.sqrt(bpy) if ret.std() > 0 else 0,
    }


def maximize(df: pd.DataFrame, base_signal: pd.Series,
             target_vol: float = 0.4, regime_ma: int = 120,
             fee: float = 0.0005, slippage: float = 0.0005):
    """전략 시그널에 변동성 타겟팅 + 레짐 필터를 결합.

    최종 비중 = 시그널(0/1) × 레짐 필터(0/1) × 변동성 타겟 비중(0~1)
    """
    sig = base_signal.reindex(df.index).fillna(0).clip(0, 1)
    reg = regime_filter(df, regime_ma) if regime_ma else 1
    vw = vol_target_weight(df, target_vol)
    weight = sig * reg * vw
    equity = run_backtest_sized(df, weight, fee, slippage)
    return weight, equity
