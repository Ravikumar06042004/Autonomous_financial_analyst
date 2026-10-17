# Autonomous Multi-Agent Financial & Sentiment Analyst

A Python-based financial intelligence platform combining:

- Python
- CrewAI
- LangChain Core
- Anthropic / OpenAI
- yfinance
- Serper
- pandas
- technical indicators
- FastAPI
- Django
- APScheduler
- Slack
- Alpaca paper trading
- SQLite

## Architecture

Market Data
    ↓
Technical Indicators
    ↓
Financial News
    ↓
Multi-Agent Analysis
    ↓
Risk Engine
    ↓
Final Financial Intelligence Report
    ↓
Database
    ↓
FastAPI / Django / Slack
    ↓
Optional Alpaca Paper Trading

## Run tests

python -m tests.test_market

python -m tests.test_news

python -m tests.test_indicators

python -m tests.test_agents

python -m tests.test_database

python -m tests.test_trading

python -m tests.test_full_analysis

## Start FastAPI

uvicorn api.main:app --reload

Swagger:
http://127.0.0.1:8000/docs

## Start Django

python manage.py migrate

python manage.py runserver 8001

Dashboard:
http://127.0.0.1:8001

## Start Scheduler

python -m scheduler.runner

The scheduler runs every three minutes during US market hours.

## Safety

Alpaca paper trading is disabled by default.

Set:

ENABLE_PAPER_TRADING=true

only after testing the analysis pipeline.

## Watchlist

The 10 monitored companies are controlled by:

config/watchlist.py

Changing the list does not require modifying the agents or analysis engine.