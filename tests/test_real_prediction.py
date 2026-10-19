import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8000"
STATION_ID = "112"
AS_OF = "2022-01-01T01:00:00+09:00"


def is_valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


for interval in [1, 3, 6, 12]:
    params = urllib.parse.urlencode(
        {
            "forecast_interval_h": interval,
            "mission_type": "MARITIME_TRANSPORT",
            "as_of": AS_OF,
            "mock": "false",
        }
    )

    url = f"{BASE_URL}/api/v1/stations/" f"{STATION_ID}/dashboard?{params}"

    with urllib.request.urlopen(url, timeout=60) as response:
        assert response.status == 200
        result = json.load(response)

    assert result["code"] == "PARTIAL_SUCCESS"

    data = result["data"]
    timeline = data["forecast_timeline"]
    summary = data["forecast_summary"]
    evaluation = data["mission_evaluation"]
    meta = data["meta"]

    # 1. 실제 예측 여부
    assert meta["mock"] is False

    # 2. 예측 시점 4개 생성
    assert len(timeline) == 4, f"{interval}시간 간격: 예측 개수 {len(timeline)}개"

    expected_horizons = [interval * index for index in range(1, 5)]
    actual_horizons = [item["horizon_h"] for item in timeline]

    assert actual_horizons == expected_horizons

    # 3. 예측 시각 검증
    observed_at = datetime.fromisoformat(data["current"]["observed_at"])

    for item in timeline:
        expected_time = observed_at + timedelta(hours=item["horizon_h"])
        actual_time = datetime.fromisoformat(item["valid_at"])

        assert actual_time == expected_time

        # 4. 예측 수치 검증
        for field in [
            "visibility_pred_km",
            "pm25_pred_ug_m3",
            "pm10_pred_ug_m3",
        ]:
            assert is_valid_number(item[field]), (
                f"{interval}시간 / {field}: " f"{item[field]}"
            )

        # 5. 시정 등급 검증
        visibility = item["visibility_pred_km"]

        if visibility >= 10:
            expected_grade = "GOOD"
        elif visibility >= 4:
            expected_grade = "MODERATE"
        elif visibility >= 1:
            expected_grade = "BAD"
        else:
            expected_grade = "VERY_BAD"

        assert item["visibility_grade"] == expected_grade

    # 6. 최저 시정거리 요약 검증
    worst = min(timeline, key=lambda item: item["visibility_pred_km"])

    assert summary["horizon_h"] == worst["horizon_h"]
    assert summary["visibility_pred_km"] == worst["visibility_pred_km"]
    assert summary["selection_reason"] == "MIN_VISIBILITY"

    # 7. 임무 판정 검증 (임시 MVP 기준 1.0km)
    assert evaluation["evaluation_status"] == "EVALUATED"

    if summary["visibility_pred_km"] >= 1.0:
        assert evaluation["mission_grade"] == "NORMAL"
        assert evaluation["passed"] is True
    else:
        assert evaluation["mission_grade"] == "RESTRICTED"
        assert evaluation["passed"] is False

    print(
        f"PASS: interval={interval}, "
        f"horizons={actual_horizons}, "
        f"worst_visibility={summary['visibility_pred_km']}km, "
        f"mission={evaluation['mission_grade']}"
    )

print("모든 실제 CatBoost 예측 테스트 통과!")
