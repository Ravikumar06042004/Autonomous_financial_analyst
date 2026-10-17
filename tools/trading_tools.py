import os

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
)
from alpaca.trading.requests import (
    MarketOrderRequest,
)
from dotenv import load_dotenv


load_dotenv()


def get_trading_client() -> TradingClient:

    api_key = os.getenv(
        "ALPACA_API_KEY"
    )

    secret_key = os.getenv(
        "ALPACA_SECRET_KEY"
    )

    if not api_key:
        raise ValueError(
            "ALPACA_API_KEY is missing."
        )

    if not secret_key:
        raise ValueError(
            "ALPACA_SECRET_KEY is missing."
        )

    return TradingClient(
        api_key,
        secret_key,
        paper=True,
    )


def get_account():

    client = get_trading_client()

    return client.get_account()


def submit_paper_order(
    symbol: str,
    quantity: int,
    side: str,
):

    symbol = symbol.upper().strip()

    side = side.upper().strip()

    if quantity <= 0:
        raise ValueError(
            "Quantity must be greater than zero."
        )

    if side == "BUY":
        order_side = OrderSide.BUY

    elif side == "SELL":
        order_side = OrderSide.SELL

    else:
        raise ValueError(
            "Side must be BUY or SELL."
        )

    client = get_trading_client()

    order_request = MarketOrderRequest(
        symbol=symbol,
        qty=quantity,
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )

    return client.submit_order(
        order_data=order_request
    )