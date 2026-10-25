"""조회마다 최신 관측을 수집·검증하고 기존 DB에 한 트랜잭션으로 적재한다."""

import json
import math
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pandas as pd
from backend.database import get_connection
from backend.forecast_inputs import ForecastError, collect_forecasts, store_forecasts
from backend.ingest_asos import insert_records, prepare_records, validate_csv

from backend_airkorea_test.ingest_airkorea import (
    apply_records,
)
from backend_airkorea_test.ingest_airkorea import prepare_records as prepare_air_records
from src.collectors.api import airkorea_collector, asos_collector

KST = ZoneInfo("Asia/Seoul")
MAX_AGE = timedelta(hours=2)
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
    return records


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
        with urllib.request.urlopen(
            MARINE_URL + "?" + urllib.parse.urlencode(params), timeout=15
        ) as response:
            payload = json.load(response)
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


def refresh_observations(station_id, horizons=(3, 6, 9, 12)):
    """모든 소스 검증 후 원자적으로 적재하고 모델 입력 기준 시각을 반환한다."""
    now = datetime.now(KST)
    collectors = {
        "ASOS": collect_asos,
        "AIRKOREA": collect_airkorea,
        "TIDE_OBSERVATORY": collect_marine,
    }
    observations = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            source: pool.submit(collect, station_id, now)
            for source, collect in collectors.items()
        }
        for source, future in futures.items():
            try:
                records = future.result()
                validate_records(records, now, source)
                observations[source] = records
            except CollectionError:
                raise
            except Exception as exc:
                raise CollectionError(source, "COLLECTION_FAILED") from exc

    base_time = max(row["tm"] for row in observations["ASOS"])
    aligned_times = {}
    for source, records in observations.items():
        aligned = [row for row in records if row["tm"] <= base_time]
        if not aligned:
            raise CollectionError(source, "NO_ALIGNED_OBSERVATION")
        tm = max(row["tm"] for row in aligned)
        require_fresh(tm.replace(tzinfo=KST), now, source)
        aligned_times[source] = tm.replace(tzinfo=KST).isoformat()

    try:
        forecasts = collect_forecasts(station_id, base_time, horizons)
    except ForecastError as exc:
        raise CollectionError(exc.source, exc.reason) from exc

    try:
        with get_connection() as conn:
            conn.execute("SET LOCAL statement_timeout = '10s'")
            stored = {
                "ASOS": insert_records(
                    observations["ASOS"], apply=True, connection=conn
                ),
                "AIRKOREA": apply_records(observations["AIRKOREA"], connection=conn),
            }
            columns = ["tm", "stn_name", *MARINE_FIELDS.values()]
            sql = f"""INSERT INTO public.raw_tide_observatory ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                ON CONFLICT (tm, stn_name) DO UPDATE SET
                {', '.join(f'{c} = EXCLUDED.{c}' for c in columns if c not in ('tm', 'stn_name'))}"""
            stored["TIDE_OBSERVATORY"] = 0
            with conn.cursor() as cur:
                for row in observations["TIDE_OBSERVATORY"]:
                    cur.execute(sql, tuple(row[c] for c in columns))
                    stored["TIDE_OBSERVATORY"] += cur.rowcount
            stored.update(store_forecasts(conn, station_id, forecasts))
    except Exception as exc:
        raise CollectionError("DATABASE", "INGEST_FAILED") from exc

    return {
        "base_time": base_time,
        "requested_at": now.isoformat(),
        "collected_at": datetime.now(KST).isoformat(),
        "model_input_observed_at": aligned_times,
        "stored_rows": stored,
        "forecast_provenance": forecasts["expected"],
    }
