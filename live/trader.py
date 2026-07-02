"""실시간 매매 루프.

⚠️ 반드시 --paper (모의매매)로 최소 2~4주 검증 후 실계좌 전환할 것.

사용법:
  # 모의매매 (기본, 안전)
  python -m live.trader --exchange upbit --symbol KRW-BTC --strategy donchian --paper

  # 실계좌 (환경변수에 API 키 필요)
  UPBIT_ACCESS=... UPBIT_SECRET=... python -m live.trader --exchange upbit \
      --symbol KRW-BTC --strategy donchian --live --max-krw 100000

안전장치:
  - --max-krw: 1회 주문 최대 금액 (기본 10만원)
  - --stop-loss: 진입가 대비 손절 비율 (기본 -5%)
  - kill switch: 같은 폴더에 STOP 파일 생성 시 즉시 청산 후 종료 (touch STOP)
"""
import argparse
import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

from strategies.catalog import ALL_STRATEGIES

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler("live_trading.log")])
log = logging.getLogger("trader")

STRATEGY_MAP = {
    "sma": 0, "rsi": 1, "bollinger": 2, "donchian": 3, "volbreak": 4,
}
STATE_FILE = Path("live_state.json")
TRADES_FILE = Path("live_trades.json")


def record_trade(side, price, amount, pnl_pct=None, equity=None):
    trades = json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else []
    trades.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "side": side,
                   "price": price, "amount": amount, "pnl_pct": pnl_pct,
                   "equity": equity})
    TRADES_FILE.write_text(json.dumps(trades, ensure_ascii=False, indent=1))


# ---------------- 브로커 ----------------

class PaperBroker:
    """모의매매: 실제 시세로 가상 체결. 상태는 live_state.json에 저장."""

    def __init__(self, symbol, feed, initial_krw=1_000_000):
        self.symbol, self.feed = symbol, feed
        st = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        self.cash = st.get("cash", initial_krw)
        self.qty = st.get("qty", 0.0)
        self.entry_price = st.get("entry_price", 0.0)

    def _save(self):
        STATE_FILE.write_text(json.dumps(
            {"cash": self.cash, "qty": self.qty, "entry_price": self.entry_price}))

    def position_value(self, price):
        return self.qty * price

    def buy(self, price, krw):
        krw = min(krw, self.cash)
        if krw < 5000:
            return
        self.qty += krw / price * 0.9995  # 수수료 근사
        self.cash -= krw
        self.entry_price = price
        self._save()
        record_trade("BUY", price, krw, equity=self.cash + self.qty * price)
        log.info(f"[PAPER] 매수 {krw:,.0f}원 @ {price:,.0f}")

    def sell_all(self, price):
        if self.qty <= 0:
            return
        proceeds = self.qty * price * 0.9995
        pnl = (price / self.entry_price - 1) * 100 if self.entry_price else 0
        self.cash += proceeds
        log.info(f"[PAPER] 전량 매도 @ {price:,.0f} (수익률 {pnl:+.2f}%) "
                 f"총자산 {self.cash:,.0f}원")
        record_trade("SELL", price, proceeds, pnl_pct=pnl, equity=self.cash)
        self.qty, self.entry_price = 0.0, 0.0
        self._save()


class UpbitBroker:
    def __init__(self, symbol):
        import pyupbit
        access, secret = os.environ["UPBIT_ACCESS"], os.environ["UPBIT_SECRET"]
        self.api = pyupbit.Upbit(access, secret)
        self.symbol = symbol
        self.coin = symbol.split("-")[1]
        self.entry_price = 0.0

    def position_value(self, price):
        bal = self.api.get_balance(self.coin) or 0.0
        return bal * price

    def buy(self, price, krw):
        r = self.api.buy_market_order(self.symbol, krw)
        self.entry_price = price
        log.info(f"[UPBIT] 시장가 매수 {krw:,.0f}원: {r}")

    def sell_all(self, price):
        bal = self.api.get_balance(self.coin) or 0.0
        if bal <= 0:
            return
        r = self.api.sell_market_order(self.symbol, bal)
        log.info(f"[UPBIT] 전량 매도: {r}")


class BinanceBroker:
    def __init__(self, symbol):
        import ccxt
        self.api = ccxt.binance({
            "apiKey": os.environ["BINANCE_KEY"],
            "secret": os.environ["BINANCE_SECRET"],
        })
        self.symbol = symbol
        self.entry_price = 0.0

    def position_value(self, price):
        base = self.symbol.split("/")[0]
        bal = self.api.fetch_balance().get(base, {}).get("free", 0.0)
        return bal * price

    def buy(self, price, quote_amount):
        qty = quote_amount / price
        r = self.api.create_market_buy_order(self.symbol, qty)
        self.entry_price = price
        log.info(f"[BINANCE] 시장가 매수 {qty}: {r['id']}")

    def sell_all(self, price):
        base = self.symbol.split("/")[0]
        bal = self.api.fetch_balance().get(base, {}).get("free", 0.0)
        if bal <= 0:
            return
        r = self.api.create_market_sell_order(self.symbol, bal)
        log.info(f"[BINANCE] 전량 매도: {r['id']}")


