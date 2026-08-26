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


def _build_card(n: dict) -> str:
    meta = _IMPORTANCE_META.get(n.get("importance"), _IMPORTANCE_META["Medium"])
    points = _parse_points(n.get("summary_points"))
    # summary_points[0]은 항상 "무엇이 바뀌었나", 나머지(적용대상/시행시기 등)는 한 줄로 압축
    key_change = escape(str(points[0])) if points else ""
    meta_bits = [escape(str(p)) for p in points[1:]]
    posted_at = n.get("posted_at")
    if posted_at:
        meta_bits.append(f"게시일 {escape(str(posted_at))}")
    meta_line = " · ".join(meta_bits)

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
          <div style="border-left:3px solid #1e3a8a;padding:1px 0 1px 10px;margin:0 0 6px;">
            <p style="margin:0;font-size:14.5px;color:#111827;font-weight:700;line-height:1.5;">
              {key_change}
            </p>
          </div>
          <p style="margin:0;font-size:11.5px;color:#9ca3af;">
            {meta_line}
          </p>
          {action_html}
          <a href="{url}" style="display:inline-block;margin-top:8px;font-size:12px;
             color:#1e3a8a;font-weight:600;text-decoration:none;">원문 보기 &rarr;</a>
        </div>"""


def _build_html(notices: list[dict]) -> str:
    date_str = datetime.now().strftime("%Y년 %m월 %d일")

    by_site: dict[str, list[dict]] = {}
    for n in notices:
        by_site.setdefault(n["site_key"], []).append(n)

    # 현재 모니터링 중인 사이트 순서를 기준으로 하되, 비활성화됐지만 이번 발송에 낀 사이트도 뒤에 포함
    site_order = settings_store.get_enabled_sites()
    ordered_sites = site_order + [k for k in by_site if k not in site_order]
    updated_count = sum(1 for k in ordered_sites if by_site.get(k))

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
        cards = "".join(_build_card(n) for n in items)
        sections += f"""
        <div style="margin:22px 0 0;">
          <div style="background:#1e3a8a;color:#ffffff;font-size:15px;font-weight:800;
                      padding:9px 14px;border-radius:6px;margin-bottom:4px;">
            {site_name}
          </div>
          {cards}
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic','맑은 고딕',Arial,sans-serif;
             background:#eef1f5;margin:0;padding:20px;">
  <div style="max-width:640px;margin:0 auto;">
    <div style="background:#1e3a8a;border-radius:12px 12px 0 0;padding:22px 28px;">
      <h1 style="margin:0 0 4px;color:#ffffff;font-size:18px;font-weight:700;">
        건강검진 공지 모니터링
      </h1>
      <p style="margin:0;color:#c7d2fe;font-size:12px;">
        {date_str} · 모니터링 {len(ordered_sites)}개 기관 중 {updated_count}곳 업데이트
      </p>
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
                text-transform:uppercase;letter-spacing:.4px;">세부 내용</p>
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
