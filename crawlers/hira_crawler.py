"""
건강보험심사평가원 공지사항 크롤러
공지 URL: https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020002000100
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.hira.or.kr/bbsDummy.do"
LIST_PARAMS = {"pgmid": "HIRAA020002000100"}
DETAIL_BASE = "https://www.hira.or.kr/bbsDummy.do"


class HiraCrawler(BaseCrawler):
    site_key = "hira"
    site_name = "건강보험심사평가원"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL, params=LIST_PARAMS)
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("table tbody tr"):
            num_tag = row.select_one("td.col-num")
            title_tag = row.select_one("td.col-tit a")
            if not num_tag or not title_tag:
                continue

            num_text = self.clean_text(num_tag.get_text())
            title = self.clean_text(title_tag.get_text())
            href = title_tag.get("href", "")
            if not title or not href:
                continue

            # brdBltNo 추출
            brd_blt_no = re.search(r"brdBltNo=(\d+)", href)
            if brd_blt_no:
                notice_id = brd_blt_no.group(1)
                url = (
                    f"{DETAIL_BASE}?pgmid=HIRAA020002000100"
                    f"&brdScnBltNo=4&brdBltNo={notice_id}"
                )
            else:
                notice_id = num_text
                url = href if href.startswith("http") else f"https://www.hira.or.kr{href}"

            date_tag = row.select_one("td.col-date")
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
            soup.select_one("div.viewCont div.view")
            or soup.select_one("div.viewCont")
            or soup.select_one("div.bbs_view_cont")
            or soup.select_one("div.view_cont")
            or soup.select_one("td.cont")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