# ---------------- 시세 피드 ----------------

def fetch_candles(exchange, symbol, interval, count=250) -> pd.DataFrame:
    if exchange == "upbit":
        import pyupbit
        df = pyupbit.get_ohlcv(symbol, interval=interval, count=count)
        return df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    else:
        import ccxt
        ex = ccxt.binance()
        rows = ex.fetch_ohlcv(symbol, timeframe=interval, limit=count)
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        return df.set_index("ts")


# ---------------- 메인 루프 ----------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", choices=["upbit", "binance"], required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--strategy", choices=list(STRATEGY_MAP), required=True)
    p.add_argument("--params", default="{}", help='JSON, 예: \'{"entry_n":40,"exit_n":20}\'')
    p.add_argument("--interval", default="day")
    p.add_argument("--poll-sec", type=int, default=300)
    p.add_argument("--max-krw", type=float, default=100_000)
    p.add_argument("--target-vol", type=float, default=0.0,
                   help="변동성 타겟 (예: 0.5 = 연 50%%). 0이면 비활성. 주문금액을 자동 축소/유지")
    p.add_argument("--regime-ma", type=int, default=0,
                   help="레짐 필터 이평 기간 (예: 200). 가격이 이평 아래면 신규 진입 차단. 0이면 비활성")
    p.add_argument("--stop-loss", type=float, default=-0.05)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--paper", action="store_true", default=True)
    g.add_argument("--live", dest="paper", action="store_false")
    args = p.parse_args()

    strat = ALL_STRATEGIES[STRATEGY_MAP[args.strategy]]
    params = json.loads(args.params)

    if args.paper:
        broker = PaperBroker(args.symbol, None)
        log.info("=== 모의매매(PAPER) 모드 ===")
    else:
        confirm = input("⚠️ 실계좌 매매입니다. 'YES'를 입력하세요: ")
        if confirm != "YES":
            return
        broker = (UpbitBroker(args.symbol) if args.exchange == "upbit"
                  else BinanceBroker(args.symbol))
        log.info("=== 실계좌(LIVE) 모드 ===")

    log.info(f"전략={strat.name} params={params} 심볼={args.symbol}")

    while True:
        try:
            if Path("STOP").exists():
                log.warning("STOP 파일 감지 → 전량 청산 후 종료")
                df = fetch_candles(args.exchange, args.symbol, args.interval)
                broker.sell_all(df["close"].iloc[-1])
                break

            df = fetch_candles(args.exchange, args.symbol, args.interval)
            price = df["close"].iloc[-1]
            # 마지막 봉은 미완성이므로 제외하고 시그널 계산
            closed = df.iloc[:-1]
            target = int(strat.generate_signals(closed, **params).iloc[-1])

            # 레짐 필터: 장기 이평 아래면 신규 진입 차단
            if args.regime_ma and target == 1:
                ma = closed["close"].rolling(args.regime_ma).mean().iloc[-1]
                if closed["close"].iloc[-1] < ma:
                    target = 0
                    log.info(f"레짐 필터: 가격 < MA{args.regime_ma} → 진입 차단")

            # 변동성 타겟팅: 주문 금액 스케일링
            order_krw = args.max_krw
            if args.target_vol > 0:
                from backtest.sizing import vol_target_weight
                w = vol_target_weight(closed, target_vol=args.target_vol).iloc[-1]
                order_krw = args.max_krw * float(w)
                log.info(f"변동성 타겟팅: 비중 {w:.2f} → 주문금액 {order_krw:,.0f}원")

            holding = broker.position_value(price) > 5000

            # 손절 체크
            if holding and broker.entry_price > 0:
                if price / broker.entry_price - 1 <= args.stop_loss:
                    log.warning(f"손절 발동 ({args.stop_loss*100:.0f}%)")
                    broker.sell_all(price)
                    holding = False

            if target == 1 and not holding:
                broker.buy(price, order_krw)
            elif target == 0 and holding:
                broker.sell_all(price)
            else:
                log.info(f"유지 (target={target}, holding={holding}, 현재가 {price:,.0f})")

        except Exception as e:
            log.error(f"루프 오류: {e}")

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    main()
