from datetime import datetime, timedelta, timezone

from services.market_sentiment_service import (
    build_market_sentiment_report,
    console_report,
)


def main():
    now = datetime.now(
        timezone.utc
    )

    observations = [
        {
            "factor": "brent",
            "value": 100.0,
            "previous": 103.0,
            "unit": "USD_per_barrel",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "us10y",
            "value": 4.20,
            "previous": 4.40,
            "unit": "percent",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "dxy",
            "value": 100.0,
            "previous": 101.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "usd_inr",
            "value": 96.0,
            "previous": 96.5,
            "unit": "INR_per_USD",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "sp500",
            "value": 6000.0,
            "previous": 5960.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "nasdaq",
            "value": 20000.0,
            "previous": 19800.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "asia_index",
            "value": 41000.0,
            "previous": 40500.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "india_vix",
            "value": 14.0,
            "previous": 15.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "nifty",
            "value": 25000.0,
            "previous": 24700.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "fii_cash",
            "value": 2500.0,
            "previous": None,
            "unit": "INR_crore",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "dii_cash",
            "value": 1200.0,
            "previous": None,
            "unit": "INR_crore",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "gift_nifty",
            "value": 25100.0,
            "previous": 24800.0,
            "unit": "index",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },

        {
            "factor": "advance_decline",
            "value": 1.4,
            "previous": None,
            "unit": "ratio",
            "observed_at": now.isoformat(),
            "available_at": now.isoformat(),
            "source": "TEST",
        },
    ]

    news = [
        {
            "title":
                "China announces new stimulus support for manufacturing",

            "url":
                "https://example.com/china-stimulus",

            "source":
                "TEST",

            "published_at":
                (
                    now
                    - timedelta(hours=1)
                ).isoformat(),

            "content":
                (
                    "China announces stimulus "
                    "to support manufacturing "
                    "and demand."
                ),

            "sectors": [
                "METALS",
                "CHEMICALS",
                "CAPITAL_GOODS",
            ],

            "event_type":
                "CHINA_STIMULUS",

            "event_key":
                "test-china-stimulus",

            "evidence":
                "China announces stimulus",

            "relevance":
                0.9,

            "confidence":
                0.85,

            "magnitude":
                0.7,

            "india_direction":
                0.35,
        },

        {
            "title":
                "Crude oil prices fall as supply concerns ease",

            "url":
                "https://example.com/crude-down",

            "source":
                "TEST",

            "published_at":
                (
                    now
                    - timedelta(hours=2)
                ).isoformat(),

            "content":
                (
                    "Crude oil prices fall "
                    "as supply concerns ease."
                ),

            "sectors": [
                "AVIATION",
                "PAINTS",
                "AUTO",
                "LOGISTICS",
            ],

            "event_type":
                "CRUDE_DOWN",

            "event_key":
                "test-crude-down",

            "evidence":
                "Crude oil prices fall",

            "relevance":
                0.9,

            "confidence":
                0.85,

            "magnitude":
                0.8,

            "india_direction":
                0.25,
        },
    ]

    report = build_market_sentiment_report(
        observations,
        news,
        asof=now,
        mode="demo",
    )

    print(
        console_report(
            report
        )
    )

    sector_count = len(
        report.get(
            "sectors",
            {},
        )
    )

    assert sector_count == 22, (
        f"Expected 22 sectors (20 industry + 2 global), got {sector_count}"
    )
    assert "# India market sentiment" in (
        console_report(report)
    )

    assert "## Sector signals" in (
        console_report(report)
    )

    assert "## Drivers" in (
        console_report(report)
    )

    assert "## Diagnostics" in (
        console_report(report)
    )

    print(
        "\nTEST COMPLETE"
    )
def test_sector_sentiment_demo():
    main()

if __name__ == "__main__":
    main()