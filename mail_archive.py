"""
발송 이력 화면의 "원본 메일 보기" 지원 모듈.
DB에는 발송 메타데이터(email_log)만 남기고, 실제 메일 본문은 저장하지 않는다 —
발송에 쓰는 Gmail 계정의 보낸편지함에 SMTP 발송 시 자동으로 원본이 남기 때문에,
IMAP으로 그 Gmail 계정에 접속해 Message-ID로 원본을 찾아 그대로 보여준다.
"""
import email
import imaplib
import logging
import re
from typing import Optional

import config

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _find_sent_mailbox(imap: imaplib.IMAP4_SSL) -> Optional[str]:
    """보낸편지함 폴더명은 Gmail 계정 언어 설정에 따라 달라지므로(예: "Sent Mail" vs
    한글 "보낸편지함") 이름으로 추측하지 않고 \\Sent 특수 속성으로 찾는다."""
    typ, data = imap.list()
    if typ != "OK":
        return None
    for raw in data:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if "\\Sent" in line:
            m = re.search(r'"([^"]+)"$', line)
            if m:
                return m.group(1)
    return None


def fetch_sent_html(message_id: str) -> Optional[str]:
    """Message-ID로 Gmail 보낸편지함에서 원본 HTML 본문을 가져온다. 못 찾으면 None."""
    if not message_id or not config.EMAIL_SENDER or not config.EMAIL_PASSWORD:
        return None

    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)

            sent_mailbox = _find_sent_mailbox(imap)
            if not sent_mailbox:
                logger.error("보낸편지함 폴더를 찾지 못함")
                return None
            typ, _ = imap.select(f'"{sent_mailbox}"', readonly=True)
            if typ != "OK":
                logger.error("보낸편지함 선택 실패: %s", sent_mailbox)
                return None

            typ, data = imap.search(None, f'(HEADER Message-ID "{message_id}")')
            if typ != "OK" or not data or not data[0]:
                logger.warning("보낸편지함에서 원본을 찾지 못함: %s", message_id)
                return None

            msg_num = data[0].split()[-1]
            typ, msg_data = imap.fetch(msg_num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                return None

            message = email.message_from_bytes(msg_data[0][1])
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    charset = part.get_content_charset() or "utf-8"
                    return part.get_payload(decode=True).decode(charset, errors="replace")

    except Exception as e:
        logger.error("원본 메일 조회 실패 (message_id=%s): %s", message_id, e)
        return None

    return None
