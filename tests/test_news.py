from tools.news_search import search_financial_news


def main():

    print()
    print("=" * 80)
    print("FINANCIAL NEWS SEARCH TEST")
    print("=" * 80)

    company_name = "JPMorgan Chase"
    symbol = "JPM"

    print(
        f"Company : {company_name}"
    )

    print(
        f"Symbol  : {symbol}"
    )

    print(
        "Days    : 7"
    )

    try:

        results = search_financial_news(
            company_name=company_name,
            symbol=symbol,
            max_results=5,
            days=7,
        )

        if not isinstance(
            results,
            list,
        ):
            raise TypeError(
                "search_financial_news() "
                "must return a list."
            )

        print()
        print(
            f"Results returned: {len(results)}"
        )

        for index, item in enumerate(
            results,
            start=1,
        ):

            print()
            print(
                f"{index}. "
                f"{item.get('title', 'Untitled')}"
            )

            print(
                f"   Source : "
                f"{item.get('source', 'Unknown')}"
            )

            print(
                f"   URL    : "
                f"{item.get('url', '')}"
            )

            print(
                f"   Cached : "
                f"{item.get('cached', False)}"
            )

        print()
        print("=" * 80)
        print("TEST PASSED")
        print("=" * 80)

    except Exception as exc:

        print()
        print("=" * 80)
        print("TEST FAILED")
        print("=" * 80)

        raise


if __name__ == "__main__":
    main()