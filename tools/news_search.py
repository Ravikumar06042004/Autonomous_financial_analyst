"""
Shared news search layer using the Serper News API.

Responsibilities
----------------
1. Search market/topic/sector news through Serper.
2. Normalize Serper news results into one common format.
3. Strictly filter topic/sector news to the requested publication-time window (including an exact rolling 12-hour option).
4. Support Serper relative dates such as:
       "2 hours ago"
       "5 hours ago"
       "30 minutes ago"
       "1 day ago"
5. Support company-level financial news.
6. Use yfinance company news as a fallback.
7. Use SQLite cached company news as a final fallback.

No Tavily dependency is used anywhere in this module.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(override=True)


# ============================================================
# SERPER
# ============================================================

SERPER_API_URL = "https://google.serper.dev/news"


# ============================================================
# TRUSTED NEWS DOMAINS
# ============================================================

TRUSTED_DOMAINS = [
    "reuters.com",
    "cnbc.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "investing.com",
    "prnewswire.com",
    "businesswire.com",
    "economictimes.indiatimes.com",
    "moneycontrol.com",
    "business-standard.com",
    "livemint.com",
    "financialexpress.com",
    "thehindubusinessline.com",
    "ndtvprofit.com",
    "pib.gov.in",
    "rbi.org.in",
]


# ============================================================
# URL / DOMAIN HELPERS
# ============================================================

def _domain(url: str) -> str:
    """
    Extract domain from a URL.
    """
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .removeprefix("www.")
        )
    except Exception:
        return ""


def _canonical_url(url: str) -> str:
    """
    Normalize a URL enough for duplicate detection.
    """
    url = str(url or "").strip()

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        return f"{scheme}://{netloc}{path}"

    except Exception:
        return url.lower().rstrip("/")


def _is_non_news_page(
    url: str,
    title: str = "",
) -> bool:
    """
    Reject obvious non-news pages.
    """
    text = f"{url} {title}".lower()

    bad_markers = (
        "/credit-cards",
        "/home-equity/",
        "/mortgages/",
        "best-heloc",
        "/shopping/",
        "/advisor/",
        "/personal-finance/",
        "/calculators/",
        "/reviews/",
        "/products/",
    )

    return any(
        marker in text
        for marker in bad_markers
    )


# ============================================================
# DATE PARSING
# ============================================================

def _parse_news_datetime(
    value: Any,
) -> datetime | None:
    """
    Convert different news-provider date formats into
    timezone-aware UTC datetime.

    Supported examples:

        "just now"
        "now"
        "today"
        "yesterday"
        "30 minutes ago"
        "2 hours ago"
        "5 hours ago"
        "1 day ago"
        "5 days ago"
        "1 week ago"

        "2026-10-06T10:30:00Z"
        "2026-10-06T10:30:00+00:00"
        "2026-10-06 10:30:00"

        "Oct 6, 2026"
        "October 6, 2026"
        "2026-10-06"
    """

    if value is None:
        return None

    # --------------------------------------------------------
    # datetime object
    # --------------------------------------------------------

    if isinstance(value, datetime):
        dt = value

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    # --------------------------------------------------------
    # Unix timestamp
    # --------------------------------------------------------

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                float(value),
                tz=timezone.utc,
            )
        except Exception:
            return None

    text = str(value).strip()

    if not text:
        return None

    now = datetime.now(
        timezone.utc
    )

    lower = text.lower()

    # --------------------------------------------------------
    # Relative dates
    # --------------------------------------------------------

    if lower in {
        "just now",
        "now",
    }:
        return now

    if lower == "today":
        return now

    if lower == "yesterday":
        return now - timedelta(
            days=1
        )

    # Examples:
    #
    # 30 minutes ago
    # 2 hours ago
    # 5 days ago
    # 1 week ago
    #

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(minute|minutes|min|mins|"
        r"hour|hours|hr|hrs|"
        r"day|days|"
        r"week|weeks)"
        r"(?:\s+ago)?",
        lower,
    )

    if match:

        amount = float(
            match.group(1)
        )

        unit = match.group(2)

        if unit.startswith("min"):
            return now - timedelta(
                minutes=amount
            )

        if (
            unit.startswith("hour")
            or unit.startswith("hr")
        ):
            return now - timedelta(
                hours=amount
            )

        if unit.startswith("day"):
            return now - timedelta(
                days=amount
            )

        if unit.startswith("week"):
            return now - timedelta(
                weeks=amount
            )

    # --------------------------------------------------------
    # ISO datetime
    # --------------------------------------------------------

    iso_text = text

    if iso_text.endswith("Z"):
        iso_text = (
            iso_text[:-1]
            + "+00:00"
        )

    try:
        dt = datetime.fromisoformat(
            iso_text
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Common datetime/date formats
    # --------------------------------------------------------

    formats = [
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for fmt in formats:

        try:
            dt = datetime.strptime(
                text,
                fmt,
            )

            return dt.replace(
                tzinfo=timezone.utc
            )

        except Exception:
            continue

    # Serper can include both a date and a clock time (for example,
    # "Oct 12, 2026, 10:30 AM UTC"). Keep strict date validation, but
    # accept common timestamp variants rather than silently dropping them.
    try:
        from dateutil.parser import parse as parse_datetime

        dt = parse_datetime(text, fuzzy=False)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ImportError, TypeError, ValueError, OverflowError):
        return None



def _is_date_only_value(value: Any) -> bool:
    """Return True when a value contains a calendar date but no clock time.

    Exact rolling freshness cannot be established from a date-only value.
    This helper is used by the strict topic-news filter so a lower-priority
    exact timestamp can be used when a response also contains a date-only
    field, while a lone date-only field remains rejected.
    """
    if isinstance(value, datetime):
        return False
    if isinstance(value, (int, float)) or value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    patterns = (
        r"\d{4}-\d{2}-\d{2}",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{1,2}[-/]\d{1,2}[-/]\d{4}",
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}",
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2}",
    )
    return any(re.fullmatch(pattern, text, re.IGNORECASE) for pattern in patterns)


# ============================================================
# FRESHNESS HELPERS
# ============================================================

def _time_range_to_hours(
    time_range: str,
) -> int:
    """
    Convert a generic time-range name into hours.

    This is kept for compatibility with the
    previous Tavily-based interface.
    """

    value = str(
        time_range or "day"
    ).strip().lower()

    mapping = {
        "hour": 1,
        "hours": 1,
        "1h": 1,

        # Serper itself only supports broad ranges such as hour/day.
        # "12h" is enforced exactly by our local timestamp check.
        "6h": 6,
        "6 hours": 6,
        "six hours": 6,
        "12h": 12,
        "12 hours": 12,
        "twelve hours": 12,

        "day": 24,
        "days": 24,
        "1d": 24,

        "week": 24 * 7,
        "weeks": 24 * 7,
        "7d": 24 * 7,

        "month": 24 * 30,
        "months": 24 * 30,
        "30d": 24 * 30,
    }

    return mapping.get(
        value,
        24,
    )


def _is_recent(
    published_value: Any,
    *,
    max_age_hours: int = 24,
    now: datetime | None = None,
) -> bool:
    """
    Return True only when the publication time is
    within the requested freshness window.
    """

    now = (
        now
        or datetime.now(
            timezone.utc
        )
    )

    published = _parse_news_datetime(
        published_value
    )

    if published is None:
        return False

    if published > now:
        return False

    age_hours = (
        now - published
    ).total_seconds() / 3600.0

    return (
        0.0
        <= age_hours
        <= float(max_age_hours)
    )


# ============================================================
# COMPANY RELEVANCE
# ============================================================

def _company_terms(
    company_name: str,
    symbol: str,
) -> set[str]:
    """
    Build simple company search terms.
    """

    cleaned = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        company_name.lower(),
    ).strip()

    terms = {
        cleaned,
        symbol.lower().strip(),
    }

    words = [
        word
        for word in cleaned.split()
        if len(word) >= 3
    ]

    if len(words) >= 2:
        terms.add(
            " ".join(words[-2:])
        )

    return {
        value
        for value in terms
        if value
    }


def _is_company_relevant(
    item: dict[str, Any],
    company_name: str,
    symbol: str,
) -> tuple[bool, float]:
    """
    Determine whether an article is relevant to
    the requested company.
    """

    title = str(
        item.get("title")
        or ""
    )

    content = str(
        item.get("content")
        or item.get("snippet")
        or ""
    )

    source = str(
        item.get("source")
        or ""
    )

    url = str(
        item.get("url")
        or ""
    )

    text = (
        f"{title} "
        f"{content} "
        f"{source} "
        f"{url}"
    ).lower()

    if _is_non_news_page(
        url,
        title,
    ):
        return False, 0.0

    terms = _company_terms(
        company_name,
        symbol,
    )

    score = 0.0

    exact_name = (
        company_name
        .lower()
        .strip()
    )

    sym = (
        symbol
        .lower()
        .strip()
    )

    # Exact company name
    if (
        exact_name
        and exact_name in text
    ):
        score += 0.70

    # Exact ticker
    if (
        sym
        and re.search(
            rf"(?<![a-z0-9])"
            rf"{re.escape(sym)}"
            rf"(?![a-z0-9])",
            text,
        )
    ):
        score += 0.45

    # Company-related term in title
    if any(
        term in title.lower()
        for term in terms
        if len(term) >= 3
    ):
        score += 0.35

    # Financial context
    financial_keywords = (
        "earnings",
        "revenue",
        "profit",
        "shares",
        "stock",
        "ceo",
        "bank",
        "acquisition",
        "investment",
        "results",
        "quarter",
        "guidance",
        "deal",
        "merger",
    )

    if any(
        keyword in text
        for keyword in financial_keywords
    ):
        score += 0.05

    return (
        score >= 0.45,
        min(1.5, score),
    )


# ============================================================
# SERPER CLIENT
# ============================================================

class SerperClient:

    def __init__(
        self,
        api_key: str | None = None,
        gl: str | None = None,
    ):
        self.api_key = (
            api_key
            or os.getenv(
                "SERPER_API_KEY",
                "",
            )
        ).strip()

        self.gl = (
            gl
            if gl is not None
            else os.getenv(
                "SERPER_GL",
                "",
            )
        ).strip()

        if not self.api_key:
            raise RuntimeError(
                "SERPER_API_KEY is missing from .env"
            )

    def search_news(
        self,
        query: str,
        num: int = 5,
        domains: Iterable[str] | None = None,
        time_range: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Call the Serper News API.
        """

        payload: dict[str, Any] = {
            "q": query,
            "num": max(
                1,
                min(
                    int(num),
                    10,
                ),
            ),
            "hl": "en",
        }

        if self.gl:
            payload["gl"] = self.gl

        # Serper offers broad ranges, not an exact rolling twelve-hour window.
        # For "12h", ask it for candidates from the past day and enforce the
        # exact twelve-hour boundary locally in search_topic_news().
        range_key = str(time_range or "").strip().lower()
        tbs_value = {
            "hour": "qdr:h",
            "hours": "qdr:h",
            "1h": "qdr:h",
            "6h": "qdr:d",
            "6 hours": "qdr:d",
            "six hours": "qdr:d",
            "12h": "qdr:d",
            "12 hours": "qdr:d",
            "twelve hours": "qdr:d",
            "day": "qdr:d",
            "days": "qdr:d",
            "1d": "qdr:d",
            "week": "qdr:w",
            "weeks": "qdr:w",
            "7d": "qdr:w",
            "month": "qdr:m",
            "months": "qdr:m",
            "30d": "qdr:m",
        }.get(range_key)
        if tbs_value:
            payload["tbs"] = tbs_value

        domain_list = [
            str(domain).strip()
            for domain in (
                domains or []
            )
            if str(domain).strip()
        ]

        if domain_list:

            site_query = " OR ".join(
                f"site:{domain}"
                for domain in domain_list
            )

            payload["q"] = (
                f"{query} "
                f"({site_query})"
            )

        request = Request(
            SERPER_API_URL,
            data=json.dumps(
                payload
            ).encode("utf-8"),
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "autonomous-financial-analyst/1.0"
                ),
            },
            method="POST",
        )

        # ----------------------------------------------------
        # Request
        # ----------------------------------------------------

        try:

            with urlopen(
                request,
                timeout=20,
            ) as response:

                body = (
                    response
                    .read()
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                )

        except HTTPError as exc:

            detail = (
                exc.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )[:500]
            )

            raise RuntimeError(
                f"Serper HTTP "
                f"{exc.code}: "
                f"{detail}"
            ) from exc

        except URLError as exc:

            raise RuntimeError(
                "Serper network error: "
                f"{exc.reason}"
            ) from exc

        except Exception as exc:

            raise RuntimeError(
                "Serper request failed: "
                f"{type(exc).__name__}: "
                f"{exc}"
            ) from exc

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        try:
            data = json.loads(
                body
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Serper returned invalid JSON"
            ) from exc

        news = data.get(
            "news"
        )

        if not isinstance(
            news,
            list,
        ):
            return []

        return news


