import logging
import math
import uuid
from datetime import timedelta

from backend.aqi import calculate_current_aqi
from backend.forecast_inputs import ForecastError, read_forecasts
from backend.kma_weather import (
    asos_wind_direction,
    fetch_realtime_weather,
    weather_label,
)
from backend.live_observations import (
    SOURCES,
    CollectionError,
    observation_history,
    refresh_observations,
)
from backend.model_predict import (
    METADATA_PATH,
    MODEL_PATHS,
    MODEL_VERSION,
    predict_visibility_pm,
    read_model_history,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="WeatherElfs Backend API", version="0.1.0")


# 프런트엔드 개발 서버의 API 접근 허용
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "WeatherElfs 백엔드 서버 실행 성공"}


@app.get("/api/health")
def health():
    return {"status": "OK"}


from fastapi import HTTPException, Query

STATIONS = [
    {
        "station_id": "102",
        "station_name": "백령도",
        "latitude": 37.97396,
        "longitude": 124.71237,
    },
    {
        "station_id": "112",
        "station_name": "인천",
        "latitude": 37.47772,
        "longitude": 126.62490,
    },
    {
        "station_id": "201",
        "station_name": "강화",
        "latitude": 37.70739,
        "longitude": 126.44634,
    },
]

AIRKOREA_MAPPING = {
    "102": "831492",  # 백령도 → 백령도
    "112": "823632",  # 인천 → 숭의
    "201": "831481",  # 강화 → 석모리
}

# 해양 관측소 매핑 (확정된 연결 기준)
MARINE_MAPPING = {
    "112": {
        "source": "TIDE_OBSERVATORY",
        "station_name": "인천",
    },
    "201": {
        "source": "TIDE_OBSERVATORY",
        "station_name": "인천",
    },
    "102": {
        "source": "TIDE_OBSERVATORY",
        "station_name": "소청초",
    },
}


@app.get("/api/v1/dashboard/config")
def dashboard_config(
    south: float | None = Query(None),
    west: float | None = Query(None),
    north: float | None = Query(None),
    east: float | None = Query(None),
):
    bounds = (south, west, north, east)

    if all(value is None for value in bounds):
        selected_stations = STATIONS
    elif any(value is None for value in bounds):
        raise HTTPException(
            status_code=422, detail="지도 경계 좌표 4개를 모두 입력해야 합니다."
        )
    else:
        if south > north or west > east:
            raise HTTPException(
                status_code=422, detail="지도 경계 좌표가 올바르지 않습니다."
            )

        selected_stations = [
            station
            for station in STATIONS
            if south <= station["latitude"] <= north
            and west <= station["longitude"] <= east
        ]

    stations = []

    for station in selected_stations:
        stations.append(
            {
                **station,
                "available": True,
                # 아직 수집하지 않은 관측소를 정상으로 표시하지 않는다.
                "current_status": "UNKNOWN",
                "forecast_status": (
                    "SUCCESS"
                    if all(path.is_file() for path in MODEL_PATHS.values())
                    and METADATA_PATH.is_file()
                    else "FAIL"
                ),
            }
        )

    return {
        "code": "SUCCESS",
        "message": "대시보드 설정을 조회했습니다.",
        "data": {
            "stations": stations,
            "forecast_interval_options_h": [1, 3, 6, 12],
            "forecast_slots": 4,
            "mission_types": [
                {
                    "mission_type": "MARITIME_TRANSPORT",
                    "display_name": "해상 수송 보급",
                    "enabled": True,
                    "rule_version": "maritime-transport-v1",
                    "required_metrics": ["visibility_pred_km"],
                }
            ],
        },
    }


from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.database import get_connection

KST = timezone(timedelta(hours=9))


def json_number(value):
    value = float(value) if isinstance(value, Decimal) else value
    return None if isinstance(value, float) and not math.isfinite(value) else value


# AirKorea 데이터 조회 함수
def get_airkorea_data(conn, station_id, observed_at):
    air_code = AIRKOREA_MAPPING[station_id]

    sql = """
        SELECT
            tm,
            station_name,
            station_code,
            pm10,
            pm25,
            so2,
            no2,
            o3,
            co
        FROM public.raw_air_quality
        WHERE station_code = %s
          AND tm <= %s
        ORDER BY tm DESC
        LIMIT 1
    """

    with conn.cursor() as cur:
        cur.execute(sql, (air_code, observed_at))
        row = cur.fetchone()

    if row is None:
        return None

    return format_airkorea(row)


def format_airkorea(row):
    return {
        "observed_at": row["tm"].replace(tzinfo=KST).isoformat(),
        "station_name": row["station_name"],
        "pm10_ug_m3": json_number(row["pm10"]),
        "pm25_ug_m3": json_number(row["pm25"]),
        "so2": json_number(row["so2"]),
        "no2": json_number(row["no2"]),
        "o3": json_number(row["o3"]),
        "co": json_number(row["co"]),
    }


