"""
대한산업보건협회 공지사항 크롤러

목록은 Kendo Grid가 호출하는 JSON API(brd_list.do)에서 가져오고,
상세 본문은 POST 폼 제출로만 열람 가능한 brd_noti_det_main.do에서 가져온다.
"""
import logging

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

BASE_URL = "https://edu21.kiha21.or.kr"
LIST_PAGE_URL = f"{BASE_URL}/service/brd/page/brd_notice_main.do"
LIST_API_URL = f"{BASE_URL}/service/brd/ajax/select/brd_list.do"
DETAIL_URL = f"{BASE_URL}/service/brd/page/brd_noti_det_main.do"
BOARD_CODE = "1"


class KihaCrawler(BaseCrawler):
    site_key = "kiha"
    site_name = "대한산업보건협회"

    def fetch_notice_list(self) -> list[NoticeItem]:
        # 목록 API는 세션(mid 컨텍스트) 확보를 위해 페이지를 먼저 방문해야 함
        self.get(LIST_PAGE_URL, params={"mid": "350"})

        resp = self.post(LIST_API_URL, data={
            "LKUP_CNDT": "",
            "LKUP_TXT": "",
            "startIndex": 0,
            "pageSize": 20,
            "sortField": "",
            "sortDir": "",
            "BOARD_CODE": BOARD_CODE,
            "BOARD_AREA": "CMNT",
            "USER_AUTH": "USER",
        })
        data = resp.json()
        items = []

        for row in data.get("items", []):
            board_num = row.get("BOARD_NUM")
            title = self.clean_text(row.get("BRD_TTL", ""))
            if not board_num or not title:
                continue

            notice_id = str(board_num)
            url = f"{DETAIL_URL}?mid=350&BOARD_NUM={notice_id}&BOARD_CODE={BOARD_CODE}"
            posted_at = row.get("REG_DTM")

            items.append(NoticeItem(
                notice_id=notice_id,
                title=title,
                url=url,
                posted_at=posted_at,
            ))

        return items

    def fetch_notice_content(self, item: NoticeItem) -> str:
        resp = self.post(DETAIL_URL, params={"mid": "350"}, data={
            "BOARD_NUM": item.notice_id,
            "BOARD_CODE": BOARD_CODE,
        })
        soup = self.soup(resp.text)
        content_div = soup.select_one("div.brd-cont")
        return self.clean_text(content_div.get_text()) if content_div else ""
