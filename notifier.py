"""
이메일 발송 모듈
분석된 공지 중 is_notification_needed=True이고 아직 발송 안 된 항목을 HTML 이메일로 발송
"""
import json
import logging
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid
from html import escape

import config
import screenshot
import settings_store
from db import database

logger = logging.getLogger(__name__)

# 중요도별 색상/라벨 (카드 안에서 작은 텍스트 배지로만 사용 — 임원 보고용이라 색은 절제)
_IMPORTANCE_META = {
    "High":   {"color": "#dc2626", "label": "긴급"},
    "Medium": {"color": "#d97706", "label": "중요"},
    "Low":    {"color": "#6b7280", "label": "참고"},
}
_IMPORTANCE_RANK = {"High": 0, "Medium": 1, "Low": 2}  # 숫자가 작을수록 중요 — 사이트 요약 미리보기 선정용


def _parse_points(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return [raw] if raw else []


def _build_card(n: dict, show_key_change: bool = True) -> str:
    meta = _IMPORTANCE_META.get(n.get("importance"), _IMPORTANCE_META["Medium"])
    points = _parse_points(n.get("summary_points"))
    # summary_points[0]은 항상 "무엇이 바뀌었나", 나머지(적용대상/시행시기 등)는 한 줄로 압축
    meta_bits = [escape(str(p)) for p in points[1:]]
    posted_at = n.get("posted_at")
    # law는 posted_at이 실제 게시일이 아니라 시행일자라서 summary_points의 "언제부터"와
    # 같은 날짜를 또 보여주게 됨 — law만 이 태그를 생략한다.
    if posted_at and n.get("site_key") != "law":
        meta_bits.append(f"게시일 {escape(str(posted_at))}")
    meta_line = " · ".join(meta_bits)

    # 이 항목이 상단 "한눈에 보기" 표의 미리보기 문장으로 이미 노출된 경우,
    # 펼쳤을 때 같은 문장이 굵은 글씨로 또 나오는 걸 막기 위해 생략한다.
    key_change_html = ""
    if show_key_change and points:
        key_change_html = f"""
          <div style="border-left:3px solid #1e3a8a;padding:1px 0 1px 10px;margin:0 0 6px;">
            <p style="margin:0;font-size:14.5px;color:#111827;font-weight:700;line-height:1.5;">
              {escape(str(points[0]))}
            </p>
          </div>"""

    action = (n.get("action_required") or "").strip()
    action_html = ""
    if action and action != "해당 없음":
        action_html = f"""
          <p style="margin:8px 0 0;font-size:12.5px;color:#111827;line-height:1.6;">
            <span style="font-weight:700;">▸ 조치 필요</span> {escape(action)}
          </p>"""

    category = escape(n.get("category") or "")
    title = escape(n.get("title") or "")
    url = escape(n.get("url") or "#", quote=True)

    extra_url = n.get("extra_url")
    compare_link_html = ""
    if extra_url:
        compare_link_html = f"""
             <a href="{escape(extra_url, quote=True)}" style="display:inline-block;margin-top:8px;
                margin-left:14px;font-size:12px;color:#6b21a8;font-weight:600;
                text-decoration:none;">신구법비교 &rarr;</a>"""

    return f"""
        <div style="padding:14px 0;border-bottom:1px solid #f0f0f0;">
          <div style="margin-bottom:5px;">
            <span style="font-size:11px;font-weight:700;color:{meta['color']};margin-right:8px;">
              ■ {meta['label']}
            </span>
            <span style="font-size:11px;color:#9ca3af;">{category}</span>
          </div>
          <p style="margin:0 0 6px;font-size:13.5px;color:#4b5563;line-height:1.5;">
            {title}
          </p>
          {key_change_html}
          <p style="margin:0;font-size:11.5px;color:#9ca3af;">
            {meta_line}
          </p>
          {action_html}
          <a href="{url}" style="display:inline-block;margin-top:8px;font-size:12px;
             color:#1e3a8a;font-weight:600;text-decoration:none;">원문 보기 &rarr;</a>{compare_link_html}
        </div>"""


def _build_html(notices: list[dict]) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")

    by_site: dict[str, list[dict]] = {}
    for n in notices:
        by_site.setdefault(n["site_key"], []).append(n)

    # 현재 모니터링 중인 사이트 순서를 기준으로 하되, 비활성화됐지만 이번 발송에 낀 사이트도 뒤에 포함
    site_order = settings_store.get_enabled_sites()
    ordered_sites = site_order + [k for k in by_site if k not in site_order]
    overview_rows = ""
    for site_key in ordered_sites:
        site_name = escape(config.SITES.get(site_key, {}).get("name", site_key))
        items = by_site.get(site_key, [])
        count = len(items)
        if items:
            top = min(items, key=lambda n: _IMPORTANCE_RANK.get(n.get("importance"), 1))
            top_points = _parse_points(top.get("summary_points"))
            preview = str(top_points[0]) if top_points else (top.get("title") or "")
            if len(preview) > 42:
                preview = preview[:42] + "…"
            extra = f" 외 {count - 1}건" if count > 1 else ""
            overview_rows += f"""
            <tr>
              <td style="padding:9px 0;border-bottom:1px solid #f0f0f0;">
                <div style="display:flex;align-items:baseline;justify-content:space-between;">
                  <span style="font-size:15px;font-weight:800;color:#1e3a8a;">{site_name}</span>
                  <span style="background:#dcfce7;color:#16a34a;font-weight:700;font-size:11px;
                        padding:2px 9px;border-radius:10px;white-space:nowrap;">{count}건</span>
                </div>
                <div style="font-size:12px;color:#4b5563;margin-top:3px;">
                  {escape(preview)}{extra}
                </div>
              </td>
            </tr>"""
        else:
            overview_rows += f"""
            <tr>
              <td style="padding:9px 0;border-bottom:1px solid #f0f0f0;">
                <div style="display:flex;align-items:baseline;justify-content:space-between;">
                  <span style="font-size:15px;font-weight:800;color:#c3c9d3;">{site_name}</span>
                  <span style="color:#d1d5db;font-size:11px;">업데이트 없음</span>
                </div>
              </td>
            </tr>"""

    sections = ""
    for site_key in ordered_sites:
        items = by_site.get(site_key)
        if not items:
            continue
        site_name = escape(config.SITES.get(site_key, {}).get("name", site_key))
        # 상단 개요표의 미리보기 문장으로 이미 노출된 항목(중요도 최상위 1건)은
        # 카드에서 핵심 변경 문구를 다시 강조하지 않는다 (완전한 중복이라 반응이 안 좋았음)
        top = min(items, key=lambda n: _IMPORTANCE_RANK.get(n.get("importance"), 1))
        cards = "".join(_build_card(n, show_key_change=(n is not top)) for n in items)
        sections += f"""
        <details style="margin:22px 0 0;">
          <summary style="background:#1e3a8a;color:#ffffff;font-size:15px;font-weight:800;
                      padding:9px 14px;border-radius:6px;margin-bottom:4px;cursor:pointer;">
            {site_name}
            <span style="font-weight:400;font-size:11.5px;color:#c7d2fe;">(클릭하여 펼치기/접기)</span>
          </summary>
          {cards}
        </details>"""

    contact = settings_store.get_contact()
    contact_bits = [escape(v) for v in (contact["name"], contact["phone"], contact["email"]) if v]
    contact_html = ""
    if contact_bits:
        contact_html = f"""
      <p style="margin:0 0 12px;color:#6b7280;font-size:11px;line-height:1.6;text-align:center;">
        분류 기준·키워드 수정 등 문의사항은 담당자에게 연락해 주세요 — {" · ".join(contact_bits)}
      </p>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic','맑은 고딕',Arial,sans-serif;
             background:#eef1f5;margin:0;padding:20px;">
  <div style="max-width:640px;margin:0 auto;">
    <div style="background:#1e3a8a;border-radius:12px 12px 0 0;padding:22px 28px;">
      <h1 style="margin:0 0 4px;color:#ffffff;font-size:18px;font-weight:700;">
        [건강의학부] 건강검진 업데이트 사항
      </h1>
      <div style="display:flex;align-items:baseline;justify-content:space-between;">
        <span style="color:#c7d2fe;font-size:12px;">모니터링 {len(ordered_sites)}개 기관 중</span>
        <span style="color:#c7d2fe;font-size:12px;">{date_str} · 예방건진센터</span>
      </div>
    </div>
    <div style="background:#ffffff;padding:18px 24px 6px;border-left:1px solid #e5e7eb;
                border-right:1px solid #e5e7eb;">
      <table style="width:100%;border-collapse:collapse;">
        {overview_rows}
      </table>
    </div>
    <div style="background:#ffffff;padding:0 24px 8px;border-left:1px solid #e5e7eb;
                border-right:1px solid #e5e7eb;">
      <p style="margin:18px 0 0;font-size:11px;font-weight:700;color:#9ca3af;
                text-transform:uppercase;letter-spacing:.4px;">세부 내용 (기관명 클릭 시 펼쳐짐)</p>
      {sections}
    </div>
    <div style="background:#ffffff;border-radius:0 0 12px 12px;padding:16px 24px 22px;
                border:1px solid #e5e7eb;border-top:none;">
      <hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 14px;">
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;
                  padding:12px 14px;margin-bottom:12px;">
        <p style="margin:0;color:#6b7280;font-size:11px;line-height:1.6;">
          ⚠️ <strong>안내:</strong> 본 메일은 AI를 통한 자동 검색·분석 결과를 참고용으로
          제공하는 것으로, 정보의 누락·오류 또는 최신성 문제가 있을 수 있습니다.
          실제 정책 적용, 법령 해석, 업무 처리 등 중요한 의사결정 시에는 반드시 원문 공지사항 및
          관계 기관을 통해 정확한 내용을 직접 확인하시기 바랍니다.
        </p>
      </div>
      {contact_html}
      <p style="color:#9ca3af;font-size:11px;text-align:center;margin:0;">
        본 메일은 자동 발송되었습니다.
      </p>
    </div>
  </div>
</body>
</html>"""


def _site_breakdown(notices: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for n in notices:
        counts[n["site_key"]] = counts.get(n["site_key"], 0) + 1
    return counts


def send_notification(notices: list[dict]) -> bool:
    """
    notices: database.get_unnotified_analyses() 반환값.
    발송 성공 시 각 공지를 mark_notified 처리 후 True 반환.
    성공/실패 여부와 무관하게 email_log에 발송 이력을 남긴다 (관리자 페이지 발송 이력 탭,
    실패 원인 진단용). 성공 시에는 실제 발송 화면을 헤드리스 브라우저로 캡처해 저장해서,
    나중에 관리자 페이지에서 그때 발송된 화면을 그대로 다시 볼 수 있게 한다
    (Gmail IMAP으로 보낸편지함 원본을 직접 조회하는 방식은 배포 환경에서 연결이 불안정해
    이 방식으로 대체함).
    """
    if not notices:
        logger.info("발송할 공지 없음")
        return True

    recipients = settings_store.get_recipients()
    if not config.EMAIL_SENDER or not recipients:
        logger.warning("이메일 설정 누락 — 발송 건너뜀 (EMAIL_SENDER, 발송 대상 이메일 확인)")
        database.log_email(
            sent_at=datetime.now().isoformat(timespec="seconds"),
            recipients=recipients, subject="", message_id=None,
            notice_count=len(notices), site_breakdown=_site_breakdown(notices),
            success=False, error="이메일 설정 누락 (EMAIL_SENDER/발송 대상 없음)",
        )
        return False

    subject = f"[공지] 건강검진 업데이트 - 건강의학부 ({datetime.now().strftime('%Y-%m-%d')})"
    html = _build_html(notices)
    message_id = make_msgid(domain="health-notice.local")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = message_id
    msg.attach(MIMEText(html, "html", "utf-8"))

    success = False
    error_msg = ""
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
        success = True

    except Exception as exc:
        error_msg = str(exc)
        logger.error("이메일 발송 실패: %s", exc)

    screenshot_path = None
    if success:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", message_id)
        candidate_path = f"data/email_screenshots/{safe_id}.png"
        if screenshot.capture(html, candidate_path):
            screenshot_path = candidate_path

    database.log_email(
        sent_at=datetime.now().isoformat(timespec="seconds"),
        recipients=recipients,
        subject=subject,
        message_id=message_id,
        notice_count=len(notices),
        site_breakdown=_site_breakdown(notices),
        success=success,
        error=error_msg,
        screenshot_path=screenshot_path,
    )

    return success
