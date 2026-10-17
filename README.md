# Autonomous Multi-Agent Financial & Sentiment Analyst

An AI-powered financial research project designed to organize market data, news analysis, sentiment insights, risk assessment, and financial reporting through a modular multi-agent architecture.

## Overview

This project combines Python-based services, AI agent components, market-data tools, and reporting functionality to support financial research workflows.

## Key Components

- **Multi-Agent System:** Separate agent modules for market research, financial analysis, sentiment analysis, risk assessment, and decision support.
- **Market Data Tools:** Tools for collecting and processing market information and technical indicators.
- **News & Sentiment Analysis:** Services for retrieving financial news and analyzing market sentiment.
- **Analysis Services:** Modular services for coordinating analysis and generating reports.
- **API:** FastAPI-based application components and API routes.
- **Dashboard:** Django dashboard application components.
- **Telegram Reporting:** Notification and report-generation modules.
- **Testing:** Automated tests covering selected agents, market tools, analysis, database, and notifications.

## Technology Stack

- Python
- CrewAI and LangChain (where configured)
- FastAPI
- Django
- SQLite/database components
- Financial market data and news tools
- Telegram Bot API integration
- Git and GitHub

## Project Structure

```text
autonomous_financial_analyst/
├── agents/          # Agent modules
├── api/             # API application and routes
├── config/          # Application configuration
├── dashboard/       # Dashboard application
├── database/        # Database repository
├── notifications/   # Reporting and Telegram notifications
├── scheduler/       # Scheduled task components
├── services/        # Business logic and analysis services
├── tests/           # Automated tests
├── tools/           # Market, news, risk and sentiment tools
├── requirements.txt
├── manage.py
├── start_project.py
└── README.md
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Ravikumar06042004/Autonomous_financial_analyst.git
cd Autonomous_financial_analyst
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file using `.env.example` as a reference. Add your own required API keys and credentials locally.

**Never commit `.env`, API keys, bot tokens, passwords, or other credentials to GitHub.**

### 5. Run the application

Review `start_project.py` and the project configuration to confirm the required environment variables and startup command before running:

```bash
python start_project.py
```

### 6. Run tests

```bash
python -m pytest
```

Some tests may require API credentials, external services, or additional configuration.

## Security

- Keep API keys and Telegram bot tokens in environment variables.
- Do not upload private credentials or local databases.
- Review external API usage and costs before enabling scheduled jobs.

## Disclaimer

This project is intended for software development, financial research, and educational purposes. Its outputs are not guaranteed to be accurate and should not be treated as personalized investment advice.

## Author

**Ravi Kumar Bitra**

- GitHub: [Ravikumar06042004](https://github.com/Ravikumar06042004)
- Project: [Autonomous Financial Analyst](https://github.com/Ravikumar06042004/Autonomous_financial_analyst)
