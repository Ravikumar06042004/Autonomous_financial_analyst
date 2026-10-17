from django.urls import path

from dashboard.views import (
    dashboard_home,
    refresh_market_sentiment,
)

urlpatterns = [
    path("", dashboard_home, name="dashboard_home"),
    path(
        "market-sentiment/refresh/",
        refresh_market_sentiment,
        name="refresh_market_sentiment",
    ),
]