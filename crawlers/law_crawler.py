"""
국가법령정보센터 법령 개정 이력 크롤러
모니터링 대상 법령: 건강검진기본법, 국민건강보험법, 산업안전보건법, 공무원 채용신체검사 규정
API: https://www.law.go.kr/DRF/lawSearch.do (오픈 API)
"""
import logging

from .base_crawler import BaseCrawler, NoticeItem

logger = logging.getLogger(__name__)

# 국가법령정보 오픈 API (별도 인증키 없이 이용 가능한 간이 조회)
BASE_URL = "https://www.law.go.kr"
SEARCH_API = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_API = "https://www.law.go.kr/DRF/lawService.do"
DETAIL_URL = "https://www.law.go.kr/lsInfoP.do"
OLD_AND_NEW_URL = "https://www.law.go.kr/lsInfoP.do"  # 신구조문대비표(신구법비교) — urlMode/viewCls로 진입해야 실제 사이트와 동일한 화면(헤더/메뉴 포함)이 뜸

# 모니터링 대상 법령 (법령명: 법령 일련번호)
TARGET_LAWS = {
    "건강검진기본법": "1001",
    "국민건강보험법": "1532",
    "산업안전보건법": "2040",
    "공무원 채용신체검사 규정": "1002",
}


class LawCrawler(BaseCrawler):
    site_key = "law"
    site_name = "국가법령정보센터"

    def fetch_notice_list(self) -> list[NoticeItem]:
        items = []
        for law_name in TARGET_LAWS:
            try:
                fetched = self._search_law(law_name)
                items.extend(fetched)
            except Exception as e:
                logger.warning("[%s] '%s' 조회 실패: %s", self.site_name, law_name, e)
        return items

    def _search_law(self, law_name: str) -> list[NoticeItem]:
        params = {
            "OC": "open",
            "target": "law",
            "type": "XML",
            "query": law_name,
            "display": "5",
            "page": "1",
            "sort": "efDt",
        }
        resp = self.get(SEARCH_API, params=params)
        resp.encoding = "utf-8"
        soup = self.soup(resp.text, parser="lxml-xml")
        items = []

        for law in soup.find_all("law"):
            law_id = law.find("법령ID")
            mst = law.find("법령일련번호")  # 개정될 때마다 바뀌는 일련번호 (dedup 기준)
            lnm = law.find("법령명한글")
            efd = law.find("시행일자")
            revision = law.find("제개정구분명")
            dept = law.find("소관부처명")
            link = law.find("법령상세링크")
            ancYd = law.find("공포일자")
            ancNo = law.find("공포번호")

            if not law_id or not mst:
                continue

            notice_id = f"{law_id.get_text()}_{mst.get_text()}"
            title_text = lnm.get_text() if lnm else law_name
            efd_text = efd.get_text() if efd else ""
            revision_text = revision.get_text() if revision else ""
            dept_text = dept.get_text() if dept else ""

            # 카테고리 배지("법령·고시 개정")와 메타줄의 시행일이 이미 같은 정보를 보여주므로
            # 제목에는 법령명과 개정구분만 남긴다 (예전엔 [법령개정]/시행일까지 넣어 3중 중복이었음)
            title = f"{title_text} ({revision_text})"
            url = f"{BASE_URL}{link.get_text()}" if link else f"{DETAIL_URL}?lsiSeq={mst.get_text()}"

            # 신구법비교 링크 — 제정(최초 등록)이라 비교 대상이 없는 경우는 제외
            extra_url = None
            if ancYd and ancNo and revision_text != "제정":
                extra_url = (
                    f"{OLD_AND_NEW_URL}?lsiSeq={mst.get_text()}&lsId={law_id.get_text()}"
                    f"&ancYd={ancYd.get_text()}&ancNo={ancNo.get_text()}"
                    f"&urlMode=lsOldAndNew&viewCls=lsOldAndNew"
                )

            items.append(NoticeItem(
                notice_id=notice_id,
                title=title,
                url=url,
                posted_at=efd_text,
                content=f"{title_text} - {revision_text} (소관부처: {dept_text}, 시행일자: {efd_text})",
                extra_url=extra_url,
            ))

        return items

    def fetch_notice_content(self, item: NoticeItem) -> str:
        """
        법령 상세 API에서 '제개정이유'(무엇이 왜 바뀌었는지 공식 요약문)를 가져온다.
        실패 시 목록 조회 때 만든 메타데이터 요약으로 대체.
        """
        mst = item.notice_id.rsplit("_", 1)[-1]
        try:
            resp = self.get(LAW_SERVICE_API, params={
                "OC": "open",
                "target": "law",
                "MST": mst,
                "type": "XML",
            })
            resp.encoding = "utf-8"
            soup = self.soup(resp.text, parser="lxml-xml")
            reason = soup.find("제개정이유내용")
            if reason:
                text = self.clean_text(reason.get_text())
                if text:
                    return text
        except Exception as e:
            logger.warning("[%s] 제개정이유 수집 실패 (MST=%s): %s", self.site_name, mst, e)

        return item.content or ""
