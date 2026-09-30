"""
발송된 이메일 화면을 실제 이미지로 캡처해서 관리자 페이지 "발송 이력"에서 보여주기 위한 모듈.
Gmail IMAP 연동(보낸편지함에서 원본 조회)이 배포 환경에서 불안정해서,
발송 직후 헤드리스 브라우저로 그 순간 렌더링 결과를 캡처해 저장하는 방식으로 대체했다.
"""
import logging
import os

logger = logging.getLogger(__name__)


def capture(html: str, out_path: str) -> bool:
    """html을 헤드리스 브라우저로 렌더링해 out_path에 PNG로 저장. 성공 여부 반환."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright 미설치 — 이메일 스크린샷 캡처 건너뜀")
        return False

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 900})
            page.set_content(html, wait_until="load")
            # <details> 아코디언이 기본 접힘 상태라 그대로 찍으면 세부 내용이 안 보임 —
            # 발송 이력 기록용 스크린샷은 전체 내용을 남겨야 하므로 전부 펼친 뒤 캡처
            page.eval_on_selector_all("details", "els => els.forEach(e => e.open = true)")
            page.screenshot(path=out_path, full_page=True)
            browser.close()
        return True
    except Exception as e:
        logger.error("이메일 스크린샷 캡처 실패: %s", e)
        return False
