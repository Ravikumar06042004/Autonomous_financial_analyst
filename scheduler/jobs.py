import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config.watchlist import WATCHLIST

from database.repository import (
    initialize_database,
    save_market_context,
)

from services.analysis_service import (
    analyze_company,
)

from services.market_sentiment_service import (
    build_market_sentiment_report,
)

from notifications.slack import (
    send_slack_message,
)


MARKET_TZ = ZoneInfo(
    "America/New_York"
)


def _enabled(
    name: str,
    default: bool = False,
) -> bool:

    return (
        os.getenv(
            name,
            str(default),
        )
        .strip()
        .lower()
        == "true"
    )


def _max_companies() -> int:

    try:

        return max(
            1,
            min(
                int(
                    os.getenv(
                        "MAX_COMPANIES_PER_RUN",
                        "10",
                    )
                ),
                len(WATCHLIST),
            ),
        )

    except ValueError:

        return len(
            WATCHLIST
        )


def is_market_window() -> bool:

    now = datetime.now(
        MARKET_TZ
    )

    if now.weekday() >= 5:
        return False

    market_open = now.replace(
        hour=9,
        minute=30,
        second=0,
        microsecond=0,
    )

    market_close = now.replace(
        hour=16,
        minute=0,
        second=0,
        microsecond=0,
    )

    return (
        market_open
        <= now
        <= market_close
    )


def _slack_market_summary(
    context,
):

    lines = [
        "Global Market Cues & Indian Market Sentiment",
        "",
        f"Overall: {context.get('overall_sentiment', 'Unknown')}",
        "",
    ]

    for row in context.get(
        "factor_matrix",
        [],
    ):

        lines.append(
            f"{row.get('factor')}: "
            f"{row.get('latest_signal')} -> "
            f"{row.get('expected_india_impact')}"
        )

    return "\n".join(lines)


def run_analysis_job():

    initialize_database()

    if not is_market_window():

        print(
            "Outside configured U.S. market window. "
            "Job skipped."
        )

        return

    market_context = (
        build_market_sentiment_report()
    )

    save_market_context(
        market_context
    )

    if _enabled(
        "ENABLE_SLACK",
        False,
    ):

        print(
            send_slack_message(
                _slack_market_summary(
                    market_context
                )
            )
        )

    for company in WATCHLIST[
        :_max_companies()
    ]:

        try:

            result = analyze_company(
                company["name"],
                company["symbol"],
                market_context=market_context,
            )

            message = (
                "Financial Intelligence\n\n"
                f"Company: "
                f"{result['company_name']} "
                f"({result['symbol']})\n"
                f"Price: "
                f"{result['indicators']['current_price']}\n"
                f"RSI: "
                f"{result['indicators']['rsi']}\n"
                f"Sentiment: "
                f"{result['sentiment']}\n"
                f"Risk: "
                f"{result['risk_level']}\n"
                f"Signal: "
                f"{result['signal']}\n"
            )

            if _enabled(
                "ENABLE_SLACK",
                False,
            ):

                print(
                    send_slack_message(
                        message
                    )
                )

            else:

                print(message)

        except Exception as exc:

            print(
                f"{company['symbol']} "
                f"analysis failed: {exc}"
            )