"""
Live market-factor collector for the India market sentiment engine.

Live factors:
    - Brent
    - US 10Y
    - DXY
    - USD/INR
    - S&P 500
    - Nasdaq
    - Nikkei / Asia
    - India VIX
    - Nifty
    - FII cash
    - DII cash
    - FII futures positioning
    - GIFT Nifty
    - Advance/Decline breadth

Consensus-dependent factors:
    - CPI surprise
    - PMI surprise
    - RBI rate surprise

Consensus-dependent factors are collected from the latest released
 economic-calendar observations using Actual vs Forecast. Missing or
 unverifiable release timestamps are not replaced with the current time.
"""

from __future__ import annotations

import csv
import html
import io
import json
import logging
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(override=True)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_PATH = BASE_DIR / "data" / "market_snapshot.json"


# ============================================================
# TIME AND PARSING HELPERS
# ============================================================

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _as_utc_iso(value: Any) -> str | None:
    """Convert an actual datetime/timestamp into ISO UTC; do not guess on bad input."""
    if value is None:
        return None

    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        except ValueError:
            return None

    # Yahoo timestamps without a zone are exchange/session dates, not local machine time.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_provider_datetime(value: Any, *, default_timezone: timezone = IST) -> datetime | None:
    """Parse known provider timestamp formats. Return None when time is not verifiable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_timezone)
        return dt.astimezone(UTC)

    text = str(value).strip()
    if not text:
        return None

    # ISO-8601 is the least ambiguous format.
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(iso_text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_timezone)
        return dt.astimezone(UTC)
    except ValueError:
        pass

    for fmt in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M %p",
    ):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=default_timezone)
            return dt.astimezone(UTC)
        except ValueError:
            continue

    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_timezone)
        return dt.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _ist_date_time_iso(date_value: datetime | date, hour: int, minute: int) -> str:
    dt = datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        hour,
        minute,
        tzinfo=IST,
    )
    return dt.astimezone(UTC).isoformat()


def _parse_report_date(value: Any) -> date | None:
    """Parse report dates from known NSE formats, without substituting today's date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ============================================================
# YFINANCE FACTORS
# ============================================================

FACTOR_TICKERS: dict[str, tuple[str, str]] = {
    "brent": ("BZ=F", "USD_per_barrel"),
    "us10y": ("^TNX", "percent"),
    "dxy": ("DX-Y.NYB", "index"),
    "usd_inr": ("INR=X", "INR_per_USD"),
    "sp500": ("^GSPC", "index"),
    "nasdaq": ("^IXIC", "index"),
    "asia_index": ("^N225", "index"),
    "india_vix": ("^INDIAVIX", "index"),
    "nifty": ("^NSEI", "index"),
}


def _download_two_closes(ticker: str) -> tuple[float, float, str]:
    import yfinance as yf

    # Yahoo currently emits noisy ERROR-level log lines for BZ=F even though
    # the collector intentionally has a CL=F fallback. Silence only the
    # expected primary-ticker failure; the fallback and final diagnostics
    # remain active. Restore the logger state immediately afterwards.
    yf_logger = logging.getLogger("yfinance")
    previous_disabled = yf_logger.disabled
    silence_expected_brent_failure = ticker == "BZ=F"

    try:
        if silence_expected_brent_failure:
            yf_logger.disabled = True

        df = yf.download(
            tickers=ticker,
            period="10d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="column",
            multi_level_index=False,
            threads=False,
        )

        if df is None or df.empty:
            # Retry through Ticker.history when Yahoo's download wrapper fails.
            try:
                df = yf.Ticker(ticker).history(
                    period="10d",
                    interval="1d",
                    auto_adjust=False,
                )
            except Exception:
                df = None
    finally:
        if silence_expected_brent_failure:
            yf_logger.disabled = previous_disabled

    if df is None or df.empty:
        raise ValueError(f"No data returned for {ticker} via download/history")

    close = None
    if "Close" in df.columns:
        close = df["Close"]
    elif "close" in df.columns:
        close = df["close"]
    else:
        try:
            if hasattr(df.columns, "get_level_values"):
                for column in df.columns:
                    label = str(column[-1] if isinstance(column, tuple) else column).lower()
                    if label == "close":
                        close = df[column]
                        break
        except Exception:
            close = None

    if close is None:
        raise ValueError(f"Close column not found for {ticker}")

    if hasattr(close, "columns"):
        if len(close.columns) == 0:
            raise ValueError(f"Close column empty for {ticker}")
        close = close.iloc[:, 0]

    rows: list[tuple[Any, float]] = []
    for timestamp, raw_value in close.items():
        value = _safe_float(raw_value)
        if value is not None:
            rows.append((timestamp, value))

    if len(rows) < 2:
        raise ValueError(f"Not enough observations for {ticker}")

    latest_timestamp, latest_value = rows[-1]
    _, previous_value = rows[-2]
    observed_at = _as_utc_iso(latest_timestamp)
    if observed_at is None:
        raise ValueError(f"Invalid timestamp for {ticker}")

    return latest_value, previous_value, observed_at


# ============================================================
# NSE SESSION
# ============================================================

NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def _create_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    response = session.get(NSE_BASE, timeout=20)
    response.raise_for_status()
    return session


def _nse_json(session: requests.Session, path: str) -> Any:
    url = path if path.startswith("http") else f"{NSE_BASE}{path}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


# ============================================================
# FII / DII CASH
# ============================================================

def _collect_fii_dii_cash(
    session: requests.Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    try:
        payload = _nse_json(session, "/api/fiidiiTradeReact")
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("Unexpected FII/DII response shape")

        retrieved_at = _utc_now().isoformat()
        skipped_missing_dates = 0

        for row in rows:
            if not isinstance(row, dict):
                continue

            category = str(row.get("category", "")).strip().upper()
            if category not in {"FII/FPI", "FII", "DII"}:
                continue

            net = _safe_float(row.get("netValue"))
            if net is None:
                buy = _safe_float(row.get("buyValue"))
                sell = _safe_float(row.get("sellValue"))
                if buy is not None and sell is not None:
                    net = buy - sell
            if net is None:
                continue

            report_date = _parse_report_date(
                row.get("date") or row.get("tradeDate") or row.get("businessDate")
            )
            if report_date is None:
                skipped_missing_dates += 1
                continue

            factor = "fii_cash" if category in {"FII/FPI", "FII"} else "dii_cash"
            observations.append(
                {
                    "factor": factor,
                    "value": net,
                    "previous": None,
                    "unit": "INR_crore",
                    "observed_at": _ist_date_time_iso(report_date, 16, 0),
                    "observed_at_precision": "date",
                    "available_at": retrieved_at,
                    "source": "NSE:fiidiiTradeReact",
                }
            )

        if skipped_missing_dates:
            diagnostics.append(
                f"FII/DII rows skipped because report date was missing/unparseable: {skipped_missing_dates}"
            )

    except Exception as exc:
        diagnostics.append(
            f"FII/DII cash unavailable ({type(exc).__name__}: {str(exc)[:140]})"
        )

    return observations, diagnostics


# ============================================================
# FII FUTURES PARTICIPANT OPEN INTEREST
# ============================================================

def _business_date_candidates(days: int = 7) -> list[datetime]:
    today = datetime.now(IST).date()
    candidates = []
    for offset in range(days):
        value = today - timedelta(days=offset)
        candidates.append(datetime(value.year, value.month, value.day))
    return candidates


def _download_participant_oi_for_date(
    session: requests.Session,
    date_value: datetime,
) -> float | None:
    date_text = date_value.strftime("%d%m%Y")
    urls = [
        "https://nsearchives.nseindia.com/content/nsccl/"
        f"fao_participant_oi_{date_text}.csv",
        "https://archives.nseindia.com/content/nsccl/"
        f"fao_participant_oi_{date_text}.csv",
    ]

    for url in urls:
        try:
            response = session.get(url, timeout=20)
            if response.status_code != 200:
                continue

            reader = csv.reader(
                io.StringIO(response.content.decode("utf-8", errors="replace"))
            )
            for row in reader:
                if not row or str(row[0]).strip().upper() != "FII":
                    continue
                if len(row) < 3:
                    continue
                future_index_long = _safe_float(row[1])
                future_index_short = _safe_float(row[2])
                if future_index_long is None or future_index_short is None:
                    continue
                return future_index_long - future_index_short
        except Exception:
            continue

    return None


def _collect_fii_futures(
    session: requests.Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    try:
        values: list[tuple[datetime, float]] = []
        for date_value in _business_date_candidates(7):
            value = _download_participant_oi_for_date(session, date_value)
            if value is not None:
                values.append((date_value, value))
            if len(values) >= 2:
                break

        if not values:
            raise ValueError("No NSE participant-wise OI file was available in the last 7 days.")

        latest_date, latest_value = values[0]
        previous_value = values[1][1] if len(values) > 1 else None
        observations.append(
            {
                "factor": "fii_futures",
                "value": latest_value,
                "previous": previous_value,
                "unit": "contracts_net_change",
                "observed_at": _ist_date_time_iso(latest_date, 17, 30),
                "observed_at_precision": "date",
                "available_at": _utc_now().isoformat(),
                "source": "NSE:participant-wise-open-interest",
            }
        )
    except Exception as exc:
        diagnostics.append(
            f"FII futures unavailable ({type(exc).__name__}: {str(exc)[:140]})"
        )

    return observations, diagnostics


# ============================================================
# GIFT NIFTY
# ============================================================

def _collect_gift_nifty(
    session: requests.Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    try:
        payload = _nse_json(session, "/api/marketStatus")
        if not isinstance(payload, dict):
            raise ValueError("Unexpected marketStatus response")

        gift = payload.get("giftnifty")
        if not isinstance(gift, dict):
            raise ValueError("GIFT Nifty data unavailable")

        value = _safe_float(gift.get("LASTPRICE"))
        day_change = _safe_float(gift.get("DAYCHANGE"))
        if value is None:
            raise ValueError("GIFT Nifty last price missing")

        timestamp_text = gift.get("TIMESTMP") or gift.get("TIMESTAMP") or gift.get("timestamp")
        parsed_timestamp = _parse_provider_datetime(timestamp_text, default_timezone=IST)
        if parsed_timestamp is None:
            raise ValueError("GIFT Nifty source timestamp missing or unparseable; observation skipped")

        previous = value - day_change if day_change is not None else None
        observations.append(
            {
                "factor": "gift_nifty",
                "value": value,
                "previous": previous,
                "unit": "index",
                "observed_at": parsed_timestamp.isoformat(),
                "available_at": _utc_now().isoformat(),
                "source": "NSE:marketStatus",
            }
        )
    except Exception as exc:
        diagnostics.append(
            f"GIFT Nifty unavailable ({type(exc).__name__}: {str(exc)[:140]})"
        )

    return observations, diagnostics


# ============================================================
# ADVANCE / DECLINE
# ============================================================

def _collect_advance_decline(
    session: requests.Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    try:
        payload = _nse_json(session, "/api/allIndices")
        if not isinstance(payload, dict):
            raise ValueError("Unexpected allIndices response")

        advances = _safe_float(payload.get("advances"))
        declines = _safe_float(payload.get("declines"))
        unchanged = _safe_float(payload.get("unchanged"))
        if advances is None or declines is None:
            raise ValueError("NSE advances/declines values missing")
        if declines <= 0:
            raise ValueError("Declines are zero; breadth ratio cannot be calculated safely.")

        timestamp_text = payload.get("timestamp") or payload.get("timeStamp") or payload.get("asOf")
        parsed_timestamp = _parse_provider_datetime(timestamp_text, default_timezone=IST)
        if parsed_timestamp is None:
            raise ValueError("NSE breadth source timestamp missing or unparseable; observation skipped")

        observations.append(
            {
                "factor": "advance_decline",
                "value": advances / declines,
                "previous": None,
                "unit": "ratio",
                "observed_at": parsed_timestamp.isoformat(),
                "available_at": _utc_now().isoformat(),
                "source": "NSE:allIndices",
                "advance_count": int(advances),
                "decline_count": int(declines),
                "unchanged_count": int(unchanged) if unchanged is not None else None,
            }
        )
    except Exception as exc:
        diagnostics.append(
            f"Advance/decline unavailable ({type(exc).__name__}: {str(exc)[:140]})"
        )

    return observations, diagnostics


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

ECONOMIC_CALENDAR_URLS: dict[str, dict[str, str]] = {
    "cpi_surprise": {
        "url": "https://www.investing.com/economic-calendar/cpi-973",
        "name": "India-CPI",
        "unit": "percentage_points",
    },
    "pmi_surprise": {
        "url": (
            "https://www.investing.com/economic-calendar/"
            "pmi-industrial-nikkei-sp-global-754"
        ),
        "name": "India-Manufacturing-PMI",
        "unit": "index_points",
    },
    "rbi_rate_surprise": {
        "url": (
            "https://www.investing.com/economic-calendar/"
            "interest-rate-decision-597"
        ),
        "name": "India-RBI-Rate-Decision",
        "unit": "bps",
    },
}

ECONOMIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _clean_html_text(content: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_number_text(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Calendar numbers can use decimal comma; thousands separators are not expected here.
    if re.fullmatch(r"[+-]?\d+,\d+", text):
        text = text.replace(",", ".")
    return _safe_float(text)


def _parse_release_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in (
        "%b %d, %Y",
        "%B %d, %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_latest_calendar_record(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    # Restrict extraction to the calendar's explicitly labelled Latest Release.
    patterns = [
        re.compile(
            r"""
            Latest\s+Release\s+
            (?P<date>[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})
            .{0,180}?Actual\s*(?P<actual>[+-]?\d+(?:[.,]\d+)?)\s*%?
            .{0,80}?Forecast\s*(?P<forecast>[+-]?\d+(?:[.,]\d+)?)\s*%?
            (?:.{0,80}?Previous\s*(?P<previous>[+-]?\d+(?:[.,]\d+)?)\s*%?)?
            """,
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
        re.compile(
            r"""
            Latest\s+Release\s+
            (?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})
            .{0,180}?Actual\s*(?P<actual>[+-]?\d+(?:[.,]\d+)?)\s*%?
            .{0,80}?Forecast\s*(?P<forecast>[+-]?\d+(?:[.,]\d+)?)\s*%?
            (?:.{0,80}?Previous\s*(?P<previous>[+-]?\d+(?:[.,]\d+)?)\s*%?)?
            """,
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        actual = _parse_number_text(match.group("actual"))
        forecast = _parse_number_text(match.group("forecast"))
        previous = _parse_number_text(match.groupdict().get("previous"))
        release_date = _parse_release_date(match.group("date"))

        # A record without a verifiable date is not considered a confirmed release.
        if actual is None or forecast is None or release_date is None:
            continue

        return {
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
            "release_date": release_date,
        }
    return None


def _serper_search(query: str, num: int = 5) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return []

    response = requests.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "autonomous-financial-analyst/1.0",
        },
        json={"q": query, "num": max(1, min(int(num), 10)), "hl": "en", "gl": "in"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    organic = payload.get("organic", [])
    return organic if isinstance(organic, list) else []


def _serper_text(results: list[dict[str, Any]]) -> str:
    parts = []
    for item in results:
        if not isinstance(item, dict):
            continue
        parts.append(
            f"{item.get('title', '')} {item.get('snippet', '')} {item.get('link', '')}"
        )
    return " ".join(parts)


def _fetch_calendar_record(
    factor: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    url = str(config.get("url", "")).strip()
    source_name = str(config.get("name", factor)).strip()
    direct_error = None

    # 1. Direct economic-calendar page.
    try:
        response = requests.get(url, headers=ECONOMIC_HEADERS, timeout=25)
        response.raise_for_status()
        record = _extract_latest_calendar_record(_clean_html_text(response.text))
        if record is not None:
            return record, f"Investing.com:{source_name}"
    except Exception as exc:
        direct_error = f"{type(exc).__name__}: {str(exc)[:100]}"

    # 2. Serper fallback. It uses the same date/value extraction and validation.
    queries = {
        "cpi_surprise": (
            'India Consumer Price Index CPI "Latest Release" Actual Forecast Previous '
            "site:investing.com/economic-calendar/cpi-973"
        ),
        "pmi_surprise": (
            'India S&P Global Manufacturing PMI "Latest Release" Actual Forecast Previous '
            "site:investing.com/economic-calendar/pmi-industrial-nikkei-sp-global-754"
        ),
        "rbi_rate_surprise": (
            'India Interest Rate Decision RBI "Latest Release" Actual Forecast Previous '
            "site:investing.com/economic-calendar/interest-rate-decision-597"
        ),
    }
    try:
        query = queries.get(factor, "")
        if query:
            results = _serper_search(query, num=5)
            record = _extract_latest_calendar_record(_serper_text(results))
            if record is not None:
                return record, f"Serper:Investing.com:{source_name}"
    except Exception:
        pass

    if direct_error:
        return None, f"Investing calendar fetch failed for {factor}: {direct_error}"
    return None, f"Investing calendar values not found for {factor}"


def _calendar_release_to_utc(release_date: str | None) -> str | None:
    """Return an explicitly date-precision marker only for a valid, non-future release date."""
    if not release_date:
        return None
    try:
        release_day = datetime.strptime(str(release_date).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    if release_day > _utc_now().date():
        return None

    # Calendar pages supply a date, not a reliable release time. Keep precision metadata
    # so downstream code does not mistake midnight for the exact publication time.
    return datetime(
        release_day.year,
        release_day.month,
        release_day.day,
        tzinfo=UTC,
    ).isoformat()


def _build_macro_surprise_observation(
    factor: str,
    record: dict[str, Any],
    source: str,
    unit: str,
) -> dict[str, Any] | None:
    actual = _safe_float(record.get("actual"))
    forecast = _safe_float(record.get("forecast"))
    previous = _safe_float(record.get("previous"))
    if actual is None or forecast is None:
        return None

    release_date = record.get("release_date")
    observed_at = _calendar_release_to_utc(release_date)
    if observed_at is None:
        return None

    # Surprise = ACTUAL - CONSENSUS. RBI rate differences are converted from percentage
    # points to basis points. This does not infer an unreported forecast or actual.
    surprise = (actual - forecast) * 100.0 if factor == "rbi_rate_surprise" else actual - forecast

    return {
        "factor": factor,
        "value": surprise,
        "previous": None,
        "unit": unit,
        "observed_at": observed_at,
        "observed_at_precision": "date",
        "available_at": _utc_now().isoformat(),
        "source": source,
        "actual": actual,
        "consensus": forecast,
        "calendar_previous": previous,
        "release_date": release_date,
    }


def _collect_india_macro_surprises() -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    requested = (
        ("cpi_surprise", "percentage_points", "CPI"),
        ("pmi_surprise", "index_points", "PMI"),
        ("rbi_rate_surprise", "bps", "RBI rate"),
    )

    for factor, unit, label in requested:
        try:
            config = ECONOMIC_CALENDAR_URLS[factor]
            record, source = _fetch_calendar_record(factor, config)
            if record is None:
                raise ValueError(source or f"{label} calendar data unavailable")
            observation = _build_macro_surprise_observation(
                factor=factor,
                record=record,
                source=source or f"Investing.com:{config.get('name', factor)}",
                unit=unit,
            )
            if observation is None:
                raise ValueError(
                    f"{label} actual/forecast or verified release date unavailable"
                )
            observations.append(observation)
        except Exception as exc:
            diagnostics.append(
                f"{label} surprise unavailable ({type(exc).__name__}: {str(exc)[:140]})"
            )

    return observations, diagnostics


# ============================================================
# OPTIONAL SNAPSHOT
# ============================================================

def _load_snapshot(
    path: str | Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    snapshot_path = Path(
        path
        or os.getenv("MARKET_SNAPSHOT_PATH", str(DEFAULT_SNAPSHOT_PATH))
    )
    if not snapshot_path.exists():
        return [], []

    diagnostics: list[str] = []
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"Market snapshot skipped ({type(exc).__name__}: {str(exc)[:140]})"]

    if not isinstance(payload, dict):
        return [], ["Market snapshot skipped (root must be an object)"]
    if payload.get("synthetic"):
        return [], ["Synthetic market snapshot ignored during live market sentiment run."]

    raw_items = payload.get("observations", [])
    if not isinstance(raw_items, list):
        return [], ["Market snapshot skipped (observations must be a list)"]

    allowed = {
        "fii_cash",
        "fii_futures",
        "dii_cash",
        "cpi_surprise",
        "pmi_surprise",
        "rbi_rate_surprise",
        "gift_nifty",
        "advance_decline",
    }
    observations: list[dict[str, Any]] = []
    retrieved_at = _utc_now().isoformat()

    for item in raw_items:
        if not isinstance(item, dict):
            diagnostics.append("Skipped malformed snapshot observation")
            continue

        factor = str(item.get("factor", "")).strip()
        if factor not in allowed:
            continue

        value = _safe_float(item.get("value"))
        if value is None:
            diagnostics.append(f"Skipped invalid snapshot value: {factor}")
            continue

        unit = str(item.get("unit") or "").strip()
        if not unit:
            diagnostics.append(f"Skipped snapshot factor without unit: {factor}")
            continue

        observed_raw = item.get("observed_at") or item.get("published_at")
        observed_at = _as_utc_iso(observed_raw)
        if observed_at is None:
            diagnostics.append(
                f"Skipped snapshot factor without a valid observed_at timestamp: {factor}"
            )
            continue

        previous = item.get("previous")
        if previous is None:
            previous = item.get("previous_value")

        observation = {
            "factor": factor,
            "value": value,
            "previous": _safe_float(previous) if previous is not None else None,
            "unit": unit,
            "observed_at": observed_at,
            "available_at": _as_utc_iso(item.get("available_at")) or retrieved_at,
            "source": str(item.get("source") or "MARKET_SNAPSHOT"),
        }
        if item.get("observed_at_precision"):
            observation["observed_at_precision"] = str(item["observed_at_precision"])
        observations.append(observation)

    return observations, diagnostics


# ============================================================
# MAIN COLLECTOR
# ============================================================

def collect_market_observations(
    snapshot_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    available_at = _utc_now().isoformat()

    # Primary ticker first; proxies are explicitly labelled if needed.
    fallback_tickers: dict[str, tuple[str, ...]] = {
        "brent": ("BZ=F", "CL=F"),
        "dxy": ("DX-Y.NYB", "UUP"),
        "sp500": ("^GSPC", "SPY"),
        "nasdaq": ("^IXIC", "QQQ"),
        "asia_index": ("^N225", "^HSI", "^KS11"),
    }

    # 1. Yahoo Finance factors.
    for factor, (ticker, unit) in FACTOR_TICKERS.items():
        candidates = fallback_tickers.get(factor, (ticker,))
        collected: list[tuple[float, float, str, str]] = []
        errors: list[str] = []

        for candidate_ticker in candidates:
            try:
                value, previous, observed_at = _download_two_closes(candidate_ticker)
                collected.append((value, previous, observed_at, candidate_ticker))
            except Exception as exc:
                errors.append(
                    f"{candidate_ticker}: {type(exc).__name__}: {str(exc)[:100]}"
                )
                continue

            if factor != "asia_index":
                break

        if not collected:
            diagnostics.append(
                f"{factor}: market data unavailable ({'; '.join(errors) or 'No usable ticker data'})"
            )
            continue

        # Prefer the freshest source timestamp; on ties prefer the first configured ticker.
        value, previous, observed_at, used_ticker = max(
            collected,
            key=lambda item: item[2],
        )

        if used_ticker == ticker or factor == "asia_index":
            source = f"yfinance:{used_ticker}"
        else:
            source = (
                f"yfinance-proxy:{used_ticker} "
                f"(fallback for {factor}; primary {ticker})"
            )

        observations.append(
            {
                "factor": factor,
                "value": value,
                "previous": previous,
                "unit": unit,
                "observed_at": observed_at,
                "available_at": available_at,
                "source": source,
            }
        )

    # 2. NSE live factors.
    session = None
    try:
        session = _create_nse_session()
    except Exception as exc:
        diagnostics.append(
            f"NSE session unavailable ({type(exc).__name__}: {str(exc)[:120]})"
        )

    if session is not None:
        fii_dii, d1 = _collect_fii_dii_cash(session)
        observations.extend(fii_dii)
        diagnostics.extend(d1)

        fii_futures, d2 = _collect_fii_futures(session)
        observations.extend(fii_futures)
        diagnostics.extend(d2)

        gift_nifty, d3 = _collect_gift_nifty(session)
        observations.extend(gift_nifty)
        diagnostics.extend(d3)

        breadth, d4 = _collect_advance_decline(session)
        observations.extend(breadth)
        diagnostics.extend(d4)

    # 3. Latest released India macro surprises.
    macro_surprises, d5 = _collect_india_macro_surprises()
    observations.extend(macro_surprises)
    diagnostics.extend(d5)

    # 4. Optional snapshot overrides/inputs.
    snapshot_observations, snapshot_diagnostics = _load_snapshot(snapshot_path)
    observations.extend(snapshot_observations)
    diagnostics.extend(snapshot_diagnostics)

    return observations, diagnostics


# ============================================================
# EXISTING PROJECT API
# ============================================================

def fetch_macro_market_data(
    snapshot_path: str | Path | None = None,
) -> dict[str, Any]:
    observations, diagnostics = collect_market_observations(snapshot_path)
    return {
        "observations": observations,
        "diagnostics": diagnostics,
        "collected_at": _utc_now().isoformat(),
    }


# ============================================================
# TEST / CLI
# ============================================================

if __name__ == "__main__":
    payload = fetch_macro_market_data()

    print()
    print("=" * 80)
    print("LIVE MARKET FACTOR COLLECTION")
    print("=" * 80)
    print()
    print("Observations:", len(payload["observations"]))
    print()

    for item in payload["observations"]:
        print(
            f"- {item['factor']}: {item['value']} "
            f"(previous={item.get('previous')}, unit={item['unit']}, "
            f"source={item['source']}, observed_at={item.get('observed_at')})"
        )

    print()
    print("=" * 80)
    print("DIAGNOSTICS")
    print("=" * 80)
    if payload["diagnostics"]:
        for item in payload["diagnostics"]:
            print("-", item)
    else:
        print("No diagnostics.")
    print()
