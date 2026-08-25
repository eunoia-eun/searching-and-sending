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
from html import escape

import config
import settings_store
from db import database

logger = logging.getLogger(__name__)

# 중요도별 배지 색상/라벨/이모지 (색 하나에만 의존하지 않도록 이모지 병행)
_IMPORTANCE_META = {
    "High":   {"color": "#dc2626", "bg": "#fef2f2", "label": "긴급", "emoji": "🔴"},
    "Medium": {"color": "#d97706", "bg": "#fffbeb", "label": "중요", "emoji": "🟠"},
    "Low":    {"color": "#6b7280", "bg": "#f9fafb", "label": "참고", "emoji": "⚪"},
}
_IMPORTANCE_ORDER = ["High", "Medium", "Low"]


def _parse_points(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return [raw] if raw else []


def _build_card(n: dict) -> str:
    meta = _IMPORTANCE_META.get(n.get("importance"), _IMPORTANCE_META["Medium"])
    site_name = config.SITES.get(n["site_key"], {}).get("name", n["site_key"])
    points = _parse_points(n.get("summary_points"))
    # summary_points[0]은 항상 "무엇이 바뀌었나" — 나머지(적용대상/시행시기)와 분리해서 강조
    key_change = escape(str(points[0])) if points else ""
    rest_points = points[1:]
    points_html = "".join(
        f'<li style="margin-bottom:5px;">{escape(str(p))}</li>' for p in rest_points
    )
    action = escape(n.get("action_required") or "해당 없음")
    category = escape(n.get("category") or "")
    title = escape(n.get("title") or "")
    posted_at = escape(n.get("posted_at") or "-")
    url = escape(n.get("url") or "#", quote=True)

    return f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;
                    margin-bottom:14px;overflow:hidden;">
          <div style="padding:16px 18px;">
            <div style="margin-bottom:10px;">
              <span style="display:inline-block;background:{meta['bg']};color:{meta['color']};
                    font-weight:700;font-size:11px;padding:3px 10px;border-radius:20px;
                    margin-right:6px;white-space:nowrap;">{meta['emoji']} {meta['label']}</span>
              <span style="display:inline-block;background:#f3f4f6;color:#4b5563;
                    font-size:11px;padding:3px 10px;border-radius:20px;white-space:nowrap;">{category}</span>
            </div>
            <h3 style="margin:0 0 8px;font-size:15px;color:#111827;line-height:1.5;font-weight:700;">
              {title}
            </h3>
            <div style="background:#eff6ff;border-left:3px solid #2563eb;border-radius:4px;
                 padding:9px 12px;margin:0 0 10px;font-size:13px;color:#1e3a8a;
                 font-weight:700;line-height:1.5;">
              📌 {key_change}
            </div>
            <p style="margin:0 0 10px;color:#9ca3af;font-size:12px;">
              {escape(site_name)} · 게시일 {posted_at}
            </p>
            <ul style="margin:0 0 12px;padding-left:20px;color:#374151;font-size:13px;line-height:1.7;">
              {points_html}
            </ul>
            <div style="background:#f9fafb;border-radius:8px;padding:10px 12px;margin-bottom:14px;
                 font-size:13px;color:#374151;line-height:1.5;">
              <span style="color:#111827;font-weight:700;">✅ 조치 필요</span><br>{action}
            </div>
            <a href="{url}" style="display:inline-block;background:#1e3a8a;color:#ffffff;
               font-size:12px;font-weight:700;padding:9px 18px;border-radius:6px;
               text-decoration:none;">원문 보기 &rarr;</a>
          </div>
        </div>"""


def _build_html(notices: list[dict]) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")

    groups: dict[str, list[dict]] = {k: [] for k in _IMPORTANCE_ORDER}
    for n in notices:
        importance = n.get("importance")
        groups[importance if importance in groups else "Medium"].append(n)

    sections = ""
    for importance in _IMPORTANCE_ORDER:
        items = groups[importance]
        if not items:
            continue
        meta = _IMPORTANCE_META[importance]
        sections += f"""
        <div style="margin:22px 0 10px;font-size:13px;font-weight:700;color:{meta['color']};">
          {meta['emoji']} {meta['label']} ({len(items)}건)
        </div>"""
        sections += "".join(_build_card(n) for n in items)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic','맑은 고딕',Arial,sans-serif;
             background:#eef1f5;margin:0;padding:20px;">
  <div style="max-width:640px;margin:0 auto;">
    <div style="background:#1e3a8a;border-radius:12px 12px 0 0;padding:22px 28px;">
      <h1 style="margin:0 0 4px;color:#ffffff;font-size:18px;font-weight:700;">
        🏥 건강검진 공지 모니터링
      </h1>
      <p style="margin:0;color:#c7d2fe;font-size:12px;">
        {date_str} · 신규 {len(notices)}건
      </p>
    </div>
    <div style="background:#ffffff;padding:20px 24px 8px;border-left:1px solid #e5e7eb;
                border-right:1px solid #e5e7eb;">
      {sections}
    </div>
    <div style="background:#ffffff;border-radius:0 0 12px 12px;padding:16px 24px 22px;
                border:1px solid #e5e7eb;border-top:none;">
      <hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 14px;">
      <p style="color:#9ca3af;font-size:11px;text-align:center;margin:0;">
        본 메일은 자동 발송되었습니다.
      </p>
    </div>
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

    subject = f"[공지] 건강검진 업데이트 - 건강의학부 ({datetime.now().strftime('%Y-%m-%d')})"
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
