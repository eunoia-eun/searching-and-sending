"""
건강검진 공지 분석 모듈
Claude API를 사용하여 각 공지를 구조화된 JSON으로 분석
"""
import json
import logging

import anthropic

import config
from db import database

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-8"

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "일반/암/영유아 검진",
                "특수건강진단/배치전검진",
                "공무원/일반 채용신체검사",
                "기타/공통 행정",
            ],
        },
        "importance": {
            "type": "string",
            "enum": ["High", "Medium", "Low"],
        },
        "summary_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "변경 내용 / 적용 대상 / 시행 시기 순서의 3줄 요약 (정확히 3개)",
        },
        "action_required": {
            "type": "string",
            "description": "검진기관이 취해야 할 후속 조치. 없으면 '해당 없음'",
        },
        "is_notification_needed": {
            "type": "boolean",
            "description": "검진기관에 즉시 알림이 필요한지 여부",
        },
    },
    "required": [
        "category",
        "importance",
        "summary_points",
        "action_required",
        "is_notification_needed",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 건강검진 관련 법령·정책 공지 분석 전문가입니다.
건강검진기관 운영자에게 제공할 분석 결과를 JSON으로 반환하세요.

[category 분류 기준]
- 일반/암/영유아 검진: 일반건강검진·국가암검진·영유아검진 항목·기준·수가 등
- 특수건강진단/배치전검진: 산업안전보건법상 특수·배치전건강진단 관련
- 공무원/일반 채용신체검사: 채용 신체검사 관련
- 기타/공통 행정: 청구·서식·시스템·교육·행사 등 행정 사항

[importance 기준]
- High: 법령·고시 개정, 수가 변경, 검진 항목·기준 변경, 시스템 의무 적용 등 즉각 대응 필요
- Medium: 지침·안내·유권해석 등 숙지 필요
- Low: 단순 공지, 행사, 모집, 순수 홍보

[summary_points] 반드시 3개
  1) 무엇이 바뀌었나 (변경·공지 핵심)
  2) 누가 해당하나 (적용 대상)
  3) 언제부터인가 (시행·적용 시기)

[action_required]
검진기관이 실제로 해야 할 조치를 구체적으로 기술. 없으면 "해당 없음".

[is_notification_needed]
true: High·Medium 중요도이며 현장 대응이 필요한 공지
false: Low 중요도이거나 단순 홍보·참고 사항"""


def _build_notice_text(notice: dict) -> str:
    site_name = config.SITES.get(notice["site_key"], {}).get("name", notice["site_key"])
    content = (notice.get("content") or "")[:8000]
    return (
        f"출처: {site_name}\n"
        f"제목: {notice['title']}\n"
        f"URL: {notice['url']}\n"
        f"게시일: {notice.get('posted_at') or '불명'}\n\n"
        f"--- 공지 본문 ---\n{content}"
    )


def _analyze_single(client: anthropic.Anthropic, notice: dict) -> dict:
    user_text = _build_notice_text(notice)

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        output_config={
            "format": {
                "type": "json_schema",
                "schema": ANALYSIS_SCHEMA,
            }
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        message = stream.get_final_message()

    for block in message.content:
        if block.type == "text":
            return json.loads(block.text)

    raise ValueError(f"분석 응답에 텍스트 블록 없음: {notice['title']}")


def analyze_notices() -> list[dict]:
    """
    DB에서 미분석 공지를 가져와 Claude로 분석 후 저장.
    is_notification_needed=True인 공지+분석 결과 목록 반환.
    """
    pending = database.get_pending_notices()
    if not pending:
        logger.info("분석 대기 공지 없음")
        return []

    logger.info("분석 대상: %d건", len(pending))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    to_notify = []

    for notice in pending:
        title = notice["title"]
        logger.info("분석 중: [%s] %s", notice["site_key"], title)
        try:
            result = _analyze_single(client, notice)
            database.save_analysis(notice["id"], result)
            logger.info(
                "  → %s | %s | 알림=%s",
                result.get("category"),
                result.get("importance"),
                result.get("is_notification_needed"),
            )
            if result.get("is_notification_needed"):
                to_notify.append({**notice, "analysis": result})
        except Exception as exc:
            logger.error("분석 실패 [%s]: %s", title, exc)

    logger.info("분석 완료 — 알림 대상 %d건", len(to_notify))
    return to_notify
