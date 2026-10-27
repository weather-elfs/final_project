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
from backend.logging_utils import log_json, response_snapshot

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
_air_cache = {}
_air_cache_lock = Lock()
_observation_cache = {}
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
        (end - timedelta(hours=72)).strftime("%Y%m%d%H%M"),
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


def collect_airkorea(station_id, now, *, on_response=None):
    """선택 측정소의 시간별 자료를 수집하고 기존 적재 스키마로 검증한다."""
    key = os.getenv("AIRKOREA_API_KEY") or os.getenv("DATA_API_KEY")
    if not key:
        raise CollectionError("AIRKOREA", "API_KEY_MISSING")
    name = STATIONS[station_id][0]
    rows = airkorea_collector.normalize(
        name, airkorea_collector.fetch(name, key, retries=1, on_response=on_response)
    )
    with TemporaryDirectory() as temp:
        path = Path(temp) / "airkorea.csv"
        pd.DataFrame(rows, columns=airkorea_collector.COLUMNS).to_csv(path, index=False)
        records, _ = prepare_air_records(path)
    # AirKorea는 다음 시각의 부분 수신 행도 공개하므로 요청 시각 이후 행은 사용하지 않는다.
    return [row for row in records if row["tm"] <= now.replace(tzinfo=None)]


def collect_marine(station_id, now, *, on_response=None):
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
        if on_response:
            on_response(payload)
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


def select_air_pm(records, previous_records, origin, now, *, source_reused=False):
    """관측 시각을 보존하며 항목별 마지막 정상값을 최대 2시간까지 사용한다."""
    latest = max((row["tm"] for row in records if row["tm"] <= origin), default=None)
    candidates = [(row, False) for row in records] + [
        (row, True) for row in previous_records
    ]
    selected = {}
    for field in ("pm25", "pm10"):
        valid = [
            (row, cached)
            for row, cached in candidates
            if row["tm"] <= origin
            and timedelta(0) <= now.replace(tzinfo=None) - row["tm"] <= MAX_AGE
            and row.get(field) is not None
            and math.isfinite(row[field])
            and row[field] >= 0
        ]
        if valid:
            row, cached = max(valid, key=lambda item: item[0]["tm"])
            selected[field] = {
                "value": row[field],
                "observed_at": row["tm"].replace(tzinfo=KST).isoformat(),
                "reused": source_reused
                or cached
                or (latest is not None and row["tm"] < latest),
            }
        else:
            selected[field] = {"value": None, "observed_at": None, "reused": False}
    return selected


