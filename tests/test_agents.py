from agents.financial_agent import (
    create_financial_agent,
)

from agents.market_agent import (
    create_market_agent,
)

from agents.sentiment_agent import (
    create_sentiment_agent,
)

from agents.risk_agent import (
    create_risk_agent,
)

from agents.decision_agent import (
    create_decision_agent,
)


if __name__ == "__main__":

    agents = [
        create_financial_agent(),
        create_market_agent(),
        create_sentiment_agent(),
        create_risk_agent(),
        create_decision_agent(),
    ]

    print(
        "Agents created successfully:"
    )

    for agent in agents:

        print(
            "-",
            agent.role,
        )