"""
사용자 설정 저장소 — 크롤링 대상 사이트, 관심 키워드 필터, 발송 대상 이메일

admin.py / admin_web.py로 관리하며, main.py/scheduler.py는 별도 --sites 지정이
없으면 여기 저장된 enabled_sites를 사용한다. base_crawler.py는 keywords로
제목/본문을 필터링한다 (키워드가 비어있으면 필터 없이 전체 통과).
notifier.py는 recipients를 발송 대상으로 사용한다 (아직 한 번도 수정 안 했으면
.env의 EMAIL_RECIPIENTS를 초기값으로 사용).
"""
import json
import os

import config

SETTINGS_PATH = "./data/settings.json"

DEFAULT_SETTINGS = {
    "enabled_sites": ["nhis", "moel", "hira", "kdca", "law", "khhi", "kahp", "kiha", "mpm"],
    "keywords": [],
    "recipients": None,  # None = 아직 커스터마이즈 안 함 -> config.EMAIL_RECIPIENTS 사용
}


def _load() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {**DEFAULT_SETTINGS, **data}


def _save(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH) or ".", exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_enabled_sites() -> list[str]:
    return list(_load()["enabled_sites"])


def enable_site(site_key: str):
    data = _load()
    if site_key not in data["enabled_sites"]:
        data["enabled_sites"].append(site_key)
        _save(data)


def disable_site(site_key: str):
    data = _load()
    if site_key in data["enabled_sites"]:
        data["enabled_sites"].remove(site_key)
        _save(data)


def get_keywords() -> list[str]:
    return list(_load()["keywords"])


def add_keyword(keyword: str):
    keyword = keyword.strip()
    if not keyword:
        return
    data = _load()
    if keyword not in data["keywords"]:
        data["keywords"].append(keyword)
        _save(data)


def remove_keyword(keyword: str):
    data = _load()
    if keyword in data["keywords"]:
        data["keywords"].remove(keyword)
        _save(data)


def get_recipients() -> list[str]:
    recipients = _load()["recipients"]
    if recipients is None:
        return list(config.EMAIL_RECIPIENTS)
    return list(recipients)


def add_recipient(email: str):
    email = email.strip()
    if not email:
        return
    data = _load()
    current = data["recipients"]
    if current is None:
        current = list(config.EMAIL_RECIPIENTS)
    if email not in current:
        current.append(email)
    data["recipients"] = current
    _save(data)


def remove_recipient(email: str):
    data = _load()
    current = data["recipients"]
    if current is None:
        current = list(config.EMAIL_RECIPIENTS)
    if email in current:
        current.remove(email)
    data["recipients"] = current
    _save(data)


def matches_keywords(title: str, content: str) -> bool:
    """키워드 미등록 시 항상 통과. 등록된 키워드가 하나라도 제목/본문에 포함되면 통과."""
    keywords = get_keywords()
    if not keywords:
        return True
    text = f"{title} {content or ''}".lower()
    return any(kw.lower() in text for kw in keywords)
