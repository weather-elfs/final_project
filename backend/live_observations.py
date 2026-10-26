"""조회마다 최신 관측·시계열·예보를 수집하고 메모리에서 모델 입력을 맞춘다."""

import json
import logging
import math
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import pandas as pd
from backend.forecast_inputs import collect_air, collect_kma, match_forecasts
from backend.ingest_asos import prepare_records, validate_csv

from backend_airkorea_test.ingest_airkorea import prepare_records as prepare_air_records
from src.collectors.api import airkorea_collector, asos_collector

KST = ZoneInfo("Asia/Seoul")
MAX_AGE = timedelta(hours=2)
SESSION_SECONDS = 600
MAX_SESSIONS = 64
COLLECTION_PHASE_SECONDS = 25
OBSERVATION_SOURCES = ("ASOS", "AIRKOREA", "TIDE_OBSERVATORY")
FORECAST_SOURCES = ("KMA_FORECAST", "AIRKOREA_FORECAST")
SOURCES = (*OBSERVATION_SOURCES, *FORECAST_SOURCES)
_sessions = OrderedDict()
_sessions_lock = Lock()
MARINE_URL = "https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService"
# 국립해양조사원 공식 활용가이드의 관측소 목록. 기존 모델의 지점 매핑을 유지한다.
STATIONS = {
    "102": ("백령도", "IE_0062", "옹진소청초", "소청초"),
    "112": ("숭의", "DT_0001", "인천", "인천"),
    "201": ("석모리", "DT_0001", "인천", "인천"),
}
MARINE_FIELDS = {
    "wtem": "water_temp",
    "slntQty": "salinity",
    "artmp": "temp",
    "atmpr": "air_press",
    "wspd": "wind_speed",
    "wndrct": "wind_dir",
    "maxMmntWspd": "gust_speed",
}


class CollectionError(Exception):
    """소스·단계만 노출하고 인증키가 포함된 하위 예외는 응답에 노출하지 않는다."""

    def __init__(self, source, reason):
        super().__init__(f"{source}: {reason}")
        self.source = source
        self.reason = reason


def require_fresh(observed_at, reference_time, source):
    """미래 자료나 2시간을 초과한 관측을 최신 예측 입력에서 제외한다."""
    if not timedelta(0) <= reference_time - observed_at <= MAX_AGE:
        raise CollectionError(source, "STALE_OR_FUTURE_OBSERVATION")


def collect_asos(station_id, now):
    """기존 ASOS 수집기·CSV 검증기를 재사용해 선택 지점만 수집한다."""
    key = os.getenv("KMA_AUTH_KEY") or os.getenv("KMA_API_KEY")
    if not key:
        raise CollectionError("ASOS", "API_KEY_MISSING")
    end = now.replace(minute=0, second=0, microsecond=0)
    rows = asos_collector.fetch_period_data(
        int(station_id),
        (end - timedelta(hours=24)).strftime("%Y%m%d%H%M"),
        end.strftime("%Y%m%d%H%M"),
        key,
        max_retries=1,
        timeout=15,
    )
    if not rows or any(str(row.get("STN")) != station_id for row in rows):
        raise CollectionError("ASOS", "INVALID_STATION_OR_EMPTY_DATA")
    for row in rows:
        row["station_name"] = asos_collector.STATIONS[int(station_id)]
    with TemporaryDirectory() as temp:
        path = Path(temp) / "asos.csv"
        asos_collector.format_dataframe(rows).to_csv(path, index=False)
        records = prepare_records(validate_csv(path))
    return records


def collect_airkorea(station_id, now):
    """선택 측정소의 시간별 자료를 수집하고 기존 적재 스키마로 검증한다."""
    key = os.getenv("AIRKOREA_API_KEY") or os.getenv("DATA_API_KEY")
    if not key:
        raise CollectionError("AIRKOREA", "API_KEY_MISSING")
    name = STATIONS[station_id][0]
    rows = airkorea_collector.normalize(
        name, airkorea_collector.fetch(name, key, retries=1)
    )
    with TemporaryDirectory() as temp:
        path = Path(temp) / "airkorea.csv"
        pd.DataFrame(rows, columns=airkorea_collector.COLUMNS).to_csv(path, index=False)
        records, _ = prepare_air_records(path)
    # AirKorea는 다음 시각의 부분 수신 행도 공개하므로 요청 시각 이후 행은 사용하지 않는다.
    return [row for row in records if row["tm"] <= now.replace(tzinfo=None)]


