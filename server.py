"""Railway 배포용 통합 서버: 모의매매 봇(백그라운드) + 웹 대시보드(HTTP).

환경변수 설정 (Railway Variables에서):
  PORT       - Railway가 자동 주입 (직접 설정 불필요)
  STRATEGY   - donchian_ls | sma_ls          (기본: donchian_ls)
  PARAMS     - 전략 파라미터 JSON             (기본: {"n":40})
  SYMBOL     - 거래 심볼                      (기본: BTC/USDT:USDT)
  INTERVAL   - 봉 주기                        (기본: 4h)
  POLL_SEC   - 폴링 간격 초                   (기본: 300)
  MAX_USDT   - 가상 포지션 명목가              (기본: 500)
  STOP_LOSS  - 손절 비율                      (기본: -0.05)

⚠️ 이 서버는 페이퍼(모의매매) 전용이다. 실계좌 매매는 배포하지 말 것.
⚠️ Railway 재배포 시 상태 파일(futures_state.json)이 초기화된다 (기록용 로그는 대시보드에서 확인).
⚠️ Bybit는 미국 IP를 차단한다. 시세 조회가 403으로 실패하면
   Railway 프로젝트 Settings → Region을 Southeast Asia(싱가포르) 또는 EU로 변경할 것.
"""
import json
import logging
import os
import threading
import time
from http.server import HTTPServer

from live.dashboard import Handler
from live.futures_trader import (PaperFuturesBroker, fetch_candles, reconcile,
                                 STRATEGY_MAP)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("server")


def trading_loop():
    strategy_key = os.environ.get("STRATEGY", "donchian_ls")
    params = json.loads(os.environ.get("PARAMS", '{"n":40}'))
    symbol = os.environ.get("SYMBOL", "BTC/USDT:USDT")
    interval = os.environ.get("INTERVAL", "4h")
    poll_sec = int(os.environ.get("POLL_SEC", "300"))
    max_usdt = float(os.environ.get("MAX_USDT", "500"))
    stop_loss = float(os.environ.get("STOP_LOSS", "-0.05"))

    strat = STRATEGY_MAP[strategy_key]()
    broker = PaperFuturesBroker()
    log.info(f"[BOT] 모의매매 시작: {strat.name} {params} {symbol} {interval}")

    while True:
        try:
            df = fetch_candles(symbol, interval)
            price = float(df["close"].iloc[-1])
            target = int(strat.generate_signals(df.iloc[:-1], **params).iloc[-1])
            reconcile(broker, target, price, max_usdt, stop_loss)
        except Exception as e:
            log.error(f"[BOT] 루프 오류 (다음 폴링에서 재시도): {e}")
        time.sleep(poll_sec)


def main():
    port = int(os.environ.get("PORT", "8800"))
    t = threading.Thread(target=trading_loop, daemon=True)
    t.start()
    log.info(f"[WEB] 대시보드 서비스 시작: 0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
