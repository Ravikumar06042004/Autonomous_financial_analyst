import pandas as pd
import yfinance as yf


def get_intraday_data(
    symbol: str,
    period: str = "5d",
    interval: str = "15m",
) -> pd.DataFrame:

    symbol = symbol.upper().strip()

    if not symbol:
        raise ValueError("Symbol cannot be empty.")

    try:

        df = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            group_by="column",
            multi_level_index=False,
        )

        if df.empty:
            raise ValueError(
                f"No market data returned for {symbol}"
            )

        if isinstance(df.columns, pd.MultiIndex):

            df.columns = [
                column[0]
                for column in df.columns
            ]

        df = df.reset_index()

        df.columns = [
            str(column)
            .strip()
            .lower()
            .replace(" ", "_")
            for column in df.columns
        ]

        required_columns = {
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        missing = required_columns.difference(
            df.columns
        )

        if missing:
            raise ValueError(
                f"Missing market columns: {sorted(missing)}"
            )

        return df

    except Exception as exc:

        raise RuntimeError(
            f"Market-data error for {symbol}: {exc}"
        ) from exc