import os

from dotenv import load_dotenv

from database.repository import save_trade
from tools.risk_tools import calculate_position_size
from tools.trading_tools import submit_paper_order

load_dotenv()


def execute_paper_signal(
    symbol: str,
    signal: str,
    account_value: float,
    current_price: float,
):
    signal = signal.upper()

    enabled = os.getenv(
        "ENABLE_PAPER_TRADING",
        "false",
    ).lower() == "true"

    if signal not in {"BUY", "SELL"}:
        return {
            "status": "skipped",
            "reason": "Signal is HOLD or unsupported.",
        }

    if not enabled:
        return {
            "status": "skipped",
            "reason": "ENABLE_PAPER_TRADING is false.",
        }

    quantity = calculate_position_size(
        account_value,
        current_price,
    )

    if quantity == 0:
        return {
            "status": "skipped",
            "reason": "Calculated position size is zero.",
        }

    order = submit_paper_order(
        symbol,
        quantity,
        signal,
    )

    order_id = str(
        getattr(order, "id", "")
    )

    order_status = str(
        getattr(order, "status", "submitted")
    )

    save_trade(
        symbol,
        signal,
        quantity,
        order_id,
        order_status,
    )

    return {
        "status": order_status,
        "symbol": symbol.upper(),
        "side": signal,
        "quantity": quantity,
        "order_id": order_id,
    }