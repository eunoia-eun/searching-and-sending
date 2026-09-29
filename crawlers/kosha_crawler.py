"""
한국산업안전보건공단(KOSHA) 공지사항 크롤러

사이트 전체가 Vue SPA라 정적 HTML에는 목록이 없다(<div id="app"></div>만 있음).
실제 데이터는 "표준게시판(STD Tboard)" 공통 API(process.do)를 통해 JSON으로
오가는데, Chrome 개발자도구로 실제 요청을 가로채서 payload 구조를 알아냈다
(2026-09-29). frontAuthKey/auth가 전부 빈 값이어도 200이 오는 것으로 보아
이 게시판(공지사항)은 별도 인증 없이 열려있는 공개 API — session/token 없이도
동작함을 실측 확인.

목록 API는 pstNoGrid(정렬된 pstNo 목록)와 bbsPstGrid(각 pstNo의 상세, 순서
무관)를 같이 반환한다. 화면에 보이는 순서 = pstNoGrid 순서이므로, 반드시
pstNoGrid 순서대로 bbsPstGrid에서 pstNo를 찾아 매칭해야 한다(bbsPstGrid
자체의 배열 순서는 표시 순서와 다름 — 실측으로 확인된 함정).
"""
import logging

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

API_URL = "https://kosha.or.kr/api/compn24/auth/stdtboard/process.do"
DETAIL_PAGE_URL = "https://kosha.or.kr/notification/notice/contruction"
BBS_ID = "B2025021400001"  # 알림소식 > 공지사항 > 공지사항


def _tboard_common(service_id: str) -> dict:
    return {
        "frontInfo": {"viewId": "", "menuId": "", "siteId": ""},
        "frontAuthKey": "",
        "auth": {},
        "securityInfo": {},
        "data": {
            "pagingInfo": None,
            "whereId": None,
            "tboard": {
                "systemCd": "50",
                "channel": "web",
                "bbsId": BBS_ID,
                "bbsGrpId": "",
                "serviceId": service_id,
            },
        },
    }


class KoshaCrawler(BaseCrawler):
    site_key = "kosha"
    site_name = "한국산업안전보건공단"

    def fetch_notice_list(self) -> list[NoticeItem]:
        payload = {
            "common": _tboard_common("basicAccess"),
            "service": {
                "info": {"id": "", "type": ""},
                "data": {
                    "searchDefaultCndGrid": [{
                        "orPstNm": "", "orPstCn": "",
                        "curPageCo": 1, "recodePageCo": 10, "rowsPerPage": 10,
                        "pstSeCd": "1200001", "atcflCntSrchYn": "Y", "artclNoList": [],
                        "pstNoOrder": "Y", "isDesc": "Y", "sortType": "01", "sortOrder": "1",
                        "isAddPstCn": "N",
                    }],
                    "searchArtclCndGrid": [],
                },
            },
        }
        resp = self.post(API_URL, data={"_JSON": self._to_json(payload)})
        result = resp.json().get("response", {})

        by_pst_no = {row["pstNo"]: row for row in result.get("bbsPstGrid", [])}
        items = []
        for order_row in result.get("pstNoGrid", []):
            row = by_pst_no.get(order_row.get("pstNo"))
            if not row:
                continue

            title = self.clean_text(row.get("pstNm", ""))
            pst_no = row.get("pstNo")
            if not title or not pst_no:
                continue

            reg_ymd = row.get("regYmd", "")
            posted_at = f"{reg_ymd[:4]}-{reg_ymd[4:6]}-{reg_ymd[6:8]}" if len(reg_ymd) == 8 else None

            items.append(NoticeItem(
                notice_id=pst_no,
                title=title,
                url=f"{DETAIL_PAGE_URL}?bbsId={BBS_ID}&pstNo={pst_no}",
                posted_at=posted_at,
            ))

        return items

    def fetch_notice_content(self, item: NoticeItem) -> str:
        payload = {
            "common": _tboard_common("basicRead"),
            "service": {
                "info": {"id": "", "type": ""},
                "data": {"pstDefaultGrid": [{"bbsId": BBS_ID, "pstNo": item.notice_id}]},
            },
        }
        resp = self.post(API_URL, data={"_JSON": self._to_json(payload)})
        detail_list = resp.json().get("response", {}).get("bbsDetailInfo", [])
        if not detail_list:
            return ""

        html = detail_list[0].get("pstCn") or ""
        soup = self.soup(html)
        return self.clean_text(soup.get_text())

    @staticmethod
    def _to_json(payload: dict) -> str:
        import json
        return json.dumps(payload, ensure_ascii=False)
