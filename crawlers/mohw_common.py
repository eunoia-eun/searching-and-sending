"""
보건복지부 board.es 게시판 공통 파싱 로직 — 고시/훈령/예규 게시판(mohw_gosi)과
보도자료 게시판(mohw_press)이 같은 게시판 스킨(board.es)을 쓰기 때문에 공유한다.
"""
import re

from .base_crawler import NoticeItem

LIST_URL = "https://www.mohw.go.kr/board.es"


def parse_list(soup, mid: str, bid: str) -> list[NoticeItem]:
    items = []
    for row in soup.select("table tbody tr"):
        title_td = row.select_one("td[data-label='제목']")
        if not title_td:
            continue  # "미리보기" 숨김 행(<tr id="preView...">)은 이 td가 없어서 자동 제외

        a = title_td.select_one("a")
        if not a:
            continue

        href = a.get("href", "")
        m = re.search(r"list_no=(\d+)", href)
        if not m:
            continue
        notice_id = m.group(1)

        # "새글" 아이콘의 <span class="sr_only">새글</span>이 스크린리더용 숨김 텍스트라
        # get_text()에 그대로 섞여 들어오는 것을 제거
        for sr in a.select(".sr_only, .sr-only"):
            sr.decompose()
        title = " ".join(a.get_text().split()).strip()
        if not title:
            continue

        date_td = row.select_one("td[data-label='등록일']")
        posted_at = " ".join(date_td.get_text().split()).strip() if date_td else None

        url = f"{LIST_URL}?mid={mid}&bid={bid}&act=view&list_no={notice_id}"
        items.append(NoticeItem(notice_id=notice_id, title=title, url=url, posted_at=posted_at))

    return items


def parse_content(soup) -> str:
    art = soup.select_one("article.board_view")
    return " ".join(art.get_text().split()).strip() if art else ""
