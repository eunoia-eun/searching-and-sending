"""
관리자 웹 페이지 — 크롤링 대상 사이트 / 관심 키워드 관리
실행: run_admin.bat 더블클릭 (또는 python admin_web.py)
브라우저에서 http://127.0.0.1:5050 자동으로 열림
"""
import secrets
import threading
import webbrowser

from flask import Flask, redirect, request, session, url_for
from markupsafe import escape

import config
import settings_store

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # 서버 재시작 시 기존 로그인 세션은 만료됨

PORT = 5050

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
  .row {{ display: flex; align-items: center; justify-content: space-between;
          padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
  .row:last-child {{ border-bottom: none; }}
  .site-name {{ font-size: 14px; }}
  .site-key {{ color: #999; font-size: 12px; margin-left: 6px; }}
  button {{ border: none; border-radius: 6px; padding: 6px 14px; font-size: 12px;
            cursor: pointer; font-weight: 600; }}
  .btn-on {{ background: #2e7d32; color: white; }}
  .btn-off {{ background: #e0e0e0; color: #666; }}
  .kw-tag {{ display: inline-flex; align-items: center; gap: 6px;
             background: #e3f2fd; color: #1565c0; border-radius: 14px;
             padding: 5px 8px 5px 12px; font-size: 13px; margin: 4px 6px 4px 0; }}
  .kw-tag button {{ background: #1565c0; color: white; border-radius: 50%;
                     width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 12px; }}
  form.inline {{ display: inline; }}
  .add-form {{ margin-top: 12px; display: flex; gap: 8px; }}
  .add-form input[type=text] {{ flex: 1; padding: 8px 10px; border: 1px solid #ddd;
                                 border-radius: 6px; font-size: 13px; }}
  .add-form button {{ background: #1565c0; color: white; padding: 8px 16px; }}
  .hint {{ color: #999; font-size: 12px; margin-top: 10px; }}
  .empty {{ color: #999; font-size: 13px; }}
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:baseline;">
    <h1>건강검진 공지 크롤러 관리</h1>
    <a href="/logout" style="font-size:12px;color:#999;">로그아웃</a>
  </div>
  <p class="hint">여기서 바꾼 설정은 다음 크롤링부터 바로 적용됩니다.</p>

  <h2>크롤링 대상 사이트</h2>
  <div class="card">
    {sites_html}
  </div>

  <h2>관심 키워드 필터</h2>
  <div class="card">
    <p class="hint" style="margin-top:0;">
      제목이나 본문에 아래 키워드가 하나라도 포함된 공지만 수집합니다.
      키워드가 하나도 없으면 필터 없이 전체 공지를 수집합니다.
    </p>
    {keywords_html}
    <form class="add-form" method="post" action="/keyword/add">
      <input type="text" name="keyword" placeholder="예: 검진, 특수건강진단" required>
      <button type="submit">추가</button>
    </form>
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
</div>
</body>
</html>"""


def _render():
    enabled = set(settings_store.get_enabled_sites())
    sites_html = ""
    for key, meta in config.SITES.items():
        name = meta.get("name", key)
        is_on = key in enabled
        btn_class = "btn-on" if is_on else "btn-off"
        btn_label = "켜짐" if is_on else "꺼짐"
        action = "/site/disable" if is_on else "/site/enable"
        sites_html += f"""
        <div class="row">
          <span class="site-name">{escape(name)}<span class="site-key">{escape(key)}</span></span>
          <form class="inline" method="post" action="{action}">
            <input type="hidden" name="site" value="{key}">
            <button type="submit" class="{btn_class}">{btn_label}</button>
          </form>
        </div>"""

    keywords = settings_store.get_keywords()
    if keywords:
        keywords_html = ""
        for kw in keywords:
            keywords_html += f"""
            <span class="kw-tag">{escape(kw)}
              <form class="inline" method="post" action="/keyword/remove">
                <input type="hidden" name="keyword" value="{escape(kw)}">
                <button type="submit" title="삭제">&times;</button>
              </form>
            </span>"""
    else:
        keywords_html = '<p class="empty">등록된 키워드 없음 (전체 공지 수집 중)</p>'

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

    return PAGE_TEMPLATE.format(
        sites_html=sites_html,
        keywords_html=keywords_html,
        recipients_html=recipients_html,
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
    keyword = request.form.get("keyword", "")
    settings_store.add_keyword(keyword)
    return redirect("/")


@app.route("/keyword/remove", methods=["POST"])
def keyword_remove():
    keyword = request.form.get("keyword", "")
    settings_store.remove_keyword(keyword)
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
    url = f"http://127.0.0.1:{PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"관리자 페이지: {url}  (이 창을 닫으면 서버가 종료됩니다)")
    app.run(host="127.0.0.1", port=PORT, debug=False)
