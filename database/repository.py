from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "financial.db"


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# HELPERS
# ============================================================

def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _ensure_column(
    conn,
    table_name: str,
    column_name: str,
    column_definition: str,
):
    """
    Add a missing column to an existing database table.

    This keeps the existing financial.db intact and performs
    a lightweight schema migration when required.
    """

    columns = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    existing_columns = {
        row["name"]
        for row in columns
    }

    if column_name not in existing_columns:

        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    conn = get_connection()

    cur = conn.cursor()

    # --------------------------------------------------------
    # Companies
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            symbol TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )
        """
    )

    # --------------------------------------------------------
    # News
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_symbol TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT,
            published_at TEXT,
            content TEXT,
            created_at TEXT
        )
        """
    )

    # Existing databases created by an older version may not
    # have created_at.
    _ensure_column(
        conn,
        "news_articles",
        "created_at",
        "TEXT",
    )

    # --------------------------------------------------------
    # Company reports
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_symbol TEXT NOT NULL,
            company_name TEXT NOT NULL,
            current_price REAL,
            rsi REAL,
            sentiment TEXT,
            risk_level TEXT,
            signal TEXT,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # Paper trades
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            order_id TEXT,
            status TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # Scheduler runs
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT,
            details TEXT
        )
        """
    )

    # --------------------------------------------------------
    # Legacy market-context snapshots
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_context_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            overall_sentiment TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # NEW / REQUIRED MARKET SENTIMENT REPORTS
    # --------------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_sentiment_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asof TEXT NOT NULL,
            mode TEXT NOT NULL,
            overall_score REAL,
            bias TEXT NOT NULL,
            evidence_quality_pct REAL,
            coverage REAL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # Fill missing created_at in old news records
    # --------------------------------------------------------

    cur.execute(
        """
        UPDATE news_articles
        SET created_at = ?
        WHERE created_at IS NULL
        """,
        (
            _utc_now_iso(),
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# COMPANY
# ============================================================

def save_company(
    name: str,
    symbol: str,
):
    initialize_database()

    conn = get_connection()

    conn.execute(
        """
        INSERT OR IGNORE INTO companies
        (
            name,
            symbol,
            active
        )
        VALUES (?, ?, 1)
        """,
        (
            name.strip(),
            symbol.upper().strip(),
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# NEWS
# ============================================================

def save_news_articles(
    symbol: str,
    articles: list[dict],
):

    initialize_database()

    conn = get_connection()

    now = _utc_now_iso()

    for item in articles:

        url = (
            item.get("url")
            or ""
        ).strip()

        title = (
            item.get("title")
            or "Untitled"
        ).strip()

        if not url or not title:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO news_articles
            (
                company_symbol,
                title,
                url,
                source,
                published_at,
                content,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol.upper(),
                title,
                url,
                item.get("source"),
                (
                    item.get("published_date")
                    or item.get("published_at")
                ),
                item.get("content"),
                now,
            ),
        )

    conn.commit()

    conn.close()


# ============================================================
# COMPANY REPORT
# ============================================================

def save_report(
    symbol: str,
    company_name: str,
    indicators: dict,
    report: str,
    sentiment: str = "Unknown",
    risk_level: str = "Unknown",
    signal: str = "HOLD",
):

    initialize_database()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO reports
        (
            company_symbol,
            company_name,
            current_price,
            rsi,
            sentiment,
            risk_level,
            signal,
            report,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol.upper(),
            company_name,
            indicators.get(
                "current_price"
            ),
            indicators.get(
                "rsi"
            ),
            sentiment,
            risk_level,
            signal,
            report,
            _utc_now_iso(),
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# MARKET CONTEXT SNAPSHOT
# ============================================================

def save_market_context(
    context: dict,
):

    initialize_database()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO market_context_snapshots
        (
            overall_sentiment,
            payload_json,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            str(
                context.get(
                    "overall_sentiment",
                    "Unknown",
                )
            ),
            json.dumps(
                context,
                default=str,
            ),
            _utc_now_iso(),
        ),
    )

    conn.commit()

    conn.close()


def get_latest_market_context():

    initialize_database()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            payload_json,
            created_at
        FROM market_context_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    if not row:
        return None

    try:

        payload = json.loads(
            row["payload_json"]
        )

        payload[
            "snapshot_created_at"
        ] = row["created_at"]

        return payload

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return None


# ============================================================
# MARKET SENTIMENT REPORT
# ============================================================

def save_market_sentiment_report(
    report: dict,
):

    initialize_database()

    conn = get_connection()

    created_at = (
        report.get("created_at")
        or report.get("generated_at")
        or _utc_now_iso()
    )

    asof = (
        report.get("asof")
        or report.get("generated_at")
        or created_at
    )

    mode = str(
        report.get(
            "mode",
            "live",
        )
    )

    overall_score = report.get(
        "overall_score"
    )

    bias = (
        report.get("bias")
        or report.get("overall_sentiment")
        or "UNKNOWN"
    )

    evidence_quality_pct = (
        report.get(
            "evidence_quality_pct"
        )
    )

    coverage = report.get(
        "coverage"
    )

    report_json = json.dumps(
        report,
        default=str,
    )

    conn.execute(
        """
        INSERT INTO market_sentiment_reports
        (
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            report_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asof,
            mode,
            overall_score,
            str(bias),
            evidence_quality_pct,
            coverage,
            report_json,
            created_at,
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# LATEST MARKET SENTIMENT
# ============================================================

def get_latest_market_sentiment_report():

    initialize_database()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            id,
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            report_json,
            created_at
        FROM market_sentiment_reports
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return (
        dict(row)
        if row
        else None
    )


# ============================================================
# MARKET SENTIMENT HISTORY
# ============================================================

def get_recent_market_sentiment_reports(
    limit: int = 10,
):

    limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    initialize_database()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            created_at
        FROM market_sentiment_reports
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            limit,
        ),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# PAPER TRADE
