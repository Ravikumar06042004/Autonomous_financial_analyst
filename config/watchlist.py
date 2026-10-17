WATCHLIST = [
    {
        "name": "JPMorgan Chase",
        "symbol": "JPM",
        "sector": "Banking",
    },
    {
        "name": "Bank of America",
        "symbol": "BAC",
        "sector": "Banking",
    },
    {
        "name": "Citigroup",
        "symbol": "C",
        "sector": "Banking",
    },
    {
        "name": "Wells Fargo",
        "symbol": "WFC",
        "sector": "Banking",
    },
    {
        "name": "Goldman Sachs",
        "symbol": "GS",
        "sector": "Investment Banking",
    },
    {
        "name": "Morgan Stanley",
        "symbol": "MS",
        "sector": "Investment Banking",
    },
    {
        "name": "BlackRock",
        "symbol": "BLK",
        "sector": "Asset Management",
    },
    {
        "name": "American Express",
        "symbol": "AXP",
        "sector": "Financial Services",
    },
    {
        "name": "Charles Schwab",
        "symbol": "SCHW",
        "sector": "Financial Services",
    },
    {
        "name": "CME Group",
        "symbol": "CME",
        "sector": "Financial Markets",
    },
]


def get_watchlist() -> list[dict]:
    return WATCHLIST.copy()