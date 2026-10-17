"""Sector-level news collection using one shared Serper collection.

The 20 sector definitions are retained from the supplied reference engine.

News is collected once and then reused for sector scoring.

Freshness policy:
- Sector / market news = last 12 hours only.
- Articles without a trustworthy publication timestamp are rejected.
- Older articles are rejected before entering sentiment scoring.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from config.sector_config import ALL_PORTAL_DOMAINS
from tools.news_search import (
    TRUSTED_DOMAINS,
    SerperClient,
    search_topic_news,
)


# ============================================================
# MARKET QUERY
# ============================================================

MACRO_QUERY = (
    "India stock market latest Nifty Sensex FII DII RBI "
    "rates inflation Fed crude oil geopolitical technology "
    "global markets"
)


# ============================================================
# 22 NEWS CHANNEL QUERIES: 20 industry sectors + 2 global-market channels
# ============================================================

GLOBAL_CHANNEL_SOURCE_PAGES = {
    "GLOBAL_INDICES": {
        "name": "Moneycontrol — Global Indices News",
        "url": "https://www.moneycontrol.com/news/tags/global-indices.html",
    },
    "WORLD_MARKET_TRENDS": {
        "name": "Moneycontrol — World Market Trends",
        "url": "https://www.moneycontrol.com/markets/global-indices/",
    },
}


SECTOR_QUERIES = {
    "BANKING":
        "India banking banks RBI credit loans NPA net interest margin latest news",

    "NBFC":
        "India NBFC finance companies RBI asset quality lending latest news",

    "IT":
        "India IT services software technology export deals AI spending latest news",

    "PHARMA":
        "India pharmaceutical companies drug regulation FDA medicines latest news",

    "HEALTHCARE":
        "India healthcare hospitals medical devices diagnostics latest news",

    "AUTO":
        "India automobile auto sales EV passenger vehicles commercial vehicles latest news",

    "FMCG":
        "India FMCG consumer goods rural demand latest news",

    "RETAIL":
        "India retail consumer demand e commerce stores latest news",

    "METALS":
        "India steel aluminium metals mining commodity prices latest news",

    "OIL_UPSTREAM":
        "India oil gas upstream crude ONGC oil prices latest news",

    "OMC":
        "India oil marketing BPCL HPCL IOC fuel prices refining margins latest news",

    "AVIATION":
        "India aviation airlines air travel jet fuel latest news",

    "PAINTS":
        "India paints coatings companies raw material prices latest news",

    "CHEMICALS":
        "India chemicals specialty chemicals petrochemical latest news",

    "REALTY":
        "India real estate housing property developers mortgage rates latest news",

    "UTILITIES":
        "India utilities power electricity grid renewable energy latest news",

    "CAPITAL_GOODS":
        "India capital goods industrial infrastructure capex engineering latest news",

    "TELECOM":
        "India telecom 5G mobile tariff broadband latest news",

    "LOGISTICS":
        "India logistics freight shipping transport warehouse latest news",

    "CONSUMER_DURABLES":
        "India consumer durables appliances electronics air conditioner refrigerator latest news",

    "GLOBAL_INDICES": (
        "global indices world stock markets latest news Dow Jones S&P 500 Nasdaq FTSE DAX Nikkei Hang Seng"
    ),

    "WORLD_MARKET_TRENDS": (
        "world market trends global equity indices US European Asian markets market movement latest"
    ),
}


# ============================================================
# SEPARATE MACRO-FACTOR NEWS FEED (not used to alter sector scoring)
# ============================================================
# These topics mirror the market-factor table requested for Telegram. They are
# collected separately from the 20 industry sectors + 2 global channels so
# adding this digest does not silently change sector labels or sentiment weights.
FACTOR_NEWS_QUERIES = {
    "BRENT CRUDE": (
        "Brent crude oil price latest news supply OPEC production inventories "
        "geopolitics global oil market"
    ),
    "U.S. 10Y YIELD": (
        "US 10 year Treasury yield latest news bond yields inflation Federal Reserve "
        "Treasury market"
    ),
    "U.S. DOLLAR (DXY)": (
        "US dollar index DXY latest news dollar strength weakness currencies "
        "Federal Reserve three month high"
    ),
    "USD/INR": (
        "USD INR rupee exchange rate latest news Indian rupee dollar RBI forex market"
    ),
    "FII FLOWS": (
        "foreign institutional investors FII India net buying selling latest news "
        "NSE cash market flows"
    ),
    "U.S. INFLATION": (
        "US inflation CPI PCE latest news actual versus expectations inflation data"
    ),
    "FED RATE EXPECTATIONS": (
        "Federal Reserve interest rate expectations rate cut hike probability futures latest news"
    ),
    "U.S. TECHNOLOGY / AI": (
        "US technology stocks artificial intelligence AI latest news Nasdaq Nvidia "
        "semiconductor earnings spending"
    ),
    "ASIAN MARKETS": (
        "Asian stock markets latest news Nikkei Hang Seng Kospi China equities market movement"
    ),
    "MIDDLE EAST / GEOPOLITICS": (
        "Middle East geopolitical tensions latest news Israel Iran Gulf shipping crude oil markets"
    ),
    "INDIA DOMESTIC INSTITUTIONS (DII)": (
        "India domestic institutional investors DII buying selling latest news mutual funds "
        "equity cash market flows"
    ),
}


# ============================================================
# SECTOR TERMS
# ============================================================

SECTOR_TERMS = {
    "BANKING": {
        "bank",
        "banks",
        "banking",
        "rbi",
        "credit",
        "loan",
        "loans",
        "npa",
        "deposit",
    },

    "NBFC": {
        "nbfc",
        "housing finance",
        "microfinance",
        "finance company",
    },

    "IT": {
        "it services",
        "software",
        "technology",
        "ai",
        "cloud",
        "digital",
        "cybersecurity",
        "outsourcing",
    },

    "PHARMA": {
        "pharma",
        "pharmaceutical",
        "drug",
        "drugs",
        "medicine",
        "fda",
        "usfda",
        "biotech",
    },

    "HEALTHCARE": {
        "healthcare",
        "hospital",
        "hospitals",
        "diagnostics",
        "medical devices",
        "surgery",
    },

    "AUTO": {
        "auto",
        "automobile",
        "automotive",
        "ev",
        "vehicle",
        "vehicles",
        "car",
        "cars",
        "motorcycle",
        "truck",
    },

    "FMCG": {
        "fmcg",
        "consumer goods",
        "packaged foods",
        "beverages",
        "rural demand",
    },

    "RETAIL": {
        "retail",
        "ecommerce",
        "e-commerce",
        "consumer demand",
        "stores",
        "shopping",
    },

    "METALS": {
        "steel",
        "aluminium",
        "metal",
        "metals",
        "mining",
        "iron ore",
    },

    "OIL_UPSTREAM": {
        "crude",
        "oil",
        "gas",
        "upstream",
        "ongc",
        "petroleum",
        "brent",
    },

    "OMC": {
        "bpcl",
        "hpcl",
        "ioc",
        "refining",
        "refiner",
        "fuel prices",
        "marketing margin",
    },

    "AVIATION": {
        "aviation",
        "airline",
        "airlines",
        "airport",
        "jet fuel",
        "air travel",
    },

    "PAINTS": {
        "paint",
        "paints",
        "coatings",
    },

    "CHEMICALS": {
        "chemical",
        "chemicals",
        "specialty chemicals",
        "petrochemical",
    },

    "REALTY": {
        "real estate",
        "property",
        "housing",
        "residential",
        "developer",
        "developers",
    },

    "UTILITIES": {
        "utility",
        "utilities",
        "power",
        "electricity",
        "grid",
        "renewable",
    },

    "CAPITAL_GOODS": {
        "capital goods",
        "industrial",
        "infrastructure",
        "capex",
        "engineering",
    },

    "TELECOM": {
        "telecom",
        "5g",
        "mobile tariff",
        "broadband",
    },

    "LOGISTICS": {
        "logistics",
        "freight",
        "shipping",
        "transport",
        "warehouse",
    },

    "CONSUMER_DURABLES": {
        "consumer durable",
        "appliance",
        "electronics",
        "air conditioner",
        "refrigerator",
    },

    "GLOBAL_INDICES": {
        "dax",
        "dow jones",
        "ftse",
        "global indices",
        "global stock market",
        "hang seng",
        "nasdaq",
        "nikkei",
        "s&p 500",
        "world indices",
        "world stock market",
    },

    "WORLD_MARKET_TRENDS": {
        "asian markets",
        "european markets",
        "global equity markets",
        "global markets",
        "us markets",
        "world market trends",
        "world markets",
        "world stocks",
    },
}


# ============================================================
# EVENT PATTERNS
# ============================================================

EVENT_PATTERNS = [
    (
        "CRUDE_UP",
        [
            r"crude[^.]{0,80}(?:rise|rises|rose|surge|surges|higher|jump|jumps|up\b)",
            r"oil prices?[^.]{0,60}(?:rise|higher|surge|jump|up\b)",
        ],
    ),

    (
        "CRUDE_DOWN",
        [
            r"crude[^.]{0,80}(?:fall|falls|fell|lower|drop|drops|down\b)",
            r"oil prices?[^.]{0,60}(?:fall|lower|drop|down\b)",
        ],
    ),

    (
        "YIELDS_UP",
        [
            r"(?:us|u\.s\.|treasury)[^.]{0,50}(?:10-year|10 year|yield)[^.]{0,50}(?:rise|higher|surge|up\b)",
            r"yields?[^.]{0,30}(?:rise|higher|surge|up\b)",
        ],
    ),

    (
        "YIELDS_DOWN",
        [
            r"(?:us|u\.s\.|treasury)[^.]{0,50}(?:10-year|10 year|yield)[^.]{0,50}(?:fall|lower|drop|down\b)",
            r"yields?[^.]{0,30}(?:fall|lower|drop|down\b)",
        ],
    ),

    (
        "INR_WEAK",
        [
            r"rupee[^.]{0,40}(?:weak|weaken|falls|drops|slides|depreciat)",
            r"inr[^.]{0,40}(?:weak|falls|drops|slides)",
        ],
    ),

    (
        "INR_STRONG",
        [
            r"rupee[^.]{0,40}(?:strengthen|stronger|rises|gains|appreciat)",
            r"inr[^.]{0,40}(?:strong|rises|gains)",
        ],
    ),

    (
        "US_TECH_UP",
        [
            r"nasdaq[^.]{0,50}(?:rally|rise|higher|gains|surge)",
            r"us tech[^.]{0,50}(?:rally|rise|higher|gains)",
        ],
    ),

    (
        "CHINA_STIMULUS",
        [
            r"china[^.]{0,100}(?:stimulus|stimulus package|support measures|rate cut|fiscal support)",
        ],
    ),

    (
        "RECESSION_RISK",
        [
            r"(?:recession|slowdown|hard landing|growth fears|demand weakness)",
        ],
    ),

    (
        "GEOPOLITICAL_RISK",
        [
            r"(?:war|conflict|geopolitical|missile|sanctions|middle east|iran|ukraine)",
        ],
    ),

    (
        "INDIA_GROWTH",
        [
            r"(?:india|indian)[^.]{0,90}(?:growth|expansion|strong demand|capex|gdp|pmi|industrial output)",
        ],
    ),

    (
        "RBI_EASING",
        [
            r"rbi[^.]{0,90}(?:cut|cuts|cutting|easing|lower rates|rate reduction)",
        ],
    ),

    (
        "RBI_TIGHTENING",
        [
            r"rbi[^.]{0,90}(?:hike|hikes|hiking|tightening|higher rates|rate increase)",
        ],
    ),

    (
        "PHARMA_REGULATION",
        [
            r"(?:fda|usfda|drug regulator|pharma regulation|drug recall|warning letter)",
        ],
    ),

    (
        "TRADE_RESTRICTIONS",
        [
            r"(?:tariff|tariffs|trade restriction|export ban|import duty|sanction)",
        ],
    ),
]


# ============================================================
# KEYWORD SENTIMENT
# ============================================================

POSITIVE_WORDS = {
    "beat",
    "growth",
    "strong",
    "record",
    "surge",
    "rally",
    "support",
    "recovery",
    "easing",
    "stimulus",
    "upgrade",
    "inflow",
    "rise",
    "rises",
    "higher",
    "gains",
}

NEGATIVE_WORDS = {
    "miss",
    "decline",
    "weak",
    "fall",
    "drop",
    "selloff",
    "inflation",
    "hike",
    "restriction",
    "tariff",
    "war",
    "recession",
    "downgrade",
    "losses",
    "lower",
    "down",
}


# ============================================================
# EVENT DIRECTION
# ============================================================

EVENT_BROAD_DIRECTION = {
    "CRUDE_UP": -0.6,
    "CRUDE_DOWN": 0.6,
    "YIELDS_UP": -0.4,
    "YIELDS_DOWN": 0.4,
    "INR_WEAK": -0.2,
    "INR_STRONG": 0.2,
    "US_TECH_UP": 0.3,
    "CHINA_STIMULUS": 0.2,
    "RECESSION_RISK": -0.6,
    "GEOPOLITICAL_RISK": -0.6,
    "INDIA_GROWTH": 0.5,
    "RBI_EASING": 0.3,
    "RBI_TIGHTENING": -0.3,
    "PHARMA_REGULATION": -0.2,
    "TRADE_RESTRICTIONS": -0.3,
}


# ============================================================
# SOURCE RELIABILITY
# ============================================================

SOURCE_RELIABILITY = {
    "reuters.com": 0.95,
    "cnbc.com": 0.90,
    "rbi.org.in": 0.98,
    "pib.gov.in": 0.95,
    "economictimes.indiatimes.com": 0.85,
    "business-standard.com": 0.85,
    "livemint.com": 0.80,
    "financialexpress.com": 0.80,
    "moneycontrol.com": 0.75,
    "thehindubusinessline.com": 0.85,
    "ndtvprofit.com": 0.80,
    "investing.com": 0.70,
}


# ============================================================
# HELPERS
# ============================================================

def _domain(url: str) -> str:
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .removeprefix("www.")
        )

    except Exception:
        return ""


def _published_date(value):
    """The topic-news layer already returns ISO dates.

    This parser also supports Unix timestamps as a defensive
    fallback.
    """

    if not value:
        return None

    if isinstance(
        value,
        (int, float),
    ):
        try:
            timestamp = float(value)

            if timestamp > 10_000_000_000:
                timestamp /= 1000.0

            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
            OSError,
        ):
            return None

    text = str(value).strip()

    try:
        dt = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        return (
            dt
            if dt.tzinfo
            else dt.replace(
                tzinfo=timezone.utc
            )
        )

    except ValueError:
        return None


def _is_recent_1h(
    value,
    reference: datetime | None = None,
) -> bool:
    """Accept only timestamped articles from the last rolling 12 hours."""
    published = _published_date(value)
    if published is None:
        return False

    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    published = published.astimezone(timezone.utc)

    reference = reference or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    age_hours = (reference - published).total_seconds() / 3600.0
    return 0.0 <= age_hours <= NEWS_FRESHNESS_HOURS


def _event_for_article(text: str):
    lower = text.lower()

    for event_type, patterns in EVENT_PATTERNS:
        for pattern in patterns:
            match = re.search(
                pattern,
                lower,
            )

            if match:
                evidence = text[
                    max(
                        0,
                        match.start(),
                    ):
                    min(
                        len(text),
                        match.end() + 50,
                    )
                ].strip()

                return (
                    event_type,
                    evidence,
                )

    return (
        "OTHER",
        "",
    )


def _keyword_sentiment(
    text: str,
) -> float:

    words = re.findall(
        r"[a-z][a-z-]+",
        text.lower(),
    )

    positive = sum(
        1
        for word in words
        if word in POSITIVE_WORDS
    )

    negative = sum(
        1
        for word in words
        if word in NEGATIVE_WORDS
    )

    if positive == negative == 0:
        return 0.0

    return max(
        -1.0,
        min(
            1.0,
            (
                positive - negative
            )
            / max(
                3,
                positive + negative,
            ),
        ),
    )


def _sector_matches(
    text: str,
    *,
    include_global: bool = True,
) -> list[str]:

    lower = text.lower()

    matches: list[str] = []
    global_channels = {"GLOBAL_INDICES", "WORLD_MARKET_TRENDS"}

    for sector, terms in SECTOR_TERMS.items():
        if not include_global and sector in global_channels:
            continue
        if any(term in lower for term in terms):
            matches.append(sector)

    # A headline can describe world-market trends by comparing multiple named
    # international indices even if it does not literally say "global markets".
    # Requiring at least two references avoids tagging every generic market item.
    if include_global:
        named_indices = (
            "s&p 500", "nasdaq", "dow jones", "ftse", "dax",
            "nikkei", "hang seng", "kospi", "shanghai composite",
            "stoxx", "russell 2000",
        )
        index_mentions = sum(1 for term in named_indices if term in lower)
        if (
            index_mentions >= 2
            and "GLOBAL_INDICES" in matches
            and "WORLD_MARKET_TRENDS" not in matches
        ):
            matches.append("WORLD_MARKET_TRENDS")

    return matches


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize_item(
    item: dict,
    forced_sector: str | None = None,
) -> dict:

    title = str(
        item.get("title")
        or ""
    ).strip()

    url = str(
        item.get("url")
        or ""
    ).strip()

    content = str(
        item.get("content")
        or item.get("snippet")
        or ""
    ).strip()

    combined = (
        f"{title}. {content}"
    )

    # General MARKET-query articles may also be classified into the two
    # global-market topics by their actual headline/content. The dedicated
    # query name still controls channel provenance; content-based classification
    # fills global topic scores when the dedicated 12-hour search has no fresh
    # results. Industry-specific queries do not automatically add global tags.
    include_global_topics = (
        forced_sector is None
        or forced_sector in GLOBAL_MARKET_KEYS
    )
    matches = _sector_matches(
        combined,
        include_global=include_global_topics,
    )

    if (
        forced_sector
        and forced_sector in SECTOR_TERMS
        and forced_sector not in matches
    ):
        matches.append(
            forced_sector
        )

    event_type, evidence = (
        _event_for_article(
            combined
        )
    )

    direction = (
        EVENT_BROAD_DIRECTION.get(
            event_type,
            _keyword_sentiment(
                combined
            ),
        )
    )

    published = _published_date(
        item.get("published_at")
        or item.get("published_date")
    )

    source = str(
        item.get("source")
        or _domain(url)
    ).lower().removeprefix(
        "www."
    )

    relevance = min(
        1.0,
        0.45
        + 0.10 * len(matches)
        + (
            0.20
            if event_type != "OTHER"
            else 0.0
        ),
    )

    confidence = min(
        0.90,
        0.55
        + (
            0.15
            if event_type != "OTHER"
            else 0.0
        )
        + (
            0.05
            if content
            else 0.0
        ),
    )

    return {
        "title": title,
        "url": url,
        "source": source,
        "source_reference_name": GLOBAL_CHANNEL_SOURCE_PAGES.get(
            forced_sector, {}
        ).get("name", ""),
        "source_reference_url": GLOBAL_CHANNEL_SOURCE_PAGES.get(
            forced_sector, {}
        ).get("url", ""),

        "published_at": (
            published.isoformat()
            if published
            else None
        ),

        "published_date": (
            published.isoformat()
            if published
            else None
        ),

        "content": content[:4000],

        "sectors": matches,
        "news_channel": (forced_sector or ""),
        "news_channels": ([forced_sector] if forced_sector else []),

        "event_type": event_type,

        "event_key": url.lower(),

        "evidence": (
            evidence
            or title[:300]
        ),

        "relevance": round(
            relevance,
            3,
        ),

        "confidence": round(
            confidence,
            3,
        ),

        "magnitude": round(
            min(
                1.0,
                0.5
                + 0.1 * len(matches),
            ),
            3,
        ),

        "india_direction": round(
            direction,
            3,
        ),

        "reliability": SOURCE_RELIABILITY.get(
            source,
            0.70,
        ),
    }


# ============================================================
# DOMAIN SELECTION
# ============================================================

def _query_domains():
    return (
        ALL_PORTAL_DOMAINS
        or TRUSTED_DOMAINS
    )


# ============================================================
# GLOBAL-MARKET CHANNEL COLLECTION
# ============================================================

GLOBAL_MARKET_KEYS = {
    "GLOBAL_INDICES",
    "WORLD_MARKET_TRENDS",
}

# Only these established financial-news domains are used for fallback.
# Results are additionally checked locally because a search API's site
# restriction is not a guarantee that every returned URL matches.
GLOBAL_FALLBACK_DOMAINS = [
    "reuters.com",
    "cnbc.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "investing.com",
    "ft.com",
    "livemint.com",
    "apnews.com",
    "financialexpress.com",
]

GLOBAL_PAGE_TIMEOUT_SECONDS = 5
GLOBAL_MAX_PAGE_FETCHES = 10
GLOBAL_MAX_ARTICLES_PER_CHANNEL = 4

# Strict rolling publication-time window applied to every news channel.
NEWS_FRESHNESS_HOURS = 12


class _GlobalArticleParser(HTMLParser):
    """Extract article metadata and same-domain links from an HTML page."""

    _DATE_KEYS = {
        "article:published_time",
        "datepublished",
        "datepublishedoriginal",
        "publishdate",
        "pubdate",
        "date",
        "dc.date",
        "dc.date.issued",
        "datecreated",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dates = []
        self.links = []
        self.jsonld = []
        self.title_parts = []
        self.description = ""
        self.canonical_url = ""
        self._in_title = False
        self._in_jsonld = False
        self._script_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "meta":
            key = (
                attrs.get("property")
                or attrs.get("name")
                or attrs.get("itemprop")
                or ""
            ).strip().lower()
            content = (
                attrs.get("content")
                or attrs.get("datetime")
                or ""
            ).strip()

            if key in self._DATE_KEYS and content:
                self.dates.append(content)

            if key in {"og:title", "twitter:title"} and content:
                self.title_parts.append(content)

            if (
                key in {"og:description", "description", "twitter:description"}
                and content
                and not self.description
            ):
                self.description = content

        elif tag == "time":
            value = (
                attrs.get("datetime")
                or attrs.get("content")
                or ""
            ).strip()
            if value:
                self.dates.append(value)

        elif tag == "link":
            rel = (attrs.get("rel") or "").lower().split()
            if "canonical" in rel:
                self.canonical_url = (attrs.get("href") or "").strip()

            key = (
                attrs.get("itemprop")
                or attrs.get("property")
                or ""
            ).strip().lower()
            value = (
                attrs.get("content")
                or attrs.get("href")
                or ""
            ).strip()
            if key in self._DATE_KEYS and value:
                self.dates.append(value)

        elif tag == "a":
            href = (attrs.get("href") or "").strip()
            if href:
                self.links.append(href)

        elif tag == "title":
            self._in_title = True

        elif tag == "script":
            script_type = (attrs.get("type") or "").lower()
            if "ld+json" in script_type:
                self._in_jsonld = True
                self._script_parts = []

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.title_parts.append(data.strip())
        if self._in_jsonld:
            self._script_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            payload = "".join(self._script_parts).strip()
            if payload:
                try:
                    self.jsonld.append(json.loads(payload))
                except (ValueError, TypeError):
                    pass
            self._in_jsonld = False
            self._script_parts = []


def _global_parse_datetime(value):
    """Parse only verifiable publication timestamps into UTC.

    Important: date-only metadata (for example ``2026-10-13``) must be
    rejected BEFORE ``datetime.fromisoformat`` sees it. Otherwise it becomes
    midnight UTC and an earlier date-only meta tag can mask a later, exact
    publication timestamp from the same page.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        try:
            stamp = float(value)
            if stamp > 10_000_000_000:  # milliseconds
                stamp /= 1000.0
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    text = str(value).strip()
    if not text:
        return None

    # Date-only values cannot prove the item is inside the rolling six-hour
    # window. Reject them before any parser that silently assumes midnight.
    date_only_patterns = (
        r"\d{4}-\d{2}-\d{2}",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{1,2}[-/]\d{1,2}[-/]\d{4}",
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}",
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2}",
    )
    if any(re.fullmatch(pattern, text, re.IGNORECASE) for pattern in date_only_patterns):
        return None

    # Handles ISO timestamps, date/time strings, and Unix values represented
    # as text. Naive publisher timestamps are consistently treated as UTC.
    try:
        iso_text = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    lower = text.lower()
    now = datetime.now(timezone.utc)
    if lower in {"just now", "now"}:
        return now

    # Serper and publisher pages commonly use relative labels.
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\s+ago",
        lower,
    )
    if match:
        amount = float(match.group(1))
        unit = match.group(2)
        if unit.startswith("min"):
            return now - timedelta(minutes=amount)
        if unit.startswith("hour") or unit.startswith("hr"):
            return now - timedelta(hours=amount)
        if unit.startswith("day"):
            return now - timedelta(days=amount)
        if unit.startswith("week"):
            return now - timedelta(weeks=amount)

    # dateutil is already used by the shared news search layer. Its fuzzy=False
    # mode accepts publisher variants such as "Oct 13, 2026, 10:30 AM UTC"
    # without guessing from unrelated headline text. Keep it optional for
    # environments where dateutil is not installed.
    try:
        from dateutil.parser import parse as parse_datetime
        parsed = parse_datetime(text, fuzzy=False)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ImportError, TypeError, ValueError, OverflowError):
        return None

