"""기상청 단기예보 조회서비스 연동 모듈."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

BASE_URL = "https://apihub.kma.go.kr/api/typ02/openApi/" "VilageFcstInfoService_2.0"

SKY_LABELS = {
    "1": "맑음",
    "3": "구름많음",
    "4": "흐림",
}

PTY_LABELS = {
    "0": None,
    "1": "비",
    "2": "비 또는 눈",
    "3": "눈",
    "4": "소나기",
    "5": "빗방울",
    "6": "빗방울 또는 눈날림",
    "7": "눈날림",
}


def weather_label(sky=None, pty=None):
    """하늘상태와 강수형태를 날씨 문구로 변환."""
    if pty is not None:
        precipitation = PTY_LABELS.get(str(pty))
        if precipitation:
            return precipitation

    if sky is not None:
        return SKY_LABELS.get(str(sky))

    return None


def fetch_kma_items(endpoint, nx, ny, base_date, base_time):
    """기상청 API를 호출하고 항목 목록을 반환."""
    api_key = os.getenv("KMA_API_KEY")

    if not api_key:
        raise RuntimeError("KMA_API_KEY 환경변수가 설정되지 않았습니다.")

    allowed_endpoints = {
        "getUltraSrtNcst",
        "getUltraSrtFcst",
        "getVilageFcst",
    }

    if endpoint not in allowed_endpoints:
        raise ValueError("지원하지 않는 기상청 API입니다.")

    params = {
        "authKey": api_key,
        "numOfRows": 1000,
        "pageNo": 1,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/{endpoint}?{query}"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "WeatherElfs-Backend/0.1"},
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("기상청 API 호출에 실패했습니다.") from exc

    header = payload.get("response", {}).get("header", {})
    if str(header.get("resultCode")) not in ("00", "0"):
        raise RuntimeError(
            f"기상청 API 응답 오류: {header.get('resultMsg', 'UNKNOWN')}"
        )

    body = payload.get("response", {}).get("body", {})
    items = body.get("items", {})

    if not isinstance(items, dict):
        return []

    return items.get("item", [])


def latest_observation_base(now=None):
    """초단기실황 발표 시각 계산(매시각 10분 이후 제공)."""
    now = now or datetime.now(KST)
    hour = now.replace(minute=0, second=0, microsecond=0)

    if now.minute < 15:
        hour -= timedelta(hours=1)

    return hour.strftime("%Y%m%d"), hour.strftime("%H00")


def parse_observation(items):
    """초단기실황 항목을 필드별 딕셔너리로 변환."""
    values = {
        item["category"]: item.get("obsrValue") for item in items if "category" in item
    }

    return {
        "temperature_c": _number(values.get("T1H")),
        "relative_humidity_pct": _number(values.get("REH")),
        "wind_speed_m_s": _number(values.get("WSD")),
        "wind_direction_deg": _number(values.get("VEC")),
        "precipitation_type": values.get("PTY"),
        "precipitation_1h_mm": _number(values.get("RN1")),
    }


def _number(value):
    if value in (None, "", "-", "null"):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not -900 < number < 900:
        return None

    return number


def wind_direction_label(degrees):
    """풍향 각도를 16방위 한글 이름으로 변환."""
    if degrees is None:
        return None

    directions = [
        "북풍",
        "북북동풍",
        "북동풍",
        "동북동풍",
        "동풍",
        "동남동풍",
        "남동풍",
        "남남동풍",
        "남풍",
        "남남서풍",
        "남서풍",
        "서남서풍",
        "서풍",
        "서북서풍",
        "북서풍",
        "북북서풍",
    ]

    index = int((float(degrees) % 360 + 11.25) // 22.5) % 16
    return directions[index]


def asos_wind_direction(wd):
    """ASOS WD(10도 단위)를 각도와 16방위 이름으로 변환."""
    if wd is None:
        return {
            "wind_direction_deg": None,
            "wind_direction_label": None,
        }

    try:
        value = float(wd)
    except (TypeError, ValueError):
        return {
            "wind_direction_deg": None,
            "wind_direction_label": None,
        }

    if not 0 <= value <= 36:
        return {
            "wind_direction_deg": None,
            "wind_direction_label": None,
        }

    degrees = value * 10

    return {
        "wind_direction_deg": degrees,
        "wind_direction_label": wind_direction_label(degrees),
    }
