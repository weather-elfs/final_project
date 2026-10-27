"""기상청 단기예보·AirKorea PM2.5 예보를 수집하고 기존 테이블로 매칭한다."""

import json
import logging
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from backend.kma_weather import latest_forecast_base

KST = ZoneInfo("Asia/Seoul")

KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KMA_HUB_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "VilageFcstInfoService_2.0/getVilageFcst"
)
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


def request_items(url, params, *, timeout=15):
    """페이지 전체의 시간 제한 안에서 정상 응답·완전성을 검증한다."""
    records = []
    deadline = monotonic() + timeout
    for page in range(1, 5):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError()
        query = urllib.parse.urlencode({**params, "pageNo": page})
        with urllib.request.urlopen(url + "?" + query, timeout=remaining) as response:
            document = json.load(response)
        if not isinstance(document, dict) or not isinstance(
            document.get("response"), dict
        ):
            raise ValueError("예보 API 응답 구조 오류")
        payload = document["response"]
        if not isinstance(payload.get("header"), dict):
            raise ValueError("예보 API 결과 헤더 누락")
        if str(payload.get("header", {}).get("resultCode")) not in ("00", "0"):
            raise ValueError("예보 API 비정상 응답")
        body = payload.get("body", {})
        if not isinstance(body, dict):
            raise ValueError("예보 API 본문 구조 오류")
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise ValueError("예보 API 항목 구조 오류")
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
    """공공데이터 실패 시 API허브에서 같은 발표·격자의 예보를 검증한다."""
    base = latest_forecast_base(origin.replace(tzinfo=KST))
    nx, ny = GRIDS[station_id]
    params = {
        "dataType": "JSON",
        "numOfRows": 1000,
        "base_date": base.strftime("%Y%m%d"),
        "base_time": base.strftime("%H%M"),
        "nx": nx,
        "ny": ny,
    }
    providers = (
        ("DATA_GO_KR", KMA_URL, "serviceKey", os.getenv("DATA_API_KEY"), 8),
        (
            "KMA_APIHUB",
            KMA_HUB_URL,
            "authKey",
            os.getenv("KMA_API_KEY") or os.getenv("KMA_AUTH_KEY"),
            12,
        ),
    )
    last_error = ForecastError("KMA_FORECAST", "API_KEY_MISSING")
    for provider, url, key_name, key, timeout in providers:
        if not key:
            continue
        try:
            items = request_items(url, {**params, key_name: key}, timeout=timeout)
            rows = normalize_kma_items(items, origin, base, nx, ny)
            logging.getLogger("uvicorn.error").info(
                "[기상청 예보 수신] 경로 %s / 관측소 %s / 발표 %s / %s시간",
                provider,
                station_id,
                base.isoformat(),
                len(rows),
            )
            return rows
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            last_error = exc
            logging.getLogger("uvicorn.error").warning(
                "기상청 예보 경로 실패: %s / %s / HTTP %s",
                provider,
                type(exc).__name__,
                exc.code if isinstance(exc, urllib.error.HTTPError) else None,
            )
    raise last_error


def normalize_kma_items(items, origin, base, nx, ny):
    """두 경로에 동일한 발표시각·격자·항목·수치 검증을 적용한다."""
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
        weather = cur.fetchall()
        cur.execute(
            """SELECT DISTINCT ON (target_date) * FROM public.raw_air_pm25_forecast
            WHERE target_date=ANY(%s) AND announce_time <= %s
            ORDER BY target_date, announce_time DESC""",
            ([t.date() for t in targets], origin),
        )
        air = cur.fetchall()
    return match_forecasts(weather, air, origin, horizons)


def match_forecasts(weather_rows, air_rows, origin, horizons, allow_missing=False):
    """수집 경로와 과거 DB 조회가 같은 공개 시각·대상 시각·입력 변환을 사용한다."""
    weather, air = {}, {}
    for row in weather_rows:
        target, issued = row["fcst_time_kst"], row["base_time_kst"]
        if issued <= origin - timedelta(minutes=20) and (
            target not in weather or issued > weather[target]["base_time_kst"]
        ):
            weather[target] = row
    for row in air_rows:
        target, issued = row["target_date"], row["announce_time"]
        if issued <= origin and (
            target not in air or issued > air[target]["announce_time"]
        ):
            air[target] = row
    result = {}
    for h in horizons:
        target = origin + timedelta(hours=h)
        w, a = weather.get(target), air.get(target.date())
        if w and origin - w["base_time_kst"] > timedelta(hours=6):
            w = None
        if a and origin - a["announce_time"] > timedelta(hours=24):
            a = None
        if not allow_missing and (not w or not a):
            raise ForecastError("FORECAST", "TARGET_MISSING_OR_STALE")
        values = {
            f"future_fcst_{name}": (
                float(w[column]) if w and w.get(column) is not None else float("nan")
            )
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
        missing = []
        if any(not math.isfinite(v) for v in values.values()):
            missing.append("KMA_FORECAST")
        grade = a.get("fcst_pm25_grade") if a else None
        if grade not in (1, 2, 3, 4):
            missing.append("AIRKOREA_FORECAST")
        if missing and not allow_missing:
            raise ForecastError("FORECAST", "INVALID_VALUE")
        degrees = values["future_fcst_wind_dir"]
        values.update(
            future_fcst_wind_dir_sin=round(math.sin(math.radians(degrees)), 4),
            future_fcst_wind_dir_cos=round(math.cos(math.radians(degrees)), 4),
            future_fcst_pm25_grade=grade if grade in (1, 2, 3, 4) else float("nan"),
            fcst_age_h=(
                (origin - w["base_time_kst"]).total_seconds() / 3600
                if w
                else float("nan")
            ),
        )
        result[h] = {
            "values": values,
            "valid_at": target.replace(tzinfo=KST).isoformat(),
            "kma_issued_at": (
                w["base_time_kst"].replace(tzinfo=KST).isoformat() if w else None
            ),
            "airkorea_issued_at": (
                a["announce_time"].replace(tzinfo=KST).isoformat() if a else None
            ),
            "missing_sources": missing,
        }
    return result
