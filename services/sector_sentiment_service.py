"""Sector sentiment analysis using one shared Serper news collection.

The public build_sector_report() interface is preserved for the existing
market-sentiment pipeline.  News is collected once and then reused for all
five dashboard sectors, so the project does not perform one separate provider
call per sector.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from config.llm_config import LLM_MODE, SPECIALIST_LLM
from services.sector_news_service import collect_sector_news

logger = logging.getLogger(__name__)


# ============================================================
# FIVE DASHBOARD SECTORS
# ============================================================

SECTOR_DEFINITIONS = {
    "banking_financial_services": {
        "sector": "Banking & Financial Services",
        "members": {"BANKING", "NBFC"},
        "baseline": -0.55,
        "baseline_sentiment": "Bearish to Neutral",
        "global_drivers": [
            "US bond yields",
            "FII institutional flows",
            "interest-rate expectations",
            "credit and liquidity conditions",
        ],
        "outlook": (
            "News-adjusted banking sentiment based on RBI, credit, "
            "asset-quality and rate developments."
        ),
    },
    "information_technology": {
        "sector": "Information Technology",
        "members": {"IT"},
        "baseline": 0.05,
        "baseline_sentiment": "Neutral / Defensive",
        "global_drivers": [
            "Nasdaq movement",
            "US technology spending",
            "Fed rate expectations",
            "USD strength",
            "enterprise IT spending",
        ],
        "outlook": (
            "News-adjusted IT sentiment based on technology demand, "
            "AI spending, exports and global risk conditions."
        ),
    },
    "pharmaceuticals_healthcare": {
        "sector": "Pharmaceuticals & Healthcare",
        "members": {"PHARMA", "HEALTHCARE"},
        "baseline": 0.55,
        "baseline_sentiment": "Bullish (Defensive Pivot)",
        "global_drivers": [
            "safe-haven rotation",
            "global uncertainty",
            "healthcare demand",
            "defensive allocation",
        ],
        "outlook": (
            "News-adjusted pharma and healthcare sentiment based on "
            "regulation, demand and defensive characteristics."
        ),
    },
    "automobiles_consumer_retail": {
        "sector": "Automobiles & Consumer Retail",
        "members": {"AUTO", "FMCG", "RETAIL", "CONSUMER_DURABLES"},
        "baseline": 0.55,
        "baseline_sentiment": "Bullish",
        "global_drivers": [
            "oil prices",
            "consumer demand",
            "EV adoption",
            "input costs",
        ],
        "outlook": (
            "News-adjusted auto and consumer sentiment based on sales, "
            "fuel costs, demand and input-price developments."
        ),
    },
    "oil_gas_energy": {
        "sector": "Oil & Gas / Energy",
        "members": {"OIL_UPSTREAM", "OMC"},
        "baseline": -0.55,
        "baseline_sentiment": "Bearish to Mixed",
        "global_drivers": [
            "crude-price movement",
            "refining margins",
            "geopolitics",
            "domestic fuel pricing",
        ],
        "outlook": (
            "News-adjusted energy sentiment based on crude, refining, "
            "fuel-price and geopolitical developments."
        ),
    },
}


# ============================================================
# DETERMINISTIC SCORING
# ============================================================


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _label(score: float) -> str:
    if score >= 0.35:
        return "Bullish"
    if score <= -0.35:
        return "Bearish"
    return "Neutral"


def _baseline_score(label: str) -> float:
    text = str(label or "").lower()
    if "bullish" in text:
        return 0.55
    if "bearish" in text:
        return -0.55
    if "mildly bullish" in text:
        return 0.30
    return 0.0


def _article_matches(article: dict[str, Any], members: set[str]) -> bool:
    article_sectors = {
        str(item).upper().strip()
        for item in (article.get("sectors") or [])
    }
    return bool(article_sectors & members)


def _news_adjustment(articles: list[dict[str, Any]]) -> float:
    if not articles:
        return 0.0

    weighted = 0.0
    total_weight = 0.0

    for article in articles:
        try:
            direction = float(article.get("india_direction", 0.0) or 0.0)
            relevance = float(article.get("relevance", 0.5) or 0.5)
            confidence = float(article.get("confidence", 0.5) or 0.5)
            reliability = float(article.get("reliability", 0.7) or 0.7)
        except (TypeError, ValueError):
            direction = 0.0
            relevance = 0.5
            confidence = 0.5
            reliability = 0.7

        weight = max(0.05, relevance * confidence * reliability)
        weighted += _clamp(direction) * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return _clamp(weighted / total_weight)


# ============================================================
# MOCK / DEVELOPMENT MODE
# ============================================================


def _mock_sector_result(
    sector_key: str,
    news: list[dict[str, Any]],
) -> dict[str, Any]:
    definition = SECTOR_DEFINITIONS[sector_key]

    text_parts: list[str] = []
    for item in news:
        text_parts.append(str(item.get("title", "")))
        text_parts.append(str(item.get("content", "")))

    text = " ".join(text_parts).lower()
    positive_words = {
        "growth", "strong", "positive", "buying", "buy", "outperform",
        "support", "supportive", "improves", "improvement", "recovery",
        "demand", "bullish", "beat", "rise", "rises", "gains", "higher",
        "record", "surge", "rally", "easing", "stimulus", "upgrade",
        "inflow", "inflows",
    }
    negative_words = {
        "sell", "selling", "weak", "negative", "bearish", "uncertainty",
        "risk", "risks", "inflation", "pressure", "slowdown", "outflow",
        "outflows", "geopolitical", "volatility", "decline", "declining",
        "fall", "falls", "drop", "drops", "loss", "losses", "hike",
        "tariff", "war", "recession", "downgrade", "lower", "down",
    }

    tokens = [token.strip(".,:;()[]{}\"'") for token in text.split()]
    positive = sum(1 for token in tokens if token in positive_words)
    negative = sum(1 for token in tokens if token in negative_words)
    total = positive + negative

    news_score = 0.0 if total == 0 else _clamp((positive - negative) / total)
    baseline = float(definition["baseline"])

    # Baseline preserves the configured sector characteristics, while current
    # Serper evidence can move the score when news is available.
    final_score = _clamp(
        baseline if not news else (0.40 * baseline + 0.60 * news_score)
    )

    return {
        "sector_key": sector_key,
        "sector": definition["sector"],
        "sentiment": _label(final_score),
        "sentiment_score": round(final_score, 3),
        "baseline_sentiment": definition["baseline_sentiment"],
        "global_drivers": definition["global_drivers"],
        "outlook": definition["outlook"],
        "news_count": len(news),
        "news": news[:5],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if LLM_MODE == "mock" else "baseline-fallback",
        "news_score": round(news_score, 3),
    }


# ============================================================
# OPTIONAL CREWAI LIVE MODE
# ============================================================


def _live_sector_result(
    sector_key: str,
    news: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the existing CrewAI specialist against shared news evidence."""
    if SPECIALIST_LLM is None:
        raise RuntimeError("SPECIALIST_LLM is not configured")

    from crewai import Agent, Crew, Process, Task

    definition = SECTOR_DEFINITIONS[sector_key]
    news_payload = json.dumps(news[:8], indent=2, default=str)

    agent = Agent(
        role="Sector Financial Sentiment Analyst",
        goal=(
            "Analyze recent financial news and determine the current sentiment "
            "of an Indian market sector."
        ),
        backstory=(
            "You are a financial research specialist focused on Indian equities, "
            "global macro drivers and sector rotation."
        ),
        llm=SPECIALIST_LLM,
        verbose=False,
    )

    task = Task(
        description=f"""
Analyze this sector.

Sector: {definition['sector']}

Baseline context:
{definition['baseline_sentiment']}

Global drivers:
{definition['global_drivers']}

Outlook:
{definition['outlook']}

Recent Serper financial news:
{news_payload}

Return ONLY valid JSON:
{{
  "sentiment": "Bullish | Neutral | Bearish",
  "sentiment_score": 0.0,
  "key_drivers": ["..."],
  "outlook": "...",
  "reasoning": "..."
}}
""",
        expected_output="Valid JSON only.",
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    raw = str(crew.kickoff()).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "sentiment": _label(float(definition["baseline"])),
            "sentiment_score": float(definition["baseline"]),
            "key_drivers": definition["global_drivers"],
            "outlook": definition["outlook"],
            "reasoning": raw,
        }

    try:
        live_score = _clamp(float(parsed.get("sentiment_score", 0.0)))
    except (TypeError, ValueError):
        live_score = float(definition["baseline"])

    sentiment = str(parsed.get("sentiment") or _label(live_score))
    if sentiment not in {"Bullish", "Neutral", "Bearish"}:
        sentiment = _label(live_score)

    return {
        "sector_key": sector_key,
        "sector": definition["sector"],
        "sentiment": sentiment,
        "sentiment_score": round(live_score, 3),
        "baseline_sentiment": definition["baseline_sentiment"],
        "global_drivers": parsed.get("key_drivers") or definition["global_drivers"],
        "outlook": parsed.get("outlook") or definition["outlook"],
        "reasoning": str(parsed.get("reasoning") or ""),
        "news_count": len(news),
        "news": news[:5],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live",
    }


