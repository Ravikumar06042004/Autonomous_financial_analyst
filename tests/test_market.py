from tools.market_data import (
    get_intraday_data,
)


if __name__ == "__main__":

    df = get_intraday_data(
        symbol="JPM"
    )

    print(
        df.tail()
    )

    print(
        "\nRows:",
        len(df),
    )

    print(
        "\nColumns:",
        list(df.columns),
    )