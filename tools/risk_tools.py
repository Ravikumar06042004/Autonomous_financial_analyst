def determine_risk_level(
    rsi: float,
    sentiment_score: float,
    current_price: float,
    sma_20: float,
    ema_50: float,
) -> str:

    risk_points = 0

    if rsi >= 70 or rsi <= 30:
        risk_points += 2

    if abs(sentiment_score) < 0.15:
        risk_points += 1

    if current_price < sma_20 and current_price < ema_50:
        risk_points += 1

    if risk_points >= 3:
        return "High"

    if risk_points >= 1:
        return "Medium"

    return "Low"


def calculate_position_size(
    account_value: float,
    current_price: float,
    risk_percentage: float = 1.0,
) -> int:

    if account_value <= 0:
        return 0

    if current_price <= 0:
        return 0

    risk_amount = (
        account_value
        * risk_percentage
        / 100
    )

    quantity = int(
        risk_amount / current_price
    )

    return max(
        quantity,
        0,
    )


def apply_risk_guard(
    signal: str,
    risk_level: str,
) -> str:

    signal = str(
        signal
    ).upper().strip()

    risk_level = str(
        risk_level
    ).capitalize().strip()

    if signal not in {
        "BUY",
        "SELL",
        "HOLD",
    }:
        return "HOLD"

    if risk_level == "High":
        return "HOLD"

    return signal