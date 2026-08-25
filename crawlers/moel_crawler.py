"""
고용노동부 공지사항 크롤러
공지 URL: https://www.moel.go.kr/news/notice/noticeList.do
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.moel.go.kr/news/notice/noticeList.do"
DETAIL_BASE = "https://www.moel.go.kr/news/notice/noticeView.do"
BASE_URL = "https://www.moel.go.kr"


class MoelCrawler(BaseCrawler):
    site_key = "moel"
    site_name = "고용노동부"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL, params={"pageIndex": 1})
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("table tbody tr"):
            cols = row.select("td")
            if not cols or len(cols) < 3:
                continue

            num_text = self.clean_text(cols[0].get_text())
            if not num_text.isdigit():
                continue

            title_tag = cols[1].find("a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            href = title_tag.get("href", "")
            onclick = title_tag.get("onclick", "")

            # bbs_seq 또는 bltNo 추출
            seq = (re.search(r"bbs_seq=(\d+)", href or onclick)
                   or re.search(r"bltNo=(\d+)", href or onclick))

            if seq:
                notice_id = seq.group(1)
                url = f"{DETAIL_BASE}?bbs_seq={notice_id}"
            else:
                notice_id = num_text
                url = href if href.startswith("http") else f"{BASE_URL}{href}"

            posted_at = None
            for col in cols:
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
            soup.select_one("div.board_view_wrap div.b_content")
            or soup.select_one("div.view_con")
            or soup.select_one("div.brd_view_cont")
            or soup.select_one("div.cont_area")
            or soup.select_one("div#content")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