# ============================================================

def save_trade(
    symbol: str,
    side: str,
    quantity: int,
    order_id: str,
    status: str,
):

    initialize_database()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO paper_trades
        (
            symbol,
            side,
            quantity,
            order_id,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            symbol.upper(),
            side.upper(),
            quantity,
            order_id,
            status,
            _utc_now_iso(),
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# RECENT COMPANY REPORTS
# ============================================================

def get_recent_reports(
    limit: int = 20,
):

    limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    initialize_database()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            company_symbol,
            company_name,
            current_price,
            rsi,
            sentiment,
            risk_level,
            signal,
            report,
            created_at
        FROM reports
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            limit,
        ),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# LATEST REPORT PER COMPANY
# ============================================================

def get_latest_reports_by_company():

    initialize_database()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT r.*
        FROM reports r
        INNER JOIN (
            SELECT
                company_symbol,
                MAX(id) AS max_id
            FROM reports
            GROUP BY company_symbol
        ) latest
        ON latest.max_id = r.id
        ORDER BY r.company_symbol
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

def get_dashboard_summary():

    initialize_database()

    conn = get_connection()

    companies = conn.execute(
        """
        SELECT COUNT(*)
        FROM companies
        WHERE active = 1
        """
    ).fetchone()[0]

    reports = conn.execute(
        """
        SELECT COUNT(*)
        FROM reports
        """
    ).fetchone()[0]

    news_articles = conn.execute(
        """
        SELECT COUNT(*)
        FROM news_articles
        """
    ).fetchone()[0]

    paper_trades = conn.execute(
        """
        SELECT COUNT(*)
        FROM paper_trades
        """
    ).fetchone()[0]

    conn.close()

    latest_market = (
        get_latest_market_sentiment_report()
    )

    return {
        "companies": int(
            companies
        ),

        "reports": int(
            reports
        ),

        "news_articles": int(
            news_articles
        ),

        "news": int(
            news_articles
        ),

        "paper_trades": int(
            paper_trades
        ),

        "latest_market_sentiment": (
            latest_market
        ),
    }


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

def get_table_names():

    initialize_database()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    ).fetchall()

    conn.close()

    return [
        row["name"]
        for row in rows
    ]

# ============================================================
# FINAL MARKET SENTIMENT PERSISTENCE PATCH
# ============================================================

def save_market_sentiment_report(report: dict):
    """
    Persist the complete market sentiment report into SQLite.

    This definition is intentionally at the end of the module so
    it becomes the active implementation even if an older version
    of this function exists earlier in the file.
    """

    if not isinstance(report, dict):
        raise TypeError("Market sentiment report must be a dictionary.")

    initialize_database()

    conn = get_connection()

    created_at = (
        report.get("created_at")
        or report.get("generated_at")
        or _utc_now_iso()
    )

    asof = (
        report.get("asof")
        or report.get("generated_at")
        or created_at
    )

    mode = str(
        report.get("mode")
        or "live"
    )

    overall_score = report.get(
        "overall_score"
    )

    bias = (
        report.get("bias")
        or report.get("overall_sentiment")
        or "UNKNOWN"
    )

    evidence_quality_pct = report.get(
        "evidence_quality_pct"
    )

    coverage = report.get(
        "coverage"
    )

    report_json = json.dumps(
        report,
        default=str,
    )

    cursor = conn.execute(
        """
        INSERT INTO market_sentiment_reports
        (
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            report_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(asof),
            mode,
            overall_score,
            str(bias),
            evidence_quality_pct,
            coverage,
            report_json,
            str(created_at),
        ),
    )

    conn.commit()

    saved_id = cursor.lastrowid

    conn.close()

    return int(saved_id)


def get_latest_market_sentiment_report():

    initialize_database()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            id,
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            report_json,
            created_at
        FROM market_sentiment_reports
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def get_recent_market_sentiment_reports(
    limit: int = 10,
):

    limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    initialize_database()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            asof,
            mode,
            overall_score,
            bias,
            evidence_quality_pct,
            coverage,
            created_at
        FROM market_sentiment_reports
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]