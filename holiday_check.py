"""
주말/한국 공휴일 여부 확인 — "평일에만 발송" 옵션에서 사용.
주말은 GitHub Actions cron의 요일 필드로도 걸러지지만(schedule_store.py),
설날·추석 등 공휴일은 요일만으로 알 수 없어 실행 시점에 별도로 확인한다.
"""
from datetime import date, datetime, timedelta, timezone

import holidays

KST = timezone(timedelta(hours=9))


def is_weekend_or_holiday(d: date | None = None) -> bool:
    if d is None:
        d = datetime.now(KST).date()
    if d.weekday() >= 5:  # 5=토요일, 6=일요일
        return True
    return d in holidays.SouthKorea(years=d.year)
