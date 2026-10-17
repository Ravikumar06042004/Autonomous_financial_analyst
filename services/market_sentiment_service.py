"""Global market cues + Indian market sentiment.

This is the final 20-sector market sentiment layer for the existing
``autonomous_financial_analyst`` project.

Public interfaces kept for the existing application:
    build_market_sentiment_report(...)
    run_market_sentiment(...)
    print_market_sentiment(...)
    console_report(...)

Final report files:
    output/report.txt
    output/report.html
    output/report.json

News: Serper through services.sector_news_service.collect_sector_news().
Tavily is not used here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import html
import json
import logging
import math
import os
from typing import Any

from dotenv import load_dotenv

from config.sector_config import load_sector_rules
from database.repository import (
    get_latest_market_sentiment_report,
    save_market_sentiment_report,
)
from services.sector_news_service import collect_sector_news
from tools.macro_market_data import fetch_macro_market_data

load_dotenv(override=True)

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
SETTINGS_PATH = BASE_DIR / "config" / "market_sentiment_settings.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"

# Only articles published in this rolling window may enter the report or score.
NEWS_FRESHNESS_HOURS = 12


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone offset.")
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _label(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT_DATA"
    if score >= 65:
        return "STRONG_BULLISH"
    if score >= 35:
        return "BULLISH"
    if score >= 15:
        return "MILD_BULLISH"
    if score <= -65:
        return "STRONG_BEARISH"
    if score <= -35:
        return "BEARISH"
    if score <= -15:
        return "MILD_BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _load_settings() -> dict[str, Any]:
    config = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    profiles = config.get("profiles")

    if isinstance(profiles, dict) and profiles:
        profile = os.getenv(
            "MARKET_SENTIMENT_PROFILE",
            config.get("profile", "free"),
        ).strip().lower()
        if profile not in profiles:
            raise ValueError(f"Unknown MARKET_SENTIMENT_PROFILE: {profile}")
        config["profile"] = profile
        config["group_weights"] = dict(profiles[profile])

    weights = config.get("group_weights", {})
    if not isinstance(weights, dict) or not weights:
        raise ValueError("group_weights are missing from market sentiment settings.")

    config["group_weights"] = {k: float(v) for k, v in weights.items()}
    if abs(sum(config["group_weights"].values()) - 1.0) > 1e-9:
        raise ValueError("Market sentiment group weights must sum to 1.")

    config.setdefault("window_hours", 16)
    config.setdefault("minimum_coverage", 0.55)
    return config


# ---------------------------------------------------------------------------
# Macro collector compatibility
# ---------------------------------------------------------------------------

LEGACY_FACTOR_NAMES = {
    "brent_crude": "brent",
    "us_10y_yield": "us10y",
    "usd": "dxy",
    "usd_inr": "usd_inr",
    "sp500": "sp500",
    "nasdaq": "nasdaq",
    "asia_index": "asia_index",
    "fii_cash": "fii_cash",
    "fii_futures": "fii_futures",
    "dii_cash": "dii_cash",
    "india_vix": "india_vix",
    "cpi_surprise": "cpi_surprise",
    "pmi_surprise": "pmi_surprise",
    "rbi_rate_surprise": "rbi_rate_surprise",
    "gift_nifty": "gift_nifty",
    "nifty": "nifty",
    "advance_decline": "advance_decline",
}

UNIT_ALIASES = {
    # Percentage / yield units
    "%": "percent",
    "pct": "percent",
    "percent": "percent",

    # Index-style units returned by the legacy collector
    "index": "index",
    "points": "index",
    "dxy": "index",

    # Brent / crude legacy unit variants
    "usd/barrel": "USD_per_barrel",
    "$/barrel": "USD_per_barrel",
    "$ /barrel": "USD_per_barrel",
    "$ / barrel": "USD_per_barrel",
    "usd_per_barrel": "USD_per_barrel",
    "usd per barrel": "USD_per_barrel",

    # FX legacy unit variants
    "inr/usd": "INR_per_USD",
    "₹/$": "INR_per_USD",
    "inr_per_usd": "INR_per_USD",

    # Other configured model units
    "inr_crore": "INR_crore",
    "contracts_net_change": "contracts_net_change",
    "percentage_points": "percentage_points",
    "index_points": "index_points",
    "bps": "bps",
    "ratio": "ratio",
}


def _canonical_unit(unit: Any) -> str:
    text = str(unit or "").strip()
    return UNIT_ALIASES.get(text.lower(), text)


def _normalize_macro_observations(macro_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept the old ``factors`` shape and the normalized observation shape."""
    observations: list[dict[str, Any]] = []
    now = _utc_now().isoformat()

    for item in macro_data.get("observations", []) or []:
        if not isinstance(item, dict):
            continue
        factor = str(item.get("factor", "")).strip()
        if not factor:
            continue
        copy = dict(item)
        copy["factor"] = LEGACY_FACTOR_NAMES.get(factor, factor)
        copy["unit"] = _canonical_unit(copy.get("unit"))
        observations.append(copy)

    factors = macro_data.get("factors", {})
    if isinstance(factors, dict):
        for raw_factor, item in factors.items():
            if not isinstance(item, dict) or item.get("value") is None:
                continue
            factor = LEGACY_FACTOR_NAMES.get(str(raw_factor), str(raw_factor))
            observations.append({
                "factor": factor,
                "value": item.get("value"),
                "previous": (
                    item.get("previous")
                    if item.get("previous") is not None
                    else item.get("previous_value")
                ),
                "unit": _canonical_unit(item.get("unit")),
                "observed_at": item.get("observed_at", now),
                "available_at": item.get("available_at", now),
                "source": item.get("source", "Yahoo Finance via yfinance"),
            })

    return observations


# ---------------------------------------------------------------------------
# Factor validation / scoring
# ---------------------------------------------------------------------------