# ============================================================
# CLIENT FACTORY
# ============================================================

def _client() -> SerperClient:
    return SerperClient()


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize(
    item: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize Serper result.

    Serper normally returns:

        title
        link
        snippet
        date
        source
        imageUrl
    """

    url = str(
        item.get("link")
        or item.get("url")
        or ""
    ).strip()

    title = str(
        item.get("title")
        or ""
    ).strip()

    content = str(
        item.get("snippet")
        or item.get("content")
        or ""
    ).strip()

    source = str(
        item.get("source")
        or _domain(url)
        or "unknown"
    ).strip()

    published = (
        item.get("date")
        or item.get("publishedDate")
        or item.get("published_date")
    )

    return {
        "title": title,
        "url": url,
        "source": source.lower(),
        "published_date": published,
        "published_at": published,
        "content": content[:5000],
        "snippet": content[:2000],
    }


# ============================================================
# GENERIC SERPER SEARCH
# ============================================================

def _search(
    client: SerperClient,
    query: str,
    max_results: int = 5,
    domains: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Internal Serper search helper.
    """

    raw = client.search_news(
        query=query,
        num=max_results,
        domains=domains,
    )

    return [
        _normalize(item)
        for item in raw
        if isinstance(item, dict)
    ]


# ============================================================
# TOPIC / MARKET / SECTOR NEWS
# ============================================================
def _host_matches_allowed_domains(
    url: str,
    domains: Iterable[str] | None,
) -> bool:
    """Return True only when the URL host is in the explicit allow-list.

    Subdomains are accepted (for example, ``www.moneycontrol.com``), but
    look-alike hosts such as ``moneycontrol.com.example.org`` are rejected.
    An empty allow-list means there is no domain restriction.
    """
    allowed: set[str] = set()

    for raw_domain in domains or []:
        candidate = str(raw_domain or "").strip().lower()
        if not candidate:
            continue

        # Accept either a bare domain or a complete URL.
        if "://" in candidate:
            candidate = urlparse(candidate).hostname or ""
        else:
            # Strip a path/query if a caller accidentally provides one.
            candidate = candidate.split("/", 1)[0].split("?", 1)[0]
            # urlparse handles optional ports and bracketed host formats.
            candidate = urlparse("//" + candidate).hostname or candidate

        candidate = candidate.strip().strip(".").removeprefix("www.")
        if candidate:
            allowed.add(candidate)

    if not allowed:
        return True

    try:
        host = (urlparse(str(url or "").strip()).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return False

    if not host:
        return False

    host = host.removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in allowed)


def search_topic_news(
    query: str,
    max_results: int = 5,
    time_range: str = "day",
    domains: Iterable[str] | None = None,
    use_domains: bool = False,
) -> list[dict[str, Any]]:
    """Search current market/topic/sector news through Serper.

    When a domain allow-list is supplied, it is used as a Serper search hint
    and every returned URL is also checked locally. The local check is
    essential because search APIs can return off-domain results despite a
    ``site:`` query. Results without a parseable, sufficiently fresh date are
    rejected. ``use_domains`` remains for caller compatibility; supplying
    ``domains`` itself always activates strict local host filtering.
    """
    max_age_hours = _time_range_to_hours(time_range)
    requested_domains = [
        str(domain).strip()
        for domain in (domains or [])
        if str(domain or "").strip()
    ]

    if use_domains and not requested_domains:
        raise ValueError("use_domains=True requires at least one domain.")

    client = _client()
    candidate_count = min(10, max(int(max_results) * 3, 5))

    # Current SerperClient supports time_range. The fallback keeps compatible
    # test doubles/older client wrappers working if they do not accept it.
    try:
        raw_results = client.search_news(
            query=query,
            num=candidate_count,
            domains=requested_domains or None,
            time_range=time_range,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument 'time_range'" not in message:
            raise
        raw_results = client.search_news(
            query=query,
            num=candidate_count,
            domains=requested_domains or None,
        )

    output: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    now = datetime.now(timezone.utc)

    for item in raw_results:
        if not isinstance(item, dict):
            continue

        normalized = _normalize(item)
        url = normalized.get("url", "")
        title = normalized.get("title", "")

        if not url or not title:
            continue

        # Strict local allow-list validation. A URL path mentioning a trusted
        # domain is not enough; the actual hostname must match.
        if requested_domains and not _host_matches_allowed_domains(
            url, requested_domains
        ):
            continue

        if _is_non_news_page(url, title):
            continue

        canonical = _canonical_url(url)
        if not canonical or canonical in seen_urls:
            continue

        # Try every provider date field instead of blindly trusting the first
        # truthy field. Some results contain a date-only `date` plus a precise
        # `publishedDate`/`published_at`; the former cannot prove six-hour
        # freshness and must not mask the latter.
        published = None
        for field in (
            "date", "publishedDate", "published_date", "published_at",
            "publishedAt", "datePublished", "date_published",
        ):
            published_value = item.get(field)
            if published_value in (None, "") or _is_date_only_value(published_value):
                continue
            candidate_published = _parse_news_datetime(published_value)
            if candidate_published is not None:
                published = candidate_published
                break

        # Strict freshness: missing, stale, and future dates are rejected.
        if published is None or published > now:
            continue

        age_hours = (now - published).total_seconds() / 3600.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue

        normalized["published_date"] = published.isoformat()
        normalized["published_at"] = published.isoformat()
        normalized["age_hours"] = round(max(0.0, age_hours), 2)

        seen_urls.add(canonical)
        output.append(normalized)

    output.sort(
        key=lambda item: (
            _parse_news_datetime(item.get("published_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return output[:max_results]

def _get_yfinance_news(
    company_name: str,
    symbol: str,
    max_results: int = 5,
    days: int = 7,
) -> list[dict[str, Any]]:
    """
    Best-effort yfinance company-news fallback.
    """

    try:

        import yfinance as yf

        raw = (
            yf.Ticker(symbol).news
            or []
        )

    except Exception:
        return []

    results: list[
        dict[str, Any]
    ] = []

    now = datetime.now(
        timezone.utc
    )

    max_age_hours = (
        int(days) * 24
    )

    for item in raw[
        : max_results * 4
    ]:

        if not isinstance(
            item,
            dict,
        ):
            continue

        content = item.get(
            "content"
        )

        # ----------------------------------------------------
        # New yfinance structure
        # ----------------------------------------------------

        if isinstance(
            content,
            dict,
        ):

            title = (
                content.get(
                    "title"
                )
                or ""
            )

            canonical = (
                content.get(
                    "canonicalUrl"
                )
                or {}
            )

            url = (
                canonical.get(
                    "url"
                )
                if isinstance(
                    canonical,
                    dict,
                )
                else ""
            )

            provider = (
                content.get(
                    "provider"
                )
                or {}
            )

            source = (
                provider.get(
                    "displayName"
                )
                if isinstance(
                    provider,
                    dict,
                )
                else ""
            )

            published = (
                content.get(
                    "pubDate"
                )
            )

            snippet = (
                content.get(
                    "summary"
                )
                or ""
            )

        # ----------------------------------------------------
        # Older yfinance structure
        # ----------------------------------------------------

        else:

            title = (
                item.get("title")
                or ""
            )

            url = (
                item.get("link")
                or ""
            )

            source = (
                item.get(
                    "publisher"
                )
                or ""
            )

            published = (
                item.get(
                    "providerPublishTime"
                )
            )

            snippet = (
                item.get("summary")
                or ""
            )

        normalized = {
            "title": str(title),
            "url": str(url),
            "source": str(source),
            "published_date": published,
            "published_at": published,
            "content": str(
                snippet
            )[:5000],
            "snippet": str(
                snippet
            )[:2000],
        }

        # ----------------------------------------------------
        # Convert yfinance publication time.
        # ----------------------------------------------------

        parsed = _parse_news_datetime(
            published
        )

        if parsed is not None:

            age_hours = (
                now - parsed
            ).total_seconds() / 3600.0

            if (
                age_hours < 0
                or age_hours > max_age_hours
            ):
                continue

            normalized[
                "published_date"
            ] = parsed.isoformat()

            normalized[
                "published_at"
            ] = parsed.isoformat()

            normalized[
                "age_hours"
            ] = round(
                max(
                    0.0,
                    age_hours,
                ),
                2,
            )

        # ----------------------------------------------------
        # Company relevance
        # ----------------------------------------------------

        relevant, _ = (
            _is_company_relevant(
                normalized,
                company_name,
                symbol,
            )
        )

        if (
            normalized["url"]
            and normalized["title"]
            and relevant
        ):
            results.append(
                normalized
            )

        if len(results) >= max_results:
            break

    return results


# ============================================================
# SQLITE COMPANY NEWS CACHE
# ============================================================

def _load_cached_company_news(
    company_name: str,
    symbol: str,
    max_results: int = 5,
    days: int = 7,
) -> list[dict[str, Any]]:
    """
    SQLite cache fallback when live providers
    are unavailable.
    """

    try:

        from database.repository import (
            get_connection,
        )

    except Exception:
        return []

    queries = [
        (
            "SELECT title, url, source, "
            "published_date, content "
            "FROM news_articles "
            "ORDER BY id DESC LIMIT ?"
        ),
        (
            "SELECT title, url, source, "
            "published_date, content "
            "FROM news_articles "
            "ORDER BY created_at DESC LIMIT ?"
        ),
    ]

    rows = []

    conn = None

    try:

        conn = get_connection()

        for sql in queries:

            try:

                rows = conn.execute(
                    sql,
                    (
                        max(
                            20,
                            max_results * 5,
                        ),
                    ),
                ).fetchall()

                break

            except Exception:
                continue

    except Exception:
        return []

    finally:

        try:

            if conn:
                conn.close()

        except Exception:
            pass

    results: list[
        dict[str, Any]
    ] = []

    now = datetime.now(
        timezone.utc
    )

    max_age_hours = (
        int(days) * 24
    )

    for row in rows or []:

        item = dict(row)

        # ----------------------------------------------------
        # Freshness
        # ----------------------------------------------------

        published = _parse_news_datetime(
            item.get(
                "published_date"
            )
        )

        if published is not None:

            age_hours = (
                now - published
            ).total_seconds() / 3600.0

            if (
                age_hours < 0
                or age_hours > max_age_hours
            ):
                continue

            item[
                "published_date"
            ] = published.isoformat()

            item[
                "published_at"
            ] = published.isoformat()

            item[
                "age_hours"
            ] = round(
                max(
                    0.0,
                    age_hours,
                ),
                2,
            )

        else:

            # Missing publication date
            # is not considered reliable
            # for freshness-sensitive company news.
            continue

        relevant, _ = (
            _is_company_relevant(
                item,
                company_name,
                symbol,
            )
        )

        if relevant:
            results.append(
                item
            )

        if len(results) >= max_results:
            break

    return results


# ============================================================
# COMPANY FINANCIAL NEWS
# ============================================================

def search_financial_news(
    company_name: str,
    symbol: str,
    max_results: int = 8,
    days: int = 7,
) -> list[dict[str, Any]]:
    """
    Return relevant company-level financial news.

    Provider order:
        1. Serper News API
        2. yfinance company-news fallback
        3. SQLite cache

    Company news uses a configurable freshness window.
    Default = last 7 days.

    The `days` argument is kept for compatibility with
    existing project/test code.
    """

    company_name = (
        str(company_name)
        .strip()
    )

    symbol = (
        str(symbol)
        .strip()
        .upper()
    )

    if not company_name or not symbol:
        return []

    days = max(
        1,
        int(days),
    )

    max_age_hours = (
        days * 24
    )

    # ========================================================
    # 1. SERPER
    # ========================================================

    try:

        client = _client()

        queries = [
            (
                f'"{company_name}" '
                f'"{symbol}" '
                f'latest financial news'
            ),
            (
                f'"{company_name}" '
                f'"{symbol}" '
                f'earnings stock markets'
            ),
            (
                f'"{company_name}" '
                f'latest company news'
            ),
        ]

        combined: list[
            tuple[
                dict[str, Any],
                float,
            ]
        ] = []

        seen: set[str] = set()

        now = datetime.now(
            timezone.utc
        )

        for query in queries:

            raw_items = (
                client.search_news(
                    query=query,
                    num=min(
                        10,
                        max(
                            5,
                            max_results * 2,
                        ),
                    ),
                    domains=TRUSTED_DOMAINS,
                )
            )

            for raw_item in raw_items:

                if not isinstance(
                    raw_item,
                    dict,
                ):
                    continue

                item = _normalize(
                    raw_item
                )

                url = item.get(
                    "url",
                    "",
                )

                title = item.get(
                    "title",
                    "",
                )

                if not url or not title:
                    continue

                if _is_non_news_page(
                    url,
                    title,
                ):
                    continue

                canonical = _canonical_url(
                    url
                )

                if (
                    not canonical
                    or canonical in seen
                ):
                    continue

                # ------------------------------------------------
                # Freshness
                # ------------------------------------------------

                published_value = (
                    raw_item.get(
                        "date"
                    )
                    or raw_item.get(
                        "publishedDate"
                    )
                    or raw_item.get(
                        "published_date"
                    )
                )

                published = (
                    _parse_news_datetime(
                        published_value
                    )
                )

                if published is None:
                    continue

                if published > now:
                    continue

                age_hours = (
                    now - published
                ).total_seconds() / 3600.0

                if (
                    age_hours < 0
                    or age_hours
                    > max_age_hours
                ):
                    continue

                item[
                    "published_date"
                ] = published.isoformat()

                item[
                    "published_at"
                ] = published.isoformat()

                item[
                    "age_hours"
                ] = round(
                    max(
                        0.0,
                        age_hours,
                    ),
                    2,
                )

                # ------------------------------------------------
                # Relevance
                # ------------------------------------------------

                relevant, score = (
                    _is_company_relevant(
                        item,
                        company_name,
                        symbol,
                    )
                )

                if not relevant:
                    continue

                item[
                    "company_relevance"
                ] = round(
                    score,
                    3,
                )

                seen.add(
                    canonical
                )

                combined.append(
                    (
                        item,
                        score,
                    )
                )

        # Highest relevance first
        combined.sort(
            key=lambda pair: (
                pair[1],
                -float(
                    pair[0].get(
                        "age_hours",
                        999999,
                    )
                ),
            ),
            reverse=True,
        )

        serper_results = [
            item
            for item, _ in combined[
                :max_results
            ]
        ]

        if serper_results:
            return serper_results

    except Exception as exc:

        print(
            "Serper company news unavailable: "
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    # ========================================================
    # 2. YFINANCE FALLBACK
    # ========================================================

    print(
        "Trying yfinance company-news fallback..."
    )

    yf_results = _get_yfinance_news(
        company_name=company_name,
        symbol=symbol,
        max_results=max_results,
        days=days,
    )

    if yf_results:
        return yf_results

    print(
        "yfinance returned no relevant "
        "company news."
    )

    # ========================================================
    # 3. SQLITE FALLBACK
    # ========================================================

    print(
        "Trying relevant SQLite news cache..."
    )

    cached_results = (
        _load_cached_company_news(
            company_name=company_name,
            symbol=symbol,
            max_results=max_results,
            days=days,
        )
    )

    print(
        "SQLite cache returned "
        f"{len(cached_results)} "
        "relevant article(s)."
    )

    return cached_results[
        :max_results
    ]


# ============================================================
# PUBLIC EXPORTS
# ============================================================

__all__ = [
    "TRUSTED_DOMAINS",
    "SerperClient",
    "search_topic_news",
    "search_financial_news",
    "_client",
    "_search",
    "_normalize",
    "_parse_news_datetime",
    "_time_range_to_hours",
    "_is_recent",
    "_get_yfinance_news",
    "_load_cached_company_news",
    "_is_company_relevant",
    "_is_non_news_page",
    "_host_matches_allowed_domains",
]