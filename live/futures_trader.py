"""선물 롱숏 자동매매 (Bybit 무기한).

⚠️ 반드시 --paper로 충분히 검증 후 실계좌 전환. 레버리지는 1배로 고정된다.

사용법:
  # 모의매매 (기본)
  python -m live.futures_trader --symbol BTC/USDT:USDT --strategy donchian_ls \
      --params '{"n":40}' --paper

  # 실계좌 (Bybit API 키 필요, 선물 지갑에 USDT 필요)
  BYBIT_KEY=... BYBIT_SECRET=... python -m live.futures_trader \
      --symbol BTC/USDT:USDT --strategy donchian_ls --params '{"n":40}' \
      --live --max-usdt 100

안전장치:
  - 레버리지 1배 강제 설정
  - --max-usdt: 포지션 명목가 상한
  - --stop-loss: 진입가 대비 손절 (롱/숏 모두, 기본 -5%)
  - kill switch: touch STOP → 전량 청산 후 종료
주의: 펀딩비는 8시간마다 자동 정산되며 이 봇은 이를 제어하지 않는다.
"""
import argparse
import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

from strategies.long_short import SmaCrossLS, DonchianLS

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler("futures_trading.log")])
log = logging.getLogger("futures")

STRATEGY_MAP = {"sma_ls": SmaCrossLS, "donchian_ls": DonchianLS}
STATE_FILE = Path("futures_state.json")
TRADES_FILE = Path("live_trades.json")


def record_trade(side, price, amount, pnl_pct=None, equity=None):
    trades = json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else []
    trades.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "side": side,
                   "price": price, "amount": amount, "pnl_pct": pnl_pct,
                   "equity": equity})
    TRADES_FILE.write_text(json.dumps(trades, ensure_ascii=False, indent=1))


class PaperFuturesBroker:
    """모의 선물: 롱(+qty)/숏(-qty) 가상 체결. 대시보드와 동일 파일 사용."""

    FEE = 0.00055  # bybit taker

    def __init__(self, initial_usdt=1000.0):
        st = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        self.cash = st.get("cash", initial_usdt)
        self.qty = st.get("qty", 0.0)       # +롱 / -숏
        self.entry_price = st.get("entry_price", 0.0)

    def _save(self):
        STATE_FILE.write_text(json.dumps(
            {"cash": self.cash, "qty": self.qty, "entry_price": self.entry_price}))

    def side(self):
        return 1 if self.qty > 0 else -1 if self.qty < 0 else 0

    def unrealized_pct(self, price):
        if not self.qty or not self.entry_price:
            return 0.0
        d = price / self.entry_price - 1
        return d if self.qty > 0 else -d

    def open(self, direction, price, usdt):
        usdt = min(usdt, self.cash)
        if usdt < 10:
            return
        self.qty = direction * (usdt / price) * (1 - self.FEE)
        self.entry_price = price
        self._save()
        tag = "LONG" if direction > 0 else "SHORT"
        record_trade(tag, price, usdt, equity=self.cash)
        log.info(f"[PAPER] {tag} 진입 {usdt:,.0f} USDT @ {price:,.2f}")

    def close(self, price):
        if not self.qty:
            return
        pnl = self.unrealized_pct(price) - 2 * self.FEE
        self.cash *= (1 + pnl * abs(self.qty) * self.entry_price / self.cash) \
            if self.cash else 1
        # 단순화: 포지션 명목가 기준 손익 반영
        tag = "CLOSE-L" if self.qty > 0 else "CLOSE-S"
        record_trade(tag, price, abs(self.qty) * price, pnl_pct=pnl * 100,
                     equity=self.cash)
        log.info(f"[PAPER] {tag} @ {price:,.2f} (손익 {pnl*100:+.2f}%) "
                 f"잔고 {self.cash:,.2f} USDT")
        self.qty, self.entry_price = 0.0, 0.0
        self._save()


