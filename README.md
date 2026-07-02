# Crypto Auto-Trading Framework

암호화폐(업비트/바이낸스) 자동매매 프레임워크. 백테스팅 → walk-forward 검증 → 모의매매 → 실계좌 순서로 단계적 검증을 강제하는 구조입니다.

## ⚠️ 먼저 읽을 것

**백테스트 승률은 실전 수익을 보장하지 않습니다.** 이 프레임워크는 그 착각을 방지하기 위해 두 가지 숫자를 항상 함께 보여줍니다.

- **In-Sample (IS)**: 전체 기간에 파라미터를 최적화한 결과. 과최적화된 "최상의 경우"이며 **믿으면 안 됩니다.**
- **Walk-Forward (WF)**: 학습 구간에서 파라미터를 고르고, 모델이 본 적 없는 검증 구간에서만 측정한 결과. **이 숫자만 믿으세요.** IS와 WF의 승률 차이가 15%p 이상이면 과최적화 경고가 표시됩니다.

실제 검증 예시 (합성 데이터): 볼린저 전략이 IS 승률 70.7%를 기록했지만 WF에서는 -16% 손실. 프레임워크가 정상적으로 과최적화를 잡아낸 것입니다.

투자 손실은 전적으로 본인 책임입니다. 반드시 잃어도 되는 소액으로만 시작하세요.

## 구조

```
├── backtest/
│   ├── engine.py        # 백테스팅 엔진 (다음 봉 시가 체결, 수수료/슬리피지 반영)
│   ├── metrics.py       # 승률, MDD, Sharpe, Profit Factor 등
│   └── walkforward.py   # Walk-forward 검증 (과최적화 방지 핵심)
├── strategies/
│   └── catalog.py       # 전략 5종 (SMA크로스, RSI회귀, 볼린저, 돈치안, 변동성돌파)
├── live/
│   └── trader.py        # 실시간 매매 루프 (paper/upbit/binance + 손절 + kill switch)
├── data/
│   └── download.py      # 과거 시세 다운로드
├── scripts/
│   └── compare_strategies.py  # 전략 일괄 비교
└── tests/
    └── test_engine.py   # 엔진 정합성 테스트 (미래참조 방지 검증)
```

## 설치

```bash
pip install -r requirements.txt
python -m tests.test_engine   # 엔진 검증
```

## 사용 순서

### 1단계: 데이터 다운로드

```bash
# 업비트 BTC 일봉 1500개
python -m data.download --exchange upbit --symbol KRW-BTC --interval day --count 1500

# 바이낸스
python -m data.download --exchange binance --symbol BTC/USDT --interval 1d --count 1500
```

### 2단계: 전략 비교 (백테스트 + Walk-Forward)

```bash
python -m scripts.compare_strategies --csv data/upbit_KRWBTC_day.csv
```

WF 수익률이 Buy&Hold를 이기고, IS/WF 승률 격차가 작고, WF 거래 수가 30회 이상인 전략만 다음 단계로 진행하세요. 여러 코인(BTC, ETH 등)에서 반복 검증하면 신뢰도가 올라갑니다.

### 3단계: 모의매매 (최소 2~4주)

```bash
python -m live.trader --exchange upbit --symbol KRW-BTC \
    --strategy donchian --params '{"entry_n":40,"exit_n":20}' --paper
```

가상 자금으로 실시간 시세에 따라 매매하며 `live_trading.log`에 기록됩니다.

### 4단계: 실계좌 (소액부터)

```bash
export UPBIT_ACCESS=발급받은키
export UPBIT_SECRET=발급받은키
python -m live.trader --exchange upbit --symbol KRW-BTC \
    --strategy donchian --params '{"entry_n":40,"exit_n":20}' \
    --live --max-krw 100000 --stop-loss -0.05
```

안전장치:
- `--max-krw`: 1회 주문 최대 금액
- `--stop-loss`: 진입가 대비 자동 손절 (기본 -5%)
- **Kill switch**: 실행 폴더에 `touch STOP` → 전량 청산 후 즉시 종료
- API 키는 반드시 환경변수로만. **코드/git에 절대 커밋 금지** (`.gitignore` 확인)

