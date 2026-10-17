def normalize_sentiment(sentiment: str) -> str:
    """
    Convert sentiment text into a standard label.
    """

    value = str(sentiment).strip().lower()

    if value in {"positive", "bullish"}:
        return "Positive"

    if value in {"negative", "bearish"}:
        return "Negative"

    return "Neutral"


def clamp_sentiment_score(score: float) -> float:
    """
    Keep the sentiment score between -1 and +1.
    """

    score = float(score)

    return max(-1.0, min(1.0, score))


def classify_sentiment_score(score: float) -> str:
    """
    Convert a numerical sentiment score into a label.
    """

    score = clamp_sentiment_score(score)

    if score >= 0.25:
        return "Positive"

    if score <= -0.25:
        return "Negative"

    return "Neutral"