"""
관리자 웹페이지(admin_web.py)가 설정 변경(data/settings.json,
.github/workflows/daily.yml)을 GitHub 저장소와 동기화하기 위한 모듈.

CLOUD_SYNC=true인 환경(클라우드에 배포된 admin_web.py)에서는:
- 별도 디렉터리에 저장소를 클론해두고
- 읽기 전에 git pull(hard reset), 쓰기 후에 git commit + push
로 GitHub Actions(매일 자동 실행)와 설정을 동기화한다.

CLOUD_SYNC이 없는 로컬 실행(admin_web.py를 내 컴퓨터에서 직접 실행)에서는
읽기(pull)는 하지 않지만(현재 작업 디렉터리가 곧 최신 상태인 실제 프로젝트
저장소이고, 매번 fetch하면 관리자 페이지가 느려짐), 쓰기(push)는 현재 작업
디렉터리에서 직접 git add/commit/push한다(2026-09-30 추가) — 이게 없으면
로컬 관리자 페이지에서 바꾼 값(특히 발송 시각)이 로컬 디스크에만 남고
GitHub Actions에는 전혀 반영되지 않아 "저장이 안 되는" 것처럼 보이는
문제가 있었음. main.py/GitHub Actions 등 읽기 전용 실행에서는 이 모듈이
아예 호출되지 않으므로 영향 없음.
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


def resolve_repo_path(rel_path: str) -> str:
    """레포 루트 기준 상대경로(rel_path)를 실제 읽을 수 있는 절대/상대 경로로 변환.
    CLOUD_SYNC 환경(admin_web.py)에서는 동기화 클론 기준 절대경로로, 그 외(로컬 실행,
    GitHub Actions)에서는 레포 루트 기준 상대경로 그대로 반환한다."""
    if not ENABLED:
        return rel_path
    pull()
    return os.path.join(SYNC_DIR, rel_path)


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
    """설정 변경을 git에 반영. 클라우드 모드는 동기화 전용 클론(SYNC_DIR)에서,
    로컬 모드는 현재 작업 디렉터리(=실제 프로젝트 저장소)에서 직접 commit+push한다."""
    repo_dir = SYNC_DIR if ENABLED else "."

    for rel_path in (rel_paths or [_SETTINGS_REL_PATH]):
        _run(["git", "add", rel_path], cwd=repo_dir)
    diff = _run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir)
    if diff.returncode == 0:
        return  # 변경 없음

    commit_r = _run(["git", "commit", "-m", message], cwd=repo_dir)
    if commit_r.returncode != 0:
        logger.error("git commit 실패: %s", commit_r.stderr)
        return

    r = _run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir)
    if r.returncode == 0:
        return

    # 그 사이 원격이 앞서갔을 수 있음(예: GitHub Actions 자동 커밋) —
    # 최신을 받아 우리 커밋만 그 위에 다시 얹어서 재시도
    logger.warning("git push 실패, 재시도: %s", r.stderr)
    fetch_cmd = ["git", "fetch", "--depth", "1", "origin", "main"] if ENABLED \
        else ["git", "fetch", "origin", "main"]
    _run(fetch_cmd, cwd=repo_dir)
    rb = _run(["git", "rebase", "origin/main"], cwd=repo_dir)
    if rb.returncode != 0:
        logger.error("git rebase 실패, 동기화 포기: %s", rb.stderr)
        _run(["git", "rebase", "--abort"], cwd=repo_dir)
        return
    r = _run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir)
    if r.returncode != 0:
        logger.error("git push 재시도 실패: %s", r.stderr)
