import json
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
STATION_ID = "112"
AS_OF = "2022-01-01T01:00:00+09:00"

for interval in [1, 3, 6, 12]:
    params = urllib.parse.urlencode(
        {
            "forecast_interval_h": interval,
            "mission_type": "MARITIME_TRANSPORT",
            "as_of": AS_OF,
            "mock": "true",
        }
    )

    url = f"{BASE_URL}/api/v1/stations/" f"{STATION_ID}/dashboard?{params}"

    with urllib.request.urlopen(url, timeout=30) as response:
        result = json.load(response)

    # API 응답 구조
    data = result.get("data", result)

    timeline = data["forecast_timeline"]
    summary = data["forecast_summary"]
    evaluation = data["mission_evaluation"]
    meta = data["meta"]

    expected_horizons = [interval * index for index in range(1, 5)]
    actual_horizons = [item["horizon_h"] for item in timeline]

    assert actual_horizons == expected_horizons, (
        f"interval={interval}: " f"{actual_horizons} != {expected_horizons}"
    )

    assert meta["mock"] is True
    assert summary["horizon_h"] == interval * 3
    assert summary["visibility_pred_km"] == 0.8
    assert summary["selection_reason"] == "MIN_VISIBILITY"
    assert evaluation["evaluation_status"] == "NOT_EVALUABLE"
    assert evaluation["reason_codes"] == ["MOCK_DATA"]

    print(
        f"PASS: interval={interval}, "
        f"horizons={actual_horizons}, "
        f"worst_horizon={summary['horizon_h']}"
    )

print("모든 Mock 예측 시간 간격 테스트 통과!")
