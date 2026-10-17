from config.llm_config import (
    SPECIALIST_MODEL,
    FINAL_MODEL,
    SPECIALIST_LLM,
    FINAL_LLM,
)


if __name__ == "__main__":

    print("Specialist model:")
    print(SPECIALIST_MODEL)

    print("\nFinal model:")
    print(FINAL_MODEL)

    print("\nSpecialist LLM:")
    print(SPECIALIST_LLM)

    print("\nFinal LLM:")
    print(FINAL_LLM)

    print("\nLLM configuration loaded successfully.")