def _global_jsonld_dates(value):
    dates = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"datepublished", "datecreated", "uploaddate"} and item:
                dates.append(item)
            dates.extend(_global_jsonld_dates(item))
    elif isinstance(value, list):
        for item in value:
            dates.extend(_global_jsonld_dates(item))
    return dates


def _global_host_allowed(url, allowed_domains):
    try:
        host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return False
    if not host:
        return False
    return any(
        host == domain or host.endswith("." + domain)
        for domain in allowed_domains
    )


def _global_listing_page(url):
    """Identify known channel/landing pages, not publishable articles."""
    try:
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/")
    except (TypeError, ValueError):
        return True

    known_source_pages = {
        urlparse(item.get("url", "")).path.lower().rstrip("/")
        for item in GLOBAL_CHANNEL_SOURCE_PAGES.values()
    }
    return (
        path in known_source_pages
        or "/news/tags/" in path
        or path.endswith("/markets")
        or path.endswith("/news")
    )


def _fetch_global_html(url, allowed_domains):
    """Fetch a public page with a short timeout; return parsed metadata."""
    if not _global_host_allowed(url, allowed_domains):
        return None

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=GLOBAL_PAGE_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not _global_host_allowed(final_url, allowed_domains):
                return None
            raw = response.read(1_000_000)
            html = raw.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None
    except Exception:
        return None

    parser = _GlobalArticleParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass

    date_candidates = list(parser.dates)
    for item in parser.jsonld:
        date_candidates.extend(_global_jsonld_dates(item))

    published = None
    for candidate in date_candidates:
        published = _global_parse_datetime(candidate)
        if published is not None:
            break

    canonical_url = (
        urljoin(final_url, parser.canonical_url)
        if parser.canonical_url
        else final_url
    )
    if not _global_host_allowed(canonical_url, allowed_domains):
        canonical_url = final_url

    links = []
    for href in parser.links:
        link = urljoin(final_url, href)
        if not link.startswith("https://"):
            continue
        if not _global_host_allowed(link, allowed_domains):
            continue
        if link not in links:
            links.append(link)

    return {
        "url": canonical_url,
        "title": " ".join(parser.title_parts).strip(),
        "content": parser.description.strip(),
        "published_at": published,
        "links": links,
    }


