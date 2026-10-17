from tools.market_data import (
    get_intraday_data,
)

from tools.technical_indicators import (
    calculate_indicators,
)


if __name__ == "__main__":

    df = get_intraday_data(
        "JPM"
    )

    indicators = (
        calculate_indicators(
            df
        )
    )

    print(
        indicators
    )