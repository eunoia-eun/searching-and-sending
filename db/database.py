import sqlite3
import os
import json
from typing import Optional

import config
import timeutil


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS notices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                site_key    TEXT    NOT NULL,
                notice_id   TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                posted_at   TEXT,
                content     TEXT,
                status      TEXT    NOT NULL DEFAULT 'new',
                crawled_at  TEXT    NOT NULL,
                UNIQUE(site_key, notice_id)
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id       INTEGER NOT NULL REFERENCES notices(id),
                category        TEXT,
                importance      TEXT,
                summary_points  TEXT,
                action_required TEXT,
                is_notification_needed INTEGER,
                analyzed_at     TEXT NOT NULL,
                notified_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS crawl_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                site_key    TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                new_count   INTEGER DEFAULT 0,
                error       TEXT
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at         TEXT NOT NULL,
                recipients      TEXT NOT NULL,
                subject         TEXT NOT NULL,
                message_id      TEXT,
                notice_count    INTEGER DEFAULT 0,
                site_breakdown  TEXT,
                success         INTEGER NOT NULL,
                error           TEXT,
                screenshot_path TEXT
            );
        """)
        # 기존 DB 호환: screenshot_path 컬럼이 없으면 추가
        # (Gmail IMAP 원본 조회가 배포 환경에서 불안정해서 발송 시 자동 캡처 방식으로 대체)
        try:
            conn.execute("ALTER TABLE email_log ADD COLUMN screenshot_path TEXT")
        except Exception:
            pass
        # 기존 DB 호환: notified_at 컬럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE analysis_results ADD COLUMN notified_at TEXT")
        except Exception:
            pass
        # 기존 DB 호환: extra_url 컬럼이 없으면 추가 (law_crawler의 신구법비교 링크 등 보조 링크용)
        try:
            conn.execute("ALTER TABLE notices ADD COLUMN extra_url TEXT")
        except Exception:
            pass


def is_seen(site_key: str, notice_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM notices WHERE site_key=? AND notice_id=?",
            (site_key, notice_id),
        ).fetchone()
    return row is not None


def save_notice(
    site_key: str,
    notice_id: str,
    title: str,
    url: str,
    posted_at: Optional[str],
    content: Optional[str] = None,
    extra_url: Optional[str] = None,
) -> Optional[int]:
    """새 공지를 저장하고 row id를 반환. 이미 존재하면 None 반환."""
    crawled_at = timeutil.now_utc_iso()
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notices (site_key, notice_id, title, url, posted_at, content, extra_url, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (site_key, notice_id, title, url, posted_at, content, extra_url, crawled_at),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def search_notices(query: str = "", site_key: str = "", limit: int = 100) -> list[dict]:
    """관리자 페이지 '공지 이력' 탭 검색용 — 제목 기준 검색, 공지별 발송일(notified_at)과
    원문 링크(url/extra_url)를 함께 반환한다. 아직 분석 전인 공지는 importance/notified_at이
    NULL로 나온다."""
    sql = """
        SELECT n.id, n.site_key, n.title, n.url, n.extra_url, n.posted_at, n.crawled_at,
               a.importance, a.category, a.notified_at
        FROM notices n
        LEFT JOIN analysis_results a ON a.notice_id = n.id
        WHERE 1=1
    """
    params: list = []
    if query:
        sql += " AND n.title LIKE ?"
        params.append(f"%{query}%")
    if site_key:
        sql += " AND n.site_key = ?"
        params.append(site_key)
    sql += " ORDER BY n.crawled_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_content(site_key: str, notice_id: str, content: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE notices SET content=? WHERE site_key=? AND notice_id=?",
            (content, site_key, notice_id),
        )


def get_pending_notices():
    """분석 대기 중인 공지 목록 반환."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT n.* FROM notices n
            LEFT JOIN analysis_results a ON a.notice_id = n.id
            WHERE a.id IS NULL AND n.content IS NOT NULL
            ORDER BY n.crawled_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def save_analysis(notice_db_id: int, result: dict):
    analyzed_at = timeutil.now_utc_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO analysis_results
              (notice_id, category, importance, summary_points, action_required,
               is_notification_needed, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notice_db_id,
                result.get("category", ""),
                result.get("importance", ""),
                json.dumps(result.get("summary_points", []), ensure_ascii=False),
                result.get("action_required", ""),
                1 if result.get("is_notification_needed") else 0,
                analyzed_at,
            ),
        )
        conn.execute(
            "UPDATE notices SET status='analyzed' WHERE id=?",
            (notice_db_id,),
        )


def get_unnotified_analyses() -> list[dict]:
    """알림 필요하나 아직 발송하지 않은 공지+분석 결과 반환 (중요도 순)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                n.id, n.site_key, n.title, n.url, n.posted_at, n.extra_url,
                a.id         AS analysis_id,
                a.category,
                a.importance,
                a.summary_points,
                a.action_required
            FROM analysis_results a
            JOIN notices n ON n.id = a.notice_id
            WHERE a.is_notification_needed = 1
              AND a.notified_at IS NULL
            ORDER BY
                CASE a.importance WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
                n.crawled_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def mark_notified(analysis_id: int):
    """이메일 발송 완료 후 호출 — 중복 발송 방지."""
    notified_at = timeutil.now_utc_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE analysis_results SET notified_at=? WHERE id=?",
            (notified_at, analysis_id),
        )


def log_crawl(site_key: str, started_at: str, finished_at: str, new_count: int, error: str = ""):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO crawl_log (site_key, started_at, finished_at, new_count, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (site_key, started_at, finished_at, new_count, error),
        )


def get_crawl_log(limit: int = 500) -> list[dict]:
    """최근 크롤링 실행 기록 (사이트별 성공/에러) — 관리자 페이지 '실행 이력' 탭에서
    '업데이트가 없어서 안 보낸 것'과 '사이트가 막혀서 못 본 것'을 구분하는 데 쓴다."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT site_key, started_at, finished_at, new_count, error
            FROM crawl_log
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def log_email(
    sent_at: str,
    recipients: list[str],
    subject: str,
    message_id: Optional[str],
    notice_count: int,
    site_breakdown: dict,
    success: bool,
    error: str = "",
    screenshot_path: Optional[str] = None,
):
    """발송 시도 결과를 기록 — 성공/실패와 무관하게 항상 남긴다 (실패 원인 진단용)."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO email_log
              (sent_at, recipients, subject, message_id, notice_count, site_breakdown,
               success, error, screenshot_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sent_at,
                json.dumps(recipients, ensure_ascii=False),
                subject,
                message_id,
                notice_count,
                json.dumps(site_breakdown, ensure_ascii=False),
                1 if success else 0,
                error,
                screenshot_path,
            ),
        )


def get_email_log(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM email_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_email_log_entry(entry_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM email_log WHERE id=?", (entry_id,)
        ).fetchone()
    return dict(row) if row else None
