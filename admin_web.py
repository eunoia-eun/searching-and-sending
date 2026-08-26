"""
관리자 웹 페이지 — 크롤링 대상 사이트 / 관심 키워드 관리

로컬 실행: run_admin.bat 더블클릭 (또는 python admin_web.py)
           브라우저에서 http://127.0.0.1:5050 자동으로 열림
클라우드 배포: CLOUD_SYNC=true 등 환경변수가 설정된 상태로 실행되면
              0.0.0.0에 바인딩하고(PORT 환경변수 사용) waitress로 서빙,
              설정은 git_sync를 통해 GitHub 저장소와 동기화됨
"""
import os
import secrets
import threading
import webbrowser

from flask import Flask, abort, redirect, request, send_file, session, url_for
from markupsafe import escape

import json

import config
import git_sync
import schedule_store
import settings_store
from db import database

app = Flask(__name__)
# SECRET_KEY를 환경변수로 고정하면 배포 환경이 재시작돼도 로그인 세션이 유지됨.
# 없으면(로컬 실행) 매번 새로 생성 — 로컬은 재시작이 잦지 않아 무방.
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

IS_CLOUD = os.getenv("CLOUD_SYNC", "").lower() == "true"
HOST = "0.0.0.0" if IS_CLOUD else "127.0.0.1"
PORT = int(os.getenv("PORT", "5050"))

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>관리자 로그인</title>
<style>
  body {{ font-family: "Malgun Gothic", "맑은 고딕", Arial, sans-serif;
         background: #f0f2f5; margin: 0; padding: 24px;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
  .card {{ background: white; border-radius: 10px; padding: 32px 28px; width: 280px;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  h1 {{ font-size: 17px; color: #1a237e; margin: 0 0 18px; text-align: center; }}
  input {{ width: 100%; box-sizing: border-box; padding: 10px 12px; margin-bottom: 10px;
           border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }}
  button {{ width: 100%; padding: 10px; border: none; border-radius: 6px;
            background: #1565c0; color: white; font-weight: 600; font-size: 13px; cursor: pointer; }}
  .error {{ color: #c0392b; font-size: 12px; margin: -4px 0 10px; }}
</style>
</head>
<body>
  <form class="card" method="post" action="/login">
    <h1>관리자 로그인</h1>
    {error_html}
    <input type="text" name="username" placeholder="아이디" autofocus required>
    <input type="password" name="password" placeholder="비밀번호" required>
    <button type="submit">로그인</button>
  </form>
</body>
</html>"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>건강검진 공지 크롤러 관리</title>
<style>
  body {{ font-family: "Malgun Gothic", "맑은 고딕", Arial, sans-serif;
         background: #f0f2f5; margin: 0; padding: 24px; color: #222; }}
  .wrap {{ max-width: 640px; margin: 0 auto; }}
  h1 {{ font-size: 20px; color: #1a237e; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; color: #333; margin: 28px 0 10px; }}
  .card {{ background: white; border-radius: 10px; padding: 18px 20px;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 16px; }}
  button {{ border: none; border-radius: 6px; padding: 6px 14px; font-size: 12px;
            cursor: pointer; font-weight: 600; }}
  .kw-tag {{ display: inline-flex; align-items: center; gap: 6px;
             background: #e3f2fd; color: #1565c0; border-radius: 14px;
             padding: 5px 8px 5px 12px; font-size: 13px; margin: 4px 6px 4px 0; }}
  .kw-tag button {{ background: #1565c0; color: white; border-radius: 50%;
                     width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 12px; }}
  .kw-tag-exclude {{ background: #fdecea; color: #c62828; }}
  .kw-tag-exclude button {{ background: #c62828; }}
  form.inline {{ display: inline; }}
  .add-form {{ margin-top: 12px; display: flex; gap: 8px; }}
  .add-form input[type=text] {{ flex: 1; padding: 8px 10px; border: 1px solid #ddd;
                                 border-radius: 6px; font-size: 13px; }}
  .add-form button {{ background: #1565c0; color: white; padding: 8px 16px; }}
  .hint {{ color: #999; font-size: 12px; margin-top: 10px; }}
  .empty {{ color: #999; font-size: 13px; }}

  /* 사이트 카드 */
  .site-card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px;
                margin-bottom: 12px; background: #fff; }}
  .site-card:last-child {{ margin-bottom: 0; }}
  .site-card.is-off {{ background: #fafafa; }}
  .site-head {{ display: flex; align-items: center; justify-content: space-between; }}
  .site-name {{ font-size: 15px; font-weight: 700; color: #1a1a1a; }}
  .site-card.is-off .site-name {{ color: #aaa; }}
  .site-key {{ color: #aaa; font-size: 11px; font-weight: 400; margin-left: 6px; }}

  /* 토글 스위치 (체크박스 없이 버튼 하나로 켜짐/꺼짐 폼을 제출) */
  .toggle {{ position: relative; width: 42px; height: 24px; border-radius: 12px;
             padding: 0; flex-shrink: 0; }}
  .toggle::after {{ content: ""; position: absolute; top: 2px; width: 20px; height: 20px;
                     border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.25);
                     transition: left .15s ease; }}
  .toggle-on {{ background: #2e7d32; }}
  .toggle-on::after {{ left: 20px; }}
  .toggle-off {{ background: #ccc; }}
  .toggle-off::after {{ left: 2px; }}

  /* 키워드 서브 영역 — 사이트명과 명확히 구분되도록 배경/들여쓰기 */
  .kw-box {{ margin-top: 12px; padding: 10px 12px; background: #f7f8fa;
             border-radius: 8px; }}
  .kw-box + .kw-box {{ margin-top: 8px; }}
  .kw-label {{ font-size: 11px; font-weight: 700; color: #9199a3; letter-spacing: .3px;
               text-transform: uppercase; margin-bottom: 6px; }}
  .kw-label-exclude {{ color: #c62828; }}
  .kw-add-mini {{ margin-top: 6px; display: flex; gap: 6px; }}
  .kw-add-mini input[type=text] {{ flex: 1; padding: 6px 10px; border: 1px solid #ddd;
                                    border-radius: 6px; font-size: 12px; }}
  .kw-add-mini button {{ background: #1565c0; color: white; padding: 6px 12px; }}

  /* 탭 */
  .tabs {{ display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid #e0e0e0; }}
  .tab-btn {{ background: none; border: none; padding: 10px 16px; font-size: 13px;
              font-weight: 600; color: #888; cursor: pointer; border-bottom: 2px solid transparent;
              margin-bottom: -1px; }}
  .tab-btn.active {{ color: #1e3a8a; border-bottom-color: #1e3a8a; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  /* 판단 기준 안내 */
  .guide-row {{ padding: 10px 0; border-bottom: 1px solid #f0f0f0; }}
  .guide-row:last-child {{ border-bottom: none; }}
  .guide-label {{ font-weight: 700; font-size: 13px; }}

  /* 발송 이력 */
  .log-row {{ padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
  .log-row:last-child {{ border-bottom: none; }}
  .log-head {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
  .log-time {{ font-size: 13px; font-weight: 700; color: #1a1a1a; }}
  .log-badge {{ font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 10px; white-space: nowrap; }}
  .log-badge-ok {{ background: #dcfce7; color: #16a34a; }}
  .log-badge-fail {{ background: #fdecea; color: #c62828; }}
  .log-meta {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .log-error {{ font-size: 12px; color: #c62828; margin-top: 4px; }}
  .log-view {{ font-size: 12px; color: #1565c0; font-weight: 600; text-decoration: none; margin-top: 6px; display: inline-block; }}
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:baseline;">
    <h1>건강검진 공지 크롤러 관리</h1>
    <a href="/logout" style="font-size:12px;color:#999;">로그아웃</a>
  </div>
  <p class="hint">여기서 바꾼 설정은 다음 크롤링부터 바로 적용됩니다.</p>

  <div class="tabs">
    <button type="button" class="tab-btn" data-tab="sites" onclick="showTab('sites')">사이트 &amp; 키워드</button>
    <button type="button" class="tab-btn" data-tab="notify" onclick="showTab('notify')">발송 설정</button>
    <button type="button" class="tab-btn" data-tab="guide" onclick="showTab('guide')">판단 기준 안내</button>
    <button type="button" class="tab-btn" data-tab="history" onclick="showTab('history')">발송 이력</button>
  </div>

  <div id="tab-sites" class="tab-panel">
    <h2>크롤링 대상 사이트 &amp; 키워드 필터</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        사이트를 켜고 끄고, 그 아래 제목/본문에 하나라도 포함되면 수집할 키워드를
        사이트별로 관리합니다. 키워드가 하나도 없으면 필터 없이 전체 공지를 수집합니다.
      </p>
      {sites_html}
    </div>
  </div>

  <div id="tab-notify" class="tab-panel">
    <h2>발송 대상 이메일</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        새 공지가 분석되면 이 목록의 이메일로 발송됩니다.
      </p>
      {recipients_html}
      <form class="add-form" method="post" action="/recipient/add">
        <input type="email" name="email" placeholder="example@gmail.com" required>
        <button type="submit">추가</button>
      </form>
    </div>

    <h2>자동 실행 시각</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        매일 이 시각(한국 시간 기준)에 크롤링·분석·발송이 자동 실행됩니다.
        {schedule_note}
      </p>
      <form method="post" action="/schedule/set">
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;">
          <input type="time" name="time" value="{schedule_value}" required
                 style="padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
          <button type="submit" style="background:#1565c0;color:white;padding:8px 16px;">저장</button>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#333;cursor:pointer;">
          <input type="checkbox" name="weekday_only" value="1" {weekday_only_checked}
                 style="width:16px;height:16px;">
          평일에만 실행 (주말·한국 공휴일 제외)
        </label>
      </form>
    </div>

    <h2>메일 하단 문의처</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        분류 기준·키워드 수정 문의를 받을 담당자 정보입니다. 메일 하단에 표시됩니다
        (전부 비워두면 문의처 문구 자체가 표시되지 않습니다).
      </p>
      <form method="post" action="/contact/set">
        <input type="text" name="name" placeholder="담당자 이름" value="{contact_name}"
               style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:8px;
                      border:1px solid #ddd;border-radius:6px;font-size:13px;">
        <input type="text" name="phone" placeholder="연락처 (예: 02-1234-5678)" value="{contact_phone}"
               style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:8px;
                      border:1px solid #ddd;border-radius:6px;font-size:13px;">
        <input type="email" name="email" placeholder="이메일" value="{contact_email}"
               style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:12px;
                      border:1px solid #ddd;border-radius:6px;font-size:13px;">
        <button type="submit" style="background:#1565c0;color:white;padding:8px 16px;">저장</button>
      </form>
    </div>
  </div>

  <div id="tab-guide" class="tab-panel">
    <h2>알림 중요도 판단 기준</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        공지를 수집하면 AI(Claude)가 아래 기준으로 중요도를 판단하고, 발송 여부를 결정합니다.
        이 기준 자체를 바꾸려면 코드(analyzer.py) 수정이 필요해서 여기서 직접 조정은 안 되지만,
        참고하시라고 안내만 표시해드려요.
      </p>
      <div class="guide-row">
        <span class="guide-label" style="color:#dc2626;">■ 긴급 (High)</span>
        <p style="margin:4px 0 0;font-size:13px;color:#374151;">
          법령·고시 개정, 수가 변경, 검진 항목·기준 변경, 시스템 의무 적용 등 즉각 대응이 필요한 경우
        </p>
      </div>
      <div class="guide-row">
        <span class="guide-label" style="color:#d97706;">■ 중요 (Medium)</span>
        <p style="margin:4px 0 0;font-size:13px;color:#374151;">
          지침·안내·유권해석 등 숙지가 필요한 경우
        </p>
      </div>
      <div class="guide-row">
        <span class="guide-label" style="color:#6b7280;">■ 참고 (Low)</span>
        <p style="margin:4px 0 0;font-size:13px;color:#374151;">
          단순 공지, 행사, 모집, 순수 홍보성 내용
        </p>
      </div>
      <div class="guide-row">
        <span class="guide-label" style="color:#1a1a1a;">메일 발송 여부</span>
        <p style="margin:4px 0 0;font-size:13px;color:#374151;">
          긴급·중요 중 실제 현장 대응이 필요하다고 판단되면 발송하고,
          참고이거나 단순 홍보성이면 발송하지 않습니다.
        </p>
      </div>
    </div>
  </div>

  <div id="tab-history" class="tab-panel">
    <h2>발송 이력</h2>
    <div class="card">
      <p class="hint" style="margin-top:0;">
        최근 발송 시도 이력입니다. 성공한 건은 발송 당시 실제 화면을 캡처한 스크린샷을
        볼 수 있습니다.
      </p>
      {email_log_html}
    </div>
  </div>
</div>
<script>
  function showTab(name) {{
    document.querySelectorAll('.tab-panel').forEach(function(el) {{ el.classList.remove('active'); }});
    document.querySelectorAll('.tab-btn').forEach(function(el) {{ el.classList.remove('active'); }});
    document.getElementById('tab-' + name).classList.add('active');
    document.querySelector('.tab-btn[data-tab="' + name + '"]').classList.add('active');
    try {{ localStorage.setItem('admin_tab', name); }} catch (e) {{}}
  }}
  (function() {{
    var saved = 'sites';
    try {{ saved = localStorage.getItem('admin_tab') || 'sites'; }} catch (e) {{}}
    if (!document.getElementById('tab-' + saved)) saved = 'sites';
    showTab(saved);
  }})();
</script>
</body>
</html>"""


def _render():
    enabled = set(settings_store.get_enabled_sites())
    all_keywords = settings_store.get_all_keywords()
    all_excludes = settings_store.get_all_exclude_keywords()

    sites_html = ""
    for key, meta in config.SITES.items():
        name = meta.get("name", key)
        is_on = key in enabled
        card_class = "site-card" if is_on else "site-card is-off"
        toggle_class = "toggle toggle-on" if is_on else "toggle toggle-off"
        toggle_action = "/site/disable" if is_on else "/site/enable"
        toggle_title = "끄기" if is_on else "켜기"

        site_keywords = all_keywords.get(key, [])
        tags_html = "".join(f"""
              <span class="kw-tag">{escape(kw)}
                <form class="inline" method="post" action="/keyword/remove">
                  <input type="hidden" name="site" value="{key}">
                  <input type="hidden" name="keyword" value="{escape(kw)}">
                  <button type="submit" title="삭제">&times;</button>
                </form>
              </span>""" for kw in site_keywords)
        if not tags_html:
            tags_html = '<p class="empty" style="margin:0;">필터 없음 (전체 수집)</p>'

        site_excludes = all_excludes.get(key, [])
        exclude_tags_html = "".join(f"""
              <span class="kw-tag kw-tag-exclude">{escape(kw)}
                <form class="inline" method="post" action="/exclude/remove">
                  <input type="hidden" name="site" value="{key}">
                  <input type="hidden" name="keyword" value="{escape(kw)}">
                  <button type="submit" title="삭제">&times;</button>
                </form>
              </span>""" for kw in site_excludes)
        if not exclude_tags_html:
            exclude_tags_html = '<p class="empty" style="margin:0;">없음</p>'

        sites_html += f"""
        <div class="{card_class}">
          <div class="site-head">
            <span class="site-name">{escape(name)}<span class="site-key">{escape(key)}</span></span>
            <form class="inline" method="post" action="{toggle_action}">
              <input type="hidden" name="site" value="{key}">
              <button type="submit" class="{toggle_class}" title="{toggle_title}" aria-label="{toggle_title}"></button>
            </form>
          </div>
          <div class="kw-box">
            <div class="kw-label">관심 키워드 (하나라도 포함되면 수집)</div>
            <div>{tags_html}</div>
            <form class="kw-add-mini" method="post" action="/keyword/add">
              <input type="hidden" name="site" value="{key}">
              <input type="text" name="keyword" placeholder="키워드 추가" required>
              <button type="submit">추가</button>
            </form>
          </div>
          <div class="kw-box">
            <div class="kw-label kw-label-exclude">제외 키워드 (하나라도 포함되면 무조건 제외)</div>
            <div>{exclude_tags_html}</div>
            <form class="kw-add-mini" method="post" action="/exclude/add">
              <input type="hidden" name="site" value="{key}">
              <input type="text" name="keyword" placeholder="제외 키워드 추가" required>
              <button type="submit">추가</button>
            </form>
          </div>
        </div>"""

    recipients = settings_store.get_recipients()
    if recipients:
        recipients_html = ""
        for email in recipients:
            recipients_html += f"""
            <span class="kw-tag">{escape(email)}
              <form class="inline" method="post" action="/recipient/remove">
                <input type="hidden" name="email" value="{escape(email)}">
                <button type="submit" title="삭제">&times;</button>
              </form>
            </span>"""
    else:
        recipients_html = '<p class="empty">등록된 발송 대상 이메일 없음</p>'

    hour, minute = settings_store.get_schedule()
    schedule_value = f"{hour:02d}:{minute:02d}"
    schedule_note = (
        "" if git_sync.ENABLED else
        "(로컬 실행 중이라 이 변경은 GitHub에 자동 반영되지 않습니다 — 클라우드에 배포된 페이지에서 바꿔주세요)"
    )
    weekday_only_checked = "checked" if settings_store.get_weekday_only() else ""
    contact = settings_store.get_contact()

    return PAGE_TEMPLATE.format(
        sites_html=sites_html,
        recipients_html=recipients_html,
        schedule_value=schedule_value,
        schedule_note=schedule_note,
        weekday_only_checked=weekday_only_checked,
        contact_name=escape(contact["name"]),
        contact_phone=escape(contact["phone"]),
        contact_email=escape(contact["email"]),
        email_log_html=_render_email_log(),
    )


def _render_email_log() -> str:
    entries = database.get_email_log(limit=50)
    if not entries:
        return '<p class="empty">발송 이력이 없습니다.</p>'

    rows = ""
    for e in entries:
        ok = bool(e["success"])
        badge_html = (
            '<span class="log-badge log-badge-ok">성공</span>' if ok
            else '<span class="log-badge log-badge-fail">실패</span>'
        )
        try:
            recipients = json.loads(e["recipients"])
        except (TypeError, ValueError):
            recipients = []
        try:
            breakdown = json.loads(e["site_breakdown"] or "{}")
        except (TypeError, ValueError):
            breakdown = {}
        breakdown_text = ", ".join(
            f"{config.SITES.get(k, {}).get('name', k)} {v}건" for k, v in breakdown.items()
        )

        view_html = ""
        if ok and e.get("screenshot_path"):
            view_html = (
                f'<a class="log-view" href="/email_log/{e["id"]}/screenshot" target="_blank">'
                f'스크린샷 보기 &rarr;</a>'
            )
        error_html = f'<p class="log-error">{escape(e["error"])}</p>' if e.get("error") else ""

        rows += f"""
        <div class="log-row">
          <div class="log-head">
            <span class="log-time">{escape(e["sent_at"])}</span>
            {badge_html}
          </div>
          <p class="log-meta" style="margin:4px 0 0;">{escape(e["subject"] or "(제목 없음)")}</p>
          <p class="log-meta">수신: {escape(", ".join(recipients)) or "-"}</p>
          <p class="log-meta">{e["notice_count"]}건{" — " + escape(breakdown_text) if breakdown_text else ""}</p>
          {error_html}
          {view_html}
        </div>"""

    return rows


@app.before_request
def require_login():
    if request.endpoint in ("login", "static"):
        return None
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return LOGIN_TEMPLATE.format(error_html="")

    if not config.ADMIN_USERNAME or not config.ADMIN_PASSWORD:
        error = "관리자 계정이 설정되지 않았습니다. .env의 ADMIN_USERNAME / ADMIN_PASSWORD를 확인하세요."
        return LOGIN_TEMPLATE.format(error_html=f'<p class="error">{escape(error)}</p>')

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    valid = secrets.compare_digest(username, config.ADMIN_USERNAME) and \
        secrets.compare_digest(password, config.ADMIN_PASSWORD)

    if valid:
        session["logged_in"] = True
        return redirect("/")

    return LOGIN_TEMPLATE.format(
        error_html='<p class="error">아이디 또는 비밀번호가 올바르지 않습니다.</p>'
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return _render()


@app.route("/site/enable", methods=["POST"])
def site_enable():
    key = request.form.get("site", "")
    if key in config.SITES:
        settings_store.enable_site(key)
    return redirect("/")


@app.route("/site/disable", methods=["POST"])
def site_disable():
    key = request.form.get("site", "")
    if key in config.SITES:
        settings_store.disable_site(key)
    return redirect("/")


@app.route("/keyword/add", methods=["POST"])
def keyword_add():
    site = request.form.get("site", "")
    keyword = request.form.get("keyword", "")
    if site in config.SITES:
        settings_store.add_keyword(site, keyword)
    return redirect("/")


@app.route("/keyword/remove", methods=["POST"])
def keyword_remove():
    site = request.form.get("site", "")
    keyword = request.form.get("keyword", "")
    if site in config.SITES:
        settings_store.remove_keyword(site, keyword)
    return redirect("/")


@app.route("/exclude/add", methods=["POST"])
def exclude_add():
    site = request.form.get("site", "")
    keyword = request.form.get("keyword", "")
    if site in config.SITES:
        settings_store.add_exclude_keyword(site, keyword)
    return redirect("/")


@app.route("/exclude/remove", methods=["POST"])
def exclude_remove():
    site = request.form.get("site", "")
    keyword = request.form.get("keyword", "")
    if site in config.SITES:
        settings_store.remove_exclude_keyword(site, keyword)
    return redirect("/")


@app.route("/schedule/set", methods=["POST"])
def schedule_set():
    time_str = request.form.get("time", "")
    weekday_only = request.form.get("weekday_only") == "1"
    try:
        hour_str, minute_str = time_str.split(":")
        hour, minute = int(hour_str), int(minute_str)
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        return redirect("/")

    settings_store.set_schedule(hour, minute)
    settings_store.set_weekday_only(weekday_only)
    schedule_store.apply(hour, minute, weekday_only)
    return redirect("/")


@app.route("/email_log/<int:entry_id>/screenshot")
def email_log_screenshot(entry_id):
    entry = database.get_email_log_entry(entry_id)
    if not entry or not entry.get("screenshot_path"):
        abort(404)

    path = git_sync.resolve_repo_path(entry["screenshot_path"])
    if not os.path.exists(path):
        return "<p>스크린샷 파일을 찾을 수 없습니다.</p>", 404
    return send_file(path, mimetype="image/png")


@app.route("/contact/set", methods=["POST"])
def contact_set():
    name = request.form.get("name", "")
    phone = request.form.get("phone", "")
    email = request.form.get("email", "")
    settings_store.set_contact(name, phone, email)
    return redirect("/")


@app.route("/recipient/add", methods=["POST"])
def recipient_add():
    email = request.form.get("email", "")
    settings_store.add_recipient(email)
    return redirect("/")


@app.route("/recipient/remove", methods=["POST"])
def recipient_remove():
    email = request.form.get("email", "")
    settings_store.remove_recipient(email)
    return redirect("/")


if __name__ == "__main__":
    if IS_CLOUD:
        from waitress import serve
        print(f"관리자 페이지(클라우드 모드) — 0.0.0.0:{PORT}")
        serve(app, host=HOST, port=PORT)
    else:
        url = f"http://127.0.0.1:{PORT}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        print(f"관리자 페이지: {url}  (이 창을 닫으면 서버가 종료됩니다)")
        app.run(host=HOST, port=PORT, debug=False)
