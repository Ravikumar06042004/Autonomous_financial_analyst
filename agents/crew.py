from crewai import Crew, Process, Task
from langchain_core.prompts import ChatPromptTemplate

from agents.financial_agent import create_financial_agent
from agents.market_agent import create_market_agent
from agents.sentiment_agent import create_sentiment_agent
from agents.risk_agent import create_risk_agent
from agents.decision_agent import create_decision_agent


def _format_news(news):
    blocks = []

    for item in news:
        blocks.append(
            f"Title: {item.get('title')}\n"
            f"Source: {item.get('source')}\n"
            f"Published: {item.get('published_date')}\n"
            f"Feed page: {item.get('generic_feed')}\n"
            f"URL: {item.get('url')}\n"
            f"Content: {item.get('content')}"
        )

    return "\n\n---\n\n".join(blocks)


def _format_market_context(context):
    if not context:
        return "No market context supplied."

    lines = [
        f"Overall market sentiment: "
        f"{context.get('overall_sentiment', 'Unknown')}",
        "",
        "Factor matrix:",
    ]

    for row in context.get("factor_matrix", []):
        lines.append(
            f"- {row.get('factor')}: "
            f"{row.get('latest_signal')} -> "
            f"India impact: {row.get('expected_india_impact')}"
        )

    lines.append("")
    lines.append("Sector sentiment:")

    for sector in context.get("sector_sentiment", []):
        lines.append(
            f"- {sector.get('sector')}: "
            f"{sector.get('sentiment')} "
            f"(score={sector.get('sentiment_score')})"
        )

    return "\n".join(lines)


def run_financial_analysis(
    company_name: str,
    symbol: str,
    news: list[dict],
    indicators: dict,
    market_context: dict | None = None,
) -> str:

    financial_agent = create_financial_agent()
    sentiment_agent = create_sentiment_agent()
    market_agent = create_market_agent()
    risk_agent = create_risk_agent()
    decision_agent = create_decision_agent()

    news_text = _format_news(news)
    market_text = _format_market_context(market_context)

    financial_task = Task(
        description=f"""
Analyze financially material developments for
{company_name} ({symbol}).

Company news evidence:
{news_text}

Macro and sector context:
{market_text}
""",
        expected_output=(
            "A concise factual financial-development summary "
            "with source-aware reasoning."
        ),
        agent=financial_agent,
    )

    sentiment_task = Task(
        description=f"""
Analyze financial-news sentiment for
{company_name} ({symbol}).

Evidence:
{news_text}

Return:
- Overall sentiment: Positive / Neutral / Negative
- Score: between -1 and +1
- Main evidence
- Potential market relevance
""",
        expected_output=(
            "Financial sentiment classification, numeric score, "
            "evidence and relevance."
        ),
        agent=sentiment_agent,
    )

    market_task = Task(
        description=f"""
Analyze the technical condition of {symbol}
using ONLY these indicators:

{indicators}

Explain RSI, MACD, Bollinger Bands, SMA20
and EMA50 without inventing data.
""",
        expected_output=(
            "Technical market summary based only "
            "on supplied indicators."
        ),
        agent=market_agent,
    )

    risk_task = Task(
        description=f"""
Assess risk for {company_name} ({symbol}).

Technical indicators:
{indicators}

Global/sector context:
{market_text}

Focus on uncertainty, extreme indicators
and conflicting signals.
""",
        expected_output=(
            "Low / Medium / High risk assessment with evidence."
        ),
        agent=risk_agent,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are the final financial intelligence synthesizer. "
                    "Use only supplied evidence and clearly state limitations."
                ),
            ),
            (
                "human",
                """
Create a final financial intelligence report for
{company_name} ({symbol}).

Global/sector market context:
{market_context}

Use the specialist reports in your task context.

Use exactly these headings:
COMPANY
NEWS SUMMARY
SENTIMENT
TECHNICAL SUMMARY
RISK
SIGNAL
KEY REASONS
MARKET CONTEXT
DATA LIMITATIONS

For SIGNAL use only BUY, SELL or HOLD as a
system classification. Do not claim certainty.
""",
            ),
        ]
    )

    final_description = prompt.format(
        company_name=company_name,
        symbol=symbol,
        market_context=market_text,
    )

    final_task = Task(
        description=final_description,
        expected_output=(
            "A structured final report using the "
            "exact requested headings."
        ),
        agent=decision_agent,
        context=[
            financial_task,
            sentiment_task,
            market_task,
            risk_task,
        ],
    )

    crew = Crew(
        agents=[
            financial_agent,
            sentiment_agent,
            market_agent,
            risk_agent,
            decision_agent,
        ],
        tasks=[
            financial_task,
            sentiment_task,
            market_task,
            risk_task,
            final_task,
        ],
        process=Process.sequential,
        verbose=True,
    )

    return crew.kickoff().raw