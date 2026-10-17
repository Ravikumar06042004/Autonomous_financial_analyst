import json

from django.contrib import messages
from django.shortcuts import redirect, render

from database.repository import get_latest_market_sentiment_report
from services.market_sentiment_service import (
    console_report,
    run_market_sentiment,
)


def dashboard_home(request):
    market_row = get_latest_market_sentiment_report()

    market_report = None

    if market_row and market_row.get("report_json"):
        try:
            market_report = json.loads(
                market_row["report_json"]
            )
        except (TypeError, json.JSONDecodeError):
            market_report = None

    market_report_text = ""

    if market_report:
        market_report_text = console_report(market_report)

    context = {
        "market_report": market_report,
        "market_report_text": market_report_text,
    }

    return render(
        request,
        "dashboard/home.html",
        context,
    )


def refresh_market_sentiment(request):
    if request.method != "POST":
        return redirect("dashboard_home")

    try:
        # ALWAYS generate a fresh LIVE report
        report = run_market_sentiment(
            force=True,
            mode="live",
            print_report=False,
        )

        # Important:
        # Display the exact report returned by this LIVE run.
        market_report_text = console_report(report)

        return render(
            request,
            "dashboard/home.html",
            {
                "market_report": report,
                "market_report_text": market_report_text,
            },
        )

    except Exception as exc:
        messages.error(
            request,
            (
                "Market sentiment refresh failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

        return redirect("dashboard_home")