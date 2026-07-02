"""시세 데이터 정제: 이상 틱(플래시크래시, 오기록) 제거.

실사례: Coinbase 2017-04-15 분봉에 시가 $0.06 오기록 → 백테스트 수익률 +2,000,000% 왜곡.
규칙: 직전 종가 대비 ±threshold(기본 30%) 초과 변동 가격은 직전 종가로 대체.
"""
import pandas as pd


def clean_ohlcv(df: pd.DataFrame, threshold: float = 0.3) -> pd.DataFrame:
    df = df.copy()
    prev_close = df["close"].shift(1)
    fixed = 0
    for col in ["open", "high", "low", "close"]:
        bad = (df[col] / prev_close - 1).abs() > threshold
        bad &= prev_close.notna()
        fixed += bad.sum()
        df.loc[bad, col] = prev_close[bad]
    # OHLC 정합성 복원
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    if fixed:
        print(f"[clean] 이상 틱 {fixed}개 보정 (임계 ±{threshold*100:.0f}%)")
    return df
