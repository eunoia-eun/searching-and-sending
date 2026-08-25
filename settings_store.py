"""
사용자 설정 저장소 — 크롤링 대상 사이트, 사이트별 관심 키워드 필터, 발송 대상 이메일

admin.py / admin_web.py로 관리하며, main.py/scheduler.py는 별도 --sites 지정이
없으면 여기 저장된 enabled_sites를 사용한다. base_crawler.py는 사이트별 keywords로
제목/본문을 필터링한다 (그 사이트의 키워드가 비어있으면 필터 없이 전체 통과 —
사이트마다 자주 쓰는 단어가 달라서(예: hira는 "적정성평가", law는 법령명 자체로
이미 좁혀짐) 전체 공통 키워드 하나로는 특정 사이트가 통째로 걸러지는 문제가 있었음).
notifier.py는 recipients를 발송 대상으로 사용한다 (아직 한 번도 수정 안 했으면
.env의 EMAIL_RECIPIENTS를 초기값으로 사용).
"""
import json
import os

import config
import git_sync

SETTINGS_PATH = "./data/settings.json"


def _resolve_path() -> str:
    """CLOUD_SYNC 환경(클라우드에 배포된 admin_web.py)에서는 GitHub에서 동기화한
    경로를, 그 외(로컬 실행, GitHub Actions)에서는 로컬 경로를 사용한다."""
    if git_sync.ENABLED:
        return git_sync.ensure_ready()
    return SETTINGS_PATH

DEFAULT_SETTINGS = {
    "enabled_sites": ["nhis", "moel", "hira", "kdca", "law", "khhi", "kahp", "kiha", "mpm"],
    "keywords": {},  # {site_key: [keyword, ...]} — 포함 키워드. 없는 사이트/빈 리스트 = 필터 없음(전체 통과)
    "exclude_keywords": {},  # {site_key: [keyword, ...]} — 제외 키워드. 하나라도 포함되면 무조건 걸러짐
    "recipients": None,  # None = 아직 커스터마이즈 안 함 -> config.EMAIL_RECIPIENTS 사용
}


def _load() -> dict:
    git_sync.pull()
    path = _resolve_path()
    if not os.path.exists(path):
        data = dict(DEFAULT_SETTINGS)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    merged = {**DEFAULT_SETTINGS, **data}

    # 이전 버전(사이트 공통 키워드 리스트) 마이그레이션: 기존 목록을 각 사이트의
    # 초기 키워드로 복사한다. law는 검색어 자체가 이미 좁혀져 있어 필터 없이 시작.
    if isinstance(merged.get("keywords"), list):
        old_list = merged["keywords"]
        merged["keywords"] = {
            site: list(old_list) for site in config.SITES if site != "law"
        }
        _save(merged)

    return merged


def _save(data: dict):
    path = _resolve_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    git_sync.push("관리자 페이지에서 설정 변경 [skip ci]")


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


def get_keywords(site_key: str) -> list[str]:
    return list(_load()["keywords"].get(site_key, []))


def get_all_keywords() -> dict[str, list[str]]:
    return _load()["keywords"]


def add_keyword(site_key: str, keyword: str):
    keyword = keyword.strip()
    if not keyword:
        return
    data = _load()
    site_list = data["keywords"].setdefault(site_key, [])
    if keyword not in site_list:
        site_list.append(keyword)
    _save(data)


def remove_keyword(site_key: str, keyword: str):
    data = _load()
    site_list = data["keywords"].get(site_key, [])
    if keyword in site_list:
        site_list.remove(keyword)
    _save(data)


def get_exclude_keywords(site_key: str) -> list[str]:
    return list(_load()["exclude_keywords"].get(site_key, []))


def get_all_exclude_keywords() -> dict[str, list[str]]:
    return _load()["exclude_keywords"]


def add_exclude_keyword(site_key: str, keyword: str):
    keyword = keyword.strip()
    if not keyword:
        return
    data = _load()
    site_list = data["exclude_keywords"].setdefault(site_key, [])
    if keyword not in site_list:
        site_list.append(keyword)
    _save(data)


def remove_exclude_keyword(site_key: str, keyword: str):
    data = _load()
    site_list = data["exclude_keywords"].get(site_key, [])
    if keyword in site_list:
        site_list.remove(keyword)
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


def matches_keywords(site_key: str, title: str, content: str) -> bool:
    """제외 키워드가 하나라도 포함되면 무조건 걸러짐(포함 키워드 매치 여부와 무관).
    그 다음 포함 키워드 미등록 시 항상 통과, 등록돼 있으면 하나라도 포함되어야 통과."""
    text = f"{title} {content or ''}".lower()

    exclude_keywords = get_exclude_keywords(site_key)
    if any(kw.lower() in text for kw in exclude_keywords):
        return False

    keywords = get_keywords(site_key)
    if not keywords:
        return True
    return any(kw.lower() in text for kw in keywords)