def _global_serper_candidates(query, allowed_domains):
    """Search allowed financial publishers and validate returned hosts locally."""
    domains = list(dict.fromkeys(
        str(domain).strip().lower()
        for domain in (allowed_domains or [])
        if str(domain).strip()
    ))
    if not domains:
        return []

    client = SerperClient()
    results = []
    seen = set()
    now = datetime.now(timezone.utc)
    after_date = (now - timedelta(days=1)).date().isoformat()
    fresh_count = 0

    # Separate site queries avoid unreliable multi-domain OR search behavior.
    domains_to_search = domains[:5] if len(domains) > 1 else domains
    for domain in domains_to_search:
        search_query = f"site:{domain} {query} after:{after_date}"
        try:
            try:
                rows = client.search_news(
                    query=search_query,
                    num=5,
                    time_range="12h",
                )
            except TypeError as exc:
                if "time_range" not in str(exc):
                    raise
                rows = client.search_news(query=search_query, num=5)
        except Exception:
            continue

        for row in rows or []:
            if not isinstance(row, dict):
                continue
            url = str(row.get("link") or row.get("url") or "").strip()
            if not url.startswith("https://") or not _global_host_allowed(url, [domain]):
                continue
            key = url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)

            # Some search results expose both a date-only value and an exact
            # timestamp. Try each field and use only a parseable timestamp.
            published = None
            for date_field in (
                "date", "publishedDate", "published_date", "published_at",
                "publishedAt", "datePublished", "date_published",
            ):
                parsed_date = _global_parse_datetime(row.get(date_field))
                if parsed_date is not None:
                    published = parsed_date
                    break
            results.append({
                "url": url,
                "title": str(row.get("title") or "").strip(),
                "source": str(row.get("source") or _domain(url)),
                "content": str(row.get("snippet") or row.get("content") or "").strip(),
                "published_at": published,
            })
            if published is not None:
                age_hours = (now - published).total_seconds() / 3600.0
                if 0 <= age_hours <= NEWS_FRESHNESS_HOURS:
                    fresh_count += 1

        if fresh_count >= 4:
            break

    return results

