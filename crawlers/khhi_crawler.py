"""
한국건강검진기관협의회 공지사항 크롤러

게시판 목록/상세 페이지(bbs/board.php?bo_table=notice)는 로그인해야 조회 가능하여
홈페이지 최신 공지 위젯(div.latest_top_wr)에서 목록을 수집한다.
본문은 로그인 필요로 수집 불가(빈 문자열).
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

HOME_URL = "https://www.takehealth.or.kr/"
BASE_URL = "https://www.takehealth.or.kr"


class KhhiCrawler(BaseCrawler):
    site_key = "khhi"
    site_name = "한국건강검진기관협의회"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(HOME_URL)
        soup = self.soup(resp.text)
        items = []

        widget = soup.select_one("div.latest_top_wr")
        rows = widget.select("a[href*='bo_table=notice']") if widget else []
        rows = [a.find_parent("li") or a for a in rows]
        for row in rows:
            title_tag = row.find("a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            if not title:
                continue

            href = title_tag.get("href", "")
            url = href if href.startswith("http") else f"{BASE_URL}{href}"

            wr_id = re.search(r"wr_id=(\d+)", href)
            notice_id = wr_id.group(1) if wr_id else re.sub(r"[^0-9]", "", href)[-10:]

            date_tag = row.select_one("span.lt_date")
            posted_at = self.clean_text(date_tag.get_text()) if date_tag else None

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
            soup.select_one("div#bo-view-content")
            or soup.select_one("div.bo-view-content")
            or soup.select_one("div#view_content")
            or soup.select_one("div.view_content")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
