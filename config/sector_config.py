"""
Sector and financial-portal configuration.

This module has two responsibilities:

1. Load the deterministic 20-sector scoring rules from sector_rules.json.
2. Store the five high-level display sectors, financial portals, macro-factor
   labels and macro-news queries used by the market-intelligence layer.

The scoring engine continues to use load_sector_rules() so the existing
20-sector deterministic engine is not broken.
"""

from __future__ import annotations

import json
from pathlib import Path


# ============================================================================
# PATHS
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

RULES_PATH = BASE_DIR / "config" / "sector_rules.json"


# ============================================================================
# EXISTING DETERMINISTIC SECTOR-RULE LOADER
# ============================================================================

def load_sector_rules() -> dict:
    """
    Load the 20-sector deterministic scoring rules.

    The market sentiment engine depends on this function, so keep this
    interface stable.
    """

    if not RULES_PATH.exists():
        raise FileNotFoundError(
            f"Sector rules file not found: {RULES_PATH}"
        )

    rules = json.loads(
        RULES_PATH.read_text(
            encoding="utf-8"
        )
    )

    sectors = rules.get("sectors", [])
    exposures = rules.get("factor_exposures", {})
    events = rules.get("events", {})

    if not sectors:
        raise ValueError(
            "No sectors configured in sector_rules.json."
        )

    if not isinstance(exposures, dict):
        raise ValueError(
            "Invalid factor_exposures in sector_rules.json."
        )

    if not isinstance(events, dict):
        raise ValueError(
            "Invalid events in sector_rules.json."
        )

    return rules


# Keep this existing public constant for compatibility.
SECTORS = load_sector_rules()["sectors"]


# ============================================================================
# FIVE HIGH-LEVEL DISPLAY SECTORS
# ============================================================================

SECTOR_CONFIG = {

    "banking_financial_services": {
        "name": "Banking & Financial Services",

        "baseline_sentiment": "Bearish to Neutral",

        "global_drivers": [
            "US bond yields",
            "FII institutional flows",
            "interest-rate expectations",
            "credit and liquidity conditions",
        ],

        "outlook": (
            "Downward bias when high US yields and heavy FII selling "
            "pressure large-cap financial stocks."
        ),

        "keywords": [
            "banking",
            "banks",
            "financial services",
            "private banks",
            "psu banks",
            "hdfc bank",
            "icici bank",
            "axis bank",
            "sbi",
            "nifty bank",
            "bank nifty",
        ],

        "query": (
            "Indian banking financial services sector latest news "
            "banks Nifty Bank FII RBI interest rates"
        ),
    },


    "information_technology": {
        "name": "Information Technology",

        "baseline_sentiment": "Neutral / Defensive",

        "global_drivers": [
            "Nasdaq movement",
            "US technology spending",
            "Fed rate expectations",
            "USD strength",
            "enterprise IT spending",
        ],

        "outlook": (
            "Range-bound/defensive when global technology sentiment is mixed, "
            "with dollar strength providing support to exporters."
        ),

        "keywords": [
            "information technology",
            "it services",
            "software",
            "tcs",
            "infosys",
            "wipro",
            "hcltech",
            "tech mahindra",
            "nasdaq",
            "ai",
            "technology spending",
        ],

        "query": (
            "Indian IT sector latest news TCS Infosys Wipro "
            "Nasdaq AI technology spending Fed"
        ),
    },


    "pharmaceuticals_healthcare": {
        "name": "Pharmaceuticals & Healthcare",

        "baseline_sentiment": "Bullish (Defensive Pivot)",

        "global_drivers": [
            "safe-haven rotation",
            "global uncertainty",
            "healthcare demand",
            "defensive allocation",
        ],

        "outlook": (
            "Defensive demand can support pharmaceutical and healthcare stocks "
            "during broad market uncertainty."
        ),

        "keywords": [
            "pharmaceutical",
            "pharma",
            "healthcare",
            "sun pharma",
            "dr reddy",
            "cipla",
            "divis",
            "healthcare stocks",
            "defensive sector",
        ],

        "query": (
            "Indian pharmaceuticals healthcare sector latest news "
            "pharma stocks defensive market"
        ),
    },


    "automobiles_consumer_retail": {
        "name": "Automobiles & Consumer Retail",

        "baseline_sentiment": "Mildly Bullish",

        "global_drivers": [
            "crude oil prices",
            "fuel costs",
            "input costs",
            "domestic consumption",
            "consumer demand",
        ],

        "outlook": (
            "Lower input and fuel costs can support domestic demand-driven "
            "automobile and consumer businesses."
        ),

        "keywords": [
            "automobile",
            "auto",
            "maruti",
            "tata motors",
            "mahindra",
            "consumer retail",
            "consumption",
            "fuel costs",
            "crude oil",
        ],

        "query": (
            "Indian automobile consumer retail sector latest news "
            "crude oil demand consumption"
        ),
    },


    "oil_gas_energy": {
        "name": "Oil & Gas / Energy",

        "baseline_sentiment": "Bearish",

        "global_drivers": [
            "Brent crude",
            "WTI crude",
            "global oil demand",
            "upstream margins",
            "refining margins",
        ],

        "outlook": (
            "Direction depends on crude-price movement and the exposure of "
            "upstream, refining and downstream businesses."
        ),

        "keywords": [
            "oil",
            "gas",
            "energy",
            "brent",
            "wti",
            "ongc",
            "oil india",
            "reliance",
            "refiner",
            "refining",
        ],

        "query": (
            "Indian oil gas energy sector latest news Brent crude "
            "ONGC Oil India refinery"
        ),
    },
}


