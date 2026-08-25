import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config
import settings_store
from db import database

logger = logging.getLogger(__name__)


@dataclass
class NoticeItem:
    notice_id: str
    title: str
    url: str
    posted_at: Optional[str] = None
    content: Optional[str] = None


class BaseCrawler(ABC):
    site_key: str = ""
    site_name: str = ""
    # settings_store 키워드 필터 적용 여부. law_crawler처럼 이미 자체 검색어로
    # 범위를 좁혀 수집하는 크롤러는 False로 오버라이드한다.
    apply_keyword_filter: bool = True

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.DEFAULT_HEADERS)

    # ── 하위 클래스가 반드시 구현 ───────────────────────────────
    @abstractmethod
    def fetch_notice_list(self) -> list[NoticeItem]:
        """공지 목록 페이지에서 NoticeItem 리스트를 반환."""

    @abstractmethod
    def fetch_notice_content(self, item: NoticeItem) -> str:
        """개별 공지 URL에서 본문 텍스트를 반환."""

    # ── 공통 헬퍼 ─────────────────────────────────────────────
    def get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
        resp.raise_for_status()
        time.sleep(config.REQUEST_DELAY)
        return resp

    def post(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.post(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
        resp.raise_for_status()
        time.sleep(config.REQUEST_DELAY)
        return resp

    def soup(self, html: str, parser: str = "lxml") -> BeautifulSoup:
        return BeautifulSoup(html, parser)

    def clean_text(self, text: str) -> str:
        return " ".join(text.split()).strip()

    # ── 메인 실행 ─────────────────────────────────────────────
    def run(self) -> list[dict]:
        """새 공지를 수집하고 DB에 저장. 새로 저장된 항목 목록을 반환."""
        started_at = datetime.now().isoformat(timespec="seconds")
        new_notices = []
        error_msg = ""

        try:
            items = self.fetch_notice_list()
            logger.info("[%s] 목록 %d건 조회", self.site_name, len(items))

            for item in items:
                if database.is_seen(self.site_key, item.notice_id):
                    continue

                try:
                    content = self.fetch_notice_content(item)
                except Exception as e:
                    logger.warning("[%s] 본문 수집 실패 (%s): %s", self.site_name, item.url, e)
                    content = ""

                if self.apply_keyword_filter and not settings_store.matches_keywords(item.title, content):
                    logger.info("[%s] 키워드 필터 제외: %s", self.site_name, item.title)
                    continue

                row_id = database.save_notice(
                    site_key=self.site_key,
                    notice_id=item.notice_id,
                    title=item.title,
                    url=item.url,
                    posted_at=item.posted_at,
                    content=content,
                )
                if row_id:
                    new_notices.append({
                        "db_id": row_id,
                        "site_name": self.site_name,
                        "title": item.title,
                        "url": item.url,
                        "posted_at": item.posted_at,
                        "content": content,
                    })
                    logger.info("[%s] 신규 공지 저장: %s", self.site_name, item.title)

        except Exception as e:
            error_msg = str(e)
            logger.error("[%s] 크롤링 오류: %s", self.site_name, e)

        finished_at = datetime.now().isoformat(timespec="seconds")
        database.log_crawl(self.site_key, started_at, finished_at, len(new_notices), error_msg)
        return new_notices
