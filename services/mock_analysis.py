from tools.risk_tools import (
    determine_risk_level,
)


def _simple_sentiment(
    news: list[dict],
) -> tuple[str, float]:

    positive_words = {
        "growth",
        "profit",
        "profits",
        "beat",
        "strong",
        "surge",
        "higher",
        "record",
        "positive",
        "expansion",
        "gain",
    }

    negative_words = {
        "loss",
        "losses",
        "decline",
        "lower",
        "drop",
        "fall",
        "weak",
        "negative",
        "risk",
        "lawsuit",
        "investigation",
    }

    score = 0

    for article in news:

        text = (
            f"{article.get('title', '')} "
            f"{article.get('content', '')}"
        ).lower()

        for word in positive_words:
            if word in text:
                score += 1

        for word in negative_words:
            if word in text:
                score -= 1

    if score > 0:
        return "Positive", min(score / 10, 1.0)

    if score < 0:
        return "Negative", max(score / 10, -1.0)

    return "Neutral", 0.0


def generate_mock_analysis(
    company_name: str,
    symbol: str,
    indicators: dict,
    news: list[dict],
) -> dict:

    sentiment, sentiment_score = _simple_sentiment(
        news
    )

    current_price = indicators["current_price"]
    sma_20 = indicators["sma_20"]
    ema_50 = indicators["ema_50"]
    rsi = indicators["rsi"]
    macd = indicators["macd"]
    macd_signal = indicators["macd_signal"]

    if rsi <= 30:
        rsi_view = "RSI is in an oversold range."

    elif rsi >= 70:
        rsi_view = "RSI is in an overbought range."

    else:
        rsi_view = "RSI is in a non-extreme range."

    if macd > macd_signal:
        macd_view = "MACD is above its signal line."

    else:
        macd_view = "MACD is below its signal line."

    above_moving_averages = (
        current_price > sma_20
        and current_price > ema_50
    )

    below_moving_averages = (
        current_price < sma_20
        and current_price < ema_50
    )

    if above_moving_averages:
        technical_view = (
            f"{rsi_view} "
            f"{macd_view} "
            "Price is above both SMA 20 and EMA 50."
        )

    elif below_moving_averages:
        technical_view = (
            f"{rsi_view} "
            f"{macd_view} "
            "Price is below both SMA 20 and EMA 50."
        )

    else:
        technical_view = (
            f"{rsi_view} "
            f"{macd_view} "
            "Price is mixed relative to the moving averages."
        )

    risk_level = determine_risk_level(
        rsi=rsi,
        sentiment_score=sentiment_score,
        current_price=current_price,
        sma_20=sma_20,
        ema_50=ema_50,
    )

    if (
        above_moving_averages
        and macd > macd_signal
        and sentiment_score >= 0
    ):
        signal = "BUY"

    elif (
        below_moving_averages
        and macd < macd_signal
        and sentiment_score <= 0
    ):
        signal = "SELL"

    else:
        signal = "HOLD"

    if risk_level == "High":
        signal = "HOLD"

    return {
        "company": company_name,
        "symbol": symbol,
        "sentiment": sentiment,
        "sentiment_score": round(
            sentiment_score,
            2,
        ),
        "technical_view": technical_view,
        "risk_level": risk_level,
        "signal": signal,
        "summary": (
            "Development-mode analysis generated "
            "without an external LLM API call."
        ),
        "reasoning": (
            "The development fallback combines the "
            "retrieved news text with deterministic "
            "technical and risk rules. It is not an "
            "LLM-generated financial analysis."
        ),
    }