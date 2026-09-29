"""
국립암센터 국가암정보센터 공지사항 크롤러
공지 URL: https://www.cancer.go.kr/lay1/bbs/S1T610C611/A/31/list.do
"""
import re

from .base_crawler import BaseCrawler, NoticeItem

LIST_URL = "https://www.cancer.go.kr/lay1/bbs/S1T610C611/A/31/list.do"
DETAIL_BASE = "https://www.cancer.go.kr/lay1/bbs/S1T610C611/A/31/view.do"


class NccCrawler(BaseCrawler):
    site_key = "ncc"
    site_name = "국립암센터 국가암정보센터"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL)
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("table tbody tr"):
            title_tag = row.select_one("td.title a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            if not title or len(title) < 3:
                continue

            href = title_tag.get("href", "")
            m = re.search(r"article_seq=(\d+)", href)
            notice_id = m.group(1) if m else title[:20]
            url = f"{DETAIL_BASE}?article_seq={notice_id}"

            date_tag = row.select_one("td.date")
            posted_at = self.clean_text(date_tag.get_text()).replace(".", "-") if date_tag else None
            if posted_at and posted_at.endswith("-"):
                posted_at = posted_at.rstrip("-")

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
        content_td = soup.select_one("table.view_style_1 td.contents")
        return self.clean_text(content_td.get_text()) if content_td else ""