# 해양데이터 조회 함수
def get_marine_data(conn, station_id, observed_at):
    mapping = MARINE_MAPPING.get(station_id)

    if mapping is None:
        return None

    marine_station_name = mapping["station_name"]

    sql = """
        SELECT
            tm,
            stn_name,
            water_temp,
            salinity,
            temp,
            air_press,
            wind_speed,
            wind_dir,
            gust_speed
        FROM public.raw_tide_observatory
        WHERE stn_name = %s
          AND tm <= %s
        ORDER BY tm DESC
        LIMIT 1
    """

    with conn.cursor() as cur:
        cur.execute(sql, (marine_station_name, observed_at))
        row = cur.fetchone()

    if row is None:
        return None

    return format_marine(row, mapping["source"])


def format_marine(row, source="TIDE_OBSERVATORY"):
    return {
        "source": source,
        "station_name": row["stn_name"],
        "observed_at": row["tm"].replace(tzinfo=KST).isoformat(),
        "water_temperature_c": json_number(row["water_temp"]),
        "salinity_psu": json_number(row["salinity"]),
        "air_temperature_c": json_number(row["temp"]),
        "air_pressure_hpa": json_number(row["air_press"]),
        "wind_speed_m_s": json_number(row["wind_speed"]),
        "wind_direction_deg": json_number(row["wind_dir"]),
        "gust_speed_m_s": json_number(row["gust_speed"]),
        # 새 해양 관측 테이블에는 파고 데이터가 없음
        "significant_wave_height_m": None,
        "average_wave_height_m": None,
        "wave_period_s": None,
    }


# 데이터 상태 판정 함수
def get_data_status(observed_at, reference_time, max_age_hours=2):
    # 데이터가 없는 경우
    if observed_at is None:
        return "MISSING"

    # 기준 시각과 관측 시각의 차이
    time_gap = reference_time - observed_at

    # 기준 시각보다 미래의 데이터면 사용하지 않음
    if time_gap < timedelta(0):
        return "MISSING"

    # 기준 시각으로부터 2시간 이내
    if time_gap <= timedelta(hours=max_age_hours):
        return "OK"

    # 데이터가 있지만 너무 오래된 경우
    return "STALE"


# 데이터 상태 상세 정보 함수
def get_source_detail(observed_at, reference_time, max_age_hours=2):
    status = get_data_status(observed_at, reference_time, max_age_hours)

    # 관측 데이터가 없는 경우
    if observed_at is None:
        return {
            "status": "MISSING",
            "observed_at": None,
            "age_minutes": None,
            "reason": "NO_DATA",
        }

    age_minutes = int((reference_time - observed_at).total_seconds() / 60)

    # 미래 시각의 데이터는 유효하지 않음
    if age_minutes < 0:
        return {
            "status": "MISSING",
            "observed_at": None,
            "age_minutes": None,
            "reason": "FUTURE_OBSERVATION",
        }

    return {
        "status": status,
        "observed_at": observed_at.replace(tzinfo=KST).isoformat(),
        "age_minutes": age_minutes,
        "reason": "OUTDATED" if status == "STALE" else None,
    }


def to_contract_source_status(detail):
    status_mapping = {
        "OK": "fresh",
        "STALE": "delayed",
        "MISSING": "missing",
    }

    return {
        **detail,
        "status": status_mapping.get(detail["status"], "missing"),
    }


# ASOS 관측소 ID -> AirKorea 측정소
AIR_STATION_MAP = {
    "102": "백령도",
    "112": "숭의",
    "201": "석모리",
}


