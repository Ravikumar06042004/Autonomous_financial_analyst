"""Telegram Bot API client with bounded retries."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

MAX_REQUEST_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_config() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "in the project .env file."
        )

    return token, chat_id


def _close_upload_files(kwargs: dict[str, Any]) -> None:
    """Close files passed to requests, even when the request fails."""
    files = kwargs.get("files")

    if not isinstance(files, dict):
        return

    for value in files.values():
        file_obj = (
            value[1]
            if isinstance(value, tuple) and len(value) > 1
            else value
        )

        close = getattr(file_obj, "close", None)

        if callable(close):
            try:
                close()
            except Exception:
                pass


def _retry_delay(
    attempt: int,
    response: requests.Response | None = None,
) -> float:
    """Use Telegram retry_after for 429 responses when available."""
    if response is not None and response.status_code == 429:
        try:
            body = response.json()
            retry_after = float(
                (body.get("parameters") or {}).get("retry_after", 0)
            )

            if retry_after > 0:
                return min(retry_after, 30.0)

        except (ValueError, TypeError):
            pass

    return min(2 ** (attempt - 1), 4)


def _post_with_retry(
    url: str,
    *,
    timeout: int,
    kwargs_factory: Callable[[], dict[str, Any]],
) -> requests.Response:
    """
    Retry temporary connection failures and HTTP 429/5xx errors.

    A network connection can reset after Telegram has already accepted a
    request. Retrying in that ambiguous situation can occasionally duplicate
    a message or photo.
    """
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        kwargs = kwargs_factory()
        response: requests.Response | None = None
        should_retry = False
        delay = 0.0

        try:
            response = requests.post(
                url,
                timeout=timeout,
                **kwargs,
            )

        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= MAX_REQUEST_ATTEMPTS:
                raise RuntimeError(
                    "Telegram request failed after "
                    f"{MAX_REQUEST_ATTEMPTS} attempts "
                    f"({type(exc).__name__})."
                ) from None

            delay = _retry_delay(attempt)

            print(
                f"Telegram network issue ({type(exc).__name__}); "
                f"retrying in {delay:g}s "
                f"(attempt {attempt + 1}/{MAX_REQUEST_ATTEMPTS}).",
                flush=True,
            )

            should_retry = True

        finally:
            _close_upload_files(kwargs)

        if (
            response is not None
            and response.status_code in RETRYABLE_STATUS_CODES
            and attempt < MAX_REQUEST_ATTEMPTS
        ):
            delay = _retry_delay(attempt, response)
            status_code = response.status_code
            response.close()

            print(
                f"Telegram temporary HTTP {status_code}; "
                f"retrying in {delay:g}s "
                f"(attempt {attempt + 1}/{MAX_REQUEST_ATTEMPTS}).",
                flush=True,
            )

            should_retry = True

        if should_retry:
            time.sleep(delay)
            continue

        if response is None:
            raise RuntimeError(
                "Telegram request ended without a response."
            )

        return response

    raise RuntimeError("Telegram request exhausted its retry attempts.")


def _check_response(response: requests.Response) -> None:
    """Validate Telegram's HTTP and Bot API responses without logging tokens."""
    if response.status_code >= 400:
        try:
            body = response.json()
            description = (
                body.get("description")
                if isinstance(body, dict)
                else None
            )
        except ValueError:
            description = None

        detail = str(
            description or getattr(response, "reason", "request rejected")
        )

        raise RuntimeError(
            f"Telegram HTTP {response.status_code}: {detail}"
        )

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            "Telegram returned a non-JSON response."
        ) from None

    if not isinstance(result, dict) or not result.get("ok"):
        description = (
            result.get("description", "Unknown error")
            if isinstance(result, dict)
            else "Unexpected response format"
        )

        raise RuntimeError(f"Telegram API error: {description}")


def send_telegram_message(text: str) -> None:
    """Send a text notification to the configured Telegram chat."""
    token, chat_id = _get_config()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = _post_with_retry(
        url,
        timeout=45,
        kwargs_factory=lambda: {
            "json": {
                "chat_id": chat_id,
                "text": text,
            },
        },
    )

    _check_response(response)


def send_telegram_photo(
    image_path: str | Path,
    caption: str = "Market sentiment report",
) -> None:
    """Send a report image, reopening it for each retry."""
    token, chat_id = _get_config()
    image_path = Path(image_path)

    if not image_path.is_file():
        raise FileNotFoundError(
            f"Report image not found: {image_path}"
        )

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    def build_kwargs() -> dict[str, Any]:
        return {
            "data": {
                "chat_id": chat_id,
                "caption": str(caption)[:1000],
            },
            "files": {
                "photo": image_path.open("rb"),
            },
        }

    response = _post_with_retry(
        url,
        timeout=90,
        kwargs_factory=build_kwargs,
    )

    _check_response(response)