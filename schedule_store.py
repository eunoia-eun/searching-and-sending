"""
관리자 페이지에서 설정한 실행 시각(KST)을 실제 GitHub Actions 스케줄에 반영.

settings.json에는 "사용자가 원하는 시각"만 저장하고(settings_store.get_schedule),
이 모듈이 .github/workflows/daily.yml의 cron 표현식을 그 시각(KST→UTC 변환)에 맞게
고쳐쓴 뒤 커밋한다. 클라우드(CLOUD_SYNC=true) 환경이면 git_sync를 통해 바로
GitHub에 반영되고, 로컬 실행이면 로컬 저장소 파일만 갱신한다(별도 git push 필요).
"""
import os
import re

import git_sync

_WORKFLOW_REL_PATH = os.path.join(".github", "workflows", "daily.yml")
_CRON_LINE_RE = re.compile(r"(- cron: ')(\d{1,2}) (\d{1,2}) \* \* (\S+)(')")
_COMMENT_RE = re.compile(r"# 매일[^\n]*UTC = [^\n]*KST[^\n]*")


def _to_utc(hour_kst: int, minute_kst: int) -> tuple[int, int]:
    total = (hour_kst * 60 + minute_kst - 9 * 60) % (24 * 60)
    return total // 60, total % 60


def _weekday_field(hour_kst: int, weekday_only: bool) -> str:
    """cron의 요일 필드는 실제 발화 시각(UTC) 기준이라, KST 자정을 걸치는 시각대는
    하루 어긋난다 — KST 09시 이전 실행은 UTC로는 전날이므로 요일을 하루 당겨준다."""
    if not weekday_only:
        return "*"
    return "1-5" if hour_kst >= 9 else "0-4"


def _workflow_path() -> str:
    if git_sync.ENABLED:
        git_sync.ensure_ready()
        return os.path.join(git_sync.SYNC_DIR, _WORKFLOW_REL_PATH)
    return _WORKFLOW_REL_PATH


def apply(hour_kst: int, minute_kst: int, weekday_only: bool = False) -> bool:
    """워크플로우 파일의 cron을 갱신. 성공 시 True."""
    if git_sync.ENABLED:
        git_sync.pull()

    path = _workflow_path()
    if not os.path.exists(path):
        return False

    with open(path, encoding="utf-8") as f:
        content = f.read()

    utc_hour, utc_minute = _to_utc(hour_kst, minute_kst)
    weekday_field = _weekday_field(hour_kst, weekday_only)

    def _replace(m: re.Match) -> str:
        return f"{m.group(1)}{utc_minute} {utc_hour} * * {weekday_field}{m.group(5)}"

    new_content, count = _CRON_LINE_RE.subn(_replace, content, count=1)
    if count == 0:
        return False

    weekday_note = " (평일만)" if weekday_only else ""
    new_content = _COMMENT_RE.sub(
        f"# 매일 {utc_hour:02d}:{utc_minute:02d} UTC = {hour_kst:02d}:{minute_kst:02d} KST{weekday_note}",
        new_content,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    if git_sync.ENABLED:
        git_sync.push(
            f"실행 시각 변경: 매일{weekday_note} {hour_kst:02d}:{minute_kst:02d} KST [skip ci]",
            rel_paths=[_WORKFLOW_REL_PATH],
        )
    return True