def get_station_aqi(conn, station_id, observed_at):
    empty = calculate_current_aqi([], [])

    if observed_at is None:
        return empty

    station_codes = {
        "102": "831492",
        "112": "823632",
        "201": "831481",
    }

    code = station_codes.get(str(station_id))
    if code is None:
        return empty

    anchor = observed_at.replace(tzinfo=None, minute=0, second=0, microsecond=0)

    # 현재 표시·모델·AQI가 같은 DB 스냅샷을 사용한다. CSV로 덮어쓰지 않는다.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.pm25, a.pm10
            FROM generate_series(
                %s::timestamp - INTERVAL '11 hours',
                %s::timestamp,
                INTERVAL '1 hour'
            ) AS h(obs_hour)
            LEFT JOIN public.raw_air_quality a
              ON a.tm = h.obs_hour
             AND a.station_code = %s
            ORDER BY h.obs_hour DESC
        """,
            (anchor, anchor, code),
        )

        db_rows = cur.fetchall()

    pm25 = []
    pm10 = []

    for row in db_rows:
        db25 = row["pm25"] if isinstance(row, dict) else row[0]
        db10 = row["pm10"] if isinstance(row, dict) else row[1]
        pm25.append(db25)
        pm10.append(db10)

    return calculate_current_aqi(pm25, pm10)


# 예측 시정거리 기준 안개등급 분류
def get_fog_grade_label(visibility_km: float) -> str:
    if visibility_km >= 10:
        return "안개 없음"
    elif visibility_km >= 2:
        return "옅은 안개"
    elif visibility_km >= 0.5:
        return "안개"
    else:
        return "짙은 안개"


# 예측 시정거리가 가장 낮은 시점 반환
def get_forecast_summary(forecast_timeline: list) -> dict | None:
    if not forecast_timeline:
        return None

    valid_forecasts = [
        item for item in forecast_timeline if item.get("visibility_pred_km") is not None
    ]

    if not valid_forecasts:
        return None

    worst_forecast = min(
        valid_forecasts,
        key=lambda item: item["visibility_pred_km"],
    )

    return {
        **worst_forecast,
        "selection_reason": "MIN_VISIBILITY",
    }


def get_mission_evaluation(
    mission_type: str,
    forecast_summary: dict | None,
    is_mock: bool,
) -> dict:
    result = {
        "mission_type": mission_type,
        "rule_version": "maritime-transport-v1",
        "evaluation_status": "NOT_EVALUABLE",
        "passed": None,
        "mission_grade": "UNKNOWN",
        "factors": [],
        "reason_codes": [],
    }

    # Mock 데이터는 실제 임무 판정에 사용하지 않음
    if is_mock:
        result["reason_codes"] = ["MOCK_DATA"]
        return result

    # MVP에서는 해상 수송·보급 임무만 지원
    if mission_type != "MARITIME_TRANSPORT":
        result["reason_codes"] = ["MISSION_RULE_NOT_APPLIED"]
        return result

    # 예측 결과가 없으면 판정 불가
    if forecast_summary is None:
        result["reason_codes"] = ["FORECAST_NOT_READY"]
        return result

    visibility = forecast_summary.get("visibility_pred_km")

    if visibility is None:
        result["reason_codes"] = ["VISIBILITY_MISSING"]
        result["factors"] = [
            {
                "metric": "visibility_pred_km",
                "actual": None,
                "operator": ">=",
                "threshold": 1.0,
                "unit": "km",
                "required": True,
                "passed": None,
            }
        ]
        return result

    threshold = 1.0
    passed = visibility >= threshold

    result["evaluation_status"] = "EVALUATED"
    result["passed"] = passed
    result["mission_grade"] = "NORMAL" if passed else "RESTRICTED"

    result["factors"] = [
        {
            "metric": "visibility_pred_km",
            "actual": visibility,
            "operator": ">=",
            "threshold": threshold,
            "unit": "km",
            "required": True,
            "passed": passed,
        }
    ]

    result["reason_codes"] = [
        "VISIBILITY_OK" if passed else "VISIBILITY_BELOW_THRESHOLD"
    ]

    return result


def get_diagnosis_summary(
    mission_evaluation: dict,
    is_mock: bool,
) -> str:
    if is_mock:
        return "모의 데이터입니다. 실제 임무 판정 결과가 아닙니다."

    if mission_evaluation["evaluation_status"] != "EVALUATED":
        return "임무 판정에 필요한 데이터 또는 규칙이 부족합니다."

    if mission_evaluation["passed"]:
        return "해상 수송·보급 임무 기준을 충족합니다."

    return "예측 시정거리가 임무 기준인 1.0km 미만입니다."


@app.get(
    "/api/v1/stations/{station_id}/dashboard",
    summary="선택 관측소 대시보드 조회",
    responses={
        200: {
            "description": "대시보드 조회 성공 또는 일부 기능 준비 중",
            "content": {
                "application/json": {
                    "example": {
                        "code": "PARTIAL_SUCCESS",
                        "message": "관측 데이터 조회 및 예측 결과 반환",
                        "data": {
                            "station": {
                                "station_id": "112",
                                "station_name": "인천",
                            },
                            "request_context": {
                                "forecast_interval_h": 3,
                                "forecast_horizons_h": [3, 6, 9, 12],
                                "mission_type": "MARITIME_TRANSPORT",
                            },
                            "current": {},
                            "marine": None,
                            "source_status": [],
                            "forecast_timeline": [],
                            "forecast_summary": None,
                            "mission_evaluation": {},
                            "diagnosis": {},
                            "meta": {
                                "request_id": "req_example",
                                "partial": True,
                                "mock": False,
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": (
                "지원하지 않는 관측소이거나 " "해당 시점의 관측 데이터가 없는 경우"
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "station_not_found": {
                            "summary": "지원하지 않는 관측소",
                            "value": {
                                "code": "STATION_NOT_FOUND",
                                "message": "지원하지 않는 관측소입니다.",
                                "data": {
                                    "station_id": "99999",
                                    "meta": {"request_id": "req_example"},
                                },
                            },
                        },
                        "observation_not_found": {
                            "summary": "관측 데이터 없음",
                            "value": {
                                "code": "OBSERVATION_NOT_FOUND",
                                "message": "관측 데이터가 없습니다.",
                                "data": {
                                    "station_id": "112",
                                    "meta": {"request_id": "req_example"},
                                },
                            },
                        },
                    }
                }
            },
        },
        422: {
            "description": "요청 파라미터가 유효하지 않은 경우",
            "content": {
                "application/json": {
                    "example": {
                        "code": "INVALID_PARAMETER",
                        "message": "예측 간격은 1, 3, 6, 12시간 중 선택해야 합니다.",
                        "data": {
                            "forecast_interval_h": 2,
                            "meta": {"request_id": "req_example"},
                        },
                    }
                }
            },
        },
        503: {
            "description": "최신 수집·적재 실패(LATEST_DATA_UNAVAILABLE), 예보 입력 실패(FORECAST_INPUT_UNAVAILABLE), 예측 실패(FORECAST_FAILED), DB 조회 실패(DB_ERROR)",
            "content": {
                "application/json": {
                    "example": {
                        "code": "DB_ERROR",
                        "message": "DB 데이터 조회에 실패했습니다.",
                        "data": {"meta": {"request_id": "req_example"}},
                    }
                }
            },
        },
    },
)
def station_dashboard(
    station_id: str,
    forecast_interval_h: int = Query(
        default=3,
        description="예측 간격(시간). 선택 가능: 1, 3, 6, 12",
    ),
    mission_type: str = Query(
        default="MARITIME_TRANSPORT",
        description="임무유형 코드. 현재 구현: MARITIME_TRANSPORT",
    ),
    as_of: datetime | None = Query(
        default=None,
        description="과거 데이터 테스트용 기준 시각. 예: 2022-01-01T01:00:00+09:00",
    ),
    mock: bool = Query(
        default=False,
        description="프론트엔드 연동 테스트용 Mock 예측 데이터 사용 여부",
    ),
    collection_id: str | None = Query(
        default=None,
        max_length=64,
        description="부분 수집 응답의 meta.collection.id. 재시도 시 원래 조회 조건을 유지합니다.",
    ),
    retry_source: str | None = Query(
        default=None,
        description="실패 출처만 재시도: ASOS, AIRKOREA, TIDE_OBSERVATORY, KMA_FORECAST, AIRKOREA_FORECAST",
    ),
):
    """일반 조회는 최신 관측·시계열·기상청 단기예보·AirKorea PM2.5 예보를 API에서 수집하고 메모리에서 예측합니다. DB 연결·적재는 하지 않습니다.

    기관별 공개 주기가 달라 관측 시각은 요청 시각과 다를 수 있습니다.
    실제 입력 시각은 data.meta.collection.model_input_observed_at에 포함됩니다.
    예보 입력·발표시각은 data.meta.forecasts, 모델·결측 입력 정보는 data.meta.model에 포함됩니다.
    as_of 과거 조회와 인천 mock=true 시연은 최신 수집을 수행하지 않습니다.
    """
    if station_id not in ("102", "112", "201"):
        return JSONResponse(
            status_code=404,
            content={
                "code": "STATION_NOT_FOUND",
                "message": "지원하지 않는 관측소입니다.",
                "data": {
                    "station_id": station_id,
                    "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                },
            },
        )

    # 예측 간격 검증
    if forecast_interval_h not in (1, 3, 6, 12):
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_PARAMETER",
                "message": "예측 간격은 1, 3, 6, 12시간 중 선택해야 합니다.",
                "data": {
                    "forecast_interval_h": forecast_interval_h,
                    "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                },
            },
        )

    # 임무유형 검증
    if mission_type not in ("MARITIME_TRANSPORT",):
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_PARAMETER",
                "message": "지원하지 않는 임무유형입니다.",
                "data": {
                    "mission_type": mission_type,
                    "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                },
            },
        )

    collection = None
    horizons = [forecast_interval_h * i for i in range(1, 5)]
    if (
        bool(collection_id) != bool(retry_source)
        or (retry_source and retry_source not in SOURCES)
        or ((collection_id or retry_source) and (as_of is not None or mock))
    ):
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_PARAMETER",
                "message": "재시도 ID·출처와 기존 실시간 조회 조건을 확인하세요.",
            },
        )
    if as_of is None and not (mock and station_id == "112"):
        try:
            collection = (
                refresh_observations(
                    station_id,
                    horizons=horizons,
                    collection_id=collection_id,
                    retry_source=retry_source,
                )
                if retry_source
                else refresh_observations(station_id, horizons=horizons)
            )
        except CollectionError as exc:
            print(
                f"최신 수집 실패: {exc.source} / {exc.reason} / {type(exc.__cause__).__name__}",
                flush=True,
            )
            return JSONResponse(
                status_code=409 if exc.source == "REQUEST" else 503,
                content={
                    "code": (
                        exc.reason
                        if exc.source == "REQUEST"
                        else "LATEST_DATA_UNAVAILABLE"
                    ),
                    "message": (
                        "재시도할 자료가 만료되었거나 조회 조건이 다릅니다. 전체 갱신을 실행하세요."
                        if exc.source == "REQUEST"
                        else "최신 관측·예보 수집을 처리하지 못했습니다."
                    ),
                    "data": {
                        "source": exc.source,
                        "reason": exc.reason,
                        "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                    },
                },
            )

    # 조회 모드에 따라 ASOS 테이블 선택
    # 날짜 미지정: 실시간 테이블
    # 날짜 지정: 과거 데이터 테이블
    asos_table = (
        "public.raw_weather_asos"
        if as_of is not None
        else "public.raw_weather_asos_realtime"
    )

    sql = f"""
    SELECT
        tm,
        stn_id,
        stn_ko,
        temp,
        humidity,
        dew_point,
        wind_speed,
        wind_dir,
        sea_press,
        rainfall,
        cloud,
        visibility
    FROM {asos_table}
    WHERE stn_id = %s
        AND (%s::timestamp IS NULL OR tm <= %s::timestamp)
    ORDER BY tm DESC
    LIMIT 1