# ============================================================================
# DISPLAY-SECTOR TO INTERNAL 20-SECTOR MAPPING
# ============================================================================

"""
The deterministic scoring engine uses these internal sector codes.

The dashboard uses the five display sectors above.
"""

DISPLAY_SECTOR_TO_INTERNAL = {

    "banking_financial_services": [
        "BANKING",
        "NBFC",
    ],

    "information_technology": [
        "IT",
    ],

    "pharmaceuticals_healthcare": [
        "PHARMA",
        "HEALTHCARE",
    ],

    "automobiles_consumer_retail": [
        "AUTO",
        "FMCG",
        "RETAIL",
        "CONSUMER_DURABLES",
    ],

    "oil_gas_energy": [
        "OIL_UPSTREAM",
        "OMC",
    ],
}


# Reverse lookup.

INTERNAL_TO_DISPLAY_SECTOR = {

    internal_sector: display_sector

    for display_sector, internal_sectors
    in DISPLAY_SECTOR_TO_INTERNAL.items()

    for internal_sector
    in internal_sectors
}


# ============================================================================
# GLOBAL FINANCIAL PORTALS
# ============================================================================

GLOBAL_FINANCIAL_PORTALS = [
    "investing.com",
    "tradingview.com",
    "bloomberg.com",
    "reuters.com",
]


# ============================================================================
# INDIAN FINANCIAL PORTALS
# ============================================================================

INDIAN_FINANCIAL_PORTALS = [
    "nseindia.com",
    "bseindia.com",
    "moneycontrol.com",
    "livemint.com",
    "economictimes.indiatimes.com",
]


# Remove duplicates while keeping order.

ALL_PORTAL_DOMAINS = tuple(
    dict.fromkeys(
        GLOBAL_FINANCIAL_PORTALS
        + INDIAN_FINANCIAL_PORTALS
    )
)


# ============================================================================
# MACRO FACTOR CONFIGURATION
# ============================================================================

MACRO_FACTOR_CONFIG = {

    "brent_crude": {
        "name": "Brent crude",
        "ticker": "BZ=F",
        "unit": "$/barrel",
    },

    "us_10y_yield": {
        "name": "U.S. 10Y yield",
        "ticker": "^TNX",
        "unit": "%",
    },

    "usd": {
        "name": "USD",
        "ticker": "DX-Y.NYB",
        "unit": "DXY",
    },

    "usd_inr": {
        "name": "USD/INR",
        "ticker": "INR=X",
        "unit": "₹/$",
    },

    "dow_jones": {
        "name": "Dow Jones",
        "ticker": "^DJI",
        "unit": "points",
    },

    "nasdaq": {
        "name": "Nasdaq",
        "ticker": "^IXIC",
        "unit": "points",
    },
}


# ============================================================================
# CURRENT ENGINE FACTOR ALIASES
# ============================================================================

"""
The market engine internally uses short factor codes such as:

brent
us10y
dxy
usd_inr

The user-facing configuration above uses more descriptive names.

Keep this mapping so both representations can coexist safely.
"""

MACRO_FACTOR_ALIASES = {
    "brent_crude": "brent",
    "us_10y_yield": "us10y",
    "usd": "dxy",
    "usd_inr": "usd_inr",
    "dow_jones": "sp500",
    "nasdaq": "nasdaq",
}


# ============================================================================
# MACRO NEWS QUERIES
# ============================================================================

MACRO_NEWS_QUERIES = {

    "gift_nifty_fii": (
        "GIFT Nifty latest FII selling buying India market "
        "Nifty premarket institutional flows"
    ),

    "us_inflation": (
        "latest US inflation CPI PCE softer hotter than expected "
        "market impact"
    ),

    "fed_expectations": (
        "latest Fed rate expectations next meeting rate cut hike probability"
    ),

    "us_technology_ai": (
        "latest US technology AI Nasdaq market sentiment "
        "enterprise technology spending"
    ),

    "asian_markets": (
        "latest Asian markets sentiment Nikkei Hang Seng technology"
    ),

    "middle_east": (
        "latest Middle East geopolitical uncertainty market impact oil"
    ),

    "india_domestic_institutions": (
        "latest India DII domestic institutional investors buying selling"
    ),
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_display_sector_config(
    sector_key: str,
) -> dict:
    """
    Return configuration for one of the five display sectors.
    """

    if sector_key not in SECTOR_CONFIG:
        raise KeyError(
            f"Unknown display sector: {sector_key}"
        )

    return SECTOR_CONFIG[sector_key]


def get_display_sector_name(
    sector_key: str,
) -> str:
    """
    Return display name for a five-sector key.
    """

    return get_display_sector_config(
        sector_key
    )["name"]


def get_internal_sectors(
    sector_key: str,
) -> list[str]:
    """
    Return the internal 20-sector codes associated with a display sector.
    """

    return DISPLAY_SECTOR_TO_INTERNAL.get(
        sector_key,
        []
    )


# ============================================================================
# STARTUP VALIDATION
# ============================================================================

def validate_sector_configuration() -> dict:
    """
    Validate that the important configuration objects are available.

    Returns a small diagnostic dictionary useful for tests.
    """

    rules = load_sector_rules()

    return {
        "internal_sector_count": len(
            rules.get("sectors", [])
        ),

        "display_sector_count": len(
            SECTOR_CONFIG
        ),

        "portal_count": len(
            ALL_PORTAL_DOMAINS
        ),

        "macro_factor_count": len(
            MACRO_FACTOR_CONFIG
        ),

        "macro_query_count": len(
            MACRO_NEWS_QUERIES
        ),
    }