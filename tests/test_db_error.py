import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.main import app


def simulate_db_failure():
    raise ConnectionError("테스트용 DB 연결 실패")


client = TestClient(app)

with patch(
    "backend.main.get_connection",
    side_effect=simulate_db_failure,
):
    response = client.get(
        "/api/v1/stations/112/dashboard",
        params={
            "forecast_interval_h": 3,
            "mission_type": "MARITIME_TRANSPORT",
            "as_of": "2022-01-01T01:00:00+09:00",
            "mock": "false",
        },
    )

assert response.status_code == 503, response.text

body = response.json()

assert body["code"] == "DB_ERROR"
assert body["message"] == "DB 데이터 조회에 실패했습니다."
assert body["data"]["meta"]["request_id"].startswith("req_")

print("PASS: DB 연결 실패 → HTTP 503")
print("PASS: 오류 코드 DB_ERROR")
print("PASS: 공통 오류 응답 구조")
print("DB 장애 대응 테스트 통과!")
