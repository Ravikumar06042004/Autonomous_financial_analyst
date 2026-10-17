from crewai import Agent

from config.llm_config import SPECIALIST_LLM


def create_sentiment_agent() -> Agent:
    return Agent(
        role="Financial News Sentiment Analyst",
        goal="Analyze financial news sentiment.",
        backstory="You specialize in financial-news sentiment analysis.",
        llm=SPECIALIST_LLM,
        verbose=True,
        allow_delegation=False,
    )