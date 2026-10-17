"""Send a test message using the project's Telegram client."""

from notifications.telegram_notifier import send_telegram_message


def main() -> None:
    send_telegram_message(
        "✅ Autonomous Financial Analyst connected!\n\n"
        "Telegram test successful.\n"
        "The scheduled report uses this same delivery client."
    )

    print(
        "Telegram test message sent successfully.",
        flush=True,
    )


if __name__ == "__main__":
    main()