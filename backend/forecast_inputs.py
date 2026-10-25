"""기상청 단기예보·AirKorea PM2.5 예보를 수집하고 기존 테이블로 매칭한다."""

import json
import math
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.kma_weather import latest_forecast_base

KST = ZoneInfo("Asia/Seoul")

KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMinuDustFrcstDspth"
# 전달 모델의 PIT 마트 수집 격자와 일치한다.
GRIDS = {"102": (21, 136), "112": (54, 125), "201": (51, 130)}
DONGS = {"102": "백령면", "112": "동인천동", "201": "불은면"}
FIELDS = {
    "TMP": "tmp_1h",
    "REH": "reh",
    "WSD": "wsd",
    "VEC": "vec",
    "PCP": "pcp_1h",
    "POP": "pop",
    "PTY": "pty",
    "SKY": "sky",
}
GRADES = {"좋음": 1, "보통": 2, "나쁨": 3, "매우나쁨": 4}


class ForecastError(ValueError):
    """인증 URL이나 원본 응답을 노출하지 않는 예보 검증 오류."""

    def __init__(self, source, reason):
        super().__init__(f"{source}: {reason}")
        self.source, self.reason = source, reason


def request_items(url, params):
    """정상 응답 및 페이지 완전성을 검증한다."""
    records = []
    for page in range(1, 5):
        query = urllib.parse.urlencode({**params, "pageNo": page})
        with urllib.request.urlopen(url + "?" + query, timeout=15) as response:
            payload = json.load(response).get("response", {})
        if str(payload.get("header", {}).get("resultCode")) not in ("00", "0"):
            raise ValueError("예보 API 비정상 응답")
        body = payload.get("body", {})
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        records.extend(items)
        if len(records) >= int(body.get("totalCount", len(records))):
            return records
        if not items:
            break
    raise ValueError("예보 API 페이지 누락")


def precipitation(value):
    """학습 마트와 동일한 PCP 구간 하한(mm)을 사용한다."""
    if value in ("강수없음", "1mm 미만"):
        return 0.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:~\d+(?:\.\d+)?)?mm(?: 이상)?", str(value))
    if match:
        return float(match[1])
    return float(value)


def collect_kma(station_id, origin):
    """관측 기준시각에 공개돼 있었던 단기예보를 가져온다."""
    key = os.getenv("DATA_API_KEY")
    if not key:
        raise ForecastError("KMA_FORECAST", "API_KEY_MISSING")
    base = latest_forecast_base(origin.replace(tzinfo=KST))
    nx, ny = GRIDS[station_id]
    items = request_items(
        KMA_URL,
        {
            "serviceKey": key,
            "dataType": "JSON",
            "numOfRows": 1000,
            "base_date": base.strftime("%Y%m%d"),
            "base_time": base.strftime("%H%M"),
            "nx": nx,
            "ny": ny,
        },
    )
    rows = {}
    for item in items:
        if (int(item["nx"]), int(item["ny"])) != (nx, ny):
            raise ValueError("단기예보 격자 불일치")
        issued = datetime.strptime(item["baseDate"] + item["baseTime"], "%Y%m%d%H%M")
        if issued != base.replace(tzinfo=None):
            raise ValueError("단기예보 발표시각 불일치")
        valid = datetime.strptime(item["fcstDate"] + item["fcstTime"], "%Y%m%d%H%M")
        if not origin < valid <= origin + timedelta(hours=48):
            continue
        category = item["category"]
        if category not in FIELDS:
            continue
        value = (
            precipitation(item["fcstValue"])
            if category == "PCP"
            else float(item["fcstValue"])
        )
        if not math.isfinite(value) or (category != "TMP" and value < 0):
            raise ValueError("단기예보 비정상 수치")
        if (
            category == "REH"
            and not 0 < value <= 100
            or category == "VEC"
            and value > 360
            or category == "POP"
            and value > 100
            or category == "SKY"
            and value not in (1, 3, 4)
            or category == "PTY"
            and value not in (0, 1, 2, 3, 4)
        ):
            raise ValueError("단기예보 범위 밖 수치")
        row = rows.setdefault(valid, {"base_time_kst": issued, "fcst_time_kst": valid})
        column = FIELDS[category]
        if column in row and row[column] != value:
            raise ValueError("단기예보 중복값 불일치")
        row[column] = value
    if not rows or any(not set(FIELDS.values()) <= row.keys() for row in rows.values()):
        raise ValueError("단기예보 필수 항목 누락")
    return list(rows.values())


