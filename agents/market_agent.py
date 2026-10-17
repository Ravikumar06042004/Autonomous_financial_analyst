from crewai import Agent

from config.llm_config import SPECIALIST_LLM


def create_market_agent() -> Agent:
    return Agent(
        role="Technical Market Analyst",
        goal="Analyze RSI, MACD, Bollinger Bands, SMA and EMA.",
        backstory="You are a technical market analyst.",
        llm=SPECIALIST_LLM,
        verbose=True,
        allow_delegation=False,
    )