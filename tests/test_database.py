from database.repository import (
    get_dashboard_summary,
    get_recent_reports,
    initialize_database,
)


if __name__ == "__main__":

    initialize_database()

    print(
        "Database initialized."
    )

    print(
        "\nDashboard summary:"
    )

    print(
        get_dashboard_summary()
    )

    print(
        "\nRecent reports:"
    )

    reports = get_recent_reports(
        limit=5
    )

    for report in reports:

        print(
            report[
                "company_symbol"
            ],
            report[
                "signal"
            ],
        )