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

⚠️ 페이퍼(모의매매) 전용. Bybit 미국 IP 차단 시 Railway Region을 Singapore/EU로.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path
from http.server import HTTPServer

from live.dashboard import Handler
from live.futures_trader import (PaperFuturesBroker, BybitFuturesBroker,
                                 fetch_candles, reconcile, STRATEGY_MAP)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("server")

STATUS_FILE = Path("bot_status.json")
HISTORY_FILE = Path("price_history.json")


def write_status(**kw):
    STATUS_FILE.write_text(json.dumps(kw, ensure_ascii=False))


def write_history(df):
    hist = [{"t": ts.strftime("%m-%d %H:%M"), "c": float(c)}
            for ts, c in df["close"].tail(300).items()]
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

    live_req = os.environ.get("LIVE_MODE", "").lower() == "true"
    has_keys = bool(os.environ.get("BYBIT_KEY")) and bool(os.environ.get("BYBIT_SECRET"))
    pw_ok = os.environ.get("DASHBOARD_PASSWORD", "1234") != "1234"
    if live_req and has_keys and pw_ok:
        broker = BybitFuturesBroker(symbol)
        mode = "LIVE"
        log.warning(f"[BOT] ⚠️ 실계좌(LIVE) 매매 시작 · 레버리지 1배: {strat.name} {params} {symbol}")
    else:
        broker = PaperFuturesBroker()
        mode = "PAPER"
        if live_req:
            reason = "API 키 없음" if not has_keys else "DASHBOARD_PASSWORD가 기본값(1234)"
            log.warning(f"[BOT] LIVE_MODE 요청됐지만 거부 ({reason}) → 페이퍼로 동작")
        log.info(f"[BOT] 모의매매 시작: {strat.name} {params} {symbol} {interval}")

    while True:
        try:
            df = fetch_candles(symbol, interval)
            price = float(df["close"].iloc[-1])
            write_history(df)
            target = int(strat.generate_signals(df.iloc[:-1], **params).iloc[-1])

            paused = Path("STOP").exists()
            if Path("CLOSE_NOW").exists():
                log.warning("[BOT] 수동 청산 요청")
                broker.close(price)
                Path("CLOSE_NOW").unlink(missing_ok=True)
            elif paused:
                if broker.side() != 0:
                    log.warning("[BOT] 일시정지 → 포지션 청산")
                    broker.close(price)
            else:
                reconcile(broker, target, price, max_usdt, stop_loss)

            write_status(time=time.strftime("%Y-%m-%d %H:%M:%S"),
                         price=price, signal=target, position=broker.side(),
                         paused=paused, strategy=strat.name, symbol=symbol,
                         interval=interval, mode=mode, error=None)
        except Exception as e:
            log.error(f"[BOT] 루프 오류 (재시도 예정): {e}")
            write_status(time=time.strftime("%Y-%m-%d %H:%M:%S"),
                         price=None, signal=None, position=None,
                         paused=Path("STOP").exists(), strategy=strat.name,
                         symbol=symbol, interval=interval, mode=mode,
                         error=str(e)[:200])
        time.sleep(poll_sec)


def main():
    port = int(os.environ.get("PORT", "8800"))
    threading.Thread(target=trading_loop, daemon=True).start()
    log.info(f"[WEB] 대시보드 서비스 시작: 0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
