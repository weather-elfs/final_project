import csv
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

CSV_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend_airkorea_test"
    / "data"
    / "airkorea_latest.csv"
)

STATION_CODES = {
    "102": "831492",  # 백령도
    "112": "823632",  # 인천(숭의)
    "201": "831481",  # 강화도(석모리)
}


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def read_live_airkorea(station_id, reference_time):
    code = STATION_CODES.get(str(station_id))

    if code is None or not CSV_PATH.is_file():
        return None

    if reference_time.tzinfo is not None:
        anchor = reference_time.astimezone(KST).replace(tzinfo=None)
    else:
        anchor = reference_time

    hourly = {}

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("측정소코드", "")).strip() != code:
                continue

            try:
                raw_time = row["날짜"].strip()
                # AirKorea sometimes represents midnight as 24:00.
                if raw_time.endswith(" 24:00"):
                    tm = datetime.strptime(raw_time[:10], "%Y-%m-%d") + timedelta(days=1)
                else:
                    tm = datetime.fromisoformat(raw_time)
                if tm.tzinfo is not None:
                    tm = tm.astimezone(KST).replace(tzinfo=None)
            except (KeyError, ValueError, TypeError):
                continue

            # 기준시각 이후 관측자료 사용 금지
            if tm > anchor:
                continue

            hourly[tm] = (
                _number(row.get("PM2.5")),
                _number(row.get("PM10")),
            )

    if not hourly:
        return None

    latest_time = max(hourly)
    latest_pm25, latest_pm10 = hourly[latest_time]

    # 최근 12시간 자료: 최신 관측시각부터 역순
    history = [
        hourly.get(
            latest_time - timedelta(hours=i),
            (None, None),
        )
        for i in range(12)
    ]

    return {
        "current": {
            "observed_at": latest_time.replace(tzinfo=KST).isoformat(),
            "pm25_ug_m3": latest_pm25,
            "pm10_ug_m3": latest_pm10,
        },
        "pm25_history": [x[0] for x in history],
        "pm10_history": [x[1] for x in history],
    }