def collect_air(origin):
    """관측시각 이전 발표된 인천 PM2.5 예보 등급만 수집한다."""
    key = os.getenv("AIRKOREA_API_KEY") or os.getenv("DATA_API_KEY")
    if not key:
        raise ForecastError("AIRKOREA_FORECAST", "API_KEY_MISSING")
    rows = {}
    # 자정에도 전일 23시 발표분을 찾을 수 있도록 두 날짜를 조회한다.
    for day in (origin - timedelta(days=1), origin):
        items = request_items(
            AIR_URL,
            {
                "serviceKey": key,
                "returnType": "json",
                "numOfRows": 100,
                "searchDate": day.strftime("%Y-%m-%d"),
                "informCode": "PM25",
            },
        )
        for item in items:
            if item.get("informCode") != "PM25":
                continue
            issued = datetime.strptime(item["dataTime"], "%Y-%m-%d %H시 발표")
            if issued > origin or origin - issued > timedelta(hours=24):
                continue
            region_grades = dict(
                re.findall(r"([^,:]+)\s*:\s*([^,]+)", item.get("informGrade") or "")
            )
            grade = GRADES.get(
                next(
                    (
                        v.strip()
                        for k, v in region_grades.items()
                        if k.strip() == "인천"
                    ),
                    "",
                )
            )
            if grade is None:
                continue
            target = datetime.strptime(item["informData"], "%Y-%m-%d").date()
            rows[(issued, target)] = {
                "announce_time": issued,
                "target_date": target,
                "fcst_pm25_grade": grade,
            }
    if not rows:
        raise ValueError("사용 가능한 PM2.5 지역 예보 없음")
    return list(rows.values())


def collect_forecasts(station_id, origin, horizons):
    """두 기관을 병렬 수집하고 요청한 모든 대상시각을 검증한다."""
    result = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            "KMA_FORECAST": pool.submit(collect_kma, station_id, origin),
            "AIRKOREA_FORECAST": pool.submit(collect_air, origin),
        }
        for source, future in futures.items():
            try:
                result[source] = future.result()
            except ForecastError:
                raise
            except Exception as exc:
                raise ForecastError(source, "COLLECTION_FAILED") from exc
    kma_times = {row["fcst_time_kst"] for row in result["KMA_FORECAST"]}
    air_dates = {row["target_date"] for row in result["AIRKOREA_FORECAST"]}
    result["expected"] = {}
    for h in horizons:
        target = origin + timedelta(hours=h)
        if target not in kma_times or target.date() not in air_dates:
            raise ForecastError("FORECAST", "TARGET_TIME_MISSING")
        result["expected"][h] = {
            "kma_issued_at": next(
                row["base_time_kst"]
                for row in result["KMA_FORECAST"]
                if row["fcst_time_kst"] == target
            )
            .replace(tzinfo=KST)
            .isoformat(),
            "airkorea_issued_at": max(
                row["announce_time"]
                for row in result["AIRKOREA_FORECAST"]
                if row["target_date"] == target.date()
            )
            .replace(tzinfo=KST)
            .isoformat(),
        }
    return result


