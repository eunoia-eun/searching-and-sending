import os
from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = os.getenv("DB_PATH", "./data/notices.db").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "").strip()
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "").strip()
EMAIL_RECIPIENTS = [e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()]
CRAWL_INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", "60"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

# 관리자 웹 페이지(admin_web.py) 로그인 계정
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

# 요청 공통 헤더
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

REQUEST_TIMEOUT = 20  # seconds (GitHub Actions 서버 -> 국내 사이트 왕복이 로컬보다 느릴 수 있어 여유를 둠)
REQUEST_DELAY = 1.5   # seconds between requests (예의 있는 크롤링)
MAX_RETRIES = 3          # 연결 오류/타임아웃/서버 5xx 발생 시 최대 재시도 횟수
RETRY_BACKOFF_BASE = 3   # seconds, 재시도 간격은 3초 -> 6초 -> 12초로 증가

# .go.kr 사이트 우회용 AWS Lambda 릴레이 (2026-08-27 추가)
# GitHub Actions(Azure) IP는 moel/kdca/law/mpm 등 중앙정부 .go.kr 사이트에서
# 접속 자체가 매번 타임아웃남 (해외/클라우드 IP 차단으로 추정, .or.kr 사이트는 정상).
# 서울 리전 Lambda는 정상 접속되는 것을 확인해서, 이 사이트들만 Lambda를 경유해 가져온다.
LAMBDA_RELAY_URL = os.getenv("LAMBDA_RELAY_URL", "").strip()
LAMBDA_RELAY_SECRET = os.getenv("LAMBDA_RELAY_SECRET", "").strip()
LAMBDA_RELAY_SITES = {"moel", "kdca", "law", "mpm"}

# 대상 사이트 메타 정보
SITES = {
    "nhis": {
        "name": "국민건강보험공단 (공지사항)",
        "base_url": "https://www.nhis.or.kr",
        "crawler": "NhisCrawler",
    },
    "nhis_rule": {
        "name": "국민건강보험공단 (규정 제개정예고)",
        "base_url": "https://www.nhis.or.kr",
        "crawler": "NhisRuleCrawler",
    },
    "moel": {
        "name": "고용노동부",
        "base_url": "https://www.moel.go.kr",
        "crawler": "MoelCrawler",
    },
    "hira": {
        "name": "건강보험심사평가원",
        "base_url": "https://www.hira.or.kr",
        "crawler": "HiraCrawler",
    },
    "kdca": {
        "name": "질병관리청",
        "base_url": "https://www.kdca.go.kr",
        "crawler": "KdcaCrawler",
    },
    "law": {
        "name": "국가법령정보센터",
        "base_url": "https://www.law.go.kr",
        "crawler": "LawCrawler",
    },
    "khhi": {
        "name": "한국건강검진기관협의회",
        "base_url": "https://www.takehealth.or.kr",
        "crawler": "KhhiCrawler",
    },
    "kahp": {
        "name": "한국건강관리협회",
        "base_url": "https://www.kahp.or.kr",
        "crawler": "KahpCrawler",
    },
    "kiha": {
        "name": "대한산업보건협회",
        "base_url": "https://kiha21.or.kr",
        "crawler": "KihaCrawler",
    },
    "mpm": {
        "name": "인사혁신처",
        "base_url": "https://www.mpm.go.kr",
        "crawler": "MpmCrawler",
    },
}