# ============================================================
# PUBLIC API
# ============================================================


def analyze_sector(
    sector_key: str,
    articles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze one sector using already-collected news when supplied."""
    if sector_key not in SECTOR_DEFINITIONS:
        raise ValueError(f"Unknown sector key: {sector_key}")

    diagnostics: list[str] = []
    source_articles = articles

    if source_articles is None:
        try:
            source_articles, diagnostics = collect_sector_news(
                max_results_per_query=4
            )
        except Exception as exc:
            source_articles = []
            diagnostics = [
                f"Sector news collection failed: {type(exc).__name__}: {exc}"
            ]

    definition = SECTOR_DEFINITIONS[sector_key]
    matched = [
        article
        for article in source_articles
        if isinstance(article, dict)
        and _article_matches(article, definition["members"])
    ]

    matched.sort(
        key=lambda item: float(item.get("relevance", 0.0) or 0.0),
        reverse=True,
    )

    if LLM_MODE == "live" and SPECIALIST_LLM is not None:
        try:
            result = _live_sector_result(sector_key, matched)
        except Exception as exc:
            logger.warning(
                "Live sector LLM failed for %s: %s. Using deterministic fallback.",
                sector_key,
                str(exc)[:200],
            )
            result = _mock_sector_result(sector_key, matched)
            result["mode"] = "live-fallback"
            result["error"] = f"{type(exc).__name__}: {exc}"
    else:
        result = _mock_sector_result(sector_key, matched)

    result["diagnostics"] = diagnostics
    return result


def build_sector_report() -> list[dict[str, Any]]:
    """Build the five dashboard sectors from one shared Serper collection."""
    try:
        shared_articles, diagnostics = collect_sector_news(
            max_results_per_query=3
        )
    except Exception as exc:
        shared_articles = []
        diagnostics = [
            f"Sector news collection failed: {type(exc).__name__}: {exc}"
        ]

    report: list[dict[str, Any]] = []

    for sector_key, definition in SECTOR_DEFINITIONS.items():
        try:
            item = analyze_sector(sector_key, shared_articles)
            item["collection_diagnostics"] = diagnostics
            report.append(item)
        except Exception as exc:
            logger.exception("Sector analysis failed for %s", sector_key)
            baseline = float(definition["baseline"])
            report.append(
                {
                    "sector_key": sector_key,
                    "sector": definition["sector"],
                    "sentiment": _label(baseline),
                    "sentiment_score": round(baseline, 3),
                    "baseline_sentiment": definition["baseline_sentiment"],
                    "global_drivers": definition["global_drivers"],
                    "outlook": definition["outlook"],
                    "news_count": 0,
                    "news": [],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "baseline-fallback",
                    "error": f"{type(exc).__name__}: {exc}",
                    "collection_diagnostics": diagnostics,
                }
            )

    return report


__all__ = [
    "SECTOR_DEFINITIONS",
    "analyze_sector",
    "build_sector_report",
]
