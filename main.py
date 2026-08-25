"""
건강검진 공지 자동 서칭 시스템 - 메인 진입점
실행 (전체 파이프라인): python main.py
실행 (크롤링만):        python main.py --no-analyze --no-notify
실행 (특정 사이트):     python main.py --sites nhis moel  (일회성, 지정 시 활성 사이트 설정 무시)

크롤링 대상 사이트 / 관심 키워드 관리: python admin.py 참고
"""
import argparse
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import settings_store
from db import database
from crawlers.nhis_crawler import NhisCrawler
from crawlers.moel_crawler import MoelCrawler
from crawlers.hira_crawler import HiraCrawler
from crawlers.kdca_crawler import KdcaCrawler
from crawlers.law_crawler import LawCrawler
from crawlers.khhi_crawler import KhhiCrawler
from crawlers.kahp_crawler import KahpCrawler
from crawlers.kiha_crawler import KihaCrawler
from crawlers.mpm_crawler import MpmCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crawler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

ALL_CRAWLERS = {
    "nhis": NhisCrawler,
    "moel": MoelCrawler,
    "hira": HiraCrawler,
    "kdca": KdcaCrawler,
    "law":  LawCrawler,
    "khhi": KhhiCrawler,
    "kahp": KahpCrawler,
    "kiha": KihaCrawler,
    "mpm":  MpmCrawler,
}


def run_crawlers(site_keys: list[str]) -> list[dict]:
    all_new = []
    for key in site_keys:
        cls = ALL_CRAWLERS.get(key)
        if not cls:
            logger.warning("알 수 없는 사이트 키: %s", key)
            continue
        logger.info("=== [%s] 크롤링 시작 ===", key)
        crawler = cls()
        new_notices = crawler.run()
        logger.info("=== [%s] 신규 공지 %d건 ===", key, len(new_notices))
        all_new.extend(new_notices)
    return all_new


def run_full_pipeline(
    site_keys: list[str] | None = None,
    do_analyze: bool = True,
    do_notify: bool = True,
) -> dict:
    """크롤링 → 분석 → 이메일 발송 전체 파이프라인."""
    if site_keys is None:
        site_keys = settings_store.get_enabled_sites()

    # 1. 크롤링
    new_notices = run_crawlers(site_keys)
    logger.info("크롤링 완료 -신규 %d건", len(new_notices))

    # 2. 분석
    if do_analyze:
        from analyzer import analyze_notices
        analyze_notices()

    # 3. 미발송 분석 결과 조회 → 이메일 발송
    notified_count = 0
    if do_notify:
        from notifier import send_notification
        pending = database.get_unnotified_analyses()
        if pending:
            logger.info("발송 대상: %d건", len(pending))
            send_notification(pending)
            notified_count = len(pending)
        else:
            logger.info("발송할 신규 알림 없음")

    return {
        "crawled": len(new_notices),
        "notified": notified_count,
    }


def main():
    parser = argparse.ArgumentParser(description="건강검진 공지 크롤러")
    parser.add_argument(
        "--sites",
        nargs="+",
        default=None,
        choices=list(ALL_CRAWLERS.keys()),
        help="크롤링할 사이트 키 (기본: admin.py로 설정한 활성 사이트 목록)",
    )
    parser.add_argument("--no-analyze", action="store_true", help="분석 단계 건너뜀")
    parser.add_argument("--no-notify",  action="store_true", help="이메일 발송 건너뜀")
    args = parser.parse_args()

    database.init_db()
    logger.info("DB 초기화 완료")

    result = run_full_pipeline(
        site_keys=args.sites,
        do_analyze=not args.no_analyze,
        do_notify=not args.no_notify,
    )
    logger.info("완료 -크롤링 %d건 / 발송 %d건", result["crawled"], result["notified"])


if __name__ == "__main__":
    main()