def store_forecasts(conn, station_id, forecasts):
    """관측 적재와 같은 트랜잭션으로 기존 예보 테이블에 upsert한다."""
    count = {}
    columns = [
        "dong",
        "base_time_kst",
        "fcst_lead_time",
        "fcst_time_kst",
        *FIELDS.values(),
    ]
    keys = {"dong", "base_time_kst", "fcst_lead_time", "fcst_time_kst"}
    sql = f"""INSERT INTO public.tb_kma_short_forecast ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
        ON CONFLICT (dong, fcst_time_kst, base_time_kst, fcst_lead_time) DO UPDATE SET
        {', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c not in keys)}"""
    with conn.cursor() as cur:
        count["KMA_FORECAST"] = 0
        for item in forecasts["KMA_FORECAST"]:
            row = {
                **item,
                "dong": DONGS[station_id],
                "fcst_lead_time": (
                    item["fcst_time_kst"] - item["base_time_kst"]
                ).total_seconds()
                / 3600,
            }
            cur.execute(sql, tuple(row[c] for c in columns))
            count["KMA_FORECAST"] += cur.rowcount
        count["AIRKOREA_FORECAST"] = 0
        for row in forecasts["AIRKOREA_FORECAST"]:
            cur.execute(
                """INSERT INTO public.raw_air_pm25_forecast
                (announce_time, target_date, fcst_pm25_grade) VALUES (%s,%s,%s)
                ON CONFLICT (announce_time, target_date) DO UPDATE SET
                fcst_pm25_grade=EXCLUDED.fcst_pm25_grade""",
                (row["announce_time"], row["target_date"], row["fcst_pm25_grade"]),
            )
            count["AIRKOREA_FORECAST"] += cur.rowcount
    return count


def read_forecasts(conn, station_id, origin, horizons):
    """공개 시점·대상시각으로 DB 예보를 매칭하고 모델 입력 및 계보를 반환한다."""
    targets = [origin + timedelta(hours=h) for h in horizons]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (fcst_time_kst) * FROM public.tb_kma_short_forecast
            WHERE dong=%s AND fcst_time_kst=ANY(%s) AND base_time_kst <= %s
            ORDER BY fcst_time_kst, base_time_kst DESC""",
            (DONGS[station_id], targets, origin - timedelta(minutes=20)),
        )
        weather = {row["fcst_time_kst"]: row for row in cur.fetchall()}
        cur.execute(
            """SELECT DISTINCT ON (target_date) * FROM public.raw_air_pm25_forecast
            WHERE target_date=ANY(%s) AND announce_time <= %s
            ORDER BY target_date, announce_time DESC""",
            ([t.date() for t in targets], origin),
        )
        air = {row["target_date"]: row for row in cur.fetchall()}
    result = {}
    for h, target in zip(horizons, targets):
        w, a = weather.get(target), air.get(target.date())
        if (
            not w
            or not a
            or origin - w["base_time_kst"] > timedelta(hours=6)
            or origin - a["announce_time"] > timedelta(hours=24)
        ):
            raise ForecastError("FORECAST", "DB_TARGET_MISSING_OR_STALE")
        values = {
            f"future_fcst_{name}": float(w[column]) if w[column] is not None else None
            for name, column in {
                "temp": "tmp_1h",
                "humidity": "reh",
                "wind_speed": "wsd",
                "wind_dir": "vec",
                "precipitation": "pcp_1h",
                "pop": "pop",
                "pty": "pty",
                "sky": "sky",
            }.items()
        }
        if any(v is None or not math.isfinite(v) for v in values.values()) or a[
            "fcst_pm25_grade"
        ] not in (1, 2, 3, 4):
            raise ForecastError("FORECAST", "DB_INVALID_VALUE")
        degrees = values["future_fcst_wind_dir"]
        values.update(
            future_fcst_wind_dir_sin=round(math.sin(math.radians(degrees)), 4),
            future_fcst_wind_dir_cos=round(math.cos(math.radians(degrees)), 4),
            future_fcst_pm25_grade=a["fcst_pm25_grade"],
            fcst_age_h=(origin - w["base_time_kst"]).total_seconds() / 3600,
        )
        result[h] = {
            "values": values,
            "valid_at": target.replace(tzinfo=KST).isoformat(),
            "kma_issued_at": w["base_time_kst"].replace(tzinfo=KST).isoformat(),
            "airkorea_issued_at": a["announce_time"].replace(tzinfo=KST).isoformat(),
        }
    return result
