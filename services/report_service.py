import re


def _extract(
    text: str,
    heading: str,
    next_heading: str | None = None,
) -> str:

    pattern = (
        rf"{re.escape(heading)}\s*\n(.*?)"
        rf"(?=\n{re.escape(next_heading)}\s*\n|\Z)"
        if next_heading
        else
        rf"{re.escape(heading)}\s*\n(.*)\Z"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE | re.DOTALL,
    )

    return (
        match.group(1).strip()
        if match
        else ""
    )


def parse_report(report: str) -> dict:

    signal = "HOLD"
    risk = "Unknown"
    sentiment = "Unknown"

    signal_match = re.search(
        r"^SIGNAL\s*$\n\s*(BUY|SELL|HOLD)\b",
        report,
        re.IGNORECASE | re.MULTILINE,
    )

    risk_match = re.search(
        r"^RISK\s*$\n\s*(LOW|MEDIUM|HIGH)\b",
        report,
        re.IGNORECASE | re.MULTILINE,
    )

    sentiment_match = re.search(
        r"^SENTIMENT\s*$.*?"
        r"Overall sentiment:\s*"
        r"(POSITIVE|NEGATIVE|NEUTRAL)",
        report,
        re.IGNORECASE | re.DOTALL,
    )

    if signal_match:

        signal = signal_match.group(1).upper()

    else:

        fallback = re.search(
            r"\b(BUY|SELL|HOLD)\b",
            report.upper(),
        )

        if fallback:
            signal = fallback.group(1)

    if risk_match:

        risk = risk_match.group(1).title()

    else:

        fallback = re.search(
            r"\b(LOW|MEDIUM|HIGH)\b",
            report.upper(),
        )

        if fallback:
            risk = fallback.group(1).title()

    if sentiment_match:

        sentiment = sentiment_match.group(1).title()

    else:

        fallback = re.search(
            r"\b(POSITIVE|NEGATIVE|NEUTRAL)\b",
            report.upper(),
        )

        if fallback:
            sentiment = fallback.group(1).title()

    return {
        "signal": signal,
        "risk_level": risk,
        "sentiment": sentiment,
    }


def build_market_context_markdown(
    market_context: dict | None,
) -> str:

    if not market_context:
        return ""

    lines = [
        "",
        "## Global Market Cues & Indian Market Sentiment",
        "",
    ]

    lines.append(
        f"**Overall Market Sentiment:** "
        f"{market_context.get('overall_sentiment', 'Unavailable')}"
    )

    lines.extend(
        [
            "",
            "### Global Market Impact Matrix",
            "",
            "| Factor | Latest Signal | Expected India Impact |",
            "|---|---|---|",
        ]
    )

    for row in market_context.get(
        "factor_matrix",
        [],
    ):

        lines.append(
            f"| {row.get('factor', '')} "
            f"| {row.get('latest_signal', '')} "
            f"| {row.get('expected_india_impact', '')} |"
        )

    lines.extend(
        [
            "",
            "### Sector-wise Sentiment",
            "",
            "| Sector | Sentiment | Score | Outlook |",
            "|---|---|---:|---|",
        ]
    )

    for sector in market_context.get(
        "sector_sentiment",
        [],
    ):

        lines.append(
            f"| {sector.get('sector', '')} "
            f"| {sector.get('sentiment', '')} "
            f"| {sector.get('sentiment_score', '')} "
            f"| {sector.get('outlook', '')} |"
        )

    return "\n".join(lines)


def build_report(
    company_name: str,
    symbol: str,
    indicators: dict,
    news: list[dict],
    ai_report: str,
    market_context: dict | None = None,
) -> dict:

    metadata = parse_report(
        ai_report
    )

    market_section = (
        build_market_context_markdown(
            market_context
        )
    )

    full_report = (
        ai_report
        + market_section
    )

    return {
        "company_name": company_name,
        "symbol": symbol.upper(),
        "indicators": indicators,
        "news": news,
        "ai_report": ai_report,
        "report": full_report,
        "market_context": market_context or {},
        **metadata,
    }