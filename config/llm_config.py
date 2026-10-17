from __future__ import annotations

import os

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(
    override=True
)


# ============================================================
# LLM CONFIGURATION
# ============================================================

LLM_MODE = os.getenv(
    "LLM_MODE",
    "mock",
).strip().lower()


SPECIALIST_MODEL = os.getenv(
    "SPECIALIST_MODEL",
    "openai/gpt-5-mini",
).strip()


FINAL_MODEL = os.getenv(
    "FINAL_MODEL",
    "openai/gpt-5-mini",
).strip()


TEMPERATURE = float(
    os.getenv(
        "LLM_TEMPERATURE",
        "0.2",
    )
)


# ============================================================
# CREWAI LLM
# ============================================================

try:
    from crewai import LLM
except ImportError:
    LLM = None


def _build_llm(
    model: str,
):
    """
    Build the CrewAI LLM object.

    The provider is determined from the model prefix:
        openai/...
        anthropic/...
        gemini/...
    """

    if LLM is None:
        return None

    return LLM(
        model=model,
        temperature=TEMPERATURE,
        max_tokens=4096,
    )


# ============================================================
# LLM OBJECTS
# ============================================================

SPECIALIST_LLM = _build_llm(
    SPECIALIST_MODEL
)


FINAL_LLM = _build_llm(
    FINAL_MODEL
)


# ============================================================
# DEBUG INFORMATION
# ============================================================

def get_llm_config() -> dict:
    """
    Return safe configuration information.

    API keys are intentionally never returned.
    """

    return {
        "llm_mode": LLM_MODE,
        "specialist_model": SPECIALIST_MODEL,
        "final_model": FINAL_MODEL,
        "temperature": TEMPERATURE,
        "specialist_llm_available": (
            SPECIALIST_LLM is not None
        ),
        "final_llm_available": (
            FINAL_LLM is not None
        ),
    }