import pandas as pd

from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.volatility import BollingerBands


def calculate_indicators(df: pd.DataFrame) -> dict:
    if df.empty:
        raise ValueError("DataFrame is empty")

    close = df["close"]

    rsi = RSIIndicator(close=close, window=14).rsi()

    macd = MACD(close=close)
    macd_line = macd.macd()
    macd_signal = macd.macd_signal()

    bollinger = BollingerBands(close=close, window=20, window_dev=2)

    sma_20 = SMAIndicator(close=close, window=20).sma_indicator()
    ema_50 = EMAIndicator(close=close, window=50).ema_indicator()

    latest = {
        "rsi": round(float(rsi.iloc[-1]), 2),
        "macd": round(float(macd_line.iloc[-1]), 4),
        "macd_signal": round(float(macd_signal.iloc[-1]), 4),
        "bollinger_upper": round(float(bollinger.bollinger_hband().iloc[-1]), 2),
        "bollinger_lower": round(float(bollinger.bollinger_lband().iloc[-1]), 2),
        "sma_20": round(float(sma_20.iloc[-1]), 2),
        "ema_50": round(float(ema_50.iloc[-1]), 2),
        "current_price": round(float(close.iloc[-1]), 2),
    }

    return latest