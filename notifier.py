"""
이메일 발송 모듈
분석된 공지 중 is_notification_needed=True이고 아직 발송 안 된 항목을 HTML 이메일로 발송
"""
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
import settings_store
from db import database

logger = logging.getLogger(__name__)

_IMPORTANCE_COLOR = {"High": "#c0392b", "Medium": "#e67e22", "Low": "#7f8c8d"}
_IMPORTANCE_LABEL = {"High": "긴급", "Medium": "중요", "Low": "참고"}


def _parse_points(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return [raw] if raw else []


def _build_html(notices: list[dict]) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")
    cards = ""
    for n in notices:
        importance = n.get("importance", "Medium")
        color = _IMPORTANCE_COLOR.get(importance, "#7f8c8d")
        label = _IMPORTANCE_LABEL.get(importance, importance)
        site_name = config.SITES.get(n["site_key"], {}).get("name", n["site_key"])
        points = _parse_points(n.get("summary_points"))
        points_html = "".join(
            f'<li style="margin-bottom:4px;">{p}</li>' for p in points
        )
        action = n.get("action_required") or "해당 없음"

        cards += f"""
        <div style="border:1px solid #e0e0e0;border-radius:8px;margin-bottom:18px;overflow:hidden;">
          <div style="background:{color};padding:10px 16px;display:flex;align-items:center;gap:10px;">
            <span style="background:white;color:{color};font-weight:700;font-size:11px;
                  padding:2px 8px;border-radius:10px;white-space:nowrap;">{label}</span>
            <span style="color:white;font-weight:700;font-size:14px;line-height:1.4;">
              {n['title']}
            </span>
          </div>
          <div style="padding:14px 16px;background:white;">
            <p style="margin:0 0 8px;color:#888;font-size:12px;">
              {site_name} &nbsp;|&nbsp; {n.get('category', '')} &nbsp;|&nbsp;
              게시일: {n.get('posted_at') or '-'}
            </p>
            <ul style="margin:0 0 10px;padding-left:18px;font-size:13px;color:#333;">
              {points_html}
            </ul>
            <div style="padding:8px 12px;background:#fffde7;border-left:3px solid #f9a825;
                 font-size:13px;color:#333;margin-bottom:8px;">
              <strong>조치 필요:</strong> {action}
            </div>
            <a href="{n['url']}" style="color:#1565c0;font-size:12px;text-decoration:none;">
              원문 보기 &rarr;
            </a>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Malgun Gothic','맑은 고딕',Arial,sans-serif;
             background:#f0f2f5;margin:0;padding:20px;">
  <div style="max-width:680px;margin:0 auto;background:white;border-radius:12px;
              padding:28px 32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <h2 style="margin:0 0 4px;color:#1a237e;font-size:20px;">건강검진 공지 모니터링</h2>
    <p style="margin:0 0 24px;color:#666;font-size:13px;">
      {date_str} &nbsp;·&nbsp; 신규 {len(notices)}건
    </p>
    {cards}
    <hr style="border:none;border-top:1px solid #eee;margin:20px 0 14px;">
    <p style="color:#bbb;font-size:11px;text-align:center;margin:0;">
      본 메일은 자동 발송되었습니다.
    </p>
  </div>
</body>
</html>"""


def send_notification(notices: list[dict]) -> bool:
    """
    notices: database.get_unnotified_analyses() 반환값.
    발송 성공 시 각 공지를 mark_notified 처리 후 True 반환.
    """
    if not notices:
        logger.info("발송할 공지 없음")
        return True

    recipients = settings_store.get_recipients()
    if not config.EMAIL_SENDER or not recipients:
        logger.warning("이메일 설정 누락 — 발송 건너뜀 (EMAIL_SENDER, 발송 대상 이메일 확인)")
        return False

    subject = (
        f"[건강검진 공지] {datetime.now().strftime('%Y-%m-%d')} "
        f"신규 {len(notices)}건"
    )
    html = _build_html(notices)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT) as smtp:
            smtp.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            smtp.sendmail(
                config.EMAIL_SENDER,
                recipients,
                msg.as_string(),
            )

        for n in notices:
            database.mark_notified(n["analysis_id"])

        logger.info("이메일 발송 완료 — %d건 → %s",
                    len(notices), ", ".join(recipients))
        return True

    except Exception as exc:
        logger.error("이메일 발송 실패: %s", exc)
        return False
