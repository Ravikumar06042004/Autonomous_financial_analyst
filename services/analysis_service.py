from __future__ import annotations

import os

from config.llm_config import LLM_MODE

from database.repository import (
    initialize_database,
    save_company,
    save_news_articles,
    save_report,
)

from services.news_service import (
    get_clean_financial_news,
)

from services.report_service import (
    build_report,
)

from tools.market_data import (
    get_intraday_data,
)

from tools.technical_indicators import (
    calculate_indicators,
)


def _get_market_context():
    """
    Get the global market + sector sentiment layer.

    The market sentiment engine is independent from the
    company-level mock analysis, so it can continue working
    even when LLM_MODE=mock.
    """

    try:

        from services.market_sentiment_service import (
            run_market_sentiment,
        )

        return run_market_sentiment(
            force=False,
            mode="live",
            print_report=False,
        )

    except Exception as exc:

        print(
            "\n[MARKET CONTEXT] "
            f"Could not refresh market context: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "overall_score": None,
            "bias": "INSUFFICIENT_DATA",
            "evidence_quality_pct": 0,
            "coverage": 0,
            "risk_regime": "UNKNOWN",
            "volatility_regime": "UNKNOWN",
            "sectors": {},
            "latest_factors": {},
            "news_articles": [],
            "drivers": [],
            "diagnostics": [
                f"Market context unavailable: "
                f"{type(exc).__name__}"
            ],
        }


def _build_mock_report(
    company_name: str,
    symbol: str,
    indicators: dict,
    news: list[dict],
    mock_result,
) -> str:
    """
    Your existing generate_mock_analysis() returns a dictionary.

    build_report() expects a text report, so this function converts
    that dictionary into the structured report format used by the
    rest of the application.
    """

    if isinstance(
        mock_result,
        str,
    ):

        return mock_result

    if not isinstance(
        mock_result,
        dict,
    ):

        return (
            "COMPANY\n"
            f"{company_name} ({symbol.upper()})\n\n"
            "NEWS SUMMARY\n"
            f"Analysed {len(news)} article(s).\n\n"
            "SENTIMENT\n"
            "Unknown\n\n"
            "TECHNICAL SUMMARY\n"
            f"Price: {indicators.get('current_price')}\n"
            f"RSI: {indicators.get('rsi')}\n"
            f"MACD: {indicators.get('macd')}\n\n"
            "RISK\n"
            "Unknown\n\n"
            "SIGNAL\n"
            "HOLD\n\n"
            "DATA LIMITATIONS\n"
            "Unexpected mock-analysis response format."
        )

    sentiment = (
        mock_result.get("sentiment")
        or mock_result.get("overall_sentiment")
        or "Unknown"
    )

    sentiment_score = (
        mock_result.get("sentiment_score")
        if mock_result.get("sentiment_score") is not None
        else mock_result.get("score", "N/A")
    )

    risk_level = (
        mock_result.get("risk_level")
        or mock_result.get("risk")
        or "Unknown"
    )

    signal = (
        mock_result.get("signal")
        or mock_result.get("recommendation")
        or "HOLD"
    )

    technical_score = mock_result.get(
        "technical_score",
        mock_result.get(
            "technical_composite",
            "N/A",
        ),
    )

    summary = (
        mock_result.get("summary")
        or mock_result.get("analysis")
        or mock_result.get("reasoning")
        or ""
    )

    reasons = mock_result.get(
        "reasons",
        [],
    )

    if isinstance(
        reasons,
        str,
    ):

        reasons = [
            reasons
        ]

    reason_lines = []

    for reason in reasons:

        reason_lines.append(
            f"- {reason}"
        )

    if summary:

        reason_lines.append(
            f"- {summary}"
        )

    if not reason_lines:

        reason_lines.append(
            "- Deterministic development-mode analysis."
        )

    return f"""COMPANY
{company_name} ({symbol.upper()})

NEWS SUMMARY
Analysed {len(news)} cleaned financial-news article(s).
Mock sentiment is keyword-based and is used only for development/testing.

SENTIMENT
{sentiment}
Score: {sentiment_score}

TECHNICAL SUMMARY
Price: {indicators.get('current_price')}
RSI: {indicators.get('rsi')}
MACD: {indicators.get('macd')}
MACD Signal: {indicators.get('macd_signal')}
Bollinger Upper: {indicators.get('bollinger_upper')}
Bollinger Lower: {indicators.get('bollinger_lower')}
SMA20: {indicators.get('sma_20')}
EMA50: {indicators.get('ema_50')}
Technical composite: {technical_score}

RISK
{risk_level}

SIGNAL
{str(signal).upper()}

KEY REASONS
{chr(10).join(reason_lines)}

DATA LIMITATIONS
LLM_MODE=mock.
This report uses the deterministic development analysis path.
No live LLM API call is made for company-level analysis.
"""


