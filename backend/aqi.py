import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

BREAKPOINTS = {
    "pm25": [
        (0.0, 9.0, 0, 50),
        (9.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 125.4, 151, 200),
        (125.5, 225.4, 201, 300),
        (225.5, 325.4, 301, 500),
    ],
    "pm10": [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 604, 301, 500),
    ],
}


def _concentration(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def nowcast(values):
    # 최신 시간부터 과거 12시간 순서
    values = list(values)[:12]
    values += [None] * (12 - len(values))
    values = [_concentration(v) for v in values]

    if sum(v is not None for v in values[:3]) < 2:
        return None

    valid = [v for v in values if v is not None]
    maximum = max(valid)
    if min(valid) == maximum:
        return maximum
    weight = max(0.5, min(valid) / maximum) if maximum > 0 else 1.0

    numerator = math.fsum(v * weight**i for i, v in enumerate(values) if v is not None)
    denominator = math.fsum(weight**i for i, v in enumerate(values) if v is not None)
    return numerator / denominator


def pm_to_aqi(concentration, pollutant):
    concentration = _concentration(concentration)
    if concentration is None:
        return None

    precision = "0.1" if pollutant == "pm25" else "1"
    value = Decimal(str(concentration)).quantize(
        Decimal(precision), rounding=ROUND_DOWN
    )

    # EPA May 2026: AQI > 500 keeps the final interval's slope, not a 500 cap.
    # https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf
    for low, high, aqi_low, aqi_high in BREAKPOINTS[pollutant]:
        if Decimal(str(low)) <= value <= Decimal(str(high)) or (
            high == BREAKPOINTS[pollutant][-1][1] and value > Decimal(str(high))
        ):
            index = (Decimal(aqi_high) - Decimal(aqi_low)) / (
                Decimal(str(high)) - Decimal(str(low))
            ) * (value - Decimal(str(low))) + Decimal(aqi_low)
            return int(index.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return None


def calculate_current_aqi(pm25_hourly, pm10_hourly):
    pm25 = pm_to_aqi(nowcast(pm25_hourly), "pm25")
    pm10 = pm_to_aqi(nowcast(pm10_hourly), "pm10")

    result = {
        "standard": "US_EPA",
        "basis": "NOWCAST_CURRENT",
        "pm25_subindex": pm25,
        "pm10_subindex": pm10,
        "value": None,
        "dominant_pollutant": None,
        "display_level": None,
        "display_grade": None,
        "status": "insufficient_data",
    }

    if pm25 is None or pm10 is None:
        return result

    value = max(pm25, pm10)

    if value <= 100:
        level, grade = 1, "양호"
    elif value <= 150:
        level, grade = 2, "민감군 주의"
    elif value <= 200:
        level, grade = 3, "나쁨"
    elif value <= 300:
        level, grade = 4, "매우 나쁨"
    else:
        level, grade = 5, "위험"

    result.update(
        {
            "value": value,
            "dominant_pollutant": "PM2.5" if pm25 >= pm10 else "PM10",
            "display_level": level,
            "display_grade": grade,
            "status": "calculated",
        }
    )

    return result
