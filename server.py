"""Railway 배포용 통합 서버: 모의매매 봇(백그라운드) + 웹 대시보드(HTTP).

환경변수 (Railway Variables):
  PORT, STRATEGY(donchian_ls|sma_ls), PARAMS, SYMBOL, INTERVAL, POLL_SEC,
  MAX_USDT, STOP_LOSS, DASHBOARD_PASSWORD(제어 버튼 비밀번호, 기본 "1234")

실계좌 전환 (Railway Variables에서 설정):
  LIVE_MODE=true          - 실계좌 매매 활성화
  BYBIT_KEY / BYBIT_SECRET - Bybit API 키 (거래 권한만, 출금 권한 금지!)
  단, DASHBOARD_PASSWORD가 기본값(1234)이면 실계좌 모드를 거부하고 페이퍼로 동작한다.

제어 파일 (대시보드 버튼이 생성/삭제):
  STOP      - 존재하면 일시정지 (포지션 청산 후 관망, 삭제 시 재개)
  CLOSE_NOW - 존재하면 즉시 수동 청산 후 파일 삭제 (매매는 계속)
  MODE      - "LIVE" 또는 "PAPER" (대시보드에서 전환, 키+비밀번호 조건 충족 시만)

⚠️ 페이퍼(모의매매) 전용. Bybit 미국 IP 차단 시 Railway Region을 Singapore/EU로.
"""
import json
import logging
import os
import threading
import time

from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))


def kst_now(fmt="%Y-%m-%d %H:%M:%S"):
    """컨테이너 tzdata 유무와 무관하게 항상 한국시간 반환."""
    return datetime.now(KST).strftime(fmt)
from pathlib import Path
from http.server import HTTPServer

from live.dashboard import Handler
from live.futures_trader import (PaperFuturesBroker, BybitFuturesBroker,
                                 fetch_candles, reconcile, get_bybit_keys,
                                 STRATEGY_MAP)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("server")

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATUS_FILE = DATA_DIR / "bot_status.json"
HISTORY_FILE = DATA_DIR / "price_history.json"
TICKER_FILE = DATA_DIR / "price_now.json"


def ticker_loop():
    """10초마다 현재가만 갱신 (대시보드 실시간 평가손익용)."""
    import ccxt
    ex = ccxt.bybit({"options": {"defaultType": "swap"}})
    symbol = os.environ.get("SYMBOL", "BTC/USDT:USDT")
    while True:
        try:
            t = ex.fetch_ticker(symbol)
            TICKER_FILE.write_text(json.dumps(
                {"price": float(t["last"]), "time": kst_now("%H:%M:%S")}))
        except Exception as e:
            log.debug(f"[TICKER] {e}")
        time.sleep(10)


def write_status(**kw):
    STATUS_FILE.write_text(json.dumps(kw, ensure_ascii=False))


def write_history(df):
    closes = df["close"].tail(300)
    closes.index = closes.index + __import__("pandas").Timedelta(hours=9)  # UTC→KST
    hist = [{"t": ts.strftime("%m-%d %H:%M"), "c": float(c)}
            for ts, c in closes.items()]
    HISTORY_FILE.write_text(json.dumps(hist))


def trading_loop():
    strategy_key = os.environ.get("STRATEGY", "donchian_ls")
    params = json.loads(os.environ.get("PARAMS", '{"n":40}'))
    symbol = os.environ.get("SYMBOL", "BTC/USDT:USDT")
    interval = os.environ.get("INTERVAL", "4h")
    poll_sec = int(os.environ.get("POLL_SEC", "300"))
    max_usdt = float(os.environ.get("MAX_USDT", "500"))
    stop_loss = float(os.environ.get("STOP_LOSS", "-0.05"))

    strat = STRATEGY_MAP[strategy_key]()

    def live_allowed():
        k, s = get_bybit_keys()
        pw_ok = os.environ.get("DASHBOARD_PASSWORD", "1234") != "1234"
        return bool(k and s) and pw_ok

    def desired_mode():
        if (DATA_DIR / "MODE").exists():
            m = (DATA_DIR / "MODE").read_text().strip().upper()
        else:
            m = "LIVE" if os.environ.get("LIVE_MODE", "").lower() == "true" else "PAPER"
        return "LIVE" if (m == "LIVE" and live_allowed()) else "PAPER"

    def make_broker(m):
        if m == "LIVE":
            log.warning(f"[BOT] ⚠️ 실계좌(LIVE) 매매 · 레버리지 1배: {strat.name} {params} {symbol}")
            return BybitFuturesBroker(symbol)
        log.info(f"[BOT] 모의매매(PAPER): {strat.name} {params} {symbol} {interval}")
        return PaperFuturesBroker()

    mode = desired_mode()
    broker = make_broker(mode)

    while True:
        try:
            df = fetch_candles(symbol, interval)
            price = float(df["close"].iloc[-1])
            write_history(df)

            # 모드 전환 요청 처리: 기존 포지션 청산 후 브로커 교체
            want = desired_mode()
            if want != mode:
                log.warning(f"[BOT] 모드 전환 {mode} → {want}: 기존 포지션 청산")
                broker.close(price)
                mode = want
                broker = make_broker(mode)
            target = int(strat.generate_signals(df.iloc[:-1], **params).iloc[-1])

            paused = (DATA_DIR / "STOP").exists()
            if (DATA_DIR / "CLOSE_NOW").exists():
                log.warning("[BOT] 수동 청산 요청")
                broker.close(price)
                (DATA_DIR / "CLOSE_NOW").unlink(missing_ok=True)
            elif paused:
                if broker.side() != 0:
                    log.warning("[BOT] 일시정지 → 포지션 청산")
                    broker.close(price)
            else:
                reconcile(broker, target, price, max_usdt, stop_loss)

            upnl = broker.unrealized_pct(price) * 100 if broker.side() else None

            # 시그널 판독: 돈치안 채널 트리거 가격
            advice = None
            if strategy_key == "donchian_ls":
                n = params.get("n", 40)
                closed = df.iloc[:-1]
                ch_hi = float(closed["high"].rolling(n).max().iloc[-1])
                ch_lo = float(closed["low"].rolling(n).min().iloc[-1])
                advice = {"hi": ch_hi, "lo": ch_lo, "n": n}
            write_status(time=kst_now(),
                         price=price, signal=target, position=broker.side(),
                         upnl=upnl, entry=getattr(broker, "entry_price", 0) or None,
                         advice=advice,
                         paused=paused, strategy=strat.name, symbol=symbol,
                         interval=interval, mode=mode, error=None)
        except Exception as e:
            log.error(f"[BOT] 루프 오류 (재시도 예정): {e}")
            write_status(time=kst_now(),
                         price=None, signal=None, position=None,
                         paused=(DATA_DIR / "STOP").exists(), strategy=strat.name,
                         symbol=symbol, interval=interval, mode=mode,
                         error=str(e)[:200])
        time.sleep(poll_sec)


def main():
    port = int(os.environ.get("PORT", "8800"))
    threading.Thread(target=trading_loop, daemon=True).start()
    threading.Thread(target=ticker_loop, daemon=True).start()
    log.info(f"[WEB] 대시보드 서비스 시작: 0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