def _process_global_candidates(name, candidates, allowed_domains, max_results):
    """Enrich candidates from public pages; keep only articles with exact recent timestamps."""
    found = []
    seen = set()
    queue = list(candidates)
    fetch_count = 0
    now = datetime.now(timezone.utc)
    stats = {
        "candidates_seen": len(queue),
        "listing_links_added": 0,
        "host_rejected": 0,
        "pages_failed_or_unavailable": 0,
        "missing_timestamp": 0,
        "stale_timestamp": 0,
        "future_timestamp": 0,
        "headline_rejected": 0,
        "accepted": 0,
    }

    source_info = GLOBAL_CHANNEL_SOURCE_PAGES.get(name, {})
    primary_listing_url = str(source_info.get("url") or "").strip()
    effective_domains = list(allowed_domains)
    primary_domain = _domain(primary_listing_url) if primary_listing_url else ""
    if primary_domain and primary_domain not in effective_domains:
        effective_domains.append(primary_domain)
    allowed_domains = effective_domains

    if primary_listing_url and not any(
        str(item.get("url", "")).rstrip("/").lower() == primary_listing_url.rstrip("/").lower()
        for item in queue
    ):
        queue.insert(0, {
            "url": primary_listing_url,
            "title": source_info.get("name", name),
            "source": primary_domain,
            "content": "",
            "published_at": None,
        })

    def _candidate_priority(candidate):
        url = str(candidate.get("url", "")).lower()
        non_article_paths = (
            "/video/", "/quotes/", "/watch/", "youtube.com",
            "/stocks/marketstats/", "/indian-indices/", "/india/stockpricequote/",
        )
        is_non_article = any(item in url for item in non_article_paths)
        published = _global_parse_datetime(candidate.get("published_at"))
        published_rank = published.timestamp() if published is not None else 0
        has_news_path = any(item in url for item in ("/news/", "/markets/", "/global-indices/"))
        if primary_listing_url and url.rstrip("/") == primary_listing_url.rstrip("/").lower():
            return (3, published_rank, 1)
        return (2 if candidate.get("_from_listing") else (0 if is_non_article else 1),
                published_rank, 1 if has_news_path else 0)

    queue.sort(key=_candidate_priority, reverse=True)
    while queue and len(found) < max_results and fetch_count < GLOBAL_MAX_PAGE_FETCHES:
        queue.sort(key=_candidate_priority, reverse=True)
        candidate = queue.pop(0)
        url = str(candidate.get("url") or "").strip()
        if not _global_host_allowed(url, allowed_domains):
            stats["host_rejected"] += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        listing = _global_listing_page(url)
        lowered_url = url.lower()
        if not listing and any(part in lowered_url for part in (
            "/video/", "/quotes/", "/watch/", "youtube.com",
            "/stocks/marketstats/", "/indian-indices/", "/india/stockpricequote/",
        )):
            continue

        published = _global_parse_datetime(candidate.get("published_at"))
        page = None
        if listing or published is None or not candidate.get("title"):
            fetch_count += 1
            page = _fetch_global_html(url, allowed_domains)
            if page is None:
                stats["pages_failed_or_unavailable"] += 1

        if listing:
            if page:
                for link in page.get("links", []):
                    link = str(link).strip().split("#", 1)[0]
                    lowered = link.lower()
                    if not _global_host_allowed(link, allowed_domains) or _global_listing_page(link) or link in seen:
                        continue
                    if "/news/" not in lowered or ".html" not in lowered:
                        continue
                    if any(part in lowered for part in (
                        "/news/tags/", "/news/videos/", "/video/", "/quotes/",
                        "/watch/", "youtube.com", "/stocks/marketstats/",
                        "/indian-indices/", "/india/stockpricequote/",
                    )):
                        continue
                    if any(item.get("url") == link for item in queue):
                        continue
                    queue.append({
                        "url": link,
                        "title": "",
                        "source": _domain(link),
                        "content": "",
                        "published_at": None,
                        "_from_listing": True,
                    })
                    stats["listing_links_added"] += 1
                    stats["candidates_seen"] += 1
            continue

        title = str(candidate.get("title") or (page or {}).get("title") or "").strip()
        if name in GLOBAL_MARKET_KEYS:
            headline = " ".join(title.casefold().split())
            unrelated = (
                "delhi protests", "india bloc", "rahul gandhi", "kejriwal",
                "full speech: pm modi", "pm modi announces", "chennai metro gets",
                "registers fir", "police complaint", "fighter jet", "title fight",
            )
            if any(term in headline for term in unrelated):
                continue
            market_terms = (
                "market", "markets", "stock", "stocks", "equity", "equities", "index", "indices",
                "sensex", "nifty", "nasdaq", "dow jones", "s&p 500", "ftse", "dax", "nikkei",
                "hang seng", "kospi", "shanghai composite", "wall street", "shares", "bonds",
                "bond sell", "bond yields", "treasury yields", "monetary policy", "dollar index",
                "currency", "forex", "crude oil", "oil prices", "brent", "futures", "central bank",
                "federal reserve", "tsmc", "semiconductor", "chipmaker", "ai stocks", "earnings season",
                "sell-off", "selloff", "sell off", "rally", "global economy", "world economy",
                "financial markets", "global trade", "emerging markets",
            )
            if not any(term in headline for term in market_terms):
                stats["headline_rejected"] += 1
                continue

        content = str(candidate.get("content") or (page or {}).get("content") or "").strip()
        article_url = str((page or {}).get("url") or url).strip()
        published = published or _global_parse_datetime((page or {}).get("published_at"))
        if published is None:
            stats["missing_timestamp"] += 1
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        published = published.astimezone(timezone.utc)
        age_hours = (now - published).total_seconds() / 3600.0
        if age_hours < 0:
            stats["future_timestamp"] += 1
            continue
        if age_hours > NEWS_FRESHNESS_HOURS:
            stats["stale_timestamp"] += 1
            continue

        found.append({
            "title": title,
            "url": article_url,
            "source": _domain(article_url),
            "content": content,
            "snippet": content,
            "published_at": published.isoformat(),
            "published_date": published.isoformat(),
            "age_hours": round(age_hours, 3),
        })
        stats["accepted"] += 1

    return found[:max_results], fetch_count, stats