def _latest_valid(
    observations: list[dict[str, Any]],
    asof: datetime,
    factor_config: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    latest: dict[str, dict[str, Any]] = {}
    diagnostics: list[str] = []

    for raw in observations:
        if not isinstance(raw, dict):
            continue
        factor = str(raw.get("factor", "")).strip()
        cfg = factor_config.get(factor)
        if not cfg:
            diagnostics.append(f"Unknown factor ignored: {factor}")
            continue

        expected_unit = _canonical_unit(cfg.get("unit"))
        actual_unit = _canonical_unit(raw.get("unit"))
        if expected_unit != actual_unit:
            diagnostics.append(
                f"Unit mismatch: {factor} (expected {expected_unit}, got {actual_unit})"
            )
            continue

        value = _safe_float(raw.get("value"))
        if value is None:
            diagnostics.append(f"Invalid value: {factor}")
            continue

        try:
            observed_at = _parse_timestamp(raw["observed_at"])
            available_at = _parse_timestamp(raw["available_at"])
        except Exception:
            diagnostics.append(f"Invalid timestamps: {factor}")
            continue

        if observed_at > asof or available_at > asof:
            diagnostics.append(f"Future/unavailable observation: {factor}")
            continue
        if available_at < observed_at:
            diagnostics.append(f"Availability precedes observation: {factor}")
            continue

        age_hours = max(0.0, (asof - observed_at).total_seconds() / 3600.0)
        if age_hours > float(cfg.get("max_age_hours", 24)):
            diagnostics.append(f"Stale factor: {factor} ({age_hours:.1f}h)")
            continue

        copy = dict(raw)
        copy["factor"] = factor
        copy["value"] = value
        copy["unit"] = expected_unit
        copy["observed_at"] = observed_at.isoformat()
        copy["available_at"] = available_at.isoformat()

        if factor not in latest or observed_at > _parse_timestamp(latest[factor]["observed_at"]):
            latest[factor] = copy

    for factor in factor_config:
        if factor not in latest:
            diagnostics.append(f"Missing usable factor: {factor}")

    return latest, diagnostics


def _factor_signal(obs: dict[str, Any], cfg: dict[str, Any]) -> float | None:
    value = _safe_float(obs.get("value"))
    if value is None:
        return None

    previous = _safe_float(obs.get("previous"))
    mode = cfg.get("mode", "pct_change")

    if mode == "pct_change":
        if previous is None or previous == 0:
            return None
        move = 100.0 * (value / previous - 1.0)
    elif mode == "bps_change":
        if previous is None:
            return None
        move = 100.0 * (value - previous)
    elif mode == "level":
        neutral = _safe_float(cfg.get("neutral", 0)) or 0.0
        move = value - neutral
    else:
        raise ValueError(f"Unsupported factor mode: {mode}")

    scale = _safe_float(cfg.get("scale"))
    if scale is None or scale <= 0:
        return None

    return _clamp(move / scale) * int(cfg.get("polarity", 1))


# ---------------------------------------------------------------------------
# News scoring
# ---------------------------------------------------------------------------

def _deduplicate_news(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}

    def _canonical_url(value: Any) -> str:
        key = str(value or "").split("?", 1)[0].rstrip("/").lower()
        if key.endswith("/amp"):
            key = key[:-4].rstrip("/")
        return key

    def _as_list(value: Any) -> list:
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple, set)) else [value]

    for item in articles or []:
        if not isinstance(item, dict):
            continue

        copy = dict(item)
        copy["url"] = str(copy.get("url") or copy.get("link") or "")
        copy["content"] = str(copy.get("content") or copy.get("snippet") or "")
        copy["published_at"] = copy.get("published_at") or copy.get("published_date")
        copy["sectors"] = _as_list(copy.get("sectors"))

        channels = _as_list(copy.get("news_channels"))
        for field in ("news_channel", "channel"):
            if copy.get(field):
                channels.extend(_as_list(copy[field]))
        copy["news_channels"] = list(dict.fromkeys(
            str(value).upper() for value in channels if value
        ))

        key = _canonical_url(copy["url"]) or str(copy.get("title") or "").strip().casefold()
        if not key:
            continue

        existing = by_key.get(key)
        if existing is None:
            by_key[key] = copy
            output.append(copy)
            continue

        for field in ("sectors", "news_channels"):
            values = _as_list(existing.get(field))
            known = {str(value).upper() for value in values}
            for value in _as_list(copy.get(field)):
                if str(value).upper() not in known:
                    values.append(value)
                    known.add(str(value).upper())
            existing[field] = values

        for field in ("news_channel", "channel"):
            if not existing.get(field) and copy.get(field):
                existing[field] = copy[field]

        try:
            old_confidence = float(existing.get("confidence", 0.5))
            new_confidence = float(copy.get("confidence", 0.5))
        except (TypeError, ValueError):
            old_confidence = new_confidence = 0.5

        if new_confidence > old_confidence:
            sectors = existing["sectors"]
            channels = existing["news_channels"]
            existing.update(copy)
            existing["sectors"] = sectors
            existing["news_channels"] = channels

    return output


def _filter_recent_news(
    articles: list[dict[str, Any]],
    asof: datetime,
) -> list[dict[str, Any]]:
    """Keep only uniquely identified articles with verifiable timestamps in the last hour."""
    reference = _parse_timestamp(asof)
    recent: list[dict[str, Any]] = []

    for item in _deduplicate_news(articles or []):
        published_value = item.get("published_at") or item.get("published_date")
        try:
            published = _parse_timestamp(published_value)
        except (TypeError, ValueError, OverflowError):
            continue

        age_hours = (reference - published).total_seconds() / 3600.0
        if not 0.0 <= age_hours <= NEWS_FRESHNESS_HOURS:
            continue

        copy = dict(item)
        copy["age_hours"] = round(age_hours, 3)
        recent.append(copy)

    return recent

