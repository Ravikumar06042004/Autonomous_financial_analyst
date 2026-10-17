from fastapi import APIRouter, HTTPException

from api.schemas import (
    AnalyzeRequest,
    PaperTradeRequest,
)

from config.watchlist import get_watchlist

from database.repository import (
    get_dashboard_summary,
    get_latest_market_context,
    get_latest_reports_by_company,
    get_recent_reports,
)

from services.analysis_service import analyze_company
from services.market_sentiment_service import run_market_sentiment
from services.trading_service import execute_paper_signal


router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "healthy"
    }


@router.get("/companies")
def companies():
    return get_watchlist()


@router.get("/summary")
def summary():
    return get_dashboard_summary()


@router.get("/reports")
def reports(limit: int = 20):

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 100",
        )

    return get_recent_reports(limit)


@router.get("/latest")
def latest():
    return get_latest_reports_by_company()


@router.get("/market-sentiment")
def market_sentiment():
    """
    Return the latest stored market-context report.
    """

    report = get_latest_market_context()

    if not report:
        raise HTTPException(
            status_code=404,
            detail="No market sentiment report is available yet.",
        )

    return report


@router.post("/market-sentiment/run")
def market_sentiment_run(force: bool = False):

    try:
        return run_market_sentiment(
            force=force,
            mode="live",
            print_report=False,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.post("/analyze")
def analyze(request: AnalyzeRequest):

    try:
        return analyze_company(
            company_name=request.company_name,
            symbol=request.symbol.upper(),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.get("/analyze/{symbol}")
def analyze_get(
    symbol: str,
    company_name: str,
):

    try:
        return analyze_company(
            company_name=company_name,
            symbol=symbol.upper(),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.post("/paper-trade")
def paper_trade(request: PaperTradeRequest):

    try:
        return execute_paper_signal(
            symbol=request.symbol.upper(),
            signal=request.signal.upper(),
            account_value=request.account_value,
            current_price=request.current_price,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc