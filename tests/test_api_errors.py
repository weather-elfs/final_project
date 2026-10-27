import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = "/api/v1/stations/{station_id}/dashboard"


def check_error(station_id, params, expected_status, expected_code):
    query = urllib.parse.urlencode(params)
    url = BASE_URL + ENDPOINT.format(station_id=station_id) + "?" + query

    try:
        with urllib.request.urlopen(url, timeout=30):
            raise AssertionError("오류 응답을 예상했지만 요청이 성공했습니다.")

    except urllib.error.HTTPError as error:
        body = json.load(error)

        assert error.code == expected_status, f"HTTP 상태 코드 불일치: {error.code}"
        assert body["code"] == expected_code, f"오류 코드 불일치: {body['code']}"
        assert body["message"], "오류 메시지가 없습니다."
        assert body["data"]["meta"]["request_id"].startswith("req_")

        print(f"PASS: HTTP {expected_status}, " f"code={expected_code}")


BASE_PARAMS = {
    "forecast_interval_h": 3,
    "mission_type": "MARITIME_TRANSPORT",
    "as_of": "2022-01-01T01:00:00+09:00",
    "mock": "false",
}

# TEST 1: 존재하지 않는 관측소
check_error(
    "99999",
    BASE_PARAMS,
    404,
    "STATION_NOT_FOUND",
)

# TEST 2: 지원하지 않는 예측 간격
check_error(
    "112",
    {**BASE_PARAMS, "forecast_interval_h": 2},
    422,
    "INVALID_PARAMETER",
)

# TEST 3: 지원하지 않는 임무 유형
check_error(
    "112",
    {**BASE_PARAMS, "mission_type": "INVALID_MISSION"},
    422,
    "INVALID_PARAMETER",
)

# TEST 4: 관측 데이터 없음
check_error(
    "112",
    {**BASE_PARAMS, "as_of": "2010-01-01T01:00:00+09:00"},
    404,
    "OBSERVATION_NOT_FOUND",
)

print("모든 API 오류 응답 테스트 통과!")