class BybitFuturesBroker:
    def __init__(self, symbol):
        import ccxt
        self.api = ccxt.bybit({
            "apiKey": os.environ["BYBIT_KEY"],
            "secret": os.environ["BYBIT_SECRET"],
            "options": {"defaultType": "swap"},
        })
        self.symbol = symbol
        self.entry_price = 0.0
        try:
            self.api.set_leverage(1, symbol)  # 1배 강제
            log.info("레버리지 1배 설정 완료")
        except Exception as e:
            log.warning(f"레버리지 설정 실패(이미 1배일 수 있음): {e}")

    def _position(self):
        for p in self.api.fetch_positions([self.symbol]):
            size = float(p.get("contracts") or 0)
            if size:
                sign = 1 if p["side"] == "long" else -1
                self.entry_price = float(p.get("entryPrice") or 0)
                return sign * size
        return 0.0

    def side(self):
        q = self._position()
        return 1 if q > 0 else -1 if q < 0 else 0

    def unrealized_pct(self, price):
        q = self._position()
        if not q or not self.entry_price:
            return 0.0
        d = price / self.entry_price - 1
        return d if q > 0 else -d

    def open(self, direction, price, usdt):
        qty = usdt / price
        side = "buy" if direction > 0 else "sell"
        r = self.api.create_order(self.symbol, "market", side, qty)
        log.info(f"[BYBIT] {'LONG' if direction>0 else 'SHORT'} 진입 {qty:.6f}: {r['id']}")

    def close(self, price):
        q = self._position()
        if not q:
            return
        side = "sell" if q > 0 else "buy"
        r = self.api.create_order(self.symbol, "market", side, abs(q),
                                  params={"reduceOnly": True})
        log.info(f"[BYBIT] 청산 {abs(q):.6f}: {r['id']}")


def fetch_candles(symbol, interval="4h", count=250) -> pd.DataFrame:
    import ccxt
    ex = ccxt.bybit({"options": {"defaultType": "swap"}})
    rows = ex.fetch_ohlcv(symbol, timeframe=interval, limit=count)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("ts")


def reconcile(broker, target: int, price: float, max_usdt: float, stop_loss: float):
    """현재 포지션을 목표(+1/0/-1)에 맞춘다. 손절 우선."""
    current = broker.side()

    if current != 0 and broker.unrealized_pct(price) <= stop_loss:
        log.warning(f"손절 발동 ({stop_loss*100:.0f}%) → 이번 사이클 재진입 없이 관망")
        broker.close(price)
        return  # 손절 직후 같은 시그널로 곧바로 재진입하는 것을 방지

    if target == current:
        log.info(f"유지 (포지션 {['숏','현금','롱'][current+1]}, 현재가 {price:,.2f})")
        return

    if current != 0:
        broker.close(price)
    if target != 0:
        broker.open(target, price, max_usdt)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTC/USDT:USDT")
    p.add_argument("--strategy", choices=list(STRATEGY_MAP), required=True)
    p.add_argument("--params", default="{}")
    p.add_argument("--interval", default="4h")
    p.add_argument("--poll-sec", type=int, default=300)
    p.add_argument("--max-usdt", type=float, default=100.0)
    p.add_argument("--stop-loss", type=float, default=-0.05)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--paper", action="store_true", default=True)
    g.add_argument("--live", dest="paper", action="store_false")
    args = p.parse_args()

    strat = STRATEGY_MAP[args.strategy]()
    params = json.loads(args.params)

    if args.paper:
        broker = PaperFuturesBroker()
        log.info("=== 선물 모의매매(PAPER) 모드 ===")
    else:
        if input("⚠️ 실계좌 선물 매매입니다. 'YES' 입력: ") != "YES":
            return
        broker = BybitFuturesBroker(args.symbol)
        log.info("=== Bybit 실계좌(LIVE) 모드 · 레버리지 1배 ===")

    log.info(f"전략={strat.name} params={params} 심볼={args.symbol}")

    while True:
        try:
            if Path("STOP").exists():
                log.warning("STOP 감지 → 청산 후 종료")
                df = fetch_candles(args.symbol, args.interval)
                broker.close(df["close"].iloc[-1])
                break
            df = fetch_candles(args.symbol, args.interval)
            price = float(df["close"].iloc[-1])
            target = int(strat.generate_signals(df.iloc[:-1], **params).iloc[-1])
            reconcile(broker, target, price, args.max_usdt, args.stop_loss)
        except Exception as e:
            log.error(f"루프 오류: {e}")
        time.sleep(args.poll_sec)


if __name__ == "__main__":
    main()
