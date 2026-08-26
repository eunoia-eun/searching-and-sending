"""
시간 저장/표시 규칙: DB에는 항상 UTC로 저장하고, 사람이 보는 화면(이메일 본문,
관리자 페이지)에는 항상 KST(UTC+9)로 변환해서 보여준다.

로컬 실행(이 컴퓨터는 KST)과 GitHub Actions(러너는 UTC)에서 같은 datetime.now()가
서로 다른 시간대를 반환해서, 기록된 시각이 실행 환경에 따라 뒤섞이던 문제를 막기 위함.
"""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_utc_iso() -> str:
    """DB 저장용 — 항상 UTC, 타임존 오프셋 포함."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_kst() -> datetime:
    """이메일 본문 등 사람이 보는 문구 생성용 — 항상 KST 기준 현재 시각."""
    return datetime.now(timezone.utc).astimezone(KST)


def to_kst_str(iso_str: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """DB에 저장된 시각 문자열을 KST로 변환한 표시용 문자열로 바꾼다.
    타임존 표기가 없는 과거 값(이 수정 이전 기록)은 UTC로 간주하고 변환한다."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime(fmt)
