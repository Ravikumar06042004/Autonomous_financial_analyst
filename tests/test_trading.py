import os

from dotenv import load_dotenv

from tools.risk_tools import (
    calculate_position_size,
    determine_risk_level,
)


load_dotenv()


if __name__ == "__main__":

    quantity = (
        calculate_position_size(
            account_value=100000,
            current_price=335,
            risk_percentage=1.0,
        )
    )

    risk = determine_risk_level(
        rsi=43.51,
        sentiment_score=0.20,
        current_price=335,
        sma_20=334.87,
        ema_50=336.42,
    )

    print(
        "Trading mode:",
        os.getenv(
            "ENABLE_PAPER_TRADING",
            "false",
        ),
    )

    print(
        "Calculated quantity:",
        quantity,
    )

    print(
        "Risk level:",
        risk,
    )

    print(
        "\nNo order was submitted."
    )