"""

    try:
        # 과거 관측 시각을 지정한 경우 해당 시각으로 조회
        query_time = (
            as_of.astimezone(KST).replace(tzinfo=None)
            if as_of is not None and as_of.tzinfo is not None
            else as_of
        )
        if collection is not None:
            query_time = collection["base_time"]

        if collection is not None:
            observations = collection["observations"]
            latest = {
                source: max(
                    (r for r in records if r["tm"] <= query_time),
                    key=lambda r: r["tm"],
                    default=None,
                )
                for source, records in observations.items()
            }
            row = latest["ASOS"] or {
                "_missing": True,
                **dict.fromkeys(
                    (
                        "temp",
                        "humidity",
                        "dew_point",
                        "wind_speed",
                        "wind_dir",
                        "sea_press",
                        "rainfall",
                        "cloud",
                        "visibility",
                    )
                ),
                "tm": query_time,
                "stn_id": station_id,
                "stn_ko": next(
                    s["station_name"] for s in STATIONS if s["station_id"] == station_id
                ),
            }
            airkorea = (
                format_airkorea(latest["AIRKOREA"]) if latest["AIRKOREA"] else None
            )
            marine = (
                format_marine(latest["TIDE_OBSERVATORY"])
                if latest["TIDE_OBSERVATORY"]
                else None
            )
            anchor = (
                latest["AIRKOREA"]["tm"] if latest["AIRKOREA"] else query_time
            ).replace(minute=0, second=0, microsecond=0)
            air_hours = {r["tm"]: r for r in observations["AIRKOREA"]}
            hours = [air_hours.get(anchor - timedelta(hours=i), {}) for i in range(12)]
            current_aqi = calculate_current_aqi(
                [r.get("pm25") for r in hours], [r.get("pm10") for r in hours]
            )
            model_history = observation_history(observations, query_time)
            forecast_inputs = collection["forecast_inputs"]
        else:
            with get_connection() as conn:
                conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                with conn.cursor() as cur:
                    cur.execute(sql, (station_id, query_time, query_time))
                    row = cur.fetchone()
                airkorea = (
                    get_airkorea_data(conn, station_id, row["tm"])
                    if row is not None
                    else None
                )
                aqi_time = (
                    datetime.fromisoformat(airkorea["observed_at"]).replace(tzinfo=None)
                    if airkorea is not None
                    else None
                )
                current_aqi = get_station_aqi(conn, station_id, aqi_time)
                marine = (
                    get_marine_data(conn, station_id, row["tm"])
                    if row is not None
                    else None
                )
                forecast_inputs, model_history = {}, []
                if row is not None and not (mock and station_id == "112"):
                    forecast_inputs = read_forecasts(
                        conn, station_id, row["tm"], horizons
                    )
                    model_history = read_model_history(
                        conn, station_id, row["tm"], asos_table
                    )
    except ForecastError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "code": "FORECAST_INPUT_UNAVAILABLE",
                "message": "요청 시점에 맞는 예보 입력이 없어 예측을 실행하지 않았습니다.",
                "data": {
                    "source": exc.source,
                    "reason": exc.reason,
                    "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                },
            },
        )
    except Exception as e:
        print("입력 구성 오류:", type(e).__name__, flush=True)
        return JSONResponse(
            status_code=503,
            content={
                "code": "LATEST_DATA_UNAVAILABLE" if collection else "DB_ERROR",
                "message": "예측 입력 구성에 실패했습니다.",
                "data": {"meta": {"request_id": f"req_{uuid.uuid4().hex}"}},
            },
        )

    if row is None:
        return JSONResponse(
            status_code=404,
            content={
                "code": "OBSERVATION_NOT_FOUND",
                "message": "관측 데이터가 없습니다.",
                "data": {
                    "station_id": station_id,
                    "meta": {"request_id": f"req_{uuid.uuid4().hex}"},
                },
            },
        )

    # 상태 판정 기준 시각
    reference_time = (
        query_time if as_of is not None else datetime.now(KST).replace(tzinfo=None)
    )
    display_airkorea = airkorea

    asos_time = (
        (
            datetime.fromisoformat(
                collection["model_input_observed_at"]["ASOS"]
            ).replace(tzinfo=None)
            if collection and collection["model_input_observed_at"].get("ASOS")
            else None
        )
        if collection
        else row["tm"]
    )
    asos_status = get_data_status(asos_time, reference_time)

    # AirKorea 상태
    airkorea_time = (
        datetime.fromisoformat(display_airkorea["observed_at"]).replace(tzinfo=None)
        if display_airkorea is not None
        else None
    )
    airkorea_status = get_data_status(airkorea_time, reference_time)

    # AQI 관측자료 최신성 검증
    AQI_MAX_AGE_HOURS = 2

    aqi_age_hours = (
        (reference_time - airkorea_time).total_seconds() / 3600
        if airkorea_time is not None
        else None
    )

    if aqi_age_hours is None or aqi_age_hours < 0 or aqi_age_hours > AQI_MAX_AGE_HOURS:
        current_aqi = calculate_current_aqi([], [])

    # 해양 데이터 상태

    marine_time = (
        datetime.fromisoformat(marine["observed_at"]).replace(tzinfo=None)
        if marine is not None
        else None
    )

    marine_status = get_data_status(marine_time, reference_time)

    # 시정거리 변환
    visibility_km = row["visibility"] / 100 if row["visibility"] is not None else None
    # 프론트엔드 연동 테스트용 Mock 데이터
    is_mock = mock and station_id == "112" and mission_type == "MARITIME_TRANSPORT"
    mock_base_time = (
        reference_time.replace(tzinfo=KST)
        if reference_time.tzinfo is None
        else reference_time.astimezone(KST)
    )

    mock_visibility_values = [8.5, 3.2, 0.8, 6.4]

    mock_forecast_timeline = []

    for index, visibility in enumerate(mock_visibility_values, start=1):
        horizon = forecast_interval_h * index

        if visibility >= 10:
            visibility_grade = "GOOD"
        elif visibility >= 4:
            visibility_grade = "MODERATE"
        elif visibility >= 1:
            visibility_grade = "BAD"
        else:
            visibility_grade = "VERY_BAD"

        mock_forecast_timeline.append(
            {
                "horizon_h": horizon,
                "valid_at": (mock_base_time + timedelta(hours=horizon)).isoformat(),
                "visibility_pred_km": visibility,
                "visibility_grade": visibility_grade,
                "fog_grade_label": get_fog_grade_label(visibility),
                "pm25_pred_ug_m3": None,
                "pm10_pred_ug_m3": None,
            }
        )

    # CatBoost 시간대별 예측 (4개 시점)
    real_forecast_timeline = []
    missing_features = set()

    if not is_mock:
        for h in range(
            forecast_interval_h,
            forecast_interval_h * 4 + 1,
            forecast_interval_h,
        ):

            try:
                prediction = predict_visibility_pm(
                    station_id=station_id,
                    observed_at=row["tm"],
                    h=h,
                    asos=row,
                    airkorea=airkorea
                    or dict.fromkeys(
                        ("pm25_ug_m3", "pm10_ug_m3", "so2", "no2", "o3", "co")
                    ),
                    marine=marine
                    or dict.fromkeys(
                        (
                            "water_temperature_c",
                            "air_temperature_c",
                            "salinity_psu",
                            "wind_speed_m_s",
                            "wind_direction_deg",
                            "air_pressure_hpa",
                        )
                    ),
                    history=model_history,
                    forecast=forecast_inputs[h],
                )
                missing_features.update(prediction.get("missing_features", []))
                values = {
                    key: json_number(prediction.get(key))
                    for key in ("visibility_km", "pm25", "pm10")
                }
                unavailable = [key for key, value in values.items() if value is None]
                missing_sources = sorted(
                    set(forecast_inputs[h].get("missing_sources", []))
                    | {
                        source
                        for source in (collection or {}).get("errors", {})
                        if source in ("ASOS", "AIRKOREA", "TIDE_OBSERVATORY")
                    }
                )
                predicted_visibility = values["visibility_km"]

                if predicted_visibility is None:
                    visibility_grade = None
                elif predicted_visibility >= 10:
                    visibility_grade = "GOOD"
                elif predicted_visibility >= 4:
                    visibility_grade = "MODERATE"
                elif predicted_visibility >= 1:
                    visibility_grade = "BAD"
                else:
                    visibility_grade = "VERY_BAD"

                real_forecast_timeline.append(
                    {
                        "horizon_h": h,
                        "valid_at": (
                            row["tm"].replace(tzinfo=KST) + timedelta(hours=h)
                        ).isoformat(),
                        "visibility_pred_km": (
                            round(predicted_visibility, 2)
                            if predicted_visibility is not None
                            else None
                        ),
                        "visibility_grade": visibility_grade,
                        "fog_grade_label": (
                            get_fog_grade_label(predicted_visibility)
                            if predicted_visibility is not None
                            else None
                        ),
                        "pm25_pred_ug_m3": (
                            round(values["pm25"], 2)
                            if values["pm25"] is not None
                            else None
                        ),
                        "pm10_pred_ug_m3": (
                            round(values["pm10"], 2)
                            if values["pm10"] is not None
                            else None
                        ),
                        "status": (
                            "unavailable"
                            if len(unavailable) == 3
                            else (
                                "degraded"
                                if missing_sources or unavailable
                                else "ready"
                            )
                        ),
                        "missing_sources": missing_sources,
                        "missing_features": prediction.get("missing_features", []),
                        "unavailable_targets": unavailable,
                    }
                )

            except Exception as e:
                print(
                    f"CatBoost {h}시간 예측 오류:",
                    repr(e),
                    flush=True,
                )
                real_forecast_timeline.append(
                    {
                        "horizon_h": h,
                        "valid_at": (
                            row["tm"].replace(tzinfo=KST) + timedelta(hours=h)
                        ).isoformat(),
                        "visibility_pred_km": None,
                        "pm25_pred_ug_m3": None,
                        "pm10_pred_ug_m3": None,
                        "status": "unavailable",
                        "reason": "MODEL_ERROR",
                        "unavailable_targets": ["visibility_km", "pm25", "pm10"],
                    }
                )
    selected_forecast_timeline = (
        mock_forecast_timeline if is_mock else real_forecast_timeline
    )

    if collection is not None:
        logging.getLogger("uvicorn.error").info(
            "[예측 완료] 관측소 %s / 예측 간격 %s시간 / 4개 시점",
            station_id,
            forecast_interval_h,
        )

    forecast_summary = get_forecast_summary(selected_forecast_timeline)

    mission_evaluation = get_mission_evaluation(
        mission_type=mission_type,
        forecast_summary=forecast_summary,
        is_mock=is_mock,
    )

    if collection and any(p.get("status") != "ready" for p in real_forecast_timeline):
        mission_evaluation = get_mission_evaluation(mission_type, None, False)
        mission_evaluation["reason_codes"] = ["INPUT_INCOMPLETE"]

    source_status = [
        {
            "source": source,
            **to_contract_source_status(get_source_detail(tm, reference_time)),
        }
        for source, tm in (
            ("ASOS", asos_time),
            ("AIRKOREA", airkorea_time),
            ("TIDE_OBSERVATORY", marine_time),
        )
    ]
    if collection:
        for source, key in (
            ("KMA_FORECAST", "kma_issued_at"),
            ("AIRKOREA_FORECAST", "airkorea_issued_at"),
        ):
            issued = max(
                (f[key] for f in forecast_inputs.values() if f.get(key)), default=None
            )
            source_status.append(
                {
                    "source": source,
                    "status": "fresh",
                    "observed_at": None,
                    "issued_at": issued,
                    "collected_at": collection.get("fetched_at", {}).get(source),
                    "age_minutes": None,
                    "reason": None,
                }
            )
        for source in source_status:
            if source["source"] in collection.get("errors", {}):
                source.update(
                    status=(
                        "partial"
                        if source.get("observed_at") or source.get("issued_at")
                        else "missing"
                    ),
                    reason=collection["errors"][source["source"]],
                )
        first = next(
            (
                f
                for f in forecast_inputs.values()
                if math.isfinite(f["values"].get("future_fcst_sky", float("nan")))
                and math.isfinite(f["values"].get("future_fcst_pty", float("nan")))
            ),
            None,
        )
        kma_forecast = (
            {
                "source": "KMA_VILAGE_FORECAST",
                "forecast_at": first["valid_at"],
                "weather_label": weather_label(
                    str(int(first["values"]["future_fcst_sky"])),
                    str(int(first["values"]["future_fcst_pty"])),
                ),
            }
            if first
            else None
        )
    else:
        kma_forecast = fetch_realtime_weather(station_id)

    return {
        "code": "PARTIAL_SUCCESS",
        "message": (
            "받은 자료와 가능한 예측을 표시합니다. 누락 출처는 개별 재시도할 수 있습니다."
            if collection
            and (
                collection.get("errors")
                or any(p.get("status") != "ready" for p in real_forecast_timeline)
            )
            else (
                "관측 데이터 조회 성공. 프런트엔드 테스트용 Mock 예측데이터이며 실제 임무 판정은 수행하지 않습니다."
                if is_mock
                else (
                    "관측 데이터 조회 및 CatBoost 예측 완료. 해상 수송·보급 임무 기준 판정을 수행했습니다. 일부 기능은 준비 중입니다."
                    if (
                        len(real_forecast_timeline) == 4
                        and mission_evaluation["evaluation_status"] == "EVALUATED"
                    )
                    else (
                        "관측 데이터 조회 및 CatBoost 예측 완료. 임무 판정은 수행되지 않았습니다."
                        if len(real_forecast_timeline) == 4
                        else "관측 데이터 조회 성공. 예측 결과가 없거나 일부만 생성되었습니다."
                    )
                )
            )
        ),
        "data": {
            "station": {
                "station_id": row["stn_id"],
                "station_name": row["stn_ko"],
            },
            "request_context": {
                "forecast_interval_h": forecast_interval_h,
                "forecast_horizons_h": [
                    item["horizon_h"]
                    for item in (
                        mock_forecast_timeline if is_mock else real_forecast_timeline
                    )
                ],
                "mission_type": mission_type,
            },
            "kma_forecast": kma_forecast,
            "current": {
                "weather_label": (
                    kma_forecast.get("weather_label") if kma_forecast else None
                ),
                "weather_source": (
                    kma_forecast.get("source") if kma_forecast else None
                ),
                "weather_forecast_at": (
                    kma_forecast.get("forecast_at") if kma_forecast else None
                ),
                "observed_at": (
                    asos_time.replace(tzinfo=KST).isoformat() if asos_time else None
                ),
                "temperature_c": json_number(row["temp"]),
                "relative_humidity_pct": json_number(row["humidity"]),
                "temperature_dewpoint_spread_c": (
                    round(float(row["temp"]) - float(row["dew_point"]), 2)
                    if row["temp"] is not None and row["dew_point"] is not None
                    else None
                ),
                "wind_speed_m_s": json_number(row["wind_speed"]),
                "visibility_km": visibility_km,
                "wind_direction_deg": asos_wind_direction(row["wind_dir"])[
                    "wind_direction_deg"
                ],
                "wind_direction_label": asos_wind_direction(row["wind_dir"])[
                    "wind_direction_label"
                ],
                "status": to_contract_source_status(
                    get_source_detail(asos_time, reference_time)
                )["status"],
                "pm10_ug_m3": (
                    display_airkorea["pm10_ug_m3"] if display_airkorea else None
                ),
                "pm25_ug_m3": (
                    display_airkorea["pm25_ug_m3"] if display_airkorea else None
                ),
                "aqi": current_aqi,
            },
            "marine": marine,
            "source_status": source_status,
            "forecast_timeline": selected_forecast_timeline,
            "forecast_summary": forecast_summary,
            "mission_evaluation": mission_evaluation,
            "diagnosis": {
                "fog_label": (
                    selected_forecast_timeline[0].get("fog_grade_label")
                    if selected_forecast_timeline
                    else None
                ),
                "pm_display_grade": current_aqi["display_grade"],
                "summary": get_diagnosis_summary(
                    mission_evaluation=mission_evaluation,
                    is_mock=is_mock,
                ),
            },
            "meta": {
                "request_id": f"req_{uuid.uuid4().hex}",
                "generated_at": datetime.now(KST).isoformat(),
                "partial": True,
                "mock": is_mock,
                "model": (
                    None
                    if is_mock
                    else {
                        "name": "catboost_observation_forecast_tuned",
                        "version": MODEL_VERSION,
                        "feature_count": 89,
                        "transform": "expm1(log1p(current) + predicted_residual * sigma[h])",
                        "missing_features": sorted(missing_features),
                        "origin_at": row["tm"].replace(tzinfo=KST).isoformat(),
                    }
                ),
                "forecasts": (
                    [
                        {
                            "horizon_h": h,
                            **forecast_inputs[h],
                            "values": {
                                k: json_number(v)
                                for k, v in forecast_inputs[h]["values"].items()
                            },
                        }
                        for h in horizons
                    ]
                    if not is_mock
                    else []
                ),
                "collection": (
                    {
                        key: value
                        for key, value in collection.items()
                        if key not in ("base_time", "observations", "forecast_inputs")
                    }
                    if collection is not None
                    else None
                ),
            },
        },
    }
