"""
대한병원협회 공지사항 크롤러
공지 URL: https://www.kha.or.kr/kha_home/notice_list.do
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.kha.or.kr/kha_home/notice_list.do"


class KhaCrawler(BaseCrawler):
    site_key = "kha"
    site_name = "대한병원협회"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL)
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("div.div-table__wrap div.tbody div.tr"):
            title_tag = row.select_one("div.tb_03 a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            if not title or len(title) < 3:
                continue

            href = title_tag.get("href", "")
            # href 예: "?mode=view&articleNo=47576&article.offset=0&articleLimit=10"
            m = re.search(r"articleNo=(\d+)", href)
            notice_id = m.group(1) if m else title[:20]
            url = f"{LIST_URL}?mode=view&articleNo={notice_id}"

            date_tag = row.select_one("div.tb_05")
            posted_at = self.clean_text(date_tag.get_text()) if date_tag else None
            if posted_at and not re.match(r"\d{4}-\d{2}-\d{2}", posted_at):
                posted_at = None

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
            soup.select_one("div.fr-view")
            or soup.select_one("div.board-view__txt")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
