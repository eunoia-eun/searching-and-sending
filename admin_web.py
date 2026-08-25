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

from flask import Flask, redirect, request, session, url_for
from markupsafe import escape

import config
import git_sync
import schedule_store
import settings_store

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
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:baseline;">
    <h1>건강검진 공지 크롤러 관리</h1>
    <a href="/logout" style="font-size:12px;color:#999;">로그아웃</a>
  </div>
  <p class="hint">여기서 바꾼 설정은 다음 크롤링부터 바로 적용됩니다.</p>

  <h2>크롤링 대상 사이트 &amp; 키워드 필터</h2>
  <div class="card">
    <p class="hint" style="margin-top:0;">
      사이트를 켜고 끄고, 그 아래 제목/본문에 하나라도 포함되면 수집할 키워드를
      사이트별로 관리합니다. 키워드가 하나도 없으면 필터 없이 전체 공지를 수집합니다.
    </p>
    {sites_html}
  </div>

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
    <form method="post" action="/schedule/set" style="display:flex;gap:8px;align-items:center;">
      <input type="time" name="time" value="{schedule_value}" required
             style="padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
      <button type="submit" style="background:#1565c0;color:white;padding:8px 16px;">저장</button>
    </form>
  </div>
</div>
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

    return PAGE_TEMPLATE.format(
        sites_html=sites_html,
        recipients_html=recipients_html,
        schedule_value=schedule_value,
        schedule_note=schedule_note,
    )


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
    try:
        hour_str, minute_str = time_str.split(":")
        hour, minute = int(hour_str), int(minute_str)
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        return redirect("/")

    settings_store.set_schedule(hour, minute)
    schedule_store.apply(hour, minute)
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
