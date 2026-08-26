"""
국민건강보험공단 규정 제·개정 예고 크롤러
경로: 홈 > 정책·제도 > 법령/업무기준 정보 > 규정 제·개정 예고
공지 URL: https://www.nhis.or.kr/nhis/together/wbhaec03500m01.do
(nhis_crawler.py의 '공지사항' 게시판과는 별개 게시판 — 공단 내부규정 제·개정안을
사전 공고하는 곳으로, 건강검진 관련 규정 개정 시 여기에서도 확인 가능)
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.nhis.or.kr/nhis/together/wbhaec03500m01.do"
BASE_URL = "https://www.nhis.or.kr"


class NhisRuleCrawler(BaseCrawler):
    site_key = "nhis_rule"
    site_name = "국민건강보험공단 (규정 제개정예고)"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL)
        soup = self.soup(resp.text)
        items = []

        for tag in soup.select("a[href*='mode=view'][href*='articleNo']"):
            title = self.clean_text(tag.get_text())
            if not title:
                continue

            href = tag.get("href", "")
            onclick = tag.get("onclick", "")
            src = href or onclick

            article_no = re.search(r"articleNo[=,](\d+)", src)
            if not article_no:
                continue

            notice_id = article_no.group(1)
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = f"{BASE_URL}{href}"
            else:
                url = f"{LIST_URL}?mode=view&articleNo={notice_id}"

            row = tag.find_parent("tr")
            posted_at = None
            if row:
                for col in row.select("td"):
                    txt = self.clean_text(col.get_text())
                    if re.match(r"\d{4}\.\d{2}\.\d{2}", txt):
                        posted_at = txt
                        break

            items.append(NoticeItem(
                notice_id=notice_id,
                title=title,
                url=url,
                posted_at=posted_at,
            ))

        return items

    def fetch_notice_content(self, item: NoticeItem) -> str:
        resp = self.get(item.url)
        soup = self.soup(resp.text)
        content_div = (
            soup.select_one("div.post-content div.fr-view")
            or soup.select_one("div.view_cont")
            or soup.select_one("div.board_view")
            or soup.select_one("div.cont_area")
            or soup.select_one("td.cont")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
