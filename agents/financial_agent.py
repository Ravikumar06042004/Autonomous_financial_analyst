from crewai import Agent

from config.llm_config import SPECIALIST_LLM


def create_financial_agent() -> Agent:
    return Agent(
        role="Senior Financial Research Analyst",
        goal="Analyze company news and identify financially important developments.",
        backstory="You are an experienced financial research analyst.",
        llm=SPECIALIST_LLM,
        verbose=True,
        allow_delegation=False,
    )