def collect_marine(station_id, now):
    """승인된 KHOA API로 기존 모델 지점의 시간별 해양 자료를 수집한다."""
    key = os.getenv("DATA_API_KEY")
    if not key:
        raise CollectionError("TIDE_OBSERVATORY", "API_KEY_MISSING")
    _, code, api_name, db_name = STATIONS[station_id]
    rows = []
    # 자정 직후에도 최근 관측을 찾을 수 있도록 전일과 당일을 조회한다.
    for day in (now - timedelta(days=1), now):
        params = {
            "serviceKey": key,
            "type": "json",
            "pageNo": 1,
            "numOfRows": 300,
            "obsCode": code,
            "reqDate": day.strftime("%Y%m%d"),
            "min": 60,
        }
        for attempt in range(2):
            try:
                with urllib.request.urlopen(
                    MARINE_URL + "?" + urllib.parse.urlencode(params), timeout=10
                ) as response:
                    payload = json.load(response)
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt or (
                    isinstance(exc, urllib.error.HTTPError)
                    and exc.code < 500
                    and exc.code != 429
                ):
                    raise
                logging.getLogger("uvicorn.error").warning(
                    "해양 API 일시 통신 실패: %s / 1회 재시도", type(exc).__name__
                )
        if str(payload.get("header", {}).get("resultCode")) != "00":
            raise CollectionError("TIDE_OBSERVATORY", "UPSTREAM_ERROR")
        body = payload.get("body", {})
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        if body.get("totalCount", len(items)) > len(items):
            raise CollectionError("TIDE_OBSERVATORY", "INCOMPLETE_RESPONSE")
        for item in items:
            if item.get("obsvtrNm") != api_name:
                raise CollectionError("TIDE_OBSERVATORY", "STATION_MISMATCH")
            tm = datetime.fromisoformat(item["obsrvnDt"]).replace(tzinfo=KST)
            record = {"tm": tm.replace(tzinfo=None), "stn_name": db_name}
            for field, column in MARINE_FIELDS.items():
                raw = item.get(field)
                record[column] = None if raw is None or raw == "" else float(raw)
            rows.append(record)
    return rows


def validate_records(records, now, source):
    """원천 자료의 시각·유한 수치·최신성을 확인한다."""
    if not records:
        raise CollectionError(source, "EMPTY_DATA")
    for row in records:
        tm = row["tm"].replace(tzinfo=KST)
        if tm > now:
            raise CollectionError(source, "FUTURE_OBSERVATION")
        for value in row.values():
            if isinstance(value, (int, float)) and not math.isfinite(value):
                raise CollectionError(source, "INVALID_NUMBER")
        for key in (
            "pm25",
            "pm10",
            "co",
            "so2",
            "no2",
            "o3",
            "wind_speed",
            "visibility",
            "salinity",
            "gust_speed",
        ):
            if row.get(key) is not None and row[key] < 0:
                raise CollectionError(source, "INVALID_NUMBER")
        if row.get("humidity") is not None and not 0 <= row["humidity"] <= 100:
            raise CollectionError(source, "INVALID_NUMBER")
        if row.get("wind_dir") is not None and not 0 <= row["wind_dir"] <= 360:
            raise CollectionError(source, "INVALID_NUMBER")
    require_fresh(max(row["tm"] for row in records).replace(tzinfo=KST), now, source)


