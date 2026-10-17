import time

from apscheduler.schedulers.background import (
    BackgroundScheduler,
)

from scheduler.jobs import (
    run_analysis_job,
)


def main():

    scheduler = (
        BackgroundScheduler()
    )

    scheduler.add_job(
        run_analysis_job,
        trigger="interval",
        minutes=3,
        id="financial_analysis",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()

    print(
        "===================================="
    )

    print(
        "Autonomous Financial Analyst"
    )

    print(
        "Scheduler started."
    )

    print(
        "Interval: every 3 minutes"
    )

    print(
        "===================================="
    )

    try:

        while True:

            time.sleep(1)

    except KeyboardInterrupt:

        print(
            "Stopping scheduler..."
        )

        scheduler.shutdown()


if __name__ == "__main__":
    main()