"""국립산림과학원 PM1 API를 정각 단위로 조회하고 응답을 검증하는 모듈."""

from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ENDPOINT = "https://apis.data.go.kr/1400377/AicanDustData/dustData"
API_HOST = "apis.data.go.kr"
TARGET_STATIONS = {"0383": "강화_숲2", "0151": "인천_산단"}
NUMERIC_FIELDS = (
    "obsrt_tmprt",
    "obsrt_hmdt",
    "obsrt_wndrc_val",
    "obsrt_ws",
    "obsrt_pm01_val",
    "obsrt_pm25_val",
    "obsrt_pm10_val",
    "avoc_obsrt_pm01_val",
    "avoc_obsrt_pm25_val",
    "avoc_obsrt_pm10_val",
)
MAX_ATTEMPTS = 5
PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class HourWindow:
    """API 요청에 사용할 원본 시간대의 한 시간 구간."""

    start_dtm: str
    end_dtm: str


@dataclass(frozen=True)
class MeasurementRow:
    """검증을 마친 대상 관측소의 정각 관측값 한 행."""

    obsrr_tpcd: str
    obsrr_nm: str
    obsrt_dtm: str
    observed_at_utc: datetime
    obsrt_tmprt: Decimal | None
    obsrt_hmdt: Decimal | None
    obsrt_wndrc_val: Decimal | None
    obsrt_ws: Decimal | None
    obsrt_pm01_val: Decimal | None
    obsrt_pm25_val: Decimal | None
    obsrt_pm10_val: Decimal | None
    avoc_obsrt_pm01_val: Decimal | None
    avoc_obsrt_pm25_val: Decimal | None
    avoc_obsrt_pm10_val: Decimal | None


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    """공공데이터 API와 동일한 출처로만 리다이렉트를 허용한다."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        """리다이렉트 목적지를 검사한 뒤 안전한 요청만 생성한다."""
        parsed = urlparse(newurl)
        # 요청 URL에는 API 키가 포함되므로 다른 호스트로 이동하면 비밀값이
        # 유출될 수 있다. HTTPS와 공식 호스트를 모두 고정한다.
        if not _is_api_origin(parsed):
            raise RuntimeError("API redirect left the approved HTTPS origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _is_api_origin(parsed: Any) -> bool:
    """URL이 허용된 공공데이터 API의 HTTPS 출처인지 확인한다."""
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == API_HOST
        and port
        in {
            None,
            443,
        }
    )


def parse_source_offset(value: str) -> timezone:
    """UTC 오프셋 문자열을 고정 시간대로 변환한다."""
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match is None:
        raise ValueError("PM1_SOURCE_TIMEZONE must use the form +HH:MM or -HH:MM")
    sign, hour_text, minute_text = match.groups()
    hours = int(hour_text)
    minutes = int(minute_text)
    if minutes > 59 or hours > 14 or (hours == 14 and minutes != 0):
        raise ValueError("PM1_SOURCE_TIMEZONE is outside the supported offset range")
    delta = timedelta(hours=hours, minutes=minutes)
    if sign == "-":
        delta = -delta
    return timezone(delta)


def calculate_eligible_end(
    now_utc: datetime, source_timezone: timezone, sync_lag_hours: int
) -> str:
    """API 공개 지연시간을 반영한 최신 수집 가능 정각을 반환한다."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if sync_lag_hours < 0:
        raise ValueError("PM1_SYNC_LAG_HOURS cannot be negative")
    safe_local = now_utc.astimezone(source_timezone) - timedelta(hours=sync_lag_hours)
    eligible_hour = safe_local.replace(minute=0, second=0, microsecond=0)
    return eligible_hour.strftime("%Y%m%d%H00")


def _parse_window_value(value: str, expected_minute: str) -> datetime:
    """API 시각 문자열의 형식, 분 값, 실제 달력 날짜를 검증한다."""
    if not re.fullmatch(r"\d{12}", value) or value[-2:] != expected_minute:
        raise ValueError(f"Datetime must end in {expected_minute} and use YYYYMMDDHHMM")
    try:
        return datetime.strptime(value, "%Y%m%d%H%M")
    except ValueError as error:
        raise ValueError("Datetime contains an invalid calendar value") from error


