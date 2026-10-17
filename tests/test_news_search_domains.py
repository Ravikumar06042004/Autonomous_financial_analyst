from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools.news_search import (
    _host_matches_allowed_domains,
    search_topic_news,
)


def _article(
    url: str,
    title: str,
    published_at: str,
) -> dict:
    return {
        "title": title,
        "link": url,
        "snippet": (
            "Global markets moved after investors reacted to economic data."
        ),
        "date": published_at,
        "source": "Test Source",
    }


def test_domain_allow_list_matches_domain_and_subdomains():
    assert _host_matches_allowed_domains(
        "https://www.moneycontrol.com/news/story.html",
        ["moneycontrol.com"],
    )

    assert _host_matches_allowed_domains(
        "https://m.moneycontrol.com/news/story.html",
        ["moneycontrol.com"],
    )

    assert not _host_matches_allowed_domains(
        "https://moneycontrol.com.evil.example/story.html",
        ["moneycontrol.com"],
    )

    assert not _host_matches_allowed_domains(
        "https://example.com/moneycontrol.com/story.html",
        ["moneycontrol.com"],
    )

    assert not _host_matches_allowed_domains(
        "not-a-valid-url",
        ["moneycontrol.com"],
    )


def test_search_discards_results_outside_requested_domain():
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=2)).isoformat()

    client = type("FakeClient", (), {})()
    client.seen_domains = None

    def fake_search_news(*, query, num, domains=None):
        client.seen_domains = domains

        return [
            _article(
                "https://www.moneycontrol.com/news/global/valid.html",
                "Global indices rise",
                fresh,
            ),
            _article(
                "https://example.com/global/unrelated.html",
                "World markets rise",
                fresh,
            ),
        ]

    client.search_news = fake_search_news

    with patch("tools.news_search._client", return_value=client):
        results = search_topic_news(
            query="global indices latest news",
            max_results=5,
            time_range="day",
            domains=["moneycontrol.com"],
        )

    assert client.seen_domains == ["moneycontrol.com"]
    assert len(results) == 1
    assert results[0]["url"].startswith(
        "https://www.moneycontrol.com/"
    )


def test_multiple_allowed_domains_are_supported():
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=1)).isoformat()

    client = type("FakeClient", (), {})()
    client.search_news = lambda **kwargs: [
        _article(
            "https://moneycontrol.com/news/a.html",
            "Article A",
            fresh,
        ),
        _article(
            "https://www.reuters.com/world/b.html",
            "Article B",
            fresh,
        ),
        _article(
            "https://example.org/news/c.html",
            "Article C",
            fresh,
        ),
    ]

    with patch("tools.news_search._client", return_value=client):
        results = search_topic_news(
            query="global news",
            max_results=5,
            domains=["moneycontrol.com", "reuters.com"],
        )

    assert {item["url"] for item in results} == {
        "https://moneycontrol.com/news/a.html",
        "https://www.reuters.com/world/b.html",
    }