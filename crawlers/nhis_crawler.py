"""
국민건강보험공단 공지사항 크롤러
공지 URL: https://www.nhis.or.kr/nhis/together/wbhaea01000m01.do
(wbhaea02700m01.do는 채용 게시판이라 잘못 지정되어 있던 것을 수정함)
"""
import logging
import re

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

LIST_URL = "https://www.nhis.or.kr/nhis/together/wbhaea01000m01.do"
BASE_URL = "https://www.nhis.or.kr"


class NhisCrawler(BaseCrawler):
    site_key = "nhis"
    site_name = "국민건강보험공단"

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

            # 날짜: 열 순서는 [번호, 제목, 담당부서, 등록일, 첨부, 조회수] - 날짜 패턴으로 탐색
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
