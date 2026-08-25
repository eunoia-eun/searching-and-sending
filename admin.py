"""
관리자 CLI — 크롤링 대상 사이트 및 관심 키워드 관리

실행 예:
  python admin.py site list
  python admin.py site enable hira
  python admin.py site disable nhis
  python admin.py keyword list hira
  python admin.py keyword add hira 적정성평가
  python admin.py keyword remove hira 적정성평가
  python admin.py exclude list mpm
  python admin.py exclude add mpm 문학상
  python admin.py exclude remove mpm 문학상
  python admin.py recipient list
  python admin.py recipient add someone@example.com
  python admin.py recipient remove someone@example.com
"""
import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config
import settings_store
from main import ALL_CRAWLERS


def cmd_site_list(args):
    enabled = set(settings_store.get_enabled_sites())
    for key in ALL_CRAWLERS:
        name = config.SITES.get(key, {}).get("name", key)
        mark = "[ON] " if key in enabled else "[OFF]"
        print(f"{mark} {key:6s} {name}")


def cmd_site_enable(args):
    settings_store.enable_site(args.site)
    print(f"활성화됨: {args.site}")


def cmd_site_disable(args):
    settings_store.disable_site(args.site)
    print(f"비활성화됨: {args.site}")


def cmd_keyword_list(args):
    if args.site:
        keywords = settings_store.get_keywords(args.site)
        if not keywords:
            print("등록된 키워드 없음 (필터 없이 전체 공지 수집)")
            return
        for kw in keywords:
            print(f"- {kw}")
    else:
        all_kw = settings_store.get_all_keywords()
        for key in ALL_CRAWLERS:
            name = config.SITES.get(key, {}).get("name", key)
            kws = all_kw.get(key, [])
            print(f"{key:6s} {name:16s} {', '.join(kws) if kws else '(필터 없음)'}")


def cmd_keyword_add(args):
    settings_store.add_keyword(args.site, args.keyword)
    print(f"[{args.site}] 추가됨: {args.keyword}")


def cmd_keyword_remove(args):
    settings_store.remove_keyword(args.site, args.keyword)
    print(f"[{args.site}] 삭제됨: {args.keyword}")


def cmd_exclude_list(args):
    if args.site:
        keywords = settings_store.get_exclude_keywords(args.site)
        if not keywords:
            print("등록된 제외 키워드 없음")
            return
        for kw in keywords:
            print(f"- {kw}")
    else:
        all_kw = settings_store.get_all_exclude_keywords()
        for key in ALL_CRAWLERS:
            name = config.SITES.get(key, {}).get("name", key)
            kws = all_kw.get(key, [])
            print(f"{key:6s} {name:16s} {', '.join(kws) if kws else '(없음)'}")


def cmd_exclude_add(args):
    settings_store.add_exclude_keyword(args.site, args.keyword)
    print(f"[{args.site}] 제외 키워드 추가됨: {args.keyword}")


def cmd_exclude_remove(args):
    settings_store.remove_exclude_keyword(args.site, args.keyword)
    print(f"[{args.site}] 제외 키워드 삭제됨: {args.keyword}")


def cmd_recipient_list(args):
    recipients = settings_store.get_recipients()
    if not recipients:
        print("등록된 발송 대상 이메일 없음")
        return
    for email in recipients:
        print(f"- {email}")


def cmd_recipient_add(args):
    settings_store.add_recipient(args.email)
    print(f"추가됨: {args.email}")


def cmd_recipient_remove(args):
    settings_store.remove_recipient(args.email)
    print(f"삭제됨: {args.email}")


def main():
    parser = argparse.ArgumentParser(description="건강검진 공지 크롤러 관리자 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    site_parser = sub.add_parser("site", help="크롤링 대상 사이트 관리")
    site_sub = site_parser.add_subparsers(dest="action", required=True)

    site_sub.add_parser("list", help="사이트 목록 및 활성화 상태 조회").set_defaults(func=cmd_site_list)

    p = site_sub.add_parser("enable", help="사이트 크롤링 활성화")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.set_defaults(func=cmd_site_enable)

    p = site_sub.add_parser("disable", help="사이트 크롤링 비활성화")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.set_defaults(func=cmd_site_disable)

    kw_parser = sub.add_parser("keyword", help="사이트별 관심 키워드 관리 (제목/본문에 하나라도 포함된 공지만 수집)")
    kw_sub = kw_parser.add_subparsers(dest="action", required=True)

    p = kw_sub.add_parser("list", help="키워드 목록 조회 (사이트 생략 시 전체 사이트 요약)")
    p.add_argument("site", nargs="?", choices=list(ALL_CRAWLERS.keys()))
    p.set_defaults(func=cmd_keyword_list)

    p = kw_sub.add_parser("add", help="특정 사이트에 키워드 추가")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.add_argument("keyword")
    p.set_defaults(func=cmd_keyword_add)

    p = kw_sub.add_parser("remove", help="특정 사이트에서 키워드 삭제")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.add_argument("keyword")
    p.set_defaults(func=cmd_keyword_remove)

    ex_parser = sub.add_parser("exclude", help="사이트별 제외 키워드 관리 (제목/본문에 하나라도 포함되면 무조건 제외)")
    ex_sub = ex_parser.add_subparsers(dest="action", required=True)

    p = ex_sub.add_parser("list", help="제외 키워드 목록 조회 (사이트 생략 시 전체 사이트 요약)")
    p.add_argument("site", nargs="?", choices=list(ALL_CRAWLERS.keys()))
    p.set_defaults(func=cmd_exclude_list)

    p = ex_sub.add_parser("add", help="특정 사이트에 제외 키워드 추가")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.add_argument("keyword")
    p.set_defaults(func=cmd_exclude_add)

    p = ex_sub.add_parser("remove", help="특정 사이트에서 제외 키워드 삭제")
    p.add_argument("site", choices=list(ALL_CRAWLERS.keys()))
    p.add_argument("keyword")
    p.set_defaults(func=cmd_exclude_remove)

    rc_parser = sub.add_parser("recipient", help="이메일 발송 대상 관리")
    rc_sub = rc_parser.add_subparsers(dest="action", required=True)

    rc_sub.add_parser("list", help="발송 대상 목록 조회").set_defaults(func=cmd_recipient_list)

    p = rc_sub.add_parser("add", help="발송 대상 이메일 추가")
    p.add_argument("email")
    p.set_defaults(func=cmd_recipient_add)

    p = rc_sub.add_parser("remove", help="발송 대상 이메일 삭제")
    p.add_argument("email")
    p.set_defaults(func=cmd_recipient_remove)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