def refresh_observations(
    station_id, horizons=(3, 6, 9, 12), *, collection_id=None, retry_source=None
):
    """성공한 자료는 최대 10분 보관하고 같은 조회 조건에서 실패 출처만 다시 수집한다."""
    now = datetime.now(KST)
    if bool(collection_id) != bool(retry_source) or (
        retry_source and retry_source not in SOURCES
    ):
        raise CollectionError("REQUEST", "INVALID_RETRY")
    with _sessions_lock:
        for key, session in list(_sessions.items()):
            if monotonic() - session["created"] >= SESSION_SECONDS:
                del _sessions[key]
        if collection_id:
            entry = _sessions.get(collection_id)
            if entry is None:
                raise CollectionError("REQUEST", "COLLECTION_EXPIRED")
        else:
            collection_id = uuid.uuid4().hex
            entry = {
                "created": monotonic(),
                "lock": Lock(),
                "data": {
                    "station_id": station_id,
                    "horizons": tuple(horizons),
                    "records": dict.fromkeys(SOURCES),
                    "errors": {},
                    "fetched_at": {},
                    "requested_at": now.isoformat(),
                    "expires_at": (
                        now + timedelta(seconds=SESSION_SECONDS)
                    ).isoformat(),
                },
            }
            _sessions[collection_id] = entry
            while len(_sessions) > MAX_SESSIONS:
                _sessions.popitem(last=False)

    with entry["lock"]:
        state = entry["data"]
        if state["station_id"] != station_id or state["horizons"] != tuple(horizons):
            raise CollectionError("REQUEST", "RETRY_CONTEXT_MISMATCH")
        if retry_source and retry_source not in state.get("retryable_sources", []):
            raise CollectionError("REQUEST", "SOURCE_NOT_RETRYABLE")
        collectors = {
            "ASOS": collect_asos,
            "AIRKOREA": collect_airkorea,
            "TIDE_OBSERVATORY": collect_marine,
            "KMA_FORECAST": collect_kma,
            "AIRKOREA_FORECAST": collect_air,
        }

        def collect(sources):
            pool = ThreadPoolExecutor(max_workers=len(sources))
            try:
                futures = {}
                for source in sources:
                    args = (
                        (station_id, now)
                        if source in OBSERVATION_SOURCES
                        else (
                            (station_id, state["base_time"])
                            if source == "KMA_FORECAST"
                            else (state["base_time"],)
                        )
                    )
                    futures[source] = pool.submit(collectors[source], *args)
                _, pending = wait(futures.values(), timeout=COLLECTION_PHASE_SECONDS)
                for source, future in futures.items():
                    try:
                        if future in pending:
                            future.cancel()
                            raise TimeoutError()
                        rows = future.result()
                        if source in OBSERVATION_SOURCES:
                            validate_records(rows, now, source)
                        elif not rows:
                            raise CollectionError(source, "EMPTY_DATA")
                        state["records"][source] = rows
                        state["errors"].pop(source, None)
                        state["fetched_at"][source] = datetime.now(KST).isoformat()
                    except Exception as exc:
                        state["records"][source] = []
                        state["errors"][source] = (
                            exc.reason
                            if isinstance(exc, CollectionError)
                            else (
                                "TIMEOUT"
                                if isinstance(exc, TimeoutError)
                                else "COLLECTION_FAILED"
                            )
                        )
                        logging.getLogger("uvicorn.error").warning(
                            "API 부분 실패: %s / %s / %s",
                            source,
                            state["errors"][source],
                            type(exc).__name__,
                        )
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        if not retry_source or retry_source in OBSERVATION_SOURCES:
            collect([retry_source] if retry_source else OBSERVATION_SOURCES)
        asos = state["records"]["ASOS"] or []
        available = asos or [
            r for s in OBSERVATION_SOURCES for r in state["records"][s] or []
        ]
        state["base_time"] = (
            max(r["tm"] for r in available)
            if available
            else now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
        )
        if not retry_source or retry_source in FORECAST_SOURCES:
            collect([retry_source] if retry_source else FORECAST_SOURCES)

        errors = dict(state["errors"])
        observations, aligned_times = {}, {}
        for source in OBSERVATION_SOURCES:
            rows = [
                r
                for r in state["records"][source] or []
                if r["tm"] <= state["base_time"]
            ]
            try:
                validate_records(rows, now, source)
            except CollectionError as exc:
                errors.setdefault(source, exc.reason)
                rows = []
            observations[source] = rows
            baseline_fields = {
                "ASOS": ("visibility",),
                "AIRKOREA": ("pm25", "pm10"),
            }.get(source, ())
            if rows and any(
                max(rows, key=lambda r: r["tm"]).get(field) is None
                for field in baseline_fields
            ):
                errors.setdefault(source, "BASELINE_MISSING")
            aligned_times[source] = (
                max(r["tm"] for r in rows).replace(tzinfo=KST).isoformat()
                if rows
                else None
            )
        forecasts = match_forecasts(
            state["records"]["KMA_FORECAST"] or [],
            state["records"]["AIRKOREA_FORECAST"] or [],
            state["base_time"],
            horizons,
            allow_missing=True,
        )
        for forecast in forecasts.values():
            for source in forecast["missing_sources"]:
                errors.setdefault(source, "TARGET_TIME_MISSING_OR_STALE")
        state["retryable_sources"] = [source for source in SOURCES if source in errors]
        logging.getLogger("uvicorn.error").info(
            "[API 수집 완료] 관측소 %s / 재시도 %s / 누락 %s",
            station_id,
            retry_source,
            state["retryable_sources"],
        )
        return deepcopy(
            {
                "id": collection_id,
                "base_time": state["base_time"],
                "requested_at": state["requested_at"],
                "collected_at": datetime.now(KST).isoformat(),
                "expires_at": state["expires_at"],
                "storage": "memory",
                "fetched_at": state["fetched_at"],
                "errors": errors,
                "retryable_sources": state["retryable_sources"],
                "model_input_observed_at": aligned_times,
                "collected_rows": {
                    s: len(rows or []) for s, rows in state["records"].items()
                },
                "observations": observations,
                "forecast_inputs": forecasts,
            }
        )


def observation_history(observations, origin):
    """기존 DB의 정확한 시각 조인과 동일하게 결측 시간을 보간하지 않는다."""
    air = {row["tm"]: row for row in observations["AIRKOREA"]}
    return [
        {
            "tm": row["tm"],
            "visibility_km": (
                row["visibility"] / 100 if row.get("visibility") is not None else None
            ),
            "humidity": row.get("humidity"),
            "pressure": row.get("sea_press"),
            "pm25": air.get(row["tm"], {}).get("pm25"),
            "pm10": air.get(row["tm"], {}).get("pm10"),
        }
        for row in observations["ASOS"]
        if origin - timedelta(hours=24) <= row["tm"] <= origin
    ]
