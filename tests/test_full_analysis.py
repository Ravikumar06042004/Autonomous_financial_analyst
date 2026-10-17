from services.analysis_service import (
    analyze_company,
)


if __name__ == "__main__":

    result = analyze_company(
        company_name="JPMorgan Chase",
        symbol="JPM",
    )

    print(
        "\n================================"
    )

    print(
        "FINAL FINANCIAL REPORT"
    )

    print(
        "================================"
    )
    print(result["ai_report"])