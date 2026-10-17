from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from langchain_text_splitters import RecursiveCharacterTextSplitter

from tools.news_search import (
    _is_company_relevant,
    _is_non_news_page,
    search_financial_news,
)


def _parse_date(value):

    if not value:
        return None

    if isinstance(value, datetime):

        return (
            value
            if value.tzinfo
            else value.replace(
                tzinfo=timezone.utc
            )
        )

    text = str(value).strip()

    parsers = (
        lambda x: datetime.fromisoformat(
            x.replace("Z", "+00:00")
        ),
        parsedate_to_datetime,
    )

    for parser in parsers:

        try:

            result = parser(text)

            return (
                result
                if result.tzinfo
                else result.replace(
                    tzinfo=timezone.utc
                )
            )

        except Exception:
            continue

    return None


def _freshness_score(
    published_dt,
    now,
) -> float | None:

    if not published_dt:
        return None

    age_seconds = max(
        0,
        (
            now - published_dt
        ).total_seconds(),
    )

    return max(
        0.0,
        min(
            1.0,
            1.0 - (
                age_seconds
                / 86400
            ),
        ),
    )


def clean_news(
    company_name: str,
    symbol: str,
    articles: list[dict],
) -> list[dict]:

    now = datetime.now(timezone.utc)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1800,
        chunk_overlap=150,
    )

    cleaned = []

    seen_urls = set()
    seen_titles = set()

    for article in articles:

        if not isinstance(article, dict):
            continue

        title = (
            article.get("title") or ""
        ).strip()

        url = (
            article.get("url") or ""
        ).strip()

        content = (
            article.get("content") or ""
        ).strip()

        if not title or not url:
            continue

        if url in seen_urls:
            continue

        title_key = title.lower()

        if title_key in seen_titles:
            continue

        # Reject non-article pages.
        if _is_non_news_page(
            title,
            url,
        ):
            continue

        # Reject unrelated companies.
        if not _is_company_relevant(
            company_name,
            symbol,
            title,
            content,
            url,
        ):
            continue

        # Need meaningful article text.
        if len(content) < 120:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)

        published_dt = _parse_date(
            article.get("published_date")
        )

        freshness = _freshness_score(
            published_dt,
            now,
        )

        chunks = splitter.split_text(
            content
        )

        usable_content = (
            "\n\n".join(chunks[:3])
        )

        cleaned.append(
            {
                "company_name": company_name,
                "symbol": symbol.upper(),
                "title": title,
                "url": url,
                "source": urlparse(
                    url
                ).netloc,
                "published_date": (
                    published_dt.isoformat()
                    if published_dt
                    else None
                ),
                "freshness_score": (
                    round(
                        freshness,
                        3,
                    )
                    if freshness is not None
                    else None
                ),
                "generic_feed": False,
                "content": usable_content,
                "score": article.get(
                    "score"
                ),
            }
        )

    cleaned.sort(
        key=lambda item: (
            -(
                item.get(
                    "freshness_score"
                )
                or 0
            ),
            -(
                float(
                    item.get(
                        "score"
                    )
                    or 0
                )
            ),
        )
    )

    return cleaned[:8]


def get_clean_financial_news(
    company_name: str,
    symbol: str,
    max_results: int = 5,
) -> list[dict]:

    raw = search_financial_news(
        company_name,
        symbol,
        max_results=max(
            10,
            max_results * 3,
        ),
    )

    return clean_news(
        company_name,
        symbol,
        raw,
    )[:max_results]