def analyze_company(
    company_name: str,
    symbol: str,
    persist: bool = True,
    market_context: dict | None = None,
) -> dict:

    initialize_database()

    company_name = (
        company_name.strip()
    )

    symbol = (
        symbol.strip()
        .upper()
    )

    if not company_name:

        raise ValueError(
            "company_name is required."
        )

    if not symbol:

        raise ValueError(
            "symbol is required."
        )

    print(
        "\n"
        + "=" * 80
    )

    print(
        f"ANALYSING: "
        f"{company_name} ({symbol})"
    )

    print(
        "=" * 80
    )

    # ---------------------------------------------------------
    # COMPANY
    # ---------------------------------------------------------

    save_company(
        company_name,
        symbol,
    )

    # ---------------------------------------------------------
    # MARKET DATA
    # ---------------------------------------------------------

    print(
        "\n[1/6] Fetching 15-minute market data..."
    )

    market_df = get_intraday_data(
        symbol
    )

    if market_df is None:

        raise ValueError(
            f"No market data returned for {symbol}."
        )

    if market_df.empty:

        raise ValueError(
            f"Market data is empty for {symbol}."
        )

    print(
        f"Market rows: {len(market_df)}"
    )

    # ---------------------------------------------------------
    # TECHNICAL INDICATORS
    # ---------------------------------------------------------

    print(
        "\n[2/6] Calculating technical indicators..."
    )

    indicators = calculate_indicators(
        market_df
    )

    print(
        f"Current price: "
        f"{indicators.get('current_price')}"
    )

    print(
        f"RSI: "
        f"{indicators.get('rsi')}"
    )

    # ---------------------------------------------------------
    # COMPANY NEWS
    # ---------------------------------------------------------

    print(
        "\n[3/6] Fetching company financial news..."
    )

    news = get_clean_financial_news(
        company_name,
        symbol,
        max_results=5,
    )

    if news is None:

        news = []

    print(
        f"News articles: {len(news)}"
    )

    if persist:

        save_news_articles(
            symbol,
            news,
        )

    # ---------------------------------------------------------
    # GLOBAL MARKET + SECTOR SENTIMENT
    # ---------------------------------------------------------

    print(
        "\n[4/6] Building global market "
        "and sector sentiment..."
    )

    if market_context is None:

        market_context = (
            _get_market_context()
        )

    print(
        "Overall market bias: "
        f"{market_context.get('bias', 'UNKNOWN')}"
    )

    print(
        "Sectors available: "
        f"{len(market_context.get('sectors', {}))}"
    )

    # ---------------------------------------------------------
    # MOCK / LIVE ANALYSIS
    # ---------------------------------------------------------

    print(
        "\n[5/6] Generating company analysis..."
    )

    if LLM_MODE == "mock":

        print(
            "LLM_MODE=mock"
        )

        from services.mock_analysis import (
            generate_mock_analysis,
        )

        mock_result = generate_mock_analysis(
            company_name=company_name,
            symbol=symbol,
            indicators=indicators,
            news=news,
        )

        ai_report = _build_mock_report(
            company_name=company_name,
            symbol=symbol,
            indicators=indicators,
            news=news,
            mock_result=mock_result,
        )

    else:

        print(
            "LLM_MODE=live"
        )

        from agents.crew import (
            run_financial_analysis,
        )

        ai_report = run_financial_analysis(
            company_name=company_name,
            symbol=symbol,
            news=news,
            indicators=indicators,
            market_context=market_context,
        )

    # ---------------------------------------------------------
    # FINAL REPORT
    # ---------------------------------------------------------

    print(
        "\n[6/6] Building final report..."
    )

    result = build_report(
        company_name=company_name,
        symbol=symbol,
        indicators=indicators,
        news=news,
        ai_report=ai_report,
        market_context=market_context,
    )

    # ---------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------

    if persist:

        save_report(
            symbol=symbol,
            company_name=company_name,
            indicators=indicators,
            report=ai_report,
            sentiment=result.get(
                "sentiment",
                "Unknown",
            ),
            risk_level=result.get(
                "risk_level",
                "Unknown",
            ),
            signal=result.get(
                "signal",
                "HOLD",
            ),
        )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "ANALYSIS COMPLETE"
    )

    print(
        "=" * 80
    )

    return result