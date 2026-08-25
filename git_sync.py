"""
클라우드에 배포된 관리자 웹페이지(admin_web.py)가 data/settings.json을
GitHub 저장소와 동기화하기 위한 모듈.

로컬 실행(admin.py, admin_web.py를 내 컴퓨터에서 직접 실행, main.py,
GitHub Actions 등)에서는 CLOUD_SYNC 환경변수가 없으므로 전부 아무 동작도
하지 않는다 — 기존처럼 로컬 data/settings.json 파일만 그대로 사용.

CLOUD_SYNC=true인 환경(클라우드에 배포된 admin_web.py)에서만:
- 별도 디렉터리에 저장소를 클론해두고
- 읽기 전에 git pull, 쓰기 후에 git commit + push
로 GitHub Actions(매일 자동 실행)와 설정을 동기화한다.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

ENABLED = os.getenv("CLOUD_SYNC", "").lower() == "true"
REPO = os.getenv("GITHUB_REPO", "eunoia-eun/searching-and-sending")
TOKEN = os.getenv("GITHUB_PAT", "")
SYNC_DIR = os.getenv("SYNC_DIR", "/tmp/settings_sync")

_REMOTE_URL = f"https://x-access-token:{TOKEN}@github.com/{REPO}.git"
_SETTINGS_REL_PATH = os.path.join("data", "settings.json")


def _run(args: list[str], cwd: str | None = None, timeout: int = 30):
    return subprocess.run(
        args, cwd=cwd, timeout=timeout,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def ensure_ready() -> str:
    """동기화용 로컬 클론을 준비하고, settings.json의 절대경로를 반환."""
    if not os.path.isdir(os.path.join(SYNC_DIR, ".git")):
        os.makedirs(SYNC_DIR, exist_ok=True)
        r = _run(
            ["git", "clone", "--depth", "1", "--single-branch", "--branch", "main",
             _REMOTE_URL, SYNC_DIR],
            timeout=60,
        )
        if r.returncode != 0:
            logger.error("git clone 실패: %s", r.stderr)
        _run(["git", "config", "user.name", "admin-web-bot"], cwd=SYNC_DIR)
        _run(["git", "config", "user.email", "admin-web-bot@users.noreply.github.com"], cwd=SYNC_DIR)
    return os.path.join(SYNC_DIR, _SETTINGS_REL_PATH)


def pull():
    """읽기 전 항상 원격 main의 최신 상태로 맞춘다 (rebase 없이 fetch + hard reset —
    얕은 클론에서 rebase가 브랜치를 못 찾는 문제를 피하기 위함).
    이 디렉터리는 settings.json 동기화 전용이라 로컬 커밋되지 않은 변경이 없다는 전제."""
    if not ENABLED:
        return
    ensure_ready()
    r = _run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=SYNC_DIR)
    if r.returncode != 0:
        logger.warning("git fetch 실패: %s", r.stderr)
        return
    r = _run(["git", "reset", "--hard", "origin/main"], cwd=SYNC_DIR)
    if r.returncode != 0:
        logger.warning("git reset 실패: %s", r.stderr)


def push(message: str, rel_paths: list[str] | None = None):
    if not ENABLED:
        return
    for rel_path in (rel_paths or [_SETTINGS_REL_PATH]):
        _run(["git", "add", rel_path], cwd=SYNC_DIR)
    diff = _run(["git", "diff", "--cached", "--quiet"], cwd=SYNC_DIR)
    if diff.returncode == 0:
        return  # 변경 없음
    _run(["git", "commit", "-m", message], cwd=SYNC_DIR)

    r = _run(["git", "push", "origin", "HEAD:main"], cwd=SYNC_DIR)
    if r.returncode == 0:
        return

    # 그 사이 원격이 앞서갔을 수 있음 — 최신을 받아 우리 커밋만 그 위에 다시 얹어서 재시도
    logger.warning("git push 실패, 재시도: %s", r.stderr)
    _run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=SYNC_DIR)
    rb = _run(["git", "rebase", "origin/main"], cwd=SYNC_DIR)
    if rb.returncode != 0:
        logger.error("git rebase 실패, 동기화 포기: %s", rb.stderr)
        _run(["git", "rebase", "--abort"], cwd=SYNC_DIR)
        return
    r = _run(["git", "push", "origin", "HEAD:main"], cwd=SYNC_DIR)
    if r.returncode != 0:
        logger.error("git push 재시도 실패: %s", r.stderr)
