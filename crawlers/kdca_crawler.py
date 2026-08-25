"""
질병관리청 공지사항 크롤러
공지 URL: https://www.kdca.go.kr/kdca/2769/subview.do
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.kdca.go.kr/kdca/2769/subview.do"
BASE_URL = "https://www.kdca.go.kr"


class KdcaCrawler(BaseCrawler):
    site_key = "kdca"
    site_name = "질병관리청"

    def fetch_notice_list(self) -> list[NoticeItem]:
        resp = self.get(LIST_URL)
        soup = self.soup(resp.text)
        items = []

        for row in soup.select("table tbody tr"):
            title_tag = row.select_one("td.td-title a")
            if not title_tag:
                continue

            title = self.clean_text(title_tag.get_text())
            if not title:
                continue

            # href 또는 onclick에서 jf_viewArtcl 파라미터 추출
            src = title_tag.get("href", "") + " " + title_tag.get("onclick", "")
            m = re.search(r"jf_viewArtcl\(['\"](\w+)['\"],\s*['\"](\d+)['\"],\s*['\"](\d+)['\"]", src)
            if m:
                board_code, board_id, article_id = m.group(1), m.group(2), m.group(3)
                notice_id = article_id
                url = f"{BASE_URL}/bbs/{board_code}/{board_id}/{article_id}/artclView.do"
            else:
                href = title_tag.get("href", "")
                notice_id = re.sub(r"[^0-9]", "", href)[-10:] or title[:20]
                url = href if href.startswith("http") else f"{BASE_URL}{href}"

            date_tag = row.select_one("td.td-date")
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
            soup.select_one("div.viewCont")
            or soup.select_one("div.board-view-cont")
            or soup.select_one("div.artcl-view")
            or soup.select_one("div.view_cont")
            or soup.select_one("div#artclContent")
        )
        return self.clean_text(content_div.get_text()) if content_div else ""