def _search_global_channel_news(name, query, max_results):
    """Moneycontrol-first global-news search with a trusted-publisher fallback."""
    diagnostics = []
    primary_domains = ["moneycontrol.com"]
    source_page = GLOBAL_CHANNEL_SOURCE_PAGES.get(name, {}).get("url")

    try:
        primary_candidates = _global_serper_candidates(
            query=f"{query} latest news",
            allowed_domains=primary_domains,
        )
    except Exception as exc:
        primary_candidates = []
        diagnostics.append(f"Moneycontrol search error: {type(exc).__name__}: {str(exc)[:120]}")

    if source_page and not any(item.get("url") == source_page for item in primary_candidates):
        primary_candidates.insert(0, {
            "url": source_page,
            "title": "",
            "source": "moneycontrol.com",
            "content": "",
            "published_at": None,
        })

    primary, fetched, primary_stats = _process_global_candidates(
        name, primary_candidates, primary_domains, max_results
    )
    primary_timestamped = sum(
        1 for item in primary_candidates
        if _global_parse_datetime(item.get("published_at")) is not None
    )
    diagnostics.append(
        f"Moneycontrol: candidates={len(primary_candidates)}, "
        f"Serper timestamps parsed={primary_timestamped}, pages fetched={fetched}, "
        f"listing links={primary_stats['listing_links_added']}, fresh={len(primary)}, "
        f"missing timestamp={primary_stats['missing_timestamp']}, "
        f"older than 12h={primary_stats['stale_timestamp']}, "
        f"future timestamp={primary_stats['future_timestamp']}, "
        f"unavailable pages={primary_stats['pages_failed_or_unavailable']}"
    )

    try:
        fallback_candidates = _global_serper_candidates(
            query=f"{query} global world stock markets latest financial news",
            allowed_domains=GLOBAL_FALLBACK_DOMAINS,
        )
    except Exception as exc:
        fallback_candidates = []
        diagnostics.append(f"Trusted-source search error: {type(exc).__name__}: {str(exc)[:120]}")

    fallback, fetched, fallback_stats = _process_global_candidates(
        name, fallback_candidates, GLOBAL_FALLBACK_DOMAINS, max_results
    )
    fallback_timestamped = sum(
        1 for item in fallback_candidates
        if _global_parse_datetime(item.get("published_at")) is not None
    )
    diagnostics.append(
        f"Trusted sources: candidates={len(fallback_candidates)}, "
        f"Serper timestamps parsed={fallback_timestamped}, pages fetched={fetched}, "
        f"listing links={fallback_stats['listing_links_added']}, fresh={len(fallback)}, "
        f"missing timestamp={fallback_stats['missing_timestamp']}, "
        f"older than 12h={fallback_stats['stale_timestamp']}, "
        f"future timestamp={fallback_stats['future_timestamp']}, "
        f"unavailable pages={fallback_stats['pages_failed_or_unavailable']}"
    )

    combined = []
    seen_urls = set()
    for article in primary + fallback:
        url = str(article.get("url") or "").strip()
        key = url.split("?", 1)[0].rstrip("/").lower()
        if key.endswith("/amp"):
            key = key[:-4].rstrip("/")
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        copy = dict(article)
        copy["news_channel"] = name
        copy["news_channels"] = [name]
        tags = copy.get("sectors") or []
        if isinstance(tags, str):
            tags = [tags]
        else:
            tags = list(tags)
        if name not in {str(tag).upper() for tag in tags}:
            tags.append(name)
        copy["sectors"] = tags
        combined.append(copy)
        if len(combined) >= max(1, int(max_results)):
            break

    if primary and fallback:
        method = "Moneycontrol + trusted-source fallback"
    elif primary:
        method = "Moneycontrol"
    elif fallback:
        method = "trusted-source fallback"
    else:
        method = "no fresh articles"
    return combined, method, diagnostics

