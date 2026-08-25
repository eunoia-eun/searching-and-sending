"""
스케줄러 — 전체 파이프라인을 주기적으로 자동 실행
실행: python scheduler.py

크론으로 등록하려면 scheduler.py 대신 main.py를 직접 등록:
  0 * * * * cd /path/to/project && python main.py >> cron.log 2>&1
"""
import logging
import signal
import sys
import time

import config
from db import database
from main import run_full_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

_running = True


def _handle_signal(signum, frame):
    global _running
    logger.info("종료 신호 수신 — 다음 대기 후 종료됩니다.")
    _running = False


def main():
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    interval_sec = config.CRAWL_INTERVAL_MINUTES * 60
    logger.info("스케줄러 시작 — 실행 간격: %d분", config.CRAWL_INTERVAL_MINUTES)

    database.init_db()

    while _running:
        logger.info("========== 파이프라인 실행 ==========")
        try:
            result = run_full_pipeline()
            logger.info("파이프라인 완료 — 크롤링 %d건 / 발송 %d건",
                        result["crawled"], result["notified"])
        except Exception as exc:
            logger.error("파이프라인 오류: %s", exc, exc_info=True)

        if not _running:
            break

        logger.info("다음 실행까지 %d분 대기...", config.CRAWL_INTERVAL_MINUTES)
        # 1분 단위로 끊어서 종료 신호에 즉시 반응
        for _ in range(config.CRAWL_INTERVAL_MINUTES):
            if not _running:
                break
            time.sleep(60)

    logger.info("스케줄러 종료")


if __name__ == "__main__":
    main()
