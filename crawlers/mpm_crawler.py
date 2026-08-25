"""
인사혁신처 공지사항 크롤러
공지 URL: https://www.mpm.go.kr/mpm/comm/noti/newsNoitice/
공무원 채용 신체검사 규정 관련 실무 안내(시행일정, 서식, 절차 변경 등)를
law_crawler(법령 개정 자체)와 별개로 포착하기 위해 추가.
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

BASE_URL = "https://www.mpm.go.kr"
LIST_URL = "https://www.mpm.go.kr/mpm/comm/noti/newsNoitice/"
BOARD_ID = "bbs_0000000000000020"


class MpmCrawler(BaseCrawler):
    site_key = "mpm"
    site_name = "인사혁신처"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL)
        soup = self.soup(resp.text)
        items = []

        for tag in soup.select("a[href*='mode=view']"):
            title = self.clean_text(tag.get_text())
            if not title:
                continue

            href = tag.get("href", "")
            cnt_id = re.search(r"cntId=(\d+)", href)
            if not cnt_id:
                continue

            notice_id = cnt_id.group(1)
            url = f"{LIST_URL}?boardId={BOARD_ID}&mode=view&cntId={notice_id}&category=&pageIdx="

            row = tag.find_parent("tr")
            posted_at = None
            if row:
                for col in row.select("td"):
                    txt = self.clean_text(col.get_text())
                    if re.match(r"\d{4}-\d{2}-\d{2}", txt):
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
            soup.select_one("div#boardContent")
            or soup.select_one("div.board_content")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
