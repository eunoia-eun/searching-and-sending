"""
한국건강관리협회 공지사항 크롤러
공지 URL: https://www.kahp.or.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1001
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.kahp.or.kr/user/bbs/BD_selectBbsList.do"
LIST_PARAMS = {"q_bbsCode": "1001"}
DETAIL_BASE = "https://www.kahp.or.kr/user/bbs/BD_selectBbs.do"


class KahpCrawler(BaseCrawler):
    site_key = "kahp"
    site_name = "한국건강관리협회"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL, params=LIST_PARAMS)
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("table tbody tr"):
            # 실제 HTML: td.alignL.txtOver 안에 a 태그
            title_tag = row.select_one("td.txtOver a, td.alignL a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            if not title or len(title) < 3:
                continue

            href = title_tag.get("href", "")
            # href 예: "BD_selectBbs.do?q_bbsCode=1001&q_bbscttSn=20260507154649508"
            sn = re.search(r"q_bbscttSn=(\w+)", href)
            if sn:
                notice_id = sn.group(1)
                url = f"{DETAIL_BASE}?q_bbsCode=1001&q_bbscttSn={notice_id}"
            else:
                notice_id = re.sub(r"[^0-9]", "", href)[-16:] or title[:20]
                url = f"https://www.kahp.or.kr/user/bbs/{href}"

            cols = row.select("td")
            posted_at = None
            for col in reversed(cols):
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
            soup.select_one("div.board_content div.txt")
            or soup.select_one("div.view_con")
            or soup.select_one("div.board_view")
            or soup.select_one("div.bbs_view")
            or soup.select_one("td.cont")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
