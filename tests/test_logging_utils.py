"""로그 시각·원천 응답 제한·인증정보 제거를 외부 API 없이 검증한다."""

import io
import json
import logging
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest.mock import patch

from backend.forecast_inputs import request_items
from backend.logging_utils import (
    KstFormatter,
    log_json,
    response_snapshot,
    safe_log_value,
)


class LoggingTests(unittest.TestCase):
    def test_http_error_response_is_captured_without_logging_request_credentials(self):
        body = {
            "response": {
                "header": {
                    "resultCode": "30",
                    "resultMsg": "test/secret+value 인증 오류",
                }
            }
        }
        error = urllib.error.HTTPError(
            "https://example.test?serviceKey=not-for-log",
            403,
            "Forbidden",
            {},
            io.BytesIO(json.dumps(body).encode()),
        )
        snapshots = []
        with patch.dict("os.environ", {"DATA_API_KEY": "test/secret+value"}), patch(
            "urllib.request.urlopen", side_effect=error
        ), self.assertRaises(urllib.error.HTTPError):
            request_items(
                "https://example.test",
                {"serviceKey": "not-for-log"},
                on_response=lambda document: snapshots.append(
                    response_snapshot(document, "AIRKOREA_FORECAST")
                ),
            )
        self.assertEqual(snapshots[0]["header"]["resultCode"], "30")
        self.assertNotIn("secret", str(snapshots))
        self.assertNotIn("not-for-log", str(snapshots))

    def test_timestamp_is_kst_in_requested_format(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "수집 완료", (), None)
        record.created = datetime(
            2026, 10, 27, 2, 27, 28, tzinfo=timezone.utc
        ).timestamp()
        self.assertEqual(
            KstFormatter("%(asctime)s %(levelname)s: %(message)s").format(record),
            "20261027 112728 INFO: 수집 완료",
        )

    def test_json_redacts_nested_credentials_and_serializes_missing_numbers(self):
        with patch.dict(
            "os.environ", {"DATA_API_KEY": "test/secret+value"}
        ), self.assertLogs("uvicorn.error", level="WARNING") as logs:
            log_json(
                "[진단]",
                response_json={
                    "serviceKey": "hidden",
                    "nested": {"Authorization": "Bearer hidden"},
                    "resultMsg": "test%2Fsecret%2Bvalue",
                    "url": "https://example.test?authKey=unknown-value",
                    "pm25": float("nan"),
                },
            )
        message = logs.records[0].getMessage()
        self.assertNotIn("hidden", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("unknown-value", message)
        payload = json.loads(message.partition("] ")[2])["response_json"]
        self.assertIsNone(payload["pm25"])
        self.assertEqual(payload["serviceKey"], "[REDACTED]")

    def test_response_keeps_raw_missing_value_flags_and_limits_observation_rows(self):
        document = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [
                        {
                            "dataTime": "2026-10-27 11:00",
                            "pm25Value": "-",
                            "pm10Value": "",
                            "pm25Flag": "점검및교정",
                            "serviceKey": "never-log",
                            "unused": "omit",
                        }
                    ]
                    * 10
                },
            }
        }
        snapshot = response_snapshot(document, "AIRKOREA")
        self.assertEqual(snapshot["item_count"], 10)
        self.assertEqual(len(snapshot["items"]), 3)
        self.assertEqual(snapshot["items"][0]["pm25Value"], "-")
        self.assertEqual(snapshot["items"][0]["pm25Flag"], "점검및교정")
        self.assertNotIn("never-log", str(snapshot))
        self.assertNotIn("unused", str(snapshot))
        self.assertEqual(response_snapshot([], "AIRKOREA"), {"response_type": "list"})
        self.assertEqual(safe_log_value(float("inf")), None)


if __name__ == "__main__":
    unittest.main()
