import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from src.crawlers.pm1 import __main__ as pm1_main
from src.crawlers.pm1.__main__ import build_parser, load_environment
from src.crawlers.pm1.crawler import (
    HourWindow,
    calculate_eligible_end,
    fetch_hour,
    iter_hour_windows,
    parse_source_offset,
)


def api_payload(
    items: list[dict[str, object]],
    total_count: int | None = None,
    page_no: int = 1,
) -> bytes:
    body = {
        "items": items,
        "pageNo": page_no,
        "numOfRows": 1000,
        "totalCount": len(items) if total_count is None else total_count,
    }
    return json.dumps(
        {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": body,
            }
        }
    ).encode()


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, url: str = "https://apis.data.go.kr/result"):
        super().__init__(payload)
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def measurement(code: str = "0383", dtm: str = "202309180000") -> dict[str, object]:
    return {
        "obsrr_tpcd": code,
        "obsrt_dtm": dtm,
        "obsrt_tmprt": "18.2",
        "obsrt_hmdt": "71",
        "obsrt_wndrc_val": None,
        "obsrt_ws": "0.4",
        "obsrt_pm01_val": "1.2",
        "obsrt_pm25_val": "3.4",
        "obsrt_pm10_val": "5.6",
        "avoc_obsrt_pm01_val": "1.1",
        "avoc_obsrt_pm25_val": "3.3",
        "avoc_obsrt_pm10_val": "5.5",
    }


def test_hour_windows_request_only_hh00_without_gaps() -> None:
    windows = list(iter_hour_windows("202309182300", "202309190100"))

    assert windows == [
        HourWindow("202309182300", "202309182300"),
        HourWindow("202309190000", "202309190000"),
        HourWindow("202309190100", "202309190100"),
    ]


def test_calculate_eligible_end_applies_offset_and_sync_lag_once() -> None:
    result = calculate_eligible_end(
        datetime(2026, 9, 30, 3, 34, tzinfo=UTC),
        parse_source_offset("+09:00"),
        1,
    )

    assert result == "202609301100"


@pytest.mark.parametrize("value", ["09:00", "+9:00", "+15:00", "+09:60"])
def test_invalid_offset_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_source_offset(value)


def test_negative_lag_is_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_eligible_end(
            datetime(2026, 9, 30, tzinfo=UTC), parse_source_offset("+09:00"), -1
        )


def test_fetch_hour_filters_targets_and_parses_nullable_decimals() -> None:
    payload = api_payload([measurement(), measurement("9999")])

    rows = fetch_hour(
        HourWindow("202309180000", "202309180000"),
        "api-secret-sentinel",
        parse_source_offset("+09:00"),
        opener=lambda request, timeout: FakeResponse(payload),
        sleep=lambda seconds: None,
    )

    assert len(rows) == 1
    assert rows[0].obsrr_nm == "강화_숲2"
    assert str(rows[0].obsrt_pm01_val) == "1.2"
    assert rows[0].obsrt_wndrc_val is None
    assert rows[0].observed_at_utc == datetime(2023, 9, 17, 15, tzinfo=UTC)


def test_fetch_hour_accepts_verified_flat_api_envelope() -> None:
    payload = json.dumps(
        {
            "resultCode": "00",
            "resultMsg": "NORMAL SERVICE",
            "pageNo": "1",
            "numOfRows": "1000",
            "totalCount": "1",
            "items": [measurement("0151")],
        }
    ).encode()

    rows = fetch_hour(
        HourWindow("202309180000", "202309180000"),
        "key",
        parse_source_offset("+09:00"),
        opener=lambda request, timeout: FakeResponse(payload),
        sleep=lambda seconds: None,
    )

    assert [(row.obsrr_tpcd, row.obsrr_nm) for row in rows] == [("0151", "인천_산단")]


def test_fetch_hour_requests_fixed_endpoint_and_hour_parameters() -> None:
    seen_url = ""

    def opener(request: object, timeout: float) -> FakeResponse:
        nonlocal seen_url
        seen_url = request.full_url  # type: ignore[attr-defined]
        return FakeResponse(api_payload([]))

    fetch_hour(
        HourWindow("202309180000", "202309180000"),
        "encoded key/+",
        parse_source_offset("+09:00"),
        opener=opener,
        sleep=lambda seconds: None,
    )

    parsed = urlparse(seen_url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "apis.data.go.kr"
    assert parsed.path == "/1400377/AicanDustData/dustData"
    assert query["startDt"] == ["202309180000"]
    assert query["endDt"] == ["202309180000"]
    assert query["serviceKey"] == ["encoded key/+"]


def test_fetch_hour_rejects_nonstandard_https_port() -> None:
    with pytest.raises(RuntimeError, match="approved HTTPS origin"):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(
                api_payload([]), "https://apis.data.go.kr:444/result"
            ),
            sleep=lambda seconds: None,
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({"response": {"header": {"resultCode": "99"}}}).encode(),
        api_payload([measurement(dtm="202309180100")]),
        api_payload([measurement(dtm="202309180010")]),
        api_payload([{**measurement(), "obsrt_pm01_val": "NaN"}]),
    ],
)
def test_fetch_hour_rejects_malformed_or_out_of_window_data(payload: bytes) -> None:
    with pytest.raises(ValueError) as error:
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "api-secret-sentinel",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(payload),
            sleep=lambda seconds: None,
        )

    assert "api-secret-sentinel" not in str(error.value)


def test_fetch_hour_rejects_duplicate_target_key() -> None:
    payload = api_payload([measurement(), measurement()])

    with pytest.raises(ValueError, match="Duplicate"):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(payload),
            sleep=lambda seconds: None,
        )


def test_fetch_hour_reads_all_pages_and_rejects_total_count_changes() -> None:
    responses = [
        api_payload([measurement()], total_count=2, page_no=1),
        api_payload([measurement("0151", "202309180000")], total_count=2, page_no=2),
    ]

    rows = fetch_hour(
        HourWindow("202309180000", "202309180000"),
        "key",
        parse_source_offset("+09:00"),
        opener=lambda request, timeout: FakeResponse(responses.pop(0)),
        sleep=lambda seconds: None,
    )

    assert [(row.obsrr_tpcd, row.obsrt_dtm) for row in rows] == [
        ("0383", "202309180000"),
        ("0151", "202309180000"),
    ]

    responses = [
        api_payload([measurement()], total_count=2, page_no=1),
        api_payload([], total_count=3, page_no=2),
    ]
    with pytest.raises(ValueError, match="totalCount changed"):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(responses.pop(0)),
            sleep=lambda seconds: None,
        )


def test_fetch_hour_rejects_missing_measurement_field() -> None:
    item = measurement()
    del item["obsrt_pm01_val"]

    with pytest.raises(ValueError, match="missing fields"):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(api_payload([item])),
            sleep=lambda seconds: None,
        )


@pytest.mark.parametrize("missing_key", ["pageNo", "numOfRows", "totalCount"])
def test_fetch_hour_rejects_missing_pagination_metadata(missing_key: str) -> None:
    payload = json.loads(api_payload([]))
    del payload["response"]["body"][missing_key]

    with pytest.raises(ValueError, match="pagination metadata"):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=lambda request, timeout: FakeResponse(json.dumps(payload).encode()),
            sleep=lambda seconds: None,
        )


