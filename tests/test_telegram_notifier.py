from unittest.mock import Mock, patch

import requests

from notifications import telegram_notifier


def _ok_response(status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = {
        "ok": True,
        "result": {"message_id": 1},
    }
    response.close.return_value = None
    return response


def test_post_retries_connection_error_then_succeeds():
    success = _ok_response()

    with (
        patch.object(
            telegram_notifier.requests,
            "post",
            side_effect=[
                requests.ConnectionError("reset"),
                success,
            ],
        ) as post,
        patch.object(telegram_notifier.time, "sleep") as sleep,
    ):
        response = telegram_notifier._post_with_retry(
            "https://api.telegram.org/botREDACTED/sendMessage",
            timeout=10,
            kwargs_factory=lambda: {"json": {"text": "test"}},
        )

    assert response is success
    assert post.call_count == 2
    sleep.assert_called_once()


def test_post_retries_server_error_then_succeeds():
    temporary = _ok_response(503)
    success = _ok_response()

    with (
        patch.object(
            telegram_notifier.requests,
            "post",
            side_effect=[temporary, success],
        ) as post,
        patch.object(telegram_notifier.time, "sleep") as sleep,
    ):
        response = telegram_notifier._post_with_retry(
            "https://api.telegram.org/botREDACTED/sendMessage",
            timeout=10,
            kwargs_factory=lambda: {"json": {"text": "test"}},
        )

    assert response is success
    assert post.call_count == 2
    temporary.close.assert_called_once()
    sleep.assert_called_once()


def test_post_does_not_retry_permanent_http_error():
    permanent = _ok_response(400)

    with (
        patch.object(
            telegram_notifier.requests,
            "post",
            return_value=permanent,
        ) as post,
        patch.object(telegram_notifier.time, "sleep") as sleep,
    ):
        response = telegram_notifier._post_with_retry(
            "https://api.telegram.org/botREDACTED/sendMessage",
            timeout=10,
            kwargs_factory=lambda: {"json": {"text": "test"}},
        )

    assert response is permanent
    post.assert_called_once()
    sleep.assert_not_called()


def test_photo_retry_reopens_upload_file(tmp_path):
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"sample-image-bytes")

    success = _ok_response()
    payloads = []

    def fake_post(url, *, timeout, data=None, files=None, **kwargs):
        payloads.append(files["photo"].read())

        if len(payloads) == 1:
            raise requests.ConnectionError("connection reset")

        return success

    with (
        patch.object(
            telegram_notifier,
            "_get_config",
            return_value=("fake-token", "fake-chat"),
        ),
        patch.object(
            telegram_notifier.requests,
            "post",
            side_effect=fake_post,
        ) as post,
        patch.object(telegram_notifier.time, "sleep"),
    ):
        telegram_notifier.send_telegram_photo(
            image_path,
            "Test report",
        )

    assert payloads == [
        b"sample-image-bytes",
        b"sample-image-bytes",
    ]
    assert post.call_count == 2