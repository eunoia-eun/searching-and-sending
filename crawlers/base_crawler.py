import base64
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config
import settings_store
import timeutil
from db import database

logger = logging.getLogger(__name__)


@dataclass
class NoticeItem:
    notice_id: str
    title: str
    url: str
    posted_at: Optional[str] = None
    content: Optional[str] = None
    extra_url: Optional[str] = None  # 원문 외 보조 링크 (예: law_crawler의 신구법비교)


class LambdaRelayAdapter(requests.adapters.HTTPAdapter):
    """GitHub Actions(Azure) IP를 차단하는 .go.kr 사이트용 — 요청을 직접 보내는 대신
    서울 리전 AWS Lambda에 대상 URL을 넘겨 대신 가져오게 한다."""

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        relay_resp = requests.post(
            config.LAMBDA_RELAY_URL,
            json={"url": request.url},
            headers={"x-relay-secret": config.LAMBDA_RELAY_SECRET},
            timeout=timeout or config.REQUEST_TIMEOUT,
        )
        relay_resp.raise_for_status()
        data = relay_resp.json()

        resp = requests.Response()
        resp.status_code = data["status"]
        resp._content = base64.b64decode(data["body_b64"])
        resp.headers["Content-Type"] = data.get("content_type", "")
        resp.url = request.url
        resp.request = request

        # 헤더에 charset이 명시돼 있으면 그걸 쓰고, 없으면(예: moel — meta 태그로만 선언)
        # requests 기본값인 ISO-8859-1 대신 UTF-8로 가정 (대상 4개 사이트 전부 실제로는 UTF-8)
        encoding = requests.utils.get_encoding_from_headers(resp.headers)
        resp.encoding = encoding if encoding and encoding.lower() != "iso-8859-1" else "utf-8"
        return resp


class BaseCrawler(ABC):
    site_key: str = ""
    site_name: str = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.DEFAULT_HEADERS)
        if config.LAMBDA_RELAY_URL and self.site_key in config.LAMBDA_RELAY_SITES:
            base_url = config.SITES.get(self.site_key, {}).get("base_url", "")
            if base_url:
                self.session.mount(base_url, LambdaRelayAdapter())

    # ── 하위 클래스가 반드시 구현 ───────────────────────────────
    @abstractmethod
    def fetch_notice_list(self) -> list[NoticeItem]:
        """공지 목록 페이지에서 NoticeItem 리스트를 반환."""

    @abstractmethod
    def fetch_notice_content(self, item: NoticeItem) -> str:
        """개별 공지 URL에서 본문 텍스트를 반환."""

    # ── 공통 헬퍼 ─────────────────────────────────────────────
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """연결 타임아웃/네트워크 오류나 서버 5xx는 최대 config.MAX_RETRIES회까지
        지수 백오프로 재시도한다 (GitHub Actions 서버에서 국내 사이트 접속이
        가끔 일시적으로 타임아웃 나는 문제 대응)."""
        last_exc: Exception = RuntimeError("요청 실패")
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = self.session.request(method, url, timeout=config.REQUEST_TIMEOUT, **kwargs)
                resp.raise_for_status()
                time.sleep(config.REQUEST_DELAY)
                return resp
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if not (500 <= status < 600):
                    raise
                last_exc = e

            if attempt < config.MAX_RETRIES - 1:
                wait = config.RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "[%s] 요청 실패(%d/%d회), %d초 후 재시도 — %s: %s",
                    self.site_name, attempt + 1, config.MAX_RETRIES, wait, url, last_exc,
                )
                time.sleep(wait)

        raise last_exc

    def get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)

    def soup(self, html: str, parser: str = "lxml") -> BeautifulSoup:
        return BeautifulSoup(html, parser)

    def clean_text(self, text: str) -> str:
        return " ".join(text.split()).strip()

    # ── 메인 실행 ─────────────────────────────────────────────
    def run(self) -> list[dict]:
        """새 공지를 수집하고 DB에 저장. 새로 저장된 항목 목록을 반환."""
        started_at = timeutil.now_utc_iso()
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

                if not settings_store.matches_keywords(self.site_key, item.title, content):
                    logger.info("[%s] 키워드 필터 제외: %s", self.site_name, item.title)
                    continue

                row_id = database.save_notice(
                    site_key=self.site_key,
                    notice_id=item.notice_id,
                    title=item.title,
                    url=item.url,
                    posted_at=item.posted_at,
                    content=content,
                    extra_url=item.extra_url,
                )
                if row_id:
                    new_notices.append({
                        "db_id": row_id,
                        "site_name": self.site_name,
                        "title": item.title,
                        "url": item.url,
                        "posted_at": item.posted_at,
                        "content": content,
                        "extra_url": item.extra_url,
                    })
                    logger.info("[%s] 신규 공지 저장: %s", self.site_name, item.title)

        except Exception as e:
            error_msg = str(e)
            logger.error("[%s] 크롤링 오류: %s", self.site_name, e)

        finished_at = timeutil.now_utc_iso()
        database.log_crawl(self.site_key, started_at, finished_at, len(new_notices), error_msg)
        return new_notices