## 이 repo에 푸시하기

```bash
git clone https://github.com/hjk-ops/trading.git
# 이 프로젝트 파일들을 clone한 폴더에 복사 후
cd trading
git add -A
git commit -m "feat: crypto auto-trading framework (backtest + walk-forward + live)"
git push origin main
```

## 확장 아이디어

- 포트폴리오(다중 코인) 분산 및 변동성 기반 포지션 사이징
- 텔레그램 알림 연동
- 분봉 전략 (interval 파라미터는 이미 지원)
- Monte Carlo 시뮬레이션으로 MDD 신뢰구간 추정

## 고승률 전략 (strategies/high_winrate.py)

승률을 구조적으로 높인 전략 3종 (급락 반등 매수 + 짧은 익절 + 넓은 손절):
RSI2 스캘핑, 급락 반등 매수, 볼린저 스냅백. 봉 내 TP/SL 체결을 엔진이 지원합니다.

```bash
# 승률 최대화 목적으로 전체 비교
python -m scripts.compare_strategies --csv data/upbit_KRWBTC_day.csv --objective win_rate
```

**경고 — 합성 데이터 실증 결과:** RSI2 스캘핑이 In-Sample 승률 74.3%를 기록했지만
walk-forward 수익률은 **-47.1%**였습니다. 익절이 짧고 손절이 넓으면 승률은 올라가지만
한 번의 손실이 잔 수익 여러 번을 지웁니다. 전략 채택 기준은 승률이 아니라
**기대값(expectancy) > 0, PF > 1.3, WF 수익률 > Buy&Hold, 거래 30회 이상**이어야 합니다.

## 데이터 정제 (data/clean.py)

거래소 원시 데이터에는 이상 틱이 섞여 있습니다. 실제 사례: Coinbase 2017-04-15 분봉에
시가 $0.06 오기록 → 정제 전 백테스트가 +2,000,000% 수익률로 왜곡됐고, 정제 후 +13.6%로
정상화됐습니다. `clean_ohlcv(df)`를 백테스트 전에 반드시 적용하세요.
검증용 실데이터 포함: `data/coinbase_BTCUSD_day.csv`, `data/coinbase_BTCUSD_4h.csv`
(Coinbase BTC-USD, 2014-12 ~ 2018-01, 이상 틱 458개 보정 완료)

## 웹 대시보드 (live/dashboard.py)

매매 봇과 함께 띄우는 실시간 모니터링 화면. 추가 설치 불필요 (표준 라이브러리만 사용).

```bash
# 터미널 1: 봇        python -m live.trader --exchange upbit --symbol KRW-BTC --strategy donchian --paper
# 터미널 2: 대시보드   python -m live.dashboard
# 브라우저:           http://localhost:8800
```

총자산, 현금, 보유수량, 누적 실현수익, 승률, 자산 곡선 차트, 거래 내역 테이블을 10초 간격으로 자동 갱신합니다.

## 수익 극대화 모듈 (backtest/sizing.py)

조사 결과 개인 자동매매에서 가장 현실적인 수익 극대화 방법은 레버리지나 켈리 공식이 아니라
**변동성 타겟팅 + 레짐 필터**입니다 (-50% 손실은 +100%를 벌어야 복구 → MDD를 줄여야 복리가 산다).

- **변동성 타겟팅**: 포지션 비중 = 목표변동성 / 실현변동성. 시장이 거칠면 자동 축소
- **레짐 필터**: 가격이 장기 이평(예: MA200) 아래면 신규 진입 차단 (하락장 회피)

실데이터 검증 (BTC 4h, 학습/검증 분리, 검증 구간 2016-05~2018-01):

| | 수익률 | MDD | Sharpe |
|---|---|---|---|
| 돈치안 원본 | +1043% | -34% | 3.06 |
| 돈치안 + 극대화 | +321% | **-14%** | **4.23** |
| SMA 원본 | +957% | -41% | 2.88 |
| SMA + 극대화 | +917% | **-33%** | **3.53** |

라이브 적용:

```bash
python -m live.trader --exchange upbit --symbol KRW-BTC --strategy sma \
    --paper --target-vol 0.5 --regime-ma 200
```
