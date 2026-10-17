from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    company_name: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=10)


class AnalyzeResponse(BaseModel):
    company_name: str
    symbol: str
    signal: str
    sentiment: str
    risk_level: str
    indicators: dict
    news: list[dict]
    market_context: dict | None = None
    ai_report: str


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    signal: str = Field(min_length=3, max_length=4)
    account_value: float = Field(gt=0)
    current_price: float = Field(gt=0)