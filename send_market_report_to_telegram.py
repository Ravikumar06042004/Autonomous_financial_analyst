"""Generate the existing market report and send a separate 11-factor news digest.

The macro-factor digest is a separate reporting-only feed. It does not feed new
articles into the market sentiment score or change existing sector weights.
"""
from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from services.market_sentiment_service import console_report, run_market_sentiment
from services.sector_news_service import collect_macro_factor_news
from notifications.report_image import render_report_images
from notifications.telegram_notifier import send_telegram_message, send_telegram_photo

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
TELEGRAM_SAFE_MESSAGE_LENGTH = 3500


def _safe(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def format_factor_news_messages(
    articles_by_factor: dict[str, list[dict]],
    diagnostics: list[str],
    generated_at: str,
    max_chars: int = TELEGRAM_SAFE_MESSAGE_LENGTH,
) -> list[str]:
    """Format the separate 11-factor digest into Telegram-sized messages."""
    lines = [
        "🌍 MACRO FACTOR NEWS DIGEST", 
        f"Generated: {generated_at}",
        "Freshness: verified publication timestamp within rolling last 12 hours",
        "These are separate news topics; they do not change the market score by themselves.",
        "",
    ]

    total_articles = sum(len(items) for items in articles_by_factor.values())
    lines.append(f"Topics: {len(articles_by_factor)} | Fresh articles: {total_articles}")
    lines.append("")

    for factor, items in articles_by_factor.items():
        lines.append(f"━━ {factor} ━━")
        if not items:
            lines.append("No verified fresh article found in the last 12 hours for this topic.")
            lines.append("")
            continue

        for index, article in enumerate(items, start=1):
            title = _safe(article.get("title"), 220)
            source = _safe(article.get("source"), 80)
            published = _safe(article.get("published_at"), 60)
            url = _safe(article.get("url"), 500)
            lines.append(f"{index}. {title}")
            lines.append(f"Source: {source} | Published: {published}")
            if url:
                lines.append(url)
        lines.append("")

    # Diagnostics are intentionally limited and contain no secrets. Only show
    # failed query summaries so the user can identify coverage/API issues.
    errors = [line for line in diagnostics if ": ERROR " in line]
    if errors:
        lines.extend(["Search diagnostics:", *(_safe(e, 220) for e in errors), ""])

    # Split only at line boundaries and label each part after the number of
    # pieces is known. The notifier can send each part as a normal text message.
    # Leave room for the part-number prefix added below.
    chunk_limit = max_chars - 60
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > chunk_limit:
            chunks.append("\n".join(current).strip())
            current = []
            current_len = 0
        # A single unusually long line is clipped rather than violating Telegram's limit.
        if len(line) > chunk_limit - 20:
            line = line[: chunk_limit - 20]
            line_len = len(line) + 1
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current).strip())

    if len(chunks) <= 1:
        return chunks or ["🌍 MACRO FACTOR NEWS DIGEST\nNo content generated."]
    return [f"🌍 MACRO FACTOR NEWS DIGEST ({idx}/{len(chunks)})\n{chunk}"[:max_chars]
            for idx, chunk in enumerate(chunks, start=1)]


def main() -> int:
    print("Starting market report generation...", flush=True)
    try:
        report = run_market_sentiment(force=True, mode="live", print_report=False)
        report_text = console_report(report)
        if not isinstance(report_text, str):
            report_text = str(report_text)
        if not report_text.strip():
            raise RuntimeError("The market sentiment engine returned an empty report.")

        images = render_report_images(report_text)
        if not images:
            raise RuntimeError("Report image renderer returned no images.")

        generated_at = datetime.now().astimezone().strftime("%d %b %Y, %I:%M %p %Z")

        # Collect extra macro-topic news independently. A single topic failure is
        # isolated inside the collector and must not prevent the report images.
        print("Fetching separate macro-factor news (11 topics, last 12 hours)...", flush=True)
        factor_articles, factor_diagnostics = collect_macro_factor_news(max_results_per_factor=2)
        for diagnostic in factor_diagnostics:
            print(diagnostic, flush=True)

        factor_messages = format_factor_news_messages(
            factor_articles,
            factor_diagnostics,
            generated_at,
        )
        print(f"Sending macro-factor news digest to Telegram in {len(factor_messages)} message(s)...", flush=True)
        for message in factor_messages:
            try:
                send_telegram_message(message)
            except Exception as news_send_exc:
                # Preserve delivery of the primary report even if the additional
                # digest cannot be sent. The error remains visible in the console/log.
                print(
                    "WARNING: Macro-factor digest delivery failed: "
                    f"{type(news_send_exc).__name__}: {str(news_send_exc)[:250]}",
                    flush=True,
                )
                break

        # Existing report delivery remains in place.
        send_telegram_message(
            "✅ Autonomous Financial Analyst report is ready.\n"
            f"Generated: {generated_at}\n"
            f"Report image pages: {len(images)}\n"
            "A separate 11-topic macro-factor news digest was attempted before these images."
        )
        for page_number, image_path in enumerate(images, start=1):
            print(f"Uploading Telegram report page {page_number}/{len(images)}: {Path(image_path).name}", flush=True)
            send_telegram_photo(
                image_path,
                caption=f"India Market Sentiment Report | {generated_at} | Page {page_number}/{len(images)}",
            )

        print(f"SUCCESS: Sent {len(images)} report image(s) to Telegram; factor digest attempted.", flush=True)
        print(f"Fresh macro-factor news records fetched: {sum(len(items) for items in factor_articles.values())}", flush=True)
        return 0

    except Exception as exc:
        print(f"ERROR: Market report delivery failed: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        try:
            send_telegram_message(
                "❌ Autonomous Financial Analyst report automation failed.\n"
                f"Error: {type(exc).__name__}: {str(exc)[:700]}\n"
                "Check logs/telegram_hourly.log for details."
            )
        except Exception as notify_exc:
            print(
                "Could not send the failure notification to Telegram: "
                f"{type(notify_exc).__name__}: {notify_exc}",
                flush=True,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