def _search_channel_news(name, query, max_results):
    """Use the existing fresh-news search for sectors and strict retrieval for global channels."""
    if name in GLOBAL_MARKET_KEYS:
        return _search_global_channel_news(name, query, max_results)

    rows = search_topic_news(
        query=query,
        max_results=max_results,
        time_range="12h",
    )
    return rows, "standard search", []


# ============================================================
# SINGLE-SECTOR SEARCH
# ============================================================

def search_sector_news(
    sector_key: str,
    max_results: int = 5,
) -> list[dict]:
    """Backward-compatible single-sector search.

    Only the last 12 hours are allowed.
    """

    query = SECTOR_QUERIES.get(
        sector_key,
        f"{sector_key} India latest financial news",
    )

    try:
        raw, search_mode, search_details = _search_channel_news(
            sector_key,
            query,
            max_results,
        )
        for detail in search_details:
            print(f"[{sector_key}] {detail}")

    except Exception as exc:
        print(
            f"Sector news unavailable for "
            f"{sector_key}: "
            f"{type(exc).__name__}: {exc}"
        )

        return []

    reference = datetime.now(
        timezone.utc
    )

    results: list[dict] = []

    for item in raw:

        published = (
            item.get("published_at")
            or item.get("published_date")
        )

        if not _is_recent_1h(
            published,
            reference,
        ):
            continue

        normalized = _normalize_item(
            item,
            forced_sector=sector_key,
        )

        if (
            normalized["url"]
            and normalized["title"]
            and normalized.get("published_at")
        ):
            results.append(
                normalized
            )

        if len(results) >= max_results:
            break

    return results


