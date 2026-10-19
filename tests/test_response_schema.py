import json
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"

params = urllib.parse.urlencode(
    {
        "forecast_interval_h": 3,
        "mission_type": "MARITIME_TRANSPORT",
        "as_of": "2022-01-01T01:00:00+09:00",
        "mock": "false",
    }
)

url = f"{BASE_URL}/api/v1/stations/112/dashboard?" f"{params}"

with urllib.request.urlopen(url, timeout=60) as response:
    assert response.status == 200
    result = json.load(response)

# 1. 최상위 응답 구조
assert isinstance(result["code"], str)
assert isinstance(result["message"], str)
assert isinstance(result["data"], dict)

data = result["data"]

# 2. 주요 섹션 존재 여부
required_sections = [
    "station",
    "request_context",
    "current",
    "marine",
    "source_status",
    "forecast_timeline",
    "forecast_summary",
    "mission_evaluation",
    "diagnosis",
    "meta",
]

for section in required_sections:
    assert section in data, f"누락된 섹션: {section}"

print("PASS: 주요 응답 섹션 10개")

# 3. 예측 타임라인 필드 및 자료형
timeline = data["forecast_timeline"]
assert isinstance(timeline, list)
assert len(timeline) == 4

required_forecast_fields = [
    "horizon_h",
    "valid_at",
    "visibility_pred_km",
    "visibility_grade",
    "fog_grade_label",
    "pm25_pred_ug_m3",
    "pm10_pred_ug_m3",
]

for forecast in timeline:
    for field in required_forecast_fields:
        assert field in forecast, f"예측 필드 누락: {field}"

    assert isinstance(forecast["horizon_h"], int)
    assert isinstance(forecast["valid_at"], str)
    assert isinstance(forecast["visibility_pred_km"], (int, float))
    assert isinstance(forecast["visibility_grade"], str)
    assert isinstance(forecast["fog_grade_label"], str)

    for field in ["pm25_pred_ug_m3", "pm10_pred_ug_m3"]:
        assert forecast[field] is None or isinstance(forecast[field], (int, float))

print("PASS: 예측 타임라인 필드 및 자료형")

# 4. 최저 시정거리 요약
summary = data["forecast_summary"]
assert isinstance(summary, dict)
assert summary["selection_reason"] == "MIN_VISIBILITY"
assert isinstance(summary["visibility_pred_km"], (int, float))

print("PASS: 예측 요약 구조")

# 5. 임무 판정
evaluation = data["mission_evaluation"]

assert evaluation["mission_type"] == "MARITIME_TRANSPORT"
assert evaluation["evaluation_status"] in [
    "EVALUATED",
    "NOT_EVALUABLE",
]
assert evaluation["mission_grade"] in [
    "NORMAL",
    "CAUTION",
    "RESTRICTED",
    "UNKNOWN",
]
assert isinstance(evaluation["factors"], list)
assert isinstance(evaluation["reason_codes"], list)

print("PASS: 임무 판정 구조")

# 6. 진단 및 메타데이터
diagnosis = data["diagnosis"]
meta = data["meta"]

assert "fog_label" in diagnosis
assert "pm_display_grade" in diagnosis
assert "summary" in diagnosis

assert isinstance(meta["request_id"], str)
assert isinstance(meta["generated_at"], str)
assert isinstance(meta["partial"], bool)
assert isinstance(meta["mock"], bool)

print("PASS: 진단 및 메타데이터 구조")
print("API 응답 스키마 테스트 통과!")
