import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from database.repository import (
    initialize_database,
)


load_dotenv()

initialize_database()


app = FastAPI(
    title="Autonomous Multi-Agent Financial Analyst",
    description=(
        "Financial news, sentiment, technical analysis, "
        "risk analysis and paper trading."
    ),
    version="1.0.0",
)


allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8001,http://localhost:8001",
    ).split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():

    return {
        "application": (
            "Autonomous Multi-Agent Financial Analyst"
        ),
        "status": "running",
    }


app.include_router(
    router,
    prefix="/api",
)