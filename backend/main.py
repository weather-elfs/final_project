from fastapi import FastAPI
import uuid
from fastapi.responses import JSONResponse
from datetime import timedelta
from backend.model_predict import predict_visibility_pm

app = FastAPI(title="WeatherElfs Backend API", version="0.1.0")


@app.get("/")
def home():
    return {"message": "WeatherElfs 백엔드 서버 실행 성공"}


@app.get("/api/health")
def health():
    return {"status": "OK"}


from fastapi import Query, HTTPException

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


# 관측소 상태 확인 함수
def get_station_current_status(conn, station_id):
    sql = """
        SELECT tm
        FROM public.raw_weather_asos
        WHERE stn_id = %s
        ORDER BY tm DESC
        LIMIT 1
    """

    with conn.cursor() as cur:
        cur.execute(sql, (station_id,))
        row = cur.fetchone()

    if row is None:
        return "FAIL"

    # 현재 시각 기준으로 관측자료 최신성 확인
    current_time = datetime.now(KST).replace(tzinfo=None)

    status = get_data_status(row["tm"], current_time)

    # 대시보드 설정 API에서 사용하는 상태
    return "SUCCESS" if status == "OK" else "FAIL"


@app.get("/api/v1/dashboard/config")
def dashboard_config(
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
):
    if south > north or west > east:
        raise HTTPException(
            status_code=422, detail="지도 경계 좌표가 올바르지 않습니다."
        )

    # 지도 범위 안에 있는 관측소만 선택
    selected_stations = [
        station
        for station in STATIONS
        if south <= station["latitude"] <= north
        and west <= station["longitude"] <= east
    ]

    stations = []

    # PostgreSQL에서 실제 관측소 상태 조회
    try:
        with get_connection() as conn:
            for station in selected_stations:
                current_status = get_station_current_status(conn, station["station_id"])

                stations.append(
                    {
                        **station,
                        "available": True,
                        "current_status": current_status,
                        "forecast_status": "FAIL",
                    }
                )

    except Exception:
        raise HTTPException(status_code=503, detail="관측소 상태 조회에 실패했습니다.")

    return {
        "code": "SUCCESS",
        "message": "대시보드 설정을 조회했습니다.",
        "data": {
            "stations": stations,
            "forecast_intervals_h": [1, 3, 6, 12],
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
    return float(value) if isinstance(value, Decimal) else value


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

    return {
        "source": mapping["source"],
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


# 예측 시정거리 기준 안개등급 분류
def get_fog_grade_label(visibility_km: float) -> str:
    if visibility_km >= 10:
        return "정상"
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
    description="관측 데이터, 예측 시정거리, 임무 판정 결과를 조회합니다.",
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
            "description": "DB 데이터 조회 실패",
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
):
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

    sql = """
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
    FROM public.raw_weather_asos
    WHERE stn_id = %s
        AND (%s::timestamp IS NULL OR tm <= %s::timestamp)
    ORDER BY tm DESC
    LIMIT 1
"""

    try:
        # 과거 관측 시각을 지정한 경우 해당 시각으로 조회
        query_time = as_of.replace(tzinfo=None) if as_of is not None else None

        with get_connection() as conn:
            # 1. ASOS 관측 데이터 조회
            with conn.cursor() as cur:
                cur.execute(sql, (station_id, query_time, query_time))
                row = cur.fetchone()

            # 2. ASOS 관측 시각 기준 AirKorea 데이터 조회
            airkorea = (
                get_airkorea_data(conn, station_id, row["tm"])
                if row is not None
                else None
            )

            # 3. 해양 데이터 조회
            marine = (
                get_marine_data(conn, station_id, row["tm"])
                if row is not None
                else None
            )
    except Exception as e:
        print("DB 조회 오류:", repr(e))
        return JSONResponse(
            status_code=503,
            content={
                "code": "DB_ERROR",
                "message": "DB 데이터 조회에 실패했습니다.",
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
        as_of.replace(tzinfo=None)
        if as_of is not None
        else datetime.now(KST).replace(tzinfo=None)
    )

    # ASOS 상태
    asos_status = get_data_status(row["tm"], reference_time)

    # AirKorea 상태
    airkorea_time = (
        datetime.fromisoformat(airkorea["observed_at"]).replace(tzinfo=None)
        if airkorea is not None
        else None
    )

    airkorea_status = get_data_status(airkorea_time, reference_time)

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

    if not is_mock and airkorea is not None and marine is not None:
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
                    airkorea=airkorea,
                    marine=marine,
                )

                predicted_visibility = max(
                    0.0,
                    prediction["visibility_km"],
                )

                if predicted_visibility >= 10:
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
                        "visibility_pred_km": round(predicted_visibility, 2),
                        "visibility_grade": visibility_grade,
                        "fog_grade_label": get_fog_grade_label(predicted_visibility),
                        "pm25_pred_ug_m3": round(max(0.0, prediction["pm25"]), 2),
                        "pm10_pred_ug_m3": round(max(0.0, prediction["pm10"]), 2),
                    }
                )

            except Exception as e:
                print(
                    f"CatBoost {h}시간 예측 오류:",
                    repr(e),
                    flush=True,
                )
                break
    selected_forecast_timeline = (
        mock_forecast_timeline if is_mock else real_forecast_timeline
    )

    forecast_summary = get_forecast_summary(selected_forecast_timeline)

    mission_evaluation = get_mission_evaluation(
        mission_type=mission_type,
        forecast_summary=forecast_summary,
        is_mock=is_mock,
    )

    return {
        "code": "PARTIAL_SUCCESS",
        "message": (
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
            "current": {
                "observed_at": row["tm"].replace(tzinfo=KST).isoformat(),
                "temperature_c": json_number(row["temp"]),
                "relative_humidity_pct": json_number(row["humidity"]),
                "wind_speed_m_s": json_number(row["wind_speed"]),
                "visibility_km": visibility_km,
                "status": to_contract_source_status(
                    get_source_detail(row["tm"], reference_time)
                )["status"],
                "pm10_ug_m3": airkorea["pm10_ug_m3"] if airkorea else None,
                "pm25_ug_m3": airkorea["pm25_ug_m3"] if airkorea else None,
            },
            "marine": marine,
            "source_status": [
                {
                    "source": "ASOS",
                    **to_contract_source_status(
                        get_source_detail(row["tm"], reference_time)
                    ),
                },
                {
                    "source": "AIRKOREA",
                    **to_contract_source_status(
                        get_source_detail(airkorea_time, reference_time)
                    ),
                },
                {
                    "source": "TIDE_OBSERVATORY",
                    **to_contract_source_status(
                        get_source_detail(marine_time, reference_time)
                    ),
                },
            ],
            "forecast_timeline": selected_forecast_timeline,
            "forecast_summary": forecast_summary,
            "mission_evaluation": mission_evaluation,
            "diagnosis": {
                "fog_label": (
                    selected_forecast_timeline[0].get("fog_grade_label")
                    if selected_forecast_timeline
                    else None
                ),
                "pm_display_grade": None,
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
            },
        },
    }