# ============================================================
# SEPARATE MACRO-FACTOR NEWS COLLECTION FOR TELEGRAM
# ============================================================
def collect_macro_factor_news(
    max_results_per_factor: int = 2,
) -> tuple[dict[str, list[dict]], list[str]]:
    """Fetch the screenshot's 11 macro factors independently with a strict 12h window.

    Returns a mapping of factor label -> verified fresh articles, plus non-secret
    diagnostics. Results are intentionally not passed into market sentiment scoring.
    Per-factor exceptions are isolated so one failed query does not stop the other 10.
    """
    results: dict[str, list[dict]] = {}
    diagnostics: list[str] = []
    reference = datetime.now(timezone.utc)
    limit = max(1, min(int(max_results_per_factor), 5))

    for factor_name, query in FACTOR_NEWS_QUERIES.items():
        factor_articles: list[dict] = []
        seen_urls: set[str] = set()
        try:
            # search_topic_news performs Serper's broad retrieval and strict local
            # timestamp/URL checks for the requested rolling 12-hour window.
            rows = search_topic_news(
                query=query,
                max_results=limit,
                time_range="12h",
            )
            for item in rows:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                published = item.get("published_at") or item.get("published_date")
                if not title or not url or not url.lower().startswith(("http://", "https://")):
                    continue
                if not _is_recent_1h(published, reference):
                    continue
                parsed = urlparse(url)
                canonical = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}".rstrip("/")
                if canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                factor_articles.append({
                    "factor": factor_name,
                    "title": title,
                    "url": url,
                    "source": str(item.get("source") or _domain(url) or "Source not provided").strip(),
                    "published_at": _published_date(published).isoformat() if _published_date(published) else str(published),
                    "content": str(item.get("content") or item.get("snippet") or "").strip()[:450],
                })
            factor_articles.sort(
                key=lambda article: _published_date(article.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            results[factor_name] = factor_articles[:limit]
            diagnostics.append(
                f"Macro-factor news {factor_name}: {len(results[factor_name])} verified article(s) in last 12h"
            )
        except Exception as exc:
            results[factor_name] = []
            diagnostics.append(
                f"Macro-factor news {factor_name}: ERROR {type(exc).__name__}: {str(exc)[:150]}"
            )

    return results, diagnostics


# ============================================================
# SHARED COLLECTION: MARKET + 22 NEWS CHANNELS
# ============================================================

def collect_sector_news(
    max_results_per_query: int = 4,
):
    """Collect one shared recent-news pool for the 20 industry sectors plus 2 global-market channels.

    Every MARKET / sector query asks Serper for live results.

    Only articles published within the previous 12 hours
    are allowed into the shared pool.
    """

    diagnostics: list[str] = []

    raw_items: list[
        tuple[str, dict]
    ] = []

    all_queries = {
        "MARKET": MACRO_QUERY,
        **SECTOR_QUERIES,
    }

    reference = datetime.now(
        timezone.utc
    )

    # --------------------------------------------------------
    # One live Serper query per market/sector topic
    # --------------------------------------------------------
    for name, query in all_queries.items():
        try:
            raw, search_mode, search_details = _search_channel_news(
                name,
                query,
                max_results_per_query,
            )

            for detail in search_details:
                diagnostics.append(f"News query {name}: {detail}")

            diagnostics.append(
                f"News query {name}: {len(raw)} recent result(s) "
                f"from last 12h; method={search_mode}"
            )

            for item in raw:
                raw_items.append((name, item))

        except Exception as exc:
            diagnostics.append(
                f"News query {name}: ERROR "
                f"{type(exc).__name__}: {str(exc)[:160]}"
            )

    # --------------------------------------------------------
    # Normalize + defensive final freshness check. Deduplicate URLs, but
    # merge the query/channel provenance when the same article appears in
    # more than one query. This prevents first-query-wins from losing tags.
    # --------------------------------------------------------
    by_url: dict[str, dict] = {}

    for query_name, item in raw_items:
        published = item.get("published_at") or item.get("published_date")
        if not _is_recent_1h(published, reference):
            continue

        normalized = _normalize_item(
            item, None if query_name == "MARKET" else query_name
        )
        if (
            not normalized.get("url")
            or not normalized.get("title")
            or not normalized.get("published_at")
        ):
            continue

        # Strip tracking query/fragment and common AMP suffixes for identity.
        parsed = urlparse(normalized["url"])
        key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}".rstrip("/")
        key = key[:-4].rstrip("/") if key.lower().endswith("/amp") else key
        if not key:
            continue

        query_channel = query_name if query_name != "MARKET" else None
        if query_channel:
            normalized["news_channel"] = query_channel
            normalized["news_channels"] = [query_channel]
        else:
            normalized["news_channel"] = ""
            normalized["news_channels"] = []

        if key not in by_url:
            by_url[key] = normalized
            continue

        existing = by_url[key]
        for field in ("sectors", "news_channels"):
            merged = list(existing.get(field) or [])
            incoming = normalized.get(field) or []
            if isinstance(merged, str):
                merged = [merged]
            if isinstance(incoming, str):
                incoming = [incoming]
            for tag in incoming:
                if tag and tag not in merged:
                    merged.append(tag)
            existing[field] = merged
        channels = existing.get("news_channels") or []
        existing["news_channel"] = channels[0] if channels else ""

    articles: list[dict] = list(by_url.values())

    # --------------------------------------------------------
    # Final diagnostics
    # --------------------------------------------------------
    diagnostics.append(
        f"News articles collected: "
        f"{len(articles)} unique recent articles"
    )

    diagnostics.append(
        f"News sources used: "
        f"{len({a['source'] for a in articles if a.get('source')})}"
    )

    # A direct global search can return zero timestamp-verified articles while
    # the shared MARKET query still contains recent articles about indices.
    # Report both counts explicitly rather than implying the final channel
    # score must be zero merely because a dedicated query found nothing.
    for channel in sorted(GLOBAL_MARKET_KEYS):
        tagged_count = sum(
            1 for article in articles
            if channel in {str(tag).upper() for tag in (article.get("sectors") or [])}
        )
        diagnostics.append(
            f"Global channel {channel}: {tagged_count} fresh article(s) tagged across shared news pool"
        )

    return (
        articles,
        diagnostics,
    )


# ============================================================
# PUBLIC EXPORTS
# ============================================================

__all__ = [
    "MACRO_QUERY",
    "SECTOR_QUERIES",
    "SECTOR_TERMS",
    "FACTOR_NEWS_QUERIES",
    "search_sector_news",
    "collect_sector_news",
    "collect_macro_factor_news",
]