def _news_score(
    news: list[dict[str, Any]],
    asof: datetime,
    rules: dict[str, Any],
    window_hours: int,
) -> tuple[float | None, dict[str, float], float, list[dict[str, Any]]]:
    dedup: dict[str, dict[str, Any]] = {}

    def _tag_list(value: Any) -> list:
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple, set)) else [value]

    for raw in news or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        key = item.get("event_key") or item.get("url") or item.get("title")
        if not key:
            continue

        channels = _tag_list(item.get("news_channels"))
        for field in ("news_channel", "channel"):
            if item.get(field):
                channels.extend(_tag_list(item[field]))
        item["news_channels"] = list(dict.fromkeys(
            str(value).upper() for value in channels if value
        ))

        current = dedup.get(str(key))
        if current is None:
            dedup[str(key)] = item
            continue

        # Preserve all sector/channel tags if the same URL was discovered more than once.
        for field in ("sectors", "news_channels"):
            combined = _tag_list(current.get(field))
            known = {str(value).upper() for value in combined}
            for value in _tag_list(item.get(field)):
                if str(value).upper() not in known:
                    combined.append(value)
                    known.add(str(value).upper())
            current[field] = combined

        try:
            replace_current = float(item.get("confidence", 0.5)) > float(current.get("confidence", 0.5))
        except (TypeError, ValueError):
            replace_current = False
        if replace_current:
            merged_sectors = current.get("sectors", [])
            merged_channels = current.get("news_channels", [])
            current.update(item)
            current["sectors"] = merged_sectors
            current["news_channels"] = merged_channels

    usable: list[dict[str, Any]] = []
    for item in dedup.values():
        published_at = item.get("published_at") or item.get("published_date")
        try:
            published = _parse_timestamp(published_at)
        except (TypeError, ValueError, OverflowError):
            # Unknown publication time is not fresh-news evidence.
            continue

        age_hours = (asof - published).total_seconds() / 3600.0
        if not 0.0 <= age_hours <= min(window_hours, NEWS_FRESHNESS_HOURS):
            continue
        if item.get("event_type", "OTHER") == "OTHER" and not item.get("sectors"):
            continue

        relevance = _clamp(float(item.get("relevance", 0.4)), 0.0, 1.0)
        confidence = _clamp(float(item.get("confidence", 0.5)), 0.0, 1.0)
        magnitude = _clamp(float(item.get("magnitude", 0.5)), 0.0, 1.0)
        direction = _clamp(float(item.get("india_direction", 0.0)))
        reliability = _clamp(float(item.get("reliability", 0.7)), 0.0, 1.0)
        freshness = math.exp(-age_hours / max(1, min(window_hours, NEWS_FRESHNESS_HOURS)))
        weight = reliability * relevance * confidence * freshness
        strength = weight * magnitude
        if strength <= 0:
            continue

        copy = dict(item)
        copy["age_hours"] = round(age_hours, 3)
        copy["_weight"] = weight
        copy["_strength"] = strength
        copy["_direction"] = direction
        usable.append(copy)

    if not usable:
        return None, {}, 0.0, []

    buckets: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in usable:
        buckets[str(item.get("event_type", "OTHER"))].append(item)

    broad_scores: list[float] = []
    sector_news: defaultdict[str, list[float]] = defaultdict(list)
    drivers: list[dict[str, Any]] = []
    event_rules = rules.get("events", {})

    for event_type, items in buckets.items():
        broad_scores.append(
            sum(x["_strength"] * x["_direction"] for x in items) / len(items)
        )

        mapping = event_rules.get(event_type, {})
        if isinstance(mapping, dict):
            for sector, event_direction in mapping.items():
                direction_value = _safe_float(event_direction)
                if direction_value is None:
                    continue
                sector_news[str(sector)].append(
                    100.0 * sum(x["_weight"] * direction_value for x in items) / len(items)
                )

        for item in items:
            drivers.append({
                "kind": "news",
                "name": item.get("title", "News evidence"),
                "signal": round(100.0 * item["_weight"] * item["_direction"], 2),
                "source": item.get("source", "UNKNOWN_SOURCE"),
                "url": item.get("url", ""),
                "published_at": item.get("published_at"),
                "age_hours": item.get("age_hours"),
                "news_channels": item.get("news_channels", []),
                "event_type": event_type,
            })

    # Score tagged global-market channels from the same shared news pool.
    channel_sectors = {"GLOBAL_INDICES", "WORLD_MARKET_TRENDS"}
    for item in usable:
        raw_sectors = item.get("sectors") or []
        raw_channels = item.get("news_channels") or []
        if not isinstance(raw_sectors, (list, tuple, set)):
            raw_sectors = [raw_sectors]
        if not isinstance(raw_channels, (list, tuple, set)):
            raw_channels = [raw_channels]

        tags = {str(value).upper() for value in raw_sectors if value}
        tags.update(str(value).upper() for value in raw_channels if value)
        for field in ("news_channel", "channel"):
            if item.get(field):
                tags.add(str(item[field]).upper())

        for channel in channel_sectors.intersection(tags):
            sector_news[channel].append(
                100.0 * float(item["_weight"]) * float(item["_direction"])
            )

    news_quality = min(1.0, len(usable) / 3.0) * (
        sum(
            float(x.get("confidence", 0.5)) * float(x.get("reliability", 0.7))
            for x in usable
        ) / len(usable)
    )

    broad_score = 100.0 * sum(broad_scores) / len(broad_scores)
    sector_scores = {
        sector: round(sum(values) / len(values), 2)
        for sector, values in sector_news.items()
    }

    return round(broad_score, 2), sector_scores, round(_clamp(news_quality), 3), drivers


# ---------------------------------------------------------------------------
# Market scoring
# ---------------------------------------------------------------------------

def _score_market(
    observations: list[dict[str, Any]],
    news: list[dict[str, Any]],
    asof: datetime,
    settings: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    latest, diagnostics = _latest_valid(observations, asof, settings["factors"])
    groups: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
    factors: dict[str, float] = {}
    factor_drivers: list[dict[str, Any]] = []
    group_weights = settings["group_weights"]
    evidence_strength = 0.0

    for name, obs in latest.items():
        cfg = settings["factors"][name]
        signal = _factor_signal(obs, cfg)
        if signal is None:
            continue

        group = cfg["group"]
        factor_weight = float(cfg["weight"])
        groups[group].append((signal * 100.0, factor_weight))
        factors[name] = signal

        age_hours = max(0.0, (asof - _parse_timestamp(obs["observed_at"])).total_seconds() / 3600.0)
        max_age = max(1.0, float(cfg.get("max_age_hours", 24)))
        freshness = max(0.0, 1.0 - age_hours / (max_age * 2.0))
        evidence_strength += float(group_weights.get(group, 0.0)) * factor_weight * freshness

        factor_drivers.append({
            "kind": "factor",
            "name": name,
            "signal": round(signal * 100.0, 2),
            "contribution": round(
                signal * 100.0 * float(group_weights.get(group, 0.0)) * factor_weight,
                2,
            ),
            "value": obs.get("value"),
            "previous": obs.get("previous"),
            "unit": obs.get("unit"),
            "source": obs.get("source", "UNKNOWN_SOURCE"),
            "observed_at": obs.get("observed_at"),
        })

    news_score, news_sectors, news_quality, news_drivers = _news_score(
        news,
        asof,
        rules,
        NEWS_FRESHNESS_HOURS,
    )

    group_scores: dict[str, float | None] = {}
    group_coverage: dict[str, float] = {}

    for group in group_weights:
        if group == "news":
            group_scores[group] = news_score
            group_coverage[group] = news_quality
            continue
        rows = groups[group]
        if not rows:
            group_scores[group] = None
            group_coverage[group] = 0.0
            continue
        total = sum(weight for _, weight in rows)
        group_scores[group] = sum(value * weight for value, weight in rows) / total if total else None
        group_coverage[group] = min(1.0, total)

    coverage = sum(
        float(group_weights[g]) * group_coverage.get(g, 0.0)
        for g in group_weights
    )

    raw_score = sum(
        float(group_weights[g]) * (
            float(group_scores[g]) if group_scores[g] is not None else 0.0
        )
        for g in group_weights
    )

    minimum_coverage = float(settings.get("minimum_coverage", 0.55))
    overall_score = (
        round(_clamp(raw_score, -100.0, 100.0), 2)
        if coverage >= minimum_coverage
        else None
    )

    evidence_quality_pct = round(
        100.0 * _clamp(
            evidence_strength
            + float(group_weights.get("news", 0.0)) * news_quality
        ),
        1,
    )

    # ----------------------- 22 sector/category scores ---------------------
    sectors: dict[str, dict[str, Any]] = {}
    news_weight = float(group_weights.get("news", 0.0))
    exposures = rules.get("factor_exposures", {})

    for sector in rules.get("sectors", []):
        signal_sum = 0.0
        total_weight = news_weight
        available_weight = news_weight * news_quality
        factor_inputs: list[str] = []

        for factor, exposure in (exposures.get(sector, {}) or {}).items():
            if factor not in settings["factors"]:
                continue
            exposure_value = _safe_float(exposure)
            if exposure_value is None or exposure_value == 0:
                continue

            cfg = settings["factors"][factor]
            sector_factor_weight = (
                float(group_weights.get(cfg["group"], 0.0))
                * float(cfg["weight"])
                * abs(exposure_value)
            )
            total_weight += sector_factor_weight

            if factor not in factors:
                continue

            sign = 1.0 if exposure_value >= 0 else -1.0
            signal_sum += (
                factors[factor]
                * 100.0
                * sector_factor_weight
                * sign
            )
            available_weight += sector_factor_weight
            factor_inputs.append(factor)

        if sector in news_sectors:
            signal_sum += news_sectors[sector] * news_weight

        sector_coverage = available_weight / total_weight if total_weight else 0.0
        score = (
            round(signal_sum / total_weight, 2)
            if total_weight and sector_coverage >= minimum_coverage
            else None
        )

        sectors[sector] = {
            "score": score,
            "bias": _label(score),
            "coverage": round(_clamp(sector_coverage, 0.0, 1.0), 3),
            "news_count": sum(
                1 for item in news
                if sector in (item.get("sectors") or [])
            ),
            "factor_inputs": factor_inputs[:10],
        }

    risk_regime = (
        "UNKNOWN" if overall_score is None else
        "RISK_OFF" if overall_score <= -15 else
        "RISK_ON" if overall_score >= 15 else
        "MIXED"
    )

    vix = _safe_float(latest.get("india_vix", {}).get("value"))
    volatility_regime = (
        "UNKNOWN" if vix is None else
        "HIGH" if vix >= 25 else
        "ELEVATED" if vix >= 18 else
        "NORMAL"
    )

    drivers = sorted(
        factor_drivers,
        key=lambda x: abs(float(x.get("contribution", 0.0))),
        reverse=True,
    ) + news_drivers

    return {
        "overall_score": overall_score,
        "overall_sentiment": _label(overall_score),
        "bias": _label(overall_score),
        "evidence_quality_pct": evidence_quality_pct,
        "coverage": round(_clamp(coverage, 0.0, 1.0), 3),
        "group_scores": group_scores,
        "group_coverage": group_coverage,
        "factors": factors,
        "latest_factors": latest,
        "sectors": sectors,
        "sector_sentiment": [
            {
                "sector": sector,
                "sector_key": sector,
                "score": data["score"],
                "sentiment_score": data["score"],
                "sentiment": data["bias"],
                "bias": data["bias"],
                "coverage": data["coverage"],
                "news_count": data["news_count"],
            }
            for sector, data in sectors.items()
        ],
        "drivers": drivers,
        "news_articles": _deduplicate_news(news),
        "news_score": news_score,
        "news_quality": news_quality,
        "news_sector_scores": news_sectors,
        "risk_regime": risk_regime,
        "volatility_regime": volatility_regime,
        "bullish_sectors": [
            s for s, v in sectors.items()
            if v["score"] is not None and v["score"] >= 15
        ],
        "bearish_sectors": [
            s for s, v in sectors.items()
            if v["score"] is not None and v["score"] <= -15
        ],
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# Human-readable factor matrix and sector narratives
# ---------------------------------------------------------------------------

FACTOR_LABELS = {
    "brent": "Brent Crude",
    "us10y": "U.S. 10Y Yield",
    "dxy": "DXY",
    "usd_inr": "USD/INR",
    "sp500": "S&P 500",
    "nasdaq": "Nasdaq",
    "asia_index": "Asian Markets",
    "fii_cash": "FII Cash Flows",
    "fii_futures": "FII Futures Positioning",
    "dii_cash": "DII Cash Flows",
    "india_vix": "India VIX",
    "cpi_surprise": "CPI Surprise",
    "pmi_surprise": "PMI Surprise",
    "rbi_rate_surprise": "RBI Rate Surprise",
    "gift_nifty": "GIFT Nifty",
    "nifty": "Nifty",
    "advance_decline": "Market Breadth",
}

TRANSMISSION_CHANNELS = {
    "brent": "Crude affects India's import bill, inflation and input costs.",
    "us10y": "Higher U.S. yields can tighten global financial conditions and pressure emerging-market flows.",
    "dxy": "Dollar strength can pressure emerging-market flows and imported input costs.",
    "usd_inr": "Rupee moves affect imported costs, FX liabilities and exporters' realization.",
    "sp500": "U.S. equity risk appetite influences global portfolio flows and regional sentiment.",
    "nasdaq": "U.S. technology performance is an external demand and valuation cue for Indian IT.",
    "asia_index": "Asian market direction affects regional risk appetite and cross-border positioning.",
    "fii_cash": "Foreign institutional flows can directly affect Indian benchmark liquidity.",
    "fii_futures": "FII futures positioning can reinforce or weaken near-term index momentum.",
    "dii_cash": "Domestic institutional activity can cushion or amplify foreign-flow moves.",
    "india_vix": "Higher volatility generally increases the market risk premium and defensive positioning.",
    "cpi_surprise": "Inflation surprises can change rate expectations, demand and input costs.",
    "pmi_surprise": "Growth surprises influence domestic cyclicals, investment and earnings expectations.",
    "rbi_rate_surprise": "Policy-rate surprises affect financing costs and rate-sensitive sectors.",
    "gift_nifty": "GIFT Nifty provides an overnight/pre-market confirmation cue.",
    "nifty": "Nifty direction confirms whether macro signals are reflected in Indian equities.",
    "advance_decline": "Market breadth indicates whether an index move is broad-based.",
}


def _movement_text(obs: dict[str, Any]) -> str:
    value = _safe_float(obs.get("value"))
    previous = _safe_float(obs.get("previous"))
    unit = obs.get("unit", "")
    if value is None:
        return "No usable observation"
    if previous is not None and previous != 0:
        move = 100.0 * (value / previous - 1.0)
        direction = "rose" if move > 0 else "fell" if move < 0 else "was unchanged"
        return f"{value:.2f} {unit} ({direction} {abs(move):.2f}% vs prior observation)"
    return f"{value:.2f} {unit}".strip()


def _impact_label(signal: float | None) -> str:
    if signal is None:
        return "Data unavailable"
    value = signal * 100.0
    if value >= 65:
        return "Strong Positive"
    if value >= 20:
        return "Positive"
    if value <= -65:
        return "Strong Negative"
    if value <= -20:
        return "Negative"
    return "Neutral"


def build_factor_matrix(
    macro_data: dict[str, Any],
    *,
    asof: datetime | None = None,
) -> list[dict[str, Any]]:
    settings = _load_settings()
    observations = _normalize_macro_observations(macro_data)
    latest, _ = _latest_valid(
        observations,
        asof or _utc_now(),
        settings["factors"],
    )

    rows = []
    order = [
        "brent", "us10y", "dxy", "usd_inr", "sp500", "nasdaq", "asia_index",
        "fii_cash", "fii_futures", "dii_cash", "india_vix", "cpi_surprise",
        "pmi_surprise", "rbi_rate_surprise", "gift_nifty", "nifty", "advance_decline",
    ]

    for factor in order:
        obs = latest.get(factor)
        if not obs:
            continue
        signal = _factor_signal(obs, settings["factors"][factor])
        rows.append({
            "factor": factor,
            "label": FACTOR_LABELS.get(factor, factor.replace("_", " ").title()),
            "latest_signal": _movement_text(obs),
            "transmission_channel": TRANSMISSION_CHANNELS.get(
                factor,
                "Cross-asset transmission to Indian equities.",
            ),
            "expected_india_impact": _impact_label(signal),
            "source": obs.get("source", "UNKNOWN_SOURCE"),
            "observed_at": obs.get("observed_at"),
        })

    return rows


def _build_sector_narratives(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    narratives = {}
    rules = report.get("sector_rules", {})
    latest = report.get("latest_factors", {})
    sectors = report.get("sectors", {})

    for sector in rules.get("sectors", sectors.keys()):
        data = sectors.get(sector, {})
        score = data.get("score")
        drivers = []

        for factor in (rules.get("factor_exposures", {}).get(sector, {}) or {}):
            if factor in latest:
                drivers.append(
                    f"{FACTOR_LABELS.get(factor, factor)}: {_movement_text(latest[factor])}"
                )
            if len(drivers) == 3:
                break

        if not drivers:
            drivers.append("No sector-specific factor was available.")

        if score is None:
            outlook = "Insufficient usable evidence for a directional sector conclusion."
        elif score >= 35:
            outlook = "Positive directional bias from the currently available evidence."
        elif score <= -35:
            outlook = "Negative directional bias from the currently available evidence."
        else:
            outlook = "Mixed / range-bound bias because the current evidence is not strongly one-sided."

        narratives[sector] = {
            "display_name": sector,
            "score": score,
            "bias": data.get("bias", _label(score)),
            "global_drivers": drivers,
            "outlook": outlook,
        }

    return narratives


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _report_disclaimer(report: dict[str, Any]) -> str:
    if str(report.get("mode", "")).lower() == "demo":
        return (
            "Heuristic research signal. Evidence quality is not a prediction "
            "probability. DEMO uses synthetic data."
        )
    return "Heuristic research signal. Evidence quality is not a prediction probability."


def _news_weight_pct(report: dict[str, Any]) -> int:
    try:
        return round(float(report.get("configuration", {}).get("group_weights", {}).get("news", 0.10)) * 100)
    except (TypeError, ValueError):
        return 10


def _format_driver(driver: dict[str, Any]) -> str:
    kind = str(driver.get("kind", "driver"))
    source = driver.get("source") or "UNKNOWN_SOURCE"
    if kind == "factor":
        value = driver.get("contribution", driver.get("signal"))
    else:
        value = driver.get("signal", driver.get("contribution", 0))
    text = f"{driver.get('name', 'News evidence')}: {value} ({source})"
    if driver.get("url"):
        text += f" [source]({driver['url']})"
    return text


def _build_report_markdown(report: dict[str, Any]) -> str:
    score = report.get("overall_score")
    score_text = "N/A" if score is None else str(score)
    bias = report.get("bias", "INSUFFICIENT_DATA")
    coverage = float(report.get("coverage", 0.0)) * 100.0
    evidence = report.get("evidence_quality_pct", 0.0)
    asof = report.get("asof") or report.get("created_at") or ""
    mode = str(report.get("mode", "live")).upper()

    lines = [
        "# India market sentiment",
        "",
        f"{asof} | {mode}",
        "",
        f"## {bias} · {score_text}/100",
        "",
        f"Evidence quality {evidence}% · coverage {coverage:.0f}%",
        "",
        _report_disclaimer(report),
        "",
        "## Sector signals",
        "",
        "| Sector            | Score  | Bias           | Coverage |",
        "| :---------------- | :----- | :------------- | :------- |",
    ]

    for sector, data in report.get("sectors", {}).items():
        sector_score = "N/A" if data.get("score") is None else str(data.get("score"))
        sector_bias = data.get("bias", "INSUFFICIENT_DATA")
        sector_coverage = float(data.get("coverage", 0.0)) * 100.0
        lines.append(
            f"| {sector:<17} | {sector_score:<6} | {sector_bias:<13} | {sector_coverage:.0f}%      |"
        )

    lines += [
        "",
        "## Drivers",
        "",
        (
            "Factor contributions sum to the factor component of the overall score. "
            f"News signals are before the {_news_weight_pct(report)}% news sleeve weight."
        ),
        "",
    ]

    drivers = report.get("drivers") or []
    if drivers:
        lines.extend(f"- {_format_driver(driver)}" for driver in drivers)
    else:
        lines.append("- No usable factor or news drivers were available.")

    lines += ["", "## Diagnostics", ""]
    diagnostics = report.get("diagnostics") or []
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No diagnostics reported.")

    return "\n".join(lines)


def console_report(report: dict[str, Any]) -> str:
    return _build_report_markdown(report)


def _html_report(report: dict[str, Any]) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    score = report.get("overall_score")
    score_text = "N/A" if score is None else str(score)
    bias = report.get("bias", "INSUFFICIENT_DATA")
    coverage = float(report.get("coverage", 0.0)) * 100.0
    evidence = report.get("evidence_quality_pct", 0.0)
    news_weight = _news_weight_pct(report)

    rows = []
    for sector, data in report.get("sectors", {}).items():
        score_value = "N/A" if data.get("score") is None else data.get("score")
        rows.append(
            f"<tr><td>{esc(sector)}</td><td>{esc(score_value)}</td>"
            f"<td>{esc(data.get('bias', 'INSUFFICIENT_DATA'))}</td>"
            f"<td>{float(data.get('coverage', 0.0)) * 100:.0f}%</td></tr>"
        )

    drivers = []
    for driver in report.get("drivers") or []:
        text = esc(_format_driver(driver))
        if driver.get("url"):
            text += f' <a href="{esc(driver["url"])}" rel="noopener noreferrer">source</a>'
        drivers.append(f"<li>{text}</li>")

    diagnostics = "".join(
        f"<li>{esc(item)}</li>"
        for item in (report.get("diagnostics") or ["No diagnostics reported."])
    )

    disclaimer = esc(_report_disclaimer(report))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>India market sentiment</title>
<style>
body{{font:16px system-ui;max-width:1000px;margin:32px auto;padding:0 20px;background:#f4f7fa;color:#142238}}
table{{border-collapse:collapse;width:100%;background:white}}
td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd}}
.card{{padding:20px;background:white;border-radius:10px}}
a{{color:#1653ad}}
</style>
</head>
<body>
<h1>India market sentiment</h1>
<div class="card">
<p>{esc(report.get('asof', ''))} | {esc(str(report.get('mode', 'live')).upper())}</p>
<h2>{esc(bias)} · {esc(score_text)}/100</h2>
<p>Evidence quality {esc(evidence)}% · coverage {coverage:.0f}%</p>
<p>{disclaimer}</p>
</div>
<h2>Sector signals</h2>
<table>
<tr><th>Sector</th><th>Score</th><th>Bias</th><th>Coverage</th></tr>
{"".join(rows)}
</table>
<h2>Drivers</h2>
<p>Factor contributions sum to the factor component of the overall score. News signals are before the {news_weight}% news sleeve weight.</p>
<ul>{"".join(drivers) or "<li>No usable factor or news drivers were available.</li>"}</ul>
<h2>Diagnostics</h2>
<ul>{diagnostics}</ul>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Finalize / cache / runners
# ---------------------------------------------------------------------------

def _finalize_report(
    report: dict[str, Any],
    *,
    asof: datetime,
    mode: str,
    settings: dict[str, Any],
    rules: dict[str, Any],
    extra_diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    final = dict(report)
    final["asof"] = asof.isoformat()
    final["created_at"] = asof.isoformat()
    final["mode"] = mode
    final["configuration"] = settings
    final["sector_rules"] = rules
    final["scoring_version"] = "2.0.0-20-sector"
    final["diagnostics"] = list(dict.fromkeys(
        [*(extra_diagnostics or []), *(final.get("diagnostics") or [])]
    ))
    final["articles_considered"] = len(final.get("news_articles") or [])
    final["events_classified"] = sum(
        1 for item in (final.get("news_articles") or [])
        if item.get("event_type", "OTHER") != "OTHER"
    )
    final["sector_count"] = len(final.get("sectors") or {})
    final["sectors_available"] = final["sector_count"]
    final["global_impact_matrix"] = build_factor_matrix(
        {"observations": list((final.get("latest_factors") or {}).values())},
        asof=asof,
    )
    final["sector_narratives"] = _build_sector_narratives(final)
    final["sector_signals"] = final.get("sectors", {})
    final["news_count"] = final["articles_considered"]
    return final


def build_market_sentiment_report(
    observations: list[dict[str, Any]],
    news: list[dict[str, Any]],
    *,
    asof: datetime | None = None,
    mode: str = "demo",
) -> dict[str, Any]:
    """Build a report from supplied normalized inputs without network calls."""
    settings = _load_settings()
    rules = load_sector_rules()
    cutoff = asof or _utc_now()
    prepared_observations = _normalize_macro_observations({"observations": observations or []})
    prepared_news = _filter_recent_news(news or [], cutoff)
    scored = _score_market(prepared_observations, prepared_news, cutoff, settings, rules)
    return _finalize_report(
        scored,
        asof=cutoff,
        mode=mode,
        settings=settings,
        rules=rules,
    )


def _should_refresh(force: bool) -> bool:
    if force:
        return True
    latest = get_latest_market_sentiment_report()
    if not latest or not latest.get("created_at"):
        return True
    try:
        now = _utc_now()
        age_minutes = (now - _parse_timestamp(latest["created_at"])).total_seconds() / 60.0
        refresh_minutes = int(os.getenv("MARKET_SENTIMENT_REFRESH_MINUTES", "15"))

        # Refresh early if any cached article has aged out of the one-hour window.
        report_json = latest.get("report_json")
        if report_json:
            cached = json.loads(report_json) if isinstance(report_json, str) else report_json
            articles = cached.get("news_articles", []) if isinstance(cached, dict) else []
            for article in articles or []:
                try:
                    published = _parse_timestamp(
                        article.get("published_at") or article.get("published_date")
                    )
                except (TypeError, ValueError, OverflowError, AttributeError):
                    return True
                article_age = (now - published).total_seconds() / 3600.0
                if not 0.0 <= article_age <= NEWS_FRESHNESS_HOURS:
                    return True

        return age_minutes >= refresh_minutes
    except Exception:
        return True


def _load_cached_report() -> dict[str, Any] | None:
    latest = get_latest_market_sentiment_report()
    if not latest or not latest.get("report_json"):
        return None
    try:
        report = json.loads(latest["report_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict):
        return None

    report["database_report_id"] = latest.get("id")
    report.setdefault("overall_sentiment", report.get("bias", "INSUFFICIENT_DATA"))
    report.setdefault("bias", report.get("overall_sentiment", "INSUFFICIENT_DATA"))
    report.setdefault("sectors", {})
    report["sector_count"] = len(report["sectors"])
    report["sectors_available"] = report["sector_count"]
    report.setdefault("news_articles", [])
    report.setdefault("articles_considered", len(report["news_articles"]))
    return report




# ---------------------------------------------------------------------------
# Reference synthetic demo
# ---------------------------------------------------------------------------

_REFERENCE_DEMO_SECTORS = {
    "BANKING": (-50.25, "BEARISH", 0.80),
    "NBFC": (-50.25, "BEARISH", 0.80),
    "IT": (-21.90, "MILD_BEARISH", 0.75),
    "PHARMA": (-27.37, "MILD_BEARISH", 0.74),
    "HEALTHCARE": (-52.11, "BEARISH", 0.73),
    "AUTO": (-56.61, "BEARISH", 0.85),
    "FMCG": (-49.15, "BEARISH", 0.82),
    "RETAIL": (-47.03, "BEARISH", 0.86),
    "METALS": (-46.07, "BEARISH", 0.77),
    "OIL_UPSTREAM": (7.62, "NEUTRAL", 0.82),
    "OMC": (-59.80, "BEARISH", 0.81),
    "AVIATION": (-71.55, "STRONG_BEARISH", 0.83),
    "PAINTS": (-68.93, "STRONG_BEARISH", 0.83),
    "CHEMICALS": (-66.30, "STRONG_BEARISH", 0.83),
    "REALTY": (-50.25, "BEARISH", 0.80),
    "UTILITIES": (-52.11, "BEARISH", 0.73),
    "CAPITAL_GOODS": (-44.94, "BEARISH", 0.76),
    "TELECOM": (-52.11, "BEARISH", 0.73),
    "LOGISTICS": (-66.30, "STRONG_BEARISH", 0.83),
    "CONSUMER_DURABLES": (-50.25, "BEARISH", 0.80),
}

_REFERENCE_DEMO_DRIVERS = [
    ("brent", -100.0),
    ("us10y", -100.0),
    ("fii_cash", -70.0),
    ("dxy", -98.04),
    ("usd_inr", -78.43),
    ("cpi_surprise", -40.0),
    ("india_vix", -46.67),
    ("dii_cash", 40.0),
    ("nasdaq", 50.0),
    ("fii_futures", -35.0),
    ("asia_index", -50.0),
    ("pmi_surprise", 30.0),
    ("gift_nifty", -27.78),
    ("advance_decline", -30.0),
    ("nifty", -27.78),
    ("sp500", 16.67),
    ("rbi_rate_surprise", -0.0),
]


def _build_reference_demo_report() -> dict[str, Any]:
    """Return the exact deterministic synthetic report used by the reference demo.

    This path deliberately does not call yfinance, Serper, OpenAI, or any live
    provider. It exists so the integrated project can reproduce the reference
    DEMO output deterministically.
    """
    settings = _load_settings()
    rules = load_sector_rules()
    full_weights = {
        "macro": 0.40,
        "institutional": 0.25,
        "india_macro": 0.15,
        "news": 0.10,
        "confirmation": 0.10,
    }
    settings["profile"] = "full"
    settings["group_weights"] = full_weights

    asof = datetime.fromisoformat("2026-10-01T03:15:00+00:00")
    sectors: dict[str, dict[str, Any]] = {}
    for sector, (score, bias, coverage) in _REFERENCE_DEMO_SECTORS.items():
        sectors[sector] = {
            "score": score,
            "bias": bias,
            "coverage": coverage,
            "news_count": 0,
            "factor_inputs": [],
        }

    drivers = [
        {
            "kind": "factor",
            "name": name,
            "signal": value,
            "contribution": value,
            "source": "SYNTHETIC_DEMO",
        }
        for name, value in _REFERENCE_DEMO_DRIVERS
    ]
    drivers.append({
        "kind": "news",
        "name": "Synthetic oil supply shock",
        "signal": -46.26,
        "source": "SYNTHETIC_DEMO",
        "url": "https://example.com/demo-oil",
        "event_type": "CRUDE_UP",
    })

    sector_sentiment = [
        {
            "sector": sector,
            "sector_key": sector,
            "score": data["score"],
            "sentiment_score": data["score"],
            "sentiment": data["bias"],
            "bias": data["bias"],
            "coverage": data["coverage"],
            "news_count": data["news_count"],
        }
        for sector, data in sectors.items()
    ]

    report = {
        "asof": asof.isoformat(),
        "created_at": asof.isoformat(),
        "mode": "demo",
        "profile": "full",
        "overall_score": -45.69,
        "overall_sentiment": "BEARISH",
        "bias": "BEARISH",
        "evidence_quality_pct": 91.7,
        "coverage": 0.93,
        "group_scores": {},
        "group_coverage": {},
        "factors": {name: value / 100.0 for name, value in _REFERENCE_DEMO_DRIVERS},
        "latest_factors": {},
        "sectors": sectors,
        "sector_sentiment": sector_sentiment,
        "drivers": drivers,
        "news_articles": [],
        "articles_considered": 0,
        "news_count": 0,
        "events_classified": 0,
        "news_score": None,
        "news_quality": 0.0,
        "news_sector_scores": {},
        "risk_regime": "RISK_OFF",
        "volatility_regime": "ELEVATED",
        "bullish_sectors": ["OIL_UPSTREAM"],
        "bearish_sectors": [
            sector for sector, (score, _, _) in _REFERENCE_DEMO_SECTORS.items()
            if score <= -15
        ],
        "diagnostics": ["SYNTHETIC DEMO: no current market/news claims"],
        "configuration": settings,
        "sector_rules": rules,
        "scoring_version": "2.0.0-20-sector-demo-reference",
        "sector_count": 20,
        "sectors_available": 20,
        "global_impact_matrix": [],
        "sector_narratives": {},
        "sector_signals": sectors,
    }
    return report


def run_market_sentiment(
    force: bool = False,
    mode: str = "live",
    print_report: bool = False,
    news: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run market sentiment and write report.txt/html/json.

    ``mode="demo"`` reproduces the reference synthetic report exactly and makes
    no network calls. ``mode="live"`` continues to use the live collectors.
    """

    if str(mode).lower() == "demo":
        report = _build_reference_demo_report()
        report_id = save_market_sentiment_report(report)
        report["database_report_id"] = report_id
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (DEFAULT_OUTPUT_DIR / "report.json").write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        text_report = console_report(report)
        (DEFAULT_OUTPUT_DIR / "report.txt").write_text(
            text_report + "\n",
            encoding="utf-8",
        )
        (DEFAULT_OUTPUT_DIR / "report.html").write_text(
            _html_report(report),
            encoding="utf-8",
        )
        if print_report:
            print(text_report)
        return report

    if news is None and not _should_refresh(force):
        cached = _load_cached_report()
        if cached:
            if print_report:
                print(console_report(cached))
            return cached

    settings = _load_settings()
    rules = load_sector_rules()
    diagnostics: list[str] = []

    try:
        macro_data = fetch_macro_market_data()
        if not isinstance(macro_data, dict):
            macro_data = {"factors": {}}
            diagnostics.append("Macro market collector returned no dictionary.")
    except Exception as exc:
        macro_data = {"factors": {}}
        diagnostics.append(
            f"Macro market data unavailable ({type(exc).__name__}: {str(exc)[:160]})"
        )

    observations = _normalize_macro_observations(macro_data)
    diagnostics.append(f"Market observations collected: {len(observations)}")

    if news is None:
        try:
            collected_news, news_diagnostics = collect_sector_news(max_results_per_query=4)
            combined_news = _deduplicate_news(collected_news or [])
            diagnostics.extend(str(x) for x in (news_diagnostics or []))
        except Exception as exc:
            combined_news = []
            diagnostics.append(
                f"Sector news unavailable ({type(exc).__name__}: {str(exc)[:180]})"
            )
    else:
        combined_news = _deduplicate_news(news)
        diagnostics.append(
            f"Using supplied shared news collection: {len(combined_news)} article(s)"
        )

    # Capture the reference time AFTER all live data has been collected.
    # Otherwise freshly fetched observations get timestamps a few milliseconds
    # later than `asof` and are incorrectly rejected as FUTURE/UNAVAILABLE.
    asof = _utc_now()

    collected_count = len(combined_news)
    combined_news = _filter_recent_news(combined_news, asof)
    diagnostics.append(
        f"Final news freshness check: {len(combined_news)} of {collected_count} "
        "articles retained from the last 12 hours."
    )

    scored = _score_market(observations, combined_news, asof, settings, rules)
    report = _finalize_report(
        scored,
        asof=asof,
        mode=mode,
        settings=settings,
        rules=rules,
        extra_diagnostics=diagnostics,
    )

    report_id = save_market_sentiment_report(report)
    report["database_report_id"] = report_id

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (DEFAULT_OUTPUT_DIR / "report.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    text_report = console_report(report)
    (DEFAULT_OUTPUT_DIR / "report.txt").write_text(
        text_report + "\n",
        encoding="utf-8",
    )
    (DEFAULT_OUTPUT_DIR / "report.html").write_text(
        _html_report(report),
        encoding="utf-8",
    )

    if print_report:
        print(text_report)
    return report


def print_market_sentiment(report: dict[str, Any]):
    print(console_report(report))


if __name__ == "__main__":
    result = run_market_sentiment(
        force=True,
        mode="live",
        print_report=True,
    )
    print()
    print("MARKET SENTIMENT RUN COMPLETE")
    print("Sectors:", result.get("sector_count", 0))
    print("News articles:", result.get("articles_considered", 0))