def airkorea_communication_failure(document, now):
    """최신 관측 행의 미세먼지 통신장애 표기만 판단한다."""
    try:
        items = document["response"]["body"]["items"]
        items = [items] if isinstance(items, dict) else items
        dated = []
        for item in items:
            try:
                observed = datetime.strptime(item.get("dataTime", ""), "%Y-%m-%d %H:%M")
            except (ValueError, TypeError, AttributeError):
                continue
            if observed <= now.replace(tzinfo=None):
                dated.append((observed, item))
        if not dated:
            return False
        item = max(dated, key=lambda row: row[0])[1]
        return any(item.get(field) == "통신장애" for field in ("pm25Flag", "pm10Flag"))
    except (KeyError, TypeError):
        return False


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
                    "response_samples": {},
                    "reused_sources": [],
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
        with _air_cache_lock:
            previous_air = deepcopy(_air_cache.get(station_id, []))
        air_source_reused = state.get("air_source_reused", False)

        def collect(sources):
            nonlocal air_source_reused
            pool = ThreadPoolExecutor(max_workers=len(sources))
            try:
                futures = {}
                for source in sources:
                    samples = []
                    state["response_samples"][source] = samples
                    if source == "AIRKOREA":
                        state["airkorea_communication_failure"] = False

                    def capture(document, source=source, samples=samples):
                        samples.append(response_snapshot(document, source))
                        if source == "AIRKOREA":
                            state["airkorea_communication_failure"] = (
                                airkorea_communication_failure(document, now)
                            )

                    args = (
                        (station_id, now)
                        if source in OBSERVATION_SOURCES
                        else (
                            (station_id, state["base_time"])
                            if source == "KMA_FORECAST"
                            else (state["base_time"],)
                        )
                    )
                    kwargs = {"on_response": capture} if source != "ASOS" else {}
                    futures[source] = pool.submit(collectors[source], *args, **kwargs)
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
                        if source == "AIRKOREA":
                            air_source_reused = False
                            state["air_source_reused"] = False
                            with _air_cache_lock:
                                merged = {
                                    row["tm"]: deepcopy(row)
                                    for row in _air_cache.get(station_id, [])
                                }
                                for row in rows:
                                    old = merged.get(row["tm"], {})
                                    merged[row["tm"]] = {
                                        key: (
                                            old.get(key)
                                            if value is None
                                            and old.get(key) is not None
                                            else value
                                        )
                                        for key, value in row.items()
                                    }
                                _air_cache[station_id] = sorted(
                                    merged.values(),
                                    key=lambda row: row["tm"],
                                    reverse=True,
                                )[:72]
                        elif source in OBSERVATION_SOURCES:
                            with _air_cache_lock:
                                saved = deepcopy(
                                    _observation_cache.get((station_id, source))
                                )
                                if (
                                    saved
                                    and timedelta(0) <= now - saved[1] <= MAX_AGE
                                    and timedelta(0)
                                    <= now.replace(tzinfo=None)
                                    - max(r["tm"] for r in saved[0])
                                    <= MAX_AGE
                                    and max(r["tm"] for r in saved[0])
                                    > max(r["tm"] for r in rows)
                                ):
                                    state["records"][source] = saved[0]
                                    state["errors"][
                                        source
                                    ] = "PREVIOUS_OBSERVATION_USED"
                                    state["fetched_at"][source] = saved[1].isoformat()
                                    if source not in state["reused_sources"]:
                                        state["reused_sources"].append(source)
                                    continue
                                _observation_cache[(station_id, source)] = (
                                    deepcopy(rows),
                                    datetime.now(KST),
                                )
                        else:
                            with _air_cache_lock:
                                _observation_cache[(station_id, source)] = (
                                    deepcopy(rows),
                                    datetime.now(KST),
                                )
                        if source in state["reused_sources"]:
                            state["reused_sources"].remove(source)
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
                        if source == "AIRKOREA":
                            cached = [
                                r
                                for r in previous_air
                                if timedelta(0)
                                <= now.replace(tzinfo=None) - r["tm"]
                                <= MAX_AGE
                            ]
                            if cached:
                                state["records"][source] = deepcopy(previous_air)
                                air_source_reused = True
                                state["air_source_reused"] = True
                        else:
                            with _air_cache_lock:
                                saved = deepcopy(
                                    _observation_cache.get((station_id, source))
                                )
                            if saved and timedelta(0) <= now - saved[1] <= MAX_AGE:
                                cached, fetched_at = saved
                                try:
                                    if source in OBSERVATION_SOURCES:
                                        validate_records(cached, now, source)
                                except CollectionError:
                                    pass
                                else:
                                    state["records"][source] = cached
                                    state["fetched_at"][source] = fetched_at.isoformat()
                                    if source not in state["reused_sources"]:
                                        state["reused_sources"].append(source)
                        logging.getLogger("uvicorn.error").warning(
                            "API 부분 실패: %s / %s / %s",
                            source,
                            state["errors"][source],
                            type(exc).__name__,
                        )
                        log_json(
                            "[API 수집 오류 상세]",
                            collection_id=collection_id,
                            station_id=station_id,
                            source=source,
                            reason=state["errors"][source],
                            error_type=type(exc).__name__,
                            upstream_reason=(
                                getattr(exc, "reason", None)
                                if isinstance(getattr(exc, "reason", None), str)
                                else None
                            ),
                            http_status=getattr(exc, "code", None)
                            or getattr(exc.__cause__, "code", None),
                            response_json=state["response_samples"][source],
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
            baseline_fields = {"ASOS": ("visibility",)}.get(source, ())
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
        selected_pm = select_air_pm(
            observations["AIRKOREA"],
            previous_air,
            state["base_time"],
            now,
            source_reused=air_source_reused,
        )
        if any(item["value"] is None for item in selected_pm.values()):
            errors.setdefault(
                "AIRKOREA",
                (
                    "UPSTREAM_COMMUNICATION_FAILURE"
                    if state.get("airkorea_communication_failure")
                    else "BASELINE_MISSING"
                ),
            )
        elif any(item["reused"] for item in selected_pm.values()):
            errors.setdefault(
                "AIRKOREA",
                (
                    "UPSTREAM_COMMUNICATION_FAILURE"
                    if state.get("airkorea_communication_failure")
                    else "PREVIOUS_OBSERVATION_USED"
                ),
            )
        used_times = [
            item["observed_at"] for item in selected_pm.values() if item["observed_at"]
        ]
        if used_times:
            aligned_times["AIRKOREA"] = min(used_times)
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
        for source, reason in errors.items():
            records = state["records"][source] or []
            details = []
            if source in FORECAST_SOURCES:
                fields = (
                    (
                        "future_fcst_temp",
                        "future_fcst_humidity",
                        "future_fcst_wind_speed",
                        "future_fcst_wind_dir",
                        "future_fcst_precipitation",
                        "future_fcst_pop",
                        "future_fcst_pty",
                        "future_fcst_sky",
                    )
                    if source == "KMA_FORECAST"
                    else ("future_fcst_pm25_grade",)
                )
                for h, forecast in forecasts.items():
                    if source not in forecast["missing_sources"]:
                        continue
                    target = state["base_time"] + timedelta(hours=h)
                    target_key = (
                        "fcst_time_kst" if source == "KMA_FORECAST" else "target_date"
                    )
                    target_value = target if source == "KMA_FORECAST" else target.date()
                    matching = [
                        row for row in records if row.get(target_key) == target_value
                    ]
                    issued_key = (
                        "base_time_kst" if source == "KMA_FORECAST" else "announce_time"
                    )
                    latest = max((row[issued_key] for row in matching), default=None)
                    max_age_h = 6 if source == "KMA_FORECAST" else 24
                    cause = state["errors"].get(source) or (
                        "TARGET_NOT_PROVIDED"
                        if not matching
                        else (
                            "FORECAST_TOO_OLD"
                            if latest
                            and state["base_time"] - latest > timedelta(hours=max_age_h)
                            else "NO_USABLE_TARGET_VALUES"
                        )
                    )
                    details.append(
                        {
                            "horizon_h": h,
                            "target_at": forecast["valid_at"],
                            "cause": cause,
                            "latest_received_issued_at": latest,
                            "matching_response_count": len(matching),
                            "missing_fields": [
                                key
                                for key in fields
                                if not math.isfinite(
                                    forecast["values"].get(key, float("nan"))
                                )
                            ],
                            "input_values": {
                                key: forecast["values"].get(key) for key in fields
                            },
                        }
                    )
            else:
                latest = max(
                    observations[source], key=lambda row: row["tm"], default={}
                )
                required = {"ASOS": ("visibility",), "AIRKOREA": ("pm25", "pm10")}.get(
                    source, ()
                )
                details.append(
                    {
                        "observed_at": latest.get("tm"),
                        "missing_fields": [
                            key for key in required if latest.get(key) is None
                        ],
                        "input_values": latest,
                    }
                )
            log_json(
                "[API 누락 상세]",
                collection_id=collection_id,
                station_id=station_id,
                source=source,
                reason=reason,
                origin_at=state["base_time"],
                fetched_at=state["fetched_at"].get(source),
                received_count=len(records),
                response_json=state["response_samples"].get(source, []),
                reused_source=source in state["reused_sources"]
                or (source == "AIRKOREA" and air_source_reused),
                normalized_records=(
                    sorted(records, key=lambda row: row["tm"], reverse=True)[:3]
                    if source in OBSERVATION_SOURCES
                    else records
                ),
                selected_pm=selected_pm if source == "AIRKOREA" else None,
                missing_details=details,
            )
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
                "airkorea_pm": selected_pm,
                "reused_sources": state["reused_sources"],
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
    marine = {row["tm"]: row for row in observations.get("TIDE_OBSERVATORY", [])}
    return [
        {
            "tm": row["tm"],
            "visibility_km": (
                row["visibility"] / 100 if row.get("visibility") is not None else None
            ),
            "humidity": row.get("humidity"),
            "pressure": row.get("sea_press"),
            "temperature": row.get("temp"),
            "dewpoint": row.get("dew_point"),
            "wind_speed": row.get("wind_speed"),
            "precipitation": 0.0 if row.get("rainfall") is None else row["rainfall"],
            "sea_temp": marine.get(row["tm"], {}).get("water_temp"),
            "pm25": air.get(row["tm"], {}).get("pm25"),
            "pm10": air.get(row["tm"], {}).get("pm10"),
        }
        for row in observations["ASOS"]
        if origin - timedelta(hours=72) <= row["tm"] <= origin
    ]
