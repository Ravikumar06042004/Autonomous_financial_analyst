from crewai import Agent

from config.llm_config import SPECIALIST_LLM


def create_risk_agent() -> Agent:
    return Agent(
        role="Financial Risk Analyst",
        goal="Evaluate financial and market risk.",
        backstory="You are a disciplined financial risk analyst.",
        llm=SPECIALIST_LLM,
        verbose=True,
        allow_delegation=False,
    )