def test_fetch_hour_retries_429_but_not_other_4xx() -> None:
    calls = 0

    def retrying_opener(request: object, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise HTTPError("safe-url", 429, "rate limited", {}, None)
        return FakeResponse(api_payload([]))

    fetch_hour(
        HourWindow("202309180000", "202309180000"),
        "key",
        parse_source_offset("+09:00"),
        opener=retrying_opener,
        sleep=lambda seconds: None,
    )
    assert calls == 3

    calls = 0

    def failing_opener(request: object, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise HTTPError("safe-url", 400, "bad request", {}, None)

    with pytest.raises(RuntimeError):
        fetch_hour(
            HourWindow("202309180000", "202309180000"),
            "key",
            parse_source_offset("+09:00"),
            opener=failing_opener,
            sleep=lambda seconds: None,
        )
    assert calls == 1


@pytest.mark.parametrize("command", ["init-db", "backfill", "sync", "export-csv"])
def test_cli_exposes_required_commands(command: str) -> None:
    parser = build_parser()
    arguments = [command]
    if command == "backfill":
        arguments += ["--end", "202609302300"]

    parsed = parser.parse_args(arguments)

    assert parsed.command == command


def test_environment_loader_uses_process_values_without_executing_dotenv(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PM1_API_KEY=$(never-execute)\nPM1_SYNC_LAG_HOURS=1\n",
        encoding="utf-8",
    )

    loaded = load_environment(
        env_path,
        {"PM1_API_KEY": "process-secret", "PM1_SOURCE_TIMEZONE": "+09:00"},
    )

    assert loaded["PM1_API_KEY"] == "process-secret"
    assert loaded["PM1_SYNC_LAG_HOURS"] == "1"


def test_environment_loader_rejects_duplicate_relevant_key(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PM1_API_KEY=one\nPM1_API_KEY=two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate"):
        load_environment(env_path, {})


def collection_env() -> dict[str, str]:
    return {
        "PM1_API_KEY": "api-secret-sentinel",
        "PM1_SOURCE_TIMEZONE": "+09:00",
        "PM1_SYNC_LAG_HOURS": "1",
        "DB_HOST": "db.example.internal",
        "DB_PORT": "5432",
        "DB_NAME": "weather_db",
        "DB_SSLROOTCERT": "certs/root.crt",
        "DB_INGEST_USER": "pm1_ingest",
        "DB_INGEST_PASSWORD": "db-secret-sentinel",
    }


def test_future_backfill_end_is_rejected_before_database_or_api(monkeypatch) -> None:
    monkeypatch.setattr(
        pm1_main,
        "connect_database",
        lambda config: pytest.fail("database connection must not be attempted"),
    )
    monkeypatch.setattr(
        pm1_main,
        "fetch_hour",
        lambda *args, **kwargs: pytest.fail("API must not be called"),
    )

    with pytest.raises(ValueError, match="eligible boundary"):
        pm1_main.run_collection("backfill", "999912312300", collection_env())


def test_lock_failure_makes_zero_api_calls(monkeypatch) -> None:
    class ConnectionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(
        pm1_main, "connect_database", lambda config: ConnectionContext()
    )
    monkeypatch.setattr(pm1_main, "acquire_source_lock", lambda connection: False)
    monkeypatch.setattr(
        pm1_main,
        "fetch_hour",
        lambda *args, **kwargs: pytest.fail("API must not be called"),
    )

    assert pm1_main.run_collection("sync", None, collection_env()) == 2


def test_init_db_rolls_back_initialization_when_validation_fails(monkeypatch) -> None:
    class Transaction:
        rolled_back = False

        def __enter__(self) -> "Transaction":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            self.rolled_back = exc_type is not None

    class Connection:
        def __init__(self) -> None:
            self.transaction_value = Transaction()

        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def transaction(self) -> Transaction:
            return self.transaction_value

    connection = Connection()
    env = {
        **collection_env(),
        "DB_MIGRATION_USER": "pm1_migration",
        "DB_MIGRATION_PASSWORD": "migration-secret-sentinel",
        "DB_EXPORT_USER": "pm1_export",
        "DB_EXPORT_PASSWORD": "export-secret-sentinel",
    }
    monkeypatch.setattr(pm1_main, "connect_database", lambda config: connection)
    monkeypatch.setattr(pm1_main, "initialize_schema", lambda *args: None)
    monkeypatch.setattr(
        pm1_main,
        "validate_schema",
        lambda *args: (_ for _ in ()).throw(RuntimeError("stale schema")),
    )

    with pytest.raises(RuntimeError, match="stale schema"):
        pm1_main.run_init_db(env)

    assert connection.transaction_value.rolled_back is True