def iter_hour_windows(start_dtm: str, end_dtm: str) -> Iterator[HourWindow]:
    """시작과 종료를 포함해 정각 API 요청 구간을 한 시간씩 생성한다."""
    current = _parse_window_value(start_dtm, "00")
    final = _parse_window_value(end_dtm, "00")
    if current > final:
        raise ValueError("Collection start must not be after its end")
    while current <= final:
        value = current.strftime("%Y%m%d%H00")
        yield HourWindow(value, value)
        if current == final:
            break
        current += timedelta(hours=1)


def _parse_decimal(value: object, field: str) -> Decimal | None:
    """API 숫자를 Decimal로 바꾸고 결측값과 비유한 수를 구분한다."""
    if value is None or value == "":
        # API의 빈 값은 DB의 NULL로 저장한다. NaN과 Infinity는 숫자처럼
        # 연산에 섞여 품질 문제를 숨길 수 있으므로 아래에서 명시적으로 거부한다.
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid numeric value for {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid numeric value for {field}") from error
    if not parsed.is_finite():
        raise ValueError(f"Non-finite numeric value for {field}")
    return parsed


def _parse_measurement(
    item: dict[str, object], window: HourWindow, source_timezone: timezone
) -> MeasurementRow | None:
    """API 항목 하나를 검사하고 대상 관측소 행으로 변환한다."""
    code = item.get("obsrr_tpcd")
    # API는 여러 관측소를 함께 반환할 수 있으므로 필요한 두 곳만 남긴다.
    if not isinstance(code, str) or code not in TARGET_STATIONS:
        return None

    if any(field not in item for field in NUMERIC_FIELDS):
        raise ValueError("Target observation is missing fields")
    dtm = item.get("obsrt_dtm")
    if not isinstance(dtm, str) or not re.fullmatch(r"\d{12}", dtm):
        raise ValueError("Target observation has an invalid obsrt_dtm")
    if dtm != window.start_dtm or dtm != window.end_dtm or dtm[-2:] != "00":
        raise ValueError("Target observation is outside the requested exact hour")

    try:
        local_observed_at = datetime.strptime(dtm, "%Y%m%d%H%M").replace(
            tzinfo=source_timezone
        )
    except ValueError as error:
        raise ValueError(
            "Target observation has an invalid calendar datetime"
        ) from error
    numbers = {
        field: _parse_decimal(item.get(field), field) for field in NUMERIC_FIELDS
    }

    return MeasurementRow(
        obsrr_tpcd=code,
        obsrr_nm=TARGET_STATIONS[code],
        obsrt_dtm=dtm,
        # 원본 문자열은 KST 기준 값으로 보존하고, 검색·결합용 시각은 UTC로
        # 정규화해 시간대가 다른 데이터와도 안전하게 비교할 수 있게 한다.
        observed_at_utc=local_observed_at.astimezone(UTC),
        **numbers,
    )


def _response_items(
    payload: object, requested_page: int
) -> tuple[list[dict[str, object]], int]:
    """응답 봉투와 페이지 정보를 검증하고 현재 페이지 항목을 꺼낸다."""
    if not isinstance(payload, dict):
        raise ValueError("API response must be a JSON object")

    if "response" in payload:
        # 공공데이터 응답은 표준 response 봉투를 쓰지만 오류 응답 등에서는
        # 헤더와 본문이 최상위에 올 수 있어 두 형태를 모두 검증한다.
        response = payload.get("response")
        if not isinstance(response, dict):
            raise ValueError("API response envelope is invalid")
        header = response.get("header")
        body = response.get("body")
    else:
        header = payload
        body = payload

    if not isinstance(header, dict) or str(header.get("resultCode")) != "00":
        raise ValueError("API returned an unsuccessful result code")
    if not isinstance(body, dict):
        raise ValueError("API response body is missing")

    try:
        page_no = int(body["pageNo"])
        num_of_rows = int(body["numOfRows"])
        total_count = int(body["totalCount"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("API pagination metadata is invalid") from error

    if page_no != requested_page or total_count < 0 or num_of_rows != PAGE_SIZE:
        raise ValueError("API pagination metadata changed unexpectedly")
    items_value = body.get("items", [])
    if isinstance(items_value, dict):
        items_value = items_value.get("item", [])
    if items_value is None:
        items_value = []
    if not isinstance(items_value, list) or not all(
        isinstance(item, dict) for item in items_value
    ):
        raise ValueError("API items must be a list of objects")

    return items_value, total_count


def _open_with_retries(
    open_call: Callable[[Request, float], Any],
    request: Request,
    sleep: Callable[[float], None],
) -> bytes:
    """일시적인 HTTP·네트워크 오류만 지수 백오프로 재시도한다."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            with open_call(request, REQUEST_TIMEOUT_SECONDS) as response:
                final_url = urlparse(response.geturl())
                if not _is_api_origin(final_url):
                    raise RuntimeError("API response left the approved HTTPS origin")
                return response.read()
        except HTTPError as error:
            # 호출 제한(429)과 서버 오류(5xx)는 회복 가능하지만, 잘못된 요청인
            # 4xx를 반복하면 API 요청량만 낭비하므로 즉시 실패시킨다.
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == MAX_ATTEMPTS - 1:
                raise RuntimeError(
                    f"API request failed with HTTP {error.code}"
                ) from None
        except (URLError, TimeoutError, socket.timeout) as error:
            if attempt == MAX_ATTEMPTS - 1:
                raise RuntimeError("API request failed after retries") from error
        # 1, 2, 4, 8초 순으로 간격을 늘려 장애 중인 서버에 부담을 주지 않는다.
        sleep(float(2**attempt))
    raise AssertionError("unreachable")


def fetch_hour(
    window: HourWindow,
    api_key: str,
    source_timezone: timezone,
    *,
    opener: Callable[[Request, float], Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[MeasurementRow]:
    """정각 한 시간의 모든 페이지를 검증해 대상 관측소 행만 반환한다."""
    _parse_window_value(window.start_dtm, "00")
    _parse_window_value(window.end_dtm, "00")
    if window.start_dtm != window.end_dtm:
        raise ValueError("Hourly API start and end must be the same HH00")
    if not api_key:
        raise ValueError("PM1_API_KEY is required")
    if opener is None:
        # 운영에서는 출처 제한 핸들러를 사용한다. opener 주입은 네트워크 없이
        # 고정 응답을 검증하는 테스트에서만 사용한다.
        client = build_opener(_SameOriginRedirectHandler())
        open_call = lambda request, timeout: client.open(request, timeout=timeout)
    else:
        open_call = opener

    page = 1
    total_count: int | None = None
    raw_count = 0
    rows: list[MeasurementRow] = []
    seen_keys: set[tuple[str, str]] = set()
    while True:
        query = urlencode(
            {
                "serviceKey": api_key,
                "pageNo": page,
                "numOfRows": PAGE_SIZE,
                "contentType": "JSON",
                "startDt": window.start_dtm,
                "endDt": window.end_dtm,
            }
        )
        request = Request(
            f"{API_ENDPOINT}?{query}", headers={"Accept": "application/json"}
        )
        raw = _open_with_retries(open_call, request, sleep)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("API response is not valid UTF-8 JSON") from error
        items, page_total = _response_items(payload, page)
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise ValueError("API totalCount changed between pages")

        # 페이지 수집 중 원본 개수가 바뀌면 일부 행을 빠뜨리거나 중복 저장할 수
        # 있으므로, API가 처음 알려준 전체 개수와 끝까지 일치하는지 확인한다.
        if not items and raw_count < total_count:
            raise ValueError("API returned an empty page before totalCount was reached")
        raw_count += len(items)
        if raw_count > total_count:
            raise ValueError("API returned more rows than totalCount")
        for item in items:
            row = _parse_measurement(item, window, source_timezone)
            if row is None:
                continue
            key = (row.obsrr_tpcd, row.obsrt_dtm)
            # DB 기본키와 같은 조합으로 먼저 중복을 잡아 잘못된 응답을 DB까지
            # 보내지 않는다.
            if key in seen_keys:
                raise ValueError(f"Duplicate target observation: {key[0]} {key[1]}")
            seen_keys.add(key)
            rows.append(row)
        if raw_count == total_count:
            break
        page += 1
    if raw_count != total_count:
        raise ValueError("API final row count does not match totalCount")
    return rows
