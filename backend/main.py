from fastapi import FastAPI
import uuid
from fastapi.responses import JSONResponse

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
        SELECT tm, station_name, station_code, pm10, pm25
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


@app.get("/api/v1/stations/{station_id}/dashboard")
def station_dashboard(
    station_id: str,
    forecast_interval_h: int = Query(default=3),
    mission_type: str = Query(default="MARITIME_TRANSPORT"),
    as_of: datetime | None = None,
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
            tm, stn_id, stn_ko,
            temp, humidity, wind_speed, visibility
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
    except Exception:
        raise HTTPException(status_code=503, detail="DB 데이터 조회에 실패했습니다.")

    if row is None:
        raise HTTPException(status_code=404, detail="관측 데이터가 없습니다.")

    # 상태 판정 기준 시각
    # as_of가 있으면 해당 시각, 없으면 현재 KST
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

    return {
        "code": "PARTIAL_SUCCESS",
        "message": "관측 데이터 조회 성공. 예측 모델 준비 중.",
        "data": {
            "station": {
                "station_id": row["stn_id"],
                "station_name": row["stn_ko"],
            },
            "request_context": {
                "forecast_interval_h": forecast_interval_h,
                "forecast_horizons_h": [forecast_interval_h * i for i in range(1, 5)],
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
            "forecast_timeline": [],
            "mission_evaluation": {
                "mission_type": mission_type,
                "rule_version": "maritime-transport-v1",
                "evaluation_status": "NOT_EVALUABLE",
                "passed": None,
                "mission_grade": "UNKNOWN",
                "factors": [],
                "reason_codes": ["FORECAST_NOT_READY"],
            },
            "diagnosis": {
                "fog_label": None,
                "pm_display_grade": None,
                "summary": "예측 모델 준비 중으로 종합 진단을 제공할 수 없습니다.",
            },
            "meta": {
                "request_id": f"req_{uuid.uuid4().hex}",
                "generated_at": datetime.now(KST).isoformat(),
                "partial": True,
            },
        },
    }
