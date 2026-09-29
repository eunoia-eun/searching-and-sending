"""
보건복지부 보도자료 게시판 크롤러
공지 URL: https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027

robots.txt가 이 게시판 경로(mid=a10503010100&bid=0027)를 명시적으로 Allow 해둠.
"""
from .base_crawler import BaseCrawler
from .mohw_common import LIST_URL, parse_content, parse_list

MID = "a10503010100"
BID = "0027"


class MohwPressCrawler(BaseCrawler):
    site_key = "mohw_press"
    site_name = "보건복지부 (보도자료)"

    def fetch_notice_list(self):
        resp = self.get(LIST_URL, params={"mid": MID, "bid": BID})
        soup = self.soup(resp.text)
        return parse_list(soup, MID, BID)

    def fetch_notice_content(self, item):
        resp = self.get(item.url)
        soup = self.soup(resp.text)
        return parse_content(soup)
