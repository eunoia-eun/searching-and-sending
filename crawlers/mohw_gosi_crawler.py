"""
보건복지부 훈령/예규/고시/지침 게시판 크롤러
공지 URL: https://www.mohw.go.kr/board.es?mid=a10409020000&bid=0026

hira/kha 등에서 "보건복지부 고시 제OOOO호"를 인용만 하던 것의 원문이 여기서 나온다.
robots.txt가 이 게시판 경로(mid=a10409020000&bid=0026)를 명시적으로 Allow 해둠.
"""
from .base_crawler import BaseCrawler
from .mohw_common import LIST_URL, parse_content, parse_list

MID = "a10409020000"
BID = "0026"


class MohwGosiCrawler(BaseCrawler):
    site_key = "mohw_gosi"
    site_name = "보건복지부 (고시·훈령·예규)"

    def fetch_notice_list(self):
        resp = self.get(LIST_URL, params={"mid": MID, "bid": BID})
        soup = self.soup(resp.text)
        return parse_list(soup, MID, BID)

    def fetch_notice_content(self, item):
        resp = self.get(item.url)
        soup = self.soup(resp.text)
        return parse_content(soup)
