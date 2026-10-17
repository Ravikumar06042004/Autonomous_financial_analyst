from crewai import Agent

from config.llm_config import FINAL_LLM


def create_decision_agent():
    return Agent(
        role="Senior Financial Intelligence Synthesizer",
        goal=(
            "Combine company research, news sentiment, technical analysis, "
            "risk, global market cues and sector sentiment into one "
            "transparent report."
        ),
        backstory=(
            "You synthesize specialist findings. Separate observed evidence "
            "from interpretation, use only supplied data, and explicitly "
            "state limitations."
        ),
        llm=FINAL_LLM,
        verbose=True,
        allow_delegation